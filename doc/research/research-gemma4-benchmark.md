# Gemma 4 Benchmarking Analysis for Taris

**Date:** 2026-04-04
**Status:** Research & benchmark preparation — ready for on-device testing
**Related issue:** Benchmarking of Gemma 4 LLM models

---

## 1. Gemma 4 Model Family Overview

Google DeepMind released Gemma 4 on 2026-03-31 (Apache 2.0 license). Built from Gemini 3 research, it is a multimodal LLM family with 140+ languages and four model sizes:

| Model | Architecture | Total Params | Active/Token | Layers | Context | Modalities | VRAM (4-bit) | VRAM (BF16) |
|---|---|---|---|---|---|---|---|---|
| **E2B** | Dense+PLE | 5.1B | 2.3B | 35 | 128K | Text+Image+**Audio** | **3.2 GB** | 9.6 GB |
| **E4B** | Dense+PLE | 8B | 4.5B | 42 | 128K | Text+Image+**Audio** | **5 GB** | 15 GB |
| **31B** | Dense | 30.7B | 30.7B | 60 | 256K | Text+Image | 17.4 GB | 58.3 GB |
| **26B A4B** | MoE | 25.2B | 3.8B | 30 | 256K | Text+Image | 15.6 GB | 48 GB |

### Key Architectural Features

- **PLE (Per-Layer Embeddings):** E2B/E4B use separate small embedding tables per decoder layer — enables inference under 1.5 GB VRAM at 4-bit quantization
- **Hybrid Attention:** Local sliding window (512 tokens for E2B/E4B, 1024 for 31B/26B) + global full-context layers interleaved
- **Thinking Mode:** Built-in chain-of-thought (`<|think|>`) — must be disabled for latency-sensitive tasks (same as qwen3.5)
- **MoE (26B A4B):** 128 total experts + 1 shared, 8 activated per token — speed of a 4B dense model with quality near 30B
- **Audio Encoder (~300M params):** E2B and E4B only, supports ASR and speech translation, max 30-second audio

### Ollama Tags

```bash
ollama pull gemma4           # 31B (default)
ollama pull gemma4:e4b       # Edge 4B
ollama pull gemma4:e2b       # Edge 2B
# gemma4:26b-a4b may be available as a community GGUF
```

---

## 2. Hardware Compatibility Analysis

### 2.1 SintAItion (TariStation1)

| Component | Specification |
|---|---|
| CPU | AMD Ryzen AI (Zen4/Zen5, 8+ cores) |
| GPU | AMD Radeon 890M (gfx1150, RDNA3.5, 16 GB shared VRAM) |
| RAM | 48 GB |
| Storage | NVMe, 762 GB free |
| Ollama | ROCm GPU acceleration, HSA_OVERRIDE_GFX_VERSION=11.0.3 |

**Which Gemma 4 models fit on SintAItion?**

| Model | 4-bit VRAM | Fits in 16 GB iGPU? | 8-bit VRAM | Full (BF16) | Recommendation |
|---|---|---|---|---|---|
| **E2B** | 3.2 GB | **Yes** | 4.6 GB | 9.6 GB | **Excellent fit** — leaves room for other services |
| **E4B** | 5 GB | **Yes** | 7.5 GB | 15 GB | **Good fit** at 4-bit; 8-bit also OK |
| **31B** | 17.4 GB | **No** (exceeds 16 GB iGPU) | 30.4 GB | 58.3 GB | **Not recommended** — would spill to system RAM |
| **26B A4B** | 15.6 GB | **Marginal** (tight fit, KV cache overflow) | 25 GB | 48 GB | **Risky** — only 3.8B active params but 15.6 GB weights |

**Recommendation for SintAItion:**
- **Primary candidate:** `gemma4:e4b` (4-bit) — best quality-to-VRAM ratio
- **Secondary candidate:** `gemma4:e2b` (4-bit) — if E4B is too slow or VRAM-constrained
- **Not viable:** 31B (exceeds GPU memory, CPU-only would be very slow)
- **Experimental:** 26B A4B (borderline fit, only 3.8B active params — could match E4B speed with higher quality)

### 2.2 TariStation2 (IniCoS-1)

| Component | Specification |
|---|---|
| CPU | Intel Core i7-2640M @ 2.80 GHz |
| RAM | 7.6 GB |
| GPU | None usable for ML |
| Ollama | CPU-only |

**Which Gemma 4 models fit on TariStation2?**

| Model | 4-bit VRAM | Fits in 7.6 GB RAM? | Expected speed (CPU) | Recommendation |
|---|---|---|---|---|
| **E2B** | 3.2 GB | **Yes** (leaves ~4 GB for OS) | ~2-5 t/s (estimated) | **Only viable option** |
| **E4B** | 5 GB | **Tight** (~2.6 GB left for OS) | ~1-2 t/s (estimated) | **Marginal** — may OOM under load |
| **31B** | 17.4 GB | **No** | N/A | Not possible |
| **26B A4B** | 15.6 GB | **No** | N/A | Not possible |

**Recommendation for TariStation2:**
- **Only viable:** `gemma4:e2b` (4-bit) — comparable to current qwen2:0.5b in memory but much more capable
- **Risky:** `gemma4:e4b` — would likely cause swap pressure with 7.6 GB total RAM
- Currently uses qwen2:0.5b (~1 t/s) which is 350 MB — E2B at 3.2 GB is 9x larger but significantly more intelligent

---

## 3. Comparison with Currently Used Models

### 3.1 LLM Model Comparison — Specifications

| Model | Params (active) | Quantization | VRAM/RAM | GPU offload | Languages |
|---|---|---|---|---|---|
| **qwen3.5:latest (9B)** | 9.7B | Q4_K_M | 9.9 GB | 100% on 890M | 29+ |
| **qwen3.5:0.8b** | 0.8B | Q4_K_M | ~1.5 GB | 100% on 890M | 29+ |
| **qwen2:0.5b** | 0.5B | Q4_0 | ~350 MB | CPU only | 29+ |
| **gemma4:e2b** | 2.3B (effective) | Q4 | ~3.2 GB | ROCm | 140+ |
| **gemma4:e4b** | 4.5B (effective) | Q4 | ~5 GB | ROCm | 140+ |
| **gemma4:26b-a4b** | 3.8B (active) | Q4 | ~15.6 GB | ROCm | 140+ |
| **gemma4:latest (31B)** | 30.7B | Q4 | ~17.4 GB | N/A on 890M | 140+ |
| **gpt-4o-mini (cloud)** | N/A (API) | N/A | 0 (cloud) | N/A | 100+ |

### 3.2 Performance Comparison — Measured vs Expected

**SintAItion Measured Baselines (from taris-openclaw benchmarks):**

| Model | Speed (t/s) | Quality (6 prompts) | Wall time (short) | Wall time (medium) |
|---|---|---|---|---|
| **qwen3.5:latest (9B)** | 12.1-12.9 | **100%** | 1.5 s | 6.6 s |
| **qwen3.5:0.8b** | **53.8** | 67% | 4.6 s | 3.0 s |
| **qwen2:0.5b** | ~1 (CPU, TS2) | ~60% | 23.8 s (TS2) | N/A |
| **gpt-4o-mini (cloud)** | N/A | ~95% | 0.5 s (API) | 0.5 s (API) |

**Gemma 4 Expected Performance on SintAItion (ROCm, 890M):**

| Model | Expected t/s | Expected Quality | Rationale |
|---|---|---|---|
| **gemma4:e2b** | **25-40 t/s** | 60-70% | 2.3B effective params — PLE architecture optimized for edge; faster than qwen3.5:0.8b but higher quality |
| **gemma4:e4b** | **15-25 t/s** | 75-85% | 4.5B effective — similar compute to qwen3.5:latest but fewer total params; MMLU Pro 69.4% vs Gemma 3 27B's 67.6% |
| **gemma4:26b-a4b** | **15-30 t/s** | 85-90% | MoE: only 3.8B active per token = fast inference; quality near 31B (MMLU Pro 82.6%) |

*Note: These are estimates based on parameter counts and architecture. Actual benchmarks needed on device.*

### 3.3 Quality Benchmarks — Published Results

| Benchmark | gemma4 E2B | gemma4 E4B | gemma4 31B | gemma4 26B-A4B | Gemma 3 27B |
|---|---|---|---|---|---|
| MMLU Pro | 60.0% | 69.4% | **85.2%** | 82.6% | 67.6% |
| MMMLU (multilingual) | 67.4% | 76.6% | **88.4%** | 86.3% | 70.7% |
| AIME 2026 (math) | 37.5% | 42.5% | **89.2%** | 88.3% | 20.8% |
| GPQA Diamond | 43.4% | 58.6% | **84.3%** | 82.3% | 42.4% |
| LiveCodeBench v6 | 44.0% | 52.0% | **80.0%** | 77.1% | 29.1% |
| BigBench Extra Hard | 21.9% | 33.1% | **74.4%** | 64.8% | 19.3% |
| Arena ELO (LMSYS) | N/A | N/A | **1452 (#3)** | 1441 (#6) | N/A |

**Key insight:** Gemma 4 E4B (4.5B effective) outperforms Gemma 3 27B (full 27B) on MMLU Pro and multilingual benchmarks — a 6x efficiency improvement.

### 3.4 Multilingual Quality Comparison

Taris requires RU/DE/EN (and optionally SL) quality. From published MMMLU (multilingual) scores:

| Model | MMMLU Score | Languages | Russian quality (estimated) |
|---|---|---|---|
| **qwen3.5:latest (9B)** | N/A (proprietary benchmark) | 29+ | **100%** (measured, 6 prompts) |
| **gemma4:e2b** | 67.4% | 140+ | ~65% (expected) |
| **gemma4:e4b** | 76.6% | 140+ | ~75% (expected) |
| **gemma4:26b-a4b** | 86.3% | 140+ | ~85% (expected) |
| **gemma4:31b** | 88.4% | 140+ | ~88% (expected) |

---

## 4. Audio/STT Capabilities — Gemma 4 vs Faster-Whisper

### 4.1 Can Gemma 4 Replace Faster-Whisper for STT?

**Short answer: No — Gemma 4 is not a drop-in STT replacement, but it adds value as a supplementary audio-capable LLM.**

| Feature | Faster-Whisper (current) | Gemma 4 E2B/E4B Audio |
|---|---|---|
| **Primary purpose** | Dedicated STT engine | Multimodal LLM with audio input |
| **Max audio** | Unlimited (chunked) | **30 seconds max** |
| **Output** | Raw transcript (text) | Text response (can include reasoning) |
| **WER (Russian)** | 17-22% (small int8) | Unknown (not benchmarked for WER) |
| **RTF** | 0.33 (small) / 1.31 (large-v3-turbo) | Unknown (expected slower) |
| **Streaming** | Yes (real-time) | No (batch only) |
| **Languages** | 99 languages | 140+ languages |
| **Model size** | ~150 MB (small int8) | 3.2-5 GB (4-bit) |
| **CPU support** | Yes (optimized) | Yes (slow) |
| **GPU support** | CUDA, ROCm (via ctranslate2) | ROCm via Ollama |

### 4.2 Where Gemma 4 Audio Excels

1. **Speech understanding + reasoning in one step:** "Listen to this voice message and extract calendar events" — no separate STT + LLM pipeline needed
2. **Audio translation:** Transcribe Russian speech, translate to German in one call
3. **Audio + image fusion:** Process both a photo and voice note simultaneously (E2B/E4B)

### 4.3 Where Faster-Whisper Remains Superior

1. **Accuracy:** Dedicated ASR models still outperform general-purpose multimodal LLMs for pure transcription
2. **Latency:** RTF 0.33 for small model vs unknown (likely slower) for Gemma 4
3. **No length limit:** Faster-Whisper handles arbitrary-length audio via chunking
4. **Streaming:** Real-time transcription not possible with Gemma 4
5. **Memory efficiency:** 150 MB vs 3.2-5 GB

### 4.4 Recommendation for STT

Keep Faster-Whisper as the primary STT engine. Gemma 4 audio could be explored for:
- Voice-to-action commands (STT + intent extraction in one step)
- Audio translation features
- A/B testing audio comprehension quality vs Whisper pipeline

---

## 5. Benchmark Script — How to Run

The benchmark script `src/tests/llm/benchmark_ollama_models.py` supports both Qwen and Gemma 4 models.

### 5.1 Pull Models on SintAItion

```bash
# Pull Gemma 4 models for benchmarking
ssh stas@SintAItion.local "ollama pull gemma4:e2b"    # ~3.2 GB
ssh stas@SintAItion.local "ollama pull gemma4:e4b"    # ~5 GB

# Optional (if VRAM allows):
ssh stas@SintAItion.local "ollama pull gemma4:26b-a4b"  # ~15.6 GB — borderline
```

### 5.2 Run Benchmarks

```bash
# Full benchmark — all available models, all languages
python3 src/tests/llm/benchmark_ollama_models.py

# Quick benchmark — latency + Russian only
python3 src/tests/llm/benchmark_ollama_models.py --quick

# Gemma 4 only
python3 src/tests/llm/benchmark_ollama_models.py --model gemma4:e2b,gemma4:e4b

# Compare against saved baseline
python3 src/tests/llm/benchmark_ollama_models.py --compare ~/.taris/tests/llm_benchmark_baseline.json

# Save results to specific file
python3 src/tests/llm/benchmark_ollama_models.py --save tools/benchmark_gemma4_results.json
```

### 5.3 Deploy Script to Target

```bat
pscp -pw "%HOSTPWD%" src\tests\llm\benchmark_ollama_models.py stas@SintAItion.local:/home/stas/.taris/tests/llm/
plink -pw "%HOSTPWD%" -batch stas@SintAItion.local "python3 /home/stas/.taris/tests/llm/benchmark_ollama_models.py --model gemma4:e2b,gemma4:e4b -v"
```

---

## 6. Recommendations

### 6.1 What to Test (Priority Order)

1. **`gemma4:e4b` on SintAItion** — Best candidate for replacing or supplementing qwen3.5:latest. Expected ~15-25 t/s with good multilingual quality. Smaller VRAM footprint (5 GB vs 9.9 GB) leaves room for concurrent services.

2. **`gemma4:e2b` on SintAItion** — Fastest option (~25-40 t/s expected). Good for latency-critical voice assistant responses where quality can be slightly lower.

3. **`gemma4:e2b` on TariStation2** — Only Gemma 4 model that fits. Compare against current qwen2:0.5b baseline. Expected improvement in quality at cost of higher memory usage (3.2 GB vs 350 MB).

4. **`gemma4:26b-a4b` on SintAItion** — Experimental: if it fits in 16 GB shared VRAM, the MoE architecture (3.8B active params) could deliver near-31B quality at E4B-like speed.

### 6.2 Decision Criteria

| Scenario | Keep qwen3.5:latest | Switch to Gemma 4 E4B | Switch to Gemma 4 E2B |
|---|---|---|---|
| Quality >= 100% (6 prompts) | **Use if true** | If quality >= 90% | If quality >= 80% |
| Speed >= 12 t/s | Already achieved | If >= 15 t/s | If >= 25 t/s |
| Russian calendar JSON | Already works | Must pass | Must pass |
| German timezone reasoning | Already works | Must pass | Must pass |
| VRAM usage | 9.9 GB | 5 GB (saves 4.9 GB) | 3.2 GB (saves 6.7 GB) |

### 6.3 Potential Integration Changes

If Gemma 4 benchmarks prove favorable, these code changes would be needed:

1. **`src/core/bot_config.py`** — Add `OLLAMA_MODEL` default to Gemma 4 variant
2. **`~/.taris/bot.env`** — Set `OLLAMA_MODEL=gemma4:e4b` (or whichever wins)
3. **`src/core/bot_llm.py`** — Gemma 4 uses standard Ollama API; no code changes needed for basic LLM use
4. **Audio integration (future):** Would require new endpoint in bot_voice.py to send audio directly to Gemma 4 instead of Whisper pipeline

### 6.4 STT Decision

**Keep Faster-Whisper** as primary STT. Gemma 4 audio (E2B/E4B only) is complementary:
- 30-second audio limit vs unlimited chunked processing
- No streaming support vs real-time transcription
- Higher VRAM cost (3.2-5 GB) vs 150 MB for Whisper small
- Potential future use: combined STT+intent extraction in single inference call

---

## 7. Next Steps

- [ ] Pull `gemma4:e2b` and `gemma4:e4b` on SintAItion
- [ ] Run `benchmark_ollama_models.py` with both Gemma 4 and existing Qwen models
- [ ] Compare actual t/s, quality scores, and multilingual performance
- [ ] If E4B quality >= 90%: run extended A/B test with Taris bot
- [ ] If 26B-A4B fits: test MoE performance on 890M
- [ ] Test E2B on TariStation2 as qwen2:0.5b replacement
- [ ] Document results in `tools/benchmark_gemma4_results.json`
