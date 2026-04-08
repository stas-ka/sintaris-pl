#!/usr/bin/env python3
"""MCP server: ask for user confirmations/answers through Telegram."""

from __future__ import annotations

import os
import sys
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
    _, bridge = _make_bridge()
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
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        config = BridgeConfig.from_env(cwd=os.getcwd())
        if config.is_ready():
            # Pre-create the singleton with the dispatcher so all tool calls
            # share it instead of creating conflicting per-call instances.
            _bridge_singleton = TelegramBridge(config)
            _bridge_singleton.start_task_listener()
        mcp.settings.host = os.environ.get("MCP_HOST", "127.0.0.1")
        mcp.settings.port = int(os.environ.get("MCP_PORT", "3001"))
        mcp.run(transport="sse")
    else:
        mcp.run()

