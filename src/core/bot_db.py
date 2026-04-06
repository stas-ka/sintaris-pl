"""
bot_db.py — SQLite data layer for taris.

Provides a thread-local connection and init_db() which creates all tables
using CREATE TABLE IF NOT EXISTS (safe to call on every startup).

Dependency chain: bot_config → bot_db  (no other bot_* imports here)
"""

import json
import sqlite3
import threading
import os

from core.bot_config import log_datastore as log, TARIS_DIR

# ── Database file path ────────────────────────────────────────────────────────
DB_PATH = os.path.join(TARIS_DIR, "taris.db")

SYSTEM_SETTINGS_PATH = os.path.join(TARIS_DIR, "system_settings.json")

# Thread-local storage for per-thread connections
_local = threading.local()


def _is_postgres() -> bool:
    return os.environ.get("STORE_BACKEND", "sqlite").lower() == "postgres"


def _get_store():
    """Lazy store accessor — avoids circular imports at module load time."""
    from core.store import store  # noqa: PLC0415
    return store

# ── Schema ────────────────────────────────────────────────────────────────────
_SCHEMA_SQL = """
-- Core user table (replaces registrations.json + users.json)
CREATE TABLE IF NOT EXISTS users (
    chat_id     INTEGER PRIMARY KEY,
    username    TEXT,
    name        TEXT,
    role        TEXT    DEFAULT 'pending',
    language    TEXT    DEFAULT 'ru',
    audio_on    INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    approved_at TEXT
);

-- Voice optimisation flags (replaces voice_opts.json)
CREATE TABLE IF NOT EXISTS voice_opts (
    chat_id              INTEGER PRIMARY KEY REFERENCES users(chat_id),
    silence_strip        INTEGER DEFAULT 0,
    low_sample_rate      INTEGER DEFAULT 0,
    warm_piper           INTEGER DEFAULT 0,
    parallel_tts         INTEGER DEFAULT 0,
    user_audio_toggle    INTEGER DEFAULT 0,
    tmpfs_model          INTEGER DEFAULT 0,
    vad_prefilter        INTEGER DEFAULT 0,
    whisper_stt          INTEGER DEFAULT 0,
    piper_low_model      INTEGER DEFAULT 0,
    persistent_piper     INTEGER DEFAULT 0,
    voice_timing_debug   INTEGER DEFAULT 0,
    vosk_fallback        INTEGER DEFAULT 1,
    voice_male           INTEGER DEFAULT 0
);

-- Global voice optimisation flags (system-wide, not per-user)
CREATE TABLE IF NOT EXISTS global_voice_opts (
    key    TEXT PRIMARY KEY,
    value  INTEGER NOT NULL DEFAULT 0
);

-- Calendar events (replaces calendar/<chat_id>.json)
CREATE TABLE IF NOT EXISTS calendar_events (
    id                TEXT    PRIMARY KEY,
    chat_id           INTEGER,
    title             TEXT    NOT NULL,
    dt_iso            TEXT    NOT NULL,
    remind_before_min INTEGER DEFAULT 15,
    reminded          INTEGER DEFAULT 0,
    created_at        TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_calendar_chat_dt
    ON calendar_events(chat_id, dt_iso);

-- Notes index and content (content also stored in DB since v2026.3.31)
CREATE TABLE IF NOT EXISTS notes_index (
    slug        TEXT,
    chat_id     INTEGER,
    title       TEXT    NOT NULL,
    content     TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (slug, chat_id)
);

-- Per-user mail credentials (replaces mail_creds/<chat_id>.json)
CREATE TABLE IF NOT EXISTS mail_creds (
    chat_id      INTEGER PRIMARY KEY,
    provider     TEXT,
    email        TEXT,
    imap_host    TEXT,
    imap_port    INTEGER DEFAULT 993,
    password_enc TEXT,
    target_email TEXT,
    updated_at   TEXT    DEFAULT (datetime('now'))
);

-- Conversation history per user
CREATE TABLE IF NOT EXISTS chat_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    call_id    TEXT,
    created_at TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_history_chat_time
    ON chat_history(chat_id, created_at);

-- LLM calls tracker — records which history entries were included in each call
CREATE TABLE IF NOT EXISTS llm_calls (
    call_id            TEXT    PRIMARY KEY,
    chat_id            INTEGER NOT NULL,
    provider           TEXT,
    history_count      INTEGER DEFAULT 0,
    history_ids        TEXT,
    prompt_chars       INTEGER DEFAULT 0,
    response_ok        INTEGER DEFAULT 1,
    -- extended trace columns (added in v2026.5.x)
    model              TEXT    DEFAULT '',
    temperature        REAL    DEFAULT 0.0,
    system_chars       INTEGER DEFAULT 0,
    history_chars      INTEGER DEFAULT 0,
    rag_chunks_count   INTEGER DEFAULT 0,
    rag_context_chars  INTEGER DEFAULT 0,
    response_preview   TEXT    DEFAULT '',
    context_snapshot   TEXT    DEFAULT '',
    created_at         TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_chat ON llm_calls(chat_id, created_at);

-- TTS orphan cleanup tracker (replaces pending_tts.json)
CREATE TABLE IF NOT EXISTS tts_pending (
    chat_id    INTEGER PRIMARY KEY,
    msg_id     INTEGER NOT NULL,
    created_at TEXT    DEFAULT (datetime('now'))
);

-- Contacts
CREATE TABLE IF NOT EXISTS contacts (
    id          TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(4)))),
    chat_id     INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    phone       TEXT,
    email       TEXT,
    address     TEXT,
    notes       TEXT,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_contacts_chat_name
    ON contacts(chat_id, name COLLATE NOCASE);

-- Documents / Knowledge Base metadata (Phase 2d)
CREATE TABLE IF NOT EXISTS documents (
    doc_id      TEXT    PRIMARY KEY,
    chat_id     INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    file_path   TEXT,
    doc_type    TEXT,
    is_shared   INTEGER DEFAULT 0,
    doc_hash    TEXT,
    metadata    TEXT,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_docs_chat ON documents(chat_id);

-- Document text chunks — FTS5 full-text index (always available, zero dependencies)
CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks USING fts5(
    doc_id    UNINDEXED,
    chunk_idx UNINDEXED,
    chat_id   UNINDEXED,
    chunk_text,
    tokenize  = 'unicode61'
);

-- RAG query log (admin audit + last-N-queries viewer)
CREATE TABLE IF NOT EXISTS rag_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id        INTEGER NOT NULL,
    query          TEXT    NOT NULL,
    query_type     TEXT    NOT NULL DEFAULT 'contextual',
    n_chunks       INTEGER NOT NULL DEFAULT 0,
    chars_injected INTEGER NOT NULL DEFAULT 0,
    latency_ms     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_rag_log_chat ON rag_log(chat_id, created_at DESC);
-- Migration: add columns to pre-existing rag_log (ALTER TABLE IF NOT EXISTS column missing)
-- SQLite does not support IF NOT EXISTS in ALTER TABLE, so we use a workaround in init_db.


-- Conversation summaries — tiered short/mid/long-term memory
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    summary     TEXT    NOT NULL,
    tier        TEXT    NOT NULL DEFAULT 'mid',  -- 'mid' or 'long'
    msg_count   INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_summ_chat ON conversation_summaries(chat_id, tier, created_at DESC);

-- Per-user preferences (toggleable settings)
CREATE TABLE IF NOT EXISTS user_prefs (
    chat_id    INTEGER,
    key        TEXT,
    value      TEXT    NOT NULL DEFAULT '1',
    updated_at TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (chat_id, key)
);

-- System-wide settings (admin-configurable)
CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Security event log (access denied, auth failures, admin ops)
CREATE TABLE IF NOT EXISTS security_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    event_type  TEXT    NOT NULL,
    detail      TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sec_events_chat ON security_events(chat_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sec_events_type ON security_events(event_type, created_at DESC);

-- Web UI accounts (replaces accounts.json)
CREATE TABLE IF NOT EXISTS web_accounts (
    user_id           TEXT    PRIMARY KEY,
    username          TEXT    UNIQUE NOT NULL,
    display_name      TEXT    DEFAULT '',
    pw_hash           TEXT    NOT NULL,
    role              TEXT    DEFAULT 'user',
    status            TEXT    DEFAULT 'active',
    telegram_chat_id  INTEGER,
    created           TEXT    DEFAULT (datetime('now')),
    is_approved       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_web_accounts_chat ON web_accounts(telegram_chat_id);

-- Password reset tokens (replaces reset_tokens.json)
CREATE TABLE IF NOT EXISTS web_reset_tokens (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    token    TEXT    UNIQUE NOT NULL,
    username TEXT    NOT NULL,
    expires  TEXT    NOT NULL,
    used     INTEGER DEFAULT 0
);

-- Telegram↔Web link codes (replaces web_link_codes.json)
CREATE TABLE IF NOT EXISTS web_link_codes (
    code        TEXT    PRIMARY KEY,
    chat_id     INTEGER NOT NULL,
    expires_at  TEXT    NOT NULL
);
"""


# ── Connection management ─────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating it if needed."""
    if not getattr(_local, "conn", None):
        os.makedirs(TARIS_DIR, exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn


def init_db() -> None:
    """Create all tables on startup.  Safe to call every time — idempotent."""
    conn = get_db()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    # Migrations: add columns to existing tables (idempotent — ignore if already present)
    for _migration in [
        "ALTER TABLE chat_history ADD COLUMN call_id TEXT",
        "ALTER TABLE documents ADD COLUMN doc_hash TEXT",
        # llm_calls extended trace columns (v2026.5.x)
        "ALTER TABLE llm_calls ADD COLUMN model TEXT DEFAULT ''",
        "ALTER TABLE llm_calls ADD COLUMN temperature REAL DEFAULT 0.0",
        "ALTER TABLE llm_calls ADD COLUMN system_chars INTEGER DEFAULT 0",
        "ALTER TABLE llm_calls ADD COLUMN history_chars INTEGER DEFAULT 0",
        "ALTER TABLE llm_calls ADD COLUMN rag_chunks_count INTEGER DEFAULT 0",
        "ALTER TABLE llm_calls ADD COLUMN rag_context_chars INTEGER DEFAULT 0",
        "ALTER TABLE llm_calls ADD COLUMN response_preview TEXT DEFAULT ''",
        "ALTER TABLE llm_calls ADD COLUMN context_snapshot TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(_migration)
        except Exception:
            pass  # column already exists
    # notes_index content column (added in v2026.3.31)
    try:
        conn.execute("ALTER TABLE notes_index ADD COLUMN content TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass  # column already exists
    # rag_log latency_ms + query_type columns (added in v2026.3.32)
    for _col_sql in [
        "ALTER TABLE rag_log ADD COLUMN query_type TEXT NOT NULL DEFAULT 'contextual'",
        "ALTER TABLE rag_log ADD COLUMN latency_ms INTEGER NOT NULL DEFAULT 0",
    ]:
        try:
            conn.execute(_col_sql)
        except Exception:
            pass  # column already exists
    # voice_male column (added in v2026.4.25)
    try:
        conn.execute("ALTER TABLE voice_opts ADD COLUMN voice_male INTEGER DEFAULT 0")
    except Exception:
        pass  # column already exists
    conn.commit()
    log.info(f"[DB] init OK : {DB_PATH}")


def close_db() -> None:
    """Close and discard the thread-local connection (used in tests and teardown)."""
    conn = getattr(_local, "conn", None)
    if conn:
        conn.close()
        _local.conn = None


_VOICE_OPT_KEYS = [
    "silence_strip", "low_sample_rate", "warm_piper", "parallel_tts",
    "user_audio_toggle", "tmpfs_model", "vad_prefilter", "whisper_stt",
    "vosk_fallback", "piper_low_model", "persistent_piper", "voice_timing_debug",
    "voice_male",
]


def db_save_voice_opts(opts: dict) -> None:
    """Persist all voice-opt flags to the global_voice_opts table."""
    conn = get_db()
    for key in _VOICE_OPT_KEYS:
        conn.execute(
            "INSERT INTO global_voice_opts(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, 1 if opts.get(key) else 0),
        )
    conn.commit()


def db_get_voice_opts() -> dict:
    """Return all voice-opt flags from the global_voice_opts table."""
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM global_voice_opts").fetchall()
    result = {row[0]: bool(row[1]) for row in rows}
    for key in _VOICE_OPT_KEYS:
        result.setdefault(key, False)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Conversation history helpers
# ─────────────────────────────────────────────────────────────────────────────

def db_add_history(chat_id: int, role: str, content: str,
                   call_id: str | None = None) -> int:
    """Insert a conversation message. Returns the row id."""
    if _is_postgres():
        try:
            return _get_store().append_history_tracked(chat_id, role, content, call_id)
        except Exception as exc:
            log.warning("[History] store.append_history_tracked failed: %s", exc)
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO chat_history (chat_id, role, content, call_id) VALUES (?,?,?,?)",
        (chat_id, role, content, call_id),
    )
    conn.commit()
    return cur.lastrowid


def db_get_history(chat_id: int, limit: int = 15) -> list:
    """Return the last *limit* messages for chat_id, oldest first."""
    if _is_postgres():
        try:
            return _get_store().get_history(chat_id, last_n=limit)
        except Exception as exc:
            log.warning("[History] store.get_history failed: %s", exc)
    conn = get_db()
    rows = conn.execute(
        "SELECT id, role, content FROM chat_history "
        "WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    return [
        {"_db_id": r["id"], "role": r["role"], "content": r["content"]}
        for r in reversed(rows)
    ]


def db_clear_history(chat_id: int) -> None:
    """Delete all stored conversation history for a user."""
    if _is_postgres():
        try:
            _get_store().clear_history(chat_id)
            return
        except Exception as exc:
            log.warning("[History] store.clear_history failed: %s", exc)
    conn = get_db()
    conn.execute("DELETE FROM chat_history WHERE chat_id = ?", (chat_id,))
    conn.commit()


def db_log_llm_call(
    call_id: str, chat_id: int, provider: str,
    history_ids: list, prompt_chars: int, response_ok: bool,
    *,
    model: str = "",
    temperature: float = 0.0,
    system_chars: int = 0,
    history_chars: int = 0,
    rag_chunks_count: int = 0,
    rag_context_chars: int = 0,
    response_preview: str = "",
    context_snapshot: str = "",
) -> None:
    if _is_postgres():
        try:
            _get_store().log_llm_call(
                call_id, chat_id, provider, history_ids, prompt_chars, response_ok,
                model=model, temperature=temperature, system_chars=system_chars,
                history_chars=history_chars, rag_chunks_count=rag_chunks_count,
                rag_context_chars=rag_context_chars,
                response_preview=response_preview, context_snapshot=context_snapshot,
            )
            return
        except Exception as exc:
            log.warning("[LLMTrace] store.log_llm_call failed: %s", exc)
    import json as _json
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO llm_calls "
        "(call_id, chat_id, provider, history_count, history_ids, prompt_chars, response_ok,"
        " model, temperature, system_chars, history_chars,"
        " rag_chunks_count, rag_context_chars, response_preview, context_snapshot) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            call_id, chat_id, provider, len(history_ids),
            _json.dumps(history_ids), prompt_chars,
            1 if response_ok else 0,
            model, temperature, system_chars, history_chars,
            rag_chunks_count, rag_context_chars,
            response_preview[:300] if response_preview else "",
            context_snapshot,
        ),
    )
    conn.commit()


def db_get_llm_trace(chat_id: int, limit: int = 10) -> list:
    """Return the N most recent LLM calls for a user with full trace info."""
    if _is_postgres():
        try:
            return _get_store().get_llm_trace(chat_id, limit=limit)
        except Exception as exc:
            log.warning("[LLMTrace] store.get_llm_trace failed: %s", exc)
    conn = get_db()
    rows = conn.execute(
        "SELECT call_id, provider, model, temperature, history_count, history_chars,"
        " system_chars, rag_chunks_count, rag_context_chars,"
        " response_preview, context_snapshot, response_ok, created_at "
        "FROM llm_calls WHERE chat_id=? ORDER BY created_at DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Per-user preferences helpers
# ─────────────────────────────────────────────────────────────────────────────

def db_get_user_pref(chat_id: int, key: str, default: str = "1") -> str:
    if _is_postgres():
        try:
            return _get_store().get_user_pref(chat_id, key, default)
        except Exception as exc:
            log.warning("[UserPrefs] store.get_user_pref failed: %s", exc)
    try:
        db = get_db()
        row = db.execute(
            "SELECT value FROM user_prefs WHERE chat_id=? AND key=?", (chat_id, key)
        ).fetchone()
        return row[0] if row else default
    except Exception:
        return default


def db_set_user_pref(chat_id: int, key: str, value: str) -> None:
    if _is_postgres():
        try:
            _get_store().set_user_pref(chat_id, key, value)
            return
        except Exception as exc:
            log.warning("[UserPrefs] store.set_user_pref failed: %s", exc)
    try:
        db = get_db()
        db.execute(
            """INSERT INTO user_prefs(chat_id, key, value, updated_at)
               VALUES(?,?,?,datetime('now'))
               ON CONFLICT(chat_id,key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')""",
            (chat_id, key, value),
        )
        db.commit()
    except Exception as exc:
        log.warning("[UserPrefs] set failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# System settings helpers (admin-configurable)
# ─────────────────────────────────────────────────────────────────────────────

def db_get_system_setting(key: str, default: str = "") -> str:
    """Get a system setting from JSON file (~/.taris/system_settings.json)."""
    try:
        with open(SYSTEM_SETTINGS_PATH) as f:
            return json.load(f).get(key, default)
    except Exception:
        return default


def db_set_system_setting(key: str, value: str) -> None:
    """Set a system setting in JSON file (~/.taris/system_settings.json)."""
    try:
        data: dict = {}
        try:
            with open(SYSTEM_SETTINGS_PATH) as f:
                data = json.load(f)
        except Exception:
            pass
        data[key] = value
        os.makedirs(os.path.dirname(SYSTEM_SETTINGS_PATH), exist_ok=True)
        with open(SYSTEM_SETTINGS_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        log.warning("[SysSettings] set failed: %s", exc)
