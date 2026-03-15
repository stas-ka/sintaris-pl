"""04 — Calendar page (month grid + event detail)."""

import calendar as _cal
from datetime import date

from nicegui import ui

from theme import COLORS, page_layout

# ── Demo data ───────────────────────────────────────────────────
EVENT_COLORS = {"blue": "#5c6bc0", "green": "#66bb6a", "purple": "#ab47bc", "orange": "#ffa726"}

EVENTS_BY_DAY: dict[int, list[dict]] = {
    3:  [{"title": "Dentist", "color": "blue", "time": "09:00"}],
    7:  [{"title": "Sprint Review", "color": "purple", "time": "14:00"}],
    10: [
        {"title": "Lunch with Max", "color": "orange", "time": "12:30"},
        {"title": "Doctor", "color": "green", "time": "15:00"},
    ],
    14: [{"title": "Team Standup", "color": "blue", "time": "10:00"}],
    21: [{"title": "Sprint Review", "color": "purple", "time": "14:00"}],
    25: [{"title": "Birthday Party", "color": "orange", "time": "18:00"}],
}

YEAR, MONTH = 2026, 3
TODAY = 10


def _day_cell(day: int):
    """Render a single calendar day cell."""
    if day == 0:
        ui.label("").style("min-height:70px")
        return

    is_today = day == TODAY
    bg = COLORS["accent"] if is_today else "transparent"
    border = f"1px solid {COLORS['border']}"

    with ui.column().classes("items-center gap-none cursor-pointer").style(
        f"min-height:70px;border-radius:8px;border:{border};"
        f"background:{bg if is_today else COLORS['bg_card']};padding:4px"
    ):
        ui.label(str(day)).classes(
            "text-white text-caption" + (" text-weight-bold" if is_today else "")
        )
        events = EVENTS_BY_DAY.get(day, [])
        with ui.row().classes("gap-xs q-mt-xs"):
            for ev in events[:3]:
                ui.element("span").style(
                    f"width:8px;height:8px;border-radius:50%;"
                    f"background:{EVENT_COLORS[ev['color']]};display:inline-block"
                )


def _event_card(ev: dict):
    color = EVENT_COLORS[ev["color"]]
    with ui.card().classes("pico-card w-full").style(
        f"border-left:3px solid {color};padding:12px 16px"
    ):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.column().classes("gap-none"):
                ui.label(ev["title"]).classes("text-white text-body1 text-weight-medium")
                ui.label(ev["time"]).classes("text-dim text-caption")
            with ui.row().classes("gap-xs"):
                ui.button(icon="volume_up").props("flat round dense color=grey-5").tooltip("Read aloud")
                ui.button(icon="edit").props("flat round dense color=grey-5").tooltip("Edit")
                ui.button(icon="delete_outline").props("flat round dense color=red-4").tooltip("Delete")


@ui.page("/calendar")
def calendar_page():
    with page_layout("🗓 Calendar", "/calendar"):
        # ── Month navigation ────────────────────────────────
        with ui.row().classes("items-center justify-between w-full q-mb-md"):
            with ui.row().classes("items-center gap-sm"):
                ui.button(icon="chevron_left").props("flat round color=grey-5")
                ui.label("March 2026").classes("text-white text-h5 text-weight-bold")
                ui.button(icon="chevron_right").props("flat round color=grey-5")
            with ui.row().classes("gap-xs"):
                for label, active in [("Week", False), ("Month", True), ("List", False)]:
                    cls = "pico-btn-accent" if active else ""
                    ui.button(label).props("flat dense").classes(cls or "text-grey-5")

        # ── Weekday headers ─────────────────────────────────
        with ui.grid(columns=7).classes("w-full gap-xs"):
            for wd in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
                ui.label(wd).classes("text-dim text-caption text-center")

        # ── Day grid ────────────────────────────────────────
        cal = _cal.monthcalendar(YEAR, MONTH)
        with ui.grid(columns=7).classes("w-full gap-xs"):
            for week in cal:
                for day in week:
                    _day_cell(day)

        # ── Today's events detail ───────────────────────────
        ui.separator().classes("q-my-md")
        ui.label(f"Today — March {TODAY}").classes("text-white text-h6 text-weight-bold q-mb-sm")
        for ev in EVENTS_BY_DAY.get(TODAY, []):
            _event_card(ev)

        # ── Add event FAB ───────────────────────────────────
        ui.button(icon="add", on_click=lambda: ui.notify("Add event")).props(
            "fab color=deep-purple-8"
        ).style("position:fixed;bottom:24px;right:24px;z-index:10")
