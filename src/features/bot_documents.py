"""
bot_documents.py — Document upload, management, and FTS5 text search.

Supports: .txt, .md, .pdf, .docx
Pipeline: download → extract text → chunk → store via SQLite FTS5 (zero extra RAM, built-in)
         + optional vector embeddings when EmbeddingService + sqlite-vec are available.
"""
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.bot_config import log, DOCS_DIR, MAX_DOC_SIZE_MB
from core.bot_instance import bot
from core.store import store
from telegram.bot_access import _is_guest, _t
from core.bot_config import RAG_CHUNK_SIZE
import core.bot_state as _st

_SUPPORTED_EXTS = {".txt", ".md", ".pdf", ".docx"}
_CHUNK_SIZE = RAG_CHUNK_SIZE
_CHUNK_OVERLAP = 50

# pending rename state: {chat_id: doc_id}
_pending_rename: dict[int, str] = {}

# pending replace state: {chat_id: {"tmp_path": str, "file_ext": str, "orig_name": str}}
_pending_doc_replace: dict[int, dict] = {}


def _docs_user_dir(chat_id: int) -> Path:
    d = Path(DOCS_DIR) / str(chat_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _extract_text(file_path: Path, file_ext: str) -> str:
    """Extract plain text from a supported file type."""
    if file_ext in (".txt", ".md"):
        return file_path.read_text(encoding="utf-8", errors="replace")
    if file_ext == ".pdf":
        # Try PyMuPDF first (faster, handles images), fall back to pdfminer
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(file_path))
            parts = []
            for page_num, page in enumerate(doc, 1):
                parts.append(page.get_text())
                # Note image presence as placeholder
                img_list = page.get_images(full=False)
                if img_list:
                    parts.append(f"[IMAGE: page {page_num}, {len(img_list)} image(s)]")
            doc.close()
            result = "\n".join(parts).strip()
            if result:
                return result
        except ImportError:
            pass
        except Exception as e:
            log.warning("[Docs] PyMuPDF extraction failed: %s — trying pdfminer", e)
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


_MIN_CHUNK_CHARS = 20   # discard chunks shorter than this (navigation fragments, page numbers)


def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> tuple[list[str], int]:
    """Split text into overlapping chunks.

    Returns:
        (kept_chunks, skipped_count) — chunks shorter than _MIN_CHUNK_CHARS are skipped.
    """
    chunks, start, skipped = [], 0, 0
    while start < len(text):
        chunk = text[start:start + size]
        start += size - overlap
        if not chunk.strip():
            skipped += 1
            continue
        if len(chunk.strip()) < _MIN_CHUNK_CHARS:
            skipped += 1
            continue
        chunks.append(chunk)
    return chunks, skipped


def _store_text_chunks(doc_id: str, chat_id: int, chunks: list[str]) -> tuple[int, int]:
    """Store text chunks via FTS5; also generates vector embeddings when available.

    Returns:
        (n_chunks, n_embedded) — n_embedded is 0 when vector search is unavailable.
    """
    for idx, chunk in enumerate(chunks):
        store.upsert_chunk_text(doc_id, idx, chat_id, chunk)

    n_embedded = 0
    if store.has_vector_search():
        try:
            from core.bot_embeddings import EmbeddingService  # lazy import — heavy deps
            svc = EmbeddingService.get()
            if svc is not None:
                vecs = svc.embed_batch(chunks)
                if vecs:
                    for idx, vec in enumerate(vecs):
                        store.upsert_embedding(doc_id, idx, chat_id, vec)
                    n_embedded = len(vecs)
                    log.debug("[Docs] stored %d embeddings for doc %s", n_embedded, doc_id)
        except Exception as exc:
            log.warning("[Docs] embedding failed for doc %s: %s", doc_id, exc)

    return len(chunks), n_embedded


def _handle_docs_menu(chat_id: int) -> None:
    """Show user's uploaded documents with detail buttons."""
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
            shared = " 🔗" if d.get("is_shared") else ""
            kb.add(InlineKeyboardButton(
                f"📄 {d['title']}{shared}", callback_data=f"doc_detail:{d['doc_id']}"))
        text = _t(chat_id, "docs_menu_title") + "\n\n" + _t(chat_id, "docs_restrictions_info")
    else:
        text = _t(chat_id, "docs_empty") + "\n\n" + _t(chat_id, "docs_restrictions_info")
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu"))
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")


def _handle_doc_detail(chat_id: int, doc_id: str) -> None:
    """Show document detail card with action buttons."""
    try:
        docs = store.list_documents(chat_id)
        d = next((x for x in docs if x["doc_id"] == doc_id), None)
    except Exception:
        d = None
    if not d:
        bot.send_message(chat_id, _t(chat_id, "docs_not_found"))
        return
    meta = d.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    shared = "✅" if d.get("is_shared") else "❌"
    lines = [
        _t(chat_id, "docs_doc_detail"),
        f"*{d['title']}*",
        _t(chat_id, "docs_doc_type").format(doc_type=d.get("doc_type", "?")),
        _t(chat_id, "docs_doc_chunks").format(chunks=meta.get("n_chunks", "?")),
        _t(chat_id, "docs_doc_size").format(size=meta.get("file_size_bytes", "?")),
    ]
    n_embedded = meta.get("n_embedded")
    if n_embedded is not None:
        lines.append(_t(chat_id, "docs_doc_embeds").format(embeds=n_embedded))
    quality_pct = meta.get("quality_pct")
    if quality_pct is not None:
        lines.append(_t(chat_id, "docs_doc_quality").format(quality=quality_pct))
    lines += [
        _t(chat_id, "docs_doc_shared").format(shared=shared),
        _t(chat_id, "docs_doc_created").format(created=d.get("created_at", "")[:16]),
    ]
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(row_width=2)
    share_label = _t(chat_id, "docs_btn_unshare") if d.get("is_shared") else _t(chat_id, "docs_btn_share")
    kb.add(
        InlineKeyboardButton(_t(chat_id, "docs_btn_rename"), callback_data=f"doc_rename:{doc_id}"),
        InlineKeyboardButton(share_label, callback_data=f"doc_share:{doc_id}"),
    )
    kb.add(InlineKeyboardButton("🗑 " + _t(chat_id, "docs_btn_delete"), callback_data=f"doc_del:{doc_id}"))
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_back"), callback_data="menu_docs"))
    try:
        bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        bot.send_message(chat_id, text.replace("*", ""), reply_markup=kb)


def _handle_doc_rename_start(chat_id: int, doc_id: str) -> None:
    """Ask user for a new document title."""
    _pending_rename[chat_id] = doc_id
    _st._user_mode[chat_id] = "doc_rename"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(_t(chat_id, "btn_cancel"), callback_data=f"doc_detail:{doc_id}"))
    bot.send_message(chat_id, _t(chat_id, "docs_rename_prompt"), reply_markup=kb)


def _handle_doc_rename_done(chat_id: int, new_title: str) -> None:
    """Save the new title entered by the user."""
    doc_id = _pending_rename.pop(chat_id, None)
    _st._user_mode.pop(chat_id, None)
    if not doc_id or not new_title.strip():
        _handle_docs_menu(chat_id)
        return
    try:
        store.update_document_field(doc_id, title=new_title.strip())
        bot.send_message(chat_id, _t(chat_id, "docs_renamed"))
    except Exception as e:
        log.error("[Docs] rename failed: %s", e)
        bot.send_message(chat_id, _t(chat_id, "docs_rename_failed"))
    _handle_doc_detail(chat_id, doc_id)


def _handle_doc_share_toggle(chat_id: int, doc_id: str) -> None:
    """Toggle is_shared flag on a document."""
    try:
        docs = store.list_documents(chat_id)
        d = next((x for x in docs if x["doc_id"] == doc_id), None)
        if not d:
            return
        new_val = 0 if d.get("is_shared") else 1
        store.update_document_field(doc_id, is_shared=new_val)
        msg = _t(chat_id, "docs_shared_on") if new_val else _t(chat_id, "docs_shared_off")
        bot.send_message(chat_id, msg)
    except Exception as e:
        log.error("[Docs] share toggle failed: %s", e)
    _handle_doc_detail(chat_id, doc_id)


def _process_doc_file(chat_id: int, file_path: Path, file_ext: str, orig_name: str,
                      status_msg_id: int | None = None) -> None:
    """Extract text, chunk, and store a document file. Sends result to user."""
    try:
        t0 = time.monotonic()
        data = file_path.read_bytes()
        file_size = len(data)
        doc_hash = hashlib.sha256(data).hexdigest()

        doc_id = str(uuid.uuid4())
        dest = _docs_user_dir(chat_id) / f"{doc_id}{file_ext}"
        dest.write_bytes(data)
        text = _extract_text(dest, file_ext)
        if not text.strip():
            if status_msg_id:
                bot.edit_message_text(_t(chat_id, "docs_upload_failed"), chat_id, status_msg_id)
            else:
                bot.send_message(chat_id, _t(chat_id, "docs_upload_failed"))
            # Clean up the pending file if it's different from dest
            if file_path != dest and file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
            return
        chunks, skipped = _chunk_text(text)
        n, n_embedded = _store_text_chunks(doc_id, chat_id, chunks)
        parse_ms = int((time.monotonic() - t0) * 1000)
        total_parsed = n + skipped
        quality_pct = round(n / total_parsed * 100) if total_parsed else 100
        meta = {
            "char_count": len(text),
            "n_chunks": n,
            "n_skipped": skipped,
            "quality_pct": quality_pct,
            "n_embedded": n_embedded,
            "file_size_bytes": file_size,
            "parse_time_ms": parse_ms,
        }
        store.save_document_meta(doc_id, chat_id, orig_name, str(dest), file_ext.lstrip("."), meta)
        store.update_document_field(doc_id, doc_hash=doc_hash)
        msg = _t(chat_id, "docs_uploaded", title=orig_name, chunks=n)
        if status_msg_id:
            bot.edit_message_text(msg, chat_id, status_msg_id, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, msg, parse_mode="Markdown")
        # Clean up pending file if different from dest
        if file_path != dest and file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass
    except Exception as e:
        log.error("[Docs] process_doc_file failed: %s", e)
        try:
            if status_msg_id:
                bot.edit_message_text(_t(chat_id, "docs_upload_failed"), chat_id, status_msg_id)
            else:
                bot.send_message(chat_id, _t(chat_id, "docs_upload_failed"))
        except Exception:
            pass


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
    file_size = getattr(doc, "file_size", None) or 0
    if file_size > MAX_DOC_SIZE_MB * 1024 * 1024:
        bot.send_message(chat_id, _t(chat_id, "docs_too_large", max_mb=MAX_DOC_SIZE_MB))
        return
    status_msg = bot.send_message(chat_id, _t(chat_id, "docs_uploading"))

    def _process():
        try:
            file_info = bot.get_file(doc.file_id)
            data = bot.download_file(file_info.file_path)

            doc_hash = hashlib.sha256(data).hexdigest()
            existing = store.get_document_by_hash(chat_id, doc_hash)
            if existing:
                # Duplicate found — save pending file and offer replace/keep
                pending_id = str(uuid.uuid4())
                pending_path = _docs_user_dir(chat_id) / f"_pending_{pending_id}{ext}"
                pending_path.write_bytes(data)
                _pending_doc_replace[chat_id] = {
                    "tmp_path": str(pending_path),
                    "file_ext": ext,
                    "orig_name": fname,
                }
                kb = InlineKeyboardMarkup()
                kb.add(
                    InlineKeyboardButton(
                        _t(chat_id, "docs_replace_btn"),
                        callback_data=f"doc_replace:{existing['doc_id']}",
                    ),
                    InlineKeyboardButton(
                        _t(chat_id, "docs_keep_both_btn"),
                        callback_data="doc_keep_both",
                    ),
                )
                kb.add(InlineKeyboardButton(_t(chat_id, "docs_cancel_btn"), callback_data="docs_menu"))
                bot.edit_message_text(
                    _t(chat_id, "docs_dup_found").format(title=existing.get("title", fname)),
                    chat_id, status_msg.message_id,
                    reply_markup=kb, parse_mode="Markdown",
                )
                return

            # No duplicate — write to staging path and process
            staging_id = str(uuid.uuid4())
            staging_path = _docs_user_dir(chat_id) / f"_staging_{staging_id}{ext}"
            staging_path.write_bytes(data)
            _process_doc_file(chat_id, staging_path, ext, fname, status_msg.message_id)
        except Exception as e:
            log.error("[Docs] upload failed: %s", e)
            try:
                bot.edit_message_text(_t(chat_id, "docs_upload_failed"),
                                      chat_id, status_msg.message_id)
            except Exception:
                pass

    threading.Thread(target=_process, daemon=True).start()


def _handle_doc_replace(chat_id: int, old_doc_id: str) -> None:
    """Replace an existing document with the pending upload."""
    state = _pending_doc_replace.pop(chat_id, None)
    if not state:
        bot.send_message(chat_id, _t(chat_id, "docs_cancel_btn"))
        return
    try:
        store.delete_embeddings(old_doc_id)
        store.delete_text_chunks(old_doc_id)
        store.delete_document(old_doc_id)
    except Exception as e:
        log.warning("[Docs] replace: delete old failed: %s", e)
    _process_doc_file(chat_id, Path(state["tmp_path"]), state["file_ext"], state["orig_name"])


def _handle_doc_keep_both(chat_id: int) -> None:
    """Keep both documents — process the pending upload as new."""
    state = _pending_doc_replace.pop(chat_id, None)
    if not state:
        return
    _process_doc_file(chat_id, Path(state["tmp_path"]), state["file_ext"], state["orig_name"])


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
                             callback_data=f"doc_detail:{doc_id}"),
    )
    bot.send_message(chat_id,
                     _t(chat_id, "docs_delete_confirm", title=title),
                     reply_markup=kb, parse_mode="Markdown")


def _handle_doc_delete_confirmed(chat_id: int, doc_id: str) -> None:
    """Perform actual deletion of embeddings and document metadata."""
    try:
        store.delete_embeddings(doc_id)
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
