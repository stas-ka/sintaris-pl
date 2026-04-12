# Taris Bot — TODO & Roadmap

**Legend:** ✅ Done · 🔄 In progress · 🔲 Planned · 💡 Idea / future

---

## 0. Known bugs

### ✅ Fixed → See DONE.md (bugs 0.23–0.31)


### ⏳ Infrastructure / Hardware (cannot fix in code)
- [] PI2 missing Piper ONNX models (`ru_RU-irina-medium.onnx`, `.onnx.json`) — PI2 offline; install on next access
- [] PI1 missing `migrate_to_db.py` at expected path — PI1 frozen (demo); fix after demo
- [] PI1 `taris-web.service` not running — PI1 frozen (demo); fix after demo
- [] German voice models absent on both PIs (`de_DE-thorsten-medium.onnx`, `vosk-model-small-de`) — hardware task, install when Pi targets are accessible
- [] PI2 has no Whisper model (`ggml-base.bin`) — PI2 offline; install on next access
- [] Vosk WER regression on short audio (`audio_2026-03-08_08-34-23.ogg`) — WER 0.70 vs threshold 0.35; Pi-only (TariStation2 uses faster-whisper); tune model or adjust threshold when Pi is online

## 0.1 Update Documentation

1. Create `doc/howto_admin.md` - a proper standalone admin guide covering:
   - Configuration for both TariStation2 and SintAItion
   - Network setup, software stacks, memory tuning
   - All the performance optimizations from yesterday
2. Update `doc/howto_bot.md` (user guide) with any relevant user-facing changes
3. Create `doc/performance-report-2026-04-02.md` - performance report

4. Update `src/setup/load_system_docs.py` to use the new `howto_admin.md` instead of README + overview
5. ✅ Update `doc/architecture/openclaw-integration.md` with current config info (v2026.4.23)
6. Update uploaded user guide in Taris client

## 1. Access & Security

### 1.1 Role-Based Access Control (RBAC) �
Per-role command allowlists, System Chat branching, Developer role and menu.
→ [Full spec](doc/todo/1.1-rbac.md) · [Developer menu spec](doc/todo/1.3-developer-role.md)

- [x] `DEVELOPER_USERS` constant + `_is_developer()` helper (v2026.3.30)
- [x] `ADMIN_ALLOWED_CMDS` / `DEVELOPER_ALLOWED_CMDS` allowlists (v2026.3.30)
- [x] Role-aware `_handle_system_message()` with `_classify_cmd_class()` (v2026.3.30)
- [x] Dev Menu — `bot_dev.py`: Dev Chat, Restart/Log/Error/FileList/Security Log buttons (v2026.3.32)
- [x] `security_events` DB table + `log_security_event()` + `log_access_denied()` (v2026.3.32)
- [ ] Regression test — allowlist enforcement
- [ ] Configurable access rules (admin UI + config file); runtime policy updates without restart
### 1.3 Contact Book ✅ Implemented (v2026.3.30)
[] Add additional fields for contact
---
## 2. N8N Workflow — Campaign Email Broadcast ✅ Implemented (v2026.4.50)

Full spec: [doc/todo/2-n8n-campaign-workflow.md](doc/todo/2-n8n-campaign-workflow.md)

### ✅ Implemented (v2026.4.45 – v2026.4.50)
- [x] `bot_campaign.py` — campaign state machine (topic → filter → preview → send)
- [x] Agents menu in Telegram (advanced/admin users only)
- [x] N8N `Taris - Campaign Select` workflow (ID: `YF9eU2H2N3Nr4j3O`):
  - `Demo Mode?` IF branch (true → Demo Clients / false → GS Read Clients)
  - GS Read Clients from "клиенты" tab
  - OpenAI (native node, gpt-4o-mini) selects matching clients
  - GS Read Templates from "Шаблоны рассылки" — uses template if found
  - Merge Template: prefers GS template over AI-generated
  - Returns `{clients, template, count}` to Taris
- [x] N8N `Taris - Campaign Send` workflow (ID: `AjIB5izjiCunMcp6`):
  - **GS Append Queued**: writes `Status="Gesendet wird..."` to "Status рассылок" BEFORE each send
  - Send Email via Gmail (native Gmail node, OAuth2)
  - **GS Append Status**: writes `Status="sent"/"ERROR:..."` to "Status рассылок" AFTER each send
  - Both GS nodes: `onError=continueRegularOutput` (GS failure never blocks send)
- [x] Configurable `CAMPAIGN_FROM_EMAIL`, `CAMPAIGN_DEMO_MODE` env vars
- [x] Workflow files: `src/n8n/workflows/Taris - Campaign Select.json`, `Taris - Campaign Send.json`
- [x] Tests T50–T57: 40 unit tests passing (see `src/tests/test_campaign.py`)

### 🔲 Planned
- [ ] Status rows written before sending (in campaign-select response, not only in send)
- [ ] Generic Google Sheets link with filter pre-applied to campaign session
- [ ] CRM Telegram menu (§2.x)
- [ ] CRM Web UI (§2.x)

### 2.1 Advanced User Role ✅ Implemented (v2026.4.x)
- [x] `advanced` user role: can access Agents menu + campaign workflows
- [x] Admin can set user role (user/advanced/admin/developer) via admin menu
- [ ] Developer role: additional runtime debug options



### 2.2 Webhook Authentication — outbound + inbound 🔲

**Context:** `bot_n8n.py` uses `call_webhook()` as the primary trigger mechanism (standard HTTP POST, no SDK dependency). Basic auth schemes are implemented. This section tracks remaining auth work.

#### ✅ Implemented (v2026.4.45)
- `call_webhook(url, payload, *, auth_type, auth_token, ...)` — standard HTTP POST, no SDK coupling
- `_build_auth_headers()` — `bearer` / `apikey` / `hmac` / `basic` / `none`
- `verify_incoming_signature(body, header)` — HMAC-SHA256 inbound verification
- Config constants: `WEBHOOK_AUTH_TYPE`, `WEBHOOK_AUTH_TOKEN`, `WEBHOOK_AUTH_HEADER`, `WEBHOOK_HMAC_SECRET`

#### 🔲 Planned — Outbound
- [ ] **OAuth 2.0 client-credentials**: fetch token from `WEBHOOK_OAUTH_TOKEN_URL` using `WEBHOOK_OAUTH_CLIENT_ID` + `WEBHOOK_OAUTH_CLIENT_SECRET`; cache token until expiry; retry on 401
- [ ] Per-workflow auth override: store `{webhook_url, auth_type, auth_token}` in DB; admin can configure per-workflow credentials without restart

#### 🔲 Planned — Inbound (callbacks from workflow services → Taris)
- [ ] Bearer token validation on FastAPI `/webhook/callback` endpoint (currently no inbound auth)
- [ ] IP allowlist for trusted senders (configurable via `WEBHOOK_INBOUND_ALLOW_IPS` env var)
- [ ] Replay attack prevention: reject requests older than 5 min (timestamp header check)
- [ ] Rate limiting on inbound `/webhook/callback` endpoint (max N requests/min per IP)

#### 🔲 Planned — Admin UI
- [ ] Admin panel: list registered webhook URLs with auth status badge (🔒 / ⚠️ open)
- [ ] Admin panel: configure per-workflow auth type + token without restart



---

### 4.1 Local RAG Knowledge Base ✅ All done → See DONE.md (v2026.3.43 / v2026.4.14)
→ Implementation: **§24.6** (PicoClaw — FTS5-only) · **§25.6** (OpenClaw — Hybrid Tiered RAG)

### 4.2 Remote RAG Service (MCP) ✅ All done → See DONE.md (v2026.4.1 / v2026.4.38)
→ Implementation: **§25.6 Phase D** (OpenClaw) and **§26.5** (VPS)

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

### 6.1 Logging & Monitoring ✅ All done → See DONE.md (v2026.3.42 / v2026.4.40)

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

## 9. Flexible Storage Architecture 🔄

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
| Phase 2d | `documents` + `vec_embeddings` tables; `upsert_embedding` / `search_similar` | ✅ Done (v2026.4.13) |
| Phase 3 | `migrate_to_db.py` — JSON → adapter (idempotent) | ✅ |
| Phase 4 | Switch all reads to adapter; remove JSON writes | 🔄 In progress — notes/calendar/contacts/mail_creds ✅; voice_opts/registrations dual-write ⚠️; dynamic_users JSON-only ⚠️ |
| Phase 5 | `store_postgres.py` PostgreSQL adapter; test on OpenClaw | ✅ Done (v2026.4.13) |
| Phase 6 | RAG (§4.1) via `search_similar()`; conversation memory (§2.1) via `append_history()` | ✅ Done (v2026.4.13) |

- [x] `src/core/bot_db.py` schema + `init_db()` on startup — SQLite Phase 1 (v2026.3.30)
- [x] `src/core/store_base.py` — `DataStore` Protocol definition + `StoreCapabilityError`
- [x] `src/core/store.py` — `create_store()` factory + module-level `store` singleton
- [x] `src/core/store_sqlite.py` — full SQLite adapter incl. sqlite-vec optional vector support
- [x] `src/core/store_postgres.py` — PostgreSQL + pgvector adapter (OpenClaw) ✅ (v2026.4.13)
- [x] `src/core/bot_db.py` extended — `documents` table added to schema; `vec_embeddings` managed via `store_sqlite.py` (Phase 2d) (v2026.4.13)
- [x] `src/setup/install_sqlite_vec.sh` — install sqlite-vec wheel on Pi target (v2026.4.13)
- [x] `src/setup/migrate_to_db.py` — JSON → adapter migration (Phase 3, idempotent)
- [x] `src/setup/migrate_sqlite_to_postgres.py` — taris.db → PostgreSQL (Phase 5, was migrate_sqlite_to_pg.py; 316 rows migrated v2026.4.31)
- [ ] Tests T22 `sqlite_schema`, T23 `migration_idempotent`, T24 `vector_search_basic`, T25 `store_adapter_contract`, T26 `credential_encryption`
### 9.1 Storing of user data in the local database not in files
- [x] Notes reads from DB (`store.list_notes()`); file fallback preserved; double-write bug fixed (v2026.3.30)
- [x] Notes content stored in DB (`notes_index.content` column); `_load_note_text` reads DB first, file fallback; `_save_note_file` writes content to DB (v2026.3.31)
- [x] Calendar data stored in database — DB-primary via `store.save_event/load_events/delete_event`; JSON file write removed (v2026.3.31)
- [x] All kinds of memory (conversation context) stored in database — `chat_history` + `conversation_summaries` tables; cleared via Profile (v2026.3.30+5)
- [x] All user contacts stored in database — `store.save_contact / list_contacts / delete_contact / search_contacts` in `store_sqlite.py`
- [x] Migration scripts exist — `src/setup/migrate_to_db.py` idempotent JSON → DB (v2026.3.30)
- [x] Per-user preferences stored in DB — `user_prefs` table; `db_get_user_pref / db_set_user_pref` (v2026.3.31)
- [ ] Last interactions, opened UI and status of UI stored in database — not yet implemented
- [x] `src/setup/install_sqlite_vec.sh` — install sqlite-vec wheel on Pi target (v2026.4.13)
- [x] `src/setup/migrate_sqlite_to_postgres.py` — taris.db → PostgreSQL migration (was migrate_sqlite_to_pg.py; 316 rows migrated v2026.4.31)

## 10. Upload and using documents as Knowledges
- [x] FTS5 RAG context injection: `_docs_rag_context()` in `bot_access.py`; called from `_with_lang()` and `_with_lang_voice()`; caps at 2000 chars; guard on `RAG_ENABLED` and user docs present (v2026.3.30)
- [x] Upload and administration of documents (upload, view, delete, share to all, set title, share to other users) — `bot_documents.py` fully implemented with FTS5 chunking + optional vector embeddings (v2026.3.30)
- [x] Documents assigned to user or shared with all users — `is_shared` flag, `store.update_document_field()` (v2026.3.30)
- [x] Document deduplication on upload — hash check detects identical content; "Replace / Keep Both" confirmation shown (v2026.3.31) 🔲 _being deployed_
- [ ] Documents used as knowledgebase in multimodal RAG way (images, tables) — FTS5 text-only currently; no image/table extraction
- [ ] Criteria for comparing documents configurable in Admin panel
- [ ] Quality consistency check of created chunks after uploading

### 10.1 Short-, Middle- and Long-term Memories ✅ All done → See DONE.md (v2026.3.30+5 / v2026.3.31)

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

## 19. OpenClaw Platform 🔄 Core integration implemented

Taris runs as an additional deployment variant on OpenClaw (laptop / AI PC) alongside the PicoClaw (Raspberry Pi) variant.
→ Full deployment plan: **§25 Deployment Plan: OpenClaw (Laptop / AI X1 / Pi 5 8 GB / RK3588)**
→ Hardware specs and options: [doc/hw-requirements-report.md §1.3](doc/hw-requirements-report.md)
→ Integration architecture: [doc/architecture/openclaw-integration.md](doc/architecture/openclaw-integration.md)
→ Related project: [sintaris-openclaw](https://github.com/stas-ka/sintaris-openclaw) — Node.js AI gateway + `skill-taris` + MCP server

### 19.4 Pending ✅ All done → See DONE.md (v2026.3.29+10 / v2026.4.31)

## 21. Dynamic UI — Enhanced Screen DSL + JSON/YAML Loader �

Extend the existing Screen DSL with a declarative file loader that reads screen
definitions from YAML/JSON files. Zero RAM overhead; both renderers unchanged;
incremental migration from Python-coded screens.

→ [Research report](doc/research-dynamic-ui-scenarios.md) · [Spec](doc/todo/21-screen-dsl-loader.md)

### 21.6 Phase 6 — Visual Editor (OpenClaw only) 🔲

- [ ] Admin panel page: CodeMirror YAML editor + live preview pane
- [ ] `PUT /admin/screens/{id}` route to save edited YAML to `src/screens/`
- [ ] Auto-trigger `reload_screens()` on save

## 23. Research & Comparison — Hybrid RAG vs Google Grounding 🔲

Validate the Hybrid Tiered RAG architecture (Variant C) against Google's server-side Grounding and the Worksafety reference implementation. Use **Karpathy AutoResearch** (`karpathy/autoresearch`) as the autonomous evaluation framework — agent-driven experiments across three target architectures: Raspberry Pi (mini PC), OpenClaw on AI X1 (GPU), VPS.
→ [Concept paper](concept/rag-memory-architecture.md) · [Extended research](concept/rag-memory-extended-research.md) (§6b AutoResearch)

- [x] 23.1 OpenClaw on Laptop — Taris running locally via `sintaris-openclaw-local-deploy/` with `TARIS_HOME`, symlinks into `sintaris-pl/src/`; `skill-taris` connected ✅ (v2026.4.13)
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

### 25.4 Embedding Service ✅ All done → See DONE.md (v2026.4.13)

### 25.5 Voice Pipeline + NPU Acceleration ✅ All done → See DONE.md (v2026.3.28-openclaw / v2026.4.13)

### 25.6 RAG Implementation — Variant C (Hybrid Tiered RAG)
- [x] **Phase A — Memory System** ✅ → See DONE.md (v2026.3.31)
- [x] **Phase B — Enhanced RAG** ✅ → See DONE.md (v2026.3.30–v2026.4.13)
- [~] **Phase C — Document Management (one item open):**
  - [x] Upload/chunk, sharing, deduplication, PyMuPDF, per-user settings, admin-only docs, MCP UI → See DONE.md
  - [ ] Separate `doc_sharing` permission table — fine-grained per-user ACL → tracked in **§27.4**
- [x] **Phase D — Remote RAG + MCP** ✅ → See DONE.md (v2026.4.1)


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

---

## 27. Multimodal RAG 🔲

> **Hardware requirement:** GPU or Pi 5+ strongly recommended. CLIP/vision models are too slow for CPU-only inference at acceptable latency.
> **Status:** Design phase. No implementation started. Tracked separately from core RAG pipeline (§25.6).

### 27.1 Image Search (CLIP embeddings)

- [ ] **CLIP embedding service** — `src/core/bot_clip.py`; encode images to 512-dim vectors at upload time; store in `vec_embeddings` with `doc_type=image`
- [ ] **Image-aware chunker** — extract images from PDF/DOCX at upload; run CLIP encode; store metadata (page, caption if OCR available)
- [ ] **Hybrid image+text retrieval** — image query via CLIP cosine similarity; merged with FTS5 text results via RRF; `bot_rag.py` image branch
- [ ] **Admin toggle** — `CLIP_ENABLED` env var + admin UI toggle; graceful text-only fallback when disabled

### 27.2 Complex PDF Extraction (docling)

- [ ] **docling integration** — `pip install docling`; replace `PyMuPDF` for complex PDFs with tables/charts; output structured Markdown with preserved table layout
- [ ] **Table extraction** — docling Markdown tables → chunked as structured text; column headers preserved in each chunk for better FTS5 recall
- [ ] **Fallback chain** — docling (best) → PyMuPDF+fitz (fast) → pdfminer (text-only)

### 27.3 Vision API Fallback

- [ ] **Vision question answering** — when image chunk matched but no text context: call vision LLM (`GPT-4V` / `Gemini Vision`) with image + query; inject answer as synthetic RAG chunk
- [ ] **Admin config** — `VISION_LLM_PROVIDER` and `VISION_LLM_MODEL` in `bot_config.py`; cost guard: `VISION_MAX_CALLS_PER_DAY`

### 27.4 Per-User Document ACL (replaces §25.6 Phase C deferred item)

- [ ] **`doc_sharing` table** — `(id, doc_id, grantee_id, permission, granted_by, expires_at)` replaces `is_shared` flag for fine-grained per-user sharing
- [ ] **Migration** — convert existing `is_shared` rows to `doc_sharing` entries; keep backward compat for `is_shared IN (0,1,2)` during transition
- [ ] **Share UI** — "Share with user" flow in bot_documents.py: type user ID or pick from contacts; set permission level (view/edit/revoke); show share list
