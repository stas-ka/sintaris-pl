"""
render_telegram.py — Screen DSL → Telegram renderer (Phase 4)

Translates a Screen object returned by a bot_actions handler into
Telegram API calls via the shared `bot` singleton from core.bot_instance.

Usage in a callback handler:
    from ui.bot_actions import action_menu
    from ui.render_telegram import render_screen
    from core.bot_instance import bot

    screen = action_menu(user_ctx)
    render_screen(screen, chat_id, bot)

Dependency position:
    bot_config → bot_instance → render_telegram
    bot_ui (DSL definitions)
    bot_actions (builds screens) — NOT imported here; caller imports it

Rendering rules per widget:
  MarkdownBlock  → send_message(text, parse_mode)
  Card           → send_message as bold title + body; action as inline button
  ButtonRow      → accumulated into a single InlineKeyboardMarkup sent at end
  TextInput      → ForceReply prompt
  Toggle         → InlineKeyboardButton with ✅/⬜ label
  AudioPlayer    → send_voice() or send_audio() from URL / data-URI
  Spinner        → send_message("⏳ …") — ephemeral indicator
  Confirm        → send_message with yes/no button row
  Redirect       → sends nothing (caller must act on Screen.title check or use
                   the returned new_action string)
"""
from __future__ import annotations
import base64, io, logging
from typing import TYPE_CHECKING

import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
)

from ui.bot_ui import (
    Screen, Widget,
    Button, ButtonRow, Card, TextInput, Toggle,
    AudioPlayer, MarkdownBlock, Spinner, Confirm, Redirect,
)

if TYPE_CHECKING:
    from telebot import TeleBot

log = logging.getLogger("taris-tgbot")

# Map UI style names to emoji prefixes (optional visual differentiation)
_STYLE_PREFIX: dict[str, str] = {
    "primary":   "",
    "secondary": "",
    "danger":    "",
    "ghost":     "",
}


def _make_button(btn: Button) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=btn.label, callback_data=btn.action)


def render_screen(screen: Screen, chat_id: int, bot: "TeleBot",
                  reply_to_message_id: int | None = None) -> None:
    """
    Render a Screen to a Telegram chat.

    All ButtonRow widgets are coalesced into a single InlineKeyboardMarkup
    appended to the last text message.  Non-button widgets (MarkdownBlock,
    Card, etc.) are sent as individual messages in widget order.

    If the only content is buttons (menus), the title becomes the message text.
    """
    # Separate text-bearing widgets from pure-button rows
    text_widgets:   list = []
    button_rows:    list[ButtonRow] = []
    deferred_send:  list = []   # (send_fn, kwargs)

    for w in screen.widgets:
        if isinstance(w, ButtonRow):
            button_rows.append(w)
        elif isinstance(w, Redirect):
            # Nothing to render — caller should inspect return value.
            log.debug("[render_telegram] Redirect widget to %s ignored (caller handles)", w.target)
        elif isinstance(w, (MarkdownBlock, Card, TextInput, Toggle,
                             AudioPlayer, Spinner, Confirm)):
            text_widgets.append(w)

    # Build combined InlineKeyboardMarkup from all button rows
    ikm: InlineKeyboardMarkup | None = None
    if button_rows:
        ikm = InlineKeyboardMarkup(row_width=3)
        for row in button_rows:
            ikm.add(*[_make_button(b) for b in row.buttons])

    # Helper for send kwargs
    def _common(**kw):
        if reply_to_message_id:
            kw["reply_to_message_id"] = reply_to_message_id
        return kw

    # --- Emit text/media widgets ---
    sent_at_least_one = False

    for w in text_widgets:
        try:
            if isinstance(w, MarkdownBlock):
                # Attach keyboard to last MarkdownBlock if no more text follows
                is_last = (text_widgets[-1] is w)
                msg_text = w.text if w.text.strip() else "\u200b"  # guard empty/whitespace
                bot.send_message(
                    chat_id, msg_text,
                    parse_mode=screen.parse_mode,
                    reply_markup=(ikm if is_last else None),
                    **_common()
                )
                sent_at_least_one = True
                if is_last:
                    ikm = None  # consumed

            elif isinstance(w, Card):
                card_text = f"*{_escape_md(w.title)}*\n{w.body}"
                card_ikm: InlineKeyboardMarkup | None = None
                if w.action:
                    card_ikm = InlineKeyboardMarkup()
                    card_ikm.add(InlineKeyboardButton("▶", callback_data=w.action))
                bot.send_message(
                    chat_id, card_text,
                    parse_mode="Markdown",
                    reply_markup=card_ikm,
                    **_common()
                )
                sent_at_least_one = True

            elif isinstance(w, TextInput):
                fr = ForceReply(selective=True)
                bot.send_message(
                    chat_id, w.placeholder,
                    reply_markup=fr,
                    **_common()
                )
                sent_at_least_one = True

            elif isinstance(w, Toggle):
                flag = "✅" if w.value else "⬜"
                toggle_ikm = InlineKeyboardMarkup()
                toggle_ikm.add(InlineKeyboardButton(
                    f"{flag}  {w.label}",
                    callback_data=f"toggle:{w.key}",
                ))
                bot.send_message(
                    chat_id, f"Toggle: *{w.label}*",
                    parse_mode="Markdown",
                    reply_markup=toggle_ikm,
                    **_common()
                )
                sent_at_least_one = True

            elif isinstance(w, AudioPlayer):
                # src can be a URL or a base64 data-URI (data:audio/ogg;base64,...)
                if w.src.startswith("data:"):
                    _, b64 = w.src.split(",", 1)
                    audio_bytes = base64.b64decode(b64)
                    buf = io.BytesIO(audio_bytes)
                    buf.name = "audio.ogg"
                    bot.send_voice(chat_id, buf, caption=w.caption or None,
                                   **_common())
                else:
                    bot.send_voice(chat_id, w.src, caption=w.caption or None,
                                   **_common())
                sent_at_least_one = True

            elif isinstance(w, Spinner):
                bot.send_message(chat_id, f"⏳ {w.label}", **_common())
                sent_at_least_one = True

            elif isinstance(w, Confirm):
                confirm_ikm = InlineKeyboardMarkup()
                confirm_ikm.add(
                    InlineKeyboardButton("✅", callback_data=w.action_yes),
                    InlineKeyboardButton("❌", callback_data=w.action_no),
                )
                bot.send_message(
                    chat_id, w.text,
                    parse_mode=screen.parse_mode,
                    reply_markup=confirm_ikm,
                    **_common()
                )
                sent_at_least_one = True

        except Exception as exc:
            log.error("[render_telegram] widget render error: %s", exc)

    # --- If nothing was sent yet, emit the screen title + any remaining keyboard ---
    # Use screen.title as-is: it may already contain Markdown (e.g. "🔐 *Admin Panel*")
    # from strings.json. Applying _escape_md() + wrapping in *..* would double-escape.
    if not sent_at_least_one:
        msg_text = screen.title if screen.title else "\u200b"  # zero-width space if empty
        bot.send_message(
            chat_id, msg_text,
            parse_mode="Markdown",
            reply_markup=ikm,
            **_common()
        )
        ikm = None

    # --- Orphan keyboard (button rows with no associated text) ---
    if ikm is not None:
        msg_text = screen.title if screen.title else "\u200b"
        bot.send_message(
            chat_id, msg_text,
            parse_mode="Markdown",
            reply_markup=ikm,
            **_common()
        )


def _escape_md(text: str) -> str:
    """Escape Markdown v1 special characters: * _ ` ["""
    for ch in ("*", "_", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text
