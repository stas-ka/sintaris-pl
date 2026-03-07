"""
bot_state.py — Mutable runtime state shared across all handler modules.

Holds all per-user session dicts, caches, and persisted voice/user settings.
Load/save helpers for voice_opts and dynamic_users are also here because they
are tightly coupled to the state they manage.
"""

import json
from pathlib import Path
from typing import Optional

from bot_config import (
    USERS_FILE,
    _VOICE_OPTS_FILE,
    _VOICE_OPTS_DEFAULTS,
    log,
)

# ─────────────────────────────────────────────────────────────────────────────
# Per-user session state  (keyed by chat_id)
# ─────────────────────────────────────────────────────────────────────────────

# Active mode: None | 'chat' | 'system' | 'voice'
# + transient admin input modes: 'admin_add_user' | 'admin_remove_user'
# + note creation modes: 'note_add_title' | 'note_add_content' | 'note_edit_content'
_user_mode: dict[int, str] = {}

# Pending bash command awaiting user confirmation (system-chat flow)
_pending_cmd: dict[int, str] = {}

# Per-user UI language ('ru' | 'en'), detected from Telegram language_code
_user_lang: dict[int, str] = {}

# Per-user audio preference (True = play audio; default when user_audio_toggle enabled)
_user_audio: dict[int, bool] = {}

# Multi-step note creation state
# Format: {"step": "title"|"content"|"edit_content", "slug": str, "title": str}
_pending_note: dict[int, dict] = {}

# Admin is waiting to paste an LLM API key into chat
_pending_llm_key: dict[int, str] = {}

# ─────────────────────────────────────────────────────────────────────────────
# Singleton caches
# ─────────────────────────────────────────────────────────────────────────────

# Vosk model loaded once on first voice message
_vosk_model_cache = None

# §5.3 persistent_piper: Popen handle that holds the ONNX model in page cache
_persistent_piper_proc = None

# ─────────────────────────────────────────────────────────────────────────────
# Voice optimization options — persisted to _VOICE_OPTS_FILE
# ─────────────────────────────────────────────────────────────────────────────

def _load_voice_opts() -> dict:
    """Load voice optimization flags from disk; merge with defaults."""
    try:
        saved = json.loads(Path(_VOICE_OPTS_FILE).read_text(encoding="utf-8"))
        opts = dict(_VOICE_OPTS_DEFAULTS)
        opts.update({k: v for k, v in saved.items() if k in opts})
        return opts
    except FileNotFoundError:
        return dict(_VOICE_OPTS_DEFAULTS)
    except Exception as e:
        log.warning(f"[VoiceOpts] load failed: {e}")
        return dict(_VOICE_OPTS_DEFAULTS)


def _save_voice_opts() -> None:
    """Persist current voice optimization flags to disk."""
    try:
        Path(_VOICE_OPTS_FILE).write_text(
            json.dumps(_voice_opts, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"[VoiceOpts] save failed: {e}")


_voice_opts: dict = _load_voice_opts()

# ─────────────────────────────────────────────────────────────────────────────
# Dynamic guest users — runtime-added by admin, persisted to USERS_FILE
# ─────────────────────────────────────────────────────────────────────────────

def _load_dynamic_users() -> set[int]:
    try:
        data = json.loads(Path(USERS_FILE).read_text(encoding="utf-8"))
        return {int(x) for x in data.get("users", [])}
    except Exception:
        return set()


def _save_dynamic_users() -> None:
    try:
        Path(USERS_FILE).write_text(
            json.dumps({"users": sorted(_dynamic_users)}, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"[State] save dynamic_users failed: {e}")


_dynamic_users: set[int] = _load_dynamic_users()
