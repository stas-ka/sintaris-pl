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
  🎤 Voice Session  — tap to open mic → real-time Vosk STT transcription shown
                       in Telegram → picoclaw LLM answers → text + Piper TTS
                       OGG voice note sent back

Config (env vars or ~/.picoclaw/bot.env):
  BOT_TOKEN         Telegram bot token  (from @BotFather)
  ALLOWED_USER      Telegram chat_id    (numeric, single allowed user)
  PICOCLAW_BIN      path to picoclaw binary   (default /usr/bin/picoclaw)
  DIGEST_SCRIPT     path to gmail_digest.py  (default ~/.picoclaw/gmail_digest.py)
  LAST_DIGEST_FILE  path to last saved digest (default ~/.picoclaw/last_digest.txt)
  VOSK_MODEL_PATH   path to vosk Russian model dir
  PIPER_BIN         path to Piper TTS binary  (default /usr/local/bin/piper)
  PIPER_MODEL       path to Piper .onnx voice model
  XDG_RUNTIME_DIR   PipeWire runtime dir      (default /run/user/1000)
"""

import logging
import io
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
ALLOWED_USER     = int(os.environ.get("ALLOWED_USER") or os.environ.get("TELEGRAM_CHAT_ID", "0"))
PICOCLAW_BIN     = os.environ.get("PICOCLAW_BIN", "/usr/bin/picoclaw")
DIGEST_SCRIPT    = os.environ.get("DIGEST_SCRIPT",
                                   os.path.expanduser("~/.picoclaw/gmail_digest.py"))
LAST_DIGEST_FILE = os.environ.get("LAST_DIGEST_FILE",
                                   os.path.expanduser("~/.picoclaw/last_digest.txt"))

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

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set. Add it to ~/.picoclaw/bot.env")
if not ALLOWED_USER:
    raise RuntimeError("ALLOWED_USER (or TELEGRAM_CHAT_ID) not set.")

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

# ─────────────────────────────────────────────────────────────────────────────
# Session state (per chat_id)
# ─────────────────────────────────────────────────────────────────────────────

# mode: None | 'chat' | 'system'
_user_mode: dict[int, str] = {}
# pending confirmation: chat_id → bash command string
_pending_cmd: dict[int, str] = {}
# active voice sessions {chat_id: {"stop_event": Event, "msg_id": int}}
_voice_sessions: dict[int, dict] = {}
_vosk_model_cache = None   # lazy-loaded Vosk model singleton

# ─────────────────────────────────────────────────────────────────────────────
# Bot setup
# ─────────────────────────────────────────────────────────────────────────────

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────────────────────
# Access control
# ─────────────────────────────────────────────────────────────────────────────

def _is_allowed(chat_id: int) -> bool:
    return chat_id == ALLOWED_USER

def _deny(chat_id: int) -> None:
    bot.send_message(chat_id, "⛔ Access denied.")
    log.warning(f"Denied access from chat_id={chat_id}")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📧  Mail Digest",    callback_data="digest"),
        InlineKeyboardButton("💬  Free Chat",       callback_data="mode_chat"),
        InlineKeyboardButton("🖥️   System Chat",    callback_data="mode_system"),
        InlineKeyboardButton("🎤  Voice Session",  callback_data="voice_session"),
    )
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


def _send_menu(chat_id: int, text: str = "Choose an action:") -> None:
    _user_mode.pop(chat_id, None)
    bot.send_message(chat_id, text, reply_markup=_menu_keyboard())


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
    """Call picoclaw agent -m and return response text."""
    rc, out = _run_subprocess([PICOCLAW_BIN, "agent", "-m", prompt], timeout=timeout)
    if rc == 0 and out:
        return out
    log.error(f"picoclaw error (rc={rc}): {out[:200]}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Digest
# ─────────────────────────────────────────────────────────────────────────────

def _handle_digest(chat_id: int) -> None:
    """
    Show last saved digest (instant) then optionally refresh.
    """
    last = Path(LAST_DIGEST_FILE)
    if last.exists() and last.stat().st_size > 0:
        text = last.read_text(encoding="utf-8", errors="replace").strip()
        age_h = (time.time() - last.stat().st_mtime) / 3600
        header = f"📧 *Last digest* _(generated {age_h:.1f}h ago)_\n\n"
        bot.send_message(chat_id, header + _truncate(text), parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "📧 No saved digest yet. Fetching now…")
        _refresh_digest(chat_id)
        return

    # Offer refresh
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔄  Refresh now", callback_data="digest_refresh"),
        InlineKeyboardButton("🔙  Menu",        callback_data="menu"),
    )
    bot.send_message(chat_id, "_Refresh to fetch new emails from the last 24h._",
                     parse_mode="Markdown", reply_markup=kb)


def _refresh_digest(chat_id: int) -> None:
    """Run gmail_digest.py in background and report result."""
    msg = bot.send_message(chat_id, "⏳ Fetching emails…")

    def _run():
        rc, out = _run_subprocess(
            ["python3", DIGEST_SCRIPT, "--stdout"],
            timeout=120,
        )
        if rc == 0 and out:
            text = out.strip()
        else:
            text = out or "No output from digest script."

        try:
            bot.edit_message_text(
                f"📧 *Fresh digest*\n\n{_truncate(text)}",
                chat_id, msg.message_id,
                parse_mode="Markdown",
                reply_markup=_back_keyboard(),
            )
        except Exception:
            bot.send_message(chat_id, f"📧 *Fresh digest*\n\n{_truncate(text)}",
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

def _voice_stop_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⏹  Stop", callback_data="voice_stop"))
    return kb


def _get_vosk_model():
    """Lazy-load the Vosk Russian model (shared model dir with voice_assistant.py)."""
    global _vosk_model_cache
    if _vosk_model_cache is None:
        import vosk as _vosk_lib
        _vosk_lib.SetLogLevel(-1)   # suppress verbose Kaldi output
        _vosk_model_cache = _vosk_lib.Model(VOSK_MODEL_PATH)
    return _vosk_model_cache


def _pipewire_env_voice() -> dict:
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"]      = PIPEWIRE_RUNTIME
    env["PIPEWIRE_RUNTIME_DIR"] = PIPEWIRE_RUNTIME
    env["PULSE_SERVER"]         = f"unix:{PIPEWIRE_RUNTIME}/pulse/native"
    return env


def _tts_to_ogg(text: str) -> Optional[bytes]:
    """
    Synthesise text with Piper TTS, encode with ffmpeg as OGG Opus.
    Returns bytes suitable for bot.send_voice(), or None on failure.
    Requires: ffmpeg with libopus support (apt install ffmpeg).
    """
    try:
        piper = subprocess.Popen(
            [PIPER_BIN, "--model", PIPER_MODEL, "--output-raw"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-y",
             "-f", "s16le", "-ar", "22050", "-ac", "1", "-i", "pipe:0",
             "-c:a", "libopus", "-b:a", "24k", "-f", "ogg", "pipe:1"],
            stdin=piper.stdout, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        piper.stdin.write(text.encode("utf-8"))
        piper.stdin.close()
        ogg_bytes, _ = ffmpeg.communicate(timeout=30)
        piper.wait(timeout=5)
        return ogg_bytes or None
    except Exception as e:
        log.warning(f"TTS→OGG failed: {e}")
        return None


def _start_voice_session(chat_id: int) -> None:
    """Launch a background voice session thread for chat_id."""
    # Cancel any existing session for this user
    old = _voice_sessions.pop(chat_id, None)
    if old:
        old["stop_event"].set()

    stop_event = threading.Event()
    msg = bot.send_message(
        chat_id,
        "🎤 *Слушаю…*  _(говорите по-русски)_\n"
        "Запись остановится автоматически через 4 с тишины · макс 30 с.",
        parse_mode="Markdown",
        reply_markup=_voice_stop_keyboard(),
    )
    session = {"stop_event": stop_event, "msg_id": msg.message_id}
    _voice_sessions[chat_id] = session
    threading.Thread(
        target=_voice_session_worker, args=(chat_id, session), daemon=True
    ).start()


def _voice_session_worker(chat_id: int, session: dict) -> None:
    """
    Background worker: mic → Vosk STT (live transcript edited into Telegram)
    → picoclaw LLM text answer → Piper TTS OGG voice note.
    """
    import json as _json
    stop_event = session["stop_event"]
    msg_id     = session["msg_id"]

    # ── Load Vosk model ────────────────────────────────────────────────────
    try:
        import vosk as _vosk_lib
        model = _get_vosk_model()
    except Exception as e:
        _safe_edit(chat_id, msg_id,
                   f"❌ Vosk модель недоступна: {e}\n"
                   f"Выполните `src/setup/setup_voice.sh` для установки.",
                   reply_markup=_back_keyboard())
        _voice_sessions.pop(chat_id, None)
        return

    rec = _vosk_lib.KaldiRecognizer(model, VOICE_SAMPLE_RATE)
    rec.SetWords(True)

    # ── Start audio capture (pw-record, fallback to parec) ─────────────────
    env  = _pipewire_env_voice()
    proc = None
    for cmd in (
        ["pw-record", f"--rate={VOICE_SAMPLE_RATE}", "--channels=1", "--format=s16", "-"],
        ["parec", f"--rate={VOICE_SAMPLE_RATE}", "--channels=1", "--format=s16le"],
    ):
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, env=env)
            break
        except FileNotFoundError:
            continue

    if proc is None:
        _safe_edit(chat_id, msg_id,
                   "❌ Не удалось запустить захват звука — pw-record и parec не найдены.",
                   reply_markup=_back_keyboard())
        _voice_sessions.pop(chat_id, None)
        return

    # ── STT loop ───────────────────────────────────────────────────────────
    full_text  = ""
    last_sound = time.time()
    last_edit  = 0.0
    start_time = time.time()

    def _edit_live(display: str, listening: bool = True) -> None:
        nonlocal last_edit
        if time.time() - last_edit < 1.5:
            return
        last_edit = time.time()
        snip  = display[-300:] if len(display) > 300 else display
        icon  = "🎤" if listening else "✅"
        label = "Слушаю" if listening else "Записано"
        _safe_edit(chat_id, msg_id,
                   f"{icon} *{label}:*\n\n_{snip}_",
                   parse_mode="Markdown",
                   reply_markup=_voice_stop_keyboard() if listening else None)

    try:
        while not stop_event.is_set():
            if time.time() - start_time > VOICE_MAX_DURATION:
                break
            data = proc.stdout.read(VOICE_CHUNK_SIZE * 2)   # 2 bytes/sample S16
            if not data:
                break
            if rec.AcceptWaveform(data):
                word = _json.loads(rec.Result()).get("text", "").strip()
                if word:
                    full_text = (full_text + " " + word).strip()
                    last_sound = time.time()
                    _edit_live(full_text)
            else:
                partial = _json.loads(rec.PartialResult()).get("partial", "").strip()
                if partial:
                    last_sound = time.time()
                    combined  = (full_text + " " + partial).strip() or partial
                    _edit_live(combined)
            # Auto-stop on silence (only after some speech is recognised)
            if full_text and time.time() - last_sound > VOICE_SILENCE_TIMEOUT:
                break
    finally:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except Exception:
            pass

    # Collect any remaining audio buffered inside Vosk
    tail = _json.loads(rec.FinalResult()).get("text", "").strip()
    if tail:
        full_text = (full_text + " " + tail).strip()

    _voice_sessions.pop(chat_id, None)

    # ── No speech detected ─────────────────────────────────────────────────
    if not full_text:
        _safe_edit(chat_id, msg_id,
                   "🎤 _Речь не распознана. Сессия завершена._",
                   parse_mode="Markdown",
                   reply_markup=_back_keyboard())
        return

    # ── Show final transcript + picoclaw status ────────────────────────────
    _safe_edit(chat_id, msg_id,
               f"📝 *Вы сказали:*\n_{full_text}_\n\n⏳ _Спрашиваю picoclaw…_",
               parse_mode="Markdown")

    # ── Call picoclaw LLM ──────────────────────────────────────────────────
    response = _ask_picoclaw(full_text, timeout=60)
    if not response:
        response = "_(picoclaw не вернул ответ)_"

    # ── Send text answer ───────────────────────────────────────────────────
    bot.send_message(
        chat_id,
        f"🤖 *Picoclaw:*\n{_truncate(response)}",
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )

    # ── Generate Piper TTS audio → send as Telegram voice note ────────────
    tts_msg = bot.send_message(chat_id, "🔊 _Генерирую аудио…_",
                               parse_mode="Markdown")
    ogg = _tts_to_ogg(response)
    if ogg:
        try:
            bot.send_voice(chat_id, io.BytesIO(ogg), caption="🔊 Аудио ответ")
            bot.delete_message(chat_id, tts_msg.message_id)
        except Exception as e:
            log.warning(f"send_voice failed: {e}")
            _safe_edit(chat_id, tts_msg.message_id,
                       f"_Аудио не отправлено: {e}_",
                       parse_mode="Markdown")
    else:
        _safe_edit(chat_id, tts_msg.message_id,
                   "_(Аудио недоступно — ffmpeg или piper не установлен)_",
                   parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# Command handlers
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start", "menu"])
def cmd_menu(message):
    if not _is_allowed(message.chat.id):
        _deny(message.chat.id)
        return
    _send_menu(message.chat.id, "👋 *Pico* — что делаем?")


@bot.message_handler(commands=["status"])
def cmd_status(message):
    if not _is_allowed(message.chat.id):
        _deny(message.chat.id)
        return
    cid = message.chat.id
    mode = _user_mode.get(cid, "—")
    rc, out = _run_subprocess(["systemctl", "is-active",
                               "picoclaw-voice", "picoclaw-gateway",
                               "picoclaw-telegram"], timeout=5)
    voice_active = cid in _voice_sessions
    bot.send_message(cid,
                     f"*Mode:* `{mode}`\n"
                     f"*Voice session:* `{'active' if voice_active else 'idle'}`\n"
                     f"*Services:*\n```\n{out}\n```",
                     parse_mode="Markdown", reply_markup=_back_keyboard())


# ─────────────────────────────────────────────────────────────────────────────
# Callback query handlers
# ─────────────────────────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    cid = call.message.chat.id
    if not _is_allowed(cid):
        bot.answer_callback_query(call.id, "⛔ Access denied")
        return

    data = call.data
    bot.answer_callback_query(call.id)  # dismiss spinner

    if data == "menu":
        _user_mode.pop(cid, None)
        _pending_cmd.pop(cid, None)
        bot.send_message(cid, "👋 *Pico* — что делаем?",
                         parse_mode="Markdown", reply_markup=_menu_keyboard())

    elif data == "digest":
        _handle_digest(cid)

    elif data == "digest_refresh":
        _refresh_digest(cid)

    elif data == "mode_chat":
        _user_mode[cid] = "chat"
        bot.send_message(cid,
                         "💬 *Free Chat* — напишите что угодно.\n"
                         "Нажмите /menu для выхода.",
                         parse_mode="Markdown")

    elif data == "mode_system":
        _user_mode[cid] = "system"
        bot.send_message(cid,
                         "🖥️ *System Chat* — опишите задачу, я предложу команду.\n"
                         "_Примеры: «покажи диск», «список сервисов», "
                         "«температура CPU», «последние 20 строк voice.log»_\n\n"
                         "Нажмите /menu для выхода.",
                         parse_mode="Markdown")

    elif data == "voice_session":
        _user_mode.pop(cid, None)   # exit any text mode
        _start_voice_session(cid)

    elif data == "voice_stop":
        session = _voice_sessions.pop(cid, None)
        if session:
            session["stop_event"].set()

    elif data == "cancel":
        _pending_cmd.pop(cid, None)
        bot.send_message(cid, "❌ Отменено.", reply_markup=_back_keyboard())

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

    mode = _user_mode.get(cid)

    if mode is None:
        # No mode selected — show menu
        _send_menu(cid, "👋 Выберите режим:")
        return

    if mode == "chat":
        _handle_chat_message(cid, message.text)

    elif mode == "system":
        _handle_system_message(cid, message.text)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 50)
    log.info("Pico Telegram Menu Bot starting")
    log.info(f"  Allowed user : {ALLOWED_USER}")
    log.info(f"  picoclaw     : {PICOCLAW_BIN}")
    log.info(f"  Digest script: {DIGEST_SCRIPT}")
    log.info("=" * 50)

    log.info("Polling Telegram…")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)


if __name__ == "__main__":
    main()
