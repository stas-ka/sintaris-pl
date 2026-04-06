#!/usr/bin/env python3
"""
benchmark_conversation.py — Conversation quality, memory, RAG accuracy, context isolation
==========================================================================================
Benchmarks Ollama LLM for multi-turn memory, context isolation, response quality,
multilingual switching, and multi-turn latency. Calls Ollama directly — no bot needed.

Usage:
    # Run locally (TariStation2):
    python3 tools/benchmark_conversation.py

    # Quick run (skip slow/flaky suites):
    python3 tools/benchmark_conversation.py --target ts2 --skip-isolation --skip-multilang -n 1

    # Specific models:
    python3 tools/benchmark_conversation.py --ollama-models qwen2:0.5b qwen3:14b

    # Save to custom file:
    python3 tools/benchmark_conversation.py --output results/conv_ts2.json

    # Compare results:
    python3 tools/benchmark_conversation.py --compare results/conv_ts2.json results/conv_ts1.json

Output: JSON + human-readable table to stdout. Results appended to --output file.

Environment (auto-detected from ~/.taris/bot.env if present):
    OLLAMA_URL    — http://127.0.0.1:11434
    OLLAMA_MODEL  — default model tag
"""

import argparse
import json
import os
import platform
import time
import urllib.request
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Auto-load bot.env if present
# ─────────────────────────────────────────────────────────────────────────────
_taris_dir = Path(os.environ.get("TARIS_DIR", Path.home() / ".taris"))
_bot_env = _taris_dir / "bot.env"
if _bot_env.exists():
    for _line in _bot_env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

# ─────────────────────────────────────────────────────────────────────────────
# Quality test corpus
# ─────────────────────────────────────────────────────────────────────────────
QUALITY_TESTS = [
    ("Что такое фотосинтез?",
     ["свет", "растени", "хлорофил", "углекислый", "кислород"]),
    ("Назови столицу Франции.",
     ["Париж", "Paris"]),
    ("Сколько дней в году?",
     ["365", "366", "триста"]),
    ("Что такое Интернет?",
     ["сеть", "данн", "компьютер", "информац"]),
    ("Как звали первого космонавта?",
     ["Гагарин", "Юрий", "Gagarin"]),
]

MULTILANG_TESTS = [
    ("ru", "You are a helpful assistant. Answer in Russian.",
     "Сколько планет в солнечной системе?"),
    ("en", "You are a helpful assistant. Answer in English.",
     "How many planets are in the solar system?"),
    ("de", "Du bist ein hilfreicher Assistent. Antworte auf Deutsch.",
     "Wie viele Planeten gibt es im Sonnensystem?"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _sys_info() -> dict:
    cpu = ""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    cpu = line.split(":", 1)[1].strip()
                    break
    except Exception:
        cpu = platform.processor()
    mem_gb = 0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    mem_gb = round(int(line.split()[1]) / 1024 / 1024, 1)
                    break
    except Exception:
        pass
    return {
        "hostname": platform.node(),
        "cpu": cpu,
        "ram_gb": mem_gb,
        "python": platform.python_version(),
        "arch": platform.machine(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Ollama concurrency guard
# ─────────────────────────────────────────────────────────────────────────────
_BENCH_LOCK = Path("/tmp/taris_benchmark.lock")

def _acquire_bench_lock() -> bool:
    """Write a lock file. Warn if one already exists (benchmark already running)."""
    if _BENCH_LOCK.exists():
        try:
            pid = int(_BENCH_LOCK.read_text().strip())
            import os as _os
            _os.kill(pid, 0)   # check if PID is alive
            print(f"\n⚠️  WARNING: Another benchmark (PID {pid}) is already using Ollama.")
            print("   Running concurrent benchmarks may cause bot LLM timeouts.")
            print("   Use Ctrl-C to cancel, or wait for the other benchmark to finish.\n")
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass  # stale lock — overwrite
    _BENCH_LOCK.write_text(str(os.getpid()))
    return True

def _release_bench_lock() -> None:
    try:
        _BENCH_LOCK.unlink(missing_ok=True)
    except Exception:
        pass


def _ollama_check(url: str = OLLAMA_URL) -> bool:
    """Return True if Ollama is reachable."""
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _ollama_chat(model: str, messages: list[dict],
                 url: str = OLLAMA_URL, timeout: int = 120) -> tuple[str, float]:
    """POST /api/chat. Returns (response_text, latency_s)."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 300},
    }).encode()
    req = urllib.request.Request(
        f"{url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    latency = time.time() - t0
    text = data.get("message", {}).get("content", "").strip()
    return text, latency


def _print_table(headers: list[str], rows: list[list], widths: list[int]) -> None:
    def _cell(v, w):
        s = str(v)
        return s[:w].ljust(w) if len(s) <= w else s[:w - 1] + "…"

    hdr = "  " + "  ".join(_cell(h, w) for h, w in zip(headers, widths))
    sep = "  " + "  ".join("─" * w for w in widths)
    print(hdr)
    print(sep)
    for row in rows:
        print("  " + "  ".join(_cell(v, w) for v, w in zip(row, widths)))


# ─────────────────────────────────────────────────────────────────────────────
# Suite: conversation_memory
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_conversation_memory(model: str, n_repeats: int = 2,
                                   url: str = OLLAMA_URL) -> list[dict]:
    """Multi-turn memory: LLM must recall facts introduced in turn 1."""
    results = []

    for rep in range(n_repeats):
        try:
            messages: list[dict] = [
                {"role": "system", "content": "You are a helpful assistant. Answer in Russian."},
                {"role": "user",   "content":
                    "Меня зовут Алексей. Мне 35 лет. Я живу в Берлине."},
            ]
            # Turn 1 — introduce facts
            t0 = time.time()
            reply1, lat1 = _ollama_chat(model, messages, url)
            messages.append({"role": "assistant", "content": reply1})

            # Turn 2 — recall facts
            messages.append({"role": "user", "content":
                "Как меня зовут? Сколько мне лет? Где я живу?"})
            reply2, lat2 = _ollama_chat(model, messages, url)
            total_s = time.time() - t0

            facts = ["Алексей", "35", "Берлин"]
            hits = sum(1 for f in facts if f.lower() in reply2.lower())
            memory_score = round(hits / len(facts), 3)

            results.append({
                "suite": "conversation_memory",
                "model": model,
                "rep": rep,
                "ok": True,
                "memory_score": memory_score,
                "facts_recalled": hits,
                "facts_total": len(facts),
                "turn1_s": round(lat1, 3),
                "turn2_s": round(lat2, 3),
                "total_s": round(total_s, 3),
                "reply_preview": reply2[:120],
            })
            print(f"    [{model}] memory rep{rep}: score={memory_score:.0%} "
                  f"({hits}/{len(facts)} facts)  turn1={lat1:.2f}s turn2={lat2:.2f}s")
        except Exception as e:
            results.append({
                "suite": "conversation_memory", "model": model, "rep": rep,
                "ok": False, "error": str(e)[:200],
            })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Suite: context_isolation
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_context_isolation(model: str, n_repeats: int = 2,
                                  url: str = OLLAMA_URL) -> list[dict]:
    """Context isolation: trap date (1837) must not pollute unrelated year answers."""
    TRAP_YEAR = "1837"
    CHECKS = [
        ("В каком году умер Михаил Лермонтов?", "1841"),
        ("В каком году родился Лев Толстой?", "1828"),
    ]
    results = []

    for rep in range(n_repeats):
        try:
            # Prime context with the trap fact
            messages: list[dict] = [
                {"role": "system",    "content": "You are a helpful assistant. Answer briefly."},
                {"role": "user",      "content": "Александр Пушкин умер в 1837 году. Запомни это."},
            ]
            trap_reply, _ = _ollama_chat(model, messages, url)
            messages.append({"role": "assistant", "content": trap_reply})

            isolation_hits = 0
            pollution_detected = False
            details: list[dict] = []

            for question, expected_year in CHECKS:
                messages_q = messages + [{"role": "user", "content": question}]
                t0 = time.time()
                reply, lat = _ollama_chat(model, messages_q, url)
                lat_s = time.time() - t0

                correct = expected_year in reply
                polluted = TRAP_YEAR in reply and not correct
                if correct:
                    isolation_hits += 1
                if polluted:
                    pollution_detected = True

                details.append({
                    "question": question,
                    "expected": expected_year,
                    "reply_preview": reply[:80],
                    "correct": correct,
                    "polluted": polluted,
                    "latency_s": round(lat, 3),
                })
                print(f"    [{model}] isolation rep{rep}: Q='{question[:40]}' "
                      f"expected={expected_year} correct={correct} polluted={polluted}")

            results.append({
                "suite": "context_isolation",
                "model": model,
                "rep": rep,
                "ok": True,
                "isolation_score": round(isolation_hits / len(CHECKS), 3),
                "isolation_hits": isolation_hits,
                "checks_total": len(CHECKS),
                "pollution_detected": pollution_detected,
                "details": details,
            })
        except Exception as e:
            results.append({
                "suite": "context_isolation", "model": model, "rep": rep,
                "ok": False, "error": str(e)[:200],
            })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Suite: response_quality
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_response_quality(model: str, n_repeats: int = 2,
                                url: str = OLLAMA_URL) -> list[dict]:
    """Response quality: keyword hits for standard Russian questions."""
    results = []

    for rep in range(n_repeats):
        question_results: list[dict] = []
        total_keywords = 0
        total_hits = 0

        for question, keywords in QUALITY_TESTS:
            try:
                messages = [
                    {"role": "system", "content": "You are a helpful assistant. Answer in Russian."},
                    {"role": "user",   "content": question},
                ]
                t0 = time.time()
                reply, lat = _ollama_chat(model, messages, url)
                lat_s = time.time() - t0

                hits = sum(1 for kw in keywords if kw.lower() in reply.lower())
                passed = hits >= 1
                total_keywords += len(keywords)
                total_hits += hits

                question_results.append({
                    "question": question[:60],
                    "keywords": keywords,
                    "keyword_hits": hits,
                    "passed": passed,
                    "latency_s": round(lat, 3),
                    "reply_preview": reply[:100],
                })
                print(f"    [{model}] quality rep{rep}: '{question[:40]}' "
                      f"hits={hits}/{len(keywords)} {'✓' if passed else '✗'}")
            except Exception as e:
                question_results.append({
                    "question": question[:60],
                    "ok": False,
                    "error": str(e)[:100],
                })

        relevance_score = round(total_hits / total_keywords, 3) if total_keywords else 0
        passed_count = sum(1 for q in question_results if q.get("passed", False))
        results.append({
            "suite": "response_quality",
            "model": model,
            "rep": rep,
            "ok": True,
            "relevance_score": relevance_score,
            "keyword_hits": total_hits,
            "keywords_total": total_keywords,
            "questions_passed": passed_count,
            "questions_total": len(QUALITY_TESTS),
            "details": question_results,
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Suite: conversation_multilang
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_conversation_multilang(model: str, n_repeats: int = 2,
                                      url: str = OLLAMA_URL) -> list[dict]:
    """Multilingual: verify LLM answers in the requested language."""
    results = []

    for rep in range(n_repeats):
        lang_results: list[dict] = []

        for lang, system_prompt, question in MULTILANG_TESTS:
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": question},
                ]
                t0 = time.time()
                reply, lat = _ollama_chat(model, messages, url)
                lat_s = time.time() - t0

                has_cyrillic = any("\u0400" <= c <= "\u04ff" for c in reply)
                if lang == "ru":
                    lang_correct = has_cyrillic
                else:
                    lang_correct = not has_cyrillic

                lang_results.append({
                    "lang": lang,
                    "lang_correct": lang_correct,
                    "has_cyrillic": has_cyrillic,
                    "latency_s": round(lat, 3),
                    "reply_preview": reply[:80],
                })
                print(f"    [{model}] multilang rep{rep}: lang={lang} "
                      f"correct={lang_correct} ({lat:.2f}s)")
            except Exception as e:
                lang_results.append({
                    "lang": lang,
                    "lang_correct": False,
                    "ok": False,
                    "error": str(e)[:100],
                })

        langs_correct = sum(1 for lr in lang_results if lr.get("lang_correct", False))
        results.append({
            "suite": "conversation_multilang",
            "model": model,
            "rep": rep,
            "ok": True,
            "langs_correct": langs_correct,
            "langs_total": len(MULTILANG_TESTS),
            "lang_score": round(langs_correct / len(MULTILANG_TESTS), 3),
            "details": lang_results,
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Suite: llm_latency_multiturn
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_llm_latency_multiturn(model: str, n_repeats: int = 2,
                                     url: str = OLLAMA_URL) -> list[dict]:
    """Multi-turn latency: measure total + per-turn latency for 1, 3, 5 turns."""
    TURNS_SEQUENCE = [
        ("user", "Меня зовут Алексей. Мне 35 лет. Я живу в Берлине."),
        ("user", "Какая сейчас погода в Берлине?"),
        ("user", "Как мне добраться до центра города?"),
        ("user", "Какие достопримечательности там есть?"),
        ("user", "Что посоветуешь посмотреть в первую очередь?"),
    ]
    results = []

    for rep in range(n_repeats):
        for n_turns in (1, 3, 5):
            try:
                messages: list[dict] = [
                    {"role": "system", "content": "You are a helpful assistant. Answer in Russian."},
                ]
                turn_latencies: list[float] = []
                t_total = time.time()

                for i, (role, content) in enumerate(TURNS_SEQUENCE[:n_turns]):
                    messages.append({"role": role, "content": content})
                    reply, lat = _ollama_chat(model, messages, url, timeout=180)
                    messages.append({"role": "assistant", "content": reply})
                    turn_latencies.append(lat)

                total_s = time.time() - t_total
                avg_turn_s = sum(turn_latencies) / len(turn_latencies) if turn_latencies else 0

                results.append({
                    "suite": "llm_latency_multiturn",
                    "model": model,
                    "rep": rep,
                    "n_turns": n_turns,
                    "ok": True,
                    "total_s": round(total_s, 3),
                    "avg_turn_s": round(avg_turn_s, 3),
                    "turn_latencies_s": [round(t, 3) for t in turn_latencies],
                })
                print(f"    [{model}] latency rep{rep}: {n_turns} turns — "
                      f"total={total_s:.2f}s avg_turn={avg_turn_s:.2f}s")
            except Exception as e:
                results.append({
                    "suite": "llm_latency_multiturn", "model": model,
                    "rep": rep, "n_turns": n_turns,
                    "ok": False, "error": str(e)[:200],
                })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Results I/O
# ─────────────────────────────────────────────────────────────────────────────

def _load_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else [data]
    except (json.JSONDecodeError, OSError):
        return []


def _save_results(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))


# ─────────────────────────────────────────────────────────────────────────────
# Print report
# ─────────────────────────────────────────────────────────────────────────────

def _print_run_report(run_result: dict) -> None:
    sysinfo = run_result.get("sysinfo", {})
    print(f"\n{'=' * 70}")
    print(f"🖥  {sysinfo.get('hostname', '?')}  |  {sysinfo.get('cpu', '?')[:50]}")
    print(f"   RAM: {sysinfo.get('ram_gb', '?')} GB  |  Python {sysinfo.get('python', '?')}")
    print(f"   Timestamp: {run_result.get('timestamp', '?')}")
    print(f"{'=' * 70}")

    all_results = run_result.get("results", [])

    # Memory
    mem_rows = [r for r in all_results if r.get("suite") == "conversation_memory" and r.get("ok")]
    if mem_rows:
        print("\n🧠 Conversation Memory")
        _print_table(
            ["Model", "Rep", "Score", "Facts", "Turn1", "Turn2"],
            [[r["model"], r["rep"], f"{r['memory_score']:.0%}",
              f"{r['facts_recalled']}/{r['facts_total']}",
              f"{r['turn1_s']:.2f}s", f"{r['turn2_s']:.2f}s"] for r in mem_rows],
            [18, 4, 7, 7, 8, 8],
        )

    # Isolation
    iso_rows = [r for r in all_results if r.get("suite") == "context_isolation" and r.get("ok")]
    if iso_rows:
        print("\n🔒 Context Isolation")
        _print_table(
            ["Model", "Rep", "Score", "Correct", "Polluted"],
            [[r["model"], r["rep"],
              f"{r['isolation_score']:.0%}",
              f"{r['isolation_hits']}/{r['checks_total']}",
              "⚠️ YES" if r.get("pollution_detected") else "OK"] for r in iso_rows],
            [18, 4, 7, 9, 10],
        )

    # Quality
    qual_rows = [r for r in all_results if r.get("suite") == "response_quality" and r.get("ok")]
    if qual_rows:
        print("\n✅ Response Quality")
        _print_table(
            ["Model", "Rep", "Relevance", "KW Hits", "Q Passed"],
            [[r["model"], r["rep"],
              f"{r['relevance_score']:.0%}",
              f"{r['keyword_hits']}/{r['keywords_total']}",
              f"{r['questions_passed']}/{r['questions_total']}"] for r in qual_rows],
            [18, 4, 10, 9, 10],
        )

    # Multilang
    lang_rows = [r for r in all_results
                 if r.get("suite") == "conversation_multilang" and r.get("ok")]
    if lang_rows:
        print("\n🌍 Multilingual")
        _print_table(
            ["Model", "Rep", "Score", "Correct"],
            [[r["model"], r["rep"],
              f"{r['lang_score']:.0%}",
              f"{r['langs_correct']}/{r['langs_total']}"] for r in lang_rows],
            [18, 4, 7, 9],
        )

    # Latency multiturn
    lat_rows = [r for r in all_results
                if r.get("suite") == "llm_latency_multiturn" and r.get("ok")]
    if lat_rows:
        print("\n⚡ Multi-turn Latency")
        _print_table(
            ["Model", "Rep", "Turns", "Total", "Avg/turn"],
            [[r["model"], r["rep"], r["n_turns"],
              f"{r['total_s']:.2f}s", f"{r['avg_turn_s']:.2f}s"] for r in lat_rows],
            [18, 4, 6, 9, 10],
        )

    # Failures
    failed = [r for r in all_results if not r.get("ok")]
    if failed:
        print(f"\n⚠️  {len(failed)} failure(s):")
        for r in failed:
            print(f"   {r.get('suite', '?')} [{r.get('model', '?')}]: {r.get('error', '?')[:80]}")


# ─────────────────────────────────────────────────────────────────────────────
# Compare report
# ─────────────────────────────────────────────────────────────────────────────

def compare_report(result_files: list[str]) -> None:
    """Print comparison table across multiple result files."""
    runs = []
    for f in result_files:
        try:
            data = json.loads(Path(f).read_text())
            entries = data if isinstance(data, list) else [data]
            runs.extend(entries)
        except Exception as e:
            print(f"[WARN] Could not load {f}: {e}")

    if not runs:
        print("No results to compare.")
        return

    print(f"\n{'=' * 80}")
    print("📊 Cross-target conversation benchmark comparison")
    print(f"{'=' * 80}")

    def _host(run: dict) -> str:
        return run.get("sysinfo", {}).get("hostname", run.get("target", "?"))

    # Memory
    print("\n🧠 Conversation Memory (avg memory_score, avg turn2 latency)")
    mem_by_host: dict[str, list[dict]] = {}
    for run in runs:
        host = _host(run)
        for r in run.get("results", []):
            if r.get("suite") == "conversation_memory" and r.get("ok"):
                mem_by_host.setdefault(host, []).append(r)
    if mem_by_host:
        rows = []
        for host, items in sorted(mem_by_host.items()):
            models = sorted({i["model"] for i in items})
            for m in models:
                mi = [i for i in items if i["model"] == m]
                avg_score = sum(i["memory_score"] for i in mi) / len(mi)
                avg_t2 = sum(i["turn2_s"] for i in mi) / len(mi)
                rows.append([host, m, f"{avg_score:.0%}", f"{avg_t2:.2f}s"])
        _print_table(["Host", "Model", "Avg Score", "Avg Turn2"], rows, [20, 16, 10, 10])

    # Quality
    print("\n✅ Response Quality (avg relevance_score)")
    qual_by_host: dict[str, list[dict]] = {}
    for run in runs:
        host = _host(run)
        for r in run.get("results", []):
            if r.get("suite") == "response_quality" and r.get("ok"):
                qual_by_host.setdefault(host, []).append(r)
    if qual_by_host:
        rows = []
        for host, items in sorted(qual_by_host.items()):
            models = sorted({i["model"] for i in items})
            for m in models:
                mi = [i for i in items if i["model"] == m]
                avg_rel = sum(i["relevance_score"] for i in mi) / len(mi)
                avg_qp = sum(i["questions_passed"] for i in mi) / len(mi)
                rows.append([host, m, f"{avg_rel:.0%}", f"{avg_qp:.1f}/{mi[0]['questions_total']}"])
        _print_table(["Host", "Model", "Relevance", "Q Passed"], rows, [20, 16, 10, 12])

    # Isolation
    print("\n🔒 Context Isolation")
    iso_by_host: dict[str, list[dict]] = {}
    for run in runs:
        host = _host(run)
        for r in run.get("results", []):
            if r.get("suite") == "context_isolation" and r.get("ok"):
                iso_by_host.setdefault(host, []).append(r)
    if iso_by_host:
        rows = []
        for host, items in sorted(iso_by_host.items()):
            models = sorted({i["model"] for i in items})
            for m in models:
                mi = [i for i in items if i["model"] == m]
                avg_iso = sum(i["isolation_score"] for i in mi) / len(mi)
                any_pollution = any(i.get("pollution_detected") for i in mi)
                rows.append([host, m, f"{avg_iso:.0%}", "⚠️" if any_pollution else "OK"])
        _print_table(["Host", "Model", "Isolation", "Pollution"], rows, [20, 16, 10, 10])

    # Latency
    print("\n⚡ Multi-turn Latency (avg, 5 turns)")
    lat_by_host: dict[str, list[dict]] = {}
    for run in runs:
        host = _host(run)
        for r in run.get("results", []):
            if (r.get("suite") == "llm_latency_multiturn"
                    and r.get("ok") and r.get("n_turns") == 5):
                lat_by_host.setdefault(host, []).append(r)
    if lat_by_host:
        rows = []
        for host, items in sorted(lat_by_host.items()):
            models = sorted({i["model"] for i in items})
            for m in models:
                mi = [i for i in items if i["model"] == m]
                avg_total = sum(i["total_s"] for i in mi) / len(mi)
                avg_turn = sum(i["avg_turn_s"] for i in mi) / len(mi)
                rows.append([host, m, f"{avg_total:.2f}s", f"{avg_turn:.2f}s"])
        _print_table(["Host", "Model", "Total (5t)", "Avg/turn"], rows, [20, 16, 12, 10])


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

RESULTS_DEFAULT = Path(__file__).parent / "benchmark_conv_results.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Conversation quality / memory / context benchmark for Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--target", default="ts2",
                        help="Target label (ts2/sintaition/pi2/local, informational only)")
    parser.add_argument("--ollama-models", nargs="+", default=None, dest="ollama_models",
                        help="Ollama model tags to benchmark (default: from bot.env or qwen2:0.5b)")
    parser.add_argument("--ollama-url", default=None, dest="ollama_url",
                        help=f"Ollama base URL (default: {OLLAMA_URL})")
    parser.add_argument("--skip-memory",    action="store_true", help="Skip memory suite")
    parser.add_argument("--skip-isolation", action="store_true", help="Skip context isolation suite")
    parser.add_argument("--skip-quality",   action="store_true", help="Skip response quality suite")
    parser.add_argument("--skip-multilang", action="store_true", help="Skip multilang suite")
    parser.add_argument("--skip-latency",   action="store_true", help="Skip multi-turn latency suite")
    parser.add_argument("-n", "--repeats", type=int, default=2,
                        help="Repetitions per test (default: 2)")
    parser.add_argument("--output", default=str(RESULTS_DEFAULT),
                        metavar="FILE", help="JSON file to append results to")
    parser.add_argument("--compare", nargs="+", metavar="FILE",
                        help="Compare results from one or more JSON files, then exit")
    args = parser.parse_args()

    if args.compare:
        compare_report(args.compare)
        return

    url = args.ollama_url or OLLAMA_URL
    models = args.ollama_models or [os.environ.get("OLLAMA_MODEL", "qwen2:0.5b")]
    n = args.repeats

    print(f"\n{'=' * 70}")
    print(f"💬 Conversation Benchmark  ·  target={args.target}  ·  n={n}")
    print(f"   Ollama: {url}  |  Models: {', '.join(models)}")
    print(f"{'=' * 70}")

    if not _ollama_check(url):
        print(f"\n⚠️  Ollama not reachable at {url} — marking all suites as unavailable")
        run_result: dict = {
            "target": args.target,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "sysinfo": _sys_info(),
            "ollama_url": url,
            "models": models,
            "results": [{"suite": s, "model": m, "ok": False, "error": "ollama_unavailable"}
                        for s in ["conversation_memory", "context_isolation",
                                  "response_quality", "conversation_multilang",
                                  "llm_latency_multiturn"]
                        for m in models],
        }
        out_path = Path(args.output)
        existing = _load_results(out_path)
        _save_results(out_path, existing + [run_result])
        print(f"\nResults saved to {out_path}")
        return

    _acquire_bench_lock()   # warn if another benchmark is already running

    all_results: list[dict] = []
    try:
        for model in models:
            print(f"\n── Model: {model} {'─' * 50}")

            if not args.skip_memory:
                print("\n🧠 conversation_memory …")
                all_results.extend(benchmark_conversation_memory(model, n, url))

            if not args.skip_isolation:
                print("\n🔒 context_isolation …")
                all_results.extend(benchmark_context_isolation(model, n, url))

            if not args.skip_quality:
                print("\n✅ response_quality …")
                all_results.extend(benchmark_response_quality(model, n, url))

            if not args.skip_multilang:
                print("\n🌍 conversation_multilang …")
                all_results.extend(benchmark_conversation_multilang(model, n, url))

            if not args.skip_latency:
                print("\n⚡ llm_latency_multiturn …")
                all_results.extend(benchmark_llm_latency_multiturn(model, n, url))

        sysinfo = _sys_info()
        run_result = {
            "target": args.target,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "sysinfo": sysinfo,
            "ollama_url": url,
            "models": models,
            "n_repeats": n,
            "results": all_results,
        }

        _print_run_report(run_result)

        out_path = Path(args.output)
        existing = _load_results(out_path)
        _save_results(out_path, existing + [run_result])
        print(f"\n  Results saved → {out_path}")
    finally:
        _release_bench_lock()


if __name__ == "__main__":
    main()
