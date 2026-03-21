"""
bot_email.py — "Send as Email" feature for Notes, Mail Digest, and Calendar events.

Design:
  • Uses the per-user IMAP app-password (from features.bot_mail_creds) to also send via SMTP.
    No additional credentials needed — the same Gmail/Yandex/Mail.ru App Password
    that already works for IMAP reading also works for SMTP sending.
  • Per-user recipient address stored at ~/.taris/mail_creds/<chat_id>_email_target.txt
    (a plain text file with a single email address).
  • First use: bot asks "Enter recipient email". Reply is stored & email sent immediately.
  • Subsequent uses: email sent directly using stored recipient.
  • Admin can change the recipient by tapping the button again when on the /email_settings
    callback, OR by re-entering through the prompt trigger.

Dependency chain:
    bot_config → bot_state → bot_instance → bot_access → bot_mail_creds → bot_email

SECURITY:
  • Stored recipient email is never echoed in full — only shown as masked@domain.
  • App Password is read from the IMAP creds file and never logged.
  • Email body is limited to SEND_MAX_CHARS to prevent accidental data leakage.
  • SMTP connection uses SSL (port 465).
"""

import re
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import core.bot_state as _st
from core.bot_config import MAIL_CREDS_DIR, log
from core.bot_instance import bot
from telegram.bot_access import _t, _back_keyboard
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SEND_MAX_CHARS = 8000   # max body length for outgoing emails

# Mapping imap host prefix → smtp host (best-effort for known providers)
_SMTP_MAP: dict[str, tuple[str, int]] = {
    "imap.gmail.com":   ("smtp.gmail.com",   465),
    "imap.yandex.ru":   ("smtp.yandex.ru",   465),
    "imap.yandex.com":  ("smtp.yandex.com",  465),
    "imap.mail.ru":     ("smtp.mail.ru",      465),
    "imap.rambler.ru":  ("smtp.rambler.ru",   465),
}

# Multi-step state  {chat_id: {"subject": ..., "body": ..., "source": ...}}
_pending_email_send: dict[int, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Storage helpers
# ─────────────────────────────────────────────────────────────────────────────

def _target_file(chat_id: int) -> Path:
    return Path(MAIL_CREDS_DIR) / f"{chat_id}_email_target.txt"


def _get_target_email(chat_id: int) -> Optional[str]:
    f = _target_file(chat_id)
    if not f.exists():
        return None
    addr = f.read_text(encoding="utf-8").strip()
    return addr if addr else None


def _set_target_email(chat_id: int, addr: str) -> None:
    Path(MAIL_CREDS_DIR).mkdir(parents=True, exist_ok=True)
    _target_file(chat_id).write_text(addr.strip(), encoding="utf-8")


def _mask_addr(addr: str) -> str:
    """user@domain.com → u***@domain.com"""
    if "@" not in addr:
        return "***"
    local, domain = addr.split("@", 1)
    return local[0] + "***@" + domain


def _smtp_host_port(imap_host: str) -> tuple[str, int]:
    """Derive SMTP host from IMAP host.  Falls back to replacing 'imap.' → 'smtp.'."""
    if imap_host in _SMTP_MAP:
        return _SMTP_MAP[imap_host]
    if imap_host.startswith("imap."):
        return "smtp." + imap_host[5:], 465
    return imap_host, 465


# ─────────────────────────────────────────────────────────────────────────────
# SMTP send
# ─────────────────────────────────────────────────────────────────────────────

def _do_smtp_send(
    from_email: str,
    app_password: str,
    smtp_host: str,
    smtp_port: int,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    """Core SMTP-SSL send.  Raises smtplib.SMTPException on failure."""
    msg = MIMEMultipart("alternative")
    msg["From"]    = from_email
    msg["To"]      = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body[:SEND_MAX_CHARS], "plain", "utf-8"))

    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
        server.login(from_email, app_password)
        server.sendmail(from_email, to_addr, msg.as_string())


def _send_in_thread(chat_id: int, msg_id: int, subject: str, body: str) -> None:
    """Background thread: resolve creds → SMTP → edit spinner message."""
    # import here to avoid circular dep at module load time
    from features.bot_mail_creds import _load_creds

    creds = _load_creds(chat_id)
    if not creds or not creds.get("email") or not creds.get("app_password"):
        _edit_or_send(chat_id, msg_id, _t(chat_id, "email_no_mail_creds"))
        return

    target = _get_target_email(chat_id)
    if not target:
        _edit_or_send(chat_id, msg_id, _t(chat_id, "email_no_target"))
        return

    imap_host  = creds.get("imap_host", "imap.gmail.com")
    smtp_host, smtp_port = _smtp_host_port(imap_host)

    try:
        _do_smtp_send(
            from_email=creds["email"],
            app_password=creds["app_password"],
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            to_addr=target,
            subject=subject,
            body=body,
        )
        log.info(f"[Email] user {chat_id} sent '{subject[:40]}' via {smtp_host}")
        _edit_or_send(
            chat_id, msg_id,
            _t(chat_id, "email_sent_ok", to=_mask_addr(target)),
            reply_markup=_back_keyboard(),
        )
    except smtplib.SMTPAuthenticationError:
        _edit_or_send(chat_id, msg_id, _t(chat_id, "email_auth_fail"), reply_markup=_back_keyboard())
    except smtplib.SMTPException as e:
        log.warning(f"[Email] SMTP error for {chat_id}: {e}")
        _edit_or_send(chat_id, msg_id, _t(chat_id, "email_send_fail", err=str(e)[:120]), reply_markup=_back_keyboard())
    except Exception as e:
        log.exception(f"[Email] unexpected error for {chat_id}: {e}")
        _edit_or_send(chat_id, msg_id, _t(chat_id, "email_send_fail", err=str(e)[:120]), reply_markup=_back_keyboard())


def _edit_or_send(chat_id: int, msg_id: int, text: str, reply_markup=None) -> None:
    try:
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=reply_markup)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────────────

def handle_send_email(chat_id: int, subject: str, body: str) -> None:
    """
    Primary dispatcher.  Called when user taps any "📧 Send as email" button.
    - If target email already stored → send immediately.
    - Otherwise → enter "email_set_target" mode, ask for address.
    """
    from features.bot_mail_creds import _mail_has_creds

    if not _mail_has_creds(chat_id):
        bot.send_message(
            chat_id,
            _t(chat_id, "email_no_mail_creds"),
            parse_mode="Markdown",
            reply_markup=_back_keyboard(),
        )
        return

    _pending_email_send[chat_id] = {"subject": subject, "body": body}
    target = _get_target_email(chat_id)

    if target:
        # Target known — send directly with change-option keyboard
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(
                _t(chat_id, "email_btn_change_target"),
                callback_data="email_change_target",
            ),
            InlineKeyboardButton("🔙  Menu", callback_data="menu"),
        )
        msg = bot.send_message(
            chat_id,
            _t(chat_id, "email_sending", to=_mask_addr(target)),
            parse_mode="Markdown",
            reply_markup=kb,
        )
        threading.Thread(
            target=_send_in_thread,
            args=(chat_id, msg.message_id, subject, body),
            daemon=True,
        ).start()
    else:
        # No target — ask for it
        _st._user_mode[chat_id] = "email_set_target"
        bot.send_message(
            chat_id,
            _t(chat_id, "email_ask_target"),
            parse_mode="Markdown",
        )


def handle_email_change_target(chat_id: int) -> None:
    """User wants to change the stored recipient address."""
    _st._user_mode[chat_id] = "email_set_target"
    bot.send_message(
        chat_id,
        _t(chat_id, "email_ask_target"),
        parse_mode="Markdown",
    )


def finish_email_set_target(chat_id: int, text: str) -> None:
    """
    Text handler for "email_set_target" mode.
    Validates the address, saves it, then proceeds to send any pending email.
    """
    addr = text.strip()
    _st._user_mode.pop(chat_id, None)

    if not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", addr):
        bot.send_message(
            chat_id,
            _t(chat_id, "email_invalid_addr"),
            parse_mode="Markdown",
            reply_markup=_back_keyboard(),
        )
        _pending_email_send.pop(chat_id, None)
        return

    _set_target_email(chat_id, addr)

    pending = _pending_email_send.pop(chat_id, None)
    if pending:
        subject = pending.get("subject", "")
        body    = pending.get("body", "")
        msg = bot.send_message(
            chat_id,
            _t(chat_id, "email_sending", to=_mask_addr(addr)),
            parse_mode="Markdown",
        )
        threading.Thread(
            target=_send_in_thread,
            args=(chat_id, msg.message_id, subject, body),
            daemon=True,
        ).start()
    else:
        bot.send_message(
            chat_id,
            _t(chat_id, "email_target_saved", to=_mask_addr(addr)),
            parse_mode="Markdown",
            reply_markup=_back_keyboard(),
        )
