# LLM Performance Analysis & Optimization Proposal
## SintAItion — qwen3.5:latest (9B Q4_K_M) on AMD Radeon 890M

**Date:** 2026-04-02  
**Benchmark run:** `/tmp/llm_bench_sintaition.py` (no code changes — read-only analysis)  
**Results file:** `tools/benchmark_llm_sintaition_2026-04-02.json`  
**Status:** Proposal only. No changes applied.

---

## TL;DR — Root Cause of Slow Responses

The hardware is working correctly (100% GPU, 12.1 t/s). The bottleneck is **token count × generation speed**:

```
wall time ≈ 160 ms (overhead) + 82 ms × tokens_generated
```

At `LOCAL_MAX_TOKENS=512` (current default), worst case = **42 seconds**. A typical detailed answer (200 tokens) = **16.5 seconds**. A short chat answer (80 tokens) = **6.6 seconds**.

The GPU cannot go faster than 12.1 t/s on this hardware with Q4_K_M quantization — that is the ceiling. All optimization is about **reducing token count** and **improving perceived latency**.

---

## Benchmark Results

**Hardware:** SintAItion, AMD Radeon 890M (gfx1150, RDNA3.5), 48 GB RAM  
**Model:** qwen3.5:latest · Q4_K_M · 9.7B parameters · 9.9 GB VRAM (100% GPU)

### Timing Breakdown per Call

| Phase | Duration | Notes |
|---|---|---|
| Model load (warm) | ~150 ms | Model already in VRAM |
| Model load (cold, after keep_alive expires) | ~2 500 ms | Reload from VRAM |
| Prompt evaluation | ~5–8 ms/token | 38 tokens → 220 ms |
| Token generation | **82 ms/token** = **12.1 t/s** | The fundamental bottleneck |

### Section 1 — Think Mode

| Mode | Prompt | Wall time | Gen speed | Think chars |
|---|---|---|---|---|
| `think=false` (production) | short | 1 490 ms | 12.9 t/s | 0 |
| `think=true` | short | 12 706 ms | 12.2 t/s | 494 |
| `think=false` (production) | medium | **6 591 ms** | 12.3 t/s | 0 |
| `think=true` | medium | 12 750 ms | 12.2 t/s | 506 |

✅ **`OLLAMA_THINK=false` is already set correctly. Saves +6 160 ms (+93%) overhead.**

Think mode hits the `num_predict=150` test cap immediately — the model uses its full token budget just for thinking. Production setting is optimal.

### Section 2 — Context Window (num_ctx)

| num_ctx | Wall time | Load time | Gen speed |
|---|---|---|---|
| 2 048 | 8 784 ms | 2 161 ms | 12.2 t/s |
| 4 096 | 9 314 ms | 2 204 ms | 12.2 t/s |
| 8 192 | 8 987 ms | 2 280 ms | 12.2 t/s |
| 16 384 | 9 059 ms | 2 378 ms | 12.2 t/s |
| **32 768 (current)** | 9 412 ms | **2 552 ms** | 12.2 t/s |

**Finding:** Context size does **not** affect generation speed (all 12.2 t/s). It only affects model reload time when the context changes. The 391 ms difference between 2048 and 32768 only matters on cold load.

The high wall times here (8–9 s) are caused by the medium prompt generating 78–83 tokens naturally, not by the context window.

### Section 3 — Output Length (num_predict) — CRITICAL

| num_predict | Wall time | Actual tokens | Gen speed |
|---|---|---|---|
| 30 | 2 916 ms | 30 | 12.5 t/s |
| 100 | 8 730 ms | 100 | 12.2 t/s |
| **200** | **17 068 ms** | 200 | 12.1 t/s |
| 400 | 33 773 ms | 400 | 12.1 t/s |
| **512 (current default)** | **~42 000 ms** | ~512 | ~12.1 t/s |

**Finding:** Wall time scales linearly with output tokens. `LOCAL_MAX_TOKENS=512` (default) allows 42-second responses. This is the primary cause of long answer times.

### Section 4 — Model Comparison

| Model | Prompt | Wall time | Speed | Quality |
|---|---|---|---|---|
| qwen3.5:0.8b | short | 4 647 ms | **53.8 t/s** | 67% (prev benchmark) |
| qwen3.5:0.8b | medium | 3 018 ms | **53.8 t/s** | 67% |
| **qwen3.5:latest (9B)** | short | 1 530 ms | 12.6 t/s | **100%** |
| **qwen3.5:latest (9B)** | medium | 6 853 ms | 12.0 t/s | **100%** |

Note: 0.8b is **4.5× faster** but generates more tokens per answer (150 vs 15 for the short prompt), making the actual wall time similar or worse for simple queries. For short factual answers, 9B is faster because it generates fewer tokens.

### Section 5 — Temperature

| Temperature | Wall time | Gen speed | Notes |
|---|---|---|---|
| 0.0 | 7 361 ms | 11.9 t/s | Deterministic |
| **0.1 (production)** | 7 042 ms | 12.0 t/s | ✅ optimal |
| 0.5 | 7 119 ms | 12.0 t/s | — |
| 1.0 | 6 262 ms | 12.0 t/s | Shorter responses |

**Finding:** Temperature has no effect on generation speed. ✅ No change needed.

### Section 6 — Repeat Penalty

No meaningful effect on speed. ✅ No change needed.

### Section 7 — Model Info

```
Model:          qwen3.5:latest
Quantization:   Q4_K_M   ← 4-bit quantization (half precision)
Parameter size: 9.7B
Format:         gguf
Max context:    262 144 tokens (model supports it; loaded at 32 768)
VRAM used:      9.9 GB (100% GPU)
```

---

## Issues Found

### 🔴 ISSUE-1 — `LOCAL_MAX_TOKENS=512` default causes 42-second responses

**Source:** `src/core/bot_config.py:183`  
```python
LOCAL_MAX_TOKENS = int(os.getenv("LOCAL_MAX_TOKENS", "512"))
```

`OLLAMA_NUM_PREDICT` / `LOCAL_MAX_TOKENS` is **not set in `~/.taris/bot.env` on SintAItion** → falls back to 512.

At 12.1 t/s: 512 tokens = **42.3 seconds** maximum wall time.  
A typical complex explanation response (200–300 tokens): **16–25 seconds**.

**Impact:** Every response that causes the model to "want to write a lot" will be slow.

---

### 🟡 ISSUE-2 — `OLLAMA_KEEP_ALIVE` discrepancy: service=1h vs bot.env=24h

**Evidence from `ollama ps`:**  
```
qwen3.5:latest    ...    UNTIL  58 minutes from now   ← 1h timer counting down
```

- `~/.taris/bot.env` has `OLLAMA_KEEP_ALIVE=24h` — but this env var is **not read by the Ollama service**
- `/etc/systemd/system/ollama.service` has `Environment=OLLAMA_KEEP_ALIVE=1h` — this **is** active
- `_ask_ollama()` in `bot_llm.py` does **not** pass `keep_alive` in the API request body

**Effect:** After 1 hour of idle, qwen3.5:latest unloads from VRAM. Next request incurs **~2.5 second cold-load penalty**.

---

### 🟡 ISSUE-3 — No streaming → perceived latency = full generation time

Current `_ask_ollama()` uses `"stream": False`. The user sees nothing until the full response is generated.

**Measured first-token time (load + prompt_eval):** ~350 ms (warm) / ~2.8 s (cold)  
**Actual full response delivery:** 6–42 seconds  

With streaming, the first word would appear in **~350 ms** instead of waiting for the entire response. This dramatically improves the subjective experience even though total generation time is unchanged.

---

### 🟢 ISSUE-4 — Q4_K_M quantization: Q8_0 available for better quality

Current quantization: **Q4_K_M** (4-bit, 9.9 GB VRAM)  
Available disk: **762 GB free** on SintAItion  
Available RAM: **48 GB total, ~34 GB free**

**Q8_0** (8-bit quantization) would use ~14–16 GB VRAM — feasible on SintAItion's shared memory architecture.  
Expected impact: same speed (~12 t/s, GPU bandwidth-bound), **noticeably better accuracy and fewer hallucinations**.

---

### 🟢 ISSUE-5 — Both qwen3.5:latest AND qwen3.5:0.8b simultaneously loaded

`ollama ps` shows both models in GPU (9.9 GB + 2.9 GB = **12.8 GB total**):
```
qwen3.5:latest    9.9 GB    100% GPU    32768    58 min
qwen3.5:0.8b      2.9 GB    100% GPU    32768    57 min
```

The benchmark triggered loading of 0.8b and Ollama kept both loaded. This is wasting ~2.9 GB VRAM unnecessarily. With `OLLAMA_KEEP_ALIVE` consistent, only qwen3.5:latest would stay loaded.

---

## Optimization Proposals

### OPT-1 — Reduce `LOCAL_MAX_TOKENS` (HIGH IMPACT 🔴)

**Type:** Configuration change (bot.env)  
**Risk:** Low — reduces max response length, not quality per token

```ini
# ~/.taris/bot.env on SintAItion
LOCAL_MAX_TOKENS=200
```

| Scenario | Before (512 tok) | After (200 tok) | Saving |
|---|---|---|---|
| Short chat answer (model wants ~80 tok) | 6.6 s | 6.6 s | 0 s (model stops naturally) |
| Medium explanation (model wants ~200 tok) | 16.5 s | 16.5 s | 0 s |
| Detailed answer (model wants ~400 tok) | 33 s | **16.5 s** | **−16.5 s** |
| Maximum possible | **42 s** | **16.5 s** | **−25.5 s** |

200 tokens ≈ 150 words ≈ 4–6 sentences in Russian/German. Sufficient for conversational use.

For detailed technical answers, consider context-aware limits per call type:
```python
# In bot_llm.py or bot_config.py — future enhancement
LLM_CHAT_MAX_TOKENS    = 200  # conversational turns
LLM_SYSTEM_MAX_TOKENS  = 350  # system chat / technical queries
LLM_DETAIL_MAX_TOKENS  = 500  # RAG-grounded detailed answers
```

---

### OPT-2 — Fix `keep_alive` in Ollama API request (MEDIUM IMPACT 🟡)

**Type:** Code change (`src/core/bot_llm.py`) OR service config change  
**Risk:** Very low

**Option A — Pass keep_alive in API request (preferred):**
```python
# src/core/bot_llm.py — _ask_ollama() options dict
body: dict = {
    "model": OLLAMA_MODEL,
    "messages": [...],
    "stream": False,
    "think": OLLAMA_THINK,
    "keep_alive": OLLAMA_KEEP_ALIVE_STR,   # e.g. "24h"
    "options": {"num_predict": LOCAL_MAX_TOKENS, ...},
}
```
Add to `bot_config.py`:
```python
OLLAMA_KEEP_ALIVE_STR = os.getenv("OLLAMA_KEEP_ALIVE", "1h")  # read from bot.env
```
Then set in `~/.taris/bot.env`: `OLLAMA_KEEP_ALIVE=24h`

**Option B — Fix service file (simpler, admin change):**
```ini
# /etc/systemd/system/ollama.service
Environment=OLLAMA_KEEP_ALIVE=24h   # was: 1h
```
```bash
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

Impact: model stays loaded for 24h instead of 1h → saves 2.5 s cold-load after idle periods.

---

### OPT-3 — Implement Streaming (HIGH IMPACT for perceived latency 🟡)

**Type:** Code change (`src/core/bot_llm.py` + `src/telegram_menu_bot.py` + `src/bot_web.py`)  
**Risk:** Medium — requires changes in multiple layers  
**Effort:** 2–3 hours

**What changes:**

1. `bot_llm.py`: add `ask_llm_stream(prompt, callback)` that uses `"stream": True` and calls `callback(chunk)` for each token  
2. `telegram_menu_bot.py`: send initial "typing" message → edit it as tokens arrive (using `bot.edit_message_text`)  
3. `bot_web.py`: use `StreamingResponse` with `text/event-stream` (Server-Sent Events)

**Perceived latency improvement:**
```
Current:   user waits  6.6–42 s → sees full response
Streaming: user sees first word after ~350 ms → reads as it generates
```

Note: Total wall time is unchanged. Only the subjective experience improves. Most impactful for long responses.

Telegram streaming pattern:
```python
# Pseudo-code — send placeholder then edit
msg = bot.send_message(chat_id, "…")
buf = ""
for chunk in ask_llm_stream(prompt):
    buf += chunk
    if len(buf) % 20 == 0:   # edit every ~20 chars to avoid flood limits
        bot.edit_message_text(buf, chat_id, msg.message_id)
bot.edit_message_text(buf, chat_id, msg.message_id)
```

⚠️ Telegram rate-limits `editMessageText` to ~20 edits/minute per chat. Batch updates every 1–2 seconds to stay within limits.

---

### OPT-4 — Reduce num_ctx to 8192 (MINOR IMPACT 🟢)

**Type:** Configuration  
**Risk:** None if conversation history stays under 8192 tokens

```ini
# ~/.taris/bot.env
OLLAMA_NUM_CTX=8192
```
Add to `bot_config.py`:
```python
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
```
Pass in `_ask_ollama()` options:
```python
"options": {"num_predict": LOCAL_MAX_TOKENS, "num_ctx": OLLAMA_NUM_CTX, ...}
```

Impact: saves ~400 ms on cold model reload. No effect on generation speed.

8192 tokens is sufficient for:
- System prompt: ~200 tokens
- 10-turn conversation history: ~2000 tokens  
- RAG context (3 chunks × 512): ~1600 tokens  
- Total: ~3800 tokens — comfortable within 8192

---

### OPT-5 — Test Q8_0 Quantization (QUALITY IMPROVEMENT 🟢)

**Type:** New model pull + A/B test  
**Risk:** Low (existing Q4_K_M model not deleted; test only)

```bash
# On SintAItion — pull Q8_0 variant (~16 GB)
ssh stas@SintAItion "ollama pull qwen3.5:8b-instruct-q8_0"
# Or check available tags:
# https://ollama.com/library/qwen3.5/tags
```

Expected results vs Q4_K_M:
- Speed: **~same** (GPU bandwidth-bound; Q8_0 reads 2× more bytes but hardware compensates)
- Quality: **noticeably better** (higher precision weights → fewer errors in reasoning, math, multilingual)
- VRAM: ~14–16 GB (vs 9.9 GB) — fits in SintAItion's 48 GB shared memory pool

---

### OPT-6 — Concurrent Requests with OLLAMA_NUM_PARALLEL (FUTURE)

Current: `OLLAMA_NUM_PARALLEL=1` (default) — only 1 Ollama request at a time.  
For multi-user scenarios (multiple Telegram users sending messages simultaneously):

```ini
# /etc/systemd/system/ollama.service
Environment=OLLAMA_NUM_PARALLEL=2
```

**Impact:** 2nd user doesn't queue behind 1st user's generation.  
**Trade-off:** VRAM doubles (9.9 GB × 2 = 19.8 GB) — requires keeping Radeon 890M's 16 GB shared pool in mind; works only if total system RAM ≥ 30 GB after OS overhead (SintAItion has 48 GB → feasible).

---

## Optimization Priority Matrix

| Priority | ID | Change | Expected gain | Effort | Risk |
|---|---|---|---|---|---|
| 🔴 **1** | OPT-1 | `LOCAL_MAX_TOKENS=200` in bot.env | −25 s worst case, −0 typical short answers | 5 min (config) | Low |
| 🟡 **2** | OPT-2 | Fix keep_alive (service or API) | −2.5 s after idle | 10 min | Very low |
| 🟡 **3** | OPT-3 | Streaming responses | Perceived −6 s TTFT | 2–3 h (code) | Medium |
| 🟢 **4** | OPT-5 | Pull + test Q8_0 model | Better quality, same speed | 30 min (pull) | Low |
| 🟢 **5** | OPT-4 | `num_ctx=8192` | −400 ms cold reload | 10 min (config) | Very low |
| 🟢 **6** | OPT-6 | `OLLAMA_NUM_PARALLEL=2` | No queue for 2nd user | 5 min (service) | Low |

---

## What Was Already Optimal

| Setting | Status | Notes |
|---|---|---|
| `OLLAMA_THINK=false` | ✅ **Correct** | Saves 6 seconds per response |
| `OLLAMA_FLASH_ATTENTION=1` | ✅ **Correct** | Enabled in service file |
| GPU offload 100% | ✅ **Correct** | All 41 layers on Radeon 890M |
| `FASTER_WHISPER_PRELOAD=1` | ✅ **Correct** | SintAItion has dedicated RAM |
| `temperature=0.1` | ✅ **Correct** | No speed impact; good quality |
| `OLLAMA_MIN_TIMEOUT=120` | ✅ **Correct** | Covers worst-case 42 s response |

---

## Unchanged Parameters (No Effect on Speed)

| Parameter | Effect on speed | Recommendation |
|---|---|---|
| `temperature` | None | Keep 0.1 |
| `repeat_penalty` | None | Keep default (1.0) |
| `top_k`, `top_p` | None (sampling only) | Keep defaults |
| `num_ctx` (generation) | None | Can reduce for minor reload gain |

---

*Benchmark script: `/tmp/llm_bench_sintaition.py` (also in project root after next sync)*  
*Raw results: `tools/benchmark_llm_sintaition_2026-04-02.json`*
