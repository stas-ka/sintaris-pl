# Taris Bot — User Guide

**@smartpico_bot** is a Telegram bot running on Raspberry Pi that provides AI chat, mail digest, system management, and voice interaction.

> **New users:** When you first send `/start`, your request is queued for admin approval. You will be notified once approved.

---

## Features — What Taris Can Do

Taris is a personal AI assistant with the following capabilities:

| Feature | Description |
|---|---|
| 🤖 **AI Chat** | Multi-turn conversation with LLM (Ollama/OpenAI). Supports Russian, German, English. |
| 📄 **Knowledge Base (RAG)** | Upload PDF, DOCX, TXT documents; the bot uses them as context when answering questions. Hybrid FTS5 + vector search. |
| 🗓 **Calendar** | Create, view, edit, delete events. Natural language input ("on Tuesday at 3pm"). Reminders. Console mode for conversational calendar management. |
| 📧 **Mail Digest** | Summarise Gmail inbox with AI. Configure mail credentials via the bot. |
| 📝 **Notes** | Create and manage personal Markdown notes. Voice dictation supported. |
| 🎤 **Voice Assistant** | Send voice messages — the bot transcribes (Vosk/faster-whisper) and responds with TTS (Piper). Hotword detection for hands-free use. |
| 👥 **Contacts** | Personal contact book. Search and manage contacts via the menu. |
| 🔐 **Access Control** | Admin, user, developer, and guest roles. Admin approves new users. |
| 🌐 **Web Interface** | Full web UI at `https://<host>:8080/` — chat, calendar, notes, documents, admin panel. |
| 🔊 **Voice Settings** | Toggle VAD, Whisper STT, parallel TTS, model warm-up per user. |
| 📊 **System Info** | CPU, memory, disk, uptime, service status. Admin can restart services. |
| 🌍 **Multilingual** | Full Russian, English, and German interface. Language auto-detected or manually set. |

---

## Variants

Taris runs in two flavours depending on the hardware:

| Variant | Hardware | Web UI | STT |
|---|---|---|---|
| **taris / PicoClaw** | Raspberry Pi (OpenClawPI / OpenClawPI2) | `https://agents.sintaris.net/picoassist/` | Vosk (offline) |
| **OpenClaw** | Linux workstation (TariStation2 / TariStation1) | `http://localhost:8080/` (TariStation2) · `http://SintAItion:8080/` (TariStation1) | faster-whisper |

- **PicoClaw** is the default variant. All Pi-specific instructions in this guide apply to PicoClaw.
- **OpenClaw** runs on a local Linux workstation, uses **faster-whisper** for STT instead of Vosk, and supports remote **Ollama** LLM inference in addition to cloud providers.

---

## Getting Started

1. Open the bot in Telegram and send `/start`.
2. The bot shows a welcome message and the main menu.
3. Tap a menu button to enter a mode. Press **🔙 Menu** at any time to go back.

---

## Menu Modes

### 📧 Mail Digest
Fetches and summarises your Gmail inbox for the **last 24 hours** using an AI model.

- Tap **📧 Почта / Mail Digest** from the main menu.
- The last generated digest is shown immediately.
- Tap **🔄 Refresh** to fetch a fresh digest right now.
- The daily digest also runs automatically at **19:00** every day.

---

### 💬 Chat (Free Chat)
Open-ended conversation with the AI. Ask anything — questions, explanations, translations, creative tasks.

- Type your message and send it.
- The AI replies in the same language you write in.
- Press `/menu` or tap **🔙 Menu** to exit.

---

### 🖥️ System Chat

> ⚠️ **System Chat has moved to the Admin Panel.** It is no longer in the main menu and is accessible only to **Admin** and **Developer** users.

Ask about the state of the system in plain language. The bot translates your request into a shell command, shows it for confirmation, then executes it.

**Example requests:**
- `show disk usage`
- `list running services`
- `CPU temperature`
- `last 20 lines of voice.log`
- `memory usage`
- `uptime`

See **Admin Panel → System → 🖥️ System Chat** below.

---

### 🎤 Voice
Voice messages work in **all bot modes** — no separate Voice Session button is needed.

**How to send a voice message:**
1. Open the bot in any mode (💬 **Chat**, 📝 **Notes**, 🗓 **Calendar**, etc.)
2. In the Telegram input bar, hold the **🎤 microphone** button to record.
3. Release to send the voice message.
4. The bot transcribes your speech offline (Vosk), sends the text to the AI, and replies with both text and a Piper TTS voice note.

> 🗣️ The STT model is selected automatically based on your Telegram language: Russian (`vosk-model-small-ru`) or German (`vosk-model-small-de`). For all other languages the Russian model is used.

---

### � Profile
View your account details and link your Telegram account to the web interface.

- Shows your name, username, Telegram chat ID, role, and registration date.
- If you have configured mail credentials, the registered email is shown (masked).
- Tap **🔗 Link to Web** to generate a 6-character one-time code (valid 15 minutes). Use it on the Web UI `/register` page to link your accounts.

---
### 📒 Contacts
Save and manage personal contacts accessible from both Telegram and the Web UI.

- **Add Contact** — enter name, phone number, email, and optional notes.
- **View** — browse your full contact list; tap a contact to see details.
- **Edit** — update any field of a saved contact.
- **Delete** — remove a contact after confirmation.
- **Search** — find contacts by name, phone number, or email address.

Contacts are also accessible from the **Web Interface** at `/contacts`.

---
### �🔐 Admin Panel
Full system management. Visible only to **Admin** users.

#### User Management
- **📋 Pending Requests** — list of users awaiting approval; badge shows pending count. Tap to **Approve** or **Block** each request.
- **👥 User List** — show all registered users and their status (approved / blocked).
- **➕ Add User** — grant a user access by entering their Telegram chat ID.
- **➖ Remove User** — revoke access by Telegram chat ID.

#### AI / LLM
- **🤖 Switch LLM** — Change the active language model. Set `LLM_PROVIDER` in `bot.env`:
  - **taris** (default) — OpenRouter via `taris agent`; access to 100+ models
  - **openai** — direct ChatGPT API; models: gpt-4o, gpt-4o-mini, o3-mini, o1, gpt-4.5-preview
  - **yandexgpt** — Yandex Cloud LLM API (`YANDEXGPT_API_KEY`)
  - **gemini** — Google Gemini API (`GEMINI_API_KEY`)
  - **anthropic** — Anthropic Claude API (`ANTHROPIC_API_KEY`)
  - **local** — fully offline llama.cpp inference via `taris-llm.service`; set `LLM_LOCAL_FALLBACK=true` for auto-fallback
- OpenAI API key is entered once and stored persistently.

#### Voice Pipeline
- **⚡ Voice Opts** — toggle optional STT/TTS speed optimisations:

| Toggle | Effect | Time saving |
|--------|--------|-------------|
| `silence_strip` | Removes leading/trailing silence before STT | −6 s |
| `low_sample_rate` | Decode at 8 kHz instead of 16 kHz — lighter Vosk | −7 s |
| `warm_piper` | Pre-loads TTS model at startup | −15 s cold start |
| `parallel_tts` | Text reply appears immediately while TTS generates | text in ~3 s |
| `user_audio_toggle` | Adds 🔇/🔊 button to every voice reply | skip TTS entirely |
| `tmpfs_model` | Copies Piper ONNX model to `/dev/shm` (RAM) | −13 s TTS load |
| `vad_prefilter` | WebRTC VAD strips non-speech frames before Vosk | −2–5 s |
| `whisper_stt` | Use whisper.cpp (ggml-base.bin) instead of Vosk | better WER, 2× slower |
| `piper_low_model` | Use `ru_RU-irina-low.onnx` (faster, lower quality) | TTS −10 s |
| `persistent_piper` | Keep Piper subprocess alive between TTS calls | −5–10 s warmup |

#### System
- **📜 Changelog** — browse full version history with release notes.
- **🖥️ System Chat** — ask about the state of the system in plain language. The bot translates the request into a shell command, shows it for confirmation, then runs it. Available to **Admin** and **Developer** users only (moved from main menu).
- **🔍 RAG / Knowledge Base** — enables/disables FTS5-based RAG for grounding LLM answers in uploaded documents. Upload documents via the Web UI (`POST /admin/rag/upload`); relevant chunks are automatically prepended to LLM prompts during chat.

> To find a user's chat ID, ask them to message [@userinfobot](https://t.me/userinfobot) on Telegram.

---

## 🌐 Web Interface

The Pico assistant is also accessible from any browser — no Telegram required.

### URL
| Instance | URL |
|---|---|
| Pi2 (primary) | `https://agents.sintaris.net/picoassist2/` |
| Pi1 | `https://agents.sintaris.net/picoassist/` |
| Local (on your network) | `https://<pi-ip>:8080/` |

> The Pi uses a self-signed TLS certificate for local access — accept the browser security warning.  
> Internet access (via VPS) uses a valid Let's Encrypt certificate.

### Login / Register
- Go to the URL above and click **Login**.
- If you don't have a web account yet, click **Register**.
  - With a **Telegram Link Code** (from Profile → 🔗 Link to Web): your web account inherits your Telegram role and is activated immediately.
  - Without a link code: account is created as pending and an admin must approve it.

### Available Features
| Section | What you can do |
|---|---|
| 💬 Chat | Free-text conversation with the AI |
| 📝 Notes | Create, edit, view, delete Markdown notes |
| 🗓 Calendar | View events, add events via natural language |
| � Contacts | View, add, edit, and delete contacts; search by name, phone, or email |
| �📧 Mail | View last mail digest, trigger refresh |
| 🎤 Voice | Record audio in browser → STT → LLM → TTS playback |
| ⚙️ Settings | Change language (Russian / English / German), change password |
| 🔐 Admin | (Admin role only) manage users, switch LLM, toggle voice opts |

### Installing as App (PWA)
The Web UI is a Progressive Web App. On mobile or desktop:
- **Chrome/Edge:** Open the URL → click the install icon in the address bar → **Install**
- **Safari (iOS):** Tap Share → **Add to Home Screen**

The installed app opens in standalone mode (no browser chrome) and supports quick-launch shortcuts for Chat, Notes, Calendar, and Voice.

---

## 🔍 Knowledge Base (RAG)

> 🧪 **BETA** — Available on both PicoClaw and OpenClaw variants.

Admins can upload documents to the bot's knowledge base. During chat, the most relevant text chunks are automatically prepended to the LLM prompt, grounding answers in your documents.

### Uploading Documents
- Open the Web UI and navigate to the **Admin** panel.
- Use the **Upload Document** form or send a `POST` request to `/admin/rag/upload`.
- Supported formats: plain text, Markdown, PDF (PyMuPDF + pdfminer fallback), DOCX.
- Documents are split into chunks (~512 characters) and indexed in **SQLite FTS5** full-text search.
- Duplicate documents (same SHA256 hash) are detected — you can replace or keep both.

### How RAG Works
1. User sends a message in 💬 Chat.
2. `bot_rag.classify_query()` routes the query: **simple** (skip RAG), **factual** (use RAG), **contextual** (RAG if docs available).
3. `bot_rag.retrieve_context()` selects search strategy based on hardware tier:
   - **FTS5_ONLY** — BM25 full-text search (low RAM)
   - **HYBRID** — BM25 + vector similarity + Reciprocal Rank Fusion (4–8 GB RAM)
   - **FULL** — hybrid + reranking (≥ 8 GB RAM)
4. Top-K chunks are prepended to the LLM prompt as `[KNOWLEDGE FROM USER DOCUMENTS]`.
5. LLM produces a grounded answer. Retrieval metrics logged to `rag_log`.

### Admin Controls (Telegram)
- Admin panel → **System** → **🔍 RAG / Knowledge Base** — toggle RAG on/off at runtime.
- Admin panel → **🔍 RAG** → **📊 Stats** — view retrieval latency, query type breakdown, top queries.
- The toggle writes/removes `~/.taris/rag_disabled` (flag file; presence = RAG off).

### Per-User RAG Settings
Each user can override the system defaults in **Profile → ⚙️ RAG Settings**:
- **Top-K** — number of chunks to inject (1–20, ± 1)
- **Chunk size** — maximum characters per chunk (200–4000, ± 200)
- Press **↩️ Reset** to restore system defaults.

### Configuration
| Constant | Default | Env var | Description |
|---|---|---|---|
| `RAG_ENABLED` | `true` | `RAG_ENABLED` | Master on/off switch |
| `RAG_TOP_K` | `3` | `RAG_TOP_K` | Max chunks injected per request (overridable per-user) |
| `RAG_CHUNK_SIZE` | `512` | `RAG_CHUNK_SIZE` | Characters per chunk when indexing |
| `RAG_FLAG_FILE` | `~/.taris/rag_disabled` | — | Flag file (presence = RAG off) |

---

## 🛠 Developer Menu

> Available to users with the **developer** role only.

The Developer Menu provides debugging and monitoring tools accessible via Telegram.

Access: Main Menu → **🛠 Dev**

| Button | What it does |
|---|---|
| 💬 Dev Chat | Enter developer chat mode (LLM with developer context) |
| 🔄 Restart Bot | Restart the Telegram service (requires confirmation) |
| 📋 View Log | Show the last 30 lines of `telegram_bot.log` |
| 🐛 Last Error | Show the most recent ERROR entry from the journal |
| 📂 File List | List `~/.taris/*.py` files with sizes and modification times |
| 🔒 Security Log | Show the last 20 security events (access denials, suspicious activity) |

Security events are automatically logged to the `security_events` database table whenever an access denial or suspicious action occurs.

---



| Command | Description |
|---------|-------------|
| `/start` | Show welcome message and main menu |
| `/menu` | Open main menu |
| `/status` | Show current mode and service status |
| `/help_guide` | Link to this user guide |

---

## User Roles

| Role | Access |
|------|--------|
| 👑 **Admin** | All modes + full Admin panel (users, LLM, voice opts, changelog) |
| � **Developer** | Admin rights + System Chat unrestricted + Dev menu (debug, restart, log view) |
| 👤 **Full** | Mail, Chat, System Chat, Voice, Notes, Calendar |
| 👥 **Guest** | Mail, Chat, Voice, Notes, Calendar |
| ⏳ **Pending** | Registration submitted, awaiting admin approval |
| 🚫 **Blocked** | Access denied by admin |

- **Admin** users are configured in `bot.env` (`ADMIN_USERS`).
- **Developer** users are configured in `bot.env` (`DEVELOPER_USERS`).
- **Full** users are configured in `bot.env` (`ALLOWED_USERS`).
- **Guest** users are approved by an admin via the Pending Requests flow.
- When an unknown user sends `/start`, they enter **Pending** state automatically.

---

## User Registration Flow

### Via Telegram

1. New user sends `/start`.
2. Bot replies: *"Your registration request has been submitted. Please wait for admin approval."*
3. Admin receives a notification with **Approve** and **Block** buttons.
4. On approval: user is added as Guest and notified. On block: user receives a declined message.
5. The **📋 Pending Requests** button on the admin panel shows a live count of waiting requests.

### Via Web Interface

1. Open `https://agents.sintaris.net/picoassist2/` (or `https://<pi-ip>:8080/`) and go to **Register**.
2. Enter a username and password.
3. **Optional — Link to Telegram account:**
   - In Telegram, open the Profile page (tap 👤 Profile from the main menu).
   - Tap **🔗 Link to Web** — the bot sends a 6-character code (valid 15 min).
   - Enter this code in the **Telegram Link Code** field on the register form.
   - Your web account is immediately activated with the same role as your Telegram account.
4. **Without a link code:** the account is created as pending and requires admin approval.

---

## Language

The bot automatically detects your Telegram language setting:
- 🇷🇺 Russian Telegram → interface in **Russian**
- 🇩🇪 German Telegram → interface in **German**
- 🌐 Any other language → interface in **English**

In the **Web Interface**, you can also manually change the language in ⚙️ Settings.

---

## Voice Requirements

Voice recognition and speech synthesis run **fully offline** on the Pi — no cloud API needed.

| Component | Details |
|-----------|---------|
| STT | Vosk `vosk-model-small-ru` (48 MB, Russian) + `vosk-model-small-de` (48 MB, German) |
| TTS | Piper `ru_RU-irina-medium` (66 MB, Russian) + `de_DE-thorsten-medium.onnx` (65 MB, German) |
| Audio HAT | Joy-IT RB-TalkingPI (for standalone voice assistant) |

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| Bot doesn't respond | Service stopped | Admin: `sudo systemctl restart taris-telegram` |
| Voice reply missing audio | Piper not installed | Run `setup_voice.sh` |
| Mail digest fails | Gmail credentials expired | Check IMAP App Password in `bot.env` |
| "Admins only" on System Chat | You are a guest user | Ask admin to upgrade your access |
| Voice not recognised | Spoke non-Russian | Use Russian (default STT model is Russian) |
| Button press does nothing | Markdown parse error | Update bot to latest version |
| Registration pending forever | Admin hasn't approved | Ask admin to check Pending Requests in admin panel |
| `/start` shows wrong menu | Role mismatch in `bot.env` | Check `ALLOWED_USERS` / `ADMIN_USERS` in `bot.env` |
| Web UI shows `502 Bad Gateway` | Pi tunnel disconnected | Check `systemctl status taris-tunnel` on the Pi |
| Web login fails (wrong password) | Wrong web credentials | Use Telegram linking to re-register with correct creds |
| Browser shows SSL certificate warning | Self-signed cert on local access | Accept / add exception; public URL has a valid cert |
| Link code expired | Codes are valid 15 minutes | Tap 🔗 Link to Web again to get a fresh code |
| Web registered but can't log in | Account pending approval | Ask admin to approve, or use a Telegram link code |
