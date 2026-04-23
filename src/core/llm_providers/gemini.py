"""gemini.py — Google Gemini API LLM provider."""
from __future__ import annotations

from core.bot_config import GEMINI_API_KEY, GEMINI_MODEL
from core.llm_providers.base import http_post_json


def ask(prompt: str, timeout: int) -> str:
    """Call Google Gemini API."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    headers = {"Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    result = http_post_json(url, headers, body, timeout)
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()
