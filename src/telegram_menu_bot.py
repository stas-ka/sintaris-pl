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
                    Example: ALLOWED_USERS=994963580,123456789
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
if not ALLOWED_USERS:
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

# ─────────────────────────────────────────────────────────────────────────────
# Session state (per chat_id)
# ─────────────────────────────────────────────────────────────────────────────

# mode: None | 'chat' | 'system'
_user_mode: dict[int, str] = {}
# pending confirmation: chat_id → bash command string
_pending_cmd: dict[int, str] = {}
_vosk_model_cache = None   # lazy-loaded Vosk model singleton

# ─────────────────────────────────────────────────────────────────────────────
# Bot setup
# ─────────────────────────────────────────────────────────────────────────────

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────────────────────
# Access control
# ─────────────────────────────────────────────────────────────────────────────

def _is_allowed(chat_id: int) -> bool:
    return chat_id in ALLOWED_USERS

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
    """Call picoclaw agent -m and return clean response text (no log lines)."""
    try:
        result = subprocess.run(
            [PICOCLAW_BIN, "agent", "-m", prompt],
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
    """Enter voice mode — user sends a Telegram voice note to interact."""
    _user_mode[chat_id] = "voice"
    bot.send_message(
        chat_id,
        "🎤 *Режим голосового запроса*\n\n"
        "Нажмите кнопку 🎤 в поле ввода Telegram, запишите вопрос по-русски "
        "и отправьте голосовое сообщение.\n\n"
        "_Бот распознает речь через Vosk и ответит текстом + голосом._\n\n"
        "Нажмите 🔙 Menu чтобы выйти из режима.",
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
    msg = bot.send_message(chat_id, "🎤 _Распознаю речь…_", parse_mode="Markdown")

    def _run():
        # ── Download OGG from Telegram ──────────────────────────────────────
        try:
            file_info = bot.get_file(voice_obj.file_id)
            ogg_bytes = bot.download_file(file_info.file_path)
        except Exception as e:
            _safe_edit(chat_id, msg.message_id,
                       f"❌ Ошибка загрузки аудио: {e}",
                       reply_markup=_back_keyboard())
            return

        # ── OGG → 16 kHz mono S16LE raw PCM (ffmpeg) ───────────────────────
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
                       f"❌ Ошибка декодирования аудио (ffmpeg): {e}",
                       reply_markup=_back_keyboard())
            return

        if not raw_pcm:
            _safe_edit(chat_id, msg.message_id,
                       "❌ ffmpeg не выдал данных — проверьте установку ffmpeg.",
                       reply_markup=_back_keyboard())
            return

        # ── Vosk STT ─────────────────────────────────────────────────────────
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
                       f"❌ Ошибка Vosk: {e}",
                       reply_markup=_back_keyboard())
            return

        if not text:
            _safe_edit(chat_id, msg.message_id,
                       "🎤 _Речь не распознана. Говорите внятнее или используйте русский язык._",
                       parse_mode="Markdown",
                       reply_markup=_back_keyboard())
            return

        # ── Show transcript, call picoclaw ────────────────────────────────────
        _safe_edit(chat_id, msg.message_id,
                   f"📝 *Вы сказали:*\n_{text}_\n\n⏳ _Спрашиваю picoclaw…_",
                   parse_mode="Markdown")

        response = _ask_picoclaw(text, timeout=60)
        if not response:
            response = "_(picoclaw не вернул ответ)_"

        # ── Text answer ───────────────────────────────────────────────────────
        bot.send_message(
            chat_id,
            f"🤖 *Picoclaw:*\n{_truncate(response)}",
            parse_mode="Markdown",
            reply_markup=_back_keyboard(),
        )

        # ── Piper TTS → send as Telegram voice note ───────────────────────────
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
                       "_(Аудио недоступно — piper не установлен)_",
                       parse_mode="Markdown")

    threading.Thread(target=_run, daemon=True).start()


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
    bot.send_message(cid,
                     f"*Mode:* `{mode}`\n"
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
        _start_voice_session(cid)

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

    elif mode == "voice":
        bot.send_message(cid,
                         "🎤 _Отправьте голосовое сообщение — нажмите 🎤 в поле ввода._",
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
    _handle_voice_message(cid, message.voice)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 50)
    log.info("Pico Telegram Menu Bot starting")
    log.info(f"  Allowed users: {sorted(ALLOWED_USERS)}")
    log.info(f"  picoclaw     : {PICOCLAW_BIN}")
    log.info(f"  Digest script: {DIGEST_SCRIPT}")
    log.info("=" * 50)

    log.info("Polling Telegram…")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)


if __name__ == "__main__":
    main()
