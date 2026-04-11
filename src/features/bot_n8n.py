"""
bot_n8n.py — N8N workflow automation adapter.

Provides REST API integration with N8N for:
- Listing available workflows
- Triggering workflow executions
- Checking execution status
- Receiving webhook callbacks
"""

import logging
import time
from typing import Any

import requests

from core.bot_config import N8N_URL, N8N_API_KEY, N8N_TIMEOUT

log = logging.getLogger("taris.n8n")

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def _api(method: str, path: str, **kwargs) -> dict:
    """Call N8N REST API. Returns parsed JSON or {"error": ...}."""
    if not N8N_URL or not N8N_API_KEY:
        return {"error": "N8N not configured (N8N_URL or N8N_API_KEY missing)"}
    url = f"{N8N_URL.rstrip('/')}/api/v1{path}"
    try:
        resp = requests.request(method, url, headers=_headers(),
                                timeout=N8N_TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout:
        log.warning("[N8N] timeout %s %s", method, path)
        return {"error": f"N8N timeout after {N8N_TIMEOUT}s"}
    except requests.RequestException as e:
        log.warning("[N8N] request error: %s", e)
        return {"error": str(e)}
    except ValueError:
        return {"error": "Invalid JSON response from N8N"}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def is_configured() -> bool:
    """True if N8N integration is configured."""
    return bool(N8N_URL and N8N_API_KEY)


def list_workflows(active_only: bool = True, limit: int = 50) -> list[dict]:
    """Return list of N8N workflows [{id, name, active, createdAt, updatedAt}]."""
    data = _api("GET", f"/workflows?limit={limit}")
    if "error" in data:
        log.warning("[N8N] list_workflows: %s", data["error"])
        return []
    workflows = data.get("data", [])
    if active_only:
        workflows = [w for w in workflows if w.get("active")]
    return [
        {
            "id": w["id"],
            "name": w.get("name", "?"),
            "active": w.get("active", False),
        }
        for w in workflows
    ]


def trigger_workflow(workflow_id: str, payload: dict | None = None) -> dict:
    """Trigger a workflow via N8N webhook or production execution.

    Returns {"executionId": "..."} on success or {"error": "..."}.
    """
    body = {"workflowId": workflow_id}
    if payload:
        body["payload"] = payload
    data = _api("POST", f"/workflows/{workflow_id}/activate", json=body)
    if "error" in data:
        # Try webhook-based trigger as fallback
        return _trigger_via_webhook(workflow_id, payload or {})
    return data


def _trigger_via_webhook(workflow_id: str, payload: dict) -> dict:
    """Trigger workflow via its webhook URL (if configured in N8N)."""
    url = f"{N8N_URL.rstrip('/')}/webhook/{workflow_id}"
    try:
        resp = requests.post(url, json=payload, timeout=N8N_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("[N8N] webhook trigger failed: %s", e)
        return {"error": str(e)}


def get_execution(execution_id: str) -> dict:
    """Get status of a workflow execution.

    Returns {id, finished, status, startedAt, stoppedAt, data} or {"error": ...}.
    """
    data = _api("GET", f"/executions/{execution_id}")
    if "error" in data:
        return data
    return {
        "id": data.get("id"),
        "finished": data.get("finished", False),
        "status": data.get("status", "unknown"),
        "startedAt": data.get("startedAt"),
        "stoppedAt": data.get("stoppedAt"),
        "workflowId": data.get("workflowId"),
    }


def list_executions(workflow_id: str | None = None, limit: int = 10,
                    status: str | None = None) -> list[dict]:
    """List recent executions, optionally filtered by workflow and status."""
    params = f"?limit={limit}"
    if workflow_id:
        params += f"&workflowId={workflow_id}"
    if status:
        params += f"&status={status}"
    data = _api("GET", f"/executions{params}")
    if "error" in data:
        return []
    return [
        {
            "id": ex.get("id"),
            "workflowId": ex.get("workflowId"),
            "status": ex.get("status", "unknown"),
            "finished": ex.get("finished", False),
            "startedAt": ex.get("startedAt"),
        }
        for ex in data.get("data", [])
    ]


def get_workflow(workflow_id: str) -> dict:
    """Get details of a single workflow."""
    return _api("GET", f"/workflows/{workflow_id}")


def test_connection() -> dict:
    """Test N8N connectivity. Returns {ok: True, workflows: N} or {ok: False, error: ...}."""
    if not is_configured():
        return {"ok": False, "error": "N8N not configured"}
    t0 = time.time()
    data = _api("GET", "/workflows?limit=1")
    latency = round((time.time() - t0) * 1000)
    if "error" in data:
        return {"ok": False, "error": data["error"], "latency_ms": latency}
    total = len(data.get("data", []))
    return {"ok": True, "workflows": total, "latency_ms": latency}


# ─────────────────────────────────────────────────────────────────────────────
# Webhook callback processing
# ─────────────────────────────────────────────────────────────────────────────

# Registered callback handlers: event_type → handler function
_callbacks: dict[str, Any] = {}


def register_callback(event_type: str, handler) -> None:
    """Register a handler for N8N webhook events.

    handler(payload: dict) -> None
    """
    _callbacks[event_type] = handler
    log.info("[N8N] registered callback for '%s'", event_type)


def process_callback(event_type: str, payload: dict) -> bool:
    """Process an incoming N8N webhook callback. Returns True if handled."""
    handler = _callbacks.get(event_type)
    if handler:
        try:
            handler(payload)
            return True
        except Exception as e:
            log.error("[N8N] callback handler error for '%s': %s", event_type, e)
            return False
    log.warning("[N8N] no handler for event '%s'", event_type)
    return False
