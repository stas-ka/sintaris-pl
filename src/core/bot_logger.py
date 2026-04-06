"""Structured category loggers for taris (§6.1 Logging & Monitoring).

Four category loggers write to dedicated files alongside the main telegram_bot.log:
  - assistant_log  → assistant.log   (general bot activity)
  - security_log   → security.log    (access control, injection attempts)
  - voice_log      → voice.log       (STT/TTS pipeline events)
  - datastore_log  → datastore.log   (SQLite/storage I/O)

The `TelegramAlertHandler` forwards ERROR and CRITICAL messages to all admin
chat IDs.  Call `configure_alert_handler(send_fn, admin_ids)` once during
bot startup (after the Telegram bot instance is ready).  Until then the
handler queues up to _QUEUE_LIMIT events and flushes them on first configure().

Usage in any module:
    from core.bot_logger import security_log, voice_log, datastore_log
    security_log.warning("Injection attempt blocked: %s", text[:60])

All four loggers also propagate to the root 'taris-tgbot' logger so records
appear in telegram_bot.log as well (set propagate=False to silence that).
"""
import logging
import os
import threading
from collections import deque

from core.bot_config import (
    _ASSISTANT_LOG_FILE,
    _SECURITY_LOG_FILE,
    _VOICE_LOG_FILE,
    _DATASTORE_LOG_FILE,
)

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s %(message)s"
_QUEUE_LIMIT = 50   # max events buffered before configure() is called


# ─────────────────────────────────────────────────────────────────────────────
# Category file logger factory
# ─────────────────────────────────────────────────────────────────────────────

def _make_logger(name: str, path: str) -> logging.Logger:
    """Return a logger that writes to *path* and propagates to taris-tgbot."""
    logger = logging.getLogger(f"taris.{name}")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except OSError:
            pass
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(fh)
    # Propagate = True → records also appear in telegram_bot.log (main log)
    logger.propagate = True
    return logger


assistant_log = _make_logger("assistant", _ASSISTANT_LOG_FILE)
security_log  = _make_logger("security",  _SECURITY_LOG_FILE)
voice_log     = _make_logger("voice",     _VOICE_LOG_FILE)
datastore_log = _make_logger("datastore", _DATASTORE_LOG_FILE)


# ─────────────────────────────────────────────────────────────────────────────
# Telegram critical/error alert handler
# ─────────────────────────────────────────────────────────────────────────────

class _TelegramAlertHandler(logging.Handler):
    """Forward ERROR+ records to all admin Telegram chat IDs.

    Buffers up to _QUEUE_LIMIT records while not yet configured.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.setFormatter(logging.Formatter("%(message)s"))
        self._send_fn = None          # callable(chat_id: int, text: str)
        self._admin_ids: list[int] = []
        self._lock = threading.Lock()
        self._queue: deque = deque(maxlen=_QUEUE_LIMIT)
        self._configured = False

    def configure(self, send_fn, admin_ids: list[int]) -> None:
        """Enable alert forwarding.  Call once after bot instance is ready."""
        with self._lock:
            self._send_fn = send_fn
            self._admin_ids = list(admin_ids)
            self._configured = True
            queued = list(self._queue)
            self._queue.clear()

        # Flush buffered records outside the lock
        for record in queued:
            self._forward(record)

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock:
            if not self._configured:
                self._queue.append(record)
                return
            fn    = self._send_fn
            ids   = list(self._admin_ids)
        self._forward(record, fn=fn, ids=ids)

    def _forward(self, record: logging.LogRecord, fn=None, ids=None) -> None:
        if fn is None:
            with self._lock:
                fn  = self._send_fn
                ids = list(self._admin_ids)
        if not fn or not ids:
            return
        try:
            icon = "🚨" if record.levelno >= logging.CRITICAL else "⚠️"
            msg  = self.format(record)
            text = f"{icon} *\\[{record.levelname}\\]* `{record.name}`\n{msg[:900]}"
            for chat_id in ids:
                try:
                    fn(chat_id, text, parse_mode="Markdown")
                except Exception:
                    pass
        except Exception:
            self.handleError(record)


_alert_handler = _TelegramAlertHandler()


def configure_alert_handler(send_fn, admin_ids: list[int]) -> None:
    """Enable Telegram ERROR/CRITICAL alerts.  Call once in main() after bot init."""
    _alert_handler.configure(send_fn, admin_ids)


def attach_alerts_to_main_log() -> None:
    """Attach the alert handler to the main taris-tgbot logger.

    Call this from telegram_menu_bot.main() after configure_alert_handler().
    """
    main_log = logging.getLogger("taris-tgbot")
    if _alert_handler not in main_log.handlers:
        main_log.addHandler(_alert_handler)
    # Also attach to all category loggers
    for logger in (assistant_log, security_log, voice_log, datastore_log):
        if _alert_handler not in logger.handlers:
            logger.addHandler(_alert_handler)


# ─────────────────────────────────────────────────────────────────────────────
# Log tail helper (used by admin Telegram UI)
# ─────────────────────────────────────────────────────────────────────────────

def tail_log(path: str, n: int = 50) -> str:
    """Return the last *n* lines of *path*, or an error message.

    Uses the system ``tail`` command to avoid loading multi-MB log files into
    RAM — critical on memory-constrained machines where a full readlines() on a
    7 MB log file can stall the process for tens of seconds due to swap I/O.
    Falls back to a pure-Python seek-based reader if ``tail`` is unavailable.
    """
    import subprocess as _sp
    try:
        if not os.path.isfile(path):
            return f"(log file not found: {path})"
        result = _sp.run(
            ["tail", "-n", str(n), path],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=5,
        )
        chunk = result.stdout
        if not chunk.strip():
            return "(log is empty)"
        return chunk
    except (FileNotFoundError, _sp.TimeoutExpired):
        # Fallback: seek to near-end, read a bounded window (max 64 KB)
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 65536))
                raw = f.read().decode("utf-8", errors="replace")
            lines = raw.splitlines()[-n:]
            chunk = "\n".join(lines)
            return chunk if chunk.strip() else "(log is empty)"
        except OSError as exc:
            return f"(error reading log: {exc})"
    except OSError as exc:
        return f"(error reading log: {exc})"
