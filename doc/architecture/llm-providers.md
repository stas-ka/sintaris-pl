# Taris — LLM Provider Abstraction

**Version:** `2026.4.23`  
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
        ├── reads LLM_PROVIDER from env (default: "taris")
        │
        ▼
   _DISPATCH[provider](prompt, timeout)
        │
        ├── "taris"      → _ask_taris()      ← CLI subprocess: taris agent -m (PicoClaw binary)
        ├── "openai"     → _ask_openai()     ← REST: api.openai.com (or OPENAI_BASE_URL)
        ├── "yandexgpt"  → _ask_yandexgpt()  ← REST: llm.api.cloud.yandex.net
        ├── "gemini"     → _ask_gemini()     ← REST: generativelanguage.googleapis.com
        ├── "anthropic"  → _ask_anthropic()  ← REST: api.anthropic.com
        ├── "local"      → _ask_local()      ← HTTP: localhost:8081 (llama.cpp server)
        ├── "openclaw"   → _ask_openclaw()   ← CLI subprocess: openclaw agent -m --json  [OpenClaw]
        └── "ollama"     → _ask_ollama()     ← HTTP: localhost:11434 (Ollama server)      [OpenClaw]
        │
        ▼
  [on error AND (LLM_LOCAL_FALLBACK=true OR flag-file exists) AND provider != "local"]
        │
        └── _ask_local()  ← automatic offline fallback
              → response prefixed with "⚠️ [local fallback]"
```

### 19.2 Provider Reference

| `LLM_PROVIDER` | Env vars required | Default model | Notes |
|---|---|---|---|
| `taris` | *(default — uses `~/.taris/config.json`)* | OpenRouter/gpt-4o-mini | PicoClaw binary; model chosen via Admin panel |
| `openai` | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | `gpt-4o-mini` | Also works with OpenRouter, Groq, Together, etc. |
| `yandexgpt` | `YANDEXGPT_API_KEY`, `YANDEXGPT_FOLDER_ID`, `YANDEXGPT_MODEL_URI` | `yandexgpt-lite` | Russian language optimised |
| `gemini` | `GEMINI_API_KEY`, `GEMINI_MODEL` | `gemini-2.0-flash` | Google Generative AI |
| `anthropic` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | `claude-3-5-haiku-20241022` | Anthropic Claude |
| `local` | `LLAMA_CPP_URL` (default `http://127.0.0.1:8081`) | *(as loaded in llama-server)* | Fully offline; requires `taris-llm.service` |
| `openclaw` | `OPENCLAW_BIN` (default `~/.local/bin/openclaw`) | via OpenClaw gateway | **OpenClaw only**; subprocess call with `--session-id taris` |
| `ollama` | `OLLAMA_URL` (default `http://127.0.0.1:11434`), `OLLAMA_MODEL` | `qwen2:0.5b` | **OpenClaw default**; local offline; install via `setup_llm_openclaw.sh` |

### 19.3 Offline Fallback (Feature 3.2)

When `LLM_LOCAL_FALLBACK=true` in `bot.env` **or** the file `~/.taris/llm_fallback_enabled` exists, and the primary provider fails (timeout, network error, credential error), `ask_llm()` automatically retries via the local llama.cpp server.

**Fallback conditions:** Any `subprocess.TimeoutExpired`, `FileNotFoundError`, `requests.RequestException`, or generic `Exception` caught from the primary provider function.

**Fallback response format:**
```
⚠️ [local fallback]
<answer from local model>
```

**Suppressed if:** neither `LLM_LOCAL_FALLBACK` is `"true"` nor the flag file `~/.taris/llm_fallback_enabled` exists; or the primary provider is already `"local"`.

### 19.4 Local LLM Service (`taris-llm.service`)

**File:** `src/services/taris-llm.service`  
**Deployed to:** `/etc/systemd/system/taris-llm.service` on Pi  
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
# Select LLM provider (default: taris — OpenRouter via CLI)
LLM_PROVIDER=taris

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

# OpenClaw AI Gateway (if LLM_PROVIDER=openclaw — OpenClaw variant only)
# OPENCLAW_BIN=~/.local/bin/openclaw
# Install: bash ~/projects/sintaris-openclaw/scripts/setup.sh

# Ollama local LLM (if LLM_PROVIDER=ollama — recommended for OpenClaw)
# OLLAMA_URL=http://127.0.0.1:11434
# OLLAMA_MODEL=qwen2:0.5b
# Install: bash src/setup/setup_llm_openclaw.sh
```

### 19.6 Runtime Fallback Toggle (Admin Panel)

The fallback can be toggled from the Telegram Admin panel **without restarting the service**.

**Mechanism:** Admin panel → 🤖 Switch LLM → 📡 Local Fallback
- Toggle writes/removes `~/.taris/llm_fallback_enabled` (flag file)
- `ask_llm()` checks `os.path.exists(LLM_FALLBACK_FLAG_FILE)` at each call
- No env-var changes, no service restart needed

To check or change from SSH:
```bash
# Check: file present = ON, absent = OFF
ls ~/.taris/llm_fallback_enabled

# Toggle ON (create flag file):
touch ~/.taris/llm_fallback_enabled

# Toggle OFF (remove flag file):
rm -f ~/.taris/llm_fallback_enabled
```

> Both `LLM_LOCAL_FALLBACK=true` (static, env-var, requires restart) and the flag file (runtime, toggleable via Admin Panel) activate the offline fallback. The flag file takes precedence at runtime and persists across service restarts.

### 19.7 Switching Providers

**Via `bot.env`** (permanent, requires service restart):
```bash
# On Pi:
nano ~/.taris/bot.env
# Change LLM_PROVIDER=openai  (or desired provider)
sudo systemctl restart taris-telegram
```

**Active model within `taris` provider** (no restart): Admin panel → 🤖 Switch LLM. This only affects the model selection within the taris/OpenRouter backend and writes to `active_model.txt`.

> ⚠️ `active_model.txt` must contain a bare model name (e.g. `gpt-4o-mini`). Provider-prefixed names like `openai/gpt-4o-mini` cause HTTP 400 and silent fallback to Ollama. `get_active_model()` (v2026.4.22+) auto-strips the prefix.

### 19.7a Per-Function Provider Overrides (v2026.3.32+)

The admin panel can route individual use-cases to different providers **without changing `LLM_PROVIDER`**. Stored in `~/.taris/llm_per_func.json`.

| Use-case key | Used by | Default |
|---|---|---|
| `chat` | Telegram text chat (`bot_handlers.py`) | ← `LLM_PROVIDER` |
| `system` | Admin system chat | ← `LLM_PROVIDER` |
| `voice` | Voice pipeline (`bot_voice.py`) | ← `LLM_PROVIDER` |
| `calendar` | Calendar LLM classify | ← `LLM_PROVIDER` |

**Key functions** (`src/core/bot_llm.py`):

| Function | Purpose |
|---|---|
| `get_per_func_provider(use_case)` | Returns override or `""` (falls back to `LLM_PROVIDER`) |
| `set_per_func_provider(use_case, provider)` | Admin panel writes; `""` clears override |

> ⚠️ Voice calls pass `use_case="voice"` to `ask_llm_with_history()` (v2026.4.23+). Before this fix, the default `use_case="chat"` caused voice to use the chat override (e.g. Ollama) silently even when `LLM_PROVIDER=openai`.



1. Add required env-var constants to `src/core/bot_config.py`
2. Add `_ask_<provider>(prompt, timeout) -> str` function to `src/core/bot_llm.py`
3. Add entry to `_DISPATCH` dict
4. Add env-var documentation to `bot.env` comment block
5. Update this document and `doc/bot-code-map.md`

---

*For hardware performance implications of local LLM — see [hardware-performance-analysis.md](../hardware-performance-analysis.md) §8.9.*

---

## 20. Multi-Turn Conversation Context (v2026.3.30+3)

### 20.1 Architecture

Every user chat message is sent to the LLM as a proper multi-turn message array:

```
messages = [
  {"role": "system",    "content": <system_msg>},   ← bot identity + config + memory note
  {"role": "user",      "content": <prior turn 1>},  ← history loaded from DB
  {"role": "assistant", "content": <prior reply 1>},
  ...
  {"role": "user",      "content": <rag_context + user_text>}  ← current turn
]
```

**Key functions** (`src/telegram/bot_access.py`):

| Function | Purpose |
|---|---|
| `_build_system_message(chat_id, user_text)` | Returns `role:system` content: security preamble + bot config + memory context note + lang instruction |
| `_user_turn_content(chat_id, user_text)` | Returns current user turn: RAG context (if any) + wrapped user text (no preamble) |
| `_with_lang(chat_id, user_text)` | Single-turn path (voice, system chat) — bundles everything into one string |

### 20.2 Ollama Multi-Turn Fix (v2026.3.30+3)

`ask_llm_with_history(messages, provider, timeout)` in `bot_llm.py` now has an explicit `elif provider == "ollama"` branch that sends the full `messages` list natively to `/api/chat`. Previously, the `else` fallback called `_format_history_as_text()` → `_ask_ollama()` which collapsed all history into a single user message, losing multi-turn structure entirely.

### 20.3 Tiered Memory (v2026.3.30+2)

Long conversation histories are summarized into a two-tier memory to stay within LLM context limits:

| Tier | Storage | Trigger |
|---|---|---|
| **Short** | `chat_history` DB table (live messages) | Always |
| **Mid** | `conversation_summaries` DB table (`tier='mid'`) | When `chat_history` reaches `CONV_SUMMARY_THRESHOLD` (15) messages |
| **Long** | `conversation_summaries` DB table (`tier='long'`) | When mid-tier count reaches `CONV_MID_MAX` (5) summaries |

**Key functions** (`src/core/bot_state.py`):

| Function | Purpose |
|---|---|
| `add_to_history(chat_id, role, content)` | Append message; triggers async summarization at threshold |
| `_summarize_session_async(chat_id)` | Background thread: summarizes oldest messages → inserts `tier='mid'` row |
| `get_memory_context(chat_id)` | Returns formatted summary string injected into the system message |
| `clear_history(chat_id)` | Clears both `chat_history` and `conversation_summaries` for user |

**Constants** (`src/core/bot_config.py`):

| Constant | Default | Description |
|---|---|---|
| `CONV_SUMMARY_THRESHOLD` | `15` | Message count that triggers mid-tier summarization |
| `CONV_MID_MAX` | `5` | Mid-tier count that triggers long-tier compaction |
| `CONVERSATION_HISTORY_MAX` | `8` | Hard cap on live history turns sent to LLM per call (v2026.4.20+) |

> ⚠️ Memory summaries accumulate over time and are injected verbatim into every system message. 12+ summaries = ~7–11 KB added to every prompt. Monitor with: `SELECT tier, length(summary) FROM conversation_summaries WHERE chat_id=? ORDER BY created_at`.

### 20.4 Embedding Pre-Warm (v2026.4.20+)

At startup `telegram_menu_bot.py` launches `_prewarm_embeddings()` in a background thread which calls `EmbeddingService().embed(["warmup"])`. Without this, the first RAG call on a fresh start incurs a 2–3s cold-start (fastembed ONNX model load).

**Log indicator:** `[Embeddings] pre-warmed at startup: backend=fastembed`

