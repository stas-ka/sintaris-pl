"""
pytest fixtures for Screen DSL loader tests.

Pure-Python tests — no Telegram, no Pi, no network.
screen_loader.py only imports from ui.bot_ui (dataclasses) + stdlib.
"""

import sys
import os

# ---------------------------------------------------------------------------
# 1.  Environment — must come first so bot_config.py skips hard checks.
# ---------------------------------------------------------------------------
os.environ.setdefault("WEB_ONLY", "1")
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ALLOWED_USERS", "111111")
os.environ.setdefault("ADMIN_USERS", "999999")

# ---------------------------------------------------------------------------
# 2.  Add src/ to sys.path so "from ui.screen_loader import …" works.
# ---------------------------------------------------------------------------
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
