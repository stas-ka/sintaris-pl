"""copilot.py — Copilot Bridge LLM provider (local proxy to GitHub Copilot / GitHub Models API)."""
from __future__ import annotations

import urllib.error

from core.bot_config import (
    COPILOT_BRIDGE_KEY, COPILOT_BRIDGE_URL, COPILOT_MODEL, COPILOT_TIMEOUT,
    LOCAL_MAX_TOKENS,
)
from core.llm_providers.base import effective_temperature, http_post_json


def ask(prompt: str, timeout: int) -> str:
    """Call Copilot Bridge with a single prompt.

    The bridge must be running: python copilot-bridge/server.py
    Config: COPILOT_BRIDGE_URL, COPILOT_BRIDGE_KEY, COPILOT_MODEL, COPILOT_TIMEOUT.
    """
    url = f"{COPILOT_BRIDGE_URL.rstrip('/')}/v1/chat/completions"
    headers: dict = {"Content-Type": "application/json"}
    if COPILOT_BRIDGE_KEY:
        headers["Authorization"] = f"Bearer {COPILOT_BRIDGE_KEY}"
    body = {
        "model": COPILOT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": LOCAL_MAX_TOKENS,
        "temperature": effective_temperature(),
    }
    try:
        result = http_post_json(url, headers, body, timeout)
        return result["choices"][0]["message"]["content"].strip()
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Copilot Bridge not reachable at {COPILOT_BRIDGE_URL} — "
            "start it with: python copilot-bridge/server.py"
        ) from exc


def ask_with_history(messages: list, timeout: int) -> str:
    """Call Copilot Bridge with full conversation history."""
    url = f"{COPILOT_BRIDGE_URL.rstrip('/')}/v1/chat/completions"
    headers: dict = {"Content-Type": "application/json"}
    if COPILOT_BRIDGE_KEY:
        headers["Authorization"] = f"Bearer {COPILOT_BRIDGE_KEY}"
    body = {
        "model": COPILOT_MODEL,
        "messages": messages,
        "max_tokens": LOCAL_MAX_TOKENS,
        "temperature": effective_temperature(),
    }
    try:
        result = http_post_json(url, headers, body, timeout)
        return result["choices"][0]["message"]["content"].strip()
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Copilot Bridge not reachable at {COPILOT_BRIDGE_URL} — "
            "start it with: python copilot-bridge/server.py"
        ) from exc
