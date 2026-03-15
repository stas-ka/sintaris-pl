"""01 — Dashboard (Main Menu) page."""

from nicegui import ui

from theme import COLORS, page_layout


@ui.page("/")
def dashboard_page():
    with page_layout("Dashboard", "/"):
        # Welcome card
        with ui.card().classes("pico-card q-mb-md w-full").style(
            "background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);border-color:#2a2a5e"
        ):
            with ui.row().classes("items-center gap-md"):
                ui.label("🤖").classes("text-h3")
                with ui.column().classes("gap-none"):
                    ui.label("Welcome back, Stas!").classes("text-h6 text-white")
                    ui.label(
                        "Your personal AI assistant is ready. 3 new mails, 2 events today."
                    ).classes("text-muted")

        # Quick Actions
        ui.label("Quick Actions").classes("text-dim text-overline q-mb-sm")
        with ui.row().classes("gap-md q-mb-lg w-full"):
            for icon, title, sub, path in [
                ("💬", "Free Chat", "Ask anything", "/chat"),
                ("📝", "New Note", "3 notes total", "/notes"),
                ("🗓", "Calendar", "2 events today", "/calendar"),
                ("📧", "Mail Digest", "Last: 2h ago", "/mail"),
            ]:
                with ui.card().classes("pico-card cursor-pointer").style(
                    "min-width:160px;text-align:center;padding:20px 16px"
                ).on("click", lambda p=path: ui.navigate.to(p)):
                    ui.label(icon).classes("text-h5 q-mb-xs")
                    ui.label(title).classes("text-subtitle2 text-white")
                    ui.label(sub).classes("text-dim text-caption")

        # Today's events
        ui.label("Today's Events").classes("text-dim text-overline q-mb-sm")
        for time, title, color in [
            ("10:00", "Team Meeting", COLORS["info"]),
            ("15:00", "Doctor appointment", COLORS["success"]),
        ]:
            with ui.card().classes("pico-card q-mb-sm w-full accent-border-left"):
                with ui.row().classes("items-center gap-md"):
                    ui.label(time).classes("text-weight-bold").style(f"color:{COLORS['accent']}")
                    ui.label(title).classes("text-subtitle2 text-white")

        # Recent notes
        ui.label("Recent Notes").classes("text-dim text-overline q-mt-md q-mb-sm")
        for title, preview, date in [
            ("📋 Shopping List", "Milk, bread, eggs, cheese...", "Today, 08:30"),
            ("💡 Project Ideas", "1. Smart home automation...", "Yesterday, 14:22"),
        ]:
            with ui.card().classes("pico-card q-mb-sm w-full cursor-pointer").on(
                "click", lambda: ui.navigate.to("/notes")
            ):
                ui.label(title).classes("text-subtitle2 text-white")
                ui.label(preview).classes("text-dim text-caption")
                ui.label(date).classes("text-muted text-caption")

        # System status
        ui.label("System Status").classes("text-dim text-overline q-mt-md q-mb-sm")
        with ui.row().classes("gap-md w-full"):
            for label, value, color in [
                ("Bot Status", "Online", COLORS["success"]),
                ("Pi CPU", "48%", COLORS["info"]),
                ("Temperature", "58°C", COLORS["warning"]),
                ("LLM", "GPT-4o-mini", COLORS["accent"]),
            ]:
                with ui.card().classes("pico-card").style("min-width:140px;padding:12px 16px"):
                    ui.label(label).classes("text-dim text-caption")
                    ui.label(value).classes("text-subtitle1 text-weight-bold").style(f"color:{color}")
