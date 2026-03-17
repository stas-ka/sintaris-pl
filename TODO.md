# Pico Bot — TODO & Roadmap

**Legend:** ✅ Done · 🔄 In progress · 🔲 Planned · 💡 Idea / future

---

## 0. Known bugs

### Bugs — Fixed in this Sprint ✅

| Bug | Fix | Version |
|---|---|---|
| 0.1 Profile menu silent crash | `try/except` guard around deferred import in `_handle_profile()` | v2026.3.29 |
| 0.2 Hardcoded bot name | `BOT_NAME` constant + `{bot_name}` in `strings.json` | v2026.3.29 |
| 0.3 Note edit loses content | Append / Replace mode buttons in note edit flow | v2026.3.29 |
| 0.4 Calendar voice deleted | Fixed orphan TTS cleanup guard — only deletes spinner messages | v2026.3.29 |
| 0.5 Calendar console ignores add | Intent classifier calls `_finish_cal_add()` directly | v2026.3.29 |
| 0.6 System Chat no role guards | `ADMIN_ALLOWED_CMDS` / `DEVELOPER_ALLOWED_CMDS` + `_classify_cmd_class()` | v2026.3.30 |
| 0.7 Add new Contact cancel shows "btn_cancel" | Added missing `btn_cancel` i18n key to ru/en/de in `strings.json` | v2026.3.31 |
| 0.8 Profile change password error | Fixed `account["id"]` → `account["user_id"]` key in `_finish_profile_change_pw()` | v2026.3.31 || 0.9 | Telegram-Web link code HTTP 500 on `/register` | Codes persisted to `~/.picoclaw/web_link_codes.json`; shared between Telegram and Web services | v2026.3.33 |
---

## 1. Open Issues &amp; Roadmap

### 1.0 Profile Redesign ✅ Implemented (v2026.3.31)
Profile self-service hub — edit name, change password, open mailbox — in both Telegram and Web UI.

- [x] Crash guard: `try/except` in `_handle_profile()` around deferred import (Telegram) (v2026.3.29)
- [x] Profile inline keyboard: Edit name / Change password / Open mailbox / Web link (v2026.3.29)
- [x] `GET /profile` + `POST /profile/name` routes in `bot_web.py` (v2026.3.29)
- [x] `profile.html` template + `base.html` nav sidebar link (v2026.3.29)
- [x] Playwright test: `GET /profile` returns 200 — `TestProfile` class in `test_ui.py` (v2026.3.31)
- [] setting language per default for user
- [] view saved information context included about user in the app

---

## 1. Access & Security

### 1.1 Role-Based Access Control (RBAC) �
Per-role command allowlists, System Chat branching, Developer role and menu.
→ [Full spec](doc/todo/1.1-rbac.md) · [Developer menu spec](doc/todo/1.3-developer-role.md)

- [x] `DEVELOPER_USERS` constant + `_is_developer()` helper (v2026.3.30)
- [x] `ADMIN_ALLOWED_CMDS` / `DEVELOPER_ALLOWED_CMDS` allowlists (v2026.3.30)
- [x] Role-aware `_handle_system_message()` with `_classify_cmd_class()` (v2026.3.30)
- [ ] Dev Menu — `_handle_dev_menu()`, Dev Chat, Restart / Log / Error / FileList buttons
- [ ] Regression test — allowlist enforcement

### 1.2 Central Security Layer — MicoGuard 🔲
Role validation on every command/callback, security event logging, configurable access rules, runtime policy updates.

- [ ] Security event logging (`security.log`)
- [ ] Configurable access rules (admin UI + config file); runtime policy updates without restart

---


## 2. Conversation & Memory

### 2.1 Conversation Memory System ✅ Implemented (v2026.3.33)

- [x] Store per-user conversation history (sliding window, default 15 messages)
- [x] Inject last N messages as context into LLM prompt
- [x] Optional: persist across restarts (JSON / SQLite)

---

## 3. LLM Provider Support

### 3.1 Multi-LLM Provider Support ✅ Implemented (v2026.3.32)
OpenRouter ✅ · OpenAI direct ✅ · YandexGPT ✅ · Gemini ✅ · Anthropic ✅ · local llama.cpp ✅

- [x] `LLM_PROVIDER` env-var switch in `bot.env` (`picoclaw` | `openai` | `yandexgpt` | `gemini` | `anthropic` | `local`)
- [x] `_DISPATCH` table + `ask_llm(prompt, timeout)` entry point in `src/core/bot_llm.py`
- [x] OpenAI direct client `_ask_openai()` — `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- [x] YandexGPT client `_ask_yandexgpt()` — `YANDEXGPT_API_KEY`, `YANDEXGPT_FOLDER_ID`, `YANDEXGPT_MODEL_URI`
- [x] Gemini client `_ask_gemini()` — `GEMINI_API_KEY`, `GEMINI_MODEL`
- [x] Anthropic client `_ask_anthropic()` — `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- [x] 14 provider constants added to `src/core/bot_config.py`
- [x] `picoclaw` (default) provider wraps existing OpenRouter CLI — all existing behaviour unchanged

### 3.2 Local LLM — Offline Fallback ✅ Implemented (v2026.3.32)
Emergency fallback via `llama.cpp`. Pi 3: Qwen2-0.5B (~1 tok/s); Pi 4/5: Phi-3-mini.
→ See: `doc/hardware-performance-analysis.md` §8.9

- [x] `picoclaw-llm.service` systemd unit — llama-server on port 8081, `qwen2-0.5b-q4.gguf`, 4 threads, ctx 2048
- [x] `_ask_local()` client — OpenAI-compatible `/v1/chat/completions` against `LLAMA_CPP_URL` (default `http://127.0.0.1:8081`)
- [x] `LLM_LOCAL_FALLBACK=true` env-var — enables automatic fallback when primary provider fails
- [x] `ask_llm()` catches all primary errors; retries via `_ask_local()` when fallback enabled
- [x] Fallback responses prefixed with `⚠️ [local fallback]` label
- [x] Service staged on Pi2; starts automatically once `llama-server` binary is installed

---

## 4. Content & Knowledge

### 4.0 Contact Book ✅ Implemented (v2026.3.30)

---

### 4.1 Local RAG Knowledge Base 🔲

- [ ] Embed documents with `all-MiniLM-L6-v2`
- [ ] Vector similarity search → inject top-k context into LLM prompt
- [ ] Commands: `/rag_on`, `/rag_off`
- [ ] Storage: `~/.picoclaw/knowledge_base/` (documents + `embeddings.db`)
- [ ] configuration to use local knowledges or remote RAG knowledge  service.
- [ ] Using local knowledges is possible to use remote RAG servceis
- [ ] Connect , using to remote service via MCP server connection as tool
- [ ] Timeout monitoring by using RAG services or by waiting for answer from LLM
- [ ] settings for using LLM+RAG configurable (temperature, sead, system prompt, role, chunk counts) via Admin panel
- [ ] settings incl. credentials to connect to remote RAG MCP service via Admin panel
- [ ] settings for configuration of local RAG service via Admin panel
- [ ] information for the user about restrictions for uploadable documents and size of database over telegram and web ui
- [ ] logging in DB information about  founded chunks and prompt by requests to llm (input) and results from llm inclusive returned system information
- [ ] after uploading document shall be saved statistic about source document parsing, chuncking, mebedding as protocol in the database

### 4.2 [ ] optimize local RAG

### 4.2 [ ] Implement remote  RAG service as MCP service
---

## 5. Voice Pipeline

Baseline: Pi 3 B+ ~115 s total; target <25 s with all opts ON.
→ [Baseline measurements & full backlog](doc/todo/5-voice-pipeline.md)

### 5.2 TTS Bottleneck 🔲

- [ ] Add `TTS_VOICE_MAX_CHARS = 300` to `bot_config.py`; use in `_tts_to_ogg()` when `_trim=True`
- [ ] Document `persistent_piper` + `tmpfs_model` as recommended defaults in admin panel

### 5.3 STT/TTS Backlog 🔲

- [ ] Move Whisper temp WAV from `/tmp` to `/dev/shm` (−0.5 s per call)
- [ ] Add `STT_CONF_THRESHOLD` config constant for Vosk confidence strip
- [ ] Progressive delivery for "Read aloud" 1200-char chunks; expose OGG Opus bitrate as voice opt
- [ ] Add timing breakdown to `voice_timing_debug`: ffmpeg OGG→PCM, Piper model load vs inference

---

## 6. Infrastructure & Operations

### 6.1 Logging & Monitoring 🔲
- [ ] create and describe logging and monitoring concept
- [ ] Structured log categories: `assistant.log`, `security.log`, `voice.log`, `datastore.log`
- [ ] Admin Telegram UI: view last N log lines per category
- [ ] Log rotation (`logrotate` config)
- [ ] notification Administrator about critical , fatal error via telegrma and storing protocols on target
- [ ] create skill to download logs 

### 6.2 Host–Project Synchronization 🔲

- [ ] rsync-based sync script `src/` → Pi
- [ ] Git-based deployment hook
- [ ] creaet tools and skill to backup data from target to lcoal host and upload to cloud.dev2null.de

### 6.3 Deployment Workflow Enhancements 🔲

- [ ] `src/setup/notify_maintenance.py` — pre-restart user notification
- [ ] `NOTIFY_USERS_ON_UPDATE` flag in `bot.env` — ping approved users on startup after version bump
- [ ] Feature flags pattern in `bot.env` for gradual rollout

### 6.4 Hardware Upgrades 💡

- [ ] Pi 4 B upgrade — drops total latency ~115 s → ~15 s
- [ ] Pi 5 + NVMe upgrade — ~8 s total; full local LLM viable
- [ ] USB SSD — eliminates Piper model cold-start (15 s → 2 s), zero code changes

### 6.5 Recovery Testing 🔲

- [ ] Test full recovery on a different hardware device — flash image backup, restore all services, verify bot + voice + calendar come up cleanly on fresh Pi

---

## 7. Demo Features for Client Presentations 🔲

Quick-win features — Level A (LLM-only, <2 h), B (helpers, 2–4 h), C (impressive, 4–8 h).
→ [Full list with implementation notes](doc/todo/7-demo-features.md)

**Minimum demo set (1 day):** A1 Weather + A2 Translator + B2 System Status + B3 Timer + C3 QR Code

---

## 8. Web UI & CRM Platform

### 8.4 CRM Platform Vision 💡

Contacts → Deals → Custom fields → White-label. Core platform C0 done (v2026.3.28).
→ [CRM roadmap & phases](doc/todo/8.4-crm-platform.md)

### 8.5 Not planed : NiceGUI Integration 💡

Replace Jinja2 with NiceGUI for richer interactivity — evaluate RAM footprint on Pi 3 first.

- [ ] Evaluate NiceGUI RAM footprint (~60 MB vs FastAPI ~25 MB); prototype Voice Opts page
- [ ] If viable: migrate pages incrementally behind feature flag

---

## 9. Flexible Storage Architecture 🔲

Multi-backend storage with adapter pattern:  
**PicoClaw / ZeroClaw** → SQLite + `sqlite-vec` (vector search, local RAG) · **OpenClaw** → PostgreSQL + pgvector.  
Config-driven switch: `STORE_BACKEND=sqlite|postgres` in `bot.env`. Binary files always on disk.

→ **[Storage Architecture Proposal](doc/todo/storage-architecture.md)** ← full design, adapter interface, DDL, migration  
→ [Original SQLite schema & Phase 1 spec](doc/todo/9-sqlite-data-layer.md) (Phase 1 done, superseded for scope by the proposal above)

| Phase | Description | Status |
|---|---|---|
| Phase 1 | `bot_db.py` schema + `init_db()` at startup | ✅ Done (v2026.3.30) |
| Phase 2a | `store_base.py` Protocol + `store.py` factory singleton | ✅ Done (v2026.3.32) |
| Phase 2b | `store_sqlite.py` full adapter (no vector yet) | ✅ Done (v2026.3.32) |
| Phase 2c | Dual-write wrappers: existing JSON writers also call adapter | ✅ Done (v2026.3.32) |
| Phase 2d | `documents` + `vec_embeddings` tables; `upsert_embedding` / `search_similar` | 🔲 |
| Phase 3 | `migrate_to_db.py` — JSON → adapter (idempotent) | ✅ |
| Phase 4 | Switch all reads to adapter; remove JSON writes | 🔲 |
| Phase 5 | `store_postgres.py` PostgreSQL adapter; test on OpenClaw | 🔲 |
| Phase 6 | RAG (§4.1) via `search_similar()`; conversation memory (§2.1) via `append_history()` | 🔲 |

- [x] `src/core/bot_db.py` schema + `init_db()` on startup — SQLite Phase 1 (v2026.3.30)
- [x] `src/core/store_base.py` — `DataStore` Protocol definition + `StoreCapabilityError`
- [x] `src/core/store.py` — `create_store()` factory + module-level `store` singleton
- [x] `src/core/store_sqlite.py` — full SQLite adapter incl. sqlite-vec optional vector support
- [ ] `src/core/store_postgres.py` — PostgreSQL + pgvector adapter (OpenClaw)
- [ ] `src/core/bot_db.py` extended — add `documents` table; vec_embeddings created dynamically
- [ ] `src/setup/install_sqlite_vec.sh` — install sqlite-vec wheel on Pi target
- [x] `src/setup/migrate_to_db.py` — JSON → adapter migration (Phase 3, idempotent)
- [ ] `src/setup/migrate_sqlite_to_pg.py` — pico.db → PostgreSQL (Phase 5)
- [ ] Tests T22 `sqlite_schema`, T23 `migration_idempotent`, T24 `vector_search_basic`, T25 `store_adapter_contract`, T26 `credential_encryption`

## 10. Upload and using documents as Knowlegdes
- Function to upload and administration documents (upload, view,  delete , share to all , set title, set hash/label, share to other users in system)
- Using documents as knowledgebase in chat in multimodal RAG way
- documents can be contain text, images, tables
- documents used as knowledegs shall assigned to user or can be shared to use from all users as knowledges
- documents can be replaced through other document if documents are identical by hash, name, size parameters and after confirmation from user to replace already stored document with new. User shall see name and descrition already existed document
- criteria of compAring of documnts shall be configurable in Admin panel
- quality consistency check created chunks after uploading of document

### 10.1 Short-, middle and Long-term memories 
Before implementaion of memories shall be analyse how can be implemented . here is first draft, proposal for implelemnation:
- implement short-term, middle-term, long-term memories 
- conversations after reaching maximal short memory size of conversation shall be set as middle-term memory 
- middle-term memory after reaching a size shall be cleaned and summariazed/compacted and meregd together with long-term memory
- cleaning all kind of memories if user its wishes in profile 
- setting all memories parameters in Admin panel
- all kind of memories can be used as context in conversations with user per default or user can switch off using memories in conversations

## 11. Central control dashboard (primary per voice)
- IMplementing central dashboard to contorol and run all activities of the asstsiant
- all functions can be runned and controled from this board. Steering can be do per voice or per text input.
- ui shall be switchable  per voice to functional ui part to run activities

## 12. Input all textes in all application parts per voice in one window
- all inputs of textes shall be possible per voice exceptional confirmation of runnig activities

## 13. Implementing smart CRM 
- Implementing open fuctions if they are not already implemented from concept\additional\crm_system_requirements.md and concept\additional\SYSTEM_REQUIREMENTS_SmartClient360.md
- all inputs and switching between  all windows shall be controlable per voice. Smart client. 
- smart input of text and automatical set values in the input fields 


## 14. Developer Board
- Impelementing developer board to extend , update, remove functionality of applciation based on agent principe


## 15. Connecting Calendar, E-Mails, Drives from Google and Yandex


## 16 Implementing functions of personal assistant
- - Implementing open fuctions if they are not already implemented from concept\additional\KIM_PACKAGES.md

## 17. Implementing  Max messenger UI analog Telegram

## 18. Using ZeroClaw instead PicoClaw
→ [Hardware Requirements Report §4.2](doc/hw-requirements-report.md) — ZeroClaw feasibility analysis (text-only; voice not viable on 512 MB)

## 19. Using OpenClaw instead PicoClaw
→ [Hardware Requirements Report §4.3 + §6](doc/hw-requirements-report.md) — OpenClaw configurations (Pi 5, RK3588, Jetson); full local AI stack