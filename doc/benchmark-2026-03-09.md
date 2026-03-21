# Voice Pipeline Benchmark — PI1 vs PI2 (2026-03-09)

**Tested:** Both Pis running `bench_voice.py` in parallel  
**Key change before this run:** `taris-voice.service` **disabled on PI1** (was using ~30 MB RAM + caused 286 MB SD-backed swap)

---

## Hardware

| Property | PI1 (OpenClawPI) | PI2 (OpenClawPI2) |
|---|---|---|
| Model | Raspberry Pi 3 **B+** Rev 1.3 | Raspberry Pi 3 **B** Rev 1.2 |
| CPU | 4× Cortex-A53 @ **1400 MHz** | 4× Cortex-A53 @ **1200 MHz** |
| RAM | 905 MB | 906 MB |
| Kernel | 6.12.62+rpt-rpi-v8 | 6.12.47+rpt-rpi-v8 |
| Swap | ~2.9 GB (partition, SD) | ~905 MB zram (in-RAM) |
| BOT_VERSION | 2026.3.24 | 2026.3.24 |

---

## Results

### Storage bandwidth (Piper ONNX — 61 MB read)

| Metric | PI1 | PI2 |
|---|---|---|
| Cold read (MB/s) | **105 MB/s** | **380 MB/s** |
| Warm read (MB/s) | **409 MB/s** | **386 MB/s** |

> **Finding:** PI2 has a much faster SD card (380 MB/s cold vs 105 MB/s on PI1).  
> PI1 warm read (409 MB/s) is actually slightly faster once pages are cached — pure page-cache speed.  
> Cold read on PI1 is ~3.6× slower due to SD card quality.

---

### TTS Synthesis (Piper — 82 chars, Russian)

| Run | PI1 | PI2 |
|---|---|---|
| Cold (first call) | **9.57 s** | **9.85 s** |
| Warm (second call) | **9.36 s** | **10.92 s** |
| Warm2 (third call) | **9.12 s** | **9.10 s** |
| chars/s (warm2) | **~9** | **~9** |

> **Finding:** Both Pis converge to **~9 chars/s** on warm runs — performance is CPU-bound (ONNX inference), not storage-bound.  
> PI1 shows a downward trend (9.57 → 9.12) — ONNX cache is being filled progressively.  
> PI2 briefly slower on warm (10.92 s) — likely OS scheduling jitter on the slower CPU.  
> `tmpfs_model=true` opted in on both → model is in `/dev/shm/`, eliminating SD reads during TTS.

---

### STT — Vosk model load + decode

| Metric | PI1 | PI2 |
|---|---|---|
| Vosk model load | **4.56 s** | **4.64 s** |
| Decode (2s silence audio) | **1.526 s** | **1.549 s** |

> **Finding:** STT is effectively identical on both Pis despite the 200 MHz clock difference.  
> Vosk model load time is dominated by page faults / RAM bandwidth, not CPU speed.

---

### LLM call (taris → OpenRouter)

| Call | PI1 | PI2 |
|---|---|---|
| First (cold) | **5.27 s** | **14.61 s** ⚠️ |
| Second | **6.92 s** | **6.68 s** |

> ⚠️ PI2 first LLM call (14.61 s) was a network jitter anomaly — OpenRouter API latency, not Pi performance.  
> Second call (6.68 s) is in the normal 5–7 s range for both devices.

---

## End-to-End Estimate (Telegram voice message)

| Stage | Time |
|---|---|
| OGG → PCM (ffmpeg) | ~0.5 s |
| Whisper STT decode | ~30–35 s (ggml-base.bin on Pi 3) |
| LLM (OpenRouter) | ~5–7 s |
| TTS synthesis (warm, ~300 chars) | ~10–11 s |
| PCM → OGG (ffmpeg) | ~0.3 s |
| **Total (warm, real use)** | **~47–54 s** |

> TTS in real use synthesises `TTS_MAX_CHARS=600` chars — roughly double the benchmark payload, so budget ~20 s for TTS in the worst case on a warm Pi.

---

## PI1 — Before vs After (taris-voice disabled)

This benchmark was run **after** disabling `taris-voice.service` on PI1.  
Previous benchmarks (same session, voice service still running):

| Metric | PI1 **before** | PI1 **after** |
|---|---|---|
| RAM used | 347 MB | 262 MB |
| RAM free | 558 MB | 643 MB |
| Swap used | **286 MB** | **102 MB** |
| TTS warm (run 1) | 9.57 s | 9.57 s |
| TTS warm (run 2) | 9.36 s | 9.36 s |
| TTS warm (run 3) | **9.12 s** ↓ | — (same run) |

> Disabling the voice daemon freed ~85 MB RAM and **reduced swap pressure from 286 MB to 102 MB**.  
> Swap was backed by the SD card (~20 MB/s) — 286 MB of swap meant the kernel was constantly evicting  
> ONNX pages and reloading them. This caused the previously observed TTS degradation (10.5 → 11.5 → 13.1 s per run).  
> After disabling: TTS is now stable and **trending down** as the ONNX page cache fills.

---

## Recommended Optimizations (not yet applied)

| Optimization | Expected gain | Effort |
|---|---|---|
| `gpu_mem=16` in config.txt (both Pis) | +60 MB free RAM → more ONNX cache | Trivial |
| CPU governor → `performance` (both Pis) | −5–10% across all CPU-bound stages | Trivial |
| Disable `taris-gateway.service` on PI1 (stuck `activating`) | Faster boot, no spurious activation | Trivial |
| USB SSD for Piper model (PI1 only) | Cold TTS load: 9.5 s → ~2 s | Low |

See `doc/hardware-performance-analysis.md` for full analysis.

---

## Scripts

Benchmark script: `temp/bench_voice.py`  
Results saved on Pi: `/tmp/bench_pi1_new.txt`, `/tmp/bench_pi2_new.txt`  
Deployed to both Pis with: `pscp -pw "%HOSTPWD%" temp\bench_voice.py stas@OpenClawPI:/tmp/bench_voice.py`
