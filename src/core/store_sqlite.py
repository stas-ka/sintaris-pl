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

from core.bot_config import log_datastore as log, NOTES_DIR
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

# Track vec0 rowids in a regular table so we can delete by rowid
# (sqlite-vec vec0 does NOT support DELETE WHERE on auxiliary columns)
_VEC_ROWID_MAP_SQL = """
CREATE TABLE IF NOT EXISTS vec_rowid_map (
    doc_id     TEXT    NOT NULL,
    chunk_idx  INTEGER NOT NULL,
    vec_rowid  INTEGER NOT NULL,
    PRIMARY KEY (doc_id, chunk_idx)
);
"""

# ── Valid voice-opt column names (whitelist prevents SQL injection) ───────────
_VOICE_OPT_COLUMNS: frozenset[str] = frozenset({
    "silence_strip", "low_sample_rate", "warm_piper", "parallel_tts",
    "user_audio_toggle", "tmpfs_model", "vad_prefilter", "whisper_stt",
    "piper_low_model", "persistent_piper", "voice_timing_debug", "vosk_fallback",
    "voice_male",
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
                conn.executescript(_VEC_ROWID_MAP_SQL)
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
                           metadata: dict | None = None,
                           doc_hash: str | None = None) -> None:
        db = self._db()
        db.execute(
            """INSERT INTO documents
               (doc_id, chat_id, title, file_path, doc_type, metadata, doc_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(doc_id) DO UPDATE SET
                   title      = excluded.title,
                   file_path  = excluded.file_path,
                   doc_type   = excluded.doc_type,
                   metadata   = excluded.metadata,
                   doc_hash   = excluded.doc_hash,
                   updated_at = datetime('now')""",
            (
                doc_id, chat_id, title, file_path, doc_type,
                json.dumps(metadata) if metadata else None,
                doc_hash,
            ),
        )
        db.commit()

    def list_documents(self, chat_id: int) -> list[dict]:
        rows = self._db().execute(
            "SELECT * FROM documents WHERE chat_id = ? OR is_shared = 1"
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
        # Ensure rowid map table exists (auto-migration for existing DBs)
        db.execute(_VEC_ROWID_MAP_SQL)
        # Look up old embedding rowid (may be None for first insert)
        old = db.execute(
            "SELECT vec_rowid FROM vec_rowid_map WHERE doc_id = ? AND chunk_idx = ?",
            (doc_id, chunk_idx),
        ).fetchone()
        old_rowid = old[0] if old else None
        # vec0 DELETE only works inside a committed transaction.
        # Use `with db:` which handles nested transactions correctly in Python 3.12.
        with db:
            if old_rowid is not None:
                try:
                    db.execute("DELETE FROM vec_embeddings WHERE rowid = ?", (old_rowid,))
                except Exception:
                    pass
            cur = db.execute(
                "INSERT INTO vec_embeddings "
                "(doc_id, chunk_idx, chat_id, chunk_text, embedding) "
                "VALUES (?, ?, ?, ?, ?)",
                (doc_id, chunk_idx, chat_id, chunk_text, vec_blob),
            )
            vec_rowid = cur.lastrowid
        # Update rowid_map outside the vec0 transaction (regular table)
        if vec_rowid:
            db.execute(
                "INSERT OR REPLACE INTO vec_rowid_map (doc_id, chunk_idx, vec_rowid)"
                " VALUES (?, ?, ?)",
                (doc_id, chunk_idx, vec_rowid),
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
        # sqlite-vec KNN does NOT support compound WHERE (OR/IN) — fetch broadly and filter in Python
        fetch_k = max(top_k * 6, 30)  # fetch extra to survive filtering + dedup
        shared_ids = set(self._get_shared_doc_ids())
        # Unfiltered KNN — sqlite-vec requires simple single-column WHERE for KNN
        rows = self._db().execute(
            "SELECT doc_id, chunk_idx, chat_id, chunk_text, distance"
            " FROM vec_embeddings"
            " WHERE embedding MATCH ?"
            "   AND k = ?",
            (vec_blob, fetch_k),
        ).fetchall()
        # Filter by ownership (own chat_id or shared doc) and deduplicate
        seen: set[tuple] = set()
        result = []
        for r in rows:
            row_chat_id = int(r[2] or 0)
            if row_chat_id != chat_id and r[0] not in shared_ids:
                continue
            key = (r[0], int(r[1] or 0))
            if key not in seen:
                seen.add(key)
                result.append({"doc_id": r[0], "chunk_idx": int(r[1] or 0),
                                "chunk_text": r[3], "distance": r[4]})
            if len(result) >= top_k:
                break
        return result

    def delete_embeddings(self, doc_id: str) -> None:
        if not self._has_vec:
            return
        db = self._db()
        # Ensure rowid map exists
        db.execute(_VEC_ROWID_MAP_SQL)
        # Collect rowids via rowid_map AND via aux-column scan (catches orphans not in map).
        # SELECT by aux column works on vec0; DELETE with WHERE aux does not.
        # vec0 DELETE by rowid only works inside a committed transaction — use `with db:`.
        mapped_rowids = {row[0] for row in db.execute(
            "SELECT vec_rowid FROM vec_rowid_map WHERE doc_id = ?", (doc_id,)
        ).fetchall()}
        try:
            scanned_rowids = {row[0] for row in db.execute(
                "SELECT rowid FROM vec_embeddings WHERE doc_id = ?", (doc_id,)
            ).fetchall()}
        except Exception:
            scanned_rowids = set()
        all_rowids = mapped_rowids | scanned_rowids
        if all_rowids:
            with db:
                for rid in all_rowids:
                    try:
                        db.execute("DELETE FROM vec_embeddings WHERE rowid = ?", (rid,))
                    except Exception:
                        pass
        db.execute("DELETE FROM vec_rowid_map WHERE doc_id = ?", (doc_id,))
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
        """BM25 full-text search across user's document chunks (own + shared).

        Sanitises the query to bare words (removes FTS5 special chars) so
        arbitrary user input cannot cause a parse error.
        Uses OR semantics so partial matches work — FTS5 default AND requires
        all words in one chunk which is too strict for natural language queries.
        Returns [{doc_id, chunk_idx, chunk_text, score}] ordered best-first.
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
        # Include own docs + shared docs from any user
        shared_ids = self._get_shared_doc_ids()
        try:
            if shared_ids:
                placeholders = ",".join("?" * len(shared_ids))
                rows = self._db().execute(
                    f"SELECT doc_id, chunk_idx, chunk_text, rank"
                    f" FROM doc_chunks"
                    f" WHERE doc_chunks MATCH ? AND (chat_id = ? OR doc_id IN ({placeholders}))"
                    f" ORDER BY rank LIMIT ?",
                    [safe_q, str(chat_id)] + shared_ids + [top_k],
                ).fetchall()
            else:
                rows = self._db().execute(
                    "SELECT doc_id, chunk_idx, chunk_text, rank"
                    " FROM doc_chunks"
                    " WHERE doc_chunks MATCH ? AND chat_id = ?"
                    " ORDER BY rank LIMIT ?",
                    (safe_q, str(chat_id), top_k),
                ).fetchall()
            return [{"doc_id": r[0], "chunk_idx": int(r[1] or 0),
                     "chunk_text": r[2], "score": r[3]}
                    for r in rows]
        except Exception as exc:
            log.warning("[Store] FTS5 search error: %s", exc)
            return []

    def _get_shared_doc_ids(self) -> list[str]:
        """Return list of doc_ids marked is_shared=1 (from any user)."""
        try:
            rows = self._db().execute(
                "SELECT doc_id FROM documents WHERE is_shared = 1"
            ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def delete_text_chunks(self, doc_id: str) -> None:
        """Remove all FTS5 text chunks for a document."""
        db = self._db()
        db.execute("DELETE FROM doc_chunks WHERE doc_id = ?", (str(doc_id),))
        db.commit()

    def get_chunks_without_embeddings(self, chat_id_filter: int | None = None) -> list[dict]:
        """Return doc_chunks rows that have no corresponding entry in vec_embeddings.

        Used by migrate_reembed.py to find chunks that need vector generation.
        Returns [{doc_id, chunk_idx, chat_id, chunk_text}].
        """
        if not self._has_vec:
            return []
        db = self._db()
        if chat_id_filter is not None:
            rows = db.execute(
                "SELECT dc.doc_id, dc.chunk_idx, dc.chat_id, dc.chunk_text"
                " FROM doc_chunks dc"
                " LEFT JOIN vec_embeddings ve"
                "   ON ve.doc_id = dc.doc_id AND ve.chunk_idx = dc.chunk_idx"
                " WHERE dc.chat_id = ? AND ve.doc_id IS NULL"
                " ORDER BY dc.doc_id, CAST(dc.chunk_idx AS INTEGER)",
                (str(chat_id_filter),),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT dc.doc_id, dc.chunk_idx, dc.chat_id, dc.chunk_text"
                " FROM doc_chunks dc"
                " LEFT JOIN vec_embeddings ve"
                "   ON ve.doc_id = dc.doc_id AND ve.chunk_idx = dc.chunk_idx"
                " WHERE ve.doc_id IS NULL"
                " ORDER BY dc.doc_id, CAST(dc.chunk_idx AS INTEGER)",
            ).fetchall()
        return [{"doc_id": r[0], "chunk_idx": int(r[1] or 0),
                 "chat_id": int(r[2] or 0), "chunk_text": r[3]}
                for r in rows]

    def log_rag_activity(self, chat_id: int, query: str, n_chunks: int, chars: int,
                         latency_ms: int = 0, query_type: str = "contextual",
                         n_fts5: int = 0, n_vector: int = 0, n_mcp: int = 0) -> None:
        """Insert one RAG retrieval record into rag_log.

        n_fts5/n_vector/n_mcp track the component chunk counts for strategy analysis.
        Columns are added automatically on first use if the DB is older.
        """
        db = self._db()
        # Ensure extended tracing columns exist (idempotent migration)
        existing = {r[1] for r in db.execute("PRAGMA table_info(rag_log)").fetchall()}
        for col in ("n_fts5", "n_vector", "n_mcp"):
            if col not in existing:
                db.execute(f"ALTER TABLE rag_log ADD COLUMN {col} INTEGER DEFAULT 0")
        db.execute(
            "INSERT INTO rag_log(chat_id, query, query_type, n_chunks, chars_injected,"
            " latency_ms, n_fts5, n_vector, n_mcp)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (chat_id, query, query_type, n_chunks, chars, latency_ms,
             n_fts5, n_vector, n_mcp),
        )
        db.commit()

    def list_rag_log(self, limit: int = 20) -> list[dict]:
        """Return up to *limit* most recent RAG log rows, newest first."""
        rows = self._db().execute(
            "SELECT id, chat_id, query, query_type, n_chunks, chars_injected,"
            " latency_ms, COALESCE(n_fts5,0) as n_fts5,"
            " COALESCE(n_vector,0) as n_vector, COALESCE(n_mcp,0) as n_mcp,"
            " created_at "
            "FROM rag_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def append_history_tracked(self, chat_id: int, role: str, content: str,
                                call_id: str | None = None) -> int:
        db = self._db()
        cur = db.execute(
            "INSERT INTO chat_history (chat_id, role, content, call_id) VALUES (?,?,?,?)",
            (chat_id, role, content, call_id),
        )
        db.commit()
        return cur.lastrowid or 0

    def log_llm_call(
        self, call_id: str, chat_id: int, provider: str,
        history_ids: list, prompt_chars: int, response_ok: bool,
        *, model: str = "", temperature: float = 0.0,
        system_chars: int = 0, history_chars: int = 0,
        rag_chunks_count: int = 0, rag_context_chars: int = 0,
        response_preview: str = "", context_snapshot: str = "",
    ) -> None:
        import json as _json
        db = self._db()
        db.execute(
            "INSERT OR IGNORE INTO llm_calls "
            "(call_id, chat_id, provider, history_count, history_ids, prompt_chars, response_ok,"
            " model, temperature, system_chars, history_chars,"
            " rag_chunks_count, rag_context_chars, response_preview, context_snapshot) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                call_id, chat_id, provider, len(history_ids),
                _json.dumps(history_ids), prompt_chars, 1 if response_ok else 0,
                model, temperature, system_chars, history_chars,
                rag_chunks_count, rag_context_chars,
                response_preview[:300] if response_preview else "",
                context_snapshot,
            ),
        )
        db.commit()

    def get_llm_trace(self, chat_id: int, limit: int = 10) -> list[dict]:
        rows = self._db().execute(
            "SELECT call_id, provider, model, temperature, history_count, history_chars,"
            " system_chars, rag_chunks_count, rag_context_chars,"
            " response_preview, context_snapshot, response_ok, created_at "
            "FROM llm_calls WHERE chat_id=? ORDER BY created_at DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def set_tts_pending(self, chat_id: int, msg_id: int) -> None:
        db = self._db()
        db.execute(
            "INSERT INTO tts_pending (chat_id, msg_id) VALUES (?, ?)"
            " ON CONFLICT (chat_id) DO UPDATE SET msg_id = excluded.msg_id",
            (chat_id, msg_id),
        )
        db.commit()

    def get_tts_pending(self, chat_id: int) -> int | None:
        row = self._db().execute(
            "SELECT msg_id FROM tts_pending WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return row[0] if row else None

    def clear_tts_pending(self, chat_id: int) -> None:
        db = self._db()
        db.execute("DELETE FROM tts_pending WHERE chat_id = ?", (chat_id,))
        db.commit()

    def save_summary(self, chat_id: int, summary: str,
                     tier: str = "mid", msg_count: int = 0) -> None:
        db = self._db()
        db.execute(
            "INSERT INTO conversation_summaries (chat_id, summary, tier, msg_count)"
            " VALUES (?, ?, ?, ?)",
            (chat_id, summary, tier, msg_count),
        )
        db.commit()

    def count_summaries(self, chat_id: int, tier: str = "mid") -> int:
        row = self._db().execute(
            "SELECT COUNT(*) FROM conversation_summaries WHERE chat_id=? AND tier=?",
            (chat_id, tier),
        ).fetchone()
        return row[0] if row else 0

    def get_summaries_oldest(self, chat_id: int, tier: str = "mid") -> list[dict]:
        rows = self._db().execute(
            "SELECT id, summary, tier, msg_count, created_at "
            "FROM conversation_summaries WHERE chat_id=? AND tier=? "
            "ORDER BY created_at ASC",
            (chat_id, tier),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_summaries(self, chat_id: int, tier: str | None = None) -> None:
        db = self._db()
        if tier is None:
            db.execute(
                "DELETE FROM conversation_summaries WHERE chat_id = ?", (chat_id,)
            )
        else:
            db.execute(
                "DELETE FROM conversation_summaries WHERE chat_id = ? AND tier = ?",
                (chat_id, tier),
            )
        db.commit()

    def get_all_summaries(self, chat_id: int) -> list[dict]:
        rows = self._db().execute(
            "SELECT tier, summary FROM conversation_summaries "
            "WHERE chat_id = ? ORDER BY tier DESC, created_at ASC",
            (chat_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_user_pref(self, chat_id: int, key: str, default: str = "1") -> str:
        try:
            row = self._db().execute(
                "SELECT value FROM user_prefs WHERE chat_id=? AND key=?", (chat_id, key)
            ).fetchone()
            return row[0] if row else default
        except Exception:
            return default

    def set_user_pref(self, chat_id: int, key: str, value: str) -> None:
        db = self._db()
        db.execute(
            """INSERT INTO user_prefs(chat_id, key, value, updated_at)
               VALUES(?,?,?,datetime('now'))
               ON CONFLICT(chat_id,key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')""",
            (chat_id, key, value),
        )
        db.commit()

    def log_security_event(self, chat_id: int, event_type: str,
                           detail: str = "") -> None:
        try:
            db = self._db()
            db.execute(
                "INSERT INTO security_events (chat_id, event_type, detail)"
                " VALUES (?, ?, ?)",
                (chat_id, event_type, detail[:500]),
            )
            db.commit()
        except Exception:
            pass

    def list_security_events(self, limit: int = 50) -> list[dict]:
        rows = self._db().execute(
            "SELECT created_at, event_type, chat_id, detail "
            "FROM security_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_active_chat_ids(self) -> list[int]:
        rows = self._db().execute(
            "SELECT DISTINCT chat_id FROM chat_history"
        ).fetchall()
        return [r[0] for r in rows]

    # ── Web accounts ──────────────────────────────────────────────────────────

    def upsert_web_account(self, account: dict) -> None:
        db = self._db()
        db.execute(
            """INSERT INTO web_accounts
               (user_id, username, display_name, pw_hash, role, status,
                telegram_chat_id, created, is_approved)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username=excluded.username, display_name=excluded.display_name,
                 pw_hash=excluded.pw_hash, role=excluded.role,
                 status=excluded.status, telegram_chat_id=excluded.telegram_chat_id,
                 is_approved=excluded.is_approved""",
            (
                account["user_id"], account["username"].lower(),
                account.get("display_name", ""),
                account["pw_hash"], account.get("role", "user"),
                account.get("status", "active"),
                account.get("telegram_chat_id"),
                account.get("created", ""),
                1 if account.get("is_approved") else 0,
            ),
        )
        db.commit()

    def find_web_account(self, *,
                         user_id: str | None = None,
                         username: str | None = None,
                         chat_id: int | None = None) -> dict | None:
        db = self._db()
        if user_id:
            row = db.execute(
                "SELECT * FROM web_accounts WHERE user_id = ?", (user_id,)
            ).fetchone()
        elif username:
            row = db.execute(
                "SELECT * FROM web_accounts WHERE username = ?", (username.lower(),)
            ).fetchone()
        elif chat_id is not None:
            row = db.execute(
                "SELECT * FROM web_accounts WHERE telegram_chat_id = ?", (chat_id,)
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
        set_clause = ", ".join(f"{k}=?" for k in updates)
        db = self._db()
        cur = db.execute(
            f"UPDATE web_accounts SET {set_clause} WHERE user_id = ?",
            list(updates.values()) + [user_id],
        )
        db.commit()
        return cur.rowcount > 0

    def list_web_accounts(self) -> list[dict]:
        rows = self._db().execute(
            "SELECT * FROM web_accounts ORDER BY created"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Password reset tokens ─────────────────────────────────────────────────

    def save_reset_token(self, token: str, username: str, expires: str) -> None:
        db = self._db()
        db.execute(
            """INSERT INTO web_reset_tokens (token, username, expires)
               VALUES (?, ?, ?)
               ON CONFLICT(token) DO UPDATE SET
                 username=excluded.username, expires=excluded.expires, used=0""",
            (token, username.lower(), expires),
        )
        db.commit()

    def find_reset_token(self, token: str) -> dict | None:
        row = self._db().execute(
            "SELECT * FROM web_reset_tokens WHERE token = ? AND used = 0", (token,)
        ).fetchone()
        return dict(row) if row else None

    def mark_reset_token_used(self, token: str) -> None:
        db = self._db()
        db.execute("UPDATE web_reset_tokens SET used = 1 WHERE token = ?", (token,))
        db.commit()

    def delete_reset_tokens_for_user(self, username: str) -> None:
        db = self._db()
        db.execute(
            "DELETE FROM web_reset_tokens WHERE username = ?", (username.lower(),)
        )
        db.commit()

    # ── Telegram↔Web link codes ───────────────────────────────────────────────

    def save_link_code(self, code: str, chat_id: int, expires_at: str) -> None:
        db = self._db()
        db.execute(
            """INSERT INTO web_link_codes (code, chat_id, expires_at)
               VALUES (?, ?, ?)
               ON CONFLICT(code) DO UPDATE SET
                 chat_id=excluded.chat_id, expires_at=excluded.expires_at""",
            (code, chat_id, expires_at),
        )
        db.commit()

    def find_link_code(self, code: str) -> dict | None:
        row = self._db().execute(
            "SELECT code, chat_id, expires_at FROM web_link_codes WHERE code = ?",
            (code,),
        ).fetchone()
        return dict(row) if row else None

    def delete_link_code(self, code: str) -> None:
        db = self._db()
        db.execute("DELETE FROM web_link_codes WHERE code = ?", (code,))
        db.commit()

    def delete_expired_link_codes(self) -> None:
        db = self._db()
        db.execute(
            "DELETE FROM web_link_codes WHERE expires_at < datetime('now')"
        )
        db.commit()

    def rag_stats(self) -> dict:
        """Return aggregate RAG stats for the admin monitoring page."""
        db = self._db()
        row = db.execute(
            "SELECT COUNT(*) as total, AVG(latency_ms) as avg_latency_ms,"
            " AVG(n_chunks) as avg_chunks, SUM(n_chunks) as total_chunks,"
            " SUM(chars_injected) as total_chars,"
            " SUM(COALESCE(n_fts5,0)) as total_fts5,"
            " SUM(COALESCE(n_vector,0)) as total_vector,"
            " SUM(COALESCE(n_mcp,0)) as total_mcp"
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
            "total_fts5": row["total_fts5"] or 0,
            "total_vector": row["total_vector"] or 0,
            "total_mcp": row["total_mcp"] or 0,
            "top_queries": [dict(r) for r in top],
            "query_types": {r["query_type"]: r["cnt"] for r in types},
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        conn = getattr(_db_local, "conn", None)
        if conn:
            conn.close()
            _db_local.conn = None  # type: ignore[attr-defined]
