# Pico Bot — TODO & Optimization Proposals

---

## Voice Pipeline Latency Optimization

### Observed timings (real measurement, March 2026)

| Stage | Time | Status |
|---|---|---|
| Download OGG from Telegram | 0s | ✅ fine |
| Convert OGG → 16kHz PCM (ffmpeg) | 1s | ✅ fine |
| Speech-to-Text (Vosk `vosk-model-small-ru`) | **15s** | ❌ bottleneck |
| LLM response (picoclaw → OpenRouter) | 2s | ✅ fine |
| Text-to-Speech (Piper `ru_RU-irina-medium`) | **40s** | ❌ bottleneck |
| **Total** | **~58s** | ❌ target: <15s |

---

### Quick wins (low effort, low risk)

#### 1. Strip silence before STT — saves ~3–8s on STT
Telegram voice notes often contain 1–5s of silence at start and end.
Use ffmpeg `silenceremove` filter in the OGG→PCM conversion step
to crop silence before passing to Vosk.

```python
# Add silenceremove to the existing ffmpeg command in Convert step:
"-af", "silenceremove=start_periods=1:start_silence=0.3:start_threshold=-40dB"
              ":stop_periods=1:stop_silence=0.5:stop_threshold=-40dB"
```

**Impact:** Reduces audio size fed to Vosk. 5s audio with 2s silence → 3s processed.
Vosk time scales linearly with audio length → expected STT time: ~9s (−40%).


#### 2. Reduce TTS_MAX_CHARS: 400 → 200 — saves ~20s on TTS
Current limit is 400 characters (~50 words). LLM responses often are longer
text wrapped to limit that still takes 40s to synthesize on Pi 3.
At 200 chars (~25 words, ~3 sentences) Piper time halves to ~20s.
Text reply always shows the full response — only the audio is shorter.

```python
# telegram_menu_bot.py, _tts_to_ogg()
TTS_MAX_CHARS = 200   # was 400
```

**Impact:** TTS: ~40s → ~20s. Combined saving with #1: ~58s → ~28s.


#### 3. Lower Vosk sample rate 16kHz → 8kHz — saves ~6s on STT
`vosk-model-small-ru` supports 8kHz (telephone quality). Half the samples =
roughly half the CPU work. Adjust ffmpeg `-ar` and Vosk `KaldiRecognizer` rate.

```python
# constants:
VOICE_SAMPLE_RATE = 8000   # was 16000
# ffmpeg: "-ar", "8000"
# KaldiRecognizer(model, 8000)
```

**Impact:** STT: ~15s → ~8s. Audio quality for speech recognition is acceptable.

---

### Medium effort

#### 4. Keep a persistent Piper subprocess (warm process cache) — saves ~10–15s on TTS
Each TTS call currently does `subprocess.run([PIPER_BIN, ...])` — this cold-starts
Piper and loads the 66MB ONNX model from disk every time.  
A warm persistent process avoids this ~10–15s startup overhead.

**Design:**
- On first TTS call, start Piper with `Popen(stdin=PIPE, stdout=PIPE)`.
- Cache the process object as module-level singleton `_piper_proc`.
- On subsequent calls, write text to `stdin`, read `stdout` for PCM.
- Detect dead process (poll) and restart if needed.

**Caution:** Needs careful EOF / flush handling to avoid deadlock.
Current `subprocess.run` was specifically chosen to avoid the deadlock
that plagued the previous Popen approach — this must be retested carefully.

**Impact:** TTS cold-start: eliminated. Expected TTS total: ~15s → ~5s.


#### 5. Parallel TTS start — overlaps text send and TTS synthesis
Currently the pipeline is sequential:
> LLM done → **send text** → **start TTS** → encode → send audio

Text sending is near-instant. TTS is 20–40s. We can start TTS
in a sub-thread immediately after LLM returns, while text is sent:

```
LLM done ──┬─→ send_message(text)         [~0.1s, main thread]
            └─→ Thread: _tts_to_ogg()     [~20s, background]
                → send_voice() when ready
```

With quick wins #1–#3, text reply appears in ~3s.
Audio arrives ~20s later. This matches normal voice app UX.

**Impact:** User sees text response immediately. Audio follows. No apparent 40s wait.


#### 6. VAD (Voice Activity Detection) pre-filter — saves ~3–5s on STT
Use `webrtcvad` (Python bindings for Google WebRTC VAD, ~50KB, no heavy deps)
to segment incoming PCM into speech-only chunks, skipping silent frames
before passing to Vosk.

```bash
pip3 install webrtcvad
```

```python
import webrtcvad
vad = webrtcvad.Vad(2)   # aggressiveness 0–3
# filter raw_pcm frames, keep only speech frames
```

**Impact:** Complements silence stripping (#1). Removes mid-utterance pauses too.

---

### Architectural options (higher effort)

#### 7. Switch STT engine: Vosk → whisper.cpp (ARM binary)
`whisper.cpp` for aarch64 with the `tiny` model (~75MB) is ~5x faster
than `vosk-model-small-ru` on Pi 3 for Russian, and more accurate.

- Pre-built ARM binary available: https://github.com/ggerganov/whisper.cpp
- `tiny` model: 75MB, ~3–5s for a 10s clip on Pi 3
- Supports Russian via multilingual model
- Drop-in replacement: `subprocess.run(["whisper-cpp", "--model", ...], ...)`

**Trade-off:** Requires downloading ~75MB model; breaks offline availability
if using the OpenAI endpoint variant. The compiled binary approach stays offline.

**Impact:** STT: ~15s → ~4s. Most impactful single change for STT.


#### 8. Switch TTS engine: Piper medium → Piper low quality
`ru_RU-irina-low` model is the same voice at lower quality, ~2x faster synthesis.

```bash
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/low/ru_RU-irina-low.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/low/ru_RU-irina-low.onnx.json
```

**Impact:** TTS: ~20s (after #2) → ~10s. Speech quality still acceptable for bot use.


#### 9. Add user toggle: "Audio on/off"
Many users may prefer text-only replies to avoid the 40s TTS wait.
Add a `🔊 Audio` / `🔇 No audio` toggle button to the back keyboard
in voice session mode. Store preference per `chat_id`.

**Impact:** Users who disable audio get instant responses (LLM 2s only).
Avoids all TTS work for text-only users.

---

### Effort vs. Impact summary

| # | Change | Effort | STT saving | TTS saving | Total time after |
|---|---|---|---|---|---|
| 1 | Strip silence (ffmpeg) | Low | −6s | — | 52s |
| 2 | TTS_MAX_CHARS 400→200 | Low | — | −20s | 38s |
| 3 | Sample rate 16k→8k | Low | −7s | — | 31s |
| 1+2+3 combined | | Low | | | **~28s** |
| 5 | Parallel TTS thread | Medium | — | — | text in **3s**, audio in ~22s |
| 4 | Warm Piper process | Medium | — | −15s | **~13s** |
| 7 | whisper.cpp STT | High | −11s | — | |
| 8 | Piper low model | Medium | — | −10s | |
| 1+2+3+4+5 | All quick+medium | Low/Med | | | text in **2s**, audio in **~8s** |

**Recommended implementation order:**
1. `#2` (TTS_MAX_CHARS) — one-liner, zero risk
2. `#1` (silence strip) — one ffmpeg flag, test accuracy
3. `#3` (8kHz) — two constant changes, test recognition quality
4. `#5` (parallel TTS thread) — user experience improvement
5. `#4` (warm Piper process) — biggest TTS gain, needs careful testing
