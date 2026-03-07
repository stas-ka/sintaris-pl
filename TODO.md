# Pico Bot — TODO & Roadmap

**Legend:** ✅ Done · 🔄 In progress · 🔲 Planned · 💡 Idea / future

---

## 1. Access & Security

### 1.1 Telegram User Registration Workflow ✅

✅ **Implemented** (v2026.3.15-rc1). Unknown users enter a registration flow on `/start`; admins approve/block via inline buttons; pending count badge shown on admin panel button.

### 1.2 Role-Based Access Control (RBAC) 🔲

| Role | Permissions |
|---|---|
| **Admin** | Full system control — users, environment, LLM providers, backups, security policy |
| **Developer** | Develop/deploy skills, test features, debug tools; bot restart; cannot change security policy |
| **User** | Chat with assistant, voice assistant, personal notes, knowledge base |
| **Guest** | Limited access until admin approves registration |

- [ ] Implement role storage and enforcement in bot
- [ ] Admin-only commands gated by role check
- [ ] Developer: restart command available alongside Admin
- [ ] Guest mode: only `/start` and a "registration sent" message

### 1.3 Central Security Layer — MicoGuard 🔲

Centralised policy enforcement module sitting between users and all bot actions.

- [ ] Role validation on every command/callback
- [ ] Security event logging (`security.log`)
- [ ] Configurable access rules (admin UI + config file)
- [ ] Runtime policy updates without restart
- [ ] Architecture: `User → MicoGuard → LLM / Tools / System`

---

## 2. Conversation & Memory

### 2.1 Conversation Memory System 🔲

- [ ] Store per-user conversation history
- [ ] Sliding window: configurable `max_memory_messages` (default 15)
- [ ] Inject last N messages as context into LLM prompt
- [ ] Optional: persist memory across bot restarts (JSON / SQLite)
- [ ] Optional: session-based (in-memory only) mode as lighter alternative

---

## 3. LLM Provider Support

### 3.1 Multi-LLM Provider Support 🔄

| Provider | Status |
|---|---|
| OpenRouter (via picoclaw) | ✅ Default, running |
| YandexGPT | 🔲 Planned — add all model variants + API key config |
| OpenAI (direct) | 🔲 Planned |
| Gemini | 🔲 Planned |
| Anthropic | 🔲 Planned |
| Local LLM (llama.cpp) | 🔲 See §3.2 |

- [ ] Add `LLM_PROVIDER` env-var switch in `bot.env`
- [ ] Implement YandexGPT client with API key from `bot.env`
- [ ] Admin UI: show active provider + allow switching

### 3.2 Local LLM — Offline Fallback 🔲

Run a local `llama.cpp` model on the Pi as fallback when OpenRouter is unavailable.

- See full analysis: `doc/hardware-performance-analysis.md` §8.9
- Pi 3 B+: Qwen2-0.5B Q4 (~350 MB, ~1 tok/s) — emergency fallback only (~90 s/query)
- Pi 4 B (4 GB): Phi-3-mini Q4 (~2.5 GB, ~2 tok/s) — usable fallback
- Pi 5 (8 GB): Llama-3.2-3B Q4 (~2 GB, ~5 tok/s) — good fallback

Tasks:
- [ ] Build `llama.cpp` on target host, store on USB SSD
- [ ] Download appropriate model to `/mnt/ssd/models/`
- [ ] Create `picoclaw-llm.service` systemd unit
- [ ] Implement `_call_picoclaw()` with `try/except` + local HTTP redirect (`localhost:8080`)
- [ ] Label fallback responses with `⚠️ [local fallback]`

---

## 4. Content & Knowledge

### 4.1 Markdown Notes System ✅ Implemented (v2026.3.18)

### 4.2 Local RAG Knowledge Base 🔲

Lightweight offline-capable knowledge base for personal/technical documents.

```
/knowledge_base/
  documents/
  embeddings.db
```

- [ ] Embed documents with a small embedding model (e.g. `all-MiniLM-L6-v2`)
- [ ] Vector similarity search on user query
- [ ] Inject retrieved context into LLM prompt
- [ ] Commands: `/rag_on`, `/rag_off`
- [ ] Query flow: `question → vector search → context → LLM answer`
- [ ] Example use cases: personal notes, local manuals, family info, technical docs

---

## 5. Voice Pipeline Optimization

### 5.1 Measured baseline (Pi 3 B+, March 2026)

| Stage | Time | Status |
|---|---|---|
| Download OGG from Telegram | ~0 s | ✅ fine |
| OGG → 16 kHz PCM (ffmpeg) | ~1 s | ✅ fine |
| Speech-to-Text (Vosk `vosk-model-small-ru`) | **~15 s** | ❌ bottleneck |
| LLM (picoclaw → OpenRouter) | ~2 s | ✅ fine |
| TTS (Piper `ru_RU-irina-medium`) | **~40 s** | ❌ bottleneck |
| **Total** | **~58 s** | ❌ target: <15 s |

### 5.2 Active voice optimisations ✅

| Opt | Bot menu toggle | Impact |
|---|---|---|
| Silence strip (ffmpeg `silenceremove`) | `silence_strip` | ✅ STT −6 s |
| 8 kHz sample rate for Vosk | `low_sample_rate` | ✅ STT −7 s |
| Pre-warm Piper ONNX cache | `warm_piper` | ✅ TTS cold-start −15 s |
| Parallel TTS thread (text-first UX) | `parallel_tts` | ✅ text visible in ~3 s |
| Per-user audio 🔊/🔇 toggle | `user_audio_toggle` | ✅ skip TTS entirely |
| Piper model pinned to RAM (`/dev/shm`) | `tmpfs_model` | ✅ TTS load −13 s |
| ffmpeg highpass + dynaudnorm pre-filter | always on | ✅ STT quality |
| Vosk confidence filtering (`[?word]`) | always on | ✅ STT accuracy |
| `TTS_MAX_CHARS = 600` | constant | ✅ balanced audio length |

### 5.3 Planned improvements ✅ Implemented (v2026.3.19)

All items added as optional voice opts toggles (all default OFF, existing behaviour unchanged):
- **`vad_prefilter`** — webrtcvad noise gate before Vosk STT
- **`whisper_stt`** — whisper.cpp tiny model instead of Vosk (needs binary + `~/.picoclaw/ggml-tiny.bin`)
- **`piper_low_model`** — ru\_RU-irina-low.onnx for faster TTS (needs model download)
- **`persistent_piper`** — keepalive Piper subprocess holds ONNX in page cache

### 5.4 Effort vs. impact summary

| # | Change | Effort | Expected saving | Cumulative total |
|---|---|---|---|---|
| ✅ 1 | Silence strip | Low | STT −6 s | 52 s |
| ✅ 2 | TTS_MAX_CHARS tuning | Low | TTS varies | — |
| ✅ 3 | 8 kHz sample rate | Low | STT −7 s | 45 s |
| ✅ 4 | warm_piper + tmpfs_model | Low | TTS cold −15 s | 30 s |
| ✅ 5 | Parallel TTS thread | Medium | text in ~3 s | text fast |
| 🔲 6 | VAD pre-filter | Low | STT −3 s | 27 s |
| 🔲 7 | whisper.cpp STT | Medium | STT −11 s | ~16 s |
| 🔲 8 | Piper low model | Low | TTS −13 s | ~14 s |
| 🔲 9 | Persistent Piper Popen | High | TTS −20 s | ~10 s |

---

## 6. Infrastructure & Operations

### 6.1 Logging & Monitoring 🔲

- [ ] Structured log categories: `assistant.log`, `security.log`, `voice.log`
- [ ] Admin Telegram UI: view last N log lines per category
- [ ] Admin command: `/logs [category] [n]`
- [ ] Optional: log rotation (`logrotate` config)

### 6.2 Host–Project Synchronization 🔲

Synchronize between local development machine and target Raspberry Pi.

- [ ] rsync-based sync script for `src/` → Pi
- [ ] Git-based deployment hook
- [ ] Archive export for offline transfer
- Covers: source code, scripts, configs, env templates, service files

### 6.3 Backup System ✅

✅ **Implemented**. Scripts: `src/setup/backup_image.sh` (dd|zstd + SHA-256), `src/setup/install.sh` (fresh-install bootstrap), `src/setup/update.sh` (incremental update), `src/setup/backup_nextcloud.sh` (WebDAV upload/download/prune). Dependency manifests in `deploy/`.

#### 6.3 Backup Policy

| Location | What to store |
|---|---|
| **GitHub** | Source code, deploy scripts, config templates, documentation |
| **Pi (host)** | Runtime data, live configs, secrets, logs, databases |
| **Nextcloud** | Full image backups, recovery bundles, log archives |

Rules:
- Never commit secrets to GitHub
- Only reproducible, sanitized artifacts in version control
- Use dated versioned filenames: `mico-recovery-bundle-2026-03-07.tar.gz`

### 6.4 Update & Deployment Workflow

- [x] `doc/update_strategy.md` created — covers SOP, rollback, parallel deploy, service restart timing
- [ ] `src/setup/notify_maintenance.py` — pre-restart user notification script (see §3.1 of update_strategy.md)
- [ ] `NOTIFY_USERS_ON_UPDATE` flag in `bot.env` — ping approved users on bot startup after version bump
- [ ] Feature flags pattern in `bot.env` for gradual rollout

---

- [ ] Multi-user knowledge graph
- [ ] Long-term AI memory (persistent across sessions, per user)
- [ ] Smart home integration (Home Assistant, MQTT)
- [ ] Multi-device access (same user on multiple Telegram accounts or devices)
- [ ] USB SSD as local LLM host — full setup (see `doc/hardware-performance-analysis.md` §8)
- [ ] Pi 4 B upgrade — drops total latency from ~58 s to ~15 s
- [ ] Pi 5 + NVMe upgrade — ~8 s total latency, full local LLM viable
