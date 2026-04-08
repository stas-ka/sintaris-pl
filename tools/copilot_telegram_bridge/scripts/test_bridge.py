#!/usr/bin/env python3
"""Quick test of all three Telegram bridge functions.

Usage:
  python test_bridge.py             # full test (requires VPS container to be STOPPED)
  python test_bridge.py --no-wait   # notification-only test (safe while VPS is running)

IMPORTANT: When the VPS dispatcher (docker container copilot-mcp-bridge) is running,
it owns the Telegram getUpdates long-poll. Running wait tests locally at the same time
causes HTTP 409 Conflict. Use --no-wait to test notifications only, or stop the VPS
container first: plink -pw "..." boh@dev2null.website "sudo docker stop copilot-mcp-bridge"
"""
from __future__ import annotations
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from telegram_bridge import BridgeConfig, TelegramBridge

ROOT = Path(__file__).parents[3]  # scripts/ -> copilot_telegram_bridge/ -> tools/ -> workspace root
cfg = BridgeConfig.from_env(cwd=str(ROOT))

if not cfg.is_ready():
    print("FAIL: bridge not configured (check .env for TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)")
    sys.exit(1)

NO_WAIT = "--no-wait" in sys.argv

# Detect if VPS SSE tunnel is active on localhost:3001
_vps_active = False
try:
    s = socket.create_connection(("127.0.0.1", 3001), timeout=1)
    s.close()
    _vps_active = True
except OSError:
    pass

if _vps_active and not NO_WAIT:
    print(
        "WARNING: VPS SSE server detected on localhost:3001.\n"
        "Running wait tests locally while VPS dispatcher is active will cause 409 Conflict.\n"
        "Switching to --no-wait mode automatically.\n"
        "To run full test: stop the VPS container first or use '--no-wait' to suppress this warning.\n"
    )
    NO_WAIT = True

print(f"Config OK — bot_token: ...{cfg.bot_token[-8:]}, chat_id: {cfg.chat_id}")
print(f"Mode: {'notification-only (no-wait)' if NO_WAIT else 'full interactive'}")
bridge = TelegramBridge(cfg)

# --- Test 1: notification (no reply needed) ---
print("\n[1/3] Sending notification...")
ids = bridge.send_notification_text(
    "[Copilot Bridge Test 1/3] Notification test\n"
    "This is a one-way message from GitHub Copilot in VS Code.\n"
    "No reply needed."
)
print(f"  OK — message_ids: {ids}")

# --- Test 2: approval ---
print("\n[2/3] Sending approval request (timeout 60s)...")
if NO_WAIT:
    print("  SKIPPED (no-wait mode)")
else:
    print("  --> Reply /allow or /deny to @su_vscnotifier_bot in Telegram now!")
    token = bridge.new_token()
    msg_ids = bridge.send_wait_prompt(
        mode="approval",
        token=token,
        question="[Copilot Bridge Test 2/3] Approval request\n\nCopilot wants to run: git commit -m 'test'\n\nAllow this action?",
        last_chat_text="",
    )
    result = bridge.wait_for_response(
        token=token,
        mode="approval",
        prompt_message_ids=msg_ids,
        timeout_seconds=60,
    )
    decision = result.get("decision", "timeout")
    print(f"  Result: decision={decision}, approved={result.get('approved', False)}")
    if decision == "timeout":
        print("  (timed out — that is OK, bot is working, just reply faster next time)")

# --- Test 3: free-text question ---
print("\n[3/3] Sending question (timeout 60s)...")
if NO_WAIT:
    print("  SKIPPED (no-wait mode)")
else:
    print("  --> Reply /reply <TOKEN> your answer  OR just reply to the message in Telegram!")
    token2 = bridge.new_token()
    msg_ids2 = bridge.send_wait_prompt(
        mode="question",
        token=token2,
        question="[Copilot Bridge Test 3/3] Question\n\nWhat is 2 + 2?",
        last_chat_text="",
    )
    result2 = bridge.wait_for_response(
        token=token2,
        mode="question",
        prompt_message_ids=msg_ids2,
        timeout_seconds=60,
    )
    answer = result2.get("text", result2.get("decision", "timeout"))
    print(f"  Result: answer='{answer}'")

print("\n--- All tests done ---")
