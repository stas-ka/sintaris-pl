"""05 — Admin Panel page."""

from nicegui import ui

from theme import COLORS, page_layout

# ── Demo data ───────────────────────────────────────────────────
STAT_CARDS = [
    {"label": "Total Users", "value": "4", "icon": "group", "color": COLORS["accent"]},
    {"label": "Pending", "value": "1", "icon": "pending_actions", "color": "#ffa726"},
    {"label": "Active LLM", "value": "GPT-4o-mini", "icon": "smart_toy", "color": "#66bb6a"},
    {"label": "Pi Status", "value": "OK  58°C  48%", "icon": "memory", "color": "#5c6bc0"},
]

USERS = [
    {"name": "Stas", "id": "994963580", "role": "Admin", "status": "active"},
    {"name": "Anna", "id": "112233445", "role": "User", "status": "active"},
    {"name": "Max", "id": "556677889", "role": "Guest", "status": "active"},
    {"name": "Ivan", "id": "998877665", "role": "Pending", "status": "pending"},
]

LLM_MODELS = [
    {"name": "GPT-4o-mini", "provider": "OpenAI", "desc": "Fast, cost-effective", "active": True},
    {"name": "GPT-4o", "provider": "OpenAI", "desc": "Most capable", "active": False},
    {"name": "Claude 3.5 Sonnet", "provider": "Anthropic", "desc": "Strong reasoning", "active": False},
    {"name": "Llama-3 70B", "provider": "OpenRouter", "desc": "Open-source, large", "active": False},
]

VOICE_OPTS = [
    {"key": "persistent_piper", "label": "Persistent Piper", "desc": "Keep TTS process warm in memory", "gain": "−35 s cold start", "on": True},
    {"key": "tmpfs_model", "label": "Tmpfs Model", "desc": "Copy ONNX to RAM disk", "gain": "−15 s load", "on": True},
    {"key": "warm_piper", "label": "Warm Piper Cache", "desc": "Pre-load ONNX pages at startup", "gain": "−10 s first call", "on": True},
    {"key": "vad_prefilter", "label": "VAD Pre-filter", "desc": "WebRTC VAD strips silence before STT", "gain": "−3 s STT", "on": False},
    {"key": "piper_low_model", "label": "Piper Low Model", "desc": "Use low-quality voice (faster)", "gain": "−13 s TTS", "on": False},
    {"key": "whisper_stt", "label": "Whisper STT", "desc": "Use whisper.cpp instead of Vosk", "gain": "Better WER", "on": False},
    {"key": "silence_strip", "label": "Silence Strip", "desc": "ffmpeg silenceremove on incoming OGG", "gain": "−1 s decode", "on": False},
]


def _role_badge(role: str):
    color_map = {"Admin": "deep-purple", "User": "blue", "Guest": "teal", "Pending": "orange"}
    ui.badge(role, color=color_map.get(role, "grey")).props("dense")


@ui.page("/admin")
def admin_page():
    with page_layout("🔐 Admin Panel", "/admin"):
        # ── Stat cards ──────────────────────────────────────
        with ui.row().classes("w-full gap-md q-mb-lg"):
            for st in STAT_CARDS:
                with ui.card().classes("pico-card").style("flex:1;min-width:160px"):
                    with ui.row().classes("items-center gap-sm"):
                        ui.icon(st["icon"], size="sm").style(f"color:{st['color']}")
                        ui.label(st["label"]).classes("text-dim text-caption")
                    ui.label(st["value"]).classes("text-white text-h6 text-weight-bold q-mt-xs")

        # ── User Management ─────────────────────────────────
        ui.label("User Management").classes("text-white text-h6 text-weight-bold q-mb-sm")
        with ui.card().classes("pico-card w-full q-mb-lg"):
            columns = [
                {"name": "name", "label": "Name", "field": "name", "align": "left"},
                {"name": "id", "label": "Chat ID", "field": "id", "align": "left"},
                {"name": "role", "label": "Role", "field": "role", "align": "left"},
                {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
            ]
            rows = [
                {"name": u["name"], "id": u["id"], "role": u["role"]}
                for u in USERS
            ]
            table = ui.table(columns=columns, rows=rows, row_key="id").props(
                "dark flat dense"
            ).classes("w-full text-white")
            table.add_slot(
                "body-cell-role",
                '<q-td :props="props">'
                '  <q-badge :color="{'
                "    'Admin':'deep-purple','User':'blue','Guest':'teal','Pending':'orange'"
                "  }[props.value]\" dense>{{ props.value }}</q-badge>"
                "</q-td>",
            )
            table.add_slot(
                "body-cell-actions",
                '<q-td :props="props">'
                '  <q-btn v-if="props.row.role===\'Pending\'" flat dense icon="check" color="green" />'
                '  <q-btn v-if="props.row.role===\'Pending\'" flat dense icon="block" color="red" />'
                '  <q-btn v-if="props.row.role!==\'Admin\'" flat dense icon="delete_outline" color="grey" />'
                "</q-td>",
            )

        # ── LLM Model Switcher ──────────────────────────────
        ui.label("LLM Model").classes("text-white text-h6 text-weight-bold q-mb-sm")
        with ui.row().classes("w-full gap-md q-mb-md"):
            for m in LLM_MODELS:
                active = m["active"]
                border = f"2px solid {COLORS['accent']}" if active else f"1px solid {COLORS['border']}"
                with ui.card().classes("pico-card cursor-pointer").style(
                    f"flex:1;min-width:180px;border:{border}"
                ):
                    ui.label(m["name"]).classes("text-white text-body1 text-weight-medium")
                    ui.label(m["provider"]).classes("text-dim text-caption")
                    ui.label(m["desc"]).classes("text-dim text-caption q-mt-xs")
                    if active:
                        ui.badge("Active", color="deep-purple").props("dense").classes("q-mt-sm")

        with ui.row().classes("items-center gap-sm q-mb-lg"):
            ui.input(placeholder="sk-…").props("dense outlined dark type=password").classes(
                "text-white"
            ).style("min-width:300px")
            ui.button("Save API Key", icon="key").props("flat color=deep-purple-4")

        # ── Voice Optimizations ─────────────────────────────
        ui.label("Voice Optimizations").classes("text-white text-h6 text-weight-bold q-mb-sm")
        for vo in VOICE_OPTS:
            with ui.card().classes("pico-card w-full q-mb-sm"):
                with ui.row().classes("items-center justify-between w-full"):
                    with ui.column().classes("gap-none"):
                        ui.label(vo["label"]).classes("text-white text-body1")
                        ui.label(vo["desc"]).classes("text-dim text-caption")
                    with ui.row().classes("items-center gap-sm"):
                        ui.badge(vo["gain"]).props("dense outline color=grey-6")
                        ui.switch(value=vo["on"]).props("dark color=deep-purple")
