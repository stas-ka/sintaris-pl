"""
bot_llm.py — Pluggable LLM backend abstraction.

Wraps the existing picoclaw CLI call in a clean interface that the web app
can import without pulling in Telegram dependencies.

Feature 3.1: LLM_PROVIDER env-var switch (picoclaw | openai | yandexgpt | gemini | anthropic | local)
Feature 3.2: Local llama.cpp offline fallback with LLM_LOCAL_FALLBACK=1
"""

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from core.bot_config import (
    ACTIVE_MODEL_FILE,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLAMA_CPP_MODEL,
    LLAMA_CPP_URL,
    LLM_LOCAL_FALLBACK,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    PICOCLAW_BIN,
    PICOCLAW_CONFIG,
    YANDEXGPT_API_KEY,
    YANDEXGPT_FOLDER_ID,
    YANDEXGPT_MODEL_URI,
    log,
)


# ─────────────────────────────────────────────────────────────────────────────
# Active model
# ─────────────────────────────────────────────────────────────────────────────

def get_active_model() -> str:
    """Return the admin-selected model name or empty string."""
    try:
        return Path(ACTIVE_MODEL_FILE).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def set_active_model(name: str) -> None:
    Path(ACTIVE_MODEL_FILE).write_text(name, encoding="utf-8")


def list_models() -> list[dict]:
    """Read model_list from picoclaw config.json."""
    try:
        cfg = json.loads(Path(PICOCLAW_CONFIG).read_text(encoding="utf-8"))
        return cfg.get("model_list", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Output cleaning  (ported from telegram.bot_access._clean_picoclaw_output)
# ─────────────────────────────────────────────────────────────────────────────

_ANSI_RE     = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_SPINNER_RE  = re.compile(r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⣾⣽⣻⢿⡿⣟⣯⣷◐◑◒◓⠁⠂⠄⡀⢀⠠⠐⠈|/\\-]")
_PRINTF_WRAP = re.compile(r"^printf\s+['\"](.+)['\"]\s*$", re.DOTALL)
_LOG_PREFIX  = re.compile(r"^\d{4}[/-]\d{2}[/-]\d{2}[\sT]\d{2}:\d{2}:\d{2}\s*(INFO|DEBUG|WARN|ERROR)\s*", re.MULTILINE)
_PIPE_HEADER = re.compile(r"^(agent|picoclaw)\s*[|│]", re.MULTILINE | re.IGNORECASE)


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

def _ask_picoclaw(prompt: str, timeout: int) -> str:
    """Call picoclaw CLI (wraps OpenRouter or configured LLM)."""
    model = get_active_model()
    cmd = [PICOCLAW_BIN, "agent"]
    if model:
        cmd += ["--model", model]
    cmd += ["-m", prompt]

    env = {**os.environ, "NO_COLOR": "1"}
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env,
    )
    if proc.returncode != 0:
        log.warning(f"[LLM] picoclaw rc={proc.returncode}: {proc.stderr[:200]}")
    raw = proc.stdout or proc.stderr or ""
    return _clean_output(raw)


def _http_post_json(url: str, headers: dict, body: dict, timeout: int) -> dict:
    """Minimal JSON POST using stdlib urllib (no extra dependencies)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ask_openai(prompt: str, timeout: int) -> str:
    """Call OpenAI-compatible API directly."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    body = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }
    result = _http_post_json(url, headers, body, timeout)
    return result["choices"][0]["message"]["content"].strip()


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
        "completionOptions": {"stream": False, "temperature": 0.6, "maxTokens": "2000"},
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
        "max_tokens": 1024,
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
        "max_tokens": 512,
        "temperature": 0.7,
    }
    if LLAMA_CPP_MODEL:
        body["model"] = LLAMA_CPP_MODEL
    result = _http_post_json(url, headers, body, timeout)
    return result["choices"][0]["message"]["content"].strip()


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point — ask LLM
# ─────────────────────────────────────────────────────────────────────────────

_DISPATCH = {
    "picoclaw":  _ask_picoclaw,
    "openai":    _ask_openai,
    "yandexgpt": _ask_yandexgpt,
    "gemini":    _ask_gemini,
    "anthropic": _ask_anthropic,
    "local":     _ask_local,
}


def ask_llm(prompt: str, timeout: int = 60) -> str:
    """Call the configured LLM provider and return the response text.

    Falls back to local llama.cpp when LLM_LOCAL_FALLBACK=1 and the primary
    provider fails.  Fallback responses are prefixed with '⚠️ [local fallback]'.
    """
    provider = LLM_PROVIDER.lower()
    fn = _DISPATCH.get(provider, _ask_picoclaw)

    try:
        return fn(prompt, timeout)
    except subprocess.TimeoutExpired:
        log.warning(f"[LLM] {provider} timed out ({timeout}s)")
        primary_error: Exception = subprocess.TimeoutExpired([], timeout)
    except FileNotFoundError as exc:
        log.error(f"[LLM] binary not found for provider '{provider}': {exc}")
        primary_error = exc
    except Exception as exc:
        log.warning(f"[LLM] {provider} failed: {exc}")
        primary_error = exc

    # ── Local fallback (Feature 3.2) ──────────────────────────────────────
    if LLM_LOCAL_FALLBACK and provider != "local":
        log.warning(
            f"[LLM] Falling back to local llama.cpp after {provider} failure: {primary_error}"
        )
        try:
            result = _ask_local(prompt, timeout)
            return f"⚠️ [local fallback]\n{result}" if result else ""
        except Exception as exc2:
            log.error(f"[LLM] local fallback also failed: {exc2}")

    return ""


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


def ask_llm_with_history(messages: list, timeout: int = 60) -> str:
    """Call the configured LLM with a full conversation history.

    ``messages`` is a list of ``{"role": "user"|"assistant", "content": str}``
    dicts; the last entry must be the current user turn.

    Provider routing:
      - openai / anthropic / local  → native messages list
      - yandexgpt                   → "text" key instead of "content"
      - gemini                      → contents/parts with "user"/"model" roles
      - picoclaw (default)          → formatted as plain-text transcript
    """
    provider = LLM_PROVIDER.lower()
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
                url, headers, {"model": OPENAI_MODEL, "messages": messages}, timeout
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
                {"model": ANTHROPIC_MODEL, "max_tokens": 1024, "messages": messages},
                timeout,
            )
            return result["content"][0]["text"].strip()

        elif provider == "local":
            url = f"{LLAMA_CPP_URL.rstrip('/')}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
            body: dict = {"messages": messages, "max_tokens": 512, "temperature": 0.7}
            if LLAMA_CPP_MODEL:
                body["model"] = LLAMA_CPP_MODEL
            result = _http_post_json(url, headers, body, timeout)
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
                        "stream": False, "temperature": 0.6, "maxTokens": "2000",
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

        else:  # picoclaw or unknown — format history as plain text
            prompt = _format_history_as_text(messages)
            return _ask_picoclaw(prompt, timeout)

    except subprocess.TimeoutExpired as exc:
        log.warning(f"[LLM] {provider} timed out ({timeout}s) in history call")
        primary_error = exc
    except FileNotFoundError as exc:
        log.error(f"[LLM] binary not found for provider '{provider}': {exc}")
        primary_error = exc
    except Exception as exc:
        log.warning(f"[LLM] {provider} failed in history call: {exc}")
        primary_error = exc

    if LLM_LOCAL_FALLBACK and provider != "local":
        log.warning(
            f"[LLM] Falling back to local after {provider} failure: {primary_error}"
        )
        try:
            url = f"{LLAMA_CPP_URL.rstrip('/')}/v1/chat/completions"
            body_fb: dict = {"messages": messages, "max_tokens": 512, "temperature": 0.7}
            if LLAMA_CPP_MODEL:
                body_fb["model"] = LLAMA_CPP_MODEL
            result = _http_post_json(
                url, {"Content-Type": "application/json"}, body_fb, timeout
            )
            text = result["choices"][0]["message"]["content"].strip()
            return f"⚠️ [local fallback]\n{text}" if text else ""
        except Exception as exc2:
            log.error(f"[LLM] local fallback also failed in history call: {exc2}")

    return ""
