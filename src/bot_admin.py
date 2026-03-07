"""
bot_admin.py — Admin panel handlers.

Responsibilities:
  - Admin keyboard + entry point
  - Guest-user management (add / list / remove)
  - Registration approval / blocking
  - Voice-optimization toggle menu
  - Release notes — load, format, version-change admin notification
  - LLM model switcher (picoclaw models + OpenAI ChatGPT sub-menu)
"""

import re as _re
import json
import threading
from pathlib import Path

import bot_state as _st
from bot_config import (
    ADMIN_USERS, ALLOWED_USERS,
    PICOCLAW_CONFIG,
    RELEASE_NOTES_FILE, LAST_NOTIFIED_FILE, BOT_VERSION,
    _VOICE_OPTS_DEFAULTS,
    log,
)
from bot_instance import bot
from bot_access import (
    _t, _escape_md, _send_menu,
    _back_keyboard, _get_active_model,
)
from bot_users import (
    _get_pending_registrations, _find_registration, _upsert_registration,
    _set_reg_status,
)
from bot_voice import _warm_piper_cache, _start_persistent_piper, _stop_persistent_piper

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ─────────────────────────────────────────────────────────────────────────────
# Shorthand helpers for mutable state
# ─────────────────────────────────────────────────────────────────────────────

def _voice_opts() -> dict:
    return _st._voice_opts


def _save_voice_opts() -> None:
    from bot_state import _save_voice_opts as _svop
    _svop()


def _dynamic_users() -> set:
    return _st._dynamic_users


def _save_dynamic_users() -> None:
    from bot_state import _save_dynamic_users as _sdyn
    _sdyn()


def _user_info_block(uid: int, reg) -> str:
    """Compact Markdown block with all available identity info for a user."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Admin keyboard
# ─────────────────────────────────────────────────────────────────────────────

def _admin_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    pending_count = len(_get_pending_registrations())
    pending_badge = f"  ({pending_count} new)" if pending_count else ""
    kb.add(
        InlineKeyboardButton(f"👥  Pending Requests{pending_badge}",
                             callback_data="admin_pending_users"),
        InlineKeyboardButton("➕  Add user",       callback_data="admin_add_user"),
        InlineKeyboardButton("📋  List users",     callback_data="admin_list_users"),
        InlineKeyboardButton("🗑   Remove user",    callback_data="admin_remove_user"),
        InlineKeyboardButton("🤖  Switch LLM",     callback_data="admin_llm_menu"),
        InlineKeyboardButton("⚡  Voice Opts",      callback_data="voice_opts_menu"),
        InlineKeyboardButton("📝  Release Notes",   callback_data="admin_changelog"),
        InlineKeyboardButton("🔙  Menu",            callback_data="menu"),
    )
    return kb


def _handle_admin_menu(chat_id: int) -> None:
    bot.send_message(
        chat_id,
        "🔐 *Admin Panel*",
        parse_mode="Markdown",
        reply_markup=_admin_keyboard(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Guest-user management
# ─────────────────────────────────────────────────────────────────────────────

def _handle_admin_list_users(chat_id: int) -> None:
    dyn = _dynamic_users()
    if not dyn:
        bot.send_message(chat_id, _t(chat_id, "no_guests"),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
        return
    blocks = [_user_info_block(uid, _find_registration(uid)) for uid in sorted(dyn)]
    bot.send_message(
        chat_id,
        _t(chat_id, "guest_header") + "\n\n" + "\n\n".join(blocks),
        parse_mode="Markdown",
        reply_markup=_admin_keyboard(),
    )


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
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
    elif uid in ALLOWED_USERS or uid in ADMIN_USERS:
        bot.send_message(admin_id, _t(admin_id, "already_full", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
    else:
        dyn.add(uid)
        _save_dynamic_users()
        log.info(f"Admin {admin_id} added guest user {uid}")
        bot.send_message(admin_id, _t(admin_id, "user_added", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
    _st._user_mode.pop(admin_id, None)


def _start_admin_remove_user(chat_id: int) -> None:
    dyn = _dynamic_users()
    if not dyn:
        bot.send_message(chat_id, _t(chat_id, "no_guests_del"),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
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
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
    else:
        bot.send_message(admin_id, _t(admin_id, "user_not_found", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
    _st._user_mode.pop(admin_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# Registration — admin: pending list, approve, block; user: new-reg notification
# ─────────────────────────────────────────────────────────────────────────────

def _handle_admin_pending_users(chat_id: int) -> None:
    """Show all pending registration requests with approve/block buttons."""
    pending = _get_pending_registrations()
    if not pending:
        bot.send_message(chat_id, _t(chat_id, "no_pending_regs"),
                         reply_markup=_admin_keyboard())
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
    from bot_access import _menu_keyboard
    reg = _find_registration(target_id)
    if not reg:
        bot.send_message(admin_id, f"ℹ️ Registration for `{target_id}` not found.",
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
        return
    if reg.get("status") == "approved":
        bot.send_message(admin_id, f"ℹ️ User `{target_id}` is already approved.",
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
        return
    _set_reg_status(target_id, "approved")
    _dynamic_users().add(target_id)
    _save_dynamic_users()
    name_disp = f" \u2014 {reg.get('name')}" if reg.get("name") else ""
    log.info(f"[Reg] Admin {admin_id} approved user {target_id}")
    bot.send_message(admin_id, f"\u2705 User `{target_id}`{name_disp} approved and added as guest.",
                     parse_mode="Markdown", reply_markup=_admin_keyboard())
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
                     parse_mode="Markdown", reply_markup=_admin_keyboard())
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

    def _flag(key: str) -> str:
        return "✅" if opts.get(key) else "◻️"

    kb = InlineKeyboardMarkup(row_width=1)
    opts_rows = [
        ("silence_strip",     f"{_flag('silence_strip')}  Silence strip  ·  −6s STT"),
        ("low_sample_rate",   f"{_flag('low_sample_rate')}  8 kHz sample rate  ·  −7s STT"),
        ("warm_piper",        f"{_flag('warm_piper')}  Warm Piper cache  ·  −15s TTS"),
        ("parallel_tts",      f"{_flag('parallel_tts')}  Parallel TTS thread  ·  text-first UX"),
        ("user_audio_toggle", f"{_flag('user_audio_toggle')}  Per-user audio 🔊/🔇 toggle"),
        ("tmpfs_model",       f"{_flag('tmpfs_model')}  Piper model in RAM (/dev/shm)  ·  −10s TTS load"),
        ("vad_prefilter",     f"{_flag('vad_prefilter')}  VAD pre-filter (webrtcvad)  ·  −3s STT"),
        ("whisper_stt",       f"{_flag('whisper_stt')}  Whisper STT (whisper.cpp)  ·  +accuracy"),
        ("piper_low_model",   f"{_flag('piper_low_model')}  Piper low model  ·  −13s TTS"),
        ("persistent_piper",  f"{_flag('persistent_piper')}  Persistent Piper process  ·  ONNX hot"),
    ]
    for key, label in opts_rows:
        kb.add(InlineKeyboardButton(label, callback_data=f"voice_opt_toggle:{key}"))
    kb.add(InlineKeyboardButton("🔙  Admin", callback_data="admin_menu"))

    active  = [k for k, v in opts.items() if v]
    status  = ("Active: " + ", ".join(active)) if active else "All OFF — stable defaults"
    status_esc = _escape_md(status)
    text = (
        "⚡ *Voice Pipeline Optimisations*\n\n"
        "Default: all OFF (stable baseline). Toggle to test individually.\n"
        "Settings persist across restarts.\n\n"
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
# Release Notes
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
    n   = entry.get("notes", "")
    hdr = f"📦 *v{v}*" + (f"  _({d})_" if d else "") + (f" — {t}" if t else "")
    return (hdr + "\n\n" + n) if header else n


def _get_changelog_text(max_entries: int = 0) -> str:
    """Return formatted changelog Markdown (all or first max_entries entries)."""
    entries = _load_release_notes()
    if not entries:
        return "📝 _Release notes not available._"
    if max_entries:
        entries = entries[:max_entries]
    parts = [_format_release_entry(e) for e in entries]
    sep = "\n\n" + "─" * 28 + "\n\n"
    return sep.join(parts)


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
                             reply_markup=_admin_keyboard())
            log.info(f"[ReleaseNotes] notified admin {admin_id} (v{BOT_VERSION})")
        except Exception as e:
            log.warning(f"[ReleaseNotes] Markdown failed for admin {admin_id}: {e} — retrying plain")
            try:
                bot.send_message(admin_id, _re.sub(r"[*_`]", "", msg),
                                 reply_markup=_admin_keyboard())
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
                         reply_markup=_admin_keyboard())
    except Exception as e:
        log.warning(f"[Changelog] Markdown failed for {chat_id}: {e} — retrying plain")
        try:
            bot.send_message(chat_id, _re.sub(r"[*_`]", "", text),
                             reply_markup=_admin_keyboard())
        except Exception as e2:
            log.error(f"[Changelog] send failed for {chat_id}: {e2}")


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


def _get_picoclaw_models() -> list[dict]:
    """Read model_list from picoclaw config.json."""
    try:
        cfg = json.loads(Path(PICOCLAW_CONFIG).read_text(encoding="utf-8"))
        return cfg.get("model_list", [])
    except Exception as e:
        log.warning(f"[LLM] Cannot read picoclaw config: {e}")
        return []


def _handle_admin_llm_menu(chat_id: int) -> None:
    """Show LLM selection keyboard with available models from picoclaw config."""
    models  = _get_picoclaw_models()
    current = _get_active_model()

    if not models:
        bot.send_message(chat_id, "⚠️ Cannot read picoclaw config.json.",
                         reply_markup=_admin_keyboard())
        return

    kb = InlineKeyboardMarkup(row_width=1)
    shared_openai_key = _get_shared_openai_key()
    openai_prefix = "✔️" if shared_openai_key else "⚠️"
    kb.add(InlineKeyboardButton(f"🔵 {openai_prefix} OpenAI ChatGPT ▶",
                                callback_data="openai_llm_menu"))

    for m in models:
        name = m.get("model_name", "")
        if not name:
            continue
        if "openai.com" in m.get("api_base", ""):
            continue
        has_key    = bool(m.get("api_key", "").strip())
        is_current = (name == current) or (not current and name == "openrouter-auto")
        prefix     = "✅" if is_current else ("✔️" if has_key else "⚠️")
        kb.add(InlineKeyboardButton(f"{prefix}  {name}", callback_data=f"llm_select:{name}"))

    kb.add(InlineKeyboardButton("↩️  Reset to default", callback_data="llm_select:"))
    kb.add(InlineKeyboardButton("🔙  Admin", callback_data="admin_menu"))

    current_label = current or "(config default: openrouter-auto)"
    text = (
        f"🤖 *Switch LLM*\n\nActive: `{current_label}`\n\n"
        f"✅ active   ✔️ key set   ⚠️ needs key\n\n"
        f"Tap *OpenAI ChatGPT* to select GPT-4o / GPT-4o-mini and set your API key."
    )
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        log.warning(f"[LLM] llm_menu send failed: {e}")
        bot.send_message(chat_id, _re.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_set_llm(chat_id: int, model_name: str) -> None:
    """Apply LLM model selection and confirm to user."""
    _set_active_model(model_name)
    if model_name:
        models_map = {m["model_name"]: m for m in _get_picoclaw_models() if m.get("model_name")}
        m       = models_map.get(model_name, {})
        has_key = bool(m.get("api_key", "").strip())
        warn    = ("" if has_key else
                   "\n\n⚠️ No API key set for this model — go to OpenAI ChatGPT menu to add one.")
        msg = f"✅ LLM switched to: {model_name}{warn}\n\nAll subsequent chat, system, and voice requests will use this model."
    else:
        msg = "↩️ LLM reset to config default (openrouter-auto)."
    try:
        bot.send_message(chat_id, msg, reply_markup=_admin_keyboard())
    except Exception as e:
        log.warning(f"[LLM] set_llm send failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI ChatGPT sub-menu
# ─────────────────────────────────────────────────────────────────────────────

_OPENAI_CATALOG = [
    ("gpt-4o",          "openai/gpt-4o",           "GPT-4o (flagship)"),
    ("gpt-4o-mini",     "openai/gpt-4o-mini",      "GPT-4o mini (fast & cheap)"),
    ("o3-mini",         "openai/o3-mini",           "o3-mini (reasoning)"),
    ("o1",              "openai/o1",                "o1 (advanced reasoning)"),
    ("gpt-4.5-preview", "openai/gpt-4.5-preview",  "GPT-4.5 preview"),
]
_OPENAI_API_BASE = "https://api.openai.com/v1"


def _get_shared_openai_key() -> str:
    """Return the first OpenAI api_key found in config.json, or ''."""
    for m in _get_picoclaw_models():
        if "openai.com" in m.get("api_base", "") and m.get("api_key", "").strip():
            return m["api_key"].strip()
    return ""


def _save_openai_apikey(api_key: str) -> bool:
    """Set api_key for all openai.com models; add catalog entries if missing."""
    try:
        p   = Path(PICOCLAW_CONFIG)
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
    models     = {m["model_name"]: m for m in _get_picoclaw_models() if m.get("model_name")}
    shared_key = _get_shared_openai_key()
    current    = _get_active_model()

    kb = InlineKeyboardMarkup(row_width=1)
    for name, _, description in _OPENAI_CATALOG:
        m          = models.get(name, {})
        has_key    = bool(m.get("api_key", "").strip()) or bool(shared_key)
        is_current = (name == current)
        prefix     = "✅" if is_current else ("✔️" if has_key else "⚠️")
        kb.add(InlineKeyboardButton(f"{prefix} {name} — {description}",
                                    callback_data=f"llm_select:{name}"))

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
        "_The key is stored in_ `~/.picoclaw/config.json` _on the Pi._\n"
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
