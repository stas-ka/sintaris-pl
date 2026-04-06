# Taris — Data Layer

**Version:** `2026.4.31`  
→ Architecture index: [architecture.md](../architecture.md)

---

## When to read this file
Changing data storage, adding a new table column, switching SQLite↔Postgres, modifying RAG indexing, or touching anything in `core/store*.py`, `core/bot_db.py`, `security/bot_auth.py`, or `core/bot_state.py`.

---

## Architecture — 3 Layers

| Layer | Module | What it stores | Variant |
|---|---|---|---|
| **Layer 1** | `core/store.py` singleton | Users, notes, calendar, history, contacts, documents, vectors, RAG, voice_opts, mail_creds, **web_accounts**, **link_codes**, **reset_tokens** | Both (SQLite or Postgres) |
| **Layer 2** | `core/bot_db.py` wrappers | llm_calls, tts_pending, conversation_summaries, user_prefs, security_events — delegated to Layer 1 when `STORE_BACKEND=postgres` | Both |
| **Layer 3** | File system | `system_settings.json`, `web_secret.key`, `bot.env`, note `.md` files | Both |

**Rule:** All caller code imports only `from core.store import store` (Layer 1) or calls `bot_db.*` helpers (Layer 2). Never import `store_sqlite` or `store_postgres` directly.

---

## Backend Selection

| `STORE_BACKEND` | Backend | Variant |
|---|---|---|
| `sqlite` (default) | `core/store_sqlite.py` + FTS5 | PicoClaw (Pi), lightweight |
| `postgres` | `core/store_postgres.py` + pgvector | OpenClaw (TariStation) |

**Change:** Set `STORE_BACKEND=postgres` + `DATABASE_URL=postgresql://...` in `~/.taris/bot.env`. Restart service.

---

## Protocol interface (`store_base.py`)

All backends implement the `DataStore` Protocol. New methods must be added to `store_base.py` first, then implemented in both `store_postgres.py` and `store_sqlite.py`.

| Method group | Methods | Used by |
|---|---|---|
| Documents / RAG | `index_document`, `search_fts`, `get_document_by_hash`, `update_document_field` | `bot_documents.py`, `bot_llm.py` |
| Conversation | `add_chat_history`, `load_chat_history`, `clear_chat_history`, `append_history_tracked`, `list_active_chat_ids` | `bot_state.py` |
| Summaries | `save_summary`, `count_summaries`, `get_summaries_oldest`, `delete_summaries`, `get_all_summaries` | `bot_state.py` |
| LLM trace | `log_llm_call`, `get_llm_trace` | `bot_db.py` → `bot_llm.py` |
| TTS pending | `set_tts_pending`, `get_tts_pending`, `clear_tts_pending` | `bot_db.py` → `bot_voice.py` |
| User prefs | `get_user_pref`, `set_user_pref` | `bot_db.py` wrappers |
| Security | `log_security_event`, `list_security_events` | `bot_dev.py` |
| Notes | `save_note`, `load_note`, `list_notes`, `delete_note` | `bot_notes.py` |
| Contacts | `save_contact`, `list_contacts`, `delete_contact` | `bot_contacts.py` |
| Mail creds | `save_mail_creds`, `get_mail_creds`, `delete_mail_creds` | `bot_mail_creds.py`, `bot_web.py` |
| **Web accounts** | `upsert_web_account`, `find_web_account`, `update_web_account`, `list_web_accounts` | `security/bot_auth.py` |
| **Reset tokens** | `save_reset_token`, `find_reset_token`, `mark_reset_token_used`, `delete_reset_tokens_for_user` | `security/bot_auth.py` |
| **Link codes** | `save_link_code`, `find_link_code`, `delete_link_code`, `delete_expired_link_codes` | `core/bot_state.py` |

---

## SQLite schema (`core/bot_db.py` `_SCHEMA_SQL`)

| Table | Purpose | Key columns |
|---|---|---|
| `documents` | RAG doc registry | `doc_id, chat_id, filename, doc_hash, char_count, n_chunks, file_size_bytes, shared, metadata` |
| `document_chunks` | Chunk text storage | `chunk_id, doc_id, chunk_text, chunk_index` |
| `fts_documents` | FTS5 virtual table (BM25) | auto-indexed from `document_chunks` |
| `chat_history` | Conversation turns | `chat_id, role, content, created_at` |
| `conversation_summaries` | Tiered memory | `chat_id, tier (mid/long), summary, msg_count, created_at` |
| `notes_index` | Note metadata + content | `slug, chat_id, title, content, updated_at` |
| `contacts` | Contact book | `chat_id, name, phone, email` |
| `rag_log` | RAG retrieval audit | `chat_id, query, query_type, n_chunks, chars_injected, latency_ms, created_at` |
| `user_prefs` | Per-user settings | `chat_id, key, value` |
| `security_events` | Security audit log | `chat_id, event_type, detail, created_at` |
| `llm_calls` | LLM call trace | `chat_id, model, prompt_chars, response_chars, latency_ms, rag_chunks, context_snapshot` |
| `voice_opts` | Per-user TTS/STT flags | `chat_id, silence_strip, ...` |
| `global_voice_opts` | Bot-wide voice flags | `key, value` |
| **`web_accounts`** | Web UI accounts (DB-backed since v2026.4.30) | `user_id PK, username UNIQUE, display_name, pw_hash, role, status, telegram_chat_id, created, is_approved` |
| **`web_reset_tokens`** | Password reset tokens | `token PK, username, expires, used` |
| **`web_link_codes`** | Telegram↔Web link codes | `code PK, chat_id, expires_at` |

**Add a new column:** Add `ALTER TABLE ... ADD COLUMN ...` in `_SCHEMA_SQL` (wrapped in try/except) and also add `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` to `_MIGRATIONS` in `store_postgres.py`.

---

## File system (Layer 3 — minimal set)

| File | Description |
|---|---|
| `~/.taris/taris.db` | SQLite DB (all tables above) |
| `~/.taris/system_settings.json` | Admin-configured globals (not in DB) |
| `~/.taris/web_secret.key` | JWT signing secret |
| `~/.taris/notes/<chat_id_or_uuid>/<slug>.md` | Note content (Markdown body) |
| `~/.taris/voice_opts.json` | Per-user voice flags (cached in memory) |
| `~/.taris/bot.env` | All secrets + `STORE_BACKEND` + `DATABASE_URL` |
| ~~`~/.taris/accounts.json`~~ | ⚠️ Migrated to `web_accounts` table. File kept as backup. |
| ~~`~/.taris/reset_tokens.json`~~ | ⚠️ Migrated to `web_reset_tokens` table. |
| ~~`~/.taris/web_link_codes.json`~~ | ⚠️ Migrated to `web_link_codes` table. |

---

## Migration path (accounts.json → DB)

`ensure_admin_account()` in `security/bot_auth.py`:
1. Calls `store.list_web_accounts()`.
2. If empty AND `accounts.json` exists → imports all accounts via `store.upsert_web_account()`.
3. If still empty → creates default `admin/admin` account in DB.

This runs once on first startup after upgrade to v2026.4.30.

---

## bot_db.py wrappers (Layer 2 → Postgres delegation)

`bot_db.py` provides convenience helpers for modules that don't import `store` directly.  
When `STORE_BACKEND=postgres` (`_is_postgres()=True`), all wrappers call `_get_store()` lazily.  
`system_settings` always use `~/.taris/system_settings.json` (not DB).

| Helper | Delegates to |
|---|---|
| `db_get_system_setting`, `db_set_system_setting` | `SYSTEM_SETTINGS_PATH` JSON file |
| `db_add_history`, `db_get_history`, `db_clear_history` | `store.append_history_tracked`, etc. |
| `db_log_llm_call`, `db_get_llm_trace` | `store.log_llm_call`, `store.get_llm_trace` |
| `db_get_user_pref`, `db_set_user_pref` | `store.get_user_pref`, `store.set_user_pref` |

**Circular import guard:** `_get_store()` does `from core.store import store` at call time (not module load), because `store_sqlite.py` imports `get_db()` from `bot_db.py`.

---

## Config constants (`bot_config.py`)

| Constant | Default | Description |
|---|---|---|
| `STORE_BACKEND` | `"sqlite"` | `sqlite` or `postgres` |
| `DATABASE_URL` | `""` | Postgres connection string |
| `RAG_ENABLED` | `true` | Master RAG on/off |
| `RAG_TOP_K` | `3` | Chunks per LLM call |
| `RAG_CHUNK_SIZE` | `512` | Chars per chunk at indexing |
| `CONV_SUMMARY_THRESHOLD` | `15` | Messages → trigger mid-tier summary |
| `CONV_MID_MAX` | `5` | Mid summaries → trigger long-tier compaction |

Runtime overrides: `core/rag_settings.py` reads `~/.taris/rag_settings.json`.

---

## PostgreSQL extras (OpenClaw only)

- `pgvector` extension required: `CREATE EXTENSION IF NOT EXISTS vector;`
- Embedding model: `all-MiniLM-L6-v2` (384-dim), loaded by `core/bot_embeddings.py`
- Hybrid search: BM25 + cosine similarity combined
- Install: see `src/setup/setup_llm_openclaw.sh`
- **Schema note**: Postgres uses `vec_embeddings` for both chunk text and embeddings. No separate FTS5 table.
- **Shared docs**: `list_documents`, `search_fts`, `search_similar` include `OR is_shared = 1` for system docs.

---

## ✅ Completed migrations (v2026.4.31)

| What | Script / method |
|---|---|
| SQLite → Postgres (all tables, 316 rows) | `src/setup/migrate_sqlite_to_postgres.py` (idempotent) |
| `accounts.json` → `web_accounts` table | `security/bot_auth.py` `ensure_admin_account()` auto-migrates on startup |
| `mail_creds/*.json` → `mail_creds` table | `features/bot_mail_creds.py` `_load_creds()` — store-primary, file fallback |
| `web_link_codes.json` → `web_link_codes` table | `core/bot_state.py` `generate_web_link_code()` |
| `notes/*.md` (SQLite index) → Postgres notes | `src/setup/migrate_sqlite_to_postgres.py` |

**OpenClaw rule:** `STORE_BACKEND=postgres` → SQLite is NEVER created or written. `init_db()` guarded by `_postgres_mode()`.

---

## ⏳ Open items

| Item | TODO ref |
|---|---|
| Calendar events: migrate from JSON files to DB table | [TODO.md §9](../TODO.md#9-flexible-storage-architecture-) |
