"""
store_sqlite.py — SQLite adapter implementing the DataStore Protocol.

Uses bot_db.get_db() for thread-local connections so all code shares
a single connection pool per thread.

Optional features:
  - sqlite-vec:  KNN vector search (install via src/setup/install_sqlite_vec.sh)
  - Fernet:      credential encryption at rest (set STORE_CRED_KEY in bot.env)

Dependency chain: bot_config → bot_db → store_base → store_sqlite
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from typing import Any

from core.bot_config import log, NOTES_DIR
from core.bot_db import get_db, _local as _db_local  # shared thread-local
from core.store_base import StoreCapabilityError

# ── Optional: sqlite-vec for vector / RAG ────────────────────────────────────
try:
    import sqlite_vec as _sqlite_vec
    _VEC_AVAILABLE = True
except ImportError:
    _VEC_AVAILABLE = False

# ── Optional: Fernet credential encryption ───────────────────────────────────
_FERNET: Any = None
_cred_key = os.environ.get("STORE_CRED_KEY", "")
if _cred_key:
    try:
        from cryptography.fernet import Fernet
        _FERNET = Fernet(_cred_key.encode())
    except Exception as _ferr:
        log.warning("[Store] STORE_CRED_KEY set but Fernet init failed: %s — "
                    "credentials will not be encrypted", _ferr)

# ── sqlite-vec virtual table DDL (created dynamically when extension loads) ───
_VEC_TABLE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS vec_embeddings USING vec0(
    doc_id      TEXT NOT NULL,
    chunk_idx   INTEGER NOT NULL,
    chat_id     INTEGER NOT NULL,
    chunk_text  TEXT,
    embedding   FLOAT[384]
);
"""

# ── Valid voice-opt column names (whitelist prevents SQL injection) ───────────
_VOICE_OPT_COLUMNS: frozenset[str] = frozenset({
    "silence_strip", "low_sample_rate", "warm_piper", "parallel_tts",
    "user_audio_toggle", "tmpfs_model", "vad_prefilter", "whisper_stt",
    "piper_low_model", "persistent_piper", "voice_timing_debug", "vosk_fallback",
})


# ── Fernet helpers ────────────────────────────────────────────────────────────

def _encrypt(text: str) -> str:
    if _FERNET and text:
        return _FERNET.encrypt(text.encode()).decode()
    return text


def _decrypt(text: str) -> str:
    if _FERNET and text:
        try:
            return _FERNET.decrypt(text.encode()).decode()
        except Exception:
            return text  # already plaintext (pre-encryption migration)
    return text


# ── SQLiteStore ───────────────────────────────────────────────────────────────

class SQLiteStore:
    """SQLite-backed implementation of DataStore.

    Shares the thread-local connection from bot_db.get_db() so all modules
    use the same connection per thread — no extra file handles.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._has_vec = False

        conn = self._db()

        # ── Try to load sqlite-vec ────────────────────────────────────────────
        vectors_enabled = os.environ.get("STORE_VECTORS", "on").lower() != "off"
        if _VEC_AVAILABLE and vectors_enabled:
            try:
                _sqlite_vec.load(conn)
                conn.executescript(_VEC_TABLE_SQL)
                conn.commit()
                self._has_vec = True
                log.info("[Store] sqlite-vec loaded — vector search enabled")
            except Exception as exc:
                log.warning("[Store] sqlite-vec load failed: %s — "
                            "vector search disabled", exc)
        elif not _VEC_AVAILABLE:
            log.debug("[Store] sqlite-vec not installed — "
                      "install with: pip install sqlite-vec")

    def _db(self) -> sqlite3.Connection:
        """Return thread-local connection; reload sqlite-vec if needed."""
        conn = get_db()
        if _VEC_AVAILABLE and self._has_vec:
            try:
                _sqlite_vec.load(conn)
            except Exception:
                pass  # already loaded in this connection
        return conn

    # ── User management ───────────────────────────────────────────────────────

    _ALLOWED_USER_FIELDS: frozenset[str] = frozenset({
        "username", "name", "role", "language", "audio_on", "approved_at",
    })

    def upsert_user(self, chat_id: int, **fields) -> None:
        cols = {k: v for k, v in fields.items() if k in self._ALLOWED_USER_FIELDS}
        if not cols:
            return
        col_names = ", ".join(cols.keys())
        col_vals  = ", ".join("?" * len(cols))
        updates   = ", ".join(f"{k} = excluded.{k}" for k in cols)
        sql = (
            f"INSERT INTO users (chat_id, {col_names}) VALUES (?, {col_vals}) "
            f"ON CONFLICT(chat_id) DO UPDATE SET {updates}"
        )
        db = self._db()
        db.execute(sql, [chat_id, *cols.values()])
        db.commit()

    def get_user(self, chat_id: int) -> dict | None:
        row = self._db().execute(
            "SELECT * FROM users WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_users(self, role: str | None = None) -> list[dict]:
        if role:
            rows = self._db().execute(
                "SELECT * FROM users WHERE role = ? ORDER BY created_at", (role,)
            ).fetchall()
        else:
            rows = self._db().execute(
                "SELECT * FROM users ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def set_user_role(self, chat_id: int, role: str) -> None:
        db = self._db()
        db.execute("UPDATE users SET role = ? WHERE chat_id = ?", (role, chat_id))
        db.commit()

    # ── Notes ─────────────────────────────────────────────────────────────────

    def save_note(self, chat_id: int, slug: str, title: str,
                  content: str) -> None:
        db = self._db()
        db.execute(
            """INSERT INTO notes_index (slug, chat_id, title,
                                        created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), datetime('now'))
               ON CONFLICT(slug, chat_id) DO UPDATE SET
                   title      = excluded.title,
                   updated_at = datetime('now')""",
            (slug, chat_id, title),
        )
        db.commit()
        # Content stays in .md file (mirrors bot_users._save_note_file)
        user_dir = os.path.join(NOTES_DIR, str(chat_id))
        os.makedirs(user_dir, exist_ok=True)
        with open(os.path.join(user_dir, f"{slug}.md"), "w", encoding="utf-8") as fh:
            fh.write(f"# {title}\n\n{content}")

    def load_note(self, chat_id: int, slug: str) -> dict | None:
        row = self._db().execute(
            "SELECT * FROM notes_index WHERE slug = ? AND chat_id = ?",
            (slug, chat_id),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        path = os.path.join(NOTES_DIR, str(chat_id), f"{slug}.md")
        try:
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
            # Strip "# title\n\n" header if present
            parts = raw.split("\n\n", 1)
            result["content"] = parts[1] if len(parts) > 1 else raw
        except FileNotFoundError:
            result["content"] = ""
        return result

    def list_notes(self, chat_id: int) -> list[dict]:
        rows = self._db().execute(
            "SELECT slug, title, updated_at FROM notes_index "
            "WHERE chat_id = ? ORDER BY updated_at DESC",
            (chat_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_note(self, chat_id: int, slug: str) -> bool:
        db = self._db()
        cur = db.execute(
            "DELETE FROM notes_index WHERE slug = ? AND chat_id = ?",
            (slug, chat_id),
        )
        db.commit()
        path = os.path.join(NOTES_DIR, str(chat_id), f"{slug}.md")
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return cur.rowcount > 0

    # ── Calendar ──────────────────────────────────────────────────────────────

    def save_event(self, chat_id: int, event: dict) -> None:
        db = self._db()
        db.execute(
            """INSERT INTO calendar_events
               (id, chat_id, title, dt_iso, remind_before_min, reminded)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   title             = excluded.title,
                   dt_iso            = excluded.dt_iso,
                   remind_before_min = excluded.remind_before_min,
                   reminded          = excluded.reminded""",
            (
                event.get("id") or str(uuid.uuid4()),
                chat_id,
                event.get("title", ""),
                event.get("dt_iso", ""),
                int(event.get("remind_before_min", 15)),
                int(bool(event.get("reminded", False))),
            ),
        )
        db.commit()

    def load_events(self, chat_id: int,
                    from_dt: str | None = None,
                    to_dt: str | None = None) -> list[dict]:
        if from_dt and to_dt:
            rows = self._db().execute(
                "SELECT * FROM calendar_events "
                "WHERE chat_id = ? AND dt_iso >= ? AND dt_iso <= ? "
                "ORDER BY dt_iso",
                (chat_id, from_dt, to_dt),
            ).fetchall()
        else:
            rows = self._db().execute(
                "SELECT * FROM calendar_events WHERE chat_id = ? ORDER BY dt_iso",
                (chat_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_event(self, chat_id: int, ev_id: str) -> bool:
        db = self._db()
        cur = db.execute(
            "DELETE FROM calendar_events WHERE id = ? AND chat_id = ?",
            (ev_id, chat_id),
        )
        db.commit()
        return cur.rowcount > 0

    # ── Conversation history ───────────────────────────────────────────────────

    def append_history(self, chat_id: int, role: str, content: str) -> None:
        window = int(os.environ.get("STORE_HISTORY_WINDOW", "50"))
        db = self._db()
        db.execute(
            "INSERT INTO chat_history (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        # Trim sliding window — keep newest `window` messages per user
        db.execute(
            """DELETE FROM chat_history WHERE id IN (
               SELECT id FROM chat_history WHERE chat_id = ?
               ORDER BY created_at DESC LIMIT -1 OFFSET ?)""",
            (chat_id, window),
        )
        db.commit()

    def get_history(self, chat_id: int, last_n: int = 15) -> list[dict]:
        rows = self._db().execute(
            "SELECT role, content, created_at FROM chat_history "
            "WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
            (chat_id, last_n),
        ).fetchall()
        return list(reversed([dict(r) for r in rows]))  # oldest-first

    def clear_history(self, chat_id: int) -> None:
        db = self._db()
        db.execute("DELETE FROM chat_history WHERE chat_id = ?", (chat_id,))
        db.commit()

    # ── Voice opts ────────────────────────────────────────────────────────────

    def get_voice_opts(self, chat_id: int | None = None) -> dict:
        if chat_id is None:
            rows = self._db().execute(
                "SELECT key, value FROM global_voice_opts"
            ).fetchall()
            return {r["key"]: bool(r["value"]) for r in rows}
        row = self._db().execute(
            "SELECT * FROM voice_opts WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        if not row:
            return {}
        d = dict(row)
        d.pop("chat_id", None)
        return {k: bool(v) for k, v in d.items()}

    def set_voice_opt(self, key: str, value: bool,
                      chat_id: int | None = None) -> None:
        if key not in _VOICE_OPT_COLUMNS:
            raise ValueError(f"[Store] set_voice_opt: unknown key {key!r}")
        db = self._db()
        if chat_id is None:
            db.execute(
                "INSERT INTO global_voice_opts (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, int(value)),
            )
        else:
            # key is validated against whitelist — safe to use in identifier position
            db.execute(
                f"INSERT INTO voice_opts (chat_id, {key}) VALUES (?, ?) "
                f"ON CONFLICT(chat_id) DO UPDATE SET {key} = excluded.{key}",
                (chat_id, int(value)),
            )
        db.commit()

    # ── Mail credentials ──────────────────────────────────────────────────────

    def get_mail_creds(self, chat_id: int) -> dict | None:
        row = self._db().execute(
            "SELECT * FROM mail_creds WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        raw_pw = d.pop("password_enc", "") or ""
        d["password"] = _decrypt(raw_pw)
        return d

    def save_mail_creds(self, chat_id: int, creds: dict) -> None:
        password_enc = _encrypt(creds.get("password", ""))
        db = self._db()
        db.execute(
            """INSERT INTO mail_creds
               (chat_id, provider, email, imap_host, imap_port,
                password_enc, target_email)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                   provider     = excluded.provider,
                   email        = excluded.email,
                   imap_host    = excluded.imap_host,
                   imap_port    = excluded.imap_port,
                   password_enc = excluded.password_enc,
                   target_email = excluded.target_email,
                   updated_at   = datetime('now')""",
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
        db.commit()

    # ── Contacts ──────────────────────────────────────────────────────────────

    def save_contact(self, chat_id: int, contact: dict) -> str:
        cid = contact.get("id") or str(uuid.uuid4())[:8]
        db = self._db()
        db.execute(
            """INSERT INTO contacts
               (id, chat_id, name, phone, email, address, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name       = excluded.name,
                   phone      = excluded.phone,
                   email      = excluded.email,
                   address    = excluded.address,
                   notes      = excluded.notes,
                   updated_at = datetime('now')""",
            (
                cid,
                chat_id,
                contact.get("name", ""),
                contact.get("phone", ""),
                contact.get("email", ""),
                contact.get("address", ""),
                contact.get("notes", ""),
            ),
        )
        db.commit()
        return cid

    def get_contact(self, contact_id: str) -> dict | None:
        row = self._db().execute(
            "SELECT * FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_contacts(self, chat_id: int) -> list[dict]:
        rows = self._db().execute(
            "SELECT * FROM contacts WHERE chat_id = ? ORDER BY name COLLATE NOCASE",
            (chat_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_contact(self, contact_id: str) -> bool:
        db = self._db()
        cur = db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        db.commit()
        return cur.rowcount > 0

    def search_contacts(self, chat_id: int, query: str) -> list[dict]:
        q = f"%{query}%"
        rows = self._db().execute(
            """SELECT * FROM contacts
               WHERE chat_id = ?
                 AND (name LIKE ? OR phone LIKE ? OR email LIKE ? OR notes LIKE ?)
               ORDER BY name COLLATE NOCASE""",
            (chat_id, q, q, q, q),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Documents / knowledge base ────────────────────────────────────────────

    def save_document_meta(self, doc_id: str, chat_id: int,
                           title: str, file_path: str,
                           doc_type: str,
                           metadata: dict | None = None) -> None:
        db = self._db()
        db.execute(
            """INSERT INTO documents
               (doc_id, chat_id, title, file_path, doc_type, metadata)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(doc_id) DO UPDATE SET
                   title      = excluded.title,
                   file_path  = excluded.file_path,
                   doc_type   = excluded.doc_type,
                   metadata   = excluded.metadata,
                   updated_at = datetime('now')""",
            (
                doc_id, chat_id, title, file_path, doc_type,
                json.dumps(metadata) if metadata else None,
            ),
        )
        db.commit()

    def list_documents(self, chat_id: int) -> list[dict]:
        rows = self._db().execute(
            "SELECT * FROM documents WHERE chat_id = ? ORDER BY created_at DESC",
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
        db = self._db()
        db.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        db.commit()

    def update_document_field(self, doc_id: str, **fields) -> None:
        """Update arbitrary scalar fields on a document record."""
        if not fields:
            return
        db = self._db()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [doc_id]
        db.execute(
            f"UPDATE documents SET {set_clause}, updated_at = datetime('now') WHERE doc_id = ?",
            values,
        )
        db.commit()

    def get_document_by_hash(self, chat_id: int, doc_hash: str) -> dict | None:
        """Return document record matching hash for given user, or None."""
        row = self._db().execute(
            "SELECT * FROM documents WHERE chat_id = ? AND doc_hash = ?",
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

    # ── Vector / RAG ──────────────────────────────────────────────────────────

    def has_vector_search(self) -> bool:
        return self._has_vec

    def upsert_embedding(self, doc_id: str, chunk_idx: int, chat_id: int,
                         chunk_text: str, embedding: list[float],
                         metadata: dict | None = None) -> None:
        if not self._has_vec:
            raise StoreCapabilityError(
                "sqlite-vec not installed — vector search unavailable. "
                "Install with: pip install sqlite-vec"
            )
        import struct
        vec_blob = struct.pack(f"{len(embedding)}f", *embedding)
        db = self._db()
        # sqlite-vec virtual tables do not support ON CONFLICT — delete + insert
        db.execute(
            "DELETE FROM vec_embeddings WHERE doc_id = ? AND chunk_idx = ?",
            (doc_id, chunk_idx),
        )
        db.execute(
            "INSERT INTO vec_embeddings "
            "(doc_id, chunk_idx, chat_id, chunk_text, embedding) "
            "VALUES (?, ?, ?, ?, ?)",
            (doc_id, chunk_idx, chat_id, chunk_text, vec_blob),
        )
        db.commit()

    def search_similar(self, embedding: list[float], chat_id: int,
                       top_k: int = 5) -> list[dict]:
        if not self._has_vec:
            raise StoreCapabilityError(
                "sqlite-vec not installed — vector search unavailable. "
                "Install with: pip install sqlite-vec"
            )
        import struct
        vec_blob = struct.pack(f"{len(embedding)}f", *embedding)
        rows = self._db().execute(
            """SELECT doc_id, chunk_text, distance
               FROM vec_embeddings
               WHERE chat_id = ?
                 AND embedding MATCH ?
               ORDER BY distance
               LIMIT ?""",
            (chat_id, vec_blob, top_k),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_embeddings(self, doc_id: str) -> None:
        if not self._has_vec:
            return
        db = self._db()
        db.execute("DELETE FROM vec_embeddings WHERE doc_id = ?", (doc_id,))
        db.commit()

    # ── FTS5 text search ──────────────────────────────────────────────────────

    def has_document_search(self) -> bool:
        """Always True — FTS5 is built into SQLite."""
        return True

    def upsert_chunk_text(self, doc_id: str, chunk_idx: int, chat_id: int,
                          chunk_text: str) -> None:
        """Store a text chunk in the FTS5 doc_chunks index."""
        db = self._db()
        db.execute(
            "DELETE FROM doc_chunks WHERE doc_id = ? AND chunk_idx = ?",
            (str(doc_id), str(chunk_idx)),
        )
        db.execute(
            "INSERT INTO doc_chunks(doc_id, chunk_idx, chat_id, chunk_text)"
            " VALUES (?, ?, ?, ?)",
            (str(doc_id), str(chunk_idx), str(chat_id), chunk_text),
        )
        db.commit()

    def search_fts(self, query: str, chat_id: int,
                   top_k: int = 5) -> list[dict]:
        """BM25 full-text search across user's document chunks.

        Sanitises the query to bare words (removes FTS5 special chars) so
        arbitrary user input cannot cause a parse error.
        Uses OR semantics so partial matches work — FTS5 default AND requires
        all words in one chunk which is too strict for natural language queries.
        Returns [{doc_id, chunk_text, score}] ordered best-first.
        """
        import re
        tokens = re.findall(r"\w+", query, re.UNICODE)
        # Keep tokens >= 2 chars to drop single-letter noise; cap at 12 terms
        meaningful = [t for t in tokens if len(t) >= 2][:12]
        if not meaningful:
            return []
        # OR joining: any chunk matching at least one keyword is a candidate;
        # BM25 rank naturally promotes chunks with more/rarer keyword hits
        safe_q = " OR ".join(meaningful)
        try:
            rows = self._db().execute(
                "SELECT doc_id, chunk_text, rank"
                " FROM doc_chunks"
                " WHERE doc_chunks MATCH ? AND chat_id = ?"
                " ORDER BY rank LIMIT ?",
                (safe_q, str(chat_id), top_k),
            ).fetchall()
            return [{"doc_id": r[0], "chunk_text": r[1], "score": r[2]}
                    for r in rows]
        except Exception as exc:
            log.warning("[Store] FTS5 search error: %s", exc)
            return []

    def delete_text_chunks(self, doc_id: str) -> None:
        """Remove all FTS5 text chunks for a document."""
        db = self._db()
        db.execute("DELETE FROM doc_chunks WHERE doc_id = ?", (str(doc_id),))
        db.commit()

    def log_rag_activity(self, chat_id: int, query: str, n_chunks: int, chars: int,
                         latency_ms: int = 0, query_type: str = "contextual") -> None:
        """Insert one RAG retrieval record into rag_log."""
        db = self._db()
        db.execute(
            "INSERT INTO rag_log(chat_id, query, query_type, n_chunks, chars_injected, latency_ms)"
            " VALUES (?,?,?,?,?,?)",
            (chat_id, query, query_type, n_chunks, chars, latency_ms),
        )
        db.commit()

    def list_rag_log(self, limit: int = 20) -> list[dict]:
        """Return up to *limit* most recent RAG log rows, newest first."""
        rows = self._db().execute(
            "SELECT id, chat_id, query, query_type, n_chunks, chars_injected,"
            " latency_ms, created_at "
            "FROM rag_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def rag_stats(self) -> dict:
        """Return aggregate RAG stats for the admin monitoring page."""
        db = self._db()
        row = db.execute(
            "SELECT COUNT(*) as total, AVG(latency_ms) as avg_latency_ms,"
            " AVG(n_chunks) as avg_chunks, SUM(n_chunks) as total_chunks,"
            " SUM(chars_injected) as total_chars"
            " FROM rag_log"
        ).fetchone()
        top = db.execute(
            "SELECT query, COUNT(*) as cnt FROM rag_log"
            " GROUP BY query ORDER BY cnt DESC LIMIT 5"
        ).fetchall()
        types = db.execute(
            "SELECT query_type, COUNT(*) as cnt FROM rag_log GROUP BY query_type"
        ).fetchall()
        return {
            "total": row["total"] or 0,
            "avg_latency_ms": round(row["avg_latency_ms"] or 0, 1),
            "avg_chunks": round(row["avg_chunks"] or 0, 1),
            "total_chunks": row["total_chunks"] or 0,
            "total_chars": row["total_chars"] or 0,
            "top_queries": [dict(r) for r in top],
            "query_types": {r["query_type"]: r["cnt"] for r in types},
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        conn = getattr(_db_local, "conn", None)
        if conn:
            conn.close()
            _db_local.conn = None  # type: ignore[attr-defined]
