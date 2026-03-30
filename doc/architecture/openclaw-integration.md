# Taris — OpenClaw Variant

**Version:** `2026.3.28` · **Last updated:** March 2026  
→ Architecture index: [architecture.md](../architecture.md)  
→ System overview: [overview.md](overview.md)  
→ PicoClaw variant: [picoclaw.md](picoclaw.md)  
→ Deployment guide: [deployment.md](deployment.md)  
→ Install guide: [../install-new-target.md §Part B](../install-new-target.md)

---

## Overview

The **OpenClaw variant** runs Taris on a laptop or x86_64 PC alongside the `sintaris-openclaw` AI gateway. It uses better STT (faster-whisper), a local offline LLM (Ollama), PostgreSQL storage, and exposes a REST API for skill integration.

```
DEVICE_VARIANT=openclaw
```

### Ecosystem Projects (OpenClaw setup)

| Project | Role | Location | Docs |
|---------|------|----------|------|
| **[sintaris-pl](https://github.com/stas-ka/sintaris-pl)** ← *this repo* | AI voice assistant: Telegram + Web UI + voice | `~/projects/sintaris-pl/` | [architecture.md](../architecture.md) |
| **[sintaris-openclaw](https://github.com/stas-ka/sintaris-openclaw)** | Node.js AI gateway (`@suppenclaw_bot`), skills hub, MCP server | `~/projects/sintaris-openclaw/` | [sintaris-openclaw/docs/](https://github.com/stas-ka/sintaris-openclaw/tree/main/docs) |
| **sintaris-openclaw-local-deploy** | Dev launcher — symlinks into `sintaris-pl/src/`, separate `TARIS_HOME` | `~/projects/sintaris-openclaw-local-deploy/` | `run_all.sh`, `run_web.sh` |

Both `sintaris-pl` and `sintaris-openclaw` run on the same machine in the OpenClaw variant.

### Integration Architecture

```
┌──────────────────────────────────────────────────────────┐
│  sintaris-pl  (Taris AI Voice Assistant)                 │
│                                                          │
│  DEVICE_VARIANT=openclaw                                 │
│  LLM_PROVIDER=ollama  (or openclaw)                      │
│  REST API: GET /api/status · POST /api/chat              │
│  Telegram bot: @taris_bot                                │
│  Web UI: http://localhost:8080                           │
└──────────────────────┬───────────────────────────────────┘
                       │  Bearer token (TARIS_API_TOKEN)
                       │  ↕  bidirectional
┌──────────────────────▼───────────────────────────────────┐
│  sintaris-openclaw  (OpenClaw AI Gateway)                │
│                                                          │
│  Telegram bot: @suppenclaw_bot                           │
│  Port: 18789 (gateway)                                   │
│  Skills:                                                 │
│    skill-taris    → POST /api/chat to sintaris-pl        │
│    skill-postgres → pgvector RAG (1665 chunks)           │
│    skill-n8n      → N8N workflow automation              │
│    skill-espocrm  → EspoCRM CRM integration              │
│    skill-nextcloud→ Nextcloud file storage               │
└──────────────────────────────────────────────────────────┘
```

### What runs on the Laptop

```
systemd --user
  ├── taris-web.service    ← Web UI + REST API on :8080
  ├── taris-voice.service  ← voice daemon (optional)
  └── ollama.service       ← local LLM server on :11434 (optional)

Telegram bot runs via the same taris-web.service (or separately)
```

---

## PicoClaw vs OpenClaw Comparison

| Feature | PicoClaw (Raspberry Pi) | OpenClaw (Laptop/PC) |
|---------|------------------------|---------------------|
| `DEVICE_VARIANT` | `picoclaw` | `openclaw` |
| Hardware | Raspberry Pi 3/4/5 | x86_64 laptop / AI PC |
| STT (hotword) | Vosk small-ru (48MB) | Vosk small-ru (48MB) |
| STT (commands) | Vosk small-ru | **faster-whisper base** (300MB) |
| TTS | Piper ONNX (offline) | Piper ONNX (offline) |
| Default LLM | `taris` → OpenRouter | `ollama` → local Qwen2 |
| Alternative LLM | openai, yandexgpt, gemini… | openclaw gateway, openai… |
| Local offline LLM | llama.cpp (taris-llm.service) | Ollama (:11434) |
| Storage | SQLite | SQLite or PostgreSQL+pgvector |
| REST API (`/api/*`) | ❌ not needed | ✅ Bearer token auth |
| `skill-taris` integration | ❌ | ✅ via sintaris-openclaw |
| Skills / tools | None | N8N, CRM, Files, RAG |
| Session context | Stateless | ✅ `--session-id taris` |
| RAG / knowledge | SQLite FTS5 | pgvector (1665 chunks, 1536-dim) |
| GPU acceleration | ❌ (no GPU on Pi) | Optional (CUDA) |
| LLM call via subprocess | `taris agent -m` | `openclaw agent -m --json` |
| Latency (LLM) | ~1–5s (Pi 3/4 + OpenRouter) | ~1–2s (Ollama qwen2:0.5b) |

### LLM Subprocess Differences

| Property | PicoClaw (`_ask_taris`) | OpenClaw (`_ask_openclaw`) |
|----------|------------------------|--------------------------|
| Command | `taris agent -m "<prompt>"` | `openclaw agent -m "<prompt>" --json --session-id taris` |
| Output format | Plaintext (ANSI-stripped) | JSON (`content`/`text`/`response` keys) → plaintext fallback |
| Skills/tools | None | N8N, PostgreSQL/pgvector, EspoCRM, Nextcloud, Taris itself |
| RAG support | ❌ | ✅ via `skill-postgres` (pgvector) |
| Session context | ❌ (stateless) | ✅ persistent context in gateway |
| Availability | Always (binary present) | Only when `openclaw-gateway.service` running |

---

## LLM Fallback Chain

```
LLM_PROVIDER=openclaw
        │
        ▼  FileNotFoundError (binary not found) or RuntimeError
        │
LLM_PROVIDER=taris (picoclaw binary)
        │
        ▼  LLM_LOCAL_FALLBACK=1 or ~/.taris/llm_fallback_enabled present
        │
Ollama (local, :11434)   — or —   llama.cpp (:8081)
```

Fallback is transparent: on Pi without OpenClaw, `LLM_PROVIDER=openclaw` automatically falls back to `taris` — no code changes needed.

---

## STT Configuration

### Hybrid STT Architecture

The OpenClaw variant uses a **hybrid STT approach**:
- **Hotword detection**: Vosk (streaming, real-time, low-latency — always Vosk)
- **Command recognition**: faster-whisper (batch mode, after hotword triggers — better accuracy)

### STT Provider Comparison (i7-2640M, no GPU)

| Engine | Model | WER (Russian) | RTF | RAM | Recommendation |
|--------|-------|--------------|-----|-----|----------------|
| `vosk` | small-ru (48MB) | ~15–20% | ~0.1 | 200MB | Pi 3/4 only |
| `faster_whisper` | tiny | ~12–16% | ~0.15–0.3 | 150MB | Minimal HW |
| `faster_whisper` | base | ~8–12% | ~0.3–0.5 | 300MB | **Recommended OpenClaw** |
| `faster_whisper` | small | ~5–8% | ~0.8–1.2 | 500MB | Good laptop |
| `faster_whisper` | medium | ~3–5% | ~2.5–4.0 | 1.5GB | Fast CPU/GPU |

**Default for `DEVICE_VARIANT=openclaw`:** `STT_PROVIDER=faster_whisper`, `FASTER_WHISPER_MODEL=base`

### STT Configuration in `bot.env`

```bash
STT_PROVIDER=faster_whisper        # vosk | faster_whisper | whisper_cpp
FASTER_WHISPER_MODEL=base           # tiny | base | small | medium | large-v3
FASTER_WHISPER_DEVICE=cpu           # cpu | cuda
FASTER_WHISPER_COMPUTE=int8         # int8 | float16 | float32
```

### Install faster-whisper

```bash
bash src/setup/setup_voice_openclaw.sh   # step 6/6 installs faster-whisper
# or:
pip install faster-whisper
```

### STT Benchmark

```bash
python3 src/tests/benchmark_stt.py --all
python3 src/tests/benchmark_stt.py --model base small --verbose
```

→ Source: `src/tests/benchmark_stt.py`

---

## LLM Configuration

### Recommended: Ollama (offline, no API key needed)

```bash
# Install Ollama + pull default model:
bash src/setup/setup_llm_openclaw.sh

# In bot.env:
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2:0.5b     # or: llama3.2:1b, phi3:mini, mistral:7b
OLLAMA_URL=http://127.0.0.1:11434
LLM_LOCAL_FALLBACK=1
```

### Ollama Model Guide (i7-2640M, 4 cores, 7.6GB RAM, no GPU)

| Model | Size | Speed | Quality | Pull command |
|-------|------|-------|---------|-------------|
| `qwen2:0.5b` | 512MB | ~1–2s | Simple commands | `ollama pull qwen2:0.5b` |
| `llama3.2:1b` | 1.3GB | ~3–5s | Better reasoning | `ollama pull llama3.2:1b` |
| `phi3:mini` | 2.3GB | ~5–10s | Strong small model | `ollama pull phi3:mini` |
| `mistral:7b` | 4.1GB | ~15–30s | Best quality | `ollama pull mistral:7b` |

→ Source: `src/setup/setup_llm_openclaw.sh`  
→ Ollama: https://ollama.ai

### Alternative: OpenClaw AI Gateway

When `LLM_PROVIDER=openclaw`, LLM calls go through the `sintaris-openclaw` gateway subprocess:

```bash
LLM_PROVIDER=openclaw
OPENCLAW_BIN=~/.local/bin/openclaw   # or /usr/local/bin/openclaw
```

This routes requests via `openclaw agent -m "<prompt>" --json --session-id taris`, giving access to the gateway's full skill set (N8N, pgvector RAG, EspoCRM, Nextcloud).

> ⚠️ **Loop prevention:** if `LLM_PROVIDER=openclaw`, `skill-taris` in sintaris-openclaw must NOT relay LLM requests back to Taris — this creates an infinite loop. Use `skill-taris` only for data queries (notes, calendar, status).

### LLM Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `[LLM] openai failed: OPENAI_API_KEY not set` | Empty key in bot.env | Set `LLM_PROVIDER=ollama` or add key |
| `[LLM] ollama failed: connection refused` | Ollama not running | `systemctl --user start ollama` |
| Empty LLM response | Provider not configured | Check `LLM_PROVIDER` in bot.env |
| Slow responses | Heavy model, no GPU | Use `qwen2:0.5b` or cloud API |

---

## REST API

The REST API is active only when `DEVICE_VARIANT=openclaw`. It is used by `skill-taris` in `sintaris-openclaw`.

| Method | Endpoint | Auth | Body | Response |
|--------|----------|------|------|----------|
| GET | `/api/status` | Bearer Token | — | `{"status":"ok","version":"...","provider":"..."}` |
| POST | `/api/chat` | Bearer Token | `{"message":"...","timeout":60}` | `{"reply":"..."}` |

### Setup API Token

```bash
# Generate token
TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Set in Taris
echo "TARIS_API_TOKEN=$TOKEN" >> ~/.taris/bot.env

# Set in sintaris-openclaw skill-taris
echo "$TOKEN" > ~/.openclaw/skills/skill-taris/api-keys.txt
chmod 600 ~/.openclaw/skills/skill-taris/api-keys.txt
```

### Verify API

```bash
TOKEN=$(grep TARIS_API_TOKEN ~/.taris/bot.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/status | python3 -m json.tool
# Expected: {"status":"ok","version":"2026.3.28","provider":"ollama"}
```

---

## Storage

### SQLite (default)

Used by default. Same as PicoClaw. Stored at `~/.taris/taris.db`.

### PostgreSQL + pgvector (OpenClaw extended)

When `STORE_BACKEND=postgres` in `bot.env`:

```bash
STORE_BACKEND=postgres
DATABASE_URL=postgresql://taris:password@localhost:5432/taris
```

Enables:
- Full-text search (FTS5) + vector similarity (pgvector)
- 1536-dimension embeddings via `bot_embeddings.py` (fastembed / sentence-transformers)
- `skill-postgres` in sintaris-openclaw connects to the same database for RAG

→ Source: `src/core/store_postgres.py`  
→ Embedding service: `src/core/bot_embeddings.py`  
→ RAG pipeline: §25.6 in TODO.md (Phase B — planned)

---

## Local Development Setup

The `sintaris-openclaw-local-deploy` project provides a quick way to run Taris locally alongside sintaris-openclaw without affecting your production `~/.taris/`:

```bash
# Run Taris with isolated TARIS_HOME:
cd ~/projects/sintaris-openclaw-local-deploy
./run_all.sh          # starts all services
./run_web.sh          # starts only web service
./run_telegram.sh     # starts only Telegram bot
```

It symlinks directly into `sintaris-pl/src/`, so source changes are immediately reflected.

→ Location: `~/projects/sintaris-openclaw-local-deploy/`  
→ Install sintaris-openclaw: https://github.com/stas-ka/sintaris-openclaw → `bash scripts/setup.sh`

---

## Regression Tests (T27–T30)

```bash
cd /home/stas/projects/sintaris-pl
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py \
  --test t_openclaw_stt_routing t_openclaw_ollama_provider

# Full suite:
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py
```

| Test ID | Function | Status (fresh install) |
|---------|----------|----------------------|
| T27 | `t_faster_whisper_stt` — model load + silence inference | SKIP (not installed) → PASS after setup |
| T28 | `t_openclaw_llm_connectivity` — LLM provider connectivity | SKIP (ollama not running) → PASS after setup |
| T29 | `t_openclaw_stt_routing` — `STT_PROVIDER` defaults correct | PASS |
| T30 | `t_openclaw_ollama_provider` — `_ask_ollama` in dispatch + constants | PASS |

Copilot skill: `.github/prompts/taris-openclaw-setup.prompt.md`

---

## Implementation Status

| Component | Status | Source |
|-----------|--------|--------|
| `DEVICE_VARIANT` constant | ✅ | `src/core/bot_config.py` |
| `STT_PROVIDER` + `FASTER_WHISPER_*` | ✅ | `src/core/bot_config.py` |
| `OLLAMA_URL` + `OLLAMA_MODEL` | ✅ | `src/core/bot_config.py` |
| `faster_whisper_stt` voice opt (default True) | ✅ | `src/core/bot_config.py` |
| `_ask_openclaw()` LLM provider | ✅ | `src/core/bot_llm.py` |
| `_ask_ollama()` LLM provider | ✅ | `src/core/bot_llm.py` |
| LLM fallback chain | ✅ | `src/core/bot_llm.py` |
| `_stt_faster_whisper()` | ✅ | `src/features/bot_voice.py` |
| STT routing (faster_whisper → vosk) | ✅ | `src/features/bot_voice.py` |
| `voice_assistant.py` faster-whisper support | ✅ | `src/voice_assistant.py` |
| `setup_voice_openclaw.sh` + faster-whisper | ✅ | `src/setup/setup_voice_openclaw.sh` |
| `setup_llm_openclaw.sh` (Ollama installer) | ✅ | `src/setup/setup_llm_openclaw.sh` |
| STT benchmark script | ✅ | `src/tests/benchmark_stt.py` |
| T27–T30 OpenClaw regression tests | ✅ | `src/tests/test_voice_regression.py` |
| `GET /api/status` REST endpoint | ✅ | `src/bot_web.py` |
| `POST /api/chat` REST endpoint | ✅ | `src/bot_web.py` |
| Bearer-token authentication | ✅ | `src/bot_web.py` |
| 18 unit tests for `_ask_openclaw()` | ✅ | `src/tests/llm/` |
| `store_postgres.py` PostgreSQL adapter | ✅ | `src/core/store_postgres.py` |
| `bot_embeddings.py` EmbeddingService | ✅ | `src/core/bot_embeddings.py` |
| `TARIS_HOME` configurable data dir | ✅ | `src/core/bot_config.py` |
| `skill-taris` in sintaris-openclaw | ✅ | `~/projects/sintaris-openclaw/skills/skill-taris/` |
| `sintaris-openclaw-local-deploy` | ✅ | `~/projects/sintaris-openclaw-local-deploy/` |
| `migrate_sqlite_to_pg.py` | 🔲 Planned | §25.7 in TODO.md |
| pgvector HNSW RAG pipeline | 🔲 Planned | §25.6 Phase B in TODO.md |
| Screen DSL `visible_variants` | 🔲 Planned | §21.6 in TODO.md |

---

## Related Documents

| Document | Content |
|----------|---------|
| [overview.md](overview.md) | System overview, ecosystem map, all channels |
| [picoclaw.md](picoclaw.md) | PicoClaw (Raspberry Pi) variant |
| [llm-providers.md](llm-providers.md) | All LLM providers, fallback chain |
| [voice-pipeline.md](voice-pipeline.md) | STT/TTS/VAD architecture |
| [deployment.md](deployment.md) | File layout, bot.env reference |
| [../install-new-target.md §Part B](../install-new-target.md) | Fresh install guide (OpenClaw) |
| [sintaris-openclaw/docs/architecture.md](https://github.com/stas-ka/sintaris-openclaw/blob/main/docs/architecture.md) | sintaris-openclaw architecture |
| [sintaris-openclaw/docs/deployment-and-artifacts.md](https://github.com/stas-ka/sintaris-openclaw/blob/main/docs/deployment-and-artifacts.md) | Full ecosystem deployment guide |

