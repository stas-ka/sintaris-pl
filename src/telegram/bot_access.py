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

import concurrent.futures
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
    BOT_VERSION, LLM_PROVIDER, OLLAMA_MODEL, OPENAI_MODEL,
    STT_PROVIDER, FASTER_WHISPER_MODEL, PIPER_MODEL,
    RAG_ENABLED, RAG_TOP_K,
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


def _bot_config_block() -> str:
    """Return a concise [BOT CONFIG] block so the LLM can answer self-disclosure questions."""
    from pathlib import Path as _Path
    _llm_model = OLLAMA_MODEL if LLM_PROVIDER == "ollama" else OPENAI_MODEL
    _stt_model = FASTER_WHISPER_MODEL if STT_PROVIDER in ("faster_whisper", "fw") else STT_PROVIDER
    _piper = _Path(PIPER_MODEL).name if PIPER_MODEL else "piper"
    return (
        f"[BOT CONFIG]\n"
        f"Name: {BOT_NAME} | Version: {BOT_VERSION}\n"
        f"LLM: {LLM_PROVIDER}/{_llm_model}\n"
        f"STT: {STT_PROVIDER}/{_stt_model}\n"
        f"TTS: piper/{_piper}\n"
        f"[BOT CAPABILITIES]\n"
        f"- Document upload (PDF, TXT, DOCX, MD — up to 20 MB): send the file directly in chat\n"
        f"- Documents are indexed and used as a knowledge base (RAG) during conversations\n"
        f"- Calendar: add, view, edit and delete events via natural language or the menu\n"
        f"- Notes: create, view, append to and delete personal notes\n"
        f"- Voice: send a voice message and receive a spoken reply (STT → LLM → TTS)\n"
        f"- Mail digest: summarise unread emails from a connected mailbox\n"
        f"- Multi-language: Russian, English and German are supported\n"
        f"[END BOT CAPABILITIES]\n"
        f"[END BOT CONFIG]\n\n"
    )


def _calendar_context(chat_id: int) -> str:
    """Return a compact [CALENDAR] block with upcoming events (next 14 days), or empty string.

    Uses _cal_load() which already handles PostgreSQL → SQLite → JSON file fallback.
    """
    try:
        from features.bot_calendar import _cal_load
        from datetime import datetime, timedelta
        all_events = _cal_load(chat_id)
        if not all_events:
            return ""
        now    = datetime.now()
        cutoff = now + timedelta(days=14)
        events = [
            e for e in all_events
            if e.get("dt_iso") and now <= datetime.fromisoformat(e["dt_iso"]) <= cutoff
        ]
        if not events:
            # Include recent past events if no upcoming ones
            events = sorted(all_events, key=lambda e: e.get("dt_iso", ""), reverse=True)[:5]
        lines = ["[CALENDAR — upcoming events (next 14 days)]"]
        for ev in events[:20]:
            dt_str = ev.get("dt_iso", "")
            try:
                dt_fmt = datetime.fromisoformat(dt_str).strftime("%Y-%m-%d %H:%M")
            except Exception:
                dt_fmt = dt_str
            lines.append(f"  • {dt_fmt}  {ev.get('title', '')}")
        lines.append("[END CALENDAR]\n")
        return "\n".join(lines) + "\n"
    except Exception:
        return ""


def _notes_context(chat_id: int) -> str:
    """Return a [NOTES] block listing user's notes with content snippets, or empty string."""
    try:
        from core.store import store
        notes = store.list_notes(chat_id)
        if not notes:
            return ""
        lines = ["[NOTES — personal notes]"]
        for note in notes[:10]:
            title   = note.get("title") or "(untitled)"
            slug    = note.get("slug", "")
            content = (note.get("content") or "").strip()
            if not content and slug:
                try:
                    full    = store.load_note(chat_id, slug)
                    content = (full.get("content") or "").strip()
                except Exception:
                    pass
            snippet = (content[:200] + "…") if len(content) > 200 else content
            if snippet:
                lines.append(f"  • {title}: {snippet}")
            else:
                lines.append(f"  • {title}")
        lines.append("[END NOTES]\n")
        return "\n".join(lines) + "\n"
    except Exception:
        return ""


def _contacts_context(chat_id: int) -> str:
    """Return a compact [CONTACTS] block with user's contact list, or empty string."""
    try:
        from core.store import store
        contacts = store.list_contacts(chat_id)
        if not contacts:
            return ""
        lines = ["[CONTACTS]"]
        for c in contacts[:50]:
            parts = [c.get("name", "")]
            if c.get("phone"):
                parts.append(c["phone"])
            if c.get("email"):
                parts.append(c["email"])
            if c.get("notes"):
                parts.append(f"({str(c['notes'])[:80]})")
            lines.append("  • " + "  ".join(p for p in parts if p))
        lines.append("[END CONTACTS]\n")
        return "\n".join(lines) + "\n"
    except Exception:
        return ""


def _docs_rag_context(chat_id: int, query: str) -> str:
    """Return a [KNOWLEDGE] context block from user's documents, or empty string.

    Uses adaptive routing (classify_query) to skip RAG for simple queries.
    Uses RRF fusion when vector search is available (HYBRID/FULL tier).
    Falls back to FTS5-only on constrained hardware.
    Logs every retrieval to rag_log with latency_ms and query_type.
    """
    if not RAG_ENABLED:
        return ""
    try:
        import time
        from core.bot_rag import retrieve_context, classify_query
        from core.store import store
        from core.rag_settings import get as _rget
        from core.bot_db import db_get_user_pref

        rag_timeout = float(_rget("rag_timeout"))
        # Per-user overrides (user_prefs)
        top_k_pref = db_get_user_pref(chat_id, "rag_top_k")
        top_k = int(top_k_pref) if top_k_pref else int(_rget("rag_top_k"))

        t0 = time.monotonic()
        import concurrent.futures
        _user_is_admin = _is_admin(chat_id)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
            _fut = _pool.submit(retrieve_context, chat_id, query, top_k, 2000, _user_is_admin)
            try:
                chunks, assembled, strategy, trace = _fut.result(timeout=rag_timeout)
            except concurrent.futures.TimeoutError:
                log.warning("[RAG] timeout (%.0fs) chat_id=%s", rag_timeout, chat_id)
                return ""

        latency_ms = trace.get("latency_ms", int((time.monotonic() - t0) * 1000))

        if strategy == "skipped" or not assembled:
            return ""

        log.info("[RAG] strategy=%s fts5=%d vec=%d mcp=%d chunks=%d chars=%d latency=%dms",
                 strategy, trace.get("n_fts5", 0), trace.get("n_vector", 0),
                 trace.get("n_mcp", 0), len(chunks), len(assembled), latency_ms)
        try:
            store.log_rag_activity(
                chat_id, query, len(chunks), len(assembled),
                latency_ms=latency_ms, query_type=strategy,
                n_fts5=trace.get("n_fts5", 0),
                n_vector=trace.get("n_vector", 0),
                n_mcp=trace.get("n_mcp", 0),
            )
        except Exception:
            pass
        return f"[KNOWLEDGE FROM USER DOCUMENTS]\n{assembled}\n[END KNOWLEDGE]\n\n"
    except Exception as _e:
        log.debug("[RAG] docs context failed: %s", _e)
        return ""


def _rag_debug_stats(chat_id: int, query: str) -> dict:
    """Return RAG stats (chunks count, total chars) for the last retrieval for this query.

    Used by db_log_llm_call to record how much RAG context was injected.
    Returns {"chunks": 0, "chars": 0} on any error or when RAG is disabled.
    """
    if not RAG_ENABLED:
        return {"chunks": 0, "chars": 0}
    try:
        from core.store import store
        from core.rag_settings import get as _rget
        if not store.list_documents(chat_id):
            return {"chunks": 0, "chars": 0}
        rag_timeout = float(_rget("rag_timeout"))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
            _fut = _pool.submit(store.search_fts, query, chat_id, RAG_TOP_K)
            try:
                results = _fut.result(timeout=rag_timeout)
            except concurrent.futures.TimeoutError:
                return {"chunks": 0, "chars": 0}
        chunks = [r["chunk_text"] for r in (results or []) if r.get("chunk_text")]
        combined = "\n---\n".join(chunks)[:2000]
        return {"chunks": len(chunks), "chars": len(combined)}
    except Exception:
        return {"chunks": 0, "chars": 0}


def _with_lang(chat_id: int, user_text: str) -> str:
    """Prepend security preamble + bot config + RAG context + language instruction, then wrap user text.
    Used for single-turn LLM calls (ask_llm). For multi-turn use _build_system_message + _user_turn_content.
    """
    from security.bot_security import SECURITY_PREAMBLE, _wrap_user_input
    lang = _resolve_lang(chat_id, user_text)
    lang_instr = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION[_FALLBACK_LANG])
    rag_ctx = _docs_rag_context(chat_id, user_text)
    return SECURITY_PREAMBLE + _bot_config_block() + rag_ctx + lang_instr + _wrap_user_input(user_text)


def _build_system_message(chat_id: int, user_text: str = "") -> str:
    """Build the content for a role:system message in multi-turn LLM calls.

    Contains: security preamble + bot config + personal data context
    (calendar, notes, contacts) + memory context note + language instruction.
    """
    from security.bot_security import SECURITY_PREAMBLE
    lang = _resolve_lang(chat_id, user_text)
    lang_instr = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION[_FALLBACK_LANG])
    memory_note = (
        "You have access to the conversation history shown in this context. "
        "Use it to maintain coherent, context-aware responses across all turns.\n\n"
    )
    personal_ctx = _calendar_context(chat_id) + _notes_context(chat_id) + _contacts_context(chat_id)
    return SECURITY_PREAMBLE + _bot_config_block() + personal_ctx + memory_note + lang_instr


def _user_turn_content(chat_id: int, user_text: str) -> str:
    """Build the current user turn for a multi-turn call.

    Only contains RAG context (query-specific) + wrapped user text.
    Security preamble, bot config and lang instruction go in the system message.
    """
    from security.bot_security import _wrap_user_input
    rag_ctx = _docs_rag_context(chat_id, user_text)
    return rag_ctx + _wrap_user_input(user_text)


def _with_lang_voice(chat_id: int, stt_text: str) -> str:
    """Like _with_lang but includes STT-error hint for low-confidence words ([?word]).
    Kept for compatibility; voice pipeline now uses _voice_user_turn_content + history.
    """
    from security.bot_security import SECURITY_PREAMBLE, _wrap_user_input
    has_uncertain = bool(re.search(r'\[\?', stt_text))
    lang = _resolve_lang(chat_id, stt_text)
    instruction = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION[_FALLBACK_LANG])
    config_block = _bot_config_block()
    rag_ctx = _docs_rag_context(chat_id, stt_text)
    if has_uncertain:
        stt_hint = PROMPTS["stt_hints"].get(lang, PROMPTS["stt_hints"]["en"])
        return SECURITY_PREAMBLE + config_block + rag_ctx + instruction + stt_hint + _wrap_user_input(stt_text)
    return SECURITY_PREAMBLE + config_block + rag_ctx + instruction + _wrap_user_input(stt_text)


def _voice_user_turn_content(chat_id: int, stt_text: str) -> str:
    """Build the current user turn for a voice multi-turn call.

    Like _user_turn_content but adds the STT uncertainty hint when [?word]
    markers are present (low-confidence words from Vosk/Whisper).
    """
    from security.bot_security import _wrap_user_input
    rag_ctx = _docs_rag_context(chat_id, stt_text)
    has_uncertain = bool(re.search(r'\[\?', stt_text))
    if has_uncertain:
        lang = _resolve_lang(chat_id, stt_text)
        stt_hint = PROMPTS["stt_hints"].get(lang, PROMPTS["stt_hints"]["en"])
        return rag_ctx + stt_hint + _wrap_user_input(stt_text)
    return rag_ctx + _wrap_user_input(stt_text)


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


def _tg_send_with_retry(fn, *args, retries: int = 5, delay: float = 3.0, **kwargs):
    """Call a Telegram API function with up to ``retries`` attempts on network errors.

    Returns the result on success, or raises the last exception if all attempts fail.
    Only retries on connection/timeout errors, not on Telegram API logic errors
    (e.g. message too long, bad request).
    """
    import time as _time
    _last_exc: Exception = RuntimeError("no attempts")
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            _last_exc = e
            err_lower = str(e).lower()
            # Retry on transient network/timeout errors only
            if any(kw in err_lower for kw in (
                "timeout", "connection", "network", "reset by peer",
                "remotedisconnected", "read timed out", "socket", "eof",
            )):
                if attempt < retries - 1:
                    wait = min(delay * (2 ** attempt), 30.0)  # exponential, capped at 30s
                    log.warning("[TG] send attempt %d/%d failed: %s — retrying in %.0fs",
                                attempt + 1, retries, e, wait)
                    _time.sleep(wait)
                continue
            # Non-retriable error — raise immediately
            raise
    raise _last_exc


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
    if not _is_guest(chat_id):
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_notes"),    callback_data="menu_notes"))
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_calendar"), callback_data="menu_calendar"))
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_contacts"), callback_data="menu_contacts"))
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_docs"),     callback_data="menu_docs"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_profile"),  callback_data="profile"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_help"),     callback_data="help"))
    if _is_admin(chat_id):
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_error_protocol"), callback_data="errp_start"))
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_agents"), callback_data="agents_menu"))
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
