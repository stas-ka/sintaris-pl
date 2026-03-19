# Picoclaw — Telegram Bot Architecture

**Version:** `2026.3.43`  
→ Architecture index: [architecture.md](../architecture.md)

---

## 3. Telegram Menu Bot

**Version:** `BOT_VERSION = "2026.3.43"` · **Entry point:** `telegram_menu_bot.py` · **Service:** `picoclaw-telegram.service`

The interactive Telegram bot is split into 14 Python modules. All logic is in `bot_*.py`; `telegram_menu_bot.py` only registers handlers and dispatches callbacks. Shared Screen DSL modules (`bot_ui.py`, `bot_actions.py`, `render_telegram.py`) are used by both this channel and the Web UI channel.

### 3.1 Module Structure

Module dependency chain (no circular imports):

```
bot_config → bot_state → bot_instance → bot_security → bot_access → bot_users
    → bot_voice → bot_calendar → bot_admin → bot_handlers
    → bot_mail_creds → bot_email → bot_error_protocol → telegram_menu_bot

bot_config → bot_llm          ← pluggable LLM backend (shared by Telegram + Web)
bot_config → bot_auth         ← JWT/bcrypt auth (used by Web UI only)
bot_ui     → bot_actions      ← Screen DSL action handlers (shared)
bot_actions ← render_telegram ← Telegram renderer (reads bot_actions output)
bot_actions ← bot_web         ← Web renderer (reads bot_actions output via Jinja2)
```

| Module | Responsibility |
|---|---|
| `bot_config.py` | Constants, env loading, logging — root of dependency tree |
| `bot_state.py` | Mutable runtime dicts, voice_opts I/O, dynamic_users I/O; `generate_web_link_code()` / `validate_web_link_code()` for Telegram↔Web account linking |
| `bot_instance.py` | `bot = TeleBot(...)` singleton |
| `bot_security.py` | 3-layer prompt injection guard; `SECURITY_PREAMBLE`; `_wrap_user_input()` |
| `bot_access.py` | Access control, i18n `_t()`, keyboards, text utils, `_ask_picoclaw()` |
| `bot_users.py` | Registration + notes file I/O (pure, no Telegram API calls) |
| `bot_voice.py` | Full voice pipeline: STT/TTS/VAD, multi-part "Read aloud", orphan cleanup |
| `bot_calendar.py` | Smart calendar: multi-event add, NL query, console, reminders, morning briefing, TTS |
| `bot_admin.py` | Admin panel: users, LLM switcher, voice opts, release notes |
| `bot_handlers.py` | User handlers: free chat, system chat, digest, notes, profile |
| `bot_mail_creds.py` | Per-user IMAP credentials, consent flow, digest fetch + LLM summarise |
| `bot_email.py` | "Send as email" SMTP for notes, digest, and calendar events |
| `bot_error_protocol.py` | Error protocol: collect text/voice/photo → save dir → email |
| `telegram_menu_bot.py` | Entry point: handler registration + callback dispatcher + `main()` |
| `bot_llm.py` | Pluggable LLM backend abstraction — shared by Telegram + Web channels |
| `bot_auth.py` | JWT/bcrypt authentication, `accounts.json` — used by Web UI |
| `bot_ui.py` | Screen DSL dataclasses: `Screen`, `Button`, `Card`, `Toggle`, `Spinner`, etc. |
| `bot_actions.py` | Action handlers returning `Screen` objects — shared logic layer |
| `render_telegram.py` | Renders `Screen` → Telegram `send_message` / `InlineKeyboardMarkup` |
| `bot_web.py` | FastAPI application: all HTTP routes, Jinja2 templates, HTMX endpoints |

### 3.2 Main Menu — User Functions

| Button | Callback key | Access | Description |
|---|---|---|---|
| 📧 Mail | `digest` | all approved | Per-user mail digest (IMAP fetch + LLM summary) |
| 💬 Free Chat | `mode_chat` | all approved | Text chat with LLM |
| 🖥 System Chat | `mode_system` | **admin only** | NL → bash command → confirm-gate → execute on Pi |
| 🎤 Voice | `voice_session` | all approved | Voice mode instructions (voice messages work in any mode) |
| 📝 Notes | `menu_notes` | all approved | Personal Markdown notes manager |
| 🗓 Calendar | `menu_calendar` | all approved | Smart calendar with NL add, query, console, multi-event |
| 👤 Profile | `profile` | all approved | Show name, username, role, registration date, masked email |
| 🐛 Error Protocol | `errp_start` | **admin only** | Collect text/voice/photo error reports → save + email |
| ❓ Help | `help` | all approved | Contextual help (admin / user / guest variants) |
| 🔐 Admin | `admin_menu` | **admin only** | Admin control panel |

### 3.3 Admin Panel Buttons

| Button | Callback key | Description |
|---|---|---|
| ➕ Add user | `admin_add_user` | Add a guest user by Telegram chat ID |
| 📋 List users | `admin_list_users` | 4-section list: Admins / Full Users / Pending / Guests |
| 🗑 Remove user | `admin_remove_user` | Remove a dynamic guest user |
| 👥 Pending | `admin_pending_users` | Approve / block pending registrations |
| 🤖 Switch LLM | `admin_llm_menu` | Select active model; OpenAI sub-menu with key entry |
| 📡 Local Fallback | `admin_llm_fallback_menu` | Toggle `~/.picoclaw/llm_fallback_enabled`; shows ON/OFF status + URL/model |
| ⚡ Voice Opts | `voice_opts_menu` | Toggle 10 voice optimisation flags |
| 📝 Release Notes | `admin_changelog` | Full versioned changelog from `release_notes.json` |

### 3.4 Voice Optimization Flags (`⚡ Voice Opts`)

All `false` by default. Persisted in `~/.picoclaw/voice_opts.json`.

| Flag | Effect |
|---|---|
| `silence_strip` | `ffmpeg silenceremove` on incoming OGG before Vosk decode |
| `low_sample_rate` | Decode at 8 kHz instead of 16 kHz (faster Vosk, lower quality) |
| `warm_piper` | Pre-run Piper at startup to load ONNX into page cache |
| `parallel_tts` | Start TTS thread immediately after LLM call completes |
| `user_audio_toggle` | Enable per-user 🔊/🔇 toggle for TTS voice replies |
| `tmpfs_model` | Copy Piper ONNX to `/dev/shm` (RAM disk) for fastest load |
| `vad_prefilter` | WebRTC VAD noise gate strips non-speech frames before Vosk |
| `whisper_stt` | Use `whisper.cpp` (ggml-base.bin) instead of Vosk for STT |
| `piper_low_model` | Use `ru_RU-irina-low.onnx` (faster TTS, lower quality) |
| `persistent_piper` | Keep a warm Piper subprocess alive; holds ONNX in page cache |
| `voice_timing_debug` | Show per-stage ⏱ timing breakdown in voice replies (debug) |

---

## 4. Chat Architecture

### 4.1 Message Routing State Machine

Every incoming text message is routed by `_user_mode[chat_id]`:

```
Incoming text
      │
      ├─ _user_mode == "reg_name"        → _finish_registration()
      ├─ _user_mode == "chat"             → _handle_chat_message()
      ├─ _user_mode == "system"           → _handle_system_message()  [admin only]
      ├─ _user_mode == "calendar"          → _finish_cal_add()
      ├─ _user_mode == "cal_console"       → _handle_cal_console()
      ├─ _user_mode == "cal_edit_*"        → _cal_handle_edit_input()
      ├─ _user_mode == "errp_name"         → _finish_errp_name()
      ├─ _user_mode == "errp_collect"      → _errp_collect_text()
      ├─ _pending_note[cid] exists        → note title / content step
      ├─ _pending_mail_setup[cid] exists  → mail setup wizard step
      ├─ _pending_llm_key[cid] exists     → _handle_save_llm_key()
      ├─ _pending_admin_*[cid] exists     → admin user-management step
      ├─ _pending_email_target[cid]       → finish_email_set_target()
      └─ else                             → show main menu
```

Voice messages bypass the mode machine: all OGG Opus voice notes are unconditionally routed to `_handle_voice_message()` regardless of `_user_mode`.

### 4.2 Free Chat (`mode_chat`)

```
User sends text
  → _handle_chat_message(chat_id, text)
  → _check_injection(text)                 ← L1 pattern scan
  │     blocked → send warning, stop
  → SECURITY_PREAMBLE + lang instruction
    + _wrap_user_input(text)               ← L2: [USER]…[/USER]
  → _ask_picoclaw(prompt, timeout=60)      ← subprocess: picoclaw agent -m
  → bot.send_message(chat_id, response, parse_mode="Markdown")
```

### 4.3 System Chat (`mode_system` — admin only)

```
Admin sends text
  → _handle_system_message(chat_id, text)
  → _check_injection(text)                ← L1 blocks dangerous shell syntax
  │     blocked → send warning, stop
  → LLM call: generate single bash command
  → _pending_cmd[chat_id] = command
  → show confirm keyboard: ✅ Run / ❌ Cancel

Admin taps ✅ Run
  → _execute_pending_cmd(chat_id)
  → _run_subprocess(["bash", "-c", cmd], timeout=30)
  → send output (truncated to 3800 chars)
```

### 4.4 Callback Dispatcher Summary

All inline button taps arrive at a single `@bot.callback_query_handler`. Selected dispatch branches:

| Prefix / Key | Handler | Access |
|---|---|---|
| `menu` | `_send_menu` | all |
| `digest` / `digest_refresh` / `digest_tts` / `digest_email` | mail handlers | all |
| `mode_chat` | set `_user_mode='chat'` | all |
| `mode_system` | set `_user_mode='system'` | **admin** |
| `voice_session` / `voice_audio_toggle` | voice handlers | all |
| `profile` / `help` | info handlers | all |
| `admin_menu` and all `admin_*` | admin handlers | **admin** |
| `reg_approve:<id>` / `reg_block:<id>` | registration approval | **admin** |
| `llm_select:<model>` / `llm_setkey_openai` / `admin_llm_fallback_menu` / `admin_llm_fallback_toggle` | LLM switcher | **admin** |
| `voice_opts_menu` / `voice_opt_toggle:<key>` | voice opts | **admin** |
| `menu_notes` / `note_*` | notes handlers | approved |
| `menu_calendar` / `cal_*` | calendar handlers | approved |
| `mail_consent` / `mail_provider:*` / `mail_settings` / `mail_del_creds` | mail setup | all |
| `email_change_target` | SMTP target | all |
| `errp_start` / `errp_send` / `errp_cancel` | error protocol | **admin** |
| `cancel` | clear pending state, show menu | all |
| `run:<hash>` | `_execute_pending_cmd` | **admin** |
