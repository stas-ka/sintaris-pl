# Pico Bot — TODO & Roadmap

**Legend:** ✅ Done · 🔄 In progress · 🔲 Planned · 💡 Idea / future

---

## 0. Known Bugs 🐛

### 0.1 Profile menu button does nothing 🔲

**Observed (2026-03-08):** Tapping 👤 Profile sends no reply — the button silently fails.

**Code location:** `src/bot_handlers.py` `_handle_profile()`, dispatched in `telegram_menu_bot.py` line ~269.

**Likely cause:** The handler does a deferred import `from bot_mail_creds import _load_creds` inside
the function body. If `bot_mail_creds` raises an import-time error (e.g. missing dependency or module
path issue on the Pi), the entire function throws and `telebot` swallows the exception silently.

**Fix steps:**
- [ ] Wrap the deferred import + `_load_creds()` call in a `try/except` so a failed mail-creds load
      degrades gracefully (show profile without email line, not silence)
- [ ] Add fallback: if import fails, set `email_line = _t(chat_id, "profile_no_email")` and log warning
- [ ] Verify on Pi: `journalctl -u picoclaw-telegram -n 50 | grep -i profile` to see actual exception

### 0.2 Rename bot / assistant — centralise all user-facing name references 🔲

**Request (2026-03-08):** The assistant is currently named "Pico" in user-facing messages and
"picoclaw" in voice/LLM status strings. The name should be configurable via a single env var
(`BOT_NAME`) rather than scattered hardcoded strings.

**Affected locations:**
- `src/strings.json` — `welcome` (RU line 10, EN line 140), `help_text` / `help_text_admin` /
  `help_text_guest` contain "Pico Bot" · `you_said` + `no_answer` contain "picoclaw"
- `src/bot_config.py` — add `BOT_NAME = os.environ.get("BOT_NAME", "Pico")` constant
- `src/bot_access.py` — any hardcoded name in `_ask_picoclaw()` output labels or prompts
- `src/bot_security.py` — `SECURITY_PREAMBLE` may reference bot identity
- `TODO.md` header — "Pico Bot — TODO & Roadmap"

**Recommended approach:**
- [ ] Add `BOT_NAME=Pico` to `src/setup/bot.env.example` and document in `doc/architecture.md`
- [ ] Add `BOT_NAME = os.environ.get("BOT_NAME", "Pico")` to `bot_config.py`
- [ ] Replace hardcoded name strings in `strings.json` with `{bot_name}` placeholder;
      inject `bot_name=BOT_NAME` via `_t()` kwargs at send time
- [ ] Grep for stragglers: `grep -rn "Pico\b\|picoclaw" src/ --include="*.py"` after refactor

---

## 1. Access & Security

### 1.1 Telegram User Registration Workflow ✅

✅ **Implemented** (v2026.3.15-rc1). Unknown users enter a registration flow on `/start`; admins approve/block via inline buttons; pending count badge shown on admin panel button.

### 1.2 Role-Based Access Control (RBAC) 🔲

| Role | Permissions |
|---|---|
| **Admin** | Full system control — users, environment, LLM providers, backups, security policy |
| **Developer** | Develop/deploy skills, test features, debug tools; bot restart; cannot change security policy |
| **User** | Chat with assistant, voice assistant, personal notes, knowledge base |
| **Guest** | Limited access until admin approves registration |

- [ ] Implement role storage and enforcement in bot
- [ ] Admin-only commands gated by role check
- [ ] Developer: restart command available alongside Admin
- [ ] Guest mode: only `/start` and a "registration sent" message

### 1.3 Central Security Layer — MicoGuard 🔲

Centralised policy enforcement module sitting between users and all bot actions.

- [ ] Role validation on every command/callback
- [ ] Security event logging (`security.log`)
- [ ] Configurable access rules (admin UI + config file)
- [ ] Runtime policy updates without restart
- [ ] Architecture: `User → MicoGuard → LLM / Tools / System`

---

## 2. Conversation & Memory

### 2.1 Conversation Memory System 🔲

- [ ] Store per-user conversation history
- [ ] Sliding window: configurable `max_memory_messages` (default 15)
- [ ] Inject last N messages as context into LLM prompt
- [ ] Optional: persist memory across bot restarts (JSON / SQLite)
- [ ] Optional: session-based (in-memory only) mode as lighter alternative

---

## 3. LLM Provider Support

### 3.1 Multi-LLM Provider Support 🔄

| Provider | Status |
|---|---|
| OpenRouter (via picoclaw) | ✅ Default, running |
| YandexGPT | 🔲 Planned — add all model variants + API key config |
| OpenAI (direct) | 🔲 Planned |
| Gemini | 🔲 Planned |
| Anthropic | 🔲 Planned |
| Local LLM (llama.cpp) | 🔲 See §3.2 |

- [ ] Add `LLM_PROVIDER` env-var switch in `bot.env`
- [ ] Implement YandexGPT client with API key from `bot.env`
- [ ] Admin UI: show active provider + allow switching

### 3.2 Local LLM — Offline Fallback 🔲

Run a local `llama.cpp` model on the Pi as fallback when OpenRouter is unavailable.

- See full analysis: `doc/hardware-performance-analysis.md` §8.9
- Pi 3 B+: Qwen2-0.5B Q4 (~350 MB, ~1 tok/s) — emergency fallback only (~90 s/query)
- Pi 4 B (4 GB): Phi-3-mini Q4 (~2.5 GB, ~2 tok/s) — usable fallback
- Pi 5 (8 GB): Llama-3.2-3B Q4 (~2 GB, ~5 tok/s) — good fallback

Tasks:
- [ ] Build `llama.cpp` on target host, store on USB SSD
- [ ] Download appropriate model to `/mnt/ssd/models/`
- [ ] Create `picoclaw-llm.service` systemd unit
- [ ] Implement `_call_picoclaw()` with `try/except` + local HTTP redirect (`localhost:8080`)
- [ ] Label fallback responses with `⚠️ [local fallback]`

---

## 4. Content & Knowledge

### 4.1 Markdown Notes System ✅ Implemented (v2026.3.19)

✅ **Implemented**: create / list / open (Markdown rendered) / edit (ForceReply in-place) / raw text view / read aloud via Piper TTS / delete. Voice input during note creation and edit flows is routed into the note state machine instead of the LLM.

### 4.2 Per-User Mail Digest ✅ Implemented

✅ **Implemented**: Each user configures their own mailbox credentials (Gmail / Yandex / Mail.ru / Custom IMAP). GDPR (EU Reg. 2016/679 Art. 6(1)(a)) + 152-FZ consent gate shown before credential entry; credentials stored at `~/.picoclaw/mail_creds/<chat_id>.json` (chmod 600, device-only); digest fetched inline via `imaplib` + LLM summarisation; per-user cache at `<chat_id>_last_digest.txt`; full credential lifecycle: setup wizard → test connection → view → delete (= consent withdrawal). Module: `src/bot_mail_creds.py`.

### 4.3 Local RAG Knowledge Base 🔲

Lightweight offline-capable knowledge base for personal/technical documents.

```
/knowledge_base/
  documents/
  embeddings.db
```

- [ ] Embed documents with a small embedding model (e.g. `all-MiniLM-L6-v2`)
- [ ] Vector similarity search on user query
- [ ] Inject retrieved context into LLM prompt
- [ ] Commands: `/rag_on`, `/rag_off`
- [ ] Query flow: `question → vector search → context → LLM answer`
- [ ] Example use cases: personal notes, local manuals, family info, technical docs

---

## 5. Voice Pipeline Optimization

### 5.1 Measured baseline (Pi 3 B+, March 2026)

| Stage | Time | Status |
|---|---|---|
| Download OGG from Telegram | ~0 s | ✅ fine |
| OGG → 16 kHz PCM (ffmpeg) | ~1 s | ✅ fine |
| Speech-to-Text (Vosk `vosk-model-small-ru`) | **~15 s** | ❌ bottleneck |
| LLM (picoclaw → OpenRouter) | ~2 s | ✅ fine |
| TTS (Piper `ru_RU-irina-medium`) | **~40 s** | ❌ bottleneck |
| **Total** | **~58 s** | ❌ target: <15 s |

### 5.2 Active voice optimisations ✅

| Opt | Bot menu toggle | Impact |
|---|---|---|
| Silence strip (ffmpeg `silenceremove`) | `silence_strip` | ✅ STT −6 s |
| 8 kHz sample rate for Vosk | `low_sample_rate` | ✅ STT −7 s |
| Pre-warm Piper ONNX cache | `warm_piper` | ✅ TTS cold-start −15 s |
| Parallel TTS thread (text-first UX) | `parallel_tts` | ✅ text visible in ~3 s |
| Per-user audio 🔊/🔇 toggle | `user_audio_toggle` | ✅ skip TTS entirely |
| Piper model pinned to RAM (`/dev/shm`) | `tmpfs_model` | ✅ TTS load −13 s |
| ffmpeg highpass + dynaudnorm pre-filter | always on | ✅ STT quality |
| Vosk confidence filtering (`[?word]`) | always on | ✅ STT accuracy |
| `TTS_MAX_CHARS = 600` | constant | ✅ balanced audio length |

### 5.3 Advanced voice opts ✅ Implemented (v2026.3.19)

All items added as optional voice opts toggles (all default OFF, existing behaviour unchanged):
- **`vad_prefilter`** — webrtcvad noise gate before Vosk STT
- **`whisper_stt`** — whisper.cpp base model instead of Vosk (needs binary + `~/.picoclaw/ggml-base.bin`); includes hallucination guard that discards sparse output (< 2 words/s) and falls back to Vosk
- **`piper_low_model`** — ru\_RU-irina-low.onnx for faster TTS (needs model download)
- **`persistent_piper`** — keepalive Piper subprocess holds ONNX in page cache

### 5.4 Voice regression test suite ✅ Implemented (v2026.3.19)

✅ **Implemented**: T01–T13 automated test runner (`src/tests/test_voice_regression.py`) covering model files, OGG decode, VAD filtering, Vosk STT + WER, TTS, Piper synthesis, ffmpeg encode, and regression comparison against a saved baseline. Run on Pi via `plink`. Mandatory before committing voice-related changes.

### 5.5 Effort vs. impact summary

| # | Change | Effort | Expected saving | Cumulative total |
|---|---|---|---|---|
| ✅ 1 | Silence strip | Low | STT −6 s | 52 s |
| ✅ 2 | TTS_MAX_CHARS tuning | Low | TTS varies | — |
| ✅ 3 | 8 kHz sample rate | Low | STT −7 s | 45 s |
| ✅ 4 | warm_piper + tmpfs_model | Low | TTS cold −15 s | 30 s |
| ✅ 5 | Parallel TTS thread | Medium | text in ~3 s | text fast |
| ✅ 6 | VAD pre-filter (opt) | Low | STT −3 s | 27 s |
| ✅ 7 | whisper.cpp STT (opt) | Medium | STT −11 s | ~16 s |
| ✅ 8 | Piper low model (opt) | Low | TTS −13 s | ~14 s |
| ✅ 9 | Persistent Piper Popen (opt) | High | TTS −20 s | ~10 s |

### 5.6 Known Bottleneck — TTS 110 s for Short Responses 🔲

**Observed (2026-03-08):** voice_timing_debug shows `TTS 110s` for a 23-second audio reply — even for
responses that are not particularly long. This is reproduced with all `warm_piper` / `tmpfs_model` /
`persistent_piper` opts **OFF** (factory defaults).

**Root cause breakdown:**
- Cold Piper ONNX model load from microSD: ~15 s
- ONNX inference for ~600 chars (TTS_MAX_CHARS ceiling): ~80–95 s on Pi 3 B+ Cortex-A53

**Recommended fixes (in order of priority):**

| Priority | Fix | Opt toggle | Expected TTS |
|---|---|---|---|
| 🔴 High | Enable `persistent_piper` (keepalive Popen, ONNX stays in page cache) | Admin → Voice Opts → `persistent_piper` | ~25–35 s |
| 🔴 High | Enable `tmpfs_model` (copy ONNX to `/dev/shm` RAM disk) | Admin → Voice Opts → `tmpfs_model` | cold load: 0 s |
| 🟡 Med | Enable `piper_low_model` (smaller model, ~half inference time) | Admin → Voice Opts → `piper_low_model` | −13 s |
| 🟡 Med | Reduce `TTS_MAX_CHARS` below 600 for voice replies | `bot_config.py` constant | proportional |
| 🟢 Low | Add cap for voice replies only: truncate at sentence boundary ≤ 300 chars | `_tts_to_ogg()` optional param | −50% inference |

- [ ] Turn on `persistent_piper` + `tmpfs_model` opts by default for admin, document in bot help
- [ ] Investigate adding a shorter `TTS_VOICE_MAX_CHARS = 300` constant separate from the read-aloud
      `TTS_CHUNK_CHARS` so real-time voice replies are capped at ~30 s speech (≈ 300 chars)
- [ ] Consider auto-truncating at last sentence boundary within the char limit (avoid mid-sentence cuts)

### 5.7 Voice Pipeline — Detailed Analysis & Current Implementation 🔲

**Purpose:** Full audit of the STT and TTS subsystems to identify architectural weak points,
confirm what is actually measured on Pi 3 B+, and produce a prioritised optimization backlog
that goes beyond the surface-level timing captured in §5.6.

---

#### 5.7.1 STT — Current Implementation (`bot_voice.py` + `bot_config.py`)

**Primary path: Vosk** (`vosk-model-small-ru-0.22`, 48 MB)

| Property | Value | Source |
|---|---|---|
| Sample rate | `VOICE_SAMPLE_RATE = 16000` Hz | `bot_config.py:108` |
| Chunk size | `VOICE_CHUNK_SIZE = 4000` frames (250 ms at 16 kHz) | `bot_config.py:109` |
| Silence timeout | `VOICE_SILENCE_TIMEOUT = 4.0` s | `bot_config.py:110` |
| Session hard cap | `VOICE_MAX_DURATION = 30.0` s | `bot_config.py:111` |
| Confidence filter | strips `[?word]` → `word` in output | `bot_voice.py` |
| Model loading | Lazy singleton on first voice message; ~180 MB RAM | `_get_vosk_model()` |
| KaldiRecognizer | `SetWords(True)` for word-level timestamps | --|

**Pre-processing pipeline (before Vosk):**

```
Telegram OGG Opus
  → ffmpeg: -ar 16000 -ac 1 -f s16le         (OGG → S16LE 16 kHz mono)
           + silenceremove filter (if silence_strip)
           + -ar 8000 (if low_sample_rate)
  → [VAD filter]  (if vad_prefilter opt)       ← webrtcvad aggressiveness=2, 30 ms frames
  → Vosk KaldiRecognizer
```

**ffmpeg silence_strip filter** (opt `silence_strip`):
```
silenceremove=start_periods=1:start_duration=0.1:start_threshold=-50dB
             :stop_periods=-1:stop_duration=0.1:stop_threshold=-50dB
```
Combined with `highpass=f=200,dynaudnorm` — normalises volume before VAD/Vosk.

**Optional path: whisper.cpp** (opt `whisper_stt=true`, `ggml-base.bin`, 142 MB)

| Property | Value | Source |
|---|---|---|
| Invocation | subprocess with `--threads 4 --suppress-blank --entropy-thold 1.8 --no-speech-thold 0.6` | `_stt_whisper()` |
| Temp file | WAV written to `/tmp/*.wav`, deleted after | `_stt_whisper()` |
| Hallucination guard | Discards if `word_count < duration_s * 2.0` (min 2 words) | `bot_voice.py:~285` |
| Fallback | Returns `None` → caller falls back to Vosk | `_handle_voice_message()` |
| WER (Russian) | ~18% vs Vosk ~25% | `doc/architecture.md §5.4` |
| Latency on Pi 3 | ~30–35 s for 5 s audio | measured |

**Known STT issues:**
- [ ] Vosk model loaded into 180 MB RAM — competes with Piper 150 MB during voice reply synthesis
- [ ] No streaming decode to Telegram bot (full audio must arrive before STT starts)
- [ ] `low_sample_rate` opt (8 kHz) saves ~7 s STT but degrades WER noticeably on Russian fricatives
- [ ] Whisper temp WAV file written to SD-backed `/tmp` — ~0.5 s overhead per call; should use tmpfs
- [ ] Hallucination threshold (2 words/s) is fixed — short commands ("да", "нет") always pass
      regardless of content quality; needs per-length tuning

---

#### 5.7.2 TTS — Current Implementation (`_tts_to_ogg()` in `bot_voice.py`)

**Engine: Piper TTS** (`ru_RU-irina-medium.onnx`, 66 MB ONNX Runtime)

**Pipeline:**

```
text
  → _escape_tts()           strip emoji, Markdown, ANSI codes
  → trim to TTS_MAX_CHARS = 600 chars at sentence boundary (real-time path)
  → subprocess.run(piper --model <path> --output-raw)
        stdin: UTF-8 text
        stdout: raw S16LE PCM at 22050 Hz mono
  → subprocess.run(ffmpeg -f s16le -ar 22050 -ac 1
                   -c:a libopus -b:a 24k -f ogg)
        stdin: raw PCM
        stdout: OGG Opus bytes
  → bot.send_voice(BytesIO(ogg_bytes))
```

**Two separate subprocess.run() calls** (not a pipe) — deliberately avoids the classic
`piper.stdout open → ffmpeg.stdin blocks on EOF` deadlock.

**Model selection priority chain** (`_piper_model_path()`):

| Priority | Condition | Model | Note |
|---|---|---|---|
| 1 | `tmpfs_model=true` AND `/dev/shm/piper/...onnx` exists | `/dev/shm/piper/...onnx` | ~10× faster reads |
| 2 | `piper_low_model=true` AND `ru_RU-irina-low.onnx` exists | low model | ~half inference time |
| 3 | default | `ru_RU-irina-medium.onnx` | microSD, ~15 s cold load |

**Char cap constants:**

| Constant | Value | Used by | Speech duration (Pi 3) |
|---|---|---|---|
| `TTS_MAX_CHARS` | 600 | real-time voice replies (`_trim=True`) | ~25 s |
| `TTS_CHUNK_CHARS` | 1200 | "Read aloud" note/digest chunks (`_trim=False`) | ~55 s |

**Text splitting for "Read aloud"** (`_split_for_tts()`):
Prefers sentence boundaries `. ! ? ; \n` then whitespace fallback, then hard cut.
Split result is delivered as N sequential `send_voice()` calls, each labelled `(1/N)`.

**Keepalive option** (`persistent_piper`):
Launches a long-running `piper --model ... --output-raw` process via `Popen` with stdin held open.
This keeps the ONNX pages in the kernel page cache between calls.  Actual synthesis still uses fresh
`subprocess.run()` calls — the keepalive process is never sent input.

**Known TTS issues:**
- [ ] `subprocess.run()` cold-loads ONNX from microSD every call when no warm opts are active → 15 s overhead
- [ ] No `TTS_VOICE_MAX_CHARS` constant separate from `TTS_MAX_CHARS` — both real-time chat and voice
      replies use the same 600-char cap (see §5.6)
- [ ] `_trim=True` path clips at TTS_MAX_CHARS but "Read aloud" still synthesises full 1200-char chunks;
      for the longest chunks (~1200 chars) inference time on Pi 3 is ~180–200 s
- [ ] ffmpeg subprocess started fresh per TTS call — ~0.1 s overhead, avoidable with stdin pipe
- [ ] OGG Opus target bitrate 24 kbit/s fixed — no voice-quality slider exposed to user
- [ ] No SSML support — punctuation and emphasis are passed as plain text to Piper

---

#### 5.7.3 Measurement Plan — Items to Instrument

Before optimizing further, add per-stage timing to `voice_timing_debug` output:

| Stage | What to measure | How |
|---|---|---|
| ffmpeg OGG→PCM | wall time (currently missing from debug) | `t0 = time.monotonic()` bracket |
| VAD filter | retained-frame % + wall time | already logged at DEBUG level |
| Vosk decode | wall time, word count, confidence stats | `time.monotonic()` bracket |
| Whisper decode | wall time, word count, hallucination rate | `time.monotonic()` bracket |
| LLM call | wall time + token count estimate | already in timing debug |
| `_escape_tts()` + char truncation | output char count, truncation applied? | add log line |
| Piper subprocess start → first PCM byte | wall time (model load portion) | `time.monotonic()` bracket |
| Piper inference (first byte to last byte) | wall time | `time.monotonic()` bracket |
| ffmpeg PCM→OGG | wall time | `time.monotonic()` bracket |
| OGG file size | bytes → kbit/s calculation | `len(ogg_bytes)` |

- [ ] Add all missing timing probes to `_handle_voice_message()` under `if VOICE_TIMING_DEBUG`
- [ ] Log char count going _into_ Piper so we can correlate input length with inference time
- [ ] Collect 10-run timing sample on Pi 3 B+ for each STT/TTS path and populate a baseline table

---

#### 5.7.4 Actionable Improvements Backlog

| Priority | Change | Module | Expected gain |
|---|---|---|---|
| 🔴 | Add `TTS_VOICE_MAX_CHARS = 300` constant; use for real-time voice path | `bot_config.py`, `_tts_to_ogg()` | TTS −50% for real-time |
| 🔴 | Write Whisper temp WAV to `/dev/shm` (tmpfs) not `/tmp` | `_stt_whisper()` | STT −0.5 s I/O |
| 🟡 | Unified timing debug: add missing stages (ffmpeg, Piper start vs inference) | `bot_voice.py` | Diagnosability |
| 🟡 | Tune Whisper hallucination threshold per audio-length bracket | `_stt_whisper()` | Accuracy on short commands |
| 🟡 | Add `STT_CONF_THRESHOLD` config constant for Vosk confidence strip (currently implicit) | `bot_config.py` | Tuneability |
| 🟢 | Replace double subprocess.run with Popen pipe (piper→ffmpeg) | `_tts_to_ogg()` | TTS −0.1–0.3 s |
| 🟢 | Expose OGG bitrate as voice opt (16/24/32 kbit/s) — lower = faster ffmpeg | `bot_config.py`, Voice Opts | Audio size −33% |
| 🟢 | Re-use ffmpeg stdin pipe in persistent mode (like `persistent_piper`) | `bot_voice.py` | TTS −0.1 s |

---

## 6. Infrastructure & Operations

### 6.1 Logging & Monitoring 🔲

- [ ] Structured log categories: `assistant.log`, `security.log`, `voice.log`
- [ ] Admin Telegram UI: view last N log lines per category
- [ ] Admin command: `/logs [category] [n]`
- [ ] Optional: log rotation (`logrotate` config)

### 6.2 Host–Project Synchronization 🔲

Synchronize between local development machine and target Raspberry Pi.

- [ ] rsync-based sync script for `src/` → Pi
- [ ] Git-based deployment hook
- [ ] Archive export for offline transfer
- Covers: source code, scripts, configs, env templates, service files

### 6.3 Backup System ✅

✅ **Implemented**. Scripts: `src/setup/backup_image.sh` (dd|zstd + SHA-256), `src/setup/install.sh` (fresh-install bootstrap), `src/setup/update.sh` (incremental update), `src/setup/backup_nextcloud.sh` (WebDAV upload/download/prune). Dependency manifests in `deploy/`.

#### 6.3 Backup Policy

| Location | What to store |
|---|---|
| **GitHub** | Source code, deploy scripts, config templates, documentation |
| **Pi (host)** | Runtime data, live configs, secrets, logs, databases |
| **Nextcloud** | Full image backups, recovery bundles, log archives |

Rules:
- Never commit secrets to GitHub
- Only reproducible, sanitized artifacts in version control
- Use dated versioned filenames: `mico-recovery-bundle-2026-03-07.tar.gz`

### 6.4 Update & Deployment Workflow

- [x] `doc/update_strategy.md` created — covers SOP, rollback, parallel deploy, service restart timing
- [ ] `src/setup/notify_maintenance.py` — pre-restart user notification script (see §3.1 of update_strategy.md)
- [ ] `NOTIFY_USERS_ON_UPDATE` flag in `bot.env` — ping approved users on bot startup after version bump
- [ ] Feature flags pattern in `bot.env` for gradual rollout

---

- [ ] Multi-user knowledge graph
- [ ] Long-term AI memory (persistent across sessions, per user)
- [ ] Smart home integration (Home Assistant, MQTT)
- [ ] Multi-device access (same user on multiple Telegram accounts or devices)
- [ ] USB SSD as local LLM host — full setup (see `doc/hardware-performance-analysis.md` §8)
- [ ] Pi 4 B upgrade — drops total latency from ~58 s to ~15 s
- [ ] Pi 5 + NVMe upgrade — ~8 s total latency, full local LLM viable

---

## 7. Demo Features for Client Presentations 🔲

> **Цель:** функции для демонстрации возможностей системы потенциальному клиенту.  
> **Критерии:** быстро реализуются, не требуют персональных данных (credentials) гостевого пользователя, впечатляюще смотрятся в живой демонстрации через Telegram.  
> **Основа:** анализ ТЗ 1.2 / stage3 проекта KIM-ASSISTANT + существующий стек (LLM, голос, кнопочное меню).

### 7.1 Уровень A — Только LLM, время разработки < 2 часов каждая

| # | Функция | Кнопка меню | Реализация |
|---|---|---|---|
| A1 | **Погода** — текущая погода в любом городе | 🌤 Погода | `curl wttr.in/<city>?format=3` — без API-ключа |
| A2 | **Переводчик** — перевод текста на любой язык | 🌍 Перевод | LLM prompt ("переведи на {язык}: {текст}") |
| A3 | **Счётчик дней / дата** — сколько дней до события, день недели | 🗓 Дата | LLM + `datetime` Python |
| A4 | **Калькулятор / конвертер** — "100 фунтов в кг", "евро в рубли по курсу" | 🧮 Считать | LLM reasoning |
| A5 | **Генератор идей** — "5 идей подарка", "тема для статьи", "название для продукта" | 💡 Идеи | LLM prompt |
| A6 | **Факт дня / интересный факт по теме** — "расскажи факт о космосе" | 🎲 Факт | LLM prompt |
| A7 | **Шутка / загадка** — случайная по теме или на русском языке | 😄 Юмор | LLM prompt |

- [ ] A1: кнопка 🌤 Погода → режим ввода города → `subprocess curl wttr.in` → ответ текстом + голосом
- [ ] A2: кнопка 🌍 Перевод → пользователь вводит "на английский: Привет мир" → LLM переводит
- [ ] A3: кнопка 🗓 Дата → "сколько дней до 31 декабря" → LLM + Python datetime → ответ
- [ ] A4: кнопка 🧮 → пользователь вводит выражение → LLM / python eval (безопасный) → ответ
- [ ] A5–A7: отдельные быстрые кнопки в меню → LLM one-shot генерация

### 7.2 Уровень B — Небольшой helper, время разработки 2–4 часа каждая

| # | Функция | Кнопка меню | Реализация |
|---|---|---|---|
| B1 | **Веб-поиск** — найти ответ в интернете и кратко пересказать | 🔍 Поиск | `duckduckgo_search` pip (нет API-ключа), LLM суммаризует JSON |
| B2 | **Статус системы Pi** — CPU, RAM, температура, uptime | 📡 Система | `psutil` + `uptime`, без credentials |
| B3 | **Таймер / напоминание** — "напомни через 15 минут" | ⏰ Таймер | `threading.Timer`, push в Telegram |
| B4 | **Суммаризатор текста** — вставить длинный текст → краткое резюме | 📊 Резюме | LLM prompt, вход через ForceReply |
| B5 | **Корректор текста** — орфография, стиль, пунктуация | ✏️ Коррект | LLM prompt |
| B6 | **Форматировщик заметок** — "набросок → структурированный документ" | 📋 Формат | LLM prompt |
| B7 | **Генератор паролей** — надёжный пароль по параметрам | 🔐 Пароль | Python `secrets` + `string`, без внешнего API |
| B8 | **Новостные заголовки** — топ-5 новостей из открытого RSS | 📰 Новости | `feedparser` pip, RSS lenta.ru / BBC|RU |

- [ ] B1: веб-поиск — `pip install duckduckgo_search`; режим "поиск"; LLM суммаризует top-3 результата
- [ ] B2: кнопка 📡 Система → `psutil.cpu_percent()`, `psutil.virtual_memory()`, `/sys/class/thermal` → форматированный ответ + голос
- [ ] B3: таймер → пользователь пишет "15" (минут) → `threading.Timer(900, callback)` → бот шлёт push через N минут (хранить в `_pending_timers: dict[int, Timer]`)
- [ ] B4–B6: режим ввода через ForceReply, LLM-промпт, форматированный вывод
- [ ] B7: `secrets.choice` по символьным классам → показать пароль в `code` блоке
- [ ] B8: `feedparser.parse(RSS_URL)` → топ-5 заголовков + ссылки → краткий пересказ через LLM
- [ ] B9: см. ниже — умный календарь (отдельная секция)

### 7.2.1 Умный календарь с голосовым / чат добавлением 🗓 ✅ Implemented

> **Изюминка:** никаких форм и дат-пикеров. Пользователь говорит или пишет обычным языком —
> ассистент сам разбирает дату, время и действие. Утром бот голосом зачитывает план дня.

✅ **Implemented** (v2026.3.19): CRUD `~/.picoclaw/calendar/<chat_id>.json`; LLM natural-language date/time parser; `threading.Timer` voice+text reminder 15 min before; 08:00 morning voice briefing; 🗓 Calendar menu with countdown + delete; voice input in calendar mode routed to event parser. Module: `src/bot_calendar.py`.

#### Пользовательский сценарий

```
[Голос/текст]  "напомни мне послезавтра в девять утра позвонить Сергею"
[Бот]          ✅ Записал: Пт 13 марта, 09:00 — позвонить Сергею
               (осталось 2 дня 14 ч)

[Утром в 08:00] 🎙 голосовое сообщение:
               "Доброе утро! На сегодня у тебя 2 события:
                в 11:00 встреча с командой,
                в 15:30 звонок клиенту."

[Голос/текст]  "что у меня сегодня?"
[Бот]          [список событий дня с обратным отсчётом]

[Голос/текст]  "отмени встречу с командой"
[Бот]          ✅ Встреча с командой в 11:00 отменена.
```

#### Изюминки — что делает это демо эффектным

| Изюминка | Описание |
|---|---|
| 🗣 **Свободный язык ввода** | "на следующей неделе в среду" / "через три часа" / "13-го в половину четвёртого" → LLM → ISO datetime |
| 🔔 **Умные напоминания** | пуш в Telegram + голосовое сообщение за 15 мин до события |
| ☀️ **Утренний брифинг** | голосовой дайджест событий дня в заданное время (по умолчанию 08:00) |
| ⏱ **Обратный отсчёт** | при просмотре всегда показывает "через X ч Y мин" или "через 2 дня" |
| ❌ **Отмена голосом** | "отмени встречу" → LLM находит ближайшее совпадение, просит подтверждение |

#### Реализация (без сторонних credentials)

```
Хранение:  ~/.picoclaw/calendar/<chat_id>.json   ← один JSON-файл на пользователя
           [{id, title, dt_iso, remind_before_min, reminded}]

Парсинг:   _ask_picoclaw(f"Извлеки дату/время и описание из: '{text}'. Ответь JSON:
           {{\"dt\": \"2026-03-13T09:00\", \"title\": \"позвонить Сергею\"}}")
           → json.loads(response)

Напомин.:  threading.Timer до каждого события; при перезапуске — пересчёт из файла
           за 15 мин: bot.send_voice() (Piper TTS) + bot.send_message()

Брифинг:   фоновый поток с ежедневным срабатыванием в заданный час
           → Piper TTS → bot.send_voice()

Режим:     _user_mode='calendar' → любой текст/голос попадает в парсер событий
```

✅ B9a–B9f: **Implemented** — see §7.2.1 above.

### 7.3 Уровень C — Эффектные, время разработки 4–8 часов

| # | Функция | Кнопка меню | Реализация |
|---|---|---|---|
| C1 | **Анализ изображения** — пользователь присылает фото → описание + факты | 🖼 Фото | Multimodal LLM через OpenRouter (gpt-4o / claude-3) |
| C2 | **Тренажёр интервью** — вопросы на собеседование по теме | 🎓 Интервью | LLM, диалоговый режим, поддержка голоса |
| C3 | **QR-код** — сгенерировать QR из текста/ссылки → прислать картинкой | 📷 QR-код | `qrcode` pip → PNG → `bot.send_photo()` |
| C4 | **Мини-викторина** — 5 вопросов по теме с проверкой ответов | 🏆 Викторина | LLM генерирует вопросы + ответы, inline-кнопки варианты |

- [ ] C1: `voice_handler` / `photo_handler` → скачать файл → base64 → LLM vision prompt → текст + голос
- [ ] C2: диалоговый режим `_user_mode='interview'`; LLM задаёт вопросы, оценивает ответы пользователя
- [ ] C3: `pip install qrcode pillow` → `qrcode.make(text)` → BytesIO → `bot.send_photo()`
- [ ] C4: LLM генерирует JSON `{question, options[4], correct_index}` → `InlineKeyboardMarkup` с вариантами → проверка + счёт

### 7.4 Порядок реализации для демо-сценария

Минимальный демо-набор (1 день работы): **A1 (погода) + A2 (перевод) + B2 (статус Pi) + B3 (таймер) + C3 (QR-код)**  
→ Показывает: голос, текст, работу без интернета (статус), push-уведомления, мультимедиа.

Расширенный демо-набор (2–3 дня): всё выше + **B1 (поиск) + B4 (суммаризатор) + B9 (умный календарь) + C1 (фото) + C4 (викторина)**

**Флагманское демо (3–4 дня, максимальный wow-эффект):** умный календарь B9 с голосовым вводом — это самая наглядная функция: клиент говорит "напомни мне завтра в 10 встречу с командой", бот отвечает голосом "записал", а утром сам звонит с брифингом.
