#!/usr/bin/env python3
"""
load_system_docs.py — Load Taris system documentation into the knowledge base.

Two "virtual" knowledge sources are created as shared documents owned by
the system user (chat_id = 0):

  1. taris_user_guide   — doc/howto_bot.md: usage for regular users
  2. taris_admin_guide  — README.md + architecture/overview.md: full technical
                          reference for admins (architecture, hardware, config)

Documents are marked is_shared=1 so ALL users get them in RAG context.
Run once after deployment, or re-run to refresh after doc updates.

Usage:
    python3 src/setup/load_system_docs.py [--force]

    --force   Re-load even if system docs already exist (for updates)
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import uuid
from pathlib import Path

# Add src/ to path when run standalone
sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("load_system_docs")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# Chat ID 0 = system; all users see is_shared docs
SYSTEM_CHAT_ID = 0

# Source files relative to repo root (or ~/.taris/ if deployed)
_THIS_DIR = Path(__file__).parent
_REPO_ROOT = _THIS_DIR.parent.parent   # sintaris-pl/
_TARIS_HOME = Path.home() / ".taris"

def _resolve_doc(rel_path: str) -> Path | None:
    """Find a doc file — prefer repo root, fall back to ~/.taris/."""
    for base in (_REPO_ROOT, _TARIS_HOME):
        p = base / rel_path
        if p.exists():
            return p
    return None


def _load_docs(force: bool = False) -> None:
    from core.store import store

    # Collect source content
    sources: list[tuple[str, str, str]] = []  # (doc_id_tag, title, text)

    # --- User guide: howto_bot.md ---
    howto = _resolve_doc("doc/howto_bot.md")
    if howto:
        text = howto.read_text(encoding="utf-8")
        sources.append(("taris_user_guide", "📖 Taris — User Guide", text))
        log.info("Found user guide: %s (%d chars)", howto, len(text))
    else:
        log.warning("howto_bot.md not found — skipping user guide")

    # --- Admin guide: README + architecture overview ---
    readme = _resolve_doc("README.md")
    overview = _resolve_doc("doc/architecture/overview.md")
    admin_parts = []
    if readme:
        admin_parts.append(f"# Taris README\n\n{readme.read_text(encoding='utf-8')}")
        log.info("Found README: %s", readme)
    if overview:
        admin_parts.append(f"# Architecture Overview\n\n{overview.read_text(encoding='utf-8')}")
        log.info("Found overview: %s", overview)
    if admin_parts:
        admin_text = "\n\n---\n\n".join(admin_parts)
        sources.append(("taris_admin_guide", "🔧 Taris — Admin & Technical Guide", admin_text))

    if not sources:
        log.error("No source documents found — nothing loaded")
        sys.exit(1)

    for tag, title, text in sources:
        _ingest(store, tag, title, text, force)

    log.info("System docs loaded. Run once or with --force to refresh after doc updates.")


def _ingest(store, tag: str, title: str, text: str, force: bool) -> None:
    """Chunk, embed, and store a system document."""
    doc_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    # Use a stable doc_id based on tag so re-runs are idempotent
    doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"taris.system.{tag}"))

    # Check if already loaded with same hash
    existing = store.get_document_by_hash(SYSTEM_CHAT_ID, doc_hash)
    if existing and not force:
        log.info("  [%s] already up-to-date (hash=%s) — skip. Use --force to refresh.", tag, doc_hash)
        return

    # Clean up old version
    try:
        store.delete_text_chunks(doc_id)
        store.delete_embeddings(doc_id)
        store.delete_document(doc_id)
    except Exception:
        pass

    # Chunk
    chunk_size = 512
    chunk_overlap = 64
    chunks, skipped = _chunk(text, chunk_size, chunk_overlap)
    log.info("  [%s] %d chunks (%d skipped)", tag, len(chunks), skipped)

    # Store metadata
    store.save_document_meta(
        doc_id=doc_id,
        chat_id=SYSTEM_CHAT_ID,
        title=title,
        file_path=f"system:{tag}",
        doc_type="system",
        doc_hash=doc_hash,
        metadata={"tag": tag, "n_chunks": len(chunks), "system": True},
    )
    # Mark shared immediately
    try:
        store.update_document_field(doc_id, is_shared=1)
    except Exception as e:
        log.warning("  [%s] could not mark is_shared: %s", tag, e)

    # Store FTS5 chunks
    for idx, chunk in enumerate(chunks):
        store.upsert_chunk_text(doc_id, idx, SYSTEM_CHAT_ID, chunk)

    # Store vector embeddings if available
    n_embedded = 0
    if store.has_vector_search():
        try:
            from core.bot_embeddings import EmbeddingService
            svc = EmbeddingService.get()
            if svc is not None:
                vecs = svc.embed_batch(chunks)
                if vecs:
                    for idx, vec in enumerate(vecs):
                        store.upsert_embedding(doc_id, idx, SYSTEM_CHAT_ID, chunks[idx], vec)
                    n_embedded = len(vecs)
                    log.info("  [%s] %d embeddings stored", tag, n_embedded)
        except Exception as exc:
            log.warning("  [%s] embedding failed: %s", tag, exc)

    log.info("  [%s] '%s' loaded — %d chunks, %d embedded", tag, title, len(chunks), n_embedded)


def _chunk(text: str, size: int = 512, overlap: int = 64) -> tuple[list[str], int]:
    """Simple sentence-boundary chunker, mirrors bot_documents._chunk_text logic."""
    MIN_CHARS = 20
    import re
    sentences = re.split(r"(?<=[.!?\n])\s+", text)
    chunks: list[str] = []
    skipped = 0
    current = ""
    for sent in sentences:
        if len(current) + len(sent) <= size:
            current = (current + " " + sent).strip()
        else:
            if len(current.strip()) >= MIN_CHARS:
                chunks.append(current.strip())
            else:
                skipped += 1
            # overlap: carry last `overlap` chars into new chunk
            current = (current[-overlap:] + " " + sent).strip() if overlap else sent
    if current.strip() and len(current.strip()) >= MIN_CHARS:
        chunks.append(current.strip())
    elif current.strip():
        skipped += 1
    return chunks, skipped


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load Taris system docs into KB")
    parser.add_argument("--force", action="store_true",
                        help="Re-load even if already present")
    args = parser.parse_args()
    _load_docs(force=args.force)
