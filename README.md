# picoclaw — Raspberry Pi Voice Assistant

Local Russian voice assistant for Raspberry Pi, powered by [picoclaw](https://github.com/sipeed/picoclaw) + OpenRouter. Listens for the wake word **"Пико"**, sends your Russian voice command to an LLM, and speaks the response back — entirely offline except the LLM API call.

**Features:**
- Offline Russian STT via Vosk (48 MB model, real-time on Pi 3)
- Offline Russian TTS via Piper (natural female voice, ~1–3 s latency)
- LLM via OpenRouter (100+ models, free tier available)
- Telegram bot channel via picoclaw gateway
- Daily Gmail digest to Telegram
- Works on Raspberry Pi 3 B+ and newer (aarch64 / armv7)

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
- An [OpenRouter](https://openrouter.ai/keys) API key (free tier)
- A [Telegram bot token](https://t.me/BotFather) (for the Telegram channel — optional)
- This workspace cloned or your credentials files ready

---

## Step-by-Step Setup on a New Device

### Step 1 — Install picoclaw binary

```bash
# On the Pi:
wget -q https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_aarch64.deb \
     -O /tmp/picoclaw_aarch64.deb
sudo dpkg -i /tmp/picoclaw_aarch64.deb
picoclaw version   # should print v0.2.0 or newer
```

For 32-bit Pi OS (armv7), use `picoclaw_armhf.deb` instead.

---

### Step 2 — Configure picoclaw with your API key

```bash
picoclaw onboard   # initialize ~/.picoclaw/ directory
```

Edit `/home/<user>/.picoclaw/config.json` (replace `sk-or-...` with your key):

```json
{
  "model_list": [
    {
      "model_name": "openrouter-auto",
      "model": "openrouter/openai/gpt-4o-mini",
      "api_key": "sk-or-v1-xxxxxxxxxxxxxxxx"
    }
  ],
  "agents": {
    "defaults": { "model": "openrouter-auto" }
  }
}
```

Test it:
```bash
picoclaw agent -m "Привет! Как дела?"
# Should print an LLM response
```

Get a free OpenRouter key at: https://openrouter.ai/keys

---

### Step 3 — Install the Telegram gateway (optional)

> Skip this step if you don't need a Telegram bot.

Create a bot via [@BotFather](https://t.me/BotFather) and get your bot token. Find your Telegram user ID via [@userinfobot](https://t.me/userinfobot).

Add Telegram section to `~/.picoclaw/config.json`:

```json
{
  "model_list": [ ... ],
  "agents": { "defaults": { "model": "openrouter-auto" } },
  "telegram": {
    "enabled": true,
    "token": "123456789:ABCdef...",
    "allowed_users": [994963580]
  }
}
```

Install and start the gateway service:

```bash
# Copy setup_gateway.sh to the Pi then run:
sudo bash setup/setup_gateway.sh

# Verify:
systemctl status picoclaw-gateway --no-pager
```

Send a message to your bot to test it.

---

### Step 4 — Install the voice assistant stack

This installs Vosk, Piper, and configures the audio.

```bash
# From your dev machine — copy files to Pi:
pscp -pw "<password>" src\voice_assistant.py pi@<hostname>:/home/pi/.picoclaw/voice_assistant.py
pscp -pw "<password>" setup\setup_voice.sh pi@<hostname>:/tmp/setup_voice.sh

# On the Pi:
sudo bash /tmp/setup_voice.sh
```

The script installs:
- `vosk` Python package + `vosk-model-small-ru-0.22` (48 MB)
- Piper TTS binary + `ru_RU-irina-medium.onnx` voice (66 MB)
- `picoclaw-voice.service` systemd unit

#### Step 4a — RB-TalkingPI HAT (I²S mic, optional)

If you are using the Joy-IT RB-TalkingPI HAT instead of a USB microphone:

```bash
# setup_voice.sh already adds the dtoverlay — just reboot:
sudo reboot

# After reboot, verify I²S device appeared:
arecord -l    # should show "googlevoicehat" card
aplay -l

# Test mic capture:
arecord -D hw:1,0 -f S16_LE -r 16000 -c 1 -d 3 test.wav
aplay test.wav
```

If using USB mic or PipeWire default, no reboot is needed.

---

### Step 5 — Adjust the username / paths (if not using `stas`)

The default paths assume user `stas`. If your Pi user is different (e.g. `pi`), edit:

**On the Pi — `/home/<user>/.picoclaw/voice_assistant.py`** CONFIG section:
```python
"vosk_model_path": "/home/pi/.picoclaw/vosk-model-small-ru",
"piper_model":     "/home/pi/.picoclaw/ru_RU-irina-medium.onnx",
```

**`/etc/systemd/system/picoclaw-voice.service`:**
```ini
User=pi
WorkingDirectory=/home/pi/.picoclaw
Environment=VOSK_MODEL_PATH=/home/pi/.picoclaw/vosk-model-small-ru
Environment=PIPER_MODEL=/home/pi/.picoclaw/ru_RU-irina-medium.onnx
```

Also update `picoclaw_runtime_dir` in the script CONFIG if your user UID is not 1000:
```bash
id -u   # get your UID; replace 1000 with this value in pipewire_runtime_dir
```

---

### Step 6 — Start and test the voice assistant

```bash
# Fix voice.log ownership (needed on first start):
sudo chown stas:stas /home/stas/.picoclaw/voice.log 2>/dev/null || true

# Start:
sudo systemctl start picoclaw-voice

# Follow logs:
tail -f /home/stas/.picoclaw/voice.log

# You should hear:
#   "Голосовой ассистент Пико запущен. Скажите «Пико» для активации."
```

Say **"Пико"** — then ask your question in Russian. The assistant will reply.

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
tail -f /home/stas/.picoclaw/voice.log

# Telegram gateway
sudo systemctl start   picoclaw-gateway
sudo systemctl restart picoclaw-gateway
journalctl -u picoclaw-gateway -n 30 --no-pager
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

Hardware test scripts are in [`tests/hw/`](tests/hw/).

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
├── src/                          ← Python application source
│   ├── voice_assistant.py        ← voice loop daemon
│   ├── telegram_menu_bot.py      ← Telegram menu bot
│   ├── gmail_digest.py           ← daily email digest agent
│   └── gmail_auth.py             ← OAuth2 setup helper
├── setup/                        ← shell installation scripts
│   ├── services/                 ← systemd unit files
│   │   ├── picoclaw-voice.service
│   │   └── picoclaw-telegram.service
│   ├── setup_voice.sh            ← full voice stack installer
│   ├── setup_gateway.sh          ← Telegram gateway service
│   ├── deploy_telegram_bot.sh    ← Telegram menu bot deploy
│   ├── fix_implicit_fb.sh        ← USB audio fixes
│   ├── fix_usb_audio_quirk.sh
│   ├── fix_webcam_vol.sh
│   └── piper_wrapper.sh
├── tests/hw/                     ← hardware diagnostic scripts
│   ├── test_tts.sh
│   ├── test_mic.py
│   ├── test_webcam_mic.sh
│   ├── check_kernel_audio.sh
│   └── ...
├── doc/
│   └── architecture.md           ← component architecture & design notes
└── .credentials/                 ← secrets ONLY (gitignored)
    ├── .pico_env                  ← bot tokens & API keys (never commit)
    └── client_secret_*.json      ← OAuth2 client secret (never commit)
```
