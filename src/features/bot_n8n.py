"""
bot_n8n.py — Workflow automation adapter (webhook-first, technology-agnostic).

Primary integration pattern: standard HTTP webhooks and REST.
No proprietary SDK or N8N-specific library dependency is required.

Supported outbound authentication types (WEBHOOK_AUTH_TYPE env var):
  none    — no authentication (development/trusted networks only)
  bearer  — Authorization: Bearer <WEBHOOK_AUTH_TOKEN>
  apikey  — <WEBHOOK_AUTH_HEADER or 'X-Api-Key'>: <WEBHOOK_AUTH_TOKEN>
  hmac    — X-Signature: sha256=HMAC-SHA256(body, WEBHOOK_HMAC_SECRET)
  basic   — Authorization: Basic base64(<WEBHOOK_AUTH_TOKEN>)  # format "user:pass"

Optional N8N admin API (requires N8N_URL + N8N_API_KEY):
  list_workflows(), get_execution(), list_executions(), get_workflow()
  These use N8N's proprietary REST API and are only needed for admin introspection.
  All workflow triggering uses standard webhooks — no N8N API key required.

⏳ OPEN: OAuth 2.0 client-credentials, inbound auth middleware → See TODO.md §2.2
"""

import base64
import hashlib
import hmac as _hmac
import json
import logging
import time
from typing import Any

import requests

from core.bot_config import (
    N8N_URL, N8N_API_KEY, N8N_TIMEOUT,
    WEBHOOK_AUTH_TYPE, WEBHOOK_AUTH_TOKEN, WEBHOOK_AUTH_HEADER, WEBHOOK_HMAC_SECRET,
)

log = logging.getLogger("taris.n8n")


# ─────────────────────────────────────────────────────────────────────────────
# Webhook-first public API (technology-agnostic)
# Works with n8n, Make, Zapier, custom REST services, or any HTTP endpoint.
# ─────────────────────────────────────────────────────────────────────────────

def call_webhook(
    url: str,
    payload: dict,
    *,
    auth_type: str | None = None,
    auth_token: str | None = None,
    auth_header: str | None = None,
    hmac_secret: str | None = None,
    timeout: int | None = None,
) -> dict:
    """POST JSON payload to a webhook URL and return parsed response.

    This is the primary integration point — works with any HTTP service
    without proprietary SDK or N8N-specific dependencies.

    Per-call auth overrides take precedence over global WEBHOOK_AUTH_* env vars.
    Returns parsed JSON dict, or {"error": "...", "status_code": N} on failure.
    """
    if not url:
        return {"error": "Webhook URL not configured"}

    body = json.dumps(payload, ensure_ascii=False)
    _auth_type   = auth_type   or WEBHOOK_AUTH_TYPE
    _auth_token  = auth_token  or WEBHOOK_AUTH_TOKEN
    _auth_header = auth_header or WEBHOOK_AUTH_HEADER
    _secret      = hmac_secret or WEBHOOK_HMAC_SECRET
    _timeout     = timeout     or N8N_TIMEOUT

    headers = {"Content-Type": "application/json"}
    headers.update(_build_auth_headers(_auth_type, _auth_token, _auth_header, _secret, body))

    try:
        resp = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=_timeout)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return {"result": resp.text, "status_code": resp.status_code}
    except requests.Timeout:
        log.warning("[webhook] timeout after %ds: %s", _timeout, url)
        return {"error": f"Webhook timeout after {_timeout}s"}
    except requests.HTTPError as e:
        log.warning("[webhook] HTTP %s: %s", e.response.status_code, url)
        return {"error": str(e), "status_code": e.response.status_code}
    except requests.RequestException as e:
        log.warning("[webhook] request error: %s", e)
        return {"error": str(e)}


def _build_auth_headers(
    auth_type: str,
    token: str,
    header_name: str,
    hmac_secret: str,
    body: str,
) -> dict:
    """Build standard HTTP authentication headers for outgoing webhook calls.

    bearer  → Authorization: Bearer <token>
    apikey  → <header_name or 'X-Api-Key'>: <token>
    hmac    → X-Signature: sha256=<HMAC-SHA256(body, secret)>
    basic   → Authorization: Basic base64(<token>)   # token = "user:pass"
    none    → {} (no auth)

    ⏳ OPEN: OAuth 2.0 client-credentials → See TODO.md §2.2
    """
    if not auth_type or auth_type == "none":
        return {}
    if auth_type == "bearer":
        if not token:
            log.warning("[webhook] auth_type=bearer but WEBHOOK_AUTH_TOKEN not set")
            return {}
        return {"Authorization": f"Bearer {token}"}
    if auth_type == "apikey":
        if not token:
            log.warning("[webhook] auth_type=apikey but WEBHOOK_AUTH_TOKEN not set")
            return {}
        return {header_name or "X-Api-Key": token}
    if auth_type == "hmac":
        if not hmac_secret:
            log.warning("[webhook] auth_type=hmac but WEBHOOK_HMAC_SECRET not set")
            return {}
        sig = _hmac.new(hmac_secret.encode(), body.encode("utf-8"), hashlib.sha256).hexdigest()
        return {"X-Signature": f"sha256={sig}"}
    if auth_type == "basic":
        if not token:
            log.warning("[webhook] auth_type=basic but WEBHOOK_AUTH_TOKEN not set")
            return {}
        encoded = base64.b64encode(token.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    log.warning("[webhook] unknown auth_type '%s' — no auth header sent", auth_type)
    return {}


def verify_incoming_signature(body: bytes, signature_header: str) -> bool:
    """Verify HMAC-SHA256 signature on an incoming webhook callback.

    Expects signature_header in format 'sha256=<hex>'.
    Returns True if signature matches WEBHOOK_HMAC_SECRET.
    Returns True unconditionally when WEBHOOK_HMAC_SECRET is not set (open mode).

    ⏳ OPEN: full inbound auth middleware → See TODO.md §2.2
    """
    if not WEBHOOK_HMAC_SECRET:
        return True
    expected = _hmac.new(WEBHOOK_HMAC_SECRET.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return _hmac.compare_digest(expected, provided)


def trigger_workflow(webhook_url: str, payload: dict | None = None) -> dict:
    """Trigger a workflow via its webhook URL.

    Primary trigger mechanism — uses standard HTTP POST, no N8N API key required.
    Pass the full webhook URL (stored in bot.env, not derived from N8N API).

    Returns parsed response dict or {"error": "..."}.
    """
    return call_webhook(webhook_url, payload or {})


def is_configured() -> bool:
    """True if any workflow integration is reachable (webhook URLs or admin API)."""
    from core.bot_config import N8N_CAMPAIGN_SELECT_WH, N8N_CAMPAIGN_SEND_WH
    return bool(N8N_URL or N8N_CAMPAIGN_SELECT_WH or N8N_CAMPAIGN_SEND_WH)


def is_admin_api_configured() -> bool:
    """True if N8N admin API is configured (N8N_URL + N8N_API_KEY)."""
    return bool(N8N_URL and N8N_API_KEY)


# ─────────────────────────────────────────────────────────────────────────────
# N8N Admin API — optional; requires N8N_URL + N8N_API_KEY
# Use only for admin introspection (list/inspect workflows & executions).
# Workflow triggering must always use call_webhook() / trigger_workflow() above.
# ─────────────────────────────────────────────────────────────────────────────

def _n8n_headers() -> dict:
    return {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def _n8n_api(method: str, path: str, **kwargs) -> dict:
    """Call N8N proprietary admin REST API. Admin introspection only."""
    if not N8N_URL or not N8N_API_KEY:
        return {"error": "N8N admin API not configured (N8N_URL or N8N_API_KEY missing)"}
    url = f"{N8N_URL.rstrip('/')}/api/v1{path}"
    try:
        resp = requests.request(method, url, headers=_n8n_headers(),
                                timeout=N8N_TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout:
        log.warning("[N8N admin] timeout %s %s", method, path)
        return {"error": f"N8N admin API timeout after {N8N_TIMEOUT}s"}
    except requests.RequestException as e:
        log.warning("[N8N admin] request error: %s", e)
        return {"error": str(e)}
    except ValueError:
        return {"error": "Invalid JSON from N8N admin API"}


def list_workflows(active_only: bool = True, limit: int = 50) -> list[dict]:
    """[Admin] List N8N workflows via proprietary admin API."""
    data = _n8n_api("GET", f"/workflows?limit={limit}")
    if "error" in data:
        log.warning("[N8N admin] list_workflows: %s", data["error"])
        return []
    workflows = data.get("data", [])
    if active_only:
        workflows = [w for w in workflows if w.get("active")]
    return [
        {"id": w["id"], "name": w.get("name", "?"), "active": w.get("active", False)}
        for w in workflows
    ]


def get_execution(execution_id: str) -> dict:
    """[Admin] Get N8N execution status via proprietary admin API."""
    data = _n8n_api("GET", f"/executions/{execution_id}")
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
    """[Admin] List N8N executions via proprietary admin API."""
    params = f"?limit={limit}"
    if workflow_id:
        params += f"&workflowId={workflow_id}"
    if status:
        params += f"&status={status}"
    data = _n8n_api("GET", f"/executions{params}")
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
    """[Admin] Get N8N workflow details via proprietary admin API."""
    return _n8n_api("GET", f"/workflows/{workflow_id}")


def test_connection() -> dict:
    """Test N8N admin API connectivity. Returns {ok, workflows, latency_ms} or {ok, error}."""
    if not is_admin_api_configured():
        return {"ok": False, "error": "N8N admin API not configured (N8N_URL + N8N_API_KEY required)"}
    t0 = time.time()
    data = _n8n_api("GET", "/workflows?limit=1")
    latency = round((time.time() - t0) * 1000)
    if "error" in data:
        return {"ok": False, "error": data["error"], "latency_ms": latency}
    return {"ok": True, "workflows": len(data.get("data", [])), "latency_ms": latency}


# ─────────────────────────────────────────────────────────────────────────────
# Incoming webhook callback processing
# ─────────────────────────────────────────────────────────────────────────────

_callbacks: dict[str, Any] = {}


def register_callback(event_type: str, handler) -> None:
    """Register a handler for incoming webhook events.

    handler(payload: dict) -> None
    """
    _callbacks[event_type] = handler
    log.info("[webhook] registered callback for '%s'", event_type)


def process_callback(event_type: str, payload: dict) -> bool:
    """Process an incoming webhook callback. Returns True if handled."""
    handler = _callbacks.get(event_type)
    if handler:
        try:
            handler(payload)
            return True
        except Exception as e:
            log.error("[webhook] callback handler error for '%s': %s", event_type, e)
            return False
    log.warning("[webhook] no handler for event '%s'", event_type)
    return False
