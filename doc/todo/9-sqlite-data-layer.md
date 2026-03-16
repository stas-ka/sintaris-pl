# SQLite Data Layer — Spec

**Goal:** Migrate from per-user JSON files to `~/.picoclaw/pico.db`.  
`src/bot_db.py` skeleton exists (v2026.3.30); migration pending.

---

## §9.1 Decision Matrix: SQLite vs Files

| Data type | Store in | Reason |
|---|---|---|
| User records, roles, registration | ✅ **SQLite** | Filtering by status, relational joins, transactional approval |
| Calendar events | ✅ **SQLite** | Date-range queries, reminder scheduling, multi-user access |
| Notes metadata (title, mtime, tags) | ✅ **SQLite** | Fast listing, search/sort by title or date |
| Notes content | ✅ **files** (.md) | Git-trackable, rendered directly, binary-safe |
| Mail credentials | ✅ **SQLite** | Transactional updates, relational to users |
| Chat history / conversation window | ✅ **SQLite** | Time-ordered queries, per-user windowed retrieval |
| Voice opts flags | ✅ **SQLite** | Per-user row in `voice_opts` table |
| TTS orphan tracker | ✅ **SQLite** | ACID guarantees for cleanup state |
| Bot secrets (`bot.env`) | ✅ **files** | Version-controlled template, never in DB |
| picoclaw config (`config.json`) | ✅ **files** | Owned by picoclaw binary |
| LLM model selection (`active_model.txt`) | ✅ **files** | Single global value, rarely changes |
| Voice/audio model files (`.onnx`, Vosk) | ✅ **files** | Binary blobs, no query benefit |
| Error protocol bundles | 🔀 **hybrid** | Files on disk; manifest metadata row in SQLite |
| Static assets (CSS, JS, templates) | ✅ **files** | Served directly by FastAPI/Jinja2 |

---

## §9.2 Database File Location

| Environment | Path |
|---|---|
| Pi (production) | `~/.picoclaw/pico.db` |
| Local dev / tests | `~/.picoclaw/pico_test.db` or `:memory:` |

---

## §9.3 Schema (7 Tables)

```sql
-- Users (replaces registrations.json + users.json)
CREATE TABLE IF NOT EXISTS users (
    chat_id     INTEGER PRIMARY KEY,
    username    TEXT,
    name        TEXT,
    role        TEXT    DEFAULT 'pending',  -- pending | approved | blocked | admin
    language    TEXT    DEFAULT 'ru',
    audio_on    INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    approved_at TEXT
);

-- Voice optimisation flags (replaces voice_opts.json)
CREATE TABLE IF NOT EXISTS voice_opts (
    chat_id            INTEGER PRIMARY KEY REFERENCES users(chat_id),
    silence_strip      INTEGER DEFAULT 0,
    low_sample_rate    INTEGER DEFAULT 0,
    warm_piper         INTEGER DEFAULT 0,
    parallel_tts       INTEGER DEFAULT 0,
    user_audio_toggle  INTEGER DEFAULT 0,
    tmpfs_model        INTEGER DEFAULT 0,
    vad_prefilter      INTEGER DEFAULT 0,
    whisper_stt        INTEGER DEFAULT 0,
    piper_low_model    INTEGER DEFAULT 0,
    persistent_piper   INTEGER DEFAULT 0,
    voice_timing_debug INTEGER DEFAULT 0
);

-- Calendar events (replaces calendar/<chat_id>.json)
CREATE TABLE IF NOT EXISTS calendar_events (
    id                TEXT    PRIMARY KEY,
    chat_id           INTEGER REFERENCES users(chat_id),
    title             TEXT    NOT NULL,
    dt_iso            TEXT    NOT NULL,
    remind_before_min INTEGER DEFAULT 15,
    reminded          INTEGER DEFAULT 0,
    created_at        TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_calendar_chat_dt ON calendar_events(chat_id, dt_iso);

-- Notes metadata index (content stays in .md files)
CREATE TABLE IF NOT EXISTS notes_index (
    slug        TEXT,
    chat_id     INTEGER REFERENCES users(chat_id),
    title       TEXT    NOT NULL,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (slug, chat_id)
);

-- Per-user mail credentials (replaces mail_creds/<chat_id>.json)
CREATE TABLE IF NOT EXISTS mail_creds (
    chat_id      INTEGER PRIMARY KEY REFERENCES users(chat_id),
    provider     TEXT,
    email        TEXT,
    imap_host    TEXT,
    imap_port    INTEGER DEFAULT 993,
    password_enc TEXT,
    target_email TEXT,
    updated_at   TEXT    DEFAULT (datetime('now'))
);

-- Conversation history (new — needed for §2.1 memory feature)
CREATE TABLE IF NOT EXISTS chat_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER REFERENCES users(chat_id),
    role       TEXT    NOT NULL,  -- 'user' | 'assistant'
    content    TEXT    NOT NULL,
    created_at TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_history_chat_time ON chat_history(chat_id, created_at);

-- TTS orphan cleanup tracker (replaces pending_tts.json)
CREATE TABLE IF NOT EXISTS tts_pending (
    chat_id    INTEGER PRIMARY KEY,
    msg_id     INTEGER NOT NULL,
    created_at TEXT    DEFAULT (datetime('now'))
);
```

---

## §9.4 Migration Plan (files → SQLite)

| Phase | Description | Risk |
|---|---|---|
| **Phase 1** — Schema creation | `CREATE TABLE IF NOT EXISTS` on startup; existing files untouched | Zero |
| **Phase 2** — Dual-write | New writes go to both DB and legacy files; reads from DB with file fallback | Zero |
| **Phase 3** — Migrate existing data | `migrate_to_db.py` reads all JSON files, inserts into DB (idempotent) | Low |
| **Phase 4** — DB-only reads | Remove file fallback; legacy files kept as read-only backup | Low |
| **Phase 5** — Archive legacy files | Move old JSONs to `~/.picoclaw/legacy_json_backup/` | Zero |

**Migration checklist:**
- [x] `src/bot_db.py` created — `get_db()`, `init_db()`, schema SQL (v2026.3.30)
- [x] `init_db()` called in `main()` before handler registration (v2026.3.30)
- [ ] Phase 2: dual-write wrappers for `_upsert_registration`, `_save_voice_opts`, `_cal_save`, mail creds
- [ ] Phase 3: `src/setup/migrate_to_db.py` — idempotent, skip existing rows
- [ ] Phase 4: remove file fallback from all readers
- [ ] Phase 5: archive old JSON files after confirmed clean run

---

## §9.5 `bot_db.py` — CRUD Helper Stubs

```python
# Dependency: bot_config → bot_db → bot_state → …
import sqlite3, threading

_DB_PATH = os.path.join(PICOCLAW_DIR, 'pico.db')
_local = threading.local()  # per-thread connection (telebot uses threadpool)

def get_db() -> sqlite3.Connection: ...          # thread-local connection, creates if needed
def init_db() -> None: ...                        # CREATE TABLE IF NOT EXISTS; called at startup

# Users
def get_user(chat_id: int) -> sqlite3.Row | None: ...
def upsert_user(chat_id, username, name, role) -> None: ...

# Voice opts
def get_voice_opts(chat_id: int) -> dict: ...    # returns defaults if no row
def set_voice_opt(chat_id: int, key: str, value: bool) -> None: ...

# Calendar
def get_calendar_events(chat_id, from_dt=None, to_dt=None) -> list: ...
def upsert_calendar_event(chat_id: int, ev_dict: dict) -> None: ...
def delete_calendar_event(ev_id: str) -> bool: ...

# Chat history
def get_chat_history(chat_id: int, limit: int = 15) -> list: ...
def append_history(chat_id: int, role: str, content: str) -> None: ...
def trim_history(chat_id: int, keep: int = 15) -> None: ...
```

---

## §9.6 Testing

- [ ] T22 `sqlite_schema`: `init_db()` creates all 7 tables; `get_user()` / `upsert_user()` round-trips; `get_calendar_events()` date filter returns correct subset
- [ ] T23 `migration_idempotent`: run `migrate_to_db.py` twice on same source → no duplicate rows, no error
- [ ] Update T18 (`profile_resilience`) to test DB read path when available
- [ ] All existing tests must pass with DB initialised — use `:memory:` DB for test isolation (set `PICO_DB=:memory:` env var)
