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

## 1. Access & Security

### 1.1 Role-Based Access Control (RBAC) ✅ Implemented (v2026.4.50) → See DONE.md

### 1.2 Guest Users ✅ Implemented (v2026.4.73) → See DONE.md

### 1.3 Contact Book ✅ Implemented (v2026.3.30) → See DONE.md
- [ ] Add additional fields for contact (planned, not yet implemented)

---
## 2. N8N Workflow — Campaign Email Broadcast ✅ Implemented (v2026.4.50) → See DONE.md

### 🔲 Planned
- [ ] Status rows written before sending (in campaign-select response, not only in send)
- [ ] Generic Google Sheets link with filter pre-applied to campaign session
- [ ] CRM Telegram menu (§2.x)
- [ ] CRM Web UI (§2.x)

### 2.1 Advanced User Role ✅ Implemented (v2026.4.x) → See DONE.md
- [ ] Developer role: additional runtime debug options



### 2.2 Webhook Authentication — outbound + inbound 🔲

**Context:** `bot_n8n.py` uses `call_webhook()` as the primary trigger mechanism. Core auth implemented (v2026.4.45) → See DONE.md §2.2.

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

### 4.3 Remote KB via N8N MCP Server ✅ Implemented (v2026.4.75) — Phases 1–6 done → See DONE.md

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
→ Full hardware analysis: [doc/research/hw-requirements-report.md](doc/research/hw-requirements-report.md) · [doc/research/hardware-performance-analysis.md](doc/research/hardware-performance-analysis.md)

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



---

## 9. Flexible Storage Architecture ✅ Implemented (v2026.4.31) → See DONE.md

- [ ] Tests T22–T26 (sqlite_schema, migration, vector_search, adapter_contract, credential_encryption)
- [ ] Last interactions / active UI stored in DB (not yet implemented)

## 10. Upload and using documents as Knowledges
- [x] FTS5 RAG context injection: `_docs_rag_context()` in `bot_access.py`; called from `_with_lang()` and `_with_lang_voice()`; caps at 2000 chars; guard on `RAG_ENABLED` and user docs present (v2026.3.30)
- [x] Upload and administration of documents (upload, view, delete, share to all, set title, share to other users) — `bot_documents.py` fully implemented with FTS5 chunking + optional vector embeddings (v2026.3.30)
- [x] Documents assigned to user or shared with all users — `is_shared` flag, `store.update_document_field()` (v2026.3.30)
- [x] Document deduplication on upload — hash check detects identical content; "Replace / Keep Both" confirmation shown (v2026.3.31) 🔲 _being deployed_
- [ ] Documents used as knowledgebase in multimodal RAG way (images, tables) — FTS5 text-only currently; no image/table extraction
- [ ] Criteria for comparing documents configurable in Admin panel
- [ ] Quality consistency check of created chunks after uploading

### 10.1 Short-, Middle- and Long-term Memories ✅ All done → See DONE.md (v2026.3.30+5 / v2026.3.31)

## 11. Central Control Dashboard 💡 Planned

Primary control via voice — all assistant activities controllable from a unified dashboard.

- [ ] Central dashboard: all activities runnable and controllable from one place (voice + text input)
- [ ] UI switchable per voice between functional areas
- [ ] Activities stored in DB as structured entries + LLM context (deactivatable)

## 12. Voice Text Input — Unified Window 💡 Planned

- [ ] All text input fields in all application parts supportable via voice

## 13. Smart CRM 💡 Planned

- [ ] Implement open functions from [CRM requirements spec](doc/archive/concept/crm-requirements/)
- [ ] All windows controllable per voice; smart input with automatic field population
→ [Full CRM platform vision](doc/todo/8.4-crm-platform.md)

## 14. Developer Board 💡 Planned

- [ ] Developer board to extend/update/remove bot functionality via agent-based editing

## 15. Calendar, E-Mail, Drive Integration 💡 Planned

- [ ] Google Calendar, Gmail, Google Drive integration
- [ ] Yandex Calendar, Mail, Disk integration

## 16. Personal Assistant Functions 💡 Planned

- [ ] Implement open functions from [KIM packages spec](doc/archive/concept/crm-requirements/KIM_PACKAGES.md)

> **§17 and §18 moved to OBSOLETE.md** — Max messenger UI (superseded by Web UI) and ZeroClaw (hardware not viable)

## 19. OpenClaw Platform 🔄 Core integration implemented

Taris runs as an additional deployment variant on OpenClaw (laptop / AI PC) alongside the PicoClaw (Raspberry Pi) variant.
→ Full deployment plan: **§25 Deployment Plan: OpenClaw (Laptop / AI X1 / Pi 5 8 GB / RK3588)**
→ Integration architecture: [doc/architecture/openclaw-integration.md](doc/architecture/openclaw-integration.md)
→ Related project: [sintaris-openclaw](https://github.com/stas-ka/sintaris-openclaw) — Node.js AI gateway + `skill-taris` + MCP server

### 19.4 Pending ✅ All done → See DONE.md (v2026.3.29+10 / v2026.4.31)

## 21. Dynamic UI — Enhanced Screen DSL + JSON/YAML Loader ✅ Implemented (v2026.4.50) → See DONE.md (§21.1–21.5)

### 21.6 Phase 6 — Visual Editor (OpenClaw only) 🔲

- [ ] Admin panel page: CodeMirror YAML editor + live preview pane
- [ ] `PUT /admin/screens/{id}` route to save edited YAML to `src/screens/`
- [ ] Auto-trigger `reload_screens()` on save

## 23. Research Backlog — AutoResearch & RAG Comparison 💡 Future

> Not started. Planned for a dedicated research sprint.
→ [Concept paper](doc/archive/concept/rag-memory-architecture.md) · [Extended research](doc/research/rag-memory-extended-research.md)

- [x] 23.1 OpenClaw on Laptop — Taris running locally; `skill-taris` connected ✅ (v2026.4.13)
- [ ] 23.2 n8n + PostgreSQL clone on Laptop — replicate Worksafety orchestration stack for comparison baseline
- [ ] 23.3 Karpathy AutoResearch — install nanochat + autoresearch on OpenClaw (AI X1); verify GPU access
- [ ] 23.4 Hybrid RAG vs Google Grounding — bind OpenClaw to Gemini Grounding API; evaluate vs local FTS5+vector
- [ ] 23.5–23.12 — full evaluation backlog (Worksafety clone, AutoResearch runs, Pareto analysis, nanochat training)

---

## 24. Deployment Plan: PicoClaw (Raspberry Pi 3 B+) 🔲

> **Hardware:** BCM2837B0 · 4× Cortex-A53 @ 1.4 GHz · 1 GB LPDDR2. RAM budget at full load: ~715 MB (critical).
> **Voice latency baseline:** ~30–60 s; achievable after tuning: ~20–25 s. ≤2 s target is **not achievable** (no NPU/GPU).
> **Backend:** `STORE_BACKEND=sqlite` + sqlite-vec. **LLM:** Cloud only (no local inference on Pi 3).
> → Hardware deep-dive: [doc/research/hardware-performance-analysis.md](doc/research/hardware-performance-analysis.md) · [doc/research/hw-requirements-report.md §1.1](doc/research/hw-requirements-report.md)

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
- [ ] Phase A — Memory System: add `memory_summaries`/`memory_long` tables to `store_sqlite.py`; implement `compact_short_to_middle()` / `compact_middle_to_long()` (see [doc/archive/concept/rag-memory-architecture.md §6.3](doc/archive/concept/rag-memory-architecture.md))
- [ ] Phase B — FTS5 RAG: `classify_query()` adaptive routing; FTS5 BM25 search only (no vectors — RAM constraint); `rag_log` table
- [ ] **Do NOT** enable `STORE_VECTORS=on` on Pi 3 unless `free -m` under full load confirms ≥150 MB available
- [ ] Embedding model (`all-MiniLM-L6-v2`): load on demand and free after use (`EMBED_KEEP_RESIDENT=0`)

### 24.7 Known Constraints
- Voice ≤2 s target: ❌ impossible on Pi 3 B+ (no NPU/GPU; minimum requires ≥13 TOPS — see §25 for upgrade)
- Local LLM: ❌ not viable; Qwen2-0.5B only as emergency offline fallback at ≤0.4 tok/s
- Vector search: ⚠️ only if free RAM ≥150 MB confirmed; otherwise FTS5-only RAG

---

## 26. Deployment Plan: VPS (Cloud) ✅ Implemented (v2026.4.50) → See DONE.md (§26.1–26.6)

### 26.6 Backups ⚠️ Open items
- [ ] Install cron job on VPS: `(crontab -l; echo '0 3 * * * /opt/taris-docker/backup-taris-vps.sh >> /var/log/taris-backup.log 2>&1') | crontab -`
- [ ] HNSW index (optional perf): `CREATE INDEX CONCURRENTLY ON documents USING hnsw (embedding vector_cosine_ops);`

### 26.7 Security Hardening ⚠️ Open items
- [ ] SSH key-only login (currently password auth enabled)
- [ ] fail2ban check on VPS

### 26.8 Scaling
- ✅ ≤50 users: single Docker instance sufficient

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

---

## 29.4 EspoCRM Two-Way Contact Sync 🔲

> 29.1–29.3 implemented — see DONE.md §29

### 29.4 EspoCRM Two-Way Contact Sync 🔲

Full bidirectional sync: Taris contact changes → N8N → EspoCRM; EspoCRM changes → N8N → Taris.
- On `_save_contact()` / `_delete_contact()`: call `_maybe_sync_to_crm(contact, action)`
- Inbound merge: `find_contact_by_email_or_phone()` → update existing or create new
- Config: `CRM_SYNC_ENABLED`, `CRM_SYNC_DEDUPE_FIELD` (email/phone)

**Depends on:** §28.3 + §28.4  
**Files:** `features/bot_contacts.py`, `core/store_postgres.py`, `core/bot_config.py`  
**Tests:** T213

---

## 30. OpenClaw Architecture Flexibility 🔲 Planned (background / incremental)

> Refactoring work — no behavior change. Incremental, low-risk, can run in parallel with other features.

### 30.1 LLM Provider Plugin Extraction 🔲

Extract the 8 inline provider functions from `core/bot_llm.py` (800+ lines) into a `src/core/llm_providers/` package with a shared `LLMProvider` Protocol.
- One file per provider: `ollama.py`, `openclaw.py`, `openai_p.py`, `taris.py`, …
- `_DISPATCH` becomes a thin wrapper loading from registry
- Each provider independently unit-testable and replaceable

**Files:** `core/bot_llm.py` → `core/llm_providers/*.py`  
**Tests:** T220 (each provider returns non-empty string from mock)

### 30.2 STT Provider Protocol 🔲

Extract STT implementations from the 1600-line `bot_voice.py` into `src/core/stt_providers/` with a shared `STTProvider` Protocol.
- `VoskSTT` and `FasterWhisperSTT` as swappable objects
- `bot_voice.py`: `stt = stt_factory(STT_PROVIDER)` → `result = stt.transcribe(pcm)` (no more if/else chains)

**Files:** `features/bot_voice.py` → `core/stt_providers/*.py`  
**Tests:** T221

### 30.3 Variant as Composition (`VariantConfig` dataclass) 🔲

Replace scattered `if DEVICE_VARIANT == "openclaw"` checks with a single `VariantConfig` object built at startup.
```python
VARIANT_REGISTRY = {
    "picoclaw": VariantConfig(stt_engine="vosk", llm_default="taris", has_pgvector=False, ...),
    "openclaw": VariantConfig(stt_engine="faster_whisper", llm_default="ollama", has_pgvector=True, ...),
}
VARIANT = VARIANT_REGISTRY[DEVICE_VARIANT]
```
Adding a new variant = one dict entry, no code changes.

**Files:** new `core/device_variant.py`, `core/bot_config.py`, incremental updates across modules  
**Tests:** T222
