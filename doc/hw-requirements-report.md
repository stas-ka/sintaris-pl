# Hardware Requirements Report — Picoclaw Personal Assistant

**Date:** March 2026  
**Author:** Analysis for GitHub issue "Requirements to HW to run this software"  
**Scope:** Resource estimation for implemented and planned functions across three hardware realizations

---

## Overview

This report analyses the resource requirements of the Picoclaw personal assistant software for three hardware realizations, covering both currently implemented functions and functions planned in the roadmap. Resource estimates are provided in RAM, ROM/Storage, CPU load, and TOPS (for neural inference), and are derived from real benchmark measurements on Pi 3 B+ where available.

### Three Hardware Realizations

| Realization | Platform | Role | Reference |
|---|---|---|---|
| **PicoClaw** | Raspberry Pi 3 B+ (current production) | Full-featured deployment, current baseline | [benchmark-2026-03-09.md](benchmark-2026-03-09.md) |
| **ZeroClaw** | Raspberry Pi Zero 2 W | Minimal / embedded / low-cost deployment | [TODO §18](../TODO.md) |
| **OpenClaw** | Raspberry Pi 5 8 GB + NVMe, or RK3588 mini-PC | High-performance deployment; local LLM + RAG | [TODO §19](../TODO.md) |

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
| picoclaw Go binary | ~30 MB | Short-lived subprocess |
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
| picoclaw Go binary | ~30 MB | |
| Local LLM — Phi-3-mini 3.8B Q4 | ~2,500 MB | Via llama.cpp; Pi 5 can hold in RAM |
| RAG embedding model (MiniLM-L6) | ~90 MB | For local knowledge base |
| **Total (with local LLM)** | **~3,385 MB** | ✅ Fits in 8 GB |

> **OpenClaw enables the complete planned feature set**, including local LLM fallback, RAG knowledge base, and multi-modal voice at <15 s latency.

---

## 2. Implemented Function Resource Estimates

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
| **picoclaw Go binary** (OpenRouter API) | `/usr/bin/picoclaw` | 30 | ~15 MB binary | 5–10% | 1–3 s (network) | ✅ | ✅ | ✅ |
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

### 4.1 PicoClaw (Raspberry Pi 3 B+) — Full Feature Matrix

| Feature Group | Status | RAM used | CPU peak | TOPS | Verdict |
|---|---|---|---|---|---|
| OS + Python + Bot core | ✅ | ~310 MB | 10% | — | ✅ Baseline |
| Telegram bot + Web UI | ✅ | +85 MB | 15% | — | ✅ Running today |
| Voice STT (Vosk) | ✅ | +180 MB | 100% (1 core) | — | ✅ ~15 s latency |
| Voice TTS (Piper medium) | ✅ | +150 MB | 100% (1 core) | ~0.4 TOPS | ✅ ~10 s warm |
| Calendar + Notes + Mail | ✅ | +23 MB | 10% | — | ✅ |
| Contact Book + RBAC | ✅ | +5 MB | 2% | — | ✅ |
| **Total (full stack)** | ✅ | **~753 MB** | **100% peaks** | **~0.4 TOPS** | ⚠️ Near 1 GB limit |
| Local LLM (Qwen2-0.5B) | 🔲 | +350 MB | 100% all cores | — | ❌ No RAM for + Vosk/Piper |
| RAG embeddings | 🔲 | +140 MB | 60% | ~0.05 TOPS | ❌ No RAM |
| NiceGUI | 🔲 | +35 MB | +5% | — | ❌ Not viable |
| Multi-modal voice dashboard | 🔲 | +20 MB | +10% | — | ⚠️ Possible, tight |
| CRM platform (text only) | 🔲 | +10 MB | +5% | — | ✅ Feasible |
| Google/Yandex integrations | 🔲 | +30 MB | 5% | — | ✅ Feasible |

**PicoClaw summary:**
- ✅ Runs the complete current feature set
- ✅ Good for Telegram bot + Web UI + Cloud LLM + Voice (with optimizations)
- ⚠️ Memory is the critical constraint; tmpfs, gpu_mem=16 and persistent_piper are mandatory
- ❌ Cannot run local LLM + voice simultaneously
- ❌ Cannot run RAG knowledge base

---

### 4.2 ZeroClaw (Raspberry Pi Zero 2 W) — Feature Matrix

| Feature Group | Status | RAM used | CPU peak | Verdict |
|---|---|---|---|---|
| OS + Python + Bot core | ✅ | ~310 MB | 15% | ✅ Fits in 512 MB |
| Telegram bot (text only) | ✅ | +60 MB | 10% | ✅ |
| FastAPI Web UI | ✅ | +25 MB | 15% | ⚠️ Total ~395 MB — tight |
| Voice STT (Vosk) | ✅ | +180 MB | 100% | ❌ Does NOT fit alongside bot+web |
| Voice TTS (Piper) | ✅ | +150 MB | 100% | ❌ Does NOT fit alongside Vosk |
| Calendar + Notes + Mail | ✅ | +23 MB | 10% | ✅ Text-only |
| Contact Book + RBAC | ✅ | +5 MB | 2% | ✅ |
| **Text-only total** | | **~420 MB** | **20%** | ✅ Fits |
| **Full voice stack** | | **>665 MB** | **100%** | ❌ Exceeds 512 MB |
| Local LLM | 🔲 | +350+ MB | 100% | ❌ Absolutely not |
| RAG | 🔲 | +140 MB | 60% | ❌ No RAM |
| Any ML inference | — | 90+ MB per model | 100% | ❌ |

**ZeroClaw summary:**
- ✅ Runs text-only Telegram bot + Calendar + Notes + Mail + Cloud LLM
- ✅ Excellent for always-on low-power deployment where voice is not needed
- ❌ Voice (STT + TTS) is not viable — insufficient RAM
- ❌ No capacity for any local AI inference
- **Use case:** Minimal IoT assistant, always-on reminder system, text-only personal bot at ~0.4–2.5 W

---

### 4.3 OpenClaw (Raspberry Pi 5 8 GB + NVMe, or RK3588) — Feature Matrix

| Feature Group | Status | RAM used | CPU peak | TOPS | Verdict |
|---|---|---|---|---|---|
| OS + full bot stack | ✅ | ~750 MB | 20% | — | ✅ Ample headroom |
| Voice STT (Vosk, always-warm) | ✅ | +180 MB | 30% | — | ✅ ~3–4 s latency |
| Voice TTS (Piper medium, tmpfs) | ✅ | +150 MB | 40% | ~0.4 TOPS | ✅ ~2–4 s latency |
| Whisper STT (base) | ✅ | +250 MB | 60% | — | ✅ ~5–8 s latency |
| **All current features** | ✅ | **~1,330 MB** | **70%** | **~0.4 TOPS** | ✅ **~8 s total latency** |
| Local LLM — Phi-3-mini 3.8B Q4 | 🔲 | +2,500 MB | 90% all cores | — | ✅ ~16 s / 80 tok |
| Local LLM — Llama-3.2-3B Q4 | 🔲 | +2,000 MB | 90% | — | ✅ ~16 s / 80 tok |
| RAG embeddings (MiniLM-L6) | 🔲 | +90 MB | 30% | ~0.05 TOPS | ✅ ~0.3 s per query |
| RAG vector DB (FAISS) | 🔲 | +200 MB | 20% | — | ✅ |
| RAG document indexing | 🔲 | +50 MB | 50% | — | ✅ |
| NiceGUI | 🔲 | +35 MB | +5% | — | ✅ |
| CRM + voice input | 🔲 | +60 MB | 20% | — | ✅ |
| Smart central dashboard | 🔲 | +20 MB | 20% | — | ✅ |
| Google/Yandex integrations | 🔲 | +30 MB | 5% | — | ✅ |
| **Full planned stack** | | **~4,315 MB** | **100% peaks** | **~0.5 TOPS** | ✅ Fits in 8 GB |
| With Hailo-8L HAT (13 TOPS) | | same | reduced | **13 TOPS** | ✅ NPU accelerates Piper + embeddings |
| With RK3588 NPU (6 TOPS) | | same | reduced | **6 TOPS** | ✅ RKNN accelerates Piper ~4–5× |

**OpenClaw summary:**
- ✅ Runs every current and planned feature
- ✅ Local LLM at acceptable latency (~16 s on Pi 5, ~8 s on RK3588 with NPU)
- ✅ Full RAG knowledge base with <0.5 s retrieval
- ✅ Voice pipeline <10 s total
- ✅ Future-proof — can run 7B models with RK3588 NPU (12+ tok/s)
- **Use case:** Full personal assistant server, multi-user deployment, smart home hub

---

## 5. Consolidated Feature Feasibility Matrix

| TODO ref | Function | Status | PicoClaw (Pi 3 B+) | ZeroClaw (Pi Zero 2 W) | OpenClaw (Pi 5 / RK3588) |
|---|---|---|---|---|---|
| Core | Telegram bot (text) | ✅ | ✅ | ✅ | ✅ |
| Core | Web UI (FastAPI) | ✅ | ✅ | ⚠️ | ✅ |
| Core | Cloud LLM (OpenRouter) | ✅ | ✅ | ✅ | ✅ |
| Core | Calendar (NL events) | ✅ | ✅ | ✅ | ✅ |
| Core | Markdown Notes | ✅ | ✅ | ✅ | ✅ |
| Core | Mail Digest (IMAP) | ✅ | ✅ | ✅ | ✅ |
| Core | Contact Book | ✅ | ✅ | ✅ | ✅ |
| Core | RBAC + Security | ✅ | ✅ | ✅ | ✅ |
| Voice | Voice STT (Vosk) | ✅ | ✅ ~15 s | ❌ no RAM | ✅ ~3–4 s |
| Voice | Voice TTS (Piper) | ✅ | ✅ ~10 s | ❌ no RAM | ✅ ~2–4 s |
| Voice | Wake-word loop | ✅ | ⚠️ high CPU | ❌ no RAM | ✅ |
| Voice | Whisper STT | ✅ | ⚠️ 30–35 s | ❌ | ✅ ~5–8 s |
| §2.1 | Conversation memory | 🔲 | ✅ | ✅ | ✅ |
| §3.1 | Multi-LLM providers | 🔲 | ✅ | ✅ | ✅ |
| §3.2 | Local LLM (offline fallback) | 🔲 | ⚠️ ~90 s | ❌ | ✅ ~16 s |
| §4.1 | RAG knowledge base | 🔲 | ❌ | ❌ | ✅ |
| §8.5 | NiceGUI UI | 🔲 | ❌ | ❌ | ✅ |
| §10 | Doc upload + multimodal RAG | 🔲 | ❌ | ❌ | ✅ |
| §11 | Central voice dashboard | 🔲 | ⚠️ | ❌ | ✅ |
| §12 | Voice input everywhere | 🔲 | ✅ | ❌ | ✅ |
| §13 | Smart CRM | 🔲 | ✅ (text) | ⚠️ | ✅ |
| §14 | Developer Board | 🔲 | ⚠️ | ❌ | ✅ |
| §15 | Google/Yandex Calendar/Drive | 🔲 | ✅ | ✅ | ✅ |
| §16 | KIM personal assistant | 🔲 | ⚠️ subset | ❌ | ✅ |
| §17 | Max Messenger UI | 🔲 | ⚠️ | ❌ | ✅ |
| §18 | ZeroClaw realization | 🔲 | — | 🎯 text-only | — |
| §19 | OpenClaw realization | 🔲 | — | — | 🎯 full stack |

**Legend:** ✅ Fully viable · ⚠️ Limited/slow/constrained · ❌ Not viable · 🎯 Target platform for this item

---

## 6. Mini-Computer Research — Local Voice + RAG + Local LLM

This section evaluates hardware alternatives capable of running the full planned stack (voice, RAG, local LLM) locally without cloud dependence.

### 6.1 Selection Criteria

For a device to serve as **OpenClaw** hardware it must satisfy:

| Requirement | Minimum spec |
|---|---|
| Voice STT (Vosk/Whisper) | ≥2 GB RAM; ≥2 GHz ARM Cortex-A55 or better |
| Voice TTS (Piper medium) | ≥1 GB free RAM after OS; ≥1.5 GHz |
| Local LLM (3–4B params, usable latency) | ≥4 GB RAM (Phi-3-mini); ≥6 GB for 7B |
| RAG embeddings (MiniLM-L6) | ≥2 GB RAM; optional NPU for acceleration |
| Storage (models + data) | ≥32 GB fast storage (NVMe preferred) |
| Power budget | ≤20 W for 24/7 operation |
| Linux support | Debian/Ubuntu aarch64 or x86_64 |

### 6.2 Evaluated Hardware

#### Tier 1 — Minimum Viable (Local LLM ~16–40 s per response)

| Board | CPU | RAM | NPU | Storage | LLM tok/s (3–4B Q4) | Voice latency | Price | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Raspberry Pi 5 (4 GB)** | 4× A76 @ 2.4 GHz | 4 GB LPDDR4X | None (Hailo HAT optional) | NVMe via HAT | ~3–4 tok/s | ~5–7 s | ~$60 | ✅ Min viable |
| **Raspberry Pi 5 (8 GB)** | 4× A76 @ 2.4 GHz | 8 GB LPDDR4X | None (Hailo-8L: 13 TOPS) | NVMe via HAT | ~5 tok/s | ~5–7 s | ~$80 | ✅ Recommended |
| **Banana Pi BPI-M5 Pro** | 4× A76 + 4× A55 (RK3576) | 4–16 GB | 6 TOPS NPU | NVMe M.2 | ~6–8 tok/s | ~3–5 s | ~$60–$90 | ✅ Good value |

#### Tier 2 — Comfortable (Local LLM ~8–16 s, 7B models viable)

| Board | CPU | RAM | NPU | Storage | LLM tok/s (7B Q4) | Voice latency | Price | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Orange Pi 5 Pro** | 4× A76 + 4× A55 (RK3588S) | 8–16 GB LPDDR4X | **6 TOPS** | NVMe M.2 | 12–15 tok/s | ~2–3 s | ~$80–$100 | ✅ Best value |
| **Radxa Rock 5B** | 4× A76 + 4× A55 (RK3588) | 8–16 GB LPDDR4X | **6 TOPS** | NVMe M.2 (PCIe 3.0×4) | 12–15 tok/s | ~2–3 s | ~$90–$120 | ✅ Top ARM SBC |
| **Khadas VIM4** | 4× A73 + 4× A53 (A311D2) | 8 GB LPDDR4X | ~5 TOPS (AMLNN) | eMMC + M.2 | ~8–10 tok/s | ~3–4 s | ~$100 | ✅ Good |
| **Pine64 QuartzPro64** | 4× A55 + 4× A510 (RK3588) | 8–16 GB | 6 TOPS | NVMe | 12–15 tok/s | ~2–3 s | ~$90 | ✅ |
| **Raspberry Pi 5 + Hailo-8L HAT** | 4× A76 @ 2.4 GHz | 8 GB | **13 TOPS** | NVMe | 10–15 tok/s (HAT) | ~1–2 s | ~$80 + $70 HAT | ✅ Best Pi 5 setup |

#### Tier 3 — Production (Full local AI, <8 s total latency)

| Board | CPU | RAM | NPU/GPU | Storage | LLM tok/s (7B Q4) | Price | Verdict |
|---|---|---|---|---|---|---|---|
| **Nvidia Jetson Orin Nano 8 GB** | 6× A78AE @ 1.5 GHz | 8 GB unified | **40 TOPS** | NVMe | ~20–30 tok/s | ~$250 | ✅ Best-in-class NPU |
| **Nvidia Jetson Orin NX 16 GB** | 8× A78AE @ 2.0 GHz | 16 GB unified | **100 TOPS** | NVMe | ~40–50 tok/s | ~$500 | ✅ Server-grade |
| **Intel N100 mini-PC** (e.g. Beelink EQ12) | 4× E-core @ 3.4 GHz | 8–16 GB DDR5 | iGPU (OpenVINO) | NVMe | ~5–10 tok/s | ~$150 | ✅ x86, max compat |
| **AMD Ryzen 7 mini-PC** | 8× Zen4 @ 5 GHz | 32–64 GB DDR5 | RDNA3 iGPU | NVMe | ~20–40 tok/s | ~$300–$500 | ✅ Overkill but future-proof |

#### Tier 4 — Cloud/VPS (No local inference, minimal hardware)

| Option | CPU | RAM | AI inference | Price/month | Verdict |
|---|---|---|---|---|---|
| **Hetzner CX22** | 4× vCPU (AMD EPYC) | 4 GB | API only (OpenRouter) | ~$5 | ✅ Text-only, no voice |
| **Hetzner CAX21** | 4× ARM Ampere | 8 GB | llama.cpp possible | ~$9 | ✅ Local LLM via llama.cpp |
| **Oracle Cloud Free** | 4× OCPU Ampere A1 | 24 GB | llama.cpp 7B | Free | ✅ Best free tier |

### 6.3 Recommended Hardware Configurations

#### Configuration A — ZeroClaw (Minimal / Always-on text bot)

**Hardware:** Raspberry Pi Zero 2 W + 32 GB microSD  
**Total cost:** ~$25  
**Power:** 0.4–2.5 W (perfect for 24/7 on USB power bank)

```
Features: Telegram bot ✅ · Web UI ✅ · Cloud LLM ✅ · Calendar ✅ · Notes ✅ · Mail ✅
Voice: ❌ Not viable
Local LLM: ❌ Not viable
RAG: ❌ Not viable
```

**When to choose:** Battery-powered IoT assistant, minimal cost deployment, text-only use.

---

#### Configuration B — PicoClaw (Standard / Current production)

**Hardware:** Raspberry Pi 3 B+ + 32 GB A1 microSD + USB microphone + speaker  
**Optional:** Samsung 840 256 GB USB SSD for Piper model + swap  
**Total cost:** ~$50–$75  
**Power:** 3–5 W

```
Features: All current features ✅
Voice: ✅ (~15 s STT, ~10 s TTS warm)
Local LLM: ⚠️ Qwen2-0.5B only (~90 s) — emergency fallback only
RAG: ❌ Not viable
```

**Optimizations required for acceptable voice latency:**
1. `gpu_mem=16` in `/boot/firmware/config.txt`
2. `tmpfs_model=true` (pin Piper ONNX in RAM)
3. `persistent_piper=true` (keep Piper process warm)
4. `piper_low_model=true` (halves TTS inference time)
5. CPU governor → `performance`

**When to choose:** Home/office personal assistant, acceptable voice latency ~20–25 s with optimizations.

---

#### Configuration C — OpenClaw Standard (Pi 5, recommended)

**Hardware:** Raspberry Pi 5 8 GB + M.2 NVMe HAT + 256 GB NVMe SSD + USB microphone + speaker  
**Total cost:** ~$130–$160  
**Power:** 5–12 W

```
Features: All current + all planned ✅
Voice: ✅ (<8 s total)
Local LLM: ✅ Phi-3-mini at ~5 tok/s (~16 s / 80-tok answer)
RAG: ✅ MiniLM embeddings + FAISS
```

**When to choose:** Full personal assistant, local-first deployment, office or home server.

---

#### Configuration D — OpenClaw Pro (RK3588 — best value for AI)

**Hardware:** Orange Pi 5 Pro 8 GB + 256 GB NVMe + USB microphone + speaker  
**Total cost:** ~$120–$150  
**Power:** 8–15 W

```
Features: All current + all planned ✅
Voice: ✅ (<5 s total; Piper accelerated via RKNN NPU 6 TOPS)
Local LLM: ✅ Phi-3-mini ~8–10 tok/s; 7B models ~12–15 tok/s
RAG: ✅ MiniLM embeddings accelerated by NPU
TOPS: 6 TOPS available for ONNX models via RKNN-Toolkit
```

**When to choose:** Best cost/performance ratio for local AI workloads; multi-user deployment.

---

#### Configuration E — OpenClaw Max (Jetson Orin / High-end mini-PC)

**Hardware:** Nvidia Jetson Orin Nano 8 GB + 256 GB NVMe, or Beelink EQ12 (N100) 16 GB  
**Total cost:** ~$250–$350  
**Power:** 10–25 W

```
Features: All current + all planned ✅
Voice: ✅ (<3 s total)
Local LLM: ✅ 7B models at 20–30 tok/s
RAG: ✅ Multimodal RAG with vision models
TOPS: 40 TOPS (Jetson) / OpenVINO (N100)
```

**When to choose:** Production server, multi-user CRM platform, full multimodal AI.

---

## 7. Key Findings & Recommendations

### 7.1 Critical Bottlenecks by Platform

| Bottleneck | PicoClaw (Pi 3 B+) | ZeroClaw (Pi Zero 2 W) | OpenClaw (Pi 5 / RK3588) |
|---|---|---|---|
| RAM | ⚠️ Critical — near 1 GB limit | 🔴 Critical — 512 MB insufficient for voice | ✅ 8 GB — ample for all features |
| CPU (ONNX inference) | 🔴 Bottleneck for Piper/Vosk/LLM | 🔴 Worse than Pi 3 (1 GHz vs 1.4 GHz) | ✅ A76 is 3–4× faster per core |
| Storage I/O | ⚠️ microSD limits cold-start | ⚠️ Same | ✅ NVMe eliminates storage bottleneck |
| NPU/TOPS | ❌ None | ❌ None | ✅ 6–13 TOPS available |

### 7.2 Minimum Hardware for Each Feature Tier

| Tier | Required Hardware | Key constraint |
|---|---|---|
| Text-only bot | Pi Zero 2 W (512 MB) | Cloud LLM required |
| Voice assistant (acceptable latency) | Pi 3 B+ 1 GB + optimizations | tmpfs + persistent_piper mandatory |
| Local LLM fallback (emergency) | Pi 3 B+ 1 GB (Qwen2-0.5B only) | Cannot run alongside voice |
| Voice + local LLM (usable) | Pi 5 4 GB + NVMe | Phi-3-mini at ~3–4 tok/s |
| Voice + local LLM (comfortable) | Pi 5 8 GB + NVMe | Phi-3-mini at ~5 tok/s |
| Voice + RAG + local LLM | Pi 5 8 GB + NVMe | Full stack ~4.3 GB RAM |
| Full planned feature set | Pi 5 8 GB or RK3588 8 GB | OpenClaw recommended |
| Production multi-user | Jetson Orin / mini-PC | 40+ TOPS, 16+ GB RAM |

### 7.3 Upgrade Path

```
ZeroClaw (Pi Zero 2 W, $25)
    → text-only personal bot, always-on, battery-powered

PicoClaw (Pi 3 B+, $50–75)
    → full current feature set, voice with ~20 s latency
    → upgrade path: add USB SSD → Piper cold-start eliminated

OpenClaw Standard (Pi 5 8 GB + NVMe, $130–160)
    → full feature set + local LLM + RAG
    → voice <8 s, local LLM ~16 s / answer

OpenClaw Pro (Orange Pi 5 / Rock 5B 8 GB, $120–150)
    → same as Standard + 6 TOPS NPU
    → best cost/performance for AI workloads
    → 7B models at 12–15 tok/s

OpenClaw Max (Jetson Orin Nano 8 GB, $250)
    → production deployment, 40 TOPS
    → <3 s voice, <5 s local LLM response
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
