"""
bot_llm.py — Pluggable LLM backend abstraction.

Wraps the existing taris CLI call in a clean interface that the web app
can import without pulling in Telegram dependencies.

Feature 3.1: LLM_PROVIDER env-var switch (taris | openai | yandexgpt | gemini | anthropic | local)
Feature 3.2: Local llama.cpp offline fallback with LLM_LOCAL_FALLBACK=1
"""

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from core.bot_config import (
    ACTIVE_MODEL_FILE,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLAMA_CPP_MODEL,
    LLAMA_CPP_URL,
    LOCAL_MAX_TOKENS,
    LOCAL_TEMPERATURE,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MIN_TIMEOUT,
    OLLAMA_NUM_CTX,
    OLLAMA_THINK,
    LLM_LOCAL_FALLBACK,
    LLM_FALLBACK_FLAG_FILE,
    LLM_FALLBACK_PROVIDER,
    LLM_PROVIDER,
    OLLAMA_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENCLAW_BIN,
    OPENCLAW_SESSION,
    OPENCLAW_TIMEOUT,
    TARIS_BIN,
    TARIS_CONFIG,
    YANDEXGPT_API_KEY,
    YANDEXGPT_FOLDER_ID,
    YANDEXGPT_MAX_TOKENS,
    YANDEXGPT_MODEL_URI,
    YANDEXGPT_TEMPERATURE,
    LLM_PER_FUNC_FILE,
    log_assistant as log,
)


# ─────────────────────────────────────────────────────────────────────────────
# Per-function LLM override
# ─────────────────────────────────────────────────────────────────────────────
# Stored in llm_per_func.json: {"system": "openai", "chat": "ollama", ...}
# Empty string or missing key → use global LLM_PROVIDER.
# Supported use_case values: "system" (admin system chat), "chat" (user free chat).


def _effective_temperature() -> float:
    """Return runtime LLM temperature from rag_settings; falls back to LOCAL_TEMPERATURE."""
    try:
        from core.rag_settings import get as _rget
        return float(_rget("llm_temperature"))
    except Exception:
        return LOCAL_TEMPERATURE


def get_per_func_provider(use_case: str) -> str:
    """Return admin-set provider for this use_case, or '' for global default."""
    try:
        d = json.loads(Path(LLM_PER_FUNC_FILE).read_text(encoding="utf-8"))
        return d.get(use_case, "")
    except Exception:
        return ""


def set_per_func_provider(use_case: str, provider: str) -> None:
    """Set or clear per-function LLM provider override. Empty provider → resets to global."""
    try:
        try:
            d = json.loads(Path(LLM_PER_FUNC_FILE).read_text(encoding="utf-8"))
        except Exception:
            d = {}
        if provider:
            d[use_case] = provider
        else:
            d.pop(use_case, None)
        Path(LLM_PER_FUNC_FILE).write_text(json.dumps(d, indent=2, ensure_ascii=False),
                                            encoding="utf-8")
        log.info(f"[LLM] per-func override: {use_case} = {provider or '(global)'}")
    except Exception as e:
        log.warning(f"[LLM] set_per_func_provider failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Active model
# ─────────────────────────────────────────────────────────────────────────────

def get_active_model() -> str:
    """Return the admin-selected model name or empty string.

    Strips provider prefixes (e.g. ``openai/gpt-4o-mini`` → ``gpt-4o-mini``)
    that are valid in some UIs but cause HTTP 400 when passed to the API.
    """
    try:
        raw = Path(ACTIVE_MODEL_FILE).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    # Strip "<provider>/" prefix written by some admin-UI paths
    if "/" in raw:
        _, _, rest = raw.partition("/")
        log.debug(f"[LLM] active_model stripped provider prefix: '{raw}' → '{rest}'")
        return rest
    return raw


def set_active_model(name: str) -> None:
    Path(ACTIVE_MODEL_FILE).write_text(name, encoding="utf-8")


def list_models() -> list[dict]:
    """Read model_list from taris config.json."""
    try:
        cfg = json.loads(Path(TARIS_CONFIG).read_text(encoding="utf-8"))
        return cfg.get("model_list", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Output cleaning  (ported from telegram.bot_access._clean_taris_output)
# ─────────────────────────────────────────────────────────────────────────────

_ANSI_RE     = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_SPINNER_RE  = re.compile(r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⣾⣽⣻⢿⡿⣟⣯⣷◐◑◒◓⠁⠂⠄⡀⢀⠠⠐⠈]")  # ASCII |/\- removed: not spinner chars
_PRINTF_WRAP = re.compile(r"^printf\s+['\"](.+)['\"]\s*$", re.DOTALL)
_LOG_PREFIX  = re.compile(r"^(?:\d{4}[/-]\d{2}[/-]\d{2}|\d{8})[\sT]\d{2}:\d{2}:\d{2}\s*(?:INFO|DEBUG|WARN|ERROR)?\s*", re.MULTILINE)
_PIPE_HEADER = re.compile(r"^(agent|taris)\s*[|│]", re.MULTILINE | re.IGNORECASE)


def _clean_output(raw: str) -> str:
    text = _ANSI_RE.sub("", raw)
    text = _SPINNER_RE.sub("", text)
    text = _LOG_PREFIX.sub("", text)
    text = _PIPE_HEADER.sub("", text)
    m = _PRINTF_WRAP.match(text.strip())
    if m:
        text = m.group(1)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Provider clients
# ─────────────────────────────────────────────────────────────────────────────

def _raise_if_http_error(text: str) -> None:
    """Raise a descriptive RuntimeError if text contains a known HTTP error pattern.

    The taris binary may exit with rc=0 but embed the HTTP error message in
    its stdout rather than setting a non-zero exit code.  Called on both the
    rc!=0 (stderr) and rc=0 (stdout) paths in _ask_taris so the caller
    always receives a proper exception instead of an error string returned as
    an LLM answer.
    """
    lo = text.lower()
    if "payment required" in lo:
        raise RuntimeError("taris: 402 Payment Required")
    if "too many requests" in lo:
        raise RuntimeError("taris: 429 Too Many Requests")
    if "unauthorized" in lo and len(text) < 300:
        raise RuntimeError("taris: 401 Unauthorized")
    if "service unavailable" in lo and len(text) < 300:
        raise RuntimeError("taris: 503 Service Unavailable")


def _ask_taris(prompt: str, timeout: int) -> str:
    """Call taris CLI (wraps OpenRouter or configured LLM)."""
    model = get_active_model()
    cmd = [TARIS_BIN, "agent"]
    if model:
        cmd += ["--model", model]
    cmd += ["-m", prompt]

    env = {**os.environ, "NO_COLOR": "1"}
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env,
    )
    if proc.returncode != 0:
        err_text = (proc.stderr or proc.stdout or "").strip()
        log.warning(f"[LLM] taris rc={proc.returncode}: {err_text[:300]}")
        _raise_if_http_error(err_text)
        raise RuntimeError(f"taris exited rc={proc.returncode}: {err_text[:80]}")
    raw = proc.stdout or proc.stderr or ""
    result = _clean_output(raw)
    if not result:
        raise RuntimeError("taris returned empty output")
    # taris may exit rc=0 but embed HTTP error text in stdout
    _raise_if_http_error(result)
    return result


def _http_post_json(url: str, headers: dict, body: dict, timeout: int, _retries: int = 2) -> dict:
    """Minimal JSON POST using stdlib urllib (no extra dependencies).

    Retries automatically on HTTP 429 (rate limit) with exponential backoff.
    Respects the ``Retry-After`` response header when present.
    Converts socket/urllib timeout errors to subprocess.TimeoutExpired so all
    callers can catch a single exception type.
    """
    import time as _time
    import socket as _socket
    data = json.dumps(body).encode("utf-8")
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (_socket.timeout, TimeoutError) as exc:
            # urllib raises socket.timeout (alias for TimeoutError) on socket-level timeout;
            # convert to subprocess.TimeoutExpired so callers have one exception to catch.
            raise subprocess.TimeoutExpired([], timeout) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (_socket.timeout, TimeoutError)):
                raise subprocess.TimeoutExpired([], timeout) from exc
            last_exc = exc
            raise
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code == 429 and attempt < _retries:
                try:
                    wait = int(exc.headers.get("Retry-After", 0)) or (5 * (attempt + 1))
                except (ValueError, AttributeError):
                    wait = 5 * (attempt + 1)
                log.warning(
                    f"[LLM] HTTP 429 rate limit (attempt {attempt + 1}/{_retries + 1}); "
                    f"retrying in {wait}s"
                )
                _time.sleep(wait)
                continue
            raise
    raise last_exc


def _ask_openai(prompt: str, timeout: int) -> str:
    """Call OpenAI-compatible API directly."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    model_name = get_active_model() or OPENAI_MODEL
    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        result = _http_post_json(url, headers, body, timeout)
        return result["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read(400).decode("utf-8", errors="replace")
        except Exception:
            pass
        log.error(f"[LLM] openai HTTP {exc.code} model='{model_name}': {err_body[:300]}")
        raise RuntimeError(f"HTTP Error {exc.code}: {exc.reason}") from exc


def _ask_yandexgpt(prompt: str, timeout: int) -> str:
    """Call YandexGPT Foundational Models API."""
    if not YANDEXGPT_API_KEY:
        raise RuntimeError("YANDEXGPT_API_KEY not set")
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    # Build full model URI if not already absolute
    model_uri = YANDEXGPT_MODEL_URI
    if YANDEXGPT_FOLDER_ID and not model_uri.startswith("gpt://"):
        model_uri = f"gpt://{YANDEXGPT_FOLDER_ID}/{YANDEXGPT_MODEL_URI}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {YANDEXGPT_API_KEY}",
    }
    body = {
        "modelUri": model_uri,
        "completionOptions": {"stream": False, "temperature": YANDEXGPT_TEMPERATURE, "maxTokens": YANDEXGPT_MAX_TOKENS},
        "messages": [{"role": "user", "text": prompt}],
    }
    result = _http_post_json(url, headers, body, timeout)
    return result["result"]["alternatives"][0]["message"]["text"].strip()


def _ask_gemini(prompt: str, timeout: int) -> str:
    """Call Google Gemini API."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    headers = {"Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    result = _http_post_json(url, headers, body, timeout)
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()


def _ask_anthropic(prompt: str, timeout: int) -> str:
    """Call Anthropic Claude API."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    result = _http_post_json(url, headers, body, timeout)
    return result["content"][0]["text"].strip()


def _ask_local(prompt: str, timeout: int) -> str:
    """Call local llama.cpp server (OpenAI-compatible /v1/chat/completions)."""
    url = f"{LLAMA_CPP_URL.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    body: dict = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": LOCAL_MAX_TOKENS,
        "temperature": _effective_temperature(),
    }
    if LLAMA_CPP_MODEL:
        body["model"] = LLAMA_CPP_MODEL
    result = _http_post_json(url, headers, body, timeout)
    return result["choices"][0]["message"]["content"].strip()


def _ask_ollama(prompt: str, timeout: int) -> str:
    """Call local Ollama server via native /api/chat endpoint.

    Uses ``think: false`` to suppress extended-thinking tokens (qwen3 family).
    Falls back gracefully if the server is not running.
    The caller is responsible for applying OLLAMA_MIN_TIMEOUT when appropriate
    (ask_llm_with_history does this for multi-turn chat; system_chat passes a
    strict 45 s timeout intentionally).

    Install: curl -fsSL https://ollama.ai/install.sh | sh && ollama pull qwen2:0.5b
    Config:  OLLAMA_URL=http://127.0.0.1:11434  OLLAMA_MODEL=qwen2:0.5b
    GPU:     Set HSA_OVERRIDE_GFX_VERSION in Ollama service for AMD iGPU (Radeon 890M gfx1150).
    """
    url = f"{OLLAMA_URL.rstrip('/')}/api/chat"
    headers = {"Content-Type": "application/json"}
    body: dict = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": OLLAMA_THINK,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "num_predict": LOCAL_MAX_TOKENS,
            "temperature": _effective_temperature(),
            **({"num_ctx": OLLAMA_NUM_CTX} if OLLAMA_NUM_CTX > 0 else {}),
        },
    }
    result = _http_post_json(url, headers, body, timeout)
    return result["message"]["content"].strip()  # _ask_ollama return


def _ask_openclaw(prompt: str, timeout: int) -> str:
    """Call OpenClaw AI gateway as an LLM provider (DEVICE_VARIANT=openclaw).

    Uses ``openclaw agent --message <prompt> --json --session-id <session>``
    and parses the JSON reply.  Raises FileNotFoundError when the binary is
    not found so ``ask_llm()`` can fall back gracefully.
    """
    import shutil
    bin_path = OPENCLAW_BIN
    if not os.path.isfile(bin_path) and not shutil.which(bin_path):
        raise FileNotFoundError(f"openclaw binary not found: {bin_path}")

    cmd = [bin_path, "agent", "--message", prompt, "--json", "--session-id", OPENCLAW_SESSION]
    env = {**os.environ, "NO_COLOR": "1"}
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    raw = (proc.stdout or "").strip()

    if proc.returncode != 0:
        err = (proc.stderr or raw or "")[:300]
        log.warning(f"[LLM] openclaw rc={proc.returncode}: {err}")
        raise RuntimeError(f"openclaw exited rc={proc.returncode}: {err[:80]}")

    if not raw:
        raise RuntimeError("openclaw returned empty output")

    try:
        data = json.loads(raw)
        text = (data.get("content") or data.get("text") or data.get("response") or "").strip()
        if not text:
            raise ValueError("no content key in openclaw JSON response")
        return text
    except (json.JSONDecodeError, ValueError):
        return _clean_output(raw)


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point — ask LLM
# ─────────────────────────────────────────────────────────────────────────────

_DISPATCH = {
    "taris":     _ask_taris,
    "openclaw":  _ask_openclaw,
    "openai":    _ask_openai,
    "yandexgpt": _ask_yandexgpt,
    "gemini":    _ask_gemini,
    "anthropic": _ask_anthropic,
    "local":     _ask_local,
    "ollama":    _ask_ollama,
}


def _ask_with_fallback(prompt: str, timeout: int, *, raise_on_fail: bool = False,
                       use_case: str = "chat") -> str:
    """Shared try-primary → try-named-fallback → try-local-fallback logic.

    Called by both ask_llm() and ask_llm_or_raise().
    use_case: "chat" | "system" | "voice" — checked for per-function override first.
    For Ollama, applies OLLAMA_MIN_TIMEOUT floor only when use_case != "system" so
    system_chat's strict 45 s timeout is respected.
    """
    # Per-function override wins over global LLM_PROVIDER
    per_func = get_per_func_provider(use_case)
    provider = per_func if per_func else LLM_PROVIDER.lower()
    fn = _DISPATCH.get(provider, _ask_taris)

    # Apply Ollama minimum timeout floor for chat/voice but NOT for system_chat
    effective_timeout = timeout
    if provider == "ollama" and use_case != "system":
        effective_timeout = max(timeout, OLLAMA_MIN_TIMEOUT)

    primary_error: Optional[Exception] = None
    try:
        return fn(prompt, effective_timeout)
    except subprocess.TimeoutExpired:
        log.warning(f"[LLM] {provider} timed out ({timeout}s)")
        primary_error = subprocess.TimeoutExpired([], timeout)
    except FileNotFoundError as exc:
        log.error(f"[LLM] binary not found for provider '{provider}': {exc}")
        primary_error = exc
    except Exception as exc:
        log.warning(f"[LLM] {provider} failed: {exc}")
        primary_error = exc

    # ── Named fallback (LLM_FALLBACK_PROVIDER) — mirrors STT_FALLBACK_PROVIDER ──
    named_fb = LLM_FALLBACK_PROVIDER.lower() if LLM_FALLBACK_PROVIDER else ""
    if named_fb and named_fb != provider:
        log.warning(f"[LLM] falling back to named provider '{named_fb}' after {provider} failure")
        fb_fn = _DISPATCH.get(named_fb, _ask_taris)
        try:
            result = fb_fn(prompt, timeout)
            if result:
                log.debug(f"[LLM] named fallback '{named_fb}' succeeded")
                return result
        except Exception as exc2:
            log.error(f"[LLM] named fallback '{named_fb}' also failed: {exc2}")

    # ── Legacy local llama.cpp fallback (LLM_LOCAL_FALLBACK=1) ───────────────
    if (LLM_LOCAL_FALLBACK or os.path.exists(LLM_FALLBACK_FLAG_FILE)) and provider != "local":
        log.warning(
            f"[LLM] Falling back to local llama.cpp after {provider} failure: {primary_error}"
        )
        try:
            result = _ask_local(prompt, timeout)
            return f"⚠️ [local fallback]\n{result}" if result else ""
        except Exception as exc2:
            log.error(f"[LLM] local fallback also failed: {exc2}")

    if raise_on_fail and primary_error is not None:
        raise primary_error
    return ""


def ask_llm(prompt: str, timeout: int = 60, *, use_case: str = "chat") -> str:
    """Call the configured LLM provider and return the response text.

    Fallback chain (first that succeeds wins):
      1. Per-function override (if set via admin menu)
      2. LLM_PROVIDER (primary global)
      3. LLM_FALLBACK_PROVIDER (named fallback)
      4. Local llama.cpp when LLM_LOCAL_FALLBACK=1
    Returns "" when all providers fail.
    use_case: "chat" (default) | "system" | "voice" — for per-function override.
    """
    return _ask_with_fallback(prompt, timeout, use_case=use_case, raise_on_fail=False)


def ask_llm_or_raise(prompt: str, timeout: int = 60, *, use_case: str = "chat") -> str:
    """Call the configured LLM provider; raise on failure.

    Unlike ask_llm(), re-raises the primary exception when all fallbacks are
    exhausted.  Use for interactive commands where a silent empty string masks
    the real error.
    """
    return _ask_with_fallback(prompt, timeout, use_case=use_case, raise_on_fail=True)


# ─────────────────────────────────────────────────────────────────────────────
# History-aware entry point  (Feature 2.1)
# ─────────────────────────────────────────────────────────────────────────────

def _format_history_as_text(messages: list) -> str:
    """Render a messages list as a plain-text transcript for CLI providers."""
    parts = []
    for m in messages:
        label = "User" if m["role"] == "user" else "Assistant"
        parts.append(f"[{label}]: {m['content']}")
    return "\n".join(parts)


def ask_llm_with_history(messages: list, timeout: int = 60, *, use_case: str = "chat",
                          _no_history_fallback: bool = False,
                          _force_provider: str = "") -> str:
    """Call the configured LLM with a full conversation history.

    ``messages`` is a list of ``{"role": "user"|"assistant", "content": str}``
    dicts; the last entry must be the current user turn.

    Provider routing:
      - openai / anthropic / local  → native messages list
      - yandexgpt                   → "text" key instead of "content"
      - gemini                      → contents/parts with "user"/"model" roles
      - taris (default)          → formatted as plain-text transcript
    """
    per_func = get_per_func_provider(use_case)
    provider = _force_provider.lower() if _force_provider else (per_func if per_func else LLM_PROVIDER.lower())
    primary_error: Exception = RuntimeError("unknown")

    try:
        if provider == "openai":
            if not OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY not set")
            url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            }
            result = _http_post_json(
                url, headers, {"model": get_active_model() or OPENAI_MODEL, "messages": messages}, timeout
            )
            return result["choices"][0]["message"]["content"].strip()

        elif provider == "anthropic":
            if not ANTHROPIC_API_KEY:
                raise RuntimeError("ANTHROPIC_API_KEY not set")
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            }
            result = _http_post_json(
                url, headers,
                {"model": ANTHROPIC_MODEL, "max_tokens": ANTHROPIC_MAX_TOKENS, "messages": messages},
                timeout,
            )
            return result["content"][0]["text"].strip()

        elif provider == "local":
            url = f"{LLAMA_CPP_URL.rstrip('/')}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
            body: dict = {"messages": messages, "max_tokens": LOCAL_MAX_TOKENS, "temperature": _effective_temperature()}
            return result["choices"][0]["message"]["content"].strip()

        elif provider == "yandexgpt":
            if not YANDEXGPT_API_KEY:
                raise RuntimeError("YANDEXGPT_API_KEY not set")
            url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
            model_uri = YANDEXGPT_MODEL_URI
            if YANDEXGPT_FOLDER_ID and not model_uri.startswith("gpt://"):
                model_uri = f"gpt://{YANDEXGPT_FOLDER_ID}/{YANDEXGPT_MODEL_URI}"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {YANDEXGPT_API_KEY}",
            }
            yandex_msgs = [{"role": m["role"], "text": m["content"]} for m in messages]
            result = _http_post_json(
                url, headers,
                {
                    "modelUri": model_uri,
                    "completionOptions": {
                        "stream": False, "temperature": YANDEXGPT_TEMPERATURE, "maxTokens": YANDEXGPT_MAX_TOKENS,
                    },
                    "messages": yandex_msgs,
                },
                timeout,
            )
            return result["result"]["alternatives"][0]["message"]["text"].strip()

        elif provider == "gemini":
            if not GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY not set")
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            )
            headers = {"Content-Type": "application/json"}
            contents = [
                {
                    "role": "user" if m["role"] == "user" else "model",
                    "parts": [{"text": m["content"]}],
                }
                for m in messages
            ]
            result = _http_post_json(url, headers, {"contents": contents}, timeout)
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()

        elif provider == "ollama":
            # Ollama supports native OpenAI-format multi-turn messages — send as-is.
            # system_chat uses a strict 45 s budget — do NOT apply OLLAMA_MIN_TIMEOUT floor.
            effective_timeout = timeout if use_case == "system" else max(timeout, OLLAMA_MIN_TIMEOUT)
            _url = f"{OLLAMA_URL.rstrip('/')}/api/chat"
            _headers = {"Content-Type": "application/json"}
            _body: dict = {
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "think": OLLAMA_THINK,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {
                    "num_predict": LOCAL_MAX_TOKENS,
                    "temperature": _effective_temperature(),
                    **({"num_ctx": OLLAMA_NUM_CTX} if OLLAMA_NUM_CTX > 0 else {}),
                },
            }
            result = _http_post_json(_url, _headers, _body, effective_timeout)
            return result["message"]["content"].strip()

        else:  # taris, openclaw, or unknown — format history as plain text
            prompt = _format_history_as_text(messages)
            fn = _DISPATCH.get(provider, _ask_taris)
            t = OPENCLAW_TIMEOUT if provider == "openclaw" else timeout
            return fn(prompt, t)

    except subprocess.TimeoutExpired as exc:
        log.warning(f"[LLM] {provider} timed out ({timeout}s) in history call")
        primary_error = exc
    except FileNotFoundError as exc:
        log.error(f"[LLM] binary not found for provider '{provider}': {exc}")
        primary_error = exc
    except Exception as exc:
        # For HTTPError include the status code to distinguish 400 (bad model name) from 5xx
        code = getattr(exc, "code", None)
        if code and code not in (429,):
            model_hint = get_active_model() or OPENAI_MODEL
            log.warning(f"[LLM] {provider} HTTP {code} in history call (model={model_hint}): {exc}")
        else:
            log.warning(f"[LLM] {provider} failed in history call: {exc}")
        primary_error = exc

    # ── Named fallback (LLM_FALLBACK_PROVIDER) ───────────────────────────────
    named_fb = LLM_FALLBACK_PROVIDER.lower() if LLM_FALLBACK_PROVIDER else ""
    if named_fb and named_fb != provider:
        log.warning(f"[LLM] falling back to named provider '{named_fb}' after {provider} failure")
        try:
            result = ask_llm_with_history(
                messages, timeout, use_case=use_case, _no_history_fallback=True,
                _force_provider=named_fb,
            )
            if result:
                log.debug(f"[LLM] named fallback '{named_fb}' succeeded in history call")
                return result
        except Exception as exc2:
            log.error(f"[LLM] named fallback '{named_fb}' also failed in history call: {exc2}")

    # ── Global default fallback (when per-func override was used and failed) ──
    # e.g. per_func["system"]="ollama" fails; LLM_FALLBACK_PROVIDER="ollama" (same → skipped);
    # but LLM_PROVIDER="openai" — that cloud provider was never tried and should be used now.
    default_provider = LLM_PROVIDER.lower()
    if per_func and default_provider not in (provider, named_fb):
        log.warning(f"[LLM] falling back to default provider '{default_provider}' after per-func '{provider}' failure")
        try:
            result = ask_llm_with_history(
                messages, timeout, use_case=use_case, _no_history_fallback=True,
                _force_provider=default_provider,
            )
            if result:
                log.debug(f"[LLM] default provider fallback '{default_provider}' succeeded in history call")
                return result
        except Exception as exc2:
            log.error(f"[LLM] default provider fallback '{default_provider}' also failed in history call: {exc2}")

    if (LLM_LOCAL_FALLBACK or os.path.exists(LLM_FALLBACK_FLAG_FILE)) and provider != "local":
        log.warning(
            f"[LLM] Falling back to local after {provider} failure: {primary_error}"
        )
        try:
            url = f"{LLAMA_CPP_URL.rstrip('/')}/v1/chat/completions"
            body_fb: dict = {"messages": messages, "max_tokens": LOCAL_MAX_TOKENS, "temperature": _effective_temperature()}
            if LLAMA_CPP_MODEL:
                body_fb["model"] = LLAMA_CPP_MODEL
            result = _http_post_json(
                url, {"Content-Type": "application/json"}, body_fb, timeout
            )
            text = result["choices"][0]["message"]["content"].strip()
            return f"⚠️ [local fallback]\n{text}" if text else ""
        except Exception as exc2:
            log.error(f"[LLM] local fallback also failed in history call: {exc2}")

    # Last-resort: strip history, send only the final user turn + system prompt
    try:
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            None,
        )
        if last_user and not _no_history_fallback:
            log.warning("[LLM] trying no-history fallback after history call failure")
            # Preserve system prompt so system-chat use_case still returns a bash cmd
            sys_msg = next((m for m in messages if m.get("role") == "system"), None)
            fallback_messages = []
            if sys_msg:
                fallback_messages.append(sys_msg)
            fallback_messages.append({"role": "user", "content": last_user})
            return ask_llm_with_history(
                fallback_messages, timeout=timeout, use_case=use_case,
                _no_history_fallback=True,
            )
    except Exception as exc3:
        log.error(f"[LLM] no-history fallback also failed: {exc3}")

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Streaming entry point — Ollama only (other providers fall back to full call)
# ─────────────────────────────────────────────────────────────────────────────

def ask_llm_stream(messages: list, timeout: int = 120):
    """Yield LLM response text incrementally as chunks arrive (Ollama only).

    Each yielded value is a small string fragment (1–10 tokens).
    Falls back to a single-chunk yield from ask_llm_with_history() for
    non-Ollama providers (OpenAI, etc.).

    Usage in Telegram handler:
        buf = ""
        for chunk in ask_llm_stream(messages):
            buf += chunk
            # update display every N chars
    """
    if LLM_PROVIDER == "ollama":
        try:
            effective_timeout = max(timeout, OLLAMA_MIN_TIMEOUT)
            url = f"{OLLAMA_URL.rstrip('/')}/api/chat"
            body = {
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": True,
                "think": OLLAMA_THINK,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {
                    "num_predict": LOCAL_MAX_TOKENS,
                    "temperature": _effective_temperature(),
                    **({"num_ctx": OLLAMA_NUM_CTX} if OLLAMA_NUM_CTX > 0 else {}),
                },
            }
            data = json.dumps(body).encode()
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except Exception:
                        continue
                    # Skip think-mode reasoning tokens (role="think" in qwen3)
                    if chunk.get("message", {}).get("role") == "think":
                        continue
                    fragment = chunk.get("message", {}).get("content", "")
                    if fragment:
                        yield fragment
                    if chunk.get("done"):
                        break
            return
        except Exception as exc:
            log.warning(f"[LLM] stream failed ({exc}), falling back to full call")

    # Non-Ollama or stream error: yield full response as single chunk
    full = ask_llm_with_history(messages, timeout=timeout)
    if full:
        yield full
