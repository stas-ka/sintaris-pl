#!/usr/bin/env python3
"""
prepare.py — Prepare the Remote KB benchmark corpus.

Downloads or copies source documents into the local knowledge base
so that bench_remote_kb.py can measure recall against known documents.

Usage:
    python3 prepare.py [--ingest] [--qa-file path]

Steps:
    1. Verify qa_pairs.json exists and has ≥1 entry.
    2. If --ingest: upload sample documents to remote KB via bot_mcp_client.ingest_file().
    3. Print corpus stats (n_questions by language/category).

This script does NOT create questions — edit qa_pairs.json manually to add
ground-truth relevant_doc_ids after ingesting documents.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC  = _HERE.parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

QA_FILE = _HERE / "qa_pairs.json"
DOCS_DIR = _HERE / "docs"


def _stats(qa_pairs: list[dict]) -> None:
    lang_count = Counter(q.get("language", "?") for q in qa_pairs)
    cat_count  = Counter(q.get("category", "?") for q in qa_pairs)
    n_with_ids = sum(1 for q in qa_pairs if q.get("relevant_doc_ids"))
    print(f"\n📊 QA Pairs: {len(qa_pairs)}")
    print(f"   With relevant_doc_ids: {n_with_ids}")
    print(f"   By language: {dict(lang_count)}")
    print(f"   By category: {dict(cat_count)}\n")


def _ingest_docs(qa_pairs: list[dict]) -> None:
    """Ingest documents from docs/ directory into remote KB."""
    import core.bot_mcp_client as _mcp

    if not DOCS_DIR.exists():
        print(f"⚠️  docs/ directory not found at {DOCS_DIR}. Create it and add source documents.")
        return

    docs = list(DOCS_DIR.glob("*"))
    if not docs:
        print("⚠️  No documents found in docs/. Add PDF, DOCX, TXT, or MD files.")
        return

    print(f"📤 Ingesting {len(docs)} document(s) …")
    for doc_path in docs:
        ext  = doc_path.suffix.lower()
        mime_map = {
            ".pdf":  "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt":  "text/plain",
            ".md":   "text/markdown",
            ".csv":  "text/csv",
        }
        mime = mime_map.get(ext, "application/octet-stream")
        data = doc_path.read_bytes()
        try:
            result = _mcp.ingest_file(0, doc_path.name, data, mime)
            doc_id  = result.get("doc_id", "?")
            n_chunks = result.get("n_chunks", "?")
            print(f"  ✅ {doc_path.name} → doc_id={doc_id}  chunks={n_chunks}")
            print(f"     → Update qa_pairs.json: add \"{doc_id}\" to relevant_doc_ids for related questions.")
        except Exception as exc:
            print(f"  ❌ {doc_path.name}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Remote KB benchmark corpus")
    parser.add_argument("--ingest",  action="store_true", help="Ingest docs/ into remote KB")
    parser.add_argument("--qa-file", default=str(QA_FILE), help="Path to qa_pairs.json")
    args = parser.parse_args()

    qa_path = Path(args.qa_file)
    if not qa_path.exists():
        print(f"❌ QA file not found: {qa_path}")
        sys.exit(2)

    qa_pairs = json.loads(qa_path.read_text(encoding="utf-8"))
    _stats(qa_pairs)

    if args.ingest:
        _ingest_docs(qa_pairs)


if __name__ == "__main__":
    main()
