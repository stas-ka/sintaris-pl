# Picoclaw Bot — Architecture

**Version:** `2026.3.32` · **Last updated:** March 2026

This document is an **index**. All architectural content lives in topic files under `doc/arch/`.
Do NOT read this file beyond the table below — load only the specific topic file you need.

## Topic Index

| Topic | File | When to read |
|---|---|---|
| System overview, process hierarchy | [overview.md](arch/overview.md) | Understanding overall structure |
| Voice pipeline (STT/TTS/VAD/hotword/PipeWire) | [voice-pipeline.md](arch/voice-pipeline.md) | Modifying `bot_voice.py` or `voice_assistant.py` |
| Telegram bot modules, chat routing, callbacks | [telegram-bot.md](arch/telegram-bot.md) | Adding handlers, callbacks, menu buttons |
| Security, RBAC, prompt injection guard | [security.md](arch/security.md) | Modifying `bot_security.py` or access logic |
| Feature domains (mail, calendar, email, registration) | [features.md](arch/features.md) | Adding or modifying user features |
| Deployment, file layout, config, backup, versioning | [deployment.md](arch/deployment.md) | Deploying or changing config constants |
| Multilanguage support (ru/de/en), i18n, `_t()` | [multilanguage.md](arch/multilanguage.md) | Adding i18n strings or a new language |
| Web UI (FastAPI, routes, auth, Screen DSL) | [web-ui.md](arch/web-ui.md) | Modifying `bot_web.py` or templates |
| LLM provider abstraction, multi-provider dispatch, offline fallback | [llm-providers.md](arch/llm-providers.md) | Modifying `bot_llm.py` or adding LLM providers |
