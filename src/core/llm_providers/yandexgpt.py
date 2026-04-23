"""yandexgpt.py — YandexGPT Foundational Models API provider."""
from __future__ import annotations

from core.bot_config import (
    YANDEXGPT_API_KEY, YANDEXGPT_FOLDER_ID, YANDEXGPT_MAX_TOKENS,
    YANDEXGPT_MODEL_URI, YANDEXGPT_TEMPERATURE,
)
from core.llm_providers.base import http_post_json


def ask(prompt: str, timeout: int) -> str:
    """Call YandexGPT Foundational Models API."""
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
    body = {
        "modelUri": model_uri,
        "completionOptions": {
            "stream": False,
            "temperature": YANDEXGPT_TEMPERATURE,
            "maxTokens": YANDEXGPT_MAX_TOKENS,
        },
        "messages": [{"role": "user", "text": prompt}],
    }
    result = http_post_json(url, headers, body, timeout)
    return result["result"]["alternatives"][0]["message"]["text"].strip()
