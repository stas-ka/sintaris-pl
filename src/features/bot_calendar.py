"""
bot_calendar.py — Smart calendar with natural-language event add/cancel/query.

Dependencies: bot_config, bot_state, bot_instance, bot_access
(bot_voice imported lazily inside functions to avoid circular imports)

Features:
  - Add one OR multiple events from a single message (multi-event parsing)
  - LLM-based natural language date/time parsing
  - Countdown display in event list ("through 2д 3ч")
  - Reminder 15 min before event (text + optional TTS voice note)
  - Morning briefing at 08:00 with today's events (text + optional TTS)
  - Timer rescheduling on bot restart
  - NL query: "events next week", "what's tomorrow?", "show March"
  - Delete confirmation before removal
  - Calendar console: free-form text commands (add/query/edit/delete)
  - All mutations require explicit user confirmation
"""

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

import core.bot_state as _st
from core.bot_config import CALENDAR_DIR, log
from core.bot_instance import bot
from core.bot_prompts import PROMPTS, fmt_prompt
from telegram.bot_access import (
    _t, _escape_md, _back_keyboard, _send_menu, _is_allowed,
)
from core.bot_llm import ask_llm
from telegram.bot_users import _resolve_storage_id
from core.store import store


# ─────────────────────────────────────────────────────────────────────────────
# In-flight "add event" state — exported so cancel handler can clear it
# ─────────────────────────────────────────────────────────────────────────────

_pending_cal: dict[int, dict] = {}   # chat_id → {"step": "input"}


# ─────────────────────────────────────────────────────────────────────────────
# Active reminder timers (in-memory; rebuilt on startup)
# ─────────────────────────────────────────────────────────────────────────────

_cal_timers: dict[str, threading.Timer] = {}   # event_id → Timer


# ─────────────────────────────────────────────────────────────────────────────
# Storage helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cal_user_file(chat_id: int) -> Path:
    d = Path(CALENDAR_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_resolve_storage_id(chat_id)}.json"


def _cal_load(chat_id: int) -> list:
    try:
        from core.store import store
        events = store.load_events(chat_id)
        if events:
            return events
    except Exception:
        pass
    fp = _cal_user_file(chat_id)
    try:
        return json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else []
    except Exception:
        return []


def _cal_save(chat_id: int, events: list) -> None:
    """Save events to DB (primary). JSON file kept as legacy backup."""
    try:
        for ev in events:
            store.save_event(chat_id, ev)
        # Remove DB events for this user that are not in the new list
        current_ids = {e.get("id") for e in events if e.get("id")}
        try:
            existing = store.load_events(chat_id)
            for ev in existing:
                if ev.get("id") and ev["id"] not in current_ids:
                    store.delete_event(chat_id, ev["id"])
        except Exception as _del_e:
            log.warning("[Cal] delete orphaned events failed: %s", _del_e)
    except Exception as _e:
        log.warning("[Cal] store.save_event failed: %s", _e)
        # Fallback: JSON write for safety
        try:
            _cal_user_file(chat_id).write_text(
                json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass


def _cal_add_event(chat_id: int, title: str, dt: datetime,
                   remind_before_min: int = 15) -> dict:
    events = _cal_load(chat_id)
    ev = {
        "id":               str(uuid.uuid4())[:8],
        "title":            title,
        "dt_iso":           dt.strftime("%Y-%m-%dT%H:%M"),
        "remind_before_min": remind_before_min,
        "reminded":         False,
    }
    events.append(ev)
    _cal_save(chat_id, events)
    return ev


def _cal_delete_event(chat_id: int, ev_id: str) -> bool:
    events = _cal_load(chat_id)
    new_events = [e for e in events if e.get("id") != ev_id]
    if len(new_events) < len(events):
        _cal_save(chat_id, new_events)  # DB-primary; _cal_save handles deletion
        return True
    return False


def _cal_mark_reminded(chat_id: int, ev_id: str) -> None:
    events = _cal_load(chat_id)
    for e in events:
        if e.get("id") == ev_id:
            e["reminded"] = True
    _cal_save(chat_id, events)


# ─────────────────────────────────────────────────────────────────────────────
# Countdown formatting
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_countdown(dt: datetime, lang: str) -> str:
    """Return a short countdown string like '⏰ через 2д 3ч' or 'now!'."""
    from telegram.bot_access import _STRINGS
    def s(key, **kw):
        text = _STRINGS.get(lang, _STRINGS.get("en", {})).get(key, key)
        return text.format(**kw) if kw else text
    total_s = int((dt - datetime.now()).total_seconds())
    if total_s < 0:
        return "⏰ " + s("cal_passed")
    if total_s < 60:
        return "⏰ " + s("cal_now")
    if total_s < 3600:
        mins = total_s // 60
        return "⏰ " + s("cal_in_mins", mins=mins)
    if total_s < 86400:
        h = total_s // 3600
        m = (total_s % 3600) // 60
        return "⏰ " + s("cal_in_hours", h=h, m=m)
    days = total_s // 86400
    h = (total_s % 86400) // 3600
    return "⏰ " + s("cal_in_days", days=days, h=h)


# ─────────────────────────────────────────────────────────────────────────────
# Inline keyboards
# ─────────────────────────────────────────────────────────────────────────────

def _calendar_keyboard(chat_id: int, events: list) -> InlineKeyboardMarkup:
    """Main calendar keyboard: upcoming events (or recent past if none) + Add + Back."""
    lang = _st._user_lang.get(chat_id, "ru")
    kb = InlineKeyboardMarkup(row_width=1)
    now = datetime.now()
    upcoming = sorted(
        [e for e in events if datetime.fromisoformat(e["dt_iso"]) > now],
        key=lambda e: e["dt_iso"],
    )
    display = upcoming[:8]
    if not display:
        # No upcoming events — show recent past so user can view/delete them
        display = sorted(
            [e for e in events if datetime.fromisoformat(e["dt_iso"]) <= now],
            key=lambda e: e["dt_iso"],
            reverse=True,
        )[:8]
    for ev in display:
        dt = datetime.fromisoformat(ev["dt_iso"])
        cdown = _fmt_countdown(dt, lang)
        dt_str = dt.strftime("%d.%m %H:%M")
        label = f"🗓 {ev['title']} · {dt_str}  {cdown}"
        kb.add(InlineKeyboardButton(label, callback_data=f"cal_event:{ev['id']}"))
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_add"), callback_data="cal_add"))
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_console"), callback_data="cal_console"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
    return kb


def _cal_confirm_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown after LLM parses a new event — confirm or edit before saving."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "cal_btn_save"), callback_data="cal_confirm_save"),
        InlineKeyboardButton(_t(chat_id, "cal_btn_cancel"), callback_data="cancel"),
    )
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_read_aloud"), callback_data="cal_confirm_tts"))
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_edit_title"), callback_data="cal_confirm_edit_title"))
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_edit_dt"), callback_data="cal_confirm_edit_dt"))
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_edit_remind"), callback_data="cal_confirm_edit_remind"))
    return kb


def _cal_event_keyboard(chat_id: int, ev_id: str) -> InlineKeyboardMarkup:
    """Event detail keyboard: edit, reschedule, delete + back."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "cal_btn_edit"), callback_data=f"cal_edit_title:{ev_id}"),
        InlineKeyboardButton(_t(chat_id, "cal_btn_reschedule"), callback_data=f"cal_edit_dt:{ev_id}"),
    )
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_edit_remind_short"), callback_data=f"cal_edit_remind:{ev_id}"))
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_read_aloud"), callback_data=f"cal_tts:{ev_id}"))
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_delete"), callback_data=f"cal_del:{ev_id}"))
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_send_email"), callback_data=f"cal_email:{ev_id}"))
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_back"), callback_data="menu_calendar"))
    return kb
def _handle_calendar_menu(chat_id: int) -> None:
    """Show the calendar: summary of upcoming events + action buttons."""
    lang = _st._user_lang.get(chat_id, "ru")
    events = _cal_load(chat_id)
    now = datetime.now()
    upcoming = sorted(
        [e for e in events if datetime.fromisoformat(e["dt_iso"]) > now],
        key=lambda e: e["dt_iso"],
    )
    if not events:
        header = _t(chat_id, "cal_empty")
    elif not upcoming:
        # Has events but all in the past — show recent ones
        past = sorted(
            [e for e in events if datetime.fromisoformat(e["dt_iso"]) <= now],
            key=lambda e: e["dt_iso"],
            reverse=True,
        )[:5]
        lines = ["🗓 *" + _t(chat_id, "cal_header") + "*\n"]
        lines.append("_" + _t(chat_id, "cal_no_upcoming") + "_\n")
        for ev in past:
            dt = datetime.fromisoformat(ev["dt_iso"])
            cdown = _fmt_countdown(dt, lang)
            lines.append(f"• {_escape_md(ev['title'])} — {dt.strftime('%d.%m %H:%M')} {cdown}")
        header = "\n".join(lines)
    else:
        lines = ["🗓 *" + _t(chat_id, "cal_header") + "*\n"]
        for ev in upcoming[:5]:
            dt = datetime.fromisoformat(ev["dt_iso"])
            cdown = _fmt_countdown(dt, lang)
            lines.append(f"• *{_escape_md(ev['title'])}* — {dt.strftime('%d.%m %H:%M')} {cdown}")
        header = "\n".join(lines)

    bot.send_message(chat_id, header, parse_mode="Markdown",
                     reply_markup=_calendar_keyboard(chat_id, events))


def _handle_cal_event_detail(chat_id: int, ev_id: str) -> None:
    """Show event detail with delete button."""
    lang = _st._user_lang.get(chat_id, "ru")
    events = _cal_load(chat_id)
    ev = next((e for e in events if e.get("id") == ev_id), None)
    if not ev:
        _handle_calendar_menu(chat_id)
        return
    dt = datetime.fromisoformat(ev["dt_iso"])
    cdown = _fmt_countdown(dt, lang)
    text = (f"🗓 *{_escape_md(ev['title'])}*\n"
            f"📅 {dt.strftime('%d.%m.%Y %H:%M')}\n{cdown}")
    bot.send_message(chat_id, text, parse_mode="Markdown",
                     reply_markup=_cal_event_keyboard(chat_id, ev_id))


# ─────────────────────────────────────────────────────────────────────────────
# Add event flow
# ─────────────────────────────────────────────────────────────────────────────

def _start_cal_add(chat_id: int) -> None:
    """Enter calendar-add mode: prompt user for free-form event description."""
    _pending_cal[chat_id] = {"step": "input"}
    _st._user_mode[chat_id] = "calendar"

    prompt = _t(chat_id, "cal_add_prompt_ru")
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_cancel"), callback_data="cancel"))
    bot.send_message(chat_id, prompt, parse_mode="Markdown", reply_markup=kb)


def _finish_cal_add(chat_id: int, text: str) -> None:
    """Parse user input via LLM — extracts ONE or MULTIPLE events → confirmation."""
    lang = _st._user_lang.get(chat_id, "ru")
    _pending_cal.pop(chat_id, None)
    _st._user_mode.pop(chat_id, None)

    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M")
    prompt = fmt_prompt(PROMPTS["calendar"]["event_parse"], now_iso=now_iso, text=text)

    thinking_msg = bot.send_message(chat_id, _t(chat_id, "cal_parsing"))

    def _run():
        raw = ask_llm(prompt, timeout=60)
        try:
            bot.delete_message(chat_id, thinking_msg.message_id)
        except Exception:
            pass

        if not raw:
            bot.send_message(
                chat_id,
                _t(chat_id, "cal_no_llm"),
                reply_markup=_calendar_keyboard(chat_id, _cal_load(chat_id)),
            )
            return

        try:
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON block found in LLM response")
            parsed = json.loads(json_match.group())
            events_raw = parsed.get("events", [])
            if not events_raw:
                raise ValueError("LLM returned empty events list")

            drafts = []
            for item in events_raw:
                title = str(item.get("title", "")).strip()
                dt_str = str(item.get("dt", "")).strip()
                if not title or not dt_str:
                    continue
                # Normalize partial ISO "YYYY-MM-DDTHH" → "YYYY-MM-DDTHH:00"
                if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}$', dt_str):
                    dt_str += ':00'
                dt = datetime.fromisoformat(dt_str)
                drafts.append({
                    "title":             title,
                    "dt_iso":            dt.strftime("%Y-%m-%dT%H:%M"),
                    "remind_before_min": 15,
                })

            if not drafts:
                raise ValueError("No valid events parsed")

        except Exception as e:
            log.warning(f"[Cal] LLM parse failed for chat {chat_id}: {e}  raw={raw[:200]!r}")
            bot.send_message(chat_id, _t(chat_id, "cal_parse_fail"), parse_mode="Markdown",
                             reply_markup=_calendar_keyboard(chat_id, _cal_load(chat_id)))
            return

        if len(drafts) == 1:
            _pending_cal[chat_id] = {"step": "confirm", **drafts[0]}
            _show_cal_confirm(chat_id)
        else:
            _pending_cal[chat_id] = {"step": "multi_confirm", "events": drafts, "idx": 0}
            _show_cal_confirm_multi(chat_id)

    threading.Thread(target=_run, daemon=True).start()


def _show_cal_confirm(chat_id: int) -> None:
    """Send the confirmation card for a pending new event."""
    lang  = _st._user_lang.get(chat_id, "ru")
    draft = _pending_cal.get(chat_id, {})
    title = draft.get("title", "—")
    dt    = datetime.fromisoformat(draft.get("dt_iso", datetime.now().strftime("%Y-%m-%dT%H:%M")))
    remind_min = int(draft.get("remind_before_min", 15))
    cdown = _fmt_countdown(dt, lang)
    dt_fmt = dt.strftime("%d.%m.%Y %H:%M")

    header  = _t(chat_id, "cal_confirm_header")
    t_label = _t(chat_id, "cal_confirm_label_title")
    d_label = _t(chat_id, "cal_confirm_label_dt")
    r_label = _t(chat_id, "cal_confirm_label_remind")
    remind_str = _t(chat_id, "cal_confirm_remind_str", min=remind_min)

    text = (
        f"{header}\n\n"
        f"{t_label}: *{_escape_md(title)}*\n"
        f"{d_label}: {dt_fmt}  {cdown}\n"
        f"{r_label}: {remind_str}"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown",
                     reply_markup=_cal_confirm_keyboard(chat_id))


def _cal_confirm_keyboard_multi(chat_id: int, idx: int, total: int) -> InlineKeyboardMarkup:
    """Keyboard for multi-event batch confirmation (N of M flow)."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "cal_btn_save"), callback_data="cal_multi_save_one"),
        InlineKeyboardButton(_t(chat_id, "cal_btn_skip"), callback_data="cal_multi_skip"),
    )
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_save_all"), callback_data="cal_multi_save_all"))
    kb.add(InlineKeyboardButton(_t(chat_id, "cal_btn_cancel"), callback_data="cancel"))
    return kb


def _show_cal_confirm_multi(chat_id: int) -> None:
    """Show confirmation card for current event in a multi-event batch."""
    lang  = _st._user_lang.get(chat_id, "ru")
    state = _pending_cal.get(chat_id, {})
    events = state.get("events", [])
    idx    = state.get("idx", 0)
    total  = len(events)

    if idx >= total:
        _pending_cal.pop(chat_id, None)
        _handle_calendar_menu(chat_id)
        return

    draft = events[idx]
    title      = draft.get("title", "—")
    dt         = datetime.fromisoformat(draft.get("dt_iso", datetime.now().strftime("%Y-%m-%dT%H:%M")))
    remind_min = int(draft.get("remind_before_min", 15))
    cdown      = _fmt_countdown(dt, lang)
    dt_fmt     = dt.strftime("%d.%m.%Y %H:%M")

    header     = _t(chat_id, "cal_multi_confirm_header", idx=idx + 1, total=total)
    t_label    = _t(chat_id, "cal_confirm_label_title")
    d_label    = _t(chat_id, "cal_confirm_label_dt")
    r_label    = _t(chat_id, "cal_confirm_label_remind")
    remind_str = _t(chat_id, "cal_confirm_remind_str", min=remind_min)

    text = (
        f"{header}\n\n"
        f"{t_label}: *{_escape_md(title)}*\n"
        f"{d_label}: {dt_fmt}  {cdown}\n"
        f"{r_label}: {remind_str}"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown",
                     reply_markup=_cal_confirm_keyboard_multi(chat_id, idx, total))


def _cal_multi_save_one(chat_id: int) -> None:
    """Save current event in the multi-batch, advance to next."""
    lang  = _st._user_lang.get(chat_id, "ru")
    state = _pending_cal.get(chat_id, {})
    events = state.get("events", [])
    idx    = state.get("idx", 0)

    if idx < len(events):
        draft = events[idx]
        dt    = datetime.fromisoformat(draft["dt_iso"])
        ev    = _cal_add_event(chat_id, draft["title"], dt, draft.get("remind_before_min", 15))
        _schedule_reminder(chat_id, ev)
        cdown = _fmt_countdown(dt, lang)
        bot.send_message(
            chat_id,
            f"✅ *{_t(chat_id, 'cal_saved_prefix')}:* {_escape_md(draft['title'])} — {dt.strftime('%d.%m %H:%M')} {cdown}",
            parse_mode="Markdown",
        )

    state["idx"] = idx + 1
    if state["idx"] >= len(events):
        _pending_cal.pop(chat_id, None)
        _handle_calendar_menu(chat_id)
    else:
        _show_cal_confirm_multi(chat_id)


def _cal_multi_skip(chat_id: int) -> None:
    """Skip current event in the multi-batch, advance to next."""
    lang  = _st._user_lang.get(chat_id, "ru")
    state = _pending_cal.get(chat_id, {})
    events = state.get("events", [])
    idx    = state.get("idx", 0)
    if idx < len(events):
        skipped = events[idx].get("title", "")
        bot.send_message(
            chat_id,
            f"⏭ *{_t(chat_id, 'cal_skipped_prefix')}:* {_escape_md(skipped)}",
            parse_mode="Markdown",
        )
    state["idx"] = idx + 1
    if state["idx"] >= len(events):
        _pending_cal.pop(chat_id, None)
        _handle_calendar_menu(chat_id)
    else:
        _show_cal_confirm_multi(chat_id)


def _cal_multi_save_all(chat_id: int) -> None:
    """Save ALL remaining events in the multi-batch without further confirmation."""
    lang  = _st._user_lang.get(chat_id, "ru")
    state = _pending_cal.pop(chat_id, {})
    events = state.get("events", [])
    idx    = state.get("idx", 0)
    saved  = 0
    for draft in events[idx:]:
        dt = datetime.fromisoformat(draft["dt_iso"])
        ev = _cal_add_event(chat_id, draft["title"], dt, draft.get("remind_before_min", 15))
        _schedule_reminder(chat_id, ev)
        saved += 1

    summary = _t(chat_id, "cal_saved_count", n=saved)
    bot.send_message(chat_id, summary, parse_mode="Markdown")
    _handle_calendar_menu(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
# Delete with confirmation
# ─────────────────────────────────────────────────────────────────────────────

def _handle_cal_delete_request(chat_id: int, ev_id: str) -> None:
    """Show confirmation dialog before deleting an event."""
    lang = _st._user_lang.get(chat_id, "ru")
    events = _cal_load(chat_id)
    ev = next((e for e in events if e.get("id") == ev_id), None)
    if not ev:
        _handle_calendar_menu(chat_id)
        return

    dt    = datetime.fromisoformat(ev["dt_iso"])
    cdown = _fmt_countdown(dt, lang)
    text  = (
        f"{_t(chat_id, 'cal_del_prompt')}\n\n"
        f"📌 *{_escape_md(ev['title'])}*\n"
        f"📅 {dt.strftime('%d.%m.%Y %H:%M')}  {cdown}"
    )
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(
            _t(chat_id, "cal_btn_confirm_delete"),
            callback_data=f"cal_del_confirm:{ev_id}",
        ),
        InlineKeyboardButton(
            _t(chat_id, "cal_btn_cancel"),
            callback_data="menu_calendar",
        ),
    )
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


# ─────────────────────────────────────────────────────────────────────────────
# NL query — "show events next week / tomorrow / in March"
# ─────────────────────────────────────────────────────────────────────────────

def _handle_calendar_query(chat_id: int, text: str) -> None:
    """Handle a natural-language query about calendar events."""
    lang = _st._user_lang.get(chat_id, "ru")
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M")
    prompt = fmt_prompt(PROMPTS["calendar"]["date_range"], now_iso=now_iso, text=text)
    thinking = bot.send_message(chat_id, _t(chat_id, "cal_searching"))

    def _run():
        raw = ask_llm(prompt, timeout=60)
        try:
            bot.delete_message(chat_id, thinking.message_id)
        except Exception:
            pass

        try:
            m = re.search(r'\{[^{}]+\}', raw or "", re.DOTALL)
            if not m:
                raise ValueError("No JSON")
            data      = json.loads(m.group())
            from_date = datetime.fromisoformat(data["from"]).date()
            to_date   = datetime.fromisoformat(data["to"]).date()
            label     = data.get("label", f"{from_date} – {to_date}")
        except Exception:
            from_date = datetime.now().date()
            to_date   = from_date + timedelta(days=7)
            label     = _t(chat_id, "cal_default_label")

        events = _cal_load(chat_id)
        matched = sorted(
            [e for e in events
             if from_date <= datetime.fromisoformat(e["dt_iso"]).date() <= to_date],
            key=lambda e: e["dt_iso"],
        )

        if not matched:
            msg = (f"📅 *{_escape_md(label)}*\n\n" + _t(chat_id, "cal_no_events"))
        else:
            lines = [f"📅 *{_escape_md(label)}* — {len(matched)} "
                     + _t(chat_id, "cal_events_count"), ""]
            for ev in matched:
                dt    = datetime.fromisoformat(ev["dt_iso"])
                cdown = _fmt_countdown(dt, lang)
                lines.append(f"• *{_escape_md(ev['title'])}* — {dt.strftime('%d.%m %H:%M')} {cdown}")
            msg = "\n".join(lines)

        bot.send_message(chat_id, msg, parse_mode="Markdown",
                         reply_markup=_calendar_keyboard(chat_id, _cal_load(chat_id)))

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Calendar console — free-form command interface
# ─────────────────────────────────────────────────────────────────────────────

def _start_cal_console(chat_id: int) -> None:
    """Enter calendar console mode."""
    _st._user_mode[chat_id] = "cal_console"
    prompt = _t(chat_id, "cal_console_prompt")
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        _t(chat_id, "cal_btn_exit"),
        callback_data="menu_calendar",
    ))
    bot.send_message(chat_id, prompt, parse_mode="Markdown", reply_markup=kb)


def _handle_cal_console(chat_id: int, text: str) -> None:
    """Process a free-form calendar console command via LLM intent classifier.

    The LLM acts as a classifier only — Do NOT perform the action directly.
    Returns JSON intent; local handlers execute the actual calendar operation.
    """
    lang = _st._user_lang.get(chat_id, "ru")
    _st._user_mode.pop(chat_id, None)

    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M")
    events  = _cal_load(chat_id)
    event_titles = [f"id={e['id']} title={e['title']!r}" for e in events[:10]]
    events_hint  = "; ".join(event_titles) if event_titles else "none"

    prompt = fmt_prompt(PROMPTS["calendar"]["intent"], now_iso=now_iso, events_hint=events_hint, text=text)

    thinking = bot.send_message(chat_id, _t(chat_id, "cal_analyzing"))

    def _run():
        raw = ask_llm(prompt, timeout=60)
        try:
            bot.delete_message(chat_id, thinking.message_id)
        except Exception:
            pass

        intent = "add"
        ev_id  = None
        try:
            m = re.search(r'\{[^{}]+\}', raw or "", re.DOTALL)
            if m:
                data   = json.loads(m.group())
                intent = data.get("intent", "add")
                ev_id  = data.get("ev_id") or None
        except Exception as e:
            log.debug(f"[Cal] console intent parse failed: {e}")

        if intent == "query":
            _handle_calendar_query(chat_id, text)
        elif intent == "delete":
            if ev_id:
                _handle_cal_delete_request(chat_id, ev_id)
            else:
                ev = _cal_find_by_text(chat_id, text)
                if ev:
                    _handle_cal_delete_request(chat_id, ev["id"])
                else:
                    bot.send_message(
                        chat_id,
                        _t(chat_id, "cal_event_not_found"),
                        reply_markup=_calendar_keyboard(chat_id, events),
                    )
        elif intent == "edit":
            if ev_id:
                _handle_cal_event_detail(chat_id, ev_id)
            else:
                ev = _cal_find_by_text(chat_id, text)
                if ev:
                    _handle_cal_event_detail(chat_id, ev["id"])
                else:
                    bot.send_message(
                        chat_id,
                        _t(chat_id, "cal_event_not_found"),
                        reply_markup=_calendar_keyboard(chat_id, events),
                    )
        else:
            # Default: treat as add
            _st._user_mode[chat_id] = "calendar"
            _finish_cal_add(chat_id, text)

    threading.Thread(target=_run, daemon=True).start()


def _cal_find_by_text(chat_id: int, text: str) -> Optional[dict]:
    """Find the first event whose title appears (case-insensitive) in user text."""
    events = _cal_load(chat_id)
    text_l = text.lower()
    for ev in events:
        if ev.get("title", "").lower() in text_l:
            return ev
    return None


def _cal_do_confirm_save(chat_id: int) -> None:
    """User confirmed — save the pending event and schedule its reminder."""
    lang  = _st._user_lang.get(chat_id, "ru")
    draft = _pending_cal.pop(chat_id, {})
    _st._user_mode.pop(chat_id, None)

    title      = draft.get("title", "—")
    dt_iso     = draft.get("dt_iso", datetime.now().strftime("%Y-%m-%dT%H:%M"))
    remind_min = int(draft.get("remind_before_min", 15))
    dt         = datetime.fromisoformat(dt_iso)

    ev    = _cal_add_event(chat_id, title, dt, remind_before_min=remind_min)
    cdown = _fmt_countdown(dt, lang)
    dt_fmt = dt.strftime("%d.%m.%Y %H:%M")

    confirm = (
        f"✅ *{_t(chat_id, 'cal_event_saved_prefix')}*\n"
        f"📌 {_escape_md(title)}\n"
        f"📅 {dt_fmt}  {cdown}"
    )
    bot.send_message(chat_id, confirm, parse_mode="Markdown",
                     reply_markup=_calendar_keyboard(chat_id, _cal_load(chat_id)))
    _schedule_reminder(chat_id, ev)


def _cal_prompt_edit_field(chat_id: int, field: str,
                            ev_id: Optional[str] = None) -> None:
    """Prompt the user to enter a new value for a specific event field.

    For a *new* event (confirmation stage): ev_id is None, state in _pending_cal.
    For an *existing* event (post-save edit): ev_id is the event's id.
    """
    lang = _st._user_lang.get(chat_id, "ru")

    if ev_id:
        # Edit existing saved event
        events = _cal_load(chat_id)
        ev = next((e for e in events if e.get("id") == ev_id), None)
        if ev is None:
            _handle_calendar_menu(chat_id)
            return
        current_title     = ev.get("title", "")
        current_dt_iso    = ev.get("dt_iso", "")
        current_remind    = ev.get("remind_before_min", 15)
        _pending_cal[chat_id] = {
            "step":              f"event_edit_{field}",
            "ev_id":             ev_id,
            "title":             current_title,
            "dt_iso":            current_dt_iso,
            "remind_before_min": current_remind,
        }
    else:
        # Edit during confirmation flow
        draft = _pending_cal.get(chat_id, {})
        draft["step"] = f"confirm_edit_{field}"
        _pending_cal[chat_id] = draft

    _st._user_mode[chat_id] = f"cal_edit_{field}"

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        _t(chat_id, "cal_btn_cancel"),
        callback_data="cancel",
    ))

    if field == "title":
        prompt = _t(chat_id, "cal_edit_title_prompt")
    elif field == "dt":
        prompt = _t(chat_id, "cal_edit_dt_prompt")
    else:  # remind
        prompt = _t(chat_id, "cal_edit_remind_prompt")

    bot.send_message(chat_id, prompt, parse_mode="Markdown", reply_markup=kb)


def _apply_cal_edit(chat_id: int, draft: dict, ev_id: str | None) -> None:
    """Apply a completed calendar field edit — save to disk or return to confirm screen."""
    if ev_id:
        events = _cal_load(chat_id)
        for ev in events:
            if ev.get("id") == ev_id:
                ev["title"]             = draft.get("title", ev["title"])
                ev["dt_iso"]            = draft.get("dt_iso", ev["dt_iso"])
                ev["remind_before_min"] = int(draft.get("remind_before_min", 15))
                ev["reminded"]          = False
                break
        _cal_save(chat_id, events)
        _pending_cal.pop(chat_id, None)
        ev_updated = next((e for e in _cal_load(chat_id) if e.get("id") == ev_id), None)
        if ev_updated:
            _schedule_reminder(chat_id, ev_updated)
            _handle_cal_event_detail(chat_id, ev_id)
        else:
            _handle_calendar_menu(chat_id)
    else:
        _pending_cal[chat_id] = draft
        _show_cal_confirm(chat_id)


def _cal_handle_edit_input(chat_id: int, text: str, field: str) -> None:
    """Process user's text input for editing a calendar event field."""
    lang  = _st._user_lang.get(chat_id, "ru")
    draft = _pending_cal.get(chat_id, {})
    step  = draft.get("step", "")
    ev_id = draft.get("ev_id")          # None for confirmation-stage edits

    _st._user_mode.pop(chat_id, None)

    if field == "title":
        new_title = text.strip()[:200]
        if not new_title:
            bot.send_message(
                chat_id,
                _t(chat_id, "cal_title_empty"),
            )
            _cal_prompt_edit_field(chat_id, "title", ev_id)
            return
        draft["title"] = new_title

    elif field == "dt":
        # Re-parse via LLM — must be async to avoid blocking worker thread
        now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M")
        prompt = fmt_prompt(PROMPTS["calendar"]["edit_dt"], now_iso=now_iso, text=text)
        thinking = bot.send_message(chat_id, _t(chat_id, "cal_parsing_date"))
        _draft_ref = draft  # capture for closure

        def _run_dt():
            raw = ask_llm(prompt, timeout=60)
            try:
                bot.delete_message(chat_id, thinking.message_id)
            except Exception:
                pass
            try:
                m = re.search(r'\{[^{}]+\}', raw or "", re.DOTALL)
                parsed = json.loads(m.group()) if m else {}
                new_dt = datetime.fromisoformat(parsed["dt"])
                _draft_ref["dt_iso"] = new_dt.strftime("%Y-%m-%dT%H:%M")
            except Exception as exc:
                log.warning(f"[Cal] dt parse failed: {exc}  raw={raw!r}")
                bot.send_message(chat_id, _t(chat_id, "cal_date_parse_fail"), parse_mode="Markdown")
                _cal_prompt_edit_field(chat_id, "dt", ev_id)
                return
            _apply_cal_edit(chat_id, _draft_ref, ev_id)

        threading.Thread(target=_run_dt, daemon=True).start()
        return

    else:  # remind
        try:
            minutes = int(re.search(r'\d+', text).group())
            if minutes < 0 or minutes > 10000:
                raise ValueError("out of range")
            draft["remind_before_min"] = minutes
        except Exception:
            bot.send_message(chat_id, _t(chat_id, "cal_remind_invalid"))
            _cal_prompt_edit_field(chat_id, "remind", ev_id)
            return

    _apply_cal_edit(chat_id, draft, ev_id)


# ─────────────────────────────────────────────────────────────────────────────
# Read aloud (TTS) for events
# ─────────────────────────────────────────────────────────────────────────────

def _cal_tts_text(chat_id: int, ev: dict) -> str:
    """Build TTS string for an event."""
    lang = _st._user_lang.get(chat_id, "ru")
    from telegram.bot_access import _STRINGS
    tmpl = _STRINGS.get(lang, _STRINGS.get("en", {})).get("cal_tts_event_text", "Event: {title}. Date: {dt_fmt}.")
    dt_fmt = ev["dt"].strftime("%d %B %Y %H:%M")
    return tmpl.format(title=ev["title"], dt_fmt=dt_fmt)


def _handle_cal_event_tts(chat_id: int, ev_id: str) -> None:
    """Synthesise and send a voice note for a saved event."""
    lang = _st._user_lang.get(chat_id, "ru")
    events = _cal_load(chat_id)
    ev = next((e for e in events if e.get("id") == ev_id), None)
    if not ev:
        _handle_calendar_menu(chat_id)
        return
    ev_dict = {"title": ev["title"], "dt": datetime.fromisoformat(ev["dt_iso"]), "dt_iso": ev["dt_iso"]}
    tts_text = _cal_tts_text(chat_id, ev_dict)
    placeholder = bot.send_message(
        chat_id,
        _t(chat_id, "cal_tts_generating"),
    )
    try:
        from features.bot_voice import _tts_to_ogg  # noqa: PLC0415
        ogg = _tts_to_ogg(tts_text, lang=lang)
        if ogg:
            bot.delete_message(chat_id, placeholder.message_id)
            dt = datetime.fromisoformat(ev["dt_iso"])
            caption = f"🗓 *{_escape_md(ev['title'])}* — {dt.strftime('%d.%m.%Y %H:%M')}"
            bot.send_voice(chat_id, ogg, caption=caption, parse_mode="Markdown")
        else:
            bot.edit_message_text(
                _t(chat_id, "cal_tts_error"),
                chat_id, placeholder.message_id,
            )
    except Exception as e:
        log.warning(f"[Cal] TTS event failed: {e}")
        bot.edit_message_text(
            _t(chat_id, "cal_tts_error"),
            chat_id, placeholder.message_id,
        )


def _handle_cal_confirm_tts(chat_id: int) -> None:
    """Synthesise and send a voice note for the pending (not yet saved) event."""
    lang = _st._user_lang.get(chat_id, "ru")
    draft = _pending_cal.get(chat_id, {})
    title  = draft.get("title")
    dt_iso = draft.get("dt_iso")
    if not title or not dt_iso:
        return
    tts_text = _cal_tts_text(chat_id, {"title": title, "dt": datetime.fromisoformat(dt_iso), "dt_iso": dt_iso})
    placeholder = bot.send_message(
        chat_id,
        _t(chat_id, "cal_tts_generating"),
    )
    try:
        from features.bot_voice import _tts_to_ogg  # noqa: PLC0415
        ogg = _tts_to_ogg(tts_text, lang=lang)
        if ogg:
            bot.delete_message(chat_id, placeholder.message_id)
            dt = datetime.fromisoformat(dt_iso)
            caption = (f"🗓 *{_escape_md(title)}* — {dt.strftime('%d.%m.%Y %H:%M')}"
                       + "\n" + _t(chat_id, "cal_not_saved"))
            bot.send_voice(chat_id, ogg, caption=caption, parse_mode="Markdown")
        else:
            bot.edit_message_text(
                _t(chat_id, "cal_tts_error"),
                chat_id, placeholder.message_id,
            )
    except Exception as e:
        log.warning(f"[Cal] TTS confirm failed: {e}")
        bot.edit_message_text(
            _t(chat_id, "cal_tts_error"),
            chat_id, placeholder.message_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Delete / cancel event
# ─────────────────────────────────────────────────────────────────────────────

def _handle_cal_cancel_event(chat_id: int, ev_id: str) -> None:
    """Show delete confirmation (keeps backward compat — routes to _handle_cal_delete_request)."""
    _handle_cal_delete_request(chat_id, ev_id)


def _handle_cal_delete_confirmed(chat_id: int, ev_id: str) -> None:
    """Actually delete the event after user confirmed."""
    lang = _st._user_lang.get(chat_id, "ru")
    events = _cal_load(chat_id)
    ev = next((e for e in events if e.get("id") == ev_id), None)

    if _cal_delete_event(chat_id, ev_id):
        old_timer = _cal_timers.pop(ev_id, None)
        if old_timer:
            old_timer.cancel()
        title = ev.get("title", ev_id) if ev else ev_id
        msg = f"🗑 {_t(chat_id, 'cal_deleted')}: *{_escape_md(title)}*"
        bot.send_message(chat_id, msg, parse_mode="Markdown",
                         reply_markup=_calendar_keyboard(chat_id, _cal_load(chat_id)))
    else:
        _handle_calendar_menu(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
# Reminder timer management
# ─────────────────────────────────────────────────────────────────────────────

def _send_reminder(chat_id: int, ev_id: str, title: str, dt_iso: str) -> None:
    """Fired by threading.Timer: send a text + optional TTS voice reminder."""
    try:
        lang = _st._user_lang.get(chat_id, "ru")
        dt_fmt = datetime.fromisoformat(dt_iso).strftime("%H:%M")
        tts_text = _t(chat_id, "cal_reminder_text_ru").format(title=title, dt_fmt=dt_fmt)
        msg_text = f"🔔 *{_escape_md(tts_text)}*"
        bot.send_message(chat_id, msg_text, parse_mode="Markdown")
        _cal_mark_reminded(chat_id, ev_id)
        _cal_timers.pop(ev_id, None)

        # Optional TTS voice note (deferred import to avoid circular at module load)
        try:
            from features.bot_voice import _tts_to_ogg  # noqa: PLC0415  deferred on purpose
            ogg = _tts_to_ogg(tts_text, lang=lang)
            if ogg:
                bot.send_voice(chat_id, ogg)
        except Exception as tts_err:
            log.debug(f"[Cal] TTS reminder skipped: {tts_err}")
    except Exception as e:
        log.warning(f"[Cal] reminder send failed (ev={ev_id}): {e}")


def _schedule_reminder(chat_id: int, ev: dict) -> None:
    """Schedule a threading.Timer for the reminder time of an event."""
    ev_id = ev["id"]
    dt = datetime.fromisoformat(ev["dt_iso"])
    remind_dt = dt - timedelta(minutes=int(ev.get("remind_before_min", 15)))
    delay = (remind_dt - datetime.now()).total_seconds()

    # Cancel any existing timer for this event
    old = _cal_timers.pop(ev_id, None)
    if old:
        old.cancel()

    if delay < 0:
        # Reminder time already passed but the event itself is still future — fire now
        if (dt - datetime.now()).total_seconds() > 0:
            delay = 0
        else:
            return  # Entirely in the past — skip

    t = threading.Timer(delay, _send_reminder,
                        args=(chat_id, ev_id, ev["title"], ev["dt_iso"]))
    t.daemon = True
    t.start()
    _cal_timers[ev_id] = t
    log.debug(f"[Cal] Reminder scheduled: '{ev['title']}' in {delay:.0f}s (ev={ev_id})")


# ─────────────────────────────────────────────────────────────────────────────
# Startup: reschedule all pending reminders
# ─────────────────────────────────────────────────────────────────────────────

def _cal_reschedule_all() -> None:
    """Called on bot startup: reload all calendar files and reschedule reminders."""
    d = Path(CALENDAR_DIR)
    if not d.exists():
        return
    count = 0
    for fp in d.glob("*.json"):
        try:
            chat_id = int(fp.stem)
            events = json.loads(fp.read_text(encoding="utf-8"))
            for ev in events:
                if not ev.get("reminded"):
                    if datetime.fromisoformat(ev["dt_iso"]) > datetime.now():
                        _schedule_reminder(chat_id, ev)
                        count += 1
        except Exception as e:
            log.debug(f"[Cal] reschedule error for {fp}: {e}")
    log.info(f"[Cal] Rescheduled {count} pending reminder(s)")


# ─────────────────────────────────────────────────────────────────────────────
# Morning briefing background thread
# ─────────────────────────────────────────────────────────────────────────────

_BRIEFING_HOUR = 8   # 08:00 local time


def _cal_morning_briefing_loop() -> None:
    """Daemon thread: fires a morning briefing every day at 08:00."""
    while True:
        now = datetime.now()
        next_briefing = now.replace(
            hour=_BRIEFING_HOUR, minute=0, second=0, microsecond=0
        )
        if now >= next_briefing:
            next_briefing += timedelta(days=1)
        sleep_s = (next_briefing - now).total_seconds()
        log.debug(f"[Cal] Next morning briefing in {sleep_s / 3600:.1f}h")
        time.sleep(sleep_s)

        # Collect and send today's events for every user
        d = Path(CALENDAR_DIR)
        if not d.exists():
            continue
        today = datetime.now().date()
        for fp in d.glob("*.json"):
            try:
                chat_id = int(fp.stem)
                if not _is_allowed(chat_id):
                    continue
                events = json.loads(fp.read_text(encoding="utf-8"))
                today_evs = sorted(
                    [e for e in events
                     if datetime.fromisoformat(e["dt_iso"]).date() == today],
                    key=lambda e: e["dt_iso"],
                )
                if not today_evs:
                    continue

                lang = _st._user_lang.get(chat_id, "ru")
                from telegram.bot_access import _STRINGS
                greeting = _STRINGS.get(lang, _STRINGS.get("en", {})).get("cal_morning_greeting", "☀️ *Good morning! Today:*\n\n")
                lines = []
                for ev in today_evs:
                    dt = datetime.fromisoformat(ev["dt_iso"])
                    cdown = _fmt_countdown(dt, lang)
                    lines.append(
                        f"• *{_escape_md(ev['title'])}* — {dt.strftime('%H:%M')} {cdown}"
                    )
                bot.send_message(chat_id, greeting + "\n".join(lines),
                                 parse_mode="Markdown")

                # Optional TTS voice briefing
                try:
                    from features.bot_voice import _tts_to_ogg  # noqa: PLC0415  deferred
                    tts_text = _STRINGS.get(lang, _STRINGS.get("en", {})).get("cal_morning_tts_prefix", "Good morning. ")
                    for ev in today_evs:
                        dt = datetime.fromisoformat(ev["dt_iso"])
                        tts_text += f"{ev['title']} в {dt.strftime('%H:%M')}. "
                    ogg = _tts_to_ogg(tts_text[:300], lang=lang)
                    if ogg:
                        bot.send_voice(chat_id, ogg)
                except Exception as tts_err:
                    log.debug(f"[Cal] Morning TTS skipped: {tts_err}")

            except Exception as e:
                log.debug(f"[Cal] Morning briefing error for {fp}: {e}")
