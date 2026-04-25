#!/usr/bin/env python3
"""
evaluate.py — Run the Remote KB benchmark and compute rag_score.

rag_score formula (§12 of 4.3-remote-mcp-rag.md):
    rag_score = 0.5 * recall_at_k + 0.3 * mrr + 0.2 * (1 - lat_p95_ms / LAT_CEILING_MS)

Where LAT_CEILING_MS = 5000 (5 seconds is considered worst acceptable latency).

Usage:
    python3 evaluate.py [--strategy remote|local|all] [--top-k 5]
    python3 evaluate.py --compare  # compare remote vs local side-by-side
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC  = _HERE.parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Add tests/ to path for bench_remote_kb
_TESTS = _HERE.parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

QA_FILE        = _HERE / "qa_pairs.json"
LAT_CEILING_MS = 5000.0

# Weight parameters (tune via AutoResearch)
W_RECALL = 0.5
W_MRR    = 0.3
W_LAT    = 0.2


def rag_score(recall: float, mrr: float, lat_p95_ms: float) -> float:
    lat_score = max(0.0, 1.0 - lat_p95_ms / LAT_CEILING_MS)
    return W_RECALL * recall + W_MRR * mrr + W_LAT * lat_score


def _run_bench(strategy: str, top_k: int) -> list[dict]:
    from bench_remote_kb import _run_remote, _run_local
    qa_pairs = json.loads(QA_FILE.read_text(encoding="utf-8"))
    results = []
    if strategy in ("remote", "all"):
        results.append(_run_remote(qa_pairs, top_k))
    if strategy in ("local", "all"):
        results.append(_run_local(qa_pairs, top_k))
    return results


def _print_results(results: list[dict], top_k: int) -> None:
    print(f"\n{'Strategy':<10} {'Recall@'+str(top_k):<12} {'MRR':<8} {'p95ms':<10} {'rag_score':<12}")
    print("-" * 54)
    for r in results:
        score = rag_score(r["recall_at_k"], r["mrr"], r["lat_p95_ms"])
        print(
            f"{r['strategy']:<10} {r['recall_at_k']:<12.3f} {r['mrr']:<8.3f} "
            f"{r['lat_p95_ms']:<10.0f} {score:<12.3f}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Remote KB with rag_score")
    parser.add_argument("--strategy", choices=["local", "remote", "all"], default="all")
    parser.add_argument("--top-k",   type=int, default=5)
    parser.add_argument("--compare", action="store_true", help="Force all strategies")
    parser.add_argument("--json",    action="store_true", help="Output JSON only")
    args = parser.parse_args()

    strategy = "all" if args.compare else args.strategy
    results  = _run_bench(strategy, args.top_k)

    if args.json:
        payload = [
            {**r, "rag_score": round(rag_score(r["recall_at_k"], r["mrr"], r["lat_p95_ms"]), 4)}
            for r in results
        ]
        print(json.dumps(payload, indent=2))
    else:
        _print_results(results, args.top_k)

    # Return exit code 0 if best rag_score >= 0.5, else 1
    if results:
        best = max(rag_score(r["recall_at_k"], r["mrr"], r["lat_p95_ms"]) for r in results)
        sys.exit(0 if best >= 0.5 else 1)


if __name__ == "__main__":
    main()
