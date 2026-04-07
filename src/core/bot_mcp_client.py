"""
bot_mcp_client.py — Phase D: MCP remote RAG client.

Calls an external MCP-compatible RAG endpoint and returns ranked chunks
that are merged into the local RRF pipeline.

Circuit breaker:
  After 3 consecutive failures the client stops calling the remote for
  MCP_CB_RESET_SEC seconds (default 300 = 5 min), then retries once.
  On the retry success the circuit closes; on failure it stays open.

Configuration (via bot.env / environment):
  MCP_REMOTE_URL   — full URL of the remote /mcp/search endpoint (empty = disabled)
  MCP_TIMEOUT      — per-request timeout in seconds (default 15)
  TARIS_API_TOKEN  — Bearer token sent in Authorization header
  MCP_REMOTE_TOP_K — max chunks to request from remote (default 3)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

# ─── circuit-breaker state (module-level singleton) ─────────────────────────
_CB_THRESHOLD = 3           # failures before opening
_CB_RESET_SEC = 300         # seconds to wait before retrying
_cb_lock       = threading.Lock()
_cb_failures   = 0
_cb_open_until = 0.0        # epoch time; 0 = closed
# ─────────────────────────────────────────────────────────────────────────────


def _cb_record_success() -> None:
    global _cb_failures, _cb_open_until
    with _cb_lock:
        _cb_failures = 0
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
    with _cb_lock:
        if _cb_open_until == 0.0:
            return False
        if time.monotonic() >= _cb_open_until:
            # half-open: allow one probe
            _cb_open_until = 0.0
            return False
        return True


def query_remote(query: str, chat_id: int, top_k: int | None = None) -> list[dict[str, Any]]:
    """Fetch ranked RAG chunks from a remote MCP-compatible endpoint.

    Returns an empty list when:
    - MCP_REMOTE_URL is not configured
    - Circuit breaker is open
    - Remote call fails / times out

    Each returned chunk dict has keys: ``doc_id``, ``chunk_text``, ``score``.

    Configuration priority: system_settings DB (admin-editable) > bot.env / environment.
    """
    from core.bot_config import MCP_REMOTE_URL, MCP_TIMEOUT, TARIS_API_TOKEN, MCP_REMOTE_TOP_K
    try:
        from core.bot_db import db_get_system_setting as _gs
        url     = _gs("mcp_remote_url") or MCP_REMOTE_URL
        token   = _gs("mcp_api_token")  or TARIS_API_TOKEN
        _to_s   = _gs("mcp_timeout")
        timeout = int(_to_s) if _to_s else MCP_TIMEOUT
        _tk_s   = _gs("mcp_remote_top_k")
        default_top_k = int(_tk_s) if _tk_s else MCP_REMOTE_TOP_K
    except Exception:
        url, token, timeout, default_top_k = MCP_REMOTE_URL, TARIS_API_TOKEN, MCP_TIMEOUT, MCP_REMOTE_TOP_K

    if not url:
        return []

    if _cb_is_open():
        log.debug("[MCP-client] circuit breaker open — skipping remote query")
        return []

    k = top_k if top_k is not None else default_top_k

    try:
        import urllib.request, json as _json

        payload = _json.dumps({
            "query":   query,
            "chat_id": chat_id,
            "top_k":   k,
        }).encode()

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(
            url,
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = _json.loads(resp.read())

        chunks = body.get("chunks", [])
        if not isinstance(chunks, list):
            raise ValueError(f"unexpected response format: {type(chunks)}")

        _cb_record_success()
        log.debug("[MCP-client] received %d remote chunks for query %r", len(chunks), query[:40])
        return chunks

    except Exception as exc:
        _cb_record_failure()
        log.warning("[MCP-client] remote query failed (%s) — falling back to local RAG", exc)
        return []


def circuit_status() -> dict[str, Any]:
    """Return circuit-breaker status dict (for admin health check)."""
    with _cb_lock:
        return {
            "failures":   _cb_failures,
            "open_until": _cb_open_until,
            "is_open":    _cb_is_open(),
        }
