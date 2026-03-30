"""
rag_settings.py — Runtime-mutable RAG/LLM settings stored in ~/.taris/rag_settings.json.

Allows the Admin Panel to override env-var defaults without restarting the service.
Settings are loaded lazily and cached; call invalidate() after save.
"""
import json
import os
from pathlib import Path
from core.bot_config import RAG_SETTINGS_FILE, RAG_TOP_K, RAG_CHUNK_SIZE, LLM_TIMEOUT, RAG_TIMEOUT, LOCAL_TEMPERATURE, log

_DEFAULTS = {
    "rag_top_k":       RAG_TOP_K,
    "rag_chunk_size":  RAG_CHUNK_SIZE,
    "llm_timeout":     LLM_TIMEOUT,
    "rag_timeout":     RAG_TIMEOUT,
    "llm_temperature": LOCAL_TEMPERATURE,
}
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        _cache = json.loads(Path(RAG_SETTINGS_FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        _cache = dict(_DEFAULTS)
    return _cache


def get(key: str):
    """Return current setting value, falling back to env-var default."""
    return _load().get(key, _DEFAULTS.get(key))


def set_value(key: str, value) -> None:
    """Persist a setting override and invalidate cache."""
    global _cache
    data = _load()
    data[key] = value
    Path(RAG_SETTINGS_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(RAG_SETTINGS_FILE).write_text(json.dumps(data, indent=2))
    _cache = data
    log.info("[RAGSettings] %s = %s", key, value)


def invalidate() -> None:
    """Force reload on next access."""
    global _cache
    _cache = None
