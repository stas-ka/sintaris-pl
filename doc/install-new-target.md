# Installing Taris Bot on a New Target

**Last updated:** 2026-03-27  
**Applies to:**
- **PicoClaw variant** — OpenClawPI, OpenClawPI2, or any new Raspberry Pi (aarch64)
- **OpenClaw variant** — Laptop / AI PC running Ubuntu 22.04+ (x86_64), alongside `sintaris-openclaw`

Use this guide for a complete fresh deployment from a bare OS image.
For incremental updates to an existing host, see `doc/update_strategy.md`.
For integration architecture (PicoClaw ↔ OpenClaw), see `doc/architecture/openclaw-integration.md`.

---

## Part A — PicoClaw: Raspberry Pi Installation

---

## Hardware Requirements

| Item | Minimum | Notes |
|------|---------|-------|
| Board | Raspberry Pi 3 B+ | arm64/aarch64 architecture |
| RAM | 1 GB | Pi 4 B (2–4 GB) strongly recommended for voice |
| Storage | 16 GB SD card | USB SSD optional but recommended for Piper model |
| Network | Ethernet or Wi-Fi | Internet required for initial setup |
| USB | Any USB port | For RB-TalkingPI HAT / USB mic (voice, optional) |

---

## Prerequisites (do once before running these steps)

1. Flash **Raspberry Pi OS Bookworm Lite (64-bit)** to the SD card
2. Enable SSH and set hostname in Raspberry Pi Imager (or via `raspi-config`)
3. Create user `stas` with a password
4. Boot, get the IP, verify SSH: `ssh stas@<hostname>`
5. Add the hostname to your local `hosts` file on Windows:
   ```
   C:\Windows\System32\drivers\etc\hosts
   192.168.178.XXX  OpenClawPI3
   ```

---

## Step 1 — System Packages

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y \
  git curl wget \
  python3 python3-pip \
  ffmpeg \
  portaudio19-dev \
  espeak-ng \
  openssl \
  zstd unzip \
  cron
```

> `openssl` is required for SSL certificate generation.  
> `portaudio19-dev` + `espeak-ng` are required for voice features.

---

## Step 2 — Python Packages

```bash
pip3 install --break-system-packages \
  pyTelegramBotAPI \
  vosk \
  sounddevice \
  google-api-python-client \
  google-auth-httplib2 \
  google-auth-oauthlib \
  fastapi \
  "uvicorn[standard]" \
  jinja2 \
  bcrypt \
  PyJWT \
  python-multipart \
  requests
```

Or from the requirements file (after deploying source files in Step 5):
```bash
pip3 install --break-system-packages -r /home/stas/.taris/deploy/requirements.txt
```

---

## Step 3 — taris Go Binary

```bash
wget -q https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_aarch64.deb \
     -O /tmp/taris_aarch64.deb
sudo dpkg -i /tmp/taris_aarch64.deb
taris version   # should print v0.2.0 or newer
```

---

## Step 4 — Piper TTS Engine

```bash
PIPER_VERSION="1.2.0"
wget -q "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_aarch64.tar.gz" \
     -O /tmp/piper.tar.gz
sudo mkdir -p /usr/local/share/piper
sudo tar -xzf /tmp/piper.tar.gz -C /usr/local/share/piper --strip-components=1
rm /tmp/piper.tar.gz

# Wrapper script
sudo tee /usr/local/bin/piper << 'EOF'
#!/bin/bash
exec /usr/local/share/piper/piper "$@"
EOF
sudo chmod +x /usr/local/bin/piper
piper --version   # should print version
```

---

## Step 5 — Deploy Source Files from Windows

Run these commands from the **Windows developer machine** (from `D:\Projects\workspace\taris`).

Replace `HOSTPWD`, `NEWTARGET`, and `NEWPWD` with your target values.

```bat
set NEWTARGET=OpenClawPI3
set NEWPWD=<password>

rem Create working directory
plink -pw "%NEWPWD%" -batch stas@%NEWTARGET% "mkdir -p ~/.taris/ssl ~/.taris/notes ~/.taris/calendar ~/.taris/mail_creds ~/.taris/error_protocols"

rem Deploy bot modules
pscp -pw "%NEWPWD%" src\bot_config.py src\bot_state.py src\bot_instance.py stas@%NEWTARGET%:/home/stas/.taris/
pscp -pw "%NEWPWD%" src\bot_security.py src\bot_access.py src\bot_users.py stas@%NEWTARGET%:/home/stas/.taris/
pscp -pw "%NEWPWD%" src\bot_voice.py src\bot_calendar.py src\bot_admin.py stas@%NEWTARGET%:/home/stas/.taris/
pscp -pw "%NEWPWD%" src\bot_handlers.py src\bot_mail_creds.py src\bot_email.py stas@%NEWTARGET%:/home/stas/.taris/
pscp -pw "%NEWPWD%" src\bot_error_protocol.py src\bot_llm.py src\bot_web.py stas@%NEWTARGET%:/home/stas/.taris/
pscp -pw "%NEWPWD%" src\telegram_menu_bot.py src\gmail_digest.py src\voice_assistant.py stas@%NEWTARGET%:/home/stas/.taris/
pscp -pw "%NEWPWD%" src\strings.json src\release_notes.json stas@%NEWTARGET%:/home/stas/.taris/

rem Deploy Web UI templates and static assets
plink -pw "%NEWPWD%" -batch stas@%NEWTARGET% "mkdir -p ~/.taris/templates ~/.taris/static"
pscp -pw "%NEWPWD%" src\templates\*.html stas@%NEWTARGET%:/home/stas/.taris/templates/
pscp -pw "%NEWPWD%" src\static\style.css stas@%NEWTARGET%:/home/stas/.taris/static/
```

---

## Step 6 — Voice Models

```bash
# Russian Vosk STT model (48 MB)
wget -q https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip -O /tmp/vosk.zip
unzip -q /tmp/vosk.zip -d ~/.taris/
mv ~/.taris/vosk-model-small-ru-0.22 ~/.taris/vosk-model-small-ru 2>/dev/null || true
rm /tmp/vosk.zip

# Piper Russian voice — Irina medium (66 MB)
wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx" \
     -O ~/.taris/ru_RU-irina-medium.onnx
wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json" \
     -O ~/.taris/ru_RU-irina-medium.onnx.json

# Optional: Piper Russian voice — Irina low (faster TTS)
wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/low/ru_RU-irina-low.onnx" \
     -O ~/.taris/ru_RU-irina-low.onnx
wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/low/ru_RU-irina-low.onnx.json" \
     -O ~/.taris/ru_RU-irina-low.onnx.json
```

---

## Step 7 — Secrets: `bot.env`

```bash
nano ~/.taris/bot.env
```

Minimal content required:
```bash
BOT_TOKEN=<from BotFather>
ALLOWED_USER=<your Telegram chat ID>
ADMIN_USERS=<comma-separated admin chat IDs>
OPENROUTER_API_KEY=<from openrouter.ai>
```

Full template reference: `src/setup/bot.env.example`

```bash
chmod 600 ~/.taris/bot.env
```

---

## Step 8 — taris Config

```bash
taris onboard   # initialises ~/.taris/config.json
```

Add an LLM model to `~/.taris/config.json`:
```json
{
  "model_list": [
    {
      "model_name": "openrouter-auto",
      "model": "openrouter/auto",
      "api_key": "<your_openrouter_api_key>"
    }
  ],
  "agents": {
    "defaults": {
      "model": "openrouter-auto"
    }
  }
}
```

Test:
```bash
taris agent -m "Hello"
```

---

## Step 9 — SSL Certificate (for HTTPS Web UI)

Deploy and run the SSL setup script from Windows:

```bat
pscp -pw "%NEWPWD%" src\setup\setup_ssl.sh stas@%NEWTARGET%:/tmp/setup_ssl.sh
plink -pw "%NEWPWD%" -batch stas@%NEWTARGET% "bash /tmp/setup_ssl.sh"
```

This creates `~/.taris/ssl/key.pem` and `~/.taris/ssl/cert.pem` with proper SAN entries.

### Download cert to Windows for trust store import

```bat
pscp -pw "%NEWPWD%" stas@%NEWTARGET%:/home/stas/.taris/ssl/cert.pem %NEWTARGET%.crt
```

### Import cert as Trusted Root CA (Windows) — requires Admin

Open **Command Prompt as Administrator** and run:
```bat
certutil -addstore -f "Root" "D:\Projects\workspace\taris\%NEWTARGET%.crt"
```

Then restart Chrome/Edge completely (close all windows). The browser will no longer show "Not Secure" for `https://<NEWTARGET>:8080`.

> **Note:** Each developer machine needs to import the cert once per target.  
> The cert is valid for 10 years. Re-run `setup_ssl.sh` if the Pi's IP changes.

---

## Step 10 — Systemd Services

Deploy service files from Windows:

```bat
rem Telegram bot service (required on all targets)
pscp -pw "%NEWPWD%" src\services\taris-telegram.service stas@%NEWTARGET%:/tmp/taris-telegram.service
plink -pw "%NEWPWD%" -batch stas@%NEWTARGET% "echo %NEWPWD% | sudo -S cp /tmp/taris-telegram.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable taris-telegram"

rem Web UI service (required for browser access)
pscp -pw "%NEWPWD%" src\services\taris-web.service stas@%NEWTARGET%:/tmp/taris-web.service
plink -pw "%NEWPWD%" -batch stas@%NEWTARGET% "echo %NEWPWD% | sudo -S cp /tmp/taris-web.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable taris-web"

rem Voice service (optional — requires RB-TalkingPI HAT)
rem pscp -pw "%NEWPWD%" src\services\taris-voice.service stas@%NEWTARGET%:/tmp/taris-voice.service
rem plink -pw "%NEWPWD%" -batch stas@%NEWTARGET% "echo %NEWPWD% | sudo -S cp /tmp/taris-voice.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable taris-voice"
```

---

## Step 11 — Start Services and Verify

```bat
rem Start Telegram bot
plink -pw "%NEWPWD%" -batch stas@%NEWTARGET% "echo %NEWPWD% | sudo -S systemctl start taris-telegram && sleep 3 && journalctl -u taris-telegram -n 10 --no-pager"

rem Start Web UI
plink -pw "%NEWPWD%" -batch stas@%NEWTARGET% "echo %NEWPWD% | sudo -S systemctl start taris-web && sleep 3 && journalctl -u taris-web -n 10 --no-pager"
```

Expected Telegram bot log:
```
[INFO] Version      : 2026.X.Y
[INFO] Polling Telegram…
```

Expected Web UI log:
```
Started server process
Uvicorn running on https://0.0.0.0:8080
```

Open in browser: `https://<NEWTARGET>:8080`

---

## Step 12 — Optional: Gmail Digest Cron

```bash
(crontab -l 2>/dev/null; echo "0 19 * * * python3 /home/stas/.taris/gmail_digest.py >> /home/stas/.taris/digest.log 2>&1") | crontab -
```

---

## Step 13 — Optional: Tailscale (Remote Access)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Follow the auth URL printed in the terminal
tailscale ip -4   # note the assigned IP
```

After setup, access the Pi from anywhere: `plink -pw "..." -batch stas@<TAILSCALE_IP> "..."`

---

## Quick Checklist

| # | Step | Verify command |
|---|------|----------------|
| 1 | System packages | `ffmpeg -version && python3 --version` |
| 2 | Python packages | `python3 -c "import telebot, vosk, fastapi; print('ok')"` |
| 3 | taris binary | `taris version` |
| 4 | Piper TTS | `echo test \| piper --model ~/.taris/ru_RU-irina-medium.onnx --output-raw > /dev/null && echo OK` |
| 5 | Source files | `ls ~/.taris/telegram_menu_bot.py strings.json` |
| 6 | Voice models | `ls ~/.taris/vosk-model-small-ru/ ~/.taris/ru_RU-irina-medium.onnx` |
| 7 | Secrets | `cat ~/.taris/bot.env \| grep BOT_TOKEN` |
| 8 | taris config | `taris status` |
| 9 | SSL cert | `ls ~/.taris/ssl/cert.pem ~/.taris/ssl/key.pem` |
| 10 | Services enabled | `systemctl is-enabled taris-telegram taris-web` |
| 11 | Services running | `systemctl status taris-telegram taris-web --no-pager` |
| 12 | Web UI HTTPS | Open `https://<HOST>:8080` in browser — should show login page, no cert warning |

---

## Installed File Locations

| File / Directory | Purpose |
|---|---|
| `~/.taris/` | All bot source files and runtime data |
| `~/.taris/bot.env` | Secrets (BOT_TOKEN, ALLOWED_USER, etc.) — chmod 600 |
| `~/.taris/config.json` | taris LLM config (model_list, agents) |
| `~/.taris/ssl/cert.pem` | TLS certificate (auto-detected by bot_web.py) |
| `~/.taris/ssl/key.pem` | TLS private key |
| `~/.taris/templates/` | Jinja2 HTML templates for Web UI |
| `~/.taris/static/` | CSS/JS assets for Web UI |
| `~/.taris/vosk-model-small-ru/` | Vosk Russian STT model (48 MB) |
| `~/.taris/ru_RU-irina-medium.onnx` | Piper Russian TTS voice (66 MB) |
| `/usr/bin/picoclaw` | taris Go binary |
| `/usr/local/bin/piper` | Piper TTS wrapper script |
| `/usr/local/share/piper/` | Piper binary and bundled libs |
| `/etc/systemd/system/taris-*.service` | Systemd service units |

---

## Differences Between Pi1 (OpenClawPI) and Pi2 (OpenClawPI2)

| Feature | OpenClawPI (Pi1) | OpenClawPI2 (Pi2) |
|---------|-----------------|------------------|
| Telegram bot | ✅ | ✅ |
| Web UI (`taris-web.service`) | ❌ not installed | ✅ running |
| Voice service | ❌ not installed | — |
| taris gateway | ✅ | — |
| Tailscale IP | `$DEV_TAILSCALE_IP` (see `.env`) | — |
| LAN IP | `$PI1_LAN_IP` (see `.env`) | `$PI2_LAN_IP` (see `.env`) |

---

## User Data: Storage, Backup & Migration

### Data map — what lives where

| Data | Storage | Path |
|------|---------|------|
| Users + roles | SQLite | `taris.db` → `users` table |
| Voice settings | SQLite | `taris.db` → `voice_opts`, `global_voice_opts` |
| Calendar events | SQLite | `taris.db` → `calendar_events` |
| Notes index + content | SQLite + Files | `taris.db` → `notes_index`; files at `notes/<chat_id>/*.md` |
| Contacts | SQLite | `taris.db` → `contacts` (no files) |
| Mail credentials | SQLite + Files | `taris.db` → `mail_creds`; legacy JSON in `mail_creds/` |
| Chat history | SQLite | `taris.db` → `chat_history` |
| Conversation memory | SQLite | `taris.db` → `conversation_summaries`, `user_prefs` |
| RAG documents (metadata) | SQLite | `taris.db` → `documents`, `doc_chunks` |
| RAG documents (files) | Files | `docs/<chat_id>/*.pdf/.docx/.txt/.md` |
| Uploaded knowledge base | Files | `docs/<chat_id>/` |
| Screen DSL configs | Files | `screens/*.yaml` |
| Error protocols | Files | `error_protocols/` |
| Secrets | File | `bot.env` |
| System settings | File + SQLite | `config.json`, `taris.db` → `system_settings` |

### Before every deploy: backup user data

```bash
# TariStation2 (local)
TS=$(date +%Y%m%d_%H%M%S)
VER=$(grep BOT_VERSION ~/.taris/core/bot_config.py | head -1 | cut -d'"' -f2)
BNAME="taris_backup_TariStation2_v${VER}_${TS}"
tar czf ~/projects/sintaris-pl/backup/snapshots/${BNAME}.tar.gz \
  -C ~/.taris \
  --exclude='vosk-model-*' --exclude='*.onnx' --exclude='ggml-*.bin' --exclude='*/__pycache__' \
  taris.db bot.env config.json *.json \
  calendar/ mail_creds/ notes/ error_protocols/ docs/ screens/ \
  2>/dev/null && echo "BACKUP_OK"
```

> **CRITICAL:** `docs/` must be included — it holds uploaded PDF/DOCX files for the RAG knowledge base.
> Without backing up `docs/`, document metadata in the DB exists but the files are gone.

### After fresh install / restore: run migration

```bash
# After restoring a backup to a new machine or fresh OS:
cd ~/.taris
python3 setup/migrate_to_db.py

# To skip document re-indexing (faster, e.g. schema-only migration):
python3 setup/migrate_to_db.py --skip-docs

# Dry-run preview:
python3 setup/migrate_to_db.py --dry-run
```

Migration handles:
- `users.json` / `registrations.json` → `users` table
- `voice_opts.json` → `global_voice_opts` table
- `calendar/<user>.json` → `calendar_events` table
- `notes/<user>/*.md` → `notes_index` table
- `mail_creds/<user>.json` → `mail_creds` table
- `docs/<chat_id>/<file>` → `documents` + `doc_chunks` tables *(re-indexes on restore)*

---

## Updating an Existing Target

For incremental code updates (no fresh OS needed), see the deployment workflow in `.github/copilot-instructions.md`:

```bat
rem Deploy changed files
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py stas@OpenClawPI:/home/stas/.taris/
pscp -pw "%HOSTPWD%" src\strings.json src\release_notes.json stas@OpenClawPI:/home/stas/.taris/

rem Restart service
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S systemctl restart taris-telegram && sleep 3 && journalctl -u taris-telegram -n 8 --no-pager"
```

---

## Part B — OpenClaw: Laptop / AI PC Installation

This section covers installing Taris on a laptop or AI PC (x86_64) as the **OpenClaw variant**, running alongside the `sintaris-openclaw` AI gateway.

**Prerequisites:**
- Ubuntu 22.04 LTS or Debian 12 (x86_64)
- Python 3.11+, git, ffmpeg installed
- [sintaris-openclaw](https://github.com/stas-ka/sintaris-openclaw) installed (see `sintaris-openclaw/docs/install.md`)
- Internet connection for initial downloads

---

### B.1 — Clone the repo and install Python dependencies

```bash
# Clone sintaris-pl (already done if using sintaris-openclaw-local-deploy)
git clone https://github.com/stas-ka/sintaris-pl ~/projects/sintaris-pl
cd ~/projects/sintaris-pl

# Checkout the taris-openclaw branch (has OpenClaw integration)
git checkout taris-openclaw

# Install Python packages
pip3 install -r deploy/requirements.txt
```

---

### B.2 — Set up the local deploy directory

`sintaris-openclaw-local-deploy` provides a symlink-based launcher so you can run
Taris locally without copying files. Source changes in `sintaris-pl/src/` are
reflected immediately.

```bash
# Create the local deploy directory
mkdir -p ~/projects/sintaris-openclaw-local-deploy
cd ~/projects/sintaris-openclaw-local-deploy

# Create symlinks into sintaris-pl/src/
for mod in core features security telegram ui screens; do
  ln -sf ~/projects/sintaris-pl/src/$mod ./$mod
done
ln -sf ~/projects/sintaris-pl/src/telegram_menu_bot.py ./telegram_menu_bot.py
ln -sf ~/projects/sintaris-pl/src/bot_web.py ./bot_web.py
ln -sf ~/projects/sintaris-pl/src/strings.json ./strings.json
ln -sf ~/projects/sintaris-pl/src/prompts.json ./prompts.json
ln -sf ~/projects/sintaris-pl/src/release_notes.json ./release_notes.json
ln -sf ~/projects/sintaris-pl/src/web ./web
```

---

### B.3 — Configure credentials

```bash
mkdir -p ~/projects/sintaris-openclaw-local-deploy/.taris

# Generate a secure API token
TARIS_API_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Create bot.env — choose the LLM section matching your hardware (see comments)
cat > ~/projects/sintaris-openclaw-local-deploy/.taris/bot.env << EOF
BOT_TOKEN=<your_telegram_bot_token>
ALLOWED_USERS=<your_telegram_user_id>
ADMIN_USERS=<your_telegram_user_id>
DEVICE_VARIANT=openclaw
TARIS_API_TOKEN=$TARIS_API_TOKEN

# ── LLM: choose one block ──────────────────────────────────────────────────
# Option A — Local Ollama with AMD/NVIDIA GPU (recommended for SintAItion / GPU machines)
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:14b
OLLAMA_THINK=false
OLLAMA_MIN_TIMEOUT=90
LLM_LOCAL_FALLBACK=1
# OPENAI_API_KEY=sk-...         # set if you want OpenAI as fallback

# Option B — OpenAI (for CPU-only machines without Ollama)
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...
# LLM_LOCAL_FALLBACK=1          # retry on local Ollama if OpenAI times out

# ── STT: choose device ─────────────────────────────────────────────────────
STT_PROVIDER=faster_whisper
# CPU:      FASTER_WHISPER_DEVICE=cpu  FASTER_WHISPER_COMPUTE=int8   MODEL=base
# AMD GPU:  FASTER_WHISPER_DEVICE=cuda FASTER_WHISPER_COMPUTE=float16 MODEL=small
#           + add HSA_OVERRIDE_GFX_VERSION=11.0.3 to systemd service (see B.5-GPU)
FASTER_WHISPER_MODEL=base
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE=int8
EOF

chmod 600 ~/projects/sintaris-openclaw-local-deploy/.taris/bot.env
echo "API token: $TARIS_API_TOKEN"
```

> **`TARIS_API_TOKEN`**: This token authorises `skill-taris` (in sintaris-openclaw) to call
> Taris `/api/*` endpoints. Copy it to the skill's API keys file:
> ```bash
> echo "<token>" > ~/.openclaw/skills/skill-taris/api-keys.txt
> chmod 600 ~/.openclaw/skills/skill-taris/api-keys.txt
> ```

> ⚠️ **LLM provider matters for performance.** See `doc/install-new-target.md §C.1` and
> `errors/perf-sintaition-2026-03-31.md` for measured latency differences between
> `openai` and `ollama` on GPU hardware.

---

### B.4 — Create run scripts

Create `~/projects/sintaris-openclaw-local-deploy/run_telegram.sh`:
```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export TARIS_HOME="$(pwd)/.taris"
export PYTHONPATH="$(pwd)"
python3 telegram_menu_bot.py
```

Create `~/projects/sintaris-openclaw-local-deploy/run_web.sh`:
```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export TARIS_HOME="$(pwd)/.taris"
export PYTHONPATH="$(pwd)"
export WEB_ONLY=1
uvicorn bot_web:app --host 0.0.0.0 --port 8080 --reload
```

Create `~/projects/sintaris-openclaw-local-deploy/run_all.sh`:
```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export TARIS_HOME="$(pwd)/.taris"
export PYTHONPATH="$(pwd)"

./run_telegram.sh &
echo $! > .taris/telegram.pid

WEB_ONLY=1 uvicorn bot_web:app --host 0.0.0.0 --port 8080 &
echo $! > .taris/web.pid

echo "Taris running. Stop with: kill \$(cat .taris/telegram.pid) \$(cat .taris/web.pid)"
```

```bash
chmod +x run_telegram.sh run_web.sh run_all.sh
```

---

### B.5 — Install the voice stack (x86_64)

Run the OpenClaw voice setup script from `sintaris-pl`:

```bash
bash ~/projects/sintaris-pl/src/setup/setup_voice_openclaw.sh
```

This installs:
- Vosk x86_64 model (`vosk-model-small-ru`) into `~/.taris/`
- Piper binary + Russian TTS model (`ru_RU-irina-medium.onnx`)
- faster-whisper Python package (CPU by default)

#### B.5-GPU — AMD GPU (ROCm) acceleration for STT

If the machine has an AMD GPU with ROCm support (Radeon 680M/780M/890M, gfx1100+):

```bash
# 1. Verify ROCm is available (Ollama GPU install sets this up)
ls /usr/local/lib/ollama/rocm/libamdhip64.so 2>/dev/null && echo "ROCm libs present"

# 2. Add STT GPU settings to bot.env
cat >> ~/.taris/bot.env << 'EOF'
FASTER_WHISPER_DEVICE=cuda
FASTER_WHISPER_COMPUTE=float16
FASTER_WHISPER_MODEL=small
EOF
```

Add ROCm environment variables to **both** systemd service files
(`~/.config/systemd/user/taris-telegram.service` and `taris-web.service`).
Insert inside the `[Service]` block, **before** the `ExecStart=` line:

```ini
[Service]
Environment="HSA_OVERRIDE_GFX_VERSION=11.0.3"
Environment="LD_LIBRARY_PATH=/usr/local/lib/ollama/rocm"
```

Then reload and restart:
```bash
systemctl --user daemon-reload
systemctl --user restart taris-telegram taris-web
```

> **Why `FASTER_WHISPER_DEVICE=cuda` for AMD?**  
> `faster-whisper` uses the CUDA compatibility layer that comes with the Ollama ROCm installation.  
> There is no `rocm` device name in faster-whisper — `cuda` routes through ROCm on AMD hardware.

Expected STT latency improvement for a 2-second voice command:  
- CPU (small model): ~600–900 ms  
- AMD GPU (small model, ROCm): ~50–100 ms

---

### B.6 — Install the embedding model (optional, for RAG)

```bash
bash ~/projects/sintaris-pl/src/setup/install_embedding_model.sh
```

Downloads `all-MiniLM-L6-v2` (ONNX) into `~/.taris/`. Used by `bot_embeddings.py` for document RAG.

---

### B.7 — Start Taris

```bash
cd ~/projects/sintaris-openclaw-local-deploy
./run_all.sh

# Or start individually:
./run_web.sh    # Web UI on http://localhost:8080
./run_telegram.sh   # Telegram bot
```

---

### B.8 — Connect OpenClaw ↔ Taris

Ensure the `skill-taris` API token matches:

```bash
# In Taris bot.env:
grep TARIS_API_TOKEN ~/projects/sintaris-openclaw-local-deploy/.taris/bot.env

# In sintaris-openclaw skill-taris:
cat ~/.openclaw/skills/skill-taris/api-keys.txt

# Both must be the same value. Test:
curl -s -H "Authorization: Bearer $(cat ~/.openclaw/skills/skill-taris/api-keys.txt)" \
  http://localhost:8080/api/status | python3 -m json.tool
# Expected: {"status": "ok", "version": "2026.x.x", ...}
```

Then restart the OpenClaw gateway to reload the skill:
```bash
systemctl --user restart openclaw-gateway.service
```

---

### B.9 — Verify

```bash
# 1. Taris Web UI is running
curl -sk https://localhost:8080/ | grep "Taris"

# 2. Taris API is reachable (from OpenClaw)
openclaw agent -m "Taris, what is your status?" --json

# 3. Telegram bot is active
# Send a message to your Telegram bot — it should respond

# 4. LLM routing works
# In Telegram, open Free Chat and send: "Hello from OpenClaw"
# Response should come via the openclaw provider
```

---

### B.10 — Optional: PostgreSQL backend

For full OpenClaw capabilities (pgvector RAG, multi-user data at scale):

```bash
sudo apt install postgresql-16 postgresql-16-pgvector -y
pip3 install psycopg2-binary

sudo -u postgres psql -c "CREATE USER taris WITH PASSWORD 'changeme'; CREATE DATABASE taris_db OWNER taris;"
sudo -u postgres psql -d taris_db -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Add to bot.env:
echo "STORE_BACKEND=postgres" >> ~/projects/sintaris-openclaw-local-deploy/.taris/bot.env
echo "DB_URL=postgresql://taris:changeme@localhost/taris_db" >> ~/projects/sintaris-openclaw-local-deploy/.taris/bot.env
echo "STORE_VECTORS=on" >> ~/projects/sintaris-openclaw-local-deploy/.taris/bot.env
```

Restart Taris after configuration changes.

---

### B.11 — Loop Guard (important!)

⚠️ **Circular dependency prevention:**

If `LLM_PROVIDER=openclaw` is set in Taris **and** `skill-taris` is active in OpenClaw,
do NOT configure `skill-taris` to send chat/LLM requests to Taris — this creates an
infinite loop. Safe usage pattern:

- `skill-taris` → call `GET /api/status` to check Taris health ✅
- `skill-taris` → call `POST /api/chat` to query notes/calendar ✅
- `skill-taris` → relay general LLM chat to Taris ❌ (loop if `LLM_PROVIDER=openclaw`)

See `doc/architecture/openclaw-integration.md` for the full loop-prevention guide.

---

## Part C — Performance Tuning (OpenClaw)

> Reference: `errors/perf-sintaition-2026-03-31.md` — full root-cause analysis.

### C.1 — LLM provider selection

| Hardware | Recommended `LLM_PROVIDER` | Model | Typical latency |
|---|---|---|---|
| CPU only (i7-2640M or weaker) | `openai` | gpt-4o-mini | 1.5–4 s (network) |
| AMD GPU (Radeon 680M/780M/890M) | `ollama` | `qwen3:14b` | ~1.2 s (local) |
| CPU with fast SSD (≥ 8 GB RAM) | `ollama` | `qwen2:0.5b` | ~300 ms (local, tiny) |

Always set `LLM_LOCAL_FALLBACK=1` when using `openai` as primary — it retries on Ollama if OpenAI times out.

For `qwen3` models, `OLLAMA_THINK=false` is **required**. Without it, the model consumes all tokens for internal reasoning and returns an empty reply via the OpenAI-compat endpoint.

### C.2 — STT device selection

```ini
# CPU-only machines:
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE=int8
FASTER_WHISPER_MODEL=base       # or small if CPU is fast enough

# AMD GPU (ROCm) — follow B.5-GPU steps first:
FASTER_WHISPER_DEVICE=cuda
FASTER_WHISPER_COMPUTE=float16
FASTER_WHISPER_MODEL=small      # small model is fine; GPU makes it fast
```

### C.3 — Preventing event loop blocking in FastAPI endpoints

All blocking operations (LLM calls, TTS subprocess, STT inference) must be wrapped in `asyncio.to_thread` inside async route handlers. Without this, the uvicorn event loop freezes for the duration of the call, causing other requests to time out.

```python
# ❌ BAD — blocks event loop:
reply = ask_llm(prompt, timeout=60)

# ✅ GOOD — runs in thread pool, event loop stays responsive:
reply = await asyncio.to_thread(lambda: ask_llm(prompt, timeout=60))
```

The production conversation endpoints (`voice_chat_endpoint`, `chat_send`) already follow this pattern. When adding new API endpoints, always verify that heavy operations are wrapped.

### C.4 — Benchmark and monitor performance

```bash
TOKEN=$(cat ~/.openclaw/skills/skill-taris/api-keys.txt)
BASE=http://localhost:8080

# Single benchmark run (LLM + TTS + STT timing)
curl -s -H "Authorization: Bearer $TOKEN" \
  -X POST -H "Content-Type: application/json" \
  -d '{"lang":"ru"}' "$BASE/api/benchmark" | python3 -m json.tool

# Today's pipeline logs (all stage timings)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/logs?date=$(date +%Y-%m-%d)&last_n=20" | python3 -m json.tool

# Aggregated stats
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/logs/stats?date=$(date +%Y-%m-%d)" | python3 -m json.tool
```

### C.5 — Verify GPU is being used

```bash
# Check Ollama uses AMD GPU (should show GPU layers, not CPU)
curl -s http://localhost:11434/api/tags | python3 -m json.tool

# Check faster-whisper device at runtime
grep "FASTER_WHISPER" ~/.taris/bot.env

# Watch GPU usage during a voice command
watch -n1 'cat /sys/class/drm/card*/device/gpu_busy_percent 2>/dev/null'
# or: radeontop -d -
```
