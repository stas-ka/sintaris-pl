"""
bot_config.py — All constants, environment loading, and logging setup.

Every other bot module imports from here.  No imports from other bot_*.py
modules — this is the root of the dependency tree.
"""

import logging
import os
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Environment loading
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


# Load credentials: bot.env first, then .taris_env (bot.env takes priority via setdefault)
_load_env_file(os.path.expanduser("~/.taris/bot.env"))
_load_env_file(os.path.expanduser("~/.taris/.taris_env"))


# ─────────────────────────────────────────────────────────────────────────────
# User-set config
# ─────────────────────────────────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _parse_allowed_users() -> set[int]:
    raw = (os.environ.get("ALLOWED_USERS")
           or os.environ.get("ALLOWED_USER")
           or os.environ.get("TELEGRAM_CHAT_ID", ""))
    return {int(p) for p in raw.split(",") if p.strip().isdigit()}


def _parse_admin_users() -> set[int]:
    raw = os.environ.get("ADMIN_USERS", "")
    ids = {int(p) for p in raw.split(",") if p.strip().isdigit()}
    return ids if ids else set(_parse_allowed_users())


def _parse_developer_users() -> set[int]:
    raw = os.environ.get("DEVELOPER_USERS", "")
    return {int(p) for p in raw.split(",") if p.strip().isdigit()}


ALLOWED_USERS:   set[int] = _parse_allowed_users()
ADMIN_USERS:     set[int] = _parse_admin_users()
DEVELOPER_USERS: set[int] = _parse_developer_users()

BOT_NAME = os.environ.get("BOT_NAME", "Taris")

USERS_FILE          = os.environ.get("USERS_FILE",
                          os.path.expanduser("~/.taris/users.json"))
REGISTRATIONS_FILE  = os.environ.get("REGISTRATIONS_FILE",
                          os.path.expanduser("~/.taris/registrations.json"))
TARIS_BIN        = os.environ.get("TARIS_BIN", "/usr/bin/taris")
TARIS_CONFIG     = os.environ.get("TARIS_CONFIG",
                          os.path.expanduser("~/.taris/config.json"))
ACTIVE_MODEL_FILE   = os.environ.get("ACTIVE_MODEL_FILE",
                          os.path.expanduser("~/.taris/active_model.txt"))

# ─────────────────────────────────────────────────────────────────────────────
# LLM provider switching  (Feature 3.1 + 3.2)
# Set LLM_PROVIDER in ~/.taris/bot.env to switch backends.
# ─────────────────────────────────────────────────────────────────────────────

# Primary provider: taris | openai | yandexgpt | gemini | anthropic | local
LLM_PROVIDER        = os.environ.get("LLM_PROVIDER", "taris")

# Local llama.cpp fallback — enable with LLM_LOCAL_FALLBACK=1 (Feature 3.2)
LLM_LOCAL_FALLBACK      = os.environ.get("LLM_LOCAL_FALLBACK", "0") == "1"
LLM_FALLBACK_FLAG_FILE  = os.path.expanduser("~/.taris/llm_fallback_enabled")  # runtime toggle
LLAMA_CPP_URL           = os.environ.get("LLAMA_CPP_URL",   "http://127.0.0.1:8081")
LLAMA_CPP_MODEL     = os.environ.get("LLAMA_CPP_MODEL", "")

# YandexGPT (Feature 3.1)
YANDEXGPT_API_KEY   = os.environ.get("YANDEXGPT_API_KEY",   "")
YANDEXGPT_FOLDER_ID = os.environ.get("YANDEXGPT_FOLDER_ID", "")
YANDEXGPT_MODEL_URI = os.environ.get("YANDEXGPT_MODEL_URI", "yandexgpt-lite")

# Gemini (Feature 3.1)
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY",  "")
GEMINI_MODEL        = os.environ.get("GEMINI_MODEL",    "gemini-1.5-flash")

# Anthropic (Feature 3.1)
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL     = os.environ.get("ANTHROPIC_MODEL",   "claude-3-haiku-20240307")

# Direct OpenAI (bypasses taris, uses own key — Feature 3.1)
OPENAI_API_KEY      = os.environ.get("OPENAI_API_KEY",  "")
OPENAI_MODEL        = os.environ.get("OPENAI_MODEL",    "gpt-4o-mini")
OPENAI_BASE_URL     = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

# LLM provider tuning parameters
YANDEXGPT_TEMPERATURE  = float(os.getenv("YANDEXGPT_TEMPERATURE", "0.6"))
YANDEXGPT_MAX_TOKENS   = os.getenv("YANDEXGPT_MAX_TOKENS", "2000")
ANTHROPIC_MAX_TOKENS   = int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024"))
LOCAL_MAX_TOKENS       = int(os.getenv("LOCAL_MAX_TOKENS", "512"))
LOCAL_TEMPERATURE      = float(os.getenv("LOCAL_TEMPERATURE", "0.7"))

# Conversation memory (Feature 2.1)
CONVERSATION_HISTORY_MAX  = int(os.environ.get("CONVERSATION_HISTORY_MAX",  "15"))
CONVERSATION_PERSIST      = os.environ.get("CONVERSATION_PERSIST", "0") == "1"
CONVERSATION_HISTORY_FILE = os.environ.get(
    "CONVERSATION_HISTORY_FILE",
    os.path.expanduser("~/.taris/conversation_history.json"),
)

DIGEST_SCRIPT       = os.environ.get("DIGEST_SCRIPT",
                          os.path.expanduser("~/.taris/gmail_digest.py"))
LAST_DIGEST_FILE    = os.environ.get("LAST_DIGEST_FILE",
                          os.path.expanduser("~/.taris/last_digest.txt"))
NOTES_DIR           = os.environ.get("NOTES_DIR",
                          os.path.expanduser("~/.taris/notes"))
CALENDAR_DIR        = os.environ.get("CALENDAR_DIR",
                          os.path.expanduser("~/.taris/calendar"))
MAIL_CREDS_DIR      = os.environ.get("MAIL_CREDS_DIR",
                          os.path.expanduser("~/.taris/mail_creds"))
ERROR_PROTOCOL_DIR  = os.environ.get("ERROR_PROTOCOL_DIR",
                          os.path.expanduser("~/.taris/error_protocols"))
DOCS_DIR            = os.environ.get("DOCS_DIR",
                          os.path.expanduser("~/.taris/docs"))

# ─────────────────────────────────────────────────────────────────────────────
# Bot version — bump on every user-visible deployment
# ─────────────────────────────────────────────────────────────────────────────

BOT_VERSION        = "2026.4.10"
RELEASE_NOTES_FILE = os.environ.get(
    "RELEASE_NOTES_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "release_notes.json"),
)
LAST_NOTIFIED_FILE = os.path.expanduser("~/.taris/last_notified_version.txt")

# ─────────────────────────────────────────────────────────────────────────────
# Voice pipeline constants
# ─────────────────────────────────────────────────────────────────────────────

VOSK_MODEL_PATH    = os.environ.get("VOSK_MODEL_PATH",
                         os.path.expanduser("~/.taris/vosk-model-small-ru"))
VOSK_MODEL_DE_PATH = os.environ.get("VOSK_MODEL_DE_PATH",
                         os.path.expanduser("~/.taris/vosk-model-small-de"))
PIPER_BIN          = os.environ.get("PIPER_BIN",  "/usr/local/bin/piper")
PIPER_MODEL        = os.environ.get("PIPER_MODEL",
                         os.path.expanduser("~/.taris/ru_RU-irina-medium.onnx"))
PIPER_MODEL_TMPFS  = os.path.join("/dev/shm/piper",
                         os.path.basename(os.path.expanduser(
                             "~/.taris/ru_RU-irina-medium.onnx")))
PIPER_MODEL_LOW    = os.environ.get("PIPER_MODEL_LOW",
                         os.path.expanduser("~/.taris/ru_RU-irina-low.onnx"))
PIPER_MODEL_DE     = os.environ.get("PIPER_MODEL_DE",
                         os.path.expanduser("~/.taris/de_DE-thorsten-medium.onnx"))
PIPER_MODEL_DE_TMPFS = os.path.join("/dev/shm/piper",
                         os.path.basename(os.path.expanduser(
                             "~/.taris/de_DE-thorsten-medium.onnx")))
WHISPER_BIN        = os.environ.get("WHISPER_BIN",  "/usr/local/bin/whisper-cpp")
WHISPER_MODEL      = os.environ.get("WHISPER_MODEL",
                         os.path.expanduser("~/.taris/ggml-base.bin"))
PIPEWIRE_RUNTIME   = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")

VOICE_SAMPLE_RATE     = 16000
VOICE_CHUNK_SIZE      = 4000       # 250 ms at 16 kHz
VOICE_SILENCE_TIMEOUT = 4.0        # seconds of silence → auto-stop
VOICE_MAX_DURATION    = 30.0       # hard session cap (seconds)
TTS_MAX_CHARS         = 600        # ~75 words / ~25 s on Pi 3 — cap for real-time voice chat
TTS_CHUNK_CHARS       = 1200       # ~150 words / ~55 s on Pi 3 — per-part cap for "Read aloud"
VOICE_TIMING_DEBUG    = os.environ.get("VOICE_TIMING_DEBUG", "0").lower() in ("1", "true", "yes")

# Strings file
_STRINGS_FILE = os.environ.get(
    "STRINGS_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strings.json"),
)

# ─────────────────────────────────────────────────────────────────────────────
# Voice optimization feature flags
# All OFF by default — enable via Admin → ⚡ Voice Opts menu.
# Settings persist in ~/.taris/voice_opts.json.
# ─────────────────────────────────────────────────────────────────────────────

_VOICE_OPTS_FILE      = os.path.expanduser("~/.taris/voice_opts.json")
_WEB_LINK_CODES_FILE  = os.path.expanduser("~/.taris/web_link_codes.json")
_PENDING_TTS_FILE    = os.path.expanduser("~/.taris/pending_tts.json")
_VOICE_OPTS_DEFAULTS: dict = {
    "silence_strip":     False,   # #1: strip leading/trailing silence (ffmpeg)
    "low_sample_rate":   False,   # #3: 8 kHz instead of 16 kHz for Vosk STT
    "warm_piper":        False,   # #4: pre-warm Piper ONNX model at startup
    "parallel_tts":      False,   # #5: start TTS thread immediately after LLM
    "user_audio_toggle": False,   # #9: show 🔊/🔇 per-voice-reply audio toggle
    "tmpfs_model":       False,   # #10: copy Piper ONNX to /dev/shm (RAM disk)
    "vad_prefilter":     False,   # §5.3: webrtcvad noise gate before Vosk STT
    "whisper_stt":       False,   # §5.3: use whisper.cpp tiny instead of Vosk
    "vosk_fallback":     True,    # §5.3: fall back to Vosk when Whisper returns nothing (set False to save ~180 MB RAM)
    "piper_low_model":   False,   # §5.3: use ru_RU-irina-low.onnx (faster TTS)
    "persistent_piper":  False,   # §5.3: keep warm Piper process alive (ONNX hot)
    "voice_timing_debug": False,  # show per-stage ⏱ timings in voice replies
}

# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

# WEB_ONLY=1 allows bot_auth / bot_llm / bot_web to import without Telegram config.
# telegram_menu_bot.py performs its own hard check at startup.
_WEB_ONLY = os.environ.get("WEB_ONLY", "0").lower() in ("1", "true", "yes")

if not _WEB_ONLY:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set. Add it to ~/.taris/bot.env")
    if not ALLOWED_USERS and not ADMIN_USERS:
        raise RuntimeError(
            "ALLOWED_USERS (or ALLOWED_USER / TELEGRAM_CHAT_ID) not set. "
            "Set to a comma-separated list of Telegram chat IDs."
    )

# ─────────────────────────────────────────────────────────────────────────────
# Logging — set up once here; all modules use getLogger("taris-tgbot")
# ─────────────────────────────────────────────────────────────────────────────

_LOG_FILE           = os.path.expanduser("~/.taris/telegram_bot.log")
_ASSISTANT_LOG_FILE = os.path.expanduser("~/.taris/assistant.log")
_SECURITY_LOG_FILE  = os.path.expanduser("~/.taris/security.log")
_VOICE_LOG_FILE     = os.path.expanduser("~/.taris/voice.log")
_DATASTORE_LOG_FILE = os.path.expanduser("~/.taris/datastore.log")
_log_handlers: list = [logging.StreamHandler()]
try:
    os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
    _log_handlers.append(logging.FileHandler(_LOG_FILE, encoding="utf-8"))
except OSError:
    pass  # dev environment without ~/.taris/ — log to console only

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_log_handlers,
)
log = logging.getLogger("taris-tgbot")
