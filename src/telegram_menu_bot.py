#!/usr/bin/env python3
"""
Picoclaw Telegram Menu Bot
==========================
Telegram bot with inline menu for picoclaw on Raspberry Pi.

Menus
-----
  📧 Mail Digest    — show last email digest (or trigger a fresh one)
  💬 Free Chat      — natural language chat via picoclaw LLM (no system access)
  🖥️  System Chat   — describe a task → LLM generates bash command
                       → user confirms → runs on Pi → shows output
  🎤 Voice Session  — tap to enter voice mode; then press the 🎤 mic button in
                       Telegram, record your question in Russian, and send it.
                       Bot downloads the OGG, runs Vosk STT offline, sends text
                       to picoclaw LLM, replies with text + Piper TTS voice note.
                       Voice messages are also processed without entering the mode.

Config (env vars or ~/.picoclaw/bot.env):
  BOT_TOKEN         Telegram bot token  (from @BotFather)
  ALLOWED_USERS     Comma-separated Telegram chat_ids allowed to use the bot
                    (full access: Mail, Free Chat, System Chat, Voice)
                    Example: ALLOWED_USERS=994963580
  ADMIN_USERS       Comma-separated chat_ids with admin privileges
                    Admins see all menus + 🔐 Admin; can add/remove guest users.
                    Defaults to ALLOWED_USERS if not set.
                    Example: ADMIN_USERS=994963580
  USERS_FILE        Path to runtime users file  (default ~/.picoclaw/users.json)
                    Stores guest users added via the Admin menu at runtime.
  PICOCLAW_BIN      path to picoclaw binary   (default /usr/bin/picoclaw)
  DIGEST_SCRIPT     path to gmail_digest.py  (default ~/.picoclaw/gmail_digest.py)
  LAST_DIGEST_FILE  path to last saved digest (default ~/.picoclaw/last_digest.txt)
  VOSK_MODEL_PATH   path to vosk Russian model dir
  PIPER_BIN         path to Piper TTS binary  (default /usr/local/bin/piper)
  PIPER_MODEL       path to Piper .onnx voice model
  XDG_RUNTIME_DIR   PipeWire runtime dir      (default /run/user/1000)
  VOICE_TIMING_DEBUG  set to 1/true to append per-step timing to voice replies
                      (for testing only — leave 0 in production)
  STRINGS_FILE        path to strings.json UI text file
                      (default: strings.json next to this script)

User roles:
  Admin    — chat_id in ADMIN_USERS: all menus + 🔐 Admin panel
  Full     — chat_id in ALLOWED_USERS (not admin): all menus except Admin
  Guest    — added at runtime by admin: Mail Digest, Free Chat, Voice Session only
"""

import logging
import io
import json
import os
import subprocess
import textwrap
import hashlib
import threading
import time
from pathlib import Path
from typing import Optional

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def _load_env_file(path: str) -> None:
    """Load KEY=VALUE pairs from a file into os.environ (skip comments)."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())
    except FileNotFoundError:
        pass

# Try loading credentials from bot.env then .pico_env
_load_env_file(os.path.expanduser("~/.picoclaw/bot.env"))
_load_env_file(os.path.expanduser("~/.picoclaw/.pico_env"))

BOT_TOKEN        = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
def _parse_allowed_users() -> set[int]:
    raw = (os.environ.get("ALLOWED_USERS")
           or os.environ.get("ALLOWED_USER")
           or os.environ.get("TELEGRAM_CHAT_ID", ""))
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids

ALLOWED_USERS: set[int] = _parse_allowed_users()

def _parse_admin_users() -> set[int]:
    raw = os.environ.get("ADMIN_USERS", "")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    # Default: all ALLOWED_USERS are admins if ADMIN_USERS not explicitly set
    return ids if ids else set(ALLOWED_USERS)

ADMIN_USERS: set[int] = _parse_admin_users()
USERS_FILE       = os.environ.get("USERS_FILE",
                       os.path.expanduser("~/.picoclaw/users.json"))
PICOCLAW_BIN     = os.environ.get("PICOCLAW_BIN", "/usr/bin/picoclaw")
PICOCLAW_CONFIG  = os.environ.get("PICOCLAW_CONFIG",
                       os.path.expanduser("~/.picoclaw/config.json"))
ACTIVE_MODEL_FILE = os.environ.get("ACTIVE_MODEL_FILE",
                       os.path.expanduser("~/.picoclaw/active_model.txt"))
DIGEST_SCRIPT    = os.environ.get("DIGEST_SCRIPT",
                                   os.path.expanduser("~/.picoclaw/gmail_digest.py"))
LAST_DIGEST_FILE = os.environ.get("LAST_DIGEST_FILE",
                                   os.path.expanduser("~/.picoclaw/last_digest.txt"))

# ─────────────────────────────────────────────────────────────────────────────
# Dynamic guest-user storage (persisted to USERS_FILE)
# ─────────────────────────────────────────────────────────────────────────────
import json as _json_mod

def _load_dynamic_users() -> set[int]:
    try:
        data = _json_mod.loads(Path(USERS_FILE).read_text(encoding="utf-8"))
        return set(int(x) for x in data.get("users", []))
    except Exception:
        return set()

def _save_dynamic_users() -> None:
    try:
        Path(USERS_FILE).write_text(
            _json_mod.dumps({"users": sorted(_dynamic_users)}, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"Failed to save users file: {e}")

# Populated after logging is set up (see bottom of config section)
_dynamic_users: set[int] = set()

# ─────────────────────────────────────────────────────────────────────────────
# Voice session config (mirrors defaults from voice_assistant.py)
# ─────────────────────────────────────────────────────────────────────────────
VOSK_MODEL_PATH    = os.environ.get("VOSK_MODEL_PATH",
                         os.path.expanduser("~/.picoclaw/vosk-model-small-ru"))
PIPER_BIN          = os.environ.get("PIPER_BIN",  "/usr/local/bin/piper")
PIPER_MODEL        = os.environ.get("PIPER_MODEL",
                         os.path.expanduser("~/.picoclaw/ru_RU-irina-medium.onnx"))
PIPEWIRE_RUNTIME   = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")

VOICE_SAMPLE_RATE     = 16000
VOICE_CHUNK_SIZE      = 4000      # 250 ms at 16 kHz
VOICE_SILENCE_TIMEOUT = 4.0       # seconds of silence → auto-stop
VOICE_MAX_DURATION    = 30.0      # hard session cap (seconds)
# When True, appends per-step timing footer to voice replies (test mode only)
VOICE_TIMING_DEBUG    = os.environ.get("VOICE_TIMING_DEBUG", "0").lower() in ("1", "true", "yes")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set. Add it to ~/.picoclaw/bot.env")
if not ALLOWED_USERS and not ADMIN_USERS:
    raise RuntimeError("ALLOWED_USERS (or ALLOWED_USER / TELEGRAM_CHAT_ID) not set. "
                       "Set to a comma-separated list of Telegram chat IDs.")

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.expanduser("~/.picoclaw/telegram_bot.log"),
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("pico-tgbot")

# Load dynamic users now that logging is available
_dynamic_users = _load_dynamic_users()

# ─────────────────────────────────────────────────────────────────────────────
# Session state (per chat_id)
# ─────────────────────────────────────────────────────────────────────────────

# mode: None | 'chat' | 'system'
_user_mode: dict[int, str] = {}
# pending confirmation: chat_id → bash command string
_pending_cmd: dict[int, str] = {}
# per-user language: 'ru' or 'en', set on first incoming message/callback
_user_lang: dict[int, str] = {}
_vosk_model_cache = None   # lazy-loaded Vosk model singleton
_pending_llm_key: dict[int, str] = {}  # chat_id → waiting for OpenAI API key input

# ─────────────────────────────────────────────────────────────────────────────
# Bot setup
# ─────────────────────────────────────────────────────────────────────────────

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────────────────────
# Access control
# ─────────────────────────────────────────────────────────────────────────────

def _is_allowed(chat_id: int) -> bool:
    """True for admins, full users, and dynamically added guests."""
    return chat_id in ADMIN_USERS or chat_id in ALLOWED_USERS or chat_id in _dynamic_users

def _is_admin(chat_id: int) -> bool:
    return chat_id in ADMIN_USERS

def _is_guest(chat_id: int) -> bool:
    """Guest = runtime-added user; cannot use System Chat or Admin."""
    return chat_id in _dynamic_users and chat_id not in ALLOWED_USERS and chat_id not in ADMIN_USERS

def _deny(chat_id: int) -> None:
    bot.send_message(chat_id, "⛔ Access denied.")
    log.warning(f"Denied access from chat_id={chat_id}")


# ─────────────────────────────────────────────────────────────────────────────
# i18n — language detection + string lookup
# Telegram language_code starts with 'ru' for Russian; everything else → English.
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# UI strings — loaded from strings.json (same directory as this script)
# ─────────────────────────────────────────────────────────────────────────────

_STRINGS_FILE = os.environ.get(
    "STRINGS_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "strings.json"),
)


def _load_strings(path: str) -> dict:
    """Load UI strings from a JSON file.  Exits with a clear error if missing."""
    try:
        with open(path, encoding="utf-8") as _f:
            return json.load(_f)
    except FileNotFoundError:
        raise SystemExit(f"[strings] File not found: {path}")
    except json.JSONDecodeError as _exc:
        raise SystemExit(f"[strings] JSON parse error in {path}: {_exc}")


_STRINGS: dict[str, dict[str, str]] = _load_strings(_STRINGS_FILE)


def _set_lang(chat_id: int, from_user) -> None:
    """Detect and store the user's preferred language (ru or en)."""
    lc = getattr(from_user, "language_code", "") or ""
    _user_lang[chat_id] = "ru" if lc.lower().startswith("ru") else "en"


def _lang(chat_id: int) -> str:
    """Return stored language code for this chat_id, default 'en'."""
    return _user_lang.get(chat_id, "en")


def _t(chat_id: int, key: str, **kwargs) -> str:
    """Look up a localised string by key for the given chat_id."""
    lang = _lang(chat_id)
    text = _STRINGS.get(lang, _STRINGS.get("en", {})).get(key, key)
    return text.format(**kwargs) if kwargs else text


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _menu_keyboard(chat_id: int = 0) -> InlineKeyboardMarkup:
    """Return the main menu keyboard filtered by the caller's role, in the user's language."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_digest"),  callback_data="digest"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_chat"),    callback_data="mode_chat"))
    if not _is_guest(chat_id):
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_system"), callback_data="mode_system"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_voice"),   callback_data="voice_session"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_help"),    callback_data="help"))
    if _is_admin(chat_id):
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_admin"),  callback_data="admin_menu"))
    return kb


def _back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙  Menu", callback_data="menu"))
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
    """Run a command and return (returncode, combined output)."""
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


def _ask_picoclaw(prompt: str, timeout: int = 60) -> Optional[str]:
    """Call picoclaw agent -m and return clean response text (no log lines)."""
    try:
        cmd = [PICOCLAW_BIN, "agent"]
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
            log.error(f"picoclaw error (rc={result.returncode}): {result.stderr[:300]}")
            return None
        return _clean_picoclaw_output(out)
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        log.error(f"picoclaw exception: {e}")
        return None


def _clean_picoclaw_output(text: str) -> str:
    """
    Extract the human-readable answer from picoclaw stdout.
    Handles two artefacts:
      1. Log lines mixed into stdout (timestamp prefixes)
      2. The LLM wrapping its answer in a printf '...' shell command
    """
    import re
    # Drop lines that look like picoclaw log entries
    clean_lines = []
    for line in text.splitlines():
        if re.match(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}", line):
            continue
        if re.match(r"^\[?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", line):
            continue
        clean_lines.append(line)

    clean = "\n".join(clean_lines).strip()

    # Strip  printf 'text'  or  printf "text"  wrapper if present
    m = re.match(r"^printf\s+'(.*)'$", clean, re.DOTALL)
    if not m:
        m = re.match(r'^printf\s+"(.*)"$', clean, re.DOTALL)
    if m:
        clean = m.group(1).replace("\\n", "\n").replace("\\'", "'").strip()

    return clean


# ─────────────────────────────────────────────────────────────────────────────
# Admin panel
# ─────────────────────────────────────────────────────────────────────────────

def _admin_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("➕  Add user",     callback_data="admin_add_user"),
        InlineKeyboardButton("📋  List users",   callback_data="admin_list_users"),
        InlineKeyboardButton("🗑   Remove user",  callback_data="admin_remove_user"),
        InlineKeyboardButton("🤖  Switch LLM",   callback_data="admin_llm_menu"),
        InlineKeyboardButton("🔙  Menu",          callback_data="menu"),
    )
    return kb


def _handle_admin_menu(chat_id: int) -> None:
    bot.send_message(
        chat_id,
        "🔐 *Admin Panel*",
        parse_mode="Markdown",
        reply_markup=_admin_keyboard(),
    )


def _handle_admin_list_users(chat_id: int) -> None:
    if not _dynamic_users:
        bot.send_message(chat_id, _t(chat_id, "no_guests"),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
        return
    lines = [f"• `{uid}`" for uid in sorted(_dynamic_users)]
    bot.send_message(
        chat_id,
        _t(chat_id, "guest_header") + "\n" + "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=_admin_keyboard(),
    )


def _start_admin_add_user(chat_id: int) -> None:
    _user_mode[chat_id] = "admin_add_user"
    bot.send_message(
        chat_id,
        _t(chat_id, "add_prompt"),
        parse_mode="Markdown",
    )


def _finish_admin_add_user(admin_id: int, text: str) -> None:
    text = text.strip()
    if not text.lstrip("-").isdigit():
        bot.send_message(admin_id, _t(admin_id, "bad_id"), parse_mode="Markdown")
        return
    uid = int(text)
    if uid in _dynamic_users:
        bot.send_message(admin_id, _t(admin_id, "already_guest", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
    elif uid in ALLOWED_USERS or uid in ADMIN_USERS:
        bot.send_message(admin_id, _t(admin_id, "already_full", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
    else:
        _dynamic_users.add(uid)
        _save_dynamic_users()
        log.info(f"Admin {admin_id} added guest user {uid}")
        bot.send_message(
            admin_id,
            _t(admin_id, "user_added", uid=uid),
            parse_mode="Markdown",
            reply_markup=_admin_keyboard(),
        )
    _user_mode.pop(admin_id, None)


def _start_admin_remove_user(chat_id: int) -> None:
    if not _dynamic_users:
        bot.send_message(chat_id, _t(chat_id, "no_guests_del"),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
        return
    _user_mode[chat_id] = "admin_remove_user"
    lst = "\n".join(f"• `{uid}`" for uid in sorted(_dynamic_users))
    bot.send_message(
        chat_id,
        _t(chat_id, "remove_prompt", lst=lst),
        parse_mode="Markdown",
    )


def _finish_admin_remove_user(admin_id: int, text: str) -> None:
    text = text.strip()
    if not text.lstrip("-").isdigit():
        bot.send_message(admin_id, _t(admin_id, "bad_id_rem"), parse_mode="Markdown")
        return
    uid = int(text)
    if uid in _dynamic_users:
        _dynamic_users.discard(uid)
        _save_dynamic_users()
        log.info(f"Admin {admin_id} removed guest user {uid}")
        bot.send_message(admin_id, _t(admin_id, "user_removed", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
    else:
        bot.send_message(admin_id, _t(admin_id, "user_not_found", uid=uid),
                         parse_mode="Markdown", reply_markup=_admin_keyboard())
    _user_mode.pop(admin_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# LLM model switcher
# ─────────────────────────────────────────────────────────────────────────────

def _get_active_model() -> str:
    """Return the admin-selected model name, or '' to use config.json default."""
    try:
        return Path(ACTIVE_MODEL_FILE).read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _set_active_model(model_name: str) -> None:
    """Persist the chosen model name (empty string = reset to config default)."""
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
    models = _get_picoclaw_models()
    current = _get_active_model()

    if not models:
        bot.send_message(chat_id, "⚠️ Cannot read picoclaw config.json.",
                         reply_markup=_admin_keyboard())
        return

    kb = InlineKeyboardMarkup(row_width=1)
    # OpenAI sub-menu button
    shared_openai_key = _get_shared_openai_key()
    openai_prefix = "✔️" if shared_openai_key else "⚠️"
    kb.add(InlineKeyboardButton(f"🔵 {openai_prefix} OpenAI ChatGPT ▶", callback_data="openai_llm_menu"))

    # Other models from config (exclude openai.com — shown in sub-menu)
    for m in models:
        name = m.get("model_name", "")
        if not name:
            continue
        if "openai.com" in m.get("api_base", ""):
            continue
        has_key = bool(m.get("api_key", "").strip())
        is_current = (name == current) or (not current and name == "openrouter-auto")
        prefix = "✅" if is_current else ("✔️" if has_key else "⚠️")
        kb.add(InlineKeyboardButton(f"{prefix}  {name}", callback_data=f"llm_select:{name}"))

    kb.add(InlineKeyboardButton("↩️  Reset to default", callback_data="llm_select:"))
    kb.add(InlineKeyboardButton("🔙  Admin", callback_data="admin_menu"))

    current_label = current or "(config default: openrouter-auto)"
    bot.send_message(
        chat_id,
        f"🤖 *Switch LLM*\n\nActive: `{current_label}`\n\n"
        f"✅ active   ✔️ key set   ⚠️ needs key\n\n"
        f"Tap *OpenAI ChatGPT* to select GPT-4o / GPT-4o-mini and set your API key.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


def _handle_set_llm(chat_id: int, model_name: str) -> None:
    """Apply LLM model selection and confirm to user."""
    _set_active_model(model_name)
    if model_name:
        models_map = {m["model_name"]: m for m in _get_picoclaw_models() if m.get("model_name")}
        m = models_map.get(model_name, {})
        has_key = bool(m.get("api_key", "").strip())
        warn = "" if has_key else "\n\n⚠️ _No API key set for this model — go to OpenAI ChatGPT menu to add one._"
        msg = f"✅ *LLM switched to:* `{model_name}`{warn}\n\n_All subsequent chat, system, and voice requests will use this model._"
    else:
        msg = "↩️ *LLM reset to config default* (`openrouter-auto`)."
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=_admin_keyboard())


# ── OpenAI ChatGPT sub-menu ───────────────────────────────────────────────────

_OPENAI_CATALOG = [
    ("gpt-4o",          "openai/gpt-4o",          "GPT-4o (flagship)"),
    ("gpt-4o-mini",     "openai/gpt-4o-mini",     "GPT-4o mini (fast & cheap)"),
    ("o3-mini",         "openai/o3-mini",          "o3-mini (reasoning)"),
    ("o1",              "openai/o1",               "o1 (advanced reasoning)"),
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
    """Set api_key for all openai.com models in config.json. Add catalog models if missing."""
    try:
        p = Path(PICOCLAW_CONFIG)
        cfg = json.loads(p.read_text(encoding="utf-8"))
        model_names = {m["model_name"] for m in cfg.get("model_list", []) if m.get("model_name")}
        for m in cfg.get("model_list", []):
            if "openai.com" in m.get("api_base", ""):
                m["api_key"] = api_key
        for name, model_id, _ in _OPENAI_CATALOG:
            if name not in model_names:
                cfg["model_list"].append({
                    "model_name": name,
                    "model": model_id,
                    "api_base": _OPENAI_API_BASE,
                    "api_key": api_key,
                })
        p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("[LLM] OpenAI key saved to config.json")
        return True
    except Exception as e:
        log.error(f"[LLM] Failed to save OpenAI key: {e}")
        return False


def _handle_openai_llm_menu(chat_id: int) -> None:
    """Show OpenAI ChatGPT model selection keyboard with key status."""
    models = {m["model_name"]: m for m in _get_picoclaw_models() if m.get("model_name")}
    shared_key = _get_shared_openai_key()
    current = _get_active_model()

    kb = InlineKeyboardMarkup(row_width=1)
    for name, _, description in _OPENAI_CATALOG:
        m = models.get(name, {})
        has_key = bool(m.get("api_key", "").strip()) or bool(shared_key)
        is_current = (name == current)
        prefix = "✅" if is_current else ("✔️" if has_key else "⚠️")
        kb.add(InlineKeyboardButton(f"{prefix} {name} — {description}",
                                    callback_data=f"llm_select:{name}"))

    key_label = (f"🔑 Update OpenAI Key (…{shared_key[-4:]})" if shared_key
                 else "🔑 Set OpenAI API Key")
    kb.add(InlineKeyboardButton(key_label, callback_data="llm_setkey_openai"))
    kb.add(InlineKeyboardButton("🔙  LLM Menu", callback_data="admin_llm_menu"))

    status_line = (f"🔑 Key: `…{shared_key[-4:]}` ✅ configured"
                   if shared_key else "🔑 Key: ⚠️ not set — tap below to add")
    bot.send_message(
        chat_id,
        f"🔵 *OpenAI ChatGPT Models*\n\n"
        f"{status_line}\n\n"
        f"✅ active   ✔️ key set   ⚠️ needs key\n\n"
        f"_One API key is shared by all OpenAI models._\n"
        f"_Get yours at: https://platform.openai.com/api-keys_",
        parse_mode="Markdown",
        reply_markup=kb,
    )


def _handle_llm_setkey_prompt(chat_id: int) -> None:
    """Ask admin to paste their OpenAI API key into chat."""
    _pending_llm_key[chat_id] = "openai"
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
    _pending_llm_key.pop(chat_id, None)
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
            f"_All OpenAI models now use this key._",
            parse_mode="Markdown",
        )
    else:
        bot.send_message(chat_id, "❌ Failed to save key — check Pi logs.", parse_mode="Markdown")
    _handle_openai_llm_menu(chat_id)


# ─────────────────────────────────────────────────────────────────────────────

def _handle_digest(chat_id: int) -> None:
    """
    Show last saved digest (instant) then optionally refresh.
    """
    last = Path(LAST_DIGEST_FILE)
    if last.exists() and last.stat().st_size > 0:
        text = last.read_text(encoding="utf-8", errors="replace").strip()
        age_h = (time.time() - last.stat().st_mtime) / 3600
        header = _t(chat_id, "digest_header", age=age_h)
        bot.send_message(chat_id, header + _truncate(text), parse_mode="Markdown")
    else:
        bot.send_message(chat_id, _t(chat_id, "digest_none"))
        _refresh_digest(chat_id)
        return

    # Offer refresh
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "btn_refresh_now"), callback_data="digest_refresh"),
        InlineKeyboardButton("🔙  Menu",                     callback_data="menu"),
    )
    bot.send_message(chat_id, _t(chat_id, "digest_hint"),
                     parse_mode="Markdown", reply_markup=kb)


def _refresh_digest(chat_id: int) -> None:
    """Run gmail_digest.py in background and report result."""
    msg = bot.send_message(chat_id, _t(chat_id, "fetching"))

    def _run():
        rc, out = _run_subprocess(
            ["python3", DIGEST_SCRIPT, "--stdout"],
            timeout=120,
        )
        if rc == 0 and out:
            text = out.strip()
        else:
            text = out or _t(chat_id, "digest_no_out")

        try:
            bot.edit_message_text(
                _t(chat_id, "digest_fresh") + _truncate(text),
                chat_id, msg.message_id,
                parse_mode="Markdown",
                reply_markup=_back_keyboard(),
            )
        except Exception:
            bot.send_message(chat_id, _t(chat_id, "digest_fresh") + _truncate(text),
                             parse_mode="Markdown", reply_markup=_back_keyboard())

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# System chat — natural language → bash → confirm → execute
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a Linux system assistant running on a Raspberry Pi 3 B+ "
    "(aarch64, Raspberry Pi OS Bookworm). The user will describe a task. "
    "Respond with ONLY a single safe bash command that accomplishes the task. "
    "No explanation, no markdown fences, no commentary — just the bare command."
)

def _handle_system_message(chat_id: int, user_text: str) -> None:
    """Translate natural language → bash command → ask for confirmation."""
    # Show typing indicator
    bot.send_chat_action(chat_id, "typing")

    prompt = f"{_SYSTEM_PROMPT}\n\nTask: {user_text}"
    msg = bot.send_message(chat_id, "⏳ Generating command…")

    def _run():
        cmd_text = _ask_picoclaw(prompt, timeout=45)
        if not cmd_text:
            bot.edit_message_text("❌ Could not generate a command. Try again.",
                                  chat_id, msg.message_id)
            return

        # Clean up: strip markdown fences if model added them anyway
        cmd_clean = cmd_text.strip().lstrip("`").rstrip("`").strip()
        if cmd_clean.startswith("bash\n"):
            cmd_clean = cmd_clean[5:].strip()

        # Store pending command, keyed by short hash
        cmd_hash = hashlib.md5(cmd_clean.encode()).hexdigest()[:8]
        _pending_cmd[chat_id] = cmd_clean

        reply = (
            f"🖥️  I'll run the following command:\n\n"
            f"```\n{cmd_clean}\n```\n\n"
            f"Confirm?"
        )
        try:
            bot.edit_message_text(
                reply, chat_id, msg.message_id,
                parse_mode="Markdown",
                reply_markup=_confirm_keyboard(cmd_hash),
            )
        except Exception:
            bot.send_message(chat_id, reply,
                             parse_mode="Markdown",
                             reply_markup=_confirm_keyboard(cmd_hash))

    threading.Thread(target=_run, daemon=True).start()


def _execute_pending_cmd(chat_id: int) -> None:
    """Execute the confirmed pending command and show output."""
    cmd = _pending_cmd.pop(chat_id, None)
    if not cmd:
        bot.send_message(chat_id, "⚠️ No pending command.", reply_markup=_back_keyboard())
        return

    msg = bot.send_message(chat_id, f"▶️  Running…\n```\n{cmd}\n```",
                            parse_mode="Markdown")

    def _run():
        rc, output = _run_subprocess(["bash", "-c", cmd], timeout=30)
        if not output:
            output = "(no output)"

        status = "✅" if rc == 0 else f"⚠️ exit {rc}"
        result = (
            f"{status} `{cmd[:60]}{'…' if len(cmd)>60 else ''}`\n\n"
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
    """Forward message to picoclaw agent and return response."""
    bot.send_chat_action(chat_id, "typing")
    msg = bot.send_message(chat_id, "⏳ Thinking…")

    def _run():
        response = _ask_picoclaw(user_text, timeout=60)
        reply = response if response else "❌ No response from picoclaw."
        try:
            bot.edit_message_text(_truncate(reply), chat_id, msg.message_id,
                                  reply_markup=_back_keyboard())
        except Exception:
            bot.send_message(chat_id, _truncate(reply),
                             reply_markup=_back_keyboard())

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Voice Session — on-demand mic → Vosk STT → picoclaw LLM → text + TTS audio
#
# Activation: tap "🎤 Voice Session" in the Telegram menu.
# The microphone opens immediately. The Telegram message is edited in real-time
# with the live transcription (Vosk partial results).
# Recording stops automatically on VOICE_SILENCE_TIMEOUT seconds of silence
# or when the user taps ⏹ Stop.
# The final transcript is sent to picoclaw agent; the text answer is displayed
# and a Piper TTS .ogg is sent as a Telegram voice note (requires ffmpeg).
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Voice Session ─ on-demand voice query via Telegram voice note
#
# How it works:
#   1. User taps "🎤 Voice Session" → bot enters voice mode and shows instructions
#   2. User records a voice message in Telegram (the mic button in the input bar)
#      and sends it to the bot
#   3. Bot downloads the OGG, converts to 16 kHz PCM via ffmpeg, runs Vosk STT
#   4. Recognised text is sent to picoclaw agent
#   5. Text answer is sent back + Piper TTS OGG voice note
#
# Works regardless of mode — any voice message sent to the bot is processed.
# ─────────────────────────────────────────────────────────────────────────────

def _get_vosk_model():
    """Lazy-load the Vosk Russian model (shared model dir with voice_assistant.py)."""
    global _vosk_model_cache
    if _vosk_model_cache is None:
        import vosk as _vosk_lib
        _vosk_lib.SetLogLevel(-1)   # suppress verbose Kaldi output
        _vosk_model_cache = _vosk_lib.Model(VOSK_MODEL_PATH)
    return _vosk_model_cache


def _tts_to_ogg(text: str) -> Optional[bytes]:
    """
    Synthesise text with Piper TTS, encode with ffmpeg as OGG Opus.
    Returns bytes suitable for bot.send_voice(), or None on failure.
    Requires: ffmpeg with libopus + piper (installed by setup_voice.sh).

    Uses two sequential subprocess.run() calls instead of Popen pipe-chaining.
    The Popen approach caused a deadlock: the parent process held piper.stdout
    open, so ffmpeg never received EOF on its stdin and blocked forever.
    Sequential approach: piper → raw PCM bytes → ffmpeg → OGG bytes.
    Text is truncated to TTS_MAX_CHARS to keep synthesis fast on Pi 3.
    """
    TTS_MAX_CHARS = 400   # ~50 words, ~25s audio on Pi 3 — fits well within 90s

    # Trim to whole sentences where possible, hard-cap at TTS_MAX_CHARS
    tts_text = text.strip()
    if len(tts_text) > TTS_MAX_CHARS:
        # Try to cut at last sentence boundary before the limit
        cut = tts_text[:TTS_MAX_CHARS]
        for sep in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
            idx = cut.rfind(sep)
            if idx > TTS_MAX_CHARS // 2:
                cut = cut[:idx + 1]
                break
        tts_text = cut.strip()

    try:
        # ── Step 1: Piper TTS → raw S16LE PCM ──────────────────────────────
        piper_result = subprocess.run(
            [PIPER_BIN, "--model", PIPER_MODEL, "--output-raw"],
            input=tts_text.encode("utf-8"),
            capture_output=True,
            timeout=60,
        )
        raw_pcm = piper_result.stdout
        if not raw_pcm:
            log.warning(f"TTS→OGG: piper produced no output "
                        f"(rc={piper_result.returncode}): "
                        f"{piper_result.stderr[:200]}")
            return None

        # ── Step 2: ffmpeg PCM → OGG Opus ─────────────────────────────────
        ff_result = subprocess.run(
            ["ffmpeg", "-y",
             "-f", "s16le", "-ar", "22050", "-ac", "1", "-i", "pipe:0",
             "-c:a", "libopus", "-b:a", "24k", "-f", "ogg", "pipe:1"],
            input=raw_pcm,
            capture_output=True,
            timeout=30,
        )
        ogg_bytes = ff_result.stdout
        if not ogg_bytes:
            log.warning(f"TTS→OGG: ffmpeg produced no output "
                        f"(rc={ff_result.returncode}): "
                        f"{ff_result.stderr[:200]}")
            return None
        return ogg_bytes

    except subprocess.TimeoutExpired as e:
        log.warning(f"TTS→OGG timeout: {e}")
        return None
    except Exception as e:
        log.warning(f"TTS→OGG failed: {e}")
        return None



def _start_voice_session(chat_id: int) -> None:
    """Enter voice mode — user sends a Telegram voice note to interact."""
    _user_mode[chat_id] = "voice"
    bot.send_message(
        chat_id,
        _t(chat_id, "voice_enter"),
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )


def _handle_voice_message(chat_id: int, voice_obj) -> None:
    """
    Process a Telegram voice note sent by the user:
      OGG download → ffmpeg decode→16kHz PCM → Vosk STT
        → picoclaw LLM → text answer + Piper TTS voice note.
    Runs in a background thread so the handler returns immediately.
    """
    msg = bot.send_message(chat_id, _t(chat_id, "recognizing"), parse_mode="Markdown")

    def _run():
        _timing: dict[str, float] = {}

        def _fmt_timing() -> str:
            """Return timing footer string (empty if VOICE_TIMING_DEBUG is off)."""
            if not VOICE_TIMING_DEBUG or not _timing:
                return ""
            parts = [f"{k} {v:.0f}s" for k, v in _timing.items()]
            return "\n\n⏱ " + " · ".join(parts)

        # ── Download OGG from Telegram ──────────────────────────────────────
        _ts = time.time()
        try:
            file_info = bot.get_file(voice_obj.file_id)
            ogg_bytes = bot.download_file(file_info.file_path)
        except Exception as e:
            _safe_edit(chat_id, msg.message_id,
                       _t(chat_id, "dl_error", e=e),
                       reply_markup=_back_keyboard())
            return
        _timing["Download"] = time.time() - _ts

        # ── OGG → 16 kHz mono S16LE raw PCM (ffmpeg) ───────────────────────
        _ts = time.time()
        try:
            ff = subprocess.Popen(
                ["ffmpeg", "-i", "pipe:0",
                 "-ar", str(VOICE_SAMPLE_RATE), "-ac", "1",
                 "-f", "s16le", "pipe:1"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            raw_pcm, _ = ff.communicate(input=ogg_bytes, timeout=30)
        except Exception as e:
            _safe_edit(chat_id, msg.message_id,
                       _t(chat_id, "decode_error", e=e),
                       reply_markup=_back_keyboard())
            return
        _timing["Convert"] = time.time() - _ts

        if not raw_pcm:
            _safe_edit(chat_id, msg.message_id,
                       _t(chat_id, "ffmpeg_no_data"),
                       reply_markup=_back_keyboard())
            return

        # ── Vosk STT ─────────────────────────────────────────────────────────
        _ts = time.time()
        try:
            import vosk as _vosk_lib
            import json as _json
            model = _get_vosk_model()
            rec = _vosk_lib.KaldiRecognizer(model, VOICE_SAMPLE_RATE)
            rec.SetWords(True)
            chunk = VOICE_CHUNK_SIZE * 2   # 2 bytes per S16 sample
            for i in range(0, len(raw_pcm), chunk):
                rec.AcceptWaveform(raw_pcm[i:i + chunk])
            text = _json.loads(rec.FinalResult()).get("text", "").strip()
        except Exception as e:
            _safe_edit(chat_id, msg.message_id,
                       _t(chat_id, "vosk_error", e=e),
                       reply_markup=_back_keyboard())
            return
        _timing["STT"] = time.time() - _ts

        if not text:
            _safe_edit(chat_id, msg.message_id,
                       _t(chat_id, "not_recognized"),
                       parse_mode="Markdown",
                       reply_markup=_back_keyboard())
            return

        # ── Show transcript, call picoclaw ────────────────────────────────────
        _safe_edit(chat_id, msg.message_id,
                   _t(chat_id, "you_said", text=text),
                   parse_mode="Markdown")

        _ts = time.time()
        response = _ask_picoclaw(text, timeout=90)
        _timing["LLM"] = time.time() - _ts

        if not response:
            response = _t(chat_id, "no_answer")

        # ── Text answer ───────────────────────────────────────────────────────
        bot.send_message(
            chat_id,
            f"🤖 *Picoclaw:*\n{_truncate(response)}{_fmt_timing()}",
            parse_mode="Markdown",
            reply_markup=_back_keyboard(),
        )

        # ── Piper TTS → send as Telegram voice note ───────────────────────────
        tts_msg = bot.send_message(chat_id, _t(chat_id, "gen_audio"),
                                   parse_mode="Markdown")
        _ts = time.time()
        ogg = _tts_to_ogg(response)
        _timing["TTS"] = time.time() - _ts

        if ogg:
            try:
                caption = _t(chat_id, "audio_caption") + _fmt_timing()
                bot.send_voice(chat_id, io.BytesIO(ogg), caption=caption)
                bot.delete_message(chat_id, tts_msg.message_id)
            except Exception as e:
                log.warning(f"send_voice failed: {e}")
                _safe_edit(chat_id, tts_msg.message_id,
                           _t(chat_id, "audio_error", e=e),
                           parse_mode="Markdown")
        else:
            _safe_edit(chat_id, tts_msg.message_id,
                       _t(chat_id, "audio_na"),
                       parse_mode="Markdown")

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Command handlers
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(message):
    if not _is_allowed(message.chat.id):
        _deny(message.chat.id)
        return
    _set_lang(message.chat.id, message.from_user)
    cid = message.chat.id
    bot.send_message(cid, _t(cid, "welcome"), parse_mode="Markdown",
                     reply_markup=_menu_keyboard(cid))


@bot.message_handler(commands=["menu"])
def cmd_menu(message):
    if not _is_allowed(message.chat.id):
        _deny(message.chat.id)
        return
    _set_lang(message.chat.id, message.from_user)
    _send_menu(message.chat.id)


@bot.message_handler(commands=["status"])
def cmd_status(message):
    if not _is_allowed(message.chat.id):
        _deny(message.chat.id)
        return
    _set_lang(message.chat.id, message.from_user)
    cid = message.chat.id
    mode = _user_mode.get(cid, "—")
    active_model = _get_active_model() or "default"

    # Query each service individually with a label
    services = [
        ("🤖 Telegram Bot",    "picoclaw-telegram"),
        ("🌐 AI Gateway",      "picoclaw-gateway"),
        ("🎤 Voice Assistant", "picoclaw-voice"),
    ]
    svc_lines = []
    for label, svc_name in services:
        _, state = _run_subprocess(["systemctl", "is-active", svc_name], timeout=5)
        state = state.strip()
        icon = "✅" if state == "active" else "❌"
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
# Callback query handlers
# ─────────────────────────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    cid = call.message.chat.id
    if not _is_allowed(cid):
        bot.answer_callback_query(call.id, "⛔ Access denied")
        return

    _set_lang(cid, call.from_user)   # update language on every interaction
    data = call.data
    bot.answer_callback_query(call.id)  # dismiss spinner

    if data == "menu":
        _user_mode.pop(cid, None)
        _pending_cmd.pop(cid, None)
        _send_menu(cid)

    elif data == "digest":
        _handle_digest(cid)

    elif data == "digest_refresh":
        _refresh_digest(cid)

    elif data == "mode_chat":
        _user_mode[cid] = "chat"
        bot.send_message(cid, _t(cid, "chat_enter"), parse_mode="Markdown")

    elif data == "mode_system":
        _user_mode[cid] = "system"
        bot.send_message(cid, _t(cid, "system_enter"), parse_mode="Markdown")

    elif data == "voice_session":
        _start_voice_session(cid)

    elif data == "help":
        if _is_admin(cid):
            help_key = "help_text_admin"
        elif _is_guest(cid):
            help_key = "help_text_guest"
        else:
            help_key = "help_text"
        bot.send_message(cid, _t(cid, help_key),
                         parse_mode="Markdown",
                         reply_markup=_back_keyboard())

    elif data == "admin_menu":
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_admin_menu(cid)

    elif data == "admin_add_user":
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _start_admin_add_user(cid)

    elif data == "admin_list_users":
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_admin_list_users(cid)

    elif data == "admin_remove_user":
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _start_admin_remove_user(cid)

    elif data == "admin_llm_menu":
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_admin_llm_menu(cid)

    elif data.startswith("llm_select:"):
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            model_name = data[len("llm_select:"):]
            _handle_set_llm(cid, model_name)

    elif data == "openai_llm_menu":
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_openai_llm_menu(cid)

    elif data == "llm_setkey_openai":
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_llm_setkey_prompt(cid)

    elif data == "cancel":
        _pending_cmd.pop(cid, None)
        bot.send_message(cid, _t(cid, "cancelled"), reply_markup=_back_keyboard())

    elif data.startswith("run:"):
        _execute_pending_cmd(cid)


# ─────────────────────────────────────────────────────────────────────────────
# Text message router
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=["text"])
def text_handler(message):
    cid = message.chat.id
    if not _is_allowed(cid):
        _deny(cid)
        return

    _set_lang(cid, message.from_user)

    # Admin is typing an API key
    if cid in _pending_llm_key:
        if _is_admin(cid):
            _handle_save_llm_key(cid, message.text)
        else:
            _pending_llm_key.pop(cid, None)
        return

    mode = _user_mode.get(cid)

    if mode is None:
        _send_menu(cid, greeting=False)
        return

    if mode == "admin_add_user":
        if _is_admin(cid):
            _finish_admin_add_user(cid, message.text)
        else:
            _user_mode.pop(cid, None)
            bot.send_message(cid, _t(cid, "admin_only"))
        return

    elif mode == "admin_remove_user":
        if _is_admin(cid):
            _finish_admin_remove_user(cid, message.text)
        else:
            _user_mode.pop(cid, None)
            bot.send_message(cid, _t(cid, "admin_only"))
        return

    if mode == "chat":
        _handle_chat_message(cid, message.text)

    elif mode == "system":
        _handle_system_message(cid, message.text)

    elif mode == "voice":
        bot.send_message(cid,
                         _t(cid, "voice_hint"),
                         parse_mode="Markdown",
                         reply_markup=_back_keyboard())


# ─────────────────────────────────────────────────────────────────────────────
# Voice message handler — processes Telegram voice notes (mic button)
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

def main():
    log.info("=" * 50)
    log.info("Pico Telegram Menu Bot starting")
    log.info(f"  Admin users  : {sorted(ADMIN_USERS)}")
    log.info(f"  Allowed users: {sorted(ALLOWED_USERS)}")
    log.info(f"  Guest users  : {sorted(_dynamic_users)}")
    log.info(f"  picoclaw     : {PICOCLAW_BIN}")
    log.info(f"  Digest script: {DIGEST_SCRIPT}")
    log.info("=" * 50)

    log.info("Polling Telegram…")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)


if __name__ == "__main__":
    main()
