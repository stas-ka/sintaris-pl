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
import time as _time

# ─── Core ────────────────────────────────────────────────────────────────────
from core.bot_config import (
    BOT_VERSION, TARIS_BIN, DIGEST_SCRIPT,
    PIPER_MODEL_TMPFS, LLM_PROVIDER, STT_PROVIDER, DEVICE_VARIANT,
    FASTER_WHISPER_PRELOAD, AUTO_GUEST_ENABLED,
    GUEST_MSG_HOURLY_LIMIT, GUEST_MSG_DAILY_LIMIT,
    ADMIN_USERS,
    log,
)
import core.bot_state as _st

from core.bot_instance import bot
from core.bot_logger import configure_alert_handler, attach_alerts_to_main_log
from core.bot_embeddings import EmbeddingService

# ─── Shared utilities ─────────────────────────────────────────────────────────
from telegram.bot_access import (
    _is_allowed, _is_admin, _is_guest, _is_advanced,
    _deny, _set_lang, _send_menu, _lang,
    _t, _menu_keyboard, _back_keyboard, _escape_md,
    _get_active_model, _run_subprocess,
    _get_prompt_role_key, _check_guest_rate_limit,
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
    _set_reg_lang,
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
    _do_approve_registration, _do_block_registration, _do_approve_as_guest,
    _notify_admins_new_registration, _notify_admins_new_version,
    _handle_voice_opts_menu, _handle_voice_opt_toggle,
    _handle_admin_changelog,
    _handle_admin_logs_menu, _handle_admin_logs_show,
    _handle_admin_llm_menu, _handle_set_llm,
    _handle_admin_llm_per_func, _handle_admin_llm_set,
    _handle_openai_llm_menu, _handle_llm_setkey_prompt, _handle_save_llm_key,
    _handle_admin_llm_fallback_menu, _handle_admin_llm_fallback_toggle,
    _handle_ollama_llm_menu, _handle_ollama_set_model, _handle_ollama_persist_model,
    _handle_ollama_pull_start, _handle_ollama_pull_done, _pending_ollama_pull,
    _handle_user_model_menu, _handle_user_model_set,
    _handle_admin_voice_config, _handle_admin_stt_set, _handle_admin_fw_model_set,
    _handle_admin_voice_menu,
    _handle_admin_rag_menu, _handle_admin_rag_toggle, _handle_admin_rag_log,
    _handle_admin_rag_settings, _handle_admin_rag_stats, _handle_admin_doc_stats,
    _start_admin_rag_set, _finish_admin_rag_set,
    _handle_admin_rag_user_settings, _handle_admin_rag_user_adjust, _handle_admin_rag_user_reset,
    _handle_admin_llm_trace,
    _handle_admin_memory_menu, _handle_admin_mem_set_start,
    _handle_admin_mcp_menu, _start_admin_mcp_set, _finish_admin_mcp_set, _handle_admin_mcp_clear,
    _handle_admin_restart, _handle_admin_restart_confirmed,
    _handle_admin_n8n_menu, _handle_admin_crm_menu,
    _handle_crm_contacts_list, _handle_crm_add_start, _handle_crm_search_start,
    _handle_crm_stats, finish_crm_input,
    _handle_admin_roles_menu, _handle_admin_user_set_role, _handle_admin_role_notify,
    _handle_admin_user_role_detail, _handle_admin_users_menu,
    _handle_admin_security_policy, _handle_admin_syschat_block_remove,
    _handle_admin_syschat_block_add_prompt, handle_admin_syschat_block_add_input,
    _pending_syschat_block_add,
    _handle_admin_appt_menu, _handle_admin_appt_mode_toggle,
    _handle_admin_appt_single_menu, _handle_admin_appt_single_set,
    _handle_admin_appt_roles_menu, _handle_admin_appt_role_toggle,
    _admin_keyboard,
)

# ─── Campaign Agent ───────────────────────────────────────────────────────────
import features.bot_campaign as _campaign
# ─── Content Strategy Agent ──────────────────────────────────────────────────
import features.bot_content as _content

# ─── Notify Agent ────────────────────────────────────────────────────────────
import features.bot_notify as _notify

# ─── Remote Knowledge Base Agent ─────────────────────────────────────────────
import features.bot_remote_kb as _remote_kb

# ─── User handlers ────────────────────────────────────────────────────────────
from telegram.bot_handlers import (
    _handle_digest, _refresh_digest,
    _handle_chat_message,
    _handle_system_message, _execute_pending_cmd,
    _handle_notes_menu, _handle_note_list, _start_note_create,
    _handle_note_open, _handle_note_raw, _start_note_edit,
    _handle_note_delete, _handle_note_delete_confirmed,
    _start_note_append, _start_note_replace,
    _start_note_rename, _handle_note_download, _handle_note_download_zip,
    _notes_menu_keyboard,
    _note_slug_from_cb,
    _handle_profile,
    _handle_web_link,
    _start_profile_edit_name, _finish_profile_edit_name,
    _start_profile_set_email, _finish_profile_set_email,
    _start_profile_change_pw, _finish_profile_change_pw,
    _handle_profile_lang, _set_profile_lang, _handle_profile_my_data,
    _handle_profile_clear_memory, _handle_profile_clear_memory_confirmed,
    _handle_profile_toggle_memory,
    _handle_profile_voice_gender,
    _pending_profile,
)

# ─── Calendar ─────────────────────────────────────────────────────────────────
from features.bot_calendar import (
    _handle_calendar_menu, _handle_cal_event_detail, _handle_guest_cal_event_detail,
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
    _start_guest_meeting, _finish_guest_meeting_topic, _finish_guest_meeting_slot,
    _handle_inv_confirm, _handle_inv_decline,
    _handle_expert_selected, _handle_day_nav,
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
    _handle_contact_sync_crm,
    _pending_contact,
)

# ─── Documents / RAG ──────────────────────────────────────────────────────────
from features.bot_documents import (
    _handle_docs_menu,
    _handle_doc_upload,
    _handle_doc_delete,
    _handle_doc_delete_confirmed,
    _handle_doc_detail,
    _handle_doc_rename_start,
    _handle_doc_rename_done,
    _handle_doc_share_toggle,
    _handle_doc_replace,
    _handle_doc_keep_both,
    _pending_rename as _docs_pending_rename,
)
from features.bot_dev import (
    _handle_dev_menu,
    _handle_dev_chat_start,
    handle_dev_chat_message,
    _handle_dev_restart,
    _handle_dev_restart_confirmed,
    _handle_dev_log,
    _handle_dev_error,
    _handle_dev_files,
    _handle_dev_security_log,
    log_access_denied,
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
        elif AUTO_GUEST_ENABLED:
            # Auto-register as guest — no admin approval needed
            name = f"{first} {last}".strip() or username or str(cid)
            _upsert_registration(cid, username=username, name=name,
                                 status="guest",
                                 first_name=first, last_name=last)
            # Persist the detected language so it survives bot restarts
            _set_reg_lang(cid, _lang(cid))
            _st._dynamic_guests.add(cid)
            log.info("[Guest] auto-registered chat_id=%s username=%s lang=%s", cid, username, _lang(cid))
            bot.send_message(cid, _t(cid, "guest_welcome"),
                             parse_mode="Markdown",
                             reply_markup=_menu_keyboard(cid))
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

    # Service list and systemctl scope differ by variant
    if DEVICE_VARIANT == "openclaw":
        services = [
            ("🤖 Telegram Bot",    "taris-telegram"),
            ("🌐 Web UI",          "taris-web"),
            ("🧠 Ollama LLM",      "ollama"),
        ]
        systemctl_scope = ["--user"]
    else:
        services = [
            ("🤖 Telegram Bot",    "taris-telegram"),
            ("🌐 AI Gateway",      "taris-gateway"),
            ("🎤 Voice Assistant", "taris-voice"),
        ]
        systemctl_scope = []

    svc_lines = []
    for label, svc_name in services:
        _, state = _run_subprocess(
            ["systemctl"] + systemctl_scope + ["is-active", svc_name], timeout=5
        )
        state = state.strip() or "unknown"
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
    _cb_t0 = _time.perf_counter()
    cid  = call.message.chat.id
    if not _is_allowed(cid):
        try:
            bot.answer_callback_query(call.id, "⛔ Access denied")
        except Exception:
            pass
        return

    _set_lang(cid, call.from_user)
    data = call.data

    _ack_t0 = _time.perf_counter()
    try:
        bot.answer_callback_query(call.id)   # dismiss spinner
    except Exception as _ack_err:
        # Callback expired (>60s old) or already answered — log and CONTINUE.
        # Do NOT return: skipping the action leaves the user with no response.
        # Do NOT propagate: unhandled ApiTelegramException in a worker triggers
        # raise_exceptions() in the polling loop, which doubles the poll backoff
        # (0.25s → 60s) and makes the bot appear frozen.
        log.warning("[PERF] answer_callback_query failed (data=%s): %s", data, _ack_err)
    _ack_ms = (_time.perf_counter() - _ack_t0) * 1000
    if _ack_ms > 300:
        log.warning("[PERF] answer_callback_query slow: %.0fms (data=%s)", _ack_ms, data)

    # ── Navigation ─────────────────────────────────────────────────────────
    if data == "menu":
        _st._user_mode.pop(cid, None)
        _st._pending_cmd.pop(cid, None)
        _st._system_history.pop(cid, None)
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

    # ── Meeting request (all allowed users) ────────────────────────────────
    elif data == "guest_meeting":
        _start_guest_meeting(cid)
    elif data == "guest_request_access":
        bot.answer_callback_query(call.id)
        bot.send_message(cid, _t(cid, "guest_access_requested"), parse_mode="Markdown")
        uname = getattr(call.from_user, "username", None)
        fname = getattr(call.from_user, "first_name", "") or ""
        lname = getattr(call.from_user, "last_name", "") or ""
        display = f"{fname} {lname}".strip() or f"@{uname}" if uname else str(cid)
        for admin_id in ADMIN_USERS:
            try:
                from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("✅ Promote to User", callback_data=f"admin_promote_user:{cid}"))
                bot.send_message(
                    admin_id,
                    f"🔓 *Guest access request*\n\nID: `{cid}`\nName: {display}",
                    parse_mode="Markdown",
                    reply_markup=kb,
                )
            except Exception as _e:
                log.warning("guest_request_access: admin notify failed %s: %s", admin_id, _e)
    elif data.startswith("cal_meet_expert:"):
        try:
            _handle_expert_selected(cid, int(data.split(":", 1)[1]))
        except (ValueError, IndexError):
            pass
    elif data.startswith("cal_meet_day:"):
        # format: cal_meet_day:<expert_id>:<YYYY-MM-DD>
        parts = data.split(":", 2)
        try:
            _handle_day_nav(cid, int(parts[1]), parts[2])
        except (ValueError, IndexError):
            pass
    elif data.startswith("cal_meet_slot:"):
        # format: cal_meet_slot:<expert_id>:<YYYY-MM-DD>:<hour>
        parts = data.split(":", 3)
        try:
            _finish_guest_meeting_slot(cid, int(parts[1]), parts[2], int(parts[3]))
        except (ValueError, IndexError):
            pass
    elif data.startswith("cal_inv_ok:"):
        inv_id = data.split(":", 1)[1]
        _handle_inv_confirm(cid, inv_id)
    elif data.startswith("cal_inv_no:"):
        inv_id = data.split(":", 1)[1]
        _handle_inv_decline(cid, inv_id)

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
    elif data == "profile_set_email":
        # All users (including guests) may set their contact email
        _start_profile_set_email(cid)
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
    elif data == "profile_clear_memory":
        if not _is_allowed(cid): return _deny(cid)
        _handle_profile_clear_memory(cid)
    elif data == "profile_clear_memory_confirm":
        if not _is_allowed(cid): return _deny(cid)
        _handle_profile_clear_memory_confirmed(cid)
    elif data == "profile_toggle_memory":
        if not _is_allowed(cid): return _deny(cid)
        _handle_profile_toggle_memory(cid)
    elif data == "profile_voice_gender":
        if not _is_allowed(cid): return _deny(cid)
        _handle_profile_voice_gender(cid)
    # ── Developer menu ─────────────────────────────────────────────────────
    elif data == "dev_menu":
        _handle_dev_menu(cid)
    elif data == "dev_chat":
        _handle_dev_chat_start(cid)
    elif data == "dev_restart":
        _handle_dev_restart(cid)
    elif data == "dev_restart_confirmed":
        _handle_dev_restart_confirmed(cid)
    elif data == "dev_log":
        _handle_dev_log(cid)
    elif data == "dev_error":
        _handle_dev_error(cid)
    elif data == "dev_files":
        _handle_dev_files(cid)
    elif data == "dev_security_log":
        _handle_dev_security_log(cid)
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

    elif data == "admin_users_menu":
        if _is_admin(cid):
            _handle_admin_users_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_add_user":
        if _is_admin(cid):
            _start_admin_add_user(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_restart":
        if _is_admin(cid):
            _handle_admin_restart(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_restart_confirmed":
        if _is_admin(cid):
            _handle_admin_restart_confirmed(cid)
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

    elif data.startswith("reg_guest:"):
        if _is_admin(cid):
            _do_approve_as_guest(cid, int(data.split(":", 1)[1]))
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

    elif data == "ollama_llm_menu":
        if _is_admin(cid):
            _handle_ollama_llm_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_ollama_set:"):
        if _is_admin(cid):
            _handle_ollama_set_model(cid, data[len("admin_ollama_set:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_ollama_persist:"):
        if _is_admin(cid):
            _handle_ollama_persist_model(cid, data[len("admin_ollama_persist:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "ollama_pull_start":
        if _is_admin(cid):
            _handle_ollama_pull_start(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "user_model_menu":
        if _is_admin(cid):
            _handle_user_model_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("user_model_set:"):
        if _is_admin(cid):
            _handle_user_model_set(cid, data[len("user_model_set:"):])
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

    elif data == "admin_voice_menu":
        if _is_admin(cid):
            _handle_admin_voice_menu(cid)
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

    elif data == "admin_rag_stats":
        if _is_admin(cid):
            _handle_admin_rag_stats(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_doc_stats":
        if _is_admin(cid):
            _handle_admin_doc_stats(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_llm_trace":
        if _is_admin(cid):
            _handle_admin_llm_trace(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_memory_menu":
        if _is_admin(cid):
            _handle_admin_memory_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data in ("admin_mem_set_hist", "admin_mem_set_summ", "admin_mem_set_mid"):
        if _is_admin(cid):
            _handle_admin_mem_set_start(cid, data[len("admin_mem_set_"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_rag_settings":
        if _is_admin(cid):
            _handle_admin_rag_settings(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data in ("admin_rag_set_topk", "admin_rag_set_chunk", "admin_rag_set_timeout", "admin_rag_set_temp"):
        if _is_admin(cid):
            _start_admin_rag_set(cid, data[len("admin_rag_set_"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_rag_user_settings":
        if _is_admin(cid):
            _handle_admin_rag_user_settings(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data in ("admin_rag_user_topk_inc", "admin_rag_user_topk_dec",
                  "admin_rag_user_chunk_inc", "admin_rag_user_chunk_dec"):
        if _is_admin(cid):
            key   = "topk" if "topk" in data else "chunk"
            delta = 1 if data.endswith("_inc") else -1
            if key == "chunk": delta *= 200
            _handle_admin_rag_user_adjust(cid, key, delta)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_rag_user_reset":
        if _is_admin(cid):
            _handle_admin_rag_user_reset(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── MCP remote RAG configuration ───────────────────────────────────────
    elif data == "admin_mcp_menu":
        if _is_admin(cid):
            _handle_admin_mcp_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data in ("admin_mcp_set_url", "admin_mcp_set_token", "admin_mcp_set_timeout", "admin_mcp_set_top_k"):
        if _is_admin(cid):
            _start_admin_mcp_set(cid, data[len("admin_mcp_set_"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_mcp_clear":
        if _is_admin(cid):
            _handle_admin_mcp_clear(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── N8N integration ───────────────────────────────────────────────────
    elif data == "admin_n8n_menu":
        if _is_admin(cid):
            _handle_admin_n8n_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── CRM ───────────────────────────────────────────────────────────────
    elif data == "admin_crm_menu":
        if _is_admin(cid):
            _handle_admin_crm_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "crm_contacts":
        if _is_admin(cid):
            _handle_crm_contacts_list(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "crm_add_start":
        if _is_admin(cid):
            _handle_crm_add_start(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "crm_search_start":
        if _is_admin(cid):
            _handle_crm_search_start(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "crm_stats":
        if _is_admin(cid):
            _handle_crm_stats(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── Role management ────────────────────────────────────────────────────────
    elif data == "admin_roles_menu":
        if _is_admin(cid):
            _handle_admin_roles_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_role_user:"):
        if _is_admin(cid):
            try:
                _handle_admin_user_role_detail(cid, int(data.split(":", 1)[1]))
            except (ValueError, IndexError):
                pass
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_role_set:"):
        if _is_admin(cid):
            parts = data.split(":", 2)
            if len(parts) == 3:
                _handle_admin_user_set_role(cid, int(parts[1]), parts[2])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_promote_user:"):
        if _is_admin(cid):
            try:
                target_id = int(data.split(":", 1)[1])
                _handle_admin_user_set_role(cid, target_id, "user")
            except (ValueError, IndexError):
                pass
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_role_notify:"):
        if _is_admin(cid):
            parts = data.split(":", 3)
            if len(parts) == 4:
                _handle_admin_role_notify(cid, int(parts[1]), parts[2], parts[3])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── Security policy ───────────────────────────────────────────────────────
    elif data == "admin_security_policy":
        if _is_admin(cid):
            _handle_admin_security_policy(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_syschat_block_add":
        if _is_admin(cid):
            _handle_admin_syschat_block_add_prompt(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_syschat_block_rm:"):
        if _is_admin(cid):
            try:
                idx = int(data.split(":")[1])
                _handle_admin_syschat_block_remove(cid, idx)
            except (ValueError, IndexError):
                pass
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── Appointment routing settings ──────────────────────────────────────────
    elif data == "admin_appt_menu":
        if _is_admin(cid): _handle_admin_appt_menu(cid)
        else: bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_appt_mode_toggle":
        if _is_admin(cid): _handle_admin_appt_mode_toggle(cid)
        else: bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_appt_single_menu":
        if _is_admin(cid): _handle_admin_appt_single_menu(cid)
        else: bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_appt_single_set:"):
        if _is_admin(cid):
            try:
                _handle_admin_appt_single_set(cid, int(data.split(":", 1)[1]))
            except (ValueError, IndexError):
                pass
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "admin_appt_roles_menu":
        if _is_admin(cid): _handle_admin_appt_roles_menu(cid)
        else: bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("admin_appt_role_toggle:"):
        if _is_admin(cid):
            _handle_admin_appt_role_toggle(cid, data.split(":", 1)[1])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    # ── Agents menu ───────────────────────────────────────────────────────────
    elif data == "agents_menu":
        if _is_admin(cid) or _is_advanced(cid):
            _handle_agents_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "campaign_start":
        if _is_admin(cid) or _is_advanced(cid):
            if not _campaign.is_configured():
                bot.send_message(cid, _t(cid, "campaign_not_configured"))
            else:
                _campaign.start_campaign(cid, bot, _t)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "campaign_confirm_send":
        if _is_admin(cid) or _is_advanced(cid):
            _campaign.confirm_send(cid, bot, _t)

    elif data == "campaign_edit_template":
        if _is_admin(cid) or _is_advanced(cid):
            _campaign.start_template_edit(cid, bot, _t)

    elif data == "campaign_cancel":
        _campaign.cancel(cid)
        bot.send_message(cid, _t(cid, "campaign_cancelled"))

    # ── Content Strategy Agent ─────────────────────────────────────────────────
    elif data == "content_start":
        if _is_admin(cid) or _is_advanced(cid):
            _content.show_menu(cid, bot, _t)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("content_mode:"):
        if _is_admin(cid) or _is_advanced(cid):
            mode = data[len("content_mode:"):]
            _content.start_mode(cid, mode, bot, _t)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("content_platform:"):
        if _is_admin(cid) or _is_advanced(cid):
            platform = data[len("content_platform:"):]
            _content.on_platform_selected(cid, platform, bot, _t)

    elif data.startswith("content_kb:"):
        if _is_admin(cid) or _is_advanced(cid):
            use_kb = data[len("content_kb:"):] == "yes"
            _content.on_kb_selected(cid, use_kb, bot, _t)

    # Plan preview actions (correct / accept / download / new)
    elif data.startswith("content_plan_action:"):
        if _is_admin(cid) or _is_advanced(cid):
            action = data[len("content_plan_action:"):]
            _content.on_plan_action(cid, action, bot, _t)

    # Post #N generation trigger
    elif data.startswith("content_genpost:"):
        if _is_admin(cid) or _is_advanced(cid):
            try:
                n = int(data[len("content_genpost:"):])
            except ValueError:
                n = 1
            _content.on_genpost_selected(cid, n, bot, _t)

    # Post preview actions (correct / save / download / publish / back_plan / new)
    elif data.startswith("content_post_action:"):
        if _is_admin(cid) or _is_advanced(cid):
            action = data[len("content_post_action:"):]
            _content.on_post_action(cid, action, bot, _t)

    # Delete item from cleanup menu
    elif data.startswith("content_del:"):
        if _is_admin(cid) or _is_advanced(cid):
            parts = data.split(":", 2)   # content_del:TYPE:SLUG
            if len(parts) == 3:
                _content.on_delete_request(cid, parts[1], parts[2], bot, _t)

    elif data == "content_del_confirm":
        if _is_admin(cid) or _is_advanced(cid):
            _content.on_delete_confirmed(cid, bot, _t)

    elif data == "content_del_cancel":
        if _is_admin(cid) or _is_advanced(cid):
            _content.on_delete_cancelled(cid, bot, _t)

    elif data.startswith("content_publish:"):
        if _is_admin(cid) or _is_advanced(cid):
            decision = data[len("content_publish:"):]
            _content.on_publish_decision(cid, decision, bot, _t)

    elif data == "content_pub_config":
        if _is_admin(cid) or _is_advanced(cid):
            _content.show_pub_config(cid, bot, _t)

    elif data.startswith("content_pub_set:"):
        if _is_admin(cid) or _is_advanced(cid):
            field = data[len("content_pub_set:"):]
            _content.on_pub_set(cid, field, bot, _t)

    # Legacy callback (pre-v2 sessions) — just cancel
    elif data.startswith("content_action:"):
        _content.cancel(cid)
        bot.send_message(cid, _t(cid, "content_cancelled"))

    elif data == "content_cancel":
        _content.cancel(cid)
        bot.send_message(cid, _t(cid, "content_cancelled"))

    # ── Notify Agent ───────────────────────────────────────────────────────────
    elif data == "notify_menu":
        if _is_admin(cid) or _is_advanced(cid):
            _notify.show_notify_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "notify_tpl_menu":
        if _is_admin(cid) or _is_advanced(cid):
            _notify.show_tpl_menu(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "notify_tpl_add":
        if _is_admin(cid) or _is_advanced(cid):
            _notify.start_tpl_add(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("notify_tpl_view:"):
        if _is_admin(cid) or _is_advanced(cid):
            _notify.show_tpl_view(cid, data[len("notify_tpl_view:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("notify_tpl_edit:"):
        if _is_admin(cid) or _is_advanced(cid):
            _notify.start_tpl_edit(cid, data[len("notify_tpl_edit:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("notify_tpl_del:"):
        if _is_admin(cid) or _is_advanced(cid):
            _notify.confirm_tpl_delete(cid, data[len("notify_tpl_del:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("notify_tpl_del_confirm:"):
        if _is_admin(cid) or _is_advanced(cid):
            _notify.do_tpl_delete(cid, data[len("notify_tpl_del_confirm:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "notify_send":
        if _is_admin(cid) or _is_advanced(cid):
            _notify.start_send(cid, owner_chat_id=cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("notify_tpl_pick:"):
        if _is_admin(cid) or _is_advanced(cid):
            _notify.on_tpl_picked(cid, data[len("notify_tpl_pick:"):])
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "notify_custom_msg":
        if _is_admin(cid) or _is_advanced(cid):
            _notify.start_custom_msg(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "notify_recipients_all":
        if _is_admin(cid) or _is_advanced(cid):
            _notify.on_recipients_all(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "notify_recipients_filter":
        if _is_admin(cid) or _is_advanced(cid):
            _notify.start_filter_input(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "notify_confirm_send":
        if _is_admin(cid) or _is_advanced(cid):
            _notify.confirm_send(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "notify_cancel":
        _notify.cancel(cid)
        bot.send_message(cid, _t(cid, "notify_cancelled"))

    # ── Remote KB Agent ────────────────────────────────────────────────────
    elif data == "remote_kb_menu":
        if _is_admin(cid) or _is_advanced(cid):
            _remote_kb.show_menu(cid, bot, _t)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "remote_kb_search":
        if _is_admin(cid) or _is_advanced(cid):
            if not _remote_kb.is_configured():
                bot.send_message(cid, _t(cid, "remote_kb_not_configured"))
            else:
                _remote_kb.start_search(cid, bot, _t)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "remote_kb_upload":
        if _is_admin(cid) or _is_advanced(cid):
            if not _remote_kb.is_configured():
                bot.send_message(cid, _t(cid, "remote_kb_not_configured"))
            else:
                _remote_kb.start_upload(cid, bot, _t)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "remote_kb_upload_done":
        if _is_admin(cid) or _is_advanced(cid):
            _remote_kb.finish_upload(cid, bot, _t)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "remote_kb_list_docs":
        if _is_admin(cid) or _is_advanced(cid):
            if not _remote_kb.is_configured():
                bot.send_message(cid, _t(cid, "remote_kb_not_configured"))
            else:
                _remote_kb.list_docs(cid, bot, _t)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "remote_kb_clear_mem":
        if _is_admin(cid) or _is_advanced(cid):
            if not _remote_kb.is_configured():
                bot.send_message(cid, _t(cid, "remote_kb_not_configured"))
            else:
                _remote_kb.clear_memory(cid, bot, _t)
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

    elif data.startswith("note_del_confirm:"):
        if not _is_guest(cid):
            slug = _note_slug_from_cb(cid, data[len("note_del_confirm:"):]) or data[len("note_del_confirm:"):]
            _handle_note_delete_confirmed(cid, slug)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_rename:"):
        if not _is_guest(cid):
            slug = _note_slug_from_cb(cid, data[len("note_rename:"):]) or data[len("note_rename:"):]
            _start_note_rename(cid, slug)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("note_download:"):
        if not _is_guest(cid):
            slug = _note_slug_from_cb(cid, data[len("note_download:"):]) or data[len("note_download:"):]
            _handle_note_download(cid, slug)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data == "note_download_zip":
        if not _is_guest(cid):
            _handle_note_download_zip(cid)
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

    elif data.startswith("cnt_sync_crm:"):
        if not _is_guest(cid):
            _handle_contact_sync_crm(cid, data[len("cnt_sync_crm:"):])

    # ── Calendar ───────────────────────────────────────────────────────────
    elif data == "menu_calendar":
        _handle_calendar_menu(cid)  # guest: shows own events, read-only keyboard (no Add/Console)

    elif data == "cal_add":
        if not _is_guest(cid):
            _start_cal_add(cid)
        else:
            bot.send_message(cid, _t(cid, "admin_only"))

    elif data.startswith("cal_event:"):
        if not _is_guest(cid):
            _handle_cal_event_detail(cid, data[len("cal_event:"):])
        else:
            _handle_guest_cal_event_detail(cid, data[len("cal_event:"):])

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
    elif data.startswith("doc_detail:"):
        if not _is_guest(cid):
            _handle_doc_detail(cid, data[len("doc_detail:"):])
    elif data.startswith("doc_rename:"):
        if not _is_guest(cid):
            _handle_doc_rename_start(cid, data[len("doc_rename:"):])
    elif data.startswith("doc_share:"):
        if not _is_guest(cid):
            _handle_doc_share_toggle(cid, data[len("doc_share:"):])
    elif data.startswith("doc_del:"):
        if not _is_guest(cid):
            _handle_doc_delete(cid, data[len("doc_del:"):])
    elif data.startswith("doc_del_confirm:"):
        if not _is_guest(cid):
            _handle_doc_delete_confirmed(cid, data[len("doc_del_confirm:"):])
    elif data.startswith("doc_replace:"):
        if not _is_guest(cid):
            _handle_doc_replace(cid, data[len("doc_replace:"):])
    elif data == "doc_keep_both":
        if not _is_guest(cid):
            _handle_doc_keep_both(cid)
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

    _cb_ms = (_time.perf_counter() - _cb_t0) * 1000
    if _cb_ms > 500:
        log.warning("[PERF] callback slow: %.0fms (data=%s cid=%s)", _cb_ms, data, cid)
    else:
        log.debug("[PERF] callback: %.0fms (data=%s)", _cb_ms, data)

# ─────────────────────────────────────────────────────────────────────────────
# Text message router
# ─────────────────────────────────────────────────────────────────────────────

# ── Agents menu ──────────────────────────────────────────────────────────────

def _handle_agents_menu(chat_id: int) -> None:
    """Show the Agents submenu."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            _t(chat_id, "agents_btn_campaign"), callback_data="campaign_start"
        ),
        InlineKeyboardButton(
            _t(chat_id, "agents_btn_content"), callback_data="content_start"
        ),
        InlineKeyboardButton(
            _t(chat_id, "agents_btn_notify"), callback_data="notify_menu"
        ),
    )
    kb.add(
        InlineKeyboardButton(
            _t(chat_id, "agents_btn_remote_kb"), callback_data="remote_kb_menu"
        ),
    )
    kb.add(
        InlineKeyboardButton(
            _t(chat_id, "agents_btn_back"), callback_data="menu"
        ),
    )
    bot.send_message(
        chat_id,
        _t(chat_id, "agents_menu_title"),
        reply_markup=kb,
        parse_mode="Markdown",
    )


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

    # Guest rate-limit check — applied before any LLM-bound flow
    if _is_guest(cid):
        allowed, reason = _check_guest_rate_limit(cid)
        if not allowed:
            if reason == "hourly":
                bot.send_message(cid, _t(cid, "guest_rate_limit_hourly",
                                         limit=str(GUEST_MSG_HOURLY_LIMIT)),
                                 parse_mode="Markdown")
            else:
                bot.send_message(cid, _t(cid, "guest_rate_limit_daily",
                                         limit=str(GUEST_MSG_DAILY_LIMIT)),
                                 parse_mode="Markdown")
            return

    # Admin typing an API key
    if cid in _st._pending_llm_key:
        if _is_admin(cid):
            _handle_save_llm_key(cid, message.text)
        else:
            _st._pending_llm_key.pop(cid, None)
        return

    # Admin typing a command to block in security policy
    if cid in _pending_syschat_block_add:
        if _is_admin(cid):
            handle_admin_syschat_block_add_input(cid, message.text)
        else:
            _pending_syschat_block_add.discard(cid)
        return

    mode = _st._user_mode.get(cid)

    # ── Meeting topic input — all allowed users ─────────────────────────────
    if mode == "guest_meeting_topic":
        _finish_guest_meeting_topic(cid, message.text)
        return

    # ── Campaign agent text input — must be checked BEFORE mode fallback to chat ──
    if _campaign.is_active(cid):
        if _is_admin(cid) or _is_advanced(cid):
            consumed = _campaign.handle_message(cid, message.text, bot, _t)
            if consumed:
                return
        else:
            _campaign.cancel(cid)

    # ── Content Strategy agent text input ─────────────────────────────────────
    if _content.is_active(cid):
        if _is_admin(cid) or _is_advanced(cid):
            consumed = _content.handle_message(cid, message.text, bot, _t)
            if consumed:
                return
        else:
            _content.cancel(cid)

    # ── Notify agent text input ────────────────────────────────────────────────
    if _notify.is_active(cid):
        if _is_admin(cid) or _is_advanced(cid):
            consumed = _notify.handle_message(cid, message.text)
            if consumed:
                return
        else:
            _notify.cancel(cid)

    # ── Remote KB agent text input ─────────────────────────────────────────────
    if _remote_kb.is_active(cid):
        if _is_admin(cid) or _is_advanced(cid):
            consumed = _remote_kb.handle_message(cid, message.text, bot, _t)
            if consumed:
                return
        else:
            _remote_kb.cancel(cid)

    if mode is None:
        # Default to chat mode — don't force menu on every unrouted text
        _st._user_mode[cid] = "chat"
        _handle_chat_message(cid, message.text)
        return

    # ── Profile self-service text flows ────────────────────────────────────────
    if mode == "profile_edit_name":
        _finish_profile_edit_name(cid, message.text)
        return

    if mode == "profile_set_email":
        _finish_profile_set_email(cid, message.text)
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

    if mode in ("admin_rag_set_topk", "admin_rag_set_chunk", "admin_rag_set_timeout", "admin_rag_set_temp"):
        if _is_admin(cid):
            _finish_admin_rag_set(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
            bot.send_message(cid, _t(cid, "admin_only"))
        return

    if mode is not None and mode.startswith("admin_mcp_set_"):
        if _is_admin(cid):
            _finish_admin_mcp_set(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
            bot.send_message(cid, _t(cid, "admin_only"))
        return

    if mode is not None and mode.startswith("admin_mem_"):
        if _is_admin(cid):
            setting_key = mode[len("admin_mem_"):]  # "hist", "summ", or "mid"
            db_keys = {
                "hist": "CONVERSATION_HISTORY_MAX",
                "summ": "CONV_SUMMARY_THRESHOLD",
                "mid":  "CONV_MID_MAX",
            }
            try:
                val = int(message.text.strip())
                from core.bot_db import db_set_system_setting
                db_set_system_setting(db_keys[setting_key], str(val))
                _st._user_mode.pop(cid, None)
                bot.send_message(cid, f"✅ {db_keys[setting_key]} = {val}")
                _handle_admin_memory_menu(cid)
            except (ValueError, KeyError):
                bot.send_message(cid, "❌ Please enter a valid integer.")
        else:
            _st._user_mode.pop(cid, None)
            bot.send_message(cid, _t(cid, "admin_only"))
        return

    # ── CRM multi-step input ─────────────────────────────────────────────
    if mode is not None and mode.startswith("crm_"):
        if _is_admin(cid):
            finish_crm_input(cid, message.text)
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
        _handle_note_open(cid, slug)
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
        _handle_note_open(cid, slug)
        return

    if mode == "note_rename_title":
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
        new_title  = message.text.strip()[:100]
        existing   = _load_note_text(cid, slug)
        if existing is None:
            bot.send_message(cid, _t(cid, "note_not_found"),
                             reply_markup=_notes_menu_keyboard(cid))
            return
        lines = existing.splitlines()
        body_lines = lines[2:] if len(lines) > 2 else (lines[1:] if len(lines) > 1 else [])
        content = f"# {new_title}\n\n" + "\n".join(body_lines).strip()
        _save_note_file(cid, slug, content)
        _handle_note_open(cid, slug)
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

    if mode == "doc_rename":
        if not _is_guest(cid):
            _handle_doc_rename_done(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
            _docs_pending_rename.pop(cid, None)
        return

    if mode == "ollama_pull":
        if _is_admin(cid):
            _handle_ollama_pull_done(cid, message.text)
        else:
            _st._user_mode.pop(cid, None)
            _pending_ollama_pull.pop(cid, None)
        return

    if mode == "dev_chat":
        handle_dev_chat_message(cid, message.text)
        return

    # ── Chat modes ─────────────────────────────────────────────────────────
    if mode == "chat":
        bot.send_chat_action(cid, "typing")
        threading.Thread(target=_handle_chat_message, args=(cid, message.text),
                         daemon=True, name=f"chat-{cid}").start()

    elif mode == "system":
        if _is_admin(cid):           # defense-in-depth: guard even at routing level
            bot.send_chat_action(cid, "typing")
            threading.Thread(target=_handle_system_message, args=(cid, message.text),
                             daemon=True, name=f"syschat-{cid}").start()
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
    bot.send_chat_action(cid, "typing")
    threading.Thread(target=_handle_voice_message, args=(cid, message.voice),
                     daemon=True, name=f"voice-{cid}").start()


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
    # ── Remote KB upload flow ─────────────────────────────────────────────────
    if _remote_kb.is_active(cid):
        if _is_admin(cid) or _is_advanced(cid):
            if _remote_kb.handle_document(cid, message.document, bot, _t):
                return
        else:
            _remote_kb.cancel(cid)
    _handle_doc_upload(message)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    from core.bot_db import _is_postgres as _postgres_mode
    if not _postgres_mode():
        from core.bot_db import init_db as _init_db
        _init_db()
    else:
        log.info("[DB] Postgres mode — skipping SQLite init_db()")
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

    # FasterWhisper preloading: disabled by default (CUDA libs inflate RSS to 1 GB+).
    # Re-enabled for the openclaw variant where the device is ROCm (AMD GPU), not CUDA,
    # so the RAM penalty is lower and cold-start latency (~4s) is unacceptable.
    # Override with FASTER_WHISPER_PRELOAD=0 in bot.env on low-memory machines.
    if DEVICE_VARIANT == "openclaw" and FASTER_WHISPER_PRELOAD and (
        STT_PROVIDER == "faster_whisper" or _st._voice_opts.get("faster_whisper_stt")
    ):
        log.info("[FasterWhisper] openclaw: preloading model in background thread")
        threading.Thread(target=_fw_preload, daemon=True).start()
    elif DEVICE_VARIANT == "openclaw" and not FASTER_WHISPER_PRELOAD:
        log.info("[FasterWhisper] preload disabled (FASTER_WHISPER_PRELOAD=0) — lazy load on first voice message")

    # Pre-warm embedding service so first RAG/chat call has no cold-start delay (~2s).
    if DEVICE_VARIANT == "openclaw":
        def _prewarm_embeddings():
            svc = EmbeddingService.get()
            if svc:
                log.info("[Embeddings] pre-warmed at startup: backend=%s", svc.backend)
            else:
                log.debug("[Embeddings] pre-warm skipped (no embedding backend)")
        threading.Thread(target=_prewarm_embeddings, daemon=True).start()

    # ── Startup tasks ─────────────────────────────────────────────────────
    _st.load_conversation_history()
    _cleanup_orphaned_tts()
    _notify_admins_new_version()
    configure_alert_handler(bot.send_message, ADMIN_USERS)
    attach_alerts_to_main_log()
    _cal_reschedule_all()
    threading.Thread(target=_cal_morning_briefing_loop, daemon=True).start()

    # ── Low-memory warning (Linux /proc/meminfo — no psutil required) ────────
    try:
        _meminfo = {}
        with open("/proc/meminfo") as _f:
            for _line in _f:
                _k, _, _v = _line.partition(":")
                _meminfo[_k.strip()] = int(_v.split()[0])  # kB
        _avail_mb  = _meminfo.get("MemAvailable", 0) // 1024
        _swap_tot  = _meminfo.get("SwapTotal", 1)
        _swap_used = _meminfo.get("SwapTotal", 0) - _meminfo.get("SwapFree", 0)
        _swap_pct  = (_swap_used / _swap_tot * 100) if _swap_tot else 0
        if _avail_mb < 512 or _swap_pct > 80:
            log.warning(
                "[Memory] LOW MEMORY at startup: available=%dMB  swap=%.0f%%"
                " — menu callbacks may be slow due to swap I/O."
                " Set FASTER_WHISPER_PRELOAD=0 in bot.env to free ~460 MB.",
                _avail_mb, _swap_pct,
            )
        else:
            log.info("[Memory] startup: available=%dMB  swap=%.0f%%", _avail_mb, _swap_pct)
    except Exception:
        pass  # non-Linux or /proc not available

    # Auto-load system KB docs (user guide + admin guide) in background
    def _ensure_system_docs() -> None:
        try:
            from setup.load_system_docs import _load_docs
            _load_docs(force=False)
        except Exception as exc:
            log.debug("[SystemDocs] auto-load skipped: %s", exc)
    threading.Thread(target=_ensure_system_docs, daemon=True).start()

    log.info("Polling Telegram…")

    # Graceful shutdown: stop polling before process exits so Telegram drops
    # the connection cleanly and the next start doesn't get a 409 Conflict.
    def _on_stop(signum, _frame):
        log.info(f"[Bot] signal {signum} — stopping polling…")
        bot.stop_polling()

    signal.signal(signal.SIGTERM, _on_stop)
    signal.signal(signal.SIGINT,  _on_stop)

    # timeout > long_polling_timeout: HTTP socket timeout must exceed Telegram hold time.
    # long_polling_timeout=20: Telegram holds the connection 20s → well within NAT router's
    #   typical 30-60s idle TCP timeout → prevents RemoteDisconnected errors.
    #   Previously 55s caused ~70 RemoteDisconnected/hour on SintAItion (NAT kills idle TCP).
    # timeout=25: fail fast on network loss (5s buffer over long_polling_timeout).
    # logger_level=DEBUG: suppress telebot's ERROR-level ReadTimeout traceback spam —
    #   reconnection is automatic; spamming ERROR fills journals on flaky connections.
    # Outer loop: guards against the rare case where infinity_polling itself raises.
    import logging as _logging
    while True:
        try:
            bot.infinity_polling(
                timeout=25, long_polling_timeout=20,
                interval=0, logger_level=_logging.DEBUG,
            )
            break  # clean shutdown via _on_stop
        except Exception as _poll_exc:
            log.warning("[Bot] polling crashed: %s — restarting in 5s", _poll_exc)
            import time as _t; _t.sleep(5)


if __name__ == "__main__":
    main()
