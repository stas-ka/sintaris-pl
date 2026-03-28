"""
bot_instance.py — Single shared Telegram bot instance.

Created once; imported by every module that needs to call the Telegram API.
Keeping the bot object here avoids circular imports between handler modules.
"""

import time
import logging
import telebot
from core.bot_config import BOT_TOKEN

log = logging.getLogger(__name__)

_409_BACKOFF = [30, 60, 90, 120]  # successive sleep seconds on repeated 409s


class _409Handler(telebot.ExceptionHandler):
    """Exponential-ish backoff on Telegram 409 Conflict.

    409 happens when two getUpdates sessions exist (rapid restart or another
    bot instance running the same token).  We sleep progressively longer so
    the old session can expire (Telegram long-poll timeout = 20 s).
    """
    def __init__(self):
        self._count = 0

    def handle(self, exc) -> bool:
        if isinstance(exc, telebot.apihelper.ApiTelegramException) and getattr(exc, "error_code", 0) == 409:
            delay = _409_BACKOFF[min(self._count, len(_409_BACKOFF) - 1)]
            self._count += 1
            log.warning(f"[Bot] 409 Conflict (attempt {self._count}) — sleeping {delay} s; "
                        "check that no other bot instance uses the same token.")
            time.sleep(delay)
            return True   # handled; telebot will retry
        self._count = 0   # reset on non-409 error
        return False      # not handled; telebot logs and retries normally


bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown", exception_handler=_409Handler())
