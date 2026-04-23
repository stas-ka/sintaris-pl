"""openai_p.py — OpenAI-compatible API LLM provider."""
from __future__ import annotations

import urllib.error

from core.bot_config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, log_assistant as log
from core.llm_providers.base import get_active_model, http_post_json


def ask(prompt: str, timeout: int) -> str:
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
        result = http_post_json(url, headers, body, timeout)
        return result["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read(400).decode("utf-8", errors="replace")
        except Exception:
            pass
        log.error(f"[LLM] openai HTTP {exc.code} model='{model_name}': {err_body[:300]}")
        raise RuntimeError(f"HTTP Error {exc.code}: {exc.reason}") from exc
