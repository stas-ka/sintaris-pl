"""
bot_handlers.py — User-facing message handlers.

Responsibilities:
  - Mail digest (show last + refresh)
  - System chat (natural language → bash → confirm → run)
  - Free chat (taris LLM)
  - Notes UI (menu, list, create, open, edit, delete)
"""

import hashlib
import re
import subprocess
import threading
import time
import unicodedata
from pathlib import Path
from typing import Optional

import core.bot_state as _st
from core.bot_config import (
    LAST_DIGEST_FILE, DIGEST_SCRIPT, MAIL_CREDS_DIR,
    RAG_ENABLED, RAG_TOP_K, RAG_FLAG_FILE,
    log,
)
from core.bot_instance import bot
from core.bot_prompts import PROMPTS
from telegram.bot_access import (
    _t, _is_admin, _is_allowed, _is_developer, _is_guest, _lang,
    _with_lang, _escape_md, _truncate,
    _safe_edit, _back_keyboard, _run_subprocess,
)
from ui.screen_loader import load_screen
from ui.render_telegram import render_screen
from ui.bot_ui import UserContext
from core.bot_llm import ask_llm as _ask_builtin_llm, ask_llm_or_raise as _ask_llm_strict
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
    return UserContext(user_id=chat_id, chat_id=chat_id, lang=_lang(chat_id), role=role)


def _render(chat_id: int, path: str, variables: dict | None = None):
    ctx = _screen_ctx(chat_id)
    screen = load_screen(path, ctx, variables=variables,
                         t_func=lambda _l, key: _t(chat_id, key))
    render_screen(screen, chat_id, bot)


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


def _notes_list_keyboard(chat_id: int, notes: list[dict]) -> InlineKeyboardMarkup:
    """Per-note open / edit / delete inline buttons."""
    kb = InlineKeyboardMarkup(row_width=3)
    for note in notes:
        slug  = note["slug"]
        title = note["title"][:30]
        kb.add(InlineKeyboardButton(f"📄 {title}", callback_data=f"note_open:{slug}"))
        kb.row(
            InlineKeyboardButton(_t(chat_id, "btn_edit"),   callback_data=f"note_edit:{slug}"),
            InlineKeyboardButton(_t(chat_id, "btn_delete"), callback_data=f"note_delete:{slug}"),
        )
    kb.add(InlineKeyboardButton(_t(chat_id, "note_btn_create"), callback_data="note_create"))
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
    _render(chat_id, "screens/note_view.yaml", {
        "note_title": _escape_md(slug.replace('_', ' ')),
        "note_content": _escape_md(text),
        "slug": slug,
    })


def _handle_note_raw(chat_id: int, slug: str) -> None:
    """Send the note body as an unformatted plain-text message — easy to copy."""
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    # Send without parse_mode — every character appears exactly as stored
    _render(chat_id, "screens/note_raw.yaml", {
        "note_content": text or _t(chat_id, "note_empty_body"),
        "slug": slug,
    })


def _start_note_edit(chat_id: int, slug: str) -> None:
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    lines = text.splitlines()
    note_title = lines[0].lstrip("# ").strip() if lines else ""
    _render(chat_id, "screens/note_edit.yaml", {
        "title": _escape_md(note_title),
        "slug": slug,
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
    bot.send_message(chat_id, note_body or _t(chat_id, "note_empty_body"), reply_markup=ForceReply(selective=False))


def _handle_note_delete(chat_id: int, slug: str) -> None:
    deleted = _delete_note_file(chat_id, slug)
    if deleted:
        bot.send_message(chat_id, _t(chat_id, "note_deleted"),
                         parse_mode="Markdown",
                         reply_markup=_notes_menu_keyboard(chat_id))
    else:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))


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
    })


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
    prompt = f"{_SYSTEM_PROMPT}\n\nTask: {user_text}"
    msg = bot.send_message(chat_id, "⏳ Generating command…")

    def _run():
        try:
            cmd_text = _ask_llm_strict(prompt, timeout=45)
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

        cmd_hash = hashlib.md5(cmd_clean.encode()).hexdigest()[:8]
        _st._pending_cmd[chat_id] = cmd_clean

        from telegram.bot_access import _confirm_keyboard
        reply = (
            "🖥️  I'll run the following command:\n\n"
            f"```\n{cmd_clean}\n```\n\n"
            "Confirm?"
        )
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

        # Build message list: past history + current user turn (with lang hint)
        current_content = _with_lang(chat_id, user_text)
        # ── RAG context injection ──────────────────────────────────────────
        import os as _os
        if RAG_ENABLED and not _os.path.exists(RAG_FLAG_FILE):
            try:
                from core.store import store as _store
                if _store.has_document_search():
                    _MAX_CHUNK_CHARS = 400
                    _MAX_RAG_CHARS   = 1600
                    _chunks = _store.search_fts(user_text, chat_id, top_k=RAG_TOP_K)
                    if _chunks:
                        _rag_ctx = "\n---\n".join(
                            c["chunk_text"][:_MAX_CHUNK_CHARS] for c in _chunks
                        )
                        _injected = len(_rag_ctx[:_MAX_RAG_CHARS])
                        current_content = (
                            f"[Relevant context:\n{_rag_ctx[:_MAX_RAG_CHARS]}]\n\n{current_content}"
                        )
                        log.debug("[RAG] injected %d chars from %d chunks", _injected, len(_chunks))
                        _store.log_rag_activity(chat_id, user_text, len(_chunks), _injected)
            except Exception as _rag_e:
                log.debug("[RAG] search failed: %s", _rag_e)
        messages = history_msgs + [{"role": "user", "content": current_content}]

        # Record the raw user text (without lang prefix) before calling the LLM
        add_to_history(chat_id, "user", user_text, call_id=call_id)

        response = ask_llm_with_history(messages, timeout=60)
        reply    = response if response else "❌ No response from LLM."

        # Record assistant turn
        add_to_history(chat_id, "assistant", reply, call_id=call_id)

        # Log which history messages were included in this LLM call
        try:
            db_log_llm_call(
                call_id, chat_id, LLM_PROVIDER,
                history_ids,
                sum(len(m["content"]) for m in messages),
                bool(response),
            )
        except Exception as _e:
            log.warning(f"[History] LLM call DB logging failed: {_e}")

        try:
            bot.edit_message_text(_truncate(reply), chat_id, msg.message_id,
                                  reply_markup=_back_keyboard())
        except Exception:
            bot.send_message(chat_id, _truncate(reply),
                             reply_markup=_back_keyboard())

    threading.Thread(target=_run, daemon=True).start()
