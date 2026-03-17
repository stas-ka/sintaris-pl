# Picoclaw — LLM Provider Abstraction

**Version:** `2026.3.32`  
→ Architecture index: [architecture.md](../architecture.md)

---

## 19. Multi-Provider LLM Backend (`bot_llm.py`)

**Implemented:** v2026.3.32 — Feature 3.1 (Multi-LLM Provider Support) + Feature 3.2 (Local LLM Offline Fallback)

All LLM calls from both the Telegram bot and the Web UI route through a single entry point `ask_llm(prompt, timeout=60)` in `src/core/bot_llm.py`. The active provider is selected at startup via the `LLM_PROVIDER` environment variable in `bot.env`.

---

### 19.1 Provider Dispatch Architecture

```
ask_llm(prompt, timeout=60)
        │
        ├── reads LLM_PROVIDER from env (default: "picoclaw")
        │
        ▼
   _DISPATCH[provider](prompt, timeout)
        │
        ├── "picoclaw"    → _ask_picoclaw()  ← CLI subprocess: picoclaw agent -m
        ├── "openai"      → _ask_openai()    ← REST: api.openai.com (or OPENAI_BASE_URL)
        ├── "yandexgpt"   → _ask_yandexgpt() ← REST: llm.api.cloud.yandex.net
        ├── "gemini"      → _ask_gemini()    ← REST: generativelanguage.googleapis.com
        ├── "anthropic"   → _ask_anthropic() ← REST: api.anthropic.com
        └── "local"       → _ask_local()     ← HTTP: localhost:8081 (llama.cpp server)
        │
        ▼
  [on error AND LLM_LOCAL_FALLBACK=true AND provider != "local"]
        │
        └── _ask_local()  ← automatic offline fallback
              → response prefixed with "⚠️ [local fallback]"
```

### 19.2 Provider Reference

| `LLM_PROVIDER` | Env vars required | Default model | Notes |
|---|---|---|---|
| `picoclaw` | *(default — uses `~/.picoclaw/config.json`)* | OpenRouter/gpt-4o-mini | Existing behaviour; model chosen via Admin panel |
| `openai` | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | `gpt-4o-mini` | Also works with any OpenAI-compatible API (Groq, Together, etc.) |
| `yandexgpt` | `YANDEXGPT_API_KEY`, `YANDEXGPT_FOLDER_ID`, `YANDEXGPT_MODEL_URI` | `yandexgpt-lite` | Russian language optimised |
| `gemini` | `GEMINI_API_KEY`, `GEMINI_MODEL` | `gemini-2.0-flash` | Google Generative AI |
| `anthropic` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | `claude-3-5-haiku-20241022` | Anthropic Claude |
| `local` | `LLAMA_CPP_URL` (default `http://127.0.0.1:8081`) | *(as loaded in llama-server)* | Fully offline; requires `picoclaw-llm.service` |

### 19.3 Offline Fallback (Feature 3.2)

When `LLM_LOCAL_FALLBACK=true` in `bot.env` and the primary provider fails (timeout, network error, credential error), `ask_llm()` automatically retries via the local llama.cpp server.

**Fallback conditions:** Any `subprocess.TimeoutExpired`, `FileNotFoundError`, `requests.RequestException`, or generic `Exception` caught from the primary provider function.

**Fallback response format:**
```
⚠️ [local fallback]
<answer from local model>
```

**Suppressed if:** `LLM_LOCAL_FALLBACK` is not set / not `"true"`, or the primary provider is already `"local"`.

### 19.4 Local LLM Service (`picoclaw-llm.service`)

**File:** `src/services/picoclaw-llm.service`  
**Deployed to:** `/etc/systemd/system/picoclaw-llm.service` on Pi  
**Port:** `8081` (separate from Web UI port 8080)

| Configuration | Value |
|---|---|
| Binary | `llama-server` (from llama.cpp) |
| Model | `qwen2-0.5b-q4.gguf` (350 MB, fits Pi 3 page cache) |
| Threads | 4 (all Pi 3 cores) |
| Context | 2048 tokens |
| API | OpenAI-compatible (`/v1/chat/completions`) |

Expected Pi 3 B+ performance: ~0.8–1.5 tok/s. A 80-token answer takes ~55–100 s. Best used as emergency fallback only (Pi 3); more usable on Pi 4/5.

> The service starts automatically when `llama-server` binary is installed. The service unit is staged on `OpenClawPI2` but the binary is not yet installed.

### 19.5 Configuration in `bot.env`

```bash
# Select LLM provider (default: picoclaw — OpenRouter via CLI)
LLM_PROVIDER=picoclaw

# Enable offline fallback to local llama.cpp on provider failure
# LLM_LOCAL_FALLBACK=true

# OpenAI (if LLM_PROVIDER=openai)
# OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o-mini

# YandexGPT (if LLM_PROVIDER=yandexgpt)
# YANDEXGPT_API_KEY=...
# YANDEXGPT_FOLDER_ID=...
# YANDEXGPT_MODEL_URI=gpt://...

# Google Gemini (if LLM_PROVIDER=gemini)
# GEMINI_API_KEY=...
# GEMINI_MODEL=gemini-2.0-flash

# Anthropic Claude (if LLM_PROVIDER=anthropic)
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-3-5-haiku-20241022

# Local llama.cpp (if LLM_PROVIDER=local or as fallback target)
# LLAMA_CPP_URL=http://127.0.0.1:8081
# LLAMA_CPP_MODEL=qwen2-0.5b-q4.gguf
```

### 19.6 Switching Providers

**Via `bot.env`** (permanent, requires service restart):
```bash
# On Pi:
nano ~/.picoclaw/bot.env
# Change LLM_PROVIDER=openai  (or desired provider)
sudo systemctl restart picoclaw-telegram
```

**Active model within `picoclaw` provider** (no restart): Admin panel → 🤖 Switch LLM. This only affects the model selection within the picoclaw/OpenRouter backend and writes to `active_model.txt`.

### 19.7 Adding a New Provider

1. Add required env-var constants to `src/core/bot_config.py`
2. Add `_ask_<provider>(prompt, timeout) -> str` function to `src/core/bot_llm.py`
3. Add entry to `_DISPATCH` dict
4. Add env-var documentation to `bot.env` comment block
5. Update this document and `doc/bot-code-map.md`

---

*For hardware performance implications of local LLM — see [hardware-performance-analysis.md](../hardware-performance-analysis.md) §8.9.*
