# Copilot Instructions — picoclaw workspace

## Workspace Layout

```
picoclaw/
  src/                   ← ALL target-side sources (Python, shell, services, tests)
    setup/               ← installation & fix shell scripts (run on Pi)
    services/            ← systemd .service unit files
    tests/               ← hardware test & diagnostic scripts
  backup/device/         ← sanitized Pi config snapshot
  doc/                   ← architecture and design documentation
  .credentials/          ← secrets ONLY (never scripts or code)
  .env                   ← remote host connection vars (gitignored)
```

### `.credentials/` — secrets only

**`.credentials/` must contain only credential files:**

| File | Type |
|---|---|
| `.pico_env` | API keys, bot tokens, passwords |
| `client_secret_*.json` | OAuth2 client secret |

**Never place scripts, Python files, `.sh` files, or service units in `.credentials/`.**  
All target-side sources go in `src/`. Shell scripts go in `src/setup/`. Systemd units go in `src/services/`. Hardware tests go in `src/tests/`.

---

## Remote Host Access

All remote operations target the host defined in `.env`.

| Key            | Value           |
|----------------|-----------------|
| `TARGETHOST`   | `OpenClawPI`    |
| `HOSTUSER`     | `stas`          |
| `HOSTPWD`      | *(see .env)* |
| `ACCESSINGTOOL`| `ssh`           |

### SSH tool

`sshpass` is **not available** on this Windows machine.  
Use **`plink`** (PuTTY command-line client, installed at `C:\Program Files\PuTTY\plink.exe`) for non-interactive SSH with password.

**Template for remote commands:**
```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "<remote command>"
```

Always add `-batch` to suppress interactive prompts.

---

## picoclaw Installation on Remote Host

- **Installed as:** npm global package
- **Location:** `/home/stas/.npm-global/lib/node_modules/picoclaw`
- **Version:** `2026.3.3`
- **Entry point:** `index.js`
- **No CLI binary** — `package.json` has no `bin` field, so `which picoclaw` returns nothing. It is used as a Node.js module only (`require('picoclaw')` / `import`).
- **No systemd service** registered.
- **SDK dependency:** `@cmdop/node` — installed globally at `/home/stas/.npm-global/lib/node_modules/@cmdop/node`

picoclaw is a themed wrapper around the **CMDOP SDK** (`@cmdop/node`). It requires an API key from [https://my.cmdop.com/dashboard/settings/](https://my.cmdop.com/dashboard/settings/).

Verify installation at any time:
```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "npm list -g picoclaw && npm list -g @cmdop/node"
```

Verify picoclaw loads correctly (no errors):
```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "node -e \"const p = require('/home/stas/.npm-global/lib/node_modules/picoclaw'); console.log('OK', p.defaultConfig);\""
```

---

## sipeed/picoclaw — AI Agent Go Binary

This is a **separate, different project** from the npm `picoclaw` package above.  
Source: [github.com/sipeed/picoclaw](https://github.com/sipeed/picoclaw) | Official site: **picoclaw.io** (⚠️ `picoclaw.ai` is a third-party domain).

### Installation on Remote Host

- **Installed via:** `picoclaw_aarch64.deb` (managed by dpkg)
- **Binary:** `/usr/bin/picoclaw` (v0.2.0)
- **Also installed:** `/usr/bin/picoclaw-launcher`, `/usr/bin/picoclaw-launcher-tui`
- **Config:** `/home/stas/.picoclaw/config.json`
- **Workspace:** `/home/stas/.picoclaw/workspace`
- **Initialized:** yes (`picoclaw onboard` already run)

Re-install or upgrade:
```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "wget -q https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_aarch64.deb -O /tmp/picoclaw_aarch64.deb && echo $HOSTPWD | sudo -S dpkg -i /tmp/picoclaw_aarch64.deb"
```

```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "picoclaw version"
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "picoclaw status"
```

### Setup: Add an LLM API Key

Edit the config to add an API key — picoclaw won't work without one.
Recommended: [OpenRouter](https://openrouter.ai/keys) (free tier, 100+ models).

```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "cat ~/.picoclaw/config.json"
```

Minimal `model_list` to add to `~/.picoclaw/config.json`:
```json
{
  "model_list": [
    {
      "model_name": "my-model",
      "model": "openrouter/openai/gpt-4o-mini",
      "api_key": "sk-or-..."
    }
  ],
  "agents": {
    "defaults": {
      "model": "my-model"
    }
  }
}
```

### Usage

```bat
rem Chat one-shot
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "picoclaw agent -m \"Hello!\""

rem Start gateway (for Telegram/Discord/WhatsApp bots)
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "picoclaw gateway"

rem Show status
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "picoclaw status"

rem List CLI commands
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "picoclaw --help"
```

### CLI Reference

| Command | Description |
|---|---|
| `picoclaw onboard` | Initialize config & workspace |
| `picoclaw agent -m "..."` | One-shot chat with agent |
| `picoclaw agent` | Interactive chat mode |
| `picoclaw gateway` | Start gateway (for bot channels) |
| `picoclaw status` | Show config/API key status |
| `picoclaw version` | Show version |
| `picoclaw cron list` | List scheduled jobs |

---

## Gmail Daily Digest Agent

Runs daily at 19:00 on the Pi — reads Gmail (INBOX + Spam), summarizes with OpenRouter, sends digest to Telegram.

- **Script:** `/home/stas/.picoclaw/gmail_digest.py`
- **Log:** `/home/stas/.picoclaw/digest.log`
- **Gmail:** `stas.ulmer@gmail.com` via IMAP + App Password (no OAuth2 needed)
- **Folders checked:** INBOX + `[Google Mail]/Spam` (last 24h, max 50 each)
- **LLM:** OpenRouter `openai/gpt-4o-mini`
- **Delivery:** Telegram bot `@smartpico_bot` → chat ID `994963580`
- **Cron:** `0 19 * * *` (Pi local time)

```bat
rem Run manually
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "python3 /home/stas/.picoclaw/gmail_digest.py"

rem View log
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "tail -20 /home/stas/.picoclaw/digest.log"

rem Update script after local edits
pscp -pw "$HOSTPWD" src\gmail_digest.py stas@OpenClawPI:/home/stas/.picoclaw/gmail_digest.py
```

### picoclaw Telegram Gateway

- **Bot:** `@smartpico_bot` — token & chat ID in `.credentials/.pico_env`
- **LLM:** OpenRouter auto-routing (`openrouter-auto` model)
- **Config:** `~/.picoclaw/config.json` (Telegram enabled, allowed user: `994963580`)
- **Service:** `picoclaw-gateway.service` (systemd, auto-starts on boot)

```bat
rem Check gateway status
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "systemctl status picoclaw-gateway --no-pager"

rem Restart gateway
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "echo $HOSTPWD | sudo -S systemctl restart picoclaw-gateway"

rem View gateway logs
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "journalctl -u picoclaw-gateway -n 30 --no-pager"
```

---

## Russian Voice Assistant (RB-TalkingPI)

Local offline Russian voice interface for picoclaw. Based on analysis of KIM-ASSISTANT project
(`D:\Projects\workspace\hp\KIM-ASSISTANT\analyse`).

### Hardware Required
- **Joy-IT RB-TalkingPI** HAT — I2S stereo mic + 3W amp (Google AIY compatible)
- Compatible: Pi A+, B+, 2, **3B**, **3B+**, 4B

### Voice Pipeline
```
RB-TalkingPI mic
  → Vosk STT (vosk-model-small-ru, offline)   ← replaces KIM's CPU-heavy full Vosk
  → hotword "Пико" (fuzzy-match, like KIM's "Ким" detection)
  → record command → recognize Russian text
  → picoclaw agent -m "..."                    (OpenRouter via gateway)
  → Piper TTS (ru_RU-irina-medium, offline)    ← replaces KIM's Silero/PyTorch (2GB, too heavy)
  → RB-TalkingPI 3W speaker
```

### Why Piper instead of Silero (from KIM analysis)
- KIM uses Silero `xenia` TTS — requires PyTorch ~2GB RAM — **unusable on Pi 3 (1GB)**
- Piper TTS uses ONNX Runtime — 50MB binary, 66MB voice model, runs in 1–3s/sentence on Pi 3
- Russian voice: `ru_RU-irina-medium` — natural female voice

### Installed Files
| Local file | Location on Pi | Description |
|---|---|---|
| `src/voice_assistant.py` | `~/.picoclaw/voice_assistant.py` | Main daemon |
| `src/setup/setup_voice.sh` | run via `/tmp/` | Full install script |
| `src/services/picoclaw-voice.service` | `/etc/systemd/system/` | systemd unit |
| _(downloaded)_ | `~/.picoclaw/vosk-model-small-ru/` | 48MB Russian STT model |
| _(downloaded)_ | `/usr/local/bin/piper` | TTS engine |
| _(downloaded)_ | `~/.picoclaw/ru_RU-irina-medium.onnx` | 66MB Russian voice |

### Initial Setup (run once when RB-TalkingPI is physically attached)

1. Copy files and run software install:
```bat
pscp -pw "$HOSTPWD" src\voice_assistant.py stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "$HOSTPWD" src\setup\setup_voice.sh stas@OpenClawPI:/tmp/setup_voice.sh
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "echo $HOSTPWD | sudo -S bash /tmp/setup_voice.sh"
```

2. Reboot (required for I2S driver):
```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "echo $HOSTPWD | sudo -S reboot"
```

3. After reboot, verify I2S audio device:
```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "arecord -l && aplay -l"
```

4. Start voice assistant:
```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "echo $HOSTPWD | sudo -S systemctl start picoclaw-voice"
```

### Service Management
```bat
rem Start / stop / restart
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "echo $HOSTPWD | sudo -S systemctl start picoclaw-voice"
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "echo $HOSTPWD | sudo -S systemctl stop picoclaw-voice"
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "echo $HOSTPWD | sudo -S systemctl restart picoclaw-voice"

rem View logs
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "tail -30 ~/.picoclaw/voice.log"
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "journalctl -u picoclaw-voice -n 30 --no-pager"
```

### Test TTS manually (without microphone)
```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "echo 'Привет я Пико' | piper --model ~/.picoclaw/ru_RU-irina-medium.onnx --output-raw | aplay -r22050 -fS16_LE -c1 -"
```

### Software Stack (already installed on Pi)
| Component | Version | Location |
|---|---|---|
| `vosk` | 0.3.45 | pip3 (system) |
| `sounddevice` | 0.5.5 | pip3 (system) |
| `portaudio19-dev` | 19.6.0 | apt |
| `espeak-ng` | 1.52.0 | apt |
| Vosk Russian model | small-ru-0.22 (48MB) | `~/.picoclaw/vosk-model-small-ru/` |
| Piper TTS binary | 1.2.0 | `/usr/local/bin/piper` (wrapper) |
| Piper libs | bundled | `/usr/local/share/piper/` |
| Piper voice (Irina) | medium (61MB) | `~/.picoclaw/ru_RU-irina-medium.onnx` |

### Wake Word
Say **"Пико"** (or "Привет Пико") — the assistant activates, listens for a command, sends to picoclaw, speaks the response.

---

## Common Remote Tasks

### Run a remote command
```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "<command>"
```

### Copy a file to the remote host
```bat
pscp -pw "$HOSTPWD" <local-file> stas@OpenClawPI:<remote-path>
```

### Copy a file from the remote host
```bat
pscp -pw "$HOSTPWD" stas@OpenClawPI:<remote-path> <local-dest>
```

(`pscp` is bundled with PuTTY at `C:\Program Files\PuTTY\pscp.exe`)

### Use picoclaw in a Node.js script on the remote host
```js
// Example: use picoclaw via node -e on the remote host
const { createPicoClaw } = require('/home/stas/.npm-global/lib/node_modules/picoclaw');
const client = createPicoClaw({ apiKey: 'cmdop_live_xxx' });
const result = await client.run('uptime');
console.log(result);
```

Run it remotely:
```bat
plink -pw "$HOSTPWD" -batch stas@OpenClawPI "node /path/to/your/script.js"
```

---

## Documentation Maintenance Rule

**When you add new functionality, change the architecture, add a new service, script, or component, or make any significant change to how the system works, you MUST update the relevant documents:**

| Document | Update when… |
|---|---|
| `README.md` | New setup steps, new features listed in the intro, directory structure changes, new services/scripts |
| `doc/architecture.md` | New component added, new pipeline stage, new systemd service, new file appears on the Pi, process hierarchy changes |
| `backup/device/README.md` | New software installed on Pi, new systemd services, new cron jobs, version upgrades |

**Rules:**
- Always update documents **in the same commit** as the code change, not in a later "fix docs" commit.
- The `README.md` features list and directory structure must always accurately reflect what exists in `src/`.
- The `architecture.md` "File Layout on Pi", "Process Hierarchy", and component sections must stay in sync with what actually runs.
- If a new `.service` file is added to `src/services/`, it must appear in the architecture process hierarchy.
- If new env vars or config keys are introduced, they must be added to the configuration reference table in `architecture.md`.

---

## Notes

- All credentials are stored in `.credentials/.pico_env` — never hard-code them and never commit that file.
- Remote host credentials (host/user/pwd) are also in `.env`.
- The `.credentials/` directory and `.env` are in `.gitignore`.
- `.credentials/` contains **only** secret/credential files — never scripts, `.py`, `.sh`, or `.service` files.
- All target-side sources belong in `src/`. Shell setup scripts go in `src/setup/`. Systemd units go in `src/services/`. Hardware tests go in `src/tests/`.
- The remote OS is Linux (Raspberry Pi 3 B+ — hostname `openclawpi`, arm64 / aarch64 architecture).
- `python3`, `npm`, `node`, and `curl` are available on the remote host.
- `node_modules` path for picoclaw: `/home/stas/.npm-global/lib/node_modules/picoclaw`
- `node_modules` path for @cmdop/node: `/home/stas/.npm-global/lib/node_modules/@cmdop/node`
