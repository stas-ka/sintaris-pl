"""anthropic.py — Anthropic Claude API LLM provider."""
from __future__ import annotations

from core.bot_config import (
    ANTHROPIC_API_KEY, ANTHROPIC_MAX_TOKENS, ANTHROPIC_MODEL,
)
from core.llm_providers.base import http_post_json


def ask(prompt: str, timeout: int) -> str:
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
    result = http_post_json(url, headers, body, timeout)
    return result["content"][0]["text"].strip()
