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


class _409Handler(telebot.ExceptionHandler):
    """Fast retry on Telegram 409 Conflict.

    409 means two getUpdates sessions exist simultaneously.  Rather than
    backing off (which lets the competing instance stay in control), we retry
    quickly (1-2 s) so this instance wins the next polling slot.

    A warning is logged on the first conflict.  If the conflict persists for
    more than 30 consecutive attempts, a louder warning is emitted every 30
    attempts so the operator knows another bot instance is running.
    """
    def __init__(self):
        self._count = 0

    def handle(self, exc) -> bool:
        if isinstance(exc, telebot.apihelper.ApiTelegramException) and getattr(exc, "error_code", 0) == 409:
            self._count += 1
            if self._count == 1:
                log.warning("[Bot] 409 Conflict — another getUpdates session active; retrying fast…")
            elif self._count % 30 == 0:
                log.warning(f"[Bot] 409 Conflict: {self._count} attempts — ensure no other bot instance "
                            "uses the same token (e.g. Pi service still running).")
            time.sleep(1)   # retry quickly to win the next polling slot
            return True     # handled; telebot will retry
        self._count = 0     # reset on non-409 error
        return False        # not handled; telebot logs and retries normally


bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, exception_handler=_409Handler())
