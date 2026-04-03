#!/usr/bin/env python3
"""
LLM Parameter Performance Benchmark — SintAItion (qwen3.5:latest)
Measures Ollama internal timing: load / prompt-eval / generation
Tests: context size, think mode, num_predict, model variants, temperature
"""
import json, time, urllib.request, os, sys

OLLAMA_URL    = "http://127.0.0.1:11434"
MODEL_PRIMARY = "qwen3.5:latest"
MODEL_SMALL   = "qwen3.5:0.8b"

def _ns(x):
    return round(x / 1e6, 1)  # nanoseconds → milliseconds

def call_ollama(model, prompt, options=None, think=None):
    payload = {"model": model, "prompt": prompt, "stream": False,
               "options": options or {}}
    if think is not None:
        payload["think"] = think
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=data,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:
        r = json.loads(resp.read())
    wall = round((time.time() - t0) * 1000, 1)

    load_ms        = _ns(r.get("load_duration",        0))
    prompt_eval_ms = _ns(r.get("prompt_eval_duration", 0))
    eval_ms        = _ns(r.get("eval_duration",        0))
    prompt_tokens  = r.get("prompt_eval_count", 0)
    gen_tokens     = r.get("eval_count",        0)
    gen_speed      = round(gen_tokens / (eval_ms / 1000), 1) if eval_ms > 0 else 0
    prompt_speed   = round(prompt_tokens / (prompt_eval_ms / 1000), 1) if prompt_eval_ms > 0 else 0
    think_text     = r.get("thinking", "")
    answer         = r.get("response", "").strip()[:80]

    return {
        "wall_ms":           wall,
        "load_ms":           load_ms,
        "prompt_eval_ms":    prompt_eval_ms,
        "eval_ms":           eval_ms,
        "prompt_tokens":     prompt_tokens,
        "gen_tokens":        gen_tokens,
        "gen_speed_tps":     gen_speed,
        "prompt_speed_tps":  prompt_speed,
        "think_len":         len(think_text),
        "answer":            answer,
    }

def row(label, r):
    print(f"  {label:<40} wall={r['wall_ms']:6.0f}ms  "
          f"load={r['load_ms']:5.0f}ms  "
          f"prompt_eval={r['prompt_eval_ms']:5.0f}ms({r['prompt_tokens']}tok)  "
          f"gen={r['eval_ms']:5.0f}ms({r['gen_tokens']}tok)  "
          f"speed={r['gen_speed_tps']:5.1f}t/s  "
          f"think_len={r['think_len']}")

def sep(title=""):
    print("\n" + "="*100)
    if title:
        print(f"  {title}")
        print("="*100)

SHORT_PROMPT  = "Nazovi stolicu Frantsii po-russki."
MEDIUM_PROMPT = "Obyasni kratko, chto takoye fotosintez. Maksimum 3 predlozheniya."
LONG_PROMPT   = ("Ty — umnyy pomoshchnik. Obyasni podrobno raznitsu mezhdu protokolami TCP i UDP, "
                 "privedi primery ispolzovaniya kazhdogo, i ukazhi plyusy i minusy. "
                 "Otvet na russkom yazyke.")

results = []

# ── 0. Warm-up ────────────────────────────────────────────────────────────────
sep("0. WARM-UP (ensures model is loaded in GPU memory)")
print("  Sending short prompt to warm up model...")
r = call_ollama(MODEL_PRIMARY, "Hi", options={"num_predict": 5})
row(f"{MODEL_PRIMARY} warm-up", r)

# ── 1. Think mode ─────────────────────────────────────────────────────────────
sep("1. THINK MODE: think=false vs think=true  (production uses think=false)")
for prompt_label, prompt in [("short", SHORT_PROMPT), ("medium", MEDIUM_PROMPT)]:
    for think_val in [False, True]:
        label = f"think={str(think_val):<5} / {prompt_label}"
        try:
            r = call_ollama(MODEL_PRIMARY, prompt,
                            options={"num_predict": 150, "temperature": 0.1},
                            think=think_val)
            row(label, r)
            results.append({"test": "think_mode", "think": think_val,
                             "prompt": prompt_label, **r})
        except Exception as e:
            print(f"  {label}: ERROR {e}")

# ── 2. Context window ─────────────────────────────────────────────────────────
sep("2. CONTEXT WINDOW (num_ctx)  — running at 32768 currently")
for ctx in [2048, 4096, 8192, 16384, 32768]:
    label = f"num_ctx={ctx:<6} / medium"
    try:
        r = call_ollama(MODEL_PRIMARY, MEDIUM_PROMPT,
                        options={"num_predict": 150, "temperature": 0.1, "num_ctx": ctx},
                        think=False)
        row(label, r)
        results.append({"test": "num_ctx", "num_ctx": ctx, **r})
    except Exception as e:
        print(f"  {label}: ERROR {e}")

# ── 3. Output length ──────────────────────────────────────────────────────────
sep("3. OUTPUT LENGTH (num_predict)  — how response length affects total latency")
for n in [30, 100, 200, 400]:
    label = f"num_predict={n:<4} / long"
    try:
        r = call_ollama(MODEL_PRIMARY, LONG_PROMPT,
                        options={"num_predict": n, "temperature": 0.1},
                        think=False)
        row(label, r)
        results.append({"test": "num_predict", "num_predict": n, **r})
    except Exception as e:
        print(f"  {label}: ERROR {e}")

# ── 4. Model comparison ───────────────────────────────────────────────────────
sep("4. MODEL COMPARISON: 0.8b vs 9b")
for model in [MODEL_SMALL, MODEL_PRIMARY]:
    for prompt_label, prompt in [("short", SHORT_PROMPT), ("medium", MEDIUM_PROMPT)]:
        label = f"{model:<22} / {prompt_label}"
        try:
            r = call_ollama(model, prompt,
                            options={"num_predict": 150, "temperature": 0.1},
                            think=False)
            row(label, r)
            results.append({"test": "model_compare", "model": model,
                             "prompt": prompt_label, **r})
        except Exception as e:
            print(f"  {label}: ERROR {e}")

# ── 5. Temperature ────────────────────────────────────────────────────────────
sep("5. TEMPERATURE — generation speed is deterministic, but affects output length")
for temp in [0.0, 0.1, 0.5, 1.0]:
    label = f"temperature={temp} / medium"
    try:
        r = call_ollama(MODEL_PRIMARY, MEDIUM_PROMPT,
                        options={"num_predict": 150, "temperature": temp},
                        think=False)
        row(label, r)
        results.append({"test": "temperature", "temperature": temp, **r})
    except Exception as e:
        print(f"  {label}: ERROR {e}")

# ── 6. Repeat penalty ─────────────────────────────────────────────────────────
sep("6. REPEAT PENALTY — may cause early stop, shortening response")
for rp in [1.0, 1.1, 1.3]:
    label = f"repeat_penalty={rp} / medium"
    try:
        r = call_ollama(MODEL_PRIMARY, MEDIUM_PROMPT,
                        options={"num_predict": 150, "temperature": 0.1,
                                 "repeat_penalty": rp},
                        think=False)
        row(label, r)
        results.append({"test": "repeat_penalty", "repeat_penalty": rp, **r})
    except Exception as e:
        print(f"  {label}: ERROR {e}")

# ── 7. Model info / quantization ──────────────────────────────────────────────
sep("7. MODEL INFO — quantization level, parameter count")
try:
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/show",
        data=json.dumps({"name": MODEL_PRIMARY}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        info = json.loads(resp.read())
    details = info.get("details", {})
    model_info = info.get("model_info", {})
    print(f"  Model:           {MODEL_PRIMARY}")
    print(f"  Quantization:    {details.get('quantization_level', 'unknown')}")
    print(f"  Parameter size:  {details.get('parameter_size', 'unknown')}")
    print(f"  Family:          {details.get('family', 'unknown')}")
    print(f"  Format:          {details.get('format', 'unknown')}")
    for k, v in model_info.items():
        if any(x in k.lower() for x in ["context", "ctx", "head", "layer"]):
            print(f"  {k}: {v}")
    results.append({"test": "model_info", "details": details,
                    "model_info_keys": list(model_info.keys())})
except Exception as e:
    print(f"  ERROR: {e}")

# ── 8. SUMMARY ────────────────────────────────────────────────────────────────
sep("SUMMARY — Key findings")

think_tests = [r for r in results if r.get("test") == "think_mode" and r.get("prompt") == "medium"]
tf = next((r for r in think_tests if not r.get("think")), None)
tt = next((r for r in think_tests if r.get("think")), None)
if tf and tt:
    delta = tt["wall_ms"] - tf["wall_ms"]
    pct = 100 * delta / tf["wall_ms"] if tf["wall_ms"] > 0 else 0
    print(f"\n  THINK MODE:")
    print(f"    think=false  wall={tf['wall_ms']:.0f}ms  speed={tf['gen_speed_tps']:.1f}t/s")
    print(f"    think=true   wall={tt['wall_ms']:.0f}ms  speed={tt['gen_speed_tps']:.1f}t/s  think_chars={tt['think_len']}")
    print(f"    Overhead: +{delta:.0f}ms ({pct:+.0f}%)")

ctx_tests = [r for r in results if r.get("test") == "num_ctx"]
if ctx_tests:
    print(f"\n  CONTEXT WINDOW:")
    for r in ctx_tests:
        print(f"    num_ctx={r['num_ctx']:<6}  wall={r['wall_ms']:.0f}ms  "
              f"prompt_eval={r['prompt_eval_ms']:.0f}ms  gen_speed={r['gen_speed_tps']:.1f}t/s")

model_tests = [r for r in results if r.get("test") == "model_compare" and r.get("prompt") == "medium"]
if model_tests:
    print(f"\n  MODEL COMPARISON (medium prompt):")
    for r in model_tests:
        print(f"    {r.get('model','?'):<24}  wall={r['wall_ms']:.0f}ms  speed={r['gen_speed_tps']:.1f}t/s")

predict_tests = [r for r in results if r.get("test") == "num_predict"]
if predict_tests:
    print(f"\n  OUTPUT LENGTH (long prompt):")
    for r in predict_tests:
        print(f"    num_predict={r['num_predict']:<4}  wall={r['wall_ms']:.0f}ms  "
              f"actual_tokens={r['gen_tokens']}  gen_speed={r['gen_speed_tps']:.1f}t/s")

print("\n" + "="*100)
print("  Writing /tmp/llm_bench_results.json")
with open("/tmp/llm_bench_results.json", "w") as f:
    json.dump(results, f, indent=2)
print("  DONE.")
