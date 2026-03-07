# Picoclaw Voice Assistant — Architecture

## Overview

A fully offline Russian voice interface running on a Raspberry Pi 3 B+. The pipeline converts spoken Russian into text, routes it to an LLM via picoclaw, then speaks the LLM response back in Russian — all locally except the LLM call.

```
Microphone (USB / I2S HAT)
      │
      ▼
 [pw-record]   ← PipeWire subprocess (S16_LE, 16 kHz, mono)
      │              fallback: parec (PulseAudio compat layer)
      ▼
 [Vosk STT]    ← vosk-model-small-ru-0.22 (48 MB, offline, Kaldi-based)
      │              streaming decode, 250 ms chunks
      ▼
 Hotword gate  ← fuzzy SequenceMatcher match on "пико / пика / пике / пик"
      │              threshold: 0.75 similarity ratio
      ▼
 [Vosk STT]    ← same model, fresh recognizer for the command phrase
      │              stops on 2 s silence or 15 s max
      ▼
 [picoclaw]    ← CLI subprocess: picoclaw agent -m "<text>"
      │              binary: /usr/bin/picoclaw (sipeed/picoclaw v0.2.0)
      ▼
 [OpenRouter]  ← HTTPS call to openrouter.ai (cloud, configurable model)
      │              default: openrouter/openai/gpt-4o-mini
      ▼
 [Piper TTS]   ← ru_RU-irina-medium.onnx (ONNX Runtime, 66 MB, offline)
      │              output: raw S16_LE PCM at 22050 Hz
      ▼
   [aplay]     ← ALSA playback → Pi 3.5 mm jack / USB speaker
```

---

## Component Details

### 1. Audio Capture — PipeWire / pw-record

| Property | Value |
|---|---|
| Backend | PipeWire (default on Raspberry Pi OS Bookworm) |
| Capture command | `pw-record --rate=16000 --channels=1 --format=s16 -` |
| Fallback | `parec --rate=16000 --channels=1 --format=s16le` |
| Chunk size | 4000 frames (250 ms at 16 kHz) |
| Required env vars | `XDG_RUNTIME_DIR=/run/user/1000`, `PIPEWIRE_RUNTIME_DIR=/run/user/1000`, `PULSE_SERVER=unix:/run/user/1000/pulse/native` |
| Source selection | Configurable via `AUDIO_TARGET` env var (see below) |

**`AUDIO_TARGET` values:**

| Value | Behavior |
|---|---|
| `auto` (default) | Let PipeWire select the default source |
| `webcam` | Use Philips SPC 520 USB webcam mic node |
| `<node name>` | Any PipeWire source node (from `pactl list sources short`) |

> **Known issue**: Philips SPC 520/525NC USB webcam mic fails on Pi 3's DWC_OTG USB controller — isochronous transfers complete the USB handshake but deliver zero data. `implicit_fb=1` modprobe flag does not resolve this. Use a standard USB microphone or the I2S RB-TalkingPI HAT instead.

---

### 2. Speech-to-Text — Vosk

| Property | Value |
|---|---|
| Library | `vosk` 0.3.45 (Python binding for Kaldi-based ASR) |
| Model | `vosk-model-small-ru-0.22` (48 MB) |
| Model path | `/home/stas/.picoclaw/vosk-model-small-ru/` |
| Language | Russian |
| Mode | Streaming (real-time chunk processing) |
| Word timestamps | Enabled (`SetWords(True)`) |
| CPU usage | ~40–60% on Pi 3 single core during recognition |

**Why not the full model?**  
`vosk-model-ru-0.42` (1.5 GB) runs out of RAM on Pi 3 (1 GB). The small model handles short voice commands well.

---

### 3. Hotword Detection

Implemented in `voice_assistant.py` using Python's `difflib.SequenceMatcher`:

```
text → split into words → fuzzy match each word against hotword list
```

- Hotwords: `пико`, `пика`, `пике`, `пик`, `привет пико`
- Threshold: `0.75` similarity ratio
- Also checks exact substring before fuzzy match
- Bigram matching for two-word hotwords ("привет пико")

The hotword loop runs `pw-record` continuously at 16 kHz. When triggered:
1. Hotword stream is killed
2. A beep plays (`/usr/share/sounds/alsa/Front_Left.wav`)
3. A fresh Vosk recognizer records the command phrase
4. Stream restarts after the response is spoken

---

### 4. LLM — picoclaw + OpenRouter

| Property | Value |
|---|---|
| Binary | `/usr/bin/picoclaw` (sipeed/picoclaw v0.2.0 aarch64 deb) |
| Invocation | `picoclaw agent -m "<recognized text>"` |
| LLM provider | OpenRouter (`openrouter.ai`) |
| Default model | `openrouter/openai/gpt-4o-mini` |
| Config file | `/home/stas/.picoclaw/config.json` |
| Timeout | 60 seconds |

picoclaw wraps the OpenRouter API call, manages the model config, and returns plain text response to stdout. The voice assistant captures that stdout and pipes it to TTS.

**config.json structure (minimal):**
```json
{
  "model_list": [
    {
      "model_name": "openrouter-auto",
      "model": "openrouter/openai/gpt-4o-mini",
      "api_key": "sk-or-..."
    }
  ],
  "agents": {
    "defaults": { "model": "openrouter-auto" }
  }
}
```

---

### 5. Text-to-Speech — Piper

| Property | Value |
|---|---|
| Engine | [Piper TTS](https://github.com/rhasspy/piper) (ONNX Runtime) |
| Binary | `/usr/local/bin/piper` (wrapper calling `/usr/local/share/piper/piper`) |
| Voice model | `ru_RU-irina-medium.onnx` (66 MB, natural female Russian) |
| Model path | `/home/stas/.picoclaw/ru_RU-irina-medium.onnx` |
| Output format | Raw PCM S16_LE at 22050 Hz mono |
| Playback | `aplay --rate=22050 --format=S16_LE --channels=1 -` |
| Latency | ~1–3 seconds per sentence on Pi 3 (RTF ≈ 0.83) |
| RAM usage | ~150 MB peak |

**Why Piper instead of Silero?**  
Silero TTS requires PyTorch (~2 GB download, ~1.5 GB RAM at runtime). Pi 3 has 1 GB RAM total — impossible. Piper uses ONNX Runtime with bundled shared libs, no Python dependencies, runs comfortably on Pi 3.

**Pipeline:**
```
echo "text" → piper stdin  →  piper stdout (raw PCM)  →  aplay stdin  →  speaker
```
Piper and aplay run as chained subprocesses with a pipe between them.

---

### 6. Telegram Gateway (parallel channel)

The picoclaw gateway also handles Telegram messages independently of the voice assistant:

| Property | Value |
|---|---|
| Bot | `@smartpico_bot` |
| Service | `picoclaw-gateway.service` (systemd) |
| LLM | Same OpenRouter config |
| Allowed user | Chat ID `994963580` |

---

### 7. Telegram Menu Bot (`telegram_menu_bot.py`)

Interactive Telegram bot that exposes three operating modes via inline keyboard:

| Mode | Button | Description |
|---|---|---|
| Mail Digest | 📧 Mail Digest | Runs `gmail_digest.py --stdout` and returns the summary inline |
| Free Chat | 💬 Free Chat | Any text sent goes directly to `picoclaw agent -m` and returns the LLM response |
| System Chat | 🖥 System Chat | Like Free Chat but prepends a system-admin context prompt |

| Property | Value |
|---|---|
| Script | `/home/stas/.picoclaw/telegram_menu_bot.py` |
| Service | `picoclaw-telegram.service` (systemd) |
| Bot | `@smartpico_bot` |
| Token source | `/home/stas/.picoclaw/bot.env` (loaded via `EnvironmentFile=`) |
| Allowed user | `ALLOWED_USER` env var (chat ID) |
| LLM backend | `picoclaw agent -m` subprocess (same config as gateway) |

**Relationship to the gateway:**  
`picoclaw-gateway.service` handles Telegram natively via the picoclaw Go binary (currently with `"enabled": false` in config.json — disabled in favour of the menu bot). `picoclaw-telegram.service` runs the menu bot independently and gives a structured, button-driven UX instead of raw chat.

---

### 8. Gmail Digest Agent (cron job)

Daily email digest sent to Telegram at 19:00 Pi local time:

| Property | Value |
|---|---|
| Script | `/home/stas/.picoclaw/gmail_digest.py` |
| Cron | `0 19 * * *` |
| IMAP | `stas.ulmer@gmail.com` via App Password |
| Folders | INBOX + `[Google Mail]/Spam` (last 24 h, max 50 each) |
| Output | Telegram `@smartpico_bot` → chat `994963580` |

---

## Process Hierarchy (at runtime)

```
systemd
  ├── picoclaw-gateway.service
  │     └── /usr/bin/picoclaw gateway
  │
  ├── picoclaw-telegram.service
  │     └── /usr/bin/python3 telegram_menu_bot.py
  │           └── /usr/bin/picoclaw agent -m "..." [subprocess, per message]
  │           └── /usr/bin/python3 gmail_digest.py --stdout [subprocess, on demand]
  │
  └── picoclaw-voice.service
        └── /usr/bin/python3 voice_assistant.py
              ├── pw-record [subprocess, stdout pipe] ← continuous hotword listen
              ├── pw-record [subprocess, stdout pipe] ← command recording (transient)
              ├── piper     [subprocess, stdin/stdout pipe] ← TTS synthesis
              └── aplay     [subprocess, stdin pipe]        ← audio output
```

---

## File Layout on Pi

```
/home/stas/.picoclaw/
  voice_assistant.py          ← main voice daemon
  telegram_menu_bot.py        ← interactive Telegram menu bot
  config.json                 ← picoclaw + LLM config (API key here)
  gmail_digest.py             ← daily email digest agent
  bot.env                     ← BOT_TOKEN + ALLOWED_USER (loaded by systemd EnvironmentFile=)
  vosk-model-small-ru/        ← 48 MB STT model directory
  ru_RU-irina-medium.onnx     ← 66 MB Piper TTS voice model
  ru_RU-irina-medium.onnx.json← Piper voice metadata
  voice.log                   ← voice assistant log (append)
  digest.log                  ← Gmail digest log
  last_digest.txt             ← last digest output (read by menu bot)

/usr/local/bin/piper          ← Piper wrapper script
/usr/local/share/piper/       ← Piper binary + bundled libs (libonnxruntime, etc.)
  piper
  libpiper_phonemize.so.1
  libonnxruntime.so.1.14.1
  ...

/usr/bin/picoclaw             ← picoclaw Go binary (from .deb)
/usr/bin/picoclaw-launcher
/usr/bin/picoclaw-launcher-tui

/etc/systemd/system/
  picoclaw-gateway.service
  picoclaw-voice.service
  picoclaw-telegram.service

/etc/modprobe.d/
  usb-audio-fix.conf          ← options snd-usb-audio implicit_fb=1
```

---

## Configuration Reference (`voice_assistant.py` CONFIG)

| Key | Default | Env Override | Description |
|---|---|---|---|
| `vosk_model_path` | `/home/stas/.picoclaw/vosk-model-small-ru` | `VOSK_MODEL_PATH` | Vosk model directory |
| `piper_bin` | `/usr/local/bin/piper` | `PIPER_BIN` | Piper TTS binary path |
| `piper_model` | `/home/stas/.picoclaw/ru_RU-irina-medium.onnx` | `PIPER_MODEL` | Piper voice model |
| `picoclaw_bin` | `/usr/bin/picoclaw` | `PICOCLAW_BIN` | picoclaw binary |
| `pipewire_runtime_dir` | `/run/user/1000` | — | PipeWire runtime socket dir |
| `audio_target` | `auto` | `AUDIO_TARGET` | Microphone selection |
| `sample_rate` | `16000` | — | Audio capture rate (Hz) |
| `chunk_size` | `4000` | — | Frames per processing chunk |
| `hotwords` | `["пико", "пика", ...]` | — | Wake words list |
| `hotword_threshold` | `0.75` | — | Fuzzy match sensitivity |
| `silence_timeout` | `2.0` | — | Seconds of silence to end recording |
| `max_phrase_duration` | `15.0` | — | Max command recording length (s) |
| `min_phrase_chars` | `3` | — | Minimum chars to accept STT result |
