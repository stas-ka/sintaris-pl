# Taris Bot — Architecture

**Version:** `2026.3.28` · **Last updated:** March 2026

This document is an **index**. All architectural content lives in topic files under `doc/arch/`.
Do NOT read this file beyond the table below — load only the specific topic file you need.

## Topic Index

| Topic | File | When to read |
|---|---|---|
| System overview, channels, ecosystem map | [overview.md](arch/overview.md) | Understanding overall structure; variant comparison |
| **PicoClaw variant** (Raspberry Pi) | [picoclaw.md](arch/picoclaw.md) | Pi hardware, Vosk STT, Piper TTS, deploy workflow |
| **OpenClaw variant** (Laptop/PC) | [openclaw-integration.md](arch/openclaw-integration.md) | faster-whisper, Ollama, REST API, sintaris-openclaw integration |
| Voice pipeline (STT/TTS/VAD/hotword/PipeWire) | [voice-pipeline.md](arch/voice-pipeline.md) | Modifying `bot_voice.py` or `voice_assistant.py` |
| Telegram bot modules, chat routing, callbacks | [telegram-bot.md](arch/telegram-bot.md) | Adding handlers, callbacks, menu buttons |
| Security, RBAC, prompt injection guard | [security.md](arch/security.md) | Modifying `bot_security.py` or access logic |
| Feature domains (mail, calendar, email, registration) | [features.md](arch/features.md) | Adding or modifying user features |
| Deployment, file layout, config, backup, versioning | [deployment.md](arch/deployment.md) | Deploying or changing config constants |
| Multilanguage support (ru/de/en), i18n, `_t()` | [multilanguage.md](arch/multilanguage.md) | Adding i18n strings or a new language |
| Web UI (FastAPI, routes, auth, Screen DSL) | [web-ui.md](arch/web-ui.md) | Modifying `bot_web.py` or templates |
| LLM provider abstraction, multi-provider dispatch, offline fallback | [llm-providers.md](arch/llm-providers.md) | Modifying `bot_llm.py` or adding LLM providers |
| **Conversation architecture** — message structure, routing, tiered memory, RAG | [conversation.md](arch/conversation.md) | Modifying LLM message structure, history, memory, RAG injection |
| **Data layer** — SQLite/Postgres backends, schema, store API, file paths | [data-layer.md](arch/data-layer.md) | Adding DB columns, switching backends, data paths |
| **Software stacks** — all libraries, binaries, third-party services per variant | [stacks.md](arch/stacks.md) | Checking dependencies, upgrading packages, adding third-party tools |
| **Knowledge base** — RAG pipeline, document indexing, knowledge sources for conversation | [knowledge-base.md](arch/knowledge-base.md) | Modifying RAG, documents, notes-as-KB, calendar context injection |
