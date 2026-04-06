"""
bot_ui.py — Screen DSL for multi-channel rendering (Phase 4)

Provides a channel-agnostic representation of UI screens so the same
action handler can produce output for Telegram keyboards, the FastAPI web
UI, or any future channel.

Dependency position: bot_config → bot_ui   (no further bot_* imports here)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# User context — passed to every action handler
# ---------------------------------------------------------------------------

@dataclass
class UserContext:
    """Minimal user identity needed to build a screen."""
    user_id: str         # account username (web) or str(chat_id) (Telegram)
    chat_id: int | None  # Telegram chat_id; None for web-only users
    lang: str = "ru"     # ru | en | de
    role: str = "user"   # user | admin | developer | guest
    variant: str = "taris"  # taris | openclaw — deployment target variant


# ---------------------------------------------------------------------------
# Widget primitives
# ---------------------------------------------------------------------------

@dataclass
class Button:
    """Single inline button."""
    label: str
    action: str          # callback_data key or URL path fragment
    style: str = "primary"   # primary | secondary | danger | ghost


@dataclass
class ButtonRow:
    """A horizontal row of buttons."""
    buttons: list[Button] = field(default_factory=list)


@dataclass
class Card:
    """An info card widget with an optional primary action."""
    title: str
    body: str
    action: str | None = None   # callback_data / route when tapped


@dataclass
class TextInput:
    """Prompt the user to enter text (ForceReply on Telegram; <input> on web)."""
    placeholder: str
    action: str   # the callback_data / route that will receive the input


@dataclass
class Toggle:
    """A boolean toggle switch."""
    label: str
    key: str          # settings key name
    value: bool = False


@dataclass
class AudioPlayer:
    """An audio playback widget."""
    src: str          # URL or base64 data-URI
    caption: str = ""


@dataclass
class MarkdownBlock:
    """A block of Markdown-formatted text."""
    text: str


@dataclass
class Spinner:
    """A "processing" indicator with a label."""
    label: str = "Processing…"


@dataclass
class Confirm:
    """A yes/no confirmation prompt."""
    text: str
    action_yes: str   # callback_data / route for confirmation
    action_no: str    # callback_data / route for cancellation


@dataclass
class Redirect:
    """Tell the renderer to navigate to a different screen immediately."""
    target: str   # action name or URL


# ---------------------------------------------------------------------------
# Screen — top-level container rendered by a channel renderer
# ---------------------------------------------------------------------------

# All widget types accepted inside Screen.widgets
Widget = (
    Button | ButtonRow | Card | TextInput | Toggle |
    AudioPlayer | MarkdownBlock | Spinner | Confirm | Redirect
)


@dataclass
class Screen:
    """
    A complete UI screen returned by an action handler.

    Renderers translate this into channel-specific output:
      - render_telegram.py  → InlineKeyboardMarkup + bot.send_message()
      - bot_web.py templates → Jinja2 context dict
    """
    title: str
    widgets: list[Any] = field(default_factory=list)
    parse_mode: str = "Markdown"   # Markdown | HTML | plain
    ephemeral: bool = False        # if True, auto-delete after 30 s (Telegram only)


# ---------------------------------------------------------------------------
# Convenience helpers used by action handlers
# ---------------------------------------------------------------------------

def back_button(label: str = "🔙 Back", target: str = "menu") -> ButtonRow:
    """Return a single-button row for going back to `target`."""
    return ButtonRow(buttons=[Button(label=label, action=target, style="ghost")])


def confirm_buttons(action_yes: str, action_no: str,
                    yes_label: str = "✅ Confirm",
                    no_label: str  = "❌ Cancel") -> ButtonRow:
    """Return yes/no button row."""
    return ButtonRow(buttons=[
        Button(label=yes_label, action=action_yes, style="primary"),
        Button(label=no_label,  action=action_no,  style="secondary"),
    ])
