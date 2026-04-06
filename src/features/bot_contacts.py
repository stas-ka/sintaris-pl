"""
bot_contacts.py — Personal contact book (add / view / edit / delete / search).

Dependencies: bot_config, bot_state, bot_instance, bot_access, bot_db
"""

import json
import re

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

import core.bot_state as _st
from core.bot_config import log
from core.bot_instance import bot
from telegram.bot_access import (
    _is_allowed, _is_guest, _deny, _t, _lang,
    _ask_taris, _safe_edit, _send_menu,
)
from core.store import store as _store

# ── State ─────────────────────────────────────────────────────────────────────
# Multi-step add/edit state.  Keys are chat_id (int).
_pending_contact: dict[int, dict] = {}

# Steps for contact creation flow
_ADD_STEPS = ["name", "phone", "email", "address", "notes"]

# ── NL extraction prompt ──────────────────────────────────────────────────────
_CONTACT_EXTRACT_PROMPT = (
    'Extract contact details from the text. Return ONLY JSON:\n'
    '{{"name": "", "phone": "", "email": "", "address": "", "notes": ""}}\n'
    'Use null for absent fields. Name is required.\n'
    'Text: {text}'
)

# ── DB helpers ────────────────────────────────────────────────────────────────

def _contact_add(chat_id: int, name: str, phone: str = None, email: str = None,
                 address: str = None, notes: str = None) -> str:
    """Insert a new contact and return its id."""
    contact = {"name": name.strip(), "phone": phone or "", "email": email or "",
               "address": address or "", "notes": notes or ""}
    return _store.save_contact(chat_id, contact)


def _contact_get(chat_id: int, cid: str) -> dict | None:
    c = _store.get_contact(cid)
    if c and c.get("chat_id") == chat_id:
        return c
    return None


def _contact_update(chat_id: int, cid: str, **fields) -> bool:
    allowed = {"name", "phone", "email", "address", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    existing = _store.get_contact(cid)
    if not existing or existing.get("chat_id") != chat_id:
        return False
    existing.update(updates)
    _store.save_contact(chat_id, existing)
    return True


def _contact_delete(chat_id: int, cid: str) -> bool:
    existing = _store.get_contact(cid)
    if not existing or existing.get("chat_id") != chat_id:
        return False
    return _store.delete_contact(cid)


def _contact_list(chat_id: int, offset: int = 0, limit: int = 8) -> list[dict]:
    all_contacts = _store.list_contacts(chat_id)
    return all_contacts[offset:offset + limit]


def _contact_count(chat_id: int) -> int:
    return len(_store.list_contacts(chat_id))


def _contact_search(chat_id: int, query: str) -> list[dict]:
    return _store.search_contacts(chat_id, query)


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _contacts_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "contact_btn_add"),    callback_data="contact_create"),
        InlineKeyboardButton(_t(chat_id, "contact_btn_list"),   callback_data="contact_list"),
    )
    kb.add(InlineKeyboardButton(_t(chat_id, "contact_btn_search"), callback_data="contact_search"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
    return kb


def _contacts_list_keyboard(chat_id: int, contacts: list[dict],
                             offset: int = 0, total: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for c in contacts:
        kb.add(InlineKeyboardButton(
            f"👤 {c['name']}" + (f"  ·  {c['phone']}" if c.get("phone") else ""),
            callback_data=f"contact_open:{c['id']}"
        ))
    # Pagination
    row = []
    if offset > 0:
        row.append(InlineKeyboardButton("◀", callback_data=f"contact_page:{max(0, offset-8)}"))
    if offset + 8 < total:
        row.append(InlineKeyboardButton("▶", callback_data=f"contact_page:{offset+8}"))
    if row:
        kb.add(*row)
    kb.add(InlineKeyboardButton(_t(chat_id, "contact_btn_add"),  callback_data="contact_create"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu_contacts"))
    return kb


def _contact_detail_keyboard(chat_id: int, cid: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "contact_btn_edit"),   callback_data=f"contact_edit:{cid}"),
        InlineKeyboardButton(_t(chat_id, "contact_btn_delete"), callback_data=f"contact_del:{cid}"),
    )
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="contact_list"))
    return kb


def _contact_edit_field_keyboard(chat_id: int, cid: str) -> InlineKeyboardMarkup:
    """Choose which field to edit."""
    fields = [
        ("name",    "✏️ " + _t(chat_id, "contact_field_name")),
        ("phone",   "📞 " + _t(chat_id, "contact_field_phone")),
        ("email",   "📧 " + _t(chat_id, "contact_field_email")),
        ("address", "🏠 " + _t(chat_id, "contact_field_address")),
        ("notes",   "📝 " + _t(chat_id, "contact_field_notes")),
    ]
    kb = InlineKeyboardMarkup(row_width=1)
    for key, label in fields:
        kb.add(InlineKeyboardButton(label, callback_data=f"contact_edit_field:{cid}:{key}"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data=f"contact_open:{cid}"))
    return kb


# ── Formatting helpers ────────────────────────────────────────────────────────

def _format_contact(c: dict, chat_id: int) -> str:
    lines = [f"👤 *{c['name']}*"]
    if c.get("phone"):
        lines.append(f"📞 {c['phone']}")
    if c.get("email"):
        lines.append(f"📧 {c['email']}")
    if c.get("address"):
        lines.append(f"🏠 {c['address']}")
    if c.get("notes"):
        lines.append(f"📝 {c['notes']}")
    created = c.get("created_at", "")[:10]
    lines.append(f"\n_{_t(chat_id, 'contact_added')} {created}_")
    return "\n".join(lines)


# ── Menu / list / open ────────────────────────────────────────────────────────

def _handle_contacts_menu(chat_id: int) -> None:
    total = _contact_count(chat_id)
    text = _t(chat_id, "contact_menu_title") + f"\n\n{_t(chat_id, 'contact_count', n=total)}"
    bot.send_message(chat_id, text, parse_mode="Markdown",
                     reply_markup=_contacts_menu_keyboard(chat_id))


def _handle_contact_list(chat_id: int, offset: int = 0) -> None:
    total = _contact_count(chat_id)
    if total == 0:
        bot.send_message(chat_id, _t(chat_id, "contact_list_empty"),
                         reply_markup=_contacts_menu_keyboard(chat_id))
        return
    contacts = _contact_list(chat_id, offset=offset, limit=8)
    text = _t(chat_id, "contact_list_title", n=total)
    bot.send_message(chat_id, text, parse_mode="Markdown",
                     reply_markup=_contacts_list_keyboard(chat_id, contacts, offset, total))


def _handle_contact_open(chat_id: int, cid: str) -> None:
    c = _contact_get(chat_id, cid)
    if not c:
        bot.send_message(chat_id, _t(chat_id, "contact_not_found"))
        _handle_contacts_menu(chat_id)
        return
    bot.send_message(chat_id, _format_contact(c, chat_id), parse_mode="Markdown",
                     reply_markup=_contact_detail_keyboard(chat_id, cid))


# ── Add flow ──────────────────────────────────────────────────────────────────

def _start_contact_add(chat_id: int) -> None:
    _st._user_mode[chat_id] = "contact_add"
    _pending_contact[chat_id] = {"step": "name"}
    bot.send_message(chat_id, _t(chat_id, "contact_add_prompt_name"),
                     reply_markup=InlineKeyboardMarkup().add(
                         InlineKeyboardButton(_t(chat_id, "btn_cancel"), callback_data="cancel")
                     ))


def _finish_contact_add(chat_id: int, text: str) -> None:
    state = _pending_contact.get(chat_id, {})
    step = state.get("step", "name")
    value = text.strip() or None

    if step == "name" and not value:
        bot.send_message(chat_id, _t(chat_id, "contact_name_required"))
        return

    state[step] = value

    # Advance to next step
    idx = _ADD_STEPS.index(step)
    if idx + 1 < len(_ADD_STEPS):
        next_step = _ADD_STEPS[idx + 1]
        state["step"] = next_step
        _pending_contact[chat_id] = state
        prompt_key = f"contact_add_prompt_{next_step}"
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(_t(chat_id, "contact_btn_skip"), callback_data="contact_add_skip"),
            InlineKeyboardButton(_t(chat_id, "btn_cancel"),       callback_data="cancel"),
        )
        bot.send_message(chat_id, _t(chat_id, prompt_key), reply_markup=kb)
    else:
        # All steps done — save
        _pending_contact.pop(chat_id, None)
        _st._user_mode.pop(chat_id, None)
        cid = _contact_add(
            chat_id,
            name=state.get("name", ""),
            phone=state.get("phone"),
            email=state.get("email"),
            address=state.get("address"),
            notes=state.get("notes"),
        )
        bot.send_message(chat_id, _t(chat_id, "contact_saved", name=state.get("name", "")))
        _handle_contact_open(chat_id, cid)


def _handle_contact_add_skip(chat_id: int) -> None:
    """Skip the current optional step during add."""
    state = _pending_contact.get(chat_id)
    if not state:
        return
    _finish_contact_add(chat_id, "")


# ── Edit flow ─────────────────────────────────────────────────────────────────

def _start_contact_edit(chat_id: int, cid: str) -> None:
    c = _contact_get(chat_id, cid)
    if not c:
        bot.send_message(chat_id, _t(chat_id, "contact_not_found"))
        _handle_contacts_menu(chat_id)
        return
    bot.send_message(chat_id,
                     _t(chat_id, "contact_edit_choose_field", name=c["name"]),
                     parse_mode="Markdown",
                     reply_markup=_contact_edit_field_keyboard(chat_id, cid))


def _start_contact_edit_field(chat_id: int, cid: str, field: str) -> None:
    _st._user_mode[chat_id] = "contact_edit"
    _pending_contact[chat_id] = {"cid": cid, "field": field}
    prompt_key = f"contact_edit_prompt_{field}"
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(_t(chat_id, "btn_cancel"), callback_data="cancel")
    )
    bot.send_message(chat_id, _t(chat_id, prompt_key), reply_markup=kb)


def _finish_contact_edit(chat_id: int, text: str) -> None:
    state = _pending_contact.pop(chat_id, {})
    _st._user_mode.pop(chat_id, None)
    cid = state.get("cid")
    field = state.get("field")
    if not cid or not field:
        _handle_contacts_menu(chat_id)
        return
    value = text.strip() or None
    if field == "name" and not value:
        bot.send_message(chat_id, _t(chat_id, "contact_name_required"))
        _start_contact_edit_field(chat_id, cid, field)
        return
    _contact_update(chat_id, cid, **{field: value})
    bot.send_message(chat_id, _t(chat_id, "contact_updated"))
    _handle_contact_open(chat_id, cid)


# ── Delete flow ───────────────────────────────────────────────────────────────

def _handle_contact_delete(chat_id: int, cid: str) -> None:
    """Show delete confirmation card."""
    c = _contact_get(chat_id, cid)
    if not c:
        bot.send_message(chat_id, _t(chat_id, "contact_not_found"))
        _handle_contacts_menu(chat_id)
        return
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅  " + _t(chat_id, "contact_btn_confirm_delete"),
                             callback_data=f"contact_del_confirm:{cid}"),
        InlineKeyboardButton("❌  " + _t(chat_id, "btn_cancel"), callback_data=f"contact_open:{cid}"),
    )
    bot.send_message(chat_id, _t(chat_id, "contact_delete_confirm", name=c["name"]),
                     parse_mode="Markdown", reply_markup=kb)


def _handle_contact_delete_confirmed(chat_id: int, cid: str) -> None:
    _contact_delete(chat_id, cid)
    bot.send_message(chat_id, _t(chat_id, "contact_deleted"))
    _handle_contact_list(chat_id)


# ── Search flow ───────────────────────────────────────────────────────────────

def _start_contact_search(chat_id: int) -> None:
    _st._user_mode[chat_id] = "contact_search"
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(_t(chat_id, "btn_cancel"), callback_data="cancel")
    )
    bot.send_message(chat_id, _t(chat_id, "contact_search_prompt"), reply_markup=kb)


def _finish_contact_search(chat_id: int, query: str) -> None:
    _st._user_mode.pop(chat_id, None)
    results = _contact_search(chat_id, query)
    if not results:
        bot.send_message(chat_id, _t(chat_id, "contact_search_empty", q=query),
                         reply_markup=_contacts_menu_keyboard(chat_id))
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for c in results:
        kb.add(InlineKeyboardButton(
            f"👤 {c['name']}" + (f"  ·  {c['phone']}" if c.get("phone") else ""),
            callback_data=f"contact_open:{c['id']}"
        ))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu_contacts"))
    bot.send_message(chat_id,
                     _t(chat_id, "contact_search_results", q=query, n=len(results)),
                     parse_mode="Markdown",
                     reply_markup=kb)
