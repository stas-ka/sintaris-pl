# Pico Bot — TODO & Roadmap

**Legend:** ✅ Done · 🔄 In progress · 🔲 Planned · 💡 Idea / future

---

## 0. Known bugs
### 0.7 Add new Contact errors
Showing title of cancel button as "btn_cancel" 
### 0.8 Errors in the profile window
After input new password ❌ Error: could not change password.
### Bugs — Fixed in this Sprint ✅

| Bug | Fix | Version |
|---|---|---|
| 0.1 Profile menu silent crash | `try/except` guard around deferred import in `_handle_profile()` | v2026.3.29 |
| 0.2 Hardcoded bot name | `BOT_NAME` constant + `{bot_name}` in `strings.json` | v2026.3.29 |
| 0.3 Note edit loses content | Append / Replace mode buttons in note edit flow | v2026.3.29 |
| 0.4 Calendar voice deleted | Fixed orphan TTS cleanup guard — only deletes spinner messages | v2026.3.29 |
| 0.5 Calendar console ignores add | Intent classifier calls `_finish_cal_add()` directly | v2026.3.29 |
| 0.6 System Chat no role guards | `ADMIN_ALLOWED_CMDS` / `DEVELOPER_ALLOWED_CMDS` + `_classify_cmd_class()` | v2026.3.30 |

---

## 1. Open Issues &amp; Roadmap

### 1.0 Profile Redesign 🔲
Profile must be a self-service hub — edit name, email, change password, open mailbox — in both Telegram and Web UI.
→ [Full spec](doc/todo/1.1-rbac.md)

- [ ] Crash guard: `try/except` in `_handle_profile()` around deferred import (Telegram)
- [ ] Profile inline keyboard: Edit name / Email settings / Change password / Open mailbox
- [ ] `GET /profile` + `POST /profile/name|email` routes in `bot_web.py`
- [ ] Add `profile.html` template; link from `base.html` nav sidebar
- [ ] Playwright test: `GET /profile` returns 200

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

### 2.1 Conversation Memory System 🔲

- [ ] Store per-user conversation history (sliding window, default 15 messages)
- [ ] Inject last N messages as context into LLM prompt
- [ ] Optional: persist across restarts (JSON / SQLite)

---

## 3. LLM Provider Support

### 3.1 Multi-LLM Provider Support 🔄
OpenRouter ✅ · OpenAI direct ✅ · YandexGPT / Gemini / Anthropic / local llama.cpp 🔲

- [ ] `LLM_PROVIDER` env-var switch in `bot.env`
- [ ] YandexGPT client with API key from `bot.env`

### 3.2 Local LLM — Offline Fallback 🔲
Emergency fallback via `llama.cpp`. Pi 3: Qwen2-0.5B (~1 tok/s); Pi 4/5: Phi-3-mini.
→ See: `doc/hardware-performance-analysis.md` §8.9

- [ ] Build `llama.cpp` on Pi; create `picoclaw-llm.service`; `try/except` fallback in `_ask_picoclaw()`
- [ ] Label fallback responses with `⚠️ [local fallback]`

---

## 4. Content & Knowledge

### 4.0 Contact Book ✅ Implemented (v2026.3.30)

---

### 4.1 Local RAG Knowledge Base 🔲

- [ ] Embed documents with `all-MiniLM-L6-v2`
- [ ] Vector similarity search → inject top-k context into LLM prompt
- [ ] Commands: `/rag_on`, `/rag_off`
- [ ] Storage: `~/.picoclaw/knowledge_base/` (documents + `embeddings.db`)

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

- [ ] Structured log categories: `assistant.log`, `security.log`, `voice.log`
- [ ] Admin Telegram UI: view last N log lines per category
- [ ] Log rotation (`logrotate` config)

### 6.2 Host–Project Synchronization 🔲

- [ ] rsync-based sync script `src/` → Pi
- [ ] Git-based deployment hook

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

### 8.5 NiceGUI Integration 💡

Replace Jinja2 with NiceGUI for richer interactivity — evaluate RAM footprint on Pi 3 first.

- [ ] Evaluate NiceGUI RAM footprint (~60 MB vs FastAPI ~25 MB); prototype Voice Opts page
- [ ] If viable: migrate pages incrementally behind feature flag

---

## 9. SQLite Data Layer 🔲

Migrate from per-user JSON files to `pico.db`. `bot_db.py` created (v2026.3.30); migration pending.
→ [Full spec, schema & migration plan](doc/todo/9-sqlite-data-layer.md)

- [x] `src/bot_db.py` created + `init_db()` called on startup (v2026.3.30)
- [ ] Dual-write wrappers (Phase 2): `_upsert_registration`, `_save_voice_opts`, `_cal_save`, mail creds
- [ ] `src/setup/migrate_to_db.py` script (Phase 3)
- [ ] Tests T22 `sqlite_schema` + T23 `migration_idempotent`

## 10. Upload and using documents as Knowlegdes
- Function to upload and administration documents (upload, view,  delete , move to directory , set title, set hash/label, share to other users in system)
- Using documents as knowledgebase in chat in multimodal RAG way
- documents can be contain text, images, tables

## 11. Central control dashboard (primary per voice)
- IMplementing central dashboard to contorol and run all activities of the asstsiant
- all functions can be runned and controled from this board. Steering can be do per voice or per text input.
- ui shall be switchable  per voice to functional ui part to run activities

## 12. Input all textes in all application parts per voice
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

## 19. Using OpenClaw instead PicoClaw