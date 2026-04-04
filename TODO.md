# Taris Bot — TODO & Roadmap

**Legend:** ✅ Done · 🔄 In progress · 🔲 Planned · 💡 Idea / future

---

## 0. Known bugs
- [] System chat error . Not enough admin rights to run commands. LOg from Telegram:
[18.03.2026 20:05] SU: how much space i have on flash
[18.03.2026 20:05] Smart PicoClaw Bot: ❌ Could not generate a command. Try again.
[20.03.2026 06:28] Smart PicoClaw Bot: 📄 taris



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
- [] Uploaded from user Documents shall be used only in your context and can be shared with other users, in first step with all
- [] Admin can administrate(view, delete) all uploaded documents from all users and which user which document uploaded and status of sharing documents 
- [] Admin can remove sharing documents for uploaded documents from user to all 
- [] Uploaded documents can be downloaded in original format 
- [] ( nice to have) if is possible to show txt, pdf, rtf, docx, md documents

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

### 3.2 Gemma 4 Model Evaluation 🔄

Evaluate Google Gemma 4 models as potential replacement/supplement for current Ollama LLMs.
→ See: `doc/research-gemma4-benchmark.md` for full analysis

- [x] Research Gemma 4 model family (E2B, E4B, 31B, 26B-A4B) — specs, architecture, audio capabilities
- [x] Create benchmark script `src/tests/llm/benchmark_ollama_models.py` with Gemma 4 + Qwen candidates
- [x] Hardware compatibility analysis (SintAItion: E2B/E4B fit, 31B too large; TS2: only E2B)
- [x] Comparison with currently used models (qwen3.5:latest, qwen2:0.5b, gpt-4o-mini)
- [x] STT feasibility analysis (E2B/E4B have audio, but not a Whisper replacement)
- [ ] Pull gemma4:e2b + gemma4:e4b on SintAItion and run benchmark
- [ ] Compare actual t/s and quality vs qwen3.5:latest baseline
- [ ] Test gemma4:e2b on TariStation2 as qwen2:0.5b alternative
- [ ] Decision: adopt Gemma 4 or keep current models

---

## 4. Content & Knowledge
- [ ] Timeout monitoring by using RAG services or by waiting for answer from LLM
- [ ] settings for using LLM+RAG configurable (temperature, sead, system prompt, role, chunk counts) via Admin panel
- [ ] settings incl. credentials to connect to remote RAG MCP service via Admin panel
- [ ] information for the user about restrictions for uploadable documents and size of database over telegram and web ui
- [ ] logging in DB information about  founded chunks and prompt by requests to llm (input) and results from llm inclusive returned system information . Access via Admin panel to last RAG activities(log outpus)
- [ ] after uploading document shall be saved statistic about source document parsing, chuncking, embedding as protocol in the database . Output statistic for Admin by loading documents 


---

### 4.1 Local RAG Knowledge Base 🔲

- [ ] using local llm for RAG optional , configurable in Admin PAnel 
- [ ] Embed documents with `all-MiniLM-L6-v2` fro local RAG
- [ ] Vector similarity search → inject top-k context into LLM prompt
- [ ] Commands: `/rag_on`, `/rag_off`
- [ ] Storage: `~/.taris/knowledge_base/` (documents + `embeddings.db`)
- [ ] configuration to use local knowledges for integrated RAG with local LLM and remote llm and remote RAG knowledge  service.
- [ ] settings for configuration of local RAG service via Admin panel


### 4.2 [ ] optimize local RAG

### 4.2 [ ] Implement remote  RAG service as MCP service
- [ ] Using local knowledges is possible and connect to use remote RAG services as additional
- [ ] Connect , using to remote service via MCP server connection as tool
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

- [ ] Pi 4 B upgrade — drops total latency ~115 s → ~15 s
- [ ] Pi 5 + NVMe upgrade — ~8 s total; full local LLM viable
- [ ] USB SSD — eliminates Piper model cold-start (15 s → 2 s), zero code changes

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

## [] 19. Using OpenClaw instead PicoClaw
→ [Hardware Requirements Report §4.3 + §6](doc/hw-requirements-report.md) — OpenClaw configurations (Pi 5, RK3588, Jetson); full local AI stack

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

- [ ] **P-5** Split `src/bot_web.py` (83 KB) into `bot_web_app.py` + `bot_web_api.py` + `bot_web_render.py` (~25–40 KB each) — **deferred** (4–8 h, deployment risk; schedule as standalone sprint)
- [x] **P-11** Back-link footers added to all 9 `doc/todo/*.md` specs; `storage-architecture.md` noted as 18 KB (> 10 KB target, trimming deferred) — ✅ done

### 20.4 Guidelines & Process ✅ All done

- [x] **G-1** Create `doc/vibe-coding-guidelines.md` — artifact structuring rules, session habits, naming conventions — ✅ done
- [x] **G-2** Add quarterly review section to `doc/vibe-coding-protocol.md` — ✅ done
- [x] **G-3** Add context-optimization bullet to session-start checklist in `AGENTS.md` — ✅ done

---

## 21. Dynamic UI — Enhanced Screen DSL + JSON/YAML Loader 🔲

Extend the existing Screen DSL with a declarative file loader that reads screen
definitions from YAML/JSON files. Zero RAM overhead; both renderers unchanged;
incremental migration from Python-coded screens.

→ [Research report](doc/research-dynamic-ui-scenarios.md) · [Spec](doc/todo/21-screen-dsl-loader.md)

### 21.1 Phase 1 — Core Loader 🔲

- [ ] Create `src/ui/screen_loader.py` (~100 lines): `_WIDGET_BUILDERS` registry, `load_screen()`, all 10 widget builders
- [ ] JSON support (stdlib `json`) + YAML support (optional `pyyaml`)
- [ ] i18n key resolution via `t_func(lang, key)` parameter
- [ ] Role-based widget visibility (`visible_roles: [admin]` in YAML)
- [ ] Variable substitution in text and actions (`{var_name}` → `variables` dict)
- [ ] `load_all_screens(dir)` for preload at startup
- [ ] `reload_screens()` for hot-reload (clears `_screen_cache`)
- [ ] Add `pyyaml` to `deploy/requirements.txt`
- [ ] Unit tests: all 10 widget types, i18n resolution, role filtering, variable substitution

### 21.2 Phase 2 — Proof of Concept 🔲

- [ ] Create `src/screens/` directory for YAML/JSON screen definitions
- [ ] Convert `help` screen to `screens/help.yaml`
- [ ] Wire Telegram callback: `load_screen("screens/help.yaml", ctx, t_func=_t_by_lang)` + `render_screen()`
- [ ] Add `GET /dynamic/{screen_id}` route in `bot_web.py` + `templates/dynamic.html`
- [ ] Add `reload_screens` admin callback → "✅ Screens reloaded"
- [ ] Smoke test: both channels render identical output from same YAML file

### 21.3 Phase 3 — Main & Admin Menus 🔲

- [ ] Convert main menu to `screens/main_menu.yaml` (with `visible_roles` for admin button row)
- [ ] Convert admin menu to `screens/admin_menu.yaml`
- [ ] Test: regular user sees filtered menu; admin sees full menu

### 21.4 Phase 4 — Feature Screens 🔲

- [ ] Convert notes list + note view + note edit screens
- [ ] Convert calendar event list screen
- [ ] Convert mail digest screen
- [ ] Convert settings/profile screen

### 21.5 Phase 5 — Validation & Docs 🔲

- [ ] Create `src/screens/screen.schema.json` JSON Schema
- [ ] Add schema validation in `_load_file()` — log warning on invalid files
- [ ] Document screen file format as new section in `doc/dev-patterns.md`
- [ ] Update `doc/bot-code-map.md` with `screen_loader.py` entry

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