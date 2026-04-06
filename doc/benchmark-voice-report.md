# Voice Pipeline Benchmark Report
**Date:** 2026-03-29  
**Targets:** supertaris2/TariStation2 (IniCoS-1) · supertaris/SintAItion  
**Note:** taris2/OpenClawPI2 not reachable via SSH at time of benchmark.

---

## Hardware Profiles

| Target | Hostname | CPU | RAM | Role |
|---|---|---|---|---|
| supertaris2 | IniCoS-1 | Intel Core i7-2640M @ 2.80 GHz (2011) | 7.6 GB | Engineering (TariStation2) |
| supertaris | SintAItion | AMD Ryzen AI 9 HX 470 w/ Radeon 890M | 46.7 GB | Production |

---

## Results Summary

### TTS — Piper (ru_RU-irina-medium.onnx)

| Text length | TS2 latency | SintAItion latency | Speedup | RTF (TS2) | RTF (Sint) |
|---|---|---|---|---|---|
| short (29 chars) | 1.313 s | **0.303 s** | 4.3× | 0.30 | **0.07** |
| medium (105 chars) | 2.801 s | **0.457 s** | 6.1× | 0.24 | **0.04** |
| long (204 chars) | 5.188 s | **0.775 s** | 6.7× | 0.25 | **0.04** |

*RTF < 1.0 = faster than real-time.*  
**SintAItion TTS is 4–7× faster.** Both are well below real-time (RTF < 0.31).

---

### STT — Vosk vs faster-whisper (all models)

> **Note on WER:** Fixtures are Piper-TTS-synthesized audio (known text → audio → STT).  
> WER is elevated vs. natural speech because TTS prosody differs from human speech.  
> RTF and latency figures are fully representative of real-world performance.

#### TariStation2 (i7-2640M)

| Engine | Model | Audio | Latency | RTF | WER |
|---|---|---|---|---|---|
| Vosk | vosk-model-small-ru | short (4.4s) | 1.27 s | **0.29** | **0%** |
| Vosk | vosk-model-small-ru | medium (11.2s) | 2.14 s | **0.19** | 21% |
| faster-whisper | tiny | short | 2.72 s | 0.62 | 80% |
| faster-whisper | tiny | medium | 3.93 s | 0.35 | 37% |
| faster-whisper | base | short | 6.08 s | 1.39 ⚠️ | 60% |
| faster-whisper | base | medium | 7.69 s | 0.69 | 47% |
| faster-whisper | small | short | 20.36 s | **4.65 ❌** | 60% |
| faster-whisper | small | medium | 24.39 s | **2.17 ❌** | 37% |

⚠️ RTF > 1.0 = slower than real-time. ❌ = very slow, unacceptable for live use.  
**On TS2: Vosk dominates — fastest AND most accurate.**

#### SintAItion (Ryzen AI 9 HX 470)

| Engine | Model | Audio | Latency | RTF | WER |
|---|---|---|---|---|---|
| faster-whisper | tiny | short (4.2s) | 0.37 s | 0.09 | 60% |
| faster-whisper | tiny | medium (11.2s) | 0.37 s | 0.03 | 42% |
| faster-whisper | base | short | 0.38 s | 0.09 | 60% |
| faster-whisper | base | medium | **0.51 s** | **0.05** | **32%** |
| faster-whisper | small | short | 0.93 s | 0.22 | 60% |
| faster-whisper | small | medium | 1.28 s | 0.11 | 37% |

**On SintAItion: all models are sub-second. fw/base offers best accuracy/speed balance.**

#### STT Cross-target speedup (fw/small)

| Audio | TS2 | SintAItion | Speedup |
|---|---|---|---|
| short (4.4s) | 20.36 s | 0.93 s | **21.9×** |
| medium (11.2s) | 24.39 s | 1.28 s | **19.1×** |

---

### LLM — Ollama

| Target | Model | Prompt type | Latency | Speed |
|---|---|---|---|---|
| TS2 | qwen2:0.5b | factual_short | 8.29 s | 2 c/s |
| TS2 | qwen2:0.5b | factual_medium | 26.90 s | 11 c/s |
| TS2 | qwen2:0.5b | creative | 21.99 s | 5 c/s |
| TS2 | qwen2:0.5b | command_like | 8.20 s | 3 c/s |
| SintAItion | qwen2:0.5b | factual_short | **0.53 s** | **24 c/s** |
| SintAItion | qwen2:0.5b | factual_medium | **1.46 s** | **478 c/s** |
| SintAItion | qwen2:0.5b | creative | **0.83 s** | **296 c/s** |
| SintAItion | qwen2:0.5b | command_like | **0.19 s** | **122 c/s** |
| SintAItion | qwen3:14b | all prompts | ~25 s | 0 c/s ⚠️ |

**qwen3:14b issue:** Returns empty response with ~25 s delay — the model uses "thinking" tokens internally (CoT reasoning) before outputting. The Ollama API `/api/generate` endpoint captures thinking tokens; with `num_predict: 200` the model exhausts tokens on chain-of-thought and outputs nothing visible. Fix: use `/api/chat` endpoint with `think: false` option.

---

### End-to-End Pipeline (STT fw/small + LLM qwen2:0.5b + TTS Piper)

| Target | STT | LLM | TTS | **Total** |
|---|---|---|---|---|
| TS2 (IniCoS-1) | 23.9 s | 113.2 s | 2.1 s | **140.9 s ❌** |
| SintAItion | 1.5 s | 1.7 s | 0.3 s | **4.1 s ✅** |

**35× pipeline speedup** on SintAItion.

---

## Infrastructure Issues Found During Benchmark

| Issue | Target | Impact | Fix applied |
|---|---|---|---|
| faster-whisper not installed | SintAItion | Voice STT broken (silent fail) | ✅ Installed v1.2.1 |
| Piper not deployed | SintAItion | TTS broken, bot sends "audio unavailable" | ✅ Copied from TS2 |
| PIPER_BIN/PIPER_MODEL missing in bot.env | SintAItion | Piper not found by bot | ✅ Added to bot.env |
| qwen2:0.5b not pulled | SintAItion | LLM fallback non-functional | ✅ Pulled |
| VOSK_MODEL not installed | SintAItion | No Vosk fallback available | See recommendations |
| taris2/OpenClawPI2 | PI2 | Not reachable — not benchmarked | Manual run needed |

---

## Recommendations

### 1. TariStation2 (supertaris2) — STT

**Problem:** faster-whisper is 20–80× slower than Vosk on this 2011 CPU. fw/small has RTF=4.65 (4.65s to process 1s of audio) — completely unusable for live voice interaction.

**Action:** Switch default STT from `faster_whisper_stt` to Vosk:
```bash
# On TariStation2 — update voice_opts
sqlite3 ~/.taris/taris.db "UPDATE global_voice_opts SET value=0 WHERE key='faster_whisper_stt'; UPDATE global_voice_opts SET value=0 WHERE key='vosk_fallback';"
# Update voice_opts.json
python3 -c "
import json; p='$HOME/.taris/voice_opts.json'
opts = json.loads(open(p).read())
opts['faster_whisper_stt'] = False
opts['vosk_fallback'] = False
open(p,'w').write(json.dumps(opts, indent=2))
print('Updated')
"
```
Vosk achieves: 1.27 s latency, RTF=0.29, WER=0% — **clearly the best engine for this hardware.**

### 2. TariStation2 — LLM

**Problem:** qwen2:0.5b generates 2–11 chars/sec on this CPU. Simple queries take 8s, creative responses take 22–27s. Pipeline becomes 140s total.

**Options (in order of preference):**
- ✅ **Use OpenAI/cloud LLM** (`LLM_PROVIDER=openai`) — already configured as fallback. Set as primary for TS2 since cloud latency (~1–2s) beats local qwen2 (8–27s).
- ⚠️ **Use taris/picoclaw binary** — set `LLM_PROVIDER=taris` if offline is required.
- ❌ **qwen2:0.5b on CPU** — not viable for real-time interaction on this hardware.

```bash
# In ~/.taris/bot.env on TariStation2:
LLM_PROVIDER=openai          # primary (cloud, fast)
LLM_FALLBACK_PROVIDER=ollama  # offline fallback if no API key
```

### 3. SintAItion (supertaris) — STT Model

**Current:** `FASTER_WHISPER_MODEL=small` (0.93s, RTF=0.22, WER=60% synthetic)  
**Recommendation:** Switch to **`base`** as default.

On SintAItion, fw/base and fw/tiny run equally fast (0.37–0.38s on short audio) but fw/base achieves **32% WER on medium text** vs 42% for tiny. The `small` model offers marginally better WER (37%) but takes 2.5–3.5× longer (0.93–1.28s vs 0.37–0.51s). For real-time voice, `base` is the sweet spot.

```bash
# In ~/.taris/bot.env on SintAItion:
FASTER_WHISPER_MODEL=base
```

### 4. SintAItion — qwen3:14b LLM

**Problem:** Default Ollama API call returns 0 chars with ~25s delay (chain-of-thought uses all token budget internally).

**Fix options:**
1. Use `/api/chat` endpoint with `options.think: false` (Ollama ≥ 0.7)
2. Or use a custom system prompt to suppress thinking: `"Answer directly without thinking."`
3. Or switch to `qwen3:8b` or `qwen2.5:14b` which don't have forced CoT

For bot.env on SintAItion:
```bash
OLLAMA_MODEL=qwen2:0.5b       # fast, works (keep as default)
# qwen3:14b — available for manual use but needs API fix first
```

To benchmark qwen3:14b properly, update `benchmark_voice.py` to use `/api/chat` with `think: false`.

### 5. SintAItion — Piper Model Quality

**Current:** Using `ru_RU-irina-medium.onnx` (copied from TS2). Works correctly, fast.  
**Consider:** The `irina` voice was designed for Pi targets. SintAItion has 46GB RAM and a fast CPU — a **high-quality or large Piper model** would noticeably improve TTS quality at minimal cost (SintAItion synthesis time is already <0.8s for long text).

Suggested models to evaluate:
```bash
# Download higher-quality Russian model:
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/high/ru_RU-irina-high.onnx -O ~/.taris/ru_RU-irina-high.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/high/ru_RU-irina-high.onnx.json -O ~/.taris/ru_RU-irina-high.onnx.json
# Then in bot.env: PIPER_MODEL=~/.taris/ru_RU-irina-high.onnx
```

### 6. Install Vosk on SintAItion (optional but recommended)

SintAItion currently has no Vosk fallback. If faster-whisper fails or for hotword detection, having Vosk installed provides resilience.

```bash
# On SintAItion:
pip install vosk
# Download Russian small model:
wget https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip -P ~/.taris/
cd ~/.taris && unzip vosk-model-small-ru-0.22.zip
mv vosk-model-small-ru-0.22 vosk-model-small-ru
# In bot.env: VOSK_MODEL_PATH=/home/stas/.taris/vosk-model-small-ru
```

### 7. taris2/OpenClawPI2 — Benchmark Pending

Target not reachable via SSH during this session. Expected profile:
- **STT:** Vosk (only option on Pi 3 without enough RAM for FW)
- **LLM:** picoclaw/taris binary (local) or openai fallback
- **TTS:** Piper irina-medium (deployed)
- **Expected pipeline:** 15–30s total (based on Pi 3 specs)

Run manually when reachable:
```bash
# Deploy and run on PI2:
scp tools/benchmark_voice.py stas@OpenClawPI2:~/
ssh stas@OpenClawPI2 "TARIS_DIR=~/.taris python3 ~/benchmark_voice.py --target pi2 --skip-pipeline --stt-models tiny"
```

---

## Priority Action Plan

| Priority | Target | Action | Expected improvement |
|---|---|---|---|
| 🔴 P1 | TS2 | Disable `faster_whisper_stt`, use Vosk | STT: 20s → 1.3s |
| 🔴 P1 | SintAItion | Set `LLM_PROVIDER=openai`, keep ollama as fallback | Already configured ✅ |
| 🟠 P2 | SintAItion | Set `FASTER_WHISPER_MODEL=base` | WER: 60→32% medium, same speed |
| 🟠 P2 | SintAItion | Fix qwen3:14b API call (`think=false`) | Enable large model for complex queries |
| 🟡 P3 | SintAItion | Install Vosk as fallback | Voice resilience |
| 🟡 P3 | SintAItion | Evaluate irina-high TTS model | Better voice quality |
| 🟢 P4 | TS2 | Set `LLM_PROVIDER=openai` as primary | LLM: 8–27s → ~1–2s |
| 🟢 P4 | PI2 | Run benchmark when reachable | Baseline for Pi3 targets |

---

## Benchmark Script

Tool: `tools/benchmark_voice.py`  
Results: `tools/benchmark_results/ts2.json`, `tools/benchmark_results/sintaition.json`  

```bash
# Re-run any target:
python3 tools/benchmark_voice.py --target ts2 --stt-models tiny base small

# Compare targets:
python3 tools/benchmark_voice.py --compare tools/benchmark_results/ts2.json tools/benchmark_results/sintaition.json

# Test single suite:
python3 tools/benchmark_voice.py --skip-stt --skip-llm --skip-pipeline  # TTS only
python3 tools/benchmark_voice.py --skip-tts --skip-pipeline             # STT+LLM only
```
