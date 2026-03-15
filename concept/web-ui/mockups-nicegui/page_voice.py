"""07 — Voice page (orb, waveform, transcript, pipeline timing)."""

from nicegui import ui

from theme import COLORS, page_layout

# ── Demo data ───────────────────────────────────────────────────
PIPELINE_STEPS = [
    {"label": "OGG → PCM", "time": "0.8 s", "pct": 8},
    {"label": "STT (Vosk)", "time": "3.2 s", "pct": 31},
    {"label": "LLM", "time": "1.8 s", "pct": 17},
    {"label": "TTS (Piper)", "time": "4.2 s", "pct": 41},
    {"label": "PCM → OGG", "time": "0.3 s", "pct": 3},
]


@ui.page("/voice")
def voice_page():
    with page_layout("🎤 Voice", "/voice"):
        # ── Voice orb ───────────────────────────────────────
        with ui.column().classes("items-center q-mb-lg"):
            ui.element("div").classes("voice-orb").on("click", lambda: ui.notify("Recording…"))
            ui.label("Ready — tap to record").classes("text-dim text-body2 q-mt-md")
            ui.label("Hold to record, release to send").classes("text-dim text-caption")

        # ── Waveform visualizer ─────────────────────────────
        with ui.card().classes("pico-card w-full q-mb-md"):
            ui.label("Waveform").classes("text-dim text-caption q-mb-sm")
            with ui.row().classes("gap-xs items-center justify-center").style("height:50px"):
                import random

                random.seed(7)
                for _ in range(50):
                    h = random.randint(4, 44)
                    ui.element("div").style(
                        f"width:3px;height:{h}px;background:{COLORS['accent']};"
                        f"border-radius:2px;opacity:0.6"
                    )

        # ── Transcript ──────────────────────────────────────
        with ui.grid(columns=2).classes("w-full gap-md q-mb-md"):
            with ui.card().classes("pico-card"):
                ui.label("Your speech (STT)").classes("text-dim text-caption q-mb-sm")
                ui.label("Какая погода завтра в Берлине?").classes("text-white text-body1")
            with ui.card().classes("pico-card"):
                ui.label("AI Response").classes("text-dim text-caption q-mb-sm")
                ui.markdown(
                    "Прогноз для **Берлина** на завтра:\n"
                    "- 🌡 12–18 °C, переменная облачность\n"
                    "- 💨 Ветер 15 км/ч, западный"
                ).classes("text-white")

        # ── TTS audio player ────────────────────────────────
        with ui.card().classes("pico-card w-full q-mb-md"):
            with ui.row().classes("items-center gap-md"):
                ui.button(icon="play_arrow").props("round color=deep-purple-8")
                ui.linear_progress(value=0.0).props("color=deep-purple-4 dark").classes("flex-grow")
                ui.label("0:00 / 0:12").classes("text-dim text-caption")

        # ── Pipeline timing ─────────────────────────────────
        with ui.card().classes("pico-card w-full q-mb-md"):
            ui.label("Pipeline Timing").classes("text-white text-body1 text-weight-medium q-mb-sm")
            for step in PIPELINE_STEPS:
                with ui.row().classes("items-center w-full gap-sm q-mb-xs"):
                    ui.label(step["label"]).classes("text-dim text-caption").style("min-width:100px")
                    with ui.element("div").style(
                        f"flex:1;height:18px;background:{COLORS['bg_hover']};border-radius:4px;overflow:hidden"
                    ):
                        ui.element("div").style(
                            f"width:{step['pct']}%;height:100%;background:{COLORS['accent']};"
                            f"border-radius:4px"
                        )
                    ui.label(step["time"]).classes("text-white text-caption text-weight-medium").style(
                        "min-width:50px;text-align:right"
                    )
            ui.separator().classes("q-my-sm")
            with ui.row().classes("justify-end"):
                ui.label("Total: 10.3 s").classes("text-white text-body2 text-weight-bold")

        # ── Language selector ───────────────────────────────
        with ui.row().classes("gap-sm items-center"):
            ui.label("Language:").classes("text-dim text-body2")
            for lang, active in [("RU", True), ("DE", False), ("EN", False)]:
                props = "color=deep-purple" if active else "flat color=grey-5"
                ui.button(lang).props(f"dense {props}")
