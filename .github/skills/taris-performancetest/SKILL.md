---
name: taris-performancetest
description: >
  Run taris performance benchmarks (storage, menus, voice, conversation) locally
  and/or on Pi/OpenClaw targets, merge results, and print a cross-platform comparison.
argument-hint: >
  target: ts2 | ts1 | sintaition | pi1 | pi2 | all | all-openclaw | all-picoclaw (default: ts2)
  suite: storage | menus | voice | conversation | all (default: all)
  n: iterations/repeats (default: 500 for storage, 100 for menus, 2 for voice/conversation)
---

## When to Use

Run benchmarks when:
- A storage change was made (`bot_db.py`, `store_sqlite.py`, JSON data layer)
- A menu handler was optimized or refactored
- Voice pipeline (STT/TTS) latency regression is suspected
- LLM response quality or conversation memory regression is suspected
- Context pollution bug (wrong date/fact leaking across conversations) needs verification
- Before/after comparing two implementations on different targets
- Cross-platform OpenClaw vs PicoClaw performance comparison

---

## Targets

| Label | Description | Type | SSH |
|---|---|---|---|
| `ts2` | TariStation2 (local machine) | OpenClaw | none — runs directly |
| `ts1` / `sintaition` | TariStation1 = SintAItion (remote production) | OpenClaw | sshpass |
| `pi2` | OpenClawPI2 (Pi engineering) | PicoClaw | sshpass |
| `pi1` | OpenClawPI (Pi production) | PicoClaw | sshpass |
| `all-openclaw` | ts2 + sintaition | — | — |
| `all-picoclaw` | pi1 + pi2 | — | — |
| `all` | ts2 + sintaition + pi1 + pi2 | — | — |

OpenClaw targets run Ollama + faster-whisper. PicoClaw targets run Vosk + picoclaw binary.

---

## Suites

| Suite | What it measures | Targets |
|---|---|---|
| `storage` | JSON/SQLite read-write ops (500 iterations) | all |
| `menus` | Telegram menu handler latency (100 iterations) | all |
| `voice` | STT (Vosk/faster-whisper), TTS (Piper), LLM (Ollama) latency | OpenClaw only |
| `conversation` | Multi-turn memory, context isolation, response quality, multilang, latency | OpenClaw only |
| `all` | storage + menus + voice + conversation | — |

---

## Quick Reference

| Command | What it does |
|---|---|
| `python tools/benchmark_suite.py` | All suites, ts2 (local, default) |
| `python tools/benchmark_suite.py --suite storage` | Storage ops only |
| `python tools/benchmark_suite.py --suite menus` | Menu latency only |
| `python tools/benchmark_suite.py --suite voice` | STT/TTS/LLM voice pipeline |
| `python tools/benchmark_suite.py --suite conversation` | Conversation quality |
| `python tools/benchmark_suite.py --target sintaition` | All suites on SintAItion |
| `python tools/benchmark_suite.py --target all-openclaw` | ts2 + sintaition |
| `python tools/benchmark_suite.py --target all` | All 4 targets |
| `python tools/benchmark_suite.py --compare` | Print table, no re-run |
| `python tools/benchmark_suite.py -n 50` | Quick run (50 iterations) |
| `python tools/benchmark_suite.py --yes` | Non-interactive |

---

## Conversation Benchmark Details

`tools/benchmark_conversation.py` runs standalone (no bot needed — calls Ollama directly).

### Sub-suites

| Suite | What it checks | Metric |
|---|---|---|
| `conversation_memory` | LLM recalls facts from turn 1 in turn 2 | `memory_score` (0–1), per-turn latency |
| `context_isolation` | Old facts (trap year 1837) don't pollute unrelated answers | `isolation_score`, `pollution_detected` |
| `response_quality` | Keyword hits for 5 standard Russian questions | `relevance_score`, `questions_passed` |
| `conversation_multilang` | LLM stays in ru/en/de as instructed | `lang_score` (Cyrillic heuristic) |
| `llm_latency_multiturn` | Latency for 1/3/5-turn conversations | `total_s`, `avg_turn_s` |

### Run conversation benchmark directly

```bash
# Quick local test (skip slow suites)
python3 tools/benchmark_conversation.py --target ts2 --skip-isolation --skip-multilang -n 1

# Full run
python3 tools/benchmark_conversation.py --target ts2

# Compare two targets
python3 tools/benchmark_conversation.py \
    --compare tools/benchmark_conv_results.json results/conv_sintaition.json
```

---

## Step-by-Step

### Step 1 — Local sanity check (ts2)

```bash
cd /home/stas/projects/sintaris-pl
python3 tools/benchmark_suite.py --target ts2 --suite all -n 200
```

- ✅ no `⚠️` flags → no regression
- ⚠️ flag on a metric → >20% slower than previous same-node run → investigate
- ❌ FAILED → import/runtime error; check `PYTHONPATH=src`

### Step 2 — SintAItion (OpenClaw remote)

```bash
# Ensure OPENCLAW1PWD is set in .env
python3 tools/benchmark_suite.py --target sintaition
```

### Step 3 — Pi targets (PicoClaw)

```bash
# DEV_HOST_PWD and PROD_HOST_PWD must be set in .env
python3 tools/benchmark_suite.py --target pi2
python3 tools/benchmark_suite.py --target pi1
```

### Step 4 — Full cross-platform run

```bash
python3 tools/benchmark_suite.py --target all
```

---

## Cross-Platform Comparison

```bash
# After running benchmarks on multiple targets:
python3 tools/benchmark_suite.py --compare

# Conversation comparison across result files:
python3 tools/benchmark_conversation.py \
    --compare tools/benchmark_conv_results.json results/conv_ts1.json
```

---

## Pass / Warn / Fail

| Status | Condition | Action |
|---|---|---|
| ✅ PASS | All metrics within 20% of previous run on same node | None |
| ⚠️ WARN | Any metric >20% slower | Re-run to confirm; investigate if persistent |
| ❌ FAIL | Script exits non-zero | Fix import/runtime error |

For conversation suites:
| Status | Condition |
|---|---|
| ✅ memory_score = 100% | LLM recalled all 3 facts |
| ⚠️ memory_score < 67% | Model too small or temperature too high |
| ✅ pollution_detected = false | Context isolation OK |
| ⚠️ pollution_detected = true | Context pollution bug — investigate model/prompt |

---

## Credentials

Stored in `/home/stas/projects/sintaris-pl/.env` (gitignored):

| Target | Env var |
|---|---|
| sintaition / ts1 | `OPENCLAW1PWD` |
| pi2 | `DEV_HOST_PWD` |
| pi1 | `PROD_HOST_PWD` |

---

## Results Files

| File | Suite |
|---|---|
| `tools/benchmark_results.json` | storage + menus |
| `tools/benchmark_voice_results.json` | voice (STT/TTS/LLM) |
| `tools/benchmark_conv_results.json` | conversation quality |

Commit results files together with performance-affecting code changes. The comparison table always uses the *prior entry from the same node* as reference baseline.

