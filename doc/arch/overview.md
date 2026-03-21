# Taris — System Overview

**Version:** `2026.3.28` · **Last updated:** March 2026  
→ Architecture index: [architecture.md](../architecture.md)

---

## 1. Overview

A multi-modal personal assistant running on a Raspberry Pi 3 B+. Three parallel channels reach the same LLM backend:

1. **Telegram Menu Bot** (`bot = @smartpico_bot`) — interactive button-driven Telegram interface with text chat, voice sessions, notes, calendar, mail digest, and admin panel.
2. **Standalone Voice Assistant** (`voice_assistant.py`) — always-on wake-word loop using the Pi's microphone and speaker.
3. **FastAPI Web UI** (`bot_web.py`) — HTTPS web interface on port 8080 with full chat, voice (browser recording → STT → LLM → TTS), notes, calendar, mail, and admin panel. JWT cookie authentication. PWA-installable.

All three channels call the same LLM backend (`bot_llm.py`) and share the same data layer. The Telegram and Web UI channels additionally share a common **Screen DSL** (`bot_ui.py` + `bot_actions.py` + `render_telegram.py`) so that action logic is written once and rendered by each channel independently.

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
