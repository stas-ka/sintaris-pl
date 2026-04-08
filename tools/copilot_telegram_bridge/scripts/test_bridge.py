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
    """Return True if a remote VPS dispatcher owns the Telegram getUpdates long-poll.

    Two checks (either is sufficient):
    1. Local tunnel port 3001 is open and responding → tunnel is up → VPS is active.
    2. VPS_MCP_HOST is set in .env → VPS is a permanently-running container
       (restart: unless-stopped). If we have no local tunnel it is still polling
       Telegram, so treat it as active to avoid 409 conflicts.
    """
    # Check 1: local tunnel
    try:
        req = urllib.request.Request("http://127.0.0.1:3001/", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status < 500:
                return True
    except urllib.error.HTTPError:
        return True   # HTTP error → server IS responding via tunnel
    except OSError:
        pass  # no tunnel — fall through to check 2

    # Check 2: VPS_MCP_HOST configured → always-on container is polling
    vps_host = cfg.vps_host  # None if not set
    return bool(vps_host)

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
    approved = decision == "allow"
    print(f"  Result: decision={decision}, approved={approved}")
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

# --- Test 4: /task queue (VPS task API) ---
print("\n[4/4] Testing /task queue via VPS HTTP API...")
vps_tasks_url = None
# Check if tunnel is up (port 3002)
try:
    import urllib.request as _req
    with _req.urlopen("http://127.0.0.1:3002/tasks/peek", timeout=3) as r:
        if r.status == 200:
            vps_tasks_url = "http://127.0.0.1:3002"
except Exception:
    pass

if vps_tasks_url is None:
    print("  SKIPPED — task API not reachable at localhost:3002 (start mcp-tunnel.ps1 first)")
else:
    import json as _json
    # 1. Confirm queue starts empty (or drain it)
    with _req.urlopen(f"{vps_tasks_url}/tasks/peek", timeout=5) as r:
        before = _json.loads(r.read())
    print(f"  Queue before: {len(before)} item(s)")

    # 2. Send /task via Telegram and wait for it to appear in queue
    print("  Sending /task test message via Telegram bot API...")
    _tg_url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
    _payload = _json.dumps({"chat_id": cfg.chat_id, "text": "/task [Copilot Test 4/4] verify task queue"}).encode()
    _req2 = _req.Request(_tg_url, data=_payload, headers={"Content-Type": "application/json"}, method="POST")
    with _req.urlopen(_req2, timeout=10) as r:
        _resp = _json.loads(r.read())
    print(f"  Message sent (id={_resp['result']['message_id']}). Waiting 25s for VPS dispatcher...")

    # 3. Wait up to 25s for VPS dispatcher to process
    deadline = time.time() + 25
    queued = None
    while time.time() < deadline:
        time.sleep(2)
        with _req.urlopen(f"{vps_tasks_url}/tasks/peek", timeout=5) as r:
            tasks = _json.loads(r.read())
        if tasks:
            queued = tasks[0]
            break

    if queued:
        print(f"  OK — task appeared in queue: {queued['text'][:60]!r}")
        # Pop it
        with _req.urlopen(f"{vps_tasks_url}/tasks/pop", timeout=5) as r:
            popped = _json.loads(r.read())
        print(f"  OK — popped: status={popped.get('status') or 'task'}, text={str(popped.get('text',''))[:40]!r}")
    else:
        print("  FAIL — task did NOT appear in queue within 25s")
        print("  Check VPS container logs: plink ... 'sudo docker logs copilot-mcp-bridge --tail 20'")

print("\n=== Done ===")
