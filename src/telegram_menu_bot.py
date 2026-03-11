#!/usr/bin/env python3
"""
telegram_menu_bot.py — Picoclaw Telegram Menu Bot (entry point)

This file registers all Telegram handlers and launches the bot.
All business logic lives in the bot_* modules:

  bot_config.py    — Constants, env loading, logging
  bot_state.py     — Mutable runtime state, voice_opts, dynamic-users I/O
  bot_instance.py  — Shared TeleBot singleton
  bot_access.py    — Access control, i18n, keyboards, text utils, picoclaw
  bot_users.py     — Registration + notes file I/O (pure data layer)
  bot_voice.py     — Full voice pipeline (STT/TTS/VAD)
  bot_admin.py     — Admin panel handlers (LLM, changelog, voice opts, users)
  bot_handlers.py  — User handlers (chat, digest, system, notes UI)
"""

import os
import threading

# ─── Core ────────────────────────────────────────────────────────────────────
from bot_config import (
    BOT_VERSION, PICOCLAW_BIN, DIGEST_SCRIPT,
    PIPER_MODEL_TMPFS,
    log,
)
import bot_state as _st

from bot_instance import bot

# ─── Shared utilities ─────────────────────────────────────────────────────────
from bot_access import (
    _is_allowed, _is_admin, _is_guest,
    _deny, _set_lang, _send_menu,
    _t, _menu_keyboard, _back_keyboard, _escape_md,
    _get_active_model, _run_subprocess,
)

# ─── Data layer ───────────────────────────────────────────────────────────────
from bot_users import (
    _upsert_registration, _is_blocked_reg, _is_pending_reg,
    _slug, _load_note_text, _save_note_file,
)

# ─── Voice pipeline ───────────────────────────────────────────────────────────
from bot_voice import (
    _handle_voice_message, _start_voice_session, _handle_note_read_aloud, _handle_digest_tts,
    _warm_piper_cache, _start_persistent_piper, _setup_tmpfs_model,
    _cleanup_orphaned_tts,
)

# ─── Admin handlers ───────────────────────────────────────────────────────────
from bot_admin import (
    _handle_admin_menu, _handle_admin_list_users,
    _start_admin_add_user, _finish_admin_add_user,
    _start_admin_remove_user, _finish_admin_remove_user,
    _handle_admin_pending_users,
    _do_approve_registration, _do_block_registration,
    _notify_admins_new_registration, _notify_admins_new_version,
    _handle_voice_opts_menu, _handle_voice_opt_toggle,
    _handle_admin_changelog,
    _handle_admin_llm_menu, _handle_set_llm,
    _handle_openai_llm_menu, _handle_llm_setkey_prompt, _handle_save_llm_key,
    _admin_keyboard,
)

# ─── User handlers ────────────────────────────────────────────────────────────
from bot_handlers import (
    _handle_digest, _refresh_digest,
    _handle_chat_message,
    _handle_system_message, _execute_pending_cmd,
    _handle_notes_menu, _handle_note_list, _start_note_create,
    _handle_note_open, _handle_note_raw, _start_note_edit, _handle_note_delete,
    _notes_menu_keyboard,
    _handle_profile,
)

# ─── Calendar ─────────────────────────────────────────────────────────────────
from bot_calendar import (
    _handle_calendar_menu, _handle_cal_event_detail,
    _start_cal_add, _finish_cal_add, _handle_cal_cancel_event,
    _cal_do_confirm_save, _show_cal_confirm,
    _cal_prompt_edit_field, _cal_handle_edit_input,
    _cal_reschedule_all, _cal_morning_briefing_loop,
    _handle_cal_event_tts, _handle_cal_confirm_tts,
    _pending_cal,
    # New features
    _show_cal_confirm_multi, _cal_multi_save_one, _cal_multi_skip, _cal_multi_save_all,
    _handle_cal_delete_request, _handle_cal_delete_confirmed,
    _handle_calendar_query, _start_cal_console, _handle_cal_console,
)

# ─── Mail credentials ──────────────────────────────────────────────────────────
from bot_mail_creds import (
    handle_mail_consent, handle_mail_consent_agree,
    handle_mail_provider, finish_mail_setup,
    handle_mail_settings, handle_mail_del_creds,
    _pending_mail_setup,
)
# ─── Email send ────────────────────────────────────────────────────────────
from bot_email import (
    handle_send_email, handle_email_change_target, finish_email_set_target,
)

# ─────────────────────────────────────────────────────────────────────────────
# Registration helper
# ─────────────────────────────────────────────────────────────────────────────

def _finish_registration(cid: int, display_name: str) -> None:
    """Complete new-user registration after the user has typed their display name."""
    info         = _st._pending_registration.pop(cid, {})
    _st._user_mode.pop(cid, None)
    display_name = display_name.strip()[:100]
    if not display_name:
        _st._pending_registration[cid] = info
        _st._user_mode[cid] = "reg_name"
        bot.send_message(cid, _t(cid, "reg_ask_name"), parse_mode="Markdown")
        return
    username   = info.get("username", "")
    first_name = info.get("first_name", "")
    last_name  = info.get("last_name", "")
    _upsert_registration(cid, username, display_name, "pending",
                         first_name=first_name, last_name=last_name)
    bot.send_message(cid, _t(cid, "reg_waiting"), parse_mode="Markdown")
    log.info(f"[Reg] New request: id={cid} username={username!r} name={display_name!r}")
    _notify_admins_new_registration(cid, username, display_name, first_name, last_name)


# ─────────────────────────────────────────────────────────────────────────────
# /start — welcome or registration flow
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(message):
    cid = message.chat.id
    _set_lang(cid, message.from_user)

    if not _is_allowed(cid):
        username = getattr(message.from_user, "username", "") or ""
        first    = getattr(message.from_user, "first_name", "") or ""
        last     = getattr(message.from_user, "last_name", "") or ""

        if _is_blocked_reg(cid):
            bot.send_message(cid, _t(cid, "reg_blocked"))
        elif _is_pending_reg(cid):
            bot.send_message(cid, _t(cid, "reg_pending_exists"))
        elif _st._user_mode.get(cid) == "reg_name":
            bot.send_message(cid, _t(cid, "reg_ask_name"), parse_mode="Markdown")
        else:
            _st._pending_registration[cid] = {
                "username":   username,
                "first_name": first,
                "last_name":  last,
            }
            _st._user_mode[cid] = "reg_name"
            bot.send_message(cid, _t(cid, "reg_ask_name"), parse_mode="Markdown")
        return

    bot.send_message(cid, _t(cid, "welcome"), parse_mode="Markdown",
                     reply_markup=_menu_keyboard(cid))


# ─────────────────────────────────────────────────────────────────────────────
# /menu
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["menu"])
def cmd_menu(message):
    if not _is_allowed(message.chat.id):
        _deny(message.chat.id)
        return
    _set_lang(message.chat.id, message.from_user)
    _send_menu(message.chat.id)


# ─────────────────────────────────────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["status"])
def cmd_status(message):
    if not _is_allowed(message.chat.id):
        _deny(message.chat.id)
        return
    _set_lang(message.chat.id, message.from_user)
    cid          = message.chat.id
    mode         = _st._user_mode.get(cid, "—")
    active_model = _get_active_model() or "default"

    services = [
        ("🤖 Telegram Bot",    "picoclaw-telegram"),
        ("🌐 AI Gateway",      "picoclaw-gateway"),
        ("🎤 Voice Assistant", "picoclaw-voice"),
    ]
    svc_lines = []
    for label, svc_name in services:
        _, state = _run_subprocess(["systemctl", "is-active", svc_name], timeout=5)
        state = state.strip()
        icon  = "✅" if state == "active" else "❌"
        svc_lines.append(f"{icon} {label}: `{state}`")

    if _is_admin(cid):
        role = "👑 Admin"
    elif _is_guest(cid):
        role = "👥 Guest"
    else:
        role = "👤 Full"

    text = (
        f"🖥️ *Pico Bot Status*\n\n"
        f"🎯 *Mode:* `{mode}`\n"
        f"🤖 *LLM:* `{active_model}`\n"
        f"👤 *Role:* {role}\n\n"
        f"*Services:*\n" + "\n".join(svc_lines)
    )
    bot.send_message(cid, text, parse_mode="Markdown", reply_markup=_back_keyboard())


# ─────────────────────────────────────────────────────────────────────────────
# Inline callback dispatcher
# ─────────────────────────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    cid  = call.message.chat.id
    if not _is_allowed(cid):
        bot.answer_callback_query(call.id, "⛔ Access denied")
        return

    _set_lang(cid, call.from_user)
    data = call.data
    bot.answer_callback_query(call.id)   # dismiss spinner

    # ── Navigation ─────────────────────────────────────────────────────────
    if data == "menu":
        _st._user_mode.pop(cid, None)
        _st._pending_cmd.pop(cid, None)
        _send_menu(cid)

    # ── Mail digest ────────────────────────────────────────────────────────
    elif data == "digest":
        _handle_digest(cid)
    elif data == "digest_refresh":
        _refresh_digest(cid)
    elif data == "digest_tts":
        _handle_digest_tts(cid)

    # ── Chat / System mode ─────────────────────────────────────────────────
    elif data == "mode_chat":
        _st._user_mode[cid] = "chat"
        bot.send_message(cid, _t(cid, "chat_enter"), parse_mode="Markdown")
    elif data == "mode_system":
        if not _is_admin(cid):       # System Chat executes commands — admin only
            _deny(cid)
            return
        _st._user_mode[cid] = "system"
        bot.send_message(cid, _t(cid, "system_enter"), parse_mode="Markdown")

    # ── Voice ──────────────────────────────────────────────────────────────
    elif data == "voice_session":
        _start_voice_session(cid)
    elif data == "voice_audio_toggle":
        _st._user_audio[cid] = not _st._user_audio.get(cid, True)

    # ── Help ───────────────────────────────────────────────────────────────
    elif data == "help":
        if _is_admin(cid):
            key = "help_text_admin"
        elif _is_guest(cid):
            key = "help_text_guest"
        else:
            key = "help_text"
        bot.send_message(cid, _t(cid, key),
                         parse_mode="Markdown",
                         reply_markup=_back_keyboard())
    # ── User profile ───────────────────────────────────────────────────────────
    elif data == "profile":
        if not _is_allowed(cid): return _deny(cid)
        _handle_profile(cid)
    # ── Admin panel ────────────────────────────────────────────────────────
    elif data == "admin_menu":
        if _is_admin(cid):
            _handle_admin_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_add_user":
        if _is_admin(cid):
            _start_admin_add_user(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_list_users":
        if _is_admin(cid):
            _handle_admin_list_users(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_remove_user":
        if _is_admin(cid):
            _start_admin_remove_user(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_pending_users":
        if _is_admin(cid):
            _handle_admin_pending_users(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("reg_approve:"):
        if _is_admin(cid):
            _do_approve_registration(cid, int(data.split(":", 1)[1]))
        else:
            bot.answer_callback_query(call.id, _t(cid, "admin_only"))

    elif data.startswith("reg_block:"):
        if _is_admin(cid):
            _do_block_registration(cid, int(data.split(":", 1)[1]))
        else:
            bot.answer_callback_query(call.id, _t(cid, "admin_only"))

    # ── LLM switcher ───────────────────────────────────────────────────────
    elif data == "admin_llm_menu":
        if _is_admin(cid):
            _handle_admin_llm_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("llm_select:"):
        if _is_admin(cid):
            _handle_set_llm(cid, data[len("llm_select:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "openai_llm_menu":
        if _is_admin(cid):
            _handle_openai_llm_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "llm_setkey_openai":
        if _is_admin(cid):
            _handle_llm_setkey_prompt(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── Voice opts ─────────────────────────────────────────────────────────
    elif data == "voice_opts_menu":
        if _is_admin(cid):
            _handle_voice_opts_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("voice_opt_toggle:"):
        if _is_admin(cid):
            _handle_voice_opt_toggle(cid, data[len("voice_opt_toggle:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── Changelog ──────────────────────────────────────────────────────────
    elif data == "admin_changelog":
        if _is_admin(cid):
            _handle_admin_changelog(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── Notes ──────────────────────────────────────────────────────────────
    elif data == "menu_notes":
        if not _is_guest(cid):
            _handle_notes_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "note_create":
        if not _is_guest(cid):
            _start_note_create(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "note_list":
        if not _is_guest(cid):
            _handle_note_list(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_open:"):
        if not _is_guest(cid):
            _handle_note_open(cid, data[len("note_open:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_tts:"):
        if not _is_guest(cid):
            _handle_note_read_aloud(cid, data[len("note_tts:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_raw:"):
        if not _is_guest(cid):
            _handle_note_raw(cid, data[len("note_raw:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_edit:"):
        if not _is_guest(cid):
            _start_note_edit(cid, data[len("note_edit:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_delete:"):
        if not _is_guest(cid):
            _handle_note_delete(cid, data[len("note_delete:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))
    # ── Send as email ───────────────────────────────────────────────────────
    elif data.startswith("note_email:"):
        from bot_users import _load_note_text
        slug    = data[len("note_email:"):]
        content = _load_note_text(cid, slug)
        if content:
            handle_send_email(cid, f"Note: {slug.replace('_', ' ')}", content)
        else:
            bot.send_message(cid, _t(cid, "note_not_found"), reply_markup=_back_keyboard())

    elif data == "digest_email":
        from bot_mail_creds import _last_digest_file
        last_f = _last_digest_file(cid)
        if last_f.exists() and last_f.stat().st_size > 0:
            body = last_f.read_text(encoding="utf-8", errors="replace").strip()
            handle_send_email(cid, "Mail Digest", body)
        else:
            bot.send_message(cid, _t(cid, "digest_not_ready"), reply_markup=_back_keyboard())

    elif data.startswith("cal_email:"):
        from bot_calendar import _cal_load
        ev_id  = data[len("cal_email:"):]
        events = _cal_load(cid)
        ev     = next((e for e in events if e["id"] == ev_id), None)
        if ev:
            from datetime import datetime
            try:
                dt_str = datetime.fromisoformat(ev["dt_iso"]).strftime("%d.%m.%Y %H:%M")
            except Exception:
                dt_str = ev.get("dt_iso", "")
            body = f"{ev['title']}\n{dt_str}"
            handle_send_email(cid, f"Calendar: {ev['title']}", body)
        else:
            bot.send_message(cid, "❌ Event not found.", reply_markup=_back_keyboard())

    elif data == "email_change_target":
        handle_email_change_target(cid)
    # ── Mail credentials setup ────────────────────────────────────────────
    elif data == "mail_consent":
        handle_mail_consent(cid)
    elif data == "mail_consent_agree":
        handle_mail_consent_agree(cid)
    elif data.startswith("mail_provider:"):
        handle_mail_provider(cid, data[len("mail_provider:"):])
    elif data == "mail_settings":
        handle_mail_settings(cid)
    elif data == "mail_del_creds":
        handle_mail_del_creds(cid)

    # ── Calendar ───────────────────────────────────────────────────────────
    elif data == "menu_calendar":
        if not _is_guest(cid):
            _handle_calendar_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "cal_add":
        if not _is_guest(cid):
            _start_cal_add(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("cal_event:"):
        if not _is_guest(cid):
            _handle_cal_event_detail(cid, data[len("cal_event:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("cal_del:"):
        if not _is_guest(cid):
            _handle_cal_delete_request(cid, data[len("cal_del:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("cal_del_confirm:"):
        if not _is_guest(cid):
            _handle_cal_delete_confirmed(cid, data[len("cal_del_confirm:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "cal_confirm_save":
        if not _is_guest(cid) and cid in _pending_cal:
            _cal_do_confirm_save(cid)
        else:
            _handle_calendar_menu(cid)

    elif data == "cal_multi_save_one":
        if not _is_guest(cid) and cid in _pending_cal:
            _cal_multi_save_one(cid)
        else:
            _handle_calendar_menu(cid)

    elif data == "cal_multi_skip":
        if not _is_guest(cid) and cid in _pending_cal:
            _cal_multi_skip(cid)
        else:
            _handle_calendar_menu(cid)

    elif data == "cal_multi_save_all":
        if not _is_guest(cid) and cid in _pending_cal:
            _cal_multi_save_all(cid)
        else:
            _handle_calendar_menu(cid)

    elif data == "cal_console":
        if not _is_guest(cid):
            _start_cal_console(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "cal_confirm_edit_title":
        if not _is_guest(cid):
            _cal_prompt_edit_field(cid, "title")

    elif data == "cal_confirm_edit_dt":
        if not _is_guest(cid):
            _cal_prompt_edit_field(cid, "dt")

    elif data == "cal_confirm_edit_remind":
        if not _is_guest(cid):
            _cal_prompt_edit_field(cid, "remind")

    elif data.startswith("cal_edit_title:"):
        if not _is_guest(cid):
            _cal_prompt_edit_field(cid, "title", ev_id=data[len("cal_edit_title:"):])

    elif data.startswith("cal_edit_dt:"):
        if not _is_guest(cid):
            _cal_prompt_edit_field(cid, "dt", ev_id=data[len("cal_edit_dt:"):])

    elif data.startswith("cal_edit_remind:"):
        if not _is_guest(cid):
            _cal_prompt_edit_field(cid, "remind", ev_id=data[len("cal_edit_remind:"):])
    elif data.startswith("cal_tts:"):
        if not _is_guest(cid):
            _handle_cal_event_tts(cid, data[len("cal_tts:"):])

    elif data == "cal_confirm_tts":
        if not _is_guest(cid) and cid in _pending_cal:
            _handle_cal_confirm_tts(cid)
    # ── Confirm / cancel system command ────────────────────────────────────
    elif data == "cancel":
        _st._pending_cmd.pop(cid, None)
        _st._pending_note.pop(cid, None)
        _pending_cal.pop(cid, None)
        _pending_mail_setup.pop(cid, None)
        _st._user_mode.pop(cid, None)
        bot.send_message(cid, _t(cid, "cancelled"), reply_markup=_back_keyboard())

    elif data.startswith("run:"):
        _execute_pending_cmd(cid)


# ─────────────────────────────────────────────────────────────────────────────
# Text message router
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=["text"])
def text_handler(message):
    cid = message.chat.id

    # ── Registration: non-allowed user entering their display name ─────────────
    if _st._user_mode.get(cid) == "reg_name" and cid in _st._pending_registration:
        _set_lang(cid, message.from_user)
        _finish_registration(cid, message.text)
        return

    if not _is_allowed(cid):
        _deny(cid)
        return

    _set_lang(cid, message.from_user)

    # Admin typing an API key
    if cid in _st._pending_llm_key:
        if _is_admin(cid):
            _handle_save_llm_key(cid, message.text)
        else:
            _st._pending_llm_key.pop(cid, None)
        return

    mode = _st._user_mode.get(cid)

    if mode is None:
        _send_menu(cid, greeting=False)
        return

    # ── Admin text flows ───────────────────────────────────────────────────
    if mode == "admin_add_user":
        if _is_admin(cid):
            _finish_admin_add_user(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
            bot.send_message(cid, _t(cid, "admin_only"))
        return

    if mode == "admin_remove_user":
        if _is_admin(cid):
            _finish_admin_remove_user(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
            bot.send_message(cid, _t(cid, "admin_only"))
        return

    # ── Note multi-step creation ───────────────────────────────────────────
    if mode == "note_add_title":
        if _is_guest(cid):
            _st._user_mode.pop(cid, None)
            _st._pending_note.pop(cid, None)
            return
        title = message.text.strip()
        if not title:
            bot.send_message(cid, _t(cid, "note_create_prompt_title"),
                             parse_mode="Markdown")
            return
        note_slug = _slug(title)
        _st._pending_note[cid] = {"step": "content", "slug": note_slug, "title": title}
        _st._user_mode[cid]    = "note_add_content"
        bot.send_message(cid,
                         _t(cid, "note_create_prompt_content", title=_escape_md(title)),
                         parse_mode="Markdown")
        return

    if mode == "note_add_content":
        if _is_guest(cid):
            _st._user_mode.pop(cid, None)
            _st._pending_note.pop(cid, None)
            return
        info  = _st._pending_note.pop(cid, {})
        _st._user_mode.pop(cid, None)
        slug  = info.get("slug", _slug(message.text[:30]))
        title = info.get("title", slug)
        content = f"# {title}\n\n{message.text.strip()}"
        _save_note_file(cid, slug, content)
        bot.send_message(cid,
                         _t(cid, "note_saved", title=_escape_md(title)),
                         parse_mode="Markdown",
                         reply_markup=_notes_menu_keyboard(cid))
        return

    if mode == "note_edit_content":
        if _is_guest(cid):
            _st._user_mode.pop(cid, None)
            _st._pending_note.pop(cid, None)
            return
        info = _st._pending_note.pop(cid, {})
        _st._user_mode.pop(cid, None)
        slug = info.get("slug")
        if not slug:
            _send_menu(cid, greeting=False)
            return
        existing   = _load_note_text(cid, slug)
        title_line = (existing or "").splitlines()[0] if existing else f"# {slug}"
        content    = f"{title_line}\n\n{message.text.strip()}"
        _save_note_file(cid, slug, content)
        title = title_line.lstrip("# ").strip()
        bot.send_message(cid,
                         _t(cid, "note_updated", title=_escape_md(title)),
                         parse_mode="Markdown",
                         reply_markup=_notes_menu_keyboard(cid))
        return

    # ── Email recipient address entry ─────────────────────────────────
    if mode == "email_set_target":
        finish_email_set_target(cid, message.text)
        return

    # ── Mail credential setup flow ────────────────────────────────────
    if mode == "mail_setup":
        finish_mail_setup(cid, message.text)
        return

    # ── Calendar add flow ──────────────────────────────────────────────────
    if mode == "calendar":
        if not _is_guest(cid):
            _finish_cal_add(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
            _pending_cal.pop(cid, None)
        return
    # ── Calendar console ────────────────────────────────────────────────────
    if mode == "cal_console":
        if not _is_guest(cid):
            _handle_cal_console(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
        return
    # ── Calendar field edit flows ────────────────────────────────────────────
    if mode == "cal_edit_title":
        if not _is_guest(cid):
            _cal_handle_edit_input(cid, message.text, "title")
        else:
            _st._user_mode.pop(cid, None)
            _pending_cal.pop(cid, None)
        return

    if mode == "cal_edit_dt":
        if not _is_guest(cid):
            _cal_handle_edit_input(cid, message.text, "dt")
        else:
            _st._user_mode.pop(cid, None)
            _pending_cal.pop(cid, None)
        return

    if mode == "cal_edit_remind":
        if not _is_guest(cid):
            _cal_handle_edit_input(cid, message.text, "remind")
        else:
            _st._user_mode.pop(cid, None)
            _pending_cal.pop(cid, None)
        return
    # ── Chat modes ─────────────────────────────────────────────────────────
    if mode == "chat":
        _handle_chat_message(cid, message.text)

    elif mode == "system":
        if _is_admin(cid):           # defense-in-depth: guard even at routing level
            _handle_system_message(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
            bot.send_message(cid, _t(cid, "security_admin_only"),
                             reply_markup=_back_keyboard())

    elif mode == "voice":
        bot.send_message(cid, _t(cid, "voice_hint"),
                         parse_mode="Markdown",
                         reply_markup=_back_keyboard())


# ─────────────────────────────────────────────────────────────────────────────
# Voice note handler
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=["voice"])
def voice_handler(message):
    cid = message.chat.id
    if not _is_allowed(cid):
        _deny(cid)
        return
    _set_lang(cid, message.from_user)
    _handle_voice_message(cid, message.voice)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("=" * 50)
    log.info("Pico Telegram Menu Bot starting")
    from bot_config import ADMIN_USERS, ALLOWED_USERS
    log.info(f"  Admin users  : {sorted(ADMIN_USERS)}")
    log.info(f"  Allowed users: {sorted(ALLOWED_USERS)}")
    log.info(f"  Guest users  : {sorted(_st._dynamic_users)}")
    log.info(f"  picoclaw     : {PICOCLAW_BIN}")
    log.info(f"  Digest script: {DIGEST_SCRIPT}")
    active_opts = [k for k, v in _st._voice_opts.items() if v]
    log.info(f"  Voice opts   : {active_opts or 'all OFF (stable defaults)'}")
    log.info(f"  Version      : {BOT_VERSION}")
    log.info("=" * 50)

    # ── Voice-opt startup side-effects ───────────────────────────────────
    if _st._voice_opts.get("tmpfs_model"):
        if os.path.exists(PIPER_MODEL_TMPFS):
            log.info(f"[VoiceOpt] tmpfs_model: model already in RAM")
        else:
            log.info("[VoiceOpt] tmpfs_model enabled — copying model to /dev/shm on startup")
            threading.Thread(target=_setup_tmpfs_model, args=(True,), daemon=True).start()

    if _st._voice_opts.get("warm_piper"):
        log.info("[VoiceOpt] warm_piper enabled — starting background warm-up")
        threading.Thread(target=_warm_piper_cache, daemon=True).start()

    if _st._voice_opts.get("persistent_piper"):
        log.info("[VoiceOpt] persistent_piper enabled — starting Piper keepalive")
        threading.Thread(target=_start_persistent_piper, daemon=True).start()

    # ── Startup tasks ─────────────────────────────────────────────────────
    _cleanup_orphaned_tts()
    _notify_admins_new_version()
    _cal_reschedule_all()
    threading.Thread(target=_cal_morning_briefing_loop, daemon=True).start()

    log.info("Polling Telegram…")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)


if __name__ == "__main__":
    main()
