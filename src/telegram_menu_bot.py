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
USERS_FILE            = os.environ.get("USERS_FILE",
                           os.path.expanduser("~/.picoclaw/users.json"))
REGISTRATIONS_FILE    = os.environ.get("REGISTRATIONS_FILE",
                           os.path.expanduser("~/.picoclaw/registrations.json"))
PICOCLAW_BIN     = os.environ.get("PICOCLAW_BIN", "/usr/bin/picoclaw")
PICOCLAW_CONFIG  = os.environ.get("PICOCLAW_CONFIG",
                       os.path.expanduser("~/.picoclaw/config.json"))
ACTIVE_MODEL_FILE = os.environ.get("ACTIVE_MODEL_FILE",
                       os.path.expanduser("~/.picoclaw/active_model.txt"))
DIGEST_SCRIPT    = os.environ.get("DIGEST_SCRIPT",
                                   os.path.expanduser("~/.picoclaw/gmail_digest.py"))
LAST_DIGEST_FILE = os.environ.get("LAST_DIGEST_FILE",
                                   os.path.expanduser("~/.picoclaw/last_digest.txt"))

# Bot version — bump this string with every deployment so admins get notified
BOT_VERSION           = "2026.3.19"
RELEASE_NOTES_FILE    = os.environ.get(
    "RELEASE_NOTES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "release_notes.json"),
)
LAST_NOTIFIED_FILE    = os.path.expanduser("~/.picoclaw/last_notified_version.txt")
NOTES_DIR             = os.environ.get("NOTES_DIR",
                                        os.path.expanduser("~/.picoclaw/notes"))

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
# Registration workflow (pending / approved / blocked)
# ─────────────────────────────────────────────────────────────────────────────

def _load_registrations() -> list[dict]:
    """Load registration list from disk."""
    try:
        data = _json_mod.loads(Path(REGISTRATIONS_FILE).read_text(encoding="utf-8"))
        return data.get("registrations", [])
    except Exception:
        return []


def _save_registrations(regs: list[dict]) -> None:
    try:
        Path(REGISTRATIONS_FILE).write_text(
            _json_mod.dumps({"registrations": regs}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"[Reg] save failed: {e}")


def _find_registration(chat_id: int) -> dict | None:
    for r in _load_registrations():
        if r.get("chat_id") == chat_id:
            return r
    return None


def _upsert_registration(chat_id: int, username: str, name: str,
                         status: str = "pending") -> None:
    """Add a new registration or update status/name if it already exists."""
    import datetime
    regs = _load_registrations()
    for r in regs:
        if r.get("chat_id") == chat_id:
            r["status"]   = status
            r["username"] = username
            r["name"]     = name
            _save_registrations(regs)
            return
    regs.append({
        "chat_id":   chat_id,
        "username":  username,
        "name":      name,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "status":    status,
    })
    _save_registrations(regs)


def _set_reg_status(chat_id: int, status: str) -> None:
    regs = _load_registrations()
    for r in regs:
        if r.get("chat_id") == chat_id:
            r["status"] = status
            _save_registrations(regs)
            return


def _get_pending_registrations() -> list[dict]:
    return [r for r in _load_registrations() if r.get("status") == "pending"]


def _is_blocked_reg(chat_id: int) -> bool:
    r = _find_registration(chat_id)
    return r is not None and r.get("status") == "blocked"


def _is_pending_reg(chat_id: int) -> bool:
    r = _find_registration(chat_id)
    return r is not None and r.get("status") == "pending"

# ─────────────────────────────────────────────────────────────────────────────
# Voice session config (mirrors defaults from voice_assistant.py)
# ─────────────────────────────────────────────────────────────────────────────
VOSK_MODEL_PATH    = os.environ.get("VOSK_MODEL_PATH",
                         os.path.expanduser("~/.picoclaw/vosk-model-small-ru"))
PIPER_BIN          = os.environ.get("PIPER_BIN",  "/usr/local/bin/piper")
PIPER_MODEL        = os.environ.get("PIPER_MODEL",
                         os.path.expanduser("~/.picoclaw/ru_RU-irina-medium.onnx"))
PIPER_MODEL_TMPFS  = os.path.join("/dev/shm/piper",
                         os.path.basename(os.path.expanduser("~/.picoclaw/ru_RU-irina-medium.onnx")))
PIPER_MODEL_LOW    = os.environ.get("PIPER_MODEL_LOW",
                         os.path.expanduser("~/.picoclaw/ru_RU-irina-low.onnx"))
WHISPER_BIN        = os.environ.get("WHISPER_BIN",  "/usr/local/bin/whisper-cpp")
WHISPER_MODEL      = os.environ.get("WHISPER_MODEL",
                         os.path.expanduser("~/.picoclaw/ggml-tiny.bin"))
PIPEWIRE_RUNTIME   = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")

VOICE_SAMPLE_RATE     = 16000
VOICE_CHUNK_SIZE      = 4000      # 250 ms at 16 kHz
VOICE_SILENCE_TIMEOUT = 4.0       # seconds of silence → auto-stop
VOICE_MAX_DURATION    = 30.0      # hard session cap (seconds)
TTS_MAX_CHARS         = 600       # ~75 words / ~25 s of audio on Pi 3
# When True, appends per-step timing footer to voice replies (test mode only)
VOICE_TIMING_DEBUG    = os.environ.get("VOICE_TIMING_DEBUG", "0").lower() in ("1", "true", "yes")

# ─────────────────────────────────────────────────────────────────────────────
# Voice pipeline optimization feature flags
# All OFF by default — enable via Admin → ⚡ Voice Opts menu.
# Settings persist in ~/.picoclaw/voice_opts.json.
# ─────────────────────────────────────────────────────────────────────────────
_VOICE_OPTS_FILE     = os.path.expanduser("~/.picoclaw/voice_opts.json")
_PENDING_TTS_FILE    = os.path.expanduser("~/.picoclaw/pending_tts.json")
_VOICE_OPTS_DEFAULTS: dict = {
    "silence_strip":     False,   # #1: strip leading/trailing silence (ffmpeg)
    "low_sample_rate":   False,   # #3: 8 kHz instead of 16 kHz for Vosk STT
    "warm_piper":        False,   # #4: pre-warm Piper ONNX model at bot startup
    "parallel_tts":      False,   # #5: start TTS thread immediately after LLM
    "user_audio_toggle": False,   # #9: show 🔊/🔇 per-voice-reply audio toggle
    "tmpfs_model":       False,   # #10: copy Piper ONNX to /dev/shm (RAM disk) for ~10x faster load
    # §5.3 improvements (all default OFF — current behaviour unchanged)
    "vad_prefilter":     False,   # §5.3: webrtcvad silence/noise gate before Vosk STT
    "whisper_stt":       False,   # §5.3: use whisper.cpp tiny instead of Vosk for STT
    "piper_low_model":   False,   # §5.3: use ru_RU-irina-low.onnx (faster, smaller TTS)
    "persistent_piper":  False,   # §5.3: keep a warm Piper process alive → ONNX stays in page cache
}

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
_vosk_model_cache = None          # lazy-loaded Vosk model singleton
_persistent_piper_proc = None    # §5.3 persistent_piper: keeps the Piper ONNX hot in page cache
_pending_llm_key: dict[int, str] = {}  # chat_id → waiting for OpenAI API key input
_user_audio: dict[int, bool] = {}      # chat_id → True=audio on (default); used when user_audio_toggle enabled
_pending_note: dict[int, dict] = {}   # chat_id → {"step": "title"|"content"|"edit_content", "slug": str, "title": str}

# ─────────────────────────────────────────────────────────────────────────────
# Voice optimization options — load / save / runtime state
# ─────────────────────────────────────────────────────────────────────────────

def _load_voice_opts() -> dict:
    """Load voice optimization flags from disk (all OFF by default)."""
    try:
        saved = json.loads(Path(_VOICE_OPTS_FILE).read_text(encoding="utf-8"))
        opts = dict(_VOICE_OPTS_DEFAULTS)
        opts.update({k: v for k, v in saved.items() if k in opts})
        return opts
    except FileNotFoundError:
        return dict(_VOICE_OPTS_DEFAULTS)
    except Exception as e:
        log.warning(f"[VoiceOpts] load failed: {e}")
        return dict(_VOICE_OPTS_DEFAULTS)


def _save_voice_opts() -> None:
    """Persist voice optimization flags to disk."""
    try:
        Path(_VOICE_OPTS_FILE).write_text(
            json.dumps(_voice_opts, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning(f"[VoiceOpts] save failed: {e}")


_voice_opts: dict = _load_voice_opts()

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


# Languages the voice assistant supports (must match _LANG_INSTRUCTION keys)
_SUPPORTED_LANGS: frozenset[str] = frozenset({"ru", "en"})
_DEFAULT_LANG  = "ru"   # primary default (Russian)
_FALLBACK_LANG = "en"   # backup when default unavailable


def _set_lang(chat_id: int, from_user) -> None:
    """Store the best-supported UI language for this user (ru / en)."""
    lc = (getattr(from_user, "language_code", "") or "").lower()
    # Map Telegram language_code to a supported language (ru | en).
    # For UI strings we keep the nearest match; for LLM replies the
    # priority chain in _resolve_lang() applies separately.
    _user_lang[chat_id] = "ru" if lc.startswith("ru") else "en"


def _lang(chat_id: int) -> str:
    """Return stored UI language for this chat_id, default Russian."""
    return _user_lang.get(chat_id, _DEFAULT_LANG)


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
    if not _is_guest(chat_id):
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_notes"),  callback_data="menu_notes"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_help"),    callback_data="help"))
    if _is_admin(chat_id):
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_admin"),  callback_data="admin_menu"))
    return kb


def _back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙  Menu", callback_data="menu"))
    return kb


def _voice_back_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Back keyboard extended with optional 🔊/🔇 audio toggle (when user_audio_toggle is enabled)."""
    kb = InlineKeyboardMarkup()
    if _voice_opts.get("user_audio_toggle"):
        audio_on = _user_audio.get(chat_id, True)
        lbl = "🔇  Mute audio" if audio_on else "🔊  Unmute audio"
        kb.add(InlineKeyboardButton(lbl, callback_data="voice_audio_toggle"))
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
    Handles artefacts:
      1. Log lines mixed into stdout (timestamp prefixes)
      2. "Picoclaw:" section header line
      3. printf 'text' or printf "text" bare wrapper
      4. [emoji] bash -lc 'printf "text"' wrapper (picoclaw agent command format)
    """
    import re
    # Drop lines that look like picoclaw log entries or section headers
    clean_lines = []
    for line in text.splitlines():
        if re.match(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}", line):
            continue
        if re.match(r"^\[?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", line):
            continue
        # Drop bare "Picoclaw:" header emitted by the agent binary
        if re.match(r"^Picoclaw\s*:?\s*$", line, re.IGNORECASE):
            continue
        clean_lines.append(line)

    clean = "\n".join(clean_lines).strip()

    # Pattern 1: bash -lc 'printf "text"'  (with optional leading emoji/chars)
    # e.g.  🦞 bash -lc 'printf "Hello world"'
    m = re.match(r"""^.*?bash\s+-lc\s+'printf\s+"(.*)"\s*'\s*$""", clean, re.DOTALL)
    if m:
        return m.group(1).replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'").strip()

    # Pattern 2: bash -lc 'printf '\''text'\'''  (single-quoted printf inside bash)
    m = re.match(r"""^.*?bash\s+-lc\s+'printf\s+'\\''(.*)'\\''\s*$""", clean, re.DOTALL)
    if m:
        return m.group(1).replace("\\n", "\n").strip()

    # Pattern 3: bare printf 'text'  or  printf "text"
    m = re.match(r"^printf\s+'(.*)'$", clean, re.DOTALL)
    if not m:
        m = re.match(r'^printf\s+"(.*)"$', clean, re.DOTALL)
    if m:
        return m.group(1).replace("\\n", "\n").replace("\\'", "'").strip()

    # Unescape literal \n that some models emit as two characters (outside printf)
    clean = clean.replace("\\n", "\n")
    return clean


# ─────────────────────────────────────────────────────────────────────────────
# Language enforcement — injected into every LLM prompt
# ─────────────────────────────────────────────────────────────────────────────

_LANG_INSTRUCTION: dict[str, str] = {
    "ru": (
        "Отвечай строго на русском языке. "
        "Не используй эмоджи, смайлики и символы. "
        "Отвечай по существу (3–6 предложений).\n\n"
    ),
    "en": (
        "Reply in English only. "
        "Do not use emoji or emoticons. "
        "Keep the answer informative (3–6 sentences).\n\n"
    ),
}


def _detect_text_lang(text: str) -> str | None:
    """
    Detect the language of *text* from Unicode character composition.
    Returns a key from _SUPPORTED_LANGS, or None when undetermined.

    Heuristic:
      - significant Cyrillic  (≥40 % of alpha chars) → 'ru'
      - significant Latin     (≥60 % of alpha chars) → 'en'
      - otherwise → None  (fall through to Telegram / default)
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
    """
    Resolve the reply language following the priority chain:
      1. Language detected from the question text           (if supported)
      2. Telegram UI language stored for this user          (if supported)
      3. Russian (_DEFAULT_LANG)  — primary default
      4. English (_FALLBACK_LANG) — backup
    """
    # Priority 1: question language
    if user_text:
        detected = _detect_text_lang(user_text)
        if detected:
            return detected
    # Priority 2: Telegram user language
    tg_lang = _user_lang.get(chat_id)
    if tg_lang and tg_lang in _SUPPORTED_LANGS:
        return tg_lang
    # Priority 3: Russian default
    if _DEFAULT_LANG in _SUPPORTED_LANGS:
        return _DEFAULT_LANG
    # Priority 4: English backup
    return _FALLBACK_LANG


def _with_lang(chat_id: int, user_text: str) -> str:
    """Prepend a language-enforcement instruction to any user → LLM prompt."""
    lang = _resolve_lang(chat_id, user_text)
    instruction = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION.get(_FALLBACK_LANG, ""))
    return instruction + user_text


def _with_lang_voice(chat_id: int, stt_text: str) -> str:
    """
    Like _with_lang but adds an STT-error hint when low-confidence words are
    present (marked as [?word] by the Vosk confidence filter).
    The LLM is instructed to silently correct them using context.
    """
    import re as _re
    has_uncertain = bool(_re.search(r'\[\?', stt_text))
    lang = _resolve_lang(chat_id, stt_text)
    instruction = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION.get(_FALLBACK_LANG, ""))
    if has_uncertain:
        if lang == "ru":
            stt_hint = (
                "Следующий текст — результат автоматического распознавания речи. "
                "Слова в скобках [?слово] распознаны с низкой уверенностью — "
                "исправь их по контексту и ответь на исходный вопрос. "
                "Не упоминай исправления явно.\n\n"
            )
        else:
            stt_hint = (
                "The following text was produced by automatic speech recognition. "
                "Words marked [?word] were recognized with low confidence — "
                "correct them using context and answer the original question. "
                "Do not mention the corrections.\n\n"
            )
        return instruction + stt_hint + stt_text
    return instruction + stt_text


# Comprehensive emoji / Unicode pictograph pattern used by _escape_tts()
import re as _re_module
_EMOJI_RE = _re_module.compile(
    "[\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\u200D\uFE0F\u20E3]+",
    flags=_re_module.UNICODE,
)


def _escape_tts(text: str) -> str:
    """
    Prepare text for Piper TTS:
    - Strip all emoji / Unicode pictographs (Piper reads them as Russian words)
    - Strip remaining Markdown syntax
    - Collapse multiple blank lines
    """
    import re as _re
    t = _EMOJI_RE.sub("", text)
    # Strip Markdown
    t = _re.sub(r"\*+([^*\n]+)\*+", r"\1", t)         # **bold** / *italic*
    t = _re.sub(r"_+([^_\n]+)_+", r"\1", t)           # __bold__ / _italic_
    t = _re.sub(r"`[^`]+`", "", t)                     # `code`
    t = _re.sub(r"```.*?```", "", t, flags=_re.DOTALL) # code blocks
    t = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)  # [link](url)
    t = _re.sub(r"\n{3,}", "\n\n", t)                  # collapse blank lines
    return t.strip()


def _escape_md(text: str) -> str:
    """Escape Markdown v1 special characters in free-form LLM response text."""
    import re as _re
    # Escape the four chars Telegram Markdown v1 treats as special: * _ ` [
    return _re.sub(r"([*_`\[])", r"\\\1", text)


# ─────────────────────────────────────────────────────────────────────────────
# Admin panel
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
# Registration — admin actions: approve / block
# ─────────────────────────────────────────────────────────────────────────────

def _handle_admin_pending_users(chat_id: int) -> None:
    """Show all pending registration requests with approve/block buttons."""
    pending = _get_pending_registrations()
    if not pending:
        bot.send_message(chat_id, _t(chat_id, "no_pending_regs"),
                         reply_markup=_admin_keyboard())
        return
    for reg in pending:
        uid   = reg.get("chat_id")
        uname = reg.get("username", "")
        name  = reg.get("name", "")
        ts    = reg.get("timestamp", "")[:16].replace("T", " ")
        # Escape user-supplied strings to prevent Markdown parse failures
        uname_disp = f"@{_escape_md(uname)}" if uname else "(no username)"
        name_disp  = _escape_md(name) if name else "(not set)"
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("\u2705  Approve", callback_data=f"reg_approve:{uid}"),
            InlineKeyboardButton("\U0001f6ab  Block",   callback_data=f"reg_block:{uid}"),
        )
        text = (
            f"\U0001f464 *Pending registration*\n\n"
            f"ID: `{uid}`\n"
            f"Username: {uname_disp}\n"
            f"Name: {name_disp}\n"
            f"Time: {ts}"
        )
        try:
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            log.warning(f"[Reg] pending_users send failed: {e}")
            import re as _re_pu
            bot.send_message(chat_id, _re_pu.sub(r"[*_`]", "", text), reply_markup=kb)


def _do_approve_registration(admin_id: int, target_id: int) -> None:
    """Approve a pending registration: add to guests and notify user."""
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
    _dynamic_users.add(target_id)
    _save_dynamic_users()
    log.info(f"[Reg] Admin {admin_id} approved user {target_id}")
    bot.send_message(admin_id, f"✅ User `{target_id}` approved and added as guest.",
                     parse_mode="Markdown", reply_markup=_admin_keyboard())
    try:
        bot.send_message(target_id, _t(target_id, "reg_approved"),
                         parse_mode="Markdown",
                         reply_markup=_menu_keyboard(target_id))
    except Exception as e:
        log.warning(f"[Reg] Cannot notify approved user {target_id}: {e}")


def _do_block_registration(admin_id: int, target_id: int) -> None:
    """Block a registration request: mark blocked and optionally notify user."""
    _set_reg_status(target_id, "blocked")
    _dynamic_users.discard(target_id)
    _save_dynamic_users()
    log.info(f"[Reg] Admin {admin_id} blocked user {target_id}")
    bot.send_message(admin_id, f"🚫 User `{target_id}` blocked.",
                     parse_mode="Markdown", reply_markup=_admin_keyboard())
    try:
        bot.send_message(target_id, _t(target_id, "reg_declined"))
    except Exception as e:
        log.warning(f"[Reg] Cannot notify blocked user {target_id}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Notes System — per-user Markdown note files in ~/.picoclaw/notes/<chat_id>/
# ─────────────────────────────────────────────────────────────────────────────

import re as _notes_re


def _slug(title: str) -> str:
    """Convert a note title to a safe filename slug (lowercase, underscores)."""
    s = title.lower().strip()
    s = _notes_re.sub(r"[^\w\s\u0400-\u04ff-]", "", s)  # keep letters, digits, cyrillic, hyphens
    s = _notes_re.sub(r"[\s]+", "_", s)
    s = s.strip("_")
    return s[:60] or "note"


def _notes_user_dir(chat_id: int) -> Path:
    """Return (and create) the per-user notes directory."""
    p = Path(NOTES_DIR) / str(chat_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _list_notes_for(chat_id: int) -> list[dict]:
    """Return list of {slug, title, mtime} sorted by modification time (newest first)."""
    d = _notes_user_dir(chat_id)
    notes = []
    for f in sorted(d.glob("*.md"), key=lambda x: -x.stat().st_mtime):
        try:
            first_line = f.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        except Exception:
            first_line = f.stem
        notes.append({"slug": f.stem, "title": first_line, "mtime": f.stat().st_mtime})
    return notes


def _load_note_text(chat_id: int, slug: str) -> Optional[str]:
    """Return note file contents or None if not found."""
    p = _notes_user_dir(chat_id) / f"{slug}.md"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def _save_note_file(chat_id: int, slug: str, content: str) -> None:
    """Write note file (creates or overwrites)."""
    p = _notes_user_dir(chat_id) / f"{slug}.md"
    p.write_text(content, encoding="utf-8")
    log.info(f"[Notes] Saved note '{slug}' for user {chat_id}")


def _delete_note_file(chat_id: int, slug: str) -> bool:
    """Delete a note file. Returns True if deleted, False if not found."""
    p = _notes_user_dir(chat_id) / f"{slug}.md"
    if p.exists():
        p.unlink()
        log.info(f"[Notes] Deleted note '{slug}' for user {chat_id}")
        return True
    return False


def _notes_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Notes main submenu."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "note_btn_create"),  callback_data="note_create"),
        InlineKeyboardButton(_t(chat_id, "note_btn_list"),    callback_data="note_list"),
        InlineKeyboardButton("🔙  Menu",                       callback_data="menu"),
    )
    return kb


def _notes_list_keyboard(chat_id: int, notes: list[dict]) -> InlineKeyboardMarkup:
    """Show per-note open/edit/delete inline buttons."""
    kb = InlineKeyboardMarkup(row_width=3)
    for note in notes:
        slug  = note["slug"]
        title = note["title"][:30]
        kb.add(InlineKeyboardButton(f"📄 {title}", callback_data=f"note_open:{slug}"))
        kb.row(
            InlineKeyboardButton("✏️ Edit",   callback_data=f"note_edit:{slug}"),
            InlineKeyboardButton("🗑 Delete",  callback_data=f"note_delete:{slug}"),
        )
    kb.add(InlineKeyboardButton(_t(chat_id, "note_btn_create"), callback_data="note_create"))
    kb.add(InlineKeyboardButton("🔙  Menu", callback_data="menu"))
    return kb


def _handle_notes_menu(chat_id: int) -> None:
    bot.send_message(
        chat_id,
        _t(chat_id, "note_menu_header"),
        parse_mode="Markdown",
        reply_markup=_notes_menu_keyboard(chat_id),
    )


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
    _user_mode[chat_id] = "note_add_title"
    _pending_note[chat_id] = {"step": "title"}
    bot.send_message(chat_id, _t(chat_id, "note_create_prompt_title"),
                     parse_mode="Markdown")


def _handle_note_open(chat_id: int, slug: str) -> None:
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    # Show note with Edit / Back buttons
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("✏️ Edit",   callback_data=f"note_edit:{slug}"),
        InlineKeyboardButton("🗑 Delete",  callback_data=f"note_delete:{slug}"),
    )
    kb.add(InlineKeyboardButton("📋 All Notes", callback_data="note_list"))
    kb.add(InlineKeyboardButton("🔙  Menu",      callback_data="menu"))
    bot.send_message(chat_id,
                     f"📄 *{_escape_md(slug.replace('_', ' '))}*\n\n{_escape_md(text)}",
                     parse_mode="Markdown",
                     reply_markup=kb)


def _start_note_edit(chat_id: int, slug: str) -> None:
    text = _load_note_text(chat_id, slug)
    if text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return
    _user_mode[chat_id] = "note_edit_content"
    _pending_note[chat_id] = {"step": "edit_content", "slug": slug}
    note_title = text.splitlines()[0].lstrip("# ").strip()
    bot.send_message(
        chat_id,
        _t(chat_id, "note_edit_prompt", title=_escape_md(note_title)),
        parse_mode="Markdown",
    )


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
# Voice pipeline optimization admin menu
# ─────────────────────────────────────────────────────────────────────────────

def _handle_voice_opts_menu(chat_id: int) -> None:
    """Show voice optimization toggle panel for admins."""
    def _flag(key: str) -> str:
        return "✅" if _voice_opts.get(key) else "◻️"

    kb = InlineKeyboardMarkup(row_width=1)
    opts_rows = [
        ("silence_strip",     f"{_flag('silence_strip')}  Silence strip  ·  −6s STT"),
        ("low_sample_rate",   f"{_flag('low_sample_rate')}  8 kHz sample rate  ·  −7s STT"),
        ("warm_piper",        f"{_flag('warm_piper')}  Warm Piper cache  ·  −15s TTS"),
        ("parallel_tts",      f"{_flag('parallel_tts')}  Parallel TTS thread  ·  text-first UX"),
        ("user_audio_toggle", f"{_flag('user_audio_toggle')}  Per-user audio 🔊/🔇 toggle"),
        ("tmpfs_model",       f"{_flag('tmpfs_model')}  Piper model in RAM (/dev/shm)  ·  −10s TTS load"),
        # §5.3 new opts
        ("vad_prefilter",     f"{_flag('vad_prefilter')}  VAD pre-filter (webrtcvad)  ·  −3s STT"),
        ("whisper_stt",       f"{_flag('whisper_stt')}  Whisper STT (whisper.cpp)  ·  +accuracy"),
        ("piper_low_model",   f"{_flag('piper_low_model')}  Piper low model  ·  −13s TTS"),
        ("persistent_piper",  f"{_flag('persistent_piper')}  Persistent Piper process  ·  ONNX hot"),
    ]
    for key, label in opts_rows:
        kb.add(InlineKeyboardButton(label, callback_data=f"voice_opt_toggle:{key}"))
    kb.add(InlineKeyboardButton("🔙  Admin", callback_data="admin_menu"))

    active = [k for k, v in _voice_opts.items() if v]
    status = ("Active: " + ", ".join(active)) if active else "All OFF — stable defaults"
    # Escape key names (contain underscores) so Markdown parser doesn't treat them as italics
    status_esc = _escape_md(status)
    text = (
        f"⚡ *Voice Pipeline Optimisations*\n\n"
        f"Default: all OFF (stable baseline). Toggle to test individually.\n"
        f"Settings persist across restarts.\n\n"
        f"_{status_esc}_"
    )
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        log.warning(f"[VoiceOpts] Markdown failed: {e}")
        import re as _re_vo
        bot.send_message(chat_id, _re_vo.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_voice_opt_toggle(chat_id: int, key: str) -> None:
    """Toggle one voice optimization flag and refresh the menu."""
    if key not in _VOICE_OPTS_DEFAULTS:
        return
    _voice_opts[key] = not _voice_opts.get(key, False)
    _save_voice_opts()
    state = "ON ✅" if _voice_opts[key] else "OFF ◻️"
    log.info(f"[VoiceOpts] {key} → {state} (by admin {chat_id})")
    # warm_piper: pre-warm immediately when enabled
    if key == "warm_piper" and _voice_opts[key]:
        threading.Thread(target=_warm_piper_cache, daemon=True).start()
        bot.send_message(chat_id, "⚡ _Warming Piper cache in background…_",
                         parse_mode="Markdown")
    # persistent_piper: start/stop keepalive process
    if key == "persistent_piper":
        if _voice_opts[key]:
            threading.Thread(target=_start_persistent_piper, daemon=True).start()
            bot.send_message(chat_id, "⚡ _Starting persistent Piper process…_",
                             parse_mode="Markdown")
        else:
            threading.Thread(target=_stop_persistent_piper, daemon=True).start()
    _handle_voice_opts_menu(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
# Release Notes — load, format, notify admins, admin menu handler
# ─────────────────────────────────────────────────────────────────────────────

def _load_release_notes() -> list[dict]:
    """Load release_notes.json; returns [] on any error."""
    try:
        return json.loads(Path(RELEASE_NOTES_FILE).read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"[ReleaseNotes] cannot load {RELEASE_NOTES_FILE}: {e}")
        return []


def _format_release_entry(entry: dict, header: bool = True) -> str:
    """Format one release notes entry as Telegram Markdown text."""
    v   = entry.get("version", "?")
    d   = entry.get("date", "")
    t   = _escape_md(entry.get("title", ""))   # escape to prevent Markdown parse errors
    n   = entry.get("notes", "")
    hdr = f"📦 *v{v}*" + (f"  _({d})_" if d else "") + (f" — {t}" if t else "")
    return (hdr + "\n\n" + n) if header else n


def _get_changelog_text(max_entries: int = 0) -> str:
    """Return formatted changelog Markdown (all entries, or limited to max_entries)."""
    entries = _load_release_notes()
    if not entries:
        return "📝 _Release notes not available._"
    if max_entries:
        entries = entries[:max_entries]
    parts = [_format_release_entry(e) for e in entries]
    sep = "\n\n" + "\u2500" * 28 + "\n\n"
    return sep.join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Orphaned TTS message tracker
# Persists 'Generating audio…' message IDs across restarts so they can be
# cleaned up even if the bot was killed mid-synthesis.
# ─────────────────────────────────────────────────────────────────────────────

def _save_pending_tts(chat_id: int, msg_id: int) -> None:
    """Record a pending TTS message so it can be cleaned up on restart."""
    try:
        try:
            data: dict = json.loads(Path(_PENDING_TTS_FILE).read_text(encoding="utf-8"))
        except Exception:
            data = {}
        data[str(chat_id)] = msg_id
        Path(_PENDING_TTS_FILE).write_text(json.dumps(data), encoding="utf-8")
    except Exception as _e:
        log.debug(f"_save_pending_tts: {_e}")


def _clear_pending_tts(chat_id: int) -> None:
    """Remove a chat's TTS entry once the message has been handled."""
    try:
        data: dict = json.loads(Path(_PENDING_TTS_FILE).read_text(encoding="utf-8"))
        data.pop(str(chat_id), None)
        Path(_PENDING_TTS_FILE).write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _cleanup_orphaned_tts() -> None:
    """
    On startup: edit any 'Generating audio…' messages left orphaned by
    a previous restart so users don't see a permanently stuck status bubble.
    """
    try:
        data: dict = json.loads(Path(_PENDING_TTS_FILE).read_text(encoding="utf-8"))
    except Exception:
        return
    if not data:
        return
    cleaned = 0
    for chat_id_str, msg_id in list(data.items()):
        try:
            # Use bilingual message — we don't know the user's language here
            bot.edit_message_text(
                "⚠️ Генерация аудио прервана (бот перезапущен)\n"
                "⚠️ Audio generation interrupted (bot restarted)",
                int(chat_id_str), msg_id,
            )
            cleaned += 1
        except Exception:
            pass  # message already gone or too old
    try:
        Path(_PENDING_TTS_FILE).unlink(missing_ok=True)
    except Exception:
        pass
    if cleaned:
        log.info(f"[TTS] Cleaned {cleaned} orphaned 'Generating audio…' message(s)")


def _notify_admins_new_version() -> None:
    """On startup, send release notes to all admins if BOT_VERSION is new."""
    try:
        last = Path(LAST_NOTIFIED_FILE).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        last = ""
    except Exception as e:
        log.warning(f"[ReleaseNotes] read last-notified: {e}")
        last = ""

    if last == BOT_VERSION:
        return   # already notified for this version

    entries = _load_release_notes()
    # Find this version's entry
    entry = next((e for e in entries if e.get("version") == BOT_VERSION), None)
    if entry:
        body = _format_release_entry(entry)
    else:
        body = f"📦 *v{BOT_VERSION}* deployed."

    msg = f"� *New version deployed: v{BOT_VERSION}*\n\n{body}"
    for admin_id in ADMIN_USERS:
        try:
            bot.send_message(admin_id, msg, parse_mode="Markdown",
                             reply_markup=_admin_keyboard())
            log.info(f"[ReleaseNotes] notified admin {admin_id} (v{BOT_VERSION})")
        except Exception as e:
            log.warning(f"[ReleaseNotes] Markdown failed for admin {admin_id}: {e} — retrying as plain text")
            try:
                import re as _re_rn
                plain = _re_rn.sub(r"[*_`]", "", msg)
                bot.send_message(admin_id, plain, reply_markup=_admin_keyboard())
                log.info(f"[ReleaseNotes] notified admin {admin_id} (v{BOT_VERSION}, plain text)")
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
        log.warning(f"[Changelog] Markdown failed for {chat_id}: {e} — retrying plain text")
        try:
            import re as _re_cl
            plain = _re_cl.sub(r"[*_`]", "", text)
            bot.send_message(chat_id, plain, reply_markup=_admin_keyboard())
        except Exception as e2:
            log.error(f"[Changelog] send failed for {chat_id}: {e2}")


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
    text = (
        f"\U0001f916 *Switch LLM*\n\nActive: `{current_label}`\n\n"
        f"\u2705 active   \u2714\ufe0f key set   \u26a0\ufe0f needs key\n\n"
        f"Tap *OpenAI ChatGPT* to select GPT-4o / GPT-4o-mini and set your API key."
    )
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        log.warning(f"[LLM] llm_menu send failed: {e}")
        import re as _re_llm
        bot.send_message(chat_id, _re_llm.sub(r"[*_`]", "", text), reply_markup=kb)


def _handle_set_llm(chat_id: int, model_name: str) -> None:
    """Apply LLM model selection and confirm to user."""
    _set_active_model(model_name)
    if model_name:
        models_map = {m["model_name"]: m for m in _get_picoclaw_models() if m.get("model_name")}
        m = models_map.get(model_name, {})
        has_key = bool(m.get("api_key", "").strip())
        warn = "" if has_key else "\n\n\u26a0\ufe0f No API key set for this model — go to OpenAI ChatGPT menu to add one."
        msg = f"\u2705 LLM switched to: {model_name}{warn}\n\nAll subsequent chat, system, and voice requests will use this model."
    else:
        msg = "\u21a9\ufe0f LLM reset to config default (openrouter-auto)."
    try:
        bot.send_message(chat_id, msg, reply_markup=_admin_keyboard())
    except Exception as e:
        log.warning(f"[LLM] set_llm send failed: {e}")


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
        prefix = "\u2705" if is_current else ("\u2714\ufe0f" if has_key else "\u26a0\ufe0f")
        kb.add(InlineKeyboardButton(f"{prefix} {name} — {description}",
                                    callback_data=f"llm_select:{name}"))

    key_label = (f"\U0001f511 Update OpenAI Key (\u2026{shared_key[-4:]})" if shared_key
                 else "\U0001f511 Set OpenAI API Key")
    kb.add(InlineKeyboardButton(key_label, callback_data="llm_setkey_openai"))
    kb.add(InlineKeyboardButton("\U0001f519  LLM Menu", callback_data="admin_llm_menu"))

    status_line = (f"\U0001f511 Key: ...{shared_key[-4:]} configured"
                   if shared_key else "\U0001f511 Key: not set — tap below to add")
    text = (
        f"\U0001f535 *OpenAI ChatGPT Models*\n\n"
        f"{status_line}\n\n"
        f"\u2705 active   \u2714\ufe0f key set   \u26a0\ufe0f needs key\n\n"
        f"One API key is shared by all OpenAI models.\n"
        f"Get yours at: https://platform.openai.com/api-keys"
    )
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        log.warning(f"[LLM] openai_menu send failed: {e}")
        import re as _re_oa
        bot.send_message(chat_id, _re_oa.sub(r"[*_`]", "", text), reply_markup=kb)


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
        response = _ask_picoclaw(_with_lang(chat_id, user_text), timeout=60)
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


def _piper_model_path() -> str:
    """Return the effective Piper ONNX model path.
    Priority: tmpfs copy (RAM disk) > low model > original medium model.
    piper_low_model uses ru_RU-irina-low.onnx when available (§5.3).
    tmpfs_model (~10x faster reads vs microSD) always wins if the copy exists."""
    if _voice_opts.get("tmpfs_model") and os.path.exists(PIPER_MODEL_TMPFS):
        return PIPER_MODEL_TMPFS
    if _voice_opts.get("piper_low_model") and os.path.exists(PIPER_MODEL_LOW):
        return PIPER_MODEL_LOW
    return PIPER_MODEL


def _setup_tmpfs_model(enable: bool) -> None:
    """Copy or remove the Piper ONNX model to/from /dev/shm (tmpfs).
    Runs in a background thread; logs success / failure.
    enable=True  → mkdir -p /dev/shm/piper + cp  (takes ~30s on Pi 3)
    enable=False → remove file from /dev/shm       (fast)
    """
    import shutil
    if enable:
        try:
            os.makedirs("/dev/shm/piper", exist_ok=True)
            log.info(f"[VoiceOpt] tmpfs_model: copying {PIPER_MODEL} → {PIPER_MODEL_TMPFS} …")
            shutil.copy2(PIPER_MODEL, PIPER_MODEL_TMPFS)
            size_mb = os.path.getsize(PIPER_MODEL_TMPFS) / 1024 / 1024
            log.info(f"[VoiceOpt] tmpfs_model: copy done ({size_mb:.0f} MB in RAM, reads ~10x faster)")
        except Exception as e:
            log.warning(f"[VoiceOpt] tmpfs_model: copy failed: {e}")
            # Disable the opt so it doesn't silently fall back without warning
            _voice_opts["tmpfs_model"] = False
            _save_voice_opts()
    else:
        try:
            if os.path.exists(PIPER_MODEL_TMPFS):
                os.unlink(PIPER_MODEL_TMPFS)
                log.info(f"[VoiceOpt] tmpfs_model: removed {PIPER_MODEL_TMPFS} from RAM")
        except Exception as e:
            log.warning(f"[VoiceOpt] tmpfs_model: remove failed: {e}")


def _warm_piper_cache() -> None:
    """Pre-warm Piper ONNX model into OS page cache (runs in a background thread).
    Eliminates the 10–15s cold ONNX model load on the first TTS call after startup.
    Only called when the warm_piper voice opt is enabled."""
    try:
        log.info("[VoiceOpt] Warming Piper ONNX cache…")
        result = subprocess.run(
            [PIPER_BIN, "--model", _piper_model_path(), "--output-raw"],
            input=b".",
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0:
            log.info("[VoiceOpt] Piper cache warm complete.")
        else:
            log.warning(f"[VoiceOpt] Piper warmup rc={result.returncode}: "
                        f"{result.stderr[:100]}")
    except Exception as e:
        log.warning(f"[VoiceOpt] Piper warmup failed: {e}")


def _start_persistent_piper() -> None:
    """Launch a long-running Piper process to keep the ONNX model resident in
    the kernel page cache (§5.3 persistent_piper opt).
    The subprocess never receives any input — it just holds the model in memory.
    Actual TTS synthesis still uses fresh subprocess.run() calls for safety."""
    global _persistent_piper_proc
    _stop_persistent_piper()   # kill any stale instance first
    try:
        _persistent_piper_proc = subprocess.Popen(
            [PIPER_BIN, "--model", _piper_model_path(), "--output-raw"],
            stdin=subprocess.PIPE,    # hold open without writing
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info(f"[PersistentPiper] started PID={_persistent_piper_proc.pid} — "
                 f"ONNX model kept warm in page cache")
    except Exception as e:
        log.warning(f"[PersistentPiper] failed to start: {e}")


def _stop_persistent_piper() -> None:
    """Terminate the persistent Piper keepalive subprocess."""
    global _persistent_piper_proc
    if _persistent_piper_proc is not None:
        try:
            if _persistent_piper_proc.poll() is None:
                _persistent_piper_proc.terminate()
                _persistent_piper_proc.wait(timeout=5)
            log.info(f"[PersistentPiper] stopped PID={_persistent_piper_proc.pid}")
        except Exception as e:
            log.debug(f"[PersistentPiper] stop: {e}")
        _persistent_piper_proc = None


def _vad_filter_pcm(raw_pcm: bytes, sample_rate: int) -> bytes:
    """Apply WebRTC VAD to remove non-speech frames from raw S16LE PCM.
    Returns filtered PCM.  Falls back to original PCM if webrtcvad is not
    installed or an error occurs — so this is always safe to call.
    Requires: pip3 install webrtcvad"""
    try:
        import webrtcvad as _vad_lib
        vad = _vad_lib.Vad(2)   # aggressiveness 0–3 (2 = balanced)
        frame_ms = 30            # 10 / 20 / 30 ms frames allowed by WebRTC VAD
        frame_bytes = int(sample_rate * (frame_ms / 1000.0)) * 2  # 16-bit samples
        out_frames = []
        for i in range(0, len(raw_pcm) - frame_bytes + 1, frame_bytes):
            frame = raw_pcm[i:i + frame_bytes]
            try:
                if vad.is_speech(frame, sample_rate):
                    out_frames.append(frame)
            except Exception:
                out_frames.append(frame)  # keep on per-frame error
        filtered = b"".join(out_frames)
        removed_pct = 100 * (1 - len(filtered) / max(len(raw_pcm), 1))
        log.debug(f"[VAD] removed {removed_pct:.0f}% non-speech frames")
        return filtered if filtered else raw_pcm   # never return empty
    except ImportError:
        log.debug("[VAD] webrtcvad not installed — skipping filter")
        return raw_pcm
    except Exception as e:
        log.debug(f"[VAD] filter error: {e} — skipping")
        return raw_pcm


def _stt_whisper(raw_pcm: bytes, sample_rate: int) -> Optional[str]:
    """Run whisper.cpp (§5.3) on raw S16LE PCM. Returns transcript or None.
    Writes PCM to a temp WAV file, invokes WHISPER_BIN, parses stdout.
    Falls back to None on any error so caller can use Vosk as fallback."""
    try:
        import tempfile, wave as _wave_mod
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        # Write a proper 16-bit WAV file so whisper.cpp can read it
        with _wave_mod.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)     # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(raw_pcm)
        result = subprocess.run(
            [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", tmp_path,
             "-l", "ru", "--no-timestamps", "-otxt"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=60,
        )
        os.unlink(tmp_path)
        if result.returncode != 0:
            log.warning(f"[WhisperSTT] rc={result.returncode}: {result.stderr[:200]}")
            return None
        # whisper.cpp -otxt writes <file>.txt — also check stdout
        txt_path = tmp_path + ".txt"
        if os.path.exists(txt_path):
            text = open(txt_path, encoding="utf-8").read().strip()
            os.unlink(txt_path)
        else:
            text = result.stdout.strip()
        # Strip whisper.cpp timestamp markers like [00:00:00.000 --> 00:00:05.000]
        import re as _re_w
        text = _re_w.sub(r"\[[\d:.]+ --> [\d:.]+\]\s*", "", text).strip()
        return text if text else None
    except FileNotFoundError:
        log.debug(f"[WhisperSTT] binary not found: {WHISPER_BIN}")
        return None
    except subprocess.TimeoutExpired:
        log.warning("[WhisperSTT] timed out after 60 s")
        return None
    except Exception as e:
        log.warning(f"[WhisperSTT] error: {e}")
        return None


def _tts_to_ogg(text: str) -> Optional[bytes]:
    """
    Synthesise text with Piper TTS, encode with ffmpeg as OGG Opus.
    Returns bytes suitable for bot.send_voice(), or None on failure.
    Requires: ffmpeg with libopus + piper (installed by setup_voice.sh).

    Uses two sequential subprocess.run() calls instead of Popen pipe-chaining.
    The Popen approach caused a deadlock: the parent process held piper.stdout
    open, so ffmpeg never received EOF on its stdin and blocked forever.
    Sequential approach: piper → raw PCM bytes → ffmpeg → OGG bytes.
    Text is truncated to TTS_MAX_CHARS (top-level constant) before synthesis.
    """
    # Clean text: strip emoji (Piper reads them as words) + Markdown syntax
    tts_text = _escape_tts(text)

    # Trim to whole sentences where possible, hard-cap at TTS_MAX_CHARS
    if len(tts_text) > TTS_MAX_CHARS:
        # Try to cut at last sentence boundary before the limit
        cut = tts_text[:TTS_MAX_CHARS]
        for sep in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
            idx = cut.rfind(sep)
            if idx > TTS_MAX_CHARS // 2:
                cut = cut[:idx + 1]
                break
        tts_text = cut.strip()

    if not tts_text:
        return None

    try:
        # ── Step 1: Piper TTS → raw S16LE PCM ──────────────────────────────
        piper_result = subprocess.run(
            [PIPER_BIN, "--model", _piper_model_path(), "--output-raw"],
            input=tts_text.encode("utf-8"),
            capture_output=True,
            timeout=120,   # increased: Pi 3 under memory pressure takes longer
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
        _srate = 8000 if _voice_opts.get("low_sample_rate") else VOICE_SAMPLE_RATE
        _ff_cmd = ["ffmpeg", "-i", "pipe:0"]
        # Always apply audio enhancement to improve STT accuracy:
        #   highpass=f=80     — remove low-frequency noise/rumble below 80 Hz
        #   dynaudnorm=p=0.9  — normalize volume so quiet speech is clearly heard
        _af_filters = []
        if _voice_opts.get("silence_strip"):
            _af_filters.append(
                "silenceremove=start_periods=1:start_silence=0.3"
                ":start_threshold=-40dB"
                ":stop_periods=1:stop_silence=0.5:stop_threshold=-40dB"
            )
        _af_filters += ["highpass=f=80", "dynaudnorm=p=0.9"]
        _ff_cmd += ["-af", ",".join(_af_filters)]
        _ff_cmd += ["-ar", str(_srate), "-ac", "1", "-f", "s16le", "pipe:1"]
        _ts = time.time()
        try:
            ff = subprocess.Popen(
                _ff_cmd,
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

        # ── VAD pre-filter (§5.3) ─────────────────────────────────────────────
        if _voice_opts.get("vad_prefilter"):
            _ts = time.time()
            raw_pcm = _vad_filter_pcm(raw_pcm, _srate)
            _timing["VAD"] = time.time() - _ts

        # ── STT: whisper.cpp (§5.3) OR Vosk (default / fallback) ─────────────
        _ts = time.time()
        text = ""
        if _voice_opts.get("whisper_stt"):
            text = _stt_whisper(raw_pcm, _srate) or ""
            if text:
                log.debug(f"[WhisperSTT] transcript: {text[:80]}")
            else:
                log.warning("[WhisperSTT] no result — falling back to Vosk")

        if not text:
            # ─ Vosk STT (default / fallback) ────────────────────────────────
            # STT_CONF_THRESHOLD: words with confidence below this are marked [?word]
            # so the LLM can attempt to fill them from context.
            STT_CONF_THRESHOLD = 0.65
            try:
                import vosk as _vosk_lib
                import json as _json
                model = _get_vosk_model()
                rec = _vosk_lib.KaldiRecognizer(model, _srate)
                rec.SetWords(True)
                chunk = VOICE_CHUNK_SIZE * 2 * _srate // VOICE_SAMPLE_RATE  # adjust for sample rate
                for i in range(0, len(raw_pcm), chunk):
                    rec.AcceptWaveform(raw_pcm[i:i + chunk])
                final = _json.loads(rec.FinalResult())
                words = final.get("result", [])
                if words:
                    # Build transcript: low-confidence words wrapped in [?…]
                    parts = []
                    low_conf_count = 0
                    for w in words:
                        conf = w.get("conf", 1.0)
                        word = w.get("word", "")
                        if conf < STT_CONF_THRESHOLD:
                            parts.append(f"[?{word}]")
                            low_conf_count += 1
                        else:
                            parts.append(word)
                    text = " ".join(parts).strip()
                    if low_conf_count:
                        log.debug(f"STT: {low_conf_count}/{len(words)} words below "
                                  f"conf={STT_CONF_THRESHOLD}: {text[:120]}")
                else:
                    text = final.get("text", "").strip()
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

        # ── Voice note commands (intercept before LLM) ───────────────────────
        _text_lower = text.lower()

        # "запиши заметку …" / "create note …" — save STT text as a note
        _note_create_ru = ("запиши заметку", "создай заметку", "запишите заметку", "сохрани заметку")
        _note_create_en = ("create note", "save note", "new note")
        _note_read_ru   = ("прочитай заметку", "читай заметку", "открой заметку")
        _note_read_en   = ("read note", "open note", "show note")

        def _starts_with_any(s: str, prefixes) -> Optional[str]:
            for p in prefixes:
                if s.startswith(p):
                    return s[len(p):].strip()
            return None

        _create_remainder = (
            _starts_with_any(_text_lower, _note_create_ru)
            or _starts_with_any(_text_lower, _note_create_en)
        )
        _read_remainder = (
            _starts_with_any(_text_lower, _note_read_ru)
            or _starts_with_any(_text_lower, _note_read_en)
        )

        if _create_remainder is not None and not _is_guest(chat_id):
            # Use remainder as title, full text as content
            _note_title   = _create_remainder.strip() or _t(chat_id, "note_voice_default_title")
            _note_slug    = _slug(_note_title)
            _note_content = f"# {_note_title}\n\n(голосовая заметка / voice note)\n{text}"
            _save_note_file(chat_id, _note_slug, _note_content)
            _reply = _t(chat_id, "note_voice_saved", title=_note_title)
            _safe_edit(chat_id, msg.message_id,
                       f"📝 *Заметка / Note:* _{_escape_md(text)}_\n\n{_escape_md(_reply)}",
                       parse_mode="Markdown",
                       reply_markup=_voice_back_keyboard(chat_id))
            # TTS confirmation
            _audio_on2 = (not _voice_opts.get("user_audio_toggle") or _user_audio.get(chat_id, True))
            if _audio_on2:
                _ogg2 = _tts_to_ogg(_reply)
                if _ogg2:
                    bot.send_voice(chat_id, io.BytesIO(_ogg2))
            return

        if _read_remainder is not None and not _is_guest(chat_id):
            _notes = _list_notes_for(chat_id)
            _match = None
            if _read_remainder:
                # Fuzzy match: find note whose title contains the remainder
                for _n in _notes:
                    if _read_remainder in _n["title"].lower() or _read_remainder in _n["slug"]:
                        _match = _n
                        break
            if not _match and _notes:
                _match = _notes[0]   # fall back to most recent note
            if not _match:
                _reply2 = _t(chat_id, "note_voice_read_notfound")
                _safe_edit(chat_id, msg.message_id,
                           _escape_md(_reply2),
                           parse_mode="Markdown",
                           reply_markup=_voice_back_keyboard(chat_id))
                return
            _note_body = _load_note_text(chat_id, _match["slug"]) or ""
            # Strip markdown heading for TTS
            _note_plain = _escape_tts(_note_body)
            _safe_edit(chat_id, msg.message_id,
                       f"📄 *{_escape_md(_match['title'])}*\n\n{_escape_md(_note_body)}",
                       parse_mode="Markdown",
                       reply_markup=_voice_back_keyboard(chat_id))
            _audio_on3 = (not _voice_opts.get("user_audio_toggle") or _user_audio.get(chat_id, True))
            if _audio_on3:
                _tts3 = bot.send_message(chat_id, _t(chat_id, "gen_audio"), parse_mode="Markdown")
                _ogg3 = _tts_to_ogg(_note_plain)
                if _ogg3:
                    bot.send_voice(chat_id, io.BytesIO(_ogg3), caption=_t(chat_id, "audio_caption"))
                    bot.delete_message(chat_id, _tts3.message_id)
                else:
                    _safe_edit(chat_id, _tts3.message_id, _t(chat_id, "audio_na"), parse_mode="Markdown")
            return

        # ── Show transcript, call picoclaw ────────────────────────────────────
        _safe_edit(chat_id, msg.message_id,
                   _t(chat_id, "you_said", text=text),
                   parse_mode="Markdown")

        _ts = time.time()
        response = _ask_picoclaw(_with_lang_voice(chat_id, text), timeout=90)
        _timing["LLM"] = time.time() - _ts

        if not response:
            response = _t(chat_id, "no_answer")

        # ── Text answer ───────────────────────────────────────────────────────
        _audio_on = (not _voice_opts.get("user_audio_toggle")
                     or _user_audio.get(chat_id, True))
        _tts_result: list = [None]
        _tts_thread = None
        if _audio_on and _voice_opts.get("parallel_tts"):
            def _bg_tts():
                _tts_result[0] = _tts_to_ogg(response)
            _tts_thread = threading.Thread(target=_bg_tts, daemon=True)
            _tts_thread.start()

        import html as _html_mod
        _display_text = _escape_md(_truncate(response))
        try:
            bot.send_message(
                chat_id,
                f"🤖 *Picoclaw:*\n{_display_text}{_fmt_timing()}",
                parse_mode="Markdown",
                reply_markup=_voice_back_keyboard(chat_id),
            )
        except Exception:
            # Fallback: plain text when Markdown parse fails
            bot.send_message(
                chat_id,
                f"Picoclaw:\n{_truncate(response)}{_fmt_timing()}",
                parse_mode=None,
                reply_markup=_voice_back_keyboard(chat_id),
            )

        if _audio_on:
            tts_msg = None
            try:
                tts_msg = bot.send_message(chat_id, _t(chat_id, "gen_audio"),
                                           parse_mode="Markdown")
                _save_pending_tts(chat_id, tts_msg.message_id)
                _ts = time.time()
                if _tts_thread is not None:
                    # piper timeout 120s + ffmpeg timeout 30s + scheduling margin
                    _tts_thread.join(timeout=160)
                    ogg = _tts_result[0]
                else:
                    ogg = _tts_to_ogg(response)
                _timing["TTS"] = time.time() - _ts

                if ogg:
                    caption = _t(chat_id, "audio_caption") + _fmt_timing()
                    bot.send_voice(chat_id, io.BytesIO(ogg), caption=caption)
                    bot.delete_message(chat_id, tts_msg.message_id)
                    tts_msg = None   # cleaned up successfully
                else:
                    _safe_edit(chat_id, tts_msg.message_id,
                               _t(chat_id, "audio_na"),
                               parse_mode="Markdown")
                    tts_msg = None   # cleaned up successfully
            except Exception as e:
                log.warning(f"TTS block error: {e}")
            finally:
                _clear_pending_tts(chat_id)
                # If tts_msg is still set an unhandled exception occurred before cleanup
                if tts_msg is not None:
                    try:
                        _safe_edit(chat_id, tts_msg.message_id,
                                   _t(chat_id, "audio_error", e="generation failed"),
                                   parse_mode="Markdown")
                    except Exception:
                        pass

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Command handlers
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(message):
    cid = message.chat.id
    _set_lang(cid, message.from_user)

    if not _is_allowed(cid):
        # Unknown user — run registration flow
        username = getattr(message.from_user, "username", "") or ""
        first    = getattr(message.from_user, "first_name", "") or ""
        last     = getattr(message.from_user, "last_name", "") or ""
        name     = f"{first} {last}".strip()

        if _is_blocked_reg(cid):
            bot.send_message(cid, _t(cid, "reg_blocked"))
        elif _is_pending_reg(cid):
            bot.send_message(cid, _t(cid, "reg_pending_exists"))
        else:
            _upsert_registration(cid, username, name, "pending")
            bot.send_message(cid, _t(cid, "reg_waiting"))
            log.info(f"[Reg] New request: chat_id={cid} username={username!r} name={name!r}")
            _notify_admins_new_registration(cid, username, name)
        return

    bot.send_message(cid, _t(cid, "welcome"), parse_mode="Markdown",
                     reply_markup=_menu_keyboard(cid))


def _notify_admins_new_registration(chat_id: int, username: str, name: str) -> None:
    """Send approve/block buttons to all admins when a new user registers."""
    uname_disp = f"@{username}" if username else "_(no username)_"
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
                f"Username: {uname_disp}\n"
                f"Name: {name or '_(not set)_'}",
                parse_mode="Markdown",
                reply_markup=kb,
            )
            log.info(f"[Reg] Notified admin {admin_id} of registration from {chat_id}")
        except Exception as e:
            log.warning(f"[Reg] Notify admin {admin_id} failed: {e}")


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

    elif data == "voice_opts_menu":
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_voice_opts_menu(cid)

    elif data.startswith("voice_opt_toggle:"):
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_voice_opt_toggle(cid, data[len("voice_opt_toggle:"):])

    elif data == "voice_audio_toggle":
        _user_audio[cid] = not _user_audio.get(cid, True)
        # answer_callback_query already called above; spinner is dismissed

    elif data == "admin_changelog":
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_admin_changelog(cid)

    elif data == "admin_pending_users":
        if not _is_admin(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_admin_pending_users(cid)

    elif data.startswith("reg_approve:"):
        if not _is_admin(cid):
            bot.answer_callback_query(call.id, _t(cid, "admin_only"))
        else:
            target_id = int(data.split(":", 1)[1])
            _do_approve_registration(cid, target_id)

    elif data.startswith("reg_block:"):
        if not _is_admin(cid):
            bot.answer_callback_query(call.id, _t(cid, "admin_only"))
        else:
            target_id = int(data.split(":", 1)[1])
            _do_block_registration(cid, target_id)

    # ── Notes ────────────────────────────────────────────────────────────────

    elif data == "menu_notes":
        if _is_guest(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_notes_menu(cid)

    elif data == "note_create":
        if _is_guest(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _start_note_create(cid)

    elif data == "note_list":
        if _is_guest(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_note_list(cid)

    elif data.startswith("note_open:"):
        if _is_guest(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_note_open(cid, data[len("note_open:"):])

    elif data.startswith("note_edit:"):
        if _is_guest(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _start_note_edit(cid, data[len("note_edit:"):])

    elif data.startswith("note_delete:"):
        if _is_guest(cid):
            bot.send_message(cid, _t(cid, "admin_only"))
        else:
            _handle_note_delete(cid, data[len("note_delete:"):])

    elif data == "cancel":
        _pending_cmd.pop(cid, None)
        _pending_note.pop(cid, None)
        _user_mode.pop(cid, None)
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

    elif mode == "note_add_title":
        if _is_guest(cid):
            _user_mode.pop(cid, None)
            _pending_note.pop(cid, None)
            return
        title = message.text.strip()
        if not title:
            bot.send_message(cid, _t(cid, "note_create_prompt_title"), parse_mode="Markdown")
            return
        slug = _slug(title)
        _pending_note[cid] = {"step": "content", "slug": slug, "title": title}
        _user_mode[cid] = "note_add_content"
        bot.send_message(cid, _t(cid, "note_create_prompt_content", title=_escape_md(title)),
                         parse_mode="Markdown")
        return

    elif mode == "note_add_content":
        if _is_guest(cid):
            _user_mode.pop(cid, None)
            _pending_note.pop(cid, None)
            return
        info = _pending_note.pop(cid, {})
        _user_mode.pop(cid, None)
        slug  = info.get("slug", _slug(message.text[:30]))
        title = info.get("title", slug)
        content = f"# {title}\n\n{message.text.strip()}"
        _save_note_file(cid, slug, content)
        bot.send_message(cid, _t(cid, "note_saved", title=_escape_md(title)),
                         parse_mode="Markdown",
                         reply_markup=_notes_menu_keyboard(cid))
        return

    elif mode == "note_edit_content":
        if _is_guest(cid):
            _user_mode.pop(cid, None)
            _pending_note.pop(cid, None)
            return
        info = _pending_note.pop(cid, {})
        _user_mode.pop(cid, None)
        slug = info.get("slug")
        if not slug:
            _send_menu(cid, greeting=False)
            return
        existing = _load_note_text(cid, slug)
        title_line = (existing or "").splitlines()[0] if existing else f"# {slug}"
        content = f"{title_line}\n\n{message.text.strip()}"
        _save_note_file(cid, slug, content)
        title = title_line.lstrip("# ").strip()
        bot.send_message(cid, _t(cid, "note_updated", title=_escape_md(title)),
                         parse_mode="Markdown",
                         reply_markup=_notes_menu_keyboard(cid))
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
    active_opts = [k for k, v in _voice_opts.items() if v]
    log.info(f"  Voice opts   : {active_opts or 'all OFF (stable defaults)'}")
    log.info(f"  Version      : {BOT_VERSION}")
    log.info("=" * 50)

    # If tmpfs_model is enabled, ensure the RAM-disk copy exists at startup
    if _voice_opts.get("tmpfs_model"):
        if os.path.exists(PIPER_MODEL_TMPFS):
            log.info(f"[VoiceOpt] tmpfs_model: model already in RAM ({PIPER_MODEL_TMPFS})")
        else:
            log.info("[VoiceOpt] tmpfs_model enabled — copying model to /dev/shm on startup")
            threading.Thread(target=_setup_tmpfs_model, args=(True,), daemon=True).start()

    # Pre-warm Piper ONNX model if opt is enabled
    if _voice_opts.get("warm_piper"):
        log.info("[VoiceOpt] warm_piper enabled — starting background warm-up")
        threading.Thread(target=_warm_piper_cache, daemon=True).start()

    # Start persistent Piper keepalive process if opt is enabled
    if _voice_opts.get("persistent_piper"):
        log.info("[VoiceOpt] persistent_piper enabled — starting Piper keepalive")
        threading.Thread(target=_start_persistent_piper, daemon=True).start()

    # Clean up any 'Generating audio…' messages orphaned by a previous restart
    _cleanup_orphaned_tts()

    # Notify admins if this is a new deployment
    _notify_admins_new_version()

    log.info("Polling Telegram…")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)


if __name__ == "__main__":
    main()
