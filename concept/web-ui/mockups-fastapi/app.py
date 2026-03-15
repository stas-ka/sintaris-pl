"""Pico Bot — FastAPI + HTMX + Jinja2 mockup entry point.

Static mockup: no real backend logic, only hardcoded demo data.
Run:  python app.py           → http://localhost:8080
      uvicorn app:app --port 8080 --reload
"""

from __future__ import annotations

import calendar
import random
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Pico Bot Mockup")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))


# ── Demo data ──────────────────────────────────────────────────

QUICK_ACTIONS = [
    {"icon": "💬", "title": "Free Chat",    "sub": "Ask anything",              "href": "/chat"},
    {"icon": "📝", "title": "New Note",     "sub": "3 notes total",              "href": "/notes"},
    {"icon": "🗓",  "title": "Calendar",    "sub": "2 events today",             "href": "/calendar"},
    {"icon": "📧", "title": "Mail Digest",  "sub": "Last: 2h ago",              "href": "/mail"},
]

TODAYS_EVENTS = [
    {"time": "10:00", "title": "Team Meeting",       "color": "#00b0ff"},
    {"time": "15:00", "title": "Doctor appointment", "color": "#00c853"},
]

RECENT_NOTES = [
    {"title": "📋 Shopping List", "preview": "Milk, bread, eggs, cheese...",        "date": "Today, 08:30"},
    {"title": "💡 Project Ideas", "preview": "1. Smart home automation...",        "date": "Yesterday, 14:22"},
]

SYSTEM_STATUS = [
    {"label": "Bot Status",  "value": "Online",       "color": "#00c853"},
    {"label": "Pi CPU",      "value": "48%",          "color": "#00b0ff"},
    {"label": "Temperature", "value": "58°C",         "color": "#ffd600"},
    {"label": "LLM",         "value": "GPT-4o-mini",  "color": "#7c4dff"},
]

# ── Chat demo data ─────────────────────────────────────────────

CHAT_MODELS = ["GPT-4o-mini", "GPT-4o", "Claude 3.5 Sonnet"]

MESSAGES = [
    {"role": "bot",  "text": "Hello, Stas! I'm your personal AI assistant. How can I help you today?", "time": "08:00"},
    {"role": "user", "text": "What is the weather forecast for Berlin tomorrow?", "time": "08:12"},
    {
        "role": "bot", "time": "08:12",
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
        "role": "bot", "time": "08:13",
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

# ── Notes demo data ────────────────────────────────────────────

NOTES = [
    {"slug": "shopping-list", "title": "Shopping List",  "preview": "Milk, bread, eggs, cheese…",                          "date": "Today 09:15"},
    {"slug": "meeting-notes", "title": "Meeting Notes",  "preview": "Sprint review outcomes: increased velocity…",       "date": "Yesterday"},
    {"slug": "recipe-borsch", "title": "Recipe: Борщ",   "preview": "Ingredients: beets, cabbage, potatoes…",             "date": "Mar 8"},
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

# ── Calendar demo data ─────────────────────────────────────────

CAL_YEAR, CAL_MONTH, CAL_TODAY = 2026, 3, 10

EVENT_COLORS = {
    "blue": "#5c6bc0", "green": "#66bb6a",
    "purple": "#ab47bc", "orange": "#ffa726",
}

EVENTS_BY_DAY = {
    3:  [{"title": "Dentist",        "color": "blue",   "time": "09:00"}],
    7:  [{"title": "Sprint Review",  "color": "purple", "time": "14:00"}],
    10: [
        {"title": "Lunch with Max", "color": "orange", "time": "12:30"},
        {"title": "Doctor",         "color": "green",  "time": "15:00"},
    ],
    14: [{"title": "Team Standup",   "color": "blue",   "time": "10:00"}],
    21: [{"title": "Sprint Review",  "color": "purple", "time": "14:00"}],
    25: [{"title": "Birthday Party", "color": "orange", "time": "18:00"}],
}

# ── Mail demo data ─────────────────────────────────────────────

DIGEST_STATS = {"total": 12, "important": 2, "promo": 3, "spam": 5, "last_refresh": "Today 07:00"}

CATEGORY_META = {
    "important": {"label": "Important",       "color": "#ef5350", "icon": "priority_high"},
    "regular":   {"label": "Regular",         "color": "#7c4dff", "icon": "mail"},
    "promo":     {"label": "Promotional",     "color": "#ffa726", "icon": "local_offer"},
    "spam":      {"label": "Spam / Blocked",  "color": "#78909c", "icon": "report"},
}

EMAILS = {
    "important": [
        {"from": "GitHub", "time": "06:45", "subject": "Security alert for picoclaw repo", "summary": "A new vulnerability was detected in dependency X. Review and update recommended."},
        {"from": "Boss", "time": "06:30", "subject": "Project deadline moved", "summary": "The delivery date has been moved to April 1st. Please adjust your timeline."},
    ],
    "regular": [
        {"from": "Jira", "time": "06:20", "subject": "Sprint 12 started", "summary": "New sprint with 8 stories and 3 bugs assigned to you."},
        {"from": "Google Calendar", "time": "06:00", "subject": "Reminder: Team Standup", "summary": "Team standup at 10:00 AM in the main conference room."},
    ],
    "promo": [
        {"from": "DigitalOcean", "time": "05:30", "subject": "50% off managed databases", "summary": "Limited-time offer on managed PostgreSQL and MySQL."},
        {"from": "Udemy", "time": "04:00", "subject": "New courses for you", "summary": "Top-rated Python and machine learning courses on sale."},
        {"from": "Amazon", "time": "03:00", "subject": "Deals of the day", "summary": "Electronics and home gadgets up to 40% off today."},
    ],
    "spam": [
        {"from": "unknown@xyz.com", "time": "02:15", "subject": "You've won $1,000,000", "summary": "Congratulations! Click here to claim your prize…"},
    ],
}

# ── Voice demo data ────────────────────────────────────────────

PIPELINE_STEPS = [
    {"label": "OGG → PCM",   "time": "0.8 s",  "pct": 8},
    {"label": "STT (Vosk)",  "time": "3.2 s",  "pct": 31},
    {"label": "LLM",         "time": "1.8 s",  "pct": 17},
    {"label": "TTS (Piper)", "time": "4.2 s",  "pct": 41},
    {"label": "PCM → OGG",   "time": "0.3 s",  "pct": 3},
]

VOICE_TRANSCRIPT = {
    "stt": "Какая погода завтра в Берлине?",
    "response": "Прогноз для **Берлина** на завтра:\n- 🌡 12–18 °C, переменная облачность\n- 💨 Ветер 15 км/ч, западный",
}

VOICE_LANGUAGES = [
    {"code": "ru", "label": "RU", "active": True},
    {"code": "de", "label": "DE", "active": False},
    {"code": "en", "label": "EN", "active": False},
]

# ── Admin demo data ────────────────────────────────────────────

ADMIN_STATS = [
    {"label": "Total Users", "value": "4",              "icon": "group",           "color": "#7c4dff"},
    {"label": "Pending",     "value": "1",              "icon": "pending_actions", "color": "#ffa726"},
    {"label": "Active LLM",  "value": "GPT-4o-mini",    "icon": "smart_toy",       "color": "#66bb6a"},
    {"label": "Pi Status",   "value": "OK  58°C  48%",  "icon": "memory",          "color": "#5c6bc0"},
]

ADMIN_USERS = [
    {"name": "Stas",  "chat_id": "994963580", "role": "Admin",   "badge": "purple", "status": "active"},
    {"name": "Anna",  "chat_id": "112233445", "role": "User",    "badge": "blue",   "status": "active"},
    {"name": "Max",   "chat_id": "556677889", "role": "Guest",   "badge": "teal",   "status": "active"},
    {"name": "Ivan",  "chat_id": "998877665", "role": "Pending", "badge": "orange",  "status": "pending"},
]

LLM_MODELS = [
    {"name": "GPT-4o-mini",       "provider": "OpenAI",     "desc": "Fast, cost-effective", "active": True},
    {"name": "GPT-4o",            "provider": "OpenAI",     "desc": "Most capable",         "active": False},
    {"name": "Claude 3.5 Sonnet", "provider": "Anthropic",  "desc": "Strong reasoning",     "active": False},
    {"name": "Llama-3 70B",       "provider": "OpenRouter", "desc": "Open-source, large",   "active": False},
]

VOICE_OPTS = [
    {"key": "persistent_piper", "label": "Persistent Piper",     "desc": "Keep TTS process warm in memory",     "on": True,  "gain": "−35 s cold start"},
    {"key": "tmpfs_model",      "label": "Tmpfs Model",          "desc": "Copy ONNX to RAM disk",                "on": True,  "gain": "−15 s load"},
    {"key": "warm_piper",       "label": "Warm Piper Cache",     "desc": "Pre-load ONNX pages at startup",       "on": True,  "gain": "−10 s first call"},
    {"key": "vad_prefilter",    "label": "VAD Pre-filter",       "desc": "WebRTC VAD strips silence before STT", "on": False, "gain": "−3 s STT"},
    {"key": "piper_low_model",  "label": "Piper Low Model",      "desc": "Use low-quality voice (faster)",       "on": False, "gain": "−13 s TTS"},
    {"key": "whisper_stt",      "label": "Whisper STT",          "desc": "Use whisper.cpp instead of Vosk",      "on": False, "gain": "Better WER"},
    {"key": "silence_strip",    "label": "Silence Strip",        "desc": "ffmpeg silenceremove on incoming OGG", "on": False, "gain": "−1 s decode"},
]


# ── Helpers ────────────────────────────────────────────────────

def _waveform(n: int, seed: int = 42, lo: int = 4, hi: int = 44) -> list[int]:
    """Generate deterministic random waveform bar heights."""
    rng = random.Random(seed)
    return [rng.randint(lo, hi) for _ in range(n)]


def _month_weeks(year: int, month: int) -> list[list[int]]:
    """Return calendar weeks (Mon=0) with 0 for blanks."""
    return calendar.monthcalendar(year, month)


# ── Routes ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "active_page": "dashboard",
        "quick_actions": QUICK_ACTIONS,
        "todays_events": TODAYS_EVENTS,
        "recent_notes": RECENT_NOTES,
        "system_status": SYSTEM_STATUS,
    })


@app.get("/chat", response_class=HTMLResponse)
async def chat(request: Request):
    return templates.TemplateResponse("chat.html", {
        "request": request, "active_page": "chat",
        "models": CHAT_MODELS, "messages": MESSAGES,
    })


@app.get("/notes", response_class=HTMLResponse)
async def notes(request: Request):
    return templates.TemplateResponse("notes.html", {
        "request": request, "active_page": "notes",
        "notes": NOTES, "sample_md": SAMPLE_MD,
    })


@app.get("/calendar", response_class=HTMLResponse)
async def cal(request: Request):
    weeks = _month_weeks(CAL_YEAR, CAL_MONTH)
    return templates.TemplateResponse("calendar.html", {
        "request": request, "active_page": "calendar",
        "year": CAL_YEAR, "month": CAL_MONTH, "today": CAL_TODAY,
        "weeks": weeks, "events_by_day": EVENTS_BY_DAY,
        "event_colors": EVENT_COLORS,
    })


@app.get("/mail", response_class=HTMLResponse)
async def mail(request: Request):
    waveform = _waveform(40, seed=42)
    return templates.TemplateResponse("mail.html", {
        "request": request, "active_page": "mail",
        "stats": DIGEST_STATS, "emails": EMAILS,
        "category_meta": CATEGORY_META, "waveform": waveform,
    })


@app.get("/voice", response_class=HTMLResponse)
async def voice(request: Request):
    waveform = _waveform(50, seed=7)
    return templates.TemplateResponse("voice.html", {
        "request": request, "active_page": "voice",
        "pipeline": PIPELINE_STEPS, "transcript": VOICE_TRANSCRIPT,
        "languages": VOICE_LANGUAGES, "waveform": waveform,
    })


@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    return templates.TemplateResponse("admin.html", {
        "request": request, "active_page": "admin",
        "stats": ADMIN_STATS, "users": ADMIN_USERS,
        "llm_models": LLM_MODELS, "voice_opts": VOICE_OPTS,
    })


# ── Entry point ────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
