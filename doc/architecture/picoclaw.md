# Taris — PicoClaw Variant

**Version:** `2026.3.28` · **Last updated:** March 2026  
→ Architecture index: [architecture.md](../architecture.md)  
→ System overview: [overview.md](overview.md)  
→ OpenClaw variant: [openclaw-integration.md](openclaw-integration.md)  
→ Deployment guide: [deployment.md](deployment.md)  
→ Install guide: [../install-new-target.md](../install-new-target.md)

---

## Overview

The **PicoClaw variant** runs Taris on a Raspberry Pi (3 B+, 4, or 5). It is the default deployment variant, optimized for the Pi's constrained RAM and CPU. It operates with a fully offline voice pipeline (Vosk STT + Piper TTS) and routes LLM calls via the `taris` CLI binary to OpenRouter (cloud) or a local llama.cpp server.

```
DEVICE_VARIANT=picoclaw  (or unset — picoclaw is default)
```

### What runs on the Pi

```
systemd
  ├── taris-telegram.service   ← Telegram bot (@taris_bot / @smartpico_bot)
  ├── taris-web.service        ← Web UI on :8080 (HTTPS, LAN only)
  ├── taris-voice.service      ← always-on voice daemon (hotword + TTS response)
  ├── taris-gateway.service    ← (disabled; picoclaw gateway not used)
  └── taris-llm.service        ← optional llama.cpp local LLM on :8081
```

---

## Hardware

### Target Hosts

| Name | Role | SSH (LAN) | Tailscale IP |
|------|------|-----------|-------------|
| **OpenClawPI2** | Engineering / dev target | `stas@OpenClawPI2` | `$DEV_TAILSCALE_IP` (see `.env`) |
| **OpenClawPI** | Production target (master branch only) | `stas@OpenClawPI` | — |

> **Deployment rule:** always deploy to **PI2** first, verify, then deploy to **PI1**. PI1 receives only the `master` branch.

### Supported Pi Models

| Model | RAM | LLM local | Voice | Notes |
|-------|-----|-----------|-------|-------|
| Pi 3 B+ | 1 GB | Emergency fallback only (~1 tok/s) | ✅ Vosk+Piper | Minimum spec; no GPU |
| Pi 4 B 4GB | 4 GB | llama.cpp 7B slow (~3–5 tok/s) | ✅ | Comfortable for all features |
| Pi 5 8GB | 8 GB | llama.cpp 7B usable (~5–10 tok/s) | ✅ | Full stack; NVMe HAT recommended |

→ See [hardware-performance-analysis.md](../hardware-performance-analysis.md) for benchmarks.

### External Access

Taris is accessible remotely via VPS reverse proxy:
- **PI1 (production):** `https://agents.sintaris.net/picoassist/`
- **PI2 (engineering):** `https://agents.sintaris.net/picoassist2/`

---

## Voice Pipeline

> Full reference: [voice-pipeline.md](voice-pipeline.md)

### Architecture

```
Microphone (USB / I2S HAT)
      │
      ▼
 [pw-record]    ← PipeWire subprocess (S16_LE, 16 kHz, mono)
      │               fallback: parec (PulseAudio compat)
      ▼
 [Vosk STT]     ← vosk-model-small-ru-0.22 (48 MB, Kaldi-based, offline)
      │               streaming, 250 ms chunks
      ▼
 Hotword gate   ← fuzzy SequenceMatcher: "пико / пика / пике / пик"
      │               threshold: 0.75 similarity ratio
      ▼
 [Vosk STT]     ← fresh recognizer for command phrase
      │               stops on 2s silence or 15s max
      ▼
 [taris agent]  ← CLI subprocess via bot_llm.py::_ask_taris()
      │               binary: /usr/bin/picoclaw
      ▼
 [OpenRouter]   ← HTTPS (cloud LLM, configurable model)
      │               default: openrouter/openai/gpt-4o-mini
      ▼
 [Piper TTS]    ← ru_RU-irina-medium.onnx (ONNX Runtime, 66 MB, offline)
      │               output: raw PCM S16_LE 22050 Hz mono
      ▼
   [aplay]      ← ALSA playback → 3.5mm jack / USB speaker
```

### Voice Model Software Artifacts

| Component | Source | Install command |
|-----------|--------|-----------------|
| **Vosk small-ru** | https://alphacephei.com/vosk/models (`vosk-model-small-ru-0.22`) | `bash src/setup/setup_voice.sh` |
| **Vosk small-de** | https://alphacephei.com/vosk/models (`vosk-model-small-de-0.15`) | Included in `setup_voice.sh` |
| **Piper TTS binary** | https://github.com/rhasspy/piper/releases (aarch64) | `bash src/setup/setup_voice.sh` |
| **Piper voice: ru irina** | https://huggingface.co/rhasspy/piper-voices | `bash src/setup/setup_voice.sh` |
| **Piper voice: de thorsten** | https://huggingface.co/rhasspy/piper-voices | `bash src/setup/setup_voice.sh` |

```bash
# Install all voice components on Pi:
bash src/setup/setup_voice.sh
```

### Voice Optimisation Flags (Telegram voice messages)

The Telegram bot supports 10 per-user voice toggles, configurable from the voice opts menu (`⚙️ Voice options`). Key flags:

| Flag | Default | Effect |
|------|---------|--------|
| `voice_reply_tts` | True | Use TTS to read responses aloud |
| `voice_stt_enabled` | True | Enable STT for incoming voice messages |
| `silence_strip` | True | VAD strips silence before STT |
| `confidence_strip` | True | Remove Vosk low-confidence `[?word]` tokens |
| `piper_tmpfs` | False | Load Piper model into RAM (tmpfs) for faster synthesis |
| `whisper_stt` | False | Use whisper-cpp instead of Vosk for Telegram voice STT |

---

## LLM Configuration

> Full reference: [llm-providers.md](llm-providers.md)

### Default Stack

```
LLM_PROVIDER=taris   →   taris agent -m "<prompt>"
                              │
                              └─ binary: /usr/bin/picoclaw
                                 config: ~/.taris/config.json
                                 LLM:    OpenRouter (cloud)
                                 model:  gpt-4o-mini (configurable via Admin panel)
```

### picoclaw Binary

| Property | Value |
|----------|-------|
| **Name** | `picoclaw` (alias `taris`) |
| **Source** | https://github.com/sipeed/picoclaw/releases |
| **Version** | v0.2.0 |
| **Architecture** | aarch64 .deb (Raspberry Pi) |
| **Install path** | `/usr/bin/picoclaw` |
| **Config** | `~/.taris/config.json` (model list, active model, agents) |
| **Invocation** | `taris agent -m "<text>"` |

```bash
# Install picoclaw on Pi:
wget -q https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_aarch64.deb \
  && sudo dpkg -i picoclaw_aarch64.deb
```

### LLM Provider Options for PicoClaw

| `LLM_PROVIDER` | What it uses | Key env vars |
|----------------|-------------|-------------|
| `taris` (default) | picoclaw CLI → OpenRouter | `~/.taris/config.json` |
| `openai` | OpenRouter or OpenAI REST | `OPENAI_API_KEY`, `OPENAI_BASE_URL` |
| `yandexgpt` | Yandex cloud LLM | `YANDEXGPT_API_KEY`, `YANDEXGPT_FOLDER_ID` |
| `gemini` | Google Gemini REST | `GEMINI_API_KEY` |
| `anthropic` | Anthropic Claude REST | `ANTHROPIC_API_KEY` |
| `local` | llama.cpp server on :8081 | `LLAMA_CPP_URL` |

### Local Offline Fallback

When `LLM_LOCAL_FALLBACK=true` in `bot.env`, any provider failure auto-falls back to local llama.cpp:

```
LLM_PROVIDER=taris  →  fails  →  llama.cpp on :8081 (taris-llm.service)
```

Service: `src/services/taris-llm.service` — installs llama.cpp server with `qwen2-0.5b-q4.gguf` (350 MB).  
Expected Pi 3 speed: ~0.8–1.5 tok/s (emergency fallback only; Pi 4/5 significantly faster).

---

## Services & Deployment

### Systemd Services

| Service file | Deployed to | Manages |
|-------------|------------|---------|
| `src/services/taris-telegram.service` | `/etc/systemd/system/` | Telegram bot |
| `src/services/taris-web.service` | `/etc/systemd/system/` | Web UI (uvicorn :8080) |
| `src/services/taris-voice.service` | `/etc/systemd/system/` | Voice daemon |
| `src/services/taris-llm.service` | `/etc/systemd/system/` | Local llama.cpp (optional) |

```bash
# Deploy service files:
sudo cp src/services/taris-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now taris-telegram taris-web taris-voice

# Verify:
journalctl -u taris-telegram -n 20 --no-pager
# Expected: [INFO] Version : 2026.X.Y + [INFO] Polling Telegram…
```

### Deployed File Layout (`~/.taris/`)

```
/home/stas/.taris/
  telegram_menu_bot.py, bot_web.py, voice_assistant.py
  core/    security/    telegram/    features/    ui/    screens/    web/
  strings.json    release_notes.json    config.json    prompts.json
  bot.env          ← secrets (BOT_TOKEN, ALLOWED_USERS, TARIS_API_TOKEN)
  accounts.json    ← Web UI JWT user accounts
  taris.db         ← SQLite database (notes, calendar, contacts, chat history)
  vosk-model-small-ru/    vosk-model-small-de/
  *.onnx  *.onnx.json     ← Piper voice models
  telegram_bot.log
```

> Override data directory: `TARIS_HOME=/path/to/dir` env var (useful for multi-instance or dev).

### Deploy Workflow

```bash
# 1. Sync changed source files to PI2 (engineering target)
pscp -pw "%HOSTPWD%" src\core\bot_config.py stas@OpenClawPI2:/home/stas/.taris/core/

# 2. Restart and verify on PI2
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI2 \
  "sudo systemctl restart taris-telegram && sleep 3 && journalctl -u taris-telegram -n 12 --no-pager"

# 3. Run regression tests on PI2
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI2 \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"

# 4. Only after tests pass: deploy to PI1 (production, master branch only)
pscp -pw "%HOSTPWD%" src\core\bot_config.py stas@OpenClawPI:/home/stas/.taris/core/
```

→ Full deploy commands: `.github/instructions/bot-deploy.instructions.md`  
→ Deploy skill: `.github/prompts/taris-deploy-to-target.prompt.md`

---

## Setup & Installation

```bash
# 1. Install voice pipeline (Vosk + Piper + PipeWire)
bash src/setup/setup_voice.sh

# 2. Install picoclaw binary
wget https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_aarch64.deb
sudo dpkg -i picoclaw_aarch64.deb

# 3. Configure bot.env
cp src/setup/bot.env.example ~/.taris/bot.env
nano ~/.taris/bot.env   # set BOT_TOKEN, ALLOWED_USERS, OPENROUTER_API_KEY

# 4. Install systemd services
sudo cp src/services/taris-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now taris-telegram taris-web taris-voice
```

→ Full step-by-step guide: [../install-new-target.md](../install-new-target.md)

---

## Regression Tests

```bash
# Run full voice regression suite on Pi (T01–T26):
python3 /home/stas/.taris/tests/test_voice_regression.py

# Run specific test group:
python3 /home/stas/.taris/tests/test_voice_regression.py --test tts
python3 /home/stas/.taris/tests/test_voice_regression.py --verbose

# Set new baseline after confirmed-good deploy:
python3 /home/stas/.taris/tests/test_voice_regression.py --set-baseline
```

| Test range | What it covers |
|-----------|----------------|
| T01–T03 | Model files present, Piper JSON, tmpfs model |
| T04–T06 | OGG decode, VAD filter, Vosk STT WER |
| T07–T09 | Confidence strip, TTS escape, Piper synthesis |
| T10–T12 | Whisper STT (SKIP if absent), hallucination guard, regression baseline |
| T13–T16 | i18n coverage, language routing, German TTS/STT |
| T17–T21 | Bot name injection, profile resilience, note edit/append, calendar TTS/console |

→ Full test documentation: [../test-suite.md](../test-suite.md)  
→ Copilot skill: `.github/prompts/taris-voicetests.prompt.md`

---

## Related Documents

| Document | Content |
|----------|---------|
| [voice-pipeline.md](voice-pipeline.md) | Detailed STT/TTS/VAD/hotword/PipeWire reference |
| [llm-providers.md](llm-providers.md) | All LLM providers, fallback chain, configuration |
| [deployment.md](deployment.md) | File layout, bot.env config, backup system |
| [telegram-bot.md](telegram-bot.md) | Telegram module structure, callbacks, menus |
| [web-ui.md](web-ui.md) | FastAPI routes, JWT auth, Screen DSL |
| [security.md](security.md) | 3-layer prompt injection guard, RBAC |
| [../install-new-target.md](../install-new-target.md) | Step-by-step fresh Pi install guide |
| [../hardware-performance-analysis.md](../hardware-performance-analysis.md) | Pi 3 tuning, upgrade paths, benchmarks |
| [../test-suite.md](../test-suite.md) | Complete test suite reference |
