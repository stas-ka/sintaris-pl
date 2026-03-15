"""06 — Mail Digest page."""

from nicegui import ui

from theme import COLORS, page_layout

# ── Demo data ───────────────────────────────────────────────────
DIGEST_STATS = {"total": 12, "important": 2, "promo": 3, "spam": 5, "last_refresh": "Today 07:00"}

EMAILS = {
    "important": [
        {"from": "GitHub", "subject": "Security alert for picoclaw repo", "summary": "A new vulnerability was detected in dependency X. Review and update recommended.", "time": "06:45"},
        {"from": "Boss", "subject": "Project deadline moved", "summary": "The delivery date has been moved to April 1st. Please adjust your timeline.", "time": "06:30"},
    ],
    "regular": [
        {"from": "Jira", "subject": "Sprint 12 started", "summary": "New sprint with 8 stories and 3 bugs assigned to you.", "time": "06:20"},
        {"from": "Google Calendar", "subject": "Reminder: Team Standup", "summary": "Team standup at 10:00 AM in the main conference room.", "time": "06:00"},
    ],
    "promo": [
        {"from": "DigitalOcean", "subject": "50% off managed databases", "summary": "Limited-time offer on managed PostgreSQL and MySQL.", "time": "05:30"},
        {"from": "Udemy", "subject": "New courses for you", "summary": "Top-rated Python and machine learning courses on sale.", "time": "04:00"},
        {"from": "Amazon", "subject": "Deals of the day", "summary": "Electronics and home gadgets up to 40% off today.", "time": "03:00"},
    ],
    "spam": [
        {"from": "unknown@xyz.com", "subject": "You've won $1,000,000", "summary": "Congratulations! Click here to claim your prize…", "time": "02:15"},
    ],
}

CATEGORY_META = {
    "important": {"label": "Important", "color": "#ef5350", "icon": "priority_high"},
    "regular":   {"label": "Regular", "color": COLORS["accent"], "icon": "mail"},
    "promo":     {"label": "Promotional", "color": "#ffa726", "icon": "local_offer"},
    "spam":      {"label": "Spam", "color": "#78909c", "icon": "report"},
}


@ui.page("/mail")
def mail_page():
    with page_layout("📧 Mail Digest", "/mail"):
        # ── Summary card ────────────────────────────────────
        with ui.card().classes("pico-card w-full q-mb-lg"):
            with ui.row().classes("items-center justify-between w-full"):
                with ui.column().classes("gap-none"):
                    ui.label("Daily Digest").classes("text-white text-h6 text-weight-bold")
                    ui.label(
                        f"{DIGEST_STATS['total']} emails  ·  {DIGEST_STATS['important']} important  ·  "
                        f"{DIGEST_STATS['promo']} promo  ·  {DIGEST_STATS['spam']} spam"
                    ).classes("text-dim text-body2")
                    ui.label(f"Last refresh: {DIGEST_STATS['last_refresh']}").classes(
                        "text-dim text-caption q-mt-xs"
                    )
                with ui.row().classes("gap-sm"):
                    ui.button("Refresh", icon="refresh").props("flat color=deep-purple-4")
                    ui.button(icon="volume_up").props("flat round color=grey-5").tooltip("Read aloud")
                    ui.button(icon="email").props("flat round color=grey-5").tooltip("Send as email")

        # ── Audio player (digest TTS) ───────────────────────
        with ui.card().classes("pico-card w-full q-mb-lg"):
            with ui.row().classes("items-center gap-md w-full"):
                ui.button(icon="play_arrow").props("round color=deep-purple-8")
                # Fake waveform bars
                with ui.row().classes("gap-xs items-end flex-grow").style("height:32px"):
                    import random

                    random.seed(42)
                    for _ in range(40):
                        h = random.randint(6, 28)
                        ui.element("div").style(
                            f"width:4px;height:{h}px;background:{COLORS['accent']};"
                            f"border-radius:2px;opacity:0.7"
                        )
                ui.label("0:00 / 2:15").classes("text-dim text-caption")

        # ── Email categories ────────────────────────────────
        for cat_key in ("important", "regular", "promo", "spam"):
            meta = CATEGORY_META[cat_key]
            emails = EMAILS.get(cat_key, [])
            if not emails:
                continue

            with ui.row().classes("items-center gap-sm q-mb-sm q-mt-md"):
                ui.icon(meta["icon"], size="sm").style(f"color:{meta['color']}")
                ui.label(f"{meta['label']} ({len(emails)})").classes(
                    "text-white text-body1 text-weight-medium"
                )

            for em in emails:
                opacity = "opacity:0.7" if cat_key == "promo" else ""
                with ui.card().classes("pico-card w-full q-mb-xs").style(
                    f"border-left:3px solid {meta['color']};padding:10px 16px;{opacity}"
                ):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label(em["from"]).classes("text-white text-body2 text-weight-medium")
                        ui.label(em["time"]).classes("text-dim text-caption")
                    ui.label(em["subject"]).classes("text-white text-body2 q-mt-xs")
                    ui.label(em["summary"]).classes("text-dim text-caption q-mt-xs")
                    if cat_key == "spam":
                        ui.badge("SPAM", color="blue-grey-7").props("dense").classes("q-mt-xs")
