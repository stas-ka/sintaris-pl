"""
bot_mcp_client.py — Remote KB client: direct PostgreSQL + N8N ingest webhook.

Provides list, search (via pgvector), and delete for the KB document store,
bypassing N8N MCP SSE (incompatible with the Python mcp client library due to
N8N's non-standard SSE session protocol). File ingestion still uses the N8N
Ingest Webhook (multipart POST).

When KB_PG_DSN is set (preferred on VPS-Supertaris):
  • list_documents  → direct SELECT on kb_documents
  • delete_document → direct DELETE on kb_documents/kb_chunks
  • search (RAG)    → Ollama embedding + pgvector cosine search on kb_chunks

When KB_PG_DSN is not set, falls back to N8N MCP Server SSE calls.

Circuit breaker (MCP SSE path only):
  After 3 consecutive failures the client stops calling the remote for
  MCP_CB_RESET_SEC seconds (default 300 = 5 min), then retries once.

Configuration (via bot.env / environment):
  KB_PG_DSN        — PostgreSQL DSN for taris_kb DB (direct path, preferred)
                     e.g. postgresql://taris:pw@127.0.0.1:5432/taris_kb
  MCP_REMOTE_URL   — N8N MCP Server SSE endpoint (fallback if KB_PG_DSN empty)
  N8N_KB_API_KEY   — N8N API key sent as X-N8N-API-Key header
  N8N_KB_TOKEN     — Bearer token for the N8N ingest webhook (file upload)
  MCP_TIMEOUT      — per-request timeout in seconds (default 15)
  MCP_REMOTE_TOP_K — max chunks to request from kb_search (default 3)

Requires: psycopg>=3, mcp>=1.2.0, httpx>=0.27.0, httpx-sse>=0.4.0
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json as _json
import logging
import threading
import time
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

# ─── circuit-breaker state (module-level singleton) ─────────────────────────
_CB_THRESHOLD  = 3       # failures before opening
_CB_RESET_SEC  = 300     # seconds to wait before retrying
_cb_lock       = threading.Lock()
_cb_failures   = 0
_cb_open_until = 0.0     # monotonic epoch; 0 = closed
# ─────────────────────────────────────────────────────────────────────────────


def _cb_record_success() -> None:
    global _cb_failures, _cb_open_until
    with _cb_lock:
        _cb_failures   = 0
        _cb_open_until = 0.0


def _cb_record_failure() -> None:
    global _cb_failures, _cb_open_until
    with _cb_lock:
        _cb_failures += 1
        if _cb_failures >= _CB_THRESHOLD:
            _cb_open_until = time.monotonic() + _CB_RESET_SEC
            log.warning("[MCP-client] circuit breaker OPEN for %ds after %d failures",
                        _CB_RESET_SEC, _cb_failures)


def _cb_is_open() -> bool:
    global _cb_open_until
    with _cb_lock:
        if _cb_open_until == 0.0:
            return False
        if time.monotonic() >= _cb_open_until:
            _cb_open_until = 0.0   # half-open: allow one probe
            return False
        return True


def _run_in_new_loop(coro) -> Any:
    """Run an async coroutine in a fresh event loop inside a worker thread.

    Using a ThreadPoolExecutor guarantees the thread has no existing event loop,
    so asyncio.run() never raises 'cannot run nested event loop'.
    This is safe whether the caller is sync or already in an async context.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


# ─── async implementation ─────────────────────────────────────────────────────

async def _kb_search_async(url: str, api_key: str, query: str,
                            chat_id: int, top_k: int, timeout: float) -> list[dict]:
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    headers = {}
    if api_key:
        headers["X-N8N-API-Key"] = api_key

    async with sse_client(url, headers=headers, timeout=timeout) as (r_stream, w_stream):
        async with ClientSession(r_stream, w_stream) as session:
            await session.initialize()
            result = await session.call_tool("kb_search", {
                "query":   query,
                "chat_id": chat_id,
                "top_k":   top_k,
            })
            # MCP tool result: list of TextContent items; each .text is a JSON string
            if not result.content:
                return []
            raw = result.content[0].text
            data = _json.loads(raw) if isinstance(raw, str) else raw
            chunks = data.get("chunks", []) if isinstance(data, dict) else []
            if not isinstance(chunks, list):
                raise ValueError(f"unexpected kb_search response: {type(data)}")
            return chunks


async def _kb_tool_async(url: str, api_key: str, tool: str,
                          args: dict, timeout: float) -> dict:
    """Generic MCP tool call — used for memory_*, list_documents, delete_document."""
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    headers = {"X-N8N-API-Key": api_key} if api_key else {}

    async with sse_client(url, headers=headers, timeout=timeout) as (r_stream, w_stream):
        async with ClientSession(r_stream, w_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            if not result.content:
                return {}
            raw = result.content[0].text
            return _json.loads(raw) if isinstance(raw, str) else (raw or {})


# ─── public sync API ──────────────────────────────────────────────────────────

def _load_config() -> tuple[str, str, str, int, int]:
    """Return (url, api_key, ingest_token, timeout, top_k) from config/system_settings."""
    from core.bot_config import MCP_REMOTE_URL, N8N_KB_API_KEY, N8N_KB_TOKEN, MCP_TIMEOUT, MCP_REMOTE_TOP_K
    try:
        from core.bot_db import db_get_system_setting as _gs
        url     = _gs("mcp_remote_url")    or MCP_REMOTE_URL
        api_key = _gs("n8n_kb_api_key")    or N8N_KB_API_KEY
        token   = _gs("n8n_kb_token")      or N8N_KB_TOKEN
        _to     = _gs("mcp_timeout")
        timeout = int(_to) if _to else MCP_TIMEOUT
        _tk     = _gs("mcp_remote_top_k")
        top_k   = int(_tk) if _tk else MCP_REMOTE_TOP_K
    except Exception:
        url, api_key, token, timeout, top_k = (
            MCP_REMOTE_URL, N8N_KB_API_KEY, N8N_KB_TOKEN, MCP_TIMEOUT, MCP_REMOTE_TOP_K
        )
    return url, api_key, token, timeout, top_k


def query_remote(query: str, chat_id: int, top_k: int | None = None) -> list[dict[str, Any]]:
    """Search remote KB via `kb_search`.

    When KB_PG_DSN is set, queries pgvector directly (bypasses MCP SSE).
    Otherwise uses N8N MCP Server tool call.
    Returns an empty list when disabled, circuit open, or on any failure.
    Each chunk dict has keys: ``doc_id``, ``section``, ``text``, ``score``, ``source_uri``.
    """
    from core.bot_config import KB_PG_DSN
    url, api_key, _, timeout, default_top_k = _load_config()
    k = top_k if top_k is not None else default_top_k

    # Direct pgvector path (preferred — MCP SSE incompatible with N8N)
    if KB_PG_DSN:
        return _kb_search_direct(query, chat_id, k)

    if not url:
        return []
    if _cb_is_open():
        log.debug("[MCP-client] circuit breaker open — skipping remote query")
        return []

    try:
        chunks = _run_in_new_loop(_kb_search_async(url, api_key, query, chat_id, k, timeout))
        _cb_record_success()
        log.debug("[MCP-client] kb_search returned %d chunks for %r", len(chunks), query[:40])
        return chunks
    except Exception as exc:
        _cb_record_failure()
        log.warning("[MCP-client] kb_search failed (%s)", exc)
        return []


def _kb_list_documents_direct(chat_id: int) -> dict[str, Any]:
    """Query kb_documents directly via psycopg (bypasses MCP SSE).

    Returns {"documents": [{doc_id, title, mime, created_at, n_chunks}, ...]}
    or {} on error.
    """
    from core.bot_config import KB_PG_DSN
    if not KB_PG_DSN:
        return {}
    try:
        import psycopg
        with psycopg.connect(KB_PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT d.doc_id::text, d.title, d.mime,
                              to_char(d.created_at, 'YYYY-MM-DD HH24:MI') AS created_at,
                              COUNT(c.chunk_id) AS n_chunks
                         FROM kb_documents d
                         LEFT JOIN kb_chunks c ON c.doc_id = d.doc_id
                        WHERE d.owner_chat_id = %s
                        GROUP BY d.doc_id, d.title, d.mime, d.created_at
                        ORDER BY d.created_at DESC""",
                    (chat_id,),
                )
                rows = cur.fetchall()
        docs = [
            {
                "doc_id":     r[0],
                "title":      r[1],
                "mime":       r[2],
                "created_at": r[3],
                "n_chunks":   r[4],
            }
            for r in rows
        ]
        log.debug("[MCP-client] kb_list direct: %d docs for chat_id=%s", len(docs), chat_id)
        return {"documents": docs}
    except Exception as exc:
        log.warning("[MCP-client] kb_list_documents_direct failed (%s)", exc)
        return {}


def _kb_delete_document_direct(doc_id: str, chat_id: int) -> dict[str, Any]:
    """Delete a KB document and its chunks directly via psycopg."""
    from core.bot_config import KB_PG_DSN
    if not KB_PG_DSN:
        return {}
    try:
        import psycopg
        with psycopg.connect(KB_PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM kb_documents WHERE doc_id=%s::uuid AND owner_chat_id=%s RETURNING doc_id",
                    (doc_id, chat_id),
                )
                deleted = cur.fetchone()
            conn.commit()
        if deleted:
            log.info("[MCP-client] deleted doc %s", doc_id)
            return {"deleted": True, "doc_id": doc_id}
        return {"deleted": False, "doc_id": doc_id}
    except Exception as exc:
        log.warning("[MCP-client] kb_delete_document_direct failed (%s)", exc)
        return {}


def _kb_search_direct(query: str, chat_id: int, top_k: int) -> list[dict]:
    """Search KB via direct Ollama embedding + pgvector query (bypasses MCP SSE)."""
    from core.bot_config import KB_PG_DSN, OLLAMA_URL
    if not KB_PG_DSN:
        return []
    # 1. Get embedding from Ollama
    try:
        embed_url = OLLAMA_URL.rstrip('/').replace('/v1', '') + "/api/embeddings"
        payload = _json.dumps({"model": "all-minilm", "prompt": query}).encode()
        req = urllib.request.Request(
            embed_url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            emb_data = _json.loads(resp.read())
        embedding = emb_data.get("embedding", [])
        if not embedding:
            log.warning("[MCP-client] kb_search_direct: empty embedding from Ollama")
            return []
    except Exception as exc:
        log.warning("[MCP-client] kb_search_direct: Ollama embedding failed (%s)", exc)
        return []

    # 2. pgvector cosine similarity search
    try:
        import psycopg
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        with psycopg.connect(KB_PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT c.doc_id::text, c.section, c.text,
                              1 - (c.embedding <=> %s::vector) AS score
                         FROM kb_chunks c
                         JOIN kb_documents d ON d.doc_id = c.doc_id
                        WHERE d.owner_chat_id = %s
                        ORDER BY c.embedding <=> %s::vector
                        LIMIT %s""",
                    (vec_str, chat_id, vec_str, top_k),
                )
                rows = cur.fetchall()
        chunks = [
            {"doc_id": r[0], "section": r[1], "text": r[2], "score": float(r[3]), "source_uri": ""}
            for r in rows
        ]
        log.debug("[MCP-client] kb_search direct: %d chunks for %r", len(chunks), query[:40])
        return chunks
    except Exception as exc:
        log.warning("[MCP-client] kb_search_direct: pgvector query failed (%s)", exc)
        return []


def call_tool(tool: str, args: dict) -> dict[str, Any]:
    """Generic MCP tool call (memory_get, memory_append, memory_clear,
    kb_list_documents, kb_delete_document).

    For kb_list_documents and kb_delete_document, falls back to direct DB
    queries when KB_PG_DSN is set (MCP SSE is incompatible with N8N's SSE
    protocol and closes the connection immediately).

    Returns {} on any failure. Circuit breaker applies to MCP path.
    """
    from core.bot_config import KB_PG_DSN

    # Direct DB path for document operations (bypasses broken MCP SSE)
    if tool == "kb_list_documents" and KB_PG_DSN:
        return _kb_list_documents_direct(args.get("chat_id", 0))
    if tool == "kb_delete_document" and KB_PG_DSN:
        return _kb_delete_document_direct(args.get("doc_id", ""), args.get("chat_id", 0))

    url, api_key, _, timeout, _ = _load_config()
    if not url:
        return {}
    if _cb_is_open():
        log.debug("[MCP-client] circuit breaker open — skipping %s", tool)
        return {}
    try:
        result = _run_in_new_loop(_kb_tool_async(url, api_key, tool, args, timeout))
        _cb_record_success()
        return result
    except Exception as exc:
        _cb_record_failure()
        log.warning("[MCP-client] tool %s failed (%s)", tool, exc)
        return {}


def _extract_to_text(
    file_bytes: bytes, filename: str, mime: str
) -> tuple[bytes, str, str]:
    """Pre-process RTF and legacy DOC files to plain text before sending to N8N.

    Returns (file_bytes, filename, mime) — converted to text/plain when possible.
    Other formats are passed through unchanged.
    """
    fname_lower = filename.lower()

    # RTF → plain text via striprtf
    if fname_lower.endswith('.rtf') or 'rtf' in mime.lower():
        try:
            from striprtf.striprtf import rtf_to_text
            text = rtf_to_text(file_bytes.decode('utf-8', errors='replace'))
            base = filename.rsplit('.', 1)[0]
            log.debug("[MCP-client] RTF extracted: %d chars", len(text))
            return text.encode('utf-8'), base + '.txt', 'text/plain'
        except ImportError:
            log.warning("[MCP-client] striprtf not installed — RTF upload may fail")
        except Exception as exc:
            log.warning("[MCP-client] RTF extraction failed (%s)", exc)

    # .doc (old binary Word) → try python-docx (handles OOXML-based .doc files)
    if fname_lower.endswith('.doc') and not fname_lower.endswith('.docx'):
        try:
            import io as _io
            from docx import Document as _Doc
            doc = _Doc(_io.BytesIO(file_bytes))
            text = '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
            if text:
                base = filename.rsplit('.', 1)[0]
                log.debug("[MCP-client] .doc extracted: %d paragraphs", len(doc.paragraphs))
                return text.encode('utf-8'), base + '.txt', 'text/plain'
        except Exception as exc:
            log.warning("[MCP-client] .doc extraction failed (%s) — sending as-is", exc)

    return file_bytes, filename, mime


def ingest_file(chat_id: int, filename: str, file_bytes: bytes,
                mime: str = "application/octet-stream") -> dict[str, Any]:
    """Upload a file to the N8N ingest webhook (plain HTTP POST multipart).

    File upload uses a separate N8N Webhook workflow — NOT the MCP Server —
    because MCP tool calls use JSON payloads unsuitable for binary data.

    Returns dict with keys: doc_id, n_chunks, n_embedded, parse_time_ms.
    Returns {} on failure.
    """
    from core.bot_config import N8N_KB_WEBHOOK_INGEST, MCP_TIMEOUT
    try:
        from core.bot_db import db_get_system_setting as _gs
        webhook_url = _gs("n8n_kb_webhook_ingest") or N8N_KB_WEBHOOK_INGEST
        _, _, token, timeout, _ = _load_config()
    except Exception:
        from core.bot_config import N8N_KB_TOKEN
        webhook_url, token, timeout = N8N_KB_WEBHOOK_INGEST, N8N_KB_TOKEN, MCP_TIMEOUT

    if not webhook_url:
        log.warning("[MCP-client] N8N_KB_WEBHOOK_INGEST not configured — ingest skipped")
        return {}

    # Pre-process RTF and legacy .doc files to plain text
    file_bytes, filename, mime = _extract_to_text(file_bytes, filename, mime)

    # Build multipart/form-data manually (no external lib required)
    boundary = b"----TarisMCPBoundary"
    body_parts: list[bytes] = []
    for field, value in [("chat_id", str(chat_id)), ("filename", filename), ("mime", mime)]:
        body_parts.append(
            b"--" + boundary + b"\r\n"
            + f'Content-Disposition: form-data; name="{field}"\r\n\r\n'.encode()
            + value.encode() + b"\r\n"
        )
    body_parts.append(
        b"--" + boundary + b"\r\n"
        + f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        + f"Content-Type: {mime}\r\n\r\n".encode()
        + file_bytes + b"\r\n"
    )
    body_parts.append(b"--" + boundary + b"--\r\n")
    body = b"".join(body_parts)

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        req = urllib.request.Request(webhook_url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
        if not raw.strip():
            if status == 200:
                # N8N workflow ran but Respond node expression failed — data was stored.
                # Treat as success with unknown chunk count.
                log.warning("[MCP-client] ingest webhook HTTP 200 with empty body — assuming stored ok")
                return {"n_chunks": "?"}
            log.warning("[MCP-client] ingest webhook returned empty body (HTTP %s)", status)
            return {}
        result = _json.loads(raw)
        log.info("[MCP-client] ingest ok: doc_id=%s n_chunks=%s",
                 result.get("doc_id"), result.get("n_chunks"))
        return result
    except _json.JSONDecodeError as exc:
        log.warning("[MCP-client] ingest: N8N returned non-JSON response (%s)", exc)
        return {}
    except Exception as exc:
        log.warning("[MCP-client] ingest failed (%s)", exc)
        return {}


def circuit_status() -> dict[str, Any]:
    """Return circuit-breaker status dict (for admin health check)."""
    with _cb_lock:
        return {
            "failures":   _cb_failures,
            "open_until": _cb_open_until,
            "is_open":    _cb_is_open(),
        }
