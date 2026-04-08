#!/usr/bin/env python3
"""MCP server: ask for user confirmations/answers through Telegram."""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - runtime dependency guard
    raise SystemExit("Missing dependency 'mcp'. Install with: pip install mcp") from exc

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from telegram_bridge import BridgeConfig, TelegramBridge, pop_task, peek_task_queue


mcp = FastMCP("telegramBridge")

# Module-level bridge singleton — shared across all tool calls to avoid 409 conflicts.
# In SSE mode this is initialised with the dispatcher before mcp.run(transport="sse").
# In stdio mode it is created lazily (no dispatcher, falls back to polling).
_bridge_singleton: TelegramBridge | None = None


# ---------------------------------------------------------------------------
# Minimal HTTP task-queue API (SSE mode only)
# Exposes GET /tasks/pop and GET /tasks/peek so local stdio clients can
# read the task queue that the VPS dispatcher writes to.
# ---------------------------------------------------------------------------

class _TaskAPIHandler(BaseHTTPRequestHandler):
    # Bot token used to authenticate remote callers (non-localhost requests).
    # Set once at startup from the bridge config.
    _auth_token: str | None = None

    def _check_auth(self) -> bool:
        """Return True if the request is allowed.

        Localhost access is always allowed (tunnel / container-internal).
        Remote access requires ?token=<BOT_TOKEN> query param.
        """
        client_host = self.client_address[0] if self.client_address else ""
        if client_host in ("127.0.0.1", "::1", "localhost"):
            return True
        if not self._auth_token:
            return False
        # Parse ?token=... from path
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        provided = qs.get("token", [""])[0]
        return provided == self._auth_token

    def _clean_path(self) -> str:
        """Return path without query string."""
        return self.path.split("?")[0]

    def do_GET(self) -> None:  # noqa: N802
        if not self._check_auth():
            self.send_response(403)
            self.end_headers()
            return
        path = self._clean_path()
        if path == "/tasks/pop":
            task = pop_task()
            body = json.dumps(task if task is not None else {"status": "none"}).encode()
        elif path == "/tasks/peek":
            body = json.dumps(peek_task_queue()).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        """Handle Telegram webhook POST updates at /tgwebhook."""
        if self.path != "/tgwebhook":
            self.send_response(404)
            self.end_headers()
            return
        try:
            raw_len = self.headers.get("Content-Length")
            length = int(raw_len) if raw_len else 0
            body = self.rfile.read(length) if length > 0 else self.rfile.read()
            update = json.loads(body)
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
        # Dispatch asynchronously so we return 200 to Telegram immediately
        if _bridge_singleton is not None:
            threading.Thread(
                target=_bridge_singleton._dispatch,
                args=(update,),
                daemon=True,
                name="wh-dispatch",
            ).start()
        resp = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *_args: Any) -> None:  # suppress access logs
        pass


def _start_task_api_server(port: int, auth_token: str | None = None) -> None:
    """Start the task HTTP API server in a daemon thread (SSE mode only)."""
    _TaskAPIHandler._auth_token = auth_token
    server = HTTPServer(("0.0.0.0", port), _TaskAPIHandler)
    threading.Thread(target=server.serve_forever, daemon=True, name="task-api").start()


def _missing_config_response() -> dict[str, Any]:
    return {
        "status": "error",
        "error": (
            "Telegram bridge is not configured. "
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
            "(or TG_BOT_TOKEN/TG_CHAT_ID)."
        ),
    }


def _get_bridge() -> tuple[BridgeConfig, TelegramBridge | None]:
    """Return the shared bridge singleton, creating it lazily if needed.

    In SSE mode the singleton is pre-created with the dispatcher running.
    In stdio mode it is created here on first call (no dispatcher).
    Either way all tool calls reuse the same instance and never cause
    internal 409 conflicts against each other.
    """
    global _bridge_singleton
    if _bridge_singleton is not None:
        return _bridge_singleton.config, _bridge_singleton
    config = BridgeConfig.from_env(cwd=os.getcwd())
    if not config.is_ready():
        return config, None
    _bridge_singleton = TelegramBridge(config)
    return config, _bridge_singleton


def _run(mode: str, question: str, last_chat_text: str, timeout_seconds: int) -> dict[str, Any]:
    _, bridge = _get_bridge()
    if bridge is None:
        return _missing_config_response()

    token = bridge.new_token()
    message_ids = bridge.send_wait_prompt(
        mode=mode,
        token=token,
        question=question,
        last_chat_text=last_chat_text,
    )
    result = bridge.wait_for_response(
        token=token,
        mode=mode,
        prompt_message_ids=message_ids,
        timeout_seconds=timeout_seconds,
    )
    result["prompt_message_ids"] = message_ids
    return result


@mcp.tool(
    description=(
        "Send a question and last chat text to Telegram, wait for a free-text user "
        "response, and return that response to Copilot."
    )
)
def await_telegram_response(
    question: str,
    last_chat_text: str = "",
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    return _run(
        mode="question",
        question=question,
        last_chat_text=last_chat_text,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool(
    description=(
        "Ask for Telegram approval (allow/deny/ask) and return the decision for "
        "a risky or write action."
    )
)
def await_telegram_confirmation(
    question: str,
    last_chat_text: str = "",
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    result = _run(
        mode="approval",
        question=question,
        last_chat_text=last_chat_text,
        timeout_seconds=timeout_seconds,
    )
    decision = result.get("decision")
    if decision in {"allow", "deny", "ask"}:
        result["approved"] = decision == "allow"
    else:
        result["approved"] = False
    return result


@mcp.tool(
    description=("Send a one-way notification to Telegram. Returns message id list.")
)
def send_telegram_notification(message: str) -> dict[str, Any]:
    _, bridge = _get_bridge()
    if bridge is None:
        return _missing_config_response()

    message_ids = bridge.send_notification_text(message)
    return {"status": "sent", "message_ids": message_ids, "count": len(message_ids)}


@mcp.tool(
    description=(
        "Check for a pending task sent from Telegram with /task <description>. "
        "Returns the task text and sender, or status='none' if the queue is empty. "
        "Call this at the start of each session to pick up user-initiated tasks."
    )
)
def get_pending_task() -> dict[str, Any]:
    # If the VPS is running the dispatcher (stdio mode on local machine),
    # the task was queued inside the VPS container — fetch it via the task HTTP API.
    vps_tasks_url = os.environ.get("VPS_TASKS_URL", "").rstrip("/")
    if vps_tasks_url:
        try:
            import urllib.request as _req
            with _req.urlopen(f"{vps_tasks_url}/tasks/pop", timeout=5) as resp:
                data = json.loads(resp.read())
            if data.get("status") == "none" or data is None:
                return {"status": "none"}
            return {
                "status": "task",
                "text": data.get("text", ""),
                "from_user": data.get("from_user", "telegram"),
                "queued_at": data.get("ts", 0),
            }
        except Exception as exc:
            return {"status": "error", "error": f"VPS task API unreachable: {exc}"}

    task = pop_task()
    if task is None:
        return {"status": "none"}
    return {
        "status": "task",
        "text": task.get("text", ""),
        "from_user": task.get("from_user", "telegram"),
        "queued_at": task.get("ts", 0),
    }


@mcp.tool(
    description=(
        "Notify the Telegram user that a task has been completed. "
        "Call this after finishing a /task request. "
        "summary should be a concise description of what was done."
    )
)
def complete_task(summary: str) -> dict[str, Any]:
    _, bridge = _get_bridge()
    if bridge is None:
        return _missing_config_response()

    message = f"✅ Copilot task completed:\n\n{summary}"
    message_ids = bridge.send_notification_text(message)
    return {"status": "sent", "message_ids": message_ids}

if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        config = BridgeConfig.from_env(cwd=os.getcwd())
        webhook_url = os.environ.get("TELEGRAM_WEBHOOK_URL", "").strip()
        if config.is_ready():
            # Pre-create the singleton with the dispatcher so all tool calls
            # share it instead of creating conflicting per-call instances.
            _bridge_singleton = TelegramBridge(config)
            if webhook_url:
                # Webhook mode: Telegram pushes updates — no polling, no 409.
                _bridge_singleton.set_webhook(webhook_url)
                _logging.getLogger("mcp_server").info(
                    "Webhook mode active (%s) — polling disabled", webhook_url
                )
            else:
                _bridge_singleton.start_task_listener()
        # Start task HTTP API alongside the SSE server so local stdio clients
        # can pop tasks queued by the VPS dispatcher (avoids cross-container file mismatch).
        # Also serves POST /tgwebhook when in webhook mode.
        # Pass bot token so remote callers (task-watcher over HTTPS) can authenticate.
        task_api_port = int(os.environ.get("TASK_API_PORT", "3002"))
        _start_task_api_server(task_api_port, auth_token=config.bot_token if config.is_ready() else None)
        mcp.settings.host = os.environ.get("MCP_HOST", "127.0.0.1")
        mcp.settings.port = int(os.environ.get("MCP_PORT", "3001"))
        mcp.run(transport="sse")
    else:
        mcp.run()

