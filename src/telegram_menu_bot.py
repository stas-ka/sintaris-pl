#!/usr/bin/env python3
"""
telegram_menu_bot.py — Taris Telegram Menu Bot (entry point)

This file registers all Telegram handlers and launches the bot.
All business logic lives in the bot_* modules:

  bot_config.py    — Constants, env loading, logging
  bot_state.py     — Mutable runtime state, voice_opts, dynamic-users I/O
  bot_instance.py  — Shared TeleBot singleton
  bot_access.py    — Access control, i18n, keyboards, text utils, taris
  bot_users.py     — Registration + notes file I/O (pure data layer)
  bot_voice.py     — Full voice pipeline (STT/TTS/VAD)
  bot_admin.py     — Admin panel handlers (LLM, changelog, voice opts, users)
  bot_handlers.py  — User handlers (chat, digest, system, notes UI)
"""

import os
import signal
import threading

# ─── Core ────────────────────────────────────────────────────────────────────
from core.bot_config import (
    BOT_VERSION, TARIS_BIN, DIGEST_SCRIPT,
    PIPER_MODEL_TMPFS, LLM_PROVIDER, STT_PROVIDER,
    log,
)
import core.bot_state as _st

from core.bot_instance import bot
from core.bot_logger import configure_alert_handler, attach_alerts_to_main_log

# ─── Shared utilities ─────────────────────────────────────────────────────────
from telegram.bot_access import (
    _is_allowed, _is_admin, _is_guest,
    _deny, _set_lang, _send_menu, _lang,
    _t, _menu_keyboard, _back_keyboard, _escape_md,
    _get_active_model, _run_subprocess,
)

# ─── Screen DSL ───────────────────────────────────────────────────────────────
from ui.bot_ui import UserContext
from ui.screen_loader import load_screen, reload_screens
from ui.render_telegram import render_screen

# ─── Data layer ───────────────────────────────────────────────────────────────
from telegram.bot_users import (
    _upsert_registration, _is_blocked_reg, _is_pending_reg,
    _get_pending_registrations,
    _slug, _load_note_text, _save_note_file,
)

# ─── Voice pipeline ───────────────────────────────────────────────────────────
from features.bot_voice import (
    _handle_voice_message, _handle_note_read_aloud, _handle_digest_tts,
    _warm_piper_cache, _start_persistent_piper, _setup_tmpfs_model,
    _cleanup_orphaned_tts, _fw_preload,
)

# ─── Admin handlers ───────────────────────────────────────────────────────────
from telegram.bot_admin import (
    _handle_admin_menu, _handle_admin_list_users,
    _start_admin_add_user, _finish_admin_add_user,
    _start_admin_remove_user, _finish_admin_remove_user,
    _handle_admin_pending_users,
    _do_approve_registration, _do_block_registration,
    _notify_admins_new_registration, _notify_admins_new_version,
    _handle_voice_opts_menu, _handle_voice_opt_toggle,
    _handle_admin_changelog,
    _handle_admin_logs_menu, _handle_admin_logs_show,
    _handle_admin_llm_menu, _handle_set_llm,
    _handle_admin_llm_per_func, _handle_admin_llm_set,
    _handle_openai_llm_menu, _handle_llm_setkey_prompt, _handle_save_llm_key,
    _handle_admin_llm_fallback_menu, _handle_admin_llm_fallback_toggle,
    _handle_admin_voice_config, _handle_admin_stt_set, _handle_admin_fw_model_set,
    _handle_admin_rag_menu, _handle_admin_rag_toggle, _handle_admin_rag_log,
    _admin_keyboard,
)

# ─── User handlers ────────────────────────────────────────────────────────────
from telegram.bot_handlers import (
    _handle_digest, _refresh_digest,
    _handle_chat_message,
    _handle_system_message, _execute_pending_cmd,
    _handle_notes_menu, _handle_note_list, _start_note_create,
    _handle_note_open, _handle_note_raw, _start_note_edit, _handle_note_delete,
    _start_note_append, _start_note_replace,
    _notes_menu_keyboard,
    _note_slug_from_cb,
    _handle_profile,
    _handle_web_link,
    _start_profile_edit_name, _finish_profile_edit_name,
    _start_profile_change_pw, _finish_profile_change_pw,
    _handle_profile_lang, _set_profile_lang, _handle_profile_my_data,
    _pending_profile,
)

# ─── Calendar ─────────────────────────────────────────────────────────────────
from features.bot_calendar import (
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
from features.bot_mail_creds import (
    handle_mail_consent, handle_mail_consent_agree,
    handle_mail_provider, finish_mail_setup,
    handle_mail_settings, handle_mail_del_creds,
    _pending_mail_setup,
)
# ─── Email send ────────────────────────────────────────────────────────────
from features.bot_email import (
    handle_send_email, handle_email_change_target, finish_email_set_target,
)

# ─── Error protocol ────────────────────────────────────────────────────────
from features.bot_error_protocol import (
    _start_error_protocol, _finish_errp_name,
    _errp_collect_text, _errp_collect_voice, _errp_collect_photo,
    _errp_send, _errp_cancel,
)

# ─── Contact book ───────────────────────────────────────────────────────────
from features.bot_contacts import (
    _handle_contacts_menu, _handle_contact_list, _handle_contact_open,
    _start_contact_add, _finish_contact_add, _handle_contact_add_skip,
    _start_contact_edit, _start_contact_edit_field, _finish_contact_edit,
    _handle_contact_delete, _handle_contact_delete_confirmed,
    _start_contact_search, _finish_contact_search,
    _pending_contact,
)

# ─── Documents / RAG ──────────────────────────────────────────────────────────
from features.bot_documents import (
    _handle_docs_menu,
    _handle_doc_upload,
    _handle_doc_delete,
    _handle_doc_delete_confirmed,
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
# /link — generate a web-account link code
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["link"])
def cmd_link(message):
    if not _is_allowed(message.chat.id):
        _deny(message.chat.id)
        return
    _set_lang(message.chat.id, message.from_user)
    _handle_web_link(message.chat.id)


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
        ("🤖 Telegram Bot",    "taris-telegram"),
        ("🌐 AI Gateway",      "taris-gateway"),
        ("🎤 Voice Assistant", "taris-voice"),
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
        f"🖥️ *Taris Bot Status*\n\n"
        f"🎯 *Mode:* `{mode}`\n"
        f"🤖 *LLM:* `{LLM_PROVIDER}` › `{active_model}`\n"
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
        role = "admin" if _is_admin(cid) else "guest" if _is_guest(cid) else "user"
        ctx = UserContext(user_id=cid, chat_id=cid, lang=_lang(cid), role=role)
        screen = load_screen("screens/main_menu.yaml", ctx,
                             t_func=lambda _lang_arg, key: _t(cid, key))
        render_screen(screen, cid, bot)

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
    elif data == "voice_audio_toggle":
        _st._user_audio[cid] = not _st._user_audio.get(cid, True)

    # ── Help ───────────────────────────────────────────────────────────────
    elif data == "help":
        role = "admin" if _is_admin(cid) else "guest" if _is_guest(cid) else "user"
        ctx = UserContext(user_id=cid, chat_id=cid, lang=_lang(cid), role=role)
        screen = load_screen("screens/help.yaml", ctx,
                             t_func=lambda _lang_arg, key: _t(cid, key))
        render_screen(screen, cid, bot)
    # ── User profile ───────────────────────────────────────────────────────────
    elif data == "profile":
        if not _is_allowed(cid): return _deny(cid)
        _handle_profile(cid)
    elif data == "web_link":
        if not _is_allowed(cid): return _deny(cid)
        _handle_web_link(cid)
    elif data == "profile_edit_name":
        if not _is_allowed(cid): return _deny(cid)
        _start_profile_edit_name(cid)
    elif data == "profile_change_pw":
        if not _is_allowed(cid): return _deny(cid)
        _start_profile_change_pw(cid)
    elif data == "profile_set_lang":
        if not _is_allowed(cid): return _deny(cid)
        _handle_profile_lang(cid)
    elif data.startswith("profile_lang_"):
        if not _is_allowed(cid): return _deny(cid)
        _set_profile_lang(cid, data[len("profile_lang_"):])
    elif data == "profile_my_data":
        if not _is_allowed(cid): return _deny(cid)
        _handle_profile_my_data(cid)
    # ── Admin panel ────────────────────────────────────────────────────────
    elif data == "noop":
        pass  # separator buttons — ignore silently
    elif data == "admin_menu":
        if _is_admin(cid):
            pending_count = len(_get_pending_registrations())
            pending_badge = f"  ({pending_count} new)" if pending_count else ""
            ctx = UserContext(user_id=cid, chat_id=cid, lang=_lang(cid), role="admin")
            screen = load_screen("screens/admin_menu.yaml", ctx,
                                 variables={"pending_badge": pending_badge},
                                 t_func=lambda _lang_arg, key: _t(cid, key))
            render_screen(screen, cid, bot)
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

    elif data == "admin_llm_fallback_menu":
        if _is_admin(cid):
            _handle_admin_llm_fallback_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_llm_fallback_toggle":
        if _is_admin(cid):
            _handle_admin_llm_fallback_toggle(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_llm_for:"):
        if _is_admin(cid):
            _handle_admin_llm_per_func(cid, data[len("admin_llm_for:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_llm_set:"):
        if _is_admin(cid):
            parts = data[len("admin_llm_set:"):].split(":", 1)
            use_case = parts[0]
            provider = parts[1] if len(parts) > 1 else ""
            _handle_admin_llm_set(cid, use_case, provider)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_voice_config":
        if _is_admin(cid):
            _handle_admin_voice_config(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_stt_set:"):
        if _is_admin(cid):
            _handle_admin_stt_set(cid, data[len("admin_stt_set:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_fw_model:"):
        if _is_admin(cid):
            _handle_admin_fw_model_set(cid, data[len("admin_fw_model:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── RAG administration ────────────────────────────────────────────
    elif data == "admin_rag_menu":
        if _is_admin(cid):
            _handle_admin_rag_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_rag_toggle":
        if _is_admin(cid):
            _handle_admin_rag_toggle(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_rag_log":
        if _is_admin(cid):
            _handle_admin_rag_log(cid)
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

    # ── Screen DSL reload ──────────────────────────────────────────────────
    elif data == "reload_screens":
        if _is_admin(cid):
            reload_screens()
            bot.send_message(cid, "✅ Screens reloaded")
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── Log viewer ─────────────────────────────────────────────────────────
    elif data == "admin_logs_menu":
        if _is_admin(cid):
            _handle_admin_logs_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_logs_show:"):
        if _is_admin(cid):
            _handle_admin_logs_show(cid, data[len("admin_logs_show:"):])
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
            slug = _note_slug_from_cb(cid, data[len("note_open:"):]) or data[len("note_open:"):]
            _handle_note_open(cid, slug)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_tts:"):
        if not _is_guest(cid):
            slug = _note_slug_from_cb(cid, data[len("note_tts:"):]) or data[len("note_tts:"):]
            _handle_note_read_aloud(cid, slug)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_raw:"):
        if not _is_guest(cid):
            slug = _note_slug_from_cb(cid, data[len("note_raw:"):]) or data[len("note_raw:"):]
            _handle_note_raw(cid, slug)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_edit:"):
        if not _is_guest(cid):
            slug = _note_slug_from_cb(cid, data[len("note_edit:"):]) or data[len("note_edit:"):]
            _start_note_edit(cid, slug)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_append:"):
        if not _is_guest(cid):
            slug = _note_slug_from_cb(cid, data[len("note_append:"):]) or data[len("note_append:"):]
            _start_note_append(cid, slug)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_replace:"):
        if not _is_guest(cid):
            slug = _note_slug_from_cb(cid, data[len("note_replace:"):]) or data[len("note_replace:"):]
            _start_note_replace(cid, slug)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_delete:"):
        if not _is_guest(cid):
            slug = _note_slug_from_cb(cid, data[len("note_delete:"):]) or data[len("note_delete:"):]
            _handle_note_delete(cid, slug)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))
    # ── Send as email ───────────────────────────────────────────────────────
    elif data.startswith("note_email:"):
        from telegram.bot_users import _load_note_text
        slug    = data[len("note_email:"):]
        content = _load_note_text(cid, slug)
        if content:
            handle_send_email(cid, f"Note: {slug.replace('_', ' ')}", content)
        else:
            bot.send_message(cid, _t(cid, "note_not_found"), reply_markup=_back_keyboard())

    elif data == "digest_email":
        from features.bot_mail_creds import _last_digest_file
        last_f = _last_digest_file(cid)
        if last_f.exists() and last_f.stat().st_size > 0:
            body = last_f.read_text(encoding="utf-8", errors="replace").strip()
            handle_send_email(cid, "Mail Digest", body)
        else:
            bot.send_message(cid, _t(cid, "digest_not_ready"), reply_markup=_back_keyboard())

    elif data.startswith("cal_email:"):
        from features.bot_calendar import _cal_load
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

    # ── Error protocol ─────────────────────────────────────────────────────
    elif data == "errp_start":
        if _is_admin(cid):
            _start_error_protocol(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))
    elif data == "errp_send":
        if _is_admin(cid):
            _errp_send(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))
    elif data == "errp_cancel":
        _errp_cancel(cid)

    # ── Contacts ────────────────────────────────────────────────────────────
    elif data == "menu_contacts":
        if not _is_guest(cid):
            _handle_contacts_menu(cid)
        else:
            _deny(cid)
    elif data in ("contact_create", "contact_list"):
        if not _is_guest(cid):
            if data == "contact_create":
                _start_contact_add(cid)
            else:
                _handle_contact_list(cid)
        else:
            _deny(cid)
    elif data == "contact_add_skip":
        if not _is_guest(cid):
            _handle_contact_add_skip(cid)
    elif data == "contact_search":
        if not _is_guest(cid):
            _start_contact_search(cid)
        else:
            _deny(cid)
    elif data.startswith("contact_page:"):
        if not _is_guest(cid):
            _handle_contact_list(cid, offset=int(data.split(":")[1]))
    elif data.startswith("contact_open:"):
        if not _is_guest(cid):
            _handle_contact_open(cid, data[len("contact_open:"):])
    elif data.startswith("contact_edit:"):
        if not _is_guest(cid):
            _start_contact_edit(cid, data[len("contact_edit:"):])
    elif data.startswith("contact_edit_field:"):
        if not _is_guest(cid):
            parts = data.split(":")
            _start_contact_edit_field(cid, parts[1], parts[2])
    elif data.startswith("contact_del:"):
        if not _is_guest(cid):
            _handle_contact_delete(cid, data[len("contact_del:"):])
    elif data.startswith("contact_del_confirm:"):
        if not _is_guest(cid):
            _handle_contact_delete_confirmed(cid, data[len("contact_del_confirm:"):])

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
    # ── Documents / RAG ────────────────────────────────────────────────────
    elif data == "menu_docs":
        if not _is_guest(cid):
            _handle_docs_menu(cid)
    elif data.startswith("doc_del:"):
        if not _is_guest(cid):
            _handle_doc_delete(cid, data[len("doc_del:"):])
    elif data.startswith("doc_del_confirm:"):
        if not _is_guest(cid):
            _handle_doc_delete_confirmed(cid, data[len("doc_del_confirm:"):])
    # ── Confirm / cancel system command ────────────────────────────────────
    elif data == "cancel":
        _st._pending_cmd.pop(cid, None)
        _st._pending_note.pop(cid, None)
        _pending_cal.pop(cid, None)
        _pending_mail_setup.pop(cid, None)
        _st._pending_error_protocol.pop(cid, None)
        _pending_profile.pop(cid, None)
        _pending_contact.pop(cid, None)
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

    # ── Profile self-service text flows ────────────────────────────────────────
    if mode == "profile_edit_name":
        _finish_profile_edit_name(cid, message.text)
        return

    if mode == "profile_change_pw":
        _finish_profile_change_pw(cid, message.text)
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

    if mode == "note_append_content":
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
        existing   = _load_note_text(cid, slug) or ""
        content    = existing.rstrip() + "\n\n" + message.text.strip()
        _save_note_file(cid, slug, content)
        title_line = existing.splitlines()[0] if existing else f"# {slug}"
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

    # ── Error protocol flows ──────────────────────────────────────────
    if mode == "errp_name":
        if _is_admin(cid):
            _finish_errp_name(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
        return

    if mode == "errp_collect":
        if _is_admin(cid):
            _errp_collect_text(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
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

    # ── Contact book flows ─────────────────────────────────────────────────
    if mode == "contact_add":
        if not _is_guest(cid):
            _finish_contact_add(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
            _pending_contact.pop(cid, None)
        return

    if mode == "contact_edit":
        if not _is_guest(cid):
            _finish_contact_edit(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
            _pending_contact.pop(cid, None)
        return

    if mode == "contact_search":
        if not _is_guest(cid):
            _finish_contact_search(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
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
    # Error protocol voice collection
    if _st._user_mode.get(cid) == "errp_collect" and cid in _st._pending_error_protocol:
        _errp_collect_voice(cid, message.voice)
        return
    _handle_voice_message(cid, message.voice)


# ─────────────────────────────────────────────────────────────────────────────
# Photo handler (error protocol collection)
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=["photo"])
def photo_handler(message):
    cid = message.chat.id
    if not _is_allowed(cid):
        _deny(cid)
        return
    _set_lang(cid, message.from_user)
    if _st._user_mode.get(cid) == "errp_collect" and cid in _st._pending_error_protocol:
        _errp_collect_photo(cid, message.photo)
        return
    # Outside error protocol — no general photo handling needed


@bot.message_handler(content_types=["document"])
def document_handler(message):
    cid = message.chat.id
    if not _is_allowed(cid):
        _deny(cid)
        return
    _set_lang(cid, message.from_user)
    _handle_doc_upload(message)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    from core.bot_db import init_db as _init_db
    _init_db()
    log.info("=" * 50)
    log.info("Pico Telegram Menu Bot starting")
    from core.bot_config import ADMIN_USERS, ALLOWED_USERS
    log.info(f"  Admin users  : {sorted(ADMIN_USERS)}")
    log.info(f"  Allowed users: {sorted(ALLOWED_USERS)}")
    log.info(f"  Guest users  : {sorted(_st._dynamic_users)}")
    log.info(f"  taris     : {TARIS_BIN}")
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

    # Preload faster-whisper model if it will be used — eliminates first-call cold-load
    if STT_PROVIDER == "faster_whisper" or _st._voice_opts.get("faster_whisper_stt"):
        log.info("[FasterWhisper] preloading model in background thread")
        threading.Thread(target=_fw_preload, daemon=True).start()

    # ── Startup tasks ─────────────────────────────────────────────────────
    _st.load_conversation_history()
    _cleanup_orphaned_tts()
    _notify_admins_new_version()
    configure_alert_handler(bot.send_message, ADMIN_USERS)
    attach_alerts_to_main_log()
    _cal_reschedule_all()
    threading.Thread(target=_cal_morning_briefing_loop, daemon=True).start()

    log.info("Polling Telegram…")

    # Graceful shutdown: stop polling before process exits so Telegram drops
    # the connection cleanly and the next start doesn't get a 409 Conflict.
    def _on_stop(signum, _frame):
        log.info(f"[Bot] signal {signum} — stopping polling…")
        bot.stop_polling()

    signal.signal(signal.SIGTERM, _on_stop)
    signal.signal(signal.SIGINT,  _on_stop)

    bot.infinity_polling(timeout=30, long_polling_timeout=20)


if __name__ == "__main__":
    main()
