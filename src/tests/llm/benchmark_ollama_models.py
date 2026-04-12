#!/usr/bin/env python3
"""
LLM Model Benchmark — Ollama models on SintAItion / OpenClaw targets.

Measures latency, throughput and quality for every available Ollama model.
Designed to compare Qwen3.5 series against existing Qwen3 / Qwen2 models.

Usage (run on the target machine — needs Ollama running):
    python3 src/tests/llm/benchmark_ollama_models.py
    python3 src/tests/llm/benchmark_ollama_models.py --model qwen3.5:latest
    python3 src/tests/llm/benchmark_ollama_models.py --save results.json
    python3 src/tests/llm/benchmark_ollama_models.py --compare baseline.json
    python3 src/tests/llm/benchmark_ollama_models.py --quick   # only latency test

Results are printed as a markdown table and saved to:
    ~/.taris/tests/llm_benchmark_<timestamp>.json
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

# Target label shown in report headers (override via --target or BENCHMARK_TARGET env var)
BENCHMARK_TARGET = os.environ.get("BENCHMARK_TARGET", "")

# Models to benchmark if no --model flag given
# (only models actually present in ollama list are tested)
CANDIDATE_MODELS = [
    "qwen2:0.5b",        # baseline — tiny
    "qwen3.5:0.8b",      # new tiny
    "qwen3:8b",          # current default
    "qwen3.5:latest",    # new 9B (downloaded as 'latest')
    "qwen3.5:9b",        # new 9B explicit tag
    "qwen3:14b",         # large comparison
    "qwen3.5:14b",       # new large (if available)
    # ── Google Gemma 4 models ─────────────────────────────────────────────────
    "gemma4:e2b",         # Edge 2B — 5.1B total, 2.3B effective, text+image+audio
    "gemma4:e4b",         # Edge 4B — 8B total, 4.5B effective, text+image+audio
    "gemma4:latest",      # 31B dense — text+image (default tag)
    "gemma4:26b-a4b",     # 26B MoE — 3.8B active/token, text+image
    # ── Older Gemma models (comparison) ──────────────────────────────────────
    "gemma3:4b",          # Gemma 3 4B (if available)
    "gemma3:12b",         # Gemma 3 12B (if available)
]

# ---------------------------------------------------------------------------
# Prompts for quality evaluation — organised by language
# ---------------------------------------------------------------------------

PROMPTS = {
    # ── Speed ────────────────────────────────────────────────────────────────
    "latency": {
        "text": "Say OK",
        "lang": None,
        "desc": "Minimal round-trip latency",
        "check": lambda r: "ok" in r.lower(),
        "options": {"num_predict": 10, "temperature": 0},
    },
    # ── Russian ───────────────────────────────────────────────────────────────
    "ru_factual": {
        "text": "Скажи число Пи с точностью до 5 знаков после запятой. Только число, ничего больше.",
        "lang": "ru",
        "desc": "RU factual (Pi)",
        "check": lambda r: "3.14159" in r.replace(",", "."),
        "options": {"num_predict": 30, "temperature": 0},
    },
    "ru_calendar": {
        "text": (
            'Извлеки данные события из текста и верни JSON.\n'
            'Текст: "Встреча с врачом в четверг в 14:00"\n'
            'Формат: {"title": "<название>", "dt": "<YYYY-MM-DDTHH:MM>"}\n'
            'Верни только JSON, без пояснений.'
        ),
        "lang": "ru",
        "desc": "RU calendar → JSON",
        "check": lambda r: '"title"' in r and '"dt"' in r,
        "options": {"num_predict": 60, "temperature": 0},
    },
    "ru_assistant": {
        "text": (
            "Ты — голосовой помощник Taris. Пользователь говорит: 'Включи напоминание на завтра в 9 утра.'\n"
            "Ответь кратко и подтверди действие на русском языке (1-2 предложения)."
        ),
        "lang": "ru",
        "desc": "RU assistant reply",
        "check": lambda r: len(r.strip()) > 10 and any(
            w in r.lower() for w in ["завтра", "9", "напомин", "установ", "ок", "хорошо", "понял"]
        ),
        "options": {"num_predict": 80, "temperature": 0.1},
    },
    # ── German ────────────────────────────────────────────────────────────────
    "de_factual": {
        "text": "Was ist der Wert von Pi auf 5 Dezimalstellen? Nur die Zahl.",
        "lang": "de",
        "desc": "DE factual (Pi)",
        "check": lambda r: "3.14159" in r.replace(",", "."),
        "options": {"num_predict": 30, "temperature": 0},
    },
    "de_calendar": {
        "text": (
            'Extrahiere die Ereignisdaten aus dem Text und gib JSON zurück.\n'
            'Text: "Arzttermin am Donnerstag um 14:00 Uhr"\n'
            'Format: {"title": "<Titel>", "dt": "<YYYY-MM-DDTHH:MM>"}\n'
            'Nur JSON, keine Erklärung.'
        ),
        "lang": "de",
        "desc": "DE calendar → JSON",
        "check": lambda r: '"title"' in r and '"dt"' in r,
        "options": {"num_predict": 60, "temperature": 0},
    },
    "de_reasoning": {
        "text": (
            "Wie spät ist es in Berlin, wenn es in Moskau 15:00 Uhr ist? "
            "Antworte kurz: nur die Uhrzeit."
        ),
        "lang": "de",
        "desc": "DE timezone reasoning",
        "check": lambda r: any(t in r for t in ["13:00", "14:00"]),
        "options": {"num_predict": 20, "temperature": 0},
    },
    # ── English ───────────────────────────────────────────────────────────────
    "en_factual": {
        "text": "What is the value of Pi to 5 decimal places? Just the number, nothing else.",
        "lang": "en",
        "desc": "EN factual (Pi)",
        "check": lambda r: "3.14159" in r.replace(",", "."),
        "options": {"num_predict": 30, "temperature": 0},
    },
    "en_calendar": {
        "text": (
            'Extract event data from text and return JSON.\n'
            'Text: "Meeting with doctor on Thursday at 14:00"\n'
            'Format: {"title": "<name>", "dt": "<YYYY-MM-DDTHH:MM>"}\n'
            'Return only JSON, no explanation.'
        ),
        "lang": "en",
        "desc": "EN calendar → JSON",
        "check": lambda r: '"title"' in r and '"dt"' in r,
        "options": {"num_predict": 60, "temperature": 0},
    },
    "en_code": {
        "text": (
            "Write a Python one-liner (using a list comprehension) that returns "
            "the sum of squares of even numbers in a list `nums`. "
            "Return ONLY the code, no explanation."
        ),
        "lang": "en",
        "desc": "EN code generation",
        "check": lambda r: "sum(" in r and ("nums" in r or "num" in r),
        "options": {"num_predict": 60, "temperature": 0},
    },
    # ── Slovenian ─────────────────────────────────────────────────────────────
    "sl_factual": {
        "text": "Koliko je vrednost Pi na 5 decimalnih mest? Samo število, nič drugega.",
        "lang": "sl",
        "desc": "SL factual (Pi)",
        "check": lambda r: "3.14159" in r.replace(",", "."),
        "options": {"num_predict": 30, "temperature": 0},
    },
    "sl_calendar": {
        "text": (
            'Izvleci podatke o dogodku iz besedila in vrni JSON.\n'
            'Besedilo: "Sestanek z zdravnikom v četrtek ob 14:00"\n'
            'Format: {"title": "<naziv>", "dt": "<YYYY-MM-DDTHH:MM>"}\n'
            'Vrni samo JSON, brez razlage.'
        ),
        "lang": "sl",
        "desc": "SL calendar → JSON",
        "check": lambda r: '"title"' in r and '"dt"' in r,
        "options": {"num_predict": 60, "temperature": 0},
    },
    "sl_assistant": {
        "text": (
            "Ti si glasovni pomočnik Taris. Uporabnik pravi: 'Nastavi opomnik jutri ob 9 zjutraj.'\n"
            "Odgovori kratko in potrdi dejanje v slovenščini (1-2 stavka)."
        ),
        "lang": "sl",
        "desc": "SL assistant reply",
        "check": lambda r: len(r.strip()) > 10 and any(
            w in r.lower() for w in ["jutri", "9", "opomn", "nastav", "v redu", "ok", "razumem"]
        ),
        "options": {"num_predict": 80, "temperature": 0.1},
    },
}

LANG_GROUPS = {
    "ru": ["ru_factual", "ru_calendar", "ru_assistant"],
    "de": ["de_factual", "de_calendar", "de_reasoning"],
    "en": ["en_factual", "en_calendar", "en_code"],
    "sl": ["sl_factual", "sl_calendar", "sl_assistant"],
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PromptResult:
    prompt_key: str
    desc: str
    wall_s: float          # total wall-clock seconds
    ttft_s: float          # time to first token (load + first eval)
    tokens_out: int        # output tokens
    tps: float             # output tokens per second
    passed: bool           # quality check
    response: str          # truncated response for display
    error: str = ""

@dataclass
class ModelResult:
    model: str
    timestamp: str
    prompt_results: list[PromptResult] = field(default_factory=list)
    avg_tps: float = 0.0
    avg_wall_s: float = 0.0
    quality_score: float = 0.0    # fraction of passed checks
    error: str = ""

# ---------------------------------------------------------------------------
# Ollama API helpers
# ---------------------------------------------------------------------------

def _ollama_request(path: str, payload: dict, timeout: int = 120) -> dict:
    url = f"{OLLAMA_URL}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

def _ollama_get(path: str, timeout: int = 10) -> dict:
    """GET request to Ollama API."""
    url = f"{OLLAMA_URL}{path}"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

def _get_available_models() -> list[str]:
    """Return list of model names currently pulled in Ollama."""
    try:
        result = _ollama_get("/api/tags", timeout=10)
        return [m["name"] for m in result.get("models", [])]
    except Exception as e:
        print(f"[WARN] Could not list Ollama models: {e}", file=sys.stderr)
        return []

def _run_prompt(model: str, prompt: str, options: dict) -> dict:
    """
    Call Ollama generate API (non-streaming).
    Disables thinking mode for models that emit <think> blocks (qwen3, gemma4,
    deepseek-r) to prevent consuming all tokens in CoT without producing output.
    Returns the full response dict from Ollama.
    """
    is_thinking_model = any(
        tag in model.lower() for tag in ("qwen3", "qwen3.5", "deepseek-r", "gemma4")
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": options.get("temperature", 0),
            "num_predict": options.get("num_predict", 100),
        },
    }
    if is_thinking_model:
        payload["think"] = False   # disable chain-of-thought for benchmark
    return _ollama_request("/api/generate", payload, timeout=180)

# ---------------------------------------------------------------------------
# Benchmark one model
# ---------------------------------------------------------------------------

def benchmark_model(model: str, prompt_keys: list[str], verbose: bool = False) -> ModelResult:
    result = ModelResult(model=model, timestamp=datetime.now(timezone.utc).isoformat())

    # Warm-up: brief ping to load model into VRAM
    print(f"  Warming up {model}…", end=" ", flush=True)
    try:
        _run_prompt(model, "Hi", {"num_predict": 3, "temperature": 0})
        print("done")
    except Exception as e:
        print(f"FAILED ({e})")
        result.error = str(e)
        return result

    # Run each prompt
    for key in prompt_keys:
        pdef = PROMPTS[key]
        print(f"  [{key}] {pdef['desc']}… ", end="", flush=True)
        try:
            t0 = time.time()
            resp = _run_prompt(model, pdef["text"], pdef["options"])
            wall = time.time() - t0

            tokens_out = resp.get("eval_count", 0)
            eval_dur_ns = resp.get("eval_duration", 1)
            load_dur_ns = resp.get("load_duration", 0)
            prompt_dur_ns = resp.get("prompt_eval_duration", 0)

            tps = tokens_out / (eval_dur_ns / 1e9) if eval_dur_ns > 0 else 0
            ttft = (load_dur_ns + prompt_dur_ns) / 1e9

            response_text = resp.get("response", "").strip()
            passed = pdef["check"](response_text)

            pr = PromptResult(
                prompt_key=key,
                desc=pdef["desc"],
                wall_s=round(wall, 2),
                ttft_s=round(ttft, 2),
                tokens_out=tokens_out,
                tps=round(tps, 1),
                passed=passed,
                response=response_text[:120],
            )
            status = "✅" if passed else "❌"
            print(f"{wall:.1f}s | {tps:.0f} t/s | {status}")
            if verbose:
                print(f"    → {response_text[:100]}")

        except Exception as e:
            print(f"ERROR: {e}")
            pr = PromptResult(
                prompt_key=key, desc=pdef["desc"],
                wall_s=0, ttft_s=0, tokens_out=0, tps=0,
                passed=False, response="", error=str(e),
            )
        result.prompt_results.append(pr)

    # Aggregate
    valid = [r for r in result.prompt_results if not r.error]
    if valid:
        result.avg_tps = round(sum(r.tps for r in valid) / len(valid), 1)
        result.avg_wall_s = round(sum(r.wall_s for r in valid) / len(valid), 2)
        result.quality_score = round(sum(1 for r in valid if r.passed) / len(valid), 2)

    return result

# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_summary_table(results: list[ModelResult], prompt_keys: list[str]):
    cols = ["Model", "Avg t/s", "Avg wall(s)", "Quality"]
    for k in prompt_keys:
        cols.append(k[:12])
    widths = [max(len(c), 18) for c in cols]
    widths[0] = max(22, max(len(r.model) for r in results) + 2)

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    def row(*cells):
        return "| " + " | ".join(str(c).ljust(w) for c, w in zip(cells, widths)) + " |"

    print("\n" + sep)
    print(row(*cols))
    print(sep)
    for r in results:
        q_pct = f"{r.quality_score*100:.0f}%"
        tps = f"{r.avg_tps:.0f}" if r.avg_tps else "ERR"
        wall = f"{r.avg_wall_s:.1f}s" if r.avg_wall_s else "ERR"
        cells = [r.model, tps, wall, q_pct]
        for k in prompt_keys:
            pr = next((p for p in r.prompt_results if p.prompt_key == k), None)
            if pr is None:
                cells.append("—")
            elif pr.error:
                cells.append("ERR")
            else:
                mark = "✅" if pr.passed else "❌"
                cells.append(f"{mark} {pr.tps:.0f}t/s")
        print(row(*cells))
    print(sep)


def print_lang_summary(results: list[ModelResult], langs: list[str]):
    """Per-language quality matrix: models × languages."""
    if len(langs) < 2:
        return
    print("\n=== Per-language quality score ===")
    header = f"  {'Model':<24}" + "".join(f"  {lg.upper():>7}" for lg in langs) + "   Avg"
    print(header)
    print(f"  {'-' * (24 + 9 * len(langs) + 6)}")
    for r in results:
        if r.error:
            continue
        lang_scores = {}
        for lang in langs:
            keys = LANG_GROUPS.get(lang, [])
            prs = [p for p in r.prompt_results if p.prompt_key in keys and not p.error]
            if prs:
                lang_scores[lang] = sum(1 for p in prs if p.passed) / len(prs)
        row_s = f"  {r.model:<24}"
        vals = []
        for lang in langs:
            sc = lang_scores.get(lang)
            if sc is None:
                row_s += "      n/a"
            else:
                row_s += f"  {sc:.0%}".rjust(8)
                vals.append(sc)
        if vals:
            row_s += f"  {sum(vals)/len(vals):.0%}".rjust(6)
        print(row_s)


def print_detail_table(results: list[ModelResult], prompt_keys: list[str]):
    """Per-prompt latency breakdown."""
    print("\n=== Latency breakdown (TTFT / wall) ===")
    header = ["Model"] + [k for k in prompt_keys]
    row_fmt = "{:<22} " + "  {:<16}" * len(prompt_keys)
    print(row_fmt.format(*header))
    print("-" * (22 + 18 * len(prompt_keys)))
    for r in results:
        vals = [r.model]
        for k in prompt_keys:
            pr = next((p for p in r.prompt_results if p.prompt_key == k), None)
            if pr and not pr.error:
                vals.append(f"{pr.ttft_s:.1f}s/{pr.wall_s:.1f}s")
            else:
                vals.append("—")
        print(row_fmt.format(*vals))

def compare_with_baseline(results: list[ModelResult], baseline_path: str):
    """Print delta vs saved baseline JSON."""
    if not os.path.exists(baseline_path):
        print(f"[WARN] Baseline not found: {baseline_path}")
        return
    with open(baseline_path) as f:
        baseline_data = json.load(f)
    baseline_map = {r["model"]: r for r in baseline_data.get("results", [])}
    print("\n=== Comparison vs baseline ===")
    for r in results:
        b = baseline_map.get(r.model)
        if not b:
            print(f"  {r.model}: no baseline")
            continue
        tps_delta = r.avg_tps - b.get("avg_tps", 0)
        q_delta = r.quality_score - b.get("quality_score", 0)
        tps_sign = "+" if tps_delta >= 0 else ""
        q_sign = "+" if q_delta >= 0 else ""
        print(
            f"  {r.model:<22} t/s {tps_sign}{tps_delta:.1f}  "
            f"quality {q_sign}{q_delta*100:.0f}%"
        )

# ---------------------------------------------------------------------------
# Save / load results
# ---------------------------------------------------------------------------

def save_results(results: list[ModelResult], path: str):
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ollama_url": OLLAMA_URL,
        "results": [asdict(r) for r in results],
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved → {path}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ollama LLM model benchmark — 4 languages")
    parser.add_argument("--model",  help="Benchmark only this model (comma-separated for multiple)")
    parser.add_argument("--lang",   help="Restrict to these language groups (comma-sep: ru,de,en,sl)")
    parser.add_argument("--save",   metavar="PATH", help="Save results to this JSON file")
    parser.add_argument("--compare", metavar="PATH", help="Compare against baseline JSON")
    parser.add_argument("--quick",  action="store_true", help="Run only latency + ru_factual")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show response text")
    parser.add_argument("--prompt", help="Run only these prompts (comma-separated keys)")
    parser.add_argument("--host",   metavar="URL",
                        help="Ollama API base URL (overrides OLLAMA_URL env var), "
                             "e.g. http://<sintaition-ip>:11434")
    parser.add_argument("--target", metavar="NAME",
                        help="Human-readable target label for reports, e.g. TariStation2 or SintAItion")
    args = parser.parse_args()

    # Apply --host / --target overrides before any Ollama calls
    global OLLAMA_URL, BENCHMARK_TARGET
    if args.host:
        OLLAMA_URL = args.host.rstrip("/")
    if args.target:
        BENCHMARK_TARGET = args.target

    # Determine prompt keys
    if args.quick:
        prompt_keys = ["latency", "ru_factual"]
    elif args.prompt:
        prompt_keys = [k.strip() for k in args.prompt.split(",") if k.strip() in PROMPTS]
        if not prompt_keys:
            print(f"Unknown prompt keys. Available: {', '.join(PROMPTS.keys())}")
            sys.exit(1)
    elif args.lang:
        langs_filter = [l.strip() for l in args.lang.split(",")]
        prompt_keys = ["latency"]
        for lg in langs_filter:
            prompt_keys.extend(LANG_GROUPS.get(lg, []))
    else:
        prompt_keys = list(PROMPTS.keys())
        langs_filter = list(LANG_GROUPS.keys())

    # Determine active languages for summary
    if not args.quick and not args.prompt:
        langs_active = [lg for lg in LANG_GROUPS if any(k in prompt_keys for k in LANG_GROUPS[lg])]
    else:
        langs_active = []

    # Determine models to test
    available = _get_available_models()
    if not available:
        print("ERROR: cannot reach Ollama or no models found")
        sys.exit(1)

    if args.model:
        requested = [m.strip() for m in args.model.split(",")]
        models = [m for m in requested if m in available]
        missing = [m for m in requested if m not in available]
        if missing:
            print(f"[WARN] Not found in Ollama: {', '.join(missing)}")
    else:
        models = [m for m in CANDIDATE_MODELS if m in available]
        for m in available:
            if "qwen3.5" in m and m not in models:
                models.append(m)

    if not models:
        print("No models to benchmark (check ollama list)")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"Ollama LLM Benchmark — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    target_label = BENCHMARK_TARGET or OLLAMA_URL
    print(f"Target:  {target_label}")
    if BENCHMARK_TARGET:
        print(f"Ollama:  {OLLAMA_URL}")
    print(f"Models:  {', '.join(models)}")
    print(f"Prompts: {', '.join(prompt_keys)}")
    print(f"{'='*70}")

    results = []
    for model in models:
        print(f"\n→ Benchmarking: {model}")
        r = benchmark_model(model, prompt_keys, verbose=args.verbose)
        results.append(r)

    # Summary tables
    print_summary_table(results, prompt_keys)
    if not args.quick:
        print_detail_table(results, prompt_keys)
    if langs_active:
        print_lang_summary(results, langs_active)

    if args.compare:
        compare_with_baseline(results, args.compare)

    # Save
    save_path = args.save
    if not save_path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        save_dir = os.path.expanduser("~/.taris/tests")
        save_path = os.path.join(save_dir, f"llm_benchmark_{ts}.json")
    save_results(results, save_path)

    valid_results = [r for r in results if not r.error and r.avg_tps > 0]
    if valid_results:
        fastest = max(valid_results, key=lambda r: r.avg_tps)
        best_quality = max(valid_results, key=lambda r: r.quality_score)
        print(f"\n🏆 Fastest:       {fastest.model} ({fastest.avg_tps:.0f} t/s)")
        print(f"🎯 Best quality:  {best_quality.model} ({best_quality.quality_score*100:.0f}%)")

if __name__ == "__main__":
    main()

