"""
bot_remote_kb.py — Remote Knowledge Base agent (Phase 3).

Uses N8N MCP Server Trigger as the backend (SSE transport).
Handles: search queries, file ingest, doc listing, memory clear.

Public API (called from telegram_menu_bot.py):
    is_configured()          → bool
    show_menu(cid, bot, _t)
    start_search(cid, bot, _t)
    start_upload(cid, bot, _t)
    handle_message(cid, text, bot, _t)    → bool (True = consumed)
    handle_document(cid, doc, bot, _t)
    list_docs(cid, bot, _t)
    clear_memory(cid, bot, _t)
    cancel(cid)
"""

import logging
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.bot_config import (
    REMOTE_KB_ENABLED,
    MCP_REMOTE_URL,
    N8N_KB_API_KEY,
)
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
            title = d.get("title") or d.get("filename") or "—"
            n = d.get("chunk_count", "?")
            lines.append(f"• *{title}* ({n} chunks)")
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

def _do_search(chat_id: int, query: str, bot, _t) -> None:
    cancel(chat_id)
    status = bot.send_message(chat_id, _t(chat_id, "remote_kb_searching"), parse_mode="Markdown")
    try:
        chunks = _mcp.query_remote(query, chat_id=chat_id)
        if not chunks:
            bot.edit_message_text(
                _t(chat_id, "remote_kb_no_results"),
                chat_id, status.message_id, parse_mode="Markdown",
            )
            return
        lines = [_t(chat_id, "remote_kb_result_header").format(count=len(chunks))]
        for i, chunk in enumerate(chunks, 1):
            section = chunk.get("section") or chunk.get("doc_id") or "—"
            text    = (chunk.get("text") or chunk.get("chunk_text") or "")[:400]
            score   = chunk.get("score", 0.0)
            lines.append(f"\n*{i}. {section}* _(score: {score:.2f})_\n{text}")
        bot.edit_message_text(
            "\n".join(lines), chat_id, status.message_id,
            parse_mode="Markdown",
        )
    except Exception as exc:
        log.error("[remote_kb] search error: %s", exc)
        bot.edit_message_text(
            _t(chat_id, "remote_kb_op_fail").format(error=str(exc)[:120]),
            chat_id, status.message_id, parse_mode="Markdown",
        )


def _do_ingest(chat_id: int, doc, bot, _t) -> None:
    cancel(chat_id)
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
            )
            return
        n_chunks = result.get("n_chunks", "?")
        bot.edit_message_text(
            _t(chat_id, "remote_kb_upload_ok").format(filename=fname, n_chunks=n_chunks),
            chat_id, status.message_id, parse_mode="Markdown",
        )
    except Exception as exc:
        log.error("[remote_kb] ingest error: %s", exc)
        bot.edit_message_text(
            _t(chat_id, "remote_kb_upload_fail").format(error=str(exc)[:120]),
            chat_id, status.message_id, parse_mode="Markdown",
        )
