"""
bot_calendar.py — Smart calendar with natural-language event add/cancel.

Dependencies: bot_config, bot_state, bot_instance, bot_access
(bot_voice imported lazily inside functions to avoid circular imports)

Features:
  - Add events in free-form Russian or English via text or voice
  - LLM-based natural language date/time parsing
  - Countdown display in event list ("through 2д 3ч")
  - Reminder 15 min before event (text + optional TTS voice note)
  - Morning briefing at 08:00 with today's events (text + optional TTS)
  - Timer rescheduling on bot restart
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

import bot_state as _st
from bot_config import CALENDAR_DIR, log
from bot_instance import bot
from bot_access import (
    _t, _ask_picoclaw, _escape_md, _back_keyboard, _send_menu, _is_allowed,
)


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
    return d / f"{chat_id}.json"


def _cal_load(chat_id: int) -> list:
    fp = _cal_user_file(chat_id)
    try:
        return json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else []
    except Exception:
        return []


def _cal_save(chat_id: int, events: list) -> None:
    _cal_user_file(chat_id).write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
        _cal_save(chat_id, new_events)
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
    total_s = int((dt - datetime.now()).total_seconds())
    if total_s < 0:
        return "⏰ " + ("прошло" if lang == "ru" else "passed")
    if total_s < 60:
        return "⏰ " + ("сейчас!" if lang == "ru" else "now!")
    if total_s < 3600:
        mins = total_s // 60
        return "⏰ " + (f"через {mins} мин" if lang == "ru" else f"in {mins} min")
    if total_s < 86400:
        h = total_s // 3600
        m = (total_s % 3600) // 60
        return "⏰ " + (f"через {h}ч {m}м" if lang == "ru" else f"in {h}h {m}m")
    days = total_s // 86400
    h = (total_s % 86400) // 3600
    return "⏰ " + (f"через {days}д {h}ч" if lang == "ru" else f"in {days}d {h}h")


# ─────────────────────────────────────────────────────────────────────────────
# Inline keyboards
# ─────────────────────────────────────────────────────────────────────────────

def _calendar_keyboard(chat_id: int, events: list) -> InlineKeyboardMarkup:
    """Main calendar keyboard: list of upcoming events + Add + Back."""
    lang = _st._user_lang.get(chat_id, "ru")
    kb = InlineKeyboardMarkup(row_width=1)
    now = datetime.now()
    future = sorted(
        [e for e in events if datetime.fromisoformat(e["dt_iso"]) > now],
        key=lambda e: e["dt_iso"],
    )
    for ev in future[:8]:
        dt = datetime.fromisoformat(ev["dt_iso"])
        cdown = _fmt_countdown(dt, lang)
        dt_str = dt.strftime("%d.%m %H:%M")
        label = f"🗓 {ev['title']} · {dt_str}  {cdown}"
        kb.add(InlineKeyboardButton(label, callback_data=f"cal_event:{ev['id']}"))
    kb.add(InlineKeyboardButton(
        "➕  " + ("Добавить событие" if lang == "ru" else "Add event"),
        callback_data="cal_add",
    ))
    kb.add(InlineKeyboardButton(
        "🔙  " + ("Меню" if lang == "ru" else "Menu"),
        callback_data="menu",
    ))
    return kb


def _cal_confirm_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown after LLM parses a new event — confirm or edit before saving."""
    lang = _st._user_lang.get(chat_id, "ru")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(
            "✅  " + ("Сохранить" if lang == "ru" else "Save"),
            callback_data="cal_confirm_save",
        ),
        InlineKeyboardButton(
            "❌  " + ("Отмена" if lang == "ru" else "Cancel"),
            callback_data="cancel",
        ),
    )
    kb.add(InlineKeyboardButton(
        "✏️  " + ("Изменить название" if lang == "ru" else "Edit title"),
        callback_data="cal_confirm_edit_title",
    ))
    kb.add(InlineKeyboardButton(
        "📅  " + ("Изменить дату/время" if lang == "ru" else "Edit date/time"),
        callback_data="cal_confirm_edit_dt",
    ))
    kb.add(InlineKeyboardButton(
        "⏰  " + ("Изменить напоминание" if lang == "ru" else "Edit reminder"),
        callback_data="cal_confirm_edit_remind",
    ))
    return kb


def _cal_event_keyboard(chat_id: int, ev_id: str) -> InlineKeyboardMarkup:
    """Event detail keyboard: edit, reschedule, delete + back."""
    lang = _st._user_lang.get(chat_id, "ru")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(
            "✏️  " + ("Изменить" if lang == "ru" else "Edit"),
            callback_data=f"cal_edit_title:{ev_id}",
        ),
        InlineKeyboardButton(
            "📅  " + ("Перенести" if lang == "ru" else "Reschedule"),
            callback_data=f"cal_edit_dt:{ev_id}",
        ),
    )
    kb.add(InlineKeyboardButton(
        "⏰  " + ("Изм. напоминание" if lang == "ru" else "Edit reminder"),
        callback_data=f"cal_edit_remind:{ev_id}",
    ))
    kb.add(InlineKeyboardButton(
        "🗑  " + ("Удалить" if lang == "ru" else "Delete"),
        callback_data=f"cal_del:{ev_id}",
    ))
    kb.add(InlineKeyboardButton(
        "🔙  " + ("Назад" if lang == "ru" else "Back"),
        callback_data="menu_calendar",
    ))
    return kb


# ─────────────────────────────────────────────────────────────────────────────
# Calendar menu handler
# ─────────────────────────────────────────────────────────────────────────────

def _handle_calendar_menu(chat_id: int) -> None:
    """Show the calendar: summary of upcoming events + action buttons."""
    lang = _st._user_lang.get(chat_id, "ru")
    events = _cal_load(chat_id)
    now = datetime.now()
    future = sorted(
        [e for e in events if datetime.fromisoformat(e["dt_iso"]) > now],
        key=lambda e: e["dt_iso"],
    )
    if not future:
        header = ("🗓 *Календарь*\n\n_Событий пока нет. Добавьте первое!_"
                  if lang == "ru" else
                  "🗓 *Calendar*\n\n_No events yet. Add your first!_")
    else:
        lines = ["🗓 *" + ("Календарь" if lang == "ru" else "Calendar") + "*\n"]
        for ev in future[:5]:
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
    lang = _st._user_lang.get(chat_id, "ru")
    _pending_cal[chat_id] = {"step": "input"}
    _st._user_mode[chat_id] = "calendar"

    if lang == "ru":
        prompt = (
            "✏️ *Добавить событие*\n\n"
            "Опишите в свободной форме, например:\n"
            "_«завтра в 10 встреча с командой»_\n"
            "_«напомни через час позвонить Ивану»_\n"
            "_«13 апреля в 15:00 врач»_"
        )
    else:
        prompt = (
            "✏️ *Add event*\n\n"
            "Describe freely, for example:\n"
            "_«tomorrow at 10 team meeting»_\n"
            "_«remind me in an hour to call Ivan»_\n"
            "_«April 13 at 15:00 doctor»_"
        )
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        "❌  " + ("Отмена" if lang == "ru" else "Cancel"),
        callback_data="cancel",
    ))
    bot.send_message(chat_id, prompt, parse_mode="Markdown", reply_markup=kb)


def _finish_cal_add(chat_id: int, text: str) -> None:
    """Parse user input via LLM → show confirmation card before saving."""
    lang = _st._user_lang.get(chat_id, "ru")
    _pending_cal.pop(chat_id, None)
    _st._user_mode.pop(chat_id, None)

    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M")
    prompt = (
        f"Текущая дата и время: {now_iso}\n"
        f"Задача: из текста ниже извлечь название события (title) и дату/время (dt).\n"
        f"Правила:\n"
        f"- dt всегда в формате YYYY-MM-DDTHH:MM\n"
        f"- если дата не указана — используй сегодня\n"
        f"- если время не указано — используй 09:00\n"
        f"- «завтра» = следующий день, «послезавтра» = через 2 дня\n"
        f"- «через N минут/часов» = добавь N к текущему времени\n"
        f"Если события нет — верни {{\"error\": \"no_event\"}}\n"
        f"Ответь ТОЛЬКО валидным JSON без пояснений:\n"
        f"{{\"title\": \"...\", \"dt\": \"YYYY-MM-DDTHH:MM\"}}\n\n"
        f"Текст: \"{text}\""
    )

    thinking_msg = bot.send_message(
        chat_id,
        "⏳ " + ("Разбираю событие…" if lang == "ru" else "Parsing event…"),
    )
    raw = _ask_picoclaw(prompt, timeout=30)
    try:
        bot.delete_message(chat_id, thinking_msg.message_id)
    except Exception:
        pass

    if not raw:
        bot.send_message(
            chat_id,
            "❌ " + ("Нет ответа от LLM. Попробуйте ещё раз." if lang == "ru"
                     else "No LLM response. Please try again."),
            reply_markup=_calendar_keyboard(chat_id, _cal_load(chat_id)),
        )
        return

    try:
        json_match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON block found in LLM response")
        parsed = json.loads(json_match.group())
        if "error" in parsed:
            raise ValueError(f"LLM reported no event: {parsed}")
        title = str(parsed.get("title", "")).strip()
        dt_str = str(parsed.get("dt", "")).strip()
        if not title or not dt_str:
            raise ValueError("title or dt missing from parsed JSON")
        dt = datetime.fromisoformat(dt_str)
    except Exception as e:
        log.warning(f"[Cal] LLM parse failed for chat {chat_id}: {e}  raw={raw[:200]!r}")
        fail_msg = (
            "❌ Не смог разобрать дату. Напишите иначе, например:\n"
            "_«5 апреля в 14:00 встреча с врачом»_"
            if lang == "ru" else
            "❌ Could not parse date. Try:\n"
            "_«April 5 at 14:00 doctor appointment»_"
        )
        bot.send_message(chat_id, fail_msg, parse_mode="Markdown",
                         reply_markup=_calendar_keyboard(chat_id, _cal_load(chat_id)))
        return

    # Store parsed data for confirmation / editing
    _pending_cal[chat_id] = {
        "step":              "confirm",
        "title":             title,
        "dt_iso":            dt.strftime("%Y-%m-%dT%H:%M"),
        "remind_before_min": 15,
    }

    _show_cal_confirm(chat_id)


def _show_cal_confirm(chat_id: int) -> None:
    """Send the confirmation card for a pending new event."""
    lang  = _st._user_lang.get(chat_id, "ru")
    draft = _pending_cal.get(chat_id, {})
    title = draft.get("title", "—")
    dt    = datetime.fromisoformat(draft.get("dt_iso", datetime.now().strftime("%Y-%m-%dT%H:%M")))
    remind_min = int(draft.get("remind_before_min", 15))
    cdown = _fmt_countdown(dt, lang)
    dt_fmt = dt.strftime("%d.%m.%Y %H:%M")

    if lang == "ru":
        header  = "📋 *Проверьте событие перед сохранением:*"
        t_label = "📌 Название"
        d_label = "📅 Дата/время"
        r_label = "⏰ Напоминание"
        remind_str = f"за {remind_min} мин"
    else:
        header  = "📋 *Review event before saving:*"
        t_label = "📌 Title"
        d_label = "📅 Date/time"
        r_label = "⏰ Reminder"
        remind_str = f"{remind_min} min before"

    text = (
        f"{header}\n\n"
        f"{t_label}: *{_escape_md(title)}*\n"
        f"{d_label}: {dt_fmt}  {cdown}\n"
        f"{r_label}: {remind_str}"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown",
                     reply_markup=_cal_confirm_keyboard(chat_id))


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
        f"✅ *{'Записал' if lang == 'ru' else 'Saved'}:*\n"
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
        "❌  " + ("Отмена" if lang == "ru" else "Cancel"),
        callback_data="cancel",
    ))

    if field == "title":
        prompt = ("✏️ Введите *новое название* события:" if lang == "ru"
                  else "✏️ Enter the *new title* for the event:")
    elif field == "dt":
        prompt = (
            "📅 Введите *новую дату и время* в свободной форме:\n"
            "_«завтра в 14:30»_, _«5 апреля в 9:00»_, _«через 2 часа»_"
            if lang == "ru" else
            "📅 Enter *new date and time* freely:\n"
            "_«tomorrow at 14:30»_, _«April 5 at 9:00»_, _«in 2 hours»_"
        )
    else:  # remind
        prompt = (
            "⏰ Введите *за сколько минут* напомнить (число):\n"
            "_Например: 10, 30, 60_"
            if lang == "ru" else
            "⏰ Enter *how many minutes before* to remind (number):\n"
            "_E.g.: 10, 30, 60_"
        )

    bot.send_message(chat_id, prompt, parse_mode="Markdown", reply_markup=kb)


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
                "⚠️ " + ("Название не может быть пустым." if lang == "ru"
                          else "Title cannot be empty."),
            )
            _cal_prompt_edit_field(chat_id, "title", ev_id)
            return
        draft["title"] = new_title

    elif field == "dt":
        # Re-parse via LLM
        now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M")
        prompt = (
            f"Текущая дата и время: {now_iso}\n"
            f"Задача: извлечь дату/время из текста.\n"
            f"Правила: dt всегда YYYY-MM-DDTHH:MM. «завтра» = следующий день. "
            f"«через N минут/часов» = добавь N.\n"
            f"Ответь ТОЛЬКО JSON: {{\"dt\": \"YYYY-MM-DDTHH:MM\"}}\n\n"
            f"Текст: \"{text}\""
        )
        thinking = bot.send_message(
            chat_id,
            "⏳ " + ("Разбираю дату…" if lang == "ru" else "Parsing date…"),
        )
        raw = _ask_picoclaw(prompt, timeout=25)
        try:
            bot.delete_message(chat_id, thinking.message_id)
        except Exception:
            pass
        try:
            m = re.search(r'\{[^{}]+\}', raw or "", re.DOTALL)
            parsed = json.loads(m.group()) if m else {}
            new_dt = datetime.fromisoformat(parsed["dt"])
            draft["dt_iso"] = new_dt.strftime("%Y-%m-%dT%H:%M")
        except Exception as exc:
            log.warning(f"[Cal] dt parse failed: {exc}  raw={raw!r}")
            bot.send_message(
                chat_id,
                "❌ " + ("Не смог разобрать дату. Попробуйте ещё раз." if lang == "ru"
                         else "Could not parse date. Please try again."),
                parse_mode="Markdown",
            )
            _cal_prompt_edit_field(chat_id, "dt", ev_id)
            return

    else:  # remind
        try:
            minutes = int(re.search(r'\d+', text).group())
            if minutes < 0 or minutes > 10000:
                raise ValueError("out of range")
            draft["remind_before_min"] = minutes
        except Exception:
            bot.send_message(
                chat_id,
                "⚠️ " + ("Введите число минут, например 15." if lang == "ru"
                          else "Enter a number of minutes, e.g. 15."),
            )
            _cal_prompt_edit_field(chat_id, "remind", ev_id)
            return

    # After editing: apply to saved event or return to confirmation
    if ev_id:
        # Update persisted event
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
        # Reschedule reminder
        ev_updated = next((e for e in _cal_load(chat_id) if e.get("id") == ev_id), None)
        if ev_updated:
            _schedule_reminder(chat_id, ev_updated)
        updated_ev = next((e for e in _cal_load(chat_id) if e.get("id") == ev_id), None)
        if updated_ev:
            _handle_cal_event_detail(chat_id, ev_id)
        else:
            _handle_calendar_menu(chat_id)
    else:
        # Back to confirmation screen
        _pending_cal[chat_id] = draft
        _show_cal_confirm(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
# Delete / cancel event
# ─────────────────────────────────────────────────────────────────────────────

def _handle_cal_cancel_event(chat_id: int, ev_id: str) -> None:
    """Delete an event and cancel its reminder timer."""
    lang = _st._user_lang.get(chat_id, "ru")
    events = _cal_load(chat_id)
    ev = next((e for e in events if e.get("id") == ev_id), None)

    if _cal_delete_event(chat_id, ev_id):
        old_timer = _cal_timers.pop(ev_id, None)
        if old_timer:
            old_timer.cancel()
        title = ev.get("title", ev_id) if ev else ev_id
        msg = (f"❌ {'Удалено' if lang == 'ru' else 'Removed'}: *{_escape_md(title)}*")
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
        tts_text = (f"Напоминаю: {title} в {dt_fmt}"
                    if lang == "ru" else
                    f"Reminder: {title} at {dt_fmt}")
        msg_text = f"🔔 *{_escape_md(tts_text)}*"
        bot.send_message(chat_id, msg_text, parse_mode="Markdown")
        _cal_mark_reminded(chat_id, ev_id)
        _cal_timers.pop(ev_id, None)

        # Optional TTS voice note (deferred import to avoid circular at module load)
        try:
            from bot_voice import _tts_to_ogg  # noqa: PLC0415  deferred on purpose
            ogg = _tts_to_ogg(tts_text)
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
                greeting = ("☀️ *Доброе утро! Сегодня:*\n\n"
                            if lang == "ru" else
                            "☀️ *Good morning! Today:*\n\n")
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
                    from bot_voice import _tts_to_ogg  # noqa: PLC0415  deferred
                    tts_text = ("Доброе утро. " if lang == "ru" else "Good morning. ")
                    for ev in today_evs:
                        dt = datetime.fromisoformat(ev["dt_iso"])
                        tts_text += f"{ev['title']} в {dt.strftime('%H:%M')}. "
                    ogg = _tts_to_ogg(tts_text[:300])
                    if ogg:
                        bot.send_voice(chat_id, ogg)
                except Exception as tts_err:
                    log.debug(f"[Cal] Morning TTS skipped: {tts_err}")

            except Exception as e:
                log.debug(f"[Cal] Morning briefing error for {fp}: {e}")
