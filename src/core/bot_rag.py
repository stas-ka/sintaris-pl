"""
bot_rag.py — Adaptive RAG retrieval: classify_query, RRF fusion, hardware-tier detection.

Architecture:
  classify_query()       → decide retrieval strategy (simple / factual / contextual)
  reciprocal_rank_fusion() → combine FTS5 + vector results (RRF, k=60)
  retrieve_context()     → unified entry point used by bot_access._docs_rag_context()
  detect_rag_capability() → FTS5_ONLY | HYBRID | FULL at startup

Designed for graceful degradation:
  Pi 3 (512 MB)  → FTS5_ONLY  (no vector search)
  Pi 5 / OpenClaw → HYBRID    (FTS5 + vector)
  Server          → FULL      (hybrid + semantic reranking)
"""

from __future__ import annotations

import time
from enum import Enum

from core.bot_config import (
    RAG_TOP_K, RAG_CHUNK_SIZE, log,
)

# ─── Query classification ─────────────────────────────────────────────────────

_GREETING_PATTERNS: frozenset[str] = frozenset({
    "привет", "hi", "hello", "hey", "hallo", "guten tag", "добрый день",
    "добрый вечер", "доброе утро", "ok", "ок", "да", "нет", "yes", "no",
    "спасибо", "thanks", "danke", "пожалуйста", "bitte", "please",
    "хорошо", "gut", "good", "bye", "пока", "tschüss",
})

_FACTUAL_KEYWORDS: tuple[str, ...] = (
    # Russian
    "что", "как", "когда", "где", "почему", "зачем", "кто", "сколько",
    "какой", "которых", "расскажи", "объясни", "найди", "покажи",
    # English
    "what", "how", "when", "where", "why", "who", "which", "how much",
    "explain", "find", "show", "tell", "describe", "list",
    # German
    "was", "wie", "wann", "wo", "warum", "wer", "welche", "welcher",
    "erkläre", "finde", "zeige", "liste",
)


def classify_query(user_text: str, has_documents: bool) -> str:
    """
    Decide retrieval strategy based on query type. Heuristic — no LLM call.

    Returns:
      "simple"     → skip RAG entirely (greeting, very short, yes/no)
      "factual"    → use RAG (question with factual indicator)
      "contextual" → use conversation history; RAG optional
    """
    text = user_text.strip()
    text_lower = text.lower()

    # Very short or greeting — no RAG needed
    if len(text) < 12 or text_lower in _GREETING_PATTERNS:
        return "simple"

    # Single-word or punctuation-only input
    words = text_lower.split()
    if len(words) <= 2 and not any(kw in text_lower for kw in _FACTUAL_KEYWORDS):
        return "simple"

    # Factual question — use RAG when docs are present
    if any(kw in text_lower for kw in _FACTUAL_KEYWORDS):
        return "factual" if has_documents else "contextual"

    # Default: use conversation history; include RAG if docs available
    return "contextual"


# ─── Hardware-tier detection ──────────────────────────────────────────────────

class RAGCapability(str, Enum):
    FTS5_ONLY = "fts5"      # Pi 3 / Pi Zero — keyword search only
    HYBRID    = "hybrid"    # Pi 5 / OpenClaw — FTS5 + vector
    FULL      = "full"      # Server / GPU — hybrid + semantic reranking


_detected_capability: RAGCapability | None = None


def detect_rag_capability() -> RAGCapability:
    """
    Auto-detect hardware tier for RAG configuration.
    Result is cached after first call.
    """
    global _detected_capability
    if _detected_capability is not None:
        return _detected_capability

    try:
        from core.store import store
        has_vectors = store.has_vector_search()
    except Exception:
        has_vectors = False

    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        # psutil not installed — fall back to /proc/meminfo (Linux)
        ram_gb = 0.0
        try:
            with open("/proc/meminfo") as _f:
                for _line in _f:
                    if "MemTotal" in _line:
                        ram_gb = int(_line.split()[1]) / (1024 * 1024)
                        break
        except Exception:
            pass

    if ram_gb >= 8.0 and has_vectors:
        cap = RAGCapability.FULL
    elif ram_gb >= 4.0 and has_vectors:
        cap = RAGCapability.HYBRID
    else:
        cap = RAGCapability.FTS5_ONLY

    _detected_capability = cap
    log.info("[RAG] capability detected: %s (RAM=%.1f GB, vectors=%s)", cap.value, ram_gb, has_vectors)
    return cap


# ─── RRF fusion ───────────────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    fts5_results: list[dict],
    vector_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    Combine FTS5 and vector search results using Reciprocal Rank Fusion.

    RRF score = Σ 1 / (k + rank)  for each list the chunk appears in.
    Higher score = better combined rank.

    Args:
        fts5_results:   list of chunk dicts (must have 'doc_id' and 'chunk_idx' keys)
        vector_results: list of chunk dicts (same format)
        k:              RRF constant (default 60, as per Cormack et al. 2009)

    Returns:
        Merged list of chunk dicts sorted by fused score (best first).
        Each dict gets an extra '_rrf_score' key.
    """
    # Build chunk lookup by (doc_id, chunk_idx) key
    chunk_map: dict[tuple, dict] = {}
    scores: dict[tuple, float] = {}

    def _key(chunk: dict) -> tuple:
        return (chunk.get("doc_id", ""), chunk.get("chunk_idx", 0))

    for rank, chunk in enumerate(fts5_results):
        ck = _key(chunk)
        scores[ck] = scores.get(ck, 0.0) + 1.0 / (k + rank + 1)
        chunk_map[ck] = chunk

    for rank, chunk in enumerate(vector_results):
        ck = _key(chunk)
        scores[ck] = scores.get(ck, 0.0) + 1.0 / (k + rank + 1)
        if ck not in chunk_map:
            chunk_map[ck] = chunk

    # Sort by fused score descending
    sorted_keys = sorted(scores.keys(), key=lambda ck: scores[ck], reverse=True)
    result = []
    for ck in sorted_keys:
        c = dict(chunk_map[ck])
        c["_rrf_score"] = round(scores[ck], 6)
        result.append(c)
    return result


# ─── Unified retrieval entry point ───────────────────────────────────────────

def retrieve_context(
    chat_id: int,
    query: str,
    top_k: int | None = None,
    max_chars: int = 2000,
) -> tuple[list[dict], str, str, dict]:
    """
    Unified RAG retrieval with adaptive routing + RRF fusion.

    Returns:
        (chunks, assembled_text, strategy_used, trace)
        strategy_used: "skipped" | "fts5" | "hybrid" | "hybrid+mcp" | "fts5+mcp" | "empty"
        trace: {n_fts5, n_vector, n_mcp, latency_ms, cap} for monitoring
    """
    _EMPTY: tuple[list[dict], str, str, dict] = ([], "", "skipped", {})

    if top_k is None:
        top_k = RAG_TOP_K

    from core.store import store

    # 1. Classify query
    try:
        has_docs = bool(store.list_documents(chat_id))
    except Exception:
        has_docs = False

    strategy = classify_query(query, has_docs)
    if strategy == "simple" or not has_docs:
        return [], "", "skipped", {"n_fts5": 0, "n_vector": 0, "n_mcp": 0, "latency_ms": 0}

    cap = detect_rag_capability()
    t0 = time.monotonic()

    # 2. FTS5 search (always available)
    try:
        fts5_results = store.search_fts(query, chat_id, top_k * 2) or []
    except Exception as exc:
        log.warning("[RAG] FTS5 search failed: %s", exc)
        fts5_results = []

    # 3. Vector search (when capability allows)
    vector_results: list[dict] = []
    if cap in (RAGCapability.HYBRID, RAGCapability.FULL):
        try:
            from core.bot_embeddings import EmbeddingService
            svc = EmbeddingService.get()
            if svc is not None:
                vec = svc.embed(query)
                if vec:
                    vector_results = store.search_similar(vec, chat_id, top_k * 2) or []
        except Exception as exc:
            log.debug("[RAG] vector search failed (non-fatal): %s", exc)

    # 4. Fuse or return FTS5-only
    n_fts5 = len(fts5_results)
    n_vector = len(vector_results)
    if vector_results:
        chunks = reciprocal_rank_fusion(fts5_results, vector_results)[:top_k]
        used_strategy = "hybrid"
    else:
        chunks = fts5_results[:top_k]
        used_strategy = "fts5"

    # 5. Optional: merge remote MCP chunks (Phase D)
    n_mcp = 0
    try:
        from core.bot_config import MCP_REMOTE_URL
        if MCP_REMOTE_URL:
            from core.bot_mcp_client import query_remote
            remote_chunks = query_remote(query, chat_id, top_k)
            if remote_chunks:
                n_mcp = len(remote_chunks)
                chunks = reciprocal_rank_fusion(chunks, remote_chunks)[:top_k]
                used_strategy = used_strategy + "+mcp"
                log.debug("[RAG] merged %d remote MCP chunks", n_mcp)
    except Exception as exc:
        log.debug("[RAG] MCP merge skipped: %s", exc)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    log.debug("[RAG] strategy=%s fts5=%d vec=%d mcp=%d final=%d elapsed=%dms",
              used_strategy, n_fts5, n_vector, n_mcp, len(chunks), elapsed_ms)

    trace = {"n_fts5": n_fts5, "n_vector": n_vector, "n_mcp": n_mcp,
             "latency_ms": elapsed_ms, "cap": cap.value}

    if not chunks:
        return [], "", "empty", trace

    # 6. Assemble context text
    parts = []
    total = 0
    for c in chunks:
        text = c.get("chunk_text") or c.get("content") or ""
        if not text:
            continue
        if total + len(text) > max_chars:
            text = text[: max_chars - total]
        parts.append(text.strip())
        total += len(text)
        if total >= max_chars:
            break

    assembled = "\n---\n".join(parts)
    return chunks, assembled, used_strategy, trace
