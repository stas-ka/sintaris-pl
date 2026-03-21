# Installing Taris Bot on a New Target

**Last updated:** 2026-03-12  
**Applies to:** OpenClawPI, OpenClawPI2, or any new Raspberry Pi  
**OS:** Raspberry Pi OS Bookworm (64-bit Lite), aarch64

Use this guide for a complete fresh deployment from a bare OS image.
For incremental updates to an existing host, see `doc/update_strategy.md`.

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
| Tailscale IP | `100.81.143.126` | — |
| LAN IP | `192.168.178.163` | `192.168.178.165/166` |

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
