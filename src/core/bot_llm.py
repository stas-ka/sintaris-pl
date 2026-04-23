"""
bot_llm.py — Pluggable LLM backend abstraction.

Wraps the existing taris CLI call in a clean interface that the web app
can import without pulling in Telegram dependencies.

Feature 3.1: LLM_PROVIDER env-var switch (taris | openai | yandexgpt | gemini | anthropic | local)
Feature 3.2: Local llama.cpp offline fallback with LLM_LOCAL_FALLBACK=1
§30.1: Provider implementations extracted to core/llm_providers/ package.
"""

import json
import os
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
    COPILOT_TIMEOUT,
    LLAMA_CPP_MODEL,
    LLAMA_CPP_URL,
    LOCAL_MAX_TOKENS,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MIN_TIMEOUT,
    OLLAMA_NUM_CTX,
    OLLAMA_THINK,
    LLM_LOCAL_FALLBACK,
    LLM_FALLBACK_FLAG_FILE,
    LLM_FALLBACK_PROVIDER,
    LLM_PROVIDER,
    OLLAMA_URL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENCLAW_TIMEOUT,
    TARIS_CONFIG,
    YANDEXGPT_API_KEY,
    YANDEXGPT_FOLDER_ID,
    YANDEXGPT_MAX_TOKENS,
    YANDEXGPT_MODEL_URI,
    YANDEXGPT_TEMPERATURE,
    LLM_PER_FUNC_FILE,
    log_assistant as log,
)

# §30.1 — import provider implementations from package
from core.llm_providers.base import (
    clean_output as _clean_output,
    effective_temperature as _effective_temperature,
    get_active_model,
    http_post_json as _http_post_json,
    list_models,
    raise_if_http_error as _raise_if_http_error,
    set_active_model,
)
from core.llm_providers import taris_p, openai_p, yandexgpt, gemini, anthropic, local, ollama, openclaw, copilot

# §30.1 — re-export provider ask() functions under legacy internal names
_ask_taris    = taris_p.ask
_ask_openai   = openai_p.ask
_ask_yandexgpt = yandexgpt.ask
_ask_gemini   = gemini.ask
_ask_anthropic = anthropic.ask
_ask_local    = local.ask
_ask_openclaw = openclaw.ask
_ask_copilot  = copilot.ask
_ask_copilot_with_history = copilot.ask_with_history

def _ask_ollama(prompt: str, timeout: int, *, chat_id: int | None = None) -> str:
    """Thin wrapper forwarding to ollama provider (chat_id kwarg for per-user model)."""
    return ollama.ask(prompt, timeout, chat_id=chat_id)

# §30.1 — re-export Ollama state management functions (used by admin UI)
get_ollama_model   = ollama.get_ollama_model
set_ollama_model   = ollama.set_ollama_model
_resolve_ollama_model = ollama._resolve_ollama_model
_get_user_role     = ollama._get_user_role


# ─────────────────────────────────────────────────────────────────────────────
# Per-function LLM override
# Stored in llm_per_func.json: {"system": "openai", "chat": "ollama", ...}
# Empty string or missing key → use global LLM_PROVIDER.
# Supported use_case values: "system" (admin system chat), "chat" (user free chat).
# ─────────────────────────────────────────────────────────────────────────────

def _effective_temperature() -> float:
    """Return runtime LLM temperature from rag_settings; falls back to LOCAL_TEMPERATURE."""
    from core.bot_config import LOCAL_TEMPERATURE
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
# Main entry point — ask LLM
# ─────────────────────────────────────────────────────────────────────────────

# §30.1 — use provider registry as dispatch table
from core.llm_providers import REGISTRY as _DISPATCH


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
                          _force_provider: str = "",
                          chat_id: int | None = None) -> str:
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
        if provider == "copilot":
            return _ask_copilot_with_history(messages, COPILOT_TIMEOUT)

        elif provider == "openai":
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
                "model": _resolve_ollama_model(chat_id),
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
                "model": get_ollama_model(),
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
