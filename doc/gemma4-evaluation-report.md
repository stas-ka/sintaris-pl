# Gemma4 LLM Evaluation Report

**Version:** 2026.4.xx  
**Status:** 🔄 Evaluation in progress / ✅ Complete  
**Targets evaluated:** TariStation2 · SintAItion

---

## 1. Executive Summary

> _Fill in after running the benchmark._

| Recommendation | Model | Why |
|---|---|---|
| TariStation2 | gemma4:e2b or qwen2:0.5b | Hardware-dependent (see §4) |
| SintAItion | gemma4:e4b | Best quality within 5GB VRAM |

---

## 2. Hardware Constraints (Pre-evaluation)

| Target | RAM | GPU VRAM | Max model fit |
|---|---|---|---|
| TariStation2 | 32 GB (Windows host) | CPU only | gemma4:e4b (5 GB) |
| SintAItion | 48 GB | AMD Radeon 890M 16 GB | gemma4:e4b (5 GB), 26b-a4b marginal |

See `doc/research-gemma4-benchmark.md` §3 for full hardware analysis.

---

## 3. Models Evaluated

| Model | Size (4-bit) | Thinking mode | Notes |
|---|---|---|---|
| qwen3.5:latest (baseline) | 9.9 GB | yes (disabled) | Current SintAItion primary |
| qwen2:0.5b (baseline) | 350 MB | no | Current TariStation2 default |
| gemma4:e2b | 3.2 GB | yes (disabled) | Candidate: TariStation2 + SintAItion |
| gemma4:e4b | 5.0 GB | yes (disabled) | Candidate: SintAItion |

---

## 4. Benchmark Results — TariStation2

> _Run: `bash tools/run_gemma4_evaluation.sh TariStation2`_  
> _Results saved: `~/.taris/tests/gemma4_eval_<ts>.json`_

### Quality Scores (%)

| Model | RU factual | RU reasoning | DE factual | DE reasoning | EN factual | Avg |
|---|---|---|---|---|---|---|
| qwen2:0.5b (baseline) | ? | ? | ? | ? | ? | ? |
| gemma4:e2b | ? | ? | ? | ? | ? | ? |
| gemma4:e4b | ? | ? | ? | ? | ? | ? |

### Latency (seconds to first token)

| Model | RU avg | DE avg | EN avg | Overall avg |
|---|---|---|---|---|
| qwen2:0.5b | ? | ? | ? | ? |
| gemma4:e2b | ? | ? | ? | ? |
| gemma4:e4b | ? | ? | ? | ? |

---

## 5. Benchmark Results — SintAItion

> _Run: `bash tools/run_gemma4_evaluation.sh SintAItion`_ (or `tools/eval_gemma4_windows.ps1 -Target SintAItion`)

### Quality Scores (%)

| Model | RU factual | RU reasoning | DE factual | DE reasoning | EN factual | Avg |
|---|---|---|---|---|---|---|
| qwen3.5:latest (baseline) | ? | ? | ? | ? | ? | ? |
| gemma4:e2b | ? | ? | ? | ? | ? | ? |
| gemma4:e4b | ? | ? | ? | ? | ? | ? |

### Latency (seconds)

| Model | RU avg | DE avg | EN avg | Tokens/sec |
|---|---|---|---|---|
| qwen3.5:latest | ~1.5s | ~1.5s | ~1.4s | ~13 t/s |
| gemma4:e2b | ? | ? | ? | ? |
| gemma4:e4b | ? | ? | ? | ? |

---

## 6. Full Test Results (Conversations, RAG, KB)

> _Run after switching OLLAMA_MODEL in bot.env:_  
> `PYTHONPATH=src python3 src/tests/test_voice_regression.py`

### TariStation2

| Test category | Status | Notes |
|---|---|---|
| T27-T31 OpenClaw variant | ? | STT routing, Ollama provider |
| T56-T59 Multi-turn conversation | ? | history context, system message |
| T58 RAG pipeline | ? | retrieve_context, FTS5+vector |
| T83 RU calendar intent → JSON | ? | Gemma4 calendar parsing accuracy |
| T117-T120 Gemma4 specific | ? | thinking disabled, config, availability |

### SintAItion

| Test category | Status | Notes |
|---|---|---|
| T27-T31 OpenClaw variant | ? | |
| T56-T59 Multi-turn conversation | ? | |
| T58 RAG pipeline | ? | |
| T83 RU calendar intent → JSON | ? | |
| T117-T120 Gemma4 specific | ? | |

---

## 7. Decision Criteria

| Criterion | Threshold | Decision |
|---|---|---|
| Quality (all languages) | ≥ 90% | Switch OLLAMA_MODEL |
| Latency (avg) | ≤ 30s | Acceptable |
| Calendar JSON parsing (RU) | PASS | Required |
| RAG context integration | PASS | Required |
| Regression tests | 0 FAIL | Required |

---

## 8. Recommended Configuration Changes

### If gemma4:e4b meets criteria on SintAItion:

```bash
# In ~/.taris/bot.env on SintAItion:
OLLAMA_MODEL=gemma4:e4b
# Keep primary provider as openai (gpt-4o-mini) — ollama is fallback
LLM_FALLBACK_PROVIDER=ollama
systemctl --user restart taris-telegram
```

### If gemma4:e2b meets criteria on TariStation2:

```bash
# In ~/.taris/bot.env on TariStation2:
OLLAMA_MODEL=gemma4:e2b
```

---

## 9. Embeddings — No Regeneration Needed

The embedding model (`sentence-transformers/all-MiniLM-L6-v2`, 384-dim) is **independent of the LLM**.  
RAG chunk embeddings stored in PostgreSQL will work unchanged with any LLM switch.  
Regeneration is only needed if `EMBED_MODEL` changes — **not triggered by Gemma4 adoption**.

---

## 10. Next Steps After Adopting Gemma4

| Step | Priority | Notes |
|---|---|---|
| Re-validate calendar JSON prompts (RU/DE/EN) | High | Gemma4 may have different JSON formatting quirks |
| Re-validate voice pipeline LLM responses | High | Run full voice regression T01-T120 |
| Monitor conversation quality for 1 week | Medium | Watch for context/memory regressions |
| Benchmark gemma4:26b-a4b on SintAItion | Low | Only if e4b quality < 90% |
| Consider switching primary provider to ollama | Low | Only if gpt-4o-mini response quality is a concern |
| Update `AGENTS.md` with new OLLAMA_MODEL value | Done after switch | Keep memory current |

---

## 11. Revision History

| Date | Action | Who |
|---|---|---|
| 2026-04-xx | Initial evaluation template created | Copilot |
| TBD | TariStation2 evaluation complete | — |
| TBD | SintAItion evaluation complete | — |
