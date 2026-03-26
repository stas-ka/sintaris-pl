# Device Configuration Backup — OpenClawPI2 (PI2)
## Last updated: 2026-03-09

Raspberry Pi 3 **B** Rev 1.2 running Raspberry Pi OS Bookworm (aarch64).  
Hostname: `OpenClawPI2`, user: `stas`, CPU: 4× Cortex-A53 @ 1200 MHz, RAM: 906 MB.

> **Note:** PI2 is a second/standby device running the same bot software as PI1 with a different `BOT_TOKEN`. Config is kept in sync with PI1. There is no standalone voice assistant on PI2.

---

## Files in this backup

| File | Source on Pi | Notes |
|---|---|---|
| `systemd/picoclaw-telegram.service` | `/etc/systemd/system/` | Identical to PI1 |
| `modprobe.d/usb-audio-fix.conf` | `/etc/modprobe.d/` | Identical to PI1 |

> PI2 does **not** have a crontab (no gmail digest), no picoclaw-config.json (uses same defaults), no voice service.

---

## Installed software versions (2026-03-09)

Identical to PI1. See [../device/README.md](../device/README.md) for the complete table.

| Component | Version |
|---|---|
| OS | Raspberry Pi OS Bookworm 64-bit |
| Kernel | 6.12.47+rpt-rpi-v8 |
| picoclaw (Go binary) | 0.2.0 |
| Python | **3.13.5** |
| vosk | 0.3.45 |
| webrtcvad-wheels | 2.0.14 |
| pyTelegramBotAPI | 4.31.0 |
| requests | 2.32.3 |
| Piper TTS | 2023.11.14-2 (aarch64) |
| Piper voice | ru_RU-irina-medium (61 MB) |
| Vosk model | vosk-model-small-ru-0.22 (48 MB) |
| Whisper model | ggml-base.bin (142 MB), ggml-tiny.bin (75 MB) |
| whisper-cpp binary | /usr/local/bin/whisper-cpp |
| telegram_menu_bot.py | BOT_VERSION **2026.3.24** |

---

## Active voice optimization flags (voice_opts.json)

```json
{
  "silence_strip": false,
  "low_sample_rate": false,
  "warm_piper": true,
  "parallel_tts": false,
  "user_audio_toggle": false,
  "tmpfs_model": true,
  "vad_prefilter": false,
  "whisper_stt": true,
  "piper_low_model": false,
  "persistent_piper": false
}
```

---

## Runtime state files (auto-created, not in backup)

These files are created automatically by `telegram_menu_bot.py` at runtime and are identical in purpose to PI1. Not committed to git.

| File | Description |
|---|---|
| `~/.sintaris-pl/voice_opts.json` | Voice optimization flags |
| `~/.sintaris-pl/last_notified_version.txt` | Admin notification tracking |
| `~/.sintaris-pl/pending_tts.json` | TTS orphan-cleanup tracker |
| `~/.sintaris-pl/users.json` | Dynamically approved guest users |
| `~/.sintaris-pl/registrations.json` | User registration records |

---

## Active services (2026-03-09)

```
picoclaw-telegram.service  — enabled, active (running)
picoclaw-voice.service     — not installed on PI2
picoclaw-gateway.service   — inactive (not enabled, not in use)
```

---

## System settings (2026-03-09)

| Setting | Value | Notes |
|---|---|---|
| Boot target | `multi-user.target` | No desktop |
| GPU memory | 76M | Recommendation: reduce to 16M (not yet applied) |
| CPU governor | `ondemand` | Recommendation: `performance` (not yet applied) |
| Swap | ~905 MB (zram, lz4) | Only ~5 MB used normally |
| Gmail crontab | **None** | No digest configured on PI2 |
| I2S HAT | Not connected | picoclaw-voice not installed |

---

## Differences from PI1

| Item | PI2 (OpenClawPI2) | PI1 (OpenClawPI) |
|---|---|---|
| Hardware | Pi 3 **B** Rev 1.2 | Pi 3 **B+** Rev 1.3 |
| CPU speed | **1200 MHz** | 1400 MHz |
| Bot token | PI2-specific | PI1-specific |
| Gmail crontab | **None** | Yes (`0 19 * * *`) |
| Swap | ~905 MB zram | ~2.9 GB swap partition |
| Voice service | Not installed | Installed but disabled |
| ONNX cold read | **380 MB/s** (better SD card) | 105 MB/s |

> Despite the slower CPU, PI2 has a faster SD card — cold ONNX reads are ~3.6× faster than PI1.  
> After warm-up, TTS performance on both is identical (~9 chars/s).

---

## Boot config active entries (/boot/firmware/config.txt)

Same as PI1 — standard Bookworm defaults, no I2S overlay:

```
dtparam=audio=on
camera_auto_detect=1
display_auto_detect=1
auto_initramfs=1
dtoverlay=vc4-kms-v3d
max_framebuffers=2
disable_fw_kms_setup=1
arm_64bit=1
disable_overscan=1
arm_boost=1
```

---

## Restoring config on a new PI2 device

```bash
# 1. Restore bot service:
sudo cp systemd/picoclaw-telegram.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable picoclaw-telegram
sudo systemctl start  picoclaw-telegram

# 2. Restore modprobe fix:
sudo cp modprobe.d/usb-audio-fix.conf /etc/modprobe.d/

# 3. Ensure bot.env exists with PI2-specific BOT_TOKEN + ALLOWED_USERS + ADMIN_USERS
#    See .credentials/.pico_env for actual values

# 4. Install dependencies:
sudo apt install -y ffmpeg libopenblas-dev
pip3 install --break-system-packages pyTelegramBotAPI vosk webrtcvad-wheels requests requests-oauthlib

# 5. Install picoclaw + Whisper + Piper as per src/setup/install.sh
```
