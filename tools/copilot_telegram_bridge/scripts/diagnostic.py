#!/usr/bin/env python3
"""Quick diagnostic for Telegram Bridge MCP setup."""

import os
import sys
from pathlib import Path

print("=" * 70)
print("TELEGRAM BRIDGE MCP SETUP DIAGNOSTIC")
print("=" * 70)

# Check .env file
env_file = Path('.env')
print(f"\n1. Environment File (.env)")
print(f"   Location: {env_file.absolute()}")
print(f"   Exists: {env_file.exists()}")

if env_file.exists():
    with open(env_file) as f:
        content = f.read()
    
    telegram_token = "TELEGRAM_BOT_TOKEN" in content
    telegram_chat_id = "TELEGRAM_CHAT_ID" in content
    pg_user = "PGUSER" in content
    
    print(f"   Has TELEGRAM_BOT_TOKEN: {telegram_token}")
    print(f"   Has TELEGRAM_CHAT_ID: {telegram_chat_id}")
    print(f"   Has PGUSER: {pg_user}")
    
    if telegram_token and telegram_chat_id:
        # Load and check values
        for line in content.split('\n'):
            if line.startswith('TELEGRAM_BOT_TOKEN='):
                token = line.split('=', 1)[1]
                print(f"   Token starts with: {token[:20]}...")
            if line.startswith('TELEGRAM_CHAT_ID='):
                chat_id = line.split('=', 1)[1]
                print(f"   Chat ID: {chat_id}")
else:
    print("   ❌ .env file NOT FOUND")
    print("   → Run: cp .env.example .env")

# Check MCP configuration
print(f"\n2. MCP Configuration")
mcp_config = Path('.vscode/mcp.json')
print(f"   Location: {mcp_config.absolute()}")
print(f"   Exists: {mcp_config.exists()}")

if mcp_config.exists():
    import json
    with open(mcp_config) as f:
        config = json.load(f)
    
    has_telegram = "telegramBridge" in config.get("servers", {})
    print(f"   Has telegramBridge server: {has_telegram}")
    
    if has_telegram:
        server = config["servers"]["telegramBridge"]
        print(f"   Type: {server.get('type')}")
        print(f"   Command: {server.get('command', 'N/A')[:50]}...")

# Check MCP tools
print(f"\n3. MCP Tools (Telegram Bridge)")
mcp_server = Path('tools/copilot_telegram_bridge/scripts/mcp_server.py')
print(f"   Location: {mcp_server.absolute()}")
print(f"   Exists: {mcp_server.exists()}")

if mcp_server.exists():
    with open(mcp_server) as f:
        content = f.read()
    
    has_response_tool = "await_telegram_response" in content
    has_confirmation_tool = "await_telegram_confirmation" in content
    has_notification_tool = "send_telegram_notification" in content
    
    print(f"   Has await_telegram_response: {has_response_tool}")
    print(f"   Has await_telegram_confirmation: {has_confirmation_tool}")
    print(f"   Has send_telegram_notification: {has_notification_tool}")

# Check Python MCP library
print(f"\n4. Python Dependencies")
try:
    from mcp.server.fastmcp import FastMCP
    print(f"   MCP library: ✅ Installed")
except ImportError:
    print(f"   MCP library: ❌ Not installed")
    print("   → Run: pip install mcp")

try:
    import telegram
    print(f"   python-telegram-bot: ✅ Installed")
except ImportError:
    print(f"   python-telegram-bot: ❌ Not installed")
    print("   → Run: pip install python-telegram-bot")

# Check VSCode settings
print(f"\n5. VSCode Settings")
settings_file = Path('.vscode/settings.json')
print(f"   Location: {settings_file.absolute()}")
print(f"   Exists: {settings_file.exists()}")

if settings_file.exists():
    import json
    with open(settings_file) as f:
        settings = json.load(f)
    
    has_hooks = "chat.hooks" in settings
    has_pretool = False
    if has_hooks:
        pre_hooks = settings.get("chat.hooks", {}).get("PreToolUse", [])
        has_pretool = len(pre_hooks) > 0
    
    print(f"   Has chat.hooks: {has_hooks}")
    print(f"   Has PreToolUse hook: {has_pretool}")

# Summary
print(f"\n" + "=" * 70)
print("SUMMARY & NEXT STEPS")
print("=" * 70)

required_items = [
    env_file.exists(),
    mcp_config.exists(),
    mcp_server.exists(),
]

if all(required_items):
    print("\n✅ Basic setup is COMPLETE")
    print("\nTo test Telegram notifications:")
    print("  1. Send /start to @learninguser_bot on Telegram")
    print("  2. Run: python tools/copilot_telegram_bridge/scripts/test_bridge.py")
    print("  3. Check Telegram for test message")
else:
    print("\n❌ Setup is INCOMPLETE")
    print("\nTo complete setup:")
    print("  1. Create .env: cp .env.example .env")
    print("  2. Edit .env with your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    print("  3. Install dependencies: pip install mcp python-telegram-bot")
    print("  4. Run this script again to verify")

print("\n" + "=" * 70)
