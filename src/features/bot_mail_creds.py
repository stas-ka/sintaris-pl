"""
bot_mail_creds.py — Per-user mail credential management and personalised digest runner.

Features:
  • Per-user credential storage: ~/.taris/mail_creds/<chat_id>.json  (chmod 600)
  • GDPR (EU Reg. 2016/679) + Russian 152-FZ consent gate before any credential setup
  • Supported providers: Gmail, Yandex Mail, Mail.ru, Custom IMAP
  • Per-user digest: inline IMAP fetch + LLM summarisation via _ask_taris()
  • Per-user last-digest cache: ~/.taris/mail_creds/<chat_id>_last_digest.txt
  • Full credential lifecycle: setup wizard → test connection → view → delete

Dependency chain:  bot_config → bot_state → bot_instance → bot_access → bot_mail_creds

SECURITY NOTES:
  • Credentials are stored ONLY on the Raspberry Pi device (never transmitted to any
    third-party server other than the user's own mail provider IMAP endpoint).
  • Files are chmod 600 (owner read/write only) immediately after writing.
  • App Passwords rather than account passwords are encouraged for all providers.
  • Passwords are NEVER echoed back to the user in any bot message.
  • Setup state (_pending_mail_setup) is cleared on cancel / /menu.
"""

import email
import imaplib
import json
import os
import re
import stat
import threading
import time
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from pathlib import Path
from typing import Optional

import core.bot_state as _st
from core.bot_config import MAIL_CREDS_DIR, log
from core.store import store
from core.bot_instance import bot
from core.bot_prompts import PROMPTS
from telegram.bot_access import (
    _t, _escape_md, _truncate, _back_keyboard, _send_menu, _ask_taris,
    _is_guest,
)
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ─────────────────────────────────────────────────────────────────────────────
# Provider presets
# ─────────────────────────────────────────────────────────────────────────────

PROVIDERS: dict[str, dict] = {
    "gmail": {
        "label":       "Gmail (Google)",
        "imap_host":   "imap.gmail.com",
        "imap_port":   993,
        "spam_folder": "[Google Mail]/Spam",
        "hint_ru": (
            "Используйте *Пароль приложения* Google — не основной пароль.\n"
            "Настройки Google → Безопасность → Пароли приложений."
        ),
        "hint_en": (
            "Use a Google *App Password* — not your main account password.\n"
            "Google Settings → Security → App Passwords."
        ),
        "hint_de": (
            "Verwenden Sie ein Google *App-Passwort* — nicht Ihr Hauptkontokennwort.\n"
            "Google-Einstellungen → Sicherheit → App-Passwörter."
        ),
    },
    "yandex": {
        "label":       "Яндекс.Почта",
        "imap_host":   "imap.yandex.ru",
        "imap_port":   993,
        "spam_folder": "Spam",
        "hint_ru": (
            "Включите IMAP в настройках Яндекс.Почты.\n"
            "Можно использовать пароль приложения или основной пароль."
        ),
        "hint_en": (
            "Enable IMAP in Yandex Mail settings.\n"
            "You can use an app password or your main password."
        ),
        "hint_de": (
            "Aktivieren Sie IMAP in den Yandex Mail-Einstellungen.\n"
            "Sie können ein App-Passwort oder Ihr Hauptpasswort verwenden."
        ),
    },
    "mailru": {
        "label":       "Mail.ru",
        "imap_host":   "imap.mail.ru",
        "imap_port":   993,
        "spam_folder": "Spam",
        "hint_ru": (
            "Включите IMAP в настройках Mail.ru.\n"
            "Используйте пароль приложения (рекомендуется)."
        ),
        "hint_en": (
            "Enable IMAP in Mail.ru settings.\n"
            "Use an app password (recommended)."
        ),
        "hint_de": (
            "Aktivieren Sie IMAP in den Mail.ru-Einstellungen.\n"
            "Verwenden Sie ein App-Passwort (empfohlen)."
        ),
    },
    "custom": {
        "label":       "Custom IMAP",
        "imap_host":   None,
        "imap_port":   993,
        "spam_folder": None,
        "hint_ru": "Адрес IMAP-сервера будет запрошен на следующем шаге.",
        "hint_en": "You will enter the IMAP server address in the next step.",
        "hint_de": "Die IMAP-Serveradresse wird im nächsten Schritt abgefragt.",
    },
}

MAX_BODY_CHARS = 400
HOURS_BACK     = 24

# Multi-step setup state  {chat_id: {"step": ..., "provider": ..., "email": ..., ...}}
_pending_mail_setup: dict[int, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Storage helpers
# ─────────────────────────────────────────────────────────────────────────────

def _creds_dir() -> Path:
    p = Path(MAIL_CREDS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _creds_file(chat_id: int) -> Path:
    return _creds_dir() / f"{chat_id}.json"


def _last_digest_file(chat_id: int) -> Path:
    return _creds_dir() / f"{chat_id}_last_digest.txt"


def _load_creds(chat_id: int) -> Optional[dict]:
    # DB is primary; file is migration fallback
    try:
        data = store.get_mail_creds(chat_id)
        if data:
            return data
    except Exception:
        pass
    f = _creds_file(chat_id)
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        # Migrate to DB on first load
        try:
            store.save_mail_creds(chat_id, data)
        except Exception:
            pass
        return data
    except Exception:
        return None


def _save_creds(chat_id: int, data: dict) -> None:
    try:
        store.save_mail_creds(chat_id, data)
    except Exception as _e:
        log.warning("[Mail] store.save_mail_creds failed: %s", _e)
    # Keep file as backup copy
    f = _creds_file(chat_id)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(f, stat.S_IRUSR | stat.S_IWUSR)   # chmod 600 — owner only
    except Exception:
        pass                                         # non-fatal, best-effort


def _delete_creds(chat_id: int) -> None:
    for p in (_creds_file(chat_id), _last_digest_file(chat_id)):
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def _mail_has_creds(chat_id: int) -> bool:
    c = _load_creds(chat_id)
    return bool(c and c.get("email") and c.get("app_password"))


# ─────────────────────────────────────────────────────────────────────────────
# IMAP fetch helpers
# ─────────────────────────────────────────────────────────────────────────────

def _decode_header_str(s) -> str:
    if s is None:
        return ""
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return str(s)


def _get_text_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if (part.get_content_type() == "text/plain" and
                    "attachment" not in str(part.get("Content-Disposition", ""))):
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            pass
    return body[:MAX_BODY_CHARS].strip()


def _fetch_folder(imap, folder: Optional[str]) -> list[dict]:
    if not folder:
        return []
    quoted = f'"{folder}"' if "[" in folder else folder
    status, _ = imap.select(quoted, readonly=True)
    if status != "OK":
        return []
    since = (datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)).strftime("%d-%b-%Y")
    _, data = imap.search(None, f'(SINCE "{since}")')
    ids = data[0].split()
    items: list[dict] = []
    for mid in ids[-50:]:
        try:
            _, raw = imap.fetch(mid, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            items.append({
                "subject": _decode_header_str(msg.get("Subject", "(no subject)")),
                "sender":  _decode_header_str(msg.get("From", "?")),
                "body":    _get_text_body(msg),
            })
        except Exception:
            pass
    return items


def _build_digest_prompt(inbox: list, spam: list) -> str:
    sections = []
    if inbox:
        lines = "\n\n".join(
            f"{i}. From: {e['sender']}\n   Subject: {e['subject']}\n"
            f"   Body: {e['body'] or '(empty)'}"
            for i, e in enumerate(inbox, 1)
        )
        sections.append(f"=== INBOX ({len(inbox)} emails) ===\n{lines}")
    if spam:
        lines = "\n\n".join(
            f"{i}. From: {e['sender']}\n   Subject: {e['subject']}\n"
            f"   Body: {e['body'] or '(empty)'}"
            for i, e in enumerate(spam, 1)
        )
        sections.append(f"=== SPAM ({len(spam)} emails) ===\n{lines}")
    if not sections:
        return ""
    return PROMPTS["mail"]["digest_header"] + "\n\n".join(sections)


# ─────────────────────────────────────────────────────────────────────────────
# Digest runner
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_and_summarize(chat_id: int) -> str:
    """
    Connect to the user's IMAP server using their stored credentials,
    fetch inbox + spam from the last 24h, summarise with LLM.
    Returns the formatted digest string.
    Raises: imaplib.IMAP4.error on login failure, ConnectionError on network error.
    """
    creds = _load_creds(chat_id)
    if not creds or not creds.get("email") or not creds.get("app_password"):
        raise ValueError("No credentials configured for this user")

    imap_host   = creds.get("imap_host", "imap.gmail.com")
    imap_port   = int(creds.get("imap_port", 993))
    spam_folder = creds.get("spam_folder")

    conn = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=30)
    conn.login(creds["email"], creds["app_password"])
    inbox = _fetch_folder(conn, "INBOX")
    spam  = _fetch_folder(conn, spam_folder)
    conn.logout()

    today = datetime.now().strftime("%d.%m.%Y")
    if not inbox and not spam:
        return f"📭 Email Digest — {today}\nNo new emails in the last 24 hours."

    prompt  = _build_digest_prompt(inbox, spam)
    summary = _ask_taris(prompt, timeout=90)
    if not summary:
        return (
            f"📧 Digest — {today}\n"
            f"⚠️ Could not summarise ({len(inbox)} inbox, {len(spam)} spam)."
        )

    result = (
        f"📧 *Email Digest — {today}*\n"
        f"_Inbox: {len(inbox)}, Spam: {len(spam)}_\n\n{summary}"
    )
    try:
        _last_digest_file(chat_id).write_text(summary, encoding="utf-8")
    except Exception:
        pass
    return result


def _run_refresh_thread(chat_id: int, msg_id: int) -> None:
    """Background: fetch + summarise, then edit the spinner message."""
    try:
        text = _fetch_and_summarize(chat_id)
    except imaplib.IMAP4.error as e:
        text = _t(chat_id, "mail_login_failed", err=str(e)[:120])
    except ConnectionRefusedError:
        text = _t(chat_id, "mail_connect_failed", err="connection refused")
    except OSError as e:
        text = _t(chat_id, "mail_connect_failed", err=str(e)[:120])
    except Exception as e:
        log.exception(f"[MailDigest] user {chat_id}: {e}")
        text = _t(chat_id, "mail_fetch_error", err=str(e)[:120])

    kb = _mail_main_keyboard(chat_id)
    try:
        bot.edit_message_text(
            _truncate(text), chat_id, msg_id,
            parse_mode="Markdown", reply_markup=kb,
        )
    except Exception:
        bot.send_message(
            chat_id, _truncate(text),
            parse_mode="Markdown", reply_markup=kb,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Keyboards
# ─────────────────────────────────────────────────────────────────────────────

def _mail_main_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown alongside a digest — Refresh + Read aloud + Settings + Menu."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "btn_refresh_now"),   callback_data="digest_refresh"),
        InlineKeyboardButton(_t(chat_id, "mail_btn_settings"), callback_data="mail_settings"),
    )
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_read_aloud"), callback_data="digest_tts"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_send_email"), callback_data="digest_email"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
    return kb


def _mail_nocreds_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Keyboard when no credentials — offer setup + back."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "mail_btn_setup"), callback_data="mail_consent"),
        InlineKeyboardButton(_t(chat_id, "btn_back"),        callback_data="menu"),
    )
    return kb


def _mail_consent_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "mail_consent_agree"),   callback_data="mail_consent_agree"),
        InlineKeyboardButton(_t(chat_id, "mail_consent_decline"), callback_data="menu"),
    )
    return kb


def _mail_provider_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for key, p in PROVIDERS.items():
        kb.add(InlineKeyboardButton(p["label"], callback_data=f"mail_provider:{key}"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
    return kb


def _mail_settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Keyboard for the settings view — delete + menu."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "mail_btn_delete"), callback_data="mail_del_creds"),
        InlineKeyboardButton(_t(chat_id, "btn_back"),        callback_data="menu"),
    )
    return kb


# ─────────────────────────────────────────────────────────────────────────────
# Public handler entry points  (called from telegram_menu_bot.py)
# ─────────────────────────────────────────────────────────────────────────────

def handle_digest_auth(chat_id: int) -> None:
    """
    Replacement for the old global _handle_digest.
    Routes to setup if no credentials; shows per-user digest otherwise.
    """
    if _is_guest(chat_id):
        bot.send_message(chat_id, _t(chat_id, "mail_guest_not_allowed"),
                         parse_mode="Markdown", reply_markup=_back_keyboard())
        return
    if not _mail_has_creds(chat_id):
        bot.send_message(
            chat_id,
            _t(chat_id, "mail_nocreds_msg"),
            parse_mode="Markdown",
            reply_markup=_mail_nocreds_keyboard(chat_id),
        )
        return

    last = _last_digest_file(chat_id)
    if last.exists() and last.stat().st_size > 0:
        text  = last.read_text(encoding="utf-8", errors="replace").strip()
        age_h = (time.time() - last.stat().st_mtime) / 3600
        header = _t(chat_id, "digest_header", age=age_h)
        bot.send_message(
            chat_id, header + _truncate(text),
            parse_mode="Markdown",
            reply_markup=_mail_main_keyboard(chat_id),
        )
    else:
        msg = bot.send_message(chat_id, _t(chat_id, "fetching"))
        threading.Thread(
            target=_run_refresh_thread,
            args=(chat_id, msg.message_id), daemon=True,
        ).start()


def handle_digest_refresh(chat_id: int) -> None:
    """Called on digest_refresh callback — always fetches fresh."""
    if not _mail_has_creds(chat_id):
        bot.send_message(
            chat_id,
            _t(chat_id, "mail_nocreds_msg"),
            parse_mode="Markdown",
            reply_markup=_mail_nocreds_keyboard(chat_id),
        )
        return
    msg = bot.send_message(chat_id, _t(chat_id, "fetching"))
    threading.Thread(
        target=_run_refresh_thread,
        args=(chat_id, msg.message_id), daemon=True,
    ).start()


def handle_mail_consent(chat_id: int) -> None:
    """Show GDPR / 152-FZ consent screen."""
    if _is_guest(chat_id):
        bot.send_message(chat_id, _t(chat_id, "mail_guest_not_allowed"),
                         parse_mode="Markdown", reply_markup=_back_keyboard())
        return
    bot.send_message(
        chat_id,
        _t(chat_id, "mail_consent_text"),
        parse_mode="Markdown",
        reply_markup=_mail_consent_keyboard(chat_id),
    )


def handle_mail_consent_agree(chat_id: int) -> None:
    """User agreed — record consent + show provider selection."""
    existing = _load_creds(chat_id) or {}
    existing["consent_given"] = True
    existing["consent_date"]  = datetime.now(timezone.utc).isoformat()
    _save_creds(chat_id, existing)

    bot.send_message(
        chat_id,
        _t(chat_id, "mail_choose_provider"),
        parse_mode="Markdown",
        reply_markup=_mail_provider_keyboard(chat_id),
    )


def handle_mail_provider(chat_id: int, provider_key: str) -> None:
    """User picked a provider — start the setup wizard."""
    if provider_key not in PROVIDERS:
        bot.send_message(chat_id, _t(chat_id, "unknown_provider"), reply_markup=_back_keyboard(chat_id))
        return

    prov = PROVIDERS[provider_key]

    # Custom IMAP: first ask for host; all others: straight to email
    first_step = "imap_host" if provider_key == "custom" else "email"
    _pending_mail_setup[chat_id] = {"step": first_step, "provider": provider_key}
    _st._user_mode[chat_id] = "mail_setup"

    if provider_key == "custom":
        bot.send_message(
            chat_id,
            _t(chat_id, "mail_enter_imap_host"),
            parse_mode="Markdown",
        )
    else:
        lang = _st._user_lang.get(chat_id, "ru")
        hint = prov.get("hint_de", prov["hint_en"]) if lang == "de" else (prov["hint_ru"] if lang == "ru" else prov["hint_en"])
        bot.send_message(
            chat_id,
            f"{hint}\n\n" + _t(chat_id, "mail_enter_email"),
            parse_mode="Markdown",
        )


def finish_mail_setup(chat_id: int, text: str) -> None:
    """
    Handle text input during mail_setup mode.
    Drives the setup state machine: imap_host → email → password → test.
    """
    state = _pending_mail_setup.get(chat_id, {})
    step  = state.get("step", "")
    text  = text.strip()

    if step == "imap_host":
        # Minimal host validation — just check it's not obviously wrong
        if not text or " " in text or not re.match(r"[A-Za-z0-9.\-]+", text):
            bot.send_message(
                chat_id,
                _t(chat_id, "mail_enter_imap_host"),
                parse_mode="Markdown",
            )
            return
        state["imap_host"] = text
        state["step"]      = "email"
        _pending_mail_setup[chat_id] = state
        bot.send_message(chat_id, _t(chat_id, "mail_enter_email"), parse_mode="Markdown")

    elif step == "email":
        if not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
            bot.send_message(chat_id, _t(chat_id, "mail_bad_email"), parse_mode="Markdown")
            return
        state["email"] = text
        state["step"]  = "password"
        _pending_mail_setup[chat_id] = state
        bot.send_message(chat_id, _t(chat_id, "mail_enter_password"), parse_mode="Markdown")

    elif step == "password":
        # Never log or echo the password
        state["app_password"] = text
        _st._user_mode.pop(chat_id, None)        # exit mail_setup mode immediately
        _pending_mail_setup[chat_id] = state
        msg = bot.send_message(chat_id, _t(chat_id, "mail_testing"), parse_mode="Markdown")
        threading.Thread(
            target=_do_test_and_save,
            args=(chat_id, dict(state), msg.message_id),
            daemon=True,
        ).start()

    else:
        _pending_mail_setup.pop(chat_id, None)
        _st._user_mode.pop(chat_id, None)
        bot.send_message(chat_id, _t(chat_id, "cancelled"), reply_markup=_back_keyboard())


def _do_test_and_save(chat_id: int, state: dict, msg_id: int) -> None:
    """
    Background thread: test IMAP login, save on success, report error on failure.
    The app_password is used only here and stored; it is never returned to the user.
    """
    provider_key = state.get("provider", "custom")
    prov         = PROVIDERS.get(provider_key, PROVIDERS["custom"])
    email_addr   = state.get("email", "")
    app_password = state.get("app_password", "")
    imap_host    = state.get("imap_host") or prov.get("imap_host") or ""
    imap_port    = int(prov.get("imap_port", 993))
    spam_folder  = prov.get("spam_folder")

    try:
        conn = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=20)
        conn.login(email_addr, app_password)
        conn.logout()
    except imaplib.IMAP4.error as e:
        _pending_mail_setup.pop(chat_id, None)
        try:
            bot.edit_message_text(
                _t(chat_id, "mail_login_failed", err=str(e)[:120]),
                chat_id, msg_id, parse_mode="Markdown",
                reply_markup=_mail_nocreds_keyboard(chat_id),
            )
        except Exception:
            bot.send_message(
                chat_id,
                _t(chat_id, "mail_login_failed", err=str(e)[:120]),
                parse_mode="Markdown",
                reply_markup=_mail_nocreds_keyboard(chat_id),
            )
        return
    except Exception as e:
        _pending_mail_setup.pop(chat_id, None)
        try:
            bot.edit_message_text(
                _t(chat_id, "mail_connect_failed", err=str(e)[:120]),
                chat_id, msg_id, parse_mode="Markdown",
                reply_markup=_mail_nocreds_keyboard(chat_id),
            )
        except Exception:
            bot.send_message(
                chat_id,
                _t(chat_id, "mail_connect_failed", err=str(e)[:120]),
                parse_mode="Markdown",
                reply_markup=_mail_nocreds_keyboard(chat_id),
            )
        return

    # ── Login succeeded — save ────────────────────────────────────────────
    existing = _load_creds(chat_id) or {}
    existing.update({
        "provider":    provider_key,
        "email":       email_addr,
        "app_password": app_password,
        "imap_host":   imap_host,
        "imap_port":   imap_port,
        "spam_folder": spam_folder,
        "setup_date":  datetime.now(timezone.utc).isoformat(),
    })
    _save_creds(chat_id, existing)
    _pending_mail_setup.pop(chat_id, None)
    log.info(f"[MailCreds] user {chat_id} configured {provider_key} ({_mask_email(email_addr)})")

    try:
        bot.edit_message_text(
            _t(chat_id, "mail_setup_ok", masked=_mask_email(email_addr)),
            chat_id, msg_id, parse_mode="Markdown",
            reply_markup=_mail_main_keyboard(chat_id),
        )
    except Exception:
        bot.send_message(
            chat_id,
            _t(chat_id, "mail_setup_ok", masked=_mask_email(email_addr)),
            parse_mode="Markdown",
            reply_markup=_mail_main_keyboard(chat_id),
        )


def handle_mail_settings(chat_id: int) -> None:
    """Show current mail configuration + delete option."""
    if _is_guest(chat_id):
        bot.send_message(chat_id, _t(chat_id, "mail_guest_not_allowed"),
                         parse_mode="Markdown", reply_markup=_back_keyboard())
        return
    creds = _load_creds(chat_id)
    if not creds or not creds.get("email"):
        handle_digest_auth(chat_id)
        return

    masked   = _mask_email(creds.get("email", "?"))
    provider = PROVIDERS.get(creds.get("provider", "custom"), {}).get("label", "Custom IMAP")
    setup_dt = creds.get("setup_date", "?")[:10]
    consent  = "✅" if creds.get("consent_given") else "⚠️"

    bot.send_message(
        chat_id,
        _t(chat_id, "mail_settings_msg",
           provider=provider, masked=masked, date=setup_dt, consent=consent),
        parse_mode="Markdown",
        reply_markup=_mail_settings_keyboard(chat_id),
    )


def handle_mail_del_creds(chat_id: int) -> None:
    """Delete all stored credentials for this user (includes consent withdrawal)."""
    _delete_creds(chat_id)
    log.info(f"[MailCreds] user {chat_id} deleted credentials and withdrew consent")
    bot.send_message(
        chat_id,
        _t(chat_id, "mail_creds_deleted"),
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def _mask_email(addr: str) -> str:
    """user@example.com  →  u***@example.com"""
    if "@" not in addr:
        return "***"
    local, domain = addr.split("@", 1)
    masked_local  = (local[0] + "***") if len(local) > 1 else "***"
    return f"{masked_local}@{domain}"
