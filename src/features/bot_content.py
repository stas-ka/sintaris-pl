"""
bot_content.py — Content Strategy Agent v2: AI-assisted content plan & post generation.

Plan mode flow:
  1. Q1: niche + audience + goal
  2. Q2: platform (Telegram / Instagram / Facebook / VK / Website)
  3. Q3: use Taris Knowledge Base?
  4. N8N generates 7-post content plan (mode=plan)
  5. Plan preview: [Correct | ✅ Accept & Save | Download | New]
  6. On Accept: plan saved as note (slug cp_YYYYMMDDHHMMSS_HEX)
     → if 2 plans already exist: cleanup menu first (summarise old plan → long-term memory → delete)
  7. Stored plan displayed + numbered buttons [Post #1 … #7]
  8. User picks post #N → N8N generates full post (mode=post, post_index=N, plan_content)
  9. Post preview: [Correct | Save draft | Download | Publish | ◀ Back to plan | New]
     → Save: stored as note (slug post_YYYYMMDDHHMMSS_HEX)
     → if 10 posts already exist: cleanup menu first

Quick-post mode (standalone, no plan):
  Same Q1→Q2→Q3 flow but mode=post, no plan context.
  Post preview: [Correct | Save draft | Download | Publish | New]

Storage limits (per user):
  MAX_CONTENT_PLANS = 2   (notes with slug prefix cp_)
  MAX_CONTENT_POSTS = 10  (notes with slug prefix post_)
  Before any deletion: LLM summarises content → store.save_summary(tier='long')
"""

import io
import logging
import threading
import uuid
from datetime import datetime
from typing import Any, Callable

from features.bot_n8n import call_webhook
from core.bot_config import (
    N8N_CONTENT_GENERATE_WH,
    N8N_CONTENT_PUBLISH_WH,
    CONTENT_TG_CHANNEL_ID,
    N8N_CONTENT_TIMEOUT,
)

log = logging.getLogger("taris.content")

MAX_CONTENT_PLANS = 2
MAX_CONTENT_POSTS = 10
_PLAN_PREFIX = "cp_"
_POST_PREFIX = "post_"

# ─────────────────────────────────────────────────────────────────────────────
# Session state — keyed by chat_id
# Steps: idle → q1 → q2 → q3_kb
#        → generating_plan → plan_preview → correcting_plan
#        → plan_saved (shows plan + post select buttons)
#        → generating_post → post_preview → correcting_post
#        → ask_channel → confirming_publish
#        → cleanup_plans | cleanup_posts (limit enforcement)
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
# Storage helpers
# ─────────────────────────────────────────────────────────────────────────────

def _list_content_plans(chat_id: int) -> list[dict]:
    """Return saved content plans (notes with cp_ prefix), newest first."""
    try:
        from telegram.bot_users import _list_notes_for
        return [n for n in _list_notes_for(chat_id) if n["slug"].startswith(_PLAN_PREFIX)]
    except Exception as exc:
        log.warning("[content] list plans failed: %s", exc)
        return []


def _list_content_posts(chat_id: int) -> list[dict]:
    """Return saved posts (notes with post_ prefix), newest first."""
    try:
        from telegram.bot_users import _list_notes_for
        return [n for n in _list_notes_for(chat_id) if n["slug"].startswith(_POST_PREFIX)]
    except Exception as exc:
        log.warning("[content] list posts failed: %s", exc)
        return []


def _save_content_note(chat_id: int, slug: str, content: str) -> None:
    """Save content to taris notes DB."""
    from telegram.bot_users import _save_note_file
    _save_note_file(chat_id, slug, content)


def _load_content_note(chat_id: int, slug: str) -> str:
    """Load note content. Returns empty string if not found."""
    try:
        from telegram.bot_users import _load_note_text
        return _load_note_text(chat_id, slug) or ""
    except Exception:
        return ""


def _delete_content_note(chat_id: int, slug: str) -> None:
    """Delete a content note from DB and file."""
    try:
        from telegram.bot_users import _delete_note_file
        _delete_note_file(chat_id, slug)
    except Exception as exc:
        log.warning("[content] delete note failed: %s", exc)


def _summarize_to_long_term_memory(chat_id: int, content: str, label: str) -> None:
    """Summarise content via LLM and store as long-term memory."""
    try:
        from core.bot_llm import ask_llm
        from core.store import store
        prompt = (
            f"Summarise the following content plan or post in 3–5 sentences for "
            f"long-term memory. Capture the main topic, target audience, goals, and "
            f"key ideas. Label: {label}\n\n{content[:3000]}"
        )
        summary = ask_llm(prompt, timeout=30)
        if summary:
            store.save_summary(chat_id, f"[ContentAgent] {label}: {summary}", tier="long")
            log.info("[content] long-term memory saved for chat_id=%d label=%r", chat_id, label)
    except Exception as exc:
        log.warning("[content] summarise to memory failed: %s", exc)


def _new_slug(prefix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}{ts}_{uuid.uuid4().hex[:6]}"


# ─────────────────────────────────────────────────────────────────────────────
# Entry points
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
    sess.clear()
    sess.update({"step": "q1", "mode": mode, "session_id": str(uuid.uuid4())})
    key = "content_q1_plan" if mode == "plan" else "content_q1_post"
    bot.send_message(chat_id, t(chat_id, key), parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# Question flow — shared by both modes
# ─────────────────────────────────────────────────────────────────────────────

def _ask_platform(chat_id: int, bot: Any, t: Callable) -> None:
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=2)
    for key, val in [("content_q2_tg", "Telegram"), ("content_q2_ig", "Instagram"),
                     ("content_q2_fb", "Facebook"), ("content_q2_vk", "VK"),
                     ("content_q2_web", "Website")]:
        kb.add(InlineKeyboardButton(t(chat_id, key), callback_data=f"content_platform:{val}"))
    bot.send_message(chat_id, t(chat_id, "content_q2"), parse_mode="Markdown", reply_markup=kb)


def _ask_kb(chat_id: int, bot: Any, t: Callable) -> None:
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_q3_kb_yes"), callback_data="content_kb:yes"),
        InlineKeyboardButton(t(chat_id, "content_q3_kb_no"),  callback_data="content_kb:no"),
    )
    bot.send_message(chat_id, t(chat_id, "content_q3_kb"), parse_mode="Markdown", reply_markup=kb)


def on_platform_selected(chat_id: int, platform: str, bot: Any, t: Callable) -> None:
    sess = _session(chat_id)
    if sess.get("step") != "q2":
        return
    sess["q2"] = platform
    sess["step"] = "q3_kb"
    _ask_kb(chat_id, bot, t)


def on_kb_selected(chat_id: int, use_kb: bool, bot: Any, t: Callable) -> None:
    sess = _session(chat_id)
    if sess.get("step") != "q3_kb":
        return
    sess["use_kb"] = use_kb
    if sess.get("mode") == "plan":
        _do_generate_plan(chat_id, bot, t)
    else:
        _do_generate_post(chat_id, bot, t, post_index=0)


# ─────────────────────────────────────────────────────────────────────────────
# Plan generation
# ─────────────────────────────────────────────────────────────────────────────

def _do_generate_plan(chat_id: int, bot: Any, t: Callable, correction: str = "") -> None:
    """Generate content plan via N8N (background thread)."""
    sess = _session(chat_id)
    sess["step"] = "generating_plan"
    bot.send_message(chat_id, t(chat_id, "content_generating"), parse_mode="Markdown")

    def _run():
        try:
            payload: dict[str, Any] = {
                "chat_id":    chat_id,
                "mode":       "plan",
                "q1":         sess.get("q1", ""),
                "q2":         sess.get("q2", ""),
                "kb_context": _fetch_kb(chat_id, sess) if sess.get("use_kb") else "",
                "correction": correction,
                "lang":       sess.get("lang", "ru"),
                "session_id": sess.get("session_id", str(uuid.uuid4())),
            }
            result = call_webhook(N8N_CONTENT_GENERATE_WH, payload, timeout=N8N_CONTENT_TIMEOUT)
            if result.get("error"):
                bot.send_message(chat_id,
                    t(chat_id, "content_generate_error").format(error=result["error"]),
                    parse_mode="Markdown")
                _sessions.pop(chat_id, None)
                return
            content = result.get("content") or result.get("result") or ""
            if not content:
                bot.send_message(chat_id,
                    t(chat_id, "content_generate_error").format(error="Empty response"),
                    parse_mode="Markdown")
                _sessions.pop(chat_id, None)
                return
            sess["plan_content"] = content
            sess["step"] = "plan_preview"
            _show_plan_preview(chat_id, bot, t)
        except Exception as exc:
            log.exception("[content] plan generate error: %s", exc)
            bot.send_message(chat_id,
                t(chat_id, "content_generate_error").format(error=str(exc)),
                parse_mode="Markdown")
            _sessions.pop(chat_id, None)

    threading.Thread(target=_run, daemon=True).start()


def _show_plan_preview(chat_id: int, bot: Any, t: Callable) -> None:
    """Show plan with: Correct | Accept & Save | Download | New."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    sess = _sessions.get(chat_id, {})
    content = sess.get("plan_content", "")
    display = content[:3800] + ("…" if len(content) > 3800 else "")
    try:
        bot.send_message(chat_id, t(chat_id, "content_preview_plan").format(content=display),
                         parse_mode="Markdown")
    except Exception:
        bot.send_message(chat_id, display)
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_correct"),     callback_data="content_plan_action:correct"),
        InlineKeyboardButton(t(chat_id, "content_btn_accept_plan"), callback_data="content_plan_action:accept"),
    )
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_download"), callback_data="content_plan_action:download"),
        InlineKeyboardButton(t(chat_id, "content_btn_new"),      callback_data="content_plan_action:new"),
    )
    bot.send_message(chat_id, "━━━", reply_markup=kb)


def on_plan_action(chat_id: int, action: str, bot: Any, t: Callable) -> None:
    """Handle plan preview / saved plan button press."""
    sess = _sessions.get(chat_id, {})
    if not sess:
        return
    step = sess.get("step")

    if action == "correct":
        if step != "plan_preview":
            return
        sess["step"] = "correcting_plan"
        bot.send_message(chat_id, t(chat_id, "content_correct_prompt"), parse_mode="Markdown")

    elif action == "accept":
        if step != "plan_preview":
            return
        _accept_and_save_plan(chat_id, bot, t)

    elif action == "download":
        # Download works from both plan_preview and plan_saved
        _do_download(chat_id, bot, t, content_key="plan_content", label="plan")
        if step == "plan_saved":
            _show_plan_with_post_buttons(chat_id, bot, t)
        # plan_preview: buttons still visible, user can act further

    elif action == "new":
        _sessions.pop(chat_id, None)
        show_menu(chat_id, bot, t)


def _accept_and_save_plan(chat_id: int, bot: Any, t: Callable) -> None:
    """Check limit; show cleanup menu if needed, otherwise save."""
    sess = _sessions.get(chat_id, {})
    plans = _list_content_plans(chat_id)
    if len(plans) >= MAX_CONTENT_PLANS:
        sess["step"] = "cleanup_plans"
        sess["pending_save"] = "plan"
        _show_cleanup_menu(chat_id, "plan", plans, bot, t)
        return
    _do_save_plan(chat_id, bot, t)


def _do_save_plan(chat_id: int, bot: Any, t: Callable) -> None:
    """Save plan to notes and transition to plan_saved."""
    sess = _sessions.get(chat_id, {})
    content = sess.get("plan_content", "")
    slug = _new_slug(_PLAN_PREFIX)
    try:
        _save_content_note(chat_id, slug, content)
        sess["plan_slug"] = slug
        sess["step"] = "plan_saved"
        bot.send_message(chat_id, t(chat_id, "content_plan_saved"), parse_mode="Markdown")
        _show_plan_with_post_buttons(chat_id, bot, t)
    except Exception as exc:
        log.warning("[content] save plan error: %s", exc)
        bot.send_message(chat_id, t(chat_id, "content_save_error"), parse_mode="Markdown")
        sess["step"] = "plan_preview"


def _show_plan_with_post_buttons(chat_id: int, bot: Any, t: Callable) -> None:
    """Display stored plan + numbered [Post #1…#7] generation buttons."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    sess = _sessions.get(chat_id, {})
    content = sess.get("plan_content", "")
    display = content[:3800] + ("…" if len(content) > 3800 else "")
    try:
        bot.send_message(chat_id, t(chat_id, "content_plan_header").format(content=display),
                         parse_mode="Markdown")
    except Exception:
        bot.send_message(chat_id, display)
    kb = InlineKeyboardMarkup(row_width=2)
    post_btns = [
        InlineKeyboardButton(t(chat_id, "content_btn_gen_post").format(n=n),
                             callback_data=f"content_genpost:{n}")
        for n in range(1, 8)
    ]
    kb.add(*post_btns)
    kb.row(
        InlineKeyboardButton(t(chat_id, "content_btn_download"), callback_data="content_plan_action:download"),
        InlineKeyboardButton(t(chat_id, "content_btn_new"),      callback_data="content_plan_action:new"),
    )
    bot.send_message(chat_id, t(chat_id, "content_select_post_prompt"), reply_markup=kb)


# ─────────────────────────────────────────────────────────────────────────────
# Post generation (from plan or standalone)
# ─────────────────────────────────────────────────────────────────────────────

def on_genpost_selected(chat_id: int, post_index: int, bot: Any, t: Callable) -> None:
    """User selected post #N to expand from the saved plan."""
    sess = _sessions.get(chat_id, {})
    if not sess or sess.get("step") not in ("plan_saved", "post_preview"):
        return
    sess["post_index"] = post_index
    _do_generate_post(chat_id, bot, t, post_index=post_index)


def _do_generate_post(chat_id: int, bot: Any, t: Callable,
                      post_index: int = 0, correction: str = "") -> None:
    """Generate post content via N8N (background thread)."""
    sess = _session(chat_id)
    sess["step"] = "generating_post"
    if post_index:
        bot.send_message(chat_id,
            t(chat_id, "content_generating_post").format(n=post_index),
            parse_mode="Markdown")
    else:
        bot.send_message(chat_id, t(chat_id, "content_generating"), parse_mode="Markdown")

    def _run():
        try:
            payload: dict[str, Any] = {
                "chat_id":      chat_id,
                "mode":         "post",
                "q1":           sess.get("q1", ""),
                "q2":           sess.get("q2", ""),
                "kb_context":   _fetch_kb(chat_id, sess) if sess.get("use_kb") else "",
                "correction":   correction,
                "lang":         sess.get("lang", "ru"),
                "session_id":   sess.get("session_id", str(uuid.uuid4())),
                "post_index":   post_index,
                "plan_content": sess.get("plan_content", ""),
            }
            result = call_webhook(N8N_CONTENT_GENERATE_WH, payload, timeout=N8N_CONTENT_TIMEOUT)
            if result.get("error"):
                bot.send_message(chat_id,
                    t(chat_id, "content_generate_error").format(error=result["error"]),
                    parse_mode="Markdown")
                _recover_after_post_error(chat_id, bot, t, sess)
                return
            content = result.get("content") or result.get("result") or ""
            if not content:
                bot.send_message(chat_id,
                    t(chat_id, "content_generate_error").format(error="Empty response"),
                    parse_mode="Markdown")
                _recover_after_post_error(chat_id, bot, t, sess)
                return
            sess["post_content"] = content
            sess["step"] = "post_preview"
            _show_post_preview(chat_id, bot, t)
        except Exception as exc:
            log.exception("[content] post generate error: %s", exc)
            bot.send_message(chat_id,
                t(chat_id, "content_generate_error").format(error=str(exc)),
                parse_mode="Markdown")
            _recover_after_post_error(chat_id, bot, t, sess)

    threading.Thread(target=_run, daemon=True).start()


def _recover_after_post_error(chat_id: int, bot: Any, t: Callable, sess: dict) -> None:
    if sess.get("plan_slug"):
        sess["step"] = "plan_saved"
        _show_plan_with_post_buttons(chat_id, bot, t)
    else:
        _sessions.pop(chat_id, None)


def _show_post_preview(chat_id: int, bot: Any, t: Callable) -> None:
    """Show post with action buttons."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    sess = _sessions.get(chat_id, {})
    content = sess.get("post_content", "")
    post_index = sess.get("post_index", 0)
    display = content[:3800] + ("…" if len(content) > 3800 else "")
    preview_key = "content_preview_post_from_plan" if post_index else "content_preview_post"
    try:
        bot.send_message(chat_id,
            t(chat_id, preview_key).format(content=display, n=post_index),
            parse_mode="Markdown")
    except Exception:
        bot.send_message(chat_id, display)
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_correct"),  callback_data="content_post_action:correct"),
        InlineKeyboardButton(t(chat_id, "content_btn_save"),     callback_data="content_post_action:save"),
    )
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_download"), callback_data="content_post_action:download"),
        InlineKeyboardButton(t(chat_id, "content_btn_publish"),  callback_data="content_post_action:publish"),
    )
    if sess.get("plan_slug"):
        kb.add(
            InlineKeyboardButton(t(chat_id, "content_btn_back_to_plan"), callback_data="content_post_action:back_plan"),
            InlineKeyboardButton(t(chat_id, "content_btn_new"),          callback_data="content_post_action:new"),
        )
    else:
        kb.add(InlineKeyboardButton(t(chat_id, "content_btn_new"), callback_data="content_post_action:new"))
    bot.send_message(chat_id, "━━━", reply_markup=kb)


def on_post_action(chat_id: int, action: str, bot: Any, t: Callable) -> None:
    """Handle post preview button press."""
    sess = _sessions.get(chat_id, {})
    if not sess or sess.get("step") != "post_preview":
        return

    if action == "correct":
        sess["step"] = "correcting_post"
        bot.send_message(chat_id, t(chat_id, "content_correct_prompt"), parse_mode="Markdown")

    elif action == "save":
        _accept_and_save_post(chat_id, bot, t)

    elif action == "download":
        _do_download(chat_id, bot, t, content_key="post_content", label="post")
        _show_post_preview(chat_id, bot, t)

    elif action == "publish":
        sess["step"] = "ask_channel"
        bot.send_message(chat_id, t(chat_id, "content_ask_channel"), parse_mode="Markdown")
        default = CONTENT_TG_CHANNEL_ID
        if default:
            bot.send_message(chat_id, f"_Configured default: `{default}`_", parse_mode="Markdown")

    elif action == "back_plan":
        sess["step"] = "plan_saved"
        _show_plan_with_post_buttons(chat_id, bot, t)

    elif action == "new":
        _sessions.pop(chat_id, None)
        show_menu(chat_id, bot, t)


def _accept_and_save_post(chat_id: int, bot: Any, t: Callable) -> None:
    """Check limit; show cleanup menu if needed, otherwise save."""
    sess = _sessions.get(chat_id, {})
    posts = _list_content_posts(chat_id)
    if len(posts) >= MAX_CONTENT_POSTS:
        sess["step"] = "cleanup_posts"
        sess["pending_save"] = "post"
        _show_cleanup_menu(chat_id, "post", posts, bot, t)
        return
    _do_save_post(chat_id, bot, t)


def _do_save_post(chat_id: int, bot: Any, t: Callable) -> None:
    """Save post draft to notes and return to post_preview."""
    sess = _sessions.get(chat_id, {})
    content = sess.get("post_content", "")
    slug = _new_slug(_POST_PREFIX)
    try:
        _save_content_note(chat_id, slug, content)
        bot.send_message(chat_id,
            t(chat_id, "content_save_done").format(slug=slug),
            parse_mode="Markdown")
        sess["step"] = "post_preview"
        _show_post_preview(chat_id, bot, t)
    except Exception as exc:
        log.warning("[content] save post error: %s", exc)
        bot.send_message(chat_id, t(chat_id, "content_save_error"), parse_mode="Markdown")
        sess["step"] = "post_preview"


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup — storage limit enforcement
# ─────────────────────────────────────────────────────────────────────────────

def _show_cleanup_menu(chat_id: int, item_type: str, items: list[dict],
                       bot: Any, t: Callable) -> None:
    """Show list of existing items to delete to make room for a new one."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    count = len(items)
    max_val = MAX_CONTENT_PLANS if item_type == "plan" else MAX_CONTENT_POSTS
    limit_key = "content_limit_plans" if item_type == "plan" else "content_limit_posts"
    bot.send_message(chat_id,
        t(chat_id, limit_key).format(count=count, max=max_val),
        parse_mode="Markdown")
    kb = InlineKeyboardMarkup(row_width=1)
    for item in items[:8]:
        title = (item.get("title") or item.get("slug", "?"))[:40]
        slug = item["slug"]
        kb.add(InlineKeyboardButton(
            f"🗑️ {title}",
            callback_data=f"content_del:{item_type}:{slug}",
        ))
    kb.add(InlineKeyboardButton(t(chat_id, "content_btn_new"), callback_data="content_plan_action:new"))
    bot.send_message(chat_id, t(chat_id, "content_cleanup_prompt"), reply_markup=kb)


def on_delete_request(chat_id: int, item_type: str, slug: str, bot: Any, t: Callable) -> None:
    """User tapped a delete button — show confirmation."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    sess = _sessions.get(chat_id, {})
    if not sess:
        return
    sess["del_type"] = item_type
    sess["del_slug"] = slug
    # Resolve title from cached notes list
    try:
        from telegram.bot_users import _list_notes_for
        notes = _list_notes_for(chat_id)
        note = next((n for n in notes if n["slug"] == slug), None)
        title = note.get("title", slug) if note else slug
    except Exception:
        title = slug
    sess["del_title"] = title
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_delete_yes"), callback_data="content_del_confirm"),
        InlineKeyboardButton(t(chat_id, "content_btn_delete_no"),  callback_data="content_del_cancel"),
    )
    bot.send_message(chat_id,
        t(chat_id, "content_delete_confirm").format(title=title),
        parse_mode="Markdown",
        reply_markup=kb)


def on_delete_confirmed(chat_id: int, bot: Any, t: Callable) -> None:
    """User confirmed deletion — summarise to long-term memory, delete, continue."""
    sess = _sessions.get(chat_id, {})
    slug  = sess.pop("del_slug", "")
    itype = sess.pop("del_type", "")
    title = sess.pop("del_title", slug)
    if not slug:
        return
    # Load content before deletion for summarisation
    content = _load_content_note(chat_id, slug)
    if content:
        threading.Thread(target=_summarize_to_long_term_memory,
                         args=(chat_id, content, title), daemon=True).start()
    _delete_content_note(chat_id, slug)
    bot.send_message(chat_id, t(chat_id, "content_delete_done"), parse_mode="Markdown")
    # Re-check limit and continue with the pending save
    pending = sess.get("pending_save", "")
    if pending == "plan":
        sess.pop("pending_save", None)
        if len(_list_content_plans(chat_id)) < MAX_CONTENT_PLANS:
            sess["step"] = "plan_preview"
            _do_save_plan(chat_id, bot, t)
        else:
            _show_cleanup_menu(chat_id, "plan", _list_content_plans(chat_id), bot, t)
    elif pending == "post":
        sess.pop("pending_save", None)
        if len(_list_content_posts(chat_id)) < MAX_CONTENT_POSTS:
            sess["step"] = "post_preview"
            _do_save_post(chat_id, bot, t)
        else:
            _show_cleanup_menu(chat_id, "post", _list_content_posts(chat_id), bot, t)


def on_delete_cancelled(chat_id: int, bot: Any, t: Callable) -> None:
    """User cancelled deletion — return to cleanup menu or main menu."""
    sess = _sessions.get(chat_id, {})
    sess.pop("del_slug", None)
    sess.pop("del_type", None)
    sess.pop("del_title", None)
    pending = sess.get("pending_save", "")
    if pending == "plan":
        _show_cleanup_menu(chat_id, "plan", _list_content_plans(chat_id), bot, t)
    elif pending == "post":
        _show_cleanup_menu(chat_id, "post", _list_content_posts(chat_id), bot, t)
    else:
        _sessions.pop(chat_id, None)
        show_menu(chat_id, bot, t)


# ─────────────────────────────────────────────────────────────────────────────
# Publish flow
# ─────────────────────────────────────────────────────────────────────────────

def on_channel_input(chat_id: int, channel: str, bot: Any, t: Callable) -> None:
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
    channel = _sessions.get(chat_id, {}).get("channel", "?")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "content_btn_publish_confirm"), callback_data="content_publish:confirm"),
        InlineKeyboardButton(t(chat_id, "content_btn_publish_cancel"),  callback_data="content_publish:cancel"),
    )
    bot.send_message(chat_id,
        t(chat_id, "content_publish_confirm").format(channel=channel),
        parse_mode="Markdown", reply_markup=kb)


def on_publish_decision(chat_id: int, decision: str, bot: Any, t: Callable) -> None:
    sess = _sessions.get(chat_id, {})
    if sess.get("step") != "confirming_publish":
        return
    if decision == "cancel":
        sess["step"] = "post_preview"
        _show_post_preview(chat_id, bot, t)
        return
    if not N8N_CONTENT_PUBLISH_WH:
        bot.send_message(chat_id, t(chat_id, "content_publish_not_configured"), parse_mode="Markdown")
        sess["step"] = "post_preview"
        return
    channel = sess.get("channel", "")
    content = sess.get("post_content", "")
    bot.send_message(chat_id,
        t(chat_id, "content_publishing").format(channel=channel),
        parse_mode="Markdown")

    def _run():
        try:
            result = call_webhook(N8N_CONTENT_PUBLISH_WH,
                                  {"chat_id": chat_id, "channel": channel, "content": content},
                                  timeout=30)
            if result.get("error"):
                bot.send_message(chat_id,
                    t(chat_id, "content_publish_error").format(error=result["error"]),
                    parse_mode="Markdown")
            else:
                bot.send_message(chat_id,
                    t(chat_id, "content_published").format(channel=channel),
                    parse_mode="Markdown")
        except Exception as exc:
            log.exception("[content] publish error: %s", exc)
            bot.send_message(chat_id,
                t(chat_id, "content_publish_error").format(error=str(exc)),
                parse_mode="Markdown")
        finally:
            _sessions.pop(chat_id, None)

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Common helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_kb(chat_id: int, sess: dict) -> str:
    try:
        from telegram.bot_access import _docs_rag_context
        return _docs_rag_context(chat_id, sess.get("q1", "")) or ""
    except Exception as exc:
        log.warning("[content] KB fetch failed: %s", exc)
        return ""


def _do_download(chat_id: int, bot: Any, t: Callable,
                 content_key: str = "post_content", label: str = "content") -> None:
    sess = _sessions.get(chat_id, {})
    content = sess.get(content_key, "")
    try:
        filename = f"{label}_{uuid.uuid4().hex[:8]}.txt"
        bot.send_document(chat_id, (filename, io.BytesIO(content.encode("utf-8"))))
    except Exception as exc:
        log.warning("[content] download error: %s", exc)
        bot.send_message(chat_id,
            t(chat_id, "content_generate_error").format(error=str(exc)),
            parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# Text message handler
# ─────────────────────────────────────────────────────────────────────────────

def handle_message(chat_id: int, text: str, bot: Any, t: Callable) -> bool:
    """Process incoming text. Returns True if consumed."""
    sess = _sessions.get(chat_id)
    if not sess:
        return False
    step = sess.get("step")

    if step == "q1":
        sess["q1"] = text.strip()
        sess["step"] = "q2"
        _ask_platform(chat_id, bot, t)
        return True

    if step == "correcting_plan":
        _do_generate_plan(chat_id, bot, t, correction=text.strip())
        return True

    if step == "correcting_post":
        _do_generate_post(chat_id, bot, t,
                          post_index=sess.get("post_index", 0),
                          correction=text.strip())
        return True

    if step == "ask_channel":
        on_channel_input(chat_id, text, bot, t)
        return True

    return False

