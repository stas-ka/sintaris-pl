# Taris — Knowledge Base Architecture

**Version:** `2026.3.30+3`  
→ Architecture index: [architecture.md](../architecture.md)

## When to read this file
Modifying RAG indexing, document storage, search, knowledge injection into LLM prompts, or planning new knowledge-type features (notes as KB, calendar context, contacts lookup).

---

## Knowledge Sources — What feeds LLM context

| Source | Type | Injected into | When injected | File |
|---|---|---|---|---|
| **Uploaded documents** | RAG chunks (FTS5/vector) | `role:user` turn | Every text message (if RAG enabled + match found) | `features/bot_documents.py` |
| **Conversation summaries** | Tiered memory (mid/long) | `role:system` | Every LLM call | `core/bot_state.py` `get_memory_context()` |
| **Live chat history** | Last N turns | history messages | Every multi-turn LLM call | `core/bot_state.py` `load_conversation_history()` |
| **Notes** | User Markdown notes | ❌ Not injected automatically | ⏳ Planned: notes-as-KB toggle | `features/bot_notes.py` |
| **Calendar events** | JSON events list | ❌ Not injected automatically | ⏳ Planned: calendar context injection | `features/bot_calendar.py` |
| **Contacts** | Contact book entries | ❌ Not injected automatically | ⏳ Planned | `features/bot_contacts.py` |
| **System data** | Bot config, version, variant | `role:system` preamble | Every LLM call | `telegram/bot_access.py` `_build_system_message()` |

---

## RAG Pipeline (Documents)

```
User uploads file (Telegram or Web UI)
    │
    ▼
bot_documents.py: read file → detect mime type (PDF/txt/md/docx)
    │
    ▼
Text extraction:
  - .txt / .md  → direct read
  - .pdf        → ⏳ pdfplumber / pdfminer (OPEN)
  - .docx       → ⏳ python-docx (OPEN)
    │
    ▼
Chunking: split at RAG_CHUNK_SIZE (512 chars, configurable) with sentence boundaries
    │
    ▼
Deduplication: SHA256(content) → skip if doc_hash already in store
    │
    ▼
Indexing:
  PicoClaw:  store_sqlite.index_document(chunks)
               → INSERT INTO fts_documents (BM25 FTS5 auto-indexed)
  OpenClaw:  store_postgres.index_document(chunks)
               → INSERT INTO document_chunks + pgvector embedding
               → all-MiniLM-L6-v2 (384-dim) via sentence-transformers
    │
    ▼
Stored in: documents + document_chunks tables
```

**Search at query time:**
```
User sends text message
    │
    ▼ (if RAG_ENABLED and not flag-file ~/.taris/rag_disabled)
store.search_fts(query=text, top_k=RAG_TOP_K)
  PicoClaw:  SELECT … FROM fts_documents WHERE fts_documents MATCH ? ORDER BY bm25(...)
  OpenClaw:  hybrid: BM25 + cosine similarity (pgvector <=> operator)
    │
    ▼
Top-K chunks → prepended to user turn as "Context:\n{chunks}\n"
    │
    ▼
LLM answer grounded in document content
```

---

## Storage Schema

| Table | Backend | Key columns | Purpose |
|---|---|---|---|
| `documents` | Both | `doc_id, chat_id, filename, doc_hash, n_chunks, shared` | Document registry |
| `document_chunks` | Both | `chunk_id, doc_id, chunk_text, chunk_index` | Chunk content |
| `fts_documents` | SQLite | `doc_id, chunk_text` (FTS5 virtual) | BM25 full-text search |
| `document_embeddings` | Postgres | `chunk_id, embedding vector(384)` | pgvector cosine search |

→ Full schema: [data-layer.md](data-layer.md)

---

## Document Sharing

| Scope | Set by | Access |
|---|---|---|
| **Personal** (default) | uploader | Only the uploading `chat_id` |
| **Shared** | Admin panel → "Make shared" | All users see it in their RAG context |

Admin can list all docs, toggle shared flag, delete any doc.  
→ `features/bot_documents.py` → `_handle_admin_doc_list()`, `_handle_admin_doc_toggle_shared()`

---

## Config Constants (`bot_config.py`)

| Constant | Default | Description |
|---|---|---|
| `RAG_ENABLED` | `true` | Master on/off |
| `RAG_TOP_K` | `3` | Chunks returned per query |
| `RAG_CHUNK_SIZE` | `512` | Chars per chunk at indexing |
| `RAG_FLAG_FILE` | `~/.taris/rag_disabled` | Presence = RAG off (runtime toggle, no restart) |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | OpenClaw embedding model |

Runtime override: Admin Panel → 🔍 RAG / Knowledge Base → writes `rag_settings.json`.  
→ `core/rag_settings.py` reads `~/.taris/rag_settings.json` at each LLM call.

---

## Notes as Knowledge (Planned)

> ⏳ **OPEN:** Notes-as-KB toggle — user enables "inject my notes into context" and relevant notes are found by FTS and appended to the system message. → See [TODO.md §10](../TODO.md#10-knowledge-base--rag-)

Notes are currently stored as Markdown files at `~/.taris/notes/<chat_id>/<slug>.md` and are **not** indexed or injected automatically. The design intent is:
1. Notes indexed into `fts_documents` with `type='note'` tag at save time.
2. `search_fts(query, filter='note')` finds relevant notes.
3. Injected alongside document chunks into `role:user`.

---

## Calendar as Knowledge (Planned)

> ⏳ **OPEN:** Calendar context injection — today's events + upcoming N days appended to `role:system` so the bot can answer "what do I have today?" in free chat. → See [TODO.md §10](../TODO.md#10-knowledge-base--rag-)

Currently calendar data is only available when the user explicitly opens the calendar menu or asks via console.

---

## Planned Knowledge Base Roadmap

| Feature | Status | TODO ref |
|---|---|---|
| Document RAG (FTS5/pgvector) | ✅ Implemented (v2026.3.29) | — |
| Admin RAG settings panel | ✅ Implemented (v2026.3.30) | — |
| Document deduplication (SHA256) | ✅ Implemented (v2026.3.29) | — |
| Shared documents across users | ✅ Implemented (v2026.3.29) | — |
| Tiered conversation memory | ✅ Implemented (v2026.3.30+2) | — |
| PDF / DOCX extraction | ⏳ Planned | [TODO.md §10](../TODO.md) |
| Notes indexed as KB | ⏳ Planned | [TODO.md §10](../TODO.md) |
| Calendar context injection | ⏳ Planned | [TODO.md §10](../TODO.md) |
| Contacts lookup in conversation | ⏳ Planned | [TODO.md §4](../TODO.md) |
| Knowledge base UI (browse, edit) | ⏳ Planned | [TODO.md §10](../TODO.md) |
| Per-source RAG weight tuning | ⏳ Planned | [TODO.md §10](../TODO.md) |
