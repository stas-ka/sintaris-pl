"""
bot_state.py — Mutable runtime state shared across all handler modules.

Holds all per-user session dicts, caches, and persisted voice/user settings.
Load/save helpers for voice_opts and dynamic_users are also here because they
are tightly coupled to the state they manage.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from core.bot_config import (
    CONVERSATION_HISTORY_FILE,
    CONVERSATION_HISTORY_MAX,
    CONVERSATION_PERSIST,
    CONV_SUMMARY_THRESHOLD,
    CONV_MID_MAX,
    USERS_FILE,
    _VOICE_OPTS_FILE,
    _VOICE_OPTS_DEFAULTS,
    _WEB_LINK_CODES_FILE,
    log,
    get_conv_history_max,
    get_conv_summary_threshold,
    get_conv_mid_max,
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

# Per-user system-chat conversation history (in-memory, NOT written to DB)
# Kept separate from user chat history. Each entry: {"role": "user"|"assistant", "content": str}
_system_history: dict[int, list] = {}

# Per-user UI language ('ru' | 'en'), detected from Telegram language_code
_user_lang: dict[int, str] = {}

# Per-user audio preference (True = play audio; default when user_audio_toggle enabled)
_user_audio: dict[int, bool] = {}

# Multi-step note creation state
# Format: {"step": "title"|"content"|"edit_content", "slug": str, "title": str}
_pending_note: dict[int, dict] = {}

# Admin is waiting to paste an LLM API key into chat
_pending_llm_key: dict[int, str] = {}

# Non-allowed user's Telegram info stored while awaiting their name input
# Format: {"username": str, "first_name": str, "last_name": str}
_pending_registration: dict[int, dict] = {}

# Error protocol collection state
# Format: {"name": str, "dir": str, "texts": list, "voices": list, "photos": list}
_pending_error_protocol: dict[int, dict] = {}

# Web account link codes — shared between Telegram and Web processes via file
# Format on disk: {"CODE": {"chat_id": int, "expires_at": ISO-8601 string}}
# Codes expire after WEB_LINK_CODE_TTL_MINUTES and are single-use.

WEB_LINK_CODE_TTL_MINUTES = 15


def _load_web_link_codes() -> dict:
    """Load non-expired link codes from shared JSON file. Returns {} on any error."""
    try:
        data = json.loads(Path(_WEB_LINK_CODES_FILE).read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        codes = {}
        for code, entry in data.items():
            expires = datetime.fromisoformat(entry["expires_at"])
            if not expires.tzinfo:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires > now:
                codes[code] = {"chat_id": entry["chat_id"], "expires_at": expires}
        return codes
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
        return {}
    except Exception as e:
        log.warning(f"[WebLink] load failed: {e}")
        return {}


def _save_web_link_codes(codes: dict) -> None:
    """Atomically save active link codes to shared JSON file."""
    try:
        data = {
            code: {
                "chat_id":    entry["chat_id"],
                "expires_at": entry["expires_at"].isoformat(),
            }
            for code, entry in codes.items()
        }
        target = Path(_WEB_LINK_CODES_FILE)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(target)
    except Exception as e:
        log.warning(f"[WebLink] save failed: {e}")


def generate_web_link_code(chat_id: int) -> str:
    """Generate a 6-character alphanumeric link code for the given chat_id.
    Any previous code for this user is replaced. Returns the new code."""
    import random, string
    codes = _load_web_link_codes()
    # Revoke any existing code for this user
    for existing_code, entry in list(codes.items()):
        if entry["chat_id"] == chat_id:
            del codes[existing_code]
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    codes[code] = {
        "chat_id":    chat_id,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=WEB_LINK_CODE_TTL_MINUTES),
    }
    _save_web_link_codes(codes)
    return code


def validate_web_link_code(code: str) -> Optional[int]:
    """Validate a link code. Returns chat_id if valid, None if invalid/expired.
    Consumes the code on success (single-use)."""
    codes = _load_web_link_codes()
    key   = code.upper().strip()
    entry = codes.get(key)
    if not entry:
        return None
    if datetime.now(timezone.utc) > entry["expires_at"]:
        codes.pop(key, None)
        _save_web_link_codes(codes)
        return None
    codes.pop(key, None)  # single-use
    _save_web_link_codes(codes)
    return entry["chat_id"]

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
    try:
        from core.store import store                          # lazy — avoids circular import
        from core.store_sqlite import _VOICE_OPT_COLUMNS     # injection-safe whitelist
        for key, val in _voice_opts.items():
            if key in _VOICE_OPT_COLUMNS:
                store.set_voice_opt(key, val)
    except Exception as _e:
        log.warning(f"[VoiceOpts] store.set_voice_opt failed: {_e}")


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

# ─────────────────────────────────────────────────────────────────────────────
# Conversation history  (Feature 2.1 — sliding window, optional persistence)
# ─────────────────────────────────────────────────────────────────────────────

# Per-user history.  Format: [{"role": "user"|"assistant", "content": str}]
_conversation_history: dict[int, list] = {}


def add_to_history(chat_id: int, role: str, content: str,
                   call_id: str | None = None) -> int:
    """Append a message to the user's history.
    Writes to SQLite (primary storage) and the in-memory cache.
    When the session reaches CONV_SUMMARY_THRESHOLD messages, triggers async summarization.
    Returns the DB row id for call-tracking purposes.
    """
    from core.bot_db import db_add_history
    db_id = db_add_history(chat_id, role, content, call_id)
    try:
        from core.store import store as _st
        _st.append_history(chat_id, role, content)
    except Exception as _e:
        log.debug("[State] store.append_history failed: %s", _e)
    hist = _conversation_history.setdefault(chat_id, [])
    hist.append({"role": role, "content": content, "_db_id": db_id})
    if len(hist) >= get_conv_summary_threshold() and role == "assistant":
        # Summarize what we have before trimming
        _summarize_session_async(chat_id, list(hist))
    if len(hist) > get_conv_history_max():
        _conversation_history[chat_id] = hist[-get_conv_history_max():]
    return db_id


def get_history(chat_id: int) -> list[dict]:
    """Return conversation history without internal _db_id fields (for LLM calls)."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in _conversation_history.get(chat_id, [])
    ]


def get_history_with_ids(chat_id: int) -> list[dict]:
    """Return history entries including _db_id for LLM call tracking."""
    return list(_conversation_history.get(chat_id, []))


def clear_history(chat_id: int) -> None:
    """Clear the conversation history for a user (in-memory + DB + all summary tiers)."""
    from core.bot_db import db_clear_history, get_db
    _conversation_history.pop(chat_id, None)
    db_clear_history(chat_id)
    try:
        db = get_db()
        db.execute("DELETE FROM conversation_summaries WHERE chat_id = ?", (chat_id,))
        db.commit()
    except Exception as exc:
        log.warning("[Memory] clear summaries failed: %s", exc)


def _summarize_session_async(chat_id: int, messages: list) -> None:
    """Summarize the given messages and store as mid-term memory. Runs in background thread."""
    import threading

    def _do():
        try:
            from core.bot_llm import ask_llm
            from core.bot_db import get_db
            sample = "\n".join(
                f"{m['role'].upper()}: {m['content'][:200]}" for m in messages[-20:]
            )
            prompt = (
                "Summarize the following conversation fragment in 2-4 sentences. "
                "Focus on facts, topics discussed, and user preferences. "
                "Write in the same language as the conversation.\n\n"
                f"{sample}"
            )
            summary = ask_llm(prompt, timeout=30)
            if not summary or len(summary.strip()) < 10:
                return
            db = get_db()
            # Count mid-tier summaries
            count = db.execute(
                "SELECT COUNT(*) FROM conversation_summaries WHERE chat_id=? AND tier='mid'",
                (chat_id,),
            ).fetchone()[0]
            if count >= get_conv_mid_max():
                # Compact mid-term → long-term
                rows = db.execute(
                    "SELECT summary FROM conversation_summaries "
                    "WHERE chat_id=? AND tier='mid' ORDER BY created_at ASC",
                    (chat_id,),
                ).fetchall()
                all_text = "\n".join(r[0] for r in rows)
                long_prompt = (
                    "Compress these conversation summaries into one concise paragraph "
                    "preserving key facts, preferences and topics:\n\n" + all_text
                )
                long_summary = ask_llm(long_prompt, timeout=30)
                if long_summary and len(long_summary.strip()) >= 10:
                    db.execute("DELETE FROM conversation_summaries WHERE chat_id=? AND tier='mid'", (chat_id,))
                    db.execute(
                        "INSERT INTO conversation_summaries(chat_id, summary, tier, msg_count) VALUES(?,?,?,?)",
                        (chat_id, long_summary.strip(), "long", len(messages)),
                    )
                    db.commit()
            db.execute(
                "INSERT INTO conversation_summaries(chat_id, summary, tier, msg_count) VALUES(?,?,?,?)",
                (chat_id, summary.strip(), "mid", len(messages)),
            )
            db.commit()
            log.info("[Memory] stored mid-term summary for user %s", chat_id)
        except Exception as exc:
            log.warning("[Memory] summarize failed: %s", exc)

    threading.Thread(target=_do, daemon=True).start()


def get_memory_context(chat_id: int) -> str:
    """Return formatted long+mid-term memory summaries as a context prefix (may be empty)."""
    try:
        from core.bot_db import get_db
        db = get_db()
        rows = db.execute(
            "SELECT tier, summary FROM conversation_summaries "
            "WHERE chat_id=? ORDER BY tier DESC, created_at ASC",
            (chat_id,),
        ).fetchall()
        if not rows:
            return ""
        parts = ["[Memory context from previous sessions:]"]
        for r in rows:
            parts.append(f"[{r[0].upper()}] {r[1]}")
        return "\n".join(parts) + "\n"
    except Exception as exc:
        log.debug("[Memory] get_memory_context failed: %s", exc)
        return ""


def load_conversation_history() -> None:
    """Load recent histories from the DB into the in-memory cache (call once at startup)."""
    try:
        from core.bot_db import get_db, db_get_history
        conn = get_db()
        chat_ids = [
            row[0] for row in conn.execute(
                "SELECT DISTINCT chat_id FROM chat_history"
            ).fetchall()
        ]
        loaded = 0
        for cid in chat_ids:
            rows = db_get_history(cid, limit=get_conv_history_max())
            if rows:
                _conversation_history[cid] = rows
                loaded += 1
        if loaded:
            log.info(f"[History] Loaded DB histories for {loaded} users")
    except Exception as exc:
        log.warning(f"[History] Could not load conversation history from DB: {exc}")


def _save_conversation_history() -> None:
    """Persist conversation histories to disk."""
    try:
        path = Path(CONVERSATION_HISTORY_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {str(k): v for k, v in _conversation_history.items()}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning(f"[History] Could not save conversation history: {exc}")
