"""
bot_notify.py — Agent: Notifications to Users

Send Telegram notifications to contacts from the Taris contact book.
Templates are stored in the bot DB and can be viewed, added, and edited
via the agent menu.

Flow (send):
  Agents menu → Notifications to Users → Send notification
  → Choose template / write custom message
  → Choose recipients (All with Telegram / Filter)
  → Preview (count + names + message text)
  → Confirm → bot.send_message() to each contact's Telegram chat_id
  → Report sent / failed

Flow (template management):
  Notifications to Users → Notification templates
  → List templates → View / Edit / Delete
  → Add template → name → body text → saved
"""

import json
import logging
import threading
import uuid

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.bot_config import log
from core.bot_instance import bot
from telegram.bot_access import _t

# ─────────────────────────────────────────────────────────────────────────────
# Template storage — persisted as JSON in system settings
# Key: "notify_templates"
# Value: JSON list of {"id": str, "name": str, "body": str}
# ─────────────────────────────────────────────────────────────────────────────

def _load_templates() -> list[dict]:
    from core.bot_db import db_get_system_setting
    raw = db_get_system_setting("notify_templates", "[]")
    try:
        return json.loads(raw)
    except Exception:
        return []


def _save_templates(templates: list[dict]) -> None:
    from core.bot_db import db_set_system_setting
    db_set_system_setting("notify_templates", json.dumps(templates, ensure_ascii=False))


def _get_template(tpl_id: str) -> dict | None:
    return next((t for t in _load_templates() if t.get("id") == tpl_id), None)


# ─────────────────────────────────────────────────────────────────────────────
# Contact helpers — only contacts with a numeric `telegram` field can receive
# ─────────────────────────────────────────────────────────────────────────────

def _telegram_contacts(owner_chat_id: int) -> list[dict]:
    """Return contacts that have a valid Telegram chat_id set."""
    from core.store import store
    all_contacts = store.list_contacts(owner_chat_id)
    result = []
    for c in all_contacts:
        tg = str(c.get("telegram") or "").strip().lstrip("+")
        if tg.lstrip("-").isdigit() and int(tg) != 0:
            c = dict(c)
            c["_tg_id"] = int(tg)
            result.append(c)
    return result


def _filter_contacts(contacts: list[dict], query: str) -> list[dict]:
    """Filter contacts by name, email, or notes containing query string."""
    q = query.lower()
    result = []
    for c in contacts:
        haystack = " ".join([
            c.get("name", ""), c.get("email", ""), c.get("notes", ""),
        ]).lower()
        if q in haystack:
            result.append(c)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# In-memory session state per chat_id
# ─────────────────────────────────────────────────────────────────────────────

_sessions: dict[int, dict] = {}


def is_active(chat_id: int) -> bool:
    return chat_id in _sessions


def get_step(chat_id: int) -> str:
    return _sessions.get(chat_id, {}).get("step", "idle")


def cancel(chat_id: int) -> None:
    _sessions.pop(chat_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# Keyboards
# ─────────────────────────────────────────────────────────────────────────────

def _cancel_kb(chat_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(_t(chat_id, "notify_btn_cancel"),
                                callback_data="notify_cancel"))
    return kb


def _tpl_list_kb(chat_id: int, templates: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for tpl in templates:
        kb.add(InlineKeyboardButton(
            _t(chat_id, "notify_tpl_item", name=tpl["name"]),
            callback_data=f"notify_tpl_view:{tpl['id']}"
        ))
    kb.add(InlineKeyboardButton(_t(chat_id, "notify_tpl_btn_add"),
                                callback_data="notify_tpl_add"))
    kb.add(InlineKeyboardButton(_t(chat_id, "notify_tpl_btn_back"),
                                callback_data="notify_menu"))
    return kb


def _tpl_detail_kb(chat_id: int, tpl_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "notify_tpl_btn_edit"),
                             callback_data=f"notify_tpl_edit:{tpl_id}"),
        InlineKeyboardButton(_t(chat_id, "notify_tpl_btn_delete"),
                             callback_data=f"notify_tpl_del:{tpl_id}"),
    )
    kb.add(InlineKeyboardButton(_t(chat_id, "notify_tpl_btn_back"),
                                callback_data="notify_tpl_menu"))
    return kb


def _preview_kb(chat_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "notify_btn_confirm"),
                             callback_data="notify_confirm_send"),
        InlineKeyboardButton(_t(chat_id, "notify_btn_cancel"),
                             callback_data="notify_cancel"),
    )
    return kb


# ─────────────────────────────────────────────────────────────────────────────
# Main agent menu
# ─────────────────────────────────────────────────────────────────────────────

def show_notify_menu(chat_id: int) -> None:
    """Show the Notifications agent top-level menu."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "notify_btn_send"),
                             callback_data="notify_send"),
        InlineKeyboardButton(_t(chat_id, "notify_btn_templates"),
                             callback_data="notify_tpl_menu"),
        InlineKeyboardButton(_t(chat_id, "notify_btn_back"),
                             callback_data="agents_menu"),
    )
    bot.send_message(chat_id, _t(chat_id, "notify_menu_title"),
                     parse_mode="Markdown", reply_markup=kb)


# ─────────────────────────────────────────────────────────────────────────────
# Template management
# ─────────────────────────────────────────────────────────────────────────────

def show_tpl_menu(chat_id: int) -> None:
    """List all templates with buttons."""
    templates = _load_templates()
    if templates:
        text = _t(chat_id, "notify_tpl_menu_title")
        kb = _tpl_list_kb(chat_id, templates)
    else:
        text = _t(chat_id, "notify_tpl_menu_empty")
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(_t(chat_id, "notify_tpl_btn_add"),
                                    callback_data="notify_tpl_add"))
        kb.add(InlineKeyboardButton(_t(chat_id, "notify_tpl_btn_back"),
                                    callback_data="notify_menu"))
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


def show_tpl_view(chat_id: int, tpl_id: str) -> None:
    """Show template content with Edit/Delete/Back buttons."""
    tpl = _get_template(tpl_id)
    if not tpl:
        show_tpl_menu(chat_id)
        return
    text = _t(chat_id, "notify_tpl_view_title", name=tpl["name"], body=tpl["body"])
    bot.send_message(chat_id, text, parse_mode="Markdown",
                     reply_markup=_tpl_detail_kb(chat_id, tpl_id))


def start_tpl_add(chat_id: int) -> None:
    """Begin add-template flow: ask for name."""
    _sessions[chat_id] = {"step": "tpl_add_name"}
    bot.send_message(chat_id, _t(chat_id, "notify_tpl_add_ask_name"),
                     parse_mode="Markdown", reply_markup=_cancel_kb(chat_id))


def on_tpl_add_name(chat_id: int, text: str) -> None:
    """Store template name, ask for body."""
    name = text.strip()
    if not name:
        bot.send_message(chat_id, _t(chat_id, "notify_tpl_add_ask_name"),
                         parse_mode="Markdown", reply_markup=_cancel_kb(chat_id))
        return
    _sessions[chat_id] = {"step": "tpl_add_body", "tpl_name": name}
    bot.send_message(chat_id, _t(chat_id, "notify_tpl_add_ask_body"),
                     parse_mode="Markdown", reply_markup=_cancel_kb(chat_id))


def on_tpl_add_body(chat_id: int, text: str) -> None:
    """Save new template."""
    body = text.strip()
    state = _sessions.pop(chat_id, {})
    name = state.get("tpl_name", "")
    if not body:
        _sessions[chat_id] = state
        _sessions[chat_id]["step"] = "tpl_add_body"
        bot.send_message(chat_id, _t(chat_id, "notify_tpl_add_ask_body"),
                         parse_mode="Markdown", reply_markup=_cancel_kb(chat_id))
        return
    templates = _load_templates()
    templates.append({"id": str(uuid.uuid4())[:8], "name": name, "body": body})
    _save_templates(templates)
    bot.send_message(chat_id, _t(chat_id, "notify_tpl_saved", name=name),
                     parse_mode="Markdown")
    show_tpl_menu(chat_id)


def start_tpl_edit(chat_id: int, tpl_id: str) -> None:
    """Begin edit-template flow: ask for new name."""
    tpl = _get_template(tpl_id)
    if not tpl:
        show_tpl_menu(chat_id)
        return
    _sessions[chat_id] = {"step": "tpl_edit_name", "tpl_id": tpl_id,
                           "tpl_name": tpl["name"], "tpl_body": tpl["body"]}
    bot.send_message(chat_id,
                     _t(chat_id, "notify_tpl_edit_ask_name", current=tpl["name"]),
                     parse_mode="Markdown", reply_markup=_cancel_kb(chat_id))


def on_tpl_edit_name(chat_id: int, text: str) -> None:
    """Store new name (or keep old), ask for new body."""
    state = _sessions.get(chat_id, {})
    new_name = text.strip()
    if new_name in ("-", ""):
        new_name = state.get("tpl_name", "")
    state["tpl_name_new"] = new_name
    state["step"] = "tpl_edit_body"
    _sessions[chat_id] = state
    bot.send_message(chat_id,
                     _t(chat_id, "notify_tpl_edit_ask_body",
                        current=state.get("tpl_body", "")),
                     parse_mode="Markdown", reply_markup=_cancel_kb(chat_id))


def on_tpl_edit_body(chat_id: int, text: str) -> None:
    """Save updated template."""
    state = _sessions.pop(chat_id, {})
    tpl_id = state.get("tpl_id")
    new_name = state.get("tpl_name_new") or state.get("tpl_name", "")
    new_body = text.strip() or state.get("tpl_body", "")
    templates = _load_templates()
    for tpl in templates:
        if tpl["id"] == tpl_id:
            tpl["name"] = new_name
            tpl["body"] = new_body
            break
    _save_templates(templates)
    bot.send_message(chat_id, _t(chat_id, "notify_tpl_updated"),
                     parse_mode="Markdown")
    show_tpl_view(chat_id, tpl_id)


def confirm_tpl_delete(chat_id: int, tpl_id: str) -> None:
    """Ask for delete confirmation."""
    tpl = _get_template(tpl_id)
    if not tpl:
        show_tpl_menu(chat_id)
        return
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "notify_tpl_btn_confirm_delete"),
                             callback_data=f"notify_tpl_del_confirm:{tpl_id}"),
        InlineKeyboardButton(_t(chat_id, "notify_btn_cancel"),
                             callback_data=f"notify_tpl_view:{tpl_id}"),
    )
    bot.send_message(chat_id,
                     _t(chat_id, "notify_tpl_delete_confirm", name=tpl["name"]),
                     parse_mode="Markdown", reply_markup=kb)


def do_tpl_delete(chat_id: int, tpl_id: str) -> None:
    """Delete template and return to list."""
    templates = [t for t in _load_templates() if t["id"] != tpl_id]
    _save_templates(templates)
    bot.send_message(chat_id, _t(chat_id, "notify_tpl_deleted"))
    show_tpl_menu(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
# Send notification flow
# ─────────────────────────────────────────────────────────────────────────────

def start_send(chat_id: int, owner_chat_id: int) -> None:
    """Begin send flow: choose template or write custom."""
    templates = _load_templates()
    kb = InlineKeyboardMarkup(row_width=1)
    for tpl in templates:
        kb.add(InlineKeyboardButton(
            _t(chat_id, "notify_tpl_item", name=tpl["name"]),
            callback_data=f"notify_tpl_pick:{tpl['id']}"
        ))
    kb.add(InlineKeyboardButton(_t(chat_id, "notify_btn_custom_msg"),
                                callback_data="notify_custom_msg"))
    kb.add(InlineKeyboardButton(_t(chat_id, "notify_btn_cancel"),
                                callback_data="notify_cancel"))
    _sessions[chat_id] = {"step": "pick_template", "owner": owner_chat_id}
    bot.send_message(chat_id, _t(chat_id, "notify_send_choose_tpl"),
                     parse_mode="Markdown", reply_markup=kb)


def on_tpl_picked(chat_id: int, tpl_id: str) -> None:
    """Template selected — ask for recipient selection."""
    tpl = _get_template(tpl_id)
    if not tpl:
        show_notify_menu(chat_id)
        return
    state = _sessions.get(chat_id, {})
    state["message"] = tpl["body"]
    state["step"] = "pick_recipients"
    _sessions[chat_id] = state
    _ask_recipients(chat_id)


def start_custom_msg(chat_id: int) -> None:
    """User wants to write a custom message."""
    state = _sessions.get(chat_id, {})
    state["step"] = "custom_msg"
    _sessions[chat_id] = state
    bot.send_message(chat_id, _t(chat_id, "notify_ask_custom_msg"),
                     parse_mode="Markdown", reply_markup=_cancel_kb(chat_id))


def on_custom_msg(chat_id: int, text: str) -> None:
    """Message text entered — ask for recipient selection."""
    state = _sessions.get(chat_id, {})
    state["message"] = text.strip()
    state["step"] = "pick_recipients"
    _sessions[chat_id] = state
    _ask_recipients(chat_id)


def _ask_recipients(chat_id: int) -> None:
    """Show All / Filter choice."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "notify_btn_all"),
                             callback_data="notify_recipients_all"),
        InlineKeyboardButton(_t(chat_id, "notify_btn_filter"),
                             callback_data="notify_recipients_filter"),
    )
    kb.add(InlineKeyboardButton(_t(chat_id, "notify_btn_cancel"),
                                callback_data="notify_cancel"))
    bot.send_message(chat_id, _t(chat_id, "notify_ask_filter"),
                     parse_mode="Markdown", reply_markup=kb)


def on_recipients_all(chat_id: int) -> None:
    """Send to all contacts with Telegram ID."""
    state = _sessions.get(chat_id, {})
    owner = state.get("owner", chat_id)
    contacts = _telegram_contacts(owner)
    if not contacts:
        bot.send_message(chat_id, _t(chat_id, "notify_no_contacts"),
                         parse_mode="Markdown")
        show_notify_menu(chat_id)
        _sessions.pop(chat_id, None)
        return
    state["recipients"] = contacts
    state["step"] = "preview"
    _sessions[chat_id] = state
    _show_preview(chat_id)


def start_filter_input(chat_id: int) -> None:
    """Ask user for filter string."""
    state = _sessions.get(chat_id, {})
    state["step"] = "filter_input"
    _sessions[chat_id] = state
    bot.send_message(chat_id, _t(chat_id, "notify_ask_filter"),
                     parse_mode="Markdown", reply_markup=_cancel_kb(chat_id))


def on_filter_input(chat_id: int, text: str) -> None:
    """Apply filter and show preview."""
    state = _sessions.get(chat_id, {})
    owner = state.get("owner", chat_id)
    query = text.strip()
    if query.lower() in ("-", "all", "все", "alle", ""):
        contacts = _telegram_contacts(owner)
    else:
        contacts = _filter_contacts(_telegram_contacts(owner), query)
    if not contacts:
        bot.send_message(chat_id,
                         _t(chat_id, "notify_no_contacts_filter", filter=query),
                         parse_mode="Markdown")
        _ask_recipients(chat_id)
        return
    state["recipients"] = contacts
    state["step"] = "preview"
    state["filter"] = query
    _sessions[chat_id] = state
    _show_preview(chat_id)


def _show_preview(chat_id: int) -> None:
    """Show preview message with recipient count + send/cancel buttons."""
    state = _sessions.get(chat_id, {})
    recipients = state.get("recipients", [])
    message = state.get("message", "")
    names = [c.get("name", "?") for c in recipients[:5]]
    names_str = ", ".join(names)
    if len(recipients) > 5:
        names_str += f", … (+{len(recipients) - 5})"
    msg_preview = message[:200] + ("…" if len(message) > 200 else "")
    text = _t(chat_id, "notify_preview",
              count=len(recipients), names=names_str, message=msg_preview)
    bot.send_message(chat_id, text, parse_mode="Markdown",
                     reply_markup=_preview_kb(chat_id))


def confirm_send(chat_id: int) -> None:
    """User confirmed — send messages in background thread."""
    state = _sessions.get(chat_id, {})
    if state.get("step") not in ("preview",):
        return
    state["step"] = "sending"
    _sessions[chat_id] = state
    bot.send_message(chat_id, _t(chat_id, "notify_sending"), parse_mode="Markdown")
    threading.Thread(target=_do_send, args=(chat_id,),
                     daemon=True, name=f"notify-send-{chat_id}").start()


def _do_send(chat_id: int) -> None:
    """Send messages to all recipients; report result."""
    state = _sessions.pop(chat_id, None)
    if not state:
        return
    recipients = state.get("recipients", [])
    message_tpl = state.get("message", "")
    sent = 0
    failed = 0
    for contact in recipients:
        tg_id = contact.get("_tg_id")
        name = contact.get("name", "")
        text = message_tpl.replace("{name}", name)
        try:
            bot.send_message(tg_id, text, parse_mode="Markdown")
            sent += 1
        except Exception as e:
            log.warning("[Notify] failed to send to tg_id=%s name=%s: %s",
                        tg_id, name, e)
            failed += 1
    total = sent + failed
    bot.send_message(chat_id,
                     _t(chat_id, "notify_done",
                        sent=sent, total=total, failed=failed),
                     parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# Text message dispatcher — called from telegram_menu_bot.py text_handler
# ─────────────────────────────────────────────────────────────────────────────

def handle_message(chat_id: int, text: str) -> bool:
    """Handle text input for active notify flow.

    Returns True if the message was consumed.
    """
    state = _sessions.get(chat_id)
    if not state:
        return False
    step = state.get("step")
    if step == "tpl_add_name":
        on_tpl_add_name(chat_id, text)
        return True
    if step == "tpl_add_body":
        on_tpl_add_body(chat_id, text)
        return True
    if step == "tpl_edit_name":
        on_tpl_edit_name(chat_id, text)
        return True
    if step == "tpl_edit_body":
        on_tpl_edit_body(chat_id, text)
        return True
    if step == "custom_msg":
        on_custom_msg(chat_id, text)
        return True
    if step == "filter_input":
        on_filter_input(chat_id, text)
        return True
    return False
