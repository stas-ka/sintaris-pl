"""
bot_handlers.py — User-facing message handlers.

Responsibilities:
  - Mail digest (show last + refresh)
  - System chat (natural language → bash → confirm → run)
  - Free chat (taris LLM)
  - Notes UI (menu, list, create, open, edit, delete, rename, download ZIP)
"""

import hashlib
import io
import re
import subprocess
import threading
import time
import zipfile
import unicodedata
from pathlib import Path
from typing import Optional

import core.bot_state as _st
from core.bot_config import (
    LAST_DIGEST_FILE, DIGEST_SCRIPT, MAIL_CREDS_DIR,
    RAG_ENABLED, RAG_TOP_K, RAG_FLAG_FILE,
    DEVICE_VARIANT, BOT_VERSION,
    LLM_PROVIDER, OPENAI_MODEL, OLLAMA_MODEL,
    STT_PROVIDER, STT_FALLBACK_PROVIDER, FASTER_WHISPER_MODEL, FASTER_WHISPER_DEVICE,
    PIPER_BIN, PIPER_MODEL, STT_LANG,
    log,
)
from core.bot_instance import bot
from core.bot_prompts import PROMPTS
from telegram.bot_access import (
    _t, _is_admin, _is_allowed, _is_developer, _is_guest, _lang,
    _with_lang, _escape_md, _truncate,
    _safe_edit, _back_keyboard, _run_subprocess,
    _build_system_message, _user_turn_content,
)
from ui.screen_loader import load_screen
from ui.render_telegram import render_screen
from ui.bot_ui import UserContext
from core.bot_llm import ask_llm as _ask_builtin_llm, ask_llm_or_raise as _ask_llm_strict, ask_llm_with_history as _ask_llm_with_history, ask_llm_stream as _ask_llm_stream
from telegram.bot_users import (
    _list_notes_for, _load_note_text, _save_note_file, _delete_note_file,
    _slug, _find_registration, _upsert_registration, _set_reg_lang,
)

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ─────────────────────────────────────────────────────────────────────────────
# Profile multi-step state
# ─────────────────────────────────────────────────────────────────────────────

_pending_profile: dict[int, dict] = {}


def _screen_ctx(chat_id: int) -> UserContext:
    role = "admin" if _is_admin(chat_id) else "guest" if _is_guest(chat_id) else "user"
    return UserContext(user_id=chat_id, chat_id=chat_id, lang=_lang(chat_id), role=role, variant=DEVICE_VARIANT)


def _render(chat_id: int, path: str, variables: dict | None = None):
    ctx = _screen_ctx(chat_id)
    screen = load_screen(path, ctx, variables=variables,
                         t_func=lambda _l, key: _t(chat_id, key))
    render_screen(screen, chat_id, bot, screen_path=path)


# ─────────────────────────────────────────────────────────────────────────────
# Notes UI keyboards
# ─────────────────────────────────────────────────────────────────────────────

def _notes_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Notes main submenu: Create / List / Back."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "note_btn_create"),  callback_data="note_create"),
        InlineKeyboardButton(_t(chat_id, "note_btn_list"),    callback_data="note_list"),
        InlineKeyboardButton(_t(chat_id, "btn_back"),           callback_data="menu"),
    )
    return kb


# ── Note slug ↔ short hash mapping ──────────────────────────────────────────
# Telegram limits callback_data to 64 bytes. Cyrillic slugs can exceed this
# (2 bytes/char). We hash each slug to a 12-char ASCII ID and keep a reverse
# mapping so we can look up the real slug when a callback arrives.
_note_id_map: dict[str, str] = {}   # hash_id → full_slug


def _note_cb_id(slug: str) -> str:
    """Return a 12-char ASCII callback-safe ID for a note slug (≤ 64 bytes guaranteed)."""
    h = hashlib.sha1(slug.encode()).hexdigest()[:12]
    _note_id_map[h] = slug
    return h


def _note_slug_from_cb(chat_id: int, cb_id: str) -> str | None:
    """Resolve a callback ID → full slug. Rebuilds cache from filesystem on miss."""
    if cb_id in _note_id_map:
        return _note_id_map[cb_id]
    # Cache miss (bot restarted): scan this user's notes to rebuild the mapping
    for n in _list_notes_for(chat_id):
        _note_cb_id(n["slug"])          # registers in _note_id_map as side-effect
    return _note_id_map.get(cb_id)


def _notes_list_keyboard(chat_id: int, notes: list[dict]) -> InlineKeyboardMarkup:
    """Per-note open / edit / delete inline buttons. Uses hash IDs to stay under 64-byte limit."""
    kb = InlineKeyboardMarkup(row_width=3)
    for note in notes:
        slug  = note["slug"]
        cid   = _note_cb_id(slug)      # always ≤ 12 ASCII bytes
        title = note["title"][:30]
        kb.add(InlineKeyboardButton(f"📄 {title}", callback_data=f"note_open:{cid}"))
        kb.row(
            InlineKeyboardButton(_t(chat_id, "btn_edit"),   callback_data=f"note_edit:{cid}"),
            InlineKeyboardButton(_t(chat_id, "btn_delete"), callback_data=f"note_delete:{cid}"),
        )
    kb.add(InlineKeyboardButton(_t(chat_id, "note_btn_create"), callback_data="note_create"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_download_zip"), callback_data="note_download_zip"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
    return kb


# ─────────────────────────────────────────────────────────────────────────────
# Notes UI handlers
# ─────────────────────────────────────────────────────────────────────────────

def _handle_notes_menu(chat_id: int) -> None:
    _render(chat_id, "screens/notes_menu.yaml")


def _handle_note_list(chat_id: int) -> None:
    notes = _list_notes_for(chat_id)
    if not notes:
        bot.send_message(chat_id, _t(chat_id, "note_list_empty"),
                         parse_mode="Markdown",
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    header = _t(chat_id, "note_list_header", count=len(notes))
    bot.send_message(chat_id, header,
                     parse_mode="Markdown",
                     reply_markup=_notes_list_keyboard(chat_id, notes))


def _start_note_create(chat_id: int) -> None:
    _st._user_mode[chat_id]    = "note_add_title"
    _st._pending_note[chat_id] = {"step": "title"}
    bot.send_message(chat_id, _t(chat_id, "note_create_prompt_title"),
                     parse_mode="Markdown")


def _handle_note_open(chat_id: int, slug: str) -> None:
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    slug_id = _note_cb_id(slug)     # short hash safe for callback_data
    # Use placeholder when note file exists but is empty (0-byte file)
    note_content = _escape_md(text) if text.strip() else _t(chat_id, "note_empty_body")
    _render(chat_id, "screens/note_view.yaml", {
        "note_title": _escape_md(slug.replace('_', ' ')),
        "note_content": note_content,
        "slug": slug_id,
    })


def _handle_note_raw(chat_id: int, slug: str) -> None:
    """Send the note body as an unformatted plain-text message — easy to copy."""
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    slug_id = _note_cb_id(slug)
    _render(chat_id, "screens/note_raw.yaml", {
        "note_content": text or _t(chat_id, "note_empty_body"),
        "slug": slug_id,
    })


def _start_note_edit(chat_id: int, slug: str) -> None:
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    lines = text.splitlines()
    note_title = lines[0].lstrip("# ").strip() if lines else ""
    slug_id = _note_cb_id(slug)
    _render(chat_id, "screens/note_edit.yaml", {
        "title": _escape_md(note_title),
        "slug": slug_id,
    })


def _start_note_append(chat_id: int, slug: str) -> None:
    """Prompt user for text to append to an existing note."""
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    _st._user_mode[chat_id]    = "note_append_content"
    _st._pending_note[chat_id] = {"step": "append_content", "slug": slug}
    lines = text.splitlines()
    note_title = lines[0].lstrip("# ").strip() if lines else ""
    from telebot.types import ForceReply
    bot.send_message(chat_id,
                     _t(chat_id, "note_append_prompt", title=_escape_md(note_title)),
                     parse_mode="Markdown",
                     reply_markup=ForceReply(selective=False))


def _start_note_replace(chat_id: int, slug: str) -> None:
    """Prompt user to type replacement text (original Replace flow)."""
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    _st._user_mode[chat_id]    = "note_edit_content"
    _st._pending_note[chat_id] = {"step": "edit_content", "slug": slug}

    lines = text.splitlines()
    note_title = lines[0].lstrip("# ").strip() if lines else ""
    body_lines = lines[2:] if len(lines) > 2 else (lines[1:] if len(lines) > 1 else [])
    note_body  = "\n".join(body_lines).strip() or text

    bot.send_message(
        chat_id,
        _t(chat_id, "note_edit_prompt", title=_escape_md(note_title)),
        parse_mode="Markdown",
    )
    from telebot.types import ForceReply
    bot.send_message(chat_id, note_body or _t(chat_id, "note_empty_body"), parse_mode=None, reply_markup=ForceReply(selective=False))


def _handle_note_delete(chat_id: int, slug: str) -> None:
    """Show delete confirmation before actually deleting the note."""
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    title = text.splitlines()[0].lstrip("# ").strip() if text else slug
    slug_id = _note_cb_id(slug)
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "btn_note_del_confirm"),
                             callback_data=f"note_del_confirm:{slug_id}"),
        InlineKeyboardButton("❌ " + _t(chat_id, "btn_back_short"),
                             callback_data=f"note_open:{slug_id}"),
    )
    bot.send_message(chat_id,
                     _t(chat_id, "note_delete_confirm", title=_escape_md(title)),
                     parse_mode="Markdown",
                     reply_markup=kb)


def _handle_note_delete_confirmed(chat_id: int, slug: str) -> None:
    """Perform actual note deletion after user confirmed."""
    deleted = _delete_note_file(chat_id, slug)
    if deleted:
        bot.send_message(chat_id, _t(chat_id, "note_deleted"),
                         parse_mode="Markdown",
                         reply_markup=_notes_menu_keyboard(chat_id))
    else:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))


def _start_note_rename(chat_id: int, slug: str) -> None:
    """Prompt user to enter a new title for the note."""
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    current_title = text.splitlines()[0].lstrip("# ").strip() if text else slug
    _st._user_mode[chat_id]    = "note_rename_title"
    _st._pending_note[chat_id] = {"step": "rename_title", "slug": slug}
    from telebot.types import ForceReply
    bot.send_message(chat_id,
                     _t(chat_id, "note_rename_prompt", title=_escape_md(current_title)),
                     parse_mode="Markdown",
                     reply_markup=ForceReply(selective=False))


def _handle_note_download(chat_id: int, slug: str) -> None:
    """Send a single note as a .md file attachment."""
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    title = text.splitlines()[0].lstrip("# ").strip() if text else slug
    safe_name = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_") or slug
    buf = io.BytesIO(text.encode("utf-8"))
    buf.name = f"{safe_name}.md"
    bot.send_document(chat_id, buf)


def _handle_note_download_zip(chat_id: int) -> None:
    """Pack all user notes into a ZIP archive and send it."""
    notes = _list_notes_for(chat_id)
    if not notes:
        bot.send_message(chat_id, _t(chat_id, "notes_zip_empty"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for note in notes:
            text = _load_note_text(chat_id, note["slug"])
            if text:
                safe = re.sub(r"[^\w\s-]", "", note["title"]).strip().replace(" ", "_") or note["slug"]
                zf.writestr(f"{safe}.md", text)
    buf.seek(0)
    buf.name = "notes.zip"
    bot.send_document(chat_id, buf, caption=_t(chat_id, "notes_zip_ready"))


# ─────────────────────────────────────────────────────────────────────────────
# User profile
# ─────────────────────────────────────────────────────────────────────────────

def _handle_profile(chat_id: int) -> None:
    """Show the user's own profile: name, username, chat ID, role, registration date, mail."""
    try:
        from features.bot_mail_creds import _load_creds  # deferred — avoids circular import at module level
    except Exception as _imp_err:
        log.warning(f"[Profile] cannot import features.bot_mail_creds: {_imp_err}")
        _load_creds = lambda _cid: None  # noqa: E731 — degrade gracefully

    reg = _find_registration(chat_id)

    # — Name ——————————————————————————————————————————————————————————
    if reg:
        name = reg.get("name") or " ".join(
            filter(None, [reg.get("first_name", ""), reg.get("last_name", "")])
        ).strip() or str(chat_id)
    else:
        name = str(chat_id)

    # — Username ——————————————————————————————————————————————————
    uname = (reg.get("username", "") if reg else "")
    username_line = f"@{uname}" if uname else _t(chat_id, "profile_no_username")

    # — Role ———————————————————————————————————————————————————————
    if _is_admin(chat_id):
        role = _t(chat_id, "profile_role_admin")
    elif _is_allowed(chat_id):
        role = _t(chat_id, "profile_role_user")
    else:
        role = _t(chat_id, "profile_role_guest")

    # — Registration date ———————————————————————————————————————————
    if reg and reg.get("timestamp"):
        try:
            from datetime import datetime
            reg_date = datetime.fromisoformat(reg["timestamp"]).strftime("%d.%m.%Y")
        except Exception:
            reg_date = str(reg["timestamp"])[:10]
    else:
        reg_date = _t(chat_id, "profile_not_registered")

    # — Email (masked) ——————————————————————————————————————————————
    try:
        creds = _load_creds(chat_id)
    except Exception as _creds_err:
        log.warning(f"[Profile] _load_creds failed for {chat_id}: {_creds_err}")
        creds = None
    if creds and creds.get("email"):
        addr   = creds["email"]
        parts  = addr.split("@", 1)
        masked = (parts[0][:3] + "\u2022\u2022\u2022" + "@" + parts[1]) if len(parts) == 2 else addr
        email_line = f"`{masked}`"
    else:
        email_line = _t(chat_id, "profile_no_email")

    _render(chat_id, "screens/profile.yaml", {
        "name": _escape_md(name),
        "username_line": username_line,
        "tg_id": str(chat_id),
        "role": role,
        "reg_date": reg_date,
        "email_line": email_line,
        "memory_btn_label": _t(chat_id, "profile_memory_enabled_label"
                               if _memory_enabled(chat_id) else "profile_memory_disabled_label"),
        "voice_gender_btn_label": _t(chat_id, "profile_voice_gender_male_label"
                                     if _voice_gender_is_male(chat_id) else "profile_voice_gender_female_label"),
    })


def _memory_enabled(chat_id: int) -> bool:
    """Return True if memory injection is enabled for this user."""
    try:
        from core.bot_db import db_get_user_pref
        return db_get_user_pref(chat_id, "memory_enabled", "1") == "1"
    except Exception:
        return True


def _voice_gender_is_male(chat_id: int) -> bool:
    """Return True if the user has selected male TTS voice."""
    try:
        from core.store import store as _store
        opts = _store.get_voice_opts(chat_id)
        return bool(opts.get("voice_male", False))
    except Exception:
        return False


def _handle_profile_voice_gender(chat_id: int) -> None:
    """Toggle per-user TTS voice between male (dmitri) and female (irina)."""
    try:
        from core.store import store as _store
        current = _voice_gender_is_male(chat_id)
        new_val = not current
        _store.set_voice_opt("voice_male", new_val, chat_id=chat_id)
        label = _t(chat_id, "profile_voice_gender_male_set" if new_val else "profile_voice_gender_female_set")
        bot.send_message(chat_id, label, parse_mode="Markdown", reply_markup=_back_keyboard())
    except Exception as _e:
        log.warning(f"[Profile] _handle_profile_voice_gender failed for {chat_id}: {_e}")
        bot.send_message(chat_id, "❌ Could not update voice preference.", reply_markup=_back_keyboard())
    _handle_profile(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
# Profile self-service: edit name
# ─────────────────────────────────────────────────────────────────────────────

def _start_profile_edit_name(chat_id: int) -> None:
    """Prompt the user to enter a new display name."""
    _st._user_mode[chat_id] = "profile_edit_name"
    bot.send_message(chat_id, _t(chat_id, "profile_edit_name_prompt"),
                     parse_mode="Markdown", reply_markup=_back_keyboard())


def _finish_profile_edit_name(chat_id: int, text: str) -> None:
    """Apply the new display name to the user's registration record."""
    _st._user_mode.pop(chat_id, None)
    name = text.strip()
    if not name:
        _handle_profile(chat_id)
        return
    reg = _find_registration(chat_id) or {}
    _upsert_registration(
        chat_id,
        username=reg.get("username", ""),
        name=name,
        status=reg.get("status", "allowed"),
        first_name=reg.get("first_name", ""),
        last_name=reg.get("last_name", ""),
    )
    bot.send_message(chat_id, _t(chat_id, "profile_name_updated", name=_escape_md(name)),
                     parse_mode="Markdown", reply_markup=_back_keyboard())


# ─────────────────────────────────────────────────────────────────────────────
# Profile self-service: change password
# ─────────────────────────────────────────────────────────────────────────────

def _start_profile_change_pw(chat_id: int) -> None:
    """Check that a linked web account exists, then prompt for a new password."""
    try:
        from security.bot_auth import find_account_by_chat_id
        account = find_account_by_chat_id(chat_id)
    except Exception as _e:
        log.warning(f"[Profile] cannot load bot_auth: {_e}")
        account = None
    if not account:
        bot.send_message(chat_id, _t(chat_id, "profile_no_web_account"),
                         reply_markup=_back_keyboard())
        return
    _st._user_mode[chat_id] = "profile_change_pw"
    bot.send_message(chat_id, _t(chat_id, "profile_change_pw_prompt"),
                     parse_mode="Markdown", reply_markup=_back_keyboard())


def _finish_profile_change_pw(chat_id: int, text: str) -> None:
    """Validate and apply the new password."""
    _st._user_mode.pop(chat_id, None)
    pw = text.strip()
    if len(pw) < 4:
        bot.send_message(chat_id, _t(chat_id, "profile_change_pw_short"),
                         reply_markup=_back_keyboard())
        return
    try:
        from security.bot_auth import find_account_by_chat_id, change_password
        account = find_account_by_chat_id(chat_id)
        if not account:
            bot.send_message(chat_id, _t(chat_id, "profile_no_web_account"),
                             reply_markup=_back_keyboard())
            return
        change_password(account["user_id"], pw)
        log.info(f"[Profile] password changed for chat_id={chat_id} account={account.get('username')}")
    except Exception as _e:
        log.error(f"[Profile] change_password failed for {chat_id}: {_e}")
        bot.send_message(chat_id, "❌ Error: could not change password.",
                         reply_markup=_back_keyboard())
        return
    bot.send_message(chat_id, _t(chat_id, "profile_change_pw_ok"),
                     reply_markup=_back_keyboard())


def _handle_web_link(chat_id: int) -> None:
    """Generate a web link code and show it to the user via Telegram."""
    code = _st.generate_web_link_code(chat_id)
    ttl  = _st.WEB_LINK_CODE_TTL_MINUTES
    text = _t(chat_id, "web_link_code_msg", code=code, ttl=ttl)
    bot.send_message(chat_id, text, parse_mode="Markdown",
                     reply_markup=_back_keyboard())


# ─────────────────────────────────────────────────────────────────────────────
# Profile: language selection
# ─────────────────────────────────────────────────────────────────────────────

def _handle_profile_lang(chat_id: int) -> None:
    """Show language selection keyboard."""
    _render(chat_id, "screens/profile_lang.yaml")


def _set_profile_lang(chat_id: int, lang: str) -> None:
    """Apply chosen language immediately and persist it."""
    if lang not in ("ru", "en", "de"):
        return
    _st._user_lang[chat_id] = lang
    _set_reg_lang(chat_id, lang)
    bot.send_message(chat_id, _t(chat_id, "profile_lang_set_ok", lang=lang))
    _handle_profile(chat_id)


def _handle_profile_my_data(chat_id: int) -> None:
    """Show all stored data for the user."""
    from features.bot_contacts import _contact_count
    from features.bot_calendar import _cal_load
    reg = _find_registration(chat_id) or {}
    name = reg.get("name") or str(chat_id)
    lang = _st._user_lang.get(chat_id, "en")
    reg_date = str(reg.get("timestamp", ""))[:10] or "\u2014"
    notes_count = len(_list_notes_for(chat_id))
    cal_count = len(_cal_load(chat_id))
    contacts_count = _contact_count(chat_id)
    mail_file = Path(MAIL_CREDS_DIR) / f"{chat_id}.json"
    mail_status = "\u2705" if mail_file.exists() else "\u274c"
    _render(chat_id, "screens/profile_my_data.yaml", {
        "name": _escape_md(name),
        "tg_id": str(chat_id),
        "lang": lang,
        "reg_date": reg_date,
        "notes_count": str(notes_count),
        "cal_count": str(cal_count),
        "contacts_count": str(contacts_count),
        "mail_status": mail_status,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Profile — clear conversation memory
# ─────────────────────────────────────────────────────────────────────────────

def _handle_profile_clear_memory(chat_id: int) -> None:
    """Show confirmation dialog before clearing conversation history."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ " + _t(chat_id, "yes"),
                             callback_data="profile_clear_memory_confirm"),
        InlineKeyboardButton("❌ " + _t(chat_id, "no"),
                             callback_data="profile"),
    )
    bot.send_message(chat_id, _t(chat_id, "profile_clear_memory_confirm"),
                     reply_markup=kb, parse_mode="Markdown")


def _handle_profile_clear_memory_confirmed(chat_id: int) -> None:
    """Clear all conversation history for this user (short-term + DB)."""
    _st.clear_history(chat_id)
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="profile"))
    bot.send_message(chat_id, _t(chat_id, "profile_memory_cleared"),
                     reply_markup=kb, parse_mode="Markdown")


def _handle_profile_toggle_memory(chat_id: int) -> None:
    """Toggle per-user memory injection on/off."""
    from core.bot_db import db_get_user_pref, db_set_user_pref
    current = db_get_user_pref(chat_id, "memory_enabled", "1")
    new_val = "0" if current == "1" else "1"
    db_set_user_pref(chat_id, "memory_enabled", new_val)
    status_key = "profile_memory_on" if new_val == "1" else "profile_memory_off"
    bot.send_message(chat_id, _t(chat_id, status_key))
    _handle_profile(chat_id)



# ─────────────────────────────────────────────────────────────────────────────
# Mail digest
# ─────────────────────────────────────────────────────────────────────────────

def _handle_digest(chat_id: int) -> None:
    """Delegate to per-user credential-aware digest handler."""
    from features.bot_mail_creds import handle_digest_auth   # deferred — no circular at runtime
    handle_digest_auth(chat_id)


def _refresh_digest(chat_id: int) -> None:
    """Delegate to per-user credential-aware refresh."""
    from features.bot_mail_creds import handle_digest_refresh  # deferred — no circular at runtime
    handle_digest_refresh(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
# System chat — natural language → bash → confirm → execute
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = PROMPTS["system_prompt"]


def _build_host_ctx() -> str:
    """Collect host OS / hardware facts once at startup and return a context block.

    Gathers: hostname, OS distro, kernel, arch, CPU model, RAM, disk,
    available temperature tools, init system, package manager, network interfaces,
    and available network/speed diagnostic tools.
    This is injected into the system-chat system prompt so the LLM can
    generate commands adapted to the actual host.
    """
    import platform, shutil

    def _run(cmd: list[str], default: str = "unknown") -> str:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            return out.stdout.strip() or default
        except Exception:
            return default

    def _read(path: str, default: str = "unknown") -> str:
        try:
            return Path(path).read_text().strip() or default
        except Exception:
            return default

    # OS info
    hostname = platform.node()
    kernel = platform.release()
    arch = platform.machine()
    os_name = _run(["sh", "-c", "grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"'"], platform.system())
    init = "systemd" if shutil.which("systemctl") else ("openrc" if shutil.which("rc-service") else "unknown")
    pkg_mgr = next((p for p in ("apt", "dnf", "pacman", "apk", "brew") if shutil.which(p)), "unknown")

    # CPU
    cpu_model = _run(["sh", "-c", "grep 'model name' /proc/cpuinfo | head -1 | cut -d: -f2"], "unknown").strip()
    if not cpu_model or cpu_model == "unknown":  # Raspberry Pi / ARM
        cpu_model = _run(["sh", "-c", "grep -i 'Model' /proc/cpuinfo | head -1 | cut -d: -f2"], "unknown").strip()

    # RAM / disk
    ram = _run(["sh", "-c", "free -h | awk '/^Mem:/{print $2\" total, \"$3\" used\"}'"], "unknown")
    disk = _run(["sh", "-c", "df -h / | awk 'NR==2{print $2\" total, \"$3\" used, \"$5\" full\"}'"], "unknown")

    # Temperature tools available
    temp_tools: list[str] = []
    if shutil.which("sensors"):
        temp_tools.append("sensors (lm-sensors)")
    if shutil.which("vcgencmd"):
        temp_tools.append("vcgencmd measure_temp (Raspberry Pi)")
    thermal_zones = list(Path("/sys/class/thermal").glob("thermal_zone*/temp")) if Path("/sys/class/thermal").exists() else []
    if thermal_zones:
        types = []
        for tz in thermal_zones[:4]:
            t = _read(str(tz.parent / "type"), "")
            if t:
                types.append(t)
        temp_tools.append(f"/sys/class/thermal ({', '.join(types) or str(len(thermal_zones)) + ' zones'})")
    if not temp_tools:
        temp_tools.append("none detected")

    # Network interfaces (UP only, skip loopback)
    net_ifaces_raw = _run(["sh", "-c", "ip -o link show | awk '{print $2, $9}'"], "")
    net_ifaces = [
        line.rstrip(":") for line in net_ifaces_raw.splitlines()
        if "UP" in line and not line.startswith("lo:")
    ]
    default_iface = _run(["sh", "-c", "ip route | awk '/^default/{print $5; exit}'"], "unknown")
    default_gw = _run(["sh", "-c", "ip route | awk '/^default/{print $3; exit}'"], "unknown")

    # Network speed / diagnostic tools
    speed_tools = [t for t in ("speedtest-cli", "speedtest", "iperf3", "nload", "iftop",
                                "vnstat", "nethogs", "ifstat", "bmon") if shutil.which(t)]
    if not speed_tools:
        # Always available fallbacks
        speed_tools = ["cat /proc/net/dev (rx/tx counters)", "curl -o /dev/null (HTTP speed test)"]

    # Misc tools relevant to system administration
    extra_tools = [t for t in ("htop", "top", "iotop", "lsof", "ss", "netstat", "ip", "ifconfig",
                                "journalctl", "systemctl", "docker", "kubectl") if shutil.which(t)]

    lines = [
        "[HOST ENVIRONMENT — use this to generate commands that work on this specific host]",
        f"Hostname     : {hostname}",
        f"OS           : {os_name}",
        f"Kernel       : {kernel}  arch: {arch}",
        f"CPU          : {cpu_model}",
        f"RAM          : {ram}",
        f"Disk /       : {disk}",
        f"Init system  : {init}",
        f"Package mgr  : {pkg_mgr}",
        f"Temp tools   : {', '.join(temp_tools)}",
        f"Net ifaces   : {', '.join(net_ifaces) or 'none'} (default: {default_iface}, gw: {default_gw})",
        f"Speed tools  : {', '.join(speed_tools)}",
        f"Admin tools  : {', '.join(extra_tools) or 'none'}",
        "[END HOST ENVIRONMENT]",
    ]
    return "\n".join(lines)


# Cached once at import time — host info doesn't change at runtime.
_HOST_CTX: str = _build_host_ctx()

# Broad emoji / pictograph regex — matches everything the Unicode Standard
# classifies as emoji / symbol characters.
# NOTE: \u requires 4 hex digits, \U requires exactly 8 hex digits.
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0002BFFF"   # All supplementary symbol/emoji blocks (SMP+SIP)
    "\U00002300-\U000027FF"   # Misc technical, Dingbats, weather symbols
    "\U00002B00-\U00002BFF"   # Misc symbols and arrows
    "\U0000FE00-\U0000FE0F"   # Variation selectors (VS1-VS16)
    "\U0000FE0F"               # Variation selector-16 (emoji style)
    "\U0000200D"               # Zero-width joiner
    "\U0000200B"               # Zero-width space
    "\U000020D0-\U000020FF"   # Combining diacritical marks for symbols
    "]",
    re.UNICODE,
)

# Unicode categories to treat as non-printable/symbol — extend beyond So/Sk
_SYMBOL_CATEGORIES = frozenset(("So", "Sk", "Sm", "Cf", "Cs", "Co", "Mn", "Me"))


def _strip_symbols(text: str) -> str:
    """Remove emoji and Unicode symbol chars from *text* using regex + category."""
    text = _EMOJI_RE.sub("", text)
    return "".join(ch for ch in text if unicodedata.category(ch) not in _SYMBOL_CATEGORIES)


def _extract_bash_cmd(raw: str) -> str:
    """
    Robustly extract a bare bash command from LLM output that may include:
      - markdown code fences (```bash ... ``` or plain ``` ... ```)
      - single surrounding backticks
      - emoji/pictograph prefixes  (e.g. '🦞 ls /home')
      - bracket-wrapped decoration (e.g. '[🦞] ls /home' → '[] ls' → 'ls')
      - explanatory prose before/after the actual command

    Strategy:
      1. Strip triple-backtick fences.
      2. Strip single surrounding backticks.
      3. Remove all emoji / symbol characters (_strip_symbols).
      4. Strip residual leading bracket-decoration (e.g. '[] ', '[*] ').
      5. Walk lines: return the first non-empty line whose first word is
         plain ASCII and passes the bash-command heuristic.
      6. Fallback: return the symbol-stripped text.
    """
    text = raw.strip()

    # 1. Extract content from code fence: ```(bash|sh|shell)?\n...\n```
    fence_match = re.search(
        r"```(?:bash|sh|shell|cmd|console)?\s*\n?(.*?)\n?```",
        text, re.DOTALL | re.IGNORECASE,
    )
    if fence_match:
        text = fence_match.group(1).strip()

    # 2. Strip single surrounding backticks
    if text.startswith("`") and text.endswith("`") and len(text) > 2:
        text = text[1:-1].strip()

    # 3. Remove emoji / symbol characters everywhere
    text = _strip_symbols(text).strip()

    # 4. Strip residual leading bracket decoration left after emoji removal
    #    e.g. "[] ls -la" → "ls -la",  "[*] find ..." → "find ..."
    text = re.sub(r'^[\[({<][^\])}>\n]{0,6}[\])}>\s]\s*', '', text).strip()

    # 5. Walk lines; pick the first non-empty one that looks like a bash command.
    #    Heuristic: starts with an allowed shell character AND first word is
    #    plain ASCII (no embedded Unicode / emoji survivors).
    _CMD_START    = re.compile(r'^[a-zA-Z0-9/_~.$\-\'"\\]')
    _PROSE_REJECT = re.compile(r'^[A-Z][a-z]+ ')  # "Sure, here is…" / "Here's the…"
    for line in text.splitlines():
        line = _strip_symbols(line).strip()
        # Per-line bracket decoration strip
        line = re.sub(r'^[\[({<][^\])}>\n]{0,6}[\])}>\s]\s*', '', line).strip()
        if not line:
            continue
        if _PROSE_REJECT.match(line) and len(line.split()) > 4:
            continue
        if _CMD_START.match(line):
            first_word = line.split()[0]
            # First word (the executable) must be plain ASCII
            if all(ord(c) < 128 for c in first_word):
                return line

    # 6. Fallback: return whatever is left after symbol stripping
    return text.strip()


_SYSTEM_HISTORY_MAX = 20  # max entries (10 turns) per user


def _save_system_history(chat_id: int, user_text: str, cmd: str) -> None:
    """Append a user→command turn to the per-user system chat history (in-memory)."""
    hist = _st._system_history.setdefault(chat_id, [])
    hist.append({"role": "user",      "content": user_text})
    hist.append({"role": "assistant", "content": cmd})
    # Trim oldest entries to stay within limit (keep last N entries)
    _st._system_history[chat_id] = hist[-_SYSTEM_HISTORY_MAX:]


def _handle_system_message(chat_id: int, user_text: str) -> None:
    """Translate natural language → bash command → ask for confirmation.
    Admin-only: read/inspect commands.  Developer: adds service control and writes.
    """
    if _is_admin(chat_id):
        role = "admin"
    elif _is_developer(chat_id):
        role = "developer"
    else:
        bot.send_message(chat_id,
                         _t(chat_id, "security_admin_only"),
                         reply_markup=_back_keyboard())
        log.warning(f"[Security] non-admin system-chat attempt from chat_id={chat_id}")
        return

    from security.bot_security import _check_injection, _classify_cmd_class
    is_inj, reason = _check_injection(user_text)
    if is_inj:
        bot.send_message(chat_id,
                         _t(chat_id, "security_blocked"),
                         parse_mode="Markdown",
                         reply_markup=_back_keyboard())
        return

    bot.send_chat_action(chat_id, "typing")

    # ── Runtime config context — injected so LLM can answer config questions ──
    from core.bot_llm import get_per_func_provider
    voice_llm = get_per_func_provider("voice") or LLM_PROVIDER
    _llm_model = OLLAMA_MODEL if LLM_PROVIDER == "ollama" else OPENAI_MODEL
    _stt_fallback = f" (fallback: {STT_FALLBACK_PROVIDER})" if STT_FALLBACK_PROVIDER else ""
    _piper_model = Path(PIPER_MODEL).name if PIPER_MODEL else "unknown"
    _config_ctx = (
        f"[BOT RUNTIME CONFIG — use this to answer config questions accurately]\n"
        f"Bot version: {BOT_VERSION}\n"
        f"Variant: {DEVICE_VARIANT}\n"
        f"LLM provider: {LLM_PROVIDER} (model: {_llm_model})\n"
        f"LLM for voice: {voice_llm}\n"
        f"STT provider: {STT_PROVIDER}{_stt_fallback} | model: {FASTER_WHISPER_MODEL}/{FASTER_WHISPER_DEVICE} | lang: {STT_LANG}\n"
        f"TTS: Piper | model: {_piper_model}\n"
        f"[END CONFIG]\n\n"
    )
    msg = bot.send_message(chat_id, "⏳ Generating command…")

    def _run():
        # Build multi-turn messages: system prompt + prior system-chat history + current request
        sys_content = f"{_SYSTEM_PROMPT}\n\n{_config_ctx}\n\n{_HOST_CTX}"
        hist = _st._system_history.get(chat_id, [])
        messages = [{"role": "system", "content": sys_content}] + hist + [{"role": "user", "content": user_text}]
        try:
            cmd_text = _ask_llm_with_history(messages, timeout=45, use_case="system")
        except subprocess.TimeoutExpired:
            bot.edit_message_text("❌ LLM timed out (>45 s). Try again later.",
                                  chat_id, msg.message_id)
            return
        except FileNotFoundError:
            bot.edit_message_text("❌ LLM binary not found — check bot config.",
                                  chat_id, msg.message_id)
            return
        except Exception as exc:
            err_str = str(exc)
            if "402" in err_str or "Payment Required" in err_str:
                display = "❌ LLM unavailable — payment or quota issue. Contact admin."
                md = None
            elif "401" in err_str or "Unauthorized" in err_str:
                display = "❌ LLM authentication failed — check API key. Contact admin."
                md = None
            elif "429" in err_str or "Too Many Requests" in err_str:
                display = "❌ LLM rate limit exceeded. Try again in a moment."
                md = None
            elif "503" in err_str or "Service Unavailable" in err_str:
                display = "❌ LLM service temporarily unavailable. Try again later."
                md = None
            else:
                display = f"❌ LLM error: `{err_str[:100]}`"
                md = "Markdown"
            bot.edit_message_text(display, chat_id, msg.message_id, parse_mode=md)
            log.warning(f"[SystemChat] LLM error: {exc}")
            return
        if not cmd_text:
            bot.edit_message_text("❌ LLM returned empty response. Try rephrasing.",
                                  chat_id, msg.message_id)
            return

        # Extract the bare bash command — strip code fences, emoji, prose
        cmd_clean = _extract_bash_cmd(cmd_text)
        if not cmd_clean:
            bot.edit_message_text(
                "❌ Could not extract a valid command from the LLM response.\n"
                f"Raw output: `{cmd_text[:200]}`",
                chat_id, msg.message_id, parse_mode="Markdown",
            )
            log.warning(f"[SystemChat] empty cmd after extraction. raw={cmd_text[:200]}")
            return

        # Knowledge answer pattern — LLM returns echo "answer text" for informational questions.
        # Show the answer directly without a Run/Cancel confirmation dialog.
        _echo_m = re.match(r'^echo\s+["\']?(.*?)["\']?\s*$', cmd_clean, re.DOTALL)
        if _echo_m:
            answer = _echo_m.group(1).strip().strip("\"'")
            log.info(f"[SystemChat] knowledge answer (echo): {answer[:80]}")
            # Save to system history so follow-up questions have context
            _save_system_history(chat_id, user_text, cmd_clean)
            try:
                bot.edit_message_text(
                    _t(chat_id, "system_answer", answer=answer),
                    chat_id, msg.message_id,
                    reply_markup=_back_keyboard(chat_id),
                )
            except Exception:
                bot.send_message(chat_id, _t(chat_id, "system_answer", answer=answer),
                                 reply_markup=_back_keyboard(chat_id))
            return

        # Role-based allowlist check
        cmd_class = _classify_cmd_class(cmd_clean)
        if cmd_class == "blocked":
            bot.edit_message_text(
                f"⛔ Command not permitted:\n```\n{cmd_clean}\n```\n"
                "Only read-only monitoring and config commands are allowed.",
                chat_id, msg.message_id, parse_mode="Markdown",
                reply_markup=_back_keyboard(),
            )
            log.warning(f"[Security] blocked cmd (not on allowlist) role={role}: {cmd_clean!r}")
            return
        if cmd_class == "developer" and role == "admin":
            bot.edit_message_text(
                f"⛔ Command requires Developer role:\n```\n{cmd_clean}\n```\n"
                "Admin can only run read-only commands.",
                chat_id, msg.message_id, parse_mode="Markdown",
                reply_markup=_back_keyboard(),
            )
            log.warning(f"[Security] admin attempted developer cmd: {cmd_clean!r}")
            return

        # Save to system history — user request + proposed command
        _save_system_history(chat_id, user_text, cmd_clean)

        cmd_hash = hashlib.md5(cmd_clean.encode()).hexdigest()[:8]
        _st._pending_cmd[chat_id] = cmd_clean

        from telegram.bot_access import _confirm_keyboard
        reply = _t(chat_id, "system_cmd_confirm", cmd=cmd_clean)
        try:
            bot.edit_message_text(reply, chat_id, msg.message_id,
                                  parse_mode="Markdown",
                                  reply_markup=_confirm_keyboard(cmd_hash))
        except Exception:
            bot.send_message(chat_id, reply,
                             parse_mode="Markdown",
                             reply_markup=_confirm_keyboard(cmd_hash))

    threading.Thread(target=_run, daemon=True).start()


def _execute_pending_cmd(chat_id: int) -> None:
    """Execute the confirmed pending bash command and show output."""
    cmd = _st._pending_cmd.pop(chat_id, None)
    if not cmd:
        bot.send_message(chat_id, "⚠️ No pending command.", reply_markup=_back_keyboard())
        return

    msg = bot.send_message(chat_id, f"▶️  Running…\n```\n{cmd}\n```",
                            parse_mode="Markdown")

    def _run():
        # Final safety net: strip any residual emoji/symbols from the command
        # before execution — defence-in-depth in case the extraction missed any.
        safe_cmd = _extract_bash_cmd(cmd)
        if not safe_cmd:
            bot.edit_message_text(
                "❌ Command sanitization failed — refusing to run.",
                chat_id, msg.message_id, reply_markup=_back_keyboard(),
            )
            log.warning(f"[SystemChat] refused to execute after sanitization: {cmd!r}")
            return
        if safe_cmd != cmd:
            log.info(f"[SystemChat] sanitized cmd: {cmd!r} → {safe_cmd!r}")
        rc, output = _run_subprocess(["bash", "-c", safe_cmd], timeout=30)
        if not output:
            output = "(no output)"
        status = "✅" if rc == 0 else f"⚠️ exit {rc}"
        result = (
            f"{status} `{cmd[:60]}{'…' if len(cmd) > 60 else ''}`\n\n"
            f"```\n{_truncate(output, 3500)}\n```"
        )
        try:
            bot.edit_message_text(result, chat_id, msg.message_id,
                                  parse_mode="Markdown",
                                  reply_markup=_back_keyboard())
        except Exception:
            bot.send_message(chat_id, result,
                             parse_mode="Markdown",
                             reply_markup=_back_keyboard())

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Free chat
# ─────────────────────────────────────────────────────────────────────────────

def _handle_chat_message(chat_id: int, user_text: str) -> None:
    """Forward message to LLM with conversation history context."""
    from security.bot_security import _check_injection
    from core.bot_state import add_to_history, get_history_with_ids
    from core.bot_llm import ask_llm_with_history
    is_inj, reason = _check_injection(user_text)
    if is_inj:
        bot.send_message(chat_id,
                         _t(chat_id, "security_blocked"),
                         parse_mode="Markdown",
                         reply_markup=_back_keyboard())
        log.warning(f"[Security] chat injection blocked chat_id={chat_id}")
        return

    bot.send_chat_action(chat_id, "typing")
    msg = bot.send_message(chat_id, "⏳ Thinking…")

    def _run():
        import uuid
        from core.bot_db import db_log_llm_call
        from core.bot_config import LLM_PROVIDER
        call_id = str(uuid.uuid4())

        # Get history with DB IDs for call tracking
        history_entries = get_history_with_ids(chat_id)
        history_ids = [m["_db_id"] for m in history_entries if m.get("_db_id")]
        history_msgs = [{"role": m["role"], "content": m["content"]} for m in history_entries]

        # ── System message: security preamble + bot config + memory note + lang ──
        system_content = _build_system_message(chat_id, user_text)
        # Inject tiered long/mid-term memory summaries — respects per-user toggle
        try:
            from core.bot_state import get_memory_context
            from core.bot_db import db_get_user_pref
            if db_get_user_pref(chat_id, "memory_enabled", "1") == "1":
                _mem_ctx = get_memory_context(chat_id)
                if _mem_ctx:
                    system_content = system_content + "\n\n" + _mem_ctx
        except Exception as _mem_e:
            log.debug("[Memory] context injection failed: %s", _mem_e)

        # ── Current user turn: RAG context + user text (no preamble — that's in system) ──
        current_content = _user_turn_content(chat_id, user_text)

        # ── Build full messages list: [system] + history + current_user_turn ──
        messages = [{"role": "system", "content": system_content}] + history_msgs + [{"role": "user", "content": current_content}]
        log.debug("[Chat] history=%d msgs, system=%d chars, turn=%d chars",
                  len(history_msgs), len(system_content), len(current_content))

        # Record the raw user text (without preamble) before calling the LLM
        add_to_history(chat_id, "user", user_text, call_id=call_id)

        # ── Streaming LLM response — edit message in real time ──
        import time as _time
        from core.bot_config import LLM_PROVIDER as _provider
        buf = ""
        last_edit = 0.0
        EDIT_INTERVAL = 1.5  # seconds between Telegram edits (rate limit safe)
        try:
            for fragment in _ask_llm_stream(messages, timeout=120):
                buf += fragment
                now = _time.monotonic()
                if now - last_edit >= EDIT_INTERVAL and len(buf) >= 20:
                    try:
                        bot.edit_message_text(
                            _truncate(buf) + " ▌", chat_id, msg.message_id, parse_mode=None
                        )
                        last_edit = now
                    except Exception:
                        pass  # ignore rate-limit or minor edit errors
        except Exception as _stream_err:
            log.warning(f"[Chat] stream error: {_stream_err}")
            if not buf:
                buf = ask_llm_with_history(messages, timeout=120, use_case="chat")

        reply = buf if buf else "❌ No response from LLM."
        add_to_history(chat_id, "assistant", reply, call_id=call_id)

        # Log which history messages were included in this LLM call
        try:
            import json as _json
            from core.bot_llm import _effective_temperature, get_active_model, OLLAMA_MODEL
            from telegram.bot_access import _rag_debug_stats
            _rag_stats = _rag_debug_stats(chat_id, user_text)
            _history_chars = sum(len(m["content"]) for m in history_msgs)
            _snapshot = _json.dumps([
                {"role": m["role"], "content": m["content"][:80]}
                for m in history_msgs[-5:]
            ])
            db_log_llm_call(
                call_id, chat_id, LLM_PROVIDER,
                history_ids,
                sum(len(m["content"]) for m in messages),
                bool(response),
                model=get_active_model() or OLLAMA_MODEL,
                temperature=_effective_temperature(),
                system_chars=len(system_content),
                history_chars=_history_chars,
                rag_chunks_count=_rag_stats.get("chunks", 0),
                rag_context_chars=_rag_stats.get("chars", 0),
                response_preview=reply[:300],
                context_snapshot=_snapshot,
            )
        except Exception as _e:
            log.warning(f"[History] LLM call DB logging failed: {_e}")

        try:
            bot.edit_message_text(_truncate(reply), chat_id, msg.message_id,
                                  parse_mode=None,
                                  reply_markup=_back_keyboard())
        except Exception:
            bot.send_message(chat_id, _truncate(reply),
                             parse_mode=None,
                             reply_markup=_back_keyboard())

    threading.Thread(target=_run, daemon=True).start()
