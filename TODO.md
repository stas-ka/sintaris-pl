# Pico Bot — TODO & Roadmap

**Legend:** ✅ Done · 🔄 In progress · 🔲 Planned · 💡 Idea / future

**Completed:** Registration workflow (v2026.3.15) · Notes system · Per-user mail digest · Voice opts (silence_strip, VAD, whisper, piper_low, persistent_piper, tmpfs_model, warm_piper) · Smart calendar with NL input + reminders + morning briefing · Voice regression tests T01–T12 · Backup system · 3-layer prompt injection guard · Whisper hallucination guard (v2026.3.24)

---

## 0. Known Bugs 🐛

### 0.1 Profile menu button does nothing 🔲

**Observed (2026-03-08):** Tapping 👤 Profile sends no reply — silently fails.

**Likely cause:** `_handle_profile()` in `src/bot_handlers.py` does a deferred `from bot_mail_creds import _load_creds` inside the function body. If the import throws, `telebot` swallows the exception silently.

- [ ] Wrap deferred import + `_load_creds()` in `try/except` — degrade gracefully (show profile without email line, log warning)
- [ ] Verify: `journalctl -u picoclaw-telegram -n 50 | grep -i profile`

### 0.2 Rename bot / assistant — centralise all user-facing name references 🔲

**Affected locations:**
- `src/strings.json` — `welcome` (lines 10/140), `help_text*` ("Pico Bot"), `you_said`/`no_answer` ("picoclaw")
- `src/bot_config.py` — add `BOT_NAME = os.environ.get("BOT_NAME", "Pico")`
- `src/bot_access.py`, `src/bot_security.py` — hardcoded name in prompts/preamble

- [ ] Add `BOT_NAME=Pico` to `src/setup/bot.env.example`
- [ ] Add `BOT_NAME` constant to `bot_config.py`
- [ ] Replace hardcoded names in `strings.json` with `{bot_name}` placeholder; inject via `_t()` kwargs
- [ ] Grep for stragglers: `grep -rn "Pico\b\|picoclaw" src/ --include="*.py"`

---

## 1. Access & Security

### 1.1 Role-Based Access Control (RBAC) 🔲

| Role | Permissions |
|---|---|
| **Admin** | Configuration only — manage users, LLM providers, run system commands; cannot implement features |
| **Developer** | Extend and maintain the assistant — special dev menu, LLM-assisted coding, restart, deploy, fix issues |
| **User** | Chat, voice, notes, calendar, mail |
| **Guest** | Limited until admin approves |

- [ ] Implement role storage and enforcement
- [ ] Admin-only commands gated by role check
- [ ] Guest mode: only `/start` + "registration sent"

### 1.3 Developer Role & Dev Menu 🔲

**Concept:** Developer users get a dedicated 🛠 Developer menu that opens a specialised LLM chat session pre-primed with the bot's source code context and dev patterns. The LLM acts as a coding assistant — it can propose code changes, explain implementation options, and generate patches. The developer can then apply them and restart the bot, all from within Telegram.

**Admin vs Developer distinction:**
- **Admin** — operational control: add/remove users, switch LLM model, run a bash command, view logs. Cannot write new features.
- **Developer** — full dev access: chat with Pico to extend/fix/implement; restart service; view and apply code patches.

**Dev menu buttons:**
| Button | Action |
|---|---|
| 💬 Dev Chat | LLM chat with source context injected (bot_config, bot_handlers, dev-patterns.md) |
| 🔄 Restart Bot | `systemctl restart picoclaw-telegram` with confirmation gate |
| 📋 View Log | Last 30 lines of `telegram_bot.log` |
| 🐛 Last Error | Last ERROR/EXCEPTION line from journal |
| 📂 File List | List `~/.picoclaw/*.py` with sizes + mtimes |

- [ ] Add `DEVELOPER_USERS` set to `bot_config.py` (env var `DEVELOPER_USERS`)
- [ ] Add `_is_developer(chat_id)` to `bot_access.py`
- [ ] Add dev menu keyboard + `_handle_dev_menu()` to `bot_handlers.py`
- [ ] Dev Chat: inject system prompt with `dev-patterns.md` + key source file snippets
- [ ] Restart button: confirm gate → `systemctl restart picoclaw-telegram`
- [ ] View Log / Last Error: `_run_subprocess(["journalctl", "-u", "picoclaw-telegram", "-n", "30"])`
- [ ] File List: `os.listdir(PICOCLAW_DIR)` filtered to `*.py` with size + mtime
- [ ] Add 🛠 Developer button to main menu (visible to developer role only)

### 1.2 Central Security Layer — MicoGuard 🔲

- [ ] Role validation on every command/callback
- [ ] Security event logging (`security.log`)
- [ ] Configurable access rules (admin UI + config file)
- [ ] Runtime policy updates without restart

---

## 2. Conversation & Memory

### 2.1 Conversation Memory System 🔲

- [ ] Store per-user conversation history (sliding window, default 15 messages)
- [ ] Inject last N messages as context into LLM prompt
- [ ] Optional: persist across restarts (JSON / SQLite)

---

## 3. LLM Provider Support

### 3.1 Multi-LLM Provider Support 🔄

| Provider | Status |
|---|---|
| OpenRouter (via picoclaw) | ✅ Default, running |
| OpenAI (direct) + key management | ✅ Admin UI implemented |
| YandexGPT | 🔲 Planned |
| Gemini | 🔲 Planned |
| Anthropic | 🔲 Planned |
| Local LLM (llama.cpp) | 🔲 See §3.2 |

- [ ] Add `LLM_PROVIDER` env-var switch in `bot.env`
- [ ] Implement YandexGPT client with API key from `bot.env`

### 3.2 Local LLM — Offline Fallback 🔲

See: `doc/hardware-performance-analysis.md` §8.9

- Pi 3 B+: Qwen2-0.5B Q4 (~350 MB, ~1 tok/s) — emergency fallback only
- Pi 4 B (4 GB): Phi-3-mini Q4 (~2.5 GB, ~2 tok/s) — usable
- Pi 5 (8 GB): Llama-3.2-3B Q4 — good

- [ ] Build `llama.cpp` on Pi, store on USB SSD
- [ ] Download model to `/mnt/ssd/models/`
- [ ] Create `picoclaw-llm.service` systemd unit
- [ ] `try/except` fallback in `_ask_picoclaw()` → redirect to `localhost:8080`
- [ ] Label fallback responses with `⚠️ [local fallback]`

---

## 4. Content & Knowledge

### 4.1 Local RAG Knowledge Base 🔲

- [ ] Embed documents with `all-MiniLM-L6-v2`
- [ ] Vector similarity search → inject top-k context into LLM prompt
- [ ] Commands: `/rag_on`, `/rag_off`
- [ ] Storage: `~/.picoclaw/knowledge_base/` (documents + `embeddings.db`)

---

## 5. Voice Pipeline

### 5.1 Baseline (Pi 3 B+ with all opts OFF)

| Stage | Time | Status |
|---|---|---|
| OGG → PCM (ffmpeg) | ~1 s | ✅ |
| STT (Vosk small-ru) | **~15 s** | ❌ bottleneck |
| LLM (OpenRouter) | ~2 s | ✅ |
| TTS cold load (Piper medium, microSD) | **~15 s** | ❌ bottleneck |
| TTS inference (~600 chars) | **~80–95 s** | ❌ bottleneck |
| **Total** | **~115 s** | ❌ target: <15 s |

With `persistent_piper` + `tmpfs_model` + `piper_low_model` all ON: estimated **~20–25 s**.

### 5.2 TTS 110 s bottleneck 🔲

**Root cause:** Cold Piper ONNX load (~15 s) + ONNX inference at `TTS_MAX_CHARS=600` (~80–95 s) on Pi 3 B+.

| Priority | Fix | Where | Expected gain |
|---|---|---|---|
| 🔴 | Add `TTS_VOICE_MAX_CHARS = 300`; use for real-time path | `bot_config.py`, `_tts_to_ogg()` | TTS −50% |
| 🔴 | Document `persistent_piper` + `tmpfs_model` as recommended defaults | Admin panel help | −35 s |
| 🟡 | Enable `piper_low_model` | Voice Opts | −13 s |
| 🟢 | Auto-truncate at sentence boundary ≤ 300 chars | `_tts_to_ogg()` | smooth cuts |

- [ ] Add `TTS_VOICE_MAX_CHARS = 300` to `bot_config.py`
- [ ] Use it in `_tts_to_ogg()` when `_trim=True`
- [ ] Document recommended opt settings in bot help / admin panel

### 5.3 STT/TTS Detailed Improvements Backlog 🔲

**STT issues:**
- [ ] Vosk (180 MB) + Piper (150 MB) both active during voice reply — only ~310 MB headroom on Pi 3
- [ ] Whisper temp WAV written to SD-backed `/tmp` — move to `/dev/shm` (−0.5 s per call)
- [ ] Hallucination threshold (2 words/s) fixed — needs per-length tuning for short commands
- [ ] Add `STT_CONF_THRESHOLD` config constant for Vosk confidence strip (currently implicit)

**TTS issues:**
- [ ] "Read aloud" 1200-char chunks → ~180–200 s synthesis on Pi 3; needs progressive delivery
- [ ] OGG Opus bitrate 24 kbit/s hardcoded — expose as voice opt (16/24/32 kbit/s)
- [ ] Two `subprocess.run()` (Piper → ffmpeg) adds ~0.1 s; Popen pipe avoids this

**Measurement plan (add to `voice_timing_debug`):**
- [ ] ffmpeg OGG→PCM wall time (currently missing from debug output)
- [ ] Split Piper timer: model load time vs inference time
- [ ] Log char count going into Piper (correlate input length with inference time)
- [ ] Collect 10-run timing sample per STT/TTS path on Pi 3 B+

---

## 6. Infrastructure & Operations

### 6.1 Logging & Monitoring 🔲

- [ ] Structured log categories: `assistant.log`, `security.log`, `voice.log`
- [ ] Admin Telegram UI: view last N log lines per category
- [ ] Log rotation (`logrotate` config)

### 6.2 Host–Project Synchronization 🔲

- [ ] rsync-based sync script `src/` → Pi
- [ ] Git-based deployment hook

### 6.3 Deployment Workflow Enhancements 🔲

- [ ] `src/setup/notify_maintenance.py` — pre-restart user notification
- [ ] `NOTIFY_USERS_ON_UPDATE` flag in `bot.env` — ping approved users on startup after version bump
- [ ] Feature flags pattern in `bot.env` for gradual rollout

### 6.4 Hardware Upgrades 💡

- [ ] Pi 4 B upgrade — drops total latency ~115 s → ~15 s
- [ ] Pi 5 + NVMe upgrade — ~8 s total; full local LLM viable
- [ ] USB SSD — eliminates Piper model cold-start (15 s → 2 s), zero code changes

---

## 7. Demo Features for Client Presentations 🔲

> Goal: demonstrate the assistant live via Telegram without needing guest user credentials.

### Level A — LLM only, <2 h each

| # | Feature | Button | Implementation |
|---|---|---|---|
| A1 | Weather — current weather for any city | 🌤 Weather | `curl wttr.in/<city>?format=3` — no API key |
| A2 | Translator — translate to any language | 🌍 Translate | LLM prompt |
| A3 | Date counter — days until event, day of week | 📅 Date | LLM + `datetime` |
| A4 | Calculator / converter — "100 lbs to kg" | 🧮 Calc | LLM reasoning |
| A5 | Idea generator — gifts, article topics, names | 💡 Ideas | LLM prompt |
| A6 | Fun fact on any topic | 🎲 Fact | LLM prompt |
| A7 | Joke / riddle | 😄 Joke | LLM prompt |

- [ ] A1: 🌤 button → city input → `subprocess curl wttr.in` → text + voice
- [ ] A2: 🌍 button → user types "to English: Привет мир" → LLM translates
- [ ] A3–A7: quick menu buttons → LLM one-shot generation

### Level B — Small helper, 2–4 h each

| # | Feature | Button | Implementation |
|---|---|---|---|
| B1 | Web search — find + summarise | 🔍 Search | `duckduckgo_search` pip, LLM summarises top-3 |
| B2 | Pi system status — CPU, RAM, temp, uptime | 📡 System | `psutil` + `/sys/class/thermal` |
| B3 | Timer / reminder — "remind me in 15 min" | ⏰ Timer | `threading.Timer` → Telegram push |
| B4 | Text summariser — paste long text → summary | 📊 Summary | LLM prompt via ForceReply |
| B5 | Text corrector — spelling, style, punctuation | ✏️ Correct | LLM prompt |
| B6 | Note formatter — draft → structured doc | 📋 Format | LLM prompt |
| B7 | Password generator — strong password by params | 🔐 Password | Python `secrets` |
| B8 | News headlines — top-5 from open RSS | 📰 News | `feedparser` pip, RSS lenta.ru / BBC-RU |

- [ ] B1: `pip install duckduckgo_search`; LLM summarises top-3 results
- [ ] B2: `psutil.cpu_percent()`, `psutil.virtual_memory()`, thermal zone → reply + voice
- [ ] B3: `threading.Timer(N*60, callback)` per user; `_pending_timers: dict[int, Timer]`
- [ ] B4–B6: ForceReply input → LLM prompt → formatted output
- [ ] B7: `secrets.choice` over character classes → show in `code` block
- [ ] B8: `feedparser.parse(RSS_URL)` → top-5 headlines → LLM summary

### Level C — Impressive, 4–8 h each

| # | Feature | Button | Implementation |
|---|---|---|---|
| C1 | Image analysis — user sends photo → description | 🖼 Photo | Multimodal LLM via OpenRouter (gpt-4o) |
| C2 | Interview trainer — practice Q&A by topic | 🎓 Interview | LLM dialog mode + voice |
| C3 | QR code generator — text/URL → image | 📷 QR | `qrcode` pip → PNG → `bot.send_photo()` |
| C4 | Mini quiz — 5 questions + inline answer buttons | 🏆 Quiz | LLM generates `{question, options[4], correct}` → InlineKeyboard |

- [ ] C1: photo handler → base64 → LLM vision prompt → text + voice
- [ ] C2: `_user_mode='interview'`; LLM asks questions and scores answers
- [ ] C3: `pip install qrcode pillow` → `qrcode.make(text)` → BytesIO → `send_photo()`
- [ ] C4: LLM generates JSON → `InlineKeyboardMarkup` with 4 options → score tracking

### Demo priority order

**Minimum (1 day):** A1 + A2 + B2 + B3 + C3 → shows voice, text, offline status, push notifications, multimedia
**Extended (2–3 days):** above + B1 + B4 + C1 + C4
**Flagship (already implemented):** Smart calendar — user says "remind me tomorrow at 10 for a team meeting", bot replies by voice "saved", sends reminder + morning briefing
