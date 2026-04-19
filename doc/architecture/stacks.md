# Taris — Software Stacks

**Version:** `2026.4.68`  
→ Architecture index: [architecture.md](../architecture.md)

## When to read this file
Choosing a library, checking a dependency version, understanding which third-party services are used, or planning an upgrade.

---

## Diagrams

> Color key — applies to all diagrams on this page  
> 🔵 **PicoClaw** — Raspberry Pi / aarch64 (`master` branch)  
> 🟢 **OpenClaw** — x86_64 laptop/PC (`taris-openclaw` branch)  
> 🟣 **Both variants** — shared component  
> 🟠 **Cloud service** — external, requires internet  

### Deployment Topology

```mermaid
flowchart LR
    classDef pc   fill:#2874A6,stroke:#1A5276,color:#fff
    classDef oc   fill:#1A7A3C,stroke:#0E4D24,color:#fff
    classDef br   fill:#6C3483,stroke:#4A235A,color:#fff

    MB(["📦 master branch"]):::br
    OB(["📦 taris-openclaw branch"]):::br

    subgraph DEV["⚙️ Development"]
        PI2["🍓 OpenClawPI2\nRPi 4B · aarch64\nPicoClaw · dev target"]:::pc
        TS2["💻 TariStation2\nx86_64 Ubuntu\nOpenClaw · dev target"]:::oc
    end

    subgraph PROD["🚀 Production"]
        PI1["🍓 OpenClawPI\nRPi 4B · aarch64\nPicoClaw · production"]:::pc
        TS1["💻 SintAItion\nx86_64 Ubuntu\nOpenClaw · production"]:::oc
    end

    MB --> PI2
    MB --> PI1
    OB --> TS2
    OB --> TS1

    PI2 -. "tests pass →" .-> PI1
    TS2 -. "tests pass →" .-> TS1
```

### Full Software Stack — All Variants

```mermaid
flowchart TB
    classDef pc    fill:#2874A6,stroke:#1A5276,color:#fff
    classDef oc    fill:#1A7A3C,stroke:#0E4D24,color:#fff
    classDef both  fill:#6C3483,stroke:#4A235A,color:#fff
    classDef cloud fill:#935116,stroke:#784212,color:#fff

    subgraph UI["🖥️ User Interface"]
        TG["Telegram Bot\npyTelegramBotAPI 4.x"]:::both
        WEB["Web UI · FastAPI\nJinja2 + uvicorn + JWT"]:::both
    end

    subgraph LOGIC["⚙️ Bot Logic"]
        CORE["Handlers · RAG · Memory\nbot_handlers / bot_state"]:::both
        LLMR["LLM Router\nbot_llm.py"]:::both
    end

    subgraph VOICE["🎙️ Voice Stack"]
        VOSK_PC["Vosk 0.3.45\nhotword + command STT\n🔵 PicoClaw"]:::pc
        VOSK_OC["Vosk 0.3.45\nhotword only\n🟢 OpenClaw"]:::oc
        FW["faster-whisper\nCTranslate2 command STT\n🟢 OpenClaw"]:::oc
        PIPER["Piper TTS · ONNX Runtime\nru / de / en · both variants"]:::both
        VAD["WebRTC VAD\nboth variants"]:::both
    end

    subgraph LLM["🤖 LLM Backends"]
        PC_LLM["picoclaw binary\n→ OpenRouter\n🔵 PicoClaw default"]:::pc
        LLAMA["llama.cpp GGUF\nPi 4/5 optional\n🔵 PicoClaw"]:::pc
        OAI["OpenAI API\ngpt-4o-mini\n🟠 Cloud"]:::cloud
        OLL["Ollama 0.18.3\nqwen3:8b local\n🟢 OpenClaw default"]:::oc
    end

    subgraph DATA["💾 Data Store"]
        SQLITE["SQLite + FTS5\n+ sqlite-vec 384-dim\n🔵 PicoClaw"]:::pc
        PG["PostgreSQL 14\n+ pgvector (1536-dim HNSW)\n🟢 OpenClaw"]:::oc
        FILES["~/.taris/ files\nJSON fallback\nboth variants"]:::both
    end

    UI --> LOGIC
    LOGIC --> VOICE
    LOGIC --> LLM
    LOGIC --> DATA
```

### Voice Pipeline — Variant Comparison

```mermaid
flowchart LR
    classDef pc    fill:#2874A6,stroke:#1A5276,color:#fff
    classDef oc    fill:#1A7A3C,stroke:#0E4D24,color:#fff
    classDef both  fill:#6C3483,stroke:#4A235A,color:#fff

    MIC["🎤 Microphone\npw-record"]:::both
    VAD2["WebRTC VAD\nspeech detection"]:::both
    HW_PC["Vosk\nhotword detect\n🔵"]:::pc
    HW_OC["Vosk\nhotword detect\n🟢"]:::oc
    STT_PC["Vosk\nfull command STT\n🔵 PicoClaw"]:::pc
    STT_OC["faster-whisper\nfull command STT\n🟢 OpenClaw"]:::oc
    LLM2["LLM Router\nask_llm_with_history"]:::both
    TTS2["Piper TTS\nONNX synthesis"]:::both
    OUT["🔊 Audio reply\nOGG via Telegram\nor speaker"]:::both

    MIC --> VAD2
    VAD2 --> HW_PC & HW_OC
    HW_PC -->|hotword trigger| STT_PC
    HW_OC -->|hotword trigger| STT_OC
    STT_PC --> LLM2
    STT_OC --> LLM2
    LLM2 --> TTS2
    TTS2 --> OUT
```

---

## Variant Comparison — Top-Level Stack

| Layer | PicoClaw (Pi) | OpenClaw (Laptop/PC) |
|---|---|---|
| **OS** | Raspberry Pi OS Bookworm 64-bit (aarch64) | Ubuntu 22.04 / Debian Bookworm (x86_64) |
| **Python** | 3.11 (system) | 3.11 (system) |
| **Bot framework** | pyTelegramBotAPI | pyTelegramBotAPI |
| **Web UI** | FastAPI + Jinja2 + uvicorn | FastAPI + Jinja2 + uvicorn |
| **STT (hotword)** | Vosk 0.3.45 (Kaldi, streaming) | Vosk 0.3.45 (Kaldi, streaming) |
| **STT (commands)** | Vosk or whisper.cpp | **faster-whisper** (CTranslate2) |
| **TTS** | Piper (ONNX Runtime, aarch64) | Piper (ONNX Runtime, x86_64) |
| **LLM (primary)** | `taris` / OpenRouter (cloud) | OpenAI API / Ollama (local) |
| **LLM (local)** | llama.cpp (Pi 4/5 only) | Ollama 0.18.3 (qwen3:8b default) |
| **Audio capture** | PipeWire / pw-record | PipeWire / pw-record |
| **Data store** | SQLite + FTS5 (default) | PostgreSQL 14+ + pgvector |
| **Process model** | systemd system services (`sudo`) | systemd user services |

---

## Python Dependencies (both variants)

| Package | Version | Purpose |
|---|---|---|
| `pyTelegramBotAPI` | 4.x | Telegram Bot API client |
| `fastapi` | 0.110+ | Web UI HTTP server |
| `uvicorn` | 0.29+ | ASGI server for FastAPI |
| `jinja2` | 3.x | Web UI HTML templating |
| `python-jose` | 3.3+ | JWT tokens for Web UI auth |
| `passlib[bcrypt]` | 1.7+ | Password hashing (Web UI) |
| `vosk` | 0.3.45 | Offline STT (Russian/German/English) |
| `webrtcvad` | 2.0.10 | Voice Activity Detection (VAD) |
| `requests` | 2.x | HTTP calls (LLM APIs, Telegram download) |
| `openai` | 1.x | OpenAI API + compatible (Ollama REST) |
| `pdfminer.six` | 20.x | PDF text extraction (fallback) |
| `PyMuPDF` (`fitz`) | 1.23+ | PDF text + image extraction (primary; optional) |
| `python-docx` | 0.8+ | DOCX document extraction |
| `psutil` | 5.x | RAM detection for RAG tier selection |

### PicoClaw-only Python dependencies

| Package | Version | Purpose |
|---|---|---|
| `sqlite3` | stdlib | SQLite FTS5 data layer |

### OpenClaw-only Python dependencies

| Package | Version | Purpose |
|---|---|---|
| `faster-whisper` | 0.10+ | CTranslate2-based Whisper STT |
| `ctranslate2` | 3.x | Inference backend for faster-whisper |
| `scipy` | 1.x | Audio resampling for faster-whisper |
| `sentence-transformers` | 2.x | `all-MiniLM-L6-v2` embeddings for pgvector |
| `psycopg2-binary` | 2.9+ | PostgreSQL driver |
| `pgvector` | 0.2+ | pgvector Python binding |
| `python-multipart` | 0.x | File upload in FastAPI |

---

## System Binaries

| Binary | Variant | Source | Purpose |
|---|---|---|---|
| `piper` | Both | [rhasspy/piper](https://github.com/rhasspy/piper) | TTS synthesis; ONNX Runtime bundled |
| `ffmpeg` | Both | apt `ffmpeg` | OGG→PCM decode, PCM→OGG encode, TTS encode |
| `pw-record` | Both | apt `pipewire` | Audio capture from mic |
| `picoclaw` | PicoClaw | [sipeed/picoclaw v0.2.0](https://github.com/sipeed/picoclaw) aarch64 deb | `taris` LLM CLI; wraps OpenRouter |
| `whisper` | PicoClaw (opt) | whisper.cpp ggml build | Alternative STT (slower, better WER) |
| `ollama` | OpenClaw | [ollama.ai](https://ollama.ai) 0.18.3 | Local LLM server; models at `~/.local/ollama-models` |
| `git` | Both | apt | Source control |

---

## LLM Models — Deployed

| Variant | Provider | Model | RAM | Notes |
|---|---|---|---|---|
| PicoClaw | `taris` / OpenRouter | `openrouter/openai/gpt-4o-mini` | cloud | Default; requires internet |
| PicoClaw | `local` (llama.cpp) | Any GGUF | ≥4 GB | Pi 4/5 only; Pi 3 too slow |
| PicoClaw | `openai` | `gpt-4o-mini` | cloud | Direct OpenAI API |
| OpenClaw | `ollama` (primary) | `qwen3:8b` | ~5 GB | **Default; offline local LLM** |
| OpenClaw | `ollama` | `qwen3.5:latest` | ~6 GB | SintAItion production (AMD ROCm GPU) |
| OpenClaw | `ollama` | `qwen2:0.5b` / `qwen3.5:0.8b` | ~1 GB | Low-RAM fallback (TariStation2) |
| OpenClaw | `openai` | `gpt-4o-mini` | cloud | Cloud fallback (`LLM_FALLBACK_PROVIDER`) |

---

## Voice Models — Deployed

| Model | Variant | Language | Size | Path |
|---|---|---|---|---|
| `vosk-model-small-ru-0.22` | Both | Russian | 48 MB | `~/.taris/vosk-model-small-ru/` |
| `vosk-model-small-de` | Both (opt) | German | 48 MB | `~/.taris/vosk-model-small-de/` |
| `vosk-model-small-en` | Both (opt) | English | 40 MB | `~/.taris/vosk-model-small-en/` |
| `ru_RU-irina-medium.onnx` | Both | Russian | 66 MB | `~/.taris/ru_RU-irina-medium.onnx` |
| `ru_RU-irina-low.onnx` | Both (opt) | Russian | 18 MB | `~/.taris/ru_RU-irina-low.onnx` |
| `de_DE-thorsten-medium.onnx` | Both (opt) | German | 63 MB | `~/.taris/de_DE-thorsten-medium.onnx` |
| `ggml-base.bin` | PicoClaw (opt) | Multi | 142 MB | `~/.taris/whisper/ggml-base.bin` |
| `faster-whisper base` | OpenClaw | Multi | 300 MB | `~/.cache/huggingface/...` |
| `faster-whisper small` | OpenClaw (SintAItion) | Multi | 500 MB | `~/.cache/huggingface/...` — recommended for SintAItion |

---

## Third-Party Services (Cloud)

| Service | Used by | Purpose | Required |
|---|---|---|---|
| `api.telegram.org` | All | Telegram Bot API | ✅ Always |
| `api.openai.com` | `openai` provider | GPT-4o-mini LLM | If `LLM_PROVIDER=openai` |
| `openrouter.ai` | `taris` / picoclaw binary | LLM routing | PicoClaw default |
| Tailscale | Deploy | Remote access to Pi targets | For remote deploy only |

---

## Setup Scripts

| Script | Variant | What it installs |
|---|---|---|
| `src/setup/setup_voice.sh` | PicoClaw | Vosk, Piper, ffmpeg, pw-record |
| `src/setup/setup_voice_openclaw.sh` | OpenClaw | Vosk, Piper, faster-whisper, ffmpeg |
| `src/setup/setup_llm_openclaw.sh` | OpenClaw | Ollama + pull default model |
| `src/setup/install_service.sh` | PicoClaw | systemd system service files |
