"""
bot_documents.py — Document upload, management, and FTS5 text search.

Supports: .txt, .md, .pdf, .docx
Pipeline: download → extract text → chunk → store via SQLite FTS5 (zero extra RAM, built-in)
"""
import os
import threading
import uuid
from pathlib import Path

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.bot_config import log, DOCS_DIR
from core.bot_instance import bot
from core.store import store
from telegram.bot_access import _is_guest, _t
from core.bot_config import RAG_CHUNK_SIZE

_SUPPORTED_EXTS = {".txt", ".md", ".pdf", ".docx"}
_CHUNK_SIZE = RAG_CHUNK_SIZE
_CHUNK_OVERLAP = 50


def _docs_user_dir(chat_id: int) -> Path:
    d = Path(DOCS_DIR) / str(chat_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _extract_text(file_path: Path, file_ext: str) -> str:
    """Extract plain text from a supported file type."""
    if file_ext in (".txt", ".md"):
        return file_path.read_text(encoding="utf-8", errors="replace")
    if file_ext == ".pdf":
        try:
            from pdfminer.high_level import extract_text as pdf_extract
            return pdf_extract(str(file_path)) or ""
        except Exception as e:
            log.warning("[Docs] PDF extraction failed: %s", e)
            return ""
    if file_ext == ".docx":
        try:
            from docx import Document
            return "\n".join(p.text for p in Document(str(file_path)).paragraphs)
        except Exception as e:
            log.warning("[Docs] DOCX extraction failed: %s", e)
            return ""
    return ""


def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list:
    """Split text into overlapping chunks."""
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return [c for c in chunks if c.strip()]


def _store_text_chunks(doc_id: str, chat_id: int, chunks: list) -> int:
    """Store text chunks via FTS5 — no embeddings, no external model, zero extra RAM."""
    for idx, chunk in enumerate(chunks):
        store.upsert_chunk_text(doc_id, idx, chat_id, chunk)
    return len(chunks)


def _handle_docs_menu(chat_id: int) -> None:
    """Show user's uploaded documents with delete buttons."""
    if not store.has_document_search():
        bot.send_message(chat_id, _t(chat_id, "docs_no_vector_search"))
        return
    try:
        docs = store.list_documents(chat_id)
    except Exception as e:
        log.error("[Docs] list_documents failed: %s", e)
        docs = []
    kb = InlineKeyboardMarkup(row_width=1)
    if docs:
        for d in docs:
            kb.add(InlineKeyboardButton(
                f"🗑 {d['title']}", callback_data=f"doc_del:{d['doc_id']}"))
        text = _t(chat_id, "docs_menu_title")
    else:
        text = _t(chat_id, "docs_empty")
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")


def _handle_doc_upload(message) -> None:
    """Handle an incoming document message from Telegram."""
    chat_id = message.chat.id
    if not store.has_document_search():
        bot.send_message(chat_id, _t(chat_id, "docs_no_vector_search"))
        return
    doc = message.document
    if not doc:
        return
    fname = doc.file_name or "document"
    ext = Path(fname).suffix.lower()
    if ext not in _SUPPORTED_EXTS:
        bot.send_message(chat_id, _t(chat_id, "docs_unsupported"))
        return
    status_msg = bot.send_message(chat_id, _t(chat_id, "docs_uploading"))

    def _process():
        try:
            doc_id = str(uuid.uuid4())
            dest = _docs_user_dir(chat_id) / f"{doc_id}{ext}"
            file_info = bot.get_file(doc.file_id)
            data = bot.download_file(file_info.file_path)
            dest.write_bytes(data)
            text = _extract_text(dest, ext)
            if not text.strip():
                bot.edit_message_text(
                    _t(chat_id, "docs_upload_failed"),
                    chat_id, status_msg.message_id)
                return
            chunks = _chunk_text(text)
            n = _store_text_chunks(doc_id, chat_id, chunks)
            store.save_document_meta(doc_id, chat_id, fname, str(dest), ext.lstrip("."))
            bot.edit_message_text(
                _t(chat_id, "docs_uploaded", title=fname, chunks=n),
                chat_id, status_msg.message_id, parse_mode="Markdown")
        except Exception as e:
            log.error("[Docs] upload failed: %s", e)
            try:
                bot.edit_message_text(_t(chat_id, "docs_upload_failed"),
                                      chat_id, status_msg.message_id)
            except Exception:
                pass

    threading.Thread(target=_process, daemon=True).start()


def _handle_doc_delete(chat_id: int, doc_id: str) -> None:
    """Show delete confirmation for a document."""
    try:
        docs = store.list_documents(chat_id)
        title = next((d["title"] for d in docs if d["doc_id"] == doc_id), doc_id)
    except Exception:
        title = doc_id
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ " + _t(chat_id, "yes"),
                             callback_data=f"doc_del_confirm:{doc_id}"),
        InlineKeyboardButton("❌ " + _t(chat_id, "no"),
                             callback_data="menu_docs"),
    )
    bot.send_message(chat_id,
                     _t(chat_id, "docs_delete_confirm", title=title),
                     reply_markup=kb, parse_mode="Markdown")


def _handle_doc_delete_confirmed(chat_id: int, doc_id: str) -> None:
    """Perform actual deletion of embeddings and document metadata."""
    try:
        store.delete_text_chunks(doc_id)
        store.delete_document(doc_id)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
        bot.send_message(chat_id, _t(chat_id, "docs_deleted"), reply_markup=kb)
    except Exception as e:
        log.error("[Docs] delete failed: %s", e)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
        bot.send_message(chat_id, _t(chat_id, "docs_delete_failed"), reply_markup=kb)
