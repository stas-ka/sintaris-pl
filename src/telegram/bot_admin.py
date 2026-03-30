"""
bot_admin.py — Admin panel handlers.

Responsibilities:
  - Admin keyboard + entry point
  - Guest-user management (add / list / remove)
  - Registration approval / blocking
  - Voice-optimization toggle menu
  - Release notes — load, format, version-change admin notification
  - LLM model switcher (taris models + OpenAI ChatGPT sub-menu)
  - Unified user list: Telegram users + Web UI accounts
"""

import re as _re
import json
import threading
from pathlib import Path

import core.bot_state as _st
from core.bot_config import (
    ADMIN_USERS, ALLOWED_USERS,
    TARIS_CONFIG, ACTIVE_MODEL_FILE,
    RELEASE_NOTES_FILE, LAST_NOTIFIED_FILE, BOT_VERSION,
    LLM_LOCAL_FALLBACK, LLAMA_CPP_URL, LLAMA_CPP_MODEL, LLM_FALLBACK_FLAG_FILE,
    LLM_PROVIDER, LLM_FALLBACK_PROVIDER,
    OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL,
    OLLAMA_URL, OLLAMA_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
    STT_PROVIDER, STT_FALLBACK_PROVIDER, FASTER_WHISPER_MODEL, FASTER_WHISPER_DEVICE, FASTER_WHISPER_COMPUTE,
    PIPER_BIN, PIPER_MODEL, STT_LANG,
    _VOICE_OPTS_DEFAULTS, DEVICE_VARIANT,
    _LOG_FILE, _ASSISTANT_LOG_FILE, _SECURITY_LOG_FILE, _VOICE_LOG_FILE, _DATASTORE_LOG_FILE,
    CONVERSATION_HISTORY_MAX, CONV_SUMMARY_THRESHOLD, CONV_MID_MAX,
    log,
)
from core.bot_llm import get_per_func_provider, set_per_func_provider
from core.bot_logger import tail_log
from core.bot_instance import bot
from telegram.bot_access import (
    _t, _escape_md, _send_menu,
    _back_keyboard, _get_active_model,
)
from telegram.bot_users import (
    _get_pending_registrations, _find_registration, _upsert_registration,
    _set_reg_status, _load_registrations,
)
from features.bot_voice import _warm_piper_cache, _start_persistent_piper, _stop_persistent_piper

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ─────────────────────────────────────────────────────────────────────────────
# Shorthand helpers for mutable state
# ─────────────────────────────────────────────────────────────────────────────

def _voice_opts() -> dict:
    return _st._voice_opts


def _save_voice_opts() -> None:
    from core.bot_state import _save_voice_opts as _svop
    _svop()


def _dynamic_users() -> set:
    return _st._dynamic_users


def _save_dynamic_users() -> None:
    from core.bot_state import _save_dynamic_users as _sdyn
    _sdyn()


def _user_info_block(uid: int, reg) -> str:
    """Compact Markdown block with all available identity info for a Telegram user."""
    if not reg:
        return f"\U0001f464 `{uid}` _(no registration record)_"
    first   = _escape_md(reg.get("first_name", ""))
    last    = _escape_md(reg.get("last_name", ""))
    uname   = reg.get("username", "")
    name    = _escape_md(reg.get("name", ""))
    tg_full = f"{first} {last}".strip()
    udisp   = f"@{_escape_md(uname)}" if uname else "_no username_"
    tdisp   = f"{tg_full} ({udisp})" if tg_full else udisp
    return (
        f"\U0001f464 `{uid}`\n"
        f"  \u2022 Telegram: {tdisp}\n"
        f"  \u2022 Name: {name or '\u2014'}"
    )


def _web_account_block(account: dict, tg_ids_known: set) -> str:
    """Compact Markdown block for a web UI account."""
    uname    = _escape_md(account.get("username", ""))
    display  = _escape_md(account.get("display_name", ""))
    role     = account.get("role", "user")
    tg_id    = account.get("telegram_chat_id")
    created  = (account.get("created", "")[:10])
    role_icon = "🔐" if role == "admin" else "👤"
    tg_line   = f"`{tg_id}`" if tg_id else "_not linked_"
    linked_note = " _(also in Telegram list above)_" if tg_id and int(tg_id) in tg_ids_known else ""
    return (
        f"{role_icon} *{uname}* ({display})\n"
        f"  • Role: {role}  |  Created: {created}\n"
        f"  • Telegram: {tg_line}{linked_note}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Admin keyboard
# ─────────────────────────────────────────────────────────────────────────────

def _admin_keyboard(chat_id: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    pending_count = len(_get_pending_registrations())
    pending_badge = f"  ({pending_count} new)" if pending_count else ""
    kb.add(
        InlineKeyboardButton(_t(chat_id, "admin_btn_pending", pending_badge=pending_badge),
                             callback_data="admin_pending_users"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_add_user"),   callback_data="admin_add_user"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_list_users"), callback_data="admin_list_users"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_remove_user"), callback_data="admin_remove_user"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_switch_llm"), callback_data="admin_llm_menu"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_voice_opts"), callback_data="voice_opts_menu"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_voice_config"), callback_data="admin_voice_config"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_release_notes"), callback_data="admin_changelog"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_logs"),       callback_data="admin_logs_menu"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_rag"),         callback_data="admin_rag_menu"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_system"),      callback_data="mode_system"),
        InlineKeyboardButton(_t(chat_id, "admin_btn_reload_screens"), callback_data="reload_screens"),
        InlineKeyboardButton(_t(chat_id, "btn_back"),             callback_data="menu"),
    )
    return kb


def _handle_admin_menu(chat_id: int) -> None:
    bot.send_message(
        chat_id,
        _t(chat_id, "admin_panel_title"),
        parse_mode="Markdown",
        reply_markup=_admin_keyboard(chat_id),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Guest-user management
# ─────────────────────────────────────────────────────────────────────────────

def _handle_admin_list_users(chat_id: int) -> None:
    """Show all users: Telegram users + Web UI accounts (unified view)."""
    sections = []

    # Track all Telegram IDs that appear in any section (for cross-reference)
    all_tg_ids: set = set(ADMIN_USERS) | set(ALLOWED_USERS) | set(_dynamic_users())

    # 🔐 Admins (static from config)
    if ADMIN_USERS:
        blocks = [_user_info_block(uid, _find_registration(uid)) for uid in sorted(ADMIN_USERS)]
        sections.append("🔐 *Telegram Admins:*\n\n" + "\n\n".join(blocks))

    # ✅ Static allowed users (not admins)
    static_only = sorted(uid for uid in ALLOWED_USERS if uid not in ADMIN_USERS)
    if static_only:
        blocks = [_user_info_block(uid, _find_registration(uid)) for uid in static_only]
        sections.append("✅ *Telegram Allowed:*\n\n" + "\n\n".join(blocks))

    # 👤 Dynamically approved users (not already in static lists)
    dyn_only = sorted(uid for uid in _dynamic_users()
                      if uid not in ALLOWED_USERS and uid not in ADMIN_USERS)
    if dyn_only:
        blocks = [_user_info_block(uid, _find_registration(uid)) for uid in dyn_only]
        sections.append("👤 *Telegram Approved:*\n\n" + "\n\n".join(blocks))

    # 🚫 Blocked users
    blocked = [r for r in _load_registrations() if r.get("status") == "blocked"]
    if blocked:
        blk_blocks = [_user_info_block(r.get("chat_id"), r) for r in blocked]
        sections.append("🚫 *Telegram Blocked:*\n\n" + "\n\n".join(blk_blocks))

    # 🌐 Web UI accounts (from accounts.json)
    try:
        from security.bot_auth import list_accounts as _list_web_accounts
        web_accounts = _list_web_accounts()
        if web_accounts:
            web_blocks = [_web_account_block(a, all_tg_ids) for a in
                          sorted(web_accounts, key=lambda a: (a.get("role","user") != "admin", a.get("username","")))]
            sections.append("🌐 *Web UI Accounts:*\n\n" + "\n\n".join(web_blocks))
    except Exception as exc:
        sections.append(f"🌐 *Web UI Accounts:* _(error loading: {exc})_")

    if not sections:
        bot.send_message(chat_id, _t(chat_id, "no_guests"),
                         parse_mode="Markdown", reply_markup=_admin_keyboard(chat_id))
        return

    # Split into multiple messages if too long (Telegram 4096 char limit)
    full_text = "\n\n" + "\n\n───────\n\n".join(sections)
    if len(full_text) <= 4000:
        bot.send_message(chat_id, full_text, parse_mode="Markdown",
                         reply_markup=_admin_keyboard(chat_id))
    else:
        for i, section in enumerate(sections):
            kb = _admin_keyboard(chat_id) if i == len(sections) - 1 else None
            bot.send_message(chat_id, "\n\n" + section, parse_mode="Markdown",
                             reply_markup=kb)


def _start_admin_add_user(chat_id: int) -> None:
    _st._user_mode[chat_id] = "admin_add_user"
    bot.send_message(chat_id, _t(chat_id, "add_prompt"), parse_mode="Markdown")


def _finish_admin_add_user(admin_id: int, text: str) -> None:
    text = text.strip()
    if not text.lstrip("-").isdigit():
        bot.send_message(admin_id, _t(admin_id, "bad_id"), parse_mode="Markdown")
        return
    uid = int(text)
    dyn = _dynamic_users()
    if uid in dyn:
        bot.send_message(admin_id, _t(admin_id, "already_guest", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard(admin_id))
    elif uid in ALLOWED_USERS or uid in ADMIN_USERS:
        bot.send_message(admin_id, _t(admin_id, "already_full", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard(admin_id))
    else:
        dyn.add(uid)
        _save_dynamic_users()
        log.info(f"Admin {admin_id} added user {uid}")
        bot.send_message(admin_id, _t(admin_id, "user_added", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard(admin_id))
    _st._user_mode.pop(admin_id, None)


def _start_admin_remove_user(chat_id: int) -> None:
    dyn = _dynamic_users()
    if not dyn:
        bot.send_message(chat_id, _t(chat_id, "no_guests_del"),
                         parse_mode="Markdown", reply_markup=_admin_keyboard(chat_id))
        return
    _st._user_mode[chat_id] = "admin_remove_user"
    lst = "\n\n".join(_user_info_block(uid, _find_registration(uid)) for uid in sorted(dyn))
    bot.send_message(chat_id, _t(chat_id, "remove_prompt", lst=lst), parse_mode="Markdown")


def _finish_admin_remove_user(admin_id: int, text: str) -> None:
    text = text.strip()
    if not text.lstrip("-").isdigit():
        bot.send_message(admin_id, _t(admin_id, "bad_id_rem"), parse_mode="Markdown")
        return
    uid = int(text)
    dyn = _dynamic_users()
    if uid in dyn:
        dyn.discard(uid)
        _save_dynamic_users()
        log.info(f"Admin {admin_id} removed guest user {uid}")
        bot.send_message(admin_id, _t(admin_id, "user_removed", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard(admin_id))
    else:
        bot.send_message(admin_id, _t(admin_id, "user_not_found", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard(admin_id))
    _st._user_mode.pop(admin_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# Registration — admin: pending list, approve, block; user: new-reg notification
# ─────────────────────────────────────────────────────────────────────────────

def _handle_admin_pending_users(chat_id: int) -> None:
    """Show all pending registration requests with approve/block buttons."""
    pending = _get_pending_registrations()
    if not pending:
        bot.send_message(chat_id, _t(chat_id, "no_pending_regs"),
                         reply_markup=_admin_keyboard(chat_id))
        return
    for reg in pending:
        uid      = reg.get("chat_id")
        uname    = reg.get("username", "")
        first    = reg.get("first_name", "")
        last     = reg.get("last_name", "")
        name     = reg.get("name", "")
        ts       = reg.get("timestamp", "")[:16].replace("T", " ")
        tg_full  = f"{first} {last}".strip()
        uesc     = f"@{_escape_md(uname)}" if uname else "_no username_"
        tdisp    = f"{_escape_md(tg_full)} ({uesc})" if tg_full else uesc
        name_esc = _escape_md(name) if name else "_(not set)_"
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("\u2705  Approve", callback_data=f"reg_approve:{uid}"),
            InlineKeyboardButton("\U0001f6ab  Block",   callback_data=f"reg_block:{uid}"),
        )
        text = (
            f"\U0001f464 *Pending registration*\n\n"
            f"ID: `{uid}`\n"
            f"Telegram: {tdisp}\n"
            f"Name entered: {name_esc}\n"
            f"Requested: {ts}"
        )
        try:
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            log.warning(f"[Reg] pending_users send failed: {e}")
            bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _do_approve_registration(admin_id: int, target_id: int) -> None:
    """Approve a pending registration: add to guests and notify user."""
    from telegram.bot_access import _menu_keyboard
    reg = _find_registration(target_id)
    if not reg:
        bot.send_message(admin_id, f"ℹ️ Registration for `{target_id}` not found.",
                         parse_mode="Markdown", reply_markup=_admin_keyboard(admin_id))
        return
    if reg.get("status") == "approved":
        bot.send_message(admin_id, f"ℹ️ User `{target_id}` is already approved.",
                         parse_mode="Markdown", reply_markup=_admin_keyboard(admin_id))
        return
    _set_reg_status(target_id, "approved")
    _dynamic_users().add(target_id)
    _save_dynamic_users()
    name_disp = f" \u2014 {reg.get('name')}" if reg.get("name") else ""
    log.info(f"[Reg] Admin {admin_id} approved user {target_id}")
    bot.send_message(admin_id, f"✅ User `{target_id}`{name_disp} approved and added.",
                     parse_mode="Markdown", reply_markup=_admin_keyboard(admin_id))
    try:
        bot.send_message(target_id, _t(target_id, "reg_approved"),
                         parse_mode="Markdown",
                         reply_markup=_menu_keyboard(target_id))
    except Exception as e:
        log.warning(f"[Reg] Cannot notify approved user {target_id}: {e}")


def _do_block_registration(admin_id: int, target_id: int) -> None:
    """Block a registration: mark blocked and notify user."""
    reg       = _find_registration(target_id)
    name_disp = f" \u2014 {reg.get('name')}" if reg and reg.get("name") else ""
    _set_reg_status(target_id, "blocked")
    _dynamic_users().discard(target_id)
    _save_dynamic_users()
    log.info(f"[Reg] Admin {admin_id} blocked user {target_id}")
    bot.send_message(admin_id, f"\U0001f6ab User `{target_id}`{name_disp} blocked.",
                     parse_mode="Markdown", reply_markup=_admin_keyboard(admin_id))
    try:
        bot.send_message(target_id, _t(target_id, "reg_declined"))
    except Exception as e:
        log.warning(f"[Reg] Cannot notify blocked user {target_id}: {e}")


def _notify_admins_new_registration(chat_id: int, username: str, name: str,
                                    first_name: str = "", last_name: str = "") -> None:
    """Send approve/block buttons to all admins when a new user registers."""
    tg_full    = f"{first_name} {last_name}".strip()
    udisp      = f"@{_escape_md(username)}" if username else "_no username_"
    tdisp      = f"{_escape_md(tg_full)} ({udisp})" if tg_full else udisp
    for admin_id in ADMIN_USERS:
        try:
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton("✅  Approve", callback_data=f"reg_approve:{chat_id}"),
                InlineKeyboardButton("🚫  Block",   callback_data=f"reg_block:{chat_id}"),
            )
            bot.send_message(
                admin_id,
                f"👤 *New registration request*\n\n"
                f"ID: `{chat_id}`\n"
                f"Telegram: {tdisp}\n"
                f"Name entered: {_escape_md(name) or '_(not set)_'}",
                parse_mode="Markdown",
                reply_markup=kb,
            )
            log.info(f"[Reg] Notified admin {admin_id} of registration from {chat_id}")
        except Exception as e:
            log.warning(f"[Reg] Notify admin {admin_id} failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Voice-optimization toggle menu
# ─────────────────────────────────────────────────────────────────────────────

def _handle_voice_opts_menu(chat_id: int) -> None:
    """Show voice optimization toggle panel for admins."""
    opts = _voice_opts()
    is_openclaw = DEVICE_VARIANT == "openclaw"

    def _flag(key: str) -> str:
        return "✅" if opts.get(key) else "◻️"

    kb = InlineKeyboardMarkup(row_width=1)

    # Common opts — available on all variants
    common_rows = [
        ("silence_strip",     f"{_flag('silence_strip')}  Silence strip  ·  −6s STT"),
        ("low_sample_rate",   f"{_flag('low_sample_rate')}  8 kHz sample rate  ·  −7s STT"),
        ("warm_piper",        f"{_flag('warm_piper')}  Warm Piper cache  ·  −15s TTS"),
        ("parallel_tts",      f"{_flag('parallel_tts')}  Parallel TTS thread  ·  text-first UX"),
        ("user_audio_toggle", f"{_flag('user_audio_toggle')}  Per-user audio 🔊/🔇 toggle"),
        ("vad_prefilter",     f"{_flag('vad_prefilter')}  VAD pre-filter (webrtcvad)  ·  −3s STT"),
        ("voice_timing_debug",f"{_flag('voice_timing_debug')}  Timing debug  ·  show ⏱ per stage in replies"),
    ]

    # OpenClaw-specific opts
    openclaw_rows = [
        ("faster_whisper_stt", f"{_flag('faster_whisper_stt')}  faster-whisper STT  ·  CTranslate2 (recommended)"),
    ]

    # PicoClaw/Pi-only opts — hidden on OpenClaw (packages not installed)
    picoclaw_rows = [
        ("tmpfs_model",       f"{_flag('tmpfs_model')}  Piper model in RAM (/dev/shm)  ·  −10s TTS load"),
        ("whisper_stt",       f"{_flag('whisper_stt')}  Whisper STT (whisper.cpp)  ·  +accuracy"),
        ("vosk_fallback",     f"{_flag('vosk_fallback')}  Vosk Fallback  ·  OFF = −180 MB RAM (Whisper-only)"),
        ("piper_low_model",   f"{_flag('piper_low_model')}  Piper low model  ·  −13s TTS"),
        ("persistent_piper",  f"{_flag('persistent_piper')}  Persistent Piper process  ·  ONNX hot"),
    ]

    opts_rows = common_rows[:]
    if is_openclaw:
        opts_rows += openclaw_rows
    else:
        opts_rows += picoclaw_rows

    for key, label in opts_rows:
        kb.add(InlineKeyboardButton(label, callback_data=f"voice_opt_toggle:{key}"))
    kb.add(InlineKeyboardButton("🔙  Admin", callback_data="admin_menu"))

    active  = [k for k, v in opts.items() if v]
    status  = ("Active: " + ", ".join(active)) if active else "All OFF — stable defaults"
    status_esc = _escape_md(status)

    # ── Current runtime config summary ──────────────────────────────────────
    # STT line
    fw_info = f" ({FASTER_WHISPER_MODEL}/{FASTER_WHISPER_DEVICE})" if "faster_whisper" in STT_PROVIDER else ""
    stt_fallback = f" → {STT_FALLBACK_PROVIDER}" if STT_FALLBACK_PROVIDER else ""
    stt_line = f"STT: {STT_PROVIDER}{fw_info}{stt_fallback}  ·  lang={STT_LANG}"

    # TTS line
    piper_ok = PIPER_BIN and Path(PIPER_BIN).exists()
    model_name = Path(PIPER_MODEL).stem if PIPER_MODEL else "?"
    tts_line = f"TTS: {'Piper' if piper_ok else 'Piper ⚠️ missing'} ({model_name})"

    # Voice LLM line
    voice_llm = get_per_func_provider("voice") or LLM_PROVIDER
    voice_llm_line = f"LLM (voice): {voice_llm}"

    config_block = "\n".join([stt_line, tts_line, voice_llm_line])

    text = (
        "⚡ *Voice Pipeline*\n\n"
        f"```\n{config_block}\n```\n\n"
        "*Optimisation toggles* (tap to switch):\n"
        f"_{status_esc}_"
    )
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        log.warning(f"[VoiceOpts] Markdown failed: {e}")
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_voice_opt_toggle(chat_id: int, key: str) -> None:
    """Toggle one voice optimization flag and refresh the menu."""
    if key not in _VOICE_OPTS_DEFAULTS:
        return
    opts = _voice_opts()
    opts[key] = not opts.get(key, False)
    _save_voice_opts()
    state = "ON ✅" if opts[key] else "OFF ◻️"
    log.info(f"[VoiceOpts] {key} → {state} (by admin {chat_id})")

    if key == "warm_piper" and opts[key]:
        threading.Thread(target=_warm_piper_cache, daemon=True).start()
        bot.send_message(chat_id, "⚡ _Warming Piper cache in background…_",
                         parse_mode="Markdown")
    if key == "persistent_piper":
        if opts[key]:
            threading.Thread(target=_start_persistent_piper, daemon=True).start()
            bot.send_message(chat_id, "⚡ _Starting persistent Piper process…_",
                             parse_mode="Markdown")
        else:
            threading.Thread(target=_stop_persistent_piper, daemon=True).start()

    _handle_voice_opts_menu(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
# Admin Voice Config (STT/TTS model info + STT switching)
# ─────────────────────────────────────────────────────────────────────────────

def _handle_admin_voice_config(chat_id: int) -> None:
    """Show current STT/TTS configuration and allow switching STT provider + FW model."""
    opts = _voice_opts()
    # Determine active STT
    if opts.get("faster_whisper_stt"):
        active_stt = "faster_whisper"
    else:
        active_stt = STT_PROVIDER  # from env / bot.env

    # FW model from env (runtime override stored in voice_opts stt_model key)
    fw_model = opts.get("fw_model_override") or FASTER_WHISPER_MODEL
    fw_device = FASTER_WHISPER_DEVICE
    fw_compute = FASTER_WHISPER_COMPUTE

    # Piper model (basename)
    piper_model_name = str(PIPER_MODEL).split("/")[-1] if PIPER_MODEL else "—"

    text = (
        "🎙️ *Voice Configuration*\n\n"
        f"*STT Provider:* `{active_stt}`\n"
        f"*Vosk (hotword):* {'enabled' if DEVICE_VARIANT == 'taris' or not opts.get('faster_whisper_stt') else 'hotword only'}\n"
        f"*Faster-Whisper model:* `{fw_model}` ({fw_device}/{fw_compute})\n\n"
        f"*TTS (Piper) model:* `{piper_model_name}`\n\n"
        "_Switch STT provider (takes effect immediately):_"
    )

    kb = InlineKeyboardMarkup(row_width=1)

    # STT switch buttons
    vosk_active   = not opts.get("faster_whisper_stt")
    fw_active     = bool(opts.get("faster_whisper_stt"))
    kb.add(InlineKeyboardButton(
        f"{'✅' if vosk_active else '◻️'} Vosk (default, offline)",
        callback_data="admin_stt_set:vosk",
    ))
    if DEVICE_VARIANT == "openclaw":
        kb.add(InlineKeyboardButton(
            f"{'✅' if fw_active else '◻️'} Faster-Whisper",
            callback_data="admin_stt_set:faster_whisper",
        ))
        # FW model selection
        kb.add(InlineKeyboardButton("─ Faster-Whisper model ─", callback_data="noop"))
        for model_name in ["tiny", "base", "small", "medium"]:
            icon = "✅" if fw_model == model_name else "◻️"
            kb.add(InlineKeyboardButton(f"{icon} {model_name}", callback_data=f"admin_fw_model:{model_name}"))

    kb.add(InlineKeyboardButton("🔙  Admin", callback_data="admin_menu"))

    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        log.warning(f"[VoiceCfg] send failed: {e}")
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_admin_stt_set(chat_id: int, provider: str) -> None:
    """Switch STT provider at runtime via voice_opts."""
    opts = _voice_opts()
    if provider == "faster_whisper":
        opts["faster_whisper_stt"] = True
        msg = "✅ STT switched to *Faster-Whisper*."
    else:
        opts["faster_whisper_stt"] = False
        msg = "✅ STT switched to *Vosk*."
    _save_voice_opts()
    log.info(f"[VoiceCfg] admin {chat_id} switched STT → {provider}")
    try:
        bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=_admin_keyboard(chat_id))
    except Exception:
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", msg), reply_markup=_admin_keyboard(chat_id))


def _handle_admin_fw_model_set(chat_id: int, model_name: str) -> None:
    """Store FW model override in voice_opts and confirm."""
    opts = _voice_opts()
    opts["fw_model_override"] = model_name
    _save_voice_opts()
    log.info(f"[VoiceCfg] admin {chat_id} set FW model → {model_name}")
    msg = (
        f"✅ Faster-Whisper model set to *{model_name}*.\n\n"
        "_Note: restart voice service to apply model change (`systemctl --user restart taris-voice`)._"
    )
    try:
        bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=_admin_keyboard(chat_id))
    except Exception:
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", msg), reply_markup=_admin_keyboard(chat_id))
# ─────────────────────────────────────────────────────────────────────────────

def _load_release_notes() -> list[dict]:
    """Load release_notes.json; returns [] on any error."""
    try:
        return json.loads(Path(RELEASE_NOTES_FILE).read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"[ReleaseNotes] cannot load {RELEASE_NOTES_FILE}: {e}")
        return []


def _format_release_entry(entry: dict, header: bool = True) -> str:
    """Format one release-notes entry as Telegram Markdown."""
    v   = entry.get("version", "?")
    d   = entry.get("date", "")
    t   = _escape_md(entry.get("title", ""))
    n   = _escape_md(entry.get("notes", ""))
    hdr = f"📦 *v{v}*" + (f"  _({d})_" if d else "") + (f" — {t}" if t else "")
    return (hdr + "\n\n" + n) if header else n


def _get_changelog_text(max_entries: int = 5) -> str:
    """Return formatted changelog Markdown (last max_entries entries, truncated to 3500 chars)."""
    entries = _load_release_notes()
    if not entries:
        return "📝 _Release notes not available._"
    if max_entries:
        entries = entries[:max_entries]
    sep = "\n\n" + "─" * 20 + "\n\n"
    result = ""
    for e in entries:
        part = _format_release_entry(e)
        candidate = (result + sep + part) if result else part
        if len(candidate) > 3500:
            break
        result = candidate
    return result or _format_release_entry(entries[0])


def _notify_admins_new_version() -> None:
    """On startup, notify admins once per BOT_VERSION with release notes."""
    try:
        last = Path(LAST_NOTIFIED_FILE).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        last = ""
    except Exception as e:
        log.warning(f"[ReleaseNotes] read last-notified: {e}")
        last = ""

    if last == BOT_VERSION:
        return

    entries = _load_release_notes()
    entry = next((e for e in entries if e.get("version") == BOT_VERSION), None)
    body  = _format_release_entry(entry) if entry else f"📦 *v{BOT_VERSION}* deployed."
    msg   = f"🚀 *New version deployed: v{BOT_VERSION}*\n\n{body}"

    for admin_id in ADMIN_USERS:
        try:
            bot.send_message(admin_id, msg, parse_mode="Markdown",
                             reply_markup=_admin_keyboard(admin_id))
            log.info(f"[ReleaseNotes] notified admin {admin_id} (v{BOT_VERSION})")
        except Exception as e:
            log.warning(f"[ReleaseNotes] Markdown failed for admin {admin_id}: {e} — retrying plain")
            try:
                bot.send_message(admin_id, _re.sub(r"[*_`]", "", msg),
                                 reply_markup=_admin_keyboard(admin_id))
                log.info(f"[ReleaseNotes] notified admin {admin_id} (v{BOT_VERSION}, plain)")
            except Exception as e2:
                log.warning(f"[ReleaseNotes] notify admin {admin_id} failed: {e2}")

    try:
        Path(LAST_NOTIFIED_FILE).write_text(BOT_VERSION, encoding="utf-8")
    except Exception as e:
        log.warning(f"[ReleaseNotes] save last-notified: {e}")


def _handle_admin_changelog(chat_id: int) -> None:
    """Show the full changelog in the admin panel."""
    text = f"📝 *Release Notes*  (current: v{BOT_VERSION})\n" + _get_changelog_text()
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown",
                         reply_markup=_admin_keyboard(chat_id))
    except Exception as e:
        log.warning(f"[Changelog] Markdown failed for {chat_id}: {e} — retrying plain")
        try:
            bot.send_message(chat_id, _re.sub(r"[*_`]", "", text),
                             reply_markup=_admin_keyboard(chat_id))
        except Exception as e2:
            log.error(f"[Changelog] send failed for {chat_id}: {e2}")


# ─────────────────────────────────────────────────────────────────────────────
# Log viewer
# ─────────────────────────────────────────────────────────────────────────────

_LOG_CATEGORIES = [
    ("main",      "📄  Main log",      _LOG_FILE),
    ("assistant", "🤖  Assistant",     _ASSISTANT_LOG_FILE),
    ("security",  "🔐  Security",      _SECURITY_LOG_FILE),
    ("voice",     "🎙  Voice",         _VOICE_LOG_FILE),
    ("datastore", "🗄  Datastore",     _DATASTORE_LOG_FILE),
]


def _handle_admin_logs_menu(chat_id: int) -> None:
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=1)
    for key, label, _ in _LOG_CATEGORIES:
        kb.add(InlineKeyboardButton(label, callback_data=f"admin_logs_show:{key}"))
    kb.add(InlineKeyboardButton("🔙  Admin", callback_data="admin_menu"))
    bot.send_message(chat_id, _t(chat_id, "admin_logs_title"), reply_markup=kb)


def _handle_admin_logs_show(chat_id: int, category: str) -> None:
    path = next((p for k, _, p in _LOG_CATEGORIES if k == category), None)
    if path is None:
        bot.send_message(chat_id, "Unknown log category.", reply_markup=_admin_keyboard(chat_id))
        return
    lines = tail_log(path, n=50)
    header = _t(chat_id, "admin_logs_header", n=50, cat=category)
    text = f"{header}\n\n```\n{lines or _t(chat_id, 'admin_logs_empty')}\n```"
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=_admin_keyboard(chat_id))
    except Exception:
        bot.send_message(chat_id, f"{header}\n\n{lines or _t(chat_id, 'admin_logs_empty')}",
                         reply_markup=_admin_keyboard(chat_id))


# ─────────────────────────────────────────────────────────────────────────────
# LLM model switcher
# ─────────────────────────────────────────────────────────────────────────────

def _set_active_model(model_name: str) -> None:
    """Persist the chosen model name (empty = reset to config default)."""
    try:
        Path(ACTIVE_MODEL_FILE).write_text(model_name, encoding="utf-8")
        log.info(f"[LLM] Active model set to: '{model_name or '(config default)'}'")
    except Exception as e:
        log.error(f"[LLM] Failed to write {ACTIVE_MODEL_FILE}: {e}")


def _get_taris_models() -> list[dict]:
    """Read model_list from taris config.json."""
    try:
        cfg = json.loads(Path(TARIS_CONFIG).read_text(encoding="utf-8"))
        return cfg.get("model_list", [])
    except Exception as e:
        log.warning(f"[LLM] Cannot read taris config: {e}")
        return []


def _handle_admin_llm_menu(chat_id: int) -> None:
    """Rich LLM settings panel: current status + global provider switch + per-function overrides."""
    global_p  = LLM_PROVIDER.lower()
    fallback_p = LLM_FALLBACK_PROVIDER.lower() if LLM_FALLBACK_PROVIDER else "—"
    _MODEL_LABELS = {
        "openai":    f"openai ({OPENAI_MODEL})",
        "ollama":    f"ollama ({OLLAMA_MODEL})",
        "gemini":    f"gemini ({GEMINI_MODEL})",
        "anthropic": f"anthropic ({ANTHROPIC_MODEL})",
        "taris":     "taris",
        "openclaw":  "openclaw",
    }
    global_label   = _MODEL_LABELS.get(global_p, global_p)
    fallback_label = _MODEL_LABELS.get(fallback_p, fallback_p)
    system_p = get_per_func_provider("system")
    chat_p   = get_per_func_provider("chat")
    system_label = _MODEL_LABELS.get(system_p, system_p) if system_p else f"(global: {global_p})"
    chat_label   = _MODEL_LABELS.get(chat_p, chat_p) if chat_p else f"(global: {global_p})"

    text = (
        "🤖 *LLM Settings*\n\n"
        f"*Global provider:* `{global_label}`\n"
        f"*Fallback:* `{fallback_label}`\n\n"
        "*Per-function overrides:*\n"
        f"  💬 System chat: `{system_label}`\n"
        f"  🗨️ User chat:    `{chat_label}`\n\n"
        "_Tap a provider to switch globally, or set per-function below._"
    )

    _KEY_OK = {
        "openai":    bool(OPENAI_API_KEY),
        "ollama":    True,
        "gemini":    bool(GEMINI_API_KEY),
        "anthropic": bool(ANTHROPIC_API_KEY),
        "taris":     True,
        "openclaw":  DEVICE_VARIANT == "openclaw",
    }
    _PROVIDER_NAMES = ["openai", "ollama", "gemini", "anthropic"]
    if DEVICE_VARIANT != "openclaw":
        _PROVIDER_NAMES.append("taris")

    kb = InlineKeyboardMarkup(row_width=2)
    for p in _PROVIDER_NAMES:
        icon   = "✅" if p == global_p else "◻️"
        warn   = "" if _KEY_OK.get(p, False) else " ⚠️"
        kb.add(InlineKeyboardButton(f"{icon} {p}{warn}", callback_data=f"admin_llm_set:global:{p}"))

    kb.add(InlineKeyboardButton("─ Per-Function ─", callback_data="noop"))
    kb.add(InlineKeyboardButton(
        f"💬 System chat: {system_p or global_p} ▶",
        callback_data="admin_llm_for:system",
    ))
    kb.add(InlineKeyboardButton(
        f"🗨️ User chat: {chat_p or global_p} ▶",
        callback_data="admin_llm_for:chat",
    ))

    kb.add(InlineKeyboardButton("🔵 OpenAI ChatGPT (key + models) ▶", callback_data="openai_llm_menu"))
    kb.add(InlineKeyboardButton("🔁  Fallback config ▶", callback_data="admin_llm_fallback_menu"))
    kb.add(InlineKeyboardButton("🔍  Context Trace ▶", callback_data="admin_llm_trace"))
    kb.add(InlineKeyboardButton("🧠  Memory Settings ▶", callback_data="admin_memory_menu"))
    kb.add(InlineKeyboardButton("🔙  Admin", callback_data="admin_menu"))

    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        log.warning(f"[LLM] llm_menu send failed: {e}")
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_admin_llm_per_func(chat_id: int, use_case: str) -> None:
    """Show provider picker for a specific function (system/chat)."""
    global_p  = LLM_PROVIDER.lower()
    current_p = get_per_func_provider(use_case) or global_p
    _KEY_OK = {
        "openai":    bool(OPENAI_API_KEY),
        "ollama":    True,
        "gemini":    bool(GEMINI_API_KEY),
        "anthropic": bool(ANTHROPIC_API_KEY),
        "taris":     True,
        "openclaw":  DEVICE_VARIANT == "openclaw",
    }
    labels = {"system": "System Chat", "chat": "User Chat"}
    title = labels.get(use_case, use_case)
    text = (
        f"🤖 *LLM for {title}*\n\n"
        f"Current: `{current_p}`\n"
        f"Global default: `{global_p}`\n\n"
        "_Select a provider or reset to use the global default._"
    )
    kb = InlineKeyboardMarkup(row_width=1)
    providers = ["openai", "ollama", "gemini", "anthropic"]
    if DEVICE_VARIANT != "openclaw":
        providers.append("taris")
    for p in providers:
        icon = "✅" if p == current_p else "◻️"
        warn = "" if _KEY_OK.get(p, True) else " ⚠️"
        kb.add(InlineKeyboardButton(f"{icon} {p}{warn}", callback_data=f"admin_llm_set:{use_case}:{p}"))
    kb.add(InlineKeyboardButton("↩️  Use global default", callback_data=f"admin_llm_set:{use_case}:"))
    kb.add(InlineKeyboardButton("🔙  LLM Settings", callback_data="admin_llm_menu"))
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_admin_llm_set(chat_id: int, use_case: str, provider: str) -> None:
    """Apply LLM provider selection (global or per-function) and confirm."""
    if use_case == "global":
        set_per_func_provider("system", provider)
        set_per_func_provider("chat", provider)
        msg = (
            f"✅ Global LLM switched to `{provider}`.\n\n"
            f"System chat and user chat now use `{provider}`.\n"
            f"_Note: to persist after restart, set `LLM_PROVIDER={provider}` in `~/.taris/bot.env`._"
        )
    elif provider:
        set_per_func_provider(use_case, provider)
        labels = {"system": "System Chat", "chat": "User Chat"}
        func_name = labels.get(use_case, use_case)
        msg = f"✅ {func_name} LLM set to `{provider}`."
    else:
        set_per_func_provider(use_case, "")
        labels = {"system": "System Chat", "chat": "User Chat"}
        func_name = labels.get(use_case, use_case)
        msg = f"↩️ {func_name} LLM reset to global default (`{LLM_PROVIDER}`)."

    log.info(f"[LLM] admin {chat_id} set {use_case} → '{provider or 'global'}'")
    try:
        bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=_admin_keyboard(chat_id))
    except Exception as e:
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", msg), reply_markup=_admin_keyboard(chat_id))
def _handle_set_llm(chat_id: int, model_name: str) -> None:
    """Apply LLM model selection and confirm to user."""
    _set_active_model(model_name)
    if model_name:
        models_map = {m["model_name"]: m for m in _get_taris_models() if m.get("model_name")}
        m       = models_map.get(model_name, {})
        has_key = bool(m.get("api_key", "").strip())
        warn    = ("" if has_key else
                   "\n\n⚠️ No API key set for this model — go to OpenAI ChatGPT menu to add one.")
        msg = f"✅ LLM switched to: {model_name}{warn}\n\nAll subsequent chat, system, and voice requests will use this model."
    else:
        msg = "↩️ LLM reset to config default (openrouter-auto)."
    try:
        bot.send_message(chat_id, msg, reply_markup=_admin_keyboard(chat_id))
    except Exception as e:
        log.warning(f"[LLM] set_llm send failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI ChatGPT sub-menu
# ─────────────────────────────────────────────────────────────────────────────

_OPENAI_CATALOG = [
    ("gpt-4.1",         "openai/gpt-4.1",         "GPT-4.1 (flagship 2025)"),
    ("gpt-4.1-mini",    "openai/gpt-4.1-mini",     "GPT-4.1 mini (fast)"),
    ("gpt-4.1-nano",    "openai/gpt-4.1-nano",     "GPT-4.1 nano (fastest)"),
    ("gpt-4o",          "openai/gpt-4o",           "GPT-4o (multimodal)"),
    ("gpt-4o-mini",     "openai/gpt-4o-mini",      "GPT-4o mini (cheap)"),
    ("o4-mini",         "openai/o4-mini",           "o4-mini (fast reasoning)"),
    ("o3",              "openai/o3",                "o3 (advanced reasoning)"),
    ("o3-mini",         "openai/o3-mini",           "o3-mini (reasoning, light)"),
]
_OPENAI_API_BASE = "https://api.openai.com/v1"


def _get_shared_openai_key() -> str:
    """Return the first OpenAI api_key found in config.json, or ''."""
    for m in _get_taris_models():
        if "openai.com" in m.get("api_base", "") and m.get("api_key", "").strip():
            return m["api_key"].strip()
    return ""


def _save_openai_apikey(api_key: str) -> bool:
    """Set api_key for all openai.com models; add catalog entries if missing."""
    try:
        p   = Path(TARIS_CONFIG)
        cfg = json.loads(p.read_text(encoding="utf-8"))
        model_names = {m["model_name"] for m in cfg.get("model_list", []) if m.get("model_name")}
        for m in cfg.get("model_list", []):
            if "openai.com" in m.get("api_base", ""):
                m["api_key"] = api_key
        for name, model_id, _ in _OPENAI_CATALOG:
            if name not in model_names:
                cfg["model_list"].append({
                    "model_name": name,
                    "model":      model_id,
                    "api_base":   _OPENAI_API_BASE,
                    "api_key":    api_key,
                })
        p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("[LLM] OpenAI key saved to config.json")
        return True
    except Exception as e:
        log.error(f"[LLM] Failed to save OpenAI key: {e}")
        return False


def _handle_openai_llm_menu(chat_id: int) -> None:
    """Show OpenAI model selection keyboard with key status."""
    models     = {m["model_name"]: m for m in _get_taris_models() if m.get("model_name")}
    shared_key = _get_shared_openai_key()
    current    = _get_active_model()

    kb = InlineKeyboardMarkup(row_width=1)
    for name, model_id, description in _OPENAI_CATALOG:
        m          = models.get(name, {})
        has_key    = bool(m.get("api_key", "").strip()) or bool(shared_key)
        is_current = current in (name, model_id)
        prefix     = "✅" if is_current else ("✔️" if has_key else "⚠️")
        kb.add(InlineKeyboardButton(f"{prefix} {name} — {description}",
                                    callback_data=f"llm_select:{model_id}"))

    key_label = (f"🔑 Update OpenAI Key (…{shared_key[-4:]})" if shared_key
                 else "🔑 Set OpenAI API Key")
    kb.add(InlineKeyboardButton(key_label, callback_data="llm_setkey_openai"))
    kb.add(InlineKeyboardButton("🔙  LLM Menu", callback_data="admin_llm_menu"))

    status_line = (f"🔑 Key: ...{shared_key[-4:]} configured" if shared_key
                   else "🔑 Key: not set — tap below to add")
    text = (
        "🔵 *OpenAI ChatGPT Models*\n\n"
        f"{status_line}\n\n"
        "✅ active   ✔️ key set   ⚠️ needs key\n\n"
        "One API key is shared by all OpenAI models.\n"
        "Get yours at: https://platform.openai.com/api-keys"
    )
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        log.warning(f"[LLM] openai_menu send failed: {e}")
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_llm_setkey_prompt(chat_id: int) -> None:
    """Ask admin to paste their OpenAI API key."""
    _st._pending_llm_key[chat_id] = "openai"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="openai_llm_menu"))
    bot.send_message(
        chat_id,
        "🔑 *Set OpenAI API Key*\n\n"
        "Paste your OpenAI API key in a message below.\n"
        "_It starts with_ `sk-proj-...` _or_ `sk-...`\n\n"
        "_The key is stored in_ `~/.taris/config.json` _on the Pi._\n"
        "_It applies to all OpenAI models (GPT-4o, GPT-4o-mini, o3-mini…)._",
        parse_mode="Markdown",
        reply_markup=kb,
    )


def _handle_save_llm_key(chat_id: int, raw_key: str) -> None:
    """Validate and save the typed OpenAI API key, return to OpenAI sub-menu."""
    _st._pending_llm_key.pop(chat_id, None)
    raw_key = raw_key.strip()
    if not raw_key.startswith("sk-"):
        bot.send_message(
            chat_id,
            "❌ *Invalid key* — OpenAI keys start with `sk-`.\n\nTap the button to try again.",
            parse_mode="Markdown",
        )
        _handle_openai_llm_menu(chat_id)
        return
    ok = _save_openai_apikey(raw_key)
    if ok:
        bot.send_message(
            chat_id,
            f"✅ *OpenAI API key saved!*\n\nKey: `…{raw_key[-4:]}`\n"
            "_All OpenAI models now use this key._",
            parse_mode="Markdown",
        )
    else:
        bot.send_message(chat_id, "❌ Failed to save key — check Pi logs.",
                         parse_mode="Markdown")
    _handle_openai_llm_menu(chat_id)


def _handle_admin_llm_fallback_menu(chat_id: int) -> None:
    """Show local LLM fallback status and toggle button."""
    flag_on = LLM_LOCAL_FALLBACK or Path(LLM_FALLBACK_FLAG_FILE).exists()
    status  = "✅ ON" if flag_on else "⭕ OFF"
    kb = InlineKeyboardMarkup(row_width=1)
    toggle_label = "🔴 Turn OFF" if flag_on else "🟢 Turn ON"
    kb.add(InlineKeyboardButton(toggle_label, callback_data="admin_llm_fallback_toggle"))
    kb.add(InlineKeyboardButton("🔙  LLM Menu", callback_data="admin_llm_menu"))
    url_line   = f"`{LLAMA_CPP_URL}`" if LLAMA_CPP_URL else "_not set_"
    model_line = f"`{LLAMA_CPP_MODEL}`" if LLAMA_CPP_MODEL else "_server default_"
    text = (
        f"📡 *Local LLM Fallback*\n\n"
        f"Status: *{status}*\n"
        f"URL: {url_line}\n"
        f"Model: {model_line}\n\n"
        f"When ON, failed primary LLM calls fall back to the local llama.cpp server.\n"
        f"Response is prefixed with ⚠️ `[local fallback]`."
    )
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        log.warning(f"[LLM] fallback_menu send failed: {e}")
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_admin_llm_fallback_toggle(chat_id: int) -> None:
    """Toggle LLM local fallback at runtime via flag file."""
    flag = Path(LLM_FALLBACK_FLAG_FILE)
    if flag.exists():
        flag.unlink()
        msg = "⭕ Local LLM fallback *disabled*.\n\nPrimary LLM errors will no longer fall back to local model."
    else:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch()
        msg = "✅ Local LLM fallback *enabled*.\n\nFailed primary LLM calls will fall back to local llama.cpp server."
    try:
        bot.send_message(chat_id, msg, parse_mode="Markdown")
    except Exception as e:
        log.warning(f"[LLM] fallback toggle send failed: {e}")
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", msg))
    _handle_admin_llm_fallback_menu(chat_id)


# ── RAG Administration ─────────────────────────────────────────────────────

def _handle_admin_rag_menu(chat_id: int) -> None:
    """Show RAG status, top-K, chunk size, timeout and action buttons."""
    import os
    from core.bot_config import RAG_FLAG_FILE
    from core.rag_settings import get as _rget
    enabled = not os.path.exists(RAG_FLAG_FILE)
    status  = _t(chat_id, "admin_rag_status_on" if enabled else "admin_rag_status_off")
    topk    = _rget("rag_top_k")
    chunk   = _rget("rag_chunk_size")
    timeout = _rget("rag_timeout")
    text = "\n".join([
        _t(chat_id, "admin_rag_menu_title"),
        status,
        _t(chat_id, "admin_rag_topk").format(topk=topk),
        _t(chat_id, "admin_rag_chunk_size").format(chunk=chunk),
        _t(chat_id, "admin_rag_timeout").format(timeout=timeout),
    ])
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(_t(chat_id, "admin_rag_view_log"),   callback_data="admin_rag_log"))
    kb.add(InlineKeyboardButton("📊 RAG Stats",                       callback_data="admin_rag_stats"))
    kb.add(InlineKeyboardButton(_t(chat_id, "admin_btn_toggle_rag"), callback_data="admin_rag_toggle"))
    kb.add(InlineKeyboardButton(_t(chat_id, "admin_rag_settings"),   callback_data="admin_rag_settings"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"),             callback_data="admin"))
    try:
        bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_admin_rag_toggle(chat_id: int) -> None:
    """Toggle RAG on/off via flag file."""
    import os
    from core.bot_config import RAG_FLAG_FILE
    if os.path.exists(RAG_FLAG_FILE):
        os.remove(RAG_FLAG_FILE)
        msg = _t(chat_id, "admin_rag_toggled_on")
    else:
        os.makedirs(os.path.dirname(RAG_FLAG_FILE), exist_ok=True)
        open(RAG_FLAG_FILE, "w").close()  # noqa: WPS515
        msg = _t(chat_id, "admin_rag_toggled_off")
    try:
        bot.send_message(chat_id, msg, parse_mode="Markdown")
    except Exception:
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", msg))
    _handle_admin_rag_menu(chat_id)


def _handle_admin_rag_settings(chat_id: int) -> None:
    """Show RAG parameter editor buttons."""
    from core.rag_settings import get as _rget
    topk    = _rget("rag_top_k")
    chunk   = _rget("rag_chunk_size")
    timeout = _rget("rag_timeout")
    temp    = _rget("llm_temperature")
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        _t(chat_id, "admin_rag_set_topk").format(topk=topk),
        callback_data="admin_rag_set_topk"))
    kb.add(InlineKeyboardButton(
        _t(chat_id, "admin_rag_set_chunk").format(chunk=chunk),
        callback_data="admin_rag_set_chunk"))
    kb.add(InlineKeyboardButton(
        _t(chat_id, "admin_rag_set_timeout").format(timeout=timeout),
        callback_data="admin_rag_set_timeout"))
    kb.add(InlineKeyboardButton(
        _t(chat_id, "admin_rag_set_temp").format(temp=temp),
        callback_data="admin_rag_set_temp"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="admin_rag_menu"))
    bot.send_message(chat_id, _t(chat_id, "admin_rag_settings"), reply_markup=kb)


def _start_admin_rag_set(chat_id: int, param: str) -> None:
    """Prompt admin to enter a new value for param (topk/chunk/timeout/temp)."""
    key_map = {
        "topk":    "admin_rag_enter_topk",
        "chunk":   "admin_rag_enter_chunk",
        "timeout": "admin_rag_enter_timeout",
        "temp":    "admin_rag_enter_temp",
    }
    _st._user_mode[chat_id] = f"admin_rag_set_{param}"
    bot.send_message(chat_id, _t(chat_id, key_map[param]),
                     reply_markup=_back_keyboard(chat_id, "admin_rag_settings"))


def _finish_admin_rag_set(chat_id: int, text: str) -> None:
    """Validate and save the RAG parameter the admin was entering."""
    mode = _st._user_mode.pop(chat_id, "")
    from core.rag_settings import set_value as _rset
    param = mode.replace("admin_rag_set_", "")
    limits: dict = {
        "topk": (1, 20), "chunk": (128, 2048), "timeout": (5, 120), "temp": (0.0, 2.0),
    }
    key_map = {
        "topk": "rag_top_k", "chunk": "rag_chunk_size",
        "timeout": "rag_timeout", "temp": "llm_temperature",
    }
    lo, hi = limits.get(param, (1, 9999))
    try:
        val: float | int = float(text.strip()) if param == "temp" else int(text.strip())
        assert lo <= val <= hi
    except (ValueError, AssertionError):
        bot.send_message(chat_id, _t(chat_id, "admin_rag_setting_invalid"))
        _handle_admin_rag_settings(chat_id)
        return
    _rset(key_map[param], val)
    bot.send_message(chat_id, _t(chat_id, "admin_rag_setting_saved"))
    _handle_admin_rag_settings(chat_id)


def _handle_admin_rag_log(chat_id: int) -> None:
    """Show the 20 most recent RAG activity log entries."""
    from core.store import store as _store
    rows = _store.list_rag_log(limit=20)
    if not rows:
        text = _t(chat_id, "admin_rag_log_title") + "\n" + _t(chat_id, "admin_rag_log_empty")
    else:
        lines = [_t(chat_id, "admin_rag_log_title")]
        for i, r in enumerate(rows, 1):
            lines.append(
                _t(chat_id, "admin_rag_log_row").format(
                    i=i,
                    query=r["query"][:40],
                    n_chunks=r["n_chunks"],
                    chars=r["chars_injected"],
                    ts=r["created_at"][:16],
                )
            )
        text = "\n".join(lines)
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown")
    except Exception:
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text))


def _handle_admin_rag_stats(chat_id: int) -> None:
    """Show aggregate RAG monitoring stats: avg latency, top queries, query type breakdown."""
    from core.store import store as _store
    try:
        stats = _store.rag_stats()
    except Exception as e:
        bot.send_message(chat_id, f"❌ RAG stats unavailable: {e}")
        return
    lines = [
        "📊 *RAG Monitoring*\n",
        f"• Total retrievals: *{stats['total']}*",
        f"• Avg latency: *{stats['avg_latency_ms']} ms*",
        f"• Avg chunks/query: *{stats['avg_chunks']}*",
        f"• Total chunks served: *{stats['total_chunks']}*",
        f"• Total chars injected: *{stats['total_chars']}*",
    ]
    if stats.get("query_types"):
        lines.append("\n*Query types:*")
        for qt, cnt in stats["query_types"].items():
            lines.append(f"  · {qt}: {cnt}")
    if stats.get("top_queries"):
        lines.append("\n*Top queries:*")
        for i, q in enumerate(stats["top_queries"], 1):
            lines.append(f"  {i}. {q['query'][:40]} ({q['cnt']}×)")
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 RAG", callback_data="admin_rag_menu"))
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)



    """Show a detailed context trace of recent LLM calls for this user.

    Displays: provider/model, temperature, history count/chars, RAG chunks,
    system message chars, and a preview of the last few history messages that
    were injected into each call. Helps diagnose context contamination bugs
    (e.g. the '1837 year' hallucination from Pushkin conversation history).
    """
    from core.bot_db import db_get_llm_trace
    rows = db_get_llm_trace(chat_id, limit=5)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙  LLM Settings", callback_data="admin_llm_menu"))
    if not rows:
        text = _t(chat_id, "admin_llm_trace_title").format(n=0) + "\n" + _t(chat_id, "admin_llm_trace_empty")
        try:
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)
        return

    lines = [_t(chat_id, "admin_llm_trace_title").format(n=len(rows))]
    for i, r in enumerate(rows, 1):
        model_s = (r.get("model") or "?")[:20]
        temp_s  = f"{r.get('temperature', 0.0):.2f}"
        resp_preview = (r.get("response_preview") or "")[:60].replace("\n", " ")
        lines.append(
            _t(chat_id, "admin_llm_trace_call").format(
                i=i,
                ts=r["created_at"][:16],
                provider=r.get("provider") or "?",
                model=model_s,
                temp=temp_s,
                hist=r.get("history_count", 0),
                hist_c=r.get("history_chars", 0),
                sys_c=r.get("system_chars", 0),
                rag_n=r.get("rag_chunks_count", 0),
                rag_c=r.get("rag_context_chars", 0),
                resp=resp_preview or "—",
            )
        )
        # Show context snapshot (last N history messages at call time)
        snapshot_json = r.get("context_snapshot") or ""
        if snapshot_json:
            try:
                import json as _json
                snaps = _json.loads(snapshot_json)
                if snaps:
                    lines.append(_t(chat_id, "admin_llm_trace_snapshot_title").format(i=i))
                    for s in snaps:
                        role    = s.get("role", "?")
                        preview = (s.get("content") or "")[:60].replace("\n", " ")
                        lines.append(_t(chat_id, "admin_llm_trace_snapshot_row").format(
                            role=role, preview=preview
                        ))
            except Exception:
                pass
        lines.append("")  # blank separator

    text = "\n".join(lines)
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_admin_memory_menu(chat_id: int) -> None:
    """Admin panel: memory configuration."""
    from core.bot_db import db_get_system_setting
    hist_max = db_get_system_setting("CONVERSATION_HISTORY_MAX", str(CONVERSATION_HISTORY_MAX))
    summ_thr = db_get_system_setting("CONV_SUMMARY_THRESHOLD", str(CONV_SUMMARY_THRESHOLD))
    mid_max  = db_get_system_setting("CONV_MID_MAX", str(CONV_MID_MAX))

    text = (
        f"🧠 *Memory Configuration*\n\n"
        f"Short-term window: `{hist_max}` messages\n"
        f"Summarize after: `{summ_thr}` messages\n"
        f"Max mid-term summaries: `{mid_max}`\n\n"
        f"_Each summarization compresses older messages into a summary._\n"
        f"_When mid-term summaries reach max, they compact into long-term memory._"
    )
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"📝 Short-term window: {hist_max}", callback_data="admin_mem_set_hist"))
    kb.add(InlineKeyboardButton(f"📝 Summarize threshold: {summ_thr}", callback_data="admin_mem_set_summ"))
    kb.add(InlineKeyboardButton(f"📝 Mid-term max: {mid_max}", callback_data="admin_mem_set_mid"))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_llm_menu"))
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_admin_mem_set_start(chat_id: int, setting_key: str) -> None:
    """Prompt admin to enter a new value for a memory setting."""
    labels = {
        "hist": ("Short-term window (messages)", "CONVERSATION_HISTORY_MAX"),
        "summ": ("Summarize threshold (messages)", "CONV_SUMMARY_THRESHOLD"),
        "mid":  ("Mid-term max (summaries)", "CONV_MID_MAX"),
    }
    label, _db_key = labels[setting_key]
    _st._user_mode[chat_id] = f"admin_mem_{setting_key}"
    bot.send_message(chat_id, f"Enter new value for {label} (integer):")
