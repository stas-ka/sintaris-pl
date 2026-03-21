# Hardware Performance Analysis — Taris Voice Assistant

**Date:** March 2026  
**Target device:** Raspberry Pi 3 B+ (BCM2837B0, 4× Cortex-A53 @ 1.4 GHz, 1 GB LPDDR2)  
**Pipeline analysed:** Telegram voice session + standalone voice assistant (`voice_assistant.py`)

---

## 1. Current Hardware Profile

| Component | Spec | Impact on voice pipeline |
|---|---|---|
| CPU | 4× ARM Cortex-A53 @ 1.4 GHz | In-order, weak SIMD — bottleneck for ONNX | 
| RAM | 1 GB LPDDR2 @ 900 MHz dual-channel | All processes compete for 1 GB total |
| Storage | microSD (Class 10 / A1) | ~25–40 MB/s sequential read — bottlenecks model loading |
| USB | USB 2.0 shared DWC_OTG controller | Known isochronous bug with some USB audio devices |
| Network | 100 Mbps Ethernet / 802.11n 2.4 GHz | LLM round-trip ~1–3 s, adequate |
| GPU | VideoCore IV, 64–256 MB shared | Not usable for general compute |
| NPU/DSP | None | No hardware acceleration for inference |

### Memory budget at runtime

| Component | RAM peak | Notes |
|---|---|---|
| Raspberry Pi OS + kernel | ~250 MB | Bookworm baseline |
| Python + pyTelegramBotAPI | ~60 MB | Bot process baseline |
| Vosk model (small-ru) | ~180 MB | Loaded into memory on first voice message |
| Piper ONNX (medium) | ~150 MB | Cold-loaded per TTS call; ~10–15 s from microSD |
| taris Go binary | ~30 MB | Short-lived subprocess |
| ffmpeg subprocesses (×2) | ~20 MB | Per voice note |
| **Total** | **~690 MB** | Leaves ~310 MB for OS page cache & buffers |

With 1 GB RAM, the system is operating with very little headroom. When all components are simultaneously active the OS must reclaim page cache, causing the microSD to be read repeatedly — this is the root cause of the 10–15 s Piper cold-start.

---

## 2. Measured Pipeline Latency (Telegram Voice Session — Pi 3 B+)

| Stage | Tool | Observed time | Bottleneck |
|---|---|---|---|
| Download OGG from Telegram | Telegram API | ~0.2 s | Network I/O (none) |
| OGG → 16 kHz PCM (ffmpeg) | ffmpeg subprocess | ~1 s | Minimal CPU |
| Speech-to-Text | Vosk `vosk-model-small-ru` | **~15 s** | CPU — single Cortex-A53 core, no SIMD |
| LLM call (taris → OpenRouter) | Go subprocess + HTTPS | ~2 s | Network I/O (fine) |
| TTS synthesis | Piper `ru_RU-irina-medium` ONNX | **~40 s** | ONNX model load from SD (~15 s) + inference (~25 s) |
| PCM → OGG Opus (ffmpeg) | ffmpeg | ~0.3 s | Minimal |
| **Total** | | **~58 s** | ❌ target: <15 s |

### Why STT takes 15 s

Vosk feeds raw PCM to a Kaldi decoder in Python. The Cortex-A53:
- Has a 32 KB L1 / 512 KB L2 cache — the 48 MB model thrashes L2 constantly
- Is an **in-order** design — cannot speculate past memory stalls
- Has weak NEON FPU for the floating-point MFCC and beam-search work

Result: ~40–60% of one core for the full audio duration (real-time factor ≈ 1.5×).

### Why TTS takes 40 s

Piper ONNX Runtime breakdown:
1. **Model load from microSD** — the 66 MB `.onnx` file is read from microSD at ~25 MB/s → **~2.5 s read** + kernel page-fault overhead in Python → **~10–15 s cold** when page cache is cold
2. **ONNX Runtime inference** — matrix multiplications on Cortex-A53 without vectorisation accelerator → **~20–25 s for 200 chars** of Russian text

---

## 3. Current Pi 3 B+ Tuning Opportunities

These adjustments improve performance **without changing hardware**:

### 3.1 CPU Governor — switch to `performance`

By default Raspberry Pi OS uses the `ondemand` governor. Under sustained load (Vosk or Piper) the CPU ramps up only after a few 100 ms delay, wasting cycles during inference startup.

```bash
# Set all cores to performance mode
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Make persistent across reboots (add to /etc/rc.local or a systemd service):
echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
```

**Expected gain:** STT latency reduction ~10–15%, TTS ~5–8%.

### 3.2 Reduce GPU memory split

The VideoCore IV GPU reserves GPU memory from system RAM. Default is often 64–76 MB but can be reduced further since the bot never uses display/camera.

```bash
# /boot/firmware/config.txt
gpu_mem=16
```

Frees ~50–60 MB additional RAM for OS page cache → Piper ONNX file can stay warm in cache across calls.

**Expected gain:** Eliminates most of the Piper cold-start (15 s → 2–3 s) on second and subsequent calls.

### 3.3 zram — compressed RAM swap

With only ~310 MB headroom, the OS occasionally needs to evict Python heap or Vosk model pages. Adding zram swap (compressed in-CPU-RAM swap, ~5:1 compression) prevents hitting the slow microSD swap.

```bash
sudo apt install zram-tools
# /etc/default/zramswap
ALGO=lz4       # fastest; lz4 > lzo > zstd at the cost of ratio
PERCENT=25     # 25% of RAM = 256 MB → ~1.2 GB effective with lz4
sudo systemctl restart zramswap
```

**Expected gain:** Reduces memory pressure; prevents STT/TTS time spikes under memory load.

### 3.4 Swap backing store on USB SSD (not microSD)

If you have a USB SSD or fast USB drive, moving the swap partition there removes the SD bottleneck for swap I/O.

```bash
sudo dphys-swapfile swapoff
# Edit /etc/dphys-swapfile: CONF_SWAPFILE=/mnt/usb/swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### 3.5 Overclock CPU (requires active cooling)

Pi 3 B+ can be safely overclocked to 1.5–1.6 GHz with a heatsink. The BCM2837B0 is the revised B0 stepping rated for higher clock.

```ini
# /boot/firmware/config.txt
arm_freq=1500
arm_freq_min=300
over_voltage=2
```

With a heatsink (the flat metal pad on a Pi 3 B+ dissipates ~3 W at 1.4 GHz, ~4 W at 1.5 GHz):
- **Expected gain:** ~7% across all CPU-bound stages.

### 3.6 Pin the Piper ONNX model in `tmpfs`

If GPU memory is reduced to 16 MB and zram is active, you may have enough headroom to copy the ONNX model to `tmpfs`:

```bash
sudo mkdir -p /dev/shm/piper
cp ~/.taris/ru_RU-irina-medium.onnx /dev/shm/piper/
```

Then set `PIPER_MODEL=/dev/shm/piper/ru_RU-irina-medium.onnx` in `taris-telegram.service`. RAM reads are ~10× faster than microSD reads.

**Expected gain:** Model load time: 15 s → 1–2 s. Combined with `warm_piper` opt this eliminates the cold-start entirely.

### 3.7 Use `ru_RU-irina-low` instead of `medium` quality

The low-quality variant of the same Russian Irina voice is approximately half the size in computation terms:

```bash
# Download low quality model
wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/low/ru_RU-irina-low.onnx \
     -O ~/.taris/ru_RU-irina-low.onnx
wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/low/ru_RU-irina-low.onnx.json \
     -O ~/.taris/ru_RU-irina-low.onnx.json
```

Set `PIPER_MODEL` in `taris-telegram.service` to the low model. Speech quality remains acceptable for conversational / notification use.

**Expected TTS saving:** ~10 s (inference time halves).

### 3.8 Summary — current Pi 3 B+ tuning impact

| Tuning | Effort | Expected saving |
|---|---|---|
| CPU governor → performance | Trivial | STT −2 s, TTS −3 s |
| gpu_mem=16 | Trivial | TTS cold-start −10 s (2nd+ calls) |
| Piper model in tmpfs | Low | TTS cold-start ${−}$10–13 s (every call) |
| zram (lz4, 25%) | Low | Prevents latency spikes under memory pressure |
| Piper low model | Low | TTS inference −10 s |
| Overclock to 1.5 GHz | Medium (needs heatsink) | −7% all CPU stages |
| **All combined** | Low/Medium | **Total: ~28 s → ~10–12 s** |

---

## 4. Recommended Raspberry Pi Hardware Upgrade Path

### Use case A — Voice assistant only (current use case)

#### Raspberry Pi 4 Model B — 2 GB or 4 GB

| Property | Pi 3 B+ | Pi 4 B (2 GB) | Pi 4 B (4 GB) |
|---|---|---|---|
| CPU | 4× A53 @ 1.4 GHz | 4× **A72 @ 1.8 GHz** | 4× A72 @ 1.8 GHz |
| CPU arch | ARMv8-A in-order | ARMv8-A **out-of-order** | ARMv8-A out-of-order |
| RAM | 1 GB LPDDR2 | 2 GB **LPDDR4** | 4 GB LPDDR4 |
| RAM bandwidth | ~6 GB/s | **~25 GB/s** | ~25 GB/s |
| USB | USB 2.0 shared | **USB 3.0** (1 Gbps) | USB 3.0 |
| Storage | microSD | microSD / **USB SSD** | microSD / USB SSD |
| GPIO | 40-pin | 40-pin (compatible) | 40-pin (compatible) |
| Buy price | ~$35 | ~$45 | ~$55 |

**Impact on voice pipeline (Pi 4 B, 2 GB):**

| Stage | Pi 3 B+ | Pi 4 B 2 GB | Notes |
|---|---|---|---|
| OGG → PCM | 1 s | <0.3 s | 4× faster ffmpeg |
| Vosk STT | 15 s | **~4 s** | A72 OOO + larger L2, faster NEON |
| LLM | 2 s | 2 s | Network-bound, unchanged |
| Piper cold-start | 15 s | **~2 s** | USB SSD or LPDDR4 page cache |
| Piper inference | 25 s | **~6 s** | A72 SIMD ~4× faster for ONNX matmul |
| **Total** | **~58 s** | **~15 s** | ✅ In target range |

With `warm_piper` on and `tmpfs` model: **~6–8 s** end-to-end on Pi 4.

The **Pi 4 B 2 GB** is the minimum recommended upgrade for voice assistant use. The **Pi 4 B 4 GB** is recommended if deploying any local processing alongside the voice bot.

#### Raspberry Pi 5 — 4 GB or 8 GB

| Property | Pi 4 B | Pi 5 |
|---|---|---|
| CPU | 4× A72 @ 1.8 GHz | 4× **A76 @ 2.4 GHz** |
| CPU gen | Cortex-A72 | **Cortex-A76** (+35% IPC) |
| RAM | 4 GB LPDDR4 | 4/8 GB **LPDDR4X** |
| PCIe | None | **PCIe 2.0 × 1** (NVMe via HAT) |
| Storage peak | ~50 MB/s (microSD) | **~900 MB/s** (NVMe SSD) |
| Price | ~$55 | ~$60–80 |

Pi 5 + NVMe HAT eliminates storage as a bottleneck entirely. Piper model load from NVMe: **~0.07 s** (66 MB / 900 MB/s). The A76 core also has a larger out-of-order window and improved FP/SIMD that benefits ONNX inference.

Estimated end-to-end on Pi 5 with NVMe:
- STT: ~2 s | TTS cold-start: <0.2 s | TTS inference: ~3–4 s | **Total: ~8 s**

---

### Use case B — LLM inference on-device (no OpenRouter cloud)

Running a local LLM (e.g. Llama, Mistral, Phi-3-mini) on a Raspberry Pi requires hardware that can fit the model in RAM and run inference at an acceptable tokens-per-second rate.

#### Minimum viable: Pi 5 8 GB + NVMe SSD

| Model size | Required RAM | Tokens/s on Pi 5 (8 GB, llama.cpp Q4_K_M) |
|---|---|---|
| Phi-3-mini 3.8B (Q4) | ~2.5 GB | ~5–7 tok/s |
| Llama-3.2 3B (Q4) | ~2.5 GB | ~5–7 tok/s |
| Mistral 7B (Q4) | ~5 GB | ~2–3 tok/s |
| Llama-3.1 8B (Q4) | ~6 GB | ~1.5–2 tok/s |

At 5–7 tok/s for a 3B model, a 100-token Russian response takes ~15–20 s. Combined with STT/TTS that gives a reasonable ~25–30 s total — practical for non-realtime bot queries but slow for conversation.

Recommended stack for local LLM:
- **Runtime:** `llama.cpp` — optimised ARM NEON kernels, no Python overhead
- **Model:** `Phi-3-mini-4k-instruct` (3.8B) or `Llama-3.2-3B-Instruct` in GGUF Q4_K_M
- **Server:** `llama.cpp` HTTP server replacing the `taris agent` subprocess call,  
  invoked via `http://localhost:8080/v1/chat/completions` (OpenAI-compatible endpoint)

```bash
# Pi 5, llama.cpp
cmake -B build -DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS .
cmake --build build --config Release -j4
./build/bin/llama-server \
    --model ~/models/phi-3-mini-4k-instruct-q4.gguf \
    --port 8080 --n-gpu-layers 0 --threads 4
```

#### Purpose-built edge AI hardware (if Pi 5 is too slow)

| Board | CPU | AI accelerator | RAM | LLM perf |
|---|---|---|---|---|
| **Orange Pi 5** | 4× A76 + 4× A55 @ 2.4 GHz | RK3588 NPU **6 TOPS** | 8/16 GB LPDDR4X | ~12–15 tok/s (7B Q4) |
| **Radxa Rock 5B** | Same RK3588 | NPU 6 TOPS | 16 GB | ~12–15 tok/s (7B Q4) |
| **Khadas VIM4** | 4× A73 + 4× A53 @ 2.2 GHz | AMLNN NPU ~5 TOPS | 8 GB | ~8–10 tok/s (7B Q4) |
| **Milk-V Pioneer** | RISC-V SG2042 × 64 cores | None | 128 GB DDR4 | ~6 tok/s (70B FP16) |

The RK3588-based boards (Orange Pi 5, Rock 5B) are the best Pi alternatives for LLM workloads at under $100, offering 4× the CPU performance of Pi 5 and an NPU that llm.cpp/rknn toolchains can target.

---

### Use case C — LLM + RAG on-device

RAG (Retrieval-Augmented Generation) adds a vector database lookup step before the LLM call.

**RAG pipeline on Pi:**
```
voice STT → query text
  → [embedding model] → vector → [vector DB search] → top-k documents
  → LLM with the retrieved context → answer
  → TTS → voice reply
```

#### Additional components and their RAM/CPU cost

| Component | RAM | Notes |
|---|---|---|
| Embedding model (e.g. `all-MiniLM-L6-v2`, 23M params Q8) | ~90 MB | Fast: ~0.3 s per query on Pi 5 |
| Vector database (e.g. Chroma or LanceDB, 10k docs) | ~200–500 MB | In-process; HNSW index |
| LLM (Phi-3-mini 3.8B Q4) | ~2.5 GB | Needs Pi 5 8 GB minimum |
| **Total** | **~3.4 GB** | Requires ≥ 4 GB RAM; 8 GB strongly recommended |

#### Recommended hardware for LLM + RAG

| Scenario | Board | RAM | Storage | Rationale |
|---|---|---|---|---|
| **Minimal viable** | Pi 5 | 8 GB | NVMe SSD ≥ 32 GB | Fits all components, ~15–20 s response |
| **Comfortable** | Orange Pi 5 / Rock 5B | 8–16 GB | NVMe SSD | 2–3× faster inference, NPU for embeddings |
| **Production** | Orange Pi 5 Max (RK3588S2) | 16 GB | NVMe SSD 256 GB | Runs 7B models at 12+ tok/s |

**Minimal RAG stack (Pi 5, 8 GB, Python):**

```bash
pip install llama-cpp-python chromadb sentence-transformers
```

```python
# Minimal RAG example with llama.cpp server
from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer
import requests

embedder = SentenceTransformer("all-MiniLM-L6-v2")
db = PersistentClient(path="~/.taris/rag_db")
collection = db.get_or_create_collection("docs")

def rag_query(query: str) -> str:
    q_emb = embedder.encode([query]).tolist()
    results = collection.query(query_embeddings=q_emb, n_results=3)
    context = "\n".join(results["documents"][0])
    prompt = f"Context:\n{context}\n\nQuestion: {query}\nAnswer:"
    resp = requests.post("http://localhost:8080/v1/completions",
                         json={"prompt": prompt, "max_tokens": 256})
    return resp.json()["choices"][0]["text"].strip()
```

---

## 5. Summary Recommendations

### Immediate (zero hardware cost) — current Pi 3 B+

| Action | Impact |
|---|---|
| `gpu_mem=16` in config.txt | Frees ~50 MB RAM → Piper cache stays warm |
| CPU governor → `performance` | −2–3 s across STT+TTS |
| Copy Piper ONNX to `/dev/shm` | Eliminates model-load cold-start (−15 s) |
| Enable `warm_piper` bot opt | Cold-start on first call eliminated |
| Install zram (lz4, 25%) | Prevents memory-pressure spikes |
| Use `ru_RU-irina-low` model | TTS inference −10 s |
| **Expected total** | **58 s → ~15–18 s** |

### Near-term hardware upgrade — voice assistant only

**→ Raspberry Pi 4 B, 2 GB** (~$45)
- Drop-in OS compatibility, same GPIO pinout
- All services migrate unchanged
- Expected latency: **~15 s total** (vs 58 s on Pi 3)
- Required config change: none (services just run faster)

**→ Raspberry Pi 5, 4 GB** (~$60) if budget allows
- NVMe HAT addition (~$15) makes model loading near-instant
- Expected latency: **~8 s total**

### Medium-term — local LLM + RAG

**→ Raspberry Pi 5, 8 GB + NVMe SSD** (~$80 + ~$15 HAT + ~$20 SSD)
- Runs Phi-3-mini locally at ~5–7 tok/s
- Full offline operation (no OpenRouter dependency)
- RAG with ~10k document KB fits comfortably in 8 GB

**→ Orange Pi 5 / Radxa Rock 5B, 8 GB** (~$80–100)
- Similar price to Pi 5, ~2–3× CPU performance for inference
- RK3588 NPU (6 TOPS) accelerates embedding and smaller ONNX models via RKNN-Toolkit
- Best price/performance for on-device LLM + RAG

---

## 6. Migration Checklist (Pi 3 → Pi 4/5)

All services are portable without code changes. Only the HAT driver section needs attention if RB-TalkingPI I²S HAT is connected.

```bash
# On new Pi — after flashing Bookworm and copying files:
# 1. Re-run setup scripts
sudo bash /tmp/setup_voice.sh

# 2. Copy model cache (optional — setup_voice.sh downloads fresh)
rsync -av stas@OldPi:~/.taris/ru_RU-irina-medium.onnx ~/.taris/

# 3. Restore services
sudo cp src/services/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable taris-telegram taris-voice taris-gateway
sudo systemctl start  taris-telegram taris-voice taris-gateway

# 4. Apply GPU memory tuning
echo "gpu_mem=16" | sudo tee -a /boot/firmware/config.txt

# 5. Set CPU governor
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# 6. Install zram
sudo apt install -y zram-tools
sudo sed -i 's/PERCENT=.*/PERCENT=25/' /etc/default/zramswap
sudo sed -i 's/#\?ALGO=.*/ALGO=lz4/' /etc/default/zramswap
sudo systemctl restart zramswap

# 7. (Pi 5 with NVMe) copy ONNX to fast storage path
#    Update PIPER_MODEL env in taris-telegram.service accordingly
```

---

## 7. Hardware Acceleration Adapters for Raspberry Pi 3 B+

The Pi 3 B+ has no NPU, weak SIMD, and only USB 2.0. Four categories of add-on hardware can close the gap without replacing the board.

---

### 7.1 Intel Neural Compute Stick 2 (Myriad X VPU)

**The most impactful single adapter for this specific pipeline.**

| Property | Value |
|---|---|
| Chip | Intel Myriad X MA2485 VPU |
| Performance | 4 TOPS (INT8/FP16 mixed) |
| Interface | USB 2.0 / 3.0 — works on Pi 3 B+ USB 2.0 |
| Runtime | OpenVINO (ARM aarch64 build available) |
| Price | ~$70–100 (eBay; discontinued by Intel 2023, still widely available) |
| Piper ONNX support | ✅ — ONNX → OpenVINO IR via `mo.py`; runs on NCS2 |
| Vosk / kaldi support | ⚠️ — indirect: switch STT engine to whisper.cpp with OpenVINO backend |

#### Why it helps

Both bottlenecks in the pipeline — Piper ONNX TTS and STT inference — are ONNX-based matrix operations. The NCS2 can execute them off-CPU via OpenVINO:

- **Piper TTS** (Vits encoder+decoder ONNX): convert once to OpenVINO IR, run on NCS2. Expected TTS inference: **~40 s → ~5–8 s** on Pi 3.
- **STT**: Vosk uses an internal Kaldi backend and cannot use NCS2 directly. Switch to `faster-whisper` (CTranslate2, which has an OpenVINO backend) or `whisper.cpp` compiled with OpenVINO. Expected STT: **~15 s → ~2–3 s**.

#### Setup

```bash
# Install OpenVINO Runtime for ARM (aarch64)
pip3 install openvino==2023.3.0   # last confirmed aarch64-compatible release

# Convert Piper ONNX to OpenVINO IR (run once on any x86 machine or Pi)
pip install openvino-dev
mo --input_model ~/.taris/ru_RU-irina-medium.onnx \
   --output_dir ~/.taris/piper_ov/ \
   --model_name irina_medium

# Run inference with NCS2 as device
python3 - <<'EOF'
from openvino.runtime import Core
ie = Core()
model = ie.read_model("~/.taris/piper_ov/irina_medium.xml")
compiled = ie.compile_model(model, "MYRIAD")   # MYRIAD = NCS2
EOF
```

**Note on Piper integration:** Piper currently hard-codes ONNX Runtime for inference. To use NCS2 you would replace the subprocess call (`subprocess.run([PIPER_BIN, ...])`) with a direct Python OpenVINO inference call in `_tts_to_ogg()`. This requires porting Piper's text→phoneme→spectrogram→waveform pipeline to call the OpenVINO compiled model directly — medium complexity, but feasible.

#### Expected impact on full pipeline (Pi 3 + NCS2)

| Stage | Without NCS2 | With NCS2 |
|---|---|---|
| STT (whisper.cpp tiny + OV backend) | 15 s | **~3 s** |
| TTS inference (Piper ONNX via OV) | 25 s | **~6 s** |
| TTS model load (first call) | 15 s | **~2 s** (cached in NCS2) |
| **Total** | **~58 s** | **~12–14 s** |

---

### 7.2 Google Coral USB Accelerator (Edge TPU)

| Property | Value |
|---|---|
| Chip | Google Edge TPU ASIC |
| Performance | 4 TOPS (INT8 only) |
| Interface | USB 2.0 / 3.0 — works on Pi 3 B+ |
| Runtime | TFLite Delegate (not ONNX natively) |
| Price | ~$60 (still in production via Mouser/Digikey) |
| Piper ONNX support | ❌ — requires TFLite INT8 quantised model, heavyweight conversion |
| Vosk support | ❌ — Kaldi is not TFLite-compatible |

#### Verdict for this pipeline

Coral is optimised for TFLite INT8 vision/audio models. Neither Piper nor Vosk can run on it without full model retraining in TFLite + INT8 quantisation and compilation to Edge TPU format. The conversion chain (ONNX → TFLite → INT8 quant → `edgetpu_compiler`) is lossy for Russian speech synthesis quality.

**Useful only if** you switch both STT and TTS to purpose-trained TFLite Russian models (e.g. Google's TFLite ASR model + a TFLite speech synthesis model). There are no production-quality Russian TFLite TTS models available as of 2026 that match Piper Irina quality.

**Not recommended** for this pipeline as a drop-in accelerator.

---

### 7.3 ReSpeaker 2-Mics / 4-Mics Pi HAT (Seeed Studio)

**Not an inference accelerator, but directly attacks the STT bottleneck by reducing audio length.**

| Property | Value |
|---|---|
| Chip | XMOS XU Series audio DSP (on 4-mic variant: XVF3000) |
| Interface | I²S HAT (GPIO header) |
| Function | Hardware VAD + noise cancellation + beamforming |
| Price | ~$10 (2-mic) / ~$30 (4-mic ReSpeaker Core) |
| Directional effect | Cuts silence + background noise before PCM reaches Vosk |

#### Why it helps STT

The measured 15 s Vosk time partly comes from processing silence and background noise frames. Vosk's beam-search runs on every frame regardless. Hardware VAD on a dedicated DSP chip:
- Strips silence before piping to Vosk (complements the `silence_strip` bot opt, but done in hardware before the transfer layer)
- Beamforming on 4-mic variant suppresses room echo → shorter active-speech segments → less PCM for Vosk to process

**Expected STT saving:** ~3–5 s (similar to `silence_strip` flag but more aggressive and zero CPU cost).

#### Compatibility with current config

The ReSpeaker 2-Mics HAT uses the WM8960 codec over I²S — same overlay category as the RB-TalkingPI HAT. You cannot use both simultaneously. If RB-TalkingPI is installed, ReSpeaker is not an option.

```bash
# /boot/firmware/config.txt — for ReSpeaker 2-Mics HAT
dtparam=i2s=on
dtoverlay=seeed-2mic-voicecard
```

---

### 7.4 USB SSD (Not an AI Accelerator — Storage Bottleneck Fix)

Not an accelerator, but specifically eliminates the single largest measured bottleneck: the 10–15 s Piper model load from microSD.

| Property | Value |
|---|---|
| Device | Any USB SSD adapter + SATA SSD, or USB-A thumb SSD (e.g. Samsung T7 Go) |
| Interface | USB 2.0 on Pi 3 B+ → ~35–40 MB/s effective bandwidth |
| Price | ~$20–30 (128 GB USB thumb SSD) |

```bash
# Boot from USB SSD (optional) OR just store model files on it:
cp ~/.taris/ru_RU-irina-medium.onnx /mnt/usb_ssd/piper/
# Update PIPER_MODEL in taris-telegram.service:
# Environment=PIPER_MODEL=/mnt/usb_ssd/piper/ru_RU-irina-medium.onnx
```

Even on USB 2.0 (35 MB/s): 66 MB model loads in **~2 s vs 15 s on microSD**.

---

### 7.5 Comparative Summary for Pi 3 B+ Adapters

| Adapter | Price | STT impact | TTS impact | Complexity | Recommendation |
|---|---|---|---|---|---|
| **Intel NCS2** | ~$80 | −12 s (if switch to whisper OV) | **−30 s** (Piper via OV) | High (requires OV port of Piper) | ⭐⭐⭐ Best for TTS |
| **Google Coral USB** | ~$60 | None (Vosk incompatible) | None (Piper incompatible) | Very High (full model retraining) | ❌ Not recommended |
| **ReSpeaker HAT** | ~$10–30 | −3–5 s (hardware VAD) | None | Low (dtoverlay + driver) | ⭐⭐ Good if no RB-TalkingPI |
| **USB SSD** | ~$20 | None | **−13 s** (model load) | Trivial | ⭐⭐⭐ Immediate win |

#### Recommended combination for Pi 3 B+ (keeping current board)

**Phase 1 — Immediate, zero risk (cost ~$20):**
```
USB SSD → Piper model load: 15 s → 2 s
+ warm_piper bot opt ON    → eliminates cold-start after first boot
+ gpu_mem=16 + CPU perf governor (free)
= Total: 58 s → ~20–22 s
```

**Phase 2 — NCS2 + Piper OpenVINO port (cost ~$80, effort: ~2 days):**
```
NCS2 + Piper via OpenVINO → TTS inference: 25 s → 6 s
+ Switch to faster-whisper (OpenVINO backend) → STT: 15 s → 3 s
= Total: ~10–12 s
```

**Realistic best-case on Pi 3 B+ with all hardware:**
```
USB SSD + NCS2 + warm_piper + silence_strip + parallel_tts
= Total: ~8–10 s   (text reply in ~4 s, audio follows ~5 s later)
```

This matches Pi 4 B performance levels without replacing the board, but requires the Piper OpenVINO port (the hardest part).

---

---

## 8. Samsung 840 Series 256 GB SATA SSD via USB (MZ-7TD256) — Specific Configuration

The Samsung MZ-7TD2560/0L9 is a **Samsung 840 Series (non-EVO/Pro) 256 GB 2.5" SATA III SSD**. It is a first-generation consumer TLC NAND drive released 2012–2013, in current widespread use as a repurposed internal drive. This section analyses using it as an external USB storage device on the Raspberry Pi.

---

### 8.1 Drive Identification and Inherent Specs

| Property | Value |
|---|---|
| Model | Samsung MZ-7TD2560/0L9 (840 Series, 256 GB) |
| Form factor | 2.5" SATA III (6 Gbps interface) |
| NAND type | Samsung TLC (3-bit MLC, 21 nm) |
| Controller | Samsung MDX |
| Sequential read | Up to **540 MB/s** (on native SATA host) |
| Sequential write | Up to **130 MB/s** |
| Random 4K read | Up to **98,000 IOPS** |
| Random 4K write | Up to **35,000 IOPS** |
| Power (active) | ~1.2 W (5V @ ~240 mA) |
| Endurance | ~70–75 TBW remaining for a lightly used drive |

The raw SATA capability far exceeds what any USB 2.0 adapter can deliver.

---

### 8.2 Required Adapter

The Pi 3 B+ has only USB-A ports (USB 2.0). The drive needs a **SATA-to-USB adapter**:

| Adapter type | Pi 3 B+ bus | Effective read (seq.) | Notes |
|---|---|---|---|
| SATA → **USB 2.0** cable adapter | USB 2.0 (480 Mbps) | **~35–40 MB/s** | Cheapest (~$5). The drive is limited by the bus, not by itself. Most adapters support UASP for slightly lower latency. |
| SATA → **USB 3.0** cable adapter | USB 2.0 (Pi 3 B+) | **~35–40 MB/s** | USB 3.0 adapter plugged into a USB 2.0 port negotiates at USB 2.0 — no benefit on Pi 3 B+. Buy a USB 2.0 adapter to save cost. |
| SATA → USB 3.0 adapter | USB **3.0** (Pi 4 B) | **~350–400 MB/s** | Fully utilises the drive on Pi 4's xHCI USB 3.0 controller. |

**Key point:** On Pi 3 B+ the bottleneck is USB 2.0 at ~35–40 MB/s — the Samsung 840 could sustain 540 MB/s but delivers exactly as much as the bus allows. Buying a SATA-to-USB 2.0 cable ($5) vs a SATA-to-USB 3.0 cable ($7) makes no practical difference on Pi 3 B+; save the money.

#### Power draw consideration

The Samsung 840 draws ~1.2 W active. Pi 3 B+ USB ports are rated 1.2 A total across all ports (≈6 W), shared with other peripherals. With RB-TalkingPI HAT (I²S, no USB), the drive alone is safe **if you use a ≥3 A official Pi power supply**. A powered USB hub is not required but provides more headroom.

---

### 8.3 Performance on Pi 3 B+ (USB 2.0)

| Metric | microSD (Class 10/A1) | Samsung 840 via USB 2.0 |
|---|---|---|
| Sequential read | ~25–35 MB/s | **~38–42 MB/s** |
| Sequential write | ~10–20 MB/s | **~32–35 MB/s** |
| Random 4K read | **~4–6 MB/s** (2,000–3,000 IOPS) | **~20–25 MB/s** (10,000+ IOPS) |
| Random 4K write | ~1–3 MB/s (800–1,500 IOPS) | **~18–22 MB/s** |
| Access latency | ~5–15 ms | **~0.2–0.4 ms** |

The SSD wins decisively on **random I/O** and **access latency** — the two parameters most relevant to Python process startup, model loading (many small random reads from the `.onnx` file's mmap'd pages), and swap.

---

### 8.4 Impact on the Voice Pipeline

#### Piper ONNX model load (66 MB)

| Storage | Sequential read | Load time (cold) |
|---|---|---|
| microSD (current) | ~30 MB/s | **~15 s** (incl. kernel fault overhead) |
| Samsung 840 via USB 2.0 | ~40 MB/s | **~2–3 s** (seq.) + much lower page-fault latency |
| RAM / tmpfs (`tmpfs_model` opt) | ~6,500 MB/s (LPDDR2) | **~0.01 s** |

The SSD reduces cold Piper load from ~15 s to ~2–3 s — a 5–7× improvement. It does not match `tmpfs_model` (which is ~0.01 s), but it provides persistent fast access **without consuming 66 MB of the Pi 3 B+'s scarce RAM**.

#### Model load on Pi 4 B with USB 3.0

On Pi 4 B (USB 3.0 @350 MB/s): 66 MB / 350 MB/s ≈ **~0.19 s cold load** — practically instant, and no RAM sacrifice. This is the most cost-effective path for Pi 4 users.

#### Swap (if RAM overflows)

Pi 3 B+ with 1 GB RAM occasionally swaps during simultaneous Vosk + Piper. microSD swap is catastrophically slow — even one swap page read at 5 ms latency can stall Python for seconds. On the Samsung 840 via USB 2.0: swap latency ~0.4 ms, random 4K read ~20 MB/s. This effectively eliminates swap-induced stalls.

#### Summary impact table

| Stage | microSD | Samsung 840 USB 2.0 | Samsung 840 USB 3.0 (Pi 4) |
|---|---|---|---|
| Piper cold model load | ~15 s | **~2–3 s** | **~0.2 s** |
| Python process startup | ~2 s | **~1 s** | **<0.3 s** |
| Swap read latency | ~5–15 ms/page | **~0.4 ms/page** | **~0.1 ms/page** |
| Bot service start time | ~8–12 s | **~4–6 s** | **~1–2 s** |

---

### 8.5 `tmpfs_model` opt vs USB SSD — When to Use Which

| Strategy | RAM cost | Persistent across reboots? | Setup complexity | Best for |
|---|---|---|---|---|
| `tmpfs_model` opt (copy to `/dev/shm`) | **66 MB** (from 1 GB) | ❌ Re-copied on restart (~30 s) | Zero (toggle in bot menu) | Pi 3 B+ with enough free RAM; when USB hub is not available |
| Samsung 840 via USB 2.0 | **0 MB** | ✅ Always available | Low (mount once) | Any Pi; permanent speed improvement; frees RAM for Vosk/page cache |
| **Both combined** | 66 MB | ✅ (`tmpfs_model` restores at boot) | Low | Best of both: USB SSD holds persistent copy, bot copies to RAM on startup quickly (~2 s vs ~30 s from microSD) |

**Recommended combo:** Mount the SSD, store the model there, **and** enable `tmpfs_model` bot opt. The startup copy drops from ~30 s (microSD source) to ~2–3 s (USB SSD source). After that, every TTS call uses RAM speed.

---

### 8.6 Setup

#### 1. Connect the drive and verify detection

```bash
lsblk
# Expected output: sda (your SSD), mmcblk0 (microSD)
dmesg | tail -20
# Should show: "New USB device found", "usb-storage", "sd 0:0:0:0: [sda] ..."
```

#### 2. Identify and partition (if the drive is empty or re-purposing)

```bash
sudo fdisk /dev/sda
# Create a single primary partition: n → p → 1 → defaults → w
sudo mkfs.ext4 /dev/sda1 -L taris-data
```

If the drive already has a Windows NTFS partition and you want to keep data:
```bash
sudo apt install ntfs-3g
sudo mount -t ntfs-3g /dev/sda1 /mnt/ssd
```

#### 3. Mount persistently via `/etc/fstab`

```bash
# Get UUID
sudo blkid /dev/sda1

# Add to /etc/fstab:
# UUID=<your-uuid>  /mnt/ssd  ext4  defaults,noatime,nofail  0  2
echo "UUID=$(sudo blkid -s UUID -o value /dev/sda1)  /mnt/ssd  ext4  defaults,noatime,nofail  0  2" \
    | sudo tee -a /etc/fstab
sudo mkdir -p /mnt/ssd
sudo mount -a
```

`noatime` disables access-time writes on every read — important for reducing unnecessary SSD writes.  
`nofail` prevents boot hang if the drive is unplugged.

#### 4. Copy the Piper model to the SSD

```bash
sudo mkdir -p /mnt/ssd/taris
cp ~/.taris/ru_RU-irina-medium.onnx /mnt/ssd/taris/
cp ~/.taris/ru_RU-irina-medium.onnx.json /mnt/ssd/taris/
```

#### 5. Update the `PIPER_MODEL` environment variable

In `~/.taris/bot.env` (bot's EnvironmentFile):
```bash
echo 'PIPER_MODEL=/mnt/ssd/taris/ru_RU-irina-medium.onnx' >> ~/.taris/bot.env
```

Then restart:
```bash
sudo systemctl restart taris-telegram
```

#### 6. (Optional) Enable `tmpfs_model` bot opt for maximum speed

Once the SSD is set up and `PIPER_MODEL` points to `/mnt/ssd/taris/…`, toggle the `tmpfs_model` opt in the bot's Admin → Voice Opts menu. The startup copy will now take **~2–3 s** (from SSD) instead of ~30 s (from microSD). After the copy, every TTS call reads from RAM.

#### 7. (Optional) Move Vosk model to SSD

```bash
mv ~/.taris/vosk-model-small-ru /mnt/ssd/taris/
ln -s /mnt/ssd/taris/vosk-model-small-ru ~/.taris/vosk-model-small-ru
```

Vosk loads its 48 MB model on first voice message; moving it to SSD cuts that load from ~5 s to ~1–2 s.

---

### 8.7 Expected Results After Setup

Starting from the Pi 3 B+ baseline of ~58 s total:

| Change | Saving |
|---|---|
| Piper cold-start from SSD (2–3 s vs 15 s) | **−12–13 s** |
| Swap latency improvement (no stalls) | **−2–5 s** (variable) |
| Vosk model load from SSD | **−3 s** (first call only) |
| `tmpfs_model` ON (SSD source → RAM in ~2 s) | Eliminates cold-start entirely after startup |
| **Best-case combined** | **58 s → ~20–22 s** (consistent; no spikes) |

With the full optimisation stack (SSD + `tmpfs_model` + `warm_piper` + `gpu_mem=16` + CPU performance governor):

| Stage | Baseline | Optimised |
|---|---|---|
| STT | 15 s | ~13 s (unchanged — CPU bound) |
| Piper model load | 15 s | **0 s** (warm from RAM) |
| Piper inference | 25 s | ~22 s (CPU bound, slightly better cache) |
| Other | 3 s | 3 s |
| **Total** | **~58 s** | **~38–40 s** |

> The remaining ~22–25 s is Piper ONNX inference — **purely CPU-bound** on Cortex-A53. The SSD removes the storage bottleneck completely. Further reduction requires either the Pi 4 upgrade (Section 4) or the NCS2 adapter (Section 7.1).

---

### 8.8 Compatibility Notes

- **Pi 3 B+ USB bus:** The Pi 3 uses a DWC OTG USB controller on a shared bus with the Ethernet adapter (LAN9514 chip). There is a known theoretical bandwidth contention between USB storage and Ethernet. In practice, during model loading (a brief burst of ~40 MB/s) while network is idle (bot is not polling while TTS runs), there is no observed conflict.
- **Pi 4 B:** Uses a VIA VL805 xHCI controller with separate USB 3.0 lanes — no contention. The Samsung 840 via a USB 3.0 SATA adapter will sustain ~350–400 MB/s.
- **Drive age / TLC endurance:** The Samsung 840 (non-EVO) TLC NAND had lower endurance ratings (~1,000 P/E cycles) than contemporary MLC drives. For this use case — mostly reads (model files), minimal writes (logs, voice_opts.json) — endurance is not a concern over any practical lifespan.
- **SSD hibernation:** Some USB-SATA adapters spin-down the drive after inactivity. If the drive takes 1–3 s to spin up (actually spin-up does not apply to SSDs, but firmware-level standby does), the first cold Piper load after a long idle may be 3–4 s instead of 2 s. Disable standby if the adapter supports it:
  ```bash
  sudo hdparm -S 0 /dev/sda   # disable standby (0 = never)
  sudo hdparm -B 255 /dev/sda # disable APM
  ```

---

### 8.9 Using the SSD to Store a Local LLM — Fallback to Remote Analysis

This section analyses whether the Samsung 840 SSD (mounted via USB) could host a local LLM (via `llama.cpp`) that the bot falls back to when OpenRouter is unavailable or rate-limited.

TL;DR: **the SSD is a fine storage medium for LLM weights; the bottleneck is Pi 3 B+ CPU and RAM, not the disk.**

---

#### 8.9.1 Storage Capacity — Not the Problem

The 256 GB SSD easily fits a wide range of quantised models alongside OS and Piper/Vosk files:

| Model | GGUF Q4_K_M size | Fits on 256 GB SSD? |
|---|---|---|
| Qwen2-0.5B | ~350 MB | ✅ (many copies) |
| TinyLlama-1.1B | ~660 MB | ✅ |
| Phi-3-mini-3.8B | ~2.5 GB | ✅ |
| Llama-3.2-3B | ~2 GB | ✅ |
| Llama-3.1-8B | ~5 GB | ✅ |
| Mistral-7B | ~4.5 GB | ✅ |
| Llama-3-70B | ~42 GB | ✅ (fits, but Pi 3 cannot run it) |

The SSD has more than enough capacity. The practical question is whether the Pi can actually _run_ the model.

---

#### 8.9.2 The Real Constraint: RAM, Not Disk Speed

`llama.cpp` uses `mmap()` by default — model weights live on disk and the OS loads pages into RAM on demand. This means the model does **not** need to fit entirely in RAM upfront. However, during inference every transformer layer's weight matrices must be read for every token generated. On a model with 32 layers and 1.1B parameters (TinyLlama), approximately **all 660 MB of weights are touched per token pass**.

On Pi 3 B+ with 1 GB RAM the situation is:

| Consumer | RAM held |
|---|---|
| OS + kernel | ~250 MB |
| Python bot + Vosk model | ~240 MB |
| Piper ONNX (when TTS active) | ~150 MB |
| OS page cache available for LLM weights | **~360 MB** |

A 660 MB model (TinyLlama) exceeds the available page cache by ~300 MB. The OS must constantly evict and re-load pages from USB during inference, meaning every token causes additional USB reads — **most tokens are effectively disk-speed tokens**, not RAM-speed.

| Scenario | Token generation rate |
|---|---|
| Model fully in page cache (Pi 4, 2 GB) | ~2–4 tok/s |
| Model partially cached, rest from USB SSD (Pi 3, USB 2.0) | **~0.1–0.4 tok/s** |
| Model fully in page cache on Pi 3 (only possible for ≤350 MB model) | ~0.5–1 tok/s |

At 0.1–0.4 tok/s, a 60-token Russian answer takes **2.5–10 minutes**. This is not usable for interactive conversation.

---

#### 8.9.3 The One Viable Path on Pi 3 B+: Ultra-Tiny Models

The only model that can realistically fit in the Pi 3's page cache alongside the bot is **Qwen2-0.5B-Instruct Q4_K_M**, at ~350 MB.

| Property | Value |
|---|---|
| Model | Qwen2-0.5B-Instruct (GGUF Q4_K_M) |
| Size on disk | ~350 MB |
| RAM needed (fits in page cache) | ~360 MB available ✅ |
| Parameters | 494 M |
| Context window | 32k |
| Russian language | ✅ Good (Qwen2 is multilingual) |
| llama.cpp tok/s on Pi 3 B+ (A53 @ 1.4 GHz) | **~0.8–1.5 tok/s** |
| Time for 80-token answer | **~55–100 s** |
| Time for 20-token answer ("Не знаю") | **~15–25 s** |

This is marginal — usable only if the user accepts a ~1 minute wait. For a fallback scenario (OpenRouter is down), a 1-minute response is better than no response.

> **Critically:** when Qwen2-0.5B is in use, both Vosk STT and TTS must still run. They add ~35–40 s on top. Total end-to-end for a voice query on Pi 3 with local fallback LLM: **~90–140 s**. Text-only fallback (skip TTS) reduces this to ~70 s.

---

#### 8.9.4 Performance on Pi 4 B and Pi 5

| Board | RAM | Model | tok/s | 80-tok answer | Usable? |
|---|---|---|---|---|---|
| Pi 3 B+ | 1 GB | Qwen2-0.5B Q4 | ~1 tok/s | ~80 s | ⚠️ Emergency fallback only |
| Pi 3 B+ | 1 GB | TinyLlama-1.1B Q4 | ~0.2 tok/s | ~400 s | ❌ |
| Pi 4 B | 2 GB | Phi-3-mini-3.8B Q4 | ~1.5 tok/s | ~55 s | ⚠️ Slow but functional |
| Pi 4 B | 4 GB | Phi-3-mini-3.8B Q4 | ~2 tok/s | ~40 s | ✅ Acceptable fallback |
| Pi 5 | 4 GB | Phi-3-mini-3.8B Q4 | ~5 tok/s | ~16 s | ✅ Good |
| Pi 5 | 8 GB | Llama-3.2-3B Q4 | ~5 tok/s | ~16 s | ✅ Good |

The Samsung 840 SSD plays a supporting role on all boards: the model is loaded from SSD into page cache once at startup, then inference runs from RAM. On Pi 4 B (USB 3.0 @350 MB/s), a 2.5 GB model loads in **~7 s** — very fast. On Pi 3 B+ (USB 2.0 @40 MB/s), 350 MB loads in **~9 s**.

---

#### 8.9.5 llama.cpp Setup on the Pi

```bash
# Install build dependencies
sudo apt install -y cmake libblas-dev libopenblas-dev

# Clone and build llama.cpp (ARM Neon optimisations enabled automatically)
git clone https://github.com/ggerganov/llama.cpp /mnt/ssd/llama.cpp
cd /mnt/ssd/llama.cpp
cmake -B build -DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS -DCMAKE_BUILD_TYPE=Release
cmake --build build -j4   # ~10 min on Pi 3 B+

# Download Qwen2-0.5B for Pi 3 B+ (or Phi-3-mini for Pi 4 B+)
mkdir -p /mnt/ssd/models
# Qwen2-0.5B (Pi 3):
wget -q "https://huggingface.co/Qwen/Qwen2-0.5B-Instruct-GGUF/resolve/main/qwen2-0_5b-instruct-q4_k_m.gguf" \
     -O /mnt/ssd/models/qwen2-0.5b-q4.gguf

# Phi-3-mini (Pi 4 B+):
wget -q "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf" \
     -O /mnt/ssd/models/phi3-mini-q4.gguf

# Start llama.cpp HTTP server (OpenAI-compatible, port 8080)
/mnt/ssd/llama.cpp/build/bin/llama-server \
    --model /mnt/ssd/models/qwen2-0.5b-q4.gguf \
    --port 8080 \
    --host 127.0.0.1 \
    --n-predict 200 \
    --threads 4 \
    --ctx-size 2048 \
    --log-disable
```

#### Systemd service for the local LLM server

```ini
# /etc/systemd/system/taris-llm.service
[Unit]
Description=Taris Local LLM Fallback (llama.cpp)
After=network.target

[Service]
Type=simple
User=stas
ExecStart=/mnt/ssd/llama.cpp/build/bin/llama-server \
    --model /mnt/ssd/models/qwen2-0.5b-q4.gguf \
    --port 8080 --host 127.0.0.1 \
    --n-predict 200 --threads 4 --ctx-size 2048 --log-disable
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable taris-llm
sudo systemctl start taris-llm
```

---

#### 8.9.6 Fallback Integration in the Bot

The current bot calls `taris agent -m "..."` which routes through OpenRouter. A minimal fallback can intercept the subprocess failure and redirect to the local `llama.cpp` server:

```python
import requests

LOCAL_LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"
LOCAL_LLM_TIMEOUT = 180   # 3 min — generous for Pi 3 slow inference

def _call_taris(prompt: str) -> str:
    """Try taris (OpenRouter). On failure, fall back to local llama.cpp."""
    try:
        result = subprocess.run(
            [TARIS_BIN, "agent", "-m", prompt],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return _clean_taris_output(result.stdout)
        raise RuntimeError(f"taris rc={result.returncode}")
    except Exception as primary_err:
        log.warning(f"[LLM] taris failed: {primary_err}; trying local fallback")
        try:
            resp = requests.post(LOCAL_LLM_URL,
                json={
                    "model": "local",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.7,
                },
                timeout=LOCAL_LLM_TIMEOUT,
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"].strip()
            return f"⚠️ _[local fallback]_\n{answer}"
        except Exception as local_err:
            log.error(f"[LLM] local fallback also failed: {local_err}")
            return "❌ Нет связи с LLM (OpenRouter недоступен, локальный сервер не отвечает)."
```

The `⚠️ [local fallback]` prefix lets the user know they got a degraded response. The local model quality on Qwen2-0.5B is noticeably weaker than GPT-4o-mini, but sufficient for simple factual questions.

---

#### 8.9.7 Conclusion: Is It Worth It on Pi 3 B+?

| Question | Answer |
|---|---|
| Can the SSD store the LLM? | ✅ Yes — 256 GB fits any model |
| Can Pi 3 B+ actually run a local LLM? | ⚠️ Yes, but only Qwen2-0.5B; ~80–100 s per answer |
| Is it viable for interactive conversation? | ❌ No — too slow |
| Is it viable as emergency offline fallback? | ✅ Yes — "slow answer" beats "no answer" |
| Does USB 2.0 bandwidth matter? | Only for the initial model load (~9 s). Inference is CPU/RAM bound. |
| Is it worth setting up on Pi 3 B+? | ⚠️ Only if offline resilience matters. Significant effort, poor UX. |
| **Recommended for Pi 4 B / Pi 5?** | **✅ Yes — Phi-3-mini at 2–5 tok/s gives a usable fallback** |

**Bottom line:** The Samsung 840 SSD is an appropriate home for LLM weights on any Pi. On Pi 3 B+ the CPU+RAM wall makes local LLM inference impractical for real-time use, but technically functional as a slow emergency fallback (Qwen2-0.5B only). The same SSD on a **Pi 4 B** with USB 3.0 and 4 GB RAM enables a genuinely useful Phi-3-mini fallback at ~2 tok/s.

---

*Generated from real timing measurements on Pi 3 B+ (March 2026) and benchmark data from the Pi Foundation, llama.cpp ARM benchmarks, and RKNN community reports.*
