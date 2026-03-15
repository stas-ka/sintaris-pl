"""Pico Bot — NiceGUI shared theme, layout, and CSS.

This module provides the dark-theme sidebar layout used by all screens.
Import `page_layout` as a context manager inside each `@ui.page` function.
"""

from contextlib import contextmanager
from typing import Optional

from nicegui import ui

# ── Design tokens (matches shared.css) ────────────────────────────
COLORS = {
    "bg_primary": "#121212",
    "bg_card": "#1e1e1e",
    "bg_sidebar": "#1a1a2e",
    "bg_input": "#2a2a2a",
    "bg_hover": "#2d2d2d",
    "bg_active": "#3a3a5c",
    "text_primary": "#e0e0e0",
    "text_muted": "#9e9e9e",
    "text_dim": "#757575",
    "accent": "#7c4dff",
    "accent_light": "#b388ff",
    "success": "#00c853",
    "warning": "#ffd600",
    "error": "#ff1744",
    "info": "#00b0ff",
    "border": "#333",
}

BOT_VERSION = "2026.3.26"

# ── Global CSS injected once per page ─────────────────────────────
GLOBAL_CSS = """
/* ── Sidebar ── */
.sidebar { background: %(bg_sidebar)s !important; }
.sidebar .q-item { color: %(text_primary)s; border-radius: 8px; margin: 2px 8px; }
.sidebar .q-item:hover { background: %(bg_hover)s; }
.sidebar .q-item--active, .sidebar .q-item.active-nav {
    background: %(bg_active)s !important; color: %(accent_light)s !important; }
.sidebar .q-item .q-item__section--avatar { min-width: 32px; }

/* ── Cards ── */
.pico-card { background: %(bg_card)s; border: 1px solid %(border)s; border-radius: 12px; }

/* ── Dark body ── */
body { background: %(bg_primary)s !important; }
.q-page { background: %(bg_primary)s !important; }

/* ── Chat bubbles ── */
.msg-bot  { background: %(bg_card)s; border-radius: 12px 12px 12px 0; padding: 12px 16px;
            max-width: 75%%; margin-bottom: 8px; }
.msg-user { background: rgba(124,77,255,0.15); border-radius: 12px 12px 0 12px; padding: 12px 16px;
            max-width: 75%%; margin-bottom: 8px; align-self: flex-end; }

/* ── Misc helpers ── */
.text-dim  { color: %(text_dim)s !important; }
.text-muted { color: %(text_muted)s !important; }
.accent-border-left { border-left: 3px solid %(accent)s; }

/* ── Voice orb ── */
.voice-orb {
    width: 160px; height: 160px; border-radius: 50%%;
    background: radial-gradient(circle at 40%% 40%%, #9e7cff 0%%, #5c3dba 50%%, #2d1b69 100%%);
    box-shadow: 0 0 60px rgba(124,77,255,0.4);
    display: flex; align-items: center; justify-content: center;
    font-size: 48px; cursor: pointer;
}

/* ── Calendar day cells ── */
.cal-day { min-height: 78px; border: 1px solid %(border)s; border-radius: 4px;
           padding: 4px; cursor: pointer; background: %(bg_card)s; }
.cal-day:hover { border-color: %(accent)s; }
.cal-day-today { border-color: %(accent)s !important;
                 background: rgba(124,77,255,0.08) !important; }

/* ── Toggle tweaks ── */
.q-toggle__inner--truthy .q-toggle__thumb { background: %(accent)s !important; }

/* ── Stat number ── */
.stat-value { font-size: 28px; font-weight: 700; line-height: 1.1; }
""" % COLORS

# ── Sidebar navigation items ──────────────────────────────────────
NAV_ITEMS_MAIN = [
    ("🏠", "Dashboard", "/"),
    ("💬", "Free Chat", "/chat"),
    ("📝", "Notes", "/notes"),
    ("🗓", "Calendar", "/calendar"),
    ("📧", "Mail Digest", "/mail"),
    ("🎤", "Voice", "/voice"),
]

NAV_ITEMS_ACCOUNT = [
    ("👤", "Profile", "/profile"),
    ("❓", "Help", "/help"),
]

NAV_ITEMS_ADMIN = [
    ("🔐", "Admin Panel", "/admin"),
]


def _sidebar(active_path: str = "/") -> None:
    """Render the fixed left sidebar."""
    with ui.column().classes("sidebar w-64 min-h-screen q-pa-none"):
        # Header
        with ui.row().classes("items-center q-pa-md gap-sm"):
            ui.html('<div style="width:40px;height:40px;border-radius:50%;'
                    'background:linear-gradient(135deg,#7c4dff,#536dfe);'
                    'display:flex;align-items:center;justify-content:center;'
                    'font-size:20px;">🤖</div>')
            with ui.column().classes("gap-none"):
                ui.label("Pico Bot").classes("text-subtitle1 text-weight-bold text-white")
                ui.label(f"v{BOT_VERSION}").classes("text-dim text-caption")
        ui.separator().props("color=grey-9")

        # Nav sections
        def _nav_section(label: str, items: list) -> None:
            ui.label(label).classes("text-dim text-overline q-pl-md q-pt-sm")
            for icon, title, path in items:
                cls = "active-nav" if path == active_path else ""
                with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(cls):
                    with ui.item_section().props("avatar"):
                        ui.label(icon)
                    ui.item_label(title)

        with ui.list().classes("q-pa-xs flex-grow"):
            _nav_section("Main", NAV_ITEMS_MAIN)
            _nav_section("Account", NAV_ITEMS_ACCOUNT)
            _nav_section("Admin", NAV_ITEMS_ADMIN)

        ui.space()

        # Footer — user info
        with ui.row().classes("items-center q-pa-md gap-sm"):
            ui.avatar("SU", color="deep-purple-9", text_color="white", size="sm")
            with ui.column().classes("gap-none"):
                ui.label("Stas Ulmer").classes("text-subtitle2 text-white")
                ui.label("Admin").classes("text-dim text-caption")
            ui.icon("circle", color="green", size="xs").classes("q-ml-auto").tooltip("Bot online")


@contextmanager
def page_layout(title: str, active_path: str = "/", topbar_right: Optional[callable] = None):
    """Context manager: sidebar + top bar + scrollable content area.

    Usage::

        @ui.page("/chat")
        def chat_page():
            with page_layout("💬 Free Chat", "/chat"):
                ui.label("Hello")
    """
    ui.add_css(GLOBAL_CSS)
    ui.dark_mode(True)
    ui.colors(primary=COLORS["accent"])

    with ui.row().classes("w-full min-h-screen no-wrap"):
        _sidebar(active_path)

        with ui.column().classes("flex-grow q-pa-none"):
            # Top bar
            with ui.row().classes("items-center q-px-lg q-py-sm").style(
                f"border-bottom:1px solid {COLORS['border']};background:{COLORS['bg_primary']}"
            ):
                ui.label(title).classes("text-h6 text-white")
                ui.space()
                if topbar_right:
                    topbar_right()

            # Scrollable content
            with ui.scroll_area().classes("flex-grow q-pa-lg"):
                yield
