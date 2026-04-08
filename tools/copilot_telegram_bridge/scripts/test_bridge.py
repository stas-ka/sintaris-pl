#!/usr/bin/env python3
"""Quick test of all three Telegram bridge functions.

Usage:
  python test_bridge.py             # auto-detects VPS; does full test if VPS is unreachable
  python test_bridge.py --no-wait   # notification-only test (always safe)
  python test_bridge.py --force     # full interactive test even if tunnel port is open

IMPORTANT: When the VPS dispatcher (docker container copilot-mcp-bridge) is running,
it owns the Telegram getUpdates long-poll. Running wait tests locally at the same time
causes HTTP 409 Conflict. Stop the VPS container first:
  plink -pw "zusammen2019" -batch boh@dev2null.website "echo zusammen2019 | sudo -S docker stop copilot-mcp-bridge"
then run this script, then restart:
  plink -pw "zusammen2019" -batch boh@dev2null.website "echo zusammen2019 | sudo -S systemctl start copilot-mcp-bridge"
"""
from __future__ import annotations
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from telegram_bridge import BridgeConfig, TelegramBridge

ROOT = Path(__file__).parents[3]  # scripts/ -> copilot_telegram_bridge/ -> tools/ -> workspace root
cfg = BridgeConfig.from_env(cwd=str(ROOT))

if not cfg.is_ready():
    print("FAIL: bridge not configured (check .env for TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)")
    sys.exit(1)

NO_WAIT = "--no-wait" in sys.argv
FORCE   = "--force"   in sys.argv

def _vps_dispatcher_responding() -> bool:
    """Return True only if the VPS SSE server is actually responding (not just tunnel port open)."""
    try:
        req = urllib.request.Request("http://127.0.0.1:3001/", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status < 500
    except urllib.error.HTTPError:
        return True   # got an HTTP error → server IS responding
    except OSError:
        return False  # connection refused or tunnel not reachable

_vps_active = _vps_dispatcher_responding()

if _vps_active and not NO_WAIT and not FORCE:
    print(
        "WARNING: VPS SSE dispatcher is active on localhost:3001.\n"
        "Running wait tests locally while VPS is running will cause 409 Conflict.\n"
        "Switching to --no-wait mode automatically.\n"
        "\nTo run full interactive test:\n"
        "  1. plink -pw zusammen2019 -batch boh@dev2null.website "
        "\"echo zusammen2019 | sudo -S docker stop copilot-mcp-bridge\"\n"
        "  2. python test_bridge.py\n"
        "  3. (restart VPS after test)\n"
        "\nOr use --force to skip this check (only if VPS container is actually stopped).\n"
    )
    NO_WAIT = True

print(f"Config OK — bot_token: ...{cfg.bot_token[-8:]}, chat_id: {cfg.chat_id}")
print(f"VPS active: {_vps_active}  |  Mode: {'notification-only (no-wait)' if NO_WAIT else 'full interactive'}")
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
