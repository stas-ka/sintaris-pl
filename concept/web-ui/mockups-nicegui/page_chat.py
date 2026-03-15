"""02 — Free Chat page."""

from nicegui import ui

from theme import COLORS, page_layout


def _topbar_chat():
    ui.select(
        ["GPT-4o-mini", "GPT-4o", "Claude 3.5 Sonnet"],
        value="GPT-4o-mini",
    ).props("dense outlined dark").classes("text-white").style("min-width:170px")
    ui.button(icon="delete_outline", on_click=lambda: ui.notify("Chat cleared")).props(
        "flat round color=grey-6"
    )


# Sample conversation data
MESSAGES = [
    {"role": "bot", "text": "Hello, Stas! I'm your personal AI assistant. How can I help you today?", "time": "08:00"},
    {"role": "user", "text": "What is the weather forecast for Berlin tomorrow?", "time": "08:12"},
    {
        "role": "bot",
        "time": "08:12",
        "text": (
            "Here's the weather forecast for **Berlin** tomorrow:\n\n"
            "- 🌡 Temperature: **12°C – 18°C**\n"
            "- 🌤 Conditions: Partly cloudy, clearing in the afternoon\n"
            "- 💨 Wind: 15 km/h from the West\n"
            "- 🌧 Rain probability: 10%\n\n"
            "It'll be a pleasant spring day — light jacket recommended!"
        ),
    },
    {"role": "user", "text": "Переведи на русский", "time": "08:13"},
    {
        "role": "bot",
        "time": "08:13",
        "text": (
            "Прогноз погоды для **Берлина** на завтра:\n\n"
            "- 🌡 Температура: **12°C – 18°C**\n"
            "- 🌤 Переменная облачность, прояснение к обеду\n"
            "- 💨 Ветер: западный, 15 км/ч\n"
            "- 🌧 Вероятность дождя: 10%\n\n"
            "Будет приятный весенний день — лёгкая куртка пригодится!"
        ),
    },
]


@ui.page("/chat")
def chat_page():
    with page_layout("💬 Free Chat", "/chat", topbar_right=_topbar_chat):
        # Messages area
        with ui.column().classes("w-full gap-sm").style("max-width:800px"):
            for msg in MESSAGES:
                if msg["role"] == "bot":
                    with ui.row().classes("gap-sm items-end"):
                        ui.label("🤖").classes("text-h6")
                        with ui.column().classes("gap-none"):
                            ui.markdown(msg["text"]).classes("msg-bot text-white")
                            ui.label(msg["time"]).classes("text-dim text-caption")
                else:
                    with ui.column().classes("items-end w-full gap-none"):
                        ui.label(msg["text"]).classes("msg-user text-white")
                        ui.label(msg["time"]).classes("text-dim text-caption")

        ui.space()

        # Input area pinned to bottom
        with ui.row().classes("w-full items-center gap-sm q-mt-lg").style(
            f"max-width:800px;padding:12px;background:{COLORS['bg_card']};"
            f"border:1px solid {COLORS['border']};border-radius:12px"
        ):
            ui.input(placeholder="Type your message…").props(
                "dense borderless dark"
            ).classes("flex-grow text-white")
            ui.button(icon="mic").props("flat round color=grey-5")
            ui.button(icon="send").props("flat round color=deep-purple-4")
