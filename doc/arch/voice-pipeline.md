# Taris — Voice Pipeline Architecture

**Version:** `2026.3.28`  
→ Architecture index: [architecture.md](../architecture.md)

---

## 2. Standalone Voice Assistant Components

### 2.1 Audio Capture — PipeWire / pw-record

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

### 2.2 Speech-to-Text — Vosk

| Property | Value |
|---|---|
| Library | `vosk` 0.3.45 (Python binding for Kaldi-based ASR) |
| Model | `vosk-model-small-ru-0.22` (48 MB) |
| Model path | `/home/stas/.taris/vosk-model-small-ru/` |
| Language | Russian |
| Mode | Streaming (real-time chunk processing) |
| Word timestamps | Enabled (`SetWords(True)`) |
| CPU usage | ~40–60% on Pi 3 single core during recognition |

**Why not the full model?** `vosk-model-ru-0.42` (1.5 GB) runs out of RAM on Pi 3 (1 GB). The small model handles short voice commands well.

### 2.3 Hotword Detection

Implemented in `voice_assistant.py` using Python's `difflib.SequenceMatcher`:

- Hotwords: `пико`, `пика`, `пике`, `пик`, `привет пико`
- Threshold: `0.75` similarity ratio
- Also checks exact substring before fuzzy match
- Bigram matching for two-word hotwords ("привет пико")

When triggered: hotword stream killed → beep plays → fresh Vosk recognizer records command phrase → stream restarts after response is spoken.

### 2.4 LLM — taris + OpenRouter

| Property | Value |
|---|---|
| Binary | `/usr/bin/picoclaw` (sipeed/picoclaw v0.2.0 aarch64 deb) |
| Invocation | `taris agent -m "<recognized text>"` |
| LLM provider | OpenRouter (`openrouter.ai`) |
| Default model | `openrouter/openai/gpt-4o-mini` |
| Config file | `/home/stas/.taris/config.json` |
| Timeout | 60 seconds |

### 2.5 Text-to-Speech — Piper

| Property | Value |
|---|---|
| Engine | Piper TTS (ONNX Runtime) |
| Binary | `/usr/local/bin/piper` (wrapper calling `/usr/local/share/piper/piper`) |
| Voice model | `ru_RU-irina-medium.onnx` (66 MB, natural female Russian) |
| Output format | Raw PCM S16_LE at 22050 Hz mono |
| Latency | ~1–3 s per sentence on Pi 3 (RTF ≈ 0.83) |
| RAM usage | ~150 MB peak |

**Why Piper instead of Silero?** Silero TTS requires PyTorch (~2 GB download, ~1.5 GB RAM). Pi 3 has 1 GB total — impossible. Piper uses ONNX Runtime with bundled shared libs, no Python dependencies.

---

## 5. Voice Conversation Architecture (Telegram)

### 5.1 Incoming Voice Pipeline (Telegram)

Voice messages received as OGG Opus from Telegram; processed unconditionally independent of `_user_mode`.

```
Telegram OGG Opus voice note
      │
      ▼
 bot.get_file() + bot.download_file()      ← Telegram API
      │
      ▼
 [ffmpeg] OGG → 16 kHz mono S16LE PCM
      │   -ar 16000 -ac 1 -f s16le
      │   + silenceremove filter  (if silence_strip opt)
      │   + -ar 8000              (if low_sample_rate opt)
      │
      ▼
 [VAD filter]  (if vad_prefilter opt)      ← webrtcvad: strip non-speech frames
      │
      ▼
 STT:
  ├── [Vosk]   default              ← vosk-model-small-ru (48 MB, offline)
  │            KaldiRecognizer → transcript + [?word] confidence strip
  └── [Whisper] if whisper_stt opt  ← whisper-cpp ggml-base.bin (142 MB)
                better WER, ~2× slower; hallucination guard discards
                sparse output (< 2 words/s) and falls back to Vosk
      │
      ▼
 SECURITY_PREAMBLE + lang hint
 + _wrap_user_input(transcript)            ← L2: [USER]…[/USER]
      │
      ▼
 _ask_taris(prompt, timeout=60)         ← subprocess: taris agent -m
      │
      ▼
 bot.send_message()                        ← text reply shown immediately
      │
      ▼
 [if audio not muted]
 _tts_to_ogg(response[:TTS_MAX_CHARS])
      │
      ▼
 bot.send_voice()                          ← OGG Opus voice reply
```

**Key voice constants** (from `bot_config.py`):

| Constant | Value | Meaning |
|---|---|---|
| `VOICE_SAMPLE_RATE` | `16000` | STT decode rate (Hz) |
| `TTS_MAX_CHARS` | `600` | Real-time voice chat cap (~25 s on Pi 3 B+) |
| `TTS_CHUNK_CHARS` | `1200` | Per-part "Read aloud" cap (~55 s on Pi 3 B+) |
| `VOICE_TIMING_DEBUG` | `false` | Emit per-stage latency log lines when `true` |

### 5.2 TTS Chunking — "Read Aloud" Feature

Long texts (notes, digest, calendar events) are split at sentence boundaries and sent as N sequential voice messages.

```
_handle_note_read_aloud(chat_id, slug)
  → load note text
  → _split_for_tts(text, max_chars=TTS_CHUNK_CHARS)
  │     splits on ". " / "! " / "? " / "\n" boundaries
  │     chunks ≤ TTS_CHUNK_CHARS chars each
  → for i, chunk in enumerate(chunks):
        ogg = _tts_to_ogg(chunk, _trim=False)
        bot.send_voice(chat_id, ogg,
            caption=f"🔊 {title} ({i+1}/{n})")
```

Same pattern used by `_handle_digest_tts()` and `_handle_cal_confirm_tts()`.

### 5.3 TTS Pipeline Detail

`_tts_to_ogg(text, _trim=True)`:

```
text
  │ if _trim: truncate to TTS_MAX_CHARS
  ▼
_escape_tts(text)          ← strip emoji, Markdown, ANSI
  ▼
_piper_model_path()        ← priority: tmpfs → low → medium
  ▼
piper subprocess:
  stdin  ← text (UTF-8)
  stdout → raw PCM S16LE 22050 Hz
  (if persistent_piper: reuse warm subprocess)
  ▼
ffmpeg subprocess:
  stdin  ← raw PCM
  stdout → OGG Opus 24 kbit/s
  ▼
return bytes (OGG)
```

**Piper model priority chain:**
```
tmpfs_model ON  AND  /dev/shm/piper/...onnx exists  →  tmpfs (fastest)
    ↓ else
piper_low_model ON  AND  ~/.taris/ru_RU-irina-low.onnx exists  →  low model
    ↓ else
default:  ~/.taris/ru_RU-irina-medium.onnx
```

### 5.4 STT — Vosk vs Whisper

| Property | Vosk (default) | Whisper (opt: `whisper_stt=true`) |
|---|---|---|
| Model | `vosk-model-small-ru` (48 MB) | `ggml-base.bin` (142 MB) |
| Latency on Pi 3 | ~15 s / 5 s audio | ~30–35 s / 5 s audio |
| WER (Russian) | ~25% | ~18% |
| Confidence filter | strips `[?word]` → `word` | n/a |
| Hallucination guard | n/a | discards output with < 2 words/s; falls back to Vosk |
| Parallel threads | single-threaded | `--threads 4` (all Pi 3 cores) |
