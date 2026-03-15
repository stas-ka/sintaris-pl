# Picoclaw Bot — Architecture

**Version:** `2026.3.28` · **Last updated:** March 2026

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

**Version:** `BOT_VERSION = "2026.3.28"` · **Entry point:** `telegram_menu_bot.py` · **Service:** `picoclaw-telegram.service`

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
      ├─ _user_mode == "cal_console"       → _handle_cal_console()   ← new
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
| `llm_select:<model>` / `llm_setkey_openai` | LLM switcher | **admin** |
| `voice_opts_menu` / `voice_opt_toggle:<key>` | voice opts | **admin** |
| `menu_notes` / `note_*` | notes handlers | approved |
| `menu_calendar` / `cal_*` | calendar handlers | approved |
| `mail_consent` / `mail_provider:*` / `mail_settings` / `mail_del_creds` | mail setup | all |
| `email_change_target` | SMTP target | all |
| `errp_start` / `errp_send` / `errp_cancel` | error protocol | **admin** |
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
                better WER, ~2× slower; hallucination guard discards
                sparse output (< 2 words/s) and falls back to Vosk
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
| Latency on Pi 3 | ~15 s / 5 s audio | ~30–35 s / 5 s audio |
| WER (Russian) | ~25% | ~18% |
| Confidence filter | strips `[?word]` → `word` | n/a |
| Hallucination guard | n/a | discards output with < 2 words/s; falls back to Vosk |
| Parallel threads | single-threaded | `--threads 4` (all Pi 3 cores) |

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

### 8.1 Add Event Flow (single event)

```
User writes: "встреча с командой завтра в 11 утра"
  → _finish_cal_add(chat_id, text)
  → _ask_picoclaw(): extract JSON {"events": [{title, dt}, ...]}
  → 1 event → _show_cal_confirm(): review card
    → User taps ✅ → _cal_do_confirm_save()
    → _cal_add_event(): save to calendar JSON
    → _schedule_reminder(): threading.Timer
```

### 8.2 Multi-Event Add Flow

```
User writes: "завтра в 10 команда, в 15 врач, в 19 ужин с Машей"
  → _finish_cal_add() → LLM returns {"events": [{...}, {...}, {...}]}
  → 3 events → _pending_cal = {step: "multi_confirm", events: [...], idx: 0}
  → _show_cal_confirm_multi(): "Event 1 of 3 — review:"
    → Save   → _cal_multi_save_one() → advance to next
    → Skip   → _cal_multi_skip()     → advance to next
    → Save All → _cal_multi_save_all() → save remaining without further confirmation
    → Cancel → discard all remaining
```

### 8.3 NL Query Flow

```
User writes: "что у меня на следующей неделе?"
  → _handle_calendar_query(chat_id, text)
  → _ask_picoclaw(): extract {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "label": "..."}
  → filter _cal_load() by date range
  → display formatted list with countdown
```

### 8.4 Calendar Console

```
User taps 💬 Консоль → _start_cal_console()
  → _user_mode = "cal_console"
  → User types free-form command
  → _handle_cal_console(): LLM classifies intent
      add    → _finish_cal_add()
      query  → _handle_calendar_query()
      delete → _handle_cal_delete_request()  (confirmation required)
      edit   → _handle_cal_event_detail()
```

### 8.5 Delete Confirmation

```
User taps 🗑 Delete
  → _handle_cal_delete_request(): show event + ✅ Confirm / ❌ Cancel
  → User taps ✅ → _handle_cal_delete_confirmed(): remove + cancel timer
```

### 8.6 Background Threads

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
  ├── picoclaw-web.service
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
  telegram_menu_bot.py          ← entry point (v2026.3.28)
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
  bot_error_protocol.py         ← error protocol: collect text/voice/photo → save → email
  voice_assistant.py            ← standalone voice daemon
  strings.json                  ← i18n UI strings (ru / de / en — 115 keys)
  release_notes.json            ← versioned changelog
  config.json                   ← picoclaw LLM config (model_list, agents)
  bot.env                       ← BOT_TOKEN + ALLOWED_USERS + ADMIN_USERS
  gmail_digest.py               ← legacy shared digest cron (deprecated)

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
/usr/bin/picoclaw                 ← picoclaw Go binary (from .deb)

/etc/systemd/system/
  picoclaw-gateway.service
  picoclaw-voice.service
  picoclaw-telegram.service
  picoclaw-web.service          ← FastAPI web UI (uvicorn HTTPS :8080)

/mnt/ssd/backups/images/          ← full SD card image backups (optional, USB SSD)
/etc/modprobe.d/
  usb-audio-fix.conf              ← options snd-usb-audio implicit_fb=1
```

---

## 13. Configuration Reference

### `bot_config.py` constants

| Constant | Value | Env override | Description |
|---|---|---|---|
| `BOT_VERSION` | `"2026.3.28"` | — | Version string; bump on every user-visible change |
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
| `STRINGS_FILE` | `strings.json` next to script | `STRINGS_FILE` | i18n UI text file (ru / de / en) |
| `VOSK_MODEL_DE_PATH` | `~/.picoclaw/vosk-model-small-de` | `VOSK_MODEL_DE_PATH` | Vosk German STT model directory |
| `PIPER_MODEL_DE` | `~/.picoclaw/de_DE-thorsten-medium.onnx` | `PIPER_MODEL_DE` | Piper German TTS voice model |
| `PIPER_MODEL_DE_TMPFS` | `/dev/shm/piper/de_DE-thorsten-medium.onnx` | — | RAM-disk copy of German TTS model |
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

## 14. Multilanguage Support

> **Status (2026-03-11):** Phase 1 and Phase 2 complete — all modules migrated to `_t()`. Deployed 2026-03-11.

### 14.1 Concept

The bot automatically detects each user's language from Telegram's `language_code` field and responds consistently in that language across all surfaces: UI buttons, bot messages, LLM responses, and TTS voice output.

```
User sends message / taps button
        │
        ▼
_set_lang(chat_id, from_user)
        │   reads Telegram language_code
        │   "ru*" → ru  |  "de*" → de  |  else → en
        ▼
_user_lang[chat_id] = "ru" | "de" | "en"   ← stored per session
        │
        ├── UI strings   → _t(chat_id, key)      ← looks up strings.json[lang][key]
        │
        ├── LLM replies  → _LANG_INSTRUCTION[lang]  ← prepended to every LLM prompt
        │                    "Antworte ausschließlich auf Deutsch…"
        │
        └── Voice (TTS)  → _piper_model_path(lang) ← selects language-specific ONNX
             Voice (STT)  → _get_vosk_model(lang)   ← selects language-specific Vosk
```

### 14.2 Supported Languages

| Code | Language | UI strings | LLM prompt | STT model | TTS model |
|------|----------|------------|------------|-----------|-----------|
| `ru` | Russian | ✅ 115 keys | ✅ | `vosk-model-small-ru` | `ru_RU-irina-medium.onnx` |
| `de` | German | ✅ 115 keys | ✅ | `vosk-model-small-de` *(optional)* | `de_DE-thorsten-medium.onnx` *(optional)* |
| `en` | English | ✅ 115 keys | ✅ | fallback: `vosk-model-small-ru` | fallback: `ru_RU-irina-medium.onnx` |

If a German/English voice model is absent, the pipeline falls back to Russian models with a warning log.

### 14.3 i18n String System

**`strings.json`** — flat JSON with one top-level object per language code:

```json
{
  "ru": { "welcome": "…", "btn_chat": "💬 Чат", … },
  "de": { "welcome": "…", "btn_chat": "💬 Chat", … },
  "en": { "welcome": "…", "btn_chat": "💬 Chat", … }
}
```

**`_t(chat_id, key, **kwargs)`** — the single string lookup function:
```python
lang = _user_lang.get(chat_id, "ru")
text = _STRINGS.get(lang, _STRINGS.get("en", {})).get(key, key)
return text.format(**kwargs) if kwargs else text
```
- Falls back: user lang → "en" → key name (never crashes)
- Supports `{placeholder}` substitution: `_t(cid, "note_saved", title="My note")`

**All 188 UI keys** are present in all three languages. All dynamic/inline strings in `bot_calendar.py`, `bot_handlers.py`, `bot_mail_creds.py`, and `bot_access.py` are fully migrated to `_t()` (Phase 2 complete).

### 14.4 LLM Language Injection

Every LLM call is prefixed with a language instruction from `_LANG_INSTRUCTION`:

| Lang | Instruction |
|------|-------------|
| `ru` | "Отвечай строго на русском языке. Не используй эмоджи…" |
| `de` | "Antworte ausschließlich auf Deutsch. Verwende keine Emojis…" |
| `en` | "Reply in English only. Do not use emoji…" |

For voice input with uncertain words `[?word]`, an additional STT-correction hint is injected in the user's language.

### 14.5 Per-Language Voice Pipeline

```
STT: _get_vosk_model(lang)
        lang == "de"  →  VOSK_MODEL_DE_PATH  (~/.picoclaw/vosk-model-small-de)
        else          →  VOSK_MODEL_PATH      (~/.picoclaw/vosk-model-small-ru)
        fallback: log warning + use Russian model

TTS: _piper_model_path(lang)
        lang == "de"
          tmpfs_model ON  →  PIPER_MODEL_DE_TMPFS  (/dev/shm/piper/de_DE-thorsten-medium.onnx)
          else            →  PIPER_MODEL_DE         (~/.picoclaw/de_DE-thorsten-medium.onnx)
          not found       →  log warning + fall back to Russian model
        else
          → standard RU model priority chain (see §5.3)
```

Both Vosk and Piper models are loaded lazily on first use; not at startup.

### 14.6 Implementation Status

| Component | Status | Details |
|-----------|--------|---------|
| Language detection (`_set_lang`) | ✅ Done | Detects ru/de/en from Telegram `language_code` |
| `strings.json` DE translations | ✅ Done | All 115 keys translated |
| LLM prompt injection | ✅ Done | German instruction in `_LANG_INSTRUCTION` |
| STT model routing | ✅ Done | `_get_vosk_model(lang)` in `bot_voice.py` |
| TTS model routing | ✅ Done | `_piper_model_path(lang)` in `bot_voice.py` |
| TTS `lang=` pass-through | ✅ Done | All `_tts_to_ogg()` calls pass `lang=` |
| Inline strings in `bot_calendar.py` | ✅ Done | All ternaries replaced with `_t()` — commit `143000d` |
| Inline strings in `bot_handlers.py` | ✅ Done | All labels migrated — commit `8b0db9a` |
| Inline strings in `bot_mail_creds.py` | ✅ Done | All strings + DE provider hints — commit `8b0db9a` |
| Inline strings in `bot_access.py` | ✅ Done | deny, back, mute labels — commit `8b0db9a` |
| `setup_voice.sh` German models | ✅ Done | vosk-small-de + de_DE-thorsten-medium downloads |
| **Deployed to Pi** | ✅ Done | Deployed 2026-03-11, v2026.3.26 |
| **Tested on Pi** | ✅ Done | Service start verified, journal clean |

### 14.7 Adding a New Language

To add a 4th language (e.g. French `fr`):

1. Add `"fr": { … }` section to `strings.json` — 115 keys
2. Add `"fr"` to `_SUPPORTED_LANGS` in `bot_access.py`
3. Add `elif lc.startswith("fr"): _user_lang[chat_id] = "fr"` to `_set_lang()`
4. Add French instruction to `_LANG_INSTRUCTION`
5. Add French Vosk model path to `bot_config.py` + `_get_vosk_model()` branch
6. Add French Piper voice model path to `bot_config.py` + `_piper_model_path()` branch
7. Add French model downloads to `setup_voice.sh`
8. Migrate all remaining inline strings to `_t()` (Phase 2 work applies to all languages)

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
| Constant | `BOT_VERSION = "2026.3.28"` in `bot_config.py` |
| Format | `YYYY.M.D` (no zero-padding) |
| Changelog source | `release_notes.json` (deployed alongside bot) |
| Tracking file | `~/.picoclaw/last_notified_version.txt` (auto-created) |
| Trigger | On startup: if `BOT_VERSION != last_notified`, send release entry to all admins |
| Admin view | Admin panel → 📝 Release Notes shows full changelog |

---

## 17. Web UI Channel (FastAPI)

**Service:** `picoclaw-web.service` · **Port:** HTTPS 8080 · **Auth:** JWT cookie `pico_token`

The Web UI channel provides a browser-based interface with the same features as the Telegram bot, served from the Pi over HTTPS using a self-signed TLS certificate. The interface is PWA-installable (works as a standalone app on mobile/desktop).

### 17.1 Technology Stack

| Layer | Technology |
|---|---|
| Application server | FastAPI (Python) + uvicorn |
| Transport | HTTPS TLS (self-signed, port 8080) |
| Templates | Jinja2 (server-side rendering) |
| Interactivity | HTMX (partial HTML swaps, no full-page reloads) |
| Client state | Alpine.js (lightweight reactive JS) |
| CSS framework | Pico CSS + custom `style.css` |
| PWA | `static/manifest.json` + theme_color + shortcuts |

### 17.2 Authentication (`bot_auth.py`)

| Item | Detail |
|---|---|
| User accounts | `~/.picoclaw/accounts.json` (username + bcrypt hash) |
| Token | JWT, RS256 or HS256, returned as `HttpOnly` cookie `pico_token` |
| Session | Cookie-based; re-login on expiry |
| Registration | Self-registration with admin approval flow |
| Admin check | `is_admin` flag in JWT claims |
| Dependency | FastAPI `Depends(get_current_user)` on every protected route |

**Auth flows:**
- **Flow A (login):** `POST /login` → verify bcrypt → issue JWT → set `pico_token` cookie → redirect `/`
- **Flow B (register):** `POST /register` → create pending account → admin notified → admin approves
- **Flow B2 (Telegram-linked register):** `POST /register` with `link_code` → `validate_web_link_code()` in `bot_state.py` → inherit role from Telegram account → status=active immediately (no admin approval needed)
- **Flow C (protected route):** incoming request → decode `pico_token` → raise 401 if missing/invalid → pass `UserContext` to handler
- **Flow D (logout):** `POST /logout` → delete cookie

### 17.3 Route Inventory

| Method | Path | Description | Auth |
|---|---|---|---|
| `GET` | `/login` | Login form | — |
| `POST` | `/login` | Verify creds, set JWT cookie | — |
| `GET` | `/register` | Registration form | — |
| `POST` | `/register` | Create pending account (optional `link_code` for Telegram-linked instant activation) | — |
| `POST` | `/logout` | Clear cookie | ✅ |
| `GET` | `/settings` | User settings page (language selector, change password) | ✅ |
| `POST` | `/settings` | Save language or password change | ✅ |
| `GET` | `/` | Dashboard | ✅ |
| `GET` | `/chat` | Chat page | ✅ |
| `POST` | `/api/chat/send` | Send message to LLM, return HTML partial (HTMX) | ✅ |
| `GET` | `/notes` | Notes list | ✅ |
| `GET` | `/notes/{slug}` | View note | ✅ |
| `POST` | `/notes` | Create note | ✅ |
| `PUT` | `/notes/{slug}` | Update note | ✅ |
| `DELETE` | `/notes/{slug}` | Delete note | ✅ |
| `GET` | `/calendar` | Calendar view | ✅ |
| `POST` | `/api/calendar/add` | Add event via NL | ✅ |
| `DELETE` | `/api/calendar/{id}` | Delete event | ✅ |
| `GET` | `/mail` | Mail digest page | ✅ |
| `POST` | `/api/mail/refresh` | Trigger IMAP refresh | ✅ |
| `GET` | `/voice` | Voice recording page | ✅ |
| `POST` | `/api/voice/transcribe` | Upload OGG → STT → LLM → return text+TTS | ✅ |
| `GET` | `/admin` | Admin dashboard | ✅ admin |
| `POST` | `/api/admin/users/{id}/approve` | Approve user | ✅ admin |
| `POST` | `/api/admin/llm/select` | Switch active LLM model | ✅ admin |
| `POST` | `/api/admin/voice_opts` | Toggle voice optimisation flag | ✅ admin |

### 17.5 Telegram↔Web Account Linking

Users with an existing Telegram account can link it to a new web account in one step.

**Implementation:**
- `generate_web_link_code(chat_id)` in `bot_state.py` — creates a 6-character uppercase alphanumeric code with a 15-minute TTL; stores in `_web_link_codes: dict[str, tuple[int, float]]`
- `validate_web_link_code(code)` — returns the `chat_id` if the code is valid and not expired; consumes the code (one-time use)
- Telegram callback `web_link` — triggered by Profile → **🔗 Link to Web** button;  calls `generate_web_link_code()` and sends the code to the user
- `POST /register` in `bot_web.py` — optional `link_code: str = Form("")` field; if provided, calls `validate_web_link_code()`, looks up the Telegram account's role, creates the web account with `status=active` and the corresponding role inherited — no admin approval required

**Linked account properties:**
- `username` and `password` are set from the web form
- `role` is inherited: if `chat_id in ADMIN_USERS` → `admin`; else `approved`
- `telegram_id` field in `accounts.json` references the Telegram chat ID
- Subsequent logins use web credentials only (JWT cookie)

### 17.6 Templates

| Template | Purpose |
|---|---|
| `base.html` | Root layout: PWA meta tags, HTMX script, Alpine.js, Pico CSS, nav bar |
| `login.html` | Login form with error display |
| `register.html` | Self-registration form |
| `dashboard.html` | Main dashboard: quick links to all sections |
| `chat.html` | Free-text LLM chat; message history HTMX-swapped |
| `_chat_messages.html` | Chat messages partial (returned by `POST /api/chat/send`) |
| `notes.html` | Notes list + inline create form |
| `_note_editor.html` | HTMX note editor partial (loaded on note open/edit) |
| `calendar.html` | Calendar event list + add form + NL query |
| `mail.html` | Digest text + Refresh button (HTMX) |
| `voice.html` | Voice orb UI: record button, waveform, TTS playback |
| `admin.html` | Admin: user list, approve/block, LLM switcher, voice opts |

### 17.5 PWA Support

`static/manifest.json` provides PWA metadata so the site can be added to the home screen:

| Field | Value |
|---|---|
| `name` | `"Pico Assistant"` |
| `short_name` | `"Pico"` |
| `theme_color` | `"#1e1e2e"` |
| `background_color` | `"#1e1e2e"` |
| `display` | `"standalone"` |
| `start_url` | `"/"` |
| `shortcuts` | Chat, Notes, Calendar, Voice |

### 17.6 Service File (`picoclaw-web.service`)

The service runs uvicorn with TLS. Key environment vars:
- `WEB_HOST` — bind address (default `0.0.0.0`)
- `WEB_PORT` — port (default `8080`)
- `SSL_KEYFILE` / `SSL_CERTFILE` — paths to TLS key + cert
- `JWT_SECRET` — signing secret for JWT tokens
- `ADMIN_USERS` — comma-separated chat IDs granted admin access in Web UI

---

## 18. Screen DSL & Multi-Channel Rendering (Phase 4)

### 18.1 Architecture Concept

The Screen DSL enables **write-once, render-anywhere** UI logic. A single set of action functions in `bot_actions.py` describes *what* to show; separate renderers in `render_telegram.py` and Jinja2 templates describe *how* to show it for each channel.

```
Action request (e.g. "show notes list")
    │
    ▼
bot_actions.py → action_note_list(ctx) → Screen(
    title="My Notes",
    widgets=[
        Card(title=note.title, subtitle=note.mtime),
        Button(label="➕ New Note", action="note_create"),
        Button(label="🔙 Menu", action="menu"),
    ]
)
    │
    ├── render_telegram.py → InlineKeyboardMarkup + send_message()
    │
    └── bot_web.py (Jinja2) → notes.html template renders the same Screen object
```

### 18.2 Screen DSL Dataclasses (`bot_ui.py`)

| Class | Purpose |
|---|---|
| `UserContext` | Caller identity: `chat_id`, `lang`, `is_admin` |
| `Screen` | Top-level container: `title`, `body`, `widgets`, `parse_mode` |
| `Button` | Single action button: `label`, `action` (callback key), `url` |
| `ButtonRow` | Horizontal group of `Button`s |
| `Card` | Information card: `title`, `subtitle`, `body` |
| `TextInput` | Prompt for text input (ForceReply in Telegram; `<input>` in Web) |
| `Toggle` | Boolean toggle: `label`, `key`, `value` |
| `AudioPlayer` | Playback widget: `url` or `ogg_bytes`, `caption` |
| `MarkdownBlock` | Pre-formatted Markdown content |
| `Spinner` | Loading indicator (shown while async op runs) |
| `Confirm` | Yes/No confirmation: `message`, `confirm_action`, `cancel_action` |
| `Redirect` | Immediately redirect to another action |

### 18.3 Action Handlers (`bot_actions.py`)

Each action handler receives a `UserContext` + optional parameters and returns a `Screen`. The Screen is then passed to the appropriate channel renderer.

| Function | Returns |
|---|---|
| `action_menu(ctx)` | Dashboard Screen with all menu buttons |
| `action_note_list(ctx)` | Notes list with per-note open/edit/delete buttons |
| `action_note_view(ctx, slug)` | Note detail: title, body (Markdown), action buttons |
| *(more handlers planned)* | *(calendar, chat, mail, admin)* |

### 18.4 Telegram Renderer (`render_telegram.py`)

`render_screen(chat_id, screen, bot)` converts a `Screen` to Telegram API calls:

| Widget type | Telegram output |
|---|---|
| `Card` | Formatted text block in message body |
| `Button` | `InlineKeyboardButton(text=label, callback_data=action)` |
| `ButtonRow` | One row in `InlineKeyboardMarkup` |
| `Toggle` | `InlineKeyboardButton` with ✅/⬜ prefix |
| `TextInput` | `bot.send_message(…, reply_markup=ForceReply())` |
| `AudioPlayer` | `bot.send_voice(…, ogg_bytes)` |
| `MarkdownBlock` | `bot.send_message(…, parse_mode="Markdown")` |
| `Spinner` | `bot.send_message("⏳ …")` — edited on completion |
| `Confirm` | Two-button keyboard: ✅ / ❌ |
| `Redirect` | Immediately calls the target action handler |

### 18.5 Web Renderer (Jinja2 + HTMX)

The Web UI renders the same `Screen` objects via Jinja2 templates. HTMX swaps allow partial page updates without full reloads:

| Widget type | HTML output |
|---|---|
| `Card` | `<article>` with header + body |
| `Button` | `<a hx-post="…" hx-target="#content">` |
| `ButtonRow` | `<div class="grid">` with button children |
| `Toggle` | `<input type="checkbox" hx-post="…">` |
| `TextInput` | `<input type="text">` with `hx-trigger="keyup[key=='Enter']"` |
| `AudioPlayer` | `<audio controls src="…">` |
| `MarkdownBlock` | Rendered via `marked.js` or server-side Markdown |
| `Spinner` | `<span aria-busy="true">` (Pico CSS spinner) |
| `Confirm` | Modal dialog with confirm/cancel buttons |

### 18.6 Adding a New Screen

To add a new screen visible in both Telegram and Web:

1. **Add action function in `bot_actions.py`:**
   ```python
   def action_my_feature(ctx: UserContext, **kwargs) -> Screen:
       return Screen(
           title="My Feature",
           widgets=[
               Card(title="Some info", body="Details here"),
               Button(label="🔙 Back", action="menu"),
           ]
       )
   ```

2. **Wire up in Telegram** (`telegram_menu_bot.py` callback dispatcher):
   ```python
   elif data == "my_feature":
       from render_telegram import render_screen
       from bot_actions import action_my_feature
       ctx = UserContext(chat_id=cid, lang=_lang(cid), is_admin=_is_admin(cid))
       render_screen(cid, action_my_feature(ctx), bot)
   ```

3. **Wire up in Web UI** (`bot_web.py`):
   ```python
   @app.get("/my-feature")
   async def my_feature_page(user=Depends(get_current_user)):
       ctx = UserContext(chat_id=user.chat_id, lang=user.lang, is_admin=user.is_admin)
       screen = action_my_feature(ctx)
       return templates.TemplateResponse("feature.html", {"screen": screen})
   ```

4. **Add Menu button** in `action_menu()` in `bot_actions.py`.

5. **Update `doc/bot-code-map.md`** callback key table.

