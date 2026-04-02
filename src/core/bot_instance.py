"""
bot_instance.py — Single shared Telegram bot instance.

Created once; imported by every module that needs to call the Telegram API.
Keeping the bot object here avoids circular imports between handler modules.
"""

import socket
import time
import logging
import requests
from requests.adapters import HTTPAdapter
import telebot
import telebot.apihelper
from core.bot_config import BOT_TOKEN

log = logging.getLogger(__name__)

# Suppress telebot's verbose ReadTimeout/network-error tracebacks.
# On flaky connections (e.g. SintAItion) telebot logs ERROR-level tracebacks
# every ~90s. Recovery is automatic (infinity_polling); the noise is not useful.
logging.getLogger("TeleBot").setLevel(logging.CRITICAL)


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


bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode=None,
    exception_handler=_409Handler(),
    # 16 worker threads: prevents menu callbacks from queuing behind slow LLM/STT handlers.
    # Default is 2 — one LLM call (up to 60s) blocks ALL other callbacks when pool exhausted.
    num_threads=16,
)


class _KeepAliveAdapter(HTTPAdapter):
    """HTTP adapter with TCP keepalive probes.

    Prevents home-router stateful-firewall state (IPv6 or NAT) from being
    silently dropped on idle connections.  Without keepalive the next request
    on a stale connection hangs ~48 s until the OS TCP timeout fires.

    Parameters match Fritz!Box firewall defaults:
      KEEPIDLE  30 s  — first probe after 30 s idle (well inside any 60 s timeout)
      KEEPINTVL 10 s  — repeat probes every 10 s
      KEEPCNT    5    — give up after 5 missed probes (50 s total)
    """
    def init_poolmanager(self, *args, **kwargs):
        kwargs["socket_options"] = [
            (socket.SOL_SOCKET,  socket.SO_KEEPALIVE,      1),
            (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE,     30),
            (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL,    10),
            (socket.IPPROTO_TCP, socket.TCP_KEEPCNT,       5),
        ]
        super().init_poolmanager(*args, **kwargs)


# Inject the keepalive session into telebot's HTTP layer.
# telebot.apihelper.session is used by all API calls (shared across worker threads).
_api_session = requests.Session()
_api_session.mount("https://", _KeepAliveAdapter())
_api_session.mount("http://",  _KeepAliveAdapter())
telebot.apihelper.session = _api_session
log.info("[Bot] TCP keepalive configured on Telegram API session (IDLE=30s INTVL=10s CNT=5)")
