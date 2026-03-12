"""
bot_error_protocol.py — Error Protocol: collect voice, text, photos → save → email.

Admin/developer feature for sending structured error reports.
Data is saved to ~/.picoclaw/error_protocols/YYYYMMDD-HHMMSS_errorname/
and optionally emailed with all attachments.

Imports: bot_config, bot_state, bot_instance, bot_access.
"""

import json
import os
import re
import smtplib
import threading
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_config import ERROR_PROTOCOL_DIR, log
import bot_state as _st
from bot_instance import bot
from bot_access import _is_admin, _t, _back_keyboard, _escape_md


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9\u0400-\u04FF\u00C0-\u024F _-]")


def _safe_dirname(name: str) -> str:
    """Sanitise user-supplied name into a filesystem-safe string."""
    name = _SAFE_NAME_RE.sub("", name).strip().replace(" ", "_")
    return name[:60] or "error"


def _errp_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "errp_btn_send"),   callback_data="errp_send"),
        InlineKeyboardButton(_t(chat_id, "errp_btn_cancel"), callback_data="errp_cancel"),
    )
    return kb


def _summary_text(state: dict) -> str:
    """One-line summary of collected items."""
    parts = []
    if state.get("texts"):
        parts.append(f"{len(state['texts'])} text")
    if state.get("voices"):
        parts.append(f"{len(state['voices'])} voice")
    if state.get("photos"):
        parts.append(f"{len(state['photos'])} photo")
    return ", ".join(parts) or "—"


# ─────────────────────────────────────────────────────────────────────────────
# Start / collect / send flow
# ─────────────────────────────────────────────────────────────────────────────

def _start_error_protocol(chat_id: int) -> None:
    """Step 1: ask for error name."""
    _st._user_mode[chat_id] = "errp_name"
    bot.send_message(chat_id, _t(chat_id, "errp_prompt_name"),
                     parse_mode="Markdown")


def _finish_errp_name(chat_id: int, text: str) -> None:
    """Step 2: store name, enter collection mode."""
    name = text.strip()[:100]
    if not name:
        bot.send_message(chat_id, _t(chat_id, "errp_prompt_name"),
                         parse_mode="Markdown")
        return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = _safe_dirname(name)
    folder_name = f"{ts}_{safe}"
    folder_path = os.path.join(ERROR_PROTOCOL_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    _st._pending_error_protocol[chat_id] = {
        "name": name,
        "dir": folder_path,
        "folder_name": folder_name,
        "texts": [],
        "voices": [],
        "photos": [],
    }
    _st._user_mode[chat_id] = "errp_collect"
    bot.send_message(
        chat_id,
        _t(chat_id, "errp_prompt_collect", name=_escape_md(name)),
        parse_mode="Markdown",
        reply_markup=_errp_keyboard(chat_id),
    )


def _errp_collect_text(chat_id: int, text: str) -> None:
    """Collect a text message into the protocol."""
    state = _st._pending_error_protocol.get(chat_id)
    if not state:
        return
    state["texts"].append(text)
    # Save immediately to disk
    idx = len(state["texts"])
    fpath = os.path.join(state["dir"], f"text_{idx:02d}.txt")
    Path(fpath).write_text(text, encoding="utf-8")

    bot.send_message(
        chat_id,
        _t(chat_id, "errp_collected", summary=_summary_text(state)),
        reply_markup=_errp_keyboard(chat_id),
    )


def _errp_collect_voice(chat_id: int, voice_obj) -> None:
    """Download and save a voice message."""
    state = _st._pending_error_protocol.get(chat_id)
    if not state:
        return
    try:
        fi = bot.get_file(voice_obj.file_id)
        data = bot.download_file(fi.file_path)
    except Exception as e:
        log.warning(f"[ErrP] voice download failed for {chat_id}: {e}")
        return

    idx = len(state["voices"]) + 1
    fname = f"voice_{idx:02d}.ogg"
    fpath = os.path.join(state["dir"], fname)
    Path(fpath).write_bytes(data)
    state["voices"].append(fname)

    bot.send_message(
        chat_id,
        _t(chat_id, "errp_collected", summary=_summary_text(state)),
        reply_markup=_errp_keyboard(chat_id),
    )


def _errp_collect_photo(chat_id: int, photo_list) -> None:
    """Download and save a photo (largest resolution)."""
    state = _st._pending_error_protocol.get(chat_id)
    if not state:
        return
    # Telegram sends multiple sizes; take the last (largest)
    best = photo_list[-1]
    try:
        fi = bot.get_file(best.file_id)
        data = bot.download_file(fi.file_path)
    except Exception as e:
        log.warning(f"[ErrP] photo download failed for {chat_id}: {e}")
        return

    idx = len(state["photos"]) + 1
    ext = os.path.splitext(fi.file_path or "x.jpg")[1] or ".jpg"
    fname = f"photo_{idx:02d}{ext}"
    fpath = os.path.join(state["dir"], fname)
    Path(fpath).write_bytes(data)
    state["photos"].append(fname)

    bot.send_message(
        chat_id,
        _t(chat_id, "errp_collected", summary=_summary_text(state)),
        reply_markup=_errp_keyboard(chat_id),
    )


def _errp_cancel(chat_id: int) -> None:
    """Cancel collection — keep whatever was saved but exit mode."""
    _st._pending_error_protocol.pop(chat_id, None)
    _st._user_mode.pop(chat_id, None)
    bot.send_message(chat_id, _t(chat_id, "cancelled"),
                     reply_markup=_back_keyboard())


def _errp_send(chat_id: int) -> None:
    """Finalise: write manifest, try email, report result."""
    state = _st._pending_error_protocol.pop(chat_id, None)
    _st._user_mode.pop(chat_id, None)

    if not state:
        bot.send_message(chat_id, _t(chat_id, "cancelled"),
                         reply_markup=_back_keyboard())
        return

    total = len(state["texts"]) + len(state["voices"]) + len(state["photos"])
    if total == 0:
        bot.send_message(chat_id, _t(chat_id, "errp_empty"),
                         reply_markup=_back_keyboard())
        # Clean up empty directory
        try:
            os.rmdir(state["dir"])
        except OSError:
            pass
        return

    # Write manifest
    manifest = {
        "name": state["name"],
        "created": datetime.now().isoformat(),
        "chat_id": chat_id,
        "texts": [f"text_{i+1:02d}.txt" for i in range(len(state["texts"]))],
        "voices": state["voices"],
        "photos": state["photos"],
    }
    manifest_path = os.path.join(state["dir"], "manifest.json")
    Path(manifest_path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    folder_name = state["folder_name"]

    # Confirm save
    bot.send_message(
        chat_id,
        _t(chat_id, "errp_saved", folder=_escape_md(folder_name)),
        parse_mode="Markdown",
    )

    # Try to send email in background
    threading.Thread(
        target=_errp_send_email,
        args=(chat_id, state),
        daemon=True,
    ).start()


# ─────────────────────────────────────────────────────────────────────────────
# Email sending with attachments
# ─────────────────────────────────────────────────────────────────────────────

def _errp_send_email(chat_id: int, state: dict) -> None:
    """Background thread: send error protocol as email with attachments."""
    from bot_mail_creds import _load_creds
    from bot_email import _get_target_email, _smtp_host_port, _mask_addr

    folder_name = state["folder_name"]

    creds = _load_creds(chat_id)
    if not creds or not creds.get("email") or not creds.get("app_password"):
        bot.send_message(
            chat_id,
            _t(chat_id, "errp_no_mail", folder=_escape_md(folder_name)),
            parse_mode="Markdown",
            reply_markup=_back_keyboard(),
        )
        return

    target = _get_target_email(chat_id)
    if not target:
        bot.send_message(
            chat_id,
            _t(chat_id, "errp_no_mail", folder=_escape_md(folder_name)),
            parse_mode="Markdown",
            reply_markup=_back_keyboard(),
        )
        return

    # Build email
    subject = f"Error Protocol: {state['name']}"
    body_parts = [f"Error Protocol: {state['name']}", f"Created: {datetime.now().isoformat()}", ""]
    for i, txt in enumerate(state["texts"], 1):
        body_parts.append(f"--- Text {i} ---")
        body_parts.append(txt)
        body_parts.append("")

    if state["voices"]:
        body_parts.append(f"Voice messages attached: {len(state['voices'])}")
    if state["photos"]:
        body_parts.append(f"Photos attached: {len(state['photos'])}")

    body = "\n".join(body_parts)

    msg = MIMEMultipart()
    msg["From"] = creds["email"]
    msg["To"] = target
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Attach files
    proto_dir = state["dir"]
    for fname in state["voices"] + state["photos"]:
        fpath = os.path.join(proto_dir, fname)
        if not os.path.isfile(fpath):
            continue
        with open(fpath, "rb") as f:
            part = MIMEApplication(f.read(), Name=fname)
        part["Content-Disposition"] = f'attachment; filename="{fname}"'
        msg.attach(part)

    # Attach text files too
    for i in range(len(state["texts"])):
        fname = f"text_{i+1:02d}.txt"
        fpath = os.path.join(proto_dir, fname)
        if not os.path.isfile(fpath):
            continue
        with open(fpath, "rb") as f:
            part = MIMEApplication(f.read(), Name=fname)
        part["Content-Disposition"] = f'attachment; filename="{fname}"'
        msg.attach(part)

    imap_host = creds.get("imap_host", "imap.gmail.com")
    smtp_host, smtp_port = _smtp_host_port(imap_host)

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            server.login(creds["email"], creds["app_password"])
            server.sendmail(creds["email"], target, msg.as_string())
        log.info(f"[ErrP] email sent for {chat_id}: {folder_name}")
        bot.send_message(
            chat_id,
            _t(chat_id, "errp_email_ok", to=_mask_addr(target)),
            parse_mode="Markdown",
            reply_markup=_back_keyboard(),
        )
    except Exception as e:
        log.warning(f"[ErrP] email failed for {chat_id}: {e}")
        bot.send_message(
            chat_id,
            _t(chat_id, "errp_email_fail",
               err=str(e)[:120],
               folder=_escape_md(folder_name)),
            parse_mode="Markdown",
            reply_markup=_back_keyboard(),
        )
