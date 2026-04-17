# Flexible Storage Architecture — Multi-Backend Design

**Status:** 🔲 Proposal  
**Supersedes:** §9 SQLite-only plan (extended scope — §9 Phase 1–3 remains valid as the baseline)  
**Last updated:** March 2026

---

## 1. Design Goals

| Goal | Description |
|---|---|
| **Embedded-first** | PicoClaw / ZeroClaw: zero external services, single SQLite file |
| **Server-class on OpenClaw** | PostgreSQL + pgvector for full CRM, multimodal RAG, multi-user workloads |
| **Configuration-driven** | One env var `STORE_BACKEND=sqlite|postgres` switches the entire stack |
| **Adapter isolation** | Feature modules (notes, calendar, RAG) call the adapter interface — never raw SQL |
| **Binary files always on disk** | Audio, images, raw document blobs are **never** stored in the DB |
| **Vector search native** | Embeddings and RAG chunks stored in the same DB as structured text data |
| **Minimal RAM on edge devices** | sqlite-vec extension adds ~1 MB; embedding model loaded on-demand only |

---

## 2. Storage Tiers by Platform

| Platform | DB Backend | Vector Extension | Binary Files Root | Max Practical Vectors |
|---|---|---|---|---|
| **ZeroClaw** (Pi Zero 2W, 512 MB) | SQLite | `sqlite-vec` | `~/.taris/files/` | ~10k (cosine, 384-dim) |
| **PicoClaw** (Pi 3 B+, 1 GB) | SQLite | `sqlite-vec` | `~/.taris/files/` | ~50k (cosine, 384-dim) |
| **OpenClaw** (Pi 5 / RK3588 / Jetson) | PostgreSQL | `pgvector` | `/data/taris/files/` or S3-compat | millions |

### 2.1 What goes in DB vs on disk

| Data | SQLite (Pico/Zero) | PostgreSQL (OpenClaw) | Always in files |
|---|---|---|---|
| Users / roles / registration status | ✅ `users` | ✅ `users` | — |
| Notes text content | ✅ `notes` (TEXT column) | ✅ `notes` | `.md` export only |
| Notes metadata (title, mtime, tags) | ✅ `notes_index` | ✅ `notes_index` | — |
| Calendar events | ✅ `calendar_events` | ✅ `calendar_events` | — |
| Conversation / chat history | ✅ `chat_history` (windowed) | ✅ `chat_history` | — |
| Mail credentials (encrypted) | ✅ `mail_creds` | ✅ `mail_creds` | — |
| Document entries / KB chunks | ✅ `documents` | ✅ `documents` | original binary in `/files/docs/` |
| Embeddings / RAG chunks | ✅ `vec_embeddings` (sqlite-vec) | ✅ `embeddings` (`vector` type) | — |
| Voice opts flags | ✅ `voice_opts` | ✅ `voice_opts` | — |
| TTS orphan cleanup tracker | ✅ `tts_pending` | ✅ `tts_pending` | — |
| Contacts | ✅ `contacts` | ✅ `contacts` | — |
| Audio files (voice notes, TTS) | — | — | ✅ `.ogg` in `/files/audio/` |
| Images (photos, scanned docs) | — | — | ✅ `.jpg/.png` in `/files/images/` |
| Raw document blobs (PDF, DOCX) | — | — | ✅ original in `/files/docs/` |
| Bot secrets / API tokens | — | — | ✅ `bot.env` only |
| LLM / voice model binaries | — | — | ✅ `.onnx`, Vosk dirs |
| taris `config.json` | — | — | ✅ taris-owned |
| Static assets (CSS, JS, templates) | — | — | ✅ source tree |

---

## 3. Adapter Interface (Python Protocol)

```python
# src/core/store_base.py
from typing import Protocol, Any

class DataStore(Protocol):

    # ── User management ──────────────────────────────────────────────
    def upsert_user(self, chat_id: int, **fields) -> None: ...
    def get_user(self, chat_id: int) -> dict | None: ...
    def list_users(self, role: str | None = None) -> list[dict]: ...
    def set_user_role(self, chat_id: int, role: str) -> None: ...

    # ── Notes ────────────────────────────────────────────────────────
    def save_note(self, chat_id: int, slug: str, title: str, content: str) -> None: ...
    def load_note(self, chat_id: int, slug: str) -> dict | None: ...
    def list_notes(self, chat_id: int) -> list[dict]: ...
    def delete_note(self, chat_id: int, slug: str) -> bool: ...

    # ── Calendar ─────────────────────────────────────────────────────
    def save_event(self, chat_id: int, event: dict) -> None: ...
    def load_events(self, chat_id: int,
                    from_dt: str | None = None,
                    to_dt: str | None = None) -> list[dict]: ...
    def delete_event(self, chat_id: int, ev_id: str) -> bool: ...

    # ── Conversation history ──────────────────────────────────────────
    def append_history(self, chat_id: int, role: str, content: str) -> None: ...
    def get_history(self, chat_id: int, last_n: int = 15) -> list[dict]: ...
    def clear_history(self, chat_id: int) -> None: ...

    # ── Voice opts ───────────────────────────────────────────────────
    def get_voice_opts(self, chat_id: int | None = None) -> dict: ...
    def set_voice_opt(self, key: str, value: bool,
                      chat_id: int | None = None) -> None: ...

    # ── Documents / knowledge base ────────────────────────────────────
    def save_document_meta(self, doc_id: str, chat_id: int,
                           title: str, file_path: str,
                           doc_type: str, metadata: dict | None = None) -> None: ...
    def list_documents(self, chat_id: int) -> list[dict]: ...
    def delete_document(self, doc_id: str) -> None: ...

    # ── Vector / RAG ─────────────────────────────────────────────────
    def upsert_embedding(self, doc_id: str, chunk_idx: int, chat_id: int,
                         chunk_text: str, embedding: list[float],
                         metadata: dict | None = None) -> None: ...
    def search_similar(self, embedding: list[float], chat_id: int,
                       top_k: int = 5) -> list[dict]: ...
    def delete_embeddings(self, doc_id: str) -> None: ...

    # ── Misc ─────────────────────────────────────────────────────────
    def get_mail_creds(self, chat_id: int) -> dict | None: ...
    def save_mail_creds(self, chat_id: int, creds: dict) -> None: ...
    def close(self) -> None: ...
```

### 3.1 Store singleton factory

```python
# src/core/store.py
import os
from core.store_base import DataStore

def create_store() -> DataStore:
    backend = os.environ.get("STORE_BACKEND", "sqlite").lower()
    if backend == "postgres":
        from core.store_postgres import PostgresStore
        return PostgresStore(dsn=os.environ["STORE_PG_DSN"])
    from core.store_sqlite import SQLiteStore
    db_path = os.path.expanduser(
        os.environ.get("STORE_DB_PATH", "~/.taris/taris.db"))
    return SQLiteStore(db_path=db_path)

# Module-level singleton — imported by all feature modules
store: DataStore = create_store()
```

Feature modules use only the adapter — never raw SQL:

```python
# In bot_calendar.py:
from core.store import store

def _cal_load(chat_id: int) -> list[dict]:
    return store.load_events(chat_id)

def _cal_save_event(chat_id: int, event: dict) -> None:
    store.save_event(chat_id, event)
```

---

## 4. SQLite Adapter — PicoClaw / ZeroClaw

**Implementation:** `src/core/store_sqlite.py`

### 4.1 Vector support: `sqlite-vec`

`sqlite-vec` (github.com/asg017/sqlite-vec) is a loadable SQLite extension written in pure C.  
It ships as a Python wheel (`pip install sqlite-vec`) and runs on ARM aarch64 with no external dependencies.

```python
import sqlite3
import sqlite_vec

conn = sqlite3.connect("taris.db")
sqlite_vec.load(conn)   # registers the vec0 virtual table module
```

Vector table DDL:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS vec_embeddings USING vec0(
    doc_id      TEXT      NOT NULL,
    chunk_idx   INTEGER   NOT NULL,
    chat_id     INTEGER   NOT NULL,
    chunk_text  TEXT,
    embedding   FLOAT[384]           -- all-MiniLM-L6-v2 dim = 384
);
```

Search (cosine similarity via `embedding MATCH`):

```sql
SELECT doc_id, chunk_text, distance
FROM   vec_embeddings
WHERE  chat_id   = ?
  AND  embedding MATCH ?          -- query vector as binary blob
ORDER  BY distance
LIMIT  5;
```

> `sqlite-vec` is **fully optional** — if not installed, `search_similar()` raises `StoreCapabilityError`.  
> Feature code must guard: `if store.has_vector_search(): ...`

### 4.2 Documents table (extended bot_db schema)

```sql
CREATE TABLE IF NOT EXISTS documents (
    doc_id      TEXT    PRIMARY KEY,
    chat_id     INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    file_path   TEXT,               -- relative to STORE_FILES_ROOT
    doc_type    TEXT,               -- 'pdf' | 'txt' | 'note' | 'image' | ...
    metadata    TEXT,               -- JSON blob
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_docs_chat ON documents(chat_id);
```

### 4.3 RAM budget with sqlite-vec

| Component | PicoClaw (1 GB) | ZeroClaw (512 MB) |
|---|---|---|
| `sqlite-vec` loaded extension | ~1 MB | ~1 MB |
| 10k vectors × 384 dim × f32 | ~15 MB | 15 MB (≈ limit) |
| 50k vectors × 384 dim × f32 | ~75 MB | ❌ exceeds budget |
| Embedding model `all-MiniLM-L6-v2` | ~90 MB (load on-demand) | 90 MB load-then-release |

**ZeroClaw limit:** max ~10k chunks ≈ 200–300 medium documents. The embedding model is loaded only during document ingestion, then released — it must **not** stay resident.

### 4.4 Key implementation details

- **WAL mode:** `PRAGMA journal_mode=WAL` — allow concurrent reads during write operations
- **Thread safety:** `check_same_thread=False` + per-thread connection cache (same pattern as `bot_db.py`)
- **Credential encryption:** mail passwords and OAuth tokens stored AES-encrypted (Fernet) — key lives in `bot.env` as `STORE_CRED_KEY`
- **sqlite-vec optional guard:** `_has_vec: bool` flag set at init; `search_similar()` raises `StoreCapabilityError` if False

---

## 5. PostgreSQL Adapter — OpenClaw

**Implementation:** `src/core/store_postgres.py`

### 5.1 pgvector extension

`pgvector` provides a native `vector` type, IVFFlat and HNSW indexes in PostgreSQL.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embeddings (
    id          BIGSERIAL   PRIMARY KEY,
    doc_id      TEXT        NOT NULL,
    chunk_idx   INTEGER     NOT NULL,
    chat_id     INTEGER     NOT NULL,
    chunk_text  TEXT        NOT NULL,
    embedding   vector(384),
    metadata    JSONB,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- HNSW index — fast approximate nearest-neighbour (cosine)
CREATE INDEX ON embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- For multimodal (CLIP embeddings dim=768 or 1024):
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS embedding_mm vector(768);
```

Search:

```sql
SELECT doc_id, chunk_text,
       1 - (embedding <=> $1::vector) AS score
FROM   embeddings
WHERE  chat_id = $2
ORDER  BY embedding <=> $1::vector
LIMIT  $3;
```

### 5.2 Python library: `psycopg3` + `pgvector`

```bash
pip install "psycopg[binary,pool]" pgvector
```

```python
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=10)
with pool.connection() as conn:
    register_vector(conn)
    conn.execute("SELECT ...")
```

FastAPI routes use `psycopg3` async pool — same `store` singleton, async variant.

### 5.3 Multimodal on OpenClaw

OpenClaw has the compute to run multimodal embedding models (CLIP, LLaVA, Florence-2).

| Data | Embedding model | Dim | DB column |
|---|---|---|---|
| Text (notes, chat, docs) | `all-MiniLM-L6-v2` | 384 | `embedding vector(384)` |
| Images | `CLIP ViT-B/32` or `Florence-2` | 512–768 | `embedding_mm vector(768)` |
| Audio (STT transcript + metadata) | text embedding of transcript | 384 | standard `embedding` |
| Mixed documents | CLIP text+image encoder | 512 | `embedding_mm` |

---

## 6. File Storage Layer (all variants)

Binary files are always on disk. The DB stores only the relative path.

```
~/.taris/files/           (PicoClaw / ZeroClaw)
/data/taris/files/        (OpenClaw — can be NVMe or S3 mount)

  audio/
    <chat_id>/
      <uuid>.ogg             ← downloaded voice messages, TTS older than session
  images/
    <chat_id>/
      <uuid>.jpg             ← error protocol photos, document scans
  docs/
    <chat_id>/
      <uuid>.pdf             ← uploaded PDFs, DOCX, TXT originals
  tts_cache/
      <text_hash_hex>.ogg    ← optional TTS result cache (keyed by text hash)
```

The DB record stores `file_path = "docs/<chat_id>/<uuid>.pdf"` relative to `STORE_FILES_ROOT`.

---

## 7. Configuration

In `~/.taris/bot.env`:

```bash
# ── Storage backend ───────────────────────────────────────────────────
# sqlite (default for PicoClaw/ZeroClaw) | postgres (OpenClaw)
STORE_BACKEND=sqlite

# SQLite settings (STORE_BACKEND=sqlite)
STORE_DB_PATH=~/.taris/taris.db

# PostgreSQL settings (STORE_BACKEND=postgres)
STORE_PG_DSN=postgresql://taris:secret@localhost:5432/taris

# File storage root
STORE_FILES_ROOT=~/.taris/files

# Vector search: on | off
# Set off on ZeroClaw if sqlite-vec wheel not installed
STORE_VECTORS=on

# Per-user chat history window (messages retained in DB)
STORE_HISTORY_WINDOW=15

# Credential encryption key (Fernet base64 — generate once and keep in bot.env)
# python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
STORE_CRED_KEY=<generated_key>
```

### 7.1 Platform default presets

| Configuration | STORE_BACKEND | STORE_VECTORS | STORE_HISTORY_WINDOW |
|---|---|---|---|
| ZeroClaw (512 MB) | `sqlite` | `off` (or `on` if sqlite-vec fits) | `10` |
| PicoClaw (Pi 3 B+, 1 GB) | `sqlite` | `on` | `15` |
| OpenClaw (Pi 5 / RK3588 / Jetson) | `postgres` | `on` | `50` |

---

## 8. Migration Path

This plan extends the existing §9 plan. Phase 1 is already complete.

| Phase | Description | Status |
|---|---|---|
| **Phase 1** | `bot_db.py` schema + `init_db()` at startup | ✅ Done (v2026.3.30) |
| **Phase 2a** | `store_base.py` (Protocol) + `store.py` (factory singleton) | 🔲 |
| **Phase 2b** | `store_sqlite.py` — full SQLite adapter, all methods, no vector yet | 🔲 |
| **Phase 2c** | Dual-write wrappers: existing JSON functions write via adapter too | 🔲 |
| **Phase 2d** | Add `documents` + `vec_embeddings` tables to `bot_db.py` schema; `upsert_embedding` / `search_similar` in adapter | 🔲 |
| **Phase 3** | `migrate_to_db.py` — import all JSON → adapter (idempotent) | 🔲 |
| **Phase 4** | Reads switch to adapter; JSON file writes removed | 🔲 |
| **Phase 5** | `store_postgres.py` — PostgreSQL adapter; test on OpenClaw | 🔲 |
| **Phase 6** | Wire RAG (§4.1) into `search_similar()`; wire conversation memory (§2.1) into `append_history()` | 🔲 |
| **Phase 7** | Multimodal embeddings on OpenClaw (CLIP images, audio transcript + metadata) | 🔲 |

---

## 9. New Source Files

| File | Purpose |
|---|---|
| `src/core/store_base.py` | `DataStore` Protocol + `StoreCapabilityError` |
| `src/core/store.py` | Factory function `create_store()` + module-level `store` singleton |
| `src/core/store_sqlite.py` | Full SQLite adapter: all protocol methods + sqlite-vec optional |
| `src/core/store_postgres.py` | PostgreSQL adapter via psycopg3 + pgvector (OpenClaw) |
| `src/setup/install_sqlite_vec.sh` | Install `sqlite-vec` Python wheel on Pi target |
| `src/setup/install_postgres.sh` | Install PostgreSQL + pgvector on OpenClaw target |
| `src/setup/migrate_to_db.py` | JSON → adapter (Phase 3, idempotent) |
| `src/setup/migrate_sqlite_to_pg.py` | SQLite `taris.db` → PostgreSQL (Phase 5) |

---

## 10. Schema additions to `bot_db.py` (Phase 2d)

Add to existing `_SCHEMA_SQL` in `src/core/bot_db.py`:

```sql
-- Documents / Knowledge Base metadata
CREATE TABLE IF NOT EXISTS documents (
    doc_id      TEXT    PRIMARY KEY,
    chat_id     INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    file_path   TEXT,
    doc_type    TEXT,
    is_shared   INTEGER DEFAULT 0,
    metadata    TEXT,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_docs_chat ON documents(chat_id);

-- sqlite-vec virtual table for RAG embeddings
-- Created only when STORE_VECTORS=on AND sqlite-vec is loaded
-- (created dynamically in store_sqlite.py, not in init_db())
-- CREATE VIRTUAL TABLE IF NOT EXISTS vec_embeddings USING vec0(
--     doc_id TEXT, chunk_idx INTEGER, chat_id INTEGER,
--     chunk_text TEXT, embedding FLOAT[384]
-- );
```

> `vec_embeddings` is created dynamically by `SQLiteStore.__init__()` after loading the sqlite-vec extension, so it is not in `init_db()` which may run before the extension is available.

---

## 11. Test Plan

| ID | Test | What it validates |
|---|---|---|
| T22 | `sqlite_schema` | All 10 tables present in `taris.db`; column names match spec |
| T23 | `migration_idempotent` | `migrate_to_db.py` run twice produces same row counts |
| T24 | `vector_search_basic` | `upsert_embedding` + `search_similar` returns expected top-1 match (SQLite) |
| T25 | `store_adapter_contract` | Both SQLiteStore and PostgresStore pass the same contract test suite |
| T26 | `credential_encryption` | Stored mail password is not plaintext in DB; decrypts correctly |

---

## 12. Dependency additions

```
# requirements.txt — delta for storage features
sqlite-vec>=0.1.1          # PicoClaw/ZeroClaw vector support (optional but recommended)
cryptography>=42.0.0       # Fernet encryption for stored credentials

# OpenClaw only (STORE_BACKEND=postgres)
psycopg[binary,pool]>=3.2.0
pgvector>=0.3.0
```

---
→ [Back to TODO.md §9 — Storage Architecture](../../TODO.md)
