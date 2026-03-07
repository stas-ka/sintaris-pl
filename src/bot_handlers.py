"""
bot_handlers.py — User-facing message handlers.

Responsibilities:
  - Mail digest (show last + refresh)
  - System chat (natural language → bash → confirm → run)
  - Free chat (picoclaw LLM)
  - Notes UI (menu, list, create, open, edit, delete)
"""

import hashlib
import threading
import time
from pathlib import Path
from typing import Optional

import bot_state as _st
from bot_config import (
    LAST_DIGEST_FILE, DIGEST_SCRIPT,
    log,
)
from bot_instance import bot
from bot_access import (
    _t, _with_lang, _escape_md, _truncate,
    _safe_edit, _back_keyboard, _run_subprocess, _ask_picoclaw,
)
from bot_users import (
    _list_notes_for, _load_note_text, _save_note_file, _delete_note_file,
    _slug,
)

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ─────────────────────────────────────────────────────────────────────────────
# Notes UI keyboards
# ─────────────────────────────────────────────────────────────────────────────

def _notes_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Notes main submenu: Create / List / Back."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "note_btn_create"),  callback_data="note_create"),
        InlineKeyboardButton(_t(chat_id, "note_btn_list"),    callback_data="note_list"),
        InlineKeyboardButton("🔙  Menu",                       callback_data="menu"),
    )
    return kb


def _notes_list_keyboard(chat_id: int, notes: list[dict]) -> InlineKeyboardMarkup:
    """Per-note open / edit / delete inline buttons."""
    kb = InlineKeyboardMarkup(row_width=3)
    for note in notes:
        slug  = note["slug"]
        title = note["title"][:30]
        kb.add(InlineKeyboardButton(f"📄 {title}", callback_data=f"note_open:{slug}"))
        kb.row(
            InlineKeyboardButton("✏️ Edit",  callback_data=f"note_edit:{slug}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"note_delete:{slug}"),
        )
    kb.add(InlineKeyboardButton(_t(chat_id, "note_btn_create"), callback_data="note_create"))
    kb.add(InlineKeyboardButton("🔙  Menu", callback_data="menu"))
    return kb


# ─────────────────────────────────────────────────────────────────────────────
# Notes UI handlers
# ─────────────────────────────────────────────────────────────────────────────

def _handle_notes_menu(chat_id: int) -> None:
    bot.send_message(
        chat_id,
        _t(chat_id, "note_menu_header"),
        parse_mode="Markdown",
        reply_markup=_notes_menu_keyboard(chat_id),
    )


def _handle_note_list(chat_id: int) -> None:
    notes = _list_notes_for(chat_id)
    if not notes:
        bot.send_message(chat_id, _t(chat_id, "note_list_empty"),
                         parse_mode="Markdown",
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    header = _t(chat_id, "note_list_header", count=len(notes))
    bot.send_message(chat_id, header,
                     parse_mode="Markdown",
                     reply_markup=_notes_list_keyboard(chat_id, notes))


def _start_note_create(chat_id: int) -> None:
    _st._user_mode[chat_id]    = "note_add_title"
    _st._pending_note[chat_id] = {"step": "title"}
    bot.send_message(chat_id, _t(chat_id, "note_create_prompt_title"),
                     parse_mode="Markdown")


def _handle_note_open(chat_id: int, slug: str) -> None:
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("✏️ Edit",    callback_data=f"note_edit:{slug}"),
        InlineKeyboardButton("🗑 Delete",  callback_data=f"note_delete:{slug}"),
    )
    kb.row(
        InlineKeyboardButton("� Raw text",   callback_data=f"note_raw:{slug}"),
        InlineKeyboardButton("🔊 Read aloud", callback_data=f"note_tts:{slug}"),
    )
    kb.row(
        InlineKeyboardButton("📋 All Notes", callback_data="note_list"),
        InlineKeyboardButton("🔙  Menu",      callback_data="menu"),
    )
    bot.send_message(
        chat_id,
        f"📄 *{_escape_md(slug.replace('_', ' '))}*\n\n{_escape_md(text)}",
        parse_mode="Markdown",
        reply_markup=kb,
    )


def _handle_note_raw(chat_id: int, slug: str) -> None:
    """Send the note body as an unformatted plain-text message — easy to copy."""
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("✏️ Edit",      callback_data=f"note_edit:{slug}"),
        InlineKeyboardButton("🗑 Delete",    callback_data=f"note_delete:{slug}"),
    )
    kb.row(
        InlineKeyboardButton("🔊 Read aloud", callback_data=f"note_tts:{slug}"),
        InlineKeyboardButton("🔙  Back",       callback_data=f"note_open:{slug}"),
    )
    # Send without parse_mode — every character appears exactly as stored
    bot.send_message(chat_id, text, reply_markup=kb)


def _start_note_edit(chat_id: int, slug: str) -> None:
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    _st._user_mode[chat_id]    = "note_edit_content"
    _st._pending_note[chat_id] = {"step": "edit_content", "slug": slug}

    lines = text.splitlines()
    note_title = lines[0].lstrip("# ").strip()
    # Body = everything after the "# Title" header line (skip blank separator)
    body_lines = lines[2:] if len(lines) > 2 else (lines[1:] if len(lines) > 1 else [])
    note_body  = "\n".join(body_lines).strip() or text

    # Step 1 — tell the user what to do
    bot.send_message(
        chat_id,
        _t(chat_id, "note_edit_prompt", title=_escape_md(note_title)),
        parse_mode="Markdown",
    )
    # Step 2 — send current content as copyable plain text with ForceReply
    # Telegram opens the reply box automatically; user can copy/edit the body above
    from telebot.types import ForceReply
    bot.send_message(chat_id, note_body, reply_markup=ForceReply(selective=False))


def _handle_note_delete(chat_id: int, slug: str) -> None:
    deleted = _delete_note_file(chat_id, slug)
    if deleted:
        bot.send_message(chat_id, _t(chat_id, "note_deleted"),
                         parse_mode="Markdown",
                         reply_markup=_notes_menu_keyboard(chat_id))
    else:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))


# ─────────────────────────────────────────────────────────────────────────────
# Mail digest
# ─────────────────────────────────────────────────────────────────────────────

def _handle_digest(chat_id: int) -> None:
    """Show last saved digest instantly, then offer to refresh."""
    last = Path(LAST_DIGEST_FILE)
    if last.exists() and last.stat().st_size > 0:
        text  = last.read_text(encoding="utf-8", errors="replace").strip()
        age_h = (time.time() - last.stat().st_mtime) / 3600
        header = _t(chat_id, "digest_header", age=age_h)
        bot.send_message(chat_id, header + _truncate(text), parse_mode="Markdown")
    else:
        bot.send_message(chat_id, _t(chat_id, "digest_none"))
        _refresh_digest(chat_id)
        return

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "btn_refresh_now"), callback_data="digest_refresh"),
        InlineKeyboardButton("🔙  Menu",                     callback_data="menu"),
    )
    bot.send_message(chat_id, _t(chat_id, "digest_hint"),
                     parse_mode="Markdown", reply_markup=kb)


def _refresh_digest(chat_id: int) -> None:
    """Run gmail_digest.py in a background thread and report the result."""
    msg = bot.send_message(chat_id, _t(chat_id, "fetching"))

    def _run():
        rc, out = _run_subprocess(["python3", DIGEST_SCRIPT, "--stdout"], timeout=120)
        text = out.strip() if (rc == 0 and out) else (out or _t(chat_id, "digest_no_out"))
        try:
            bot.edit_message_text(
                _t(chat_id, "digest_fresh") + _truncate(text),
                chat_id, msg.message_id,
                parse_mode="Markdown",
                reply_markup=_back_keyboard(),
            )
        except Exception:
            bot.send_message(chat_id,
                             _t(chat_id, "digest_fresh") + _truncate(text),
                             parse_mode="Markdown",
                             reply_markup=_back_keyboard())

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# System chat — natural language → bash → confirm → execute
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a Linux system assistant running on a Raspberry Pi 3 B+ "
    "(aarch64, Raspberry Pi OS Bookworm). The user will describe a task. "
    "Respond with ONLY a single safe bash command that accomplishes the task. "
    "No explanation, no markdown fences, no commentary — just the bare command."
)


def _handle_system_message(chat_id: int, user_text: str) -> None:
    """Translate natural language → bash command → ask for confirmation."""
    bot.send_chat_action(chat_id, "typing")
    prompt = f"{_SYSTEM_PROMPT}\n\nTask: {user_text}"
    msg = bot.send_message(chat_id, "⏳ Generating command…")

    def _run():
        cmd_text = _ask_picoclaw(prompt, timeout=45)
        if not cmd_text:
            bot.edit_message_text("❌ Could not generate a command. Try again.",
                                  chat_id, msg.message_id)
            return

        # Strip markdown fences the model might have added
        cmd_clean = cmd_text.strip().lstrip("`").rstrip("`").strip()
        if cmd_clean.startswith("bash\n"):
            cmd_clean = cmd_clean[5:].strip()

        cmd_hash = hashlib.md5(cmd_clean.encode()).hexdigest()[:8]
        _st._pending_cmd[chat_id] = cmd_clean

        from bot_access import _confirm_keyboard
        reply = (
            "🖥️  I'll run the following command:\n\n"
            f"```\n{cmd_clean}\n```\n\n"
            "Confirm?"
        )
        try:
            bot.edit_message_text(reply, chat_id, msg.message_id,
                                  parse_mode="Markdown",
                                  reply_markup=_confirm_keyboard(cmd_hash))
        except Exception:
            bot.send_message(chat_id, reply,
                             parse_mode="Markdown",
                             reply_markup=_confirm_keyboard(cmd_hash))

    threading.Thread(target=_run, daemon=True).start()


def _execute_pending_cmd(chat_id: int) -> None:
    """Execute the confirmed pending bash command and show output."""
    cmd = _st._pending_cmd.pop(chat_id, None)
    if not cmd:
        bot.send_message(chat_id, "⚠️ No pending command.", reply_markup=_back_keyboard())
        return

    msg = bot.send_message(chat_id, f"▶️  Running…\n```\n{cmd}\n```",
                            parse_mode="Markdown")

    def _run():
        rc, output = _run_subprocess(["bash", "-c", cmd], timeout=30)
        if not output:
            output = "(no output)"
        status = "✅" if rc == 0 else f"⚠️ exit {rc}"
        result = (
            f"{status} `{cmd[:60]}{'…' if len(cmd) > 60 else ''}`\n\n"
            f"```\n{_truncate(output, 3500)}\n```"
        )
        try:
            bot.edit_message_text(result, chat_id, msg.message_id,
                                  parse_mode="Markdown",
                                  reply_markup=_back_keyboard())
        except Exception:
            bot.send_message(chat_id, result,
                             parse_mode="Markdown",
                             reply_markup=_back_keyboard())

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Free chat
# ─────────────────────────────────────────────────────────────────────────────

def _handle_chat_message(chat_id: int, user_text: str) -> None:
    """Forward message to picoclaw agent and return response."""
    bot.send_chat_action(chat_id, "typing")
    msg = bot.send_message(chat_id, "⏳ Thinking…")

    def _run():
        response = _ask_picoclaw(_with_lang(chat_id, user_text), timeout=60)
        reply    = response if response else "❌ No response from picoclaw."
        try:
            bot.edit_message_text(_truncate(reply), chat_id, msg.message_id,
                                  reply_markup=_back_keyboard())
        except Exception:
            bot.send_message(chat_id, _truncate(reply),
                             reply_markup=_back_keyboard())

    threading.Thread(target=_run, daemon=True).start()
