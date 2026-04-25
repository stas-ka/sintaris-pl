"""
bot_remote_kb.py — Remote Knowledge Base agent (Phase 3 + AutoResearch §23.4).

Uses N8N MCP Server Trigger as the backend (SSE transport).
Handles: search queries, file ingest, doc listing, memory clear.

AutoResearch improvements (v2026.4.77):
  - 5-class query type classifier: regulation/procedure/definition/example/general
  - Type-aware system prompts for better LLM framing
  - Confidence-based web search fallback (CRAG pattern):
    if max KB score < KB_WEB_SEARCH_THRESHOLD and KB_WEB_SEARCH_ENABLED,
    augments context with web results from bot_web_search.search_web()

Public API (called from telegram_menu_bot.py):
    is_configured()          → bool
    show_menu(cid, bot, _t)
    start_search(cid, bot, _t)
    start_upload(cid, bot, _t)
    finish_upload(cid, bot, _t)           ← called by remote_kb_upload_done callback
    handle_message(cid, text, bot, _t)    → bool (True = consumed)
    handle_document(cid, doc, bot, _t)
    list_docs(cid, bot, _t)
    clear_memory(cid, bot, _t)
    cancel(cid)
"""

import logging
import re
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.bot_config import (
    REMOTE_KB_ENABLED,
    MCP_REMOTE_URL,
    N8N_KB_API_KEY,
    KB_WEB_SEARCH_ENABLED,
    KB_WEB_SEARCH_THRESHOLD,
    KB_QUERY_CLASSIFY_ENABLED,
)
from core.bot_llm import ask_llm_with_history
from telegram.bot_access import _lang
import core.bot_mcp_client as _mcp

log = logging.getLogger("taris.remote_kb")

# ─── State (keyed by chat_id) ──────────────────────────────────────────────────
# step: idle | awaiting_query | awaiting_file
_sessions: dict[int, dict] = {}


# ─── Public API ───────────────────────────────────────────────────────────────

def is_configured() -> bool:
    """Return True if Remote KB is enabled and connected."""
    return bool(REMOTE_KB_ENABLED and MCP_REMOTE_URL and N8N_KB_API_KEY)


def is_active(chat_id: int) -> bool:
    return chat_id in _sessions


def cancel(chat_id: int) -> None:
    _sessions.pop(chat_id, None)


def finish_upload(chat_id: int, bot, _t) -> None:
    """End a multi-file upload session and return to the KB menu."""
    cancel(chat_id)
    show_menu(chat_id, bot, _t)


def show_menu(chat_id: int, bot, _t) -> None:
    """Send the Remote KB inline menu."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "remote_kb_search_btn"), callback_data="remote_kb_search"),
        InlineKeyboardButton(_t(chat_id, "remote_kb_upload_btn"), callback_data="remote_kb_upload"),
        InlineKeyboardButton(_t(chat_id, "remote_kb_list_btn"),   callback_data="remote_kb_list_docs"),
        InlineKeyboardButton(_t(chat_id, "remote_kb_clear_mem_btn"), callback_data="remote_kb_clear_mem"),
        InlineKeyboardButton(_t(chat_id, "agents_btn_back"),      callback_data="agents_menu"),
    )
    title = _t(chat_id, "remote_kb_menu_title")
    bot.send_message(
        chat_id,
        title,
        reply_markup=kb,
        parse_mode="Markdown",
    )


def start_search(chat_id: int, bot, _t) -> None:
    """Enter search mode: ask for query text."""
    _sessions[chat_id] = {"step": "awaiting_query"}
    bot.send_message(chat_id, _t(chat_id, "remote_kb_enter_query"), parse_mode="Markdown")


def start_upload(chat_id: int, bot, _t) -> None:
    """Enter upload mode: ask user to send a file."""
    _sessions[chat_id] = {"step": "awaiting_file"}
    bot.send_message(chat_id, _t(chat_id, "remote_kb_upload_prompt"), parse_mode="Markdown")


def handle_message(chat_id: int, text: str, bot, _t) -> bool:
    """Handle text for active remote-kb session. Returns True if consumed."""
    state = _sessions.get(chat_id)
    if not state:
        return False
    step = state.get("step")
    if step == "awaiting_query":
        _do_search(chat_id, text, bot, _t)
        return True
    return False


def handle_document(chat_id: int, doc, bot, _t) -> bool:
    """Handle document upload for active remote-kb session. Returns True if consumed."""
    state = _sessions.get(chat_id)
    if not state or state.get("step") != "awaiting_file":
        return False
    _do_ingest(chat_id, doc, bot, _t)
    return True


def list_docs(chat_id: int, bot, _t) -> None:
    """List documents in the remote KB."""
    msg = bot.send_message(chat_id, _t(chat_id, "remote_kb_searching"), parse_mode="Markdown")
    try:
        result = _mcp.call_tool("kb_list_documents", {"chat_id": chat_id})
        docs = result.get("documents", [])
        if not docs:
            bot.edit_message_text(
                _t(chat_id, "remote_kb_docs_empty"),
                chat_id, msg.message_id, parse_mode="Markdown",
            )
            return
        lines = [_t(chat_id, "remote_kb_docs_header")]
        for d in docs[:20]:
            title    = d.get("title") or d.get("filename") or "—"
            n        = d.get("n_chunks") or d.get("chunk_count", "?")
            tokens   = d.get("total_tokens", 0)
            created  = d.get("created_at", "—")
            sha      = d.get("sha256", "")
            sha_disp = sha[:12] + "…" if len(sha) > 12 else sha or "—"
            mime     = d.get("mime", "")
            preview  = d.get("preview", "")
            preview_line = f"\n  _{preview[:200]}_" if preview else ""
            lines.append(
                f"\n📄 *{title}*{preview_line}\n"
                f"  • {_t(chat_id, 'remote_kb_doc_mime')}: `{mime}`\n"
                f"  • {_t(chat_id, 'remote_kb_doc_chunks')}: {n} | {_t(chat_id, 'remote_kb_doc_tokens')}: {tokens}\n"
                f"  • {_t(chat_id, 'remote_kb_doc_date')}: {created}\n"
                f"  • SHA256: `{sha_disp}`"
            )
        bot.edit_message_text(
            "\n".join(lines), chat_id, msg.message_id, parse_mode="Markdown",
        )
    except Exception as exc:
        log.error("[remote_kb] list_docs error: %s", exc)
        bot.edit_message_text(
            _t(chat_id, "remote_kb_op_fail").format(error=str(exc)[:120]),
            chat_id, msg.message_id, parse_mode="Markdown",
        )


def clear_memory(chat_id: int, bot, _t) -> None:
    """Clear the per-user conversational memory tier in the remote KB."""
    try:
        _mcp.call_tool("kb_memory_clear", {"chat_id": chat_id, "tier": "short"})
        bot.send_message(chat_id, _t(chat_id, "remote_kb_mem_cleared"), parse_mode="Markdown")
    except Exception as exc:
        log.error("[remote_kb] clear_memory error: %s", exc)
        bot.send_message(chat_id, _t(chat_id, "remote_kb_op_fail").format(error=str(exc)[:120]))


# ─── Internal helpers ──────────────────────────────────────────────────────────

_LANG_PROMPT = {
    "ru": "Отвечай строго на русском языке.",
    "de": "Antworte ausschließlich auf Deutsch.",
    "en": "Answer in English.",
}

# 5-class query type → specialised system prompt fragment
_QUERY_TYPE_SYSTEM: dict[str, str] = {
    "regulation": (
        "You are a regulatory compliance expert. When citing requirements, "
        "include the exact section number, document number, and verbatim wording "
        "if available. Distinguish mandatory ('shall') from recommended ('should') "
        "requirements."
    ),
    "procedure": (
        "You are a safety procedures expert. List procedural steps clearly and "
        "in sequential order using the exact numbering found in the source. "
        "Do not paraphrase safety-critical instructions."
    ),
    "definition": (
        "Provide a precise definition as stated in the context. "
        "Quote the definition verbatim if it appears in the source, "
        "then briefly explain it."
    ),
    "example": (
        "Present the example exactly as described in the source text. "
        "Preserve original numbering and formatting."
    ),
    "general": (
        "You are a helpful assistant. Answer the user's question using ONLY "
        "the context excerpts below. If the answer is not in the context, "
        "say so clearly."
    ),
}

# Russian / German / English keyword patterns per query type
_QT_PATTERNS: dict[str, list[str]] = {
    "regulation": [
        r"(?:ГОСТ|СНиП|СП\s*\d|ПБЭЭ|НПА|ПУЭ|ФЗ|закон|указ|постановление|приказ)",
        r"(?:норм[аы]|правил[оа]|требовани[яе]|обязателен|обязательн|должен|Norm|Vorschrift|regulation|requirement)",
    ],
    "procedure": [
        r"(?:порядок|последовательност|алгоритм|шаги|инструкци[яю]|как\s+(?:выполн|провест|делать))",
        r"(?:process|procedure|steps|how\s+to|Ablauf|Verfahren)",
    ],
    "definition": [
        r"(?:что\s+такое|что\s+значит|определение|понятие|термин|значение\s+слова)",
        r"(?:define|definition|what\s+is\s+a?\s+|was\s+(?:ist|bedeutet))",
    ],
    "example": [
        r"(?:пример|образец|образ[цч]|пример документа|какой пример|покажи пример)",
        r"(?:example|sample|Beispiel)",
    ],
}


def _classify_query_type(query: str) -> str:
    """5-class heuristic query type classifier (no LLM call, < 1 ms).

    Classes: regulation | procedure | definition | example | general
    Used to select specialised system prompts and adjust retrieval strategy.
    """
    q = query.lower()
    for qtype, patterns in _QT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q, re.IGNORECASE):
                return qtype
    return "general"


def _do_search(chat_id: int, query: str, bot, _t) -> None:
    """KB search with query classification, web search fallback, and source attribution.

    Pipeline:
      1. Classify query type (5-class heuristic)
      2. Retrieve from KB (hybrid vector + FTS, top_k=MCP_REMOTE_TOP_K)
      3. If max score < KB_WEB_SEARCH_THRESHOLD and KB_WEB_SEARCH_ENABLED:
           augment context with web search results (CRAG pattern)
      4. LLM synthesis with type-aware system prompt
      5. Deduplicated source attribution footer
    """
    cancel(chat_id)
    status = bot.send_message(chat_id, _t(chat_id, "remote_kb_searching"), parse_mode="Markdown")
    try:
        # 1. Query classification (only when enabled)
        qtype = "general"
        if KB_QUERY_CLASSIFY_ENABLED:
            qtype = _classify_query_type(query)
            log.debug("[remote_kb] query type: %s for %r", qtype, query[:40])

        # 2. KB retrieval
        chunks = _mcp.query_remote(query, chat_id=chat_id)

        # 3. Web search fallback (CRAG) when KB confidence is low
        web_results: list[dict] = []
        if KB_WEB_SEARCH_ENABLED and chunks:
            max_score = max((c.get("score", 0.0) for c in chunks), default=0.0)
            if max_score < KB_WEB_SEARCH_THRESHOLD:
                log.info("[remote_kb] low KB confidence (%.3f < %.3f) — augmenting with web search",
                         max_score, KB_WEB_SEARCH_THRESHOLD)
                try:
                    from core.bot_web_search import search_web
                    web_results = search_web(query, num_results=5)
                except Exception as ws_exc:
                    log.warning("[remote_kb] web search failed: %s", ws_exc)

        if not chunks and not web_results:
            bot.edit_message_text(
                _t(chat_id, "remote_kb_no_results"),
                chat_id, status.message_id, parse_mode="Markdown",
            )
            return

        # 4. Build context string from KB chunks
        context_parts: list[str] = []
        for i, chunk in enumerate(chunks[:8], 1):
            section = chunk.get("section") or ""
            text    = (chunk.get("text") or chunk.get("chunk_text") or "").strip()
            if text:
                prefix = f"[{i}] {section}\n" if section else f"[{i}] "
                context_parts.append(prefix + text)

        # 4b. Append web results labeled distinctly from KB sources
        web_idx_start = len(context_parts) + 1
        for j, wr in enumerate(web_results[:5], web_idx_start):
            title   = wr.get("title", "")
            snippet = wr.get("snippet", "").strip()
            if snippet:
                label = f"[WEB {j}] {title}\n" if title else f"[WEB {j}] "
                context_parts.append(label + snippet)

        context = "\n\n".join(context_parts)

        lang       = _lang(chat_id)
        lang_instr = _LANG_PROMPT.get(lang, _LANG_PROMPT["en"])
        type_instr = _QUERY_TYPE_SYSTEM.get(qtype, _QUERY_TYPE_SYSTEM["general"])

        web_note = (
            "\n\nNote: some context excerpts are from web search (marked [WEB N]). "
            "Prefer KB sources but use web excerpts when KB lacks the information."
            if web_results else ""
        )
        system_msg = (
            f"{type_instr} {lang_instr}"
            f"{web_note}\n\nContext:\n{context}"
        )
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": query},
        ]
        answer = ask_llm_with_history(messages, timeout=90, use_case="chat", chat_id=chat_id)

        if not answer:
            bot.edit_message_text(
                _t(chat_id, "remote_kb_no_results"),
                chat_id, status.message_id, parse_mode="Markdown",
            )
            return

        # 5. Deduplicated source references footer
        seen: set[str] = set()
        sources: list[str] = []
        for chunk in chunks[:8]:
            src = chunk.get("section") or chunk.get("doc_id") or ""
            if src and src not in seen:
                seen.add(src)
                sources.append(src)
        for wr in web_results[:5]:
            url = wr.get("url", "")
            if url and url not in seen:
                seen.add(url)
                sources.append(url)
        if sources:
            answer += f"\n\n_{_t(chat_id, 'remote_kb_sources')}: {', '.join(sources)}_"

        bot.edit_message_text(answer, chat_id, status.message_id, parse_mode="Markdown")
    except Exception as exc:
        log.error("[remote_kb] search error: %s", exc)
        bot.edit_message_text(
            _t(chat_id, "remote_kb_op_fail").format(error=str(exc)[:120]),
            chat_id, status.message_id, parse_mode="Markdown",
        )


def _done_markup(chat_id: int, _t) -> InlineKeyboardMarkup:
    """Inline keyboard with a single 'Done uploading' button."""
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        _t(chat_id, "remote_kb_upload_done_btn"),
        callback_data="remote_kb_upload_done",
    ))
    return kb


def _do_ingest(chat_id: int, doc, bot, _t) -> None:
    # Keep session alive so the user can send more files.
    from core.bot_instance import bot as _bot
    status = bot.send_message(chat_id, _t(chat_id, "remote_kb_uploading"), parse_mode="Markdown")
    try:
        file_info = _bot.get_file(doc.file_id)
        file_bytes = _bot.download_file(file_info.file_path)
        fname = doc.file_name or "document"
        mime  = doc.mime_type or "application/octet-stream"
        result = _mcp.ingest_file(chat_id, fname, file_bytes, mime)
        if not result:
            bot.edit_message_text(
                _t(chat_id, "remote_kb_upload_empty"),
                chat_id, status.message_id, parse_mode="Markdown",
                reply_markup=_done_markup(chat_id, _t),
            )
            return
        if result.get("error"):
            bot.edit_message_text(
                _t(chat_id, "remote_kb_upload_fail").format(error=result["error"][:200]),
                chat_id, status.message_id, parse_mode="Markdown",
                reply_markup=_done_markup(chat_id, _t),
            )
            return
        n_chunks = result.get("n_chunks", "?")
        bot.edit_message_text(
            _t(chat_id, "remote_kb_upload_ok").format(filename=fname, n_chunks=n_chunks),
            chat_id, status.message_id, parse_mode="Markdown",
            reply_markup=_done_markup(chat_id, _t),
        )
    except Exception as exc:
        log.error("[remote_kb] ingest error: %s", exc)
        bot.edit_message_text(
            _t(chat_id, "remote_kb_upload_fail").format(error=str(exc)[:120]),
            chat_id, status.message_id, parse_mode="Markdown",
            reply_markup=_done_markup(chat_id, _t),
        )
