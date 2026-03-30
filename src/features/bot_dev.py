"""
bot_dev.py — Developer Role Menu.

Accessible only to users in DEVELOPER_USERS.
Provides: Dev Chat (LLM with source context), Restart Bot, View Log,
          Last Error, File List, Security Log view.

RBAC: all handlers call _is_developer() guard; unauthorized access is
      logged to security_events and denied.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.bot_config import log, TARIS_DIR
from core.bot_instance import bot
import core.bot_state as _st
from telegram.bot_access import _is_developer, _is_admin, _t, _run_subprocess


# ─── Security event logging ───────────────────────────────────────────────────

def log_security_event(chat_id: int, event_type: str, detail: str = "") -> None:
    """Record a security event in DB + security.log file."""
    try:
        from core.bot_db import get_db
        db = get_db()
        db.execute(
            """INSERT INTO security_events(chat_id, event_type, detail, created_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (chat_id, event_type, detail[:500]),
        )
        db.commit()
    except Exception as exc:
        log.debug("[Security] DB log failed: %s", exc)

    # Also write to security.log
    log.warning("[SECURITY] %s chat_id=%s detail=%s", event_type, chat_id, detail[:200])


def log_access_denied(chat_id: int, action: str) -> None:
    log_security_event(chat_id, "ACCESS_DENIED", f"action={action}")


# ─── Developer keyboard ───────────────────────────────────────────────────────

def _dev_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💬 " + _t(chat_id, "dev_btn_chat"),    callback_data="dev_chat"))
    kb.add(
        InlineKeyboardButton("🔄 " + _t(chat_id, "dev_btn_restart"), callback_data="dev_restart"),
        InlineKeyboardButton("🐛 " + _t(chat_id, "dev_btn_error"),   callback_data="dev_error"),
    )
    kb.add(
        InlineKeyboardButton("📋 " + _t(chat_id, "dev_btn_log"),     callback_data="dev_log"),
        InlineKeyboardButton("📂 " + _t(chat_id, "dev_btn_files"),   callback_data="dev_files"),
    )
    kb.add(InlineKeyboardButton("🔒 " + _t(chat_id, "dev_btn_security"), callback_data="dev_security_log"))
    kb.add(InlineKeyboardButton("🔙 " + _t(chat_id, "back"),             callback_data="menu"))
    return kb


# ─── Main menu ────────────────────────────────────────────────────────────────

def _handle_dev_menu(chat_id: int) -> None:
    """Show the Developer menu (developer role only)."""
    if not _is_developer(chat_id):
        log_access_denied(chat_id, "dev_menu")
        bot.send_message(chat_id, _t(chat_id, "dev_no_access"))
        return

    text = _t(chat_id, "dev_menu_title")
    bot.send_message(chat_id, text, parse_mode="Markdown",
                     reply_markup=_dev_keyboard(chat_id))


# ─── Dev Chat ────────────────────────────────────────────────────────────────

_DEV_CHAT_SYSTEM = (
    "You are a coding assistant for the taris bot project. "
    "The bot is a Python Telegram + voice assistant. "
    "Source layout: src/core/ (config, db, llm, store), "
    "src/telegram/ (handlers, admin, access, users), "
    "src/features/ (calendar, documents, voice, contacts). "
    "Patterns: all i18n via strings.json (_t()); callbacks in telegram_menu_bot.py; "
    "DB via store adapter (store_sqlite.py / store_postgres.py); "
    "new features: add handler + callback + i18n + regression test. "
    "Answer concisely. When proposing code, show only the relevant diff."
)


def _handle_dev_chat_start(chat_id: int) -> None:
    if not _is_developer(chat_id):
        log_access_denied(chat_id, "dev_chat")
        bot.send_message(chat_id, _t(chat_id, "dev_no_access"))
        return
    _st._user_mode[chat_id] = "dev_chat"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 " + _t(chat_id, "back"), callback_data="dev_menu"))
    bot.send_message(chat_id, _t(chat_id, "dev_chat_hint"),
                     parse_mode="Markdown", reply_markup=kb)


def handle_dev_chat_message(chat_id: int, text: str) -> None:
    """Handle a message in dev_chat mode."""
    if not _is_developer(chat_id):
        return
    from core.bot_llm import ask_llm
    try:
        prompt = f"[Dev context: taris bot]\n{text}"
        reply = ask_llm(prompt, timeout=60, system=_DEV_CHAT_SYSTEM)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Dev Menu", callback_data="dev_menu"))
        bot.send_message(chat_id, reply or "_(no response)_",
                         parse_mode="Markdown", reply_markup=kb)
    except Exception as exc:
        log.error("[DevChat] LLM failed: %s", exc)
        bot.send_message(chat_id, f"⚠️ LLM error: {exc}")


# ─── Restart ─────────────────────────────────────────────────────────────────

def _handle_dev_restart(chat_id: int) -> None:
    if not _is_developer(chat_id):
        log_access_denied(chat_id, "dev_restart")
        bot.send_message(chat_id, _t(chat_id, "dev_no_access"))
        return
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ " + _t(chat_id, "dev_restart_confirm"), callback_data="dev_restart_confirmed"),
        InlineKeyboardButton("❌ " + _t(chat_id, "cancel"),              callback_data="dev_menu"),
    )
    bot.send_message(chat_id, _t(chat_id, "dev_restart_prompt"),
                     parse_mode="Markdown", reply_markup=kb)


def _handle_dev_restart_confirmed(chat_id: int) -> None:
    if not _is_developer(chat_id):
        log_access_denied(chat_id, "dev_restart_confirmed")
        return
    log_security_event(chat_id, "BOT_RESTART", "triggered via Dev Menu")
    bot.send_message(chat_id, _t(chat_id, "dev_restarting"))
    import threading
    def _do():
        time.sleep(1)
        _run_subprocess(["systemctl", "--user", "restart", "taris-telegram"], timeout=15)
    threading.Thread(target=_do, daemon=True).start()


# ─── View Log ────────────────────────────────────────────────────────────────

def _handle_dev_log(chat_id: int) -> None:
    if not _is_developer(chat_id):
        log_access_denied(chat_id, "dev_log")
        bot.send_message(chat_id, _t(chat_id, "dev_no_access"))
        return
    rc, out = _run_subprocess(
        ["journalctl", "--user", "-u", "taris-telegram", "-n", "35", "--no-pager"],
        timeout=10,
    )
    text = f"📋 *Journal (last 35 lines)*\n```\n{out[-3000:]}\n```" if out else "_(empty)_"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Dev Menu", callback_data="dev_menu"))
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


# ─── Last Error ───────────────────────────────────────────────────────────────

def _handle_dev_error(chat_id: int) -> None:
    if not _is_developer(chat_id):
        log_access_denied(chat_id, "dev_error")
        bot.send_message(chat_id, _t(chat_id, "dev_no_access"))
        return
    rc, out = _run_subprocess(
        ["journalctl", "--user", "-u", "taris-telegram", "-p", "err", "-n", "10", "--no-pager"],
        timeout=10,
    )
    text = f"🐛 *Last errors*\n```\n{out[-3000:]}\n```" if out.strip() else "✅ No recent errors."
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Dev Menu", callback_data="dev_menu"))
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


# ─── File List ────────────────────────────────────────────────────────────────

def _handle_dev_files(chat_id: int) -> None:
    if not _is_developer(chat_id):
        log_access_denied(chat_id, "dev_files")
        bot.send_message(chat_id, _t(chat_id, "dev_no_access"))
        return
    lines = []
    base = Path(TARIS_DIR)
    for subdir in ["", "core", "telegram", "features"]:
        p = base / subdir if subdir else base
        for f in sorted(p.glob("*.py")):
            try:
                stat = f.stat()
                size_kb = stat.st_size // 1024
                mtime = time.strftime("%m-%d %H:%M", time.localtime(stat.st_mtime))
                lines.append(f"{str(f.relative_to(base)):45s} {size_kb:4d} KB  {mtime}")
            except Exception:
                pass
    text = "📂 *Source files*\n```\n" + "\n".join(lines[:60]) + "\n```"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Dev Menu", callback_data="dev_menu"))
    bot.send_message(chat_id, text[:4000], parse_mode="Markdown", reply_markup=kb)


# ─── Security Log ────────────────────────────────────────────────────────────

def _handle_dev_security_log(chat_id: int) -> None:
    if not (_is_developer(chat_id) or _is_admin(chat_id)):
        log_access_denied(chat_id, "dev_security_log")
        bot.send_message(chat_id, _t(chat_id, "dev_no_access"))
        return
    try:
        from core.bot_db import get_db
        db = get_db()
        rows = db.execute(
            "SELECT created_at, event_type, chat_id, detail "
            "FROM security_events ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    except Exception as exc:
        bot.send_message(chat_id, f"⚠️ DB error: {exc}")
        return

    if not rows:
        text = "🔒 *Security Log* — no events recorded."
    else:
        lines = ["🔒 *Security Log (last 50)*\n"]
        for r in rows:
            ts = str(r[0])[:16]
            lines.append(f"`{ts}` `{r[1][:20]:<20}` uid={r[2]} {r[3][:60]}")
        text = "\n".join(lines)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Dev Menu", callback_data="dev_menu"))
    bot.send_message(chat_id, text[:4000], parse_mode="Markdown", reply_markup=kb)
