"""
bot_db.py — SQLite data layer for picoclaw.

Provides a thread-local connection and init_db() which creates all tables
using CREATE TABLE IF NOT EXISTS (safe to call on every startup).

Dependency chain: bot_config → bot_db  (no other bot_* imports here)
"""

import sqlite3
import threading
import os

from bot_config import log

# ── Database file path ────────────────────────────────────────────────────────
_PICOCLAW_DIR = os.path.expanduser("~/.picoclaw")
DB_PATH = os.path.join(_PICOCLAW_DIR, "pico.db")

# Thread-local storage for per-thread connections
_local = threading.local()

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
    voice_timing_debug   INTEGER DEFAULT 0
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

-- Notes metadata index (content stays in .md files)
CREATE TABLE IF NOT EXISTS notes_index (
    slug        TEXT,
    chat_id     INTEGER,
    title       TEXT    NOT NULL,
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
    created_at TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_history_chat_time
    ON chat_history(chat_id, created_at);

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
"""


# ── Connection management ─────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating it if needed."""
    if not getattr(_local, "conn", None):
        os.makedirs(_PICOCLAW_DIR, exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn


def init_db() -> None:
    """Create all tables on startup.  Safe to call every time — idempotent."""
    conn = get_db()
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    log.info(f"[DB] init OK : {DB_PATH}")
