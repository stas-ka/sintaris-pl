# Copilot Telegram MCP Bridge

Adds Telegram-based notifications and interaction for GitHub Copilot Chat (VS Code)
and Copilot CLI via **@su_vscnotifier_bot** (`@learninguser_bot`):

- MCP tools: Telegram Q&A, confirmation requests, one-way notifications
- A `PreToolUse` hook that routes tool approval to Telegram
- A custom chat mode `telegram-gated-agent` that tells Copilot to ask via Telegram

## Files

| File | Purpose |
|------|---------|
| `.vscode/mcp.json` | MCP server registration (`telegramBridge`) |
| `.vscode/settings.json` | `PreToolUse` hook registration |
| `.github/chatmodes/telegram-gated-agent.chatmode.md` | Custom Copilot chat mode |
| `tools/copilot_telegram_bridge/scripts/telegram_bridge.py` | Shared Telegram HTTP client |
| `tools/copilot_telegram_bridge/scripts/mcp_server.py` | FastMCP server (3 tools) |
| `tools/copilot_telegram_bridge/scripts/telegram_pre_tool_use.py` | `PreToolUse` hook script |
| `tools/copilot_telegram_bridge/scripts/get_chat_id.py` | Helper: find your chat_id |
| `tools/copilot_telegram_bridge/scripts/test_bridge.py` | Integration test (3 scenarios) |
| `tools/copilot_telegram_bridge/scripts/diagnostic.py` | Setup diagnostic |
| `tools/copilot_telegram_bridge/scripts/requirements.txt` | Python dependency (`mcp`) |

## Setup (one-time)

### Step 1 — Install Python dependency

```bash
# Using system Python:
python -m pip install mcp

# Or install from requirements.txt:
pip install -r tools/copilot_telegram_bridge/scripts/requirements.txt
```

### Step 2 — Verify .env credentials

The `.env` file at the workspace root must contain:

```env
TELEGRAM_BOT_TOKEN=<bot_token>
TELEGRAM_CHAT_ID=<your_chat_id>
TELEGRAM_TIMEOUT_SECONDS=900
TELEGRAM_LONG_POLL_SECONDS=20
```

Credentials are pre-filled. If not set, run:

```bash
# Find your chat_id (send /start to @learninguser_bot first):
python tools/copilot_telegram_bridge/scripts/get_chat_id.py
```

### Step 3 — Activate in VS Code

1. **Reload** the VS Code window (`Ctrl+Shift+P` → **Reload Window**)
2. Open Copilot Chat panel
3. Switch to mode **`telegram-gated-agent`** (dropdown in the chat input)
4. Enable/trust the **`telegramBridge`** MCP server when VS Code shows the security prompt

### Step 4 — Test the setup

```bash
python tools/copilot_telegram_bridge/scripts/test_bridge.py
```

Sends a notification, an approval request, and a question to Telegram to confirm
all three tool flows work.

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `await_telegram_response` | Send a question to Telegram, wait for free-text reply |
| `await_telegram_confirmation` | Send an approval request, wait for allow/deny/ask |
| `send_telegram_notification` | Send a one-way notification (no reply needed) |

## Telegram Reply Commands

### Free-text response (Q&A)

```
/reply <TOKEN> <your answer>
```
Or simply **reply** directly to the bot's prompt message.

### Tool approval (PreToolUse hook)

```
/allow <TOKEN>
/deny  <TOKEN>  [optional reason]
/ask   <TOKEN>  [optional question back]
```

If no reply arrives before timeout (default 900 s = 15 min), VS Code falls back
to its default confirmation UI.

## Credentials

| Where | Variables |
|-------|-----------|
| `.env` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_TIMEOUT_SECONDS`, `TELEGRAM_LONG_POLL_SECONDS` |

Credentials are loaded automatically by both the MCP server and the hook script
from the workspace root `.env` file. `.env` is git-ignored.

## Diagnostic

```bash
python tools/copilot_telegram_bridge/scripts/diagnostic.py
```

Checks `.env`, `mcp.json`, and Python imports. Run first if something doesn't work.

## Troubleshooting

**MCP server fails to start** — verify `mcp` is installed: `python -c "import mcp"`.

**Hook script not running** — check `settings.json` path matches exactly.

**Timeout with no response** — send `/start` to `@learninguser_bot` in Telegram first, then re-run.

**Wrong chat_id** — edit `.env` → `TELEGRAM_CHAT_ID=<correct number>` and reload VS Code.
