# VPS Taris Deployment Analysis

**When to read:** Before deciding whether to deploy a Taris instance on dev2null.de VPS.  
**Date:** 2026-04-16  
**VPS host:** dev2null.de (agents.sintaris.net)

---

## VPS Hardware

| Resource | Value |
|----------|-------|
| **CPU** | 6 vCPU — ARM Neoverse-N1 (aarch64), 1 thread/core |
| **Architecture** | aarch64 (ARM64) — no x86, no GPU |
| **RAM** | 7.7 GB total, **3.6 GB available** |
| **Swap** | 8 GB (only 494 MB used) |
| **Disk** | 504 GB total, 263 GB free (46% used) |
| **OS** | Ubuntu, kernel 6.8.0-106-generic |
| **Python** | 3.12.3 (system) |

---

## Current RAM Usage by Service

| Service | RAM Used | Notes |
|---------|----------|-------|
| Metabase (java) | ~1143 MB | Analytics/BI dashboard |
| Apache2 (EspoCRM + Collabora) | ~1224 MB | CRM web server |
| CoolWSD (Collabora Office) | ~1181 MB | Online office editor |
| MySQL | ~725 MB | EspoCRM database |
| n8n (Node.js) | ~674 MB | Workflow automation |
| SpamAssassin | ~399 MB | Mail filtering |
| PostgreSQL 17 | ~259 MB | Taris/application database |
| nginx | ~50 MB | Reverse proxy |
| **Total in use** | **~5655 MB** | |
| **Available** | **~3600 MB** | Per `/proc/meminfo MemAvailable` |

---

## Pre-Installed Services (usable by Taris)

| Service | Port | Status | Usable by Taris |
|---------|------|--------|----------------|
| PostgreSQL 17 | 5432 | ✅ Running | ✅ Yes — use directly |
| n8n | 5678 (localhost) | ✅ Running | ✅ Yes — existing API key |
| EspoCRM | 8888 | ✅ Running | ✅ Yes — existing CRM |
| nginx | 80/443 | ✅ Running | ✅ Yes — add new sub-path |
| Ollama | 11434 | ❌ Not installed | Optional |
| ffmpeg | — | ❌ Not installed | Needs install |

---

## Feasibility Assessment

### ✅ YES — Taris OpenClaw can be deployed on VPS

**Required additions:**
1. Install Python packages: `pyTelegramBotAPI`, `openai`, `psycopg2`, `fastapi`, `uvicorn`, etc.
2. Install `ffmpeg` (for audio processing, even without voice hardware)
3. Configure new nginx sub-path block (e.g., `/vps/`)
4. Create `~/.taris/bot.env` with bot token and config

**Zero additional RAM** if using external LLM (OpenAI) — the bot itself uses ~150–200 MB.

---

## Voice Features

**Voice: ❌ DISABLED on VPS**

The VPS has no:
- Audio input hardware (microphone)
- Audio output (speaker)
- Physical presence (remote cloud server)

Set in `bot.env`:
```
STT_PROVIDER=none
VOICE_DISABLED=1
```

---

## LLM Options on VPS

### Option A: External LLM only (Recommended)

```env
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
# No local LLM
```

| Aspect | Value |
|--------|-------|
| Extra RAM | 0 MB |
| Response time | ~0.5–1.5s |
| Quality (RU/DE/EN) | Excellent |
| Cost | ~$0.001/request |
| Risk | API dependency |

**Best choice** — zero extra RAM cost, fast, high quality.

---

### Option B: Ollama with qwen2:0.5b (Minimal local LLM)

```env
LLM_PROVIDER=ollama
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2:0.5b
LLM_FALLBACK_PROVIDER=openai
```

| Aspect | Value |
|--------|-------|
| Extra RAM | ~350–650 MB (model + Ollama server) |
| Response time | ~2–5s (ARM CPU-only) |
| Speed estimate | ~25–40 t/s on 6-core ARM Neoverse |
| Quality (RU/DE/EN) | Limited (0.5B model) |
| After install | RAM free: ~2.9 GB (acceptable) |

**Use case:** Offline fallback when OpenAI is unavailable.

---

### Option C: Ollama with qwen2.5:3b (Better quality local LLM)

```env
OLLAMA_MODEL=qwen2.5:3b
```

| Aspect | Value |
|--------|-------|
| Extra RAM | ~2.0–2.2 GB |
| Response time | ~20–40s per response (ARM CPU) |
| Speed estimate | ~5–8 t/s on ARM (very slow for interactive use) |
| Quality | Good (significantly better than 0.5b) |
| RAM after install | ~1.4 GB free — **tight under load** |

**Not recommended** — response time too slow (20–40s) for interactive Telegram chat.

---

### Option D: Ollama with llama3.2:1b (Balance)

```env
OLLAMA_MODEL=llama3.2:1b
```

| Aspect | Value |
|--------|-------|
| Extra RAM | ~800 MB–1.1 GB |
| Response time | ~8–15s (ARM CPU) |
| Speed estimate | ~12–18 t/s on ARM |
| Quality | Reasonable for simple tasks |
| RAM after install | ~2.4 GB free (safe) |

**Acceptable** if local LLM is needed — fits in RAM, response within ~10s.

---

## Recommended Configuration for VPS Taris

```env
# VPS taris instance — no voice, external LLM primary
BOT_TOKEN=CHANGE_ME
ALLOWED_USERS=CHANGE_ME
DEVICE_VARIANT=openclaw
VOICE_DISABLED=1
STT_PROVIDER=none

# LLM: OpenAI primary, Ollama local fallback (optional)
LLM_PROVIDER=openai
OPENAI_API_KEY=CHANGE_ME
OPENAI_MODEL=gpt-4o-mini
LLM_FALLBACK_PROVIDER=ollama
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:1b
LLM_LOCAL_FALLBACK=1

# Database: use existing VPS PostgreSQL
STORE_BACKEND=postgres
DATABASE_URL=postgresql://taris:CHANGE_ME@localhost:5432/taris

# N8N: use existing VPS n8n
N8N_API_URL=http://localhost:5678/api/v1
N8N_API_KEY=CHANGE_ME

# Web UI
ROOT_PATH=/vps
WEB_PORT=8092

# No faster-whisper preload (no voice)
FASTER_WHISPER_PRELOAD=0
```

---

## RAM Budget (Recommended Config)

| Item | RAM |
|------|-----|
| Current services | ~5655 MB |
| Taris bot (telegram + web) | ~150 MB |
| Ollama + llama3.2:1b (optional) | ~1100 MB |
| **Total (with local LLM)** | **~6905 MB** |
| **Headroom** | **~800 MB + 7.5 GB swap** |
| **Total (no local LLM)** | **~5805 MB** |
| **Headroom (no local LLM)** | **~1900 MB** |

> Safe to operate. Swap provides emergency buffer. ARM server is designed for sustained server workloads.

---

## Installation Steps

### 1. Install system dependencies

```bash
sudo apt-get install -y ffmpeg python3-venv python3-pip python3-dev libpq-dev
```

### 2. Create virtualenv and install Python packages

```bash
python3 -m venv ~/.taris-venv
source ~/.taris-venv/bin/activate
pip install pyTelegramBotAPI openai psycopg2-binary fastapi uvicorn \
            httpx aiohttp python-dotenv
# No faster-whisper, no vosk, no sounddevice (voice disabled)
```

### 3. Install Ollama (optional, for local LLM)

```bash
# Ollama supports aarch64 Linux
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b
# Or for minimal: ollama pull qwen2:0.5b
```

### 4. Deploy taris files

```bash
mkdir -p ~/.taris/{web/templates,web/static,core,features,telegram}
# scp or git clone to ~/.taris/
```

### 5. Add nginx sub-path

```nginx
location /vps/ {
    proxy_pass http://127.0.0.1:8092/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_redirect off;
}
```

### 6. Create systemd user service

```bash
# ~/.config/systemd/user/taris-vps-web.service
systemctl --user enable --now taris-vps-web
```

---

## Summary

| Question | Answer |
|----------|--------|
| Can Taris run on VPS? | ✅ Yes |
| Voice features? | ❌ No (no audio hardware) |
| Best LLM for VPS? | OpenAI gpt-4o-mini (external, fast, free RAM) |
| Local LLM possible? | ✅ Yes — qwen2:0.5b (fast/small) or llama3.2:1b (balanced) |
| Local LLM recommended? | ⚠️ Only as offline fallback — ARM CPU is slow for 3B+ models |
| RAM available? | 3.6 GB free → Taris alone: +150 MB, with llama3.2:1b: +1.1 GB |
| Uses existing PG/n8n? | ✅ Yes — connect directly (localhost) |
| Disk space concern? | ❌ No — 263 GB free |
| New nginx URL | `https://agents.sintaris.net/vps/` |
