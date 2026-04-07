---
mode: agent
description: Setup, configure, troubleshoot, and extend the OpenClaw variant of Taris (laptop/PC x86_64 deployment).
---

# OpenClaw Setup & Troubleshoot (`/taris-openclaw-setup`)

**Usage**: `/taris-openclaw-setup [task]`

| Task | Description |
|---|---|
| `install` | Full first-time install on this machine |
| `llm` | Configure/fix LLM (Ollama or cloud API) |
| `stt` | Configure/fix STT (faster-whisper or Vosk) |
| `benchmark` | Run STT benchmark (Vosk vs faster-whisper) |
| `status` | Check health of running services + API |
| `tests` | Run OpenClaw regression tests (T27–T30) |
| `sync` | Sync source changes from sintaris-pl/src → ~/.taris/ |

---

## Context

- **Branch**: `master` (sintaris-pl repo — `taris-openclaw` is retired/protected)
- **Data dir**: `~/.taris/` (NOT symlinked — must sync manually after source changes)
- **Config**: `~/.taris/bot.env` — primary runtime config (gitignored)
- **Service**: `systemctl --user start/stop/restart taris-web`
- **Logs**: `journalctl --user -u taris-web -n 40 --no-pager`
- **API base**: `http://localhost:8080`
- **Reference doc**: `doc/architecture/openclaw-integration.md`

---

## Quick Status Check

```bash
# Service health
systemctl --user status taris-web --no-pager

# API check (grab token from ~/.taris/bot.env TARIS_API_TOKEN)
TOKEN=$(grep TARIS_API_TOKEN ~/.taris/bot.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/status | python3 -m json.tool

# LLM check
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"ping","chat_id":1}' \
  http://localhost:8080/api/chat | python3 -m json.tool

# Check bot.env LLM provider
grep -E "LLM_PROVIDER|OPENAI_API_KEY|OLLAMA" ~/.taris/bot.env
```

---

## LLM Configuration

### Install Ollama (recommended — offline, no key needed)

```bash
bash /home/stas/projects/sintaris-pl/src/setup/setup_llm_openclaw.sh
```

This installs Ollama, pulls `qwen2:0.5b` (fast) and optionally `llama3.2:1b` (better).

### Configure bot.env for Ollama

```bash
# Edit ~/.taris/bot.env — set these values:
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2:0.5b       # or: llama3.2:1b  phi3:mini  mistral:7b
OLLAMA_URL=http://127.0.0.1:11434
LLM_LOCAL_FALLBACK=1

# Restart service
systemctl --user restart taris-web
```

### Configure bot.env for OpenRouter (cloud)

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-or-...           # your OpenRouter key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openai/gpt-4o-mini
LLM_LOCAL_FALLBACK=1               # Ollama fallback if cloud fails
```

### Model Recommendations (i7-2640M, 7.6GB RAM, no GPU)

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `qwen2:0.5b` | 512MB | ~1–2s | Commands/chat |
| `llama3.2:1b` | 1.3GB | ~3–5s | Better reasoning |
| `phi3:mini` | 2.3GB | ~5–10s | Strong small model |
| `mistral:7b` | 4.1GB | ~15–30s | Best quality (slow) |

### LLM Troubleshooting

| Symptom | Fix |
|---------|-----|
| `OPENAI_API_KEY not set` | Set `LLM_PROVIDER=ollama` in bot.env |
| `ollama failed: connection refused` | `systemctl --user start ollama` or `ollama serve &` |
| Slow responses | Use `qwen2:0.5b`; avoid `mistral:7b` without GPU |
| Empty response | Check `journalctl --user -u taris-web -n 40` for details |

---

## STT Configuration

### Install faster-whisper

```bash
bash /home/stas/projects/sintaris-pl/src/setup/setup_voice_openclaw.sh
# or individually:
pip install faster-whisper
python3 -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
```

### Configure bot.env for faster-whisper

```bash
STT_PROVIDER=faster_whisper
FASTER_WHISPER_MODEL=base      # tiny | base | small | medium
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE=int8
```

### Run STT Benchmark

```bash
python3 /home/stas/projects/sintaris-pl/src/tests/benchmark_stt.py --all
python3 /home/stas/projects/sintaris-pl/src/tests/benchmark_stt.py --model base small --verbose
```

### STT Provider Comparison (i7-2640M)

| Engine | Model | WER (Russian) | RTF | RAM |
|--------|-------|--------------|-----|-----|
| `vosk` | small-ru (48MB) | ~15–20% | ~0.1 | 200MB |
| `faster_whisper` | base | ~8–12% | ~0.3–0.5 | 300MB |
| `faster_whisper` | small | ~5–8% | ~0.8–1.2 | 500MB |

---

## Sync Source → Deployment

After changing any file in `sintaris-pl/src/`, sync to `~/.taris/`:

```bash
# Core modules
cp -r /home/stas/projects/sintaris-pl/src/core/. ~/.taris/core/
cp -r /home/stas/projects/sintaris-pl/src/features/. ~/.taris/features/
cp -r /home/stas/projects/sintaris-pl/src/telegram/. ~/.taris/telegram/
cp /home/stas/projects/sintaris-pl/src/strings.json ~/.taris/
cp /home/stas/projects/sintaris-pl/src/release_notes.json ~/.taris/

# Restart
systemctl --user restart taris-web

# Verify
TOKEN=$(grep TARIS_API_TOKEN ~/.taris/bot.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/status
```

---

## Run OpenClaw Tests

```bash
cd /home/stas/projects/sintaris-pl

# All OpenClaw tests (T27–T30)
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py \
  --test t_faster_whisper_stt t_openclaw_llm_connectivity t_openclaw_stt_routing t_openclaw_ollama_provider

# Full regression suite
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py

# Single test
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py --test t_openclaw_stt_routing
```

Expected results on clean install (before faster-whisper + ollama installed):
- T27: SKIP (faster-whisper not installed)
- T28: SKIP (ollama not running)
- T29: PASS
- T30: PASS

After full setup (`setup_llm_openclaw.sh` + `setup_voice_openclaw.sh`):
- T27: PASS
- T28: PASS
- T29: PASS
- T30: PASS

---

## Version Bump (when releasing)

```bash
# 1. Edit BOT_VERSION in src/core/bot_config.py
# 2. Prepend entry in src/release_notes.json
# 3. Sync to ~/.taris/
# 4. Restart + verify
systemctl --user restart taris-web
TOKEN=$(grep TARIS_API_TOKEN ~/.taris/bot.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/status | grep version
```

---

## File Reference

| Source | Deployed | Purpose |
|--------|----------|---------|
| `src/core/bot_config.py` | `~/.taris/core/bot_config.py` | All constants, variants, LLM/STT defaults |
| `src/core/bot_llm.py` | `~/.taris/core/bot_llm.py` | LLM providers: ollama, openai, openclaw |
| `src/features/bot_voice.py` | `~/.taris/features/bot_voice.py` | STT/TTS; `_stt_faster_whisper()` |
| `src/voice_assistant.py` | `~/.taris/voice_assistant.py` | Standalone voice loop |
| `src/setup/setup_llm_openclaw.sh` | Run locally | Installs Ollama |
| `src/setup/setup_voice_openclaw.sh` | Run locally | Installs Vosk+Piper+faster-whisper |
| `src/tests/benchmark_stt.py` | Run locally | STT benchmark |
| `src/tests/test_voice_regression.py` | Run locally | Full regression suite incl. T27–T30 |
| `~/.taris/bot.env` | Runtime config | LLM_PROVIDER, STT_PROVIDER, tokens |
