"""03 — Notes page (list + editor split view)."""

from nicegui import ui

from theme import COLORS, page_layout

# ── Demo data ───────────────────────────────────────────────────
NOTES = [
    {"slug": "shopping_list", "title": "Shopping List", "preview": "Milk, bread, eggs, cheese…", "date": "Today 09:15"},
    {"slug": "meeting_notes", "title": "Meeting Notes", "preview": "Sprint review outcomes: increased velocity…", "date": "Yesterday"},
    {"slug": "recipe_borsch", "title": "Recipe: Борщ", "preview": "Ingredients: beets, cabbage, potatoes…", "date": "Mar 8"},
]

SAMPLE_MD = (
    "# Shopping List\n\n"
    "- [ ] Milk\n"
    "- [ ] Bread\n"
    "- [x] Eggs\n"
    "- [ ] Cheese\n"
    "- [ ] Tomatoes\n\n"
    "> Also check if we need butter."
)


def _note_item(n: dict, selected: bool = False):
    border = f"border-left:3px solid {COLORS['accent']}" if selected else "border-left:3px solid transparent"
    bg = COLORS["bg_hover"] if selected else "transparent"
    with ui.card().classes("pico-card w-full cursor-pointer").style(
        f"{border};background:{bg};padding:10px 14px"
    ):
        ui.label(n["title"]).classes("text-white text-body1 text-weight-medium")
        ui.label(n["preview"]).classes("text-dim text-caption ellipsis")
        ui.label(n["date"]).classes("text-dim text-caption q-mt-xs")


@ui.page("/notes")
def notes_page():
    with page_layout("📝 Notes", "/notes"):
        with ui.grid(columns=2).classes("w-full gap-md").style(
            "grid-template-columns:300px 1fr"
        ):
            # ── Left: note list ──────────────────────────────
            with ui.column().classes("gap-sm"):
                with ui.row().classes("w-full items-center gap-sm"):
                    ui.input(placeholder="Search notes…").props(
                        "dense outlined dark"
                    ).classes("flex-grow text-white")
                    ui.button(icon="add", on_click=lambda: ui.notify("New note")).props(
                        "flat round color=deep-purple-4"
                    )
                # Notes list
                _note_item(NOTES[0], selected=True)
                _note_item(NOTES[1])
                _note_item(NOTES[2])

            # ── Right: editor ────────────────────────────────
            with ui.column().classes("gap-sm"):
                ui.input(value="Shopping List").props("dense outlined dark").classes(
                    "text-white text-h6"
                ).style("font-weight:600")

                # Toolbar
                with ui.row().classes("gap-xs"):
                    for icon, tip in [
                        ("format_bold", "Bold"),
                        ("format_italic", "Italic"),
                        ("strikethrough_s", "Strikethrough"),
                        ("title", "Heading 1"),
                        ("text_fields", "Heading 2"),
                        ("link", "Link"),
                    ]:
                        ui.button(icon=icon).props(
                            f"flat dense round color=grey-5"
                        ).tooltip(tip)

                # Split edit / preview
                with ui.grid(columns=2).classes("w-full gap-sm").style(
                    "grid-template-columns:1fr 1fr"
                ):
                    ui.textarea(value=SAMPLE_MD).props("dark outlined").classes(
                        "text-white font-mono"
                    ).style(f"min-height:350px;background:{COLORS['bg_card']}")

                    with ui.card().classes("pico-card").style("min-height:350px;overflow-y:auto"):
                        ui.markdown(SAMPLE_MD).classes("text-white")

                # Status bar
                with ui.row().classes("items-center gap-sm"):
                    ui.icon("check_circle", color="green-5", size="xs")
                    ui.label("Auto-saved").classes("text-dim text-caption")
