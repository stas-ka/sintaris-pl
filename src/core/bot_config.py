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



# ─────────────────────────────────────────────────────────────────────────────
# TARIS_HOME — runtime data directory
# Set TARIS_HOME in the OS environment (e.g. in a startup script) to redirect
# the bot's data directory away from the default ~/.taris/.
# This allows running multiple independent instances or a local dev deploy.
# ─────────────────────────────────────────────────────────────────────────────
TARIS_DIR = os.environ.get("TARIS_HOME") or os.path.expanduser("~/.taris")


def _th(rel: str) -> str:
    """Return absolute path inside TARIS_DIR."""
    return os.path.join(TARIS_DIR, rel)


# Load credentials: bot.env first, then .taris_env (bot.env takes priority via setdefault)
_load_env_file(_th("bot.env"))
_load_env_file(_th(".taris_env"))


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
                          _th("users.json"))
REGISTRATIONS_FILE  = os.environ.get("REGISTRATIONS_FILE",
                          _th("registrations.json"))
TARIS_BIN        = os.environ.get("TARIS_BIN", "/usr/bin/taris")
TARIS_CONFIG     = os.environ.get("TARIS_CONFIG",
                          _th("config.json"))

# ─────────────────────────────────────────────────────────────────────────────
# Deployment variant — controls optional features per platform
# DEVICE_VARIANT=picoclaw  → Raspberry Pi + PicoClaw robot (default)
# DEVICE_VARIANT=openclaw  → Laptop/PC + OpenClaw AI gateway
# ─────────────────────────────────────────────────────────────────────────────
DEVICE_VARIANT   = os.environ.get("DEVICE_VARIANT", "picoclaw").lower()

# OpenClaw AI gateway — optional provider (Feature §4.2 remote integration)
# Only active when DEVICE_VARIANT=openclaw or OPENCLAW_BIN is explicitly set.
# Falls back to taris/picoclaw automatically when the binary is not found.
OPENCLAW_BIN     = os.environ.get("OPENCLAW_BIN",     os.path.expanduser("~/.local/bin/openclaw"))
OPENCLAW_SESSION = os.environ.get("OPENCLAW_SESSION", "taris")
OPENCLAW_TIMEOUT = int(os.environ.get("OPENCLAW_TIMEOUT", "60"))

# Internal API token — authenticates skill-taris (sintaris-openclaw) on /api/* routes
# Required when DEVICE_VARIANT=openclaw so skill-taris can call /api/status and /api/chat.
TARIS_API_TOKEN  = os.environ.get("TARIS_API_TOKEN", "")

ACTIVE_MODEL_FILE   = os.environ.get("ACTIVE_MODEL_FILE",
                          _th("active_model.txt"))

# ─────────────────────────────────────────────────────────────────────────────
# LLM provider switching  (Feature 3.1 + 3.2)
# Set LLM_PROVIDER in TARIS_DIR/bot.env to switch backends.
# ─────────────────────────────────────────────────────────────────────────────

# Primary provider: taris | openai | yandexgpt | gemini | anthropic | local | ollama
LLM_PROVIDER        = os.environ.get("LLM_PROVIDER", "taris")

# Named fallback provider — analogous to STT_FALLBACK_PROVIDER.
# When the primary provider fails, LLM_FALLBACK_PROVIDER is tried before returning "".
# Example: LLM_PROVIDER=ollama  + LLM_FALLBACK_PROVIDER=openai   (local → cloud)
#          LLM_PROVIDER=openai  + LLM_FALLBACK_PROVIDER=ollama   (cloud → local)
# Leave empty to disable named fallback (independent of LLM_LOCAL_FALLBACK below).
LLM_FALLBACK_PROVIDER = os.environ.get("LLM_FALLBACK_PROVIDER", "")

# Legacy local llama.cpp fallback — enable with LLM_LOCAL_FALLBACK=1 (Feature 3.2)
# Only works when a llama.cpp / Ollama server is running on LLAMA_CPP_URL.
# Prefer LLM_FALLBACK_PROVIDER for named-provider fallback.
LLM_LOCAL_FALLBACK      = os.environ.get("LLM_LOCAL_FALLBACK", "0") == "1"
LLM_FALLBACK_FLAG_FILE  = _th("llm_fallback_enabled")  # runtime toggle
LLAMA_CPP_URL           = os.environ.get("LLAMA_CPP_URL",   "http://127.0.0.1:8081")
LLAMA_CPP_MODEL     = os.environ.get("LLAMA_CPP_MODEL", "")

# Ollama local LLM — OpenAI-compatible on port 11434 (OpenClaw variant default)
# Use LLM_PROVIDER=ollama or set LLM_LOCAL_FALLBACK=1 with LLAMA_CPP_URL pointing to Ollama.
# Install: curl -fsSL https://ollama.ai/install.sh | sh && ollama pull qwen2:0.5b
OLLAMA_URL          = os.environ.get("OLLAMA_URL",  "http://127.0.0.1:11434")
OLLAMA_MODEL        = os.environ.get("OLLAMA_MODEL", "qwen2:0.5b")

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

# ─────────────────────────────────────────────────────────────────────────────
# SMTP — outgoing mail for password reset notifications
# ─────────────────────────────────────────────────────────────────────────────
SMTP_HOST    = os.environ.get("SMTP_HOST",    "")
SMTP_PORT    = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER    = os.environ.get("SMTP_USER",    "")
SMTP_PASS    = os.environ.get("SMTP_PASS",    "")
SMTP_FROM    = os.environ.get("SMTP_FROM",    SMTP_USER)
ADMIN_EMAIL  = os.environ.get("ADMIN_EMAIL",  "")    # for admin notifications

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
    _th("conversation_history.json"),
)

DIGEST_SCRIPT       = os.environ.get("DIGEST_SCRIPT",
                          _th("gmail_digest.py"))
LAST_DIGEST_FILE    = os.environ.get("LAST_DIGEST_FILE",
                          _th("last_digest.txt"))
NOTES_DIR           = os.environ.get("NOTES_DIR",
                          _th("notes"))
CALENDAR_DIR        = os.environ.get("CALENDAR_DIR",
                          _th("calendar"))
MAIL_CREDS_DIR      = os.environ.get("MAIL_CREDS_DIR",
                          _th("mail_creds"))
ERROR_PROTOCOL_DIR  = os.environ.get("ERROR_PROTOCOL_DIR",
                          _th("error_protocols"))
DOCS_DIR            = os.environ.get("DOCS_DIR",
                          _th("docs"))

# ─────────────────────────────────────────────────────────────────────────────
# RAG (Retrieval-Augmented Generation) — FTS5 local knowledge base
# ─────────────────────────────────────────────────────────────────────────────
RAG_ENABLED    = os.environ.get("RAG_ENABLED",    "1") == "1"
RAG_TOP_K      = int(os.environ.get("RAG_TOP_K",      "3"))
RAG_CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "512"))
RAG_FLAG_FILE  = _th("rag_disabled")

# ─────────────────────────────────────────────────────────────────────────────
# Embedding Service — vector embeddings for semantic document search
# EMBED_MODEL: HuggingFace model name for fastembed / sentence-transformers.
#   Leave empty ("") to disable embedding generation (FTS5-only mode).
#   Default: "sentence-transformers/all-MiniLM-L6-v2" (384-dim, ~90 MB).
# EMBED_KEEP_RESIDENT: keep the model loaded in RAM between requests.
#   Set to "0" on memory-constrained devices (Pi 3 — 1 GB RAM).
# EMBED_DIMENSION: must match the model output size.
# ─────────────────────────────────────────────────────────────────────────────
EMBED_MODEL          = os.environ.get("EMBED_MODEL",
                           "sentence-transformers/all-MiniLM-L6-v2")
EMBED_KEEP_RESIDENT  = os.environ.get("EMBED_KEEP_RESIDENT", "1") == "1"
EMBED_DIMENSION      = int(os.environ.get("EMBED_DIMENSION", "384"))

# ─────────────────────────────────────────────────────────────────────────────
# RAG (Retrieval-Augmented Generation) — FTS5 local knowledge base
# ─────────────────────────────────────────────────────────────────────────────
RAG_ENABLED    = os.environ.get("RAG_ENABLED",    "1") == "1"
RAG_TOP_K      = int(os.environ.get("RAG_TOP_K",      "3"))
RAG_CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "512"))
RAG_FLAG_FILE  = os.path.expanduser("~/.taris/rag_disabled")

# ─────────────────────────────────────────────────────────────────────────────
# Bot version — bump on every user-visible deployment
# ─────────────────────────────────────────────────────────────────────────────

BOT_VERSION        = "2026.3.29"
RELEASE_NOTES_FILE = os.environ.get(
    "RELEASE_NOTES_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "release_notes.json"),
)
LAST_NOTIFIED_FILE = _th("last_notified_version.txt")

# ─────────────────────────────────────────────────────────────────────────────
# Voice pipeline constants
# ─────────────────────────────────────────────────────────────────────────────

VOSK_MODEL_PATH    = os.environ.get("VOSK_MODEL_PATH",
                         _th("vosk-model-small-ru"))
VOSK_MODEL_DE_PATH = os.environ.get("VOSK_MODEL_DE_PATH",
                         _th("vosk-model-small-de"))
PIPER_BIN          = os.environ.get("PIPER_BIN",  "/usr/local/bin/piper")
PIPER_MODEL        = os.environ.get("PIPER_MODEL",
                         _th("ru_RU-irina-medium.onnx"))
PIPER_MODEL_TMPFS  = os.path.join("/dev/shm/piper",
                         os.path.basename(os.path.expanduser(
                             "~/.taris/ru_RU-irina-medium.onnx")))
PIPER_MODEL_LOW    = os.environ.get("PIPER_MODEL_LOW",
                         _th("ru_RU-irina-low.onnx"))
PIPER_MODEL_DE     = os.environ.get("PIPER_MODEL_DE",
                         _th("de_DE-thorsten-medium.onnx"))
PIPER_MODEL_DE_TMPFS = os.path.join("/dev/shm/piper",
                         os.path.basename(os.path.expanduser(
                             "~/.taris/de_DE-thorsten-medium.onnx")))
WHISPER_BIN        = os.environ.get("WHISPER_BIN",  "/usr/local/bin/whisper-cpp")
WHISPER_MODEL      = os.environ.get("WHISPER_MODEL",
                         _th("ggml-base.bin"))
PIPEWIRE_RUNTIME   = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")
# Inference backend for hardware-accelerated STT (whisper-cpp).
# cpu      — pure CPU (default, always works)
# cuda     — NVIDIA GPU via CUDA-compiled whisper-cpp binary
# openvino — Intel NPU/GPU via OpenVINO backend (future)
VOICE_BACKEND      = os.environ.get("VOICE_BACKEND", "cpu").lower()

# STT provider — selects the speech recognition engine.
# vosk          — Vosk offline (lightweight, good for Pi 3/4)
# faster_whisper — faster-whisper (CTranslate2, better WER for laptop/PC)
# openai_whisper — OpenAI Whisper API (best accuracy for ru/en/de/sl, requires OPENAI_API_KEY)
# whisper_cpp   — whisper.cpp binary (hardware-accelerated, VOICE_BACKEND=cuda)
# Auto-default: faster_whisper for openclaw, vosk for picoclaw
_DEFAULT_STT = "faster_whisper" if os.environ.get("DEVICE_VARIANT", "picoclaw").lower() == "openclaw" else "vosk"
STT_PROVIDER            = os.environ.get("STT_PROVIDER", _DEFAULT_STT).lower()

# STT fallback — analogous to LLM_LOCAL_FALLBACK.
# When the primary provider fails (network error, missing key, model not loaded),
# STT_FALLBACK_PROVIDER is tried before returning empty.
# Example: STT_PROVIDER=openai_whisper  + STT_FALLBACK_PROVIDER=faster_whisper
#          STT_PROVIDER=faster_whisper  + STT_FALLBACK_PROVIDER=vosk
# Leave empty to disable fallback (default: auto-detect sensible default).
_DEFAULT_STT_FALLBACK = "vosk" if _DEFAULT_STT != "vosk" else ""
STT_FALLBACK_PROVIDER   = os.environ.get("STT_FALLBACK_PROVIDER", _DEFAULT_STT_FALLBACK).lower()

# faster-whisper model size: tiny, base, small, medium, large-v2, large-v3
# Recommended for i7/i5 no-GPU: base (good WER, ~0.3s RTF)
# Recommended for Pi 5 / modern laptop: small
FASTER_WHISPER_MODEL    = os.environ.get("FASTER_WHISPER_MODEL", "base")
FASTER_WHISPER_DEVICE   = os.environ.get("FASTER_WHISPER_DEVICE", "cpu")
FASTER_WHISPER_COMPUTE  = os.environ.get("FASTER_WHISPER_COMPUTE", "int8")

# Cloud STT via OpenAI Whisper API (STT_PROVIDER=openai_whisper)
# Reuses OPENAI_API_KEY + OPENAI_BASE_URL from LLM config.
# Best accuracy for ru/en/de/sl; requires valid OPENAI_API_KEY.
STT_OPENAI_MODEL        = os.environ.get("STT_OPENAI_MODEL", "whisper-1")
STT_LANG                = os.environ.get("STT_LANG", "ru")  # primary language hint (ru/en/de/sl)

VOICE_SAMPLE_RATE     = 16000
VOICE_CHUNK_SIZE      = 4000       # 250 ms at 16 kHz
VOICE_SILENCE_TIMEOUT = 4.0        # seconds of silence → auto-stop
VOICE_MAX_DURATION    = 30.0       # hard session cap (seconds)
TTS_MAX_CHARS         = 600        # ~75 words / ~25 s on Pi 3 — cap for real-time voice chat
TTS_CHUNK_CHARS       = 1200       # ~150 words / ~55 s on Pi 3 — per-part cap for "Read aloud"
VOICE_TIMING_DEBUG    = os.environ.get("VOICE_TIMING_DEBUG", "0").lower() in ("1", "true", "yes")

# Voice pipeline debug — saves every stage (audio, PCM, STT, LLM, TTS) to VOICE_DEBUG_DIR.
# Enable: VOICE_DEBUG_MODE=1 in bot.env.  All recordings land in VOICE_DEBUG_DIR.
# Use collected fixtures later for regression tests (copy to src/tests/voice/).
VOICE_DEBUG_MODE = os.environ.get("VOICE_DEBUG_MODE", "0").lower() in ("1", "true", "yes")
VOICE_DEBUG_DIR  = os.environ.get("VOICE_DEBUG_DIR",  _th("debug/voice"))

# Strings file
_STRINGS_FILE = os.environ.get(
    "STRINGS_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strings.json"),
)

# ─────────────────────────────────────────────────────────────────────────────
# Voice optimization feature flags
# All OFF by default — enable via Admin → ⚡ Voice Opts menu.
# Settings persist in TARIS_DIR/voice_opts.json.
# ─────────────────────────────────────────────────────────────────────────────

_VOICE_OPTS_FILE      = _th("voice_opts.json")
_WEB_LINK_CODES_FILE  = _th("web_link_codes.json")
_PENDING_TTS_FILE    = _th("pending_tts.json")
_VOICE_OPTS_DEFAULTS: dict = {
    "silence_strip":      False,   # #1: strip leading/trailing silence (ffmpeg)
    "low_sample_rate":    False,   # #3: 8 kHz instead of 16 kHz for Vosk STT
    "warm_piper":         False,   # #4: pre-warm Piper ONNX model at startup
    "parallel_tts":       False,   # #5: start TTS thread immediately after LLM
    "user_audio_toggle":  False,   # #9: show 🔊/🔇 per-voice-reply audio toggle
    "tmpfs_model":        False,   # #10: copy Piper ONNX to /dev/shm (RAM disk)
    "vad_prefilter":      False,   # §5.3: webrtcvad noise gate before STT
    "faster_whisper_stt": STT_PROVIDER == "faster_whisper",  # faster-whisper (Python, CTranslate2) — OpenClaw default
    "whisper_stt":        False,   # §5.3: use whisper.cpp binary instead of Vosk (Pi/whisper-cpp)
    "vosk_fallback":      True,    # §5.3: fall back to Vosk when primary STT returns nothing
    "piper_low_model":    False,   # §5.3: use ru_RU-irina-low.onnx (faster TTS)
    "persistent_piper":   False,   # §5.3: keep warm Piper process alive (ONNX hot)
    "voice_timing_debug": False,   # show per-stage ⏱ timings in voice replies
}

# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

# WEB_ONLY=1 allows bot_auth / bot_llm / bot_web to import without Telegram config.
# telegram_menu_bot.py performs its own hard check at startup.
_WEB_ONLY = os.environ.get("WEB_ONLY", "0").lower() in ("1", "true", "yes")

if not _WEB_ONLY:
    if not BOT_TOKEN:
        raise RuntimeError(f"BOT_TOKEN not set. Add it to {TARIS_DIR}/bot.env")
    if not ALLOWED_USERS and not ADMIN_USERS:
        raise RuntimeError(
            "ALLOWED_USERS (or ALLOWED_USER / TELEGRAM_CHAT_ID) not set. "
            "Set to a comma-separated list of Telegram chat IDs."
    )

# ─────────────────────────────────────────────────────────────────────────────
# Logging — set up once here; all modules use getLogger("taris-tgbot")
# ─────────────────────────────────────────────────────────────────────────────

_LOG_FILE           = _th("telegram_bot.log")
_ASSISTANT_LOG_FILE = _th("assistant.log")
_SECURITY_LOG_FILE  = _th("security.log")
_VOICE_LOG_FILE     = _th("voice.log")
_DATASTORE_LOG_FILE = _th("datastore.log")
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
