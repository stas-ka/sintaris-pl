# Picoclaw Bot — Architecture

**Version:** `2026.3.23` · **Last updated:** March 2026

## 1. Overview

A multi-modal personal assistant running on a Raspberry Pi 3 B+. Two parallel channels reach the same LLM backend:

1. **Telegram Menu Bot** (`bot = @smartpico_bot`) — interactive button-driven Telegram interface with text chat, voice sessions, notes, calendar, mail digest, and admin panel.
2. **Standalone Voice Assistant** (`voice_assistant.py`) — always-on wake-word loop using the Pi's microphone and speaker.

Both channels call the same LLM backend: `picoclaw agent -m` → OpenRouter.

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
 [picoclaw]    ← CLI subprocess: picoclaw agent -m "<text>"
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

## 2. Standalone Voice Assistant Components

### 2.1 Audio Capture — PipeWire / pw-record

| Property | Value |
|---|---|
| Backend | PipeWire (default on Raspberry Pi OS Bookworm) |
| Capture command | `pw-record --rate=16000 --channels=1 --format=s16 -` |
| Fallback | `parec --rate=16000 --channels=1 --format=s16le` |
| Chunk size | 4000 frames (250 ms at 16 kHz) |
| Required env vars | `XDG_RUNTIME_DIR=/run/user/1000`, `PIPEWIRE_RUNTIME_DIR=/run/user/1000`, `PULSE_SERVER=unix:/run/user/1000/pulse/native` |
| Source selection | Configurable via `AUDIO_TARGET` env var (see below) |

**`AUDIO_TARGET` values:**

| Value | Behavior |
|---|---|
| `auto` (default) | Let PipeWire select the default source |
| `webcam` | Use Philips SPC 520 USB webcam mic node |
| `<node name>` | Any PipeWire source node (from `pactl list sources short`) |

> **Known issue**: Philips SPC 520/525NC USB webcam mic fails on Pi 3's DWC_OTG USB controller — isochronous transfers complete the USB handshake but deliver zero data. `implicit_fb=1` modprobe flag does not resolve this. Use a standard USB microphone or the I2S RB-TalkingPI HAT instead.

### 2.2 Speech-to-Text — Vosk

| Property | Value |
|---|---|
| Library | `vosk` 0.3.45 (Python binding for Kaldi-based ASR) |
| Model | `vosk-model-small-ru-0.22` (48 MB) |
| Model path | `/home/stas/.picoclaw/vosk-model-small-ru/` |
| Language | Russian |
| Mode | Streaming (real-time chunk processing) |
| Word timestamps | Enabled (`SetWords(True)`) |
| CPU usage | ~40–60% on Pi 3 single core during recognition |

**Why not the full model?** `vosk-model-ru-0.42` (1.5 GB) runs out of RAM on Pi 3 (1 GB). The small model handles short voice commands well.

### 2.3 Hotword Detection

Implemented in `voice_assistant.py` using Python's `difflib.SequenceMatcher`:

- Hotwords: `пико`, `пика`, `пике`, `пик`, `привет пико`
- Threshold: `0.75` similarity ratio
- Also checks exact substring before fuzzy match
- Bigram matching for two-word hotwords ("привет пико")

When triggered: hotword stream killed → beep plays → fresh Vosk recognizer records command phrase → stream restarts after response is spoken.

### 2.4 LLM — picoclaw + OpenRouter

| Property | Value |
|---|---|
| Binary | `/usr/bin/picoclaw` (sipeed/picoclaw v0.2.0 aarch64 deb) |
| Invocation | `picoclaw agent -m "<recognized text>"` |
| LLM provider | OpenRouter (`openrouter.ai`) |
| Default model | `openrouter/openai/gpt-4o-mini` |
| Config file | `/home/stas/.picoclaw/config.json` |
| Timeout | 60 seconds |

### 2.5 Text-to-Speech — Piper

| Property | Value |
|---|---|
| Engine | Piper TTS (ONNX Runtime) |
| Binary | `/usr/local/bin/piper` (wrapper calling `/usr/local/share/piper/piper`) |
| Voice model | `ru_RU-irina-medium.onnx` (66 MB, natural female Russian) |
| Output format | Raw PCM S16_LE at 22050 Hz mono |
| Latency | ~1–3 s per sentence on Pi 3 (RTF ≈ 0.83) |
| RAM usage | ~150 MB peak |

**Why Piper instead of Silero?** Silero TTS requires PyTorch (~2 GB download, ~1.5 GB RAM). Pi 3 has 1 GB total — impossible. Piper uses ONNX Runtime with bundled shared libs, no Python dependencies.

---

## 3. Telegram Menu Bot

**Version:** `BOT_VERSION = "2026.3.23"` · **Entry point:** `telegram_menu_bot.py` · **Service:** `picoclaw-telegram.service`

The interactive Telegram bot is split into 12 Python modules. All logic is in `bot_*.py`; `telegram_menu_bot.py` only registers handlers and dispatches callbacks.

### 3.1 Module Structure

Module dependency chain (no circular imports):

```
bot_config → bot_state → bot_instance → bot_security → bot_access → bot_users
    → bot_voice → bot_calendar → bot_admin → bot_handlers
    → bot_mail_creds → bot_email → telegram_menu_bot
```

| Module | Responsibility |
|---|---|
| `bot_config.py` | Constants, env loading, logging — root of dependency tree |
| `bot_state.py` | Mutable runtime dicts, voice_opts I/O, dynamic_users I/O |
| `bot_instance.py` | `bot = TeleBot(...)` singleton |
| `bot_security.py` | 3-layer prompt injection guard; `SECURITY_PREAMBLE`; `_wrap_user_input()` |
| `bot_access.py` | Access control, i18n `_t()`, keyboards, text utils, `_ask_picoclaw()` |
| `bot_users.py` | Registration + notes file I/O (pure, no Telegram API calls) |
| `bot_voice.py` | Full voice pipeline: STT/TTS/VAD, multi-part "Read aloud", orphan cleanup |
| `bot_calendar.py` | Smart calendar: CRUD events, NL parsing, reminders, morning briefing, TTS |
| `bot_admin.py` | Admin panel: users, LLM switcher, voice opts, release notes |
| `bot_handlers.py` | User handlers: free chat, system chat, digest, notes, profile |
| `bot_mail_creds.py` | Per-user IMAP credentials, consent flow, digest fetch + LLM summarise |
| `bot_email.py` | "Send as email" SMTP for notes, digest, and calendar events |
| `telegram_menu_bot.py` | Entry point: handler registration + callback dispatcher + `main()` |

### 3.2 Main Menu — User Functions

| Button | Callback key | Access | Description |
|---|---|---|---|
| 📧 Mail | `digest` | all approved | Per-user mail digest (IMAP fetch + LLM summary) |
| 💬 Free Chat | `mode_chat` | all approved | Text chat with LLM |
| 🖥 System Chat | `mode_system` | **admin only** | NL → bash command → confirm-gate → execute on Pi |
| 🎤 Voice | `voice_session` | all approved | Voice mode instructions (voice messages work in any mode) |
| 📝 Notes | `menu_notes` | all approved | Personal Markdown notes manager |
| 🗓 Calendar | `menu_calendar` | all approved | Smart calendar with NL event add |
| 👤 Profile | `profile` | all approved | Show name, username, role, registration date, masked email |
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
      ├─ _user_mode == "cal_input"        → _finish_cal_add()
      ├─ _user_mode == "cal_edit_*"       → _cal_handle_edit_input()
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
| `llm_select:<model>` / `llm_setkey_openai` | LLM switcher | **admin** |
| `voice_opts_menu` / `voice_opt_toggle:<key>` | voice opts | **admin** |
| `menu_notes` / `note_*` | notes handlers | approved |
| `menu_calendar` / `cal_*` | calendar handlers | approved |
| `mail_consent` / `mail_provider:*` / `mail_settings` / `mail_del_creds` | mail setup | all |
| `email_change_target` | SMTP target | all |
| `cancel` | clear pending state, show menu | all |
| `run:<hash>` | `_execute_pending_cmd` | **admin** |

---

## 5. Voice Conversation Architecture

### 5.1 Incoming Voice Pipeline (Telegram)

Voice messages received as OGG Opus from Telegram; processed unconditionally independent of `_user_mode`.

```
Telegram OGG Opus voice note
      │
      ▼
 bot.get_file() + bot.download_file()      ← Telegram API
      │
      ▼
 [ffmpeg] OGG → 16 kHz mono S16LE PCM
      │   -ar 16000 -ac 1 -f s16le
      │   + silenceremove filter  (if silence_strip opt)
      │   + -ar 8000              (if low_sample_rate opt)
      │
      ▼
 [VAD filter]  (if vad_prefilter opt)      ← webrtcvad: strip non-speech frames
      │
      ▼
 STT:
  ├── [Vosk]   default              ← vosk-model-small-ru (48 MB, offline)
  │            KaldiRecognizer → transcript + [?word] confidence strip
  └── [Whisper] if whisper_stt opt  ← whisper-cpp ggml-base.bin (142 MB)
                better WER, ~2× slower
      │
      ▼
 SECURITY_PREAMBLE + lang hint
 + _wrap_user_input(transcript)            ← L2: [USER]…[/USER]
      │
      ▼
 _ask_picoclaw(prompt, timeout=60)         ← subprocess: picoclaw agent -m
      │
      ▼
 bot.send_message()                        ← text reply shown immediately
      │
      ▼
 [if audio not muted]
 _tts_to_ogg(response[:TTS_MAX_CHARS])
      │
      ▼
 bot.send_voice()                          ← OGG Opus voice reply
```

**Key voice constants** (from `bot_config.py`):

| Constant | Value | Meaning |
|---|---|---|
| `VOICE_SAMPLE_RATE` | `16000` | STT decode rate (Hz) |
| `TTS_MAX_CHARS` | `600` | Real-time voice chat cap (~25 s on Pi 3 B+) |
| `TTS_CHUNK_CHARS` | `1200` | Per-part "Read aloud" cap (~55 s on Pi 3 B+) |
| `VOICE_TIMING_DEBUG` | `false` | Emit per-stage latency log lines when `true` |

### 5.2 TTS Chunking — "Read Aloud" Feature

Long texts (notes, digest, calendar events) are split at sentence boundaries and sent as N sequential voice messages.

```
_handle_note_read_aloud(chat_id, slug)
  → load note text
  → _split_for_tts(text, max_chars=TTS_CHUNK_CHARS)
  │     splits on ". " / "! " / "? " / "\n" boundaries
  │     chunks ≤ TTS_CHUNK_CHARS chars each
  → for i, chunk in enumerate(chunks):
        ogg = _tts_to_ogg(chunk, _trim=False)
        bot.send_voice(chat_id, ogg,
            caption=f"🔊 {title} ({i+1}/{n})")
```

Same pattern used by `_handle_digest_tts()` and `_handle_cal_confirm_tts()`.

### 5.3 TTS Pipeline Detail

`_tts_to_ogg(text, _trim=True)`:

```
text
  │ if _trim: truncate to TTS_MAX_CHARS
  ▼
_escape_tts(text)          ← strip emoji, Markdown, ANSI
  ▼
_piper_model_path()        ← priority: tmpfs → low → medium
  ▼
piper subprocess:
  stdin  ← text (UTF-8)
  stdout → raw PCM S16LE 22050 Hz
  (if persistent_piper: reuse warm subprocess)
  ▼
ffmpeg subprocess:
  stdin  ← raw PCM
  stdout → OGG Opus 24 kbit/s
  ▼
return bytes (OGG)
```

**Piper model priority chain:**
```
tmpfs_model ON  AND  /dev/shm/piper/...onnx exists  →  tmpfs (fastest)
    ↓ else
piper_low_model ON  AND  ~/.picoclaw/ru_RU-irina-low.onnx exists  →  low model
    ↓ else
default:  ~/.picoclaw/ru_RU-irina-medium.onnx
```

### 5.4 STT — Vosk vs Whisper

| Property | Vosk (default) | Whisper (opt: `whisper_stt=true`) |
|---|---|---|
| Model | `vosk-model-small-ru` (48 MB) | `ggml-base.bin` (142 MB) |
| Latency on Pi 3 | ~15 s / 5 s audio | ~30 s / 5 s audio |
| WER (Russian) | ~25% | ~18% |
| Confidence filter | strips `[?word]` → `word` | n/a |

---

## 6. Security Architecture

### 6.1 Three-Layer Prompt Injection Defense (`bot_security.py`)

**L1 — Input validation (pre-LLM scan):**  
`_check_injection(text)` scans ~25 regex patterns covering:
- Instruction override (Russian + English): "ignore previous instructions", "забудь инструкции"
- Persona hijack: "you are now", "притворись"
- Prompt extraction: "repeat your instructions", "покажи промпт"
- Credential extraction: "show api_key", "покажи токен"
- Path disclosure: `cat /home/stas/`, `bot.env`
- Shell injection: backticks, `$()`, chained dangerous commands
- Jailbreak keywords: DAN, jailbreak, developer mode

If any pattern matches: message blocked, user warned, LLM **never called**.

**L2 — User input delimiting:**  
`_wrap_user_input(text)` → `"[USER]\n{text}\n[/USER]"` prevents the LLM from treating user text as instructions.

**L3 — Security preamble:**  
`SECURITY_PREAMBLE` prepended to every free-chat and voice LLM call. Instructs the model not to reveal credentials/paths, not to disclose system prompts, not to generate shell commands, and to ignore role-override attempts.

### 6.2 Role-Based Access

| Role | Condition | Permissions |
|---|---|---|
| **Admin** | `chat_id in ADMIN_USERS` | All features + admin panel + system chat |
| **Full user** | `chat_id in ALLOWED_USERS` | All user features |
| **Approved guest** | `chat_id in _dynamic_users` | All user features (dynamically approved) |
| **Pending** | Submitted `/start`, awaiting admin | Registration confirmation only |
| **Blocked** | `reg.status == "blocked"` | Blocked message only |

---

## 7. Per-User Mail System (`bot_mail_creds.py`)

Each user configures their own IMAP mailbox. The legacy shared `gmail_digest.py` cron job is deprecated in favour of this module.

### 7.1 Setup Flow

```
User taps 📧 Mail → handle_digest_auth()
  → no creds: show consent gate (GDPR Art. 6(1)(a) + 152-FZ)
  → User agrees → provider selection: Gmail / Yandex / Mail.ru / Custom
  → User selects → prompt email address (ForceReply)
  → User types email → prompt App Password (ForceReply)
  → finish_mail_setup(): test IMAP → save creds → show digest
```

### 7.2 Storage

| File | Contents |
|---|---|
| `~/.picoclaw/mail_creds/<chat_id>.json` | `{provider, email, password, imap_host, imap_port}` — chmod 600 |
| `~/.picoclaw/mail_creds/<chat_id>_last_digest.txt` | Last digest text cache |
| `~/.picoclaw/mail_creds/<chat_id>_target.txt` | SMTP send-to address |

### 7.3 Digest Pipeline

```
_fetch_and_summarize(chat_id)
  → IMAP4_SSL connect with stored creds
  → fetch INBOX + Spam/Junk (last 24h, max 50 each)
  → _build_digest_prompt() → _ask_picoclaw(prompt, timeout=120)
  → cache to _last_digest_file(chat_id)
  → return summary text
```

Refresh runs in a background thread so the main bot thread is not blocked.

### 7.4 Providers

| Provider | IMAP Host | Notes |
|---|---|---|
| Gmail | `imap.gmail.com:993` | Requires App Password (2FA enabled) |
| Yandex | `imap.yandex.ru:993` | Requires App Password |
| Mail.ru | `imap.mail.ru:993` | Requires App Password |
| Custom | User-supplied | Arbitrary IMAP host + port |

---

## 8. Smart Calendar (`bot_calendar.py`)

### 8.1 Add Event Flow

```
User says/writes: "встреча с командой завтра в 11 утра"
  → _finish_cal_add(chat_id, text)
  → _ask_picoclaw(): extract JSON {title, dt_iso, remind_before_min}
  → _show_cal_confirm(): show parsed data for review
  → User taps ✅ → _cal_do_confirm_save()
  → _cal_add_event(): save to calendar JSON
  → _schedule_single_reminder(): threading.Timer
```

### 8.2 Background Threads

| Thread | Purpose |
|---|---|
| `threading.Timer` per event | Fire reminder at `event_dt − remind_before_min`; rebuilt on startup |
| `_cal_morning_briefing_loop()` | Daemon thread: sends today's event summary at `_BRIEFING_HOUR = 8` (08:00) |

### 8.3 Storage

`~/.picoclaw/calendar/<chat_id>.json` — list of events: `[{id, title, dt_iso, remind_before_min, reminded}]`

---

## 9. Send as Email (`bot_email.py`)

Sends notes, digest, and calendar events to a target address using the user's own IMAP mailbox as the SMTP sender.

```
User taps 📧 Send as email
  → _get_target_email(chat_id)          ← read …_target.txt; prompt if absent
  → _load_creds(chat_id)
  → _smtp_host_port(imap_host)          ← infer smtp.*.* from imap.*.*
  → _send_in_thread(): smtplib SMTP_SSL connect → send MIMEText
  → show ✅ Sent confirmation
```

---

## 10. User Registration & Profile

### 10.1 Registration Flow

```
Unknown user sends /start
  → not in any allowed set → _user_mode[cid] = "reg_name"
  → prompt "Enter your name"
  → _finish_registration(): _upsert_registration(cid, name, "pending")
  → notify all admins with inline ✅ Approve / ❌ Block buttons

Admin approves → add to _dynamic_users; send approval message to user
Admin blocks   → set status "blocked"
```

### 10.2 Profile View

`_handle_profile(chat_id)` shows: full name, Telegram username, chat ID, role, registration date, masked email (if mail creds configured).

---

## 11. Process Hierarchy (at runtime)

```
systemd
  ├── picoclaw-gateway.service
  │     └── /usr/bin/picoclaw gateway  (disabled — config "enabled": false)
  │
  ├── picoclaw-telegram.service
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
  │           │           ├── picoclaw agent [subprocess]   ← LLM
  │           │           ├── piper [subprocess]            ← TTS synthesis
  │           │           └── ffmpeg [subprocess]           ← PCM → OGG Opus
  │           │
  │           ├── [mail refresh threads]
  │           │     └── _run_refresh_thread() per user  ← IMAP fetch + LLM
  │           │
  │           └── [email send threads]
  │                 └── _send_in_thread() per send op  ← SMTP
  │
  └── picoclaw-voice.service
        └── /usr/bin/python3 voice_assistant.py
              ├── pw-record [subprocess]  ← continuous hotword listen
              ├── pw-record [subprocess]  ← command recording (transient)
              ├── piper     [subprocess]  ← TTS synthesis
              └── aplay     [subprocess]  ← audio output
```

---

## 12. File Layout on Pi

```
/home/stas/.picoclaw/
  telegram_menu_bot.py          ← entry point (v2026.3.23)
  bot_config.py                 ← constants, env loading, logging
  bot_state.py                  ← mutable runtime state dicts
  bot_instance.py               ← TeleBot singleton
  bot_security.py               ← 3-layer prompt injection guard
  bot_access.py                 ← access control, i18n, keyboards, _ask_picoclaw
  bot_users.py                  ← registration + notes file I/O
  bot_voice.py                  ← full voice pipeline: STT/TTS/VAD + multi-part TTS
  bot_calendar.py               ← smart calendar: CRUD, NL parser, reminders, briefing
  bot_admin.py                  ← admin panel handlers
  bot_handlers.py               ← user handlers: chat, digest, notes, profile, system
  bot_mail_creds.py             ← per-user IMAP credentials + digest
  bot_email.py                  ← send-as-email SMTP
  voice_assistant.py            ← standalone voice daemon
  strings.json                  ← i18n UI strings (ru/en)
  release_notes.json            ← versioned changelog
  config.json                   ← picoclaw LLM config (model_list, agents)
  bot.env                       ← BOT_TOKEN + ALLOWED_USERS + ADMIN_USERS
  gmail_digest.py               ← legacy shared digest cron (deprecated)

  ── auto-created runtime files ──
  voice_opts.json               ← voice optimisation flags (do not commit)
  pending_tts.json              ← TTS orphan-cleanup tracker
  users.json                    ← dynamically approved guest users
  registrations.json            ← registration records (pending/approved/blocked)
  last_notified_version.txt     ← last BOT_VERSION admin notification
  active_model.txt              ← admin-selected LLM model name
  notes/<chat_id>/<slug>.md     ← per-user Markdown notes
  calendar/<chat_id>.json       ← per-user calendar events
  mail_creds/<chat_id>.json     ← per-user IMAP credentials (chmod 600)
  mail_creds/<chat_id>_last_digest.txt   ← last digest cache
  mail_creds/<chat_id>_target.txt        ← send-as-email target address
  telegram_bot.log              ← bot log file

  ── voice models ──
  vosk-model-small-ru/          ← 48 MB Vosk Russian STT model
  ru_RU-irina-medium.onnx       ← 66 MB Piper TTS voice (medium quality)
  ru_RU-irina-medium.onnx.json  ← Piper voice config
  ru_RU-irina-low.onnx          ← optional: low quality (faster TTS)
  ru_RU-irina-low.onnx.json     ← optional: low quality config
  ggml-base.bin                 ← optional: Whisper STT model (142 MB)

/dev/shm/piper/                   ← optional tmpfs model copy (voice_opt: tmpfs_model)
/usr/local/bin/piper              ← Piper wrapper script
/usr/local/share/piper/           ← Piper binary + bundled libs
/usr/bin/picoclaw                 ← picoclaw Go binary (from .deb)

/etc/systemd/system/
  picoclaw-gateway.service
  picoclaw-voice.service
  picoclaw-telegram.service

/mnt/ssd/backups/images/          ← full SD card image backups (optional, USB SSD)
/etc/modprobe.d/
  usb-audio-fix.conf              ← options snd-usb-audio implicit_fb=1
```

---

## 13. Configuration Reference

### `bot_config.py` constants

| Constant | Value | Env override | Description |
|---|---|---|---|
| `BOT_VERSION` | `"2026.3.23"` | — | Version string; bump on every user-visible change |
| `PIPER_BIN` | `/usr/local/bin/piper` | `PIPER_BIN` | Piper TTS wrapper binary |
| `PIPER_MODEL` | `~/.picoclaw/ru_RU-irina-medium.onnx` | `PIPER_MODEL` | Default Piper voice model |
| `PIPER_MODEL_LOW` | `~/.picoclaw/ru_RU-irina-low.onnx` | `PIPER_MODEL_LOW` | Low-quality Piper model |
| `WHISPER_BIN` | `/usr/local/bin/whisper-cpp` | `WHISPER_BIN` | whisper.cpp binary |
| `WHISPER_MODEL` | `~/.picoclaw/ggml-base.bin` | `WHISPER_MODEL` | Whisper model file |
| `VOSK_MODEL_PATH` | `~/.picoclaw/vosk-model-small-ru` | `VOSK_MODEL_PATH` | Vosk model directory |
| `VOICE_SAMPLE_RATE` | `16000` | — | Base STT decode rate (Hz) |
| `VOICE_CHUNK_SIZE` | `4000` | — | Frames per processing chunk (250 ms) |
| `VOICE_SILENCE_TIMEOUT` | `4.0` | — | Silence timeout for voice recording (s) |
| `VOICE_MAX_DURATION` | `30.0` | — | Hard voice session cap (s) |
| `TTS_MAX_CHARS` | `600` | — | Real-time voice TTS cap (~25 s on Pi 3) |
| `TTS_CHUNK_CHARS` | `1200` | — | Per-part "Read aloud" cap (~55 s on Pi 3) |
| `VOICE_TIMING_DEBUG` | `false` | `VOICE_TIMING_DEBUG=1` | Per-stage latency log output |
| `NOTES_DIR` | `~/.picoclaw/notes` | `NOTES_DIR` | Base dir for note files |
| `CALENDAR_DIR` | `~/.picoclaw/calendar` | `CALENDAR_DIR` | Base dir for calendar files |
| `MAIL_CREDS_DIR` | `~/.picoclaw/mail_creds` | `MAIL_CREDS_DIR` | Base dir for mail credentials |
| `REGISTRATIONS_FILE` | `~/.picoclaw/registrations.json` | `REGISTRATIONS_FILE` | User registration records |
| `STRINGS_FILE` | `strings.json` next to script | `STRINGS_FILE` | i18n UI text file (ru/en) |
| `PICOCLAW_BIN` | `/usr/bin/picoclaw` | `PICOCLAW_BIN` | picoclaw Go binary |

### `voice_assistant.py` CONFIG

| Key | Default | Env Override | Description |
|---|---|---|---|
| `vosk_model_path` | `/home/stas/.picoclaw/vosk-model-small-ru` | `VOSK_MODEL_PATH` | Vosk model directory |
| `piper_bin` | `/usr/local/bin/piper` | `PIPER_BIN` | Piper TTS binary |
| `piper_model` | `/home/stas/.picoclaw/ru_RU-irina-medium.onnx` | `PIPER_MODEL` | Piper voice model |
| `picoclaw_bin` | `/usr/bin/picoclaw` | `PICOCLAW_BIN` | picoclaw binary |
| `audio_target` | `auto` | `AUDIO_TARGET` | Microphone selection |
| `sample_rate` | `16000` | — | Audio capture rate (Hz) |
| `chunk_size` | `4000` | — | Frames per processing chunk |
| `hotwords` | `["пико", "пика", ...]` | — | Wake words list |
| `hotword_threshold` | `0.75` | — | Fuzzy match sensitivity |
| `silence_timeout` | `2.0` | — | Seconds of silence to end recording |
| `max_phrase_duration` | `15.0` | — | Max command recording length (s) |
| `min_phrase_chars` | `3` | — | Minimum chars to accept STT result |

---

## 14. Backup System

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

## 15. Release Notes & Version Tracking

| Item | Value |
|---|---|
| Constant | `BOT_VERSION = "2026.3.23"` in `bot_config.py` |
| Format | `YYYY.M.D` (no zero-padding) |
| Changelog source | `release_notes.json` (deployed alongside bot) |
| Tracking file | `~/.picoclaw/last_notified_version.txt` (auto-created) |
| Trigger | On startup: if `BOT_VERSION != last_notified`, send release entry to all admins |
| Admin view | Admin panel → 📝 Release Notes shows full changelog |
