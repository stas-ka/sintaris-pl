"""
bot_mcp_client.py — Remote KB client via N8N MCP Server (SSE transport).

Connects to an N8N workflow published as an MCP Server using the MCP protocol
over Server-Sent Events (SSE). Used exclusively by the remote_kb agent/skill.
Default Taris RAG/chat flow is NOT affected.

Circuit breaker:
  After 3 consecutive failures the client stops calling the remote for
  MCP_CB_RESET_SEC seconds (default 300 = 5 min), then retries once.
  On the retry success the circuit closes; on failure it stays open.

Configuration (via bot.env / environment):
  MCP_REMOTE_URL   — N8N MCP Server SSE endpoint (empty = disabled)
                     e.g. https://agents.sintaris.net/n8n/mcp/<path>/sse
  N8N_KB_API_KEY   — N8N API key sent as X-N8N-API-Key header
  N8N_KB_TOKEN     — Bearer token for the N8N ingest webhook (file upload)
  MCP_TIMEOUT      — per-request timeout in seconds (default 15)
  MCP_REMOTE_TOP_K — max chunks to request from kb_search tool (default 3)

Requires: mcp>=1.2.0, httpx>=0.27.0, httpx-sse>=0.4.0 (in deploy/requirements.txt)
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
    """Search remote KB via N8N MCP Server `kb_search` tool.

    Returns an empty list when disabled, circuit open, or on any failure.
    Each chunk dict has keys: ``doc_id``, ``section``, ``text``, ``score``, ``source_uri``.
    """
    url, api_key, _, timeout, default_top_k = _load_config()
    if not url:
        return []
    if _cb_is_open():
        log.debug("[MCP-client] circuit breaker open — skipping remote query")
        return []

    k = top_k if top_k is not None else default_top_k
    try:
        chunks = _run_in_new_loop(_kb_search_async(url, api_key, query, chat_id, k, timeout))
        _cb_record_success()
        log.debug("[MCP-client] kb_search returned %d chunks for %r", len(chunks), query[:40])
        return chunks
    except Exception as exc:
        _cb_record_failure()
        log.warning("[MCP-client] kb_search failed (%s)", exc)
        return []


def call_tool(tool: str, args: dict) -> dict[str, Any]:
    """Generic MCP tool call (memory_get, memory_append, memory_clear,
    kb_list_documents, kb_delete_document).

    Returns {} on any failure. Circuit breaker applies.
    """
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
            result = _json.loads(resp.read())
        log.info("[MCP-client] ingest ok: doc_id=%s n_chunks=%s",
                 result.get("doc_id"), result.get("n_chunks"))
        return result
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
