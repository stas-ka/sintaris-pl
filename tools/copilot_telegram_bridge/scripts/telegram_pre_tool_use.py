#!/usr/bin/env python3
"""Copilot PreToolUse hook: route approval to Telegram."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from telegram_bridge import BridgeConfig, TelegramBridge


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [_as_text(item) for item in value]
        return " ".join(part for part in parts if part)
    if isinstance(value, dict):
        if "text" in value and isinstance(value["text"], str):
            return value["text"].strip()
        parts = [_as_text(item) for item in value.values()]
        return " ".join(part for part in parts if part)
    return ""


def _collect_messages(node: Any, out: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        role = ""
        for role_key in ("role", "participantRole", "authorRole", "senderRole"):
            role_value = node.get(role_key)
            if isinstance(role_value, str):
                role = role_value.lower().strip()
                break

        content = ""
        for content_key in ("content", "text", "message", "body", "value"):
            if content_key in node:
                content = _as_text(node.get(content_key))
                if content:
                    break

        if role and content:
            out.append((role, content))

        for value in node.values():
            _collect_messages(value, out)
        return

    if isinstance(node, list):
        for item in node:
            _collect_messages(item, out)


def _extract_last_messages(transcript_path: str) -> tuple[str, str]:
    if not transcript_path:
        return "", ""

    path = Path(transcript_path)
    if not path.exists():
        return "", ""

    try:
        transcript = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "", ""

    messages: list[tuple[str, str]] = []
    _collect_messages(transcript, messages)

    user_text = ""
    assistant_text = ""
    for role, text in reversed(messages):
        if not user_text and role in {"user", "human", "requester"}:
            user_text = text
        if not assistant_text and role in {"assistant", "model", "copilot", "ai"}:
            assistant_text = text
        if user_text and assistant_text:
            break

    return user_text, assistant_text


def _hook_response(
    permission_decision: str,
    reason: str,
    additional_context: str = "",
) -> dict[str, Any]:
    hook_specific_output: dict[str, Any] = {
        "permissionDecision": permission_decision,
        "permissionDecisionReason": reason,
    }
    if additional_context:
        hook_specific_output["additionalContext"] = additional_context
    return {"hookSpecificOutput": hook_specific_output}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps(_hook_response("ask", f"Invalid hook input JSON: {exc}")))
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    config = BridgeConfig.from_env(cwd=cwd)
    if not config.is_ready():
        print(
            json.dumps(
                _hook_response(
                    "ask",
                    "Telegram bridge not configured (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).",
                )
            )
        )
        return 0

    tool_name = str(payload.get("tool_name") or "unknown_tool")
    tool_input = payload.get("tool_input")
    transcript_path = str(payload.get("transcript_path") or "")
    session_id = str(payload.get("session_id") or "")

    last_user, last_assistant = _extract_last_messages(transcript_path)
    tool_input_text = json.dumps(tool_input, ensure_ascii=False, indent=2)

    question = (
        "Copilot requests tool execution approval.\n"
        f"Tool: {tool_name}\n"
        f"Session: {session_id or 'n/a'}"
    )

    context_parts = []
    if last_user:
        context_parts.append(f"Last user question:\n{last_user}")
    if last_assistant:
        context_parts.append(f"Last assistant text:\n{last_assistant}")
    if tool_input_text and tool_input_text != "null":
        context_parts.append(f"Tool input:\n{tool_input_text}")
    last_chat_text = "\n\n".join(context_parts)

    bridge = TelegramBridge(config)
    token = bridge.new_token()
    try:
        prompt_message_ids = bridge.send_wait_prompt(
            mode="approval",
            token=token,
            question=question,
            last_chat_text=last_chat_text,
        )
        result = bridge.wait_for_response(
            token=token,
            mode="approval",
            prompt_message_ids=prompt_message_ids,
            timeout_seconds=config.default_timeout_seconds,
        )
    except Exception as exc:
        print(json.dumps(_hook_response("ask", f"Telegram hook error: {exc}")))
        return 0

    if result.get("status") != "received":
        print(
            json.dumps(
                _hook_response(
                    "ask",
                    "No Telegram response before timeout. Showing VS Code confirmation.",
                )
            )
        )
        return 0

    decision = str(result.get("decision") or "ask").lower()
    free_text = str(result.get("text") or "").strip()
    from_user = str(result.get("from_user") or "telegram-user")
    reason = f"Decision from Telegram user '{from_user}' via token {token}."

    if decision == "allow":
        print(json.dumps(_hook_response("allow", reason, additional_context=free_text)))
        return 0
    if decision == "deny":
        print(json.dumps(_hook_response("deny", reason, additional_context=free_text)))
        return 0

    print(json.dumps(_hook_response("ask", reason, additional_context=free_text)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

