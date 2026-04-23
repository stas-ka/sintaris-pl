#!/usr/bin/env python3
"""
bench_remote_kb.py — Remote Knowledge Base benchmark harness.

Measures Recall@5, MRR@10, and latency (p50/p95) for remote KB retrieval
across three strategies:
  (a) local Taris RAG (bot_rag.retrieve_context)
  (b) Remote KB via N8N MCP Server (bot_mcp_client.query_remote)
  (c) Google-grounded variant (if configured)

QA pairs loaded from src/tests/autoresearch_kb/qa_pairs.json:
  [{"question": "...", "relevant_doc_ids": ["...", ...], "answer": "..."}, ...]

Usage:
    python3 bench_remote_kb.py [--qa-file path] [--top-k 5] [--output-dir dir]
    python3 bench_remote_kb.py --strategy remote  # only remote
    python3 bench_remote_kb.py --strategy local   # only local RAG

Output:
    doc/research/bench-remote-kb-YYYY-MM-DD.md  (Markdown report)
    bench_remote_kb_YYYY-MM-DD.json             (raw results)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Path bootstrap ─────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_SRC  = _HERE.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

log = logging.getLogger("bench.remote_kb")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")

DEFAULT_QA_FILE   = _HERE / "autoresearch_kb" / "qa_pairs.json"
DEFAULT_OUTPUT    = Path("doc/research")
CHAT_ID_BENCH     = 0   # dummy chat_id for benchmark queries


# ─────────────────────────────────────────────────────────────────────────────
# Metrics helpers
# ─────────────────────────────────────────────────────────────────────────────

def _recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Recall@k: fraction of relevant docs found in top-k results."""
    if not relevant_ids:
        return 1.0
    hits = sum(1 for doc_id in retrieved_ids[:k] if doc_id in relevant_ids)
    return hits / len(relevant_ids)


def _reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """MRR: 1/rank of first relevant result, or 0."""
    for rank, doc_id in enumerate(retrieved_ids, 1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def _percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = max(0, int(len(s) * pct / 100) - 1)
    return s[idx]


# ─────────────────────────────────────────────────────────────────────────────
# Strategy runners
# ─────────────────────────────────────────────────────────────────────────────

def _run_remote(qa_pairs: list[dict], top_k: int) -> dict:
    """Run queries against remote N8N MCP KB."""
    import core.bot_mcp_client as _mcp

    recalls, mrrs, latencies = [], [], []
    errors = 0
    for qa in qa_pairs:
        q       = qa["question"]
        rel_ids = set(qa.get("relevant_doc_ids", []))
        t0 = time.perf_counter()
        try:
            chunks = _mcp.query_remote(q, chat_id=CHAT_ID_BENCH, top_k=top_k)
            dt = time.perf_counter() - t0
            retrieved = [c.get("doc_id", "") for c in chunks]
            recalls.append(_recall_at_k(retrieved, rel_ids, top_k))
            mrrs.append(_reciprocal_rank(retrieved, rel_ids))
            latencies.append(dt * 1000)  # ms
        except Exception as exc:
            log.warning("remote error on %r: %s", q[:60], exc)
            errors += 1
            latencies.append(0.0)

    return _aggregate("remote", recalls, mrrs, latencies, errors, len(qa_pairs))


def _run_local(qa_pairs: list[dict], top_k: int) -> dict:
    """Run queries against local Taris RAG."""
    try:
        from core.bot_rag import retrieve_context
    except ImportError as e:
        log.error("Cannot import bot_rag: %s", e)
        return _aggregate("local", [], [], [], len(qa_pairs), len(qa_pairs))

    recalls, mrrs, latencies = [], [], []
    errors = 0
    for qa in qa_pairs:
        q       = qa["question"]
        rel_ids = set(qa.get("relevant_doc_ids", []))
        t0 = time.perf_counter()
        try:
            chunks, _, _, _ = retrieve_context(CHAT_ID_BENCH, q, top_k=top_k)
            dt = time.perf_counter() - t0
            retrieved = [c.get("doc_id", "") for c in chunks]
            recalls.append(_recall_at_k(retrieved, rel_ids, top_k))
            mrrs.append(_reciprocal_rank(retrieved, rel_ids))
            latencies.append(dt * 1000)
        except Exception as exc:
            log.warning("local RAG error on %r: %s", q[:60], exc)
            errors += 1
            latencies.append(0.0)

    return _aggregate("local", recalls, mrrs, latencies, errors, len(qa_pairs))


def _aggregate(label: str, recalls: list, mrrs: list, latencies: list,
               errors: int, total: int) -> dict:
    n = len(recalls) or 1
    return {
        "strategy":   label,
        "n_queries":  total,
        "n_errors":   errors,
        "recall_at_k": round(statistics.mean(recalls) if recalls else 0.0, 4),
        "mrr":         round(statistics.mean(mrrs)    if mrrs    else 0.0, 4),
        "lat_p50_ms":  round(_percentile(latencies, 50),  1),
        "lat_p95_ms":  round(_percentile(latencies, 95),  1),
        "lat_mean_ms": round(statistics.mean(latencies) if latencies else 0.0, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────

def _md_report(results: list[dict], top_k: int, qa_file: str, date: str) -> str:
    lines = [
        f"# Remote KB Benchmark — {date}",
        "",
        f"- **QA pairs:** {results[0]['n_queries'] if results else 0}",
        f"- **Top-k:** {top_k}",
        f"- **QA file:** `{qa_file}`",
        "",
        "## Results",
        "",
        "| Strategy | Recall@{k} | MRR@10 | Lat p50 ms | Lat p95 ms | Errors |".format(k=top_k),
        "|----------|------------|--------|------------|------------|--------|",
    ]
    for r in results:
        lines.append(
            f"| {r['strategy']} | {r['recall_at_k']:.3f} | {r['mrr']:.3f} "
            f"| {r['lat_p50_ms']} | {r['lat_p95_ms']} | {r['n_errors']} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- **Recall@k**: fraction of relevant documents found in top-k results (higher = better).",
        "- **MRR**: mean reciprocal rank of first relevant hit (higher = better).",
        "- **Lat p50/p95**: retrieval latency percentiles in milliseconds.",
        "",
        "_Generated by `src/tests/bench_remote_kb.py`_",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Remote KB benchmark harness")
    parser.add_argument("--qa-file",   default=str(DEFAULT_QA_FILE), help="Path to qa_pairs.json")
    parser.add_argument("--top-k",     type=int, default=5,          help="Retrieval top-k (default 5)")
    parser.add_argument("--strategy",  choices=["local", "remote", "all"], default="all")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Directory for output files")
    args = parser.parse_args()

    qa_path = Path(args.qa_file)
    if not qa_path.exists():
        log.error("QA pairs file not found: %s", qa_path)
        sys.exit(2)

    qa_pairs = json.loads(qa_path.read_text())
    log.info("Loaded %d QA pairs from %s", len(qa_pairs), qa_path)

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    results: list[dict] = []

    if args.strategy in ("remote", "all"):
        log.info("Running remote KB strategy …")
        results.append(_run_remote(qa_pairs, args.top_k))
        log.info("remote: recall=%.3f  mrr=%.3f  p50=%sms",
                 results[-1]["recall_at_k"], results[-1]["mrr"], results[-1]["lat_p50_ms"])

    if args.strategy in ("local", "all"):
        log.info("Running local RAG strategy …")
        results.append(_run_local(qa_pairs, args.top_k))
        log.info("local:  recall=%.3f  mrr=%.3f  p50=%sms",
                 results[-1]["recall_at_k"], results[-1]["mrr"], results[-1]["lat_p50_ms"])

    # Write outputs
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"bench-remote-kb-{date_str}.json"
    json_path.write_text(json.dumps({"date": date_str, "top_k": args.top_k, "results": results}, indent=2))
    log.info("Raw results: %s", json_path)

    md_path = out_dir / f"bench-remote-kb-{date_str}.md"
    md_path.write_text(_md_report(results, args.top_k, str(qa_path), date_str))
    log.info("Report:      %s", md_path)

    # Print summary table to stdout
    print(_md_report(results, args.top_k, str(qa_path), date_str))


if __name__ == "__main__":
    main()
