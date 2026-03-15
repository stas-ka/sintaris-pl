# Telegram Menu Bot — Code Map

**Architecture:** 20-module split — Telegram core (v2026.3.19) + shared LLM/auth + Web UI layer (v2026.3.28)  
**Entry point (Telegram):** `src/telegram_menu_bot.py` (~280 lines — handlers + `main()`)  
**Entry point (Web):** `src/bot_web.py` — FastAPI application, all HTTP routes  
**Version:** 2026.3.28

Use this map to locate any function by module. All `bot_*.py` files live in `src/`.

## Module Dependency Chain (no circular imports)

```
bot_config → bot_state → bot_instance → bot_security → bot_access → bot_users
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

| Module | Lines | Responsibility |
|---|---|---|
| `bot_config.py` | ~120 | Constants, env loading, logging setup — no deps |
| `bot_state.py` | ~115 | Mutable runtime dicts, voice_opts/dynamic_users I/O; web link codes |
| `bot_instance.py` | ~12 | `bot = TeleBot(...)` singleton |
| `bot_security.py` | ~200 | 3-layer prompt injection guard; `SECURITY_PREAMBLE`; `_wrap_user_input()` |
| `bot_access.py` | ~380 | Access control, i18n, keyboards, text utils, `_ask_picoclaw()` |
| `bot_users.py` | ~160 | Registration + notes file I/O (pure, no Telegram API) |
| `bot_voice.py` | ~280 | Full voice pipeline: STT/TTS/VAD + pending TTS tracker |
| `bot_calendar.py` | ~650 | Smart calendar: CRUD, NL parser, reminders, briefing, TTS, multi-event |
| `bot_mail_creds.py` | ~450 | Per-user IMAP creds, consent flow, digest fetch + LLM summarise |
| `bot_email.py` | ~250 | Send-as-email SMTP for notes, digest, calendar events |
| `bot_admin.py` | ~310 | Admin panel: guests, reg, voice opts, release notes, LLM |
| `bot_handlers.py` | ~160 | User handlers: chat, system, digest, notes, profile |
| `bot_error_protocol.py` | ~260 | Error protocol: collect text/voice/photo → save dir → email |
| `telegram_menu_bot.py` | ~280 | Entry point: handlers + `main()` |
| `bot_llm.py` | ~130 | Pluggable LLM backend — `picoclaw_cli` / `openai_direct`; shared by Telegram + Web |
| `bot_auth.py` | ~200 | JWT/bcrypt authentication, `accounts.json` — Web UI only |
| `bot_ui.py` | ~150 | Screen DSL dataclasses: `Screen`, `Button`, `Card`, `Toggle`, `Spinner`, etc. |
| `bot_actions.py` | ~300 | Action handlers returning `Screen` objects — shared logic layer |
| `render_telegram.py` | ~220 | Renders `Screen` → Telegram `send_message` / `InlineKeyboardMarkup` |
| `bot_web.py` | ~2000 | FastAPI app: all HTTP routes, Jinja2 templates, HTMX endpoints, HTTPS :8080 |

## bot_config.py — Constants & Configuration

No imports from other `bot_*` modules. Root of the dependency tree.

| Symbol / Function | Purpose |
|---|---|
| `BOT_VERSION` | `"YYYY.M.D"` — bump on every user-visible change |
| `BOT_TOKEN` | Telegram bot token from `bot.env` |
| `ALLOWED_USERS` | `set[int]` — full-access chat IDs |
| `ADMIN_USERS` | `set[int]` — admin chat IDs |
| `PICOCLAW_BIN` | `/usr/bin/picoclaw` |
| `PICOCLAW_CONFIG` | `~/.picoclaw/config.json` |
| `ACTIVE_MODEL_FILE` | `~/.picoclaw/active_model.txt` |
| `PIPER_BIN` | `/usr/local/bin/piper` |
| `PIPER_MODEL` | `~/.picoclaw/ru_RU-irina-medium.onnx` |
| `PIPER_MODEL_TMPFS` | `/dev/shm/piper/...` (RAM-disk copy) |
| `PIPER_MODEL_LOW` | `~/.picoclaw/ru_RU-irina-low.onnx` |
| `WHISPER_BIN` | `/usr/local/bin/whisper-cpp` |
| `WHISPER_MODEL` | `~/.picoclaw/ggml-base.bin` |
| `VOSK_MODEL_PATH` | `~/.picoclaw/vosk-model-small-ru/` |
| `NOTES_DIR` | `~/.picoclaw/notes/` |
| `_PENDING_TTS_FILE` | `~/.picoclaw/pending_tts.json` |
| `_VOICE_OPTS_DEFAULTS` | All 10 voice-opt flags (all `False`) |
| `_load_env_file(path)` | Parse `KEY=VALUE` file → `os.environ` |
| `log` | `logging.getLogger("pico-tgbot")` |

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

---

## bot_instance.py — Bot Singleton

Imports: `bot_config` only.

| Symbol | Purpose |
|---|---|
| `bot` | `telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")` — shared by all modules |

---

## bot_access.py — Core Utilities

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
| `_with_lang(chat_id, user_text)` | Prepend LLM language instruction |
| `_with_lang_voice(chat_id, stt_text)` | Same + hint for low-confidence words `[?word]` |

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
| `_clean_picoclaw_output(text)` | Strip log lines, printf wrappers, timestamps |
| `_ask_picoclaw(prompt, timeout)` | Call `picoclaw agent -m "..."`, return clean text |

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
| `_notes_user_dir(chat_id)` | `~/.picoclaw/notes/<chat_id>/` — created if missing |
| `_list_notes_for(chat_id)` | `[{slug, title, mtime}]` sorted newest-first |
| `_load_note_text(chat_id, slug)` | Return note content or `None` |
| `_save_note_file(chat_id, slug, content)` | Write note `.md` file |
| `_delete_note_file(chat_id, slug)` | Delete note, return `True` if existed |

---

## bot_voice.py — Voice Pipeline

Imports: `bot_config`, `bot_state`, `bot_instance`, `bot_access`, `bot_users`.

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
| `_piper_model_path()` | Priority: tmpfs → low model → medium (default) |
| `_setup_tmpfs_model(enable)` | Copy / remove ONNX to/from `/dev/shm/piper/` |
| `_warm_piper_cache()` | Pre-run Piper with `"."` input to warm ONNX page cache |
| `_start_persistent_piper()` | Launch keepalive Piper subprocess (§5.3) |
| `_stop_persistent_piper()` | Terminate keepalive subprocess |
| `_tts_to_ogg(text)` | Piper → raw PCM → ffmpeg → OGG Opus bytes |

### Before STT

| Function | Purpose |
|---|---|
| `_vad_filter_pcm(raw_pcm, sample_rate)` | WebRTC VAD: strip non-speech frames (§5.3) |
| `_stt_whisper(raw_pcm, sample_rate)` | whisper.cpp STT + hallucination guard (sparse-output check); returns transcript or `None` |
| `_load_vosk_model_cached()` | Test helper: lazy Vosk model singleton (used by T11) |

### Session + pipeline

| Function | Purpose |
|---|---|
| `_start_voice_session(chat_id)` | Set mode `'voice'`, show instructions |
| `_handle_voice_message(chat_id, voice_obj)` | Full pipeline: OGG→PCM→[VAD]→[Whisper\|Vosk]→[NoteCmd\|LLM]→TTS→send |
| `_handle_note_read_aloud(chat_id, slug)` | Load note, synthesise body via Piper TTS, send as voice message with title caption |

---

## bot_admin.py — Admin Panel

Imports: `bot_config`, `bot_state`, `bot_instance`, `bot_access`, `bot_users`, `bot_voice`.

### Admin keyboard / entry

| Function | Purpose |
|---|---|
| `_admin_keyboard()` | Admin inline keyboard (shows pending-reg count) |
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
| `_get_picoclaw_models()` | Read `model_list` from `config.json` |
| `_handle_admin_llm_menu(chat_id)` | LLM selection keyboard |
| `_handle_set_llm(chat_id, model_name)` | Apply selection + confirm |
| `_get_shared_openai_key()` | First OpenAI `api_key` in `config.json` |
| `_save_openai_apikey(api_key)` | Write key to all OpenAI entries + add catalog |
| `_handle_openai_llm_menu(chat_id)` | OpenAI ChatGPT model submenu |
| `_handle_llm_setkey_prompt(chat_id)` | Ask admin to paste API key |
| `_handle_save_llm_key(chat_id, raw_key)` | Validate `sk-…` + save |

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
| `_handle_chat_message(chat_id, user_text)` | Forward to picoclaw LLM, return reply |

---

## bot_calendar.py — Smart Calendar

Imports: `bot_config`, `bot_state`, `bot_instance`, `bot_access`. (`bot_voice` lazy-imported inside functions.)

### Storage helpers

| Function | Purpose |
|---|---|
| `_cal_user_file(chat_id)` | Path: `~/.picoclaw/calendar/<chat_id>.json` |
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
~/.picoclaw/error_protocols/
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

| Function | Purpose |
|---|---|
| `get_active_model() -> str` | Read active model name from `active_model.txt` |
| `set_active_model(name)` | Write model name to `active_model.txt` |
| `list_models() -> list[dict]` | Read `model_list` from `config.json` |
| `_clean_output(raw) -> str` | Strip log lines, printf wrappers, ANSI from CLI output |
| `ask_llm(prompt, timeout=60) -> str` | Call `picoclaw agent -m "..."`, return clean reply |

---

## bot_auth.py — Web UI Authentication

Imports: `bot_config` only. Used by Web UI channel exclusively.

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

Storage: `~/.picoclaw/accounts.json`

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

## bot_email.py — Send-as-Email via SMTP

Imports: `bot_config`, `bot_state`, `bot_instance`. (`bot_mail_creds` lazy-imported inside `_send_in_thread()`.)

| Function | Purpose |
|---|---|
| `_target_file(chat_id)` | Path: `.picoclaw/mail_creds/<chat_id>_target.txt` |
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
| `_creds_dir()` | `~/.picoclaw/mail_creds/` — created if missing |
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
**Service:** `picoclaw-web.service` · **Port:** HTTPS 8080 · **Auth:** JWT cookie `pico_token`

### Route inventory

| Method | Path | Description |
|---|---|---|
| `GET` | `/login` | Login form |
| `POST` | `/login` | Verify credentials, set JWT `pico_token` cookie |
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
| `voice_opts_menu` | `_handle_voice_opts_menu` |
| `voice_opt_toggle:<key>` | `_handle_voice_opt_toggle` |
| `admin_changelog` | `_handle_admin_changelog` |
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
| `cancel` | clear pending cmd/note/mode |
| `run:<hash>` | `_execute_pending_cmd` |

---

## Key Files on Pi (runtime)

| File | Purpose |
|---|---|
| `~/.picoclaw/bot.env` | Secrets: `BOT_TOKEN`, `ALLOWED_USERS`, `ADMIN_USERS` |
| `~/.picoclaw/accounts.json` | Web UI user accounts (username + bcrypt hash + role) |
| `~/.picoclaw/voice_opts.json` | Persisted voice-opt flags |
| `~/.picoclaw/pending_tts.json` | TTS orphan-cleanup tracker |
| `~/.picoclaw/users.json` | Dynamically approved guest users |
| `~/.picoclaw/registrations.json` | User registration records (pending/approved/blocked) |
| `~/.picoclaw/active_model.txt` | Admin-selected LLM model name |
| `~/.picoclaw/last_notified_version.txt` | Last `BOT_VERSION` admin was notified about |
| `~/.picoclaw/notes/<chat_id>/<slug>.md` | Per-user note files |
| `~/.picoclaw/calendar/<chat_id>.json` | Per-user calendar events |
| `~/.picoclaw/mail_creds/<chat_id>.json` | Per-user IMAP credentials (chmod 600) |
| `~/.picoclaw/mail_creds/<chat_id>_last_digest.txt` | Last digest cache |
| `~/.picoclaw/mail_creds/<chat_id>_target.txt` | SMTP send-to address |
| `~/.picoclaw/config.json` | picoclaw LLM config (model_list, agents, active_model) |
| `~/.picoclaw/error_protocols/` | Error protocol reports (YYYYMMDD-HHMMSS_name/) |
| `~/.picoclaw/telegram_bot.log` | Bot log file |
