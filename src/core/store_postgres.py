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

from core.bot_config import NOTES_DIR, log

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
    vosk_fallback        BOOLEAN DEFAULT TRUE
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
    call_id       TEXT        PRIMARY KEY,
    chat_id       BIGINT      NOT NULL,
    provider      TEXT,
    history_count INTEGER     DEFAULT 0,
    history_ids   TEXT,
    prompt_chars  INTEGER     DEFAULT 0,
    response_ok   BOOLEAN     DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
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
    metadata   TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_documents_chat ON documents(chat_id);

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
        # Execute statements one by one — psycopg requires separate execute calls
        # for DDL that contains semicolons (avoids potential parsing issues)
        for stmt in _SCHEMA_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    conn.execute(stmt)
                except Exception as exc:
                    # Tolerate "already exists" errors during parallel starts
                    log.debug("[StorePostgres] DDL warning: %s", exc)

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

    def save_note(self, chat_id: int, slug: str, title: str, content: str) -> None:
        import os as _os
        note_dir = _os.path.join(NOTES_DIR, str(chat_id))
        _os.makedirs(note_dir, exist_ok=True)
        note_path = _os.path.join(note_dir, f"{slug}.md")
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
        import os as _os
        note_path = _os.path.join(NOTES_DIR, str(chat_id), f"{slug}.md")
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

        import os as _os
        path = _os.path.join(NOTES_DIR, str(chat_id), f"{slug}.md")
        try:
            _os.remove(path)
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
                           metadata: dict | None = None) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO documents
                   (doc_id, chat_id, title, file_path, doc_type, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (doc_id) DO UPDATE SET
                       title      = EXCLUDED.title,
                       file_path  = EXCLUDED.file_path,
                       doc_type   = EXCLUDED.doc_type,
                       metadata   = EXCLUDED.metadata,
                       updated_at = NOW()""",
                (
                    doc_id, chat_id, title, file_path, doc_type,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            conn.commit()

    def list_documents(self, chat_id: int) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE chat_id = %s ORDER BY created_at DESC",
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
                "SELECT doc_id, chunk_text, "
                "  (embedding <=> %s::vector) AS distance "
                "FROM vec_embeddings "
                "WHERE chat_id = %s "
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

    # ── FTS5 text search (stubs — not implemented for Postgres) ───────────────

    def has_document_search(self) -> bool:
        return False  # Postgres adapter uses pgvector; FTS5 not implemented here

    def upsert_chunk_text(self, doc_id: str, chunk_idx: int, chat_id: int,
                          chunk_text: str) -> None:
        pass  # not implemented for Postgres

    def search_fts(self, query: str, chat_id: int, top_k: int = 5) -> list[dict]:
        return []  # not implemented for Postgres

    def delete_text_chunks(self, doc_id: str) -> None:
        pass  # not implemented for Postgres

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        try:
            self._pool.close()
        except Exception:
            pass
