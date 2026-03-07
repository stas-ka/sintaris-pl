# picoclaw — Raspberry Pi Voice Assistant

Local Russian voice assistant for Raspberry Pi, powered by [picoclaw](https://github.com/sipeed/picoclaw) + OpenRouter. Listens for the wake word **"Пико"**, sends your Russian voice command to an LLM, and speaks the response back — entirely offline except the LLM API call.

**Features:**
- Offline Russian STT via Vosk (48 MB model, real-time on Pi 3)
- Offline Russian TTS via Piper (natural female voice, ~1–3 s latency)
- LLM via OpenRouter (100+ models, free tier available)
- Telegram bot channel via picoclaw gateway
- Daily Gmail digest to Telegram
- Interactive Telegram menu bot (Mail Digest / Free Chat / System Chat modes)
- Works on Raspberry Pi 3 B+ and newer (aarch64 / armv7)

---

## Documentation

| Document | Description |
|---|---|
| [doc/architecture.md](doc/architecture.md) | Full pipeline diagram, all components, file layout, configuration reference |
| [backup/device/README.md](backup/device/README.md) | Captured device configuration snapshot + restore instructions |

---

## Hardware Requirements

| Component | Recommended | Notes |
|---|---|---|
| Board | Raspberry Pi 3 B+ or newer | Pi 4 / Pi 5 also work |
| Microphone | USB microphone | Most standard USB mics work on Pi 3. See USB audio note below. |
| Speaker | Pi 3.5 mm jack + powered speaker | Or USB speaker |
| OS | Raspberry Pi OS Bookworm (64-bit) | PipeWire audio stack required |
| Storage | microSD ≥ 8 GB | Models need ~200 MB |

**Optional hardware:**
- [Joy-IT RB-TalkingPI HAT](https://joy-it.net/en/products/RB-TalkingPI) — I²S stereo mic + 3 W amp, Google AIY compatible. Requires setup step 4a below.

**USB audio note for Pi 3:**  
Most standard USB microphones work fine. The Philips SPC 520/525NC USB webcam mic specifically fails due to a Pi 3 DWC_OTG isochronous transfer bug — there is no software fix. Any other USB mic (even a cheap USB dongle) will work.

---

## Prerequisites

- A Raspberry Pi running **Raspberry Pi OS Bookworm** (64-bit recommended)
- SSH access or keyboard + monitor
- Internet access on the Pi for initial downloads
- An [OpenRouter](https://openrouter.ai/keys) API key (free tier available)
- A [Telegram bot token](https://t.me/BotFather) (for Telegram bot features — optional)  
  → Get your Telegram chat ID via [@userinfobot](https://t.me/userinfobot)
- A Gmail App Password (for Gmail digest — optional)  
  → Google Account → Security → 2-Step Verification → App Passwords
- [PuTTY](https://www.putty.org/) installed on Windows (`plink.exe`, `pscp.exe`) if deploying from Windows

---

## Step-by-Step Setup on a New Device

> **All commands marked `[Pi]` run on the Raspberry Pi (via SSH or terminal).**  
> **Commands marked `[Win]` run on your Windows dev machine (Git Bash or cmd).**  
> Replace `<user>` with your Pi username (default: `stas`), `<hostname>` with `OpenClawPI` or the Pi's IP, and `<password>` with your Pi SSH password.

---

### Step 1 — Prepare the Raspberry Pi OS

`[Pi]` Install **Raspberry Pi OS Bookworm 64-bit** (required for PipeWire audio stack). Enable SSH in `raspi-config`. Create your user and note the username and password.

Verify you are on Bookworm:
```bash
# [Pi]
cat /etc/os-release | grep VERSION_CODENAME   # should print: bookworm
```

---

### Step 2 — Clone this repo on your dev machine

`[Win]` Clone the repo and create your local credentials file:
```bat
git clone https://github.com/yourusername/picoclaw.git
cd picoclaw
```

Copy `.env.example` (if present) or create `.env` manually:
```
TARGETHOST=<hostname>
HOSTUSER=<user>
HOSTPWD=<password>
ACCESSINGTOOL=ssh
```

Create `.credentials/.pico_env` with your secrets (this file is gitignored — never commit it):
```bash
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=<your_telegram_chat_id>
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

---

### Step 3 — Install the picoclaw binary on the Pi

`[Pi]` Download and install the picoclaw Go binary:
```bash
# [Pi] — for 64-bit (aarch64):
wget -q https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_aarch64.deb \
     -O /tmp/picoclaw_aarch64.deb
sudo dpkg -i /tmp/picoclaw_aarch64.deb
picoclaw version   # should print v0.2.0 or newer
```

For 32-bit Pi OS (armv7), use `picoclaw_armhf.deb` instead.

Then initialise the picoclaw workspace:
```bash
# [Pi]
picoclaw onboard   # creates ~/.picoclaw/ with default config.json
```

---

### Step 4 — Configure picoclaw with your API key

`[Pi]` Edit `~/.picoclaw/config.json`. The minimum required config:

```json
{
  "model_list": [
    {
      "model_name": "openrouter-auto",
      "model":      "openrouter/auto",
      "api_base":   "https://openrouter.ai/api/v1",
      "api_key":    "sk-or-v1-xxxxxxxxxxxxxxxx"
    }
  ],
  "agents": {
    "defaults": {
      "model": "openrouter-auto",
      "max_tokens": 32768,
      "max_tool_iterations": 50
    }
  },
  "channels": {
    "telegram": {
      "enabled": false,
      "token": "",
      "allow_from": []
    }
  }
}
```

> Get a free OpenRouter key at: https://openrouter.ai/keys  
> The reference config with all options is in [`backup/device/picoclaw-config.json`](backup/device/picoclaw-config.json).

Test the LLM connection:
```bash
# [Pi]
picoclaw agent -m "Привет! Как дела?"
# Should print an LLM response within a few seconds
```

---

### Step 5 — Deploy all source files from Windows to the Pi

`[Win]` Copy all Python scripts and setup files to the Pi in one go:
```bat
rem Copy Python application scripts
pscp -pw "%HOSTPWD%" src\voice_assistant.py   %HOSTUSER%@%TARGETHOST%:/home/%HOSTUSER%/.picoclaw/
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py %HOSTUSER%@%TARGETHOST%:/home/%HOSTUSER%/.picoclaw/
pscp -pw "%HOSTPWD%" src\gmail_digest.py      %HOSTUSER%@%TARGETHOST%:/home/%HOSTUSER%/.picoclaw/

rem Copy setup scripts to /tmp for execution
pscp -pw "%HOSTPWD%" src\setup\setup_voice.sh         %HOSTUSER%@%TARGETHOST%:/tmp/
pscp -pw "%HOSTPWD%" src\setup\setup_gateway.sh       %HOSTUSER%@%TARGETHOST%:/tmp/
pscp -pw "%HOSTPWD%" src\setup\deploy_telegram_bot.sh %HOSTUSER%@%TARGETHOST%:/tmp/
```

Or with Git Bash (MSYS):
```bash
# [Win — Git Bash]
HOSTPWD="<password>" HOSTUSER="<user>" TARGETHOST="<hostname>"
for f in src/voice_assistant.py src/telegram_menu_bot.py src/gmail_digest.py; do
  pscp -pw "$HOSTPWD" "$f" "$HOSTUSER@$TARGETHOST:/home/$HOSTUSER/.picoclaw/"
done
pscp -pw "$HOSTPWD" src/setup/setup_voice.sh         "$HOSTUSER@$TARGETHOST:/tmp/"
pscp -pw "$HOSTPWD" src/setup/setup_gateway.sh       "$HOSTUSER@$TARGETHOST:/tmp/"
pscp -pw "$HOSTPWD" src/setup/deploy_telegram_bot.sh "$HOSTUSER@$TARGETHOST:/tmp/"
```

---

### Step 6 — Install the voice assistant stack (Vosk + Piper)

`[Pi]` Run the voice stack installer. This downloads models (~120 MB) and installs the systemd service:
```bash
# [Pi]
sudo bash /tmp/setup_voice.sh
```

The script installs:
- `vosk` Python package + `vosk-model-small-ru-0.22` (48 MB STT model)
- Piper TTS binary to `/usr/local/bin/piper` + `ru_RU-irina-medium.onnx` voice (66 MB)
- `picoclaw-voice.service` systemd unit → starts the voice assistant on boot

Verify the service was installed:
```bash
# [Pi]
systemctl status picoclaw-voice --no-pager
```

#### Step 6a — RB-TalkingPI HAT (I²S mic, optional)

If using the Joy-IT RB-TalkingPI I²S HAT instead of a USB microphone, enable the I²S overlay. Add to `/boot/firmware/config.txt`:
```
dtparam=i2s=on
dtoverlay=googlevoicehat-soundcard
```
Then reboot:
```bash
# [Pi]
sudo reboot
# After reboot:
arecord -l    # should show a "googlevoicehat" card
```

If using a USB mic, no reboot is needed.

---

### Step 7 — Configure secrets for services

`[Pi]` Create `/home/<user>/.picoclaw/bot.env` with Telegram credentials (read by `picoclaw-telegram.service` via `EnvironmentFile=`):
```bash
# [Pi]
cat > ~/.picoclaw/bot.env << 'EOF'
BOT_TOKEN=123456789:ABCdef...
ALLOWED_USER=<your_telegram_chat_id>
EOF
chmod 600 ~/.picoclaw/bot.env
```

For Gmail digest, set credentials as environment variables (or use a cron wrapper that sources `.pico_env`):
```bash
# [Pi] — add to ~/.bashrc or a cron wrapper:
export OPENROUTER_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
export TELEGRAM_BOT_TOKEN=123456789:ABCdef...
export TELEGRAM_CHAT_ID=<your_chat_id>
export GMAIL_USER=you@gmail.com
export GMAIL_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail App Password (16 chars, no spaces)
```

> **Gmail App Password**: enable 2-factor auth in Gmail → Google Account → Security → App Passwords → create one for "Mail".

---

### Step 8 — Install the picoclaw gateway service

`[Pi]` The gateway exposes picoclaw to Telegram, Discord, and other channels natively. Run:
```bash
# [Pi]
sudo bash /tmp/setup_gateway.sh
```

Verify:
```bash
# [Pi]
systemctl status picoclaw-gateway --no-pager
journalctl -u picoclaw-gateway -n 20 --no-pager
```

> **Note**: The Telegram channel in `config.json` is set to `"enabled": false` by default — the Telegram menu bot (Step 9) handles Telegram instead. Enable it only if you want the raw picoclaw gateway Telegram mode.

---

### Step 9 — Install the Telegram menu bot (optional)

The menu bot provides a structured 3-mode interface in Telegram (Mail Digest / Free Chat / System Chat). It requires Steps 7 and 8 to be done first.

`[Pi]` Run the deploy script:
```bash
# [Pi]
sudo bash /tmp/deploy_telegram_bot.sh
```

The script:
1. Installs `pyTelegramBotAPI` via pip3
2. Disables the built-in picoclaw Telegram channel in `config.json` (to avoid token conflict)
3. Installs `picoclaw-telegram.service` systemd unit and starts it

Verify:
```bash
# [Pi]
systemctl status picoclaw-telegram --no-pager
journalctl -u picoclaw-telegram -n 20 --no-pager
# Should show: "Polling Telegram…"
```

Send `/start` to your bot in Telegram — you should see the inline menu.

---

### Step 10 — Set up Gmail daily digest (optional)

The digest script reads INBOX and Spam via IMAP, summarises with OpenRouter, and sends a Telegram message daily at 19:00.

`[Pi]` Register the cron job:
```bash
# [Pi]
crontab -e
# Add this line:
0 19 * * * python3 /home/<user>/.picoclaw/gmail_digest.py >> /home/<user>/.picoclaw/digest.log 2>&1
```

Test manually:
```bash
# [Pi]
OPENROUTER_KEY=sk-or-... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... \
GMAIL_USER=you@gmail.com GMAIL_PASSWORD="xxxx xxxx xxxx xxxx" \
  python3 ~/.picoclaw/gmail_digest.py
# Should print a digest and send it to Telegram
```

Or from Windows:
```bat
rem [Win]
plink -pw "%HOSTPWD%" -batch %HOSTUSER%@%TARGETHOST% "python3 ~/.picoclaw/gmail_digest.py"
```

---

### Step 11 — Start and test the voice assistant

`[Pi]`
```bash
sudo systemctl start picoclaw-voice

# Follow logs in real time:
tail -f ~/.picoclaw/voice.log
```

You should hear (and see in the log):
```
Голосовой ассистент Пико запущен. Скажите «Пико» для активации.
```

Say **"Пико"** — wait for the beep — then ask your question in Russian. The assistant will reply by voice and print the exchange to the log.

---

### Step 12 — Verify all services are running

`[Pi]`
```bash
systemctl status picoclaw-gateway  --no-pager
systemctl status picoclaw-voice    --no-pager
systemctl status picoclaw-telegram --no-pager
```

All three should show `active (running)`. Services are enabled at boot (`systemctl enable` is called by the install scripts).

---

### Adjusting for a different username

The default username throughout is `stas`. To use a different user (e.g., `pi`):

1. Edit paths in `voice_assistant.py` CONFIG section on the Pi:
   ```python
   "vosk_model_path": "/home/pi/.picoclaw/vosk-model-small-ru",
   "piper_model":     "/home/pi/.picoclaw/ru_RU-irina-medium.onnx",
   ```

2. Edit the service units in `src/services/` before deploying:
   ```ini
   User=pi
   Environment=XDG_RUNTIME_DIR=/run/user/1000
   ```
   If your UID is not 1000, find it with `id -u` and replace accordingly.

3. Update all `WorkingDirectory=` and `Environment=HOME=` lines where they reference `/home/stas`.

---

## Changing the Wake Word

Edit the `hotwords` list in `voice_assistant.py`:

```python
"hotwords": ["алиса", "алис"],   # example: use "Alice"
"hotword_threshold": 0.75,
```

Then redeploy and restart the service.

---

## Changing the LLM Model

Edit `~/.picoclaw/config.json` on the Pi. Any OpenRouter model works:

```json
{ "model": "openrouter/anthropic/claude-3.5-haiku" }
{ "model": "openrouter/google/gemini-flash-1.5" }
{ "model": "openrouter/meta-llama/llama-3.1-8b-instruct:free" }
```

Full model list: https://openrouter.ai/models

Restart the gateway after changing:
```bash
sudo systemctl restart picoclaw-gateway
```

---

## Changing the TTS Voice

Download another Piper Russian voice from Hugging Face:

```bash
# Alternative: ruslan (male, medium)
wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx \
     -O ~/.picoclaw/ru_RU-ruslan-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx.json \
     -O ~/.picoclaw/ru_RU-ruslan-medium.onnx.json
```

Set the new voice in `voice_assistant.py` CONFIG or via env:
```bash
# In /etc/systemd/system/picoclaw-voice.service:
Environment=PIPER_MODEL=/home/stas/.picoclaw/ru_RU-ruslan-medium.onnx
```

All available Piper voices: https://rhasspy.github.io/piper-samples/

---

## Selecting a Different Microphone

List available PipeWire sources on the Pi:
```bash
XDG_RUNTIME_DIR=/run/user/1000 pactl list sources short
```

Set the source in `/etc/systemd/system/picoclaw-voice.service`:
```ini
Environment=AUDIO_TARGET=alsa_input.usb-your-mic-name.mono-fallback
```

Or set `AUDIO_TARGET=auto` to use the PipeWire default source.

---

## Service Management

```bash
# Voice assistant
sudo systemctl start   picoclaw-voice
sudo systemctl stop    picoclaw-voice
sudo systemctl restart picoclaw-voice
sudo systemctl status  picoclaw-voice --no-pager
tail -f ~/.picoclaw/voice.log

# Telegram gateway (picoclaw native LLM channel)
sudo systemctl start   picoclaw-gateway
sudo systemctl restart picoclaw-gateway
journalctl -u picoclaw-gateway -n 30 --no-pager

# Telegram menu bot (interactive 3-mode bot)
sudo systemctl start   picoclaw-telegram
sudo systemctl restart picoclaw-telegram
journalctl -u picoclaw-telegram -n 30 --no-pager
```

---

## Manual Tests

```bash
# Test TTS only (no mic needed):
echo "Привет, я Пико!" | piper \
    --model ~/.picoclaw/ru_RU-irina-medium.onnx \
    --output-raw | aplay -r22050 -fS16_LE -c1 -

# Test mic capture (replace hw:1,0 with your device from arecord -l):
arecord -D hw:1,0 -f S16_LE -r 16000 -c 1 -d 3 test.wav && aplay test.wav

# Test LLM directly:
picoclaw agent -m "Сколько будет два плюс два?"

# Check PipeWire audio sources:
XDG_RUNTIME_DIR=/run/user/1000 pactl list sources short
```

Hardware test scripts are in [`src/tests/`](src/tests/).

---

## Remote Management from Windows

This repo uses PuTTY tools for remote access:

```bat
rem Run command on Pi
plink -pw "password" -batch pi@hostname "command"

rem Copy file to Pi
pscp -pw "password" localfile pi@hostname:/remote/path

rem Copy file from Pi
pscp -pw "password" pi@hostname:/remote/path localfile
```

Set `-batch` flag always to suppress interactive prompts.  
Use `MSYS_NO_PATHCONV=1` in Git Bash to prevent path conversion of `/run/user/1000`.

---

## Architecture Diagram

See [`doc/architecture.md`](doc/architecture.md) for the full component architecture, data flow, file layout, and configuration reference.

---

## Directory Structure

```
.
├── src/                          ← ALL target-side sources
│   ├── voice_assistant.py        ← voice loop daemon
│   ├── telegram_menu_bot.py      ← interactive Telegram menu bot
│   ├── gmail_digest.py           ← daily email digest agent
│   ├── gmail_auth.py             ← OAuth2 setup helper (run once on Windows)
│   ├── setup/                    ← installation & fix scripts (run on Pi)
│   │   ├── setup_voice.sh        ← full voice stack installer
│   │   ├── setup_gateway.sh      ← picoclaw gateway service installer
│   │   ├── deploy_telegram_bot.sh← Telegram menu bot deploy
│   │   ├── fix_implicit_fb.sh    ← USB audio snd-usb-audio quirk fix
│   │   ├── fix_usb_audio_quirk.sh
│   │   ├── fix_webcam_vol.sh
│   │   ├── piper_wrapper.sh      ← Piper TTS wrapper script
│   │   └── bot.env.example       ← template for /home/stas/.picoclaw/bot.env
│   ├── services/                 ← systemd unit files
│   │   ├── picoclaw-voice.service    ← voice assistant daemon
│   │   └── picoclaw-telegram.service ← Telegram menu bot daemon
│   └── tests/                    ← hardware diagnostic scripts
│       ├── test_tts.sh
│       ├── test_mic.py
│       ├── test_webcam_mic.sh
│       ├── check_kernel_audio.sh
│       └── ...
├── backup/device/                ← sanitized Pi config snapshot
│   ├── picoclaw-config.json
│   ├── crontab
│   ├── systemd/
│   └── modprobe.d/
├── doc/
│   └── architecture.md           ← component architecture & design notes
└── .credentials/                 ← secrets ONLY (gitignored)
    ├── .pico_env                  ← bot tokens & API keys (never commit)
    └── client_secret_*.json      ← OAuth2 client secret (never commit)
```
