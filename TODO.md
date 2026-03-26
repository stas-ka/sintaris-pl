# Taris Bot — TODO & Roadmap

**Legend:** ✅ Done · 🔄 In progress · 🔲 Planned · 💡 Idea / future

---

## 0. Known bugs
- [] System chat error . Not enough admin rights to run commands. LOg from Telegram:
[18.03.2026 20:05] SU: how much space i have on flash
[18.03.2026 20:05] Smart PicoClaw Bot: ❌ Could not generate a command. Try again.
[20.03.2026 06:28] Smart PicoClaw Bot: 📄 taris
- [] PI2 missing Piper ONNX models (`ru_RU-irina-medium.onnx`, `.onnx.json`) — T01 `model_files_required` FAIL
- [] PI1 missing `migrate_to_db.py` at expected path — T23 `db_migration_idempotent` FAIL
- [] PI1 `taris-web.service` not running
- [] German voice models absent on both PIs (`de_DE-thorsten-medium.onnx`, `vosk-model-small-de`)
- [] PI2 has no Whisper model (`ggml-base.bin`) — Whisper tests SKIP
- [] Vosk WER regression on short audio (`audio_2026-03-08_08-34-23.ogg`) — WER 0.70 vs threshold 0.35
- [] Static textes for UI defined partialy in the python . For example bot_calendar.py contains strings in english or urssian languages. It is not allowed to define string directly in the python. strings.json shall be used overall. Fix it in all python scripts and move textes in the strings.json



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
| 0.8 Profile change password error | Fixed `account["id"]` → `account["user_id"]` key in `_finish_profile_change_pw()` | v2026.3.31 |
| 0.9 Telegram-Web link code HTTP 500 on `/register` | Codes persisted to `~/.taris/web_link_codes.json`; shared between Telegram and Web services | v2026.3.33 |
| 0.10 OpenAI model selection ignored active model | Fixed default `OPENAI_MODEL` + model catalog align in `bot_config.py` / `bot_llm.py`; admin model switch now reflected correctly | v2026.3.40 |
| 0.11 System Chat bypassed multi-LLM dispatch | `_handle_system_message()` now calls `ask_llm()` (bot_llm.py) instead of legacy `_ask_taris()` | v2026.3.41 |
---

## 1. Open Issues &amp; Roadmap

### 1.0 Profile Redesign ✅ Implemented (v2026.3.31)
Profile self-service hub — edit name, change password, open mailbox — in both Telegram and Web UI.

- [x] Crash guard: `try/except` in `_handle_profile()` around deferred import (Telegram) (v2026.3.29)
- [x] Profile inline keyboard: Edit name / Change password / Open mailbox / Web link (v2026.3.29)
- [x] `GET /profile` + `POST /profile/name` routes in `bot_web.py` (v2026.3.29)
- [x] `profile.html` template + `base.html` nav sidebar link (v2026.3.29)
- [x] Playwright test: `GET /profile` returns 200 — `TestProfile` class in `test_ui.py` (v2026.3.31)
- [x] Language selection in Profile: `_handle_profile_lang()` + `_set_profile_lang()` + `_set_reg_lang()` — persisted per user (v2026.3.31)
- [x] View stored data summary in Profile: `_handle_profile_my_data()` — notes, calendar, contacts, mail status (v2026.3.31)

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
### 1.3 Contact Book ✅ Implemented (v2026.3.30)
[] Add additional fields for contact
---


## 2. Conversation & Memory

### 2.1 Conversation Memory System ✅ Implemented (v2026.3.33)

- [x] Store per-user conversation history (sliding window, default 15 messages)
- [x] Inject last N messages as context into LLM prompt
- [x] Optional: persist across restarts (JSON / SQLite)
- [] Delete personly context (memory) for User via Profile menu after confirmation


---

## 3. LLM Provider Support
→ Document management and knowledge base features: see **§10** (Upload and Knowledge Documents).

### 3.1 Multi-LLM Provider Support ✅ Implemented (v2026.3.32)
OpenRouter ✅ · OpenAI direct ✅ · YandexGPT ✅ · Gemini ✅ · Anthropic ✅ · local llama.cpp ✅

- [x] `LLM_PROVIDER` env-var switch in `bot.env` (`taris` | `openai` | `yandexgpt` | `gemini` | `anthropic` | `local`)
- [x] `_DISPATCH` table + `ask_llm(prompt, timeout)` entry point in `src/core/bot_llm.py`
- [x] OpenAI direct client `_ask_openai()` — `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- [x] YandexGPT client `_ask_yandexgpt()` — `YANDEXGPT_API_KEY`, `YANDEXGPT_FOLDER_ID`, `YANDEXGPT_MODEL_URI`
- [x] Gemini client `_ask_gemini()` — `GEMINI_API_KEY`, `GEMINI_MODEL`
- [x] Anthropic client `_ask_anthropic()` — `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- [x] 14 provider constants added to `src/core/bot_config.py`
- [x] `taris` (default) provider wraps existing OpenRouter CLI — all existing behaviour unchanged

Emergency fallback via `llama.cpp`. Pi 3: Qwen2-0.5B (~1 tok/s); Pi 4/5: Phi-3-mini.
→ See: `doc/hardware-performance-analysis.md` §8.9
- [x] `taris-llm.service` systemd unit — llama-server on port 8081, `qwen2-0.5b-q4.gguf`, 4 threads, ctx 2048
- [x] `_ask_local()` client — OpenAI-compatible `/v1/chat/completions` against `LLAMA_CPP_URL` (default `http://127.0.0.1:8081`)
- [x] `LLM_LOCAL_FALLBACK=true` env-var — enables automatic fallback when primary provider fails
- [x] `ask_llm()` catches all primary errors; retries via `_ask_local()` when fallback enabled
- [x] Fallback responses prefixed with `⚠️ [local fallback]` label
- [x] Service staged on Pi2; starts automatically once `llama-server` binary is installed
- [x] Configurable, switchable via Admin Panel
---

## 4. Content & Knowledge
- [ ] Timeout monitoring by using RAG services or by waiting for answer from LLM
- [ ] settings for using LLM+RAG configurable (temperature, sead, system prompt, role, chunk counts) via Admin panel
- [ ] settings incl. credentials to connect to remote RAG MCP service via Admin panel
- [ ] information for the user about restrictions for uploadable documents and size of database over telegram and web ui
- [ ] logging in DB information about  founded chunks and prompt by requests to llm (input) and results from llm inclusive returned system information . Access via Admin panel to last RAG activities(log outpus)
- [ ] after uploading document shall be saved statistic about source document parsing, chuncking, embedding as protocol in the database . Output statistic for Admin by loading documents 


---

### 4.1 Local RAG Knowledge Base ✅ FTS5 pipeline implemented (v2026.4.13); vector + settings UI pending
→ Implementation steps: **§24.6** (PicoClaw — FTS5-only) · **§25.6 Phases A–B** (OpenClaw — Hybrid Tiered RAG)
→ Architecture: [concept/rag-memory-architecture.md](concept/rag-memory-architecture.md) (Variant C — Hybrid Tiered RAG, score 4.45)

- [x] RAG on/off toggle in Admin Panel via `RAG_FLAG_FILE` (`~/.taris/rag_disabled`); `RAG_ENABLED`, `RAG_TOP_K`, `RAG_CHUNK_SIZE` env-var constants in `bot_config.py`; admin callbacks `admin_rag_menu` / `admin_rag_toggle` / `admin_rag_log` wired (v2026.4.13)
- [ ] Configurable RAG settings from Admin Panel UI (top-K, chunk size, temperature editable at runtime — currently env-var only)
- [x] Local LLM for RAG: `LLM_PROVIDER=local` via llama.cpp — implemented in §3.1 (v2026.3.32)
- [x] FTS5-only RAG pipeline: document upload → `_chunk_text()` (512-char) → `doc_chunks` FTS5 virtual table → `search_fts()` → LLM prompt injection in `bot_handlers.py` (v2026.4.13)
- [x] `install_sqlite_vec.sh` setup script + `vec_embeddings` table (sqlite-vec `vec0`, 384-dim) + `upsert_embedding()` / `search_similar()` / `delete_embeddings()` adapter methods ready in `store_sqlite.py` — schema and plumbing in place (v2026.4.13)
- [ ] `all-MiniLM-L6-v2` embeddings via ONNX Runtime: no `EMBED_MODEL` constant, no embedding generation code wired yet; Pi 5/Server only; graceful FTS5-only fallback on Pi 3
- [ ] pgvector HNSW (OpenClaw/VPS) — §25.6 scope
- [ ] Timeout monitoring for RAG / LLM calls; configurable `MCP_TIMEOUT` per provider
- [x] RAG activity log in DB (`rag_log` table + index) + Admin Panel: view last 20 queries + chunks injected (v2026.4.13)

### 4.2 Remote RAG Service (MCP) 🔲
→ Implementation: **§25.6 Phase D** (OpenClaw) and **§26.5** (VPS)

- [ ] Expose `search_knowledge()` as local MCP tool server
- [ ] Connect to external MCP RAG services via `MCP_REMOTE_URL` config in `bot.env`
- [ ] Circuit breaker + timeout (default 10 s) with fallback to local knowledge base
- [ ] Credentials and endpoint URL configurable in Admin Panel
---

## 5. Voice Pipeline

Baseline: Pi 3 B+ ~115 s total; target <25 s with all opts ON.
→ [Baseline measurements & full backlog](doc/todo/5-voice-pipeline.md)

### 5.1 Whisper vs Vosk Decision ✅ Resolved (2026-03-21)

Full regression test run on both PIs. **Vosk wins decisively** on Raspberry Pi hardware.
→ [Test Protocol](doc/test-protocol-2026-03-21.md)

| Metric | Vosk (PI1) | Whisper (PI1) |
|---|---|---|
| Avg latency | 4–14 s | 25–45 s |
| WER (best) | 0.00 | 0.57 |
| Hallucination | None | Severe on short audio |

**Decision:** Keep Vosk as default STT. Whisper `whisper_stt` voice opt remains available but not recommended on Pi 3.
- [x] Fix test_voice_regression.py Whisper model path (ggml-tiny → ggml-base)
- [x] Run full regression on both PIs
- [x] Create test protocol (`doc/test-protocol-2026-03-21.md`)

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

### 6.1 Logging & Monitoring ✅ Implemented (v2026.3.42)
- [x] Structured log categories: `assistant.log`, `security.log`, `voice.log`, `datastore.log` (`src/core/bot_logger.py`)
- [x] Admin Telegram UI: 📊 Logs button — tail last 50 lines per category
- [x] Log rotation (`src/services/taris-logrotate`) — daily, 7 days, compress, copytruncate
- [x] Telegram alert handler: CRITICAL/ERROR forwarded to admins on startup
- [ ] create skill to download logs from target

### 6.2 Host–Project Synchronization 🔲

- [ ] rsync-based sync script `src/` → Pi
- [ ] Git-based deployment hook
- [ ] create tools and skill to backup data from target to local host and upload to cloud.dev2null.de
- [] Implement calling Backup and Recovery function for Admin

→ [CRM roadmap & phases](doc/todo/8.4-crm-platform.md)

### 6.3 Deployment Workflow Enhancements 🔲

- [ ] `src/setup/notify_maintenance.py` — pre-restart user notification
- [ ] `NOTIFY_USERS_ON_UPDATE` flag in `bot.env` — ping approved users on startup after version bump
- [ ] Feature flags pattern in `bot.env` for gradual rollout

### 6.4 Hardware Upgrades 💡
→ PicoClaw (Pi 3 B+) performance tuning: **§24.4** (USB SSD, tmpfs ONNX, zram, CPU governor, low-quality voice model)
→ OpenClaw upgrade path (Pi 5 / RK3588 / Laptop/AI X1): **§25** — pgvector, local LLM, ≤2 s voice with NPU
→ VPS cloud deployment: **§26** — Docker Compose, webhook mode, pgvector, multi-user
→ Full hardware analysis: [doc/hw-requirements-report.md](doc/hw-requirements-report.md) · [doc/hardware-performance-analysis.md](doc/hardware-performance-analysis.md)

### 6.5 Recovery Testing 🔲

- [ ] Test full recovery on a different hardware device — flash image backup, restore all services, verify bot + voice + calendar come up cleanly on fresh Pi
- [] Review existed tests, test suite. extending of regression and additional test if it's needed
- implementing test agent to implement tests for using in copilot by changing, fixing, extending functionality
- implementing agent to run all kinds tests depend on kind of changing and kind and taget of deploying  
---

## 7. Demo Features for Client Presentations 🔲

Quick-win features — Level A (LLM-only, <2 h), B (helpers, 2–4 h), C (impressive, 4–8 h).
→ [Full list with implementation notes](doc/todo/7-demo-features.md)

**Minimum demo set (1 day):** A1 Weather + A2 Translator + B2 System Status + B3 Timer + C3 QR Code

---

## 8. Web UI & CRM Platform
### 8.2 Rename Assistant to Taris / TARIS and Platform to SINTA ✅ Implemented (v2026.4.7)

### 8.3 Offline Telegram Regression Suite ✅ Implemented (v2026.4.7)
31 offline unit tests (`src/tests/telegram/test_telegram_bot.py`) — 8 classes covering: CmdStart, CallbackMode, CallbackAdmin, CallbackMenu, VoiceHandler, TextHandlerNotes, TextHandlerAdmin, ChatMode. Runs locally, no Pi required.

### 8.4 CRM Platform Vision 💡

Contacts → Deals → Custom fields → White-label. Core platform C0 done (v2026.3.28).
 [] UI: Human nice interface and interactions personly in Name of Taris. 
 [] Running implemented activities per voice
 [] Intelligent alarms
 [] Intelligent notifation 



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
- [ ] `src/setup/migrate_sqlite_to_pg.py` — taris.db → PostgreSQL (Phase 5)
- [ ] Tests T22 `sqlite_schema`, T23 `migration_idempotent`, T24 `vector_search_basic`, T25 `store_adapter_contract`, T26 `credential_encryption`
### 9.1 Storing of user data in the local database not in files
- [] all existed user data shall be migrated to database. create scripts for migration and migrate data.
- [] Notes shall be storde in Database not in files (Attention restriction of size of notes shall be transparently for user)
- [] Calendar data shall be stored in database
- [] profile user data and user settings shall be stored in database
- [] all kinds of memory(conversations context) shall be stored in the database
- [] all user contacts shall be stored in the database
- [] last interactions, opened ui and status of ui shall be storde in the database 
- [] all new implemented functions with focus of using of data shall be use database and fiels to save data

## 10. Upload and using documents as Knowlegdes
-[] Function to upload and administration documents (upload, view,  delete , share to all , set title, set hash/label, share to other users in system)
- [] Using documents as knowledgebase in chat in multimodal RAG way
- [] documents can be contain text, images, tables
- [] documents used as knowledegs shall assigned to user or can be shared to use from all users as knowledges
- [] documents can be replaced through other document if documents are identical by hash, name, size parameters and after confirmation from user to replace already stored document with new. User shall see name and descrition already existed document
- [] criteria of compAring of documnts shall be configurable in Admin panel
- [] quality consistency check created chunks after uploading of document

### 10.1 Short-, middle and Long-term memories 
Before implementaion of memories shall be analyse how can be implemented . here is first draft, proposal for implelemnation:
- [] implement short-term, middle-term, long-term memories 
- [] conversations after reaching maximal short memory size of conversation shall be set as middle-term memory 
- [] middle-term memory after reaching a size shall be cleaned and summariazed/compacted and meregd together with long-term memory
- [] cleaning all kind of memories if user its wishes in profile 
- [] setting all memories parameters in Admin panel
- [] all kind of memories can be used as context in conversations with user per default or user can switch off using memories in conversations

## 11. Central control dashboard (primary per voice)
- [] IMplementing central dashboard to control and run all activities of the asstsiant
- [] all functions can be runned and controled from this board. Steering can be do per voice or per text input.
- [] ui shall be switchable  per voice to functional ui part to run activities
- [] all activities can be used later as knowledge for conversation with assistant and for running new activities. Context depended activities. This fucntion shall be deactivatable
- [] all activities shall be  stored in databse as activities and as text for LLM context 

## 12. Input all textes in all application parts per voice in one window
- [] all inputs of textes shall be possible per voice exceptional confirmation of runnig activities

## 13. Implementing smart CRM 
- [] Implementing open fuctions if they are not already implemented from concept\additional\crm_system_requirements.md and concept\additional\SYSTEM_REQUIREMENTS_SmartClient360.md
- [] all inputs and switching between  all windows shall be controlable per voice. Smart client. 
- [] smart input of text and automatical set values in the input fields 


## 14. Developer Board
- [] Impelementing developer board to extend , update, remove functionality of applciation based on agent principe


## [] 15. Connecting Calendar, E-Mails, Drives from Google and Yandex


## 16 Implementing functions of personal assistant
- [] Implementing open fuctions if they are not already implemented from concept\additional\KIM_PACKAGES.md

## [] 17. Implementing  Max messenger UI analog Telegram

## [] 18. Using ZeroClaw instead PicoClaw
→ [Hardware Requirements Report §4.2](doc/hw-requirements-report.md) — ZeroClaw feasibility analysis (text-only; voice not viable on 512 MB)

## 19. OpenClaw Platform 💡
→ Full deployment plan: **§25 Deployment Plan: OpenClaw (Laptop / AI X1 / Pi 5 8 GB / RK3588)**
→ Hardware specs and options: [doc/hw-requirements-report.md §1.3](doc/hw-requirements-report.md)

---

## 20. Copilot Performance Optimization ✅ Implemented (v2026.3.43)

Reduce context-window consumption so Copilot sessions sustain 8–10 turns without compaction.  
→ [Analysis & Proposals](concept/copilot_optimization.md) | [Vibe Coding Guidelines](doc/vibe-coding-guidelines.md)

**Root causes:** auto-loaded instructions too large, duplicate deploy steps in 4 locations, "ALWAYS read" pulls 39 KB docs, `safe-update.instructions.md` scoped to `**`.

### 20.1 Quick wins ✅ All done

- [x] **P-4** Split `doc/architecture.md` into `doc/arch/*.md` (8 topic files) — ✅ done
- [x] **P-3** Replace "ALWAYS read bot-code-map.md" with "search it" instruction — ✅ done
- [x] **P-8** Add `doc/quick-ref.md` — single 3 KB always-read index — ✅ done
- [x] **P-2** Slim `copilot-instructions.md` — remove T01–T21 table and duplicate patterns — ✅ done
- [x] **P-1** Fix `safe-update.instructions.md` `applyTo` glob → narrowed to 4 concrete paths — ✅ done
- [x] **P-7** Move accounting task from `INSTRUCTIONS.md` to `concept/` — ✅ done
- [x] **P-6** Shorten `bot-deploy.instructions.md` — §§2–5 condensed, pointer to `/taris-deploy-to-target` — ✅ done

### 20.2 Medium effort ✅ All done

- [x] **P-6b** Shorten `safe-update.instructions.md` — Steps 1–9 bat blocks → 9-item checklist — ✅ done
- [x] **P-6c** Shorten `bot-coding.instructions.md` — doc-maintenance + Piper chain removed, pointer to `/taris-update-doc` — ✅ done
- [x] **P-9** Update `doc/copilot-skills-guide.md` — `#file:` tip box + `@workspace` warning added — ✅ done
- [x] **P-10** Add token-budget review table to `doc/vibe-coding-guidelines.md` sprint checklist — ✅ done

### 20.3 Larger refactors

- [x] **P-5** ~~Split `src/bot_web.py`~~ — **superseded by TODO 21** (Screen DSL + YAML Loader): declarative screen files naturally modularize UI without risky file split. Screen logic migrates to `src/screens/*.yaml`; `bot_web.py` gains a single `/dynamic/{screen_id}` route instead of N hardcoded render blocks.
- [x] **P-11** Back-link footers added to all 9 `doc/todo/*.md` specs; `storage-architecture.md` noted as 18 KB (> 10 KB target, trimming deferred) — ✅ done

### 20.4 Guidelines & Process ✅ All done

- [x] **G-1** Create `doc/vibe-coding-guidelines.md` — artifact structuring rules, session habits, naming conventions — ✅ done
- [x] **G-2** Add quarterly review section to `doc/vibe-coding-protocol.md` — ✅ done
- [x] **G-3** Add context-optimization bullet to session-start checklist in `AGENTS.md` — ✅ done

---

## 21. Dynamic UI — Enhanced Screen DSL + JSON/YAML Loader �

Extend the existing Screen DSL with a declarative file loader that reads screen
definitions from YAML/JSON files. Zero RAM overhead; both renderers unchanged;
incremental migration from Python-coded screens.

→ [Research report](doc/research-dynamic-ui-scenarios.md) · [Spec](doc/todo/21-screen-dsl-loader.md)

### 21.1 Phase 1 — Core Loader ✅ Implemented (v2026.4.10)

- [x] Create `src/ui/screen_loader.py` (288 lines): `_WIDGET_BUILDERS` registry, `load_screen()`, all 10 widget builders
- [x] JSON support (stdlib `json`) + YAML support (optional `pyyaml`)
- [x] i18n key resolution via `t_func(lang, key)` parameter
- [x] Role-based widget visibility (`visible_roles: [admin]` in YAML)
- [x] Variable substitution in text and actions (`{var_name}` → `variables` dict)
- [x] `load_all_screens(dir)` for preload at startup
- [x] `reload_screens()` for hot-reload (clears `_screen_cache`)
- [x] Add `pyyaml` to `deploy/requirements.txt`
- [x] Unit tests: 53 tests across 9 test classes — all pass on PI2

### 21.2 Phase 2 — Proof of Concept ✅ Implemented (v2026.4.10)

- [x] Create `src/screens/` directory for YAML/JSON screen definitions
- [x] Convert `help` screen to `screens/help.yaml`
- [x] Wire Telegram callback: `load_screen("screens/help.yaml", ctx, t_func=_t_by_lang)` + `render_screen()`
- [x] Add `GET /screen/{screen_id}` route in `bot_web.py` + `templates/dynamic.html`
- [x] Add `reload_screens` admin callback → "✅ Screens reloaded"
- [x] Smoke test: both services running v2026.4.10 on PI2, clean startup confirmed

### 21.3 Phase 3 — Main & Admin Menus ✅ Implemented (v2026.4.10)

- [x] Convert main menu to `screens/main_menu.yaml` (with `visible_roles` for admin button row)
- [x] Convert admin menu to `screens/admin_menu.yaml` (with `{pending_badge}` variable substitution)
- [x] Wire Telegram callbacks: `menu` and `admin_menu` use DSL `load_screen()` + `render_screen()`
- [x] Add 11 admin i18n keys to `strings.json` (ru/en/de)
- [x] Test: py_compile OK, YAML validation OK, IDE error-free

### 21.4 Phase 4 — Feature Screens ✅ Implemented (v2026.4.10)

- [x] Convert notes list + note view + note edit screens (`notes_menu.yaml`, `note_view.yaml`, `note_raw.yaml`, `note_edit.yaml`)
- [x] Convert settings/profile screen (`profile.yaml`, `profile_lang.yaml`, `profile_my_data.yaml`)
- [x] Wire all 7 handlers in `bot_handlers.py` via `_render()` + `_screen_ctx()` helpers
- [x] All 10 YAML screen files in `src/screens/`, validated with zero errors

### 21.5 Phase 5 — Validation & Docs ✅ Implemented (v2026.4.10)

- [x] Create `src/screens/screen.schema.json` JSON Schema (draft-07, 14 definitions, 10 widget types)
- [x] Add schema validation in `_load_file()` — log warning on invalid files
- [x] Document screen file format as new section §19 in `doc/dev-patterns.md`
- [x] Update `doc/bot-code-map.md` with `screen_loader.py` entry

### 21.6 Phase 6 — Visual Editor (OpenClaw only) 🔲

- [ ] Admin panel page: CodeMirror YAML editor + live preview pane
- [ ] `PUT /admin/screens/{id}` route to save edited YAML to `src/screens/`
- [ ] Auto-trigger `reload_screens()` on save

## 22. Notes
### 22.1. Download and Upload Notes
- [] Every user can download all Notes(in Zip) or every Note seprate
- [] Deleting of Note needs confiramtion of user  
- [] Title of Note shall be changable now is only text is possible to change only text. Add function to Change Titel of Note 
- [] Two steps to add or change content of Notes is not needed. Addding Add , Change function for Note already in First step. Second step to remove 
- [] After Update is  Note not visible and operations to change is not more available. After update show Note and switch to previous step with visualisation buttons to add or Change of text  

---

## 23. Research & Comparison — Hybrid RAG vs Google Grounding 🔲

Validate the Hybrid Tiered RAG architecture (Variant C) against Google's server-side Grounding and the Worksafety reference implementation. Use **Karpathy AutoResearch** (`karpathy/autoresearch`) as the autonomous evaluation framework — agent-driven experiments across three target architectures: Raspberry Pi (mini PC), OpenClaw on AI X1 (GPU), VPS.
→ [Concept paper](concept/rag-memory-architecture.md) · [Extended research](concept/rag-memory-extended-research.md) (§6b AutoResearch)

- [ ] 23.1 OpenClaw on Laptop — install Sintaris platform (Taris) on laptop for local development and RAG comparison experiments
- [ ] 23.2 n8n + PostgreSQL clone on Laptop — replicate Worksafety orchestration stack locally for comparison baseline
- [ ] 23.3 Karpathy nanochat + AutoResearch — install nanochat (edge LLM training) and autoresearch (autonomous evaluation) on OpenClaw laptop (AI X1); verify GPU access
- [ ] 23.4 Hybrid RAG on Google Grounding — bind OpenClaw to Gemini Grounding API; evaluate server-side RAG quality vs local FTS5+vector
- [ ] 23.5 Clone Worksafety DB + n8n app on OpenClaw — replicate Worksafety knowledge base and workflows on OpenClaw hardware
- [ ] 23.6 Clone Worksafety DB for Google Grounding case — prepare Worksafety dataset as test corpus for Gemini Grounding evaluation
- [ ] 23.7 AutoResearch environment setup — write `program.md` (RAG evaluation agenda), `evaluate.py` (RAG pipeline config runner), `prepare.py` (test corpus + ground truth); define `rag_score` composite metric (precision, recall, latency, memory, cost); configure per-architecture targets (Pi SSH, AI X1 native, VPS SSH)
- [ ] 23.8 Implement Worksafety workflow on OpenClaw with Google Grounding — port n8n RAG pipeline to Taris architecture, bind to Gemini Grounding
- [ ] 23.9 AutoResearch RAG evaluation — run automated overnight experiments per target architecture; ~100 configurations per target; measure rag_score; log all results to `~/.taris/autoresearch/results/`
- [ ] 23.10 Cross-architecture Pareto analysis — aggregate AutoResearch results across Pi/X1/VPS; identify Pareto-optimal configurations per hardware tier; document recommended defaults
- [ ] 23.11 AutoResearch for nanochat training — adapt autoresearch paradigm to optimize nanochat hyperparameters (depth, vocab_size, seq_len) for edge LLM on Pi 5 / AI X1
- [ ] 23.12 Compare Hybrid RAG vs Google Grounding — run identical queries through both pipelines using AutoResearch evaluation harness; measure quality/latency/cost; document results

---

## 24. Deployment Plan: PicoClaw (Raspberry Pi 3 B+) 🔲

> **Hardware:** BCM2837B0 · 4× Cortex-A53 @ 1.4 GHz · 1 GB LPDDR2. RAM budget at full load: ~715 MB (critical).
> **Voice latency baseline:** ~30–60 s; achievable after tuning: ~20–25 s. ≤2 s target is **not achievable** (no NPU/GPU).
> **Backend:** `STORE_BACKEND=sqlite` + sqlite-vec. **LLM:** Cloud only (no local inference on Pi 3).
> → Hardware deep-dive: [doc/hardware-performance-analysis.md](doc/hardware-performance-analysis.md) · [doc/hw-requirements-report.md §1.1](doc/hw-requirements-report.md)

### 24.1 Base System
- [ ] Flash Raspberry Pi OS Lite 64-bit (Bookworm); enable SSH; set hostname; disable GUI
- [ ] `sudo apt install python3.11 python3-pip git ffmpeg sqlite3 -y`
- [ ] Clone repo to `/home/stas/taris/`; `pip install -r deploy/requirements.txt`
- [ ] Create `~/.taris/bot.env`: `STORE_BACKEND=sqlite`, `LLM_PROVIDER=taris`, `EMBED_KEEP_RESIDENT=0`

### 24.2 Voice Pipeline
- [ ] Install Piper binary `/usr/local/bin/piper`; download `ru_RU-irina-medium.onnx` (66 MB) + `.json` config to `~/.taris/`
- [ ] Install Vosk models: `vosk-model-small-ru-0.22` (48 MB) + `vosk-model-small-en-us-0.15` to `~/.taris/`
- [ ] Optional: `ru_RU-irina-low.onnx` (faster TTS inference); `ggml-base.bin` (Whisper fallback, 142 MB)
- [ ] Run `bash src/setup/setup_voice.sh` — verifies all binaries and model paths

### 24.3 Storage & Migration
- [ ] `bash src/setup/install_sqlite_vec.sh` (ARMv8 sqlite-vec wheel)
- [ ] `python3 src/setup/migrate_to_db.py` (idempotent — JSON → SQLite)
- [ ] Set `STORE_VECTORS=off` in `bot.env` by default (FTS5-only until free RAM confirmed ≥150 MB)

### 24.4 Performance Tuning (apply in order)
- [ ] CPU governor: `echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`; persist in `/etc/rc.local`
- [ ] GPU memory: add `gpu_mem=16` to `/boot/firmware/config.txt` → frees ~50 MB extra page cache
- [ ] zram: `sudo apt install zram-tools; echo ALGO=lz4 >> /etc/default/zramswap; echo PERCENT=50 >> /etc/default/zramswap`
- [ ] Enable `tmpfs_model` voice opt in admin panel — copies 66 MB ONNX to `/dev/shm`, eliminates 10–15 s Piper cold-start
- [ ] USB SSD (optional): mount via USB 2.0; copy ONNX models; update `PIPER_MODEL` path; move swap there (→ 0.4 ms latency vs 15 ms on SD). See [doc/hardware-performance-analysis.md §8](doc/hardware-performance-analysis.md)
- [ ] Enable `piper_low_model` voice opt — TTS inference ~10 s faster at slightly lower quality
- [ ] Enable `persistent_piper` voice opt — keeps warm Piper subprocess between calls

### 24.5 Services & Smoke Test
- [ ] `sudo cp src/services/taris-telegram.service src/services/taris-web.service /etc/systemd/system/`
- [ ] `sudo systemctl daemon-reload && sudo systemctl enable --now taris-telegram taris-web`
- [ ] Smoke check: `journalctl -u taris-telegram -n 20 --no-pager` → `[INFO] Version: X.Y.Z` + `Polling Telegram…`
- [ ] Voice regression: `python3 ~/.taris/tests/test_voice_regression.py` — all T01–T26 pass

### 24.6 RAG on Pi 3 (FTS5-only mode)
- [ ] Phase A — Memory System: add `memory_summaries`/`memory_long` tables to `store_sqlite.py`; implement `compact_short_to_middle()` / `compact_middle_to_long()` (see `concept/rag-memory-architecture.md §6.3`)
- [ ] Phase B — FTS5 RAG: `classify_query()` adaptive routing; FTS5 BM25 search only (no vectors — RAM constraint); `rag_log` table
- [ ] **Do NOT** enable `STORE_VECTORS=on` on Pi 3 unless `free -m` under full load confirms ≥150 MB available
- [ ] Embedding model (`all-MiniLM-L6-v2`): load on demand and free after use (`EMBED_KEEP_RESIDENT=0`)

### 24.7 Known Constraints
- Voice ≤2 s target: ❌ impossible on Pi 3 B+ (no NPU/GPU; minimum requires ≥13 TOPS — see §25 for upgrade)
- Local LLM: ❌ not viable; Qwen2-0.5B only as emergency offline fallback at ≤0.4 tok/s
- Vector search: ⚠️ only if free RAM ≥150 MB confirmed; otherwise FTS5-only RAG

---

## 25. Deployment Plan: OpenClaw (Laptop / AI X1 / Pi 5 8 GB / RK3588) 🔲

> **Hardware options:** x86_64 Laptop/AI X1 · Pi 5 8 GB (A76 @ 2.4 GHz, NVMe 900 MB/s) · RK3588 (6 TOPS NPU, ≤16 GB, NVMe 3000 MB/s).
> **Voice target:** ≤2 s requires NPU/GPU (≥13 TOPS). Pi 5 + Hailo-8L HAT achieves 1.5–2.0 s with cloud LLM.
> **Backend:** `STORE_BACKEND=postgres` + pgvector HNSW. **LLM:** Local llama.cpp + cloud fallback.
> → Hardware specs: [doc/hw-requirements-report.md §1.3 + §0](doc/hw-requirements-report.md)
> → RAG architecture: [concept/rag-memory-architecture.md](concept/rag-memory-architecture.md) (Variant C — Hybrid Tiered RAG, score 4.45)

### 25.1 Base System
- [ ] Ubuntu 22.04 LTS (or Raspberry Pi OS Bookworm 64-bit for Pi 5); `sudo apt install python3.11 python3-pip git ffmpeg -y`
- [ ] NVMe SSD: mount at `/data/taris/`; symlink `~/.taris → /data/taris/` (Pi 5: PCIe 2.0 900 MB/s; RK3588: PCIe 3.0 3000 MB/s)
- [ ] Clone repo; `pip install -r deploy/requirements.txt`

### 25.2 PostgreSQL + pgvector
- [ ] `sudo apt install postgresql-16 -y; pip install psycopg2-binary`
- [ ] `sudo -u postgres psql -c "CREATE USER taris WITH PASSWORD '…'; CREATE DATABASE taris_db OWNER taris;"`
- [ ] `sudo apt install postgresql-16-pgvector -y` (or build from source); `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] HNSW index: `CREATE INDEX CONCURRENTLY ON documents USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);`
- [ ] Set `STORE_BACKEND=postgres`, `DB_URL=postgresql://taris:…@localhost/taris_db`, `STORE_VECTORS=on` in `bot.env`

### 25.3 Local LLM (llama.cpp)
- [ ] Build: `git clone https://github.com/ggerganov/llama.cpp /data/llama.cpp && cmake -B build -DLLAMA_BLAS=ON && cmake --build build -j$(nproc)`
- [ ] GPU (Laptop/AI X1): add `-DLLAMA_CUDA=on` (NVIDIA) or `-DLLAMA_METAL=on` (Apple) to cmake flags
- [ ] Download model: Pi 5 → `Phi-3-mini-4k-instruct-Q4_K_M.gguf` (2.4 GB); Laptop/AI X1 → 7B–13B GGUF
- [ ] Deploy `src/services/taris-llm.service`; configure `--model` path and `--port 8081`; `sudo systemctl enable --now taris-llm`
- [ ] Set `LLM_PROVIDER=local`, `LLAMA_CPP_URL=http://localhost:8081`, `LLM_LOCAL_FALLBACK=true` in `bot.env`

### 25.4 Embedding Service
✅ Implemented (v2026.4.13) — `src/core/bot_embeddings.py` (`EmbeddingService`); fastembed-first with sentence-transformers fallback; `EMBED_MODEL` / `EMBED_KEEP_RESIDENT` / `EMBED_DIMENSION` constants in `bot_config.py`; wired into `bot_documents.py`; `src/setup/install_embedding_model.sh`; `bot.env.example` updated.

### 25.5 Voice Pipeline + NPU Acceleration
✅ Implemented (v2026.4.13) — `src/setup/setup_voice_openclaw.sh` (x86_64 Vosk + Piper install); `VOICE_BACKEND=cpu|cuda|openvino` constant; `--device cuda` flag passed to whisper-cpp when `VOICE_BACKEND=cuda`.

### 25.6 RAG Implementation — Variant C (Hybrid Tiered RAG)
- [ ] **Phase A — Memory System (3–5 d):** `bot_memory.py`; DB tables `memory_summaries` + `memory_long`; `compact_short_to_middle()` / `compact_middle_to_long()` — see `concept/rag-memory-architecture.md §6.3`
- [ ] **Phase B — Enhanced RAG (5–7 d):** FTS5 + pgvector HNSW + RRF fusion (k=60); `EmbeddingService` (ONNX Runtime); `classify_query()` routing; `rag_log` table; `RAG_TOP_K=5`, `RAG_MAX_CHARS=2000`
- [ ] **Phase C — Document Management (3–4 d):** upload/chunk pipeline (`RAG_CHUNK_SIZE=512`, overlap=50); `doc_sharing` table; admin sharing controls; `PyMuPDF` for PDF+image; `rag_settings` per-user config
- [ ] **Phase D — Remote RAG + MCP (4–6 d):** expose `search_knowledge()` as MCP tool; `MCP_REMOTE_URL` client; circuit breaker + fallback; see `concept/rag-memory-architecture.md §4.3`
- [ ] **Phase E — Multimodal (future, GPU/Pi 5+ only):** CLIP embeddings for image search; `docling` for complex PDFs; vision API fallback

### 25.7 Migration from PicoClaw
- [ ] `python3 src/setup/migrate_sqlite_to_pg.py` (copies taris.db → PostgreSQL, idempotent)
- [ ] Validate row counts; run full test suite T01–T26 + Web UI Playwright + offline Telegram tests

### 25.8 Services & Test
- [ ] `sudo cp src/services/taris-*.service /etc/systemd/system/ && sudo systemctl daemon-reload`
- [ ] `sudo systemctl enable --now taris-telegram taris-web taris-llm`
- [ ] AutoResearch (§23.7–23.9): `pip install ragas deepeval`; configure `evaluate.py` per `concept/rag-memory-architecture.md §6b`
- [ ] Playwright UI tests: `py -m pytest src/tests/ui/ -v --base-url https://openclawpi2:8080`

### 25.9 Hardware Notes
- **Pi 5 8 GB** — minimum for full stack (PostgreSQL + llama.cpp + RAG). NVMe HAT strongly recommended.
- **Pi 5 4 GB** — marginal: pgvector feasible but local LLM too slow; use cloud LLM provider.
- **RK3588 (Orange Pi 5 / Rock 5B)** — best Pi-class option: 6 TOPS NPU + PCIe 3.0 + up to 16 GB.
- **Laptop / AI X1 (x86_64)** — full stack; 7B–13B models with GPU; fastest development iteration.
- **Pi 4 B 4 GB** — not recommended for OpenClaw tier; stick to §24 patterns with cloud LLM.

---

## 26. Deployment Plan: VPS (Cloud) 🔲

> **Minimum spec:** 2 vCPU · 4 GB RAM · 40 GB SSD · Ubuntu 22.04 LTS.
> **Stack:** Docker Compose · PostgreSQL 16 + pgvector · nginx + Let's Encrypt TLS.
> **Bot mode:** Telegram webhook (not polling). Multi-user (`MULTI_USER=1`).

### 26.1 Provision & Base Setup
- [ ] Provision Ubuntu 22.04 VPS; create user `taris`; enable SSH key-only login; disable password auth
- [ ] `sudo apt install docker.io docker-compose-v2 git nginx certbot python3-certbot-nginx ufw -y`
- [ ] Clone repo to `/opt/taris/`; `chown -R taris:taris /opt/taris`

### 26.2 PostgreSQL + pgvector
- [ ] Deploy `postgres:16-alpine` in Docker Compose (internal only, not exposed); or install system PostgreSQL
- [ ] `CREATE EXTENSION IF NOT EXISTS vector;`; create `taris` user + `taris_db`; run `migrate_to_db.py`
- [ ] Set `STORE_BACKEND=postgres`, `DB_URL=postgresql://taris:…@localhost/taris_db`, `STORE_VECTORS=on`, `EMBED_KEEP_RESIDENT=1` in `bot.env`
- [ ] HNSW index: `CREATE INDEX CONCURRENTLY ON documents USING hnsw (embedding vector_cosine_ops);`

### 26.3 TLS & nginx
- [ ] nginx server block: proxy `/` → `http://localhost:8080`; `/webhook` → `http://localhost:8080/webhook`
- [ ] `sudo certbot --nginx -d yourdomain.com` (Let's Encrypt; auto-renew)
- [ ] nginx rate limiting on `/webhook`: `limit_req_zone $binary_remote_addr zone=webhook:10m rate=30r/m;`
- [ ] Firewall: `ufw allow 80,443/tcp; ufw deny 5432/tcp; ufw enable`

### 26.4 Telegram Webhook
- [ ] Register: `curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://yourdomain.com/webhook&secret_token=<RANDOM_SECRET>"`
- [ ] Verify: `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"` → `"pending_update_count":0`
- [ ] Set `TELEGRAM_WEBHOOK_URL=https://yourdomain.com/webhook`, `WEBHOOK_SECRET=<secret>`, `MULTI_USER=1` in `bot.env`

### 26.5 RAG & Embeddings
- [ ] `pip install onnxruntime sentence-transformers psycopg2-binary` in bot virtualenv
- [ ] `EMBED_MODEL=all-MiniLM-L6-v2`, `EMBED_KEEP_RESIDENT=1` in `bot.env`
- [ ] LLM: connect via `LLM_PROVIDER` to cloud provider (OpenAI / Anthropic / Gemini); local llama.cpp only if VPS RAM ≥8 GB
- [ ] Implement Phases A–D from §25.6 (same RAG code; only backend differs — pgvector already configured)

### 26.6 Backups & Monitoring
- [ ] Daily: `pg_dump taris_db | gzip > /backup/taris_$(date +%F).sql.gz`; rsync to `cloud.dev2null.de` (see §6.2); retain 30 days
- [ ] Deploy `src/services/taris-logrotate` → `/etc/logrotate.d/taris`
- [ ] `bot_logger.py` structured logs; CRITICAL events forwarded to admin Telegram ID
- [ ] `Restart=on-failure; RestartSec=10` in all systemd service units

### 26.7 Security Hardening
- [ ] `ADMIN_USERS` + `ALLOWED_USERS` must be set in `bot.env` before first start; review on every deploy
- [ ] Rotate `WEBHOOK_SECRET` and `JWT_SECRET` on first deploy; store outside git
- [ ] `sudo apt install fail2ban` — monitor SSH + nginx auth log
- [ ] `sudo unattended-upgrades` enabled; monthly review of `deploy/requirements.txt` for CVEs

### 26.8 Scaling Path
- [ ] ≤50 concurrent users: single instance as above is sufficient
- [ ] 50–200 users: Redis session cache (`REDIS_URL=redis://localhost:6379`); `uvicorn --workers 4`
- [ ] 200+ users: horizontal scale via load balancer + multiple bot-web instances; RabbitMQ/Redis update queue