# Device Configuration Backup — OpenClawPI
## Captured: 2026-03-07

Raspberry Pi 3 B+ running Raspberry Pi OS Bookworm (aarch64).  
Hostname: `OpenClawPI`, user: `stas`.

---

## Files in this backup

| File | Source on Pi | Notes |
|---|---|---|
| `picoclaw-config.json` | `~/.picoclaw/config.json` | API keys replaced with `${VAR}` placeholders |
| `crontab` | `crontab -l` (user stas) | Gmail digest cron at 19:00 |
| `systemd/picoclaw-gateway.service` | `/etc/systemd/system/` | picoclaw LLM gateway |
| `systemd/picoclaw-voice.service` | `/etc/systemd/system/` | Russian voice assistant |
| `systemd/picoclaw-telegram.service` | `/etc/systemd/system/` | Telegram menu bot |
| `modprobe.d/usb-audio-fix.conf` | `/etc/modprobe.d/` | USB audio quirk fix |

---

## Installed software versions (2026-03-07)

| Component | Version |
|---|---|
| OS | Raspberry Pi OS Bookworm 64-bit |
| picoclaw (Go binary) | 0.2.0 (git: 8207c1c, built 2026-02-28) |
| Python | 3.11+ |
| vosk | 0.3.45 |
| pyTelegramBotAPI | 4.31.0 |
| sounddevice | 0.5.5 |
| numpy | 2.2.4 |
| Piper TTS | 2023.11.14-2 (aarch64) |
| Piper voice | ru_RU-irina-medium |
| Vosk model | vosk-model-small-ru-0.22 |

---

## Active services

```
picoclaw-gateway.service   — active (running)
picoclaw-voice.service     — active (running)
picoclaw-telegram.service  — active (running)
```

---

## boot config dtoverlay entries

```
dtparam=audio=on
dtoverlay=vc4-kms-v3d
dtoverlay=dwc2,dr_mode=host
```

Note: `dtparam=i2s=on` and `dtoverlay=googlevoicehat-soundcard` are **commented out** — I2S HAT is not currently connected. Enable them in `/boot/firmware/config.txt` when RB-TalkingPI is attached.

---

## Restoring config on a new device

```bash
# 1. Copy config with real API keys filled in:
cp picoclaw-config.json ~/.picoclaw/config.json
# Edit: replace ${OPENROUTER_API_KEY} and ${TELEGRAM_BOT_TOKEN} with real values

# 2. Restore crontab:
crontab crontab

# 3. Install systemd services:
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable picoclaw-gateway picoclaw-voice picoclaw-telegram
sudo systemctl start  picoclaw-gateway picoclaw-voice picoclaw-telegram

# 4. Restore modprobe fix:
sudo cp modprobe.d/usb-audio-fix.conf /etc/modprobe.d/
```
