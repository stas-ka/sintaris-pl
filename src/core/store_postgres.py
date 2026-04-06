"""
store_postgres.py — PostgreSQL implementation of the DataStore Protocol.

Requires: psycopg[binary] psycopg-pool pgvector
Optional: cryptography (for credential encryption via STORE_CRED_KEY env var)

Environment variables:
  STORE_PG_DSN          PostgreSQL connection DSN
  STORE_CRED_KEY        Fernet key for encrypting mail passwords (optional)
  STORE_HISTORY_WINDOW  Sliding window size for chat history (default: 50)

Dependency chain: core/bot_config → core/store_postgres  (no other bot_* imports)
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from core.bot_config import NOTES_DIR, log_datastore as log

# ── Credential encryption (optional) ─────────────────────────────────────────
_FERNET: Any = None
_cred_key = os.environ.get("STORE_CRED_KEY", "")
if _cred_key:
    try:
        from cryptography.fernet import Fernet
        _FERNET = Fernet(_cred_key.encode())
    except ImportError:
        log.warning("[StorePostgres] cryptography not installed — creds stored unencrypted")


def _encrypt(text: str) -> str:
    return _FERNET.encrypt(text.encode()).decode() if _FERNET and text else text


def _decrypt(text: str) -> str:
    try:
        return _FERNET.decrypt(text.encode()).decode() if _FERNET and text else text
    except Exception:
        return text  # already plaintext (migration fallback)


# ── Field whitelists (prevent SQL injection via column-name injection) ────────
_ALLOWED_USER_FIELDS = frozenset({
    "username", "name", "role", "language", "audio_on", "approved_at",
})

_VOICE_OPT_COLUMNS = frozenset({
    "silence_strip", "low_sample_rate", "warm_piper", "parallel_tts",
    "user_audio_toggle", "tmpfs_model", "vad_prefilter", "whisper_stt",
    "piper_low_model", "persistent_piper", "voice_timing_debug", "vosk_fallback",
    "voice_male",
})

# ── Schema DDL ────────────────────────────────────────────────────────────────
_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    chat_id     BIGINT PRIMARY KEY,
    username    TEXT,
    name        TEXT,
    role        TEXT        DEFAULT 'pending',
    language    TEXT        DEFAULT 'ru',
    audio_on    INTEGER     DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    approved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS voice_opts (
    chat_id              BIGINT PRIMARY KEY REFERENCES users(chat_id) ON DELETE CASCADE,
    silence_strip        BOOLEAN DEFAULT FALSE,
    low_sample_rate      BOOLEAN DEFAULT FALSE,
    warm_piper           BOOLEAN DEFAULT FALSE,
    parallel_tts         BOOLEAN DEFAULT FALSE,
    user_audio_toggle    BOOLEAN DEFAULT FALSE,
    tmpfs_model          BOOLEAN DEFAULT FALSE,
    vad_prefilter        BOOLEAN DEFAULT FALSE,
    whisper_stt          BOOLEAN DEFAULT FALSE,
    piper_low_model      BOOLEAN DEFAULT FALSE,
    persistent_piper     BOOLEAN DEFAULT FALSE,
    voice_timing_debug   BOOLEAN DEFAULT FALSE,
    vosk_fallback        BOOLEAN DEFAULT TRUE,
    voice_male           BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS global_voice_opts (
    key   TEXT PRIMARY KEY,
    value BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id                TEXT        PRIMARY KEY,
    chat_id           BIGINT,
    title             TEXT        NOT NULL,
    dt_iso            TEXT        NOT NULL,
    remind_before_min INTEGER     DEFAULT 15,
    reminded          BOOLEAN     DEFAULT FALSE,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_calendar_chat_dt ON calendar_events(chat_id, dt_iso);

CREATE TABLE IF NOT EXISTS notes_index (
    slug        TEXT,
    chat_id     BIGINT,
    title       TEXT        NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (slug, chat_id)
);

CREATE TABLE IF NOT EXISTS mail_creds (
    chat_id      BIGINT PRIMARY KEY,
    provider     TEXT,
    email        TEXT,
    imap_host    TEXT,
    imap_port    INTEGER     DEFAULT 993,
    password_enc TEXT,
    target_email TEXT,
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_history (
    id         BIGSERIAL   PRIMARY KEY,
    chat_id    BIGINT,
    role       TEXT        NOT NULL,
    content    TEXT        NOT NULL,
    call_id    TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_history_chat_time ON chat_history(chat_id, created_at);

CREATE TABLE IF NOT EXISTS llm_calls (
    call_id            TEXT        PRIMARY KEY,
    chat_id            BIGINT      NOT NULL,
    provider           TEXT,
    history_count      INTEGER     DEFAULT 0,
    history_ids        TEXT,
    prompt_chars       INTEGER     DEFAULT 0,
    response_ok        BOOLEAN     DEFAULT TRUE,
    model              TEXT        DEFAULT '',
    temperature        REAL        DEFAULT 0.0,
    system_chars       INTEGER     DEFAULT 0,
    history_chars      INTEGER     DEFAULT 0,
    rag_chunks_count   INTEGER     DEFAULT 0,
    rag_context_chars  INTEGER     DEFAULT 0,
    response_preview   TEXT        DEFAULT '',
    context_snapshot   TEXT        DEFAULT '',
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contacts (
    id         TEXT        PRIMARY KEY,
    chat_id    BIGINT,
    name       TEXT        NOT NULL,
    phone      TEXT        DEFAULT '',
    email      TEXT        DEFAULT '',
    address    TEXT        DEFAULT '',
    notes      TEXT        DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contacts_chat ON contacts(chat_id);

CREATE TABLE IF NOT EXISTS documents (
    doc_id     TEXT        PRIMARY KEY,
    chat_id    BIGINT,
    title      TEXT        NOT NULL,
    file_path  TEXT        NOT NULL,
    doc_type   TEXT        NOT NULL,
    is_shared  SMALLINT    DEFAULT 0,
    doc_hash   TEXT,
    metadata   TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_documents_chat ON documents(chat_id);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(chat_id, doc_hash);

CREATE TABLE IF NOT EXISTS vec_embeddings (
    id         BIGSERIAL   PRIMARY KEY,
    doc_id     TEXT        NOT NULL,
    chunk_idx  INTEGER     NOT NULL,
    chat_id    BIGINT      NOT NULL,
    chunk_text TEXT,
    embedding  vector(384),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (doc_id, chunk_idx, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_vec_embedding
    ON vec_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_vec_fts
    ON vec_embeddings USING GIN (to_tsvector('simple', coalesce(chunk_text, '')));

CREATE TABLE IF NOT EXISTS rag_log (
    id             BIGSERIAL   PRIMARY KEY,
    chat_id        BIGINT      NOT NULL,
    query          TEXT        NOT NULL,
    query_type     TEXT        NOT NULL DEFAULT 'contextual',
    n_chunks       INTEGER     NOT NULL DEFAULT 0,
    chars_injected INTEGER     NOT NULL DEFAULT 0,
    latency_ms     INTEGER     NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rag_log_chat ON rag_log(chat_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tts_pending (
    chat_id    BIGINT      PRIMARY KEY,
    msg_id     BIGINT      NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id         BIGSERIAL   PRIMARY KEY,
    chat_id    BIGINT      NOT NULL,
    summary    TEXT        NOT NULL,
    tier       TEXT        NOT NULL DEFAULT 'mid',
    msg_count  INTEGER     DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_summ_chat ON conversation_summaries(chat_id, tier, created_at DESC);

CREATE TABLE IF NOT EXISTS user_prefs (
    chat_id    BIGINT,
    key        TEXT,
    value      TEXT        NOT NULL DEFAULT '1',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (chat_id, key)
);

CREATE TABLE IF NOT EXISTS security_events (
    id         BIGSERIAL   PRIMARY KEY,
    chat_id    BIGINT      NOT NULL,
    event_type TEXT        NOT NULL,
    detail     TEXT        DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sec_events_type ON security_events(event_type, created_at DESC);

-- Web UI accounts (replaces accounts.json)
CREATE TABLE IF NOT EXISTS web_accounts (
    user_id           TEXT        PRIMARY KEY,
    username          TEXT        UNIQUE NOT NULL,
    display_name      TEXT        DEFAULT '',
    pw_hash           TEXT        NOT NULL,
    role              TEXT        DEFAULT 'user',
    status            TEXT        DEFAULT 'active',
    telegram_chat_id  BIGINT,
    created           TIMESTAMPTZ DEFAULT NOW(),
    is_approved       BOOLEAN     DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_web_accounts_chat ON web_accounts(telegram_chat_id);

-- Password reset tokens (replaces reset_tokens.json)
CREATE TABLE IF NOT EXISTS web_reset_tokens (
    id       BIGSERIAL   PRIMARY KEY,
    token    TEXT        UNIQUE NOT NULL,
    username TEXT        NOT NULL,
    expires  TIMESTAMPTZ NOT NULL,
    used     BOOLEAN     DEFAULT FALSE
);

-- Telegram↔Web link codes (replaces web_link_codes.json)
CREATE TABLE IF NOT EXISTS web_link_codes (
    code        TEXT        PRIMARY KEY,
    chat_id     BIGINT      NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL
);
"""


# ── PostgresStore ─────────────────────────────────────────────────────────────

class PostgresStore:
    """DataStore Protocol implementation backed by PostgreSQL + pgvector."""

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise ImportError(
                "PostgresStore requires: pip install 'psycopg[binary]' psycopg-pool"
            ) from exc

        self._pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            open=True,
        )

        # Detect pgvector support and initialise schema
        self._has_vec = False
        with self._pool.connection() as conn:
            try:
                from pgvector.psycopg import register_vector
                register_vector(conn)
                self._has_vec = True
            except Exception as exc:
                log.warning("[StorePostgres] pgvector not available — RAG disabled: %s", exc)
            self._init_schema(conn)
            conn.commit()

        log.info("[StorePostgres] connected  vec=%s", self._has_vec)

    def _init_schema(self, conn: Any) -> None:
        # Execute each DDL statement independently so one failure doesn't
        # poison subsequent statements (Postgres transactions abort on error).
        for stmt in _SCHEMA_SQL.split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                # Use a savepoint so a failure only rolls back this one statement
                conn.execute("SAVEPOINT _ddl")
                conn.execute(stmt)
                conn.execute("RELEASE SAVEPOINT _ddl")
            except Exception as exc:
                conn.execute("ROLLBACK TO SAVEPOINT _ddl")
                log.debug("[StorePostgres] DDL skipped (%s): %.80s", type(exc).__name__, stmt)
        # Migrations: add columns that may be missing in pre-existing tables
        _migrations = [
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_hash TEXT",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_shared SMALLINT DEFAULT 0",
            "ALTER TABLE voice_opts ADD COLUMN IF NOT EXISTS voice_male BOOLEAN DEFAULT FALSE",
            # llm_calls extended trace columns (idempotent)
            "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS model TEXT DEFAULT ''",
            "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS temperature REAL DEFAULT 0.0",
            "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS system_chars INTEGER DEFAULT 0",
            "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS history_chars INTEGER DEFAULT 0",
            "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS rag_chunks_count INTEGER DEFAULT 0",
            "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS rag_context_chars INTEGER DEFAULT 0",
            "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS response_preview TEXT DEFAULT ''",
            "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS context_snapshot TEXT DEFAULT ''",
        ]
        for mig in _migrations:
            try:
                conn.execute("SAVEPOINT _mig")
                conn.execute(mig)
                conn.execute("RELEASE SAVEPOINT _mig")
                log.debug("[StorePostgres] Migration applied: %s", mig)
            except Exception as exc:
                conn.execute("ROLLBACK TO SAVEPOINT _mig")
                log.debug("[StorePostgres] Migration skipped: %s", exc)

    # ── Users ─────────────────────────────────────────────────────────────────

    def upsert_user(self, chat_id: int, **fields: Any) -> None:
        cols = {k: v for k, v in fields.items() if k in _ALLOWED_USER_FIELDS}
        if not cols:
            return
        col_names = ", ".join(cols.keys())
        col_placeholders = ", ".join(["%s"] * len(cols))
        updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in cols)
        sql = (
            f"INSERT INTO users (chat_id, {col_names}) VALUES (%s, {col_placeholders}) "
            f"ON CONFLICT (chat_id) DO UPDATE SET {updates}"
        )
        with self._pool.connection() as conn:
            conn.execute(sql, [chat_id, *cols.values()])
            conn.commit()

    def get_user(self, chat_id: int) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE chat_id = %s", (chat_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_users(self, role: str | None = None) -> list[dict]:
        with self._pool.connection() as conn:
            if role:
                rows = conn.execute(
                    "SELECT * FROM users WHERE role = %s ORDER BY created_at", (role,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM users ORDER BY created_at"
                ).fetchall()
        return [dict(r) for r in rows]

    def set_user_role(self, chat_id: int, role: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE users SET role = %s WHERE chat_id = %s", (role, chat_id)
            )
            conn.commit()

    # ── Notes ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _notes_storage_dir(chat_id: int) -> str:
        """Return per-user notes directory, using UUID if account is linked."""
        try:
            import json as _json
            from pathlib import Path as _Path
            from security.bot_auth import ACCOUNTS_FILE
            data = _json.loads(_Path(ACCOUNTS_FILE).read_text(encoding="utf-8"))
            for acct in data.get("accounts", []):
                if acct.get("telegram_chat_id") == chat_id:
                    return os.path.join(NOTES_DIR, acct["user_id"])
        except Exception:
            pass
        return os.path.join(NOTES_DIR, str(chat_id))

    def save_note(self, chat_id: int, slug: str, title: str, content: str) -> None:
        note_dir = self._notes_storage_dir(chat_id)
        os.makedirs(note_dir, exist_ok=True)
        note_path = os.path.join(note_dir, f"{slug}.md")
        with open(note_path, "w", encoding="utf-8") as fh:
            fh.write(content)

        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO notes_index (slug, chat_id, title, updated_at)
                   VALUES (%s, %s, %s, NOW())
                   ON CONFLICT (slug, chat_id) DO UPDATE SET
                       title = EXCLUDED.title, updated_at = NOW()""",
                (slug, chat_id, title),
            )
            conn.commit()

    def load_note(self, chat_id: int, slug: str) -> dict:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM notes_index WHERE slug = %s AND chat_id = %s",
                (slug, chat_id),
            ).fetchone()

        result = dict(row) if row else {"slug": slug, "chat_id": chat_id, "title": slug}
        note_path = os.path.join(self._notes_storage_dir(chat_id), f"{slug}.md")
        try:
            result["content"] = open(note_path, encoding="utf-8").read()
        except FileNotFoundError:
            result["content"] = ""
        return result

    def list_notes(self, chat_id: int) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT slug, title, updated_at FROM notes_index "
                "WHERE chat_id = %s ORDER BY updated_at DESC",
                (chat_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_note(self, chat_id: int, slug: str) -> bool:
        with self._pool.connection() as conn:
            cur = conn.execute(
                "DELETE FROM notes_index WHERE slug = %s AND chat_id = %s",
                (slug, chat_id),
            )
            conn.commit()

        path = os.path.join(self._notes_storage_dir(chat_id), f"{slug}.md")
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return (cur.rowcount or 0) > 0

    # ── Calendar ──────────────────────────────────────────────────────────────

    def save_event(self, chat_id: int, event: dict) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO calendar_events
                   (id, chat_id, title, dt_iso, remind_before_min, reminded)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                       title             = EXCLUDED.title,
                       dt_iso            = EXCLUDED.dt_iso,
                       remind_before_min = EXCLUDED.remind_before_min,
                       reminded          = EXCLUDED.reminded""",
                (
                    event.get("id") or str(uuid.uuid4()),
                    chat_id,
                    event.get("title", ""),
                    event.get("dt_iso", ""),
                    int(event.get("remind_before_min", 15)),
                    bool(event.get("reminded", False)),
                ),
            )
            conn.commit()

    def load_events(self, chat_id: int,
                    from_dt: str | None = None,
                    to_dt: str | None = None) -> list[dict]:
        with self._pool.connection() as conn:
            if from_dt and to_dt:
                rows = conn.execute(
                    "SELECT * FROM calendar_events "
                    "WHERE chat_id = %s AND dt_iso >= %s AND dt_iso <= %s "
                    "ORDER BY dt_iso",
                    (chat_id, from_dt, to_dt),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM calendar_events WHERE chat_id = %s ORDER BY dt_iso",
                    (chat_id,),
                ).fetchall()
        events = [dict(r) for r in rows]
        # Normalise boolean field
        for ev in events:
            ev["reminded"] = bool(ev.get("reminded", False))
        return events

    def delete_event(self, chat_id: int, ev_id: str) -> bool:
        with self._pool.connection() as conn:
            cur = conn.execute(
                "DELETE FROM calendar_events WHERE id = %s AND chat_id = %s",
                (ev_id, chat_id),
            )
            conn.commit()
        return (cur.rowcount or 0) > 0

    # ── Conversation history ───────────────────────────────────────────────────

    def append_history(self, chat_id: int, role: str, content: str) -> None:
        window = int(os.environ.get("STORE_HISTORY_WINDOW", "50"))
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO chat_history (chat_id, role, content) VALUES (%s, %s, %s)",
                (chat_id, role, content),
            )
            # Trim: keep newest `window` rows per chat_id
            conn.execute(
                "DELETE FROM chat_history WHERE id IN ("
                "  SELECT id FROM chat_history WHERE chat_id = %s "
                "  ORDER BY created_at DESC OFFSET %s"
                ")",
                (chat_id, window),
            )
            conn.commit()

    def get_history(self, chat_id: int, last_n: int = 15) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM chat_history "
                "WHERE chat_id = %s ORDER BY created_at DESC LIMIT %s",
                (chat_id, last_n),
            ).fetchall()
        return list(reversed([dict(r) for r in rows]))

    def clear_history(self, chat_id: int) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM chat_history WHERE chat_id = %s", (chat_id,))
            conn.commit()

    # ── Voice opts ────────────────────────────────────────────────────────────

    def get_voice_opts(self, chat_id: int | None = None) -> dict:
        with self._pool.connection() as conn:
            if chat_id is None:
                rows = conn.execute(
                    "SELECT key, value FROM global_voice_opts"
                ).fetchall()
                return {r["key"]: bool(r["value"]) for r in rows}

            row = conn.execute(
                "SELECT * FROM voice_opts WHERE chat_id = %s", (chat_id,)
            ).fetchone()
        if not row:
            return {}
        d = dict(row)
        d.pop("chat_id", None)
        return {k: bool(v) for k, v in d.items()}

    def set_voice_opt(self, key: str, value: bool,
                      chat_id: int | None = None) -> None:
        if key not in _VOICE_OPT_COLUMNS:
            raise ValueError(f"[StorePostgres] set_voice_opt: unknown key {key!r}")
        with self._pool.connection() as conn:
            if chat_id is None:
                conn.execute(
                    "INSERT INTO global_voice_opts (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (key, value),
                )
            else:
                conn.execute(
                    f"INSERT INTO voice_opts (chat_id, {key}) VALUES (%s, %s) "
                    f"ON CONFLICT (chat_id) DO UPDATE SET {key} = EXCLUDED.{key}",
                    (chat_id, value),
                )
            conn.commit()

    # ── Mail credentials ──────────────────────────────────────────────────────

    def get_mail_creds(self, chat_id: int) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM mail_creds WHERE chat_id = %s", (chat_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        raw_pw = d.pop("password_enc", "") or ""
        d["password"] = _decrypt(raw_pw)
        return d

    def save_mail_creds(self, chat_id: int, creds: dict) -> None:
        password_enc = _encrypt(creds.get("password", ""))
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO mail_creds
                   (chat_id, provider, email, imap_host, imap_port,
                    password_enc, target_email)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (chat_id) DO UPDATE SET
                       provider     = EXCLUDED.provider,
                       email        = EXCLUDED.email,
                       imap_host    = EXCLUDED.imap_host,
                       imap_port    = EXCLUDED.imap_port,
                       password_enc = EXCLUDED.password_enc,
                       target_email = EXCLUDED.target_email,
                       updated_at   = NOW()""",
                (
                    chat_id,
                    creds.get("provider", ""),
                    creds.get("email", ""),
                    creds.get("imap_host", ""),
                    int(creds.get("imap_port", 993)),
                    password_enc,
                    creds.get("target_email", ""),
                ),
            )
            conn.commit()

    # ── Contacts ──────────────────────────────────────────────────────────────

    def save_contact(self, chat_id: int, contact: dict) -> str:
        cid = contact.get("id") or str(uuid.uuid4())[:8]
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO contacts
                   (id, chat_id, name, phone, email, address, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                       name       = EXCLUDED.name,
                       phone      = EXCLUDED.phone,
                       email      = EXCLUDED.email,
                       address    = EXCLUDED.address,
                       notes      = EXCLUDED.notes,
                       updated_at = NOW()""",
                (
                    cid, chat_id,
                    contact.get("name", ""),
                    contact.get("phone", ""),
                    contact.get("email", ""),
                    contact.get("address", ""),
                    contact.get("notes", ""),
                ),
            )
            conn.commit()
        return cid

    def get_contact(self, contact_id: str) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM contacts WHERE id = %s", (contact_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_contacts(self, chat_id: int) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE chat_id = %s ORDER BY name",
                (chat_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_contact(self, contact_id: str) -> bool:
        with self._pool.connection() as conn:
            cur = conn.execute(
                "DELETE FROM contacts WHERE id = %s", (contact_id,)
            )
            conn.commit()
        return (cur.rowcount or 0) > 0

    def search_contacts(self, chat_id: int, query: str) -> list[dict]:
        q = f"%{query}%"
        with self._pool.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM contacts
                   WHERE chat_id = %s
                     AND (name ILIKE %s OR phone ILIKE %s
                          OR email ILIKE %s OR notes ILIKE %s)
                   ORDER BY name""",
                (chat_id, q, q, q, q),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Documents / knowledge base ────────────────────────────────────────────

    def save_document_meta(self, doc_id: str, chat_id: int,
                           title: str, file_path: str,
                           doc_type: str,
                           metadata: dict | None = None,
                           doc_hash: str | None = None) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO documents
                   (doc_id, chat_id, title, file_path, doc_type, metadata, doc_hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (doc_id) DO UPDATE SET
                       title      = EXCLUDED.title,
                       file_path  = EXCLUDED.file_path,
                       doc_type   = EXCLUDED.doc_type,
                       metadata   = EXCLUDED.metadata,
                       doc_hash   = EXCLUDED.doc_hash,
                       updated_at = NOW()""",
                (
                    doc_id, chat_id, title, file_path, doc_type,
                    json.dumps(metadata) if metadata else None,
                    doc_hash,
                ),
            )
            conn.commit()

    def list_documents(self, chat_id: int) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE chat_id = %s OR is_shared = 1"
                " ORDER BY created_at DESC",
                (chat_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (ValueError, TypeError):
                    pass
            result.append(d)
        return result

    def delete_document(self, doc_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
            conn.commit()

    # ── Vector / RAG ──────────────────────────────────────────────────────────

    def has_vector_search(self) -> bool:
        return self._has_vec

    def upsert_embedding(self, doc_id: str, chunk_idx: int, chat_id: int,
                         chunk_text: str, embedding: list[float],
                         metadata: dict | None = None) -> None:
        from core.store_base import StoreCapabilityError
        if not self._has_vec:
            raise StoreCapabilityError(
                "pgvector not installed or not enabled — "
                "run: CREATE EXTENSION vector;"
            )
        with self._pool.connection() as conn:
            from pgvector.psycopg import register_vector
            register_vector(conn)
            conn.execute(
                """INSERT INTO vec_embeddings
                   (doc_id, chunk_idx, chat_id, chunk_text, embedding)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (doc_id, chunk_idx, chat_id) DO UPDATE SET
                       chunk_text = EXCLUDED.chunk_text,
                       embedding  = EXCLUDED.embedding,
                       updated_at = NOW()""",
                (doc_id, chunk_idx, chat_id, chunk_text, embedding),
            )
            conn.commit()

    def search_similar(self, embedding: list[float], chat_id: int,
                       top_k: int = 5) -> list[dict]:
        from core.store_base import StoreCapabilityError
        if not self._has_vec:
            raise StoreCapabilityError(
                "pgvector not installed or not enabled — "
                "run: CREATE EXTENSION vector;"
            )
        with self._pool.connection() as conn:
            from pgvector.psycopg import register_vector
            register_vector(conn)
            rows = conn.execute(
                "SELECT doc_id, chunk_idx, chunk_text, "
                "  (embedding <=> %s::vector) AS distance "
                "FROM vec_embeddings "
                "WHERE (chat_id = %s OR doc_id IN ("
                "  SELECT doc_id FROM documents WHERE is_shared = 1)) "
                "ORDER BY embedding <=> %s::vector "
                "LIMIT %s",
                (embedding, chat_id, embedding, top_k),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_embeddings(self, doc_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM vec_embeddings WHERE doc_id = %s", (doc_id,)
            )
            conn.commit()

    # ── FTS text search (Postgres plainto_tsquery on vec_embeddings) ──────────

    def has_document_search(self) -> bool:
        return True  # implemented via Postgres full-text search

    def upsert_chunk_text(self, doc_id: str, chunk_idx: int, chat_id: int,
                          chunk_text: str) -> None:
        """Store a text chunk without a vector (FTS-only path)."""
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO vec_embeddings(doc_id, chunk_idx, chat_id, chunk_text)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (doc_id, chunk_idx, chat_id) DO UPDATE
                    SET chunk_text = EXCLUDED.chunk_text
                """,
                (doc_id, chunk_idx, chat_id, chunk_text),
            )
            conn.commit()

    def search_fts(self, query: str, chat_id: int, top_k: int = 5) -> list[dict]:
        """Full-text search across user's document chunks using Postgres tsvector.

        Uses 'simple' dictionary so no language-specific stemming is needed —
        works for Russian, German, and English without extra config.
        Falls back to ILIKE when no FTS tokens matched.
        """
        import re
        tokens = re.findall(r"\w+", query, re.UNICODE)
        meaningful = [t for t in tokens if len(t) >= 2][:12]
        if not meaningful:
            return []

        # plainto_tsquery automatically handles OR/AND; 'simple' = no stemming
        fts_query = " ".join(meaningful)
        # Include user's own docs AND shared system docs (is_shared=1)
        shared_clause = "(chat_id = %s OR doc_id IN (SELECT doc_id FROM documents WHERE is_shared = 1))"
        try:
            with self._pool.connection() as conn:
                rows = conn.execute(
                    f"""
                    SELECT doc_id, chunk_text,
                           ts_rank(to_tsvector('simple', coalesce(chunk_text,'')),
                                   plainto_tsquery('simple', %s)) AS rank
                    FROM vec_embeddings
                    WHERE {shared_clause}
                      AND chunk_text IS NOT NULL
                      AND to_tsvector('simple', coalesce(chunk_text,''))
                              @@ plainto_tsquery('simple', %s)
                    ORDER BY rank DESC
                    LIMIT %s
                    """,
                    (fts_query, chat_id, fts_query, top_k),
                ).fetchall()
                if rows:
                    return [{"doc_id": r["doc_id"], "chunk_text": r["chunk_text"],
                             "score": float(r["rank"])} for r in rows]

            # Fallback: ILIKE partial match when plainto_tsquery finds nothing
            with self._pool.connection() as conn:
                patterns = [f"%{t}%" for t in meaningful[:4]]
                conditions = " OR ".join("chunk_text ILIKE %s" for _ in patterns)
                rows = conn.execute(
                    f"""
                    SELECT doc_id, chunk_text, 0.01 AS rank
                    FROM vec_embeddings
                    WHERE {shared_clause} AND chunk_text IS NOT NULL
                      AND ({conditions})
                    LIMIT %s
                    """,
                    (chat_id, *patterns, top_k),
                ).fetchall()
                return [{"doc_id": r["doc_id"], "chunk_text": r["chunk_text"],
                         "score": float(r["rank"])} for r in rows]
        except Exception as exc:
            log.warning("[StorePostgres] FTS search error: %s", exc)
            return []

    def delete_text_chunks(self, doc_id: str) -> None:
        """Remove all text chunks for a document (rows without embeddings only)."""
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM vec_embeddings WHERE doc_id = %s AND embedding IS NULL",
                (doc_id,),
            )
            conn.commit()

    def get_document_by_hash(self, chat_id: int, doc_hash: str) -> dict | None:
        """Return document record matching hash for given user, or None."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE chat_id = %s AND doc_hash = %s",
                (chat_id, doc_hash),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (ValueError, TypeError):
                pass
        return d

    def update_document_field(self, doc_id: str, **fields) -> None:
        """Update arbitrary scalar fields on a document record."""
        if not fields:
            return
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values()) + [doc_id]
        with self._pool.connection() as conn:
            conn.execute(
                f"UPDATE documents SET {set_clause}, updated_at = NOW() WHERE doc_id = %s",
                values,
            )
            conn.commit()

    def log_rag_activity(self, chat_id: int, query: str, n_chunks: int, chars: int,
                         latency_ms: int = 0, query_type: str = "contextual",
                         n_fts5: int = 0, n_vector: int = 0, n_mcp: int = 0) -> None:
        """Insert one RAG retrieval record into rag_log."""
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO rag_log(chat_id, query, query_type, n_chunks, chars_injected, latency_ms)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (chat_id, query, query_type, n_chunks, chars, latency_ms),
            )
            conn.commit()

    def list_rag_log(self, limit: int = 20) -> list[dict]:
        """Return up to *limit* most recent RAG log rows, newest first."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, chat_id, query, query_type, n_chunks, chars_injected,"
                " latency_ms, created_at "
                "FROM rag_log ORDER BY created_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def append_history_tracked(self, chat_id: int, role: str, content: str,
                                call_id: str | None = None) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO chat_history (chat_id, role, content, call_id) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (chat_id, role, content, call_id),
            ).fetchone()
            conn.commit()
        return row[0] if row else 0

    def log_llm_call(
        self, call_id: str, chat_id: int, provider: str,
        history_ids: list, prompt_chars: int, response_ok: bool,
        *, model: str = "", temperature: float = 0.0,
        system_chars: int = 0, history_chars: int = 0,
        rag_chunks_count: int = 0, rag_context_chars: int = 0,
        response_preview: str = "", context_snapshot: str = "",
    ) -> None:
        import json as _json
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO llm_calls (call_id, chat_id, provider, history_count, history_ids,"
                " prompt_chars, response_ok, model, temperature, system_chars, history_chars,"
                " rag_chunks_count, rag_context_chars, response_preview, context_snapshot)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (call_id) DO NOTHING",
                (
                    call_id, chat_id, provider, len(history_ids),
                    _json.dumps(history_ids), prompt_chars, response_ok,
                    model, temperature, system_chars, history_chars,
                    rag_chunks_count, rag_context_chars,
                    response_preview[:300] if response_preview else "",
                    context_snapshot,
                ),
            )
            conn.commit()

    def get_llm_trace(self, chat_id: int, limit: int = 10) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT call_id, provider, model, temperature, history_count, history_chars,"
                " system_chars, rag_chunks_count, rag_context_chars,"
                " response_preview, context_snapshot, response_ok, created_at "
                "FROM llm_calls WHERE chat_id=%s ORDER BY created_at DESC LIMIT %s",
                (chat_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def set_tts_pending(self, chat_id: int, msg_id: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO tts_pending (chat_id, msg_id) VALUES (%s, %s)"
                " ON CONFLICT (chat_id) DO UPDATE SET msg_id = EXCLUDED.msg_id",
                (chat_id, msg_id),
            )
            conn.commit()

    def get_tts_pending(self, chat_id: int) -> int | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT msg_id FROM tts_pending WHERE chat_id = %s", (chat_id,)
            ).fetchone()
        return row[0] if row else None

    def clear_tts_pending(self, chat_id: int) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM tts_pending WHERE chat_id = %s", (chat_id,))
            conn.commit()

    def save_summary(self, chat_id: int, summary: str,
                     tier: str = "mid", msg_count: int = 0) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO conversation_summaries (chat_id, summary, tier, msg_count)"
                " VALUES (%s, %s, %s, %s)",
                (chat_id, summary, tier, msg_count),
            )
            conn.commit()

    def count_summaries(self, chat_id: int, tier: str = "mid") -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM conversation_summaries WHERE chat_id=%s AND tier=%s",
                (chat_id, tier),
            ).fetchone()
        return row[0] if row else 0

    def get_summaries_oldest(self, chat_id: int, tier: str = "mid") -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, summary, tier, msg_count, created_at "
                "FROM conversation_summaries WHERE chat_id=%s AND tier=%s "
                "ORDER BY created_at ASC",
                (chat_id, tier),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_summaries(self, chat_id: int, tier: str | None = None) -> None:
        with self._pool.connection() as conn:
            if tier is None:
                conn.execute(
                    "DELETE FROM conversation_summaries WHERE chat_id = %s", (chat_id,)
                )
            else:
                conn.execute(
                    "DELETE FROM conversation_summaries WHERE chat_id = %s AND tier = %s",
                    (chat_id, tier),
                )
            conn.commit()

    def get_all_summaries(self, chat_id: int) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT tier, summary FROM conversation_summaries "
                "WHERE chat_id = %s ORDER BY tier DESC, created_at ASC",
                (chat_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_user_pref(self, chat_id: int, key: str, default: str = "1") -> str:
        try:
            with self._pool.connection() as conn:
                row = conn.execute(
                    "SELECT value FROM user_prefs WHERE chat_id=%s AND key=%s",
                    (chat_id, key),
                ).fetchone()
            return row[0] if row else default
        except Exception:
            return default

    def set_user_pref(self, chat_id: int, key: str, value: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO user_prefs (chat_id, key, value)"
                " VALUES (%s, %s, %s)"
                " ON CONFLICT (chat_id, key) DO UPDATE SET value = EXCLUDED.value",
                (chat_id, key, value),
            )
            conn.commit()

    def log_security_event(self, chat_id: int, event_type: str,
                           detail: str = "") -> None:
        try:
            with self._pool.connection() as conn:
                conn.execute(
                    "INSERT INTO security_events (chat_id, event_type, detail)"
                    " VALUES (%s, %s, %s)",
                    (chat_id, event_type, detail[:500]),
                )
                conn.commit()
        except Exception:
            pass  # non-critical

    def list_security_events(self, limit: int = 50) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT created_at, event_type, chat_id, detail "
                "FROM security_events ORDER BY created_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_active_chat_ids(self) -> list[int]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT chat_id FROM chat_history"
            ).fetchall()
        return [r[0] for r in rows]

    def get_chunks_without_embeddings(self, chat_id_filter: int | None = None) -> list[dict]:
        """Return text chunks that have no vector embedding yet.

        In Postgres, both text and vectors live in ``vec_embeddings``;
        rows where ``embedding IS NULL`` are FTS-only chunks awaiting embedding.
        """
        with self._pool.connection() as conn:
            if chat_id_filter is not None:
                rows = conn.execute(
                    "SELECT doc_id, chunk_idx, chat_id, chunk_text"
                    " FROM vec_embeddings"
                    " WHERE chat_id = %s AND embedding IS NULL"
                    " ORDER BY doc_id, chunk_idx",
                    (chat_id_filter,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT doc_id, chunk_idx, chat_id, chunk_text"
                    " FROM vec_embeddings"
                    " WHERE embedding IS NULL"
                    " ORDER BY doc_id, chunk_idx",
                ).fetchall()
        return [dict(r) for r in rows]

    def rag_stats(self) -> dict:
        """Return aggregate RAG stats for the admin monitoring page."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total, AVG(latency_ms) AS avg_latency_ms,"
                " AVG(n_chunks) AS avg_chunks, SUM(n_chunks) AS total_chunks,"
                " SUM(chars_injected) AS total_chars"
                " FROM rag_log"
            ).fetchone()
            top = conn.execute(
                "SELECT query, COUNT(*) AS cnt FROM rag_log"
                " GROUP BY query ORDER BY cnt DESC LIMIT 5"
            ).fetchall()
            types = conn.execute(
                "SELECT query_type, COUNT(*) AS cnt FROM rag_log GROUP BY query_type"
            ).fetchall()
        r = dict(row) if row else {}
        return {
            "total": r.get("total") or 0,
            "avg_latency_ms": round(float(r.get("avg_latency_ms") or 0), 1),
            "avg_chunks": round(float(r.get("avg_chunks") or 0), 1),
            "total_chunks": r.get("total_chunks") or 0,
            "total_chars": r.get("total_chars") or 0,
            "top_queries": [dict(t) for t in top],
            "query_types": {t["query_type"]: t["cnt"] for t in types},
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def upsert_web_account(self, account: dict) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO web_accounts"
                " (user_id, username, display_name, pw_hash, role, status,"
                "  telegram_chat_id, created, is_approved)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (user_id) DO UPDATE SET"
                "  username=EXCLUDED.username, display_name=EXCLUDED.display_name,"
                "  pw_hash=EXCLUDED.pw_hash, role=EXCLUDED.role,"
                "  status=EXCLUDED.status, telegram_chat_id=EXCLUDED.telegram_chat_id,"
                "  is_approved=EXCLUDED.is_approved",
                (
                    account["user_id"], account["username"].lower(),
                    account.get("display_name", ""),
                    account["pw_hash"], account.get("role", "user"),
                    account.get("status", "active"),
                    account.get("telegram_chat_id"),
                    account.get("created", ""),
                    bool(account.get("is_approved", False)),
                ),
            )
            conn.commit()

    def find_web_account(self, *,
                         user_id: str | None = None,
                         username: str | None = None,
                         chat_id: int | None = None) -> dict | None:
        with self._pool.connection() as conn:
            if user_id:
                row = conn.execute(
                    "SELECT * FROM web_accounts WHERE user_id = %s", (user_id,)
                ).fetchone()
            elif username:
                row = conn.execute(
                    "SELECT * FROM web_accounts WHERE username = %s",
                    (username.lower(),),
                ).fetchone()
            elif chat_id is not None:
                row = conn.execute(
                    "SELECT * FROM web_accounts WHERE telegram_chat_id = %s", (chat_id,)
                ).fetchone()
            else:
                return None
        return dict(row) if row else None

    def update_web_account(self, user_id: str, **fields) -> bool:
        _allowed = {"username", "display_name", "pw_hash", "role", "status",
                    "telegram_chat_id", "is_approved"}
        updates = {k: v for k, v in fields.items() if k in _allowed}
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        with self._pool.connection() as conn:
            cur = conn.execute(
                f"UPDATE web_accounts SET {set_clause} WHERE user_id = %s",
                list(updates.values()) + [user_id],
            )
            conn.commit()
        return (cur.rowcount or 0) > 0

    def list_web_accounts(self) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM web_accounts ORDER BY created"
            ).fetchall()
        return [dict(r) for r in rows]

    def save_reset_token(self, token: str, username: str, expires: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO web_reset_tokens (token, username, expires)"
                " VALUES (%s, %s, %s::TIMESTAMPTZ)"
                " ON CONFLICT (token) DO UPDATE SET"
                "  username=EXCLUDED.username, expires=EXCLUDED.expires, used=FALSE",
                (token, username.lower(), expires),
            )
            conn.commit()

    def find_reset_token(self, token: str) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM web_reset_tokens WHERE token = %s AND used = FALSE",
                (token,),
            ).fetchone()
        return dict(row) if row else None

    def mark_reset_token_used(self, token: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE web_reset_tokens SET used = TRUE WHERE token = %s", (token,)
            )
            conn.commit()

    def delete_reset_tokens_for_user(self, username: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM web_reset_tokens WHERE username = %s", (username.lower(),)
            )
            conn.commit()

    def save_link_code(self, code: str, chat_id: int, expires_at: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO web_link_codes (code, chat_id, expires_at)"
                " VALUES (%s, %s, %s::TIMESTAMPTZ)"
                " ON CONFLICT (code) DO UPDATE SET"
                "  chat_id=EXCLUDED.chat_id, expires_at=EXCLUDED.expires_at",
                (code, chat_id, expires_at),
            )
            conn.commit()

    def find_link_code(self, code: str) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT code, chat_id, expires_at FROM web_link_codes WHERE code = %s",
                (code,),
            ).fetchone()
        return dict(row) if row else None

    def delete_link_code(self, code: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM web_link_codes WHERE code = %s", (code,))
            conn.commit()

    def delete_expired_link_codes(self) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM web_link_codes WHERE expires_at < NOW()")
            conn.commit()

    def close(self) -> None:
        try:
            self._pool.close()
        except Exception:
            pass
