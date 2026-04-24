#!/usr/bin/env python3
"""
eval_kb_vs_worksafety.py — Compare taris KB (fastembed RAG) vs N8N Worksafety (Hybrid RAG)

Runs the same 10 worksafety test questions against both systems and prints a
side-by-side comparison table with answer quality indicators and timing.

Usage:
    python3 tools/eval_kb_vs_worksafety.py
    python3 tools/eval_kb_vs_worksafety.py --taris-chat-id 994963580
    python3 tools/eval_kb_vs_worksafety.py --out results_$(date +%Y%m%d).json

Requires:
    - .env with VPS_N8N_HOST and credentials
    - sshpass + access to mail.dev2null.de (taris VPS)
    - python3 stdlib only
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

_ENV = Path(__file__).resolve().parent.parent / ".env"

def _get_env(key: str, default: str = "") -> str:
    """Read a value from .env file (handles multi-line and comment lines)."""
    if not _ENV.exists():
        return os.environ.get(key, default)
    for line in _ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip()
    return os.environ.get(key, default)


N8N_HOST     = _get_env("VPS_N8N_HOST",   "https://automata.dev2null.de")
VPS_HOST     = _get_env("VPS_SSH_HOST",   "mail.dev2null.de")
VPS_USER     = _get_env("VPS_SSH_USER",   "stas")
VPS_PASS     = _get_env("VPS_SSH_PASS",   "Zusammen!2019")

# N8N worksafety endpoint (confirmed working: uses `query` field)
WORKSAFETY_URL = f"{N8N_HOST}/webhook/worksafety/query2"

# ── Test questions ─────────────────────────────────────────────────────────────
# Standard worksafety (охрана труда) questions typical for a Russian company.
# Designed to cover key knowledge areas so both systems are tested meaningfully.

TEST_QUESTIONS = [
    {
        "id": "WS-01",
        "question": "Какие средства индивидуальной защиты обязан выдавать работодатель?",
        "topic": "СИЗ / PPE",
        "keywords": ["СИЗ", "средства", "защиты", "выдавать", "работодатель"],
    },
    {
        "id": "WS-02",
        "question": "Каков порядок оформления наряда-допуска на опасные работы?",
        "topic": "Наряд-допуск",
        "keywords": ["наряд", "допуск", "порядок", "опасные", "оформление"],
    },
    {
        "id": "WS-03",
        "question": "Как часто нужно проводить инструктаж по охране труда?",
        "topic": "Инструктаж",
        "keywords": ["инструктаж", "проводить", "периодичность", "охрана", "труд"],
    },
    {
        "id": "WS-04",
        "question": "Что делать при несчастном случае на производстве?",
        "topic": "Несчастный случай",
        "keywords": ["несчастный", "случай", "производство", "действия", "оказать"],
    },
    {
        "id": "WS-05",
        "question": "Какие требования предъявляются к электробезопасности при работе с электроинструментом?",
        "topic": "Электробезопасность",
        "keywords": ["электробезопасность", "электроинструмент", "требования", "напряжение", "группа"],
    },
    {
        "id": "WS-06",
        "question": "Правила работы на высоте и использование страховочных систем",
        "topic": "Работа на высоте",
        "keywords": ["высота", "страховочный", "пояс", "правила", "работа"],
    },
    {
        "id": "WS-07",
        "question": "Как организовать безопасное проведение огневых работ?",
        "topic": "Огневые работы",
        "keywords": ["огневые", "работы", "пожарная", "безопасность", "разрешение"],
    },
    {
        "id": "WS-08",
        "question": "Требования к организации рабочего места и поддержанию порядка",
        "topic": "Рабочее место",
        "keywords": ["рабочее", "место", "порядок", "организация", "требования"],
    },
    {
        "id": "WS-09",
        "question": "Какова ответственность работника за нарушение правил охраны труда?",
        "topic": "Ответственность",
        "keywords": ["ответственность", "нарушение", "правила", "работник", "дисциплинарная"],
    },
    {
        "id": "WS-10",
        "question": "Порядок расследования и учёта несчастных случаев на производстве",
        "topic": "Расследование НС",
        "keywords": ["расследование", "учёт", "несчастный", "случай", "комиссия"],
    },
]


# ── System A: N8N Worksafety Hybrid RAG ──────────────────────────────────────

def query_n8n_worksafety(question: str, session_id: str) -> dict:
    """Call the N8N PROD2.0 Worksafety Hybrid RAG webhook."""
    payload = json.dumps({
        "query":      question,
        "session_id": session_id,
    }).encode()
    req = urllib.request.Request(
        WORKSAFETY_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
        elapsed = time.monotonic() - t0
        data = json.loads(raw)
        return {
            "answer":    data.get("answer", ""),
            "success":   data.get("success", False),
            "tokens":    data.get("tokens_used", 0),
            "model":     data.get("metadata", {}).get("model", "?"),
            "elapsed_s": round(elapsed, 2),
            "error":     None,
        }
    except Exception as exc:
        return {"answer": "", "success": False, "tokens": 0, "model": "?",
                "elapsed_s": round(time.monotonic() - t0, 2), "error": str(exc)}


# ── System B: Taris KB (fastembed + Ollama/OpenAI) ───────────────────────────

def query_taris_kb(question: str, chat_id: int) -> dict:
    """Call taris KB search via docker exec on the VPS container."""
    script = f"""
import sys; sys.path.insert(0, '/app')
import time, json
from core import bot_mcp_client as mcp
from core.bot_llm import ask_llm_with_history

t0 = time.monotonic()
chunks = mcp.query_remote({json.dumps(question)}, chat_id={chat_id}, top_k=5)
embed_ms = int((time.monotonic() - t0) * 1000)

if not chunks:
    print(json.dumps({{"answer":"", "chunks":0, "elapsed_s":round(time.monotonic()-t0,2), "error":"no chunks"}}))
    sys.exit(0)

# Build RAG context (same as bot_remote_kb._do_search)
context_parts = []
for i, c in enumerate(chunks[:5], 1):
    section = c.get("section") or ""
    text = (c.get("text") or "").strip()
    if text:
        context_parts.append(f"[{{i}}] {{section}}\\n{{text}}" if section else f"[{{i}}] {{text}}")
context = "\\n\\n".join(context_parts)

sys_msg = (
    "You are a helpful assistant. Answer the user question using ONLY the context excerpts below. "
    "If the answer is not in the context, say so clearly. Answer in Russian.\\n\\nContext:\\n" + context
)
messages = [{{"role":"system","content":sys_msg}},{{"role":"user","content":{json.dumps(question)}}}]

t1 = time.monotonic()
answer = ask_llm_with_history(messages, timeout=90, use_case="chat")
llm_ms = int((time.monotonic() - t1) * 1000)

print(json.dumps({{
    "answer": answer,
    "chunks": len(chunks),
    "top_score": round(chunks[0].get("score", 0), 3) if chunks else 0,
    "embed_ms": embed_ms,
    "llm_ms": llm_ms,
    "elapsed_s": round(time.monotonic()-t0, 2),
    "error": None,
}}))
"""
    # Pipe the script via stdin to avoid shell quoting / newline escaping issues
    cmd = [
        "sshpass", "-p", VPS_PASS,
        "ssh", "-o", "StrictHostKeyChecking=no",
        f"{VPS_USER}@{VPS_HOST}",
        "docker exec -i taris-vps-telegram python3 -"
    ]
    t0 = time.monotonic()
    try:
        result = subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=120)
        elapsed = time.monotonic() - t0
        stdout = result.stdout.strip()
        # Find the JSON line (last non-empty line)
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                data = json.loads(line)
                data["elapsed_s"] = round(elapsed, 2)
                return data
        return {"answer": "", "chunks": 0, "elapsed_s": round(elapsed, 2),
                "error": f"no json output: {stdout[-200:]!r}"}
    except subprocess.TimeoutExpired:
        return {"answer": "", "chunks": 0, "elapsed_s": 120, "error": "timeout"}
    except Exception as exc:
        return {"answer": "", "chunks": 0, "elapsed_s": round(time.monotonic() - t0, 2), "error": str(exc)}


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_answer(answer: str, keywords: list[str]) -> dict:
    """Simple keyword recall + length scoring (no LLM judge needed)."""
    if not answer:
        return {"keyword_recall": 0.0, "length": 0, "has_content": False}
    ans_lower = answer.lower()
    matched = sum(1 for kw in keywords if kw.lower() in ans_lower)
    return {
        "keyword_recall": round(matched / len(keywords), 2) if keywords else 0.0,
        "length":         len(answer),
        "has_content":    len(answer.strip()) > 50,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run_evaluation(chat_id: int, out_path: str | None = None, questions: list | None = None) -> None:
    if questions is None:
        questions = TEST_QUESTIONS
    print(f"\n{'='*80}")
    print(f"  KB Quality Evaluation — taris vs N8N Worksafety Hybrid RAG")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}  |  chat_id: {chat_id}")
    print(f"  Worksafety endpoint: {WORKSAFETY_URL}")
    print(f"{'='*80}\n")

    results = []

    for q in questions:
        qid  = q["id"]
        text = q["question"]
        kw   = q["keywords"]

        print(f"[{qid}] {q['topic']}")
        print(f"  Q: {text}")

        # Run both in sequence (rate-limiting friendly)
        print("  → querying N8N worksafety...", end=" ", flush=True)
        n8n = query_n8n_worksafety(text, f"eval-{qid}")
        print(f"done ({n8n['elapsed_s']}s)")

        print("  → querying taris KB...", end=" ", flush=True)
        taris = query_taris_kb(text, chat_id)
        print(f"done ({taris['elapsed_s']}s)")

        n8n_score   = score_answer(n8n["answer"],   kw)
        taris_score = score_answer(taris["answer"], kw)

        row = {
            "id":      qid,
            "topic":   q["topic"],
            "question": text,
            "n8n": {
                "answer":          n8n["answer"],
                "elapsed_s":       n8n["elapsed_s"],
                "tokens":          n8n.get("tokens", 0),
                "model":           n8n.get("model", "?"),
                "error":           n8n.get("error"),
                "keyword_recall":  n8n_score["keyword_recall"],
                "length":          n8n_score["length"],
                "has_content":     n8n_score["has_content"],
            },
            "taris": {
                "answer":          taris.get("answer", ""),
                "elapsed_s":       taris["elapsed_s"],
                "chunks":          taris.get("chunks", 0),
                "top_score":       taris.get("top_score", 0),
                "error":           taris.get("error"),
                "keyword_recall":  taris_score["keyword_recall"],
                "length":          taris_score["length"],
                "has_content":     taris_score["has_content"],
            },
        }
        results.append(row)

        # Print brief comparison
        n8n_kw   = n8n_score["keyword_recall"]
        taris_kw = taris_score["keyword_recall"]
        n8n_ok   = "✅" if n8n_score["has_content"]   else "❌"
        taris_ok = "✅" if taris_score["has_content"]  else "❌"
        print(f"  N8N  {n8n_ok}  recall={n8n_kw:.0%}  len={n8n_score['length']:4d}  {n8n['elapsed_s']}s  model={n8n.get('model','?')}")
        if n8n.get("error"):
            print(f"       error: {n8n['error']}")
        print(f"  taris{taris_ok}  recall={taris_kw:.0%}  len={taris_score['length']:4d}  {taris['elapsed_s']}s  chunks={taris.get('chunks',0)}  score={taris.get('top_score',0)}")
        if taris.get("error"):
            print(f"       error: {taris['error']}")
        print()

    # ── Summary table ──────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("  SUMMARY")
    print(f"{'='*80}")
    print(f"  {'ID':<8} {'Topic':<20} {'N8N recall':>10} {'Taris recall':>12} {'N8N len':>8} {'Taris len':>10} {'Winner':>8}")
    print(f"  {'-'*8} {'-'*20} {'-'*10} {'-'*12} {'-'*8} {'-'*10} {'-'*8}")

    n8n_wins = taris_wins = ties = 0
    for r in results:
        nk = r["n8n"]["keyword_recall"]
        tk = r["taris"]["keyword_recall"]
        if nk > tk:
            winner = "N8N"
            n8n_wins += 1
        elif tk > nk:
            winner = "taris"
            taris_wins += 1
        else:
            winner = "tie"
            ties += 1
        print(f"  {r['id']:<8} {r['topic']:<20} {nk:>10.0%} {tk:>12.0%} {r['n8n']['length']:>8} {r['taris']['length']:>10} {winner:>8}")

    print(f"\n  Results: N8N wins={n8n_wins}  taris wins={taris_wins}  ties={ties}")

    n8n_avg_recall   = sum(r["n8n"]["keyword_recall"]   for r in results) / len(results)
    taris_avg_recall = sum(r["taris"]["keyword_recall"] for r in results) / len(results)
    n8n_avg_len      = sum(r["n8n"]["length"]   for r in results) / len(results)
    taris_avg_len    = sum(r["taris"]["length"] for r in results) / len(results)
    n8n_content_ok   = sum(1 for r in results if r["n8n"]["has_content"])
    taris_content_ok = sum(1 for r in results if r["taris"]["has_content"])
    n8n_avg_time     = sum(r["n8n"]["elapsed_s"]   for r in results) / len(results)
    taris_avg_time   = sum(r["taris"]["elapsed_s"] for r in results) / len(results)

    print(f"\n  Avg keyword recall:  N8N={n8n_avg_recall:.0%}  taris={taris_avg_recall:.0%}")
    print(f"  Avg answer length:   N8N={n8n_avg_len:.0f}  taris={taris_avg_len:.0f} chars")
    print(f"  Answers with content: N8N={n8n_content_ok}/{len(results)}  taris={taris_content_ok}/{len(results)}")
    print(f"  Avg response time:   N8N={n8n_avg_time:.1f}s  taris={taris_avg_time:.1f}s")

    # ── Diagnosis ─────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("  DIAGNOSIS")
    print(f"{'='*80}")
    if taris_content_ok == 0:
        print("  ⚠️  taris KB returned no content for ANY question.")
        print("     → KB is empty for this chat_id. Upload the 5 RTF documents and re-run.")
    elif taris_avg_recall < 0.3:
        print("  ⚠️  taris KB recall is low. Possible causes:")
        print("     • Documents not yet chunked/embedded (check kb_chunks table)")
        print("     • Embedding model mismatch (check vector_dims vs fastembed dim=384)")
        print("     • LLM not answering from context (check OLLAMA_URL / LLM_PROVIDER)")
    else:
        print(f"  ✅  taris KB is answering. Recall {taris_avg_recall:.0%} vs N8N {n8n_avg_recall:.0%}.")
        if taris_avg_recall < n8n_avg_recall - 0.1:
            print("     Gap likely due to smaller KB content. Upload more documents to improve.")

    # ── Save JSON ─────────────────────────────────────────────────────────────
    report = {
        "date":        datetime.now().isoformat(),
        "chat_id":     chat_id,
        "n8n_url":     WORKSAFETY_URL,
        "summary": {
            "n8n_wins": n8n_wins, "taris_wins": taris_wins, "ties": ties,
            "n8n_avg_recall": round(n8n_avg_recall, 3),
            "taris_avg_recall": round(taris_avg_recall, 3),
            "n8n_avg_len": round(n8n_avg_len),
            "taris_avg_len": round(taris_avg_len),
            "n8n_content_ok": n8n_content_ok,
            "taris_content_ok": taris_content_ok,
            "n8n_avg_time_s": round(n8n_avg_time, 2),
            "taris_avg_time_s": round(taris_avg_time, 2),
        },
        "results": results,
    }
    if out_path:
        Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\n  Full results saved to: {out_path}")
    else:
        default = Path(__file__).parent / f"eval_kb_results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        default.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\n  Full results saved to: {default}")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate taris KB vs N8N Worksafety RAG")
    parser.add_argument("--taris-chat-id", type=int, default=994963580,
                        help="Telegram chat_id whose KB documents to search (default: 994963580)")
    parser.add_argument("--out", default=None,
                        help="Path to write JSON results (default: tools/eval_kb_results_YYYYMMDD_HHMM.json)")
    parser.add_argument("--questions", nargs="*",
                        help="Run only specific question IDs, e.g. --questions WS-01 WS-03")
    args = parser.parse_args()

    questions = TEST_QUESTIONS
    if args.questions:
        questions = [q for q in TEST_QUESTIONS if q["id"] in args.questions]
        if not questions:
            print(f"No matching questions for: {args.questions}")
            sys.exit(1)

    run_evaluation(chat_id=args.taris_chat_id, out_path=args.out, questions=questions)
