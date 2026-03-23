"""
store_base.py — DataStore Protocol + exceptions.

All storage adapters (SQLiteStore, PostgresStore) implement this interface.
Feature modules call only this interface — never raw SQL.

Dependency chain: (no other bot_* imports — this is the base)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class StoreCapabilityError(NotImplementedError):
    """Raised when the active store backend does not support a requested feature.

    Example: calling upsert_embedding() when sqlite-vec is not installed.
    """


@runtime_checkable
class DataStore(Protocol):
    """Abstract storage adapter.

    Concrete implementations: SQLiteStore (src/core/store_sqlite.py),
    PostgresStore (src/core/store_postgres.py — OpenClaw only).

    All methods are synchronous.  Thread safety is the responsibility
    of each adapter implementation.
    """

    # ── User management ───────────────────────────────────────────────────────

    def upsert_user(self, chat_id: int, **fields) -> None:
        """Create or update a user record.

        Accepted fields: username, name, role, language, audio_on, approved_at.
        Unknown fields are silently ignored.
        """
        ...

    def get_user(self, chat_id: int) -> dict | None:
        """Return user record as dict, or None if not found."""
        ...

    def list_users(self, role: str | None = None) -> list[dict]:
        """Return all users, optionally filtered by role (pending/approved/blocked/admin)."""
        ...

    def set_user_role(self, chat_id: int, role: str) -> None:
        """Update user role (pending | approved | blocked | admin | guest)."""
        ...

    # ── Notes ─────────────────────────────────────────────────────────────────

    def save_note(self, chat_id: int, slug: str, title: str,
                  content: str) -> None:
        """Create or replace a note. Updates both DB index and .md file."""
        ...

    def load_note(self, chat_id: int, slug: str) -> dict | None:
        """Return note dict {slug, title, content, updated_at} or None."""
        ...

    def list_notes(self, chat_id: int) -> list[dict]:
        """Return [{slug, title, updated_at}] sorted newest-first."""
        ...

    def delete_note(self, chat_id: int, slug: str) -> bool:
        """Delete note from DB index and .md file. Returns True if found."""
        ...

    # ── Calendar ──────────────────────────────────────────────────────────────

    def save_event(self, chat_id: int, event: dict) -> None:
        """Insert or replace a calendar event dict.

        Required event keys: id, title, dt_iso.
        Optional: remind_before_min (default 15), reminded (default False).
        """
        ...

    def load_events(self, chat_id: int,
                    from_dt: str | None = None,
                    to_dt: str | None = None) -> list[dict]:
        """Return events for user, optionally filtered by ISO-8601 date range."""
        ...

    def delete_event(self, chat_id: int, ev_id: str) -> bool:
        """Delete event by id. Returns True if found and deleted."""
        ...

    # ── Conversation history ───────────────────────────────────────────────────

    def append_history(self, chat_id: int, role: str, content: str) -> None:
        """Append a message to conversation history (role: user | assistant)."""
        ...

    def get_history(self, chat_id: int, last_n: int = 15) -> list[dict]:
        """Return last_n messages [{role, content, created_at}] oldest-first."""
        ...

    def clear_history(self, chat_id: int) -> None:
        """Delete all conversation history for user."""
        ...

    # ── Voice opts ────────────────────────────────────────────────────────────

    def get_voice_opts(self, chat_id: int | None = None) -> dict:
        """Return voice opt flags.

        chat_id=None → global flags (voice_opts.json equivalent).
        chat_id=<id> → per-user flags.
        Returns {key: bool}.
        """
        ...

    def set_voice_opt(self, key: str, value: bool,
                      chat_id: int | None = None) -> None:
        """Set a single voice opt flag (global or per-user)."""
        ...

    # ── Mail credentials ──────────────────────────────────────────────────────

    def get_mail_creds(self, chat_id: int) -> dict | None:
        """Return decrypted mail credentials dict, or None if not configured."""
        ...

    def save_mail_creds(self, chat_id: int, creds: dict) -> None:
        """Save mail credentials (password encrypted at rest if STORE_CRED_KEY set).

        Expected creds keys: provider, email, imap_host, imap_port, password,
        target_email (optional).
        """
        ...

    # ── Contacts ──────────────────────────────────────────────────────────────

    def save_contact(self, chat_id: int, contact: dict) -> str:
        """Create or update contact. Returns contact id."""
        ...

    def get_contact(self, contact_id: str) -> dict | None:
        """Return contact dict or None."""
        ...

    def list_contacts(self, chat_id: int) -> list[dict]:
        """Return all contacts for user sorted by name."""
        ...

    def delete_contact(self, contact_id: str) -> bool:
        """Delete contact. Returns True if found."""
        ...

    def search_contacts(self, chat_id: int, query: str) -> list[dict]:
        """Full-text search across name, phone, email, notes fields."""
        ...

    # ── Documents / knowledge base ────────────────────────────────────────────

    def save_document_meta(self, doc_id: str, chat_id: int,
                           title: str, file_path: str,
                           doc_type: str,
                           metadata: dict | None = None) -> None:
        """Store document metadata (file content lives on disk)."""
        ...

    def list_documents(self, chat_id: int) -> list[dict]:
        """Return [{doc_id, title, file_path, doc_type, metadata, created_at}] newest-first."""
        ...

    def delete_document(self, doc_id: str) -> None:
        """Remove document metadata record (does NOT delete the file on disk)."""
        ...

    # ── Vector / RAG ──────────────────────────────────────────────────────────

    def has_vector_search(self) -> bool:
        """Return True if vector similarity search is supported by this adapter."""
        ...

    def upsert_embedding(self, doc_id: str, chunk_idx: int, chat_id: int,
                         chunk_text: str, embedding: list[float],
                         metadata: dict | None = None) -> None:
        """Store a text-chunk embedding.

        Raises StoreCapabilityError if has_vector_search() is False.
        """
        ...

    def search_similar(self, embedding: list[float], chat_id: int,
                       top_k: int = 5) -> list[dict]:
        """KNN search within user's embeddings.

        Returns [{doc_id, chunk_text, distance}] sorted by distance ascending.
        Raises StoreCapabilityError if has_vector_search() is False.
        """
        ...

    def delete_embeddings(self, doc_id: str) -> None:
        """Remove all embedding chunks for a document. Silent if not found."""
        ...

    # ── FTS5 text search (always available) ──────────────────────────────────

    def has_document_search(self) -> bool:
        """Return True if document text search is supported.

        Always True for SQLite (FTS5 built-in); may return False on adapters
        that do not implement FTS5 or an equivalent.
        """
        ...

    def upsert_chunk_text(self, doc_id: str, chunk_idx: int, chat_id: int,
                          chunk_text: str) -> None:
        """Store a text chunk in the FTS5 index (no vector required)."""
        ...

    def search_fts(self, query: str, chat_id: int,
                   top_k: int = 5) -> list[dict]:
        """BM25 full-text search in user's document chunks.

        Returns [{doc_id, chunk_text, score}] sorted by relevance descending.
        Returns [] if no results or FTS not supported.
        """
        ...

    def delete_text_chunks(self, doc_id: str) -> None:
        """Remove all FTS5 text chunks for a document. Silent if not found."""
        ...

    def log_rag_activity(self, chat_id: int, query: str, n_chunks: int, chars: int) -> None:
        """Record a RAG retrieval event for auditing / admin log viewer."""
        ...

    def list_rag_log(self, limit: int = 20) -> list[dict]:
        """Return the most recent RAG log entries, newest first.
        Each entry: {id, chat_id, query, n_chunks, chars_injected, created_at}.
        """
        ...

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Release connections / resources held by this adapter."""
        ...
