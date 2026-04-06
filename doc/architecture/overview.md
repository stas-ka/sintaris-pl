# Taris — System Overview

**Version:** `2026.3.43` · **Last updated:** March 2026  
→ Architecture index: [architecture.md](../architecture.md)

---

## 0. Ecosystem & Deployment Variants

Taris (`sintaris-pl`) is the AI voice assistant component of the **Sintaris ecosystem**. It can run on two hardware platforms with different capability profiles:

| Variant | `DEVICE_VARIANT` | Hardware | Doc |
|---------|-----------------|----------|-----|
| **PicoClaw** | `picoclaw` (default) | Raspberry Pi 3/4/5 | [picoclaw.md](picoclaw.md) |
| **OpenClaw** | `openclaw` | Laptop / AI PC (x86_64, faster-whisper STT, Ollama LLM) | [openclaw-integration.md](openclaw-integration.md) |

### Target Hosts

| Host | Variant | Role | Web UI |
|---|---|---|---|
| **OpenClawPI2** | PicoClaw | Engineering / dev target (PI2) | `https://agents.sintaris.net/picoassist2/` |
| **OpenClawPI** | PicoClaw | Production (PI1) | `https://agents.sintaris.net/picoassist/` |
| **TariStation2** | OpenClaw | Local engineering workstation | `http://localhost:8080/` |
| **TariStation1** (SintAItion) | OpenClaw | Production workstation | `http://SintAItion:8080/` |

### Ecosystem Projects

| Project | Role | Language | Location |
|---------|------|----------|----------|
| **[sintaris-pl](https://github.com/stas-ka/sintaris-pl)** ← *this repo* | AI voice assistant: Telegram bot + Web UI + voice daemon | Python / FastAPI | `~/projects/sintaris-pl/` |
| **[sintaris-openclaw](https://github.com/stas-ka/sintaris-openclaw)** | OpenClaw AI gateway: skills hub, MCP server, Telegram bot `@suppenclaw_bot` | Node.js | `~/projects/sintaris-openclaw/` |
| **sintaris-openclaw-local-deploy** | Local dev launcher — symlinks into `sintaris-pl/src/`, separate `TARIS_HOME` | Shell scripts | `~/projects/sintaris-openclaw-local-deploy/` |
| **[sintaris](https://github.com/stas-ka/sintaris)** | Original standalone Taris gateway (historical predecessor) | Node.js | `~/projects/sintaris/` |
| **sintaris-srv** | VPS service infrastructure | Config/Nginx | `~/projects/sintaris-srv/` |

> **OpenClaw only:** `sintaris-openclaw` and `sintaris-pl` run together on the same laptop.  
> **PicoClaw only:** only `sintaris-pl` runs, on the Raspberry Pi.

### Variant Capability Comparison

| Feature | PicoClaw (Pi) | OpenClaw (Laptop) |
|---------|:---:|:---:|
| Telegram bot | ✅ | ✅ |
| Web UI | ✅ | ✅ |
| Standalone voice daemon | ✅ | ✅ |
| STT engine | Vosk (small-ru, 48MB) | faster-whisper (base, 300MB) |
| TTS engine | Piper (ONNX, offline) | Piper (ONNX, offline) |
| LLM | taris / openai / local | ollama / openclaw / openai |
| Local offline LLM | llama.cpp (taris-llm.service) | Ollama (qwen2:0.5b) |
| RAG / knowledge base | SQLite FTS5 | PostgreSQL + pgvector |
| REST API (`/api/*`) | ❌ | ✅ Bearer token |
| `skill-taris` (from OpenClaw) | ❌ | ✅ |
| Skills hub integration | ❌ | ✅ via sintaris-openclaw |
| GPU acceleration | ❌ (Pi has no GPU) | Optional (CUDA) |

---

## 1. Overview

A multi-modal personal assistant deployable on Raspberry Pi (PicoClaw) or laptop/PC (OpenClaw). Three parallel channels reach the same LLM backend:

1. **Telegram Menu Bot** (`bot = @smartpico_bot`) — interactive button-driven Telegram interface with text chat, voice sessions, notes, calendar, mail digest, and admin panel.
2. **Standalone Voice Assistant** (`voice_assistant.py`) — always-on wake-word loop using the Pi's microphone and speaker.
3. **FastAPI Web UI** (`bot_web.py`) — HTTPS web interface on port 8080 with full chat, voice (browser recording → STT → LLM → TTS), notes, calendar, mail, and admin panel. JWT cookie authentication. PWA-installable.

All three channels call the same LLM backend (`bot_llm.py`) and share the same data layer. The Telegram and Web UI channels additionally share a common **Screen DSL** (`bot_ui.py` + `bot_actions.py` + `render_telegram.py`) so that action logic is written once and rendered by each channel independently.

```
                        ┌────────────────────────────────────┐
                        │   Taris (sintaris-pl)              │
                        │                                    │
  Telegram API ─────────┤  telegram_menu_bot.py              │
                        │     bot_handlers.py                │
  Browser (port 8080) ──┤  bot_web.py (FastAPI + Jinja2)     ├─── bot_llm.py ─── LLM provider
                        │     bot_actions.py (Screen DSL)    │         │         (taris / openai /
  Microphone ───────────┤  voice_assistant.py                │         │          ollama / local ...)
                        │     hotword → STT → LLM → TTS      │         │
                        └────────────────────────────────────┘         │
                                                                        │ OpenClaw only
                                                                        ▼
                                                            sintaris-openclaw gateway
                                                            (skills: n8n, postgres, crm...)
```

### Voice Pipeline (PicoClaw default)

```
Microphone (USB / I2S HAT)
      │
      ▼
 [pw-record]   ← PipeWire subprocess (S16_LE, 16 kHz, mono)
      │              fallback: parec (PulseAudio compat layer)
      ▼
 [Vosk STT]    ← vosk-model-small-ru-0.22 (48 MB, offline, Kaldi-based)
      │              streaming decode, 250 ms chunks
      ▼
 Hotword gate  ← fuzzy SequenceMatcher match on "пико / пика / пике / пик"
      │              threshold: 0.75 similarity ratio
      ▼
 [Vosk STT]    ← same model, fresh recognizer for the command phrase
      │              stops on 2 s silence or 15 s max
      ▼
 [taris]    ← CLI subprocess: taris agent -m "<text>"
      │              binary: /usr/bin/picoclaw (sipeed/picoclaw v0.2.0)
      ▼
 [OpenRouter]  ← HTTPS call to openrouter.ai (cloud, configurable model)
      │              default: openrouter/openai/gpt-4o-mini
      ▼
 [Piper TTS]   ← ru_RU-irina-medium.onnx (ONNX Runtime, 66 MB, offline)
      │              output: raw S16_LE PCM at 22050 Hz
      ▼
   [aplay]     ← ALSA playback → Pi 3.5 mm jack / USB speaker
```

---

## 11. Process Hierarchy (at runtime)

```
systemd
  ├── taris-gateway.service
  │     └── /usr/bin/picoclaw gateway  (disabled — config "enabled": false)
  │
  ├── taris-telegram.service
  │     └── /usr/bin/python3 telegram_menu_bot.py
  │           │
  │           ├── [calendar daemon threads, started at startup]
  │           │     ├── _cal_morning_briefing_loop()   ← fires daily at 08:00
  │           │     └── threading.Timer per event      ← per-event reminder
  │           │
  │           ├── [per-message handlers] (telebot threading)
  │           │     ├── text_handler     → routes by _user_mode
  │           │     └── voice_handler    → _handle_voice_message()
  │           │           ├── ffmpeg [subprocess]           ← OGG → 16kHz PCM
  │           │           ├── vosk-cpp / whisper-cpp        ← STT
  │           │           ├── taris agent [subprocess]   ← LLM
  │           │           ├── piper [subprocess]            ← TTS synthesis
  │           │           └── ffmpeg [subprocess]           ← PCM → OGG Opus
  │           │
  │           ├── [mail refresh threads]
  │           │     └── _run_refresh_thread() per user  ← IMAP fetch + LLM
  │           │
  │           └── [email send threads]
  │                 └── _send_in_thread() per send op  ← SMTP
  │
  ├── taris-web.service
  │     └── uvicorn bot_web:app --host 0.0.0.0 --port 8080 --ssl-keyfile …
  │           │   FastAPI application (bot_web.py)
  │           │
  │           ├── GET/POST /login, /register     ← JWT cookie auth (bot_auth.py)
  │           ├── GET /                          ← dashboard (Jinja2 + HTMX)
  │           ├── GET /chat  POST /api/chat/send ← LLM chat (bot_llm.py)
  │           ├── GET /notes  GET /notes/{slug}  ← notes CRUD
  │           ├── GET /calendar                  ← calendar view
  │           ├── GET /mail  POST /api/mail/…    ← mail digest
  │           ├── GET /admin                     ← admin dashboard (admin-only)
  │           └── POST /api/voice/…              ← voice: upload/STT/TTS
  │
  └── taris-voice.service
        └── /usr/bin/python3 voice_assistant.py
              ├── pw-record [subprocess]  ← continuous hotword listen
              ├── pw-record [subprocess]  ← command recording (transient)
              ├── piper     [subprocess]  ← TTS synthesis
              └── aplay     [subprocess]  ← audio output
```

---

## 12. Module Map

```
src/
  telegram_menu_bot.py        ← Telegram bot entry point
  bot_web.py                  ← FastAPI web UI entry point
  voice_assistant.py          ← standalone voice daemon
  core/
    bot_config.py             ← all constants; root of import tree (no bot_* imports)
    bot_state.py              ← mutable runtime state dicts
    bot_instance.py           ← TeleBot singleton
    bot_db.py                 ← SQLite schema + connection helper
    bot_llm.py                ← pluggable LLM backend (8 providers + local fallback)
    bot_prompts.py            ← prompt templates
    bot_embeddings.py         ← EmbeddingService (fastembed / sentence-transformers)
    store_base.py             ← DataStore Protocol
    store.py                  ← factory (sqlite / postgres)
    store_sqlite.py           ← SQLite adapter
    store_postgres.py         ← PostgreSQL + pgvector adapter (OpenClaw)
  security/
    bot_security.py           ← 3-layer prompt injection guard
    bot_auth.py               ← JWT/bcrypt web authentication
  telegram/
    bot_access.py             ← access control, i18n _t(), keyboards
    bot_admin.py              ← admin panel: users, LLM switcher, voice opts
    bot_handlers.py           ← user handlers: chat, digest, notes, profile
    bot_users.py              ← registration + notes file I/O
  features/
    bot_voice.py              ← voice pipeline: STT / TTS / VAD / multi-part TTS
    bot_calendar.py           ← smart calendar: NL add, query, reminders, briefing
    bot_contacts.py           ← contact book CRUD
    bot_mail_creds.py         ← per-user IMAP + digest fetch
    bot_email.py              ← SMTP send-as-email
    bot_error_protocol.py     ← error report: collect text/voice/photo → email
    bot_documents.py          ← document upload / RAG knowledge base
  ui/
    bot_ui.py                 ← Screen DSL dataclasses (Screen, Button, Card, …)
    bot_actions.py            ← action handlers → Screen objects (shared logic)
    render_telegram.py        ← Telegram renderer: Screen → InlineKeyboardMarkup
    screen_loader.py          ← YAML/JSON screen file loader
  screens/                    ← declarative YAML screen definitions
  web/
    templates/                ← Jinja2 HTML templates
    static/                   ← CSS, PWA manifest, JS
  services/
    taris-telegram.service    ← systemd unit for Telegram bot
    taris-web.service         ← systemd unit for Web UI (uvicorn)
    taris-voice.service       ← systemd unit for voice daemon
    taris-llm.service         ← systemd unit for local llama.cpp (optional)
  setup/
    setup_voice.sh            ← PicoClaw: install Vosk + Piper + PipeWire
    setup_voice_openclaw.sh   ← OpenClaw: install Vosk + Piper + faster-whisper
    setup_llm_openclaw.sh     ← OpenClaw: install Ollama + pull default model
    install_embedding_model.sh ← download + verify embedding model
  tests/
    test_voice_regression.py  ← regression suite T01–T30
    benchmark_stt.py          ← Vosk vs faster-whisper benchmark
    llm/                      ← LLM provider unit tests (18 tests for _ask_openclaw)
```

---

## 13. Key External Links

| Component | Link |
|-----------|------|
| sintaris-pl (this repo) | https://github.com/stas-ka/sintaris-pl |
| sintaris-openclaw (AI gateway) | https://github.com/stas-ka/sintaris-openclaw |
| taris/picoclaw binary releases | https://github.com/sipeed/picoclaw/releases |
| Vosk STT models | https://alphacephei.com/vosk/models |
| Piper TTS | https://github.com/rhasspy/piper |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper |
| Ollama | https://ollama.ai |
| OpenRouter (cloud LLM) | https://openrouter.ai |
| llama.cpp | https://github.com/ggerganov/llama.cpp |

→ For variant-specific details:  
→ PicoClaw: [picoclaw.md](picoclaw.md)  
→ OpenClaw: [openclaw-integration.md](openclaw-integration.md)
