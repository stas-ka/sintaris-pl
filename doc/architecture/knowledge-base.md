# Taris — Knowledge Base Architecture

**Version:** `2026.4.75`  
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
  - .pdf        → PyMuPDF (fitz) first → image placeholders → pdfminer fallback
  - .docx       → python-docx
    │
    ▼
Chunking: split at RAG_CHUNK_SIZE (512 chars, configurable) with sentence boundaries
             Quality filter: fragments shorter than _MIN_CHUNK_CHARS (20) are skipped;
             n_skipped, n_embedded, quality_pct stored in document metadata (v2026.4.1)
    │
    ▼
Deduplication: SHA256(content) → skip if doc_hash already in store
               (user prompted: Replace / Keep Both)
    │
    ▼
Indexing:
  FTS5_ONLY:  store_sqlite.index_document(chunks)
               → INSERT INTO fts_documents (BM25 FTS5 auto-indexed)
  OpenClaw:  store_postgres.index_document(chunks)
               → INSERT INTO document_chunks + pgvector embedding
               → all-MiniLM-L6-v2 (384-dim) via fastembed (EmbeddingService)
    │
    ▼
Stored in: documents + document_chunks tables
```

**Search at query time:**
```
User sends text message
    │
    ▼ (if RAG_ENABLED and not flag-file ~/.taris/rag_disabled)
bot_rag.classify_query(text, has_documents) → "simple" | "factual" | "contextual"
  "simple"     → skip RAG entirely (greeting, very short, yes/no)
  "factual"    → use RAG (factual keyword detected + user has docs)
  "contextual" → RAG optional (no docs / no factual marker)
    │
    ▼ (if not "simple")
bot_rag.retrieve_context(chat_id, query, top_k, max_chars)
  hardware tier: detect_rag_capability() → FTS5_ONLY | HYBRID | FULL
  FTS5_ONLY:  store.search_fts() → BM25 results
  HYBRID/FULL: FTS5 + store.search_similar() → reciprocal_rank_fusion(k=60)
    │
    ▼ (if MCP_REMOTE_URL set — Phase D)
bot_mcp_client.query_remote(query, chat_id, top_k) → remote chunks
  circuit breaker: 3 failures → 5 min cooldown → half-open probe
  merged via reciprocal_rank_fusion() alongside local results
  strategy string extended to "fts5+mcp" or "hybrid+mcp"
    │
    ▼
Top-K chunks → prepended as "[KNOWLEDGE FROM USER DOCUMENTS]\n{chunks}\n[END KNOWLEDGE]"
    │
    ▼
LLM answer grounded in document content
Logged to rag_log with latency_ms + query_type
```

---

## Storage Schema

| Table | Backend | Key columns | Purpose |
|---|---|---|---|
| `documents` | Both | `doc_id, chat_id, title, file_path, doc_type, doc_hash, is_shared, metadata` | Document registry |
| `doc_chunks` | SQLite | `doc_id, chunk_idx, chat_id, chunk_text` (FTS5 virtual) | BM25 full-text search |
| `vec_embeddings` | SQLite (sqlite-vec) | `doc_id, chunk_idx, chat_id, chunk_text, embedding FLOAT[384]` | Cosine vector search (vec0 virtual table) |
| `vec_rowid_map` | SQLite | `doc_id, chunk_idx → vec_rowid` | Rowid tracker for vec0 DELETE workaround |
| `document_embeddings` | Postgres | `chunk_id, embedding vector(384)` | pgvector cosine search |

→ Full schema: [data-layer.md](data-layer.md)

---

## vec0 DELETE Workaround (v2026.4.2)

`sqlite-vec` `vec0` virtual tables do **not** support `DELETE WHERE` on auxiliary columns (e.g. `WHERE doc_id = ?`). Only rowid-based deletion works.

| Component | File | Mechanism |
|---|---|---|
| `vec_rowid_map` table | `store_sqlite.py` `_VEC_ROWID_MAP_SQL` | Regular SQLite table tracking `(doc_id, chunk_idx) → vec_rowid` |
| `upsert_embedding()` | `store_sqlite.py` | Looks up old rowid → DELETE by rowid → INSERT → store new rowid |
| `delete_embeddings(doc_id)` | `store_sqlite.py` | Fetches all rowids for doc_id from map → DELETE by rowid each |
| `search_similar()` | `store_sqlite.py` | Fetches 3× top_k, deduplicates (doc_id, chunk_idx) in Python |

> **Never** call `DELETE FROM vec_embeddings WHERE doc_id = ?` directly — it silently does nothing.

---

## System Knowledge Base Docs (v2026.4.2)

Shared system documents are loaded at bot startup via a background thread.

| Tag | Title | Source file | Audience |
|---|---|---|---|
| `taris_user_guide` | 📖 Taris — User Guide | `doc/howto_bot.md` | All users |
| `taris_admin_guide` | 🔧 Taris — Admin & Technical Guide | `README.md` + `doc/architecture/overview.md` | Admins |

- `SYSTEM_CHAT_ID = 0`, `is_shared = 1` → visible in all users' RAG context
- Stable `doc_id` via `uuid.uuid5(NAMESPACE_DNS, f"taris.system.{tag}")` — idempotent
- Hash-based skip: if `doc_hash` matches `documents.doc_hash`, reload is skipped
- Source files deployed to `~/.taris/` on each target (README.md, doc/howto_bot.md, doc/architecture/overview.md)
- Loader: `setup/load_system_docs.py` · Auto-loader thread: `telegram_menu_bot.py` `_ensure_system_docs()`
- Force refresh: `python3 setup/load_system_docs.py --force`

---

## Re-Embedding Migration

`setup/migrate_reembed.py` — run once after any deployment to embed chunks without vectors.

```bash
# All users
python3 setup/migrate_reembed.py

# Single user
python3 setup/migrate_reembed.py --chat-id 994963580

# Dry run (count only)
python3 setup/migrate_reembed.py --dry-run
```

Uses `store.get_chunks_without_embeddings()` (works for SQLiteStore; PostgresStore requires Postgres schema).

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
| `RAG_TOP_K` | `3` | Chunks returned per query (overridable per-user via `user_prefs`) |
| `RAG_CHUNK_SIZE` | `512` | Chars per chunk at indexing |
| `_MIN_CHUNK_CHARS` | `20` | Minimum chars for a chunk to be indexed (`features/bot_documents.py`) |
| `RAG_FLAG_FILE` | `~/.taris/rag_disabled` | Presence = RAG off (runtime toggle, no restart) |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | OpenClaw embedding model (via `fastembed`) |
| `MCP_SERVER_ENABLED` | `true` | Enable `/mcp/search` REST endpoint |
| `MCP_REMOTE_URL` | `""` | External MCP RAG server URL; empty = Phase D client disabled |
| `MCP_TIMEOUT` | `15` | HTTP timeout (s) for remote MCP calls |
| `MCP_REMOTE_TOP_K` | `3` | Chunks to request from remote MCP server |

Runtime override: Admin Panel → 🔍 RAG / Knowledge Base → writes `rag_settings.json`.  
Per-user override: Profile → ⚙️ RAG Settings → stored in `user_prefs` table (`rag_top_k`, `rag_chunk_size`).  
→ `core/rag_settings.py` reads `~/.taris/rag_settings.json` at each LLM call.

---

## RAG Intelligence Layer (`core/bot_rag.py`)

New module added in v2026.3.32 — adaptive routing + fusion. MCP integration in v2026.4.1.

| Function | Returns | Description |
|---|---|---|
| `classify_query(text, has_documents)` | `"simple"` \| `"factual"` \| `"contextual"` | Heuristic routing — no LLM call |
| `detect_rag_capability()` | `RAGCapability` enum | RAM + vector-store detection (cached) |
| `reciprocal_rank_fusion(fts5, vector, k=60)` | merged list | Interleaves + deduplicates by `id`; adds `rrf_score` |
| `retrieve_context(chat_id, query, top_k, max_chars)` | `(chunks, assembled, strategy, trace)` | Unified entry — auto-selects FTS5/hybrid by tier; merges MCP remote chunks if enabled; returns trace dict `{n_fts5, n_vector, n_mcp, latency_ms, cap}` |

Hardware tier → strategy mapping:

| `RAGCapability` | Condition | Strategy |
|---|---|---|
| `FTS5_ONLY` | RAM < 4 GB or no vector search | BM25 search only |
| `HYBRID` | 4–8 GB RAM + vectors available | BM25 + cosine + RRF |
| `FULL` | ≥ 8 GB RAM + vectors | BM25 + cosine + RRF + reranking |

When `MCP_REMOTE_URL` is set and circuit breaker is closed, strategy string is extended with `+mcp` (e.g. `"hybrid+mcp"`).

---

## MCP Client (`core/bot_mcp_client.py`) *(v2026.4.75)*

Phase D — Remote RAG integration. Queries an external MCP-compatible RAG server and merges results into the local RRF pipeline. Also handles direct PostgreSQL access for the Remote KB feature.

| Function | Returns | Description |
|---|---|---|
| `query_remote(query, chat_id, top_k)` | `list[dict]` | pgvector cosine search via `_kb_search_direct()`. Chunk dicts: `{text, score, section, chunk_id}` |
| `call_tool(tool, args)` | `dict` | Dispatches `kb_list_documents`, `kb_delete_document` to direct PG implementations |
| `ingest_file(chat_id, filename, file_bytes, mime_type)` | `dict` | Extracts text → POST to N8N KB ingest webhook → calls `_fix_doc_meta()` to restore Unicode title + preview |
| `_fix_doc_meta(doc_id, title, preview)` | — | UPDATE `kb_documents` after N8N ingest: restores original Unicode filename, stores text preview in `structure` JSONB |
| `_extract_to_text(filename, file_bytes, mime_type)` | `(text, mime)` | Extracts plain text from RTF (striprtf), PDF (pdfminer.six), DOCX (python-docx), or plain text |
| `_kb_search_direct(query, chat_id, top_k)` | `list[dict]` | pgvector cosine search: `EmbeddingService.embed(query)` → `<=>` operator → returns top-K chunks |
| `_kb_list_documents_direct(chat_id)` | `dict` | SELECT from `kb_documents` + `kb_chunks`; includes `structure->>'preview'` |
| `_kb_delete_document_direct(doc_id, chat_id)` | `dict` | DELETE from `kb_documents` + `kb_chunks` for given `doc_id` |
| `circuit_status()` | `dict` | Returns CB state: `{state, failures, last_failure, reset_at}` |
| `_cb_is_open()` | `bool` | True = circuit open (failing fast); False = allow requests |
| `_cb_record_failure()` | — | Increments failure counter; opens CB after `_CB_THRESHOLD=3` |
| `_cb_record_success()` | — | Resets failure counter; closes CB |

**Embedding**: `_kb_search_direct()` uses `EmbeddingService.embed(query: str)` (single string → `list[float]`) from `core/bot_embeddings.py`. fastembed model `sentence-transformers/all-MiniLM-L6-v2` (384-dim). **Do NOT use Ollama for embeddings** — Ollama is not available in VPS Docker.  
**Important**: `EmbeddingService.embed()` takes a **single string**, not a list. Use `embed_batch()` for batch processing.  
Circuit breaker: 3 consecutive failures → open for `_CB_RESET_SEC=300 s` → half-open probe → close on success.  
Auth: `TARIS_API_TOKEN` sent as `Bearer` token in `Authorization` header.  
Transport: stdlib `urllib.request` (no SDK dependency).

---

## Remote KB Agent (`features/bot_remote_kb.py`) *(v2026.4.75)*

Telegram UI for the Remote Knowledge Base — user-uploaded documents stored in PostgreSQL (`taris_kb` DB on VPS) with pgvector 384-dim embeddings. **OpenClaw/VPS only.**

| Function | Signature | Description |
|---|---|---|
| `is_configured()` | `→ bool` | Returns `True` if `REMOTE_KB_ENABLED` and `KB_PG_DSN` set |
| `is_active(chat_id)` | `→ bool` | True if user has an active upload/search session |
| `cancel(chat_id)` | `→ None` | Clears session state |
| `show_menu(chat_id, bot, _t)` | `→ None` | Sends KB menu with 4 buttons: Search / Upload / List / Clear |
| `start_search(chat_id, bot, _t)` | `→ None` | Opens search session; next text message triggers `_do_search()` |
| `start_upload(chat_id, bot, _t)` | `→ None` | Opens upload session; next document triggers `handle_document()` |
| `handle_message(chat_id, text, bot, _t)` | `→ bool` | Routes text to `_do_search()` when search session active |
| `handle_document(chat_id, doc, bot, _t)` | `→ bool` | Downloads Telegram document → calls `ingest_file()` |
| `finish_upload(chat_id, bot, _t)` | `→ None` | Called on `remote_kb_upload_done` callback; shows KB menu |
| `list_docs(chat_id, bot, _t)` | `→ None` | Lists all user docs with title, chunks, tokens, date, preview |
| `clear_memory(chat_id, bot, _t)` | `→ None` | Deletes all user docs via `call_tool('kb_delete_document')` |
| `_do_search(chat_id, query, bot, _t)` | `→ None` | Retrieves top-5 chunks → builds RAG context → calls `ask_llm_with_history()` → sends LLM answer + sources footer |

**`_do_search()` RAG flow** (v2026.4.75):
1. `mcp.query_remote(query, chat_id, top_k=5)` → list of chunk dicts
2. Build `context` string: `[i] section\ntext` for each chunk
3. System prompt: answer from context only, language auto-detected via `_lang(chat_id)`
4. `ask_llm_with_history(messages, timeout=90, use_case="chat")` → answer string
5. Append `_Sources: section1, section2_` footer (i18n key: `remote_kb_sources`)
6. `bot.send_message(chat_id, answer)`

**Remote KB PostgreSQL schema** (`taris_kb` database):

| Table | Key columns | Purpose |
|---|---|---|
| `kb_documents` | `doc_id uuid, owner_chat_id bigint, title text, mime text, sha256 text, source text, structure jsonb, created_at` | Document registry |
| `kb_chunks` | `chunk_id bigint, doc_id uuid, chunk_idx, section, text, tokens, embedding vector(384), fts tsvector, metadata jsonb` | Chunk storage with pgvector + FTS |

`structure` JSONB stores: `{preview: "first 300 chars of text"}` — written by `_fix_doc_meta()` after N8N ingest.

---

## RAG Monitoring (`admin_rag_stats`)

Admin Panel → RAG → 📊 RAG Stats shows:
- Total retrievals, average latency (ms), average chunks/query
- Top-5 most queried texts
- Query type breakdown (simple / factual / contextual)

Source: `store_sqlite.rag_stats()` · `telegram/bot_admin._handle_admin_rag_stats()`  
Data: `rag_log` table — columns: `query_type`, `latency_ms`, `n_chunks`, `chars_injected`

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
| Document deduplication (SHA256) | ✅ Implemented (v2026.3.31) | — |
| Shared documents across users | ✅ Implemented (v2026.3.29) | — |
| Tiered conversation memory | ✅ Implemented (v2026.3.30+2) | — |
| PDF extraction (PyMuPDF + pdfminer) | ✅ Implemented (v2026.3.32) | — |
| DOCX extraction (python-docx) | ✅ Implemented (v2026.3.30+2) | — |
| classify_query + RRF fusion | ✅ Implemented (v2026.3.32) | — |
| RAG monitoring dashboard | ✅ Implemented (v2026.3.32) | — |
| Per-user RAG settings | ✅ Implemented (v2026.3.32) | — |
| Chunk quality filter + embed stats in metadata | ✅ Implemented (v2026.4.1) | — |
| MCP server `/mcp/search` + remote MCP client | ✅ Implemented (v2026.4.1) | — |
| **Critical bug fixes** (upsert_embedding args, RRF chunk_idx, vec0 DELETE via rowid map) | ✅ Fixed (v2026.4.2) | — |
| **Shared docs in FTS + vector search** (`is_shared=1` honoured in all search paths) | ✅ Implemented (v2026.4.2, SQLite) · Fixed PostgreSQL (v2026.4.9) | — |
| **RAG tracing** (`retrieve_context` 4-tuple with `trace` dict; n_fts5/n_vector/n_mcp in rag_log) | ✅ Implemented (v2026.4.2) | — |
| **System KB docs** (README + howto + overview as shared docs; auto-loaded at startup) | ✅ Implemented (v2026.4.2) | — |
| **Re-embedding migration** (`setup/migrate_reembed.py` — store API, `--dry-run`, `--chat-id`) | ✅ Implemented (v2026.4.2) | — |
| **PostgreSQL `get_chunks_without_embeddings`** (was querying non-existent `doc_chunks`; now uses `vec_embeddings WHERE embedding IS NULL`) | ✅ Fixed (v2026.4.9) | — |
| Notes indexed as KB | ⏳ Planned | [TODO.md §10](../TODO.md) |
| Calendar context injection | ⏳ Planned | [TODO.md §10](../TODO.md) |
| Contacts lookup in conversation | ⏳ Planned | [TODO.md §4](../TODO.md) |
| Knowledge base UI (browse, edit) | ⏳ Planned | [TODO.md §10](../TODO.md) |
| sqlite-vec HNSW for PicoClaw | ⏳ Planned | [TODO.md §25.6](../TODO.md) |
| Admin Panel UI for MCP endpoint URL config | ⏳ Planned | [TODO.md §4.2](../TODO.md) |
