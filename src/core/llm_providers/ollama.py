"""ollama.py — Ollama LLM provider + per-user model management.

§30.1: Extracted from core/bot_llm.py.
Contains Ollama-specific state: runtime model override, per-user model resolution.
"""
from __future__ import annotations

from core.bot_config import (
    LOCAL_MAX_TOKENS, OLLAMA_KEEP_ALIVE, OLLAMA_MIN_TIMEOUT,
    OLLAMA_MODEL, OLLAMA_NUM_CTX, OLLAMA_THINK, OLLAMA_URL,
    log_assistant as log,
)
from core.llm_providers.base import effective_temperature, http_post_json

# ── Runtime model override (admin UI — no restart required) ──────────────────
_runtime_ollama_model: str = ""  # "" → use OLLAMA_MODEL from bot_config


def get_ollama_model() -> str:
    """Return the active Ollama model name. Runtime override takes precedence."""
    return _runtime_ollama_model or OLLAMA_MODEL


def set_ollama_model(model: str) -> None:
    """Override the active Ollama model at runtime. Does not persist across restarts."""
    global _runtime_ollama_model
    _runtime_ollama_model = model.strip()
    log.info(f"[LLM] Ollama model switched at runtime → {_runtime_ollama_model or '(default)'}")


def _resolve_ollama_model(chat_id: int | None = None) -> str:
    """Resolve the Ollama model for a specific user (Feature §29.1).

    Priority: 1) per-user pref (user_prefs key='ollama_model')
              2) role-based default (ROLE_DEFAULT_OLLAMA_MODEL)
              3) global runtime override / OLLAMA_MODEL
    """
    if chat_id:
        try:
            from core.bot_db import get_store
            store = get_store()
            user_model = store.get_user_pref(chat_id, "ollama_model", default="")
            if user_model:
                return user_model
            from core.bot_config import ROLE_DEFAULT_OLLAMA_MODEL
            if ROLE_DEFAULT_OLLAMA_MODEL:
                role = _get_user_role(chat_id)
                role_model = ROLE_DEFAULT_OLLAMA_MODEL.get(role, "")
                if role_model:
                    return role_model
        except Exception:
            pass
    return get_ollama_model()


def _get_user_role(chat_id: int) -> str:
    """Return user role string for model-preference resolution."""
    try:
        from core.bot_config import ADMIN_IDS
        if chat_id in ADMIN_IDS:
            return "admin"
        from core.bot_db import get_store
        store = get_store()
        u = store.get_user(chat_id)
        if u and u.get("role"):
            return u["role"]
    except Exception:
        pass
    return "user"


def ask(prompt: str, timeout: int, *, chat_id: int | None = None) -> str:
    """Call local Ollama server via native /api/chat endpoint."""
    model = _resolve_ollama_model(chat_id)
    url = f"{OLLAMA_URL.rstrip('/')}/api/chat"
    headers = {"Content-Type": "application/json"}
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": OLLAMA_THINK,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "num_predict": LOCAL_MAX_TOKENS,
            "temperature": effective_temperature(),
            **({"num_ctx": OLLAMA_NUM_CTX} if OLLAMA_NUM_CTX > 0 else {}),
        },
    }
    result = http_post_json(url, headers, body, timeout)
    return result["message"]["content"].strip()
