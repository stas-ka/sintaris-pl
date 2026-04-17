# Hardware Requirements Report — Taris Personal Assistant

**Date:** March 2026  
**Author:** Analysis for GitHub issue "Requirements to HW to run this software"  
**Scope:** Resource estimation for implemented and planned functions across three hardware realizations.  
**Updated:** Added 1–2 s voice-response target analysis, non-Raspberry-Pi hardware platforms (Intel, AMD, Jetson, RK3588), and per-function latency detail in all summary tables.

---

## Overview

This report analyses the resource requirements of the Taris personal assistant software for three hardware realizations, covering both currently implemented functions and functions planned in the roadmap. Resource estimates are provided in RAM, ROM/Storage, CPU load, and TOPS (for neural inference), and are derived from real benchmark measurements on Pi 3 B+ where available.

A key performance target drives the hardware selection: **voice commands of up to 3 seconds must receive a full voice reply within 1–2 seconds** (see §0 for the full pipeline budget analysis). This target requires dedicated NPU or GPU acceleration and cannot be met on Cortex-A53 class hardware. Raspberry Pi boards below Pi 5 are unsuitable for this target; the analysis includes a wide range of non-Raspberry-Pi boards with integrated GPU/NPU.

### Three Hardware Realizations

| Realization | Platform | Role | Reference |
|---|---|---|---|
| **PicoClaw** | Raspberry Pi 3 B+ (current production) | Full-featured deployment, current baseline | [benchmark-2026-03-09.md](benchmark-2026-03-09.md) |
| **ZeroClaw** | Raspberry Pi Zero 2 W | Minimal / embedded / low-cost, text-only | [TODO §18](../TODO.md) |
| **OpenClaw** | Pi 5 8 GB + NVMe **or any of the non-RPi platforms in §1.4–1.6** | High-performance; local LLM + RAG; target ≤2 s voice response | [TODO §19](../TODO.md), [§0](#0-voice-latency-target) |

---

## 0. Voice Latency Target — ≤2 Seconds for 3-Second Voice Input

> **Requirement:** A voice command of up to 3 seconds duration must receive a complete voice reply within **1–2 seconds** from the moment the user stops speaking.

### 0.1 Pipeline Stage Budget (≤2 s total)

The end-to-end voice pipeline from Telegram consists of the following stages. All times below are *measured or estimated* for a **3-second OGG voice clip** (≈48 kB, Russian, ~20 words):

| Stage | Tool | Slow (Pi 3 B+) | Medium (Pi 5 / A76) | Fast (NPU/GPU) | Budget for ≤2 s |
|---|---|---|---|---|---|
| Telegram OGG download | Telegram API | ~0.2 s | ~0.1 s | ~0.1 s | **≤0.2 s** |
| OGG → 16 kHz PCM | ffmpeg | ~0.5 s | ~0.1 s | ~0.05 s | **≤0.1 s** |
| Speech-to-Text (3 s audio) | Vosk / Whisper | ~4–15 s | ~0.5–1 s | **~0.05–0.2 s** | **≤0.2 s** |
| LLM response (cloud, ~30 tok) | OpenRouter | ~1.0–2.0 s | ~1.0–2.0 s | ~1.0–2.0 s | **≤1.2 s** (p50) |
| LLM response (local GPU, ~30 tok) | llama.cpp | — | — | ~0.3–1.0 s | **≤1.0 s** |
| TTS synthesis (~80 chars) | Piper ONNX | ~10–25 s | ~1.5–2 s | **~0.1–0.3 s** | **≤0.3 s** |
| PCM → OGG Opus | ffmpeg | ~0.1 s | ~0.05 s | ~0.03 s | **≤0.05 s** |
| **Total (cloud LLM)** | | **≫30 s** | **~3–4 s** | **~1.2–1.9 s** | **≤2.0 s ✓** |
| **Total (local LLM, GPU)** | | — | — | **~0.7–1.8 s** | **≤2.0 s ✓** |

### 0.2 Conclusions from Budget Analysis

| Hardware class | Cloud LLM path | Local LLM path | 1–2 s target |
|---|---|---|---|
| Pi 3 B+ (Cortex-A53) | ~30–60 s | Not viable | ❌ |
| Pi 5 / A76 CPU-only | ~3–4 s | ~8–15 s | ❌ |
| Pi 5 + Hailo-8L HAT (13 TOPS) | ~1.5–2.0 s | ~3–5 s | ✅ Cloud path only |
| RK3588 NPU (6 TOPS) | ~1.8–2.5 s | ~4–8 s | ⚠️ marginal |
| Intel Core Ultra (iGPU + NPU ~11 TOPS) | ~1.2–1.8 s | ~2–3 s | ✅ Cloud path |
| AMD Ryzen AI (Hawk Point, 16 TOPS NPU) | ~1.2–1.5 s | ~1.5–3 s | ✅ |
| Nvidia Jetson Orin Nano 8 GB (40 TOPS) | ~1.0–1.5 s | ~1.0–2.0 s | ✅ Both paths |
| Nvidia RTX GPU workstation | <0.5 s | <0.5 s | ✅✅ |

### 0.3 What Hardware Acceleration is Required

To achieve ≤2 s voice response with cloud LLM, two stages must be accelerated:

1. **STT acceleration** — replace CPU Vosk (~4–15 s on A53, ~0.5 s on A76) with:
   - **Whisper-tiny** via CUDA (Jetson): ~0.05 s
   - **Whisper-tiny** via OpenVINO (Intel NPU): ~0.1 s
   - **Whisper-tiny** via RKNN (RK3588): ~0.15–0.3 s
   - **Whisper-tiny** via Hailo SDK (Pi 5 HAT): ~0.1–0.2 s
   - _Whisper-tiny model size: 39 MB; 39M params; ~0.04 TOPS required_

2. **TTS acceleration** — replace CPU Piper (~10–25 s on A53, ~1.5 s on A76) with:
   - Piper ONNX Runtime via **CUDA** (Jetson): ~0.05–0.1 s
   - Piper ONNX Runtime via **OpenVINO** (Intel NPU): ~0.15–0.3 s
   - Piper ONNX Runtime via **RKNN** (RK3588): ~0.2–0.4 s
   - Piper ONNX Runtime via **Hailo** (Pi 5 HAT): ~0.1–0.2 s
   - _Piper medium model: 66 MB; inference ~0.4 TOPS_

**Minimum hardware for 1–2 s voice response: ≥13 TOPS NPU/GPU with ONNX Runtime support**  
**Optimal hardware: Nvidia Jetson Orin Nano (40 TOPS CUDA) or Intel Core Ultra (OpenVINO 11 TOPS NPU + iGPU)**

---

## 1. Hardware Profiles

### 1.1 PicoClaw — Raspberry Pi 3 B+

| Component | Specification | Notes |
|---|---|---|
| SoC | BCM2837B0 | Revised B0 stepping (improved thermals vs original BCM2837) |
| CPU | 4× ARM Cortex-A53 @ 1.4 GHz | In-order, ARMv8-A, 32 KB L1 / 512 KB L2 per core |
| RAM | 1 GB LPDDR2 @ 900 MHz dual-channel | ~6 GB/s bandwidth |
| Storage | microSD Class 10 / A1 | ~25–105 MB/s sequential read (card-dependent) |
| USB | USB 2.0 shared DWC_OTG | Shared bus with Ethernet |
| Network | 100 Mbps Ethernet + 802.11n 2.4 GHz | Adequate for cloud LLM API calls |
| GPU | VideoCore IV (64–256 MB shared, configurable) | Not usable for ML inference |
| NPU/DSP | None | No hardware acceleration |
| Power | ~3.5–5 W typical | 2.5 A micro-USB recommended |
| Price | ~$35 (board only) | + microSD, PSU, case, USB mic, speaker |

**Runtime memory budget (all services active):**

| Component | RAM peak | Notes |
|---|---|---|
| Raspberry Pi OS + kernel | ~250 MB | Bookworm baseline |
| Python + pyTelegramBotAPI | ~60 MB | Telegram bot process |
| Vosk STT model (small-ru, 48 MB) | ~180 MB | Loaded on first voice message |
| Piper ONNX TTS (medium, 66 MB) | ~150 MB | Cold-loaded; ~10–15 s from microSD |
| taris Go binary | ~30 MB | Short-lived subprocess |
| FastAPI web server (uvicorn) | ~25 MB | Always-on |
| ffmpeg subprocesses | ~20 MB | Per voice note (×2 instances) |
| **Total** | **~715 MB** | Leaves ~285 MB for OS page cache |

> **Memory pressure is critical on Pi 3 B+.** With all services active, the system operates near the 1 GB limit. The OS must evict page cache under voice load, which is the root cause of the 10–15 s Piper cold-start from microSD. See [hardware-performance-analysis.md §1](hardware-performance-analysis.md).

---

### 1.2 ZeroClaw — Raspberry Pi Zero 2 W

| Component | Specification | Notes |
|---|---|---|
| SoC | RP3A0-AU (BCM2710A1 die, same as Pi 3 B) | Rebinned Pi 3 silicon in tiny package |
| CPU | 4× ARM Cortex-A53 @ 1.0 GHz | Same arch as Pi 3, lower clock |
| RAM | 512 MB LPDDR2 | Half the RAM of Pi 3 B+ |
| Storage | microSD | Same bandwidth as Pi 3 B+ |
| USB | USB 2.0 (micro-USB OTG) | Only 1 port; requires hub for mic + drive |
| Network | 802.11n 2.4 GHz + Bluetooth 4.2 | No Ethernet (requires USB adapter) |
| GPU | VideoCore IV (64 MB shared) | Not usable for ML |
| NPU/DSP | None | No hardware acceleration |
| Power | ~0.4–2.5 W | Very low power; micro-USB |
| Price | ~$15 (board only) | Hard to source; check availability |

**Runtime memory budget (constrained profile):**

| Component | RAM (available) | Feasibility on Zero 2 W |
|---|---|---|
| Raspberry Pi OS + kernel | ~250 MB | ✅ Required |
| Python + pyTelegramBotAPI | ~60 MB | ✅ Core bot |
| FastAPI web server | ~25 MB | ⚠️ Optional — disable if needed |
| Vosk STT model (small-ru) | ~180 MB | ❌ Does NOT fit with all other services |
| Piper TTS (medium ONNX) | ~150 MB | ❌ Cannot run simultaneously with Vosk |
| **Total (all features)** | **>665 MB** | **❌ Exceeds 512 MB RAM** |
| **Total (text-only, no voice)** | **~335 MB** | ✅ Fits within 512 MB |

> **Voice features are not viable on Zero 2 W in the standard configuration.** Only one of {Vosk, Piper} can be active at a time, and even then the system is near the memory limit. A text-only subset (Telegram bot + web UI + LLM + calendar/notes/mail) is feasible. Voice requires Pi 3 B+ or better.

---

### 1.3 OpenClaw — Raspberry Pi 5 8 GB + NVMe (or RK3588 mini-PC)

#### Option A: Raspberry Pi 5 (8 GB)

| Component | Specification | Notes |
|---|---|---|
| SoC | BCM2712 | Quad-core Cortex-A76 @ 2.4 GHz |
| CPU | 4× ARM Cortex-A76 @ 2.4 GHz | Out-of-order, high IPC, strong SIMD/NEON |
| RAM | 8 GB LPDDR4X | ~17× the bandwidth of Pi 3 B+ |
| Storage | NVMe via M.2 HAT (PCIe 2.0) | ~900 MB/s read; eliminates storage bottleneck |
| USB | USB 3.0 + USB 2.0 | Separate controllers |
| Network | Gigabit Ethernet + 802.11ac | 5 GHz WiFi |
| GPU | VideoCore VII | Not usable for ML (no GPGPU driver) |
| NPU/DSP | None natively | Hailo-8L HAT: 13 TOPS; Coral USB: 4 TOPS (add-on) |
| Power | ~5–12 W | 27 W USB-C PD recommended |
| Price | ~$80 (8 GB) | + NVMe HAT ~$15, NVMe SSD ~$20 |

#### Option B: Orange Pi 5 / Radxa Rock 5B (RK3588)

| Component | Specification | Notes |
|---|---|---|
| SoC | Rockchip RK3588 | Industry-leading edge-AI SoC |
| CPU | 4× Cortex-A76 @ 2.4 GHz + 4× Cortex-A55 @ 1.8 GHz | big.LITTLE; 8-core |
| RAM | 8–16 GB LPDDR4X | Up to 16 GB on Rock 5B |
| Storage | NVMe M.2 (PCIe 3.0 ×4) | ~3,000 MB/s — eliminates all storage bottlenecks |
| NPU | RK3588 NPU — **6 TOPS** | Supports RKNN-Toolkit, ONNX model acceleration |
| GPU | Mali-G610 MP4 | Limited ML use via OpenCL |
| Network | 2.5G Ethernet + WiFi 6 | Excellent bandwidth |
| Power | ~10–15 W typical | 12 V / 2–3 A barrel connector |
| Price | ~$80–$100 (8 GB) | Orange Pi 5 Pro / Rock 5B |

**Runtime memory budget (full stack):**

| Component | RAM peak | Notes |
|---|---|---|
| OS + kernel | ~350 MB | Ubuntu 22.04 / Debian Bookworm |
| Python bot + services | ~60 MB | Telegram bot |
| FastAPI web server | ~25 MB | Web UI |
| Vosk STT (small-ru) | ~180 MB | Always-warm |
| Piper ONNX (medium) in tmpfs | ~150 MB | RAM-resident after startup |
| taris Go binary | ~30 MB | |
| Local LLM — Phi-3-mini 3.8B Q4 | ~2,500 MB | Via llama.cpp; Pi 5 can hold in RAM |
| RAG embedding model (MiniLM-L6) | ~90 MB | For local knowledge base |
| **Total (with local LLM)** | **~3,385 MB** | ✅ Fits in 8 GB |

> **OpenClaw enables the complete planned feature set**, including local LLM fallback, RAG knowledge base, and multi-modal voice. With NPU/GPU acceleration (Hailo HAT, RK3588, Jetson, or Intel/AMD NPU — see §1.4–1.5 below), voice latency drops to ≤2 s.

---

### 1.4 OpenClaw Accelerated — Intel Core Ultra Mini-PC

Representative boards: **Beelink EQR14 (Core Ultra 7 155H)**, **ASUS NUC 14 Pro (Core Ultra 5 125H)**, **Minisforum UM860 Pro (Core Ultra 9 185H)**

| Component | Specification | Notes |
|---|---|---|
| SoC | Intel Core Ultra 5/7/9 (Meteor Lake) | First Intel SoC with dedicated NPU die |
| CPU | 6–16 cores (E+P, up to 5.1 GHz) | Hybrid arch; strong single-thread + multi-thread |
| RAM | 16–64 GB DDR5 (SO-DIMM, user-upgradeable) | 64 GB/s bandwidth (dual-channel DDR5-4800) |
| Storage | NVMe M.2 PCIe 4.0 | ~7,000 MB/s read — instant model loads |
| GPU | Intel Arc iGPU (Xe-LPG, 8–16 EU) | OpenCL + OpenVINO inference; ~2–4 TOPS |
| NPU | Intel AI Boost NPU (Meteor Lake die) | **~11 TOPS** — dedicated INT8 matrix engine |
| USB | USB4 + USB 3.2 + USB 2.0 | Full host controller per port |
| Network | 2.5G Ethernet + WiFi 6E | Fast enough for any cloud LLM |
| Power | 15–45 W (TDP configurable) | Fanless mini-PC form factor or active cooling |
| Price | ~$200–$500 (complete mini-PC) | Includes RAM + SSD; no soldered RAM |
| OS | Linux (Ubuntu 22.04/24.04 x86_64) | Full OpenVINO + IPEX support |

**Key inference capabilities:**

| Workload | Tool | Performance | vs Pi 3 B+ |
|---|---|---|---|
| Whisper-tiny STT (3 s audio) | OpenVINO | ~0.08–0.15 s | **50–100×** faster |
| Piper ONNX TTS (80 chars) | ONNX Runtime + OpenVINO | ~0.15–0.25 s | **40–80×** faster |
| Piper ONNX TTS (80 chars) | Arc iGPU (OpenCL) | ~0.1–0.2 s | **50–100×** faster |
| Phi-3-mini 3.8B Q4 LLM | llama.cpp (CPU) | ~12–15 tok/s | — |
| Phi-3-mini 3.8B Q4 LLM | llama.cpp (Intel GPU via SYCL) | ~20–30 tok/s | — |
| RAG embedding (MiniLM-L6) | OpenVINO NPU | ~0.05 s / query | — |

**Runtime memory budget (full AI stack):**

| Component | RAM peak | Notes |
|---|---|---|
| Ubuntu + kernel | ~500 MB | x86_64 baseline |
| Python bot + services | ~100 MB | Bot + Web UI + background threads |
| Vosk STT model | ~180 MB | Optional; Whisper preferred |
| Piper ONNX TTS (tmpfs) | ~150 MB | Warm in RAM |
| Local LLM — Phi-3-mini Q4 | ~2,500 MB | llama.cpp CPU/iGPU |
| RAG stack (MiniLM + FAISS) | ~300 MB | 10K-doc knowledge base |
| **Total** | **~3,730 MB** | ✅ Fits in 16 GB with headroom |

**Voice response latency with OpenVINO acceleration:**

| Stage | Time |
|---|---|
| Telegram download | ~0.1 s |
| OGG → PCM | ~0.03 s |
| Whisper-tiny STT (OpenVINO NPU) | ~0.1 s |
| Cloud LLM (OpenRouter, ~30 tok) | ~1.0–1.5 s |
| Piper TTS (OpenVINO NPU, 80 chars) | ~0.2 s |
| PCM → OGG | ~0.03 s |
| **Total** | **~1.5–1.9 s ✅** |

---

### 1.5 OpenClaw Accelerated — AMD Ryzen AI Mini-PC

Representative boards: **Beelink SER8 (Ryzen 9 8945HS)**, **Minisforum UM790 Pro (Ryzen 9 7940HS)**, **ASUS NUC 14 Pro+ (Ryzen AI 9 HX 370)**

| Component | Specification | Notes |
|---|---|---|
| SoC | AMD Ryzen AI / Ryzen 7000–9000 (Phoenix/Hawk Point/Strix) | XDNA-based NPU |
| CPU | 8–12 cores (Zen4/Zen5, up to 5.2 GHz) | Best single-thread IPC among mini-PCs |
| RAM | 16–64 GB LPDDR5X or DDR5 | 100+ GB/s bandwidth (Hawk Point / Strix) |
| Storage | NVMe M.2 PCIe 4.0 | ~7,000 MB/s |
| GPU | AMD Radeon 780M / 890M iGPU (RDNA 3/4) | **ROCm / OpenCL / Vulkan compute** |
| NPU | AMD XDNA NPU | Ryzen AI 7000: ~16 TOPS; Ryzen AI 9 HX 370: **~50 TOPS** |
| Network | 2.5G Ethernet + WiFi 6E | |
| Power | 15–54 W (TDP configurable) | |
| Price | ~$180–$600 (complete mini-PC) | |
| OS | Linux (Ubuntu 22.04/24.04 x86_64) | ROCm + AMD NPU stack |

**Key inference capabilities (Ryzen AI 9 HX 370 / Strix Point, 50 TOPS NPU):**

| Workload | Tool | Performance | Notes |
|---|---|---|---|
| Whisper-tiny STT (3 s audio) | ROCm / iGPU | ~0.05–0.1 s | RDNA 3 iGPU via ROCm |
| Piper ONNX TTS (80 chars) | ONNX Runtime + ROCm | ~0.08–0.15 s | iGPU accelerated |
| Phi-3-mini 3.8B Q4 | llama.cpp (CPU) | ~20–25 tok/s | Zen4 strong AVX2 |
| Phi-3-mini 3.8B Q4 | llama.cpp (Vulkan, iGPU) | ~30–50 tok/s | RDNA 3 Vulkan |
| Llama-3.1-8B Q4 | llama.cpp (Vulkan) | ~15–25 tok/s | Runs locally |
| RAG embedding | ONNX / iGPU | ~0.05 s / query | |

**Voice response latency with Radeon iGPU acceleration:**

| Stage | Time |
|---|---|
| Telegram download | ~0.1 s |
| OGG → PCM | ~0.03 s |
| Whisper-tiny STT (ROCm iGPU) | ~0.08 s |
| Cloud LLM (OpenRouter, ~30 tok) | ~1.0–1.5 s |
| Piper TTS (ONNX + ROCm, 80 chars) | ~0.1 s |
| PCM → OGG | ~0.03 s |
| **Total** | **~1.3–1.7 s ✅** |

---

### 1.6 OpenClaw Max — Nvidia Jetson Orin Nano 8 GB

| Component | Specification | Notes |
|---|---|---|
| SoC | Nvidia Tegra234 (Orin) | Purpose-built edge AI SoC |
| CPU | 6× ARM Cortex-A78AE @ 1.5 GHz | SIMD + ECC; embedded Linux |
| RAM | 8 GB LPDDR5 unified (CPU + GPU share) | 68 GB/s bandwidth |
| Storage | NVMe M.2 PCIe 4.0 via carrier board | ~7,000 MB/s |
| GPU | **1024-core Ampere GPU** | CUDA 12, TensorRT, cuDNN |
| DLA | **Deep Learning Accelerator ×2** | Fixed-function INT8 tensor engine |
| Total AI compute | **40 TOPS** | GPU + DLA combined |
| Power | 7–15 W (configurable power modes) | Ultra-efficient for 40 TOPS |
| Price | ~$250 (module) + ~$80 carrier board | Total ~$330 |
| OS | JetPack 6 (Ubuntu 22.04 aarch64) | Full CUDA, TensorRT, DeepStream |

**Key inference capabilities (TensorRT + CUDA):**

| Workload | Tool | Performance | Notes |
|---|---|---|---|
| Whisper-tiny STT (3 s audio) | whisper.cpp (CUDA) | **~0.03–0.07 s** | TensorRT engine |
| Vosk STT (3 s audio) | CPU (A78AE) | ~0.3–0.5 s | CUDA not applicable |
| Piper ONNX TTS (80 chars) | ONNX Runtime (CUDA) | **~0.04–0.08 s** | GPU-resident model |
| Phi-3-mini 3.8B Q4 | llama.cpp (CUDA) | ~15–25 tok/s | Full GPU offload |
| Llama-3.2-3B Q4 | llama.cpp (CUDA) | ~25–35 tok/s | Fast 3B model |
| Llama-3.1-8B Q4 | llama.cpp (CUDA) | ~8–12 tok/s | Fits in 8 GB unified |
| RAG embedding (MiniLM) | ONNX Runtime (CUDA) | ~0.02 s / query | Batch capable |

**Voice response latency (Jetson Orin Nano, cloud LLM):**

| Stage | Time |
|---|---|
| Telegram download | ~0.1 s |
| OGG → PCM | ~0.02 s |
| Whisper-tiny STT (CUDA/TensorRT) | **~0.05 s** |
| Cloud LLM (OpenRouter, ~30 tok) | ~1.0–1.5 s |
| Piper TTS (ONNX CUDA, 80 chars) | **~0.06 s** |
| PCM → OGG | ~0.02 s |
| **Total** | **~1.2–1.7 s ✅** |

**Voice response latency (Jetson, local LLM Phi-3-mini ~20 tok/s):**

| Stage | Time |
|---|---|
| STT | 0.05 s |
| Local LLM (30 tok @ 20 tok/s) | ~1.5 s |
| TTS | 0.06 s |
| Overhead | 0.2 s |
| **Total** | **~1.8 s ✅** |

---



### 2.1 Core Infrastructure

| Function | Source | RAM (MB) | ROM/Storage | CPU % (idle) | CPU % (active) | TOPS needed | PicoClaw | ZeroClaw | OpenClaw |
|---|---|---|---|---|---|---|---|---|---|
| **OS + Python runtime** | OS | 250 | 2 GB OS image | 2–5% | — | — | ✅ | ✅ | ✅ |
| **Telegram bot polling** | `telegram_menu_bot.py` | 60 | ~200 KB code | 1–3% | 5–10% | — | ✅ | ✅ | ✅ |
| **FastAPI Web UI** | `src/bot_web.py` | 25 | ~100 KB code | 1–3% | 5–15% | — | ✅ | ⚠️ tight | ✅ |
| **SQLite data layer** | `src/core/bot_db.py` | 5 | ~10 MB DB | <1% | 2% | — | ✅ | ✅ | ✅ |
| **i18n / strings** | `src/strings.json` | 2 | ~30 KB JSON | <1% | <1% | — | ✅ | ✅ | ✅ |
| **User registration & RBAC** | `src/telegram/bot_access.py` | 2 | <10 KB | <1% | 1% | — | ✅ | ✅ | ✅ |

### 2.2 Voice Pipeline

| Function | Source | RAM (MB) | ROM/Storage | CPU % (active) | Latency | TOPS | PicoClaw | ZeroClaw | OpenClaw |
|---|---|---|---|---|---|---|---|---|---|
| **OGG → PCM decode** (ffmpeg) | `src/features/bot_voice.py` | 20 | ffmpeg ~4 MB | 5–15% (1 core) | ~0.5–1 s | — | ✅ ~1 s | ⚠️ ~1.5 s | ✅ <0.3 s |
| **Vosk STT** (vosk-model-small-ru, 48 MB) | `bot_voice.py` | 180 | 48 MB model | 80–100% (1 core) | 10–15 s | — | ✅ ~15 s | ❌ no RAM | ✅ ~3–4 s |
| **VAD pre-filter** (webrtcvad) | `bot_voice.py` | 5 | <1 MB | 5–10% | ~0.2 s | — | ✅ | ❌ | ✅ |
| **Whisper STT** (ggml-base, 148 MB) | `bot_voice.py` | 250 | 148 MB model | 100% (all cores) | 30–35 s | — | ⚠️ too slow | ❌ no RAM | ✅ ~5–8 s |
| **Piper TTS** (medium ONNX, 66 MB) | `bot_voice.py` | 150 | 66 MB model | 100% (1–2 cores) | 10–25 s warm | ~0.4 TOPS | ✅ ~10 s | ❌ no RAM | ✅ ~2–4 s |
| **Piper TTS** (low ONNX, 33 MB) | `bot_voice.py` | 80 | 33 MB model | 80% (1 core) | 5–12 s warm | ~0.2 TOPS | ✅ | ❌ | ✅ |
| **PCM → OGG Opus encode** (ffmpeg) | `bot_voice.py` | 20 | ffmpeg ~4 MB | 10–20% (1 core) | ~0.3 s | — | ✅ | ⚠️ | ✅ |
| **Piper tmpfs model (RAM-pinned)** | Voice opt | 150 | RAM only | Same as above | Eliminates cold-start | — | ⚠️ tight RAM | ❌ | ✅ |
| **Standalone voice assistant** (wake-word loop) | `voice_assistant.py` | 250 | +48 MB Vosk always | 20–40% continuous | — | — | ⚠️ high load | ❌ | ✅ |

> **Benchmark source:** Real measurements from `benchmark-2026-03-09.md` and `hardware-performance-analysis.md §2`.

### 2.3 LLM Integration

| Function | Source | RAM (MB) | ROM/Storage | CPU % (active) | Latency | PicoClaw | ZeroClaw | OpenClaw |
|---|---|---|---|---|---|---|---|---|
| **taris Go binary** (OpenRouter API) | `/usr/bin/picoclaw` | 30 | ~15 MB binary | 5–10% | 1–3 s (network) | ✅ | ✅ | ✅ |
| **OpenRouter cloud LLM** (gpt-4o-mini) | `src/core/bot_llm.py` | — (cloud) | — | <1% (network wait) | 1–3 s | ✅ | ✅ | ✅ |
| **OpenAI direct API** | `bot_llm.py` | — (cloud) | — | <1% | 1–5 s | ✅ | ✅ | ✅ |

### 2.4 Content Features

| Function | Source | RAM (MB) | ROM/Storage | CPU % (active) | PicoClaw | ZeroClaw | OpenClaw |
|---|---|---|---|---|---|---|---|
| **Smart Calendar** (NL events, multi-event) | `src/features/bot_calendar.py` | 5 | ~5 MB DB | 2–5% | ✅ | ✅ | ✅ |
| **Markdown Notes** (create/edit/TTS) | `src/telegram/bot_handlers.py` | 3 | ~1 MB/user | 1–3% | ✅ | ✅ | ✅ |
| **Mail Digest** (IMAP + LLM summary) | `src/features/bot_email.py` | 15 | <1 MB | 5–10% | ✅ | ✅ | ✅ |
| **Contact Book** | `src/features/bot_contacts.py` | 3 | ~1 MB DB | 1% | ✅ | ✅ | ✅ |
| **Error Protocol** (report collection) | `src/features/bot_error_protocol.py` | 3 | ~10 MB/reports | 1% | ✅ | ✅ | ✅ |

### 2.5 Operations & Security

| Function | Source | RAM (MB) | ROM/Storage | CPU % | PicoClaw | ZeroClaw | OpenClaw |
|---|---|---|---|---|---|---|---|
| **3-layer prompt injection guard** | `src/security/` | 2 | <10 KB | 1–2% | ✅ | ✅ | ✅ |
| **RBAC (roles: admin/developer/user)** | `src/telegram/bot_access.py` | 2 | <5 KB | <1% | ✅ | ✅ | ✅ |
| **JWT session auth (Web UI)** | `src/bot_web.py` | 2 | <5 KB | <1% | ✅ | ✅ | ✅ |
| **Backup (tar.gz + SD image)** | `src/setup/` | — (script) | ~2–4 GB image | 10–20% | ✅ | ✅ | ✅ |
| **Logging & journal** | systemd | — | ~50 MB/mo logs | <1% | ✅ | ✅ | ✅ |

---

## 3. Planned Function Resource Estimates

### 3.1 LLM & AI Extensions

| Function | Source | RAM (MB) | ROM/Storage | CPU % / TOPS | Latency | PicoClaw | ZeroClaw | OpenClaw | Reference |
|---|---|---|---|---|---|---|---|---|---|
| **Conversation memory** (15-msg sliding window) | [TODO §2.1](../TODO.md) | +5 | +1 MB DB | +1% | — | ✅ | ✅ | ✅ | [TODO §2.1](../TODO.md) |
| **Local LLM — Qwen2-0.5B Q4** (llama.cpp) | [TODO §3.2](../TODO.md) | +350 | 350 MB GGUF | 100% all cores | ~80–100 s / 80 tok | ⚠️ no RAM left | ❌ | ⚠️ slow | [hw-analysis §8.9](hardware-performance-analysis.md) |
| **Local LLM — Phi-3-mini 3.8B Q4** | [TODO §3.2](../TODO.md) | +2,500 | 2.5 GB GGUF | 100% all cores | ~16–40 s / 80 tok | ❌ no RAM | ❌ | ✅ | [hw-analysis §8.9](hardware-performance-analysis.md) |
| **Local LLM — Llama-3.2-3B Q4** | [TODO §3.2](../TODO.md) | +2,000 | 2 GB GGUF | 100% all cores | ~16–40 s | ❌ | ❌ | ✅ | [hw-analysis §8.9](hardware-performance-analysis.md) |
| **YandexGPT / Gemini providers** | [TODO §3.1](../TODO.md) | — (cloud) | <5 KB config | <1% | 1–5 s (network) | ✅ | ✅ | ✅ | [TODO §3.1](../TODO.md) |

### 3.2 Knowledge & RAG

| Function | Source | RAM (MB) | ROM/Storage | CPU % / TOPS | Latency | PicoClaw | ZeroClaw | OpenClaw | Reference |
|---|---|---|---|---|---|---|---|---|---|
| **RAG — embedding model** (all-MiniLM-L6-v2, 23M params) | [TODO §4.1](../TODO.md) | +90 | 90 MB model | 50% / ~0.05 TOPS | ~0.5–2 s per query | ❌ no RAM | ❌ | ✅ | [hw-analysis §5](hardware-performance-analysis.md) |
| **RAG — FAISS vector DB** | [TODO §4.1](../TODO.md) | +50–500 | 50 MB–2 GB DB | 20–40% | ~0.1–0.5 s | ❌ | ❌ | ✅ | [TODO §4.1](../TODO.md) |
| **Document upload & indexing** (PDF/DOCX/TXT) | [TODO §10](../TODO.md) | +50 | 1–5 GB docs | 30–60% | 5–60 s/doc | ❌ | ❌ | ✅ | [TODO §10](../TODO.md) |
| **Multimodal RAG** (text + images + tables) | [TODO §10](../TODO.md) | +200 | +vision model | 60–80% / 0.5 TOPS | 5–30 s/query | ❌ | ❌ | ✅ (with GPU) | [TODO §10](../TODO.md) |

### 3.3 CRM Platform

| Function | Source | RAM (MB) | ROM/Storage | CPU % | PicoClaw | ZeroClaw | OpenClaw | Reference |
|---|---|---|---|---|---|---|---|---|
| **Smart CRM** — contacts, deals, custom fields | [TODO §13](../TODO.md) | +10 | +20 MB DB | 5–10% | ✅ | ⚠️ | ✅ | [TODO §13](../TODO.md), [8.4 CRM spec](todo/8.4-crm-platform.md) |
| **CRM voice input** (all fields via voice) | [TODO §12](../TODO.md) | depends on voice | — | same as voice | ✅ | ❌ | ✅ | [TODO §12](../TODO.md) |
| **Kanban board** (Web UI, deals pipeline) | [TODO §13](../TODO.md) | +5 | +5 KB templates | 5% | ✅ | ⚠️ | ✅ | [TODO §13](../TODO.md) |

### 3.4 UI & Interaction

| Function | Source | RAM (MB) | ROM/Storage | CPU % | PicoClaw | ZeroClaw | OpenClaw | Reference |
|---|---|---|---|---|---|---|---|---|
| **NiceGUI** (replace Jinja2) | [TODO §8.5](../TODO.md) | +35 (60 vs 25) | — | +5% | ❌ RAM concern | ❌ | ✅ | [TODO §8.5](../TODO.md) |
| **Central voice dashboard** | [TODO §11](../TODO.md) | +20 | +20 KB templates | 10–20% | ✅ | ⚠️ | ✅ | [TODO §11](../TODO.md) |
| **Voice input for all text fields** | [TODO §12](../TODO.md) | depends on voice | — | same as voice | ✅ | ❌ | ✅ | [TODO §12](../TODO.md) |
| **Max Messenger UI** | [TODO §17](../TODO.md) | +50 | +500 KB templates | 10–15% | ⚠️ | ❌ | ✅ | [TODO §17](../TODO.md) |
| **Developer Board** (agent-based) | [TODO §14](../TODO.md) | +100 | +200 KB | 15–30% | ⚠️ | ❌ | ✅ | [TODO §14](../TODO.md) |

### 3.5 External Integrations

| Function | Source | RAM (MB) | ROM/Storage | CPU % | PicoClaw | ZeroClaw | OpenClaw | Reference |
|---|---|---|---|---|---|---|---|---|
| **Google Calendar / Gmail sync** | [TODO §15](../TODO.md) | +15 | <5 MB | 5% | ✅ | ✅ | ✅ | [TODO §15](../TODO.md) |
| **Yandex Calendar / Mail sync** | [TODO §15](../TODO.md) | +15 | <5 MB | 5% | ✅ | ✅ | ✅ | [TODO §15](../TODO.md) |
| **Google Drive** | [TODO §15](../TODO.md) | +20 | — | 5–10% | ✅ | ✅ | ✅ | [TODO §15](../TODO.md) |
| **KIM personal assistant functions** | [TODO §16](../TODO.md) | +50–200 | varies | 20–50% | ⚠️ | ❌ | ✅ | [KIM_PACKAGES.md](../concept/additional/KIM_PACKAGES.md) |

---

## 4. Summary Tables by Hardware Realization

### 4.1 PicoClaw (Raspberry Pi 3 B+) — Per-Function Resource & Latency

| Function | Status | RAM (MB) | Storage | CPU peak | Latency | TOPS | Verdict |
|---|---|---|---|---|---|---|---|
| OS + kernel | ✅ | 250 | 2 GB OS | 5% | — | — | ✅ |
| Python + Telegram bot | ✅ | 60 | 200 KB | 5–10% | — | — | ✅ |
| FastAPI Web UI | ✅ | 25 | 100 KB | 5–15% | — | — | ✅ |
| SQLite data layer | ✅ | 5 | ~10 MB | 2% | <0.1 s | — | ✅ |
| OGG → PCM (ffmpeg) | ✅ | 20 | 4 MB | 10–15% | **~1.0 s** | — | ✅ |
| VAD pre-filter | ✅ | 5 | <1 MB | 5% | **~0.2 s** | — | ✅ |
| Voice STT — Vosk small-ru | ✅ | 180 | 48 MB | 100% (1 core) | **~15 s** | — | ✅ slow |
| Voice STT — Whisper base | ✅ | 250 | 148 MB | 100% all | **~30–35 s** | — | ⚠️ too slow |
| Cloud LLM call (OpenRouter) | ✅ | 30 (Go) | 15 MB | 5% | **~1–3 s** | — | ✅ |
| Voice TTS — Piper medium (warm) | ✅ | 150 | 66 MB | 100% (1 core) | **~9–12 s** | ~0.4 TOPS | ✅ slow |
| Voice TTS — Piper low (warm) | ✅ | 80 | 33 MB | 80% | **~5–7 s** | ~0.2 TOPS | ✅ |
| PCM → OGG Opus | ✅ | 20 | 4 MB | 15% | **~0.3 s** | — | ✅ |
| Calendar NL events | ✅ | 5 | 5 MB | 5% | <0.1 s | — | ✅ |
| Notes / Mail / Contacts | ✅ | 21 | ~3 MB | 5% | <0.1 s | — | ✅ |
| RBAC + security | ✅ | 4 | <15 KB | 1% | <0.01 s | — | ✅ |
| **Total (full voice stack)** | ✅ | **~755 MB** | — | **100%** | **~27–55 s** voice | **~0.4 TOPS** | ⚠️ |
| Local LLM Qwen2-0.5B Q4 | 🔲 | +350 MB | 350 MB | 100% all | **~80–100 s** | — | ❌ no RAM + voice |
| RAG embeddings | 🔲 | +90 MB | 90 MB | 60% | ~1–2 s | ~0.05 TOPS | ❌ no RAM |
| 1–2 s voice target | — | — | — | — | **❌ ~27–55 s actual** | — | ❌ not achievable |

**PicoClaw optimized (tmpfs + persistent_piper + piper_low + performance governor):**  
`OGG decode 0.5 s + STT 13 s + LLM 2 s + TTS 5 s + encode 0.2 s ≈ 21 s total`

---

### 4.2 ZeroClaw (Raspberry Pi Zero 2 W) — Per-Function Resource

| Function | Status | RAM (MB) | CPU peak | Latency | Verdict |
|---|---|---|---|---|---|
| OS + kernel | ✅ | 250 | 10% | — | ✅ |
| Python + Telegram bot | ✅ | 60 | 10% | — | ✅ |
| FastAPI Web UI | ✅ | 25 | 15% | — | ⚠️ tight |
| SQLite | ✅ | 5 | 2% | <0.2 s | ✅ |
| OGG → PCM | ✅ | 20 | 15% | **~1.5 s** | ⚠️ |
| Voice STT — Vosk | ✅ | 180 | 100% | **N/A — no RAM** | ❌ |
| Voice TTS — Piper | ✅ | 150 | 100% | **N/A — no RAM** | ❌ |
| Cloud LLM call | ✅ | 30 | 5% | **~1–3 s** | ✅ |
| Calendar / Notes / Mail | ✅ | 21 | 5% | <0.1 s | ✅ |
| **Text-only total** | ✅ | **~395 MB** | **20%** | — | ✅ Fits |
| **Full voice stack** | | **>665 MB** | **100%** | — | ❌ Exceeds 512 MB |
| 1–2 s voice target | — | — | — | **❌ voice not possible** | ❌ |

---

### 4.3 OpenClaw — Pi 5 8 GB + NVMe (CPU-only, no NPU HAT)

| Function | Status | RAM (MB) | Storage | CPU peak | Latency | TOPS | Verdict |
|---|---|---|---|---|---|---|---|
| OS + kernel | ✅ | 350 | 4 GB OS | 5% | — | — | ✅ |
| Python bot + services | ✅ | 100 | 300 KB | 5% | — | — | ✅ |
| OGG → PCM | ✅ | 20 | 4 MB | 5% | **~0.1 s** | — | ✅ |
| VAD pre-filter | ✅ | 5 | <1 MB | 2% | **~0.05 s** | — | ✅ |
| Voice STT — Vosk small | ✅ | 180 | 48 MB | 40% | **~3–4 s** | — | ✅ |
| Voice STT — Whisper tiny (CPU) | ✅ | 120 | 39 MB | 80% | **~1.5–2.5 s** | — | ✅ |
| Voice STT — Whisper base (CPU) | ✅ | 250 | 148 MB | 100% | **~5–8 s** | — | ⚠️ |
| Cloud LLM call | ✅ | 30 | 15 MB | 5% | **~1–2 s** | — | ✅ |
| Voice TTS — Piper medium (warm) | ✅ | 150 | 66 MB | 60–80% | **~1.5–2.5 s** | ~0.4 TOPS | ✅ |
| Voice TTS — Piper low (warm) | ✅ | 80 | 33 MB | 40% | **~0.8–1.5 s** | ~0.2 TOPS | ✅ |
| PCM → OGG | ✅ | 20 | 4 MB | 5% | **~0.05 s** | — | ✅ |
| Calendar / Notes / Mail / CRM | ✅ | 26 | ~25 MB | 5% | <0.1 s | — | ✅ |
| Local LLM — Phi-3-mini Q4 | 🔲 | +2,500 | 2.5 GB | 90% all | **~16 s / 80 tok** | — | ✅ |
| RAG embeddings (MiniLM-L6) | 🔲 | +90 | 90 MB | 30% | **~0.3 s/query** | ~0.05 TOPS | ✅ |
| RAG FAISS vector DB | 🔲 | +200 | 200 MB | 20% | **~0.1–0.3 s** | — | ✅ |
| **Full stack (no local LLM)** | ✅ | **~975 MB** | — | **80%** | **~5–7 s voice (Whisper tiny)** | — | ✅ |
| **Full stack (+ local LLM)** | | **~3,475 MB** | — | **100%** | **~5 s voice + ~16 s LLM** | — | ✅ |
| 1–2 s voice target | — | — | — | — | **❌ ~3–5 s actual (CPU-only)** | — | ❌ needs NPU |

---

### 4.4 OpenClaw Accelerated — Intel Core Ultra Mini-PC (OpenVINO NPU)

| Function | Status | RAM (MB) | Storage | CPU/NPU/GPU | Latency | TOPS used | Verdict |
|---|---|---|---|---|---|---|---|
| OS + Python bot | ✅ | 600 | 4 GB OS | 5% | — | — | ✅ |
| OGG → PCM | ✅ | 20 | 4 MB | CPU 3% | **~0.03 s** | — | ✅ |
| VAD pre-filter | ✅ | 5 | <1 MB | CPU 1% | **~0.02 s** | — | ✅ |
| Voice STT — Whisper tiny (OpenVINO) | ✅ | 120 | 39 MB | **NPU** | **~0.08–0.15 s** | ~0.04 TOPS | ✅ |
| Cloud LLM call | ✅ | 30 | 15 MB | CPU 3% | **~1.0–1.5 s** | — | ✅ |
| Voice TTS — Piper medium (OpenVINO) | ✅ | 150 | 66 MB | **NPU/iGPU** | **~0.15–0.25 s** | ~0.4 TOPS | ✅ |
| PCM → OGG | ✅ | 20 | 4 MB | CPU 3% | **~0.03 s** | — | ✅ |
| Local LLM — Phi-3-mini Q4 (iGPU SYCL) | 🔲 | +2,500 | 2.5 GB | iGPU | **~2–3 s / 80 tok** | — | ✅ |
| Local LLM — Llama-3.1-8B Q4 (iGPU) | 🔲 | +8,000 | 5 GB | iGPU | **~4–6 s / 80 tok** | — | ✅ 16 GB RAM |
| RAG embeddings (OpenVINO NPU) | 🔲 | +90 | 90 MB | **NPU** | **~0.05 s/query** | ~0.05 TOPS | ✅ |
| **Full voice pipeline** | | **~945 MB** | — | **NPU + CPU** | **~1.4–2.0 s ✅** | ~0.44 TOPS | ✅ |
| **1–2 s voice target** | | | | | **✅ ~1.4–2.0 s** | — | ✅ |

---

### 4.5 OpenClaw Accelerated — AMD Ryzen AI Mini-PC (Radeon iGPU / NPU)

| Function | Status | RAM (MB) | Storage | Accelerator | Latency | Verdict |
|---|---|---|---|---|---|---|
| OS + Python bot | ✅ | 600 | 4 GB OS | CPU | — | ✅ |
| OGG → PCM | ✅ | 20 | 4 MB | CPU | **~0.03 s** | ✅ |
| Voice STT — Whisper tiny (ROCm) | ✅ | 120 | 39 MB | **Radeon iGPU** | **~0.05–0.10 s** | ✅ |
| Cloud LLM call | ✅ | 30 | 15 MB | CPU (network) | **~1.0–1.5 s** | ✅ |
| Voice TTS — Piper medium (ROCm) | ✅ | 150 | 66 MB | **Radeon iGPU** | **~0.08–0.15 s** | ✅ |
| Local LLM — Phi-3-mini Q4 (Vulkan) | 🔲 | +2,500 | 2.5 GB | iGPU Vulkan | **~1.5–2.0 s / 80 tok** | ✅ |
| Local LLM — Llama-3.1-8B Q4 (Vulkan) | 🔲 | +8,000 | 5 GB | iGPU Vulkan | **~3–4 s / 80 tok** | ✅ 32 GB RAM |
| RAG embeddings | 🔲 | +90 | 90 MB | CPU / iGPU | **~0.05 s/query** | ✅ |
| **Full voice pipeline** | | **~920 MB** | — | **iGPU ROCm** | **~1.2–1.7 s ✅** | ✅ |
| **1–2 s voice target** | | | | | **✅ ~1.2–1.7 s** | ✅ |

---

### 4.6 OpenClaw Max — Nvidia Jetson Orin Nano 8 GB (CUDA)

| Function | Status | RAM (MB) | Storage | Accelerator | Latency | TOPS used | Verdict |
|---|---|---|---|---|---|---|---|
| OS + Python bot | ✅ | 500 | 4 GB OS | CPU | — | — | ✅ |
| OGG → PCM | ✅ | 20 | 4 MB | CPU | **~0.02 s** | — | ✅ |
| Voice STT — Whisper tiny (CUDA) | ✅ | 120 | 39 MB | **GPU CUDA** | **~0.03–0.07 s** | ~0.04 TOPS | ✅ |
| Cloud LLM call | ✅ | 30 | 15 MB | CPU (network) | **~1.0–1.5 s** | — | ✅ |
| Local LLM — Phi-3-mini Q4 (CUDA) | 🔲 | +2,500 | 2.5 GB | **GPU CUDA** | **~1.2–2.0 s / 80 tok** | — | ✅ |
| Local LLM — Llama-3.1-8B Q4 (CUDA) | 🔲 | +5,000 | 5 GB | **GPU CUDA** | **~6–10 s / 80 tok** | — | ✅ |
| Voice TTS — Piper medium (CUDA) | ✅ | 150 | 66 MB | **GPU CUDA** | **~0.04–0.08 s** | ~0.4 TOPS | ✅ |
| RAG embeddings (CUDA) | 🔲 | +90 | 90 MB | **GPU CUDA** | **~0.02 s/query** | ~0.05 TOPS | ✅ |
| **Full voice pipeline (cloud LLM)** | | **~910 MB** | — | **CUDA** | **~1.1–1.7 s ✅** | ~0.44 TOPS | ✅ |
| **Full voice pipeline (local LLM)** | | **~3,410 MB** | — | **CUDA** | **~1.3–2.1 s ✅** | ~0.44 TOPS | ✅ |
| **1–2 s voice target** | | | | | **✅ Both paths** | — | ✅ |



## 5. Consolidated Feature Feasibility Matrix

| TODO ref | Function | Status | PicoClaw (Pi 3 B+) | ZeroClaw (Zero 2 W) | OpenClaw CPU-only (Pi 5) | OpenClaw NPU (Intel/AMD) | OpenClaw Max (Jetson) |
|---|---|---|---|---|---|---|---|
| Core | Telegram bot (text) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Core | Web UI (FastAPI) | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ |
| Core | Cloud LLM (OpenRouter) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Core | Calendar (NL events) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Core | Notes / Mail / Contacts | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Core | RBAC + Security | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Voice | OGG → PCM | ✅ | ✅ ~1 s | ⚠️ ~1.5 s | ✅ ~0.1 s | ✅ ~0.03 s | ✅ ~0.02 s |
| Voice | VAD pre-filter | ✅ | ✅ ~0.2 s | ❌ no RAM | ✅ ~0.05 s | ✅ ~0.02 s | ✅ ~0.01 s |
| Voice | STT Vosk (3 s audio) | ✅ | ✅ ~15 s | ❌ no RAM | ✅ ~3–4 s | ✅ — | ✅ ~0.5 s |
| Voice | STT Whisper-tiny (3 s) | ✅ | ⚠️ ~25 s | ❌ | ✅ ~1.5–2.5 s CPU | ✅ ~0.08–0.15 s NPU | ✅ ~0.03–0.07 s CUDA |
| Voice | TTS Piper medium (80 ch) | ✅ | ✅ ~10 s | ❌ no RAM | ✅ ~1.5–2 s CPU | ✅ ~0.15–0.25 s NPU | ✅ ~0.04–0.08 s CUDA |
| Voice | PCM → OGG | ✅ | ✅ ~0.3 s | ⚠️ | ✅ ~0.05 s | ✅ ~0.03 s | ✅ ~0.02 s |
| Voice | Wake-word loop | ✅ | ⚠️ high CPU | ❌ | ✅ | ✅ | ✅ |
| Voice | **Total voice latency** | ✅ | **~27–55 s** | ❌ | **~5–8 s** | **~1.3–1.9 s ✅** | **~1.1–1.7 s ✅** |
| §2.1 | Conversation memory | 🔲 | ✅ | ✅ | ✅ | ✅ | ✅ |
| §3.1 | Multi-LLM providers | 🔲 | ✅ | ✅ | ✅ | ✅ | ✅ |
| §3.2 | Local LLM (offline fallback) | 🔲 | ⚠️ ~90 s | ❌ | ✅ ~16 s | ✅ ~2–3 s | ✅ ~1.5–2 s |
| §4.1 | RAG knowledge base | 🔲 | ❌ | ❌ | ✅ ~0.3 s | ✅ ~0.05 s | ✅ ~0.02 s |
| §8.5 | NiceGUI UI | 🔲 | ❌ RAM | ❌ | ✅ | ✅ | ✅ |
| §10 | Doc + multimodal RAG | 🔲 | ❌ | ❌ | ✅ | ✅ | ✅ |
| §11 | Central voice dashboard | 🔲 | ⚠️ | ❌ | ✅ | ✅ | ✅ |
| §12 | Voice input everywhere | 🔲 | ✅ slow | ❌ | ✅ | ✅ | ✅ |
| §13 | Smart CRM | 🔲 | ✅ text | ⚠️ | ✅ | ✅ | ✅ |
| §14 | Developer Board | 🔲 | ⚠️ | ❌ | ✅ | ✅ | ✅ |
| §15 | Google/Yandex integrations | 🔲 | ✅ | ✅ | ✅ | ✅ | ✅ |
| §16 | KIM assistant functions | 🔲 | ⚠️ subset | ❌ | ✅ | ✅ | ✅ |
| §17 | Max Messenger UI | 🔲 | ⚠️ | ❌ | ✅ | ✅ | ✅ |
| **Target** | **1–2 s voice response** | 🎯 | ❌ ~27–55 s | ❌ | ❌ ~5–8 s | **✅ ~1.3–1.9 s** | **✅ ~1.1–1.7 s** |

**Legend:** ✅ Fully viable · ⚠️ Limited/slow/constrained · ❌ Not viable · 🎯 Key performance target

---

## 6. Mini-Computer Research — Non-Raspberry-Pi Platforms with GPU/NPU

### 6.1 Selection Criteria

For a device to serve as **OpenClaw** hardware it must satisfy:

| Requirement | Minimum for voice | Minimum for 1–2 s voice | Recommended |
|---|---|---|---|
| RAM | ≥2 GB | ≥8 GB | 16–32 GB |
| CPU | ≥4× Cortex-A55 or x86 E-core | ≥4× Cortex-A76 or Zen4 | Zen4 / Cortex-A76 |
| NPU or GPU | Optional (Vosk CPU) | **Required** (≥13 TOPS) | ≥40 TOPS CUDA |
| STT latency (3 s audio) | ≤5 s (CPU Vosk) | **≤0.2 s (NPU/GPU)** | ≤0.07 s (CUDA) |
| TTS latency (80 chars) | ≤3 s | **≤0.3 s (NPU/GPU)** | ≤0.08 s (CUDA) |
| Storage | ≥32 GB | ≥64 GB NVMe | ≥256 GB NVMe |
| Power | ≤20 W | ≤45 W | ≤15 W (Jetson) |
| Linux support | Debian/Ubuntu aarch64 | + CUDA/OpenVINO/ROCm | + TensorRT |

### 6.2 Evaluated Hardware — All Platforms

#### Group A — ARM SBCs without NPU (voice latency >5 s)

| Board | SoC | RAM | NPU | STT latency | TTS latency | Voice total | Price | 1–2 s? |
|---|---|---|---|---|---|---|---|---|
| **Raspberry Pi 3 B+** | BCM2837B0 (4× A53) | 1 GB | None | ~15 s (Vosk) | ~10 s (Piper CPU) | ~28 s | ~$35 | ❌ |
| **Raspberry Pi Zero 2 W** | RP3A0-AU (4× A53) | 512 MB | None | ❌ no RAM | ❌ no RAM | ❌ | ~$15 | ❌ |
| **Raspberry Pi 4 B (4 GB)** | BCM2711 (4× A72) | 4 GB | None | ~4–5 s (Vosk) | ~2–3 s (Piper) | ~8 s | ~$55 | ❌ |
| **Raspberry Pi 5 (8 GB)** | BCM2712 (4× A76) | 8 GB | None | ~3–4 s (Vosk) | ~1.5–2 s (Piper) | ~6 s | ~$80 | ❌ |

#### Group B — ARM SBCs with integrated NPU via RKNN / Hailo (voice latency 1.5–3 s)

Boards in this group include an on-chip or add-on NPU. The RK3588-based boards use **RKNN-Toolkit** to run Whisper and Piper ONNX models on the 6 TOPS NPU. Voice total is the full pipeline latency with cloud LLM.

| Board | SoC | RAM | NPU | STT latency | TTS latency | Voice total | Price | 1–2 s? |
|---|---|---|---|---|---|---|---|---|
| **Orange Pi 5 Pro (8 GB)** | RK3588S (4× A76 + 4× A55) | 8–16 GB | **6 TOPS (RKNN)** | ~0.5 s | ~0.3 s | ~2–3 s | ~$90 | ⚠️ marginal |
| **Radxa Rock 5B (16 GB)** | RK3588 (4× A76 + 4× A55) | 8–16 GB | **6 TOPS (RKNN)** | ~0.5 s | ~0.3 s | ~2–3 s | ~$100 | ⚠️ marginal |
| **Khadas Edge2 (16 GB)** | RK3588S | 8–16 GB | **6 TOPS (RKNN)** | ~0.5 s | ~0.3 s | ~2–3 s | ~$100 | ⚠️ |
| **NanoPi R6S** | RK3588S | 8 GB | **6 TOPS (RKNN)** | ~0.5 s | ~0.3 s | ~2–3 s | ~$80 | ⚠️ |
| **Banana Pi BPI-M5 Pro** | RK3576 (4× A76 + 4× A55) | 8–16 GB | **6 TOPS (RKNN)** | ~0.4 s | ~0.25 s | ~2 s | ~$70 | ⚠️ |
| **Pi 5 + Hailo-8L HAT** | BCM2712 + Hailo-8L | 8 GB | **13 TOPS (Hailo)** | ~0.1–0.2 s | ~0.1–0.2 s | **~1.4–2.0 s** | ~$150 | ✅ |
| **Milk-V Jupiter** | SpacemiT K1 (8× X60) | 4–16 GB | **2 TOPS** | ~0.5–1 s | ~0.5 s | ~3–4 s | ~$50 | ❌ |
| **Coral Dev Board** (NXP i.MX 8M) | ARM A53 + A72 | 1 GB | **4 TOPS** (Edge TPU) | ~0.3 s | ~0.4 s | ~2.5 s | ~$150 | ⚠️ |
| **ADVENTECH RSB-3720** | RK3588 + 6 TOPS NPU | 8–32 GB | **6 TOPS (RKNN)** | ~0.5 s | ~0.3 s | ~2 s | ~$200 | ⚠️ |

#### Group C — x86/x64 Mini-PCs without discrete GPU (voice latency 1–2 s via NPU)

| Board | SoC | RAM | NPU/iGPU | STT latency | TTS latency | Voice total | Price | 1–2 s? |
|---|---|---|---|---|---|---|---|---|
| **Intel N100 mini-PC** (Beelink EQ12) | Intel N100 (4× E-core) | 8–16 GB DDR5 | UHD iGPU only | ~0.5–1 s (CPU) | ~0.5 s (CPU) | ~3–4 s | ~$150 | ❌ no NPU |
| **Beelink EQ13 (Core i3-N305)** | Intel N305 (8× E-core) | 16–32 GB DDR5 | UHD iGPU only | ~0.3 s (CPU) | ~0.3 s | ~2.5 s | ~$180 | ❌ |
| **Beelink EQR14 (Core Ultra 7)** | Intel Core Ultra 7 155H | 16–64 GB DDR5 | **Arc GPU + 11 TOPS NPU** | **~0.08–0.15 s (NPU)** | **~0.15–0.25 s (NPU)** | **~1.4–1.9 s** | ~$380 | ✅ |
| **ASUS NUC 14 Pro (Core Ultra 5)** | Intel Core Ultra 5 125H | 16–64 GB DDR5 | **Arc GPU + 11 TOPS NPU** | **~0.1–0.18 s** | **~0.18–0.28 s** | **~1.5–2.0 s** | ~$450 | ✅ |
| **Minisforum UM860 Pro (Core Ultra 9)** | Intel Core Ultra 9 185H | 32–64 GB DDR5 | **Arc GPU + 11 TOPS NPU** | **~0.08 s** | **~0.12 s** | **~1.3–1.7 s** | ~$550 | ✅ |

#### Group D — x86/x64 Mini-PCs with AMD Radeon iGPU / XDNA NPU (voice latency ≤1.7 s)

| Board | SoC | RAM | NPU/GPU | STT latency | TTS latency | Voice total | Price | 1–2 s? |
|---|---|---|---|---|---|---|---|---|
| **Beelink SER7 (Ryzen 7 7840HS)** | Ryzen 7 7840HS (Phoenix) | 32 GB LPDDR5 | Radeon 780M + **16 TOPS XDNA** | **~0.05–0.1 s (ROCm)** | **~0.08–0.15 s** | **~1.2–1.6 s** | ~$300 | ✅ |
| **Beelink SER8 (Ryzen 9 8945HS)** | Ryzen 9 8945HS (Phoenix) | 32–64 GB | Radeon 780M + 16 TOPS | **~0.05 s** | **~0.08 s** | **~1.2–1.5 s** | ~$350 | ✅ |
| **Minisforum UM790 Pro (Ryzen 9 7940HS)** | Ryzen 9 7940HS | 32–64 GB LPDDR5 | Radeon 780M + 16 TOPS | **~0.05 s** | **~0.08 s** | **~1.2–1.5 s** | ~$350 | ✅ |
| **ASUS NUC 14 Pro+ (Ryzen AI 9 HX 370)** | Ryzen AI 9 HX 370 (Strix) | 32–96 GB LPDDR5X | Radeon 890M + **50 TOPS XDNA** | **~0.03–0.05 s** | **~0.05–0.08 s** | **~1.1–1.4 s** | ~$600 | ✅ |
| **Framework 13/16 (Ryzen AI 9 HX)** | Ryzen AI 9 HX 370 | 32–64 GB | 890M + 50 TOPS | **~0.03 s** | **~0.05 s** | **~1.1–1.3 s** | ~$700 | ✅ |

#### Group E — Dedicated Edge AI hardware (voice latency ≤1.5 s, both cloud and local LLM)

| Board | SoC | RAM | NPU/GPU | STT latency | TTS latency | Voice total | LLM (7B Q4) tok/s | Price | 1–2 s? |
|---|---|---|---|---|---|---|---|---|---|
| **Nvidia Jetson Orin Nano 8 GB** | Tegra234 + Ampere | 8 GB unified | **40 TOPS CUDA** | **~0.03–0.07 s** | **~0.04–0.08 s** | **~1.1–1.6 s** | ~8–12 tok/s | ~$330 | ✅ |
| **Nvidia Jetson Orin NX 16 GB** | Tegra234 + Ampere | 16 GB unified | **100 TOPS CUDA** | **~0.02–0.04 s** | **~0.03–0.06 s** | **~1.0–1.5 s** | ~20–30 tok/s | ~$600 | ✅ |
| **Nvidia Jetson AGX Orin** | Tegra234 + Ampere | 32–64 GB | **275 TOPS CUDA** | **~0.01–0.03 s** | **~0.02–0.04 s** | **<1 s** | ~50+ tok/s | ~$1,000 | ✅ |
| **Google Coral Dev Board Mini** | NXP i.MX 8M Mini + Edge TPU | 2 GB | **4 TOPS (INT8 only)** | ~0.2–0.4 s | ~0.3–0.5 s | ~2–3 s | ❌ no LLM | ~$100 | ⚠️ |
| **Hailo-8 M.2 Module** (as Pi 5 HAT M.2) | Hailo-8 | — | **26 TOPS** | ~0.05–0.1 s | ~0.05–0.1 s | ~1.2–1.8 s | ❌ not llama.cpp | ~$120 HAT | ✅ |

#### Group F — Apple Silicon (voice latency <1 s, best-in-class iGPU for ONNX)

| Board | SoC | RAM | GPU/NPU | STT latency | TTS latency | Voice total | LLM tok/s | Price | 1–2 s? |
|---|---|---|---|---|---|---|---|---|---|
| **Mac mini M2** | Apple M2 | 8–24 GB unified | 10-core GPU + ANE 15.8 TOPS | **~0.02–0.05 s** (CoreML) | **~0.05–0.10 s** | **~1.1–1.4 s** | ~20–30 tok/s (llama.cpp Metal) | ~$600 | ✅ |
| **Mac mini M4** | Apple M4 | 16–32 GB unified | 10-core GPU + ANE 38 TOPS | **~0.01–0.03 s** | **~0.03–0.07 s** | **<1 s** | ~40–60 tok/s | ~$600 | ✅✅ |
| **Mac mini M4 Pro** | Apple M4 Pro | 24–64 GB unified | 20-core GPU + ANE 38 TOPS | **~0.01 s** | **~0.02 s** | **<0.8 s** | ~60–80 tok/s | ~$1,000 | ✅✅ |

> **Note on Apple Silicon:** Whisper and Piper run natively via CoreML and Metal backends. llama.cpp supports Metal GPU offload with full model in unified RAM at ~20–80 tok/s depending on model size. macOS only — no Linux. Best performance/watt of any platform listed.

#### Group G — Cloud/VPS (no local voice; latency 100% network-dependent)

| Option | CPU | RAM | AI inference | Price/month | Voice possible? |
|---|---|---|---|---|---|
| **Hetzner CX22** | 4× vCPU (AMD EPYC) | 4 GB | OpenRouter API only | ~$5 | ❌ no mic/speaker |
| **Hetzner CAX21** | 4× ARM Ampere | 8 GB | llama.cpp possible | ~$9 | ❌ |
| **Oracle Cloud Free Tier** | 4× OCPU Ampere A1 | 24 GB | llama.cpp 7B free | Free | ❌ |
| **Lambda Cloud A10** | 30 vCPU | 200 GB | Full GPU inference | ~$0.60/h | ❌ |

### 6.3 Recommended Hardware Configurations — Updated for 1–2 s Target

#### Configuration A — ZeroClaw (Minimal / Always-on text bot)

**Hardware:** Raspberry Pi Zero 2 W + 32 GB microSD  
**Total cost:** ~$25 · **Power:** 0.4–2.5 W

| Feature | Status | Latency |
|---|---|---|
| Telegram bot | ✅ | — |
| Cloud LLM + Calendar + Mail | ✅ | ~1–3 s (cloud) |
| Voice STT / TTS | ❌ no RAM | — |
| 1–2 s voice target | ❌ | — |

**When to choose:** Battery-powered IoT assistant, text-only, minimal cost.

---

#### Configuration B — PicoClaw (Standard / Current production)

**Hardware:** Raspberry Pi 3 B+ + 32 GB A1 microSD + USB mic + speaker  
**Optional:** USB SSD for Piper model + swap  
**Total cost:** ~$50–$75 · **Power:** 3–5 W

| Feature | Status | Latency |
|---|---|---|
| All current bot features | ✅ | — |
| Voice STT (Vosk) | ✅ | ~15 s per 3 s clip |
| Voice TTS (Piper, optimized) | ✅ | ~5–7 s |
| Total voice latency (optimized) | ✅ | **~21–25 s** |
| 1–2 s voice target | ❌ | ~21–25 s actual |

**Required optimizations:** `gpu_mem=16`, `tmpfs_model`, `persistent_piper`, `piper_low_model`, CPU `performance` governor.

---

#### Configuration C — OpenClaw CPU (Pi 5 8 GB, no NPU)

**Hardware:** Raspberry Pi 5 8 GB + NVMe HAT + 256 GB NVMe + USB mic + speaker  
**Total cost:** ~$130–$160 · **Power:** 5–12 W

| Feature | Status | Latency |
|---|---|---|
| Full feature stack + local LLM + RAG | ✅ | — |
| Voice STT (Whisper-tiny, CPU) | ✅ | ~1.5–2.5 s |
| Voice TTS (Piper medium, CPU) | ✅ | ~1.5–2.0 s |
| Total voice latency | ✅ | **~5–7 s** |
| 1–2 s voice target | ❌ | ~5–7 s actual |

---

#### Configuration D — OpenClaw Pro (Pi 5 + Hailo-8L HAT — best RPi option for 1–2 s)

**Hardware:** Raspberry Pi 5 8 GB + Hailo-8L AI HAT+ (13 TOPS) + NVMe HAT + 256 GB NVMe  
**Total cost:** ~$200–$230 · **Power:** 6–15 W

| Feature | Status | Latency |
|---|---|---|
| Full feature stack + RAG | ✅ | — |
| Voice STT (Whisper-tiny, Hailo) | ✅ | **~0.1–0.2 s** |
| Voice TTS (Piper, Hailo) | ✅ | **~0.1–0.2 s** |
| Total voice latency | ✅ | **~1.4–2.0 s** |
| Local LLM (Phi-3-mini, CPU) | ✅ | ~16 s / 80 tok |
| 1–2 s voice target (cloud LLM) | **✅** | **~1.4–2.0 s** |

---

#### Configuration E — OpenClaw NPU (RK3588 8 GB — best ARM SBC value for AI)

**Hardware:** Orange Pi 5 Pro 8 GB (or Rock 5B) + 256 GB NVMe + USB mic + speaker  
**Total cost:** ~$120–$150 · **Power:** 8–15 W

| Feature | Status | Latency |
|---|---|---|
| Full feature stack + local LLM + RAG | ✅ | — |
| Voice STT (Whisper-tiny, RKNN) | ✅ | **~0.2–0.4 s** |
| Voice TTS (Piper, RKNN) | ✅ | **~0.2–0.4 s** |
| Total voice latency | ✅ | **~1.8–2.5 s** |
| Local LLM (7B Q4) | ✅ | ~8–15 s / 80 tok |
| 1–2 s voice target (cloud LLM) | ⚠️ | **~1.8–2.5 s marginal** |

---

#### Configuration F — OpenClaw Intel (Core Ultra mini-PC — 1–2 s guaranteed)

**Hardware:** Beelink EQR14 or ASUS NUC 14 Pro (Intel Core Ultra 7) + 32 GB DDR5 + 512 GB NVMe  
**Total cost:** ~$380–$500 · **Power:** 15–45 W

| Feature | Status | Latency |
|---|---|---|
| Full feature stack + local LLM + RAG | ✅ | — |
| Voice STT (Whisper-tiny, OpenVINO NPU) | ✅ | **~0.08–0.15 s** |
| Voice TTS (Piper, OpenVINO NPU) | ✅ | **~0.15–0.25 s** |
| Total voice latency (cloud LLM) | ✅ | **~1.4–1.9 s ✅** |
| Local LLM (Phi-3-mini, iGPU SYCL) | ✅ | ~2–3 s / 80 tok |
| 1–2 s voice target | **✅** | **~1.4–1.9 s** |

---

#### Configuration G — OpenClaw AMD (Ryzen AI mini-PC — best x86 value for AI)

**Hardware:** Beelink SER8 or Minisforum UM790 Pro (Ryzen 9 8945HS) + 32 GB LPDDR5 + 512 GB NVMe  
**Total cost:** ~$300–$400 · **Power:** 15–54 W

| Feature | Status | Latency |
|---|---|---|
| Full feature stack + local LLM + RAG | ✅ | — |
| Voice STT (Whisper-tiny, ROCm) | ✅ | **~0.05–0.10 s** |
| Voice TTS (Piper, ROCm) | ✅ | **~0.08–0.15 s** |
| Total voice latency (cloud LLM) | ✅ | **~1.2–1.7 s ✅** |
| Local LLM (Phi-3-mini, Vulkan) | ✅ | ~1.5–2.0 s / 80 tok |
| Local LLM (8B Q4, Vulkan) | ✅ | ~3–4 s / 80 tok |
| 1–2 s voice target | **✅** | **~1.2–1.7 s** |

---

#### Configuration H — OpenClaw Max (Jetson Orin — production, local LLM in 1–2 s)

**Hardware:** Nvidia Jetson Orin Nano 8 GB dev kit + 256 GB NVMe + USB mic + speaker  
**Total cost:** ~$330–$400 · **Power:** 7–15 W

| Feature | Status | Latency |
|---|---|---|
| Full feature stack + local LLM + RAG | ✅ | — |
| Voice STT (Whisper-tiny, CUDA TensorRT) | ✅ | **~0.03–0.07 s** |
| Voice TTS (Piper, CUDA) | ✅ | **~0.04–0.08 s** |
| Total voice latency (cloud LLM) | ✅ | **~1.1–1.6 s ✅** |
| Total voice latency (local LLM Phi-3) | ✅ | **~1.3–2.1 s ✅** |
| Local LLM (7B Q4 CUDA) | ✅ | ~8–12 tok/s |
| 1–2 s voice target (both paths) | **✅** | **~1.1–2.1 s** |



## 7. Key Findings & Recommendations

### 7.1 Critical Bottlenecks by Platform

| Bottleneck | PicoClaw (Pi 3 B+) | ZeroClaw (Zero 2 W) | OpenClaw CPU (Pi 5) | OpenClaw NPU (Intel/AMD) | OpenClaw Max (Jetson) |
|---|---|---|---|---|---|
| RAM | ⚠️ Near 1 GB limit | 🔴 512 MB — voice impossible | ✅ 8 GB | ✅ 16–64 GB | ✅ 8–16 GB unified |
| CPU (ONNX) | 🔴 A53 bottleneck | 🔴 Worse A53 | ⚠️ A76 ~2 s TTS | ✅ NPU offloads inference | ✅ CUDA offloads all |
| Storage I/O | ⚠️ microSD cold-start | ⚠️ microSD | ✅ NVMe | ✅ NVMe | ✅ NVMe |
| STT latency (3 s) | 🔴 ~15 s | ❌ N/A | ⚠️ ~3 s Vosk | ✅ ~0.1–0.2 s NPU | ✅ ~0.05 s CUDA |
| TTS latency (80 ch) | 🔴 ~10 s | ❌ N/A | ⚠️ ~1.5–2 s | ✅ ~0.15–0.25 s NPU | ✅ ~0.05–0.08 s CUDA |
| **1–2 s voice target** | ❌ ~27–55 s | ❌ | ❌ ~5–7 s | ✅ ~1.2–2.0 s | ✅ ~1.1–1.7 s |

### 7.2 Minimum Hardware for Each Feature Tier

| Tier | Required Hardware | Voice latency | Cost | Key constraint |
|---|---|---|---|---|
| Text-only bot | Pi Zero 2 W (512 MB) | — | ~$25 | Cloud LLM required |
| Voice (slow, no target) | Pi 3 B+ 1 GB + optimizations | ~21–25 s | ~$65 | tmpfs + persistent_piper mandatory |
| Voice + local LLM (emergency) | Pi 3 B+ (Qwen2-0.5B only) | ~90 s + voice | ~$65 | Cannot run alongside voice |
| Voice <8 s | Pi 5 8 GB + NVMe | ~5–7 s | ~$145 | A76 CPU bottleneck for TTS |
| **Voice 1–2 s (target)** | Pi 5 + Hailo-8L HAT (13 TOPS) | **~1.4–2.0 s** | ~$210 | NPU for Whisper + Piper |
| **Voice 1–2 s (budget x86)** | AMD Ryzen mini-PC (Radeon iGPU) | **~1.2–1.7 s** | ~$300 | ROCm for Whisper + Piper |
| **Voice 1–2 s (Intel)** | Intel Core Ultra mini-PC | **~1.4–1.9 s** | ~$400 | OpenVINO NPU |
| Voice + local LLM in 1–2 s | Nvidia Jetson Orin Nano 8 GB | **~1.3–2.1 s** | ~$330 | 40 TOPS CUDA; 7B LLM in ~8 s |
| Production multi-user | Jetson Orin NX / AMD mini-PC 64 GB | **<1.5 s** | ~$600+ | 100 TOPS / Vulkan 8B models |

### 7.3 Upgrade Path — Including 1–2 s Voice Target

```
ZeroClaw (Pi Zero 2 W, $25)
    → text-only personal bot, ~0.4 W, always-on
    → voice: ❌

PicoClaw (Pi 3 B+, $65)
    → full current feature set + cloud LLM
    → voice: ~21–25 s (optimized), not suitable for conversational use
    → upgrade: USB SSD → Piper cold-start eliminated; latency unchanged

OpenClaw CPU (Pi 5 8 GB + NVMe, $145)
    → full feature set + local LLM + RAG
    → voice: ~5–7 s (Whisper-tiny CPU + Piper CPU)
    → 1–2 s target: ❌ CPU-only bottleneck

OpenClaw RPi with NPU (Pi 5 8 GB + Hailo-8L HAT, $210)
    → voice: ~1.4–2.0 s with cloud LLM ✅
    → local LLM (Phi-3-mini CPU): ~16 s / 80 tok (HAT does not accelerate LLM)
    → 1–2 s target: ✅ (cloud LLM path only)

OpenClaw AMD (Ryzen AI mini-PC, $300–350)
    → voice: ~1.2–1.7 s ✅
    → local LLM (8B Vulkan): ~3–4 s / 80 tok
    → 1–2 s target: ✅ best budget x86 option

OpenClaw Intel (Core Ultra mini-PC, $400–500)
    → voice: ~1.4–1.9 s ✅
    → local LLM (Phi-3-mini iGPU): ~2–3 s / 80 tok
    → 1–2 s target: ✅

OpenClaw Max (Jetson Orin Nano 8 GB, $330)
    → voice: ~1.1–1.7 s ✅ (both cloud and local LLM paths)
    → local LLM (7B CUDA): ~8–12 tok/s; 80 tok ≈ 7–10 s (text-to-text 1–2 s possible for 30-tok answers)
    → 1–2 s target: ✅ best edge AI value for full voice + local LLM

Apple Mac mini M4 ($600)
    → voice: <1 s ✅ (CoreML + Metal)
    → local LLM (8B Metal): ~40–60 tok/s; 30-tok answer in <1 s
    → 1–2 s target: ✅✅ best overall performance
    → limitation: macOS only, cannot run Raspberry Pi OS services as-is
```

### 7.4 Hardware Selection Decision Tree for 1–2 s Voice Target

```
Is budget ≤ $150?
    YES → Pi 5 8 GB + NVMe → voice ~5–7 s → ❌ target missed
           Add Hailo-8L HAT (+$70) → voice ~1.5–2 s ✅
    NO
        Is Linux-only required? (no macOS)
            NO → Apple Mac mini M4 ($600) → <1 s ✅ best option
            YES
                Is budget ≤ $350?
                    YES → AMD Ryzen AI mini-PC ($300–350) → ~1.2–1.7 s ✅
                    NO
                        Need local LLM in 1–2 s?
                            NO → Intel Core Ultra mini-PC ($400–500) → ~1.4–1.9 s ✅
                            YES → Nvidia Jetson Orin Nano ($330) → cloud ~1.1 s + local LLM ✅
                                  OR AMD Ryzen AI + large RAM ($350+) → local 8B Vulkan ~3 s ✅ close
```



---

## 8. References

| Document | Relevance |
|---|---|
| [TODO.md §3.2](../TODO.md) | Local LLM fallback specification |
| [TODO.md §4.1](../TODO.md) | RAG knowledge base specification |
| [TODO.md §10–19](../TODO.md) | All planned future features |
| [hardware-performance-analysis.md](hardware-performance-analysis.md) | Benchmark data, timing measurements, upgrade analysis |
| [benchmark-2026-03-09.md](benchmark-2026-03-09.md) | Real PI1/PI2 voice benchmark measurements |
| [concept/additional/KIM_PACKAGES.md](../concept/additional/KIM_PACKAGES.md) | Personal assistant feature requirements |
| [concept/additional/SYSTEM_REQUIREMENTS_SmartClient360.md](../concept/additional/SYSTEM_REQUIREMENTS_SmartClient360.md) | CRM system requirements |
| [doc/todo/8.4-crm-platform.md](todo/8.4-crm-platform.md) | CRM platform roadmap |
| [doc/todo/5-voice-pipeline.md](todo/5-voice-pipeline.md) | Voice pipeline baseline & improvements |
| [deploy/requirements.txt](../deploy/requirements.txt) | Python package dependencies |
| [deploy/packages.txt](../deploy/packages.txt) | System package dependencies |

---

*Resource estimates for planned features are projections based on benchmark data from Pi 3 B+, llama.cpp ARM benchmarks, RKNN community measurements, and Pi Foundation hardware specifications. Actual values may vary by workload profile and software optimization state.*
