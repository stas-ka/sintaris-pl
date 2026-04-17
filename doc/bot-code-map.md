# Telegram Menu Bot — Code Map

**Architecture:** 20-module split — Telegram core (v2026.3.19) + shared LLM/auth + Web UI layer (v2026.3.28)  
**Entry point (Telegram):** `src/telegram_menu_bot.py` (~280 lines — handlers + `main()`)  
**Entry point (Web):** `src/bot_web.py` — FastAPI application, all HTTP routes  
**Version:** 2026.4.1

Use this map to locate any function by module. Modules are organized into packages under `src/`:

| Package | Path | Contents |
|---|---|---|
| `core/` | `src/core/` | bot_config, bot_state, bot_instance, bot_db, bot_llm |
| `security/` | `src/security/` | bot_security, bot_auth |
| `telegram/` | `src/telegram/` | bot_access, bot_users, bot_admin, bot_handlers |
| `features/` | `src/features/` | bot_voice, bot_calendar, bot_contacts, bot_mail_creds, bot_email, bot_error_protocol |
| `ui/` | `src/ui/` | bot_ui, bot_actions, render_telegram |
| `src/` (root) | entry points | telegram_menu_bot.py, bot_web.py, voice_assistant.py, gmail_digest.py |
    → bot_voice → bot_calendar → bot_mail_creds → bot_email
    → bot_admin → bot_handlers → bot_error_protocol → telegram_menu_bot

bot_config → bot_llm          ← pluggable LLM backend (shared by Telegram + Web)
bot_config → bot_auth         ← JWT/bcrypt auth (used by Web UI only)
bot_ui     → bot_actions      ← Screen DSL action handlers (shared)
bot_actions ← render_telegram ← Telegram renderer (reads bot_actions output)
bot_actions ← bot_web         ← Web renderer (reads bot_actions output via Jinja2)
```

---

## Module Overview

| Module | Package | Lines | Responsibility |
|---|---|---|---|
| `bot_config.py` | `core/` | ~120 | Constants, env loading, logging setup — no deps; exports `TARIS_DIR` |
| `bot_state.py` | `core/` | ~115 | Mutable runtime dicts, voice_opts/dynamic_users I/O; web link codes |
| `bot_instance.py` | `core/` | ~12 | `bot = TeleBot(...)` singleton |
| `bot_db.py` | `core/` | ~60 | SQLite schema + `init_db()` + thread-local connection; uses `TARIS_DIR` |
| `store_base.py` | `core/` | ~60 | `DataStore` Protocol + `StoreCapabilityError` |
| `store.py` | `core/` | ~50 | Factory singleton `create_store()` — selects SQLite or PostgreSQL adapter; uses `TARIS_DIR` |
| `store_sqlite.py` | `core/` | ~320 | Full SQLite adapter with optional sqlite-vec vector support |
| `store_postgres.py` | `core/` | ~200 | PostgreSQL + pgvector adapter (OpenClaw / VPS) |
| `bot_llm.py` | `core/` | ~250 | Pluggable LLM backend — 6 providers via `LLM_PROVIDER`; `ask_llm()` unified entry point; shared by Telegram + Web |
| `bot_security.py` | `security/` | ~200 | 3-layer prompt injection guard; `SECURITY_PREAMBLE`; `_wrap_user_input()` |
| `bot_auth.py` | `security/` | ~200 | JWT/bcrypt authentication, `accounts.json` — Web UI only |
| `bot_access.py` | `telegram/` | ~380 | Access control, i18n, keyboards, text utils, `_ask_taris()` |
| `bot_users.py` | `telegram/` | ~160 | Registration + notes file I/O (pure, no Telegram API) |
| `bot_admin.py` | `telegram/` | ~310 | Admin panel: guests, reg, voice opts, release notes, LLM |
| `bot_handlers.py` | `telegram/` | ~160 | User handlers: chat, system, digest, notes, profile |
| `bot_voice.py` | `features/` | ~280 | Full voice pipeline: STT/TTS/VAD + pending TTS tracker |
| `bot_calendar.py` | `features/` | ~650 | Smart calendar: CRUD, NL parser, reminders, briefing, TTS, multi-event |
| `bot_contacts.py` | `features/` | ~300 | Contact book: CRUD, search, Telegram UI |
| `bot_mail_creds.py` | `features/` | ~450 | Per-user IMAP creds, consent flow, digest fetch + LLM summarise |
| `bot_email.py` | `features/` | ~250 | Send-as-email SMTP for notes, digest, calendar events |
| `bot_error_protocol.py` | `features/` | ~260 | Error protocol: collect text/voice/photo → save dir → email |
| `bot_ui.py` | `ui/` | ~150 | Screen DSL dataclasses: `Screen`, `Button`, `Card`, `Toggle`, `Spinner`, etc. |
| `bot_actions.py` | `ui/` | ~300 | Action handlers returning `Screen` objects — shared logic layer |
| `render_telegram.py` | `ui/` | ~220 | Renders `Screen` → Telegram `send_message` / `InlineKeyboardMarkup` |
| `screen_loader.py` | `ui/` | ~330 | Declarative YAML/JSON → `Screen` loader with schema validation, caching, i18n, visibility rules |
| `screen.schema.json` | `screens/` | ~200 | JSON Schema (draft-07) for YAML screen file validation — all 10 widget types |
| `*.yaml` (10 files) | `screens/` | ~15 ea | Declarative screen definitions: main_menu, admin_menu, help, notes_menu, note_view, note_raw, note_edit, profile, profile_lang, profile_my_data |
| `telegram_menu_bot.py` | `src/` | ~280 | Entry point: handlers + `main()` |
| `bot_web.py` | `src/` | ~2000 | FastAPI app: all HTTP routes, Jinja2 templates, HTMX endpoints, HTTPS :8080 |

## core/bot_config.py — Constants & Configuration

No imports from other `bot_*` modules. Root of the dependency tree.

| Symbol / Function | Purpose |
|---|---|
| `TARIS_DIR` | Runtime data directory — `os.environ.get("TARIS_HOME") or ~/.taris` |
| `_th(rel)` | Helper: `os.path.join(TARIS_DIR, rel)` — used internally for all 31 path constants |
| `BOT_VERSION` | `"YYYY.M.D"` — bump on every user-visible change |
| `BOT_TOKEN` | Telegram bot token from `bot.env` |
| `ALLOWED_USERS` | `set[int]` — full-access chat IDs |
| `ADMIN_USERS` | `set[int]` — admin chat IDs |
| `DEVICE_VARIANT` | `"picoclaw"` or `"openclaw"` — controls variant-specific features |
| `TARIS_BIN` | `/usr/bin/picoclaw` |
| `TARIS_CONFIG` | `TARIS_DIR/config.json` |
| `ACTIVE_MODEL_FILE` | `TARIS_DIR/active_model.txt` |
| `PIPER_BIN` | `/usr/local/bin/piper` |
| `PIPER_MODEL` | `TARIS_DIR/ru_RU-irina-medium.onnx` |
| `PIPER_MODEL_TMPFS` | `/dev/shm/piper/...` (RAM-disk copy) |
| `PIPER_MODEL_LOW` | `TARIS_DIR/ru_RU-irina-low.onnx` |
| `WHISPER_BIN` | `/usr/local/bin/whisper-cpp` |
| `WHISPER_MODEL` | `TARIS_DIR/ggml-base.bin` |
| `VOSK_MODEL_PATH` | `TARIS_DIR/vosk-model-small-ru/` |
| `NOTES_DIR` | `TARIS_DIR/notes/` |
| `_PENDING_TTS_FILE` | `TARIS_DIR/pending_tts.json` |
| `_VOICE_OPTS_DEFAULTS` | All 10 voice-opt flags (all `False`) |
| `_load_env_file(path)` | Parse `KEY=VALUE` file → `os.environ` |
| `log` | `logging.getLogger("taris-tgbot")` |

---

## bot_state.py — Mutable Runtime State

Imports: `bot_config` only.

| Symbol / Function | Purpose |
|---|---|
| `_user_mode` | `dict[int, str]` — `None` / `'chat'` / `'system'` / `'voice'` / … |
| `_pending_cmd` | `dict[int, str]` — confirmed bash command awaiting `run:` |
| `_user_lang` | `dict[int, str]` — `'ru'` / `'en'` per chat_id |
| `_user_audio` | `dict[int, bool]` — audio on/off per user (opt `user_audio_toggle`) |
| `_pending_note` | `dict[int, dict]` — multi-step note creation state |
| `_pending_llm_key` | `dict[int, str]` — waiting for LLM API key input |
| `_vosk_model_cache` | `None` or loaded `vosk.Model` singleton |
| `_persistent_piper_proc` | `None` or keepalive `subprocess.Popen` |
| `_voice_opts` | Live `dict` loaded from `voice_opts.json` |
| `_dynamic_users` | `set[int]` — runtime-approved guest users |
| `_load_voice_opts()` | Load `voice_opts.json` → merge with defaults |
| `_save_voice_opts()` | Persist `_voice_opts` to disk |
| `_load_dynamic_users()` | Load `users.json` |
| `_save_dynamic_users()` | Persist `_dynamic_users` to disk |
| `_web_link_codes` | `dict[str, tuple[int, float]]` — active Telegram↔Web link codes (code → (chat_id, expiry)) |
| `generate_web_link_code(chat_id)` | Create 6-char uppercase code with 15-min TTL → returns code string |
| `validate_web_link_code(code)` | Verify code is valid + not expired → returns `chat_id` and consumes code (one-time use) |
| `add_to_history(chat_id, role, content)` | Append message to `chat_history` DB; triggers tiered summarization at `CONV_SUMMARY_THRESHOLD` |
| `load_conversation_history()` | Load all user histories from DB on startup |
| `get_memory_context(chat_id)` | Return formatted summaries string (mid + long tier) for injection into system message |
| `_summarize_session_async(chat_id)` | Background thread: summarizes oldest messages → `conversation_summaries` table |
| `clear_history(chat_id)` | Clear `chat_history` + `conversation_summaries` for user (all tiers) |

---

## bot_instance.py — Bot Singleton

Imports: `bot_config` only.

| Symbol | Purpose |
|---|---|
| `_409Handler` | `ExceptionHandler` subclass; swallows `ApiException` with HTTP 409 (Conflict) so a stale long-poll connection on restart doesn't crash the process |
| `bot` | `telebot.TeleBot(BOT_TOKEN, parse_mode=None, exception_handler=_409Handler())` — shared by all modules; `parse_mode=None` prevents silent send failures when LLM/user content contains Markdown special characters |

---

## core/bot_db.py — SQLite Layer

Imports: `bot_config` (incl. `TARIS_DIR`).

| Symbol / Function | Purpose |
|---|---|
| `DB_PATH` | `TARIS_DIR/taris.db` — SQLite database file path |
| `init_db(conn)` | `CREATE TABLE IF NOT EXISTS` for all tables — safe to call on every startup |
| `get_conn()` | Thread-local `sqlite3.Connection` (auto-opens + inits on first use per thread) |

---

## core/store.py — DataStore Factory

Imports: `bot_config` (incl. `TARIS_DIR`), `store_base`.

| Symbol / Function | Purpose |
|---|---|
| `create_store()` | Reads `STORE_BACKEND`; returns SQLite or PostgreSQL adapter |
| `store` | Module-level singleton — `from core.store import store` |

---

## core/bot_rag.py — RAG Intelligence Layer *(v2026.4.1)*

Imports: `bot_config`, `core.store`, `core.bot_mcp_client`.

| Function | Returns | Purpose |
|---|---|---|
| `classify_query(text, has_documents)` | `"simple"\|"factual"\|"contextual"` | Heuristic — no LLM. Simple=short/greeting, factual=knowledge+docs, contextual=fallback |
| `detect_rag_capability()` | `RAGCapability` enum | Checks RAM (psutil) + vector availability; cached after first call |
| `reciprocal_rank_fusion(fts5_results, vector_results, k=60)` | merged list | Deduplicates by `id`, scores with 1/(rank+k), sorts descending |
| `retrieve_context(chat_id, query, top_k, max_chars)` | `(chunks, assembled, strategy)` | Unified entry point: auto-selects FTS5_ONLY / HYBRID / FULL; merges MCP remote chunks via RRF if `MCP_REMOTE_URL` set |

`RAGCapability` enum values: `FTS5_ONLY` (< 4 GB RAM), `HYBRID` (4-8 GB), `FULL` (≥ 8 GB)
Strategy string extended with `+mcp` when remote chunks merged (e.g. `"hybrid+mcp"`).

---

## core/bot_mcp_client.py — Remote MCP RAG Client *(v2026.4.1)*

Imports: `bot_config`, stdlib `urllib.request`, `json`.

| Function | Returns | Purpose |
|---|---|---|
| `query_remote(query, chat_id, top_k)` | `list[dict]` | POST to `MCP_REMOTE_URL/search`; returns chunk dicts `{text, score, source}`; skips if CB open |
| `circuit_status()` | `dict` | Returns CB health: `{state, failures, last_failure, reset_at}` |
| `_cb_is_open()` | `bool` | True = circuit open (fail fast, skip remote); checks `_CB_RESET_SEC=300` cooldown |
| `_cb_record_failure()` | — | Increments `_cb_failures`; opens CB after `_CB_THRESHOLD=3` |
| `_cb_record_success()` | — | Resets `_cb_failures` to 0, closes CB |

Auth: `TARIS_API_TOKEN` as `Bearer` header. No external SDK required (stdlib only).

---

## features/bot_dev.py — Developer Menu *(v2026.3.32)*

Imports: `bot_config`, `bot_instance`, `core.bot_db`.

| Function | Purpose |
|---|---|
| `handle_dev_menu(chat_id)` | Sends developer menu keyboard (only to `_is_developer()` users) |
| `handle_dev_chat(chat_id, call)` | Sets `_user_mode = "dev_chat"`, sends mode indicator |
| `handle_dev_restart(chat_id)` | Sends confirm-restart prompt with `dev_restart_confirmed` callback |
| `handle_dev_restart_confirmed(chat_id)` | `systemctl restart taris-telegram` — requires developer role |
| `handle_dev_log(chat_id)` | Sends last 30 lines of `telegram_bot.log` |
| `handle_dev_error(chat_id)` | Sends last ERROR entry from journal |
| `handle_dev_files(chat_id)` | Lists `~/.taris/*.py` with sizes + mtimes |
| `handle_dev_security_log(chat_id)` | Fetches last 20 rows from `security_events` table |
| `log_security_event(chat_id, event_type, detail)` | INSERT into `security_events` table |
| `log_access_denied(chat_id, resource)` | Convenience wrapper: `log_security_event(…, "access_denied", …)` |

---



Imports: `bot_config`, `bot_state`, `bot_instance`.

### Access control

| Function | Purpose |
|---|---|
| `_is_allowed(chat_id)` | True if admin, full user, or approved guest |
| `_is_admin(chat_id)` | True if in `ADMIN_USERS` |
| `_is_guest(chat_id)` | True if runtime-added (not in static lists) |
| `_deny(chat_id)` | Send "⛔ Access denied" message |

### i18n

| Function | Purpose |
|---|---|
| `_load_strings(path)` | Load `strings.json` |
| `_set_lang(chat_id, from_user)` | Cache best-supported language (`ru` / `en`) |
| `_lang(chat_id)` | Get cached language for chat_id |
| `_t(chat_id, key, **kwargs)` | Get translated string by key |

### Language detection

| Function | Purpose |
|---|---|
| `_detect_text_lang(text)` | Heuristic: Cyrillic ratio → `'ru'` / `'en'` / `None` |
| `_resolve_lang(chat_id, user_text)` | Priority chain: detected → TG lang → Russian |
| `_with_lang(chat_id, user_text)` | Single-turn LLM call: prepend security preamble + bot config + lang instruction into one string |
| `_with_lang_voice(chat_id, stt_text)` | Same as `_with_lang` + hint for low-confidence words `[?word]` |
| `_build_system_message(chat_id, user_text)` | Multi-turn: returns `role:system` content — security preamble + bot config + tiered memory note + lang instruction |
| `_user_turn_content(chat_id, user_text)` | Multi-turn: returns current user turn content — RAG context + user text (no preamble) |

### Text utilities

| Function | Purpose |
|---|---|
| `_escape_tts(text)` | Strip emoji + Markdown before Piper TTS |
| `_escape_md(text)` | Escape `*_`[`` for Telegram Markdown v1 |
| `_truncate(text, limit=3800)` | Truncate to Telegram message limit |
| `_safe_edit(chat_id, msg_id, text, ...)` | Edit message, ignore "not modified" errors |
| `_run_subprocess(cmd, timeout, env)` | Run command, return `(rc, output)` |

### LLM integration

| Function | Purpose |
|---|---|
| `_get_active_model()` | Read active model name from `active_model.txt` |
| `_clean_taris_output(text)` | Strip log lines, printf wrappers, timestamps |
| `_ask_taris(prompt, timeout)` | Call `taris agent -m "..."`, return clean text |

### Keyboards / UI

| Function | Purpose |
|---|---|
| `_menu_keyboard(chat_id)` | Main menu — filtered by role |
| `_back_keyboard()` | Single `🔙 Menu` button |
| `_voice_back_keyboard(chat_id)` | Back + optional 🔊/🔇 audio toggle |
| `_confirm_keyboard(cmd_hash)` | ✅ Run / ❌ Cancel for system commands |
| `_send_menu(chat_id, greeting)` | Reset mode and send the main menu |

---

## bot_users.py — Data Layer

Pure functions — no Telegram API calls. Imports: `bot_config` only.

### Registration

| Function | Purpose |
|---|---|
| `_load_registrations()` | Load `registrations.json` |
| `_save_registrations(regs)` | Persist registrations |
| `_find_registration(chat_id)` | Return reg dict or `None` |
| `_upsert_registration(chat_id, username, name, status)` | Create or update registration |
| `_set_reg_status(chat_id, status)` | Set `pending` / `approved` / `blocked` |
| `_get_pending_registrations()` | Return list of pending regs |
| `_is_blocked_reg(chat_id)` | True if blocked |
| `_is_pending_reg(chat_id)` | True if pending |

### Notes file I/O

| Function | Purpose |
|---|---|
| `_slug(title)` | `"My Title"` → `"my_title"` (safe filename) |
| `_notes_user_dir(chat_id)` | `~/.taris/notes/<chat_id>/` — created if missing |
| `_list_notes_for(chat_id)` | `[{slug, title, mtime}]` sorted newest-first |
| `_load_note_text(chat_id, slug)` | Return note content or `None` |
| `_save_note_file(chat_id, slug, content)` | Write note `.md` file |
| `_delete_note_file(chat_id, slug)` | Delete note, return `True` if existed |

---

## bot_voice.py — Voice Pipeline

Imports: `bot_config` (incl. `TARIS_DIR`), `bot_state`, `bot_instance`, `bot_access`, `bot_users`.

### Orphaned TTS tracker

| Function | Purpose |
|---|---|
| `_save_pending_tts(chat_id, msg_id)` | Record "Generating audio…" msg for restart cleanup |
| `_clear_pending_tts(chat_id)` | Remove after msg is handled |
| `_cleanup_orphaned_tts()` | On startup: edit orphaned msgs left by previous restart |

### Vosk STT

| Function | Purpose |
|---|---|
| `_get_vosk_model()` | Lazy-load Vosk Russian model singleton |

### Piper TTS

| Function | Purpose |
|---|---|
| `_voice_lang(chat_id)` | Returns TTS/voice language: `STT_LANG` if configured, else falls back to Telegram UI language (`_lang(chat_id)`). Ensures TTS speaks the user's voice language, not their Telegram client locale |
| `_piper_model_path()` | Priority: tmpfs → low model → medium (default) |
| `_setup_tmpfs_model(enable)` | Copy / remove ONNX to/from `/dev/shm/piper/` |
| `_warm_piper_cache()` | Pre-run Piper with `"."` input to warm ONNX page cache |
| `_start_persistent_piper()` | Launch keepalive Piper subprocess (§5.3) |
| `_stop_persistent_piper()` | Terminate keepalive subprocess |
| `_tts_to_ogg(text)` | Piper → raw PCM → ffmpeg → OGG Opus bytes |

### Before STT

| Function | Purpose |
|---|---|
| `_vad_filter_pcm(raw_pcm, sample_rate)` | WebRTC VAD: strip non-speech frames; `speech_pad_ms=200` (v2026.4.19+) |
| `_stt_whisper(raw_pcm, sample_rate)` | whisper.cpp STT + hallucination guard (sparse-output check); returns transcript or `None` |
| `_stt_faster_whisper(raw_pcm, sample_rate)` | faster-whisper batch STT; `without_timestamps=True`, threads capped to `2×cpu_count−1`; lazy-loaded singleton keyed by `(model, device, compute_type)` (v2026.4.19+) |
| `_load_vosk_model_cached()` | Test helper: lazy Vosk model singleton (used by T11) |

### Session + pipeline

| Function | Purpose |
|---|---|
| `_start_voice_session(chat_id)` | Set mode `'voice'`, show instructions |
| `_handle_voice_message(chat_id, voice_obj)` | Full pipeline: OGG→PCM→[VAD]→[Whisper\|Vosk\|FasterWhisper]→[NoteCmd\|SystemChat\|LLM]→TTS→send; if `_user_mode=="system"` dispatches to `_handle_system_message()` so admin role guards apply in voice mode |
| `_handle_note_read_aloud(chat_id, slug)` | Load note, synthesise body via Piper TTS, send as voice message with title caption |

---

## bot_admin.py — Admin Panel

Imports: `bot_config`, `bot_state`, `bot_instance`, `bot_access`, `bot_users`, `bot_voice`.

### Admin keyboard / entry

| Function | Purpose |
|---|---|
| `_admin_keyboard(chat_id)` | Admin inline keyboard (shows pending-reg count); all labels localized via `_t(chat_id, ...)` (v2026.3.43) |
| `_handle_admin_menu(chat_id)` | Show admin panel |

### Guest-user management

| Function | Purpose |
|---|---|
| `_handle_admin_list_users(chat_id)` | List current dynamic guests |
| `_start_admin_add_user(chat_id)` | Prompt for user ID to add |
| `_finish_admin_add_user(admin_id, text)` | Validate + add to `_dynamic_users` |
| `_start_admin_remove_user(chat_id)` | Prompt for user ID to remove |
| `_finish_admin_remove_user(admin_id, text)` | Validate + remove from `_dynamic_users` |

### Registration approval

| Function | Purpose |
|---|---|
| `_handle_admin_pending_users(chat_id)` | Show pending regs with approve/block buttons |
| `_do_approve_registration(admin_id, target_id)` | Approve + notify user |
| `_do_block_registration(admin_id, target_id)` | Block + notify user |
| `_notify_admins_new_registration(chat_id, username, name)` | Alert all admins with inline approve/block |

### Voice-optimization menu

| Function | Purpose |
|---|---|
| `_handle_voice_opts_menu(chat_id)` | Show all 10 toggles with current state |
| `_handle_voice_opt_toggle(chat_id, key)` | Flip flag + save; side-effects: warm/persistent piper |

### Release notes

| Function | Purpose |
|---|---|
| `_load_release_notes()` | Load `release_notes.json` |
| `_format_release_entry(entry, header)` | Format one entry as Telegram Markdown |
| `_get_changelog_text(max_entries)` | Full or truncated changelog |
| `_notify_admins_new_version()` | Notify once per `BOT_VERSION` on startup |
| `_handle_admin_changelog(chat_id)` | Show full changelog in admin panel |

### LLM switcher

| Function | Purpose |
|---|---|
| `_set_active_model(model_name)` | Write chosen model to `active_model.txt` |
| `_get_taris_models()` | Read `model_list` from `config.json` |
| `_handle_admin_llm_menu(chat_id)` | LLM selection keyboard |
| `_handle_set_llm(chat_id, model_name)` | Apply selection + confirm |
| `_get_shared_openai_key()` | First OpenAI `api_key` in `config.json` |
| `_save_openai_apikey(api_key)` | Write key to all OpenAI entries + add catalog |
| `_handle_openai_llm_menu(chat_id)` | OpenAI ChatGPT model submenu |
| `_handle_llm_setkey_prompt(chat_id)` | Ask admin to paste API key |
| `_handle_save_llm_key(chat_id, raw_key)` | Validate `sk-…` + save |
| `_handle_admin_llm_fallback_menu(chat_id)` | Show fallback toggle menu; displays ON/OFF state + URL/model |
| `_handle_admin_llm_fallback_toggle(chat_id)` | Write/remove `LLM_FALLBACK_FLAG_FILE`; confirm new state |

---

## bot_handlers.py — User Handlers

Imports: `bot_config`, `bot_state`, `bot_instance`, `bot_access`, `bot_users`.

### Notes UI

| Function | Purpose |
|---|---|
| `_notes_menu_keyboard(chat_id)` | Notes submenu: Create / List / Back |
| `_notes_list_keyboard(chat_id, notes)` | Per-note open/edit/delete buttons |
| `_handle_notes_menu(chat_id)` | Show notes submenu |
| `_handle_note_list(chat_id)` | List all notes |
| `_start_note_create(chat_id)` | Begin creation — prompt for title |
| `_handle_note_open(chat_id, slug)` | Show note read view (Markdown rendered) |
| `_handle_note_raw(chat_id, slug)` | Show note body as raw plain text (no parse_mode) |
| `_start_note_edit(chat_id, slug)` | Begin edit — sends current body via ForceReply for in-place editing |
| `_handle_note_delete(chat_id, slug)` | Delete + confirm |

### Mail digest

| Function | Purpose |
|---|---|
| `_handle_digest(chat_id)` | Show last digest + offer refresh |
| `_refresh_digest(chat_id)` | Run `gmail_digest.py --stdout` in background |

### System chat

| Function | Purpose |
|---|---|
| `_EMOJI_RE` | Compiled regex matching all Unicode emoji and symbol code points |
| `_SYMBOL_CATEGORIES` | frozenset of Unicode categories stripped from LLM output before bash execution |
| `_strip_symbols(text)` | Remove emoji + symbol characters from a string |
| `_PROSE_REJECT` | Regex matching prose openers ("Sure, here is…") to skip non-command lines |
| `_extract_bash_cmd(raw)` | Extract the first valid bash command from LLM output; strips markdown, emoji, prose |
| `_handle_system_message(chat_id, user_text)` | NL → bash command via LLM → confirm gate |
| `_execute_pending_cmd(chat_id)` | Run confirmed bash command on Pi |

### Free chat

| Function | Purpose |
|---|---|
| `_handle_chat_message(chat_id, user_text)` | Forward to LLM via `ask_llm_with_history()` with `[role:system] + history + [user_turn]` structure; response sent with `parse_mode=None` |

### Screen DSL helpers (v2026.3.43)

| Function | Purpose |
|---|---|
| `_screen_ctx(chat_id)` | Build a `ScreenContext` dict with user role, lang, and bot state for DSL rendering |
| `_render(chat_id, path, variables)` | Load YAML screen at `path`, merge `variables` + `_screen_ctx()`, send via `render_telegram.render_screen()` |

---

## bot_calendar.py — Smart Calendar

Imports: `bot_config`, `bot_state`, `bot_instance`, `bot_access`. (`bot_voice` lazy-imported inside functions.)

### Storage helpers

| Function | Purpose |
|---|---|
| `_cal_user_file(chat_id)` | Path: `~/.taris/calendar/<chat_id>.json` |
| `_cal_load(chat_id)` | Load events list (returns `[]` on error) |
| `_cal_save(chat_id, events)` | Persist events list |
| `_cal_add_event(chat_id, title, dt, remind_before_min)` | Append new event, return dict |
| `_cal_delete_event(chat_id, ev_id)` | Remove event by id, return `True` if found |
| `_cal_mark_reminded(chat_id, ev_id)` | Set `reminded=True` |
| `_cal_find_by_text(chat_id, text)` | Find first event whose title appears in `text` |

### Keyboards

| Function | Purpose |
|---|---|
| `_calendar_keyboard(chat_id, events)` | Main calendar view: event buttons + ➕ Add + 💬 Console + 🔙 |
| `_cal_confirm_keyboard(chat_id)` | Single-event confirmation: ✅ Save / ❌ Cancel / ✏️ Edit fields / 🔊 TTS |
| `_cal_confirm_keyboard_multi(chat_id, idx, total)` | Multi-event confirmation: ✅ Save / ⏭ Skip / ✅✅ Save All / ❌ Cancel |
| `_cal_event_keyboard(chat_id, ev_id)` | Event detail: Edit / Reschedule / Reminder / TTS / Delete / Email / Back |

### Menu handlers

| Function | Purpose |
|---|---|
| `_handle_calendar_menu(chat_id)` | Show upcoming events + action buttons |
| `_handle_cal_event_detail(chat_id, ev_id)` | Show single event detail card |

### Add event flow

| Function | Purpose |
|---|---|
| `_start_cal_add(chat_id)` | Enter `calendar` mode, show prompt |
| `_finish_cal_add(chat_id, text)` | LLM → extract `{"events":[...]}` → single or multi confirm |
| `_show_cal_confirm(chat_id)` | Show confirmation card for single pending event |
| `_show_cal_confirm_multi(chat_id)` | Show "N of M" confirmation for multi-event batch |
| `_cal_do_confirm_save(chat_id)` | Save single confirmed event → schedule reminder |
| `_cal_multi_save_one(chat_id)` | Save current batch event, advance to next |
| `_cal_multi_skip(chat_id)` | Skip current batch event, advance to next |
| `_cal_multi_save_all(chat_id)` | Save all remaining batch events at once |

### Edit flow

| Function | Purpose |
|---|---|
| `_cal_prompt_edit_field(chat_id, field, ev_id)` | Prompt for new value of `title` / `dt` / `remind` |
| `_cal_handle_edit_input(chat_id, text, field)` | Process input, re-parse via LLM if `dt`, update state |

### Delete flow (with confirmation)

| Function | Purpose |
|---|---|
| `_handle_cal_delete_request(chat_id, ev_id)` | Show event card + ✅ Confirm / ❌ Cancel |
| `_handle_cal_delete_confirmed(chat_id, ev_id)` | Actually delete + cancel timer |
| `_handle_cal_cancel_event(chat_id, ev_id)` | Alias for `_handle_cal_delete_request` (backward compat) |

### NL query

| Function | Purpose |
|---|---|
| `_handle_calendar_query(chat_id, text)` | LLM → extract date range → filter events → display |

### Calendar console

| Function | Purpose |
|---|---|
| `_start_cal_console(chat_id)` | Enter `cal_console` mode, show usage hint |
| `_handle_cal_console(chat_id, text)` | LLM intent → add / query / delete / edit |

### TTS

| Function | Purpose |
|---|---|
| `_cal_tts_text(title, dt_iso, lang)` | Build TTS string for event |
| `_handle_cal_event_tts(chat_id, ev_id)` | Synthesise and send voice note for saved event |
| `_handle_cal_confirm_tts(chat_id)` | TTS for pending (not yet saved) event |

### Reminders & startup

| Function | Purpose |
|---|---|
| `_send_reminder(chat_id, ev_id, title, dt_iso)` | Fire timer: send text + optional TTS |
| `_schedule_reminder(chat_id, ev)` | Schedule `threading.Timer` for event reminder |
| `_cal_reschedule_all()` | On startup: reload all JSON + reschedule pending timers |
| `_cal_morning_briefing_loop()` | Daemon thread: daily 08:00 briefing to all users |

### `_user_mode` values

| Value | Set by | Cleared by |
|---|---|---|
| `"calendar"` | `_start_cal_add()` | `_finish_cal_add()` |
| `"cal_console"` | `_start_cal_console()` | `_handle_cal_console()` |
| `"cal_edit_title"` | `_cal_prompt_edit_field("title")` | `_cal_handle_edit_input()` |
| `"cal_edit_dt"` | `_cal_prompt_edit_field("dt")` | `_cal_handle_edit_input()` |
| `"cal_edit_remind"` | `_cal_prompt_edit_field("remind")` | `_cal_handle_edit_input()` |

---

## bot_error_protocol.py — Error Protocol

Imports: `bot_config`, `bot_state`, `bot_instance`, `bot_access`. (`bot_mail_creds`, `bot_email` lazy-imported inside `_errp_send_email()`.)

### Helpers

| Function | Purpose |
|---|---|
| `_safe_dirname(name)` | Strip unsafe chars → `SAFE_NAME_RE`, clamp to 60 chars |
| `_errp_keyboard(chat_id)` | InlineKeyboard: ✅ Send / ❌ Cancel |
| `_summary_text(state)` | One-line count: "2 text, 1 voice, 3 photo" |

### Start / collect / send flow

| Function | Purpose |
|---|---|
| `_start_error_protocol(chat_id)` | Enter `errp_name` mode, prompt for error name |
| `_finish_errp_name(chat_id, text)` | Create timestamped dir `YYYYMMDD-HHMMSS_safename`, enter `errp_collect` mode |
| `_errp_collect_text(chat_id, text)` | Save text to `text_NN.txt`, show summary |
| `_errp_collect_voice(chat_id, voice_obj)` | Download OGG via bot API, save as `voice_NN.ogg` |
| `_errp_collect_photo(chat_id, photo_list)` | Download largest resolution, save as `photo_NN.ext` |
| `_errp_send(chat_id)` | Write `manifest.json`, confirm save, spawn email thread |
| `_errp_cancel(chat_id)` | Pop state, exit mode (saved files remain on disk) |

### Email

| Function | Purpose |
|---|---|
| `_errp_send_email(chat_id, state)` | Background thread: MIMEMultipart with all attachments via SMTP SSL; on failure notify user data is saved locally |

### `_user_mode` values

| Value | Set by | Cleared by |
|---|---|---|
| `"errp_name"` | `_start_error_protocol()` | `_finish_errp_name()` |
| `"errp_collect"` | `_finish_errp_name()` | `_errp_send()` / `_errp_cancel()` |

### Directory structure

```
~/.taris/error_protocols/
  └── 20260312-143022_crash_report/
        ├── manifest.json
        ├── text_01.txt
        ├── text_02.txt
        ├── voice_01.ogg
        ├── photo_01.jpg
        └── photo_02.jpg
```

---

## bot_security.py — Prompt Injection Defense

Imports: `bot_config` only.

| Symbol / Function | Purpose |
|---|---|
| `SECURITY_PREAMBLE` | Multi-line LLM policy string prepended to every free-chat and voice LLM call |
| `_wrap_user_input(text)` | L2 delimiter: wraps user text as `[USER]\n{text}\n[/USER]` to prevent instruction injection |
| `_check_injection(text)` | L1 pattern scan (~25 regexes); returns `(blocked: bool, reason: str)` — never calls LLM if `True` |

**Three-layer defense:**
1. **L1 — `_check_injection()`** — scans for instruction-override, persona-hijack, credential-extraction, shell-injection, and jailbreak patterns
2. **L2 — `_wrap_user_input()`** — user text delimited so LLM cannot confuse it with system instructions
3. **L3 — `SECURITY_PREAMBLE`** — model instructed not to reveal secrets, not to generate shell commands, not to obey role-override requests

---

## bot_llm.py — Pluggable LLM Backend

Imports: `bot_config` only. Shared by Telegram and Web channels.

**Provider selection:** `LLM_PROVIDER` env-var in `bot.env` selects the active provider at startup.

| Function | Purpose |
|---|---|
| `get_active_model() -> str` | Read active model name from `active_model.txt`; strips `provider/` prefix (e.g. `openai/gpt-4o-mini` → `gpt-4o-mini`) to prevent HTTP 400 |
| `set_active_model(name)` | Write model name to `active_model.txt` |
| `list_models() -> list[dict]` | Read `model_list` from `config.json` |
| `get_per_func_provider(use_case) -> str` | Return admin-set provider override for use_case (`"chat"`, `"voice"`, `"system"`, `"calendar"`), or `""` to use `LLM_PROVIDER` |
| `set_per_func_provider(use_case, provider)` | Write per-function override to `llm_per_func.json`; `""` clears override |
| `_clean_output(raw) -> str` | Strip log lines, printf wrappers, ANSI from CLI output |
| `_http_post_json(url, payload, timeout)` | Shared HTTP helper for REST-based providers; retries on HTTP 429; logs model name on 4xx errors (v2026.4.22+) |
| `_ask_taris(prompt, timeout)` | OpenRouter via `taris agent` CLI subprocess (default; `LLM_PROVIDER=taris`) |
| `_ask_openai(prompt, timeout)` | OpenAI / OpenAI-compatible REST API (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`) |
| `_ask_yandexgpt(prompt, timeout)` | YandexGPT REST API (`YANDEXGPT_API_KEY`, `YANDEXGPT_FOLDER_ID`, `YANDEXGPT_MODEL_URI`) |
| `_ask_gemini(prompt, timeout)` | Google Gemini REST API (`GEMINI_API_KEY`, `GEMINI_MODEL`) |
| `_ask_anthropic(prompt, timeout)` | Anthropic Claude REST API (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`) |
| `_ask_local(prompt, timeout)` | Local llama.cpp HTTP server (`LLAMA_CPP_URL` default `http://127.0.0.1:8081`) |
| `_ask_ollama(prompt, timeout)` | Ollama single-turn HTTP POST to `/api/generate` (`OLLAMA_URL`, `OLLAMA_MODEL`) |
| `_DISPATCH` | `dict` mapping `LLM_PROVIDER` values → provider functions |
| `ask_llm(prompt, timeout=60) -> str` | Single-turn entry point: routes via `_DISPATCH`; if primary fails and `LLM_LOCAL_FALLBACK=true`, retries via `_ask_local()` with `⚠️ [local fallback]` prefix |
| `ask_llm_with_history(messages, timeout, use_case) -> str` | Multi-turn entry point: checks `get_per_func_provider(use_case)` first, then `LLM_PROVIDER`; sends native multi-turn to openai/anthropic/ollama/yandexgpt/gemini/local; voice calls must pass `use_case="voice"` (v2026.4.23+) |
| `_format_history_as_text(messages) -> str` | Fallback: collapses messages into plain text for providers without native multi-turn support |

---

## bot_auth.py — Web UI Authentication

Imports: `bot_config` (incl. `TARIS_DIR`). Used by Web UI channel exclusively.

### Account management

| Function | Purpose |
|---|---|
| `find_account_by_username(username)` | Return account dict or `None` |
| `find_account_by_id(user_id)` | Return account dict by UUID or `None` |
| `find_account_by_chat_id(chat_id)` | Return account linked to Telegram chat ID or `None` |
| `create_account(username, password, display_name, role, chat_id)` | Create user account with bcrypt hash, return account dict |
| `verify_password(account, password)` | Check password against stored bcrypt hash |
| `update_account(user_id, **fields)` | Update any account field(s) by UUID; return `True` if found |
| `list_accounts()` | Return all accounts (without password hashes) |
| `change_password(user_id, new_password)` | Re-hash and save new password; return `True` if found |
| `ensure_admin_account()` | Create default admin account if `accounts.json` is empty |

### JWT tokens

| Function | Purpose |
|---|---|
| `_get_jwt_secret()` | Read `JWT_SECRET` from env / `bot.env` |
| `create_token(user_id, username, role)` | Sign HS256 JWT with 7-day expiry |
| `verify_token(token)` | Decode and validate JWT; return payload dict or `None` |

Storage: `~/.taris/accounts.json`

---

## bot_ui.py — Screen DSL Dataclasses

Imports: none (pure dataclasses). Used by `bot_actions.py`, `render_telegram.py`, and `bot_web.py`.

### Dataclasses

| Class | Purpose |
|---|---|
| `UserContext` | Caller identity: `chat_id`, `lang`, `is_admin`, `username` |
| `Screen` | Top-level container: `title`, `body`, `widgets`, `parse_mode` |
| `Button` | Single action: `label`, `action` (callback key), `url` |
| `ButtonRow` | Horizontal group of `Button`s |
| `Card` | Info card: `title`, `subtitle`, `body` |
| `TextInput` | Text prompt widget: `label`, `name` (field name) |
| `Toggle` | Boolean toggle: `label`, `key`, `value` |
| `AudioPlayer` | Playback: `url` or `ogg_bytes`, `caption` |
| `MarkdownBlock` | Pre-formatted Markdown content: `text` |
| `Spinner` | Loading indicator: `label` |
| `Confirm` | Yes/No gate: `message`, `confirm_action`, `cancel_action` |
| `Redirect` | Immediately redirect to another action: `action` |

### Factory helpers

| Function | Purpose |
|---|---|
| `back_button(label, target)` | Return `ButtonRow` with a single back/menu button |
| `confirm_buttons(action_yes, action_no, label_yes, label_no)` | Return `ButtonRow` with ✅/❌ buttons |

---

## bot_actions.py — Shared Action Handlers

Imports: `bot_config`, `bot_state`, `bot_users`, `bot_ui`. Returns `Screen` objects — never calls Telegram API directly.

| Function | Returns | Purpose |
|---|---|---|
| `action_menu(user: UserContext)` | `Screen` | Main menu with role-filtered buttons |
| `action_note_list(user: UserContext)` | `Screen` | Notes list with per-note open/edit/delete buttons |
| `action_note_view(user: UserContext, slug: str)` | `Screen` | Note detail: title, body, action buttons |

---

## render_telegram.py — Telegram Screen Renderer

Imports: `bot_config`, `bot_instance`, `bot_ui`.

| Function | Purpose |
|---|---|
| `_make_button(btn: Button)` | Convert `Button` → `InlineKeyboardButton` |
| `render_screen(screen, chat_id, bot, msg_id=None)` | Render `Screen` to Telegram: `send_message` or `edit_message_text` with `InlineKeyboardMarkup` |
| `_escape_md(text)` | Escape `*_\`` for Telegram Markdown v1 |

**Widget → Telegram mapping:**

| Widget type | Telegram output |
|---|---|
| `Card` | Formatted text block in message body |
| `Button` / `ButtonRow` | `InlineKeyboardButton` rows |
| `Toggle` | `InlineKeyboardButton` with ✅/⬜ prefix |
| `TextInput` | `bot.send_message(reply_markup=ForceReply())` |
| `AudioPlayer` | `bot.send_voice(ogg_bytes)` |
| `Spinner` | `bot.send_message("⏳ …")` — edited on completion |
| `Confirm` | Two-button keyboard ✅/❌ |
| `Redirect` | Immediately calls the target action handler |

---

## screen_loader.py — Declarative Screen DSL Loader

Imports: `bot_ui` (all 11 dataclasses). Optional: `yaml` (pyyaml), `jsonschema`.

Loads YAML/JSON screen definitions from `src/screens/` and returns `Screen` objects identical to those built programmatically in `bot_actions.py`. Both Telegram and Web renderers work unchanged.

### Feature flags

| Flag | Effect when absent |
|---|---|
| `_HAS_YAML` | Only `.json` files can be loaded (`.yaml` raises warning) |
| `_HAS_JSONSCHEMA` | Schema validation silently skipped |

### Globals

| Symbol | Purpose |
|---|---|
| `_screen_cache` | `dict[str, dict]` — parsed file cache (cleared by `reload_screens()`) |
| `_SCHEMA` | Lazy-loaded JSON Schema object (from `screen.schema.json`) |
| `_VAR_RE` | `re.compile(r"\{(\w+)\}")` — variable substitution pattern |
| `_WIDGET_BUILDERS` | `dict[str, Callable]` — type name → builder function registry |

### Public API

| Function | Purpose |
|---|---|
| `load_screen(path, user, variables, t_func)` | Main entry point: load YAML/JSON → resolve i18n + variables + visibility → return `Screen` |
| `load_all_screens(directory)` | Pre-load all files in a directory → `dict[str, dict]` (raw parsed data) |
| `reload_screens()` | Clear `_screen_cache` — call for hot-reload without restart |

### Internal helpers

| Function | Purpose |
|---|---|
| `_get_schema()` | Lazy-load `screen.schema.json` from `../screens/` relative to module |
| `_validate_screen(data, path)` | Validate parsed dict against JSON Schema; `log.warning()` on error, never crashes |
| `_load_file(path)` | Read + parse YAML/JSON + cache + validate; returns raw dict |
| `_resolve_text(widget, key, t_func, lang, variables)` | Resolve `title_key` / `label_key` / `text_key` → literal text via i18n + variable substitution |
| `_resolve_action(action, variables)` | Substitute `{var}` in callback action strings |
| `_is_visible(widget, user, variables)` | Check `visible_roles` and `visible_if` conditions |
| `_substitute(text, variables)` | Replace `{var_name}` patterns with values from `variables` dict |
| `_register(type_name)` | Decorator: register a builder function in `_WIDGET_BUILDERS` |

### Widget builders (registered via `@_register`)

| Builder | Widget type | Returns |
|---|---|---|
| `_build_button(w, ...)` | `button` | `Button` |
| `_build_button_row(w, ...)` | `button_row` | `ButtonRow` |
| `_build_card(w, ...)` | `card` | `Card` |
| `_build_text_input(w, ...)` | `text_input` | `TextInput` |
| `_build_toggle(w, ...)` | `toggle` | `Toggle` |
| `_build_audio_player(w, ...)` | `audio_player` | `AudioPlayer` |
| `_build_markdown(w, ...)` | `markdown` | `MarkdownBlock` |
| `_build_spinner(w, ...)` | `spinner` | `Spinner` |
| `_build_confirm(w, ...)` | `confirm` | `Confirm` |
| `_build_redirect(w, ...)` | `redirect` | `Redirect` |

### Screen files (`src/screens/`)

| File | Screen | Key variables |
|---|---|---|
| `main_menu.yaml` | Main user menu | — |
| `admin_menu.yaml` | Admin panel menu | `{pending_badge}` |
| `help.yaml` | Role-filtered help text | — |
| `notes_menu.yaml` | Notes submenu | — |
| `note_view.yaml` | Single note detail | `{slug}`, `{note_title}`, `{note_content}` |
| `note_raw.yaml` | Raw text view | `{slug}`, `{note_title}`, `{note_content}` |
| `note_edit.yaml` | Note edit options | `{slug}`, `{note_title}` |
| `profile.yaml` | User profile card | `{user_name}`, `{role}`, `{chat_id}`, etc. |
| `profile_lang.yaml` | Language selection | — |
| `profile_my_data.yaml` | Stored data summary | `{notes_count}`, `{calendar_count}`, etc. |

---

## bot_email.py — Send-as-Email via SMTP

Imports: `bot_config`, `bot_state`, `bot_instance`. (`bot_mail_creds` lazy-imported inside `_send_in_thread()`.)

| Function | Purpose |
|---|---|
| `_target_file(chat_id)` | Path: `.taris/mail_creds/<chat_id>_target.txt` |
| `_get_target_email(chat_id)` | Read stored send-to address or `None` |
| `_set_target_email(chat_id, addr)` | Persist send-to address |
| `_mask_addr(addr)` | Mask email for display: `us**@domain.tld` |
| `_smtp_host_port(imap_host)` | Infer SMTP host/port from IMAP host (e.g. `imap.gmail.com` → `smtp.gmail.com:465`) |
| `_do_smtp_send(creds, to, subject, body)` | SMTP SSL auth + send `MIMEText` email |
| `_send_in_thread(chat_id, msg_id, subject, body)` | Background thread: load creds → `_do_smtp_send()` → notify user |
| `_edit_or_send(chat_id, msg_id, text, reply_markup)` | Edit existing msg or send new (handles missing `msg_id`) |
| `handle_send_email(chat_id, subject, body)` | Entry point: check target → confirm → launch thread |
| `handle_email_change_target(chat_id)` | Prompt for new send-to address (enters `email_target` mode) |
| `finish_email_set_target(chat_id, text)` | Validate email address + save |

---

## bot_mail_creds.py — Per-User Mail Digest

Imports: `bot_config`, `bot_state`, `bot_instance`, `bot_access`. (`bot_email` lazy-imported for send-email flow.)

### Storage helpers

| Function | Purpose |
|---|---|
| `_creds_dir()` | `~/.taris/mail_creds/` — created if missing |
| `_creds_file(chat_id)` | `…/mail_creds/<chat_id>.json` |
| `_last_digest_file(chat_id)` | `…/mail_creds/<chat_id>_last_digest.txt` |
| `_load_creds(chat_id)` | Return credentials dict or `None` |
| `_save_creds(chat_id, data)` | Persist credentials (chmod 600) |
| `_delete_creds(chat_id)` | Remove credentials file |
| `_mail_has_creds(chat_id)` | True if credentials exist |

### IMAP fetch + digest

| Function | Purpose |
|---|---|
| `_decode_header_str(s)` | Decode RFC 2047 encoded email header |
| `_get_text_body(msg)` | Extract plain-text body from `email.message.Message` |
| `_fetch_folder(imap, folder)` | Fetch messages from one IMAP folder (last 24 h, max 50) |
| `_build_digest_prompt(inbox, spam)` | Assemble LLM prompt from inbox + spam message list |
| `_fetch_and_summarize(chat_id)` | Full pipeline: IMAP connect → fetch → LLM summarise → cache |
| `_run_refresh_thread(chat_id, msg_id)` | Background thread: `_fetch_and_summarize()` → edit spinner message |

### Keyboards

| Function | Purpose |
|---|---|
| `_mail_main_keyboard(chat_id)` | Main mail view: Refresh / Settings / Email / Back |
| `_mail_nocreds_keyboard(chat_id)` | No-creds state: Set up mail / Back |
| `_mail_consent_keyboard(chat_id)` | GDPR consent gate: Agree / Back |
| `_mail_provider_keyboard(chat_id)` | Provider choice: Gmail / Yandex / Mail.ru / Custom |
| `_mail_settings_keyboard(chat_id)` | Settings: Delete creds / Change target / Back |

### Entry point handlers

| Function | Purpose |
|---|---|
| `handle_digest_auth(chat_id)` | Show last digest or consent gate if no creds |
| `handle_digest_refresh(chat_id)` | Send "refreshing…" spinner + launch `_run_refresh_thread()` |
| `handle_mail_consent(chat_id)` | Show GDPR consent text + agree/back keyboard |
| `handle_mail_consent_agree(chat_id)` | Show provider selection keyboard |
| `handle_mail_provider(chat_id, provider_key)` | Store provider choice, prompt for email address |
| `finish_mail_setup(chat_id, text)` | Multi-step wizard: email → password → test IMAP → save |
| `_do_test_and_save(chat_id, state, msg_id)` | Validate IMAP connection + save creds on success |
| `handle_mail_settings(chat_id)` | Show settings keyboard (creds present) |
| `handle_mail_del_creds(chat_id)` | Delete stored credentials + confirm |
| `_mask_email(addr)` | Mask email for display |

---

## bot_web.py — FastAPI Web Application

Imports: all `bot_*` modules. Entry point for web channel. ~2000 lines, 41 routes.
**Service:** `taris-web.service` · **Port:** HTTPS 8080 · **Auth:** JWT cookie `taris_token`

### Route inventory

| Method | Path | Description |
|---|---|---|
| `GET` | `/login` | Login form |
| `POST` | `/login` | Verify credentials, set JWT `taris_token` cookie |
| `GET` | `/register` | Registration form (optional `link_code` for Telegram-linked setup) |
| `POST` | `/register` | Create account; if `link_code` provided → role inherited, status=active |
| `GET` | `/logout` | Clear JWT cookie |
| `GET` | `/settings` | User settings: language, change password |
| `POST` | `/settings/language` | Save language preference |
| `POST` | `/settings/password` | Change password (current + new) |
| `GET` | `/` | Dashboard |
| `GET` | `/chat` | Chat page |
| `POST` | `/chat/send` | Send to LLM, return HTMX chat bubble partial |
| `DELETE` | `/chat/clear` | Clear chat history |
| `GET` | `/notes` | Notes list |
| `GET` | `/notes/list` | HTMX partial: notes list |
| `POST` | `/notes/create` | Create note (title + body) |
| `GET` | `/notes/{slug}` | View note |
| `POST` | `/notes/{slug}/save` | Save note edits |
| `DELETE` | `/notes/{slug}` | Delete note |
| `GET` | `/calendar` | Calendar view |
| `POST` | `/calendar/add` | Add event via NL text |
| `POST` | `/calendar/{ev_id}/delete` | Delete event |
| `POST` | `/calendar/parse-text` | Parse NL → event fields (HTMX preview) |
| `POST` | `/calendar/console` | Calendar console NL command |
| `GET` | `/mail` | Mail digest page |
| `POST` | `/mail/settings` | Save IMAP credentials |
| `POST` | `/mail/settings/delete` | Delete IMAP credentials |
| `POST` | `/mail/refresh` | Trigger IMAP fetch + LLM summarise |
| `GET` | `/mail/oauth/google/start` | Begin Gmail OAuth2 flow |
| `GET` | `/mail/oauth/google/callback` | Gmail OAuth2 callback |
| `GET` | `/voice` | Voice recording page |
| `GET` | `/voice/last-transcript` | Return last STT transcript (polling) |
| `POST` | `/voice/tts` | Text → TTS → return OGG audio |
| `POST` | `/voice/transcribe` | Upload OGG → Vosk STT → return transcript |
| `POST` | `/voice/chat` | Full voice pipeline: OGG → STT → LLM → TTS (returns text + audio) |
| `POST` | `/voice/chat_text` | Text → LLM → optional TTS (web text chat with voice reply) |
| `GET` | `/admin` | Admin dashboard |
| `POST` | `/admin/llm/{model_name}` | Switch active LLM model |
| `POST` | `/admin/voice-opt/{key}` | Toggle voice optimisation flag |
| `DELETE` | `/admin/user/{user_id}` | Delete web user account |
| `POST` | `/admin/user/{user_id}/approve` | Approve pending web user |
| `POST` | `/admin/user/{user_id}/block` | Block web user |
| `GET` | `/screen/{screen_id}` | Dynamic Screen DSL renderer — serve YAML screen by ID (v2026.3.43) |
| `POST` | `/mcp/search` | MCP-compatible RAG search; Bearer-token auth; returns RRF-ranked chunks (v2026.4.1) |

---

## telegram_menu_bot.py — Entry Point

Registers handlers and starts polling. All logic is imported from the modules above.

| Handler | Telegram trigger | Purpose |
|---|---|---|
| `cmd_start(message)` | `/start` | Welcome or registration flow |
| `cmd_menu(message)` | `/menu` | Show main menu |
| `cmd_status(message)` | `/status` | Show bot/service status |
| `callback_handler(call)` | Any inline button | Dispatcher for all `data=` keys |
| `text_handler(message)` | Any text message | Route by `_user_mode` |
| `voice_handler(message)` | Any voice note | Call `_handle_voice_message` |
| `photo_handler(message)` | Any photo | Route to error protocol collection |
| `main()` | `__main__` | Startup side-effects + `bot.infinity_polling()` |

---

## Callback Data Key Reference

All `data=` keys handled in `callback_handler()`:

| Key / Prefix | Handler called |
|---|---|
| `menu` | `_send_menu` |
| `digest` | `_handle_digest` |
| `digest_refresh` | `_refresh_digest` |
| `mode_chat` | set `_user_mode='chat'` |
| `mode_system` | set `_user_mode='system'` |
| `voice_session` | `_start_voice_session` |
| `voice_audio_toggle` | toggle `_user_audio[cid]` |
| `help` | send `help_text` / `help_text_admin` / `help_text_guest` |
| `profile` | `_handle_profile` |
| `web_link` | `generate_web_link_code` — send Telegram↔Web link code to user |
| `admin_menu` | `_handle_admin_menu` |
| `admin_add_user` | `_start_admin_add_user` |
| `admin_list_users` | `_handle_admin_list_users` |
| `admin_remove_user` | `_start_admin_remove_user` |
| `admin_pending_users` | `_handle_admin_pending_users` |
| `reg_approve:<id>` | `_do_approve_registration` |
| `reg_block:<id>` | `_do_block_registration` |
| `admin_llm_menu` | `_handle_admin_llm_menu` |
| `llm_select:<model>` | `_handle_set_llm` |
| `openai_llm_menu` | `_handle_openai_llm_menu` |
| `llm_setkey_openai` | `_handle_llm_setkey_prompt` |
| `admin_llm_fallback_menu` | `_handle_admin_llm_fallback_menu` |
| `admin_llm_fallback_toggle` | `_handle_admin_llm_fallback_toggle` |
| `admin_security_policy` | `_handle_admin_security_policy` in `bot_admin.py` |
| `admin_syschat_block_add` | `_handle_admin_syschat_block_add_prompt` in `bot_admin.py` |
| `admin_syschat_block_rm:<idx>` | `_handle_admin_syschat_block_remove` in `bot_admin.py` |
| `voice_opts_menu` | `_handle_voice_opts_menu` |
| `voice_opt_toggle:<key>` | `_handle_voice_opt_toggle` |
| `admin_changelog` | `_handle_admin_changelog` |
| `admin_rag_menu` | `_handle_admin_rag_menu` — RAG toggle + activity log (v2026.3.43) |
| `admin_rag_toggle` | `_handle_admin_rag_toggle` — flip `RAG_FLAG_FILE` presence (v2026.3.43) |
| `admin_rag_log` | `_handle_admin_rag_log` — show last 20 RAG queries + chunks (v2026.3.43) |
| `admin_rag_settings` | `_handle_admin_rag_settings` — show RAG settings panel (top-k, chunk, timeout) (v2026.3.30+2) |
| `admin_rag_set_topk` | `_start_admin_rag_set("rag_top_k")` — prompt for new top-K value |
| `admin_rag_set_chunk` | `_start_admin_rag_set("rag_chunk_size")` — prompt for new chunk size |
| `admin_rag_set_timeout` | `_start_admin_rag_set("rag_timeout")` — prompt for new RAG timeout |
| `reload_screens` | `reload_screens()` in `screen_loader` — hot-reload YAML screen cache (v2026.3.43) |
| `menu_notes` | `_handle_notes_menu` |
| `note_create` | `_start_note_create` |
| `note_list` | `_handle_note_list` |
| `note_open:<slug>` | `_handle_note_open` |
| `note_raw:<slug>` | `_handle_note_raw` |
| `note_edit:<slug>` | `_start_note_edit` |
| `note_delete:<slug>` | `_handle_note_delete` |
| `note_tts:<slug>` | `_handle_note_read_aloud` |
| `note_append:<slug>` | Append text to existing note |
| `note_replace:<slug>` | Replace entire note content |
| `note_email:<slug>` | Email note to target address |
| `menu_calendar` | `_handle_calendar_menu` |
| `cal_add` | `_start_cal_add` |
| `cal_event:<id>` | `_handle_cal_event_detail` |
| `cal_del:<id>` | `_handle_cal_delete_request` (shows confirmation) |
| `cal_del_confirm:<id>` | `_handle_cal_delete_confirmed` (actual delete) |
| `cal_confirm_save` | `_cal_do_confirm_save` |
| `cal_multi_save_one` | `_cal_multi_save_one` |
| `cal_multi_skip` | `_cal_multi_skip` |
| `cal_multi_save_all` | `_cal_multi_save_all` |
| `cal_confirm_edit_title` | `_cal_prompt_edit_field("title")` |
| `cal_confirm_edit_dt` | `_cal_prompt_edit_field("dt")` |
| `cal_confirm_edit_remind` | `_cal_prompt_edit_field("remind")` |
| `cal_edit_title:<id>` | `_cal_prompt_edit_field("title", ev_id)` |
| `cal_edit_dt:<id>` | `_cal_prompt_edit_field("dt", ev_id)` |
| `cal_edit_remind:<id>` | `_cal_prompt_edit_field("remind", ev_id)` |
| `cal_tts:<id>` | `_handle_cal_event_tts` |
| `cal_confirm_tts` | `_handle_cal_confirm_tts` |
| `cal_console` | `_start_cal_console` |
| `cal_email:<id>` | `handle_send_email` (via `bot_email`) |
| `mail_consent` | `handle_digest_auth` — show GDPR consent gate |
| `mail_consent_agree` | Accept consent → show provider selection |
| `mail_provider:<name>` | Select IMAP provider (gmail / yandex / mailru / custom) |
| `mail_settings` | Show mail settings keyboard |
| `mail_del_creds` | Delete stored IMAP credentials |
| `email_change_target` | `handle_email_change_target` — prompt for new send-to address |
| `errp_start` | `_start_error_protocol` |
| `errp_send` | `_errp_send` |
| `errp_cancel` | `_errp_cancel` |
| `doc_detail:<id>` | `_handle_doc_detail` — document detail view: type, chunks, size, shared, created (v2026.3.30+2) |
| `doc_rename:<id>` | `_handle_doc_rename_prompt` — start rename flow (input mode `doc_rename`) |
| `doc_rename_confirm:<id>` | `_handle_doc_rename_confirm` — apply new name |
| `doc_share:<id>` | `_handle_doc_share_toggle` — flip `shared` flag |
| `doc_del:<id>` | `_handle_doc_delete_request` — show delete confirmation |
| `doc_del_confirm:<id>` | `_handle_doc_delete_confirm` — actual delete |
| `cancel` | clear pending cmd/note/mode |
| `run:<hash>` | `_execute_pending_cmd` |
| `admin_rag_stats` | `_handle_admin_rag_stats` — RAG monitoring dashboard: latency, query types, top queries *(v2026.3.32)* |
| `dev_menu` | `handle_dev_menu` — Developer Menu (developer role only) *(v2026.3.32)* |
| `dev_chat` | `handle_dev_chat` — enter dev chat mode *(v2026.3.32)* |
| `dev_restart` | `handle_dev_restart` — show restart confirmation *(v2026.3.32)* |
| `dev_restart_confirmed` | `handle_dev_restart_confirmed` — execute restart *(v2026.3.32)* |
| `dev_log` | `handle_dev_log` — last 30 log lines *(v2026.3.32)* |
| `dev_error` | `handle_dev_error` — last ERROR entry from journal *(v2026.3.32)* |
| `dev_files` | `handle_dev_files` — list `~/.taris/*.py` *(v2026.3.32)* |
| `dev_security_log` | `handle_dev_security_log` — last 20 `security_events` rows *(v2026.3.32)* |
| `profile_rag_settings` | `_handle_profile_rag_settings` — per-user RAG settings panel *(v2026.3.32)* |
| `profile_rag_topk_inc` | `_handle_profile_rag_adjust("rag_top_k", +1)` *(v2026.3.32)* |
| `profile_rag_topk_dec` | `_handle_profile_rag_adjust("rag_top_k", -1)` *(v2026.3.32)* |
| `profile_rag_chunk_inc` | `_handle_profile_rag_adjust("rag_chunk_size", +200)` *(v2026.3.32)* |
| `profile_rag_chunk_dec` | `_handle_profile_rag_adjust("rag_chunk_size", -200)` *(v2026.3.32)* |
| `profile_rag_reset` | `_handle_profile_rag_reset` — reset to system defaults *(v2026.3.32)* |
| `profile_toggle_memory` | `_handle_profile_toggle_memory` — per-user memory on/off *(v2026.3.32)* |



## Key Files on Pi (runtime)

| File | Purpose |
|---|---|
| `~/.taris/bot.env` | Secrets: `BOT_TOKEN`, `ALLOWED_USERS`, `ADMIN_USERS` |
| `~/.taris/accounts.json` | Web UI user accounts (username + bcrypt hash + role) |
| `~/.taris/voice_opts.json` | Persisted voice-opt flags |
| `~/.taris/pending_tts.json` | TTS orphan-cleanup tracker |
| `~/.taris/users.json` | Dynamically approved guest users |
| `~/.taris/registrations.json` | User registration records (pending/approved/blocked) |
| `~/.taris/active_model.txt` | Admin-selected LLM model name |
| `~/.taris/last_notified_version.txt` | Last `BOT_VERSION` admin was notified about |
| `~/.taris/notes/<chat_id>/<slug>.md` | Per-user note files |
| `~/.taris/calendar/<chat_id>.json` | Per-user calendar events |
| `~/.taris/mail_creds/<chat_id>.json` | Per-user IMAP credentials (chmod 600) |
| `~/.taris/mail_creds/<chat_id>_last_digest.txt` | Last digest cache |
| `~/.taris/mail_creds/<chat_id>_target.txt` | SMTP send-to address |
| `~/.taris/config.json` | taris LLM config (model_list, agents, active_model) |
| `~/.taris/error_protocols/` | Error protocol reports (YYYYMMDD-HHMMSS_name/) |
| `~/.taris/telegram_bot.log` | Bot log file |
