"""
bot_actions.py — Channel-agnostic action handlers (Phase 4)

Each function receives a UserContext and returns a Screen.  The Screen is
then handed to a channel renderer (render_telegram.py for Telegram,
bot_web.py templates for the web UI).

Three proof-of-concept actions are implemented here:
  action_menu      → main navigation menu
  action_note_list → list all notes for the user
  action_note_view → display a single note

Dependency position: bot_config, bot_ui, bot_users (no Telegram API imports)
"""
from __future__ import annotations

from bot_ui import (
    UserContext, Screen, Card, ButtonRow, Button,
    MarkdownBlock, TextInput, Redirect, back_button
)
from bot_users import _list_notes_for, _load_note_text


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

_MENU_LABELS: dict[str, dict[str, str]] = {
    "ru": {
        "title": "📱 Главное меню",
        "chat":  "💬 Чат",
        "voice": "🎤 Голос",
        "notes": "📝 Заметки",
        "calendar": "🗓 Календарь",
        "mail":  "📧 Почта",
        "admin": "🔐 Админ",
        "help":  "❓ Помощь",
    },
    "en": {
        "title": "📱 Main Menu",
        "chat":  "💬 Chat",
        "voice": "🎤 Voice",
        "notes": "📝 Notes",
        "calendar": "🗓 Calendar",
        "mail":  "📧 Mail",
        "admin": "🔐 Admin",
        "help":  "❓ Help",
    },
    "de": {
        "title": "📱 Hauptmenü",
        "chat":  "💬 Chat",
        "voice": "🎤 Sprache",
        "notes": "📝 Notizen",
        "calendar": "🗓 Kalender",
        "mail":  "📧 Mail",
        "admin": "🔐 Admin",
        "help":  "❓ Hilfe",
    },
}


def action_menu(user: UserContext) -> Screen:
    """Return the main navigation menu screen."""
    lbl = _MENU_LABELS.get(user.lang, _MENU_LABELS["en"])

    rows: list[ButtonRow] = [
        ButtonRow(buttons=[
            Button(lbl["chat"],  "mode_chat",     style="primary"),
            Button(lbl["voice"], "voice_session", style="primary"),
        ]),
        ButtonRow(buttons=[
            Button(lbl["notes"],    "menu_notes",    style="secondary"),
            Button(lbl["calendar"], "menu_calendar", style="secondary"),
        ]),
        ButtonRow(buttons=[
            Button(lbl["mail"], "digest", style="secondary"),
            Button(lbl["help"], "help",   style="ghost"),
        ]),
    ]

    if user.role in ("admin", "developer"):
        rows.append(ButtonRow(buttons=[
            Button(lbl["admin"], "admin_menu", style="danger"),
        ]))

    return Screen(title=lbl["title"], widgets=rows)


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

_NOTES_LABELS: dict[str, dict[str, str]] = {
    "ru": {
        "title":   "📝 Заметки",
        "empty":   "Нет заметок. Создайте первую!",
        "create":  "➕ Создать",
        "back":    "🔙 Меню",
    },
    "en": {
        "title":   "📝 Notes",
        "empty":   "No notes yet. Create your first one!",
        "create":  "➕ Create",
        "back":    "🔙 Menu",
    },
    "de": {
        "title":   "📝 Notizen",
        "empty":   "Keine Notizen. Erstelle die erste!",
        "create":  "➕ Erstellen",
        "back":    "🔙 Menü",
    },
}


def action_note_list(user: UserContext) -> Screen:
    """
    Returns a screen listing all notes for the user.

    Falls back gracefully when chat_id is None (web-only account with no
    Telegram chat_id set — shows an empty notes list instead of crashing).
    """
    lbl = _NOTES_LABELS.get(user.lang, _NOTES_LABELS["en"])
    widgets: list = []

    if user.chat_id is None:
        widgets.append(MarkdownBlock(lbl["empty"]))
    else:
        try:
            notes = _list_notes_for(user.chat_id)
        except Exception:
            notes = []

        if not notes:
            widgets.append(MarkdownBlock(lbl["empty"]))
        else:
            for note in notes:
                slug  = note.get("slug", "")
                title = note.get("title", slug)
                mtime = note.get("mtime", "")
                caption = f"{title}\n_Last updated: {mtime}_" if mtime else title
                widgets.append(Card(
                    title=title,
                    body=caption,
                    action=f"note_open:{slug}",
                ))

    widgets.append(ButtonRow(buttons=[
        Button(lbl["create"], "note_create", style="primary"),
        Button(lbl["back"],   "menu",        style="ghost"),
    ]))

    return Screen(title=lbl["title"], widgets=widgets)


_NOTE_VIEW_LABELS: dict[str, dict[str, str]] = {
    "ru": {"not_found": "Заметка не найдена.", "edit": "✏️ Редактировать",
           "delete": "🗑 Удалить", "tts": "🔊 Озвучить", "back": "🔙 Назад"},
    "en": {"not_found": "Note not found.", "edit": "✏️ Edit",
           "delete": "🗑 Delete", "tts": "🔊 Read aloud", "back": "🔙 Back"},
    "de": {"not_found": "Notiz nicht gefunden.", "edit": "✏️ Bearbeiten",
           "delete": "🗑 Löschen", "tts": "🔊 Vorlesen", "back": "🔙 Zurück"},
}


def action_note_view(user: UserContext, slug: str) -> Screen:
    """
    Returns a screen showing the full contents of a single note.

    Returns a "not found" screen when the note is missing or chat_id is None.
    """
    lbl = _NOTE_VIEW_LABELS.get(user.lang, _NOTE_VIEW_LABELS["en"])

    if user.chat_id is None:
        return Screen(
            title=lbl["not_found"],
            widgets=[MarkdownBlock(lbl["not_found"]), back_button(lbl["back"], "menu_notes")],
        )

    try:
        content = _load_note_text(user.chat_id, slug)
    except Exception:
        content = None

    if content is None:
        return Screen(
            title=lbl["not_found"],
            widgets=[MarkdownBlock(lbl["not_found"]), back_button(lbl["back"], "menu_notes")],
        )

    # Derive title from first heading or slug
    first_line = content.splitlines()[0] if content.strip() else slug
    title = first_line.lstrip("# ").strip() or slug

    return Screen(
        title=title,
        widgets=[
            MarkdownBlock(content),
            ButtonRow(buttons=[
                Button(lbl["edit"],   f"note_edit:{slug}",   style="primary"),
                Button(lbl["tts"],    f"note_tts:{slug}",    style="secondary"),
                Button(lbl["delete"], f"note_delete:{slug}", style="danger"),
            ]),
            back_button(lbl["back"], "note_list"),
        ],
    )
