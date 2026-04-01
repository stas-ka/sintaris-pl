# GPT.md — Taris Conversation Intelligence: RAG, Memory, Knowledge

**Status as of:** 2026-04-01  
**Branch:** `taris-openclaw`  
**Bot version:** `2026.3.49`  
**Database:** `~/.taris/taris.db` (SQLite, sqlite-vec 0.1.7 loaded)

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         LLM PROMPT ASSEMBLY                              │
│                                                                          │
│  [role:system]                                                           │
│    SECURITY_PREAMBLE (~300 chars)                                        │
│    BOT_CONFIG block (name / version / variant / LLM / STT / TTS)        │
│    MEMORY NOTE (static boilerplate)                                      │
│    LANGUAGE INSTRUCTION                                                  │
│    [Memory context from previous sessions:]     ← get_memory_context()  │
│      [LONG] compact paragraph of all mid summaries                       │
│      [MID]  2-4 sentence summaries (up to CONV_MID_MAX=5 entries)       │
│                                                                          │
│  [role:user]  × N  ── live history from chat_history DB                 │
│  [role:assistant]  × N                                                  │
│  ...                                                                     │
│                                                                          │
│  [role:user]  ← CURRENT TURN                                            │
│    [KNOWLEDGE FROM USER DOCUMENTS]  ← _docs_rag_context()  (optional)  │
│      top-K FTS5 chunks (or RRF-fused FTS5+vector when available)        │
│    [END KNOWLEDGE]                                                       │
│    [USER]{text}[/USER]              ← _wrap_user_input()                │
└──────────────────────────────────────────────────────────────────────────┘
```

### Channel comparison (current state)

| Channel | LLM call | History | Memory | RAG |
|---|---|---|---|---|
| Telegram text chat | `ask_llm_with_history` | ✅ | ✅ | ✅ |
| Web UI chat | `ask_llm_with_history` | ✅ | ✅ | ✅ |
| Telegram voice | `ask_llm` (single-turn) | ❌ | ❌ | ❌ |
| System chat (admin) | `ask_llm_with_history` | ✅ | ❌ | ❌ |

> **Critical gap:** Voice uses `ask_llm` (single-turn, `bot_access._with_lang_voice()`) — no history, no memory, no RAG. Tracked in `doc/architecture/conversation.md` → Open items.

---

## 2. RAG — Document Knowledge Base

### 2.1 Upload Pipeline

```
User sends file (Telegram bot handler or Web UI POST /api/upload)
         │
         ▼ bot_documents.py  _process_document_upload()  line ~220
1. Download via Telegram API → temp file in ~/.taris/docs/<chat_id>/
         │
         ▼  _extract_text()  line 42
2. Text extraction
   .txt / .md  → direct read
   .pdf        → PyMuPDF (fitz) FIRST   ← fitz.open(path).get_text()
                 → image placeholders "<image_N>"
                 → pdfminer fallback on PyMuPDF failure
   .docx       → python-docx Document(path).paragraphs
         │
         ▼  SHA256(extracted_text) → check documents.doc_hash
3. Deduplication  ✅ IMPLEMENTED  (v2026.3.31)
   Duplicate → "Replace / Keep Both" confirmation dialog
         │
         ▼  _chunk_text(text, size=512, overlap=64)  line 82
4. Chunking
   Fixed-size 512-char windows with 64-char overlap (no sentence boundary detection)
   Empty chunks stripped
         │
         ▼  _store_text_chunks(doc_id, chat_id, chunks)  line 91
5a. FTS5 indexing  ✅ ALWAYS
   store.upsert_chunk_text() → INSERT INTO doc_chunks (FTS5 virtual table)
         │
5b. Vector embeddings  ⚠️ PARTIAL — see §2.5
   IF store.has_vector_search() AND EmbeddingService.get() is not None:
       svc.embed_batch(chunks) → List[List[float]]
       store.upsert_embedding(doc_id, idx, chat_id, vec)
               → INSERT INTO vec_embeddings (sqlite-vec virtual table)
         │
         ▼
6. Metadata stored in documents table
   {doc_id, chat_id, title, file_path, doc_type, is_shared, doc_hash, metadata}
   metadata = {char_count, n_chunks, file_size_bytes, parse_time_ms}
```

**Status per step:**

| Step | Status | Notes |
|---|---|---|
| File download | ✅ Done | Telegram file API |
| PDF extraction (PyMuPDF + pdfminer) | ✅ Done | v2026.3.32 |
| DOCX extraction | ✅ Done | v2026.3.30+2 |
| TXT/MD extraction | ✅ Done | |
| Deduplication (SHA256) | ✅ Done | v2026.3.31 |
| Chunking (512 char fixed-size) | ✅ Done | No sentence-boundary awareness |
| FTS5 indexing (`doc_chunks`) | ✅ Done | 42 chunks exist for 1 PDF |
| Vector embeddings | ⚠️ PARTIAL | See §2.5 |
| Upload size limit (20 MB) | ✅ Done | `MAX_DOC_SIZE_MB=20` enforced |
| Per-doc stats in metadata | ✅ Done | `parse_time_ms`, `char_count` shown in UI |
| Admin upload stats UI | ❌ Not yet | Metadata stored but no dedicated UI |

### 2.2 Chunking & Embedding

**Chunking** (`bot_documents.py:82`):
```python
def _chunk_text(text, size=512, overlap=64):
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return [c for c in chunks if c.strip()]
```
- Fixed-size windows, no sentence/paragraph boundary detection
- `_CHUNK_SIZE = 512`, `_CHUNK_OVERLAP = 64` (hardcoded; overridable via `RAG_CHUNK_SIZE` env var at startup)
- Runtime `rag_chunk_size` setting readable via `rag_settings.py`, but only applied at upload time

**Embedding** (`bot_embeddings.py`, `store_sqlite.py:523`):
- Model: `sentence-transformers/all-MiniLM-L6-v2` (384-dim, ~90 MB)
- Default: `EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2`
- Backend priority: `fastembed` → `sentence-transformers` → disabled
- `fastembed` 0.8.0 is installed and will use ONNX Runtime (ARM-safe)
- `sentence-transformers` is also installed (PyTorch)
- `EMBED_KEEP_RESIDENT=1` by default (model stays in RAM)

### 2.3 Vector Storage: SQLite vs PostgreSQL

**Current deployment: SQLite with sqlite-vec**

| Component | Status | Notes |
|---|---|---|
| `sqlite-vec` installed | ✅ v0.1.7 | `pip install sqlite-vec` |
| `vec_embeddings` virtual table | ✅ Created | `FLOAT[384]` via `vec0` |
| `store._has_vec` flag | ✅ True | Extension loads successfully |
| `has_vector_search()` returns True | ✅ | Confirmed in live test |
| Vector rows in `vec_embeddings` | **0 rows** | See §2.5 for root cause |

**PostgreSQL adapter** (`store_postgres.py`):
- Written and functional (v2026.4.13)
- Requires `psycopg2` (NOT installed: `ModuleNotFoundError: No module named 'psycopg2'`)
- Requires PostgreSQL + pgvector on target machine
- Activated via `STORE_BACKEND=postgres` in `bot.env`
- **Current deployment uses SQLite** (no `STORE_BACKEND` override in `bot.env`)

**Switch logic** (`store.py` factory):
```python
STORE_BACKEND = os.environ.get("STORE_BACKEND", "sqlite")
# "sqlite" → SQLiteStore(db_path)
# "postgres" → PostgresStore(db_url)
```

### 2.4 Retrieval & Context Injection

**Entry point:** `telegram/bot_access.py:_docs_rag_context(chat_id, query)` (line ~177)

**Full call chain:**
```
_handle_chat_message()          bot_handlers.py:~930
  → _user_turn_content(chat_id, user_text)    bot_access.py:282
      → _docs_rag_context(chat_id, query)     bot_access.py:177
          → retrieve_context(...)             bot_rag.py:155
              1. classify_query(text, has_docs) → "simple"|"factual"|"contextual"
              2. detect_rag_capability()       → FTS5_ONLY|HYBRID|FULL
              3. store.search_fts(query, chat_id, top_k*2)  (always)
              4. EmbeddingService.embed(query) + store.search_similar(vec, ...)  (if HYBRID/FULL)
              5. reciprocal_rank_fusion(fts5, vector, k=60)  (if vector results)
              6. Assemble: top-K chunks joined with "\n---\n", max 2000 chars
          → returns "[KNOWLEDGE FROM USER DOCUMENTS]\n{assembled}\n[END KNOWLEDGE]\n\n"
```

**Query classification** (`bot_rag.py:classify_query`):
- `"simple"` → skip RAG (greetings, <12 chars, no factual keywords)
- `"factual"` → use RAG (what/how/where/etc. + user has docs)
- `"contextual"` → use RAG optionally (longer text, no clear factual marker)

**RAG capability detection** (`bot_rag.py:detect_rag_capability`):
- Checks `store.has_vector_search()` + `/proc/meminfo` (or psutil)
- RAM ≥ 8 GB + vectors → `FULL`; ≥ 4 GB + vectors → `HYBRID`; else → `FTS5_ONLY`
- **Current: HYBRID** (machine has > 4 GB RAM, sqlite-vec loaded)

**RAG timeout:** 5.0 s default (`RAG_TIMEOUT` env var, overridable via `rag_settings.json`).  
Enforced via `concurrent.futures.ThreadPoolExecutor` with `.result(timeout=rag_timeout)`.

**Logging:** Every retrieval → `rag_log` table (currently **0 rows** — see §2.5).

### 2.5 Current State & Bugs Found

#### Bug 1: Vector embeddings never generated for uploaded documents ⚠️

**Symptom:** 1 PDF uploaded (42 FTS5 chunks), but `vec_embeddings` has **0 rows**.

**Root cause analysis:**  
The document (`iDOMP_Scan2Me...pdf`) was uploaded **before** `bot_embeddings.py` and `EmbeddingService` were integrated into the upload pipeline. Git history:
- `bot_embeddings.py` added in commit `6e3561a` (§25.4)
- Document `created_at = 2026-03-31 21:43:58`

Even post-integration, there may be a startup timing issue: `SQLiteStore.__init__` runs `sqlite_vec.load(conn)` and sets `_has_vec = True`, but `EmbeddingService.get()` loads the model lazily on first call. The fastembed backend **tries to download the ONNX model from HuggingFace on first load** — which would fail silently in a service environment without internet at startup.

**Evidence:** When triggered manually, fastembed makes live HTTP calls to `huggingface.co` to fetch `qdrant/all-MiniLM-L6-v2-onnx`. If the service process has no network access at that moment, or if model download is incomplete, `EmbeddingService.get()` returns `None` → no embeddings generated → **silent fallback to FTS5-only**.

**Impact:**
- RAG works (FTS5 keyword search active), but without semantic similarity
- `detect_rag_capability()` reports `HYBRID` because `has_vector_search()=True`
- `bot_rag.retrieve_context()` attempts `search_similar()` → returns empty list → falls back to FTS5 results
- No data loss, but vector search is silently not contributing

**Fix required:**
1. Pre-download the embedding model during setup: `python3 -c "from fastembed import TextEmbedding; TextEmbedding('Qdrant/all-MiniLM-L6-v2-onnx')"`
2. Add a re-indexing function to retroactively generate embeddings for existing chunks
3. Add a health check to detect `has_vector_search()=True` but `vec_embeddings` row count = 0

#### Bug 2: `rag_log` table is empty (0 rows) ❌

**Expected:** Every RAG retrieval logs to `rag_log` via `store.log_rag_activity()`.  
**Actual:** 0 rows in `rag_log`.  
**Likely cause:** `strategy == "skipped"` branch in `bot_rag.retrieve_context()` — if all queries are classified as `"simple"` or no documents match, `store.log_rag_activity()` is never called. The guard at line ~218 in `bot_access.py`:
```python
if strategy == "skipped" or not assembled:
    return ""
# ... log only happens here after successful retrieval
```
Since `rag_log` is empty despite `llm_calls` having 27 rows, most queries were either `"simple"` or the 1 PDF had no matching chunks for actual user queries.

#### Current DB state (2026-04-01)

| Table | Rows | Notes |
|---|---|---|
| `documents` | 1 | 1 PDF uploaded |
| `doc_chunks` (FTS5) | 42 | PDF chunked correctly |
| `vec_embeddings` | **0** | Bug: no embeddings generated |
| `rag_log` | **0** | No RAG retrievals recorded |
| `llm_calls` | 27 | With context snapshots |
| `chat_history` | 54 | Live STM |
| `conversation_summaries` | 6 (4 long + 2 mid) | MTM/LTM working |
| `notes_index` | 4 | Notes stored |

---

## 3. Notes as Knowledge

### 3.1 Storage

Notes use a **dual-storage** model:
- **DB primary:** `notes_index` table (slug, chat_id, title, content, timestamps)
- **File mirror:** `~/.taris/notes/<chat_id>/<slug>.md` (Markdown file)

**Save path** (`store_sqlite.py:save_note`):
```python
# 1. Upsert into notes_index (slug + chat_id = PK)
db.execute("INSERT INTO notes_index ... ON CONFLICT ...")
# 2. Write file: ~/.taris/notes/<chat_id>/<slug>.md
with open(path, "w") as fh:
    fh.write(f"# {title}\n\n{content}")
```

**Load path** (`store_sqlite.py:load_note`):
```python
row = db.execute("SELECT * FROM notes_index WHERE slug=? AND chat_id=?")
# Content from notes_index.content column (v2026.3.31+)
# Falls back to reading .md file if content column is empty
```

**Current DB state:** 4 notes for 2 users. Content stored in `notes_index.content` column (v2026.3.31+).

### 3.2 Usage in Conversations

**Notes are NOT injected into LLM context automatically.**

From `doc/architecture/knowledge-base.md`:
> Notes currently stored as Markdown files and are **not** indexed or injected automatically.

The architecture doc lists Notes as a **planned** knowledge source (⏳):
- Design intent: index notes into `fts_documents` with `type='note'` tag at save
- Find relevant notes via `search_fts(query, filter='note')`
- Inject alongside document chunks into `role:user`

**There is no code path** in `bot_access.py`, `bot_handlers.py`, or `bot_state.py` that reads notes for LLM injection.

### 3.3 Current State

| Feature | Status |
|---|---|
| Notes stored in DB | ✅ Done (v2026.3.31) |
| Notes readable by user | ✅ Done |
| Notes indexed in FTS5 for RAG | ❌ Not implemented |
| Notes injected into conversation | ❌ Not implemented |
| "Notes as KB" toggle in Profile | ❌ Not implemented |

---

## 4. Long-term Memory (STM / MTM / LTM)

### 4.1 Architecture

```
STM (Short-Term Memory)
  ↓ CONV_SUMMARY_THRESHOLD=15 turns reached
MTM (Mid-Term Memory) — triggered async in background thread
  ↓ CONV_MID_MAX=5 mid-summaries accumulated
LTM (Long-Term Memory) — compaction: all mid → single long paragraph
```

**Configured via** `system_settings` table (Admin Panel → 🧠 Memory Settings):

| Constant | Default | Source |
|---|---|---|
| `CONVERSATION_HISTORY_MAX` | 15 | `bot_config.py` |
| `CONV_SUMMARY_THRESHOLD` | 15 | `bot_config.py` |
| `CONV_MID_MAX` | 5 | `bot_config.py` |

All three are runtime-overridable via `get_conv_history_max()` / `get_conv_summary_threshold()` / `get_conv_mid_max()` which check `system_settings` table first.

### 4.2 Storage

| Tier | Storage | Table/Location |
|---|---|---|
| STM (live turns) | SQLite + in-memory dict | `chat_history` table + `_conversation_history` dict |
| MTM (session summaries) | SQLite | `conversation_summaries` table, `tier='mid'` |
| LTM (compacted summaries) | SQLite | `conversation_summaries` table, `tier='long'` |

**`conversation_summaries` schema:**
```sql
CREATE TABLE conversation_summaries (
    id         INTEGER PRIMARY KEY,
    chat_id    INTEGER NOT NULL,
    summary    TEXT NOT NULL,
    tier       TEXT NOT NULL DEFAULT 'mid',  -- 'mid' or 'long'
    msg_count  INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
)
```

**Current DB state:** 6 summaries (4 long + 2 mid) — MTM/LTM pipeline is actively working.

### 4.3 Conversation Injection

**Where:** `bot_state.py:get_memory_context()` (line ~338)  
**When:** At every multi-turn LLM call, appended to the `role:system` message  
**How:** `bot_handlers.py:_handle_chat_message()` (line ~958):

```python
# Inject tiered long/mid-term memory summaries
from core.bot_state import get_memory_context
from core.bot_db import db_get_user_pref
if db_get_user_pref(chat_id, "memory_enabled", "1") == "1":
    _mem_ctx = get_memory_context(chat_id)
    if _mem_ctx:
        system_content = system_content + "\n\n" + _mem_ctx
```

`get_memory_context()` returns:
```
[Memory context from previous sessions:]
[LONG] <compacted paragraph>
[MID] <2-4 sentence session summary>
[MID] <...>
```

**Per-user toggle:** Profile → 🧠 Memory On/Off → writes `user_prefs.memory_enabled`.  
**Clear:** Profile → 🗑 Clear Memory → `clear_history()` deletes `chat_history` + `conversation_summaries`.

### 4.4 Current State

| Feature | Status |
|---|---|
| STM sliding window (in-memory + DB) | ✅ Working (v2026.3.30) |
| MTM async summarization | ✅ Working (v2026.3.30+5) — 6 summaries in DB |
| LTM compaction (mid→long) | ✅ Working (v2026.3.30+5) |
| Memory injection in system message | ✅ Working (bot_handlers.py:958) |
| Per-user memory on/off toggle | ✅ Working (v2026.3.31) |
| Admin memory settings panel | ✅ Working (v2026.3.31) |
| Clear all tiers via Profile | ✅ Working |
| **Voice channel uses memory** | ❌ Not implemented (voice uses single-turn `ask_llm`) |
| Memory persistence across restart | ✅ DB-backed; `load_conversation_history()` at startup |

---

## 5. Shared Documents

### 5.1 Concept

Documents have an `is_shared` flag (default 0 = private):
- **Personal:** only the uploading `chat_id` can retrieve chunks in RAG
- **Shared:** all users see the document in their RAG context

**Search filter** in `store_sqlite.py:search_fts()`:
```python
# FTS5 query filters by chat_id
WHERE doc_chunks MATCH ? AND chat_id = ?
```

> ⚠️ **Issue:** The `search_fts()` function filters only by the uploader's `chat_id`. Shared documents (is_shared=1) are **not** returned for other users' chat_ids because `doc_chunks.chat_id` still stores the original uploader's `chat_id`.

The `list_documents()` method also only returns `WHERE chat_id = ?`.

**Expected behavior for shared docs** (from architecture docs): admin toggles `is_shared`, and all users should get those chunks. The current implementation stores `chat_id` as the uploader's ID in `doc_chunks` — so shared docs are **not actually accessible to other users in search**.

### 5.2 Implementation Status

| Feature | Status | Notes |
|---|---|---|
| `is_shared` flag in documents table | ✅ Schema exists | |
| Admin "Make Shared" toggle | ✅ UI implemented | `_handle_admin_doc_toggle_shared()` |
| Shared docs returned in other users' RAG | ❌ Bug | `doc_chunks.chat_id` = uploader; no cross-user query |
| Admin doc list (all users' docs) | ✅ Implemented | `_handle_admin_doc_list()` |

---

## 6. System Self-Knowledge

### 6.1 Bot Capabilities Prompt

Every LLM call includes a `[BOT CONFIG]` block in the `role:system` message (`bot_access.py:_bot_config_block()`):
```
[BOT CONFIG]
Name: Taris | Version: 2026.3.49
LLM: ollama/qwen2:0.5b
STT: faster_whisper/base
TTS: piper/<model_name>
[END BOT CONFIG]
```

This allows the LLM to answer "what can you do?", "what version are you?", "what models do you use?".

**Security preamble** (`security/bot_security.py:SECURITY_PREAMBLE`) is also injected — defines bot identity, rules, and anti-injection guidelines.

**Feature capabilities** are NOT hardcoded as a separate knowledge base. When a user asks "what features do you have?", the LLM responds based on:
1. The `[BOT CONFIG]` block
2. Its training data about Taris
3. Any relevant documents in the user's knowledge base

There is no dynamic feature list auto-generated from code.

### 6.2 Current State

| Feature | Status |
|---|---|
| `[BOT CONFIG]` in system message | ✅ Every call |
| Security preamble in system message | ✅ Every call |
| Language instruction in system message | ✅ Every call |
| Feature list / capabilities document | ❌ Not implemented |
| Bot "knows about itself" beyond config block | Only via LLM training data |

---

## 7. Monitoring & Tracing

### 7.1 LLM Context Trace (T60 feature)

**Fully implemented** — `bot_db.py:db_get_llm_trace()` (line 402).

Every LLM call records into `llm_calls` table:

| Column | Content |
|---|---|
| `call_id` | UUID |
| `chat_id` | User ID |
| `provider` | LLM provider name |
| `model` | Model name |
| `temperature` | Effective temperature |
| `history_count` | Number of history messages |
| `system_chars` | system message length |
| `history_chars` | total history chars |
| `rag_chunks_count` | chunks retrieved |
| `rag_context_chars` | RAG text injected |
| `response_preview` | First 300 chars of response |
| `context_snapshot` | JSON: last 5 history turns (role + 80-char preview) |
| `response_ok` | 1=success, 0=error |
| `created_at` | Timestamp |

**Admin UI:** `telegram/bot_admin.py:_handle_admin_llm_trace()` (line 1236)  
**Access:** Admin Panel → `🔍 Context Trace ▶` button (callback `admin_llm_trace`)  
**Shows:** Last 5 calls per admin's chat_id with provider, timing, RAG stats, context snapshot

**Current data:** 27 recorded `llm_calls` from 2 users.

### 7.2 Admin Panels

| Panel | Access | Data source |
|---|---|---|
| **RAG Stats** | Admin → RAG → 📊 RAG Stats | `rag_log` table (0 rows currently) |
| **LLM Context Trace** | Admin → 🔍 Context Trace | `llm_calls` table (27 rows) |
| **RAG Settings** | Admin → RAG → ⚙️ Settings | `rag_settings.json` |
| **Memory Settings** | Admin → 🧠 Memory | `system_settings` table |
| **Pipeline Logs** | Web UI → /api/pipeline_log | `~/.taris/logs/pipeline_YYYY-MM-DD.jsonl` |

### 7.3 Conversation Logs

| Log type | Location | Format |
|---|---|---|
| Live chat turns | `chat_history` DB table | SQL rows (role, content, created_at) |
| LLM call trace | `llm_calls` DB table | SQL rows with context snapshot |
| RAG retrievals | `rag_log` DB table | SQL rows (currently empty) |
| Pipeline analytics | `~/.taris/logs/pipeline_YYYY-MM-DD.jsonl` | JSONL (stt/llm/tts/rag stages) |
| Application logs | `journalctl -u taris-telegram` | Python logging |

**`pipeline_logger.py`** (`core/pipeline_logger.py`) writes one JSONL record per pipeline stage (STT, LLM, TTS, RAG, decode) to `~/.taris/logs/`. Exposed via Web UI endpoint `/api/pipeline_log?stage=llm&limit=50`.

### 7.4 Current State

| Feature | Status |
|---|---|
| `llm_calls` trace table + columns | ✅ Implemented (v2026.3.32) |
| Admin LLM Context Trace UI | ✅ Implemented |
| `rag_log` table + logging | ✅ Schema + code present |
| RAG Stats admin panel | ✅ Implemented (shows empty due to bug §2.5) |
| Pipeline JSONL logs | ✅ `pipeline_logger.py` |
| Web UI `/api/pipeline_log` endpoint | ✅ Implemented |
| Conversation history in DB | ✅ 54 rows in `chat_history` |
| Per-call context snapshot | ✅ JSON stored in `llm_calls.context_snapshot` |

---

## 8. Feature Status Matrix

| Feature | Category | Status | Version | Notes |
|---|---|---|---|---|
| Document upload (txt/md/pdf/docx) | RAG | ✅ Done | v2026.3.32 | |
| FTS5 text chunking (512 char) | RAG | ✅ Done | v2026.3.30 | 42 chunks for 1 PDF |
| BM25 keyword search | RAG | ✅ Done | v2026.3.30 | `search_fts()` |
| RAG injection into user turn | RAG | ✅ Done | v2026.3.30 | `_docs_rag_context()` |
| `classify_query()` routing | RAG | ✅ Done | v2026.3.32 | |
| `detect_rag_capability()` | RAG | ✅ Done | v2026.3.32 | Reports HYBRID correctly |
| `reciprocal_rank_fusion()` | RAG | ✅ Done | v2026.3.32 | Code present |
| sqlite-vec schema + adapter methods | RAG | ✅ Done | v2026.4.13 | `vec_embeddings` table |
| **Vector embedding generation** | RAG | ⚠️ Partial | v2026.4.13 | Code present; **0 rows** in DB |
| PostgreSQL + pgvector adapter | RAG | ✅ Done | v2026.4.13 | `psycopg2` not installed |
| Document deduplication (SHA256) | RAG | ✅ Done | v2026.3.31 | |
| Admin RAG on/off toggle | RAG | ✅ Done | v2026.3.43 | |
| Admin RAG settings panel | RAG | ✅ Done | v2026.3.30+4 | |
| Per-user RAG top-K override | RAG | ✅ Done | v2026.3.32 | `user_prefs` table |
| RAG monitoring / rag_log | RAG | ⚠️ Partial | v2026.3.30+4 | Table exists; **0 rows** |
| Admin RAG Stats panel | RAG | ✅ Done | v2026.3.32 | Shows empty data |
| Document sharing (`is_shared`) | RAG | ⚠️ Partial | v2026.3.29 | Schema OK; cross-user search broken |
| Notes-as-KB toggle | RAG | ❌ Not impl. | — | Planned in §10 |
| Calendar context injection | RAG | ❌ Not impl. | — | Planned in §10 |
| Contacts lookup in conversation | RAG | ❌ Not impl. | — | Planned in §4 |
| Remote RAG MCP service | RAG | ❌ Not impl. | — | §4.2 |
| Notes stored in DB | Memory | ✅ Done | v2026.3.31 | `notes_index` table |
| STM sliding window | Memory | ✅ Done | v2026.3.30 | `chat_history` + in-memory |
| MTM async summarization | Memory | ✅ Done | v2026.3.30+5 | 6 summaries active |
| LTM compaction (mid→long) | Memory | ✅ Done | v2026.3.30+5 | |
| Memory injection in system message | Memory | ✅ Done | v2026.3.30+5 | `get_memory_context()` |
| Per-user memory on/off | Memory | ✅ Done | v2026.3.31 | `user_prefs.memory_enabled` |
| Admin memory settings | Memory | ✅ Done | v2026.3.31 | `system_settings` table |
| Clear all memory tiers | Memory | ✅ Done | v2026.3.30+5 | Profile → 🗑 Clear memory |
| **Voice channel uses memory** | Memory | ❌ Missing | — | Voice = single-turn `ask_llm` |
| **Voice channel uses RAG** | Memory | ❌ Missing | — | Voice = single-turn `ask_llm` |
| `[BOT CONFIG]` in system prompt | Self-knowledge | ✅ Done | v2026.3.30 | Name/version/LLM/STT/TTS |
| Feature capabilities list | Self-knowledge | ❌ Not impl. | — | LLM uses training data |
| LLM call tracing (`llm_calls`) | Monitoring | ✅ Done | v2026.3.32 | 27 rows |
| Admin Context Trace panel | Monitoring | ✅ Done | — | `_handle_admin_llm_trace()` |
| Pipeline JSONL logs | Monitoring | ✅ Done | — | `pipeline_logger.py` |
| Web UI `/api/pipeline_log` | Monitoring | ✅ Done | — | |
| Multi-turn chat with history | Conversation | ✅ Done | v2026.3.30 | `ask_llm_with_history()` |
| `role:system` in every LLM call | Conversation | ✅ Done | v2026.3.30+3 | `_build_system_message()` |
| RAG in voice channel | Conversation | ❌ Missing | — | Voice uses `_with_lang_voice()` |
| History in voice channel | Conversation | ❌ Missing | — | Voice uses `ask_llm()` |
| Multi-modal RAG (images/tables) | RAG | ❌ Not impl. | — | §10 |

---

## 9. Root Cause Analysis: Known Bugs

### Bug A: `vec_embeddings` has 0 rows despite 42 FTS5 chunks

**Affected:** `vec_embeddings` table, hybrid RAG path  
**Symptom:** `store.search_similar()` always returns empty list; RRF fusion has nothing to fuse  
**Root cause (likely):** The single uploaded PDF was indexed before `bot_embeddings.py` was properly wired (or `fastembed` downloaded its ONNX model from HuggingFace on first call, which may fail in a service environment).

Evidence:
- `fastembed` is installed and makes network calls to `huggingface.co` on first `TextEmbedding()` instantiation
- If service process lacks network access at document upload time, `EmbeddingService.get()` returns `None`
- Failure is silently swallowed: `except Exception as exc: log.warning("[Docs] embedding failed...")`

**Impact:** Queries run FTS5-only despite `detect_rag_capability()` reporting `HYBRID`. No user-visible error.

**Fix:**
1. Pre-download model: run `python3 -c "from fastembed import TextEmbedding; TextEmbedding('Qdrant/all-MiniLM-L6-v2-onnx')"` during setup
2. Add a re-embed function for existing documents (call `_store_text_chunks` again for existing chunks)
3. Add admin health check: alert if `has_vector_search()=True` but `COUNT(*) FROM vec_embeddings = 0`

### Bug B: Shared documents don't appear in other users' RAG

**Affected:** `search_fts()`, `search_similar()` in store_sqlite.py  
**Symptom:** Document with `is_shared=1` is not found when user B searches (only user A, the uploader, finds it)  
**Root cause:** Both `doc_chunks` and `vec_embeddings` store `chat_id` = uploader's ID.  
`search_fts()` query: `WHERE doc_chunks MATCH ? AND chat_id = ?` — hard-filters by the requesting user's chat_id.

**Fix:** Modify `search_fts()` and `search_similar()` to also include chunks from shared documents:
```sql
WHERE doc_chunks MATCH ? 
  AND (chat_id = ? OR doc_id IN (SELECT doc_id FROM documents WHERE is_shared = 1))
```

### Bug C: `rag_log` always empty

**Affected:** Admin → RAG Stats panel  
**Symptom:** Stats panel shows "No RAG queries recorded yet" despite 27 LLM calls  
**Root cause:** The `log_rag_activity()` call only happens on successful retrieval with non-empty `assembled` text. With only 1 PDF and most conversations being greetings/short messages classified as `"simple"`, the retrieval almost always takes the `"skipped"` branch.  
**Impact:** Stats panel is non-functional. Not a code bug — a UX/data problem.

### Bug D: Voice channel has no memory, no history, no RAG

**Affected:** All voice interactions  
**Symptom:** Voice LLM responses are always single-turn, context-free  
**Root cause:** `bot_voice.py:_handle_voice_message()` calls `ask_llm(_with_lang_voice(...))` (single-turn), not `ask_llm_with_history()`. The `_with_lang_voice()` function injects RAG but NOT history.

Actually: from the architecture doc, even `_with_lang_voice()` injects RAG context. But there's no history window.  
Tests T59 checks that `ask_llm_with_history` is imported in `bot_voice.py` — if this test passes, the import exists but may not be used in the main call path.

**Impact:** Users get disconnected, context-free responses in voice mode.

---

## 10. Implementation Plan — Next Steps

### Priority 1 — Fix embedding pipeline (HIGH, ~1 day)

1. **Pre-download fastembed model during setup:**
   ```bash
   python3 -c "from fastembed import TextEmbedding; TextEmbedding('Qdrant/all-MiniLM-L6-v2-onnx')"
   ```
2. **Add admin "Re-index embeddings" function** in `bot_documents.py`:
   - Read existing `doc_chunks` content by doc_id
   - Call `_store_text_chunks()` again for each doc
   - Expose via Admin Panel → Documents → 🔄 Re-embed
3. **Add health check** to `detect_rag_capability()`: warn if `has_vector_search()` but no vectors stored

### Priority 2 — Fix shared documents RAG (HIGH, ~0.5 day)

Modify `store_sqlite.py:search_fts()` and `search_similar()` to also query chunks with `is_shared=1` documents. This requires a JOIN or subquery against the `documents` table.

### Priority 3 — Voice channel history + RAG (HIGH, ~1-2 days)

Migrate `bot_voice.py:_handle_voice_message()` from `ask_llm()` to `ask_llm_with_history()`:
1. Use `_build_system_message()` instead of `_with_lang_voice()` for the system message
2. Use `_voice_user_turn_content()` for the current turn
3. Load history via `get_history_with_ids(chat_id)`
4. Call `ask_llm_with_history(messages, ...)`
5. Call `add_to_history()` for both user and assistant turns

### Priority 4 — Notes as knowledge base (MEDIUM, ~1 day)

1. At note save time (`bot_notes.py`), also call `store.upsert_chunk_text(note_slug, 0, chat_id, content)` into `doc_chunks` with `doc_id = "note:<slug>"`
2. Register note in `documents` table with `doc_type='note'`
3. Optionally add a Profile toggle: "Include my notes in AI context"

### Priority 5 — Calendar context injection (MEDIUM, ~0.5 day)

Inject today's + upcoming 3-day events into `role:system`:
```python
# In _build_system_message():
events = store.load_events(chat_id, from_dt=today, to_dt=today+3days)
if events:
    system += "[CALENDAR]\n" + format_events(events) + "[END CALENDAR]\n"
```

### Priority 6 — fastembed model pre-warm (LOW, ~0.5 day)

Add `EmbeddingService.get()` call at service startup (in `telegram_menu_bot.py:main()`) to fail-fast rather than silently falling back.

### Priority 7 — pgvector on OpenClaw (MEDIUM, ~1 week)

Install PostgreSQL + pgvector → set `STORE_BACKEND=postgres` → run migration → validate HYBRID tier with true vector search. Tracks §25.6 Phase B.

---

## Appendix: Key File/Function Reference

| Concern | File | Function/Line |
|---|---|---|
| LLM system message assembly | `telegram/bot_access.py` | `_build_system_message()` |
| RAG injection into user turn | `telegram/bot_access.py` | `_user_turn_content()`, `_docs_rag_context()` |
| Memory injection | `telegram/bot_handlers.py` | `_handle_chat_message()` line 958 |
| Memory summaries | `core/bot_state.py` | `get_memory_context()`, `_summarize_session_async()` |
| Multi-turn LLM dispatch | `core/bot_llm.py` | `ask_llm_with_history()` line 517 |
| RAG adaptive routing | `core/bot_rag.py` | `retrieve_context()`, `classify_query()` |
| Embedding service | `core/bot_embeddings.py` | `EmbeddingService.get()`, `embed_batch()` |
| Document upload + chunking | `features/bot_documents.py` | `_process_document_upload()`, `_store_text_chunks()` line 91 |
| FTS5 search | `core/store_sqlite.py` | `search_fts()` line 595 |
| Vector search | `core/store_sqlite.py` | `search_similar()` line 547, `upsert_embedding()` line 523 |
| LLM call tracing | `core/bot_db.py` | `db_log_llm_call()` line 370, `db_get_llm_trace()` line 402 |
| Admin trace UI | `core/bot_db.py` | `_handle_admin_llm_trace()` line 1236 |
| Pipeline analytics | `core/pipeline_logger.py` | `PipelineLog` class |
| RAG settings runtime | `core/rag_settings.py` | `get()`, `set_value()` |
