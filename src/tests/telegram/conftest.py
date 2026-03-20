"""
pytest fixtures for Telegram bot regression tests.

All tests run offline — no live Telegram API calls are made.
The bot module is imported with `telebot.TeleBot` fully mocked so that
`bot.send_message / send_voice / answer_callback_query` are captured as
MagicMock calls.

Bootstrap order matters:
  1. Set env vars (WEB_ONLY, BOT_TOKEN, ALLOWED_USERS) BEFORE any import.
  2. Stub telebot + heavy optional deps in sys.modules.
  3. Add src/ to sys.path.
  4. Now all project imports succeed.
"""

import sys
import os
from unittest.mock import MagicMock
import pytest

# ---------------------------------------------------------------------------
# 1.  Environment — must come first so bot_config.py skips the hard checks.
# ---------------------------------------------------------------------------
os.environ.setdefault("WEB_ONLY", "1")          # bypass BOT_TOKEN RuntimeError
os.environ.setdefault("BOT_TOKEN", "test-token-for-testing")
os.environ.setdefault("ALLOWED_USERS", "111111,222222")
os.environ.setdefault("ADMIN_USERS", "999999")

# ---------------------------------------------------------------------------
# 2.  Stub telebot BEFORE any import so bot_instance.py does not hit the
#     live Telegram API.
# ---------------------------------------------------------------------------
def _passthrough_deco(*args, **kwargs):
    """Decorator factory: @bot.message_handler(...) must return the real fn unchanged."""
    def _deco(fn):
        return fn
    return _deco

_bot_instance = MagicMock(name="TeleBot_instance")
_bot_instance.message_handler.side_effect = _passthrough_deco
_bot_instance.callback_query_handler.side_effect = _passthrough_deco

_telebot_stub = MagicMock(name="telebot")
_telebot_stub.TeleBot.return_value = _bot_instance
sys.modules.setdefault("telebot", _telebot_stub)
sys.modules.setdefault("telebot.apihelper", MagicMock())
sys.modules.setdefault("telebot.types", MagicMock())

# Stub heavy optional Pi-side dependencies.
for _name in ("vosk", "webrtcvad", "sounddevice", "sqlite_vec", "cryptography",
              "cryptography.fernet"):
    sys.modules.setdefault(_name, MagicMock())

# ---------------------------------------------------------------------------
# 3.  Add src/ to sys.path so "from core.bot_config import …" works.
# ---------------------------------------------------------------------------
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# ---------------------------------------------------------------------------
# 4.  Pre-register the CORRECT `telegram` package from src/telegram/ before
#     pytest can shadow it with the tests/telegram/ directory.
#     (pytest adds src/tests/ to sys.path because this directory has
#      __init__.py, which would make "from telegram.xxx" find the wrong pkg.)
# ---------------------------------------------------------------------------
import importlib.util as _ilu
_tel_init = os.path.join(SRC_DIR, "telegram", "__init__.py")
_tel_spec = _ilu.spec_from_file_location(
    "telegram", _tel_init,
    submodule_search_locations=[os.path.join(SRC_DIR, "telegram")],
)
_tel_mod = _ilu.module_from_spec(_tel_spec)
sys.modules["telegram"] = _tel_mod      # force correct package before conftest finishes
_tel_spec.loader.exec_module(_tel_mod)  # __init__.py is empty — always safe


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_bot():
    """Return a MagicMock that impersonates a telebot.TeleBot instance."""
    bot = MagicMock(name="TeleBot")
    bot.send_message.return_value = MagicMock(message_id=100)
    bot.send_voice.return_value = MagicMock(message_id=101)
    bot.edit_message_text.return_value = MagicMock()
    bot.answer_callback_query.return_value = None
    bot.get_file.return_value = MagicMock(file_path="voice/file_123.ogg")
    bot.download_file.return_value = b"fake-ogg-bytes"
    return bot


def _make_user(
    chat_id: int,
    username: str = "testuser",
    language_code: str = "ru",
    first_name: str = "Test",
):
    """Build a minimal Telegram User-like object."""
    u = MagicMock()
    u.id = chat_id
    u.username = username
    u.language_code = language_code
    u.first_name = first_name
    return u


def _make_message(
    chat_id: int,
    text: str = "",
    message_id: int = 1,
    content_type: str = "text",
    **kwargs,
):
    """Build a minimal Telegram Message-like object."""
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id)
    msg.message_id = message_id
    msg.text = text
    msg.content_type = content_type
    msg.from_user = _make_user(chat_id)
    for k, v in kwargs.items():
        setattr(msg, k, v)
    return msg


def _make_callback(
    chat_id: int,
    data: str,
    message_id: int = 1,
):
    """Build a minimal Telegram CallbackQuery-like object."""
    call = MagicMock()
    call.from_user = _make_user(chat_id)
    call.message = _make_message(chat_id, message_id=message_id)
    call.data = data
    call.id = "cb_001"
    return call


@pytest.fixture()
def make_message():
    """Factory fixture: returns a callable that creates mock Messages."""
    return _make_message


@pytest.fixture()
def make_callback():
    """Factory fixture: returns a callable that creates mock CallbackQuerys."""
    return _make_callback


@pytest.fixture()
def admin_chat_id():
    """A chat_id that is treated as admin by ADMIN_USERS."""
    from core.bot_config import ADMIN_USERS
    if ADMIN_USERS:
        return next(iter(ADMIN_USERS))
    return 999999  # fallback — tests that use this must patch ADMIN_USERS


@pytest.fixture()
def user_chat_id():
    """A chat_id that is in ALLOWED_USERS (not admin)."""
    from core.bot_config import ALLOWED_USERS, ADMIN_USERS
    for uid in ALLOWED_USERS:
        if uid not in ADMIN_USERS:
            return uid
    return 111111  # fallback


@pytest.fixture()
def stranger_chat_id():
    """A chat_id not in any allowed set."""
    return 999888777
