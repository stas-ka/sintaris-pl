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
                           metadata: dict | None = None,
                           doc_hash: str | None = None) -> None:
        """Store document metadata (file content lives on disk)."""
        ...

    def list_documents(self, chat_id: int) -> list[dict]:
        """Return [{doc_id, title, file_path, doc_type, metadata, created_at}] newest-first."""
        ...

    def delete_document(self, doc_id: str) -> None:
        """Remove document metadata record (does NOT delete the file on disk)."""
        ...

    def update_document_field(self, doc_id: str, **fields) -> None:
        """Update arbitrary scalar fields on a document record."""
        ...

    def get_document_by_hash(self, chat_id: int, doc_hash: str) -> dict | None:
        """Return document matching sha256 hash for given user, or None."""
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
                       top_k: int = 5, is_admin: bool = False) -> list[dict]:
        """KNN search within user's embeddings.

        Returns [{doc_id, chunk_text, distance}] sorted by distance ascending.
        Raises StoreCapabilityError if has_vector_search() is False.
        is_admin=True also includes admin-only shared docs (is_shared=2).
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
                   top_k: int = 5, is_admin: bool = False) -> list[dict]:
        """BM25 full-text search in user's document chunks.

        Returns [{doc_id, chunk_text, score}] sorted by relevance descending.
        Returns [] if no results or FTS not supported.
        is_admin=True also includes admin-only shared docs (is_shared=2).
        """
        ...

    def delete_text_chunks(self, doc_id: str) -> None:
        """Remove all FTS5 text chunks for a document. Silent if not found."""
        ...

    def get_chunks_without_embeddings(self, chat_id_filter: int | None = None) -> list[dict]:
        """Return chunks with no corresponding vector embedding.
        Returns [{doc_id, chunk_idx, chat_id, chunk_text}].
        """
        ...

    def log_rag_activity(self, chat_id: int, query: str, n_chunks: int, chars: int,
                         latency_ms: int = 0, query_type: str = "contextual",
                         n_fts5: int = 0, n_vector: int = 0, n_mcp: int = 0) -> None:
        """Record a RAG retrieval event for auditing / admin log viewer."""
        ...

    def list_rag_log(self, limit: int = 20) -> list[dict]:
        """Return the most recent RAG log entries, newest first.
        Each entry: {id, chat_id, query, n_chunks, chars_injected, created_at}.
        """
        ...

    # ── Operational tables (Layer 2 migration) ────────────────────────────────

    def append_history_tracked(self, chat_id: int, role: str, content: str,
                                call_id: str | None = None) -> int:
        """Insert a history row with call_id tracking. Returns the row id."""
        ...

    def log_llm_call(
        self, call_id: str, chat_id: int, provider: str,
        history_ids: list, prompt_chars: int, response_ok: bool,
        *, model: str = "", temperature: float = 0.0,
        system_chars: int = 0, history_chars: int = 0,
        rag_chunks_count: int = 0, rag_context_chars: int = 0,
        response_preview: str = "", context_snapshot: str = "",
    ) -> None:
        """Log an LLM call with full trace metadata."""
        ...

    def get_llm_trace(self, chat_id: int, limit: int = 10) -> list[dict]:
        """Return the N most recent LLM calls for a user."""
        ...

    def set_tts_pending(self, chat_id: int, msg_id: int) -> None:
        """Record a pending TTS message (orphan cleanup tracking)."""
        ...

    def get_tts_pending(self, chat_id: int) -> int | None:
        """Return pending TTS msg_id for user, or None."""
        ...

    def clear_tts_pending(self, chat_id: int) -> None:
        """Remove TTS pending record for user."""
        ...

    def save_summary(self, chat_id: int, summary: str,
                     tier: str = "mid", msg_count: int = 0) -> None:
        """Store a conversation summary for a user."""
        ...

    def count_summaries(self, chat_id: int, tier: str = "mid") -> int:
        """Return count of summaries for user at given tier."""
        ...

    def get_summaries_oldest(self, chat_id: int, tier: str = "mid") -> list[dict]:
        """Return all summaries for user at tier, oldest first."""
        ...

    def delete_summaries(self, chat_id: int, tier: str | None = None) -> None:
        """Delete summaries for user. tier=None deletes all tiers."""
        ...

    def get_all_summaries(self, chat_id: int) -> list[dict]:
        """Return all summaries for user sorted by tier DESC, created_at ASC."""
        ...

    def get_user_pref(self, chat_id: int, key: str, default: str = "1") -> str:
        """Get a per-user preference value."""
        ...

    def set_user_pref(self, chat_id: int, key: str, value: str) -> None:
        """Set a per-user preference value."""
        ...

    def log_security_event(self, chat_id: int, event_type: str,
                           detail: str = "") -> None:
        """Record a security event."""
        ...

    def list_security_events(self, limit: int = 50) -> list[dict]:
        """Return recent security events, newest first."""
        ...

    def list_active_chat_ids(self) -> list[int]:
        """Return all distinct chat_ids that have conversation history."""
        ...

    # ── Web accounts (replaces accounts.json) ────────────────────────────────

    def upsert_web_account(self, account: dict) -> None:
        """Insert or replace a web account record (for migration + create)."""
        ...

    def find_web_account(self, *,
                         user_id: str | None = None,
                         username: str | None = None,
                         chat_id: int | None = None) -> dict | None:
        """Look up a web account by user_id, username, or telegram_chat_id."""
        ...

    def update_web_account(self, user_id: str, **fields) -> bool:
        """Update fields on a web account. Returns True if found."""
        ...

    def list_web_accounts(self) -> list[dict]:
        """Return all web accounts."""
        ...

    # ── Password reset tokens (replaces reset_tokens.json) ───────────────────

    def save_reset_token(self, token: str, username: str, expires: str) -> None:
        """Store a new reset token (expires is ISO-8601 string)."""
        ...

    def find_reset_token(self, token: str) -> dict | None:
        """Return reset token record if found and not used."""
        ...

    def mark_reset_token_used(self, token: str) -> None:
        """Mark a reset token as used."""
        ...

    def delete_reset_tokens_for_user(self, username: str) -> None:
        """Remove all existing reset tokens for a username."""
        ...

    # ── Telegram↔Web link codes (replaces web_link_codes.json) ───────────────

    def save_link_code(self, code: str, chat_id: int, expires_at: str) -> None:
        """Store a web link code (expires_at is ISO-8601 string)."""
        ...

    def find_link_code(self, code: str) -> dict | None:
        """Return link code record {code, chat_id, expires_at} or None."""
        ...

    def delete_link_code(self, code: str) -> None:
        """Remove a link code."""
        ...

    def delete_link_codes_by_user(self, chat_id: int) -> None:
        """Remove all active link codes for a given chat_id (used before issuing a new one)."""
        ...

    def delete_expired_link_codes(self) -> None:
        """Remove all expired link codes (cleanup)."""
        ...

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Release connections / resources held by this adapter."""
        ...
