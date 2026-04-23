"""llm_providers/base.py — Shared utilities for all LLM provider plugins.

§30.1: Extracted from core/bot_llm.py.  No business logic here — only
networking helpers, output cleaning, and the LLMProvider Protocol.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from core.bot_config import (
    ACTIVE_MODEL_FILE,
    LOCAL_TEMPERATURE,
    TARIS_CONFIG,
    log_assistant as log,
)


# ── LLMProvider Protocol ──────────────────────────────────────────────────────

@runtime_checkable
class LLMProvider(Protocol):
    """Callable interface every provider module must satisfy.

    Signature: ``ask(prompt: str, timeout: int) -> str``
    May accept additional keyword arguments (e.g. ``chat_id`` for Ollama).
    """
    def __call__(self, prompt: str, timeout: int) -> str: ...


# ── Active model management ───────────────────────────────────────────────────

def get_active_model() -> str:
    """Return the admin-selected model name or empty string.

    Strips provider prefixes (e.g. ``openai/gpt-4o-mini`` → ``gpt-4o-mini``)
    that are valid in some UIs but cause HTTP 400 when passed to the API.
    """
    try:
        raw = Path(ACTIVE_MODEL_FILE).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
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


# ── Temperature helper ────────────────────────────────────────────────────────

def effective_temperature() -> float:
    """Return runtime LLM temperature from rag_settings; falls back to LOCAL_TEMPERATURE."""
    try:
        from core.rag_settings import get as _rget
        return float(_rget("llm_temperature"))
    except Exception:
        return LOCAL_TEMPERATURE


# ── Output cleaning (ported from telegram.bot_access._clean_taris_output) ─────

_ANSI_RE     = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_SPINNER_RE  = re.compile(r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⣾⣽⣻⢿⡿⣟⣯⣷◐◑◒◓⠁⠂⠄⡀⢀⠠⠐⠈]")
_PRINTF_WRAP = re.compile(r"^printf\s+['\"](.+)['\"]\s*$", re.DOTALL)
_LOG_PREFIX  = re.compile(
    r"^(?:\d{4}[/-]\d{2}[/-]\d{2}|\d{8})[\sT]\d{2}:\d{2}:\d{2}\s*(?:INFO|DEBUG|WARN|ERROR)?\s*",
    re.MULTILINE,
)
_PIPE_HEADER = re.compile(r"^(agent|taris)\s*[|│]", re.MULTILINE | re.IGNORECASE)


def clean_output(raw: str) -> str:
    text = _ANSI_RE.sub("", raw)
    text = _SPINNER_RE.sub("", text)
    text = _LOG_PREFIX.sub("", text)
    text = _PIPE_HEADER.sub("", text)
    m = _PRINTF_WRAP.match(text.strip())
    if m:
        text = m.group(1)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines).strip()


def raise_if_http_error(text: str) -> None:
    """Raise a descriptive RuntimeError if *text* contains a known HTTP error pattern."""
    lo = text.lower()
    if "payment required" in lo:
        raise RuntimeError("taris: 402 Payment Required")
    if "too many requests" in lo:
        raise RuntimeError("taris: 429 Too Many Requests")
    if "unauthorized" in lo and len(text) < 300:
        raise RuntimeError("taris: 401 Unauthorized")
    if "service unavailable" in lo and len(text) < 300:
        raise RuntimeError("taris: 503 Service Unavailable")


# ── HTTP helper ───────────────────────────────────────────────────────────────

def http_post_json(url: str, headers: dict, body: dict, timeout: int,
                   _retries: int = 2) -> dict:
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
