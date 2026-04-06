---
name: taris-openclaw-setup
description: >
  Setup, configure, troubleshoot, and extend the OpenClaw variant of Taris
  (laptop/PC x86_64 deployment with faster-whisper STT and Ollama LLM).
argument-hint: >
  task: install | llm | stt | benchmark | status | tests | sync
---

## Context

| Item | Value |
|---|---|
| Branch | `taris-openclaw` |
| Source | `/home/stas/projects/sintaris-pl/src/` |
| Data dir | `~/.taris/` (NOT symlinked — sync manually) |
| Config | `~/.taris/bot.env` |
| Service | `systemctl --user {start\|stop\|restart} taris-web` |
| Logs | `journalctl --user -u taris-web -n 40 --no-pager` |
| API | `http://localhost:8080` |
| Reference | `doc/architecture/openclaw-integration.md` |

---

## Quick Status Check

```bash
systemctl --user status taris-web --no-pager
TOKEN=$(grep TARIS_API_TOKEN ~/.taris/bot.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/status | python3 -m json.tool
grep -E "LLM_PROVIDER|OPENAI_API_KEY|OLLAMA|STT_PROVIDER" ~/.taris/bot.env
```

---

## task: `install` — First-time setup

```bash
# Voice (Vosk + Piper + faster-whisper)
bash /home/stas/projects/sintaris-pl/src/setup/setup_voice_openclaw.sh

# LLM (Ollama)
bash /home/stas/projects/sintaris-pl/src/setup/setup_llm_openclaw.sh

# Sync sources
cp -r /home/stas/projects/sintaris-pl/src/. ~/.taris/
systemctl --user restart taris-web
```

---

## task: `llm` — Configure LLM

### Ollama (recommended — offline)

```bash
# bot.env settings:
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2:0.5b       # or: llama3.2:1b  phi3:mini  mistral:7b
OLLAMA_URL=http://127.0.0.1:11434
LLM_LOCAL_FALLBACK=1
systemctl --user restart taris-web
```

### OpenRouter (cloud)

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-or-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openai/gpt-4o-mini
LLM_LOCAL_FALLBACK=1
```

### Model recommendations (i7-2640M, 7.6 GB RAM, no GPU)

| Model | Size | Speed | Quality |
|---|---|---|---|
| `qwen2:0.5b` | 512 MB | ~1–2s | Commands/chat |
| `llama3.2:1b` | 1.3 GB | ~3–5s | Better reasoning |
| `phi3:mini` | 2.3 GB | ~5–10s | Strong |
| `mistral:7b` | 4.1 GB | ~15–30s | Best (slow) |

### LLM Troubleshooting

| Symptom | Fix |
|---|---|
| `OPENAI_API_KEY not set` | Set `LLM_PROVIDER=ollama` in bot.env |
| `ollama failed: connection refused` | `systemctl --user start ollama` |
| Slow responses | Use `qwen2:0.5b` |
| Empty response | Check `journalctl --user -u taris-web -n 40` |

---

## task: `stt` — Configure STT

```bash
# Install faster-whisper
pip install faster-whisper

# bot.env settings:
STT_PROVIDER=faster_whisper
FASTER_WHISPER_MODEL=base      # tiny | base | small | medium
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE=int8
```

### Provider comparison (i7-2640M)

| Engine | Model | WER (Russian) | RTF | RAM |
|---|---|---|---|---|
| `vosk` | small-ru (48 MB) | ~15–20% | ~0.1 | 200 MB |
| `faster_whisper` | base | ~8–12% | ~0.3–0.5 | 300 MB |
| `faster_whisper` | small | ~5–8% | ~0.8–1.2 | 500 MB |

---

## task: `benchmark` — STT benchmark

```bash
python3 /home/stas/projects/sintaris-pl/src/tests/benchmark_stt.py --all
python3 /home/stas/projects/sintaris-pl/src/tests/benchmark_stt.py --model base small --verbose
```

---

## task: `sync` — Sync sources to deployment

```bash
cp -r /home/stas/projects/sintaris-pl/src/core/.      ~/.taris/core/
cp -r /home/stas/projects/sintaris-pl/src/features/.  ~/.taris/features/
cp -r /home/stas/projects/sintaris-pl/src/telegram/.  ~/.taris/telegram/
cp -r /home/stas/projects/sintaris-pl/src/ui/.        ~/.taris/ui/
cp /home/stas/projects/sintaris-pl/src/strings.json   ~/.taris/
cp /home/stas/projects/sintaris-pl/src/release_notes.json ~/.taris/

systemctl --user restart taris-web

# Verify sync
TOKEN=$(grep TARIS_API_TOKEN ~/.taris/bot.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/status | python3 -m json.tool
```

---

## task: `tests` — Run OpenClaw regression tests

```bash
cd /home/stas/projects/sintaris-pl

# OpenClaw-specific T27–T30
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py \
  --test t_faster_whisper_stt t_openclaw_llm_connectivity t_openclaw_stt_routing t_openclaw_ollama_provider

# Full suite
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py
```

Expected results:

| Test | Without full setup | After full setup |
|---|---|---|
| T27 `faster_whisper_stt` | SKIP | PASS |
| T28 `openclaw_llm_connectivity` | SKIP | PASS |
| T29 `openclaw_stt_routing` | PASS | PASS |
| T30 `openclaw_ollama_provider` | PASS | PASS |

---

## File Reference

| Source | Deployed |
|---|---|
| `src/core/bot_config.py` | `~/.taris/core/bot_config.py` |
| `src/core/bot_llm.py` | `~/.taris/core/bot_llm.py` |
| `src/features/bot_voice.py` | `~/.taris/features/bot_voice.py` |
| `src/bot_web.py` | `~/.taris/bot_web.py` |
| `src/web/templates/` | `~/.taris/web/templates/` |
| `~/.taris/bot.env` | Runtime config (gitignored) |

---

## Mandatory: Test After Every Change

> See `doc/architecture/openclaw-integration.md` — OpenClaw Coding Instructions for full pattern guide.
> Every change: source → sync → restart → verify API → run T27–T30.
