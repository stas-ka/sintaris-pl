# VPS Taris Deployment Analysis

**When to read:** Before deciding whether to deploy a Taris instance on dev2null.de VPS.  
**Date:** 2026-04-16 (updated: gemma4 analysis added)  
**VPS host:** dev2null.de (agents.sintaris.net)

---

## VPS Hardware

| Resource | Value |
|----------|-------|
| **CPU** | 6 vCPU — ARM Neoverse-N1 (aarch64), 1 thread/core |
| **Architecture** | aarch64 (ARM64) — no x86, no GPU |
| **RAM** | 7.7 GB total, **3.5 GB available** |
| **Swap** | 8 GB file-based on SSD (~494 MB used, 391 MB/s I/O) |
| **Disk** | 504 GB total, 263 GB free (46% used) |
| **OS** | Ubuntu, kernel 6.8.0-106-generic |
| **Python** | 3.12.3 (system) |
| **Ollama** | ✅ `ollama-linux-arm64.tar.zst` v0.20.7 — installable |

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
| ffmpeg | — | ✅ Installed (2026-04-16) | ✅ Yes — audio processing |

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

## Voice Features on VPS

**⚠️ VPS has no microphone/speaker** — the live voice assistant is not usable. But **Telegram voice message processing** (STT + TTS) works fully via software.

### What works vs what doesn't

| Feature | VPS | SintAItion |
|---------|-----|-----------|
| Transcribe Telegram voice messages (OGG→text) | ✅ Yes (faster-whisper/openai_whisper) | ✅ Yes |
| Send voice replies (text→OGG) | ✅ Yes (Piper aarch64) | ✅ Yes |
| "Read aloud" any bot reply | ✅ Yes | ✅ Yes |
| Live voice assistant (hotword + mic) | ❌ No mic | ✅ Yes |
| Real-time streaming STT | ❌ No mic | ✅ Yes |

### Package availability on ARM64 (aarch64) — VERIFIED ✅

| Package | ARM64 wheel | Status |
|---------|-------------|--------|
| `faster-whisper` 1.2.1 | `ctranslate2-4.7.1-cp312-cp312-manylinux_2_27_aarch64` | ✅ Available |
| `vosk` 0.3.45 | `manylinux2014_aarch64` | ✅ Available |
| Piper binary 2023.11.14-2 | `piper_linux_aarch64.tar.gz` | ✅ Available |
| `ffmpeg` | arm64 apt package (v6.1.1) | ✅ Available |
| `onnxruntime` 1.24.4 | `manylinux_2_27_aarch64` | ✅ Available |

All packages tested and installed on VPS (2026-04-16).

### STT Benchmark — faster-whisper on VPS ARM Neoverse-N1 (CPU, int8)

*Benchmarked 2026-04-16 on actual VPS hardware:*

| Model | Load time | RTF (5s audio) | WER estimate | RAM loaded |
|-------|-----------|----------------|--------------|------------|
| `tiny` | 2.4s | **0.14** (7× real-time) | ~25% RU / ~14% EN | ~250 MB |
| `base` | 2.2s | **0.23** (4× real-time) | ~22% RU / ~12% EN | ~350 MB |
| `small` | not tested | ~0.35 estimated | ~18% RU / ~10% EN | ~650 MB |

> With `FASTER_WHISPER_PRELOAD=0` (lazy load): 0 MB at idle, peak RAM only during voice message processing.  
> **Recommendation: `base` model** — better accuracy than `tiny` at similar RAM, both very fast.

**Comparison with SintAItion** (AMD Radeon 890M GPU, `small` model):
- SintAItion STT: RTF ≈ 0.05 (GPU-accelerated) — ~3× faster than VPS base
- VPS base RTF=0.23 is still **4× faster than real-time** — fine for Telegram (10s OGG → 2.3s transcription)

### TTS Benchmark — Piper aarch64 (60 MB RU voice, no GPU)

*Benchmarked 2026-04-16:*

| Text length | Chars | Synthesis time | Audio duration | RTF | OGG encode |
|-------------|-------|----------------|----------------|-----|------------|
| Short | 41 | 0.92s | 4.1s | 0.22 | 0.19s |
| Medium | 139 | 1.43s | 9.7s | 0.15 | 0.28s |
| Long | 289 | 2.32s | 19.9s | **0.12** | 0.49s |

> Piper runs as subprocess — no persistent RAM usage (model loaded per call, ~150 MB peak).  
> Total voice reply latency for medium text: ~1.4s TTS + 0.3s OGG + LLM time = **fast enough for Telegram**.

### Recommended bot.env for VPS Voice

```env
# STT: local faster-whisper (best privacy, ~350 MB peak RAM)
STT_PROVIDER=faster_whisper
FASTER_WHISPER_MODEL=base
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE=int8
FASTER_WHISPER_THREADS=4
FASTER_WHISPER_PRELOAD=0       # lazy load — 0 MB at idle

# Or: OpenAI Whisper API (0 MB RAM, best quality, ~$0.006/min)
# STT_PROVIDER=openai_whisper
# STT_FALLBACK_PROVIDER=faster_whisper

# TTS: Piper aarch64
PIPER_BIN=~/.taris/piper/piper
PIPER_MODEL=~/.taris/ru_RU-irina-medium.onnx

# Live voice assistant disabled (no mic)
VOICE_DISABLED=1
```

### Installation (voice packages)

```bash
# System deps
sudo apt-get install -y ffmpeg

# Python voice packages
pip3 install --break-system-packages faster-whisper vosk

# Piper binary (aarch64)
mkdir -p ~/.taris/piper
curl -sL https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz \
  | tar -xz -C ~/.taris/piper/ --strip-components=1
chmod +x ~/.taris/piper/piper

# RU voice model (60 MB)
curl -sL https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx \
  -o ~/.taris/ru_RU-irina-medium.onnx
curl -sL https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json \
  -o ~/.taris/ru_RU-irina-medium.onnx.json
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
| Quality (RU/DE/EN) | Limited (0.5B model, 50% quality) |
| After install | RAM free: ~2.9 GB (acceptable) |

**Use case:** Offline fallback when OpenAI is unavailable.

---

### Option C: Ollama with qwen3.5:0.8b (Better offline fallback)

```env
OLLAMA_MODEL=qwen3.5:0.8b
OLLAMA_THINK=false
```

| Aspect | Value |
|--------|-------|
| Extra RAM | ~1.0 GB |
| Response time | ~8–15s (ARM CPU) |
| Speed estimate | ~12–18 t/s on ARM |
| Quality (RU/DE/EN) | Good for 0.8B model (~70%) |
| RAM after install | ~2.5 GB free (comfortable) |

**Best local LLM** if offline capability is needed — verified on TariStation2 (i7-2640M: 5 t/s, ARM Neoverse-N1 would be similar or faster).

---

### Option D: Ollama with qwen2.5:3b (Maximum local quality)

```env
OLLAMA_MODEL=qwen2.5:3b
```

| Aspect | Value |
|--------|-------|
| Extra RAM | ~2.0–2.2 GB |
| Response time | ~20–40s per response (ARM CPU) |
| Speed estimate | ~5–8 t/s on ARM |
| Quality | Good (~80%) |
| RAM after install | ~1.3 GB free — **tight under load** |

**Not recommended for interactive chat** — 20–40s response is too slow for Telegram use.

---

## Gemma4 on VPS — Assessment

> **TL;DR: Gemma4 is NOT feasible on the VPS — not enough RAM for any variant.**

### Why Gemma4 cannot run on VPS

| Model | Ollama actual size | VPS available RAM | Verdict |
|-------|-------------------|-------------------|---------|
| gemma4:e2b | **7.2 GB Q8** | 3.5 GB | ❌ Needs 2× available RAM |
| gemma4:e4b | **9.6 GB Q8** | 3.5 GB | ❌ Needs 2.7× available RAM |
| gemma4:31b | ~17 GB | 3.5 GB | ❌ Impossible |
| gemma4:26b | ~15 GB | 3.5 GB | ❌ Impossible |

> ⚠️ **Important:** The Ollama Q8 format of gemma4:e2b is **7.2 GB** — not 3.2 GB as the 4-bit paper estimate suggests.  
> The overhead comes from: text model (~4.5 GB) + vision encoder (~150M params, ~0.7 GB Q8) + audio encoder (~300M params, ~1.4 GB Q8) = 6.6–7.2 GB total.  
> Source: `doc/gemma4-evaluation-report.md` §3 (measured on TariStation2 2026-04-09)

### Even TariStation2 (7.6 GB RAM) could not run gemma4:e2b

TariStation2 has 7.6 GB total RAM with only 4.5 GB free (6.2 GB with all services stopped) — still not enough for 7.2 GB gemma4:e2b. The VPS with only 3.5 GB available has even less.

### Minimum hardware required for gemma4:e2b

| Requirement | Value |
|-------------|-------|
| RAM | ≥ 10 GB total (8 GB+ free for model + KV cache) |
| GPU VRAM (for fast inference) | ≥ 8 GB (SintAItion's 16 GB is ideal) |
| CPU-only speed (if RAM fits) | ~3–6 t/s on ARM (too slow: 15–25s/response) |
| Recommended target | **SintAItion** (adopted ✅, 45 t/s on AMD Radeon 890M) |

### Custom Q4 quantization (theoretical)

A custom `gemma4:e2b` build with Q4_K_M quantization (text weights only, no encoders) might reach ~2.5–3 GB. This is not available in the standard Ollama library and would require:
1. Manual GGUF conversion from Hugging Face weights
2. Disabling vision/audio encoders (losing multimodal capability)
3. Testing stability — not production-ready

**Conclusion: Not worth the effort for the VPS use case. Use external OpenAI instead.**

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

# No faster-whisper preload (lazy load, saves RAM at idle)
FASTER_WHISPER_PRELOAD=0
STT_PROVIDER=faster_whisper
FASTER_WHISPER_MODEL=base
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE=int8
FASTER_WHISPER_THREADS=4
PIPER_BIN=~/.taris/piper/piper
PIPER_MODEL=~/.taris/ru_RU-irina-medium.onnx
VOICE_DISABLED=1
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
| RAM (voice idle, PRELOAD=0) | ~0 MB (lazy load) |
| RAM (voice active, base model) | ~350 MB (during processing) |

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
