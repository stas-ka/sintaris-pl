"""local.py — Local llama.cpp server provider (OpenAI-compatible /v1/chat/completions)."""
from __future__ import annotations

from core.bot_config import LLAMA_CPP_MODEL, LLAMA_CPP_URL, LOCAL_MAX_TOKENS
from core.llm_providers.base import effective_temperature, http_post_json


def ask(prompt: str, timeout: int) -> str:
    """Call local llama.cpp server (OpenAI-compatible /v1/chat/completions)."""
    url = f"{LLAMA_CPP_URL.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    body: dict = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": LOCAL_MAX_TOKENS,
        "temperature": effective_temperature(),
    }
    if LLAMA_CPP_MODEL:
        body["model"] = LLAMA_CPP_MODEL
    result = http_post_json(url, headers, body, timeout)
    return result["choices"][0]["message"]["content"].strip()
