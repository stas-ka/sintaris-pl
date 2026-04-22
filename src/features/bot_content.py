"""
bot_content.py — Content Strategy Agent: AI-assisted content plan & post generation via N8N/OpenAI.

Modes:
  plan  — generate a 7-publication content plan for a niche/platform
  post  — write a single post (expert / selling / engaging)

Flow:
  1. User starts from Agents menu → selects mode
  2. Q1: niche + audience + goal (single combined text answer)
  3. Q2: platform (Telegram / Instagram / Facebook / VK / Website)
  4. Q3: use Taris Knowledge Base? [Yes/No inline buttons]
  5. Taris calls N8N taris-content-generate webhook → OpenAI returns content
  6. User sees preview with action buttons:
       ✏️ Correct   → types correction text → regenerate
       💾 Save Draft → saved to taris notes
       📄 Download  → sent as .txt file attachment
       📢 Publish   → asks channel → confirm → N8N taris-content-publish
       🔄 New       → back to mode selection
"""

import io
import logging
import threading
import uuid
from typing import Any, Callable

from features.bot_n8n import call_webhook
from core.bot_config import (
    N8N_CONTENT_GENERATE_WH,
    N8N_CONTENT_PUBLISH_WH,
    CONTENT_TG_CHANNEL_ID,
    N8N_CONTENT_TIMEOUT,
)

log = logging.getLogger("taris.content")

# ─────────────────────────────────────────────────────────────────────────────
# State — keyed by chat_id
# Steps: idle → mode_select → q1 → q2 → q3_kb → generating → preview
#        → correcting → ask_channel → confirming_publish
# ─────────────────────────────────────────────────────────────────────────────
_sessions: dict[int, dict] = {}


def is_active(chat_id: int) -> bool:
    return chat_id in _sessions


def get_step(chat_id: int) -> str:
    return _sessions.get(chat_id, {}).get("step", "idle")


def cancel(chat_id: int) -> None:
    _sessions.pop(chat_id, None)


def is_configured() -> bool:
    return bool(N8N_CONTENT_GENERATE_WH)


def _session(chat_id: int) -> dict:
    return _sessions.setdefault(chat_id, {})


# ─────────────────────────────────────────────────────────────────────────────
# Entry points (called from telegram_menu_bot.py callback handler)
# ─────────────────────────────────────────────────────────────────────────────

def show_menu(chat_id: int, bot: Any, t: Callable) -> None:
    """Show Content Strategist mode selection menu."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_plan"), callback_data="content_mode:plan"),
        InlineKeyboardButton(t(chat_id, "content_btn_post"), callback_data="content_mode:post"),
        InlineKeyboardButton(t(chat_id, "content_btn_back"), callback_data="agents_menu"),
    )
    bot.send_message(chat_id, t(chat_id, "content_menu_title"),
                     parse_mode="Markdown", reply_markup=kb)


def start_mode(chat_id: int, mode: str, bot: Any, t: Callable) -> None:
    """Begin a content generation session for the given mode (plan|post)."""
    sess = _session(chat_id)
    sess.update({"step": "q1", "mode": mode})
    key = "content_q1_plan" if mode == "plan" else "content_q1_post"
    bot.send_message(chat_id, t(chat_id, key), parse_mode="Markdown")


def _ask_platform(chat_id: int, bot: Any, t: Callable) -> None:
    """Ask Q2: platform selection."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=2)
    platforms = [
        ("content_q2_tg", "Telegram"),
        ("content_q2_ig", "Instagram"),
        ("content_q2_fb", "Facebook"),
        ("content_q2_vk", "VK"),
        ("content_q2_web", "Website"),
    ]
    for key, val in platforms:
        kb.add(InlineKeyboardButton(t(chat_id, key), callback_data=f"content_platform:{val}"))
    bot.send_message(chat_id, t(chat_id, "content_q2"),
                     parse_mode="Markdown", reply_markup=kb)


def _ask_kb(chat_id: int, bot: Any, t: Callable) -> None:
    """Ask Q3: use knowledge base?"""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_q3_kb_yes"), callback_data="content_kb:yes"),
        InlineKeyboardButton(t(chat_id, "content_q3_kb_no"),  callback_data="content_kb:no"),
    )
    bot.send_message(chat_id, t(chat_id, "content_q3_kb"),
                     parse_mode="Markdown", reply_markup=kb)


def on_platform_selected(chat_id: int, platform: str, bot: Any, t: Callable) -> None:
    """Callback: user selected platform via inline button."""
    sess = _session(chat_id)
    if sess.get("step") != "q2":
        return
    sess["q2"] = platform
    sess["step"] = "q3_kb"
    _ask_kb(chat_id, bot, t)


def on_kb_selected(chat_id: int, use_kb: bool, bot: Any, t: Callable) -> None:
    """Callback: user chose yes/no for knowledge base."""
    sess = _session(chat_id)
    if sess.get("step") != "q3_kb":
        return
    sess["use_kb"] = use_kb
    sess["step"] = "generating"
    _do_generate(chat_id, bot, t)


def _do_generate(chat_id: int, bot: Any, t: Callable, correction: str = "") -> None:
    """Kick off N8N generation in a background thread."""
    sess = _session(chat_id)
    sess["step"] = "generating"
    bot.send_message(chat_id, t(chat_id, "content_generating"), parse_mode="Markdown")

    def _run():
        try:
            kb_context = ""
            if sess.get("use_kb"):
                try:
                    from telegram.bot_access import _docs_rag_context
                    query = sess.get("q1", "")
                    kb_context = _docs_rag_context(chat_id, query) or ""
                except Exception as exc:
                    log.warning("[content] KB fetch failed: %s", exc)

            payload: dict[str, Any] = {
                "chat_id":    chat_id,
                "mode":       sess.get("mode", "plan"),
                "q1":         sess.get("q1", ""),
                "q2":         sess.get("q2", ""),
                "kb_context": kb_context,
                "correction": correction,
                "lang":       sess.get("lang", "ru"),
                "session_id": sess.get("session_id", str(uuid.uuid4())),
            }

            result = call_webhook(N8N_CONTENT_GENERATE_WH, payload, timeout=N8N_CONTENT_TIMEOUT)

            if result.get("error"):
                bot.send_message(
                    chat_id,
                    t(chat_id, "content_generate_error").format(error=result["error"]),
                    parse_mode="Markdown",
                )
                _sessions.pop(chat_id, None)
                return

            content = result.get("content") or result.get("result") or ""
            if not content:
                bot.send_message(
                    chat_id,
                    t(chat_id, "content_generate_error").format(error="Empty response from N8N"),
                    parse_mode="Markdown",
                )
                _sessions.pop(chat_id, None)
                return

            sess["content"] = content
            sess["step"] = "preview"
            _show_preview(chat_id, bot, t)

        except Exception as exc:
            log.exception("[content] generate thread error: %s", exc)
            bot.send_message(
                chat_id,
                t(chat_id, "content_generate_error").format(error=str(exc)),
                parse_mode="Markdown",
            )
            _sessions.pop(chat_id, None)

    threading.Thread(target=_run, daemon=True).start()


def _show_preview(chat_id: int, bot: Any, t: Callable) -> None:
    """Send content preview with action buttons."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    sess = _sessions.get(chat_id, {})
    content = sess.get("content", "")
    mode = sess.get("mode", "plan")

    preview_key = "content_preview_plan" if mode == "plan" else "content_preview_post"

    # Telegram message limit: 4096 chars. Truncate preview text if needed.
    max_content = 3800
    display = content[:max_content] + ("…" if len(content) > max_content else "")

    try:
        bot.send_message(
            chat_id,
            t(chat_id, preview_key).format(content=display),
            parse_mode="Markdown",
        )
    except Exception:
        # If Markdown parse fails, send as plain text
        bot.send_message(chat_id, display)

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_correct"),  callback_data="content_action:correct"),
        InlineKeyboardButton(t(chat_id, "content_btn_save"),     callback_data="content_action:save"),
    )
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_download"), callback_data="content_action:download"),
        InlineKeyboardButton(t(chat_id, "content_btn_publish"),  callback_data="content_action:publish"),
    )
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_new"),      callback_data="content_action:new"),
    )
    bot.send_message(chat_id, "━━━", reply_markup=kb)


def on_action(chat_id: int, action: str, bot: Any, t: Callable) -> None:
    """Handle preview action button press."""
    sess = _sessions.get(chat_id, {})
    if not sess or sess.get("step") != "preview":
        return

    if action == "correct":
        sess["step"] = "correcting"
        bot.send_message(chat_id, t(chat_id, "content_correct_prompt"), parse_mode="Markdown")

    elif action == "save":
        _do_save(chat_id, bot, t)

    elif action == "download":
        _do_download(chat_id, bot, t)

    elif action == "publish":
        sess["step"] = "ask_channel"
        default = CONTENT_TG_CHANNEL_ID
        if default:
            # Pre-fill with configured channel, still let user change
            bot.send_message(
                chat_id,
                t(chat_id, "content_ask_channel"),
                parse_mode="Markdown",
            )
            bot.send_message(chat_id, f"_Configured default: `{default}`_",
                             parse_mode="Markdown")
        else:
            bot.send_message(chat_id, t(chat_id, "content_ask_channel"), parse_mode="Markdown")

    elif action == "new":
        _sessions.pop(chat_id, None)
        show_menu(chat_id, bot, t)


def _do_save(chat_id: int, bot: Any, t: Callable) -> None:
    """Save content to taris notes."""
    sess = _sessions.get(chat_id, {})
    content = sess.get("content", "")
    mode = sess.get("mode", "plan")
    try:
        from telegram.bot_users import _save_note_text
        slug = f"content_{mode}_{uuid.uuid4().hex[:8]}"
        _save_note_text(chat_id, slug, content)
        bot.send_message(
            chat_id,
            t(chat_id, "content_save_done").format(slug=slug),
            parse_mode="Markdown",
        )
    except Exception as exc:
        log.warning("[content] save note error: %s", exc)
        bot.send_message(chat_id, t(chat_id, "content_save_error"), parse_mode="Markdown")
    finally:
        # Stay in preview so user can still publish/download
        sess["step"] = "preview"
        _show_preview(chat_id, bot, t)


def _do_download(chat_id: int, bot: Any, t: Callable) -> None:
    """Send content as a .txt file attachment."""
    sess = _sessions.get(chat_id, {})
    content = sess.get("content", "")
    mode = sess.get("mode", "plan")
    try:
        filename = f"content_{mode}_{uuid.uuid4().hex[:8]}.txt"
        data = content.encode("utf-8")
        bot.send_document(chat_id, (filename, io.BytesIO(data)))
    except Exception as exc:
        log.warning("[content] download error: %s", exc)
        bot.send_message(chat_id,
                         t(chat_id, "content_generate_error").format(error=str(exc)),
                         parse_mode="Markdown")
    finally:
        sess["step"] = "preview"


def on_channel_input(chat_id: int, channel: str, bot: Any, t: Callable) -> None:
    """Handle channel ID/username typed by user."""
    sess = _sessions.get(chat_id, {})
    if sess.get("step") != "ask_channel":
        return
    channel = channel.strip()
    if not channel:
        bot.send_message(chat_id, t(chat_id, "content_ask_channel"), parse_mode="Markdown")
        return
    sess["channel"] = channel
    sess["step"] = "confirming_publish"
    _ask_publish_confirm(chat_id, bot, t)


def _ask_publish_confirm(chat_id: int, bot: Any, t: Callable) -> None:
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    sess = _sessions.get(chat_id, {})
    channel = sess.get("channel", "?")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_publish_confirm"),
                             callback_data="content_publish:confirm"),
        InlineKeyboardButton(t(chat_id, "content_btn_publish_cancel"),
                             callback_data="content_publish:cancel"),
    )
    bot.send_message(
        chat_id,
        t(chat_id, "content_publish_confirm").format(channel=channel),
        parse_mode="Markdown",
        reply_markup=kb,
    )


def on_publish_decision(chat_id: int, decision: str, bot: Any, t: Callable) -> None:
    """Callback: user confirmed or cancelled channel publish."""
    sess = _sessions.get(chat_id, {})
    if sess.get("step") != "confirming_publish":
        return

    if decision == "cancel":
        sess["step"] = "preview"
        _show_preview(chat_id, bot, t)
        return

    if not N8N_CONTENT_PUBLISH_WH:
        bot.send_message(chat_id, t(chat_id, "content_publish_not_configured"),
                         parse_mode="Markdown")
        sess["step"] = "preview"
        return

    channel = sess.get("channel", "")
    content = sess.get("content", "")
    bot.send_message(
        chat_id,
        t(chat_id, "content_publishing").format(channel=channel),
        parse_mode="Markdown",
    )

    def _run():
        try:
            result = call_webhook(
                N8N_CONTENT_PUBLISH_WH,
                {"chat_id": chat_id, "channel": channel, "content": content},
                timeout=30,
            )
            if result.get("error"):
                bot.send_message(
                    chat_id,
                    t(chat_id, "content_publish_error").format(error=result["error"]),
                    parse_mode="Markdown",
                )
            else:
                bot.send_message(
                    chat_id,
                    t(chat_id, "content_published").format(channel=channel),
                    parse_mode="Markdown",
                )
        except Exception as exc:
            log.exception("[content] publish thread error: %s", exc)
            bot.send_message(
                chat_id,
                t(chat_id, "content_publish_error").format(error=str(exc)),
                parse_mode="Markdown",
            )
        finally:
            _sessions.pop(chat_id, None)

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Text message handler — called from telegram_menu_bot.py text_handler
# ─────────────────────────────────────────────────────────────────────────────

def handle_message(chat_id: int, text: str, bot: Any, t: Callable) -> bool:
    """Process incoming text for an active content session.

    Returns True if consumed (caller should return), False otherwise.
    """
    sess = _sessions.get(chat_id)
    if not sess:
        return False

    step = sess.get("step")

    if step == "q1":
        sess["q1"] = text.strip()
        sess["step"] = "q2"
        sess.setdefault("session_id", str(uuid.uuid4()))
        _ask_platform(chat_id, bot, t)
        return True

    if step == "correcting":
        correction = text.strip()
        _do_generate(chat_id, bot, t, correction=correction)
        return True

    if step == "ask_channel":
        on_channel_input(chat_id, text, bot, t)
        return True

    # Other steps use inline button callbacks, not text
    return False
