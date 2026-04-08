#!/usr/bin/env python3
"""
Helper: find your Telegram chat_id after sending /start to @learninguser_bot.

Usage:
    python tools/copilot_telegram_bridge/scripts/get_chat_id.py

After it prints your chat_id, paste it into .env:
    TELEGRAM_CHAT_ID=<number>
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]  # scripts/ -> copilot_telegram_bridge/ -> tools/ -> workspace root
ENV_FILE = _ROOT / ".env"

# Load token from .env
def _load_token() -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"")
    # fallback to env var
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")

BOT_TOKEN = _load_token()
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def _get(endpoint: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{qs}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.load(resp)


def _patch_env(chat_id: int) -> None:
    if not ENV_FILE.exists():
        print(f"NOTE: .env not found at {ENV_FILE}, cannot auto-patch.")
        return
    content = ENV_FILE.read_text(encoding="utf-8")
    if f"TELEGRAM_CHAT_ID={chat_id}" in content:
        print(".env already has correct TELEGRAM_CHAT_ID.")
        return
    # Replace blank or existing value
    import re
    new_content = re.sub(
        r"(?m)^TELEGRAM_CHAT_ID=.*$",
        f"TELEGRAM_CHAT_ID={chat_id}",
        content,
    )
    if new_content == content:
        # Key doesn't exist yet — append
        new_content = content.rstrip() + f"\nTELEGRAM_CHAT_ID={chat_id}\n"
    ENV_FILE.write_text(new_content, encoding="utf-8")
    print(f"✅  Patched .env: TELEGRAM_CHAT_ID={chat_id}")


def main() -> None:
    print("🔍  Fetching updates from @learninguser_bot …")
    print("   If no result appears, open Telegram, find @learninguser_bot and send /start")
    print()

    for attempt in range(12):          # poll for up to ~60 s
        try:
            data = _get("getUpdates", {"limit": "20", "timeout": "5"})
        except Exception as exc:
            print(f"  Error calling Telegram: {exc}")
            sys.exit(1)

        updates = data.get("result", [])
        ids: dict[int, str] = {}
        for u in updates:
            msg = u.get("message") or u.get("edited_message") or {}
            chat = msg.get("chat", {})
            frm = msg.get("from", {})
            cid = chat.get("id")
            if cid:
                username = frm.get("username", "")
                name = frm.get("first_name", "")
                ids[cid] = f"@{username}" if username else name

        if ids:
            print("Found the following chat_id(s):\n")
            for cid, label in ids.items():
                print(f"  chat_id = {cid}   ({label})")
            print()
            # Auto-patch .env with last (most recent) chat_id
            last_cid = list(ids.keys())[-1]
            _patch_env(last_cid)
            print()
            print("Next steps:")
            print("  1. Reload VS Code window (Ctrl+Shift+P → Reload Window)")
            print("  2. Open Copilot Chat → select mode 'telegram-gated-agent'")
            print("  3. Enable the 'telegramBridge' MCP server when prompted")
            return

        if attempt < 11:
            sys.stdout.write(f"\r  Waiting for /start message … ({attempt + 1}/12)")
            sys.stdout.flush()
            time.sleep(5)

    print("\n❌  No messages received. Please send /start to @learninguser_bot in Telegram and re-run.")


if __name__ == "__main__":
    main()
