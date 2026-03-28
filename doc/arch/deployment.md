# Taris — Deployment, File Layout & Configuration

**Version:** `2026.3.43`  
→ Architecture index: [architecture.md](../architecture.md)

---

## Deployment Variants

Taris supports two deployment targets, controlled by `DEVICE_VARIANT` in `bot.env`:

| Variant | `DEVICE_VARIANT` | Hardware | LLM Provider | REST API |
|---|---|---|---|---|
| **PicoClaw** | `picoclaw` (default) | Raspberry Pi 4/5 | `taris` / `openai` / `local` | No (not needed) |
| **OpenClaw** | `openclaw` | Laptop / Mini-PC | `openclaw` → GPT-5+ / `openai` | Yes (`/api/status`, `/api/chat`) |

### Variant: PicoClaw (Raspberry Pi)

- `DEVICE_VARIANT=picoclaw` (or unset)
- Offline voice pipeline: Vosk STT + Piper TTS
- LLM: taris binary, OpenAI, or local llama.cpp
- Web UI on `:8080` (local network only)
- REST API endpoints NOT needed (no external skill calls)
- Screen DSL menus: standard buttons only (no OpenClaw controls)

### Variant: OpenClaw (Laptop / Mini-PC)

- `DEVICE_VARIANT=openclaw`
- Runs alongside `sintaris-openclaw` (Node.js AI gateway on `:18789`)
- LLM: `openclaw` routes to GPT-5+/Codex via the local OpenClaw gateway
- REST API active: `/api/status` and `/api/chat` (Bearer token via `TARIS_API_TOKEN`)
- `skill-taris` in sintaris-openclaw calls these endpoints
- Screen DSL menus: shows additional OpenClaw buttons (`visible_variants: [openclaw]`)
- ⚠️ **Loop prevention**: if `LLM_PROVIDER=openclaw`, skill-taris must NOT relay
  chat requests back to Taris (creates an infinite loop)

### Integration Diagram (OpenClaw variant)

```
User (Telegram)
     │
     ├──► @taris_bot (sintaris-pl)
     │         │ LLM_PROVIDER=openclaw
     │         └──► openclaw agent --message ...
     │                    │
     │                    └──► GPT-5+/Codex (OpenAI)
     │
     └──► @suppenclaw_bot (sintaris-openclaw)
               │ skill-taris
               └──► POST /api/chat → sintaris-pl :8080
                         (notes, calendar, status queries)
```

---

## 12. File Layout on Pi

The runtime data directory is `~/.taris/` by default. Override with `TARIS_HOME` env var
(see §13 `TARIS_HOME`) for alternative deployments (local dev, multi-instance).

```
/home/stas/.taris/          ← TARIS_HOME (default)
  ── entry points ──
  telegram_menu_bot.py          ← Telegram bot entry point
  bot_web.py                    ← FastAPI web UI entry point
  voice_assistant.py            ← standalone voice daemon
  gmail_digest.py               ← legacy shared digest cron (deprecated)

  ── Python packages (subdirectories) ──
  core/
    bot_config.py               ← constants, TARIS_DIR, env loading, logging
    bot_state.py                ← mutable runtime state dicts
    bot_instance.py             ← TeleBot singleton
    bot_db.py                   ← SQLite schema + connection helper
    bot_llm.py                  ← pluggable LLM backend abstraction
    bot_prompts.py              ← prompt templates
    store_base.py               ← DataStore Protocol definition
    store.py                    ← factory singleton (sqlite / postgres)
    store_sqlite.py             ← SQLite adapter
    store_postgres.py           ← PostgreSQL + pgvector adapter (OpenClaw)
  security/
    bot_security.py             ← 3-layer prompt injection guard
    bot_auth.py                 ← JWT/bcrypt web authentication
  telegram/
    bot_access.py               ← access control, i18n, keyboards, _ask_taris
    bot_admin.py                ← admin panel handlers
    bot_handlers.py             ← user handlers: chat, digest, notes, profile, system
    bot_users.py                ← registration + notes file I/O
  features/
    bot_voice.py                ← full voice pipeline: STT/TTS/VAD + multi-part TTS
    bot_calendar.py             ← smart calendar: CRUD, NL parser, reminders, briefing
    bot_contacts.py             ← contact book CRUD
    bot_mail_creds.py           ← per-user IMAP credentials + digest
    bot_email.py                ← send-as-email SMTP
    bot_error_protocol.py       ← error protocol: collect text/voice/photo → save → email
    bot_documents.py            ← document upload / RAG knowledge base
  ui/
    bot_ui.py                   ← Screen DSL dataclasses: Screen, Button, Card, Toggle
    bot_actions.py              ← action handlers returning Screen objects
    render_telegram.py          ← Telegram renderer: Screen → send_message / InlineKeyboard
    screen_loader.py            ← YAML/JSON screen file loader (10 widget types)
  screens/                      ← Declarative YAML screen definitions
    main_menu.yaml · admin_menu.yaml · help.yaml
    notes_menu.yaml · note_view.yaml · note_raw.yaml · note_edit.yaml
    profile.yaml · profile_lang.yaml · profile_my_data.yaml
    screen.schema.json          ← JSON Schema (draft-07) for screen validation

  ── shared data ──
  strings.json                  ← i18n UI strings (ru / de / en)
  release_notes.json            ← versioned changelog
  config.json                   ← taris LLM config (model_list, agents)
  prompts.json                  ← LLM prompt templates
  bot.env                       ← BOT_TOKEN + ALLOWED_USERS + ADMIN_USERS (secrets)

  ── Web UI channel ──
  bot_web.py                    ← FastAPI application: HTTP routes, Jinja2, HTMX endpoints
  bot_auth.py                   ← JWT/bcrypt authentication, accounts.json management
  bot_llm.py                    ← pluggable LLM backend abstraction (Telegram + Web share)
  bot_ui.py                     ← Screen DSL dataclasses: Screen, Button, Card, Toggle, etc.
  bot_actions.py                ← action handlers returning Screen objects (shared logic)
  render_telegram.py            ← Telegram renderer: Screen → send_message / InlineKeyboard
  templates/                    ← Jinja2 HTML templates
    base.html                   ← layout with PWA meta, HTMX, Alpine.js, Pico CSS
    login.html                  ← JWT login form
    register.html               ← user self-registration
    dashboard.html              ← main dashboard (links to all sections)
    chat.html                   ← free-text LLM chat with streaming
    notes.html                  ← notes list + create form
    _note_editor.html           ← note editor partial (HTMX)
    calendar.html               ← calendar view + add/edit events
    mail.html                   ← mail digest + refresh
    voice.html                  ← voice: record → STT → LLM → TTS playback
    admin.html                  ← admin dashboard (users, LLM, voice opts)
    _chat_messages.html         ← chat messages partial (HTMX swap)
  static/
    style.css                   ← custom styles on top of Pico CSS
    manifest.json               ← PWA manifest (icons, theme_color, shortcuts)

  ── auto-created runtime files ──
  accounts.json                 ← web UI user accounts (username + bcrypt hash)
  voice_opts.json               ← voice optimisation flags (do not commit)
  pending_tts.json              ← TTS orphan-cleanup tracker
  users.json                    ← dynamically approved guest users
  registrations.json            ← registration records (pending/approved/blocked)
  last_notified_version.txt     ← last BOT_VERSION admin notification
  active_model.txt              ← admin-selected LLM model name
  llm_fallback_enabled          ← LLM fallback flag file; presence=ON, absent=OFF (toggle from Admin Panel)
  notes/<chat_id>/<slug>.md     ← per-user Markdown notes
  calendar/<chat_id>.json       ← per-user calendar events
  mail_creds/<chat_id>.json     ← per-user IMAP credentials (chmod 600)
  mail_creds/<chat_id>_last_digest.txt   ← last digest cache
  mail_creds/<chat_id>_target.txt        ← send-as-email target address
  error_protocols/              ← admin error reports (YYYYMMDD-HHMMSS_name/)
  telegram_bot.log              ← bot log file

  ── voice models ──
  vosk-model-small-ru/          ← 48 MB Vosk Russian STT model
  vosk-model-small-de/          ← 48 MB Vosk German STT model (optional, for DE users)
  ru_RU-irina-medium.onnx       ← 66 MB Piper TTS voice (medium quality, Russian)
  ru_RU-irina-medium.onnx.json  ← Piper voice config
  ru_RU-irina-low.onnx          ← optional: low quality (faster TTS)
  ru_RU-irina-low.onnx.json     ← optional: low quality config
  de_DE-thorsten-medium.onnx    ← 66 MB Piper TTS voice (German, optional)
  de_DE-thorsten-medium.onnx.json ← Piper German voice config
  ggml-base.bin                 ← optional: Whisper STT model (142 MB)

/dev/shm/piper/                   ← optional tmpfs model copy (voice_opt: tmpfs_model)
/usr/local/bin/piper              ← Piper wrapper script
/usr/local/share/piper/           ← Piper binary + bundled libs
/usr/bin/picoclaw                 ← taris Go binary (from .deb)

/etc/systemd/system/
  taris-gateway.service
  taris-voice.service
  taris-telegram.service
  taris-web.service          ← FastAPI web UI (uvicorn HTTPS :8080)
```

---

## 13. Configuration Reference

### `TARIS_HOME` — Runtime Data Directory

Set `TARIS_HOME` in the OS environment **before** starting Python to redirect
all data paths away from the default `~/.taris/`.

```bash
export TARIS_HOME=~/projects/sintaris-openclaw-local-deploy/.taris
python3 telegram_menu_bot.py
```

This is the primary mechanism for local development deploys, multi-instance
setups, and CI environments. All 31 path constants in `bot_config.py` resolve
relative to `TARIS_DIR = os.environ.get("TARIS_HOME") or ~/.taris`.

**Do not set `TARIS_HOME` inside `bot.env`** — the env var must be present
before `bot_config.py` is imported (it is needed to find `bot.env` itself).

---

### Local Development Deploy

`~/projects/sintaris-openclaw-local-deploy/` is the local OpenClaw deployment.
It contains symlinks into `src/` and a `.taris/` data directory:

```
~/projects/sintaris-openclaw-local-deploy/
  core/ features/ security/ telegram/ ui/ screens/ web/  ← symlinks to src/
  telegram_menu_bot.py  bot_web.py  strings.json         ← symlinks to src/
  .taris/
    bot.env       ← credentials (BOT_TOKEN, ALLOWED_USER, OPENAI_API_KEY)
    taris.db      ← SQLite database (auto-created)
    notes/  calendar/  contacts/  ...
  run_telegram.sh   ← sets TARIS_HOME, starts Telegram bot
  run_web.sh        ← sets TARIS_HOME + WEB_ONLY=1, starts uvicorn --reload
  run_all.sh        ← starts both in background
```

---

### `bot_config.py` constants

| Constant | Value | Env override | Description |
|---|---|---|---|
| `TARIS_DIR` | `~/.taris` | `TARIS_HOME` | Runtime data directory — base for all paths |
| `BOT_VERSION` | `"2026.3.43"` | — | Version string; bump on every user-visible change |
| `PIPER_BIN` | `/usr/local/bin/piper` | `PIPER_BIN` | Piper TTS wrapper binary |
| `PIPER_MODEL` | `~/.taris/ru_RU-irina-medium.onnx` | `PIPER_MODEL` | Default Piper voice model |
| `PIPER_MODEL_LOW` | `~/.taris/ru_RU-irina-low.onnx` | `PIPER_MODEL_LOW` | Low-quality Piper model |
| `WHISPER_BIN` | `/usr/local/bin/whisper-cpp` | `WHISPER_BIN` | whisper.cpp binary |
| `WHISPER_MODEL` | `~/.taris/ggml-base.bin` | `WHISPER_MODEL` | Whisper model file |
| `VOSK_MODEL_PATH` | `~/.taris/vosk-model-small-ru` | `VOSK_MODEL_PATH` | Vosk model directory |
| `VOICE_SAMPLE_RATE` | `16000` | — | Base STT decode rate (Hz) |
| `VOICE_CHUNK_SIZE` | `4000` | — | Frames per processing chunk (250 ms) |
| `VOICE_SILENCE_TIMEOUT` | `4.0` | — | Silence timeout for voice recording (s) |
| `VOICE_MAX_DURATION` | `30.0` | — | Hard voice session cap (s) |
| `TTS_MAX_CHARS` | `600` | — | Real-time voice TTS cap (~25 s on Pi 3) |
| `TTS_CHUNK_CHARS` | `1200` | — | Per-part "Read aloud" cap (~55 s on Pi 3) |
| `VOICE_TIMING_DEBUG` | `false` | `VOICE_TIMING_DEBUG=1` | Per-stage latency log output |
| `NOTES_DIR` | `~/.taris/notes` | `NOTES_DIR` | Base dir for note files |
| `CALENDAR_DIR` | `~/.taris/calendar` | `CALENDAR_DIR` | Base dir for calendar files |
| `MAIL_CREDS_DIR` | `~/.taris/mail_creds` | `MAIL_CREDS_DIR` | Base dir for mail credentials |
| `REGISTRATIONS_FILE` | `~/.taris/registrations.json` | `REGISTRATIONS_FILE` | User registration records |
| `STRINGS_FILE` | `strings.json` next to script | `STRINGS_FILE` | i18n UI text file (ru / de / en) |
| `VOSK_MODEL_DE_PATH` | `~/.taris/vosk-model-small-de` | `VOSK_MODEL_DE_PATH` | Vosk German STT model directory |
| `PIPER_MODEL_DE` | `~/.taris/de_DE-thorsten-medium.onnx` | `PIPER_MODEL_DE` | Piper German TTS voice model |
| `TARIS_BIN` | `/usr/bin/picoclaw` | `TARIS_BIN` | taris Go binary |
| `LLM_PROVIDER` | `"taris"` | `LLM_PROVIDER` | Active LLM backend (`taris`/`openai`/`yandexgpt`/`gemini`/`anthropic`/`local`) |
| `LLAMA_CPP_URL` | `http://127.0.0.1:8081` | `LLAMA_CPP_URL` | Local llama.cpp server endpoint |
| `LLM_LOCAL_FALLBACK` | `false` | `LLM_LOCAL_FALLBACK` | Set `true` to enable static auto-fallback to local LLM |
| `LLM_FALLBACK_FLAG_FILE` | `~/.taris/llm_fallback_enabled` | — | Flag file; presence=fallback ON (runtime toggle, no restart needed) |
| `RAG_ENABLED` | `true` | `RAG_ENABLED` | Master on/off switch for FTS5/RAG context injection |
| `RAG_TOP_K` | `3` | `RAG_TOP_K` | Max document chunks injected per LLM request |
| `RAG_CHUNK_SIZE` | `512` | `RAG_CHUNK_SIZE` | Characters per text chunk when indexing documents |
| `RAG_FLAG_FILE` | `~/.taris/rag_disabled` | — | Flag file; presence=RAG OFF (runtime toggle, no restart needed) |

### `voice_assistant.py` CONFIG

| Key | Default | Env Override | Description |
|---|---|---|---|
| `vosk_model_path` | `/home/stas/.taris/vosk-model-small-ru` | `VOSK_MODEL_PATH` | Vosk model directory |
| `piper_bin` | `/usr/local/bin/piper` | `PIPER_BIN` | Piper TTS binary |
| `piper_model` | `/home/stas/.taris/ru_RU-irina-medium.onnx` | `PIPER_MODEL` | Piper voice model |
| `taris_bin` | `/usr/bin/picoclaw` | `TARIS_BIN` | taris binary |
| `audio_target` | `auto` | `AUDIO_TARGET` | Microphone selection |
| `sample_rate` | `16000` | — | Audio capture rate (Hz) |
| `chunk_size` | `4000` | — | Frames per processing chunk |
| `hotwords` | `["пико", "пика", ...]` | — | Wake words list |
| `hotword_threshold` | `0.75` | — | Fuzzy match sensitivity |
| `silence_timeout` | `2.0` | — | Seconds of silence to end recording |
| `max_phrase_duration` | `15.0` | — | Max command recording length (s) |
| `min_phrase_chars` | `3` | — | Minimum chars to accept STT result |

---

## 15. Backup System

Three-tier backup strategy:

| Tier | Location | What | Scripts |
|---|---|---|---|
| Source | GitHub (`master`) | Code, configs, service files, docs | git push |
| Image | `/mnt/ssd/backups/images/` | Full SD card `.img.zst` | `src/setup/backup_image.sh` |
| Remote | Nextcloud `/MicoBackups/` | Images + recovery bundles | `src/setup/backup_nextcloud.sh` |

| Script | Purpose |
|---|---|
| `src/setup/backup_image.sh` | `dd | zstd` full image + SHA-256 checksum |
| `src/setup/backup_nextcloud.sh` | WebDAV upload/download/list/prune via curl |
| `src/setup/install.sh` | Complete fresh-install bootstrap |
| `src/setup/update.sh` | Incremental update: deploy files, restart services |

**Nextcloud env vars** (in `bot.env`): `NEXTCLOUD_URL`, `NEXTCLOUD_USER`, `NEXTCLOUD_PASS`, `NEXTCLOUD_REMOTE` (default `/MicoBackups`).

---

## 16. Release Notes & Version Tracking

| Item | Value |
|---|---|
| Constant | `BOT_VERSION = "2026.3.43"` in `bot_config.py` |
| Format | `YYYY.M.D` (no zero-padding) |
| Changelog source | `release_notes.json` (deployed alongside bot) |
| Tracking file | `~/.taris/last_notified_version.txt` (auto-created) |
| Trigger | On startup: if `BOT_VERSION != last_notified`, send release entry to all admins |
| Admin view | Admin panel → 📝 Release Notes shows full changelog |
