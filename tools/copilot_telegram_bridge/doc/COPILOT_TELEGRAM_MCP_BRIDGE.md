# Copilot Telegram MCP Bridge

Adds Telegram-based notifications and two-way interaction for GitHub Copilot Chat (VS Code)
via **@su_vscnotifier_bot** (`@learninguser_bot`):

- MCP tools: Q&A, confirmation requests, one-way notifications, task submission
- A `PreToolUse` hook that routes tool approval to Telegram
- A custom chat mode `telegram-gated-agent` that uses all tools above
- VPS-hosted Docker service so the bridge is always online (no local Python process needed)

## Architecture

```
Telegram App
    │  /allow  /deny  /reply  /task
    ▼
VPS Docker container (dev2null.website)
    │  SSE (port 3001, bound to 127.0.0.1)
    ▼ (via SSH tunnel: plink -N -L 3001:127.0.0.1:3001 boh@dev2null.website)
VS Code MCP client  ──  telegramBridge server  ──  Copilot Chat
```

**Unified dispatcher**: a single background thread on the VPS polls Telegram `getUpdates`
and routes messages to either the task queue (for `/task`) or to `wait_for_response`
callers (via `threading.Event` mailboxes). No duplicate polling, no 409 Conflict.

## Files

| File | Purpose |
|------|---------|
| `.vscode/mcp.json` | MCP server registration — VPS primary + local fallback |
| `.vscode/settings.json` | `PreToolUse` hook registration |
| `.github/chatmodes/telegram-gated-agent.chatmode.md` | Custom Copilot chat mode |
| `tools/copilot_telegram_bridge/scripts/telegram_bridge.py` | Telegram client + unified dispatcher |
| `tools/copilot_telegram_bridge/scripts/mcp_server.py` | FastMCP server (5 tools) |
| `tools/copilot_telegram_bridge/scripts/telegram_pre_tool_use.py` | `PreToolUse` hook script |
| `tools/copilot_telegram_bridge/scripts/get_chat_id.py` | Helper: find your chat_id |
| `tools/copilot_telegram_bridge/scripts/test_bridge.py` | Notification test (safe while VPS active) |
| `tools/copilot_telegram_bridge/scripts/diagnostic.py` | Setup diagnostic |
| `tools/copilot_telegram_bridge/scripts/requirements.txt` | Python dependencies |
| `tools/copilot_telegram_bridge/Dockerfile` | Docker image definition |
| `tools/copilot_telegram_bridge/docker-compose.yml` | VPS service config |
| `tools/copilot_telegram_bridge/deploy-vps.sh` | VPS deploy script |
| `tools/copilot_telegram_bridge/mcp-tunnel.ps1` | Windows: start SSH tunnel to VPS |
| `tools/copilot_telegram_bridge/copilot-mcp-bridge.service` | systemd service on VPS |

## Available MCP Tools (5 total)

| Tool | Description |
|------|-------------|
| `await_telegram_response` | Send a question to Telegram, wait for free-text reply |
| `await_telegram_confirmation` | Send an approval request, wait for allow/deny/ask |
| `send_telegram_notification` | Send a one-way notification (no reply needed) |
| `get_pending_task` | Pop the oldest `/task` command submitted from Telegram |
| `complete_task` | Send a "task completed" notification back to Telegram |

## Telegram Commands — Complete Reference

### Approve or deny a Copilot action

```
/allowTOKEN          — Allow (inline form, no space)
/denyTOKEN           — Deny

/allow TOKEN          — Allow (space-separated form)
/deny  TOKEN  reason  — Deny with reason
/ask   TOKEN  question — Ask Copilot a follow-up question
```

Or press the **✅ Allow / ❌ Deny / ❓ Ask** inline keyboard buttons sent with the request.
You can also just **reply** to the bot message with `allow`, `yes`, `ok`, `deny`, `no`.

### Answer a free-text question from Copilot

```
/reply TOKEN your answer
```

Or simply **reply** directly to the bot's prompt message.

### Submit a task for Copilot to pick up

```
/task deploy the latest version to TariStation2
/task fix the calendar bug described earlier
/task run regression tests
```

Copilot calls `get_pending_task()` at every session start and picks up queued tasks.
The bot replies: *"✅ Task queued for Copilot…"*

---

## Setup

### A — VPS primary (default, recommended)

The bridge runs as a Docker container on `dev2null.website`. VS Code connects via SSH tunnel.

#### Step 1 — Start the SSH tunnel (required every VS Code session)

```powershell
# Windows — run mcp-tunnel.ps1 in a terminal, keep it open:
powershell -File tools\copilot_telegram_bridge\mcp-tunnel.ps1
```

```bash
# Or manually:
plink -pw "zusammen2019" -N -L 3001:127.0.0.1:3001 boh@dev2null.website
```

Keep the terminal open. VS Code connects to `http://localhost:3001/sse` via the tunnel.

#### Step 2 — Verify VPS container is running

```bash
plink -pw "zusammen2019" -batch boh@dev2null.website \
  "echo zusammen2019 | sudo -S docker ps --filter name=copilot-mcp-bridge"
```

Expected: container in state `Up`. If not:
```bash
plink -pw "zusammen2019" -batch boh@dev2null.website \
  "echo zusammen2019 | sudo -S systemctl start copilot-mcp-bridge"
```

#### Step 3 — Activate in VS Code

1. Start the SSH tunnel (Step 1)
2. Reload VS Code window (`Ctrl+Shift+P` → **Reload Window**)
3. Open Copilot Chat → switch to mode **`telegram-gated-agent`**
4. Trust the **`telegramBridge`** MCP server when prompted

#### Step 4 — Quick smoke test (while VPS is running)

```bash
python tools/copilot_telegram_bridge/scripts/test_bridge.py
```

Auto-detects VPS tunnel, sends a notification, skips interactive wait tests.
Expected output: `OK — message_ids: [...]`

#### Step 5 — Full interactive test (pause VPS container first)

```bash
# 1. Pause VPS dispatcher to avoid 409 Conflict:
plink -pw "zusammen2019" -batch boh@dev2null.website \
  "echo zusammen2019 | sudo -S docker stop copilot-mcp-bridge"

# 2. Run full test (reply from Telegram within 60 seconds):
python tools/copilot_telegram_bridge/scripts/test_bridge.py --no-wait  # notification only
# OR with VPS stopped: waits for Telegram response
python tools/copilot_telegram_bridge/scripts/test_bridge.py

# 3. Restart VPS:
plink -pw "zusammen2019" -batch boh@dev2null.website \
  "echo zusammen2019 | sudo -S systemctl start copilot-mcp-bridge"
```

---

### B — Local fallback (stdio)

Used when VPS or tunnel is unavailable. No SSH tunnel needed; VS Code spawns the Python process directly.

```json
// .vscode/mcp.json — switch "disabled" to false for telegramBridge-local
```

Set `"disabled": true` on `telegramBridge` and `"disabled": false` on `telegramBridge-local`, then reload VS Code.

---

## Deploying / Updating the VPS Container

```bash
# From project root on Windows:
bash tools/copilot_telegram_bridge/deploy-vps.sh

# Or manually:
pscp -pw "zusammen2019" tools\copilot_telegram_bridge\scripts\*.py boh@dev2null.website:/opt/copilot_docker/scripts/
plink -pw "zusammen2019" -batch boh@dev2null.website \
  "echo zusammen2019 | sudo -S docker compose -f /opt/copilot_docker/docker-compose.yml build --no-cache && \
   echo zusammen2019 | sudo -S systemctl restart copilot-mcp-bridge"
```

---

## Credentials

| Where | Variables |
|-------|-----------|
| `.env` (project root) | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| VPS `/opt/copilot_docker/.env` | same variables (pre-configured) |
| Optional | `TELEGRAM_TIMEOUT_SECONDS=900`, `TELEGRAM_LONG_POLL_SECONDS=20` |

`.env` is git-ignored. VPS `.env` is set once manually; never committed.

---

## Task Queue

The `/task` command stores tasks in a file: `/tmp/taris_tasks.json` on the VPS container.
Tasks persist across MCP server restarts within the same container run (Docker volume).

- `get_pending_task()` — pops oldest task (FIFO)
- `complete_task(summary)` — sends "✅ Copilot task completed: …" to Telegram

Copilot's `telegram-gated-agent` chat mode automatically calls `get_pending_task()` at
the start of every session.

---

## Diagnostic

```bash
python tools/copilot_telegram_bridge/scripts/diagnostic.py
```

Checks `.env`, `mcp.json`, Python imports, and VPS reachability.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ConnectionRefusedError localhost:3001` | SSH tunnel not running — start `mcp-tunnel.ps1` |
| `409 Conflict` in logs | Two pollers running — do not run `test_bridge.py` interactive tests while VPS is active |
| MCP server not showing in VS Code | Reload VS Code window after starting tunnel |
| Notification sent but no reply received | Check VPS logs: `docker logs --tail=30 copilot-mcp-bridge` |
| `/task` message not queued | Send `/task some text` (text required after `/task`) |
| Bot doesn't respond | Send `/start` to `@learninguser_bot` in Telegram first |
| Wrong `chat_id` | Run `get_chat_id.py`, update `.env`, redeploy or restart container |

