#!/usr/bin/env python3
"""
migrate_reembed.py — Generate vector embeddings for all existing document chunks.

Run this once after deploying the embedding pipeline fix (v2026.4.2).
Iterates all rows in doc_chunks that have no corresponding entry in
vec_embeddings, generates 384-dim fastembed embeddings, and upserts them.

Requirements:
  - sqlite-vec installed: pip install sqlite-vec
  - fastembed installed:  pip install fastembed

Usage:
    python3 src/setup/migrate_reembed.py [--dry-run] [--chat-id CHAT_ID]

    --dry-run      Show what would be done without writing anything
    --chat-id N    Only process chunks for this chat_id
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("migrate_reembed")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

BATCH_SIZE = 32   # chunks per embedding batch (fastembed handles batches efficiently)


def _migrate(dry_run: bool = False, chat_id_filter: int | None = None) -> None:
    from core.store import store

    if not store.has_vector_search():
        log.error("sqlite-vec not available — cannot generate vector embeddings.")
        log.error("Install with: pip install sqlite-vec")
        sys.exit(1)

    # Load embedding service
    try:
        from core.bot_embeddings import EmbeddingService
        svc = EmbeddingService.get()
        if svc is None:
            log.error("EmbeddingService unavailable (fastembed not installed?).")
            sys.exit(1)
        log.info("Embedding backend: %s  dim=%d", svc.backend, svc.dimension)
    except Exception as exc:
        log.error("Could not load EmbeddingService: %s", exc)
        sys.exit(1)


    # Use store API method (works for both SQLite + Postgres)
    log.info("Loading chunks without embeddings…")
    rows_raw = store.get_chunks_without_embeddings(chat_id_filter=chat_id_filter)
    rows = [(r["doc_id"], r["chunk_idx"], r["chat_id"], r["chunk_text"]) for r in rows_raw]

    total = len(rows)
    log.info("Chunks needing embeddings: %d", total)
    if total == 0:
        log.info("Nothing to do — all chunks already embedded.")
        return
    if dry_run:
        log.info("[DRY RUN] Would embed %d chunks across %d distinct docs.",
                 total, len({r[0] for r in rows}))
        return

    # Process in batches
    processed = 0
    errors = 0
    t_start = time.monotonic()

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start : batch_start + BATCH_SIZE]
        texts = [r[3] for r in batch]  # chunk_text

        try:
            vecs = svc.embed_batch(texts)
        except Exception as exc:
            log.warning("  embed_batch failed at offset %d: %s", batch_start, exc)
            errors += len(batch)
            continue

        if not vecs or len(vecs) != len(batch):
            log.warning("  unexpected vec count at offset %d: got %s", batch_start, len(vecs) if vecs else 0)
            errors += len(batch)
            continue

        for (doc_id, chunk_idx, chat_id, chunk_text), vec in zip(batch, vecs):
            try:
                store.upsert_embedding(
                    doc_id, int(chunk_idx), int(chat_id),
                    chunk_text, vec,
                )
                processed += 1
            except Exception as exc:
                log.warning("  upsert failed doc=%s chunk=%s: %s", doc_id, chunk_idx, exc)
                errors += 1

        elapsed = time.monotonic() - t_start
        rate = processed / elapsed if elapsed > 0 else 0
        log.info("  Progress: %d/%d embedded  (%.1f chunks/s, %d errors)",
                 processed, total, rate, errors)

    elapsed = time.monotonic() - t_start
    log.info("Done: %d embedded, %d errors in %.1fs", processed, errors, elapsed)

    # Summary via store API (works for SQLite + Postgres)
    try:
        stats = store.rag_stats(chat_id=chat_id_filter or 0)
        log.info("vec_embeddings total: %d", stats.get("total_vector", 0))
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-embed all doc_chunks without vectors")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without writing")
    parser.add_argument("--chat-id", type=int, default=None,
                        help="Only process this chat_id")
    args = parser.parse_args()
    _migrate(dry_run=args.dry_run, chat_id_filter=args.chat_id)
