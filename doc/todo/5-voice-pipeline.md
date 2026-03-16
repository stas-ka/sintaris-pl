# Voice Pipeline — Baseline & Improvements

**Reference:** `doc/hardware-performance-analysis.md` for hardware upgrade paths

---

## Baseline Measurements (Pi 3 B+, all opts OFF)

| Stage | Time | Status |
|---|---|---|
| OGG → PCM (ffmpeg) | ~1 s | ✅ |
| STT (Vosk small-ru) | **~15 s** | ❌ bottleneck |
| LLM (OpenRouter) | ~2 s | ✅ |
| TTS cold load (Piper medium, microSD) | **~15 s** | ❌ bottleneck |
| TTS inference (~600 chars) | **~80–95 s** | ❌ bottleneck |
| **Total** | **~115 s** | ❌ target: <15 s |

With `persistent_piper` + `tmpfs_model` + `piper_low_model` all ON: estimated **~20–25 s**.

---

## §5.2 TTS Bottleneck — Fix Plan

**Root cause:** Cold Piper ONNX load (~15 s) + ONNX inference at `TTS_MAX_CHARS=600` (~80–95 s) on Pi 3 B+.

| Priority | Fix | Where | Expected gain |
|---|---|---|---|
| 🔴 | Add `TTS_VOICE_MAX_CHARS = 300`; use for real-time path | `bot_config.py`, `_tts_to_ogg()` | TTS −50% |
| 🔴 | Document `persistent_piper` + `tmpfs_model` as recommended defaults | Admin panel help | −35 s |
| 🟡 | Enable `piper_low_model` | Voice Opts | −13 s |
| 🟢 | Auto-truncate at sentence boundary ≤ 300 chars | `_tts_to_ogg()` | smooth cuts |

**Checklist:**
- [ ] Add `TTS_VOICE_MAX_CHARS = 300` to `bot_config.py`
- [ ] Use it in `_tts_to_ogg()` when `_trim=True`
- [ ] Document recommended opt settings in admin panel help or UI tooltip

---

## §5.3 STT/TTS Detailed Improvements Backlog

### STT issues
- [ ] Vosk (180 MB) + Piper (150 MB) simultaneously — only ~310 MB headroom on Pi 3; investigate memory pressure during voice reply
- [ ] Whisper temp WAV written to SD-backed `/tmp` — move to `/dev/shm` (−0.5 s per call)
- [ ] Hallucination threshold (2 words/s) fixed — needs per-length tuning for short commands
- [ ] Add `STT_CONF_THRESHOLD` config constant for Vosk confidence strip (currently implicit in `_CONF_MARKER_RE`)

### TTS issues
- [ ] "Read aloud" 1200-char chunks → ~180–200 s synthesis on Pi 3; implement progressive delivery (send first part while generating rest)
- [ ] OGG Opus bitrate 24 kbit/s hardcoded — expose as voice opt (16/24/32 kbit/s)
- [ ] Two `subprocess.run()` calls (Piper → ffmpeg) adds ~0.1 s — use `Popen` pipe instead

### Measurement improvements (`voice_timing_debug`)
- [ ] Add ffmpeg OGG→PCM wall time (currently missing from debug output)
- [ ] Split Piper timer: model load time vs inference time
- [ ] Log char count going into Piper (correlate with inference time)
- [ ] Collect 10-run timing sample per STT/TTS path on Pi 3 B+
