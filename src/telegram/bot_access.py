"""
bot_access.py — Core bot utilities usable by all handler modules.

Provides:
  - Role-based access control helpers (_is_allowed, _is_admin, _is_guest, _deny)
  - i18n string lookup (_t, _set_lang, _lang, _load_strings)
  - Language detection and LLM prompt language injection
  - Shared keyboard builders (_menu_keyboard, _back_keyboard, etc.)
  - Text helpers (_truncate, _safe_edit, _run_subprocess, _escape_tts, _escape_md)
  - LLM taris integration (_ask_taris, _get_active_model)
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.bot_config import (
    ADMIN_USERS, ALLOWED_USERS, DEVELOPER_USERS, BOT_NAME,
    ACTIVE_MODEL_FILE, TARIS_BIN,
    _STRINGS_FILE,
    log,
)
from core.bot_instance import bot
from core.bot_prompts import PROMPTS, fmt_prompt
from core.bot_state import _user_mode, _user_lang, _voice_opts, _user_audio, _dynamic_users

# ─────────────────────────────────────────────────────────────────────────────
# Access control
# ─────────────────────────────────────────────────────────────────────────────

def _is_allowed(chat_id: int) -> bool:
    """True for admins, full users, and dynamically added guests."""
    return (chat_id in ADMIN_USERS
            or chat_id in ALLOWED_USERS
            or chat_id in _dynamic_users)


def _is_admin(chat_id: int) -> bool:
    return chat_id in ADMIN_USERS


def _is_developer(chat_id: int) -> bool:
    """True if chat_id is in DEVELOPER_USERS (elevated system-chat access)."""
    return chat_id in DEVELOPER_USERS


def _is_guest(chat_id: int) -> bool:
    """All approved users get full access — no guest restrictions."""
    return False


def _deny(chat_id: int) -> None:
    bot.send_message(chat_id, _t(chat_id, "access_denied"))
    log.warning(f"[Access] denied chat_id={chat_id}")


# ─────────────────────────────────────────────────────────────────────────────
# i18n — string loading and lookup
# ─────────────────────────────────────────────────────────────────────────────

_SUPPORTED_LANGS: frozenset[str] = frozenset({"ru", "de", "en"})
_DEFAULT_LANG  = "ru"
_FALLBACK_LANG = "en"


def _load_strings(path: str) -> dict:
    """Load UI strings from JSON.  Exits with a clear error if missing."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"[strings] File not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[strings] JSON parse error in {path}: {exc}")


_STRINGS: dict[str, dict[str, str]] = _load_strings(_STRINGS_FILE)


def _set_lang(chat_id: int, from_user) -> None:
    """Store the best-supported UI language for this user ('ru' | 'de' | 'en')."""
    # Honour manually saved language preference (beats Telegram auto-detect)
    from telegram.bot_users import _find_registration
    saved = (_find_registration(chat_id) or {}).get("lang")
    if saved in ("ru", "en", "de"):
        _user_lang[chat_id] = saved
        return
    lc = (getattr(from_user, "language_code", "") or "").lower()
    if lc.startswith("ru"):
        _user_lang[chat_id] = "ru"
    elif lc.startswith("de"):
        _user_lang[chat_id] = "de"
    else:
        # Fall back to the configured default language (not hardcoded "en")
        # so that new users on a Russian-default instance get Russian.
        _user_lang[chat_id] = _DEFAULT_LANG


def _lang(chat_id: int) -> str:
    return _user_lang.get(chat_id, _DEFAULT_LANG)


def _t(chat_id: int, key: str, **kwargs) -> str:
    """Look up a localised string by key; falls back to key name."""
    lang = _lang(chat_id)
    text = _STRINGS.get(lang, _STRINGS.get("en", {})).get(key, key)
    kwargs.setdefault("bot_name", BOT_NAME)
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text


# ─────────────────────────────────────────────────────────────────────────────
# Language detection & LLM prompt injection
# ─────────────────────────────────────────────────────────────────────────────

_LANG_INSTRUCTION: dict[str, str] = PROMPTS["lang_instructions"]


def _detect_text_lang(text: str) -> Optional[str]:
    """
    Detect language from Unicode char composition.
    Cyrillic ≥ 40 % → 'ru', Latin ≥ 60 % → 'en', otherwise None.
    """
    cyrillic = sum(1 for c in text if "\u0400" <= c <= "\u04FF")
    latin    = sum(1 for c in text if c.isalpha() and ord(c) < 128)
    total    = cyrillic + latin
    if total < 3:
        return None
    if cyrillic / total >= 0.40:
        detected = "ru"
    elif latin / total >= 0.60:
        detected = "en"
    else:
        return None
    return detected if detected in _SUPPORTED_LANGS else None


def _resolve_lang(chat_id: int, user_text: str = "") -> str:
    """Resolve reply language: text detection > Telegram lang > Russian default."""
    if user_text:
        detected = _detect_text_lang(user_text)
        if detected:
            return detected
    tg_lang = _user_lang.get(chat_id)
    if tg_lang and tg_lang in _SUPPORTED_LANGS:
        return tg_lang
    return _DEFAULT_LANG if _DEFAULT_LANG in _SUPPORTED_LANGS else _FALLBACK_LANG


def _with_lang(chat_id: int, user_text: str) -> str:
    """Prepend security preamble + language instruction, then wrap user text."""
    from security.bot_security import SECURITY_PREAMBLE, _wrap_user_input
    lang = _resolve_lang(chat_id, user_text)
    lang_instr = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION[_FALLBACK_LANG])
    return SECURITY_PREAMBLE + lang_instr + _wrap_user_input(user_text)


def _with_lang_voice(chat_id: int, stt_text: str) -> str:
    """Like _with_lang but includes STT-error hint for low-confidence words ([?word])."""
    from security.bot_security import SECURITY_PREAMBLE, _wrap_user_input
    has_uncertain = bool(re.search(r'\[\?', stt_text))
    lang = _resolve_lang(chat_id, stt_text)
    instruction = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION[_FALLBACK_LANG])
    if has_uncertain:
        stt_hint = PROMPTS["stt_hints"].get(lang, PROMPTS["stt_hints"]["en"])
        return SECURITY_PREAMBLE + instruction + stt_hint + _wrap_user_input(stt_text)
    return SECURITY_PREAMBLE + instruction + _wrap_user_input(stt_text)


# ─────────────────────────────────────────────────────────────────────────────
# Text utilities
# ─────────────────────────────────────────────────────────────────────────────

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\u200D\uFE0F\u20E3]+",
    flags=re.UNICODE,
)


def _escape_tts(text: str) -> str:
    """Prepare text for Piper TTS: strip emoji, Markdown, collapse blank lines."""
    t = _EMOJI_RE.sub("", text)
    t = re.sub(r"\*+([^*\n]+)\*+", r"\1", t)
    t = re.sub(r"_+([^_\n]+)_+", r"\1", t)
    t = re.sub(r"`[^`]+`", "", t)
    t = re.sub(r"```.*?```", "", t, flags=re.DOTALL)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _escape_md(text: str) -> str:
    """Escape Markdown v1 special characters (* _ ` [) in free-form text."""
    return re.sub(r"([*_`\[])", r"\\\1", text)


def _truncate(text: str, limit: int = 3800) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n…_(truncated, {len(text)} total chars)_"


def _safe_edit(chat_id: int, msg_id: int, text: str, **kwargs) -> None:
    """Edit a message, silently ignoring 'message not modified' errors."""
    try:
        bot.edit_message_text(text, chat_id, msg_id, **kwargs)
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            log.debug(f"_safe_edit: {e}")


def _run_subprocess(cmd: list[str], timeout: int = 60,
                    env: Optional[dict] = None) -> tuple[int, str]:
    """Run a command and return (returncode, combined stdout+stderr output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            env=env or os.environ.copy(),
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output = (output + "\n" + result.stderr.strip()).strip()
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return -1, f"⏱ Command timed out after {timeout}s"
    except Exception as e:
        return -1, f"Error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# LLM integration
# ─────────────────────────────────────────────────────────────────────────────

def _get_active_model() -> str:
    """Return the admin-selected model name, or '' for config.json default."""
    try:
        return Path(ACTIVE_MODEL_FILE).read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _clean_taris_output(text: str) -> str:
    """
    Extract human-readable answer from taris stdout.

    Handles artefacts:
      1. Timestamp-prefixed log lines mixed into stdout
      2. "Taris:" section header line
      3. printf 'text' or printf "text" wrapper
      4. [emoji] bash -lc 'printf "text"' wrapper
    """
    clean_lines = []
    for line in text.splitlines():
        if re.match(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}", line):
            continue
        if re.match(r"^\[?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", line):
            continue
        if re.match(r"^Taris\s*:?\s*$", line, re.IGNORECASE):
            continue
        clean_lines.append(line)

    clean = "\n".join(clean_lines).strip()

    m = re.match(r"""^.*?bash\s+-lc\s+'printf\s+"(.*)"\s*'\s*$""", clean, re.DOTALL)
    if m:
        return m.group(1).replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'").strip()

    m = re.match(r"""^.*?bash\s+-lc\s+'printf\s+'\\''(.*)'\\''\s*$""", clean, re.DOTALL)
    if m:
        return m.group(1).replace("\\n", "\n").strip()

    m = re.match(r"^printf\s+'(.*)'$", clean, re.DOTALL)
    if not m:
        m = re.match(r'^printf\s+"(.*)"$', clean, re.DOTALL)
    if m:
        return m.group(1).replace("\\n", "\n").replace("\\'", "'").strip()

    return clean.replace("\\n", "\n")


def _ask_taris(prompt: str, timeout: int = 60) -> Optional[str]:
    """Call taris agent -m and return cleaned response text, or None on error."""
    try:
        cmd = [TARIS_BIN, "agent"]
        active_model = _get_active_model()
        if active_model:
            cmd += ["--model", active_model]
        cmd += ["-m", prompt]
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            env=os.environ.copy(),
        )
        out = result.stdout.strip()
        if result.returncode != 0 or not out:
            log.error(f"[taris] error rc={result.returncode}: {result.stderr[:300]}")
            return None
        return _clean_taris_output(out)
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        log.error(f"[taris] exception: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Keyboard builders
# ─────────────────────────────────────────────────────────────────────────────

def _menu_keyboard(chat_id: int = 0) -> InlineKeyboardMarkup:
    """Main menu keyboard filtered by the caller's role."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_digest"),  callback_data="digest"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_chat"),    callback_data="mode_chat"))
    if _is_admin(chat_id):    # System Chat is admin-only: executes commands on the Pi
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_system"), callback_data="mode_system"))
    if not _is_guest(chat_id):
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_notes"),    callback_data="menu_notes"))
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_calendar"), callback_data="menu_calendar"))
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_contacts"), callback_data="menu_contacts"))
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_docs"),     callback_data="menu_docs"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_profile"),  callback_data="profile"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_help"),     callback_data="help"))
    if _is_admin(chat_id):
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_error_protocol"), callback_data="errp_start"))
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_admin"),  callback_data="admin_menu"))
    return kb


def _back_keyboard(chat_id: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
    return kb


def _voice_back_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Back keyboard with optional 🔊/🔇 audio toggle."""
    kb = InlineKeyboardMarkup()
    if _voice_opts.get("user_audio_toggle"):
        audio_on = _user_audio.get(chat_id, True)
        lbl = _t(chat_id, "btn_mute_audio") if audio_on else _t(chat_id, "btn_unmute_audio")
        kb.add(InlineKeyboardButton(lbl, callback_data="voice_audio_toggle"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
    return kb


def _confirm_keyboard(cmd_hash: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅  Run",    callback_data=f"run:{cmd_hash}"),
        InlineKeyboardButton("❌  Cancel", callback_data="cancel"),
    )
    return kb


def _send_menu(chat_id: int, greeting: bool = True) -> None:
    _user_mode.pop(chat_id, None)
    text = _t(chat_id, "greet") if greeting else _t(chat_id, "choose")
    bot.send_message(chat_id, text,
                     parse_mode="Markdown",
                     reply_markup=_menu_keyboard(chat_id))
