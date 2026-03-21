"""
bot_web.py — FastAPI web interface for Taris Bot.

Phases 0–2: auth + chat + notes + calendar + mail + admin + voice pages.
Run: python bot_web.py  OR  uvicorn bot_web:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import base64
import calendar as cal_mod
import email as _email_mod
import email.header as _email_header_mod
import html
import imaplib
import json
import os
import random
import re
import requests as _requests_lib
import socket
import stat as _stat_mod
import subprocess
import tempfile
import threading
import uuid

try:
    from google_auth_oauthlib.flow import Flow as _GoogleFlow
    from google.oauth2.credentials import Credentials as _GoogleCreds
    from google.auth.transport.requests import Request as _GoogleAuthRequest
    _GOOGLE_AUTH_OK = True
except ImportError:
    _GOOGLE_AUTH_OK = False

try:
    from core.store import store as _store
    _STORE_OK = True
except Exception:
    _store = None   # type: ignore[assignment]
    _STORE_OK = False

# Web UI runs without a Telegram BOT_TOKEN — tell bot_config to skip that check.
os.environ.setdefault("WEB_ONLY", "1")
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, Response, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.bot_config import (
    BOT_VERSION, BOT_NAME, TARIS_BIN, TARIS_CONFIG, NOTES_DIR,
    ACTIVE_MODEL_FILE, RELEASE_NOTES_FILE, log,
)
from security.bot_auth import (
    find_account_by_username, create_account, verify_password,
    create_token, verify_token, list_accounts, ensure_admin_account,
    COOKIE_NAME, find_account_by_id, update_account, change_password,
    find_account_by_chat_id,
)
from core.bot_llm import ask_llm, ask_llm_with_history, get_active_model, list_models, set_active_model
from core.bot_prompts import PROMPTS, fmt_prompt
from ui.bot_ui import UserContext
from ui.screen_loader import load_screen

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

_TARIS_DIR = os.path.expanduser("~/.taris")
_CALENDAR_DIR = os.path.join(_TARIS_DIR, "calendar")

BASE = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE / "web" / "templates"
STATIC_DIR = BASE / "web" / "static"

# ── Web i18n helper (for Screen DSL) ──────────────────────────────────────
_WEB_STRINGS: dict = {}
try:
    with open(BASE / "strings.json", encoding="utf-8") as _f:
        _WEB_STRINGS = json.load(_f)
except Exception:
    log.warning("[Web] Could not load strings.json for Screen DSL i18n")

def _web_t(lang: str, key: str) -> str:
    """Translate a string key for the web UI (Screen DSL)."""
    text = _WEB_STRINGS.get(lang, _WEB_STRINGS.get("en", {})).get(key, key)
    return text.replace("{bot_name}", BOT_NAME) if "{bot_name}" in text else text

# ── Google OAuth2 (Gmail) ──────────────────────────────────────────────────
_GMAIL_OAUTH_SCOPES = ["https://mail.google.com/"]
_oauth_state: dict[str, dict] = {}   # state_token → {uid, redirect_uri}


def _find_google_client_secret() -> Optional[Path]:
    """Auto-detect client_secret_*.json in src/ or .credentials/."""
    for p in sorted(BASE.glob("client_secret_*.json")):
        return p
    for p in sorted((BASE.parent / ".credentials").glob("client_secret_*.json")):
        return p
    return None


def _get_google_creds_obj(creds_data: dict) -> Optional[object]:
    """Return a refreshed Google Credentials object, or None on failure."""
    if not _GOOGLE_AUTH_OK:
        return None
    cs = _find_google_client_secret()
    if not cs:
        return None
    client_info = json.loads(cs.read_text(encoding="utf-8"))
    app = client_info.get("installed") or client_info.get("web") or {}
    gc = _GoogleCreds(
        token=creds_data.get("access_token"),
        refresh_token=creds_data.get("refresh_token"),
        token_uri=app.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=app.get("client_id", ""),
        client_secret=app.get("client_secret", ""),
        scopes=creds_data.get("scopes", _GMAIL_OAUTH_SCOPES),
    )
    if not gc.valid and gc.refresh_token:
        try:
            gc.refresh(_GoogleAuthRequest())
        except Exception as exc:
            log.warning(f"[Mail] OAuth2 refresh failed: {exc}")
            return None
    return gc

# ─────────────────────────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Taris Bot Web UI")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ─────────────────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_current_user(request: Request) -> Optional[dict]:
    """Read JWT from cookie and return user payload or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = verify_token(token)
    if not payload:
        return None
    return payload


def _require_auth(request: Request) -> dict:
    """Return current user or raise 302 redirect to /login."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


def _ctx(request: Request, user: dict, page: str, **extra) -> dict:
    """Build common template context."""
    return {
        "request": request,
        "active_page": page,
        "user": user,
        "bot_version": BOT_VERSION,
        **extra,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers — Notes
# ─────────────────────────────────────────────────────────────────────────────

def _notes_dir_for(user_id: str) -> Path:
    """Return the notes directory for a web user.

    Priority: if the account has a linked telegram_chat_id and that notes
    directory already exists (created by the Telegram bot), use it so web and
    Telegram share the same notes.  Otherwise fall back to the web user_id dir.
    """
    account = find_account_by_id(user_id)
    if account:
        chat_id = account.get("telegram_chat_id")
        if chat_id:
            tg_dir = Path(NOTES_DIR) / str(chat_id)
            if tg_dir.exists():
                return tg_dir
    d = Path(NOTES_DIR) / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_notes(user_id: str) -> list[dict]:
    d = _notes_dir_for(user_id)
    notes = []
    for f in sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        title = f.stem.replace("_", " ").title()
        text = f.read_text(encoding="utf-8", errors="replace")
        preview = text[:80].replace("\n", " ")
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        notes.append({
            "slug": f.stem,
            "title": title,
            "preview": preview,
            "date": mtime.strftime("%Y-%m-%d %H:%M"),
            "content": text,
        })
    return notes


def _load_note(user_id: str, slug: str) -> Optional[str]:
    p = _notes_dir_for(user_id) / f"{slug}.md"
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    return None


def _save_note(user_id: str, slug: str, content: str) -> None:
    p = _notes_dir_for(user_id) / f"{slug}.md"
    p.write_text(content, encoding="utf-8")


def _delete_note(user_id: str, slug: str) -> bool:
    p = _notes_dir_for(user_id) / f"{slug}.md"
    if p.exists():
        p.unlink()
        return True
    return False


def _slugify(title: str) -> str:
    import re
    slug = re.sub(r"[^\w\s-]", "", title.lower().strip())
    return re.sub(r"[\s-]+", "_", slug)[:60]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers — Calendar
# ─────────────────────────────────────────────────────────────────────────────

def _cal_load(user_id: str) -> list[dict]:
    p = Path(_CALENDAR_DIR) / f"{user_id}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _cal_events_by_day(events: list[dict], year: int, month: int) -> dict[str, list]:
    """Return events keyed by 'YYYY-MM-DD' strings matching the Jinja2 template's day_key."""
    result: dict[str, list] = {}
    for ev in events:
        try:
            dt = datetime.fromisoformat(ev.get("dt_iso", ""))
            if dt.year == year and dt.month == month:
                key = f"{year}-{month:02d}-{dt.day:02d}"
                result.setdefault(key, []).append({
                    "title": ev.get("title", "?"),
                    "time": dt.strftime("%H:%M"),
                    "id": ev.get("id", ""),
                })
        except (ValueError, TypeError):
            continue
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers — System status
# ─────────────────────────────────────────────────────────────────────────────

def _system_status() -> list[dict]:
    """Collect basic system metrics."""
    status = [{"label": "Bot Status", "value": "Online", "color": "#00c853"}]
    try:
        with open("/proc/loadavg") as f:
            load = f.read().split()[0]
        status.append({"label": "Load Avg", "value": load, "color": "#00b0ff"})
    except OSError:
        status.append({"label": "Load Avg", "value": "N/A", "color": "#78909c"})
    try:
        temp_raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        temp_c = int(temp_raw) // 1000
        color = "#00c853" if temp_c < 60 else "#ffd600" if temp_c < 70 else "#ff1744"
        status.append({"label": "Temperature", "value": f"{temp_c}°C", "color": color})
    except OSError:
        status.append({"label": "Temperature", "value": "N/A", "color": "#78909c"})
    model = get_active_model() or "default"
    status.append({"label": "LLM", "value": model, "color": "#7c4dff"})
    return status


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers — Voice opts
# ─────────────────────────────────────────────────────────────────────────────

_VOICE_OPTS_FILE = os.path.join(_TARIS_DIR, "voice_opts.json")

def _load_voice_opts() -> dict:
    try:
        return json.loads(Path(_VOICE_OPTS_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_voice_opts(opts: dict) -> None:
    Path(_VOICE_OPTS_FILE).write_text(
        json.dumps(opts, indent=2), encoding="utf-8"
    )

_VOICE_OPT_META = [
    ("persistent_piper", "Persistent Piper",  "Keep TTS process warm in memory",       "-35 s cold start"),
    ("tmpfs_model",      "Tmpfs Model",       "Copy ONNX to RAM disk",                  "-15 s load"),
    ("warm_piper",       "Warm Piper Cache",  "Pre-load ONNX pages at startup",         "-10 s first call"),
    ("vad_prefilter",    "VAD Pre-filter",    "WebRTC VAD strips silence before STT",   "-3 s STT"),
    ("piper_low_model",  "Piper Low Model",   "Use low-quality voice (faster)",         "-13 s TTS"),
    ("whisper_stt",      "Whisper STT",       "Use whisper.cpp instead of Vosk",        "Better WER"),
    ("silence_strip",    "Silence Strip",     "ffmpeg silenceremove on incoming OGG",   "-1 s decode"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Per-user chat history (in-memory, session-scoped)
# ─────────────────────────────────────────────────────────────────────────────

_chat_history: dict[str, list[dict]] = {}  # user_id → [{role, text, time}]


# ─────────────────────────────────────────────────────────────────────────────
# Auth routes
# ─────────────────────────────────────────────────────────────────────────────

_HOSTNAME = socket.gethostname()

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = _get_current_user(request)
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request, "error": None, "hostname": _HOSTNAME, "username": None,
    })


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    account = find_account_by_username(username)
    if not account or not verify_password(account, password):
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid username or password",
            "hostname": _HOSTNAME, "username": username,
        })
    status = account.get("status", "active")
    if status == "pending":
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Account pending admin approval. Please wait.",
            "hostname": _HOSTNAME, "username": username,
        })
    if status == "blocked":
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Account blocked. Contact admin.",
            "hostname": _HOSTNAME, "username": username,
        })
    token = create_token(account["user_id"], account["username"], account.get("role", "user"))
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True, samesite="lax", max_age=86400,
    )
    return resp


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {
        "request": request, "error": None, "hostname": _HOSTNAME,
    })


@app.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(""),
    link_code: str = Form(""),
):
    if len(username) < 3 or len(password) < 4:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Username must be >= 3 chars, password >= 4 chars",
            "hostname": _HOSTNAME,
        })
    if find_account_by_username(username):
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Username already taken", "hostname": _HOSTNAME,
        })

    # ── Telegram link code handling ──────────────────────────────────────────
    telegram_chat_id = None
    inherited_role   = "user"
    if link_code.strip():
        import core.bot_state as _st_web
        from core.bot_config import ADMIN_USERS
        validated_cid = _st_web.validate_web_link_code(link_code.strip())
        if not validated_cid:
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Link code is invalid or expired. Get a new code from the Telegram bot.",
                "hostname": _HOSTNAME,
            })
        if find_account_by_chat_id(validated_cid):
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "This Telegram account is already linked to a web account.",
                "hostname": _HOSTNAME,
            })
        telegram_chat_id = validated_cid
        if validated_cid in ADMIN_USERS:
            inherited_role = "admin"

    # ── Account creation ──────────────────────────────────────────────────────
    # First non-admin self-registration gets active status;
    # subsequent ones are pending unless linked via a Telegram code.
    existing = [a for a in list_accounts() if a.get("role") != "admin"]
    if telegram_chat_id:
        new_status = "active"   # Telegram-linked accounts inherit approved status
    else:
        new_status = "active" if not existing else "pending"
    account = create_account(username, password,
                             display_name=display_name or username,
                             role=inherited_role,
                             telegram_chat_id=telegram_chat_id,
                             status=new_status)
    if new_status == "pending":
        return templates.TemplateResponse("register.html", {
            "request": request,
            "info": "Registration submitted. An admin will review your account.",
            "hostname": _HOSTNAME,
        })
    token = create_token(account["user_id"], account["username"], account.get("role", "user"))
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=86400)
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Settings (language + password)
# ─────────────────────────────────────────────────────────────────────────────

_SUPPORTED_LANGS = {"en": "🇬🇧 English", "ru": "🇷🇺 Русский", "de": "🇩🇪 Deutsch"}


# ─────────────────────────────────────────────────────────────────────────────
# Profile page
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, msg: str = "", error: str = ""):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    account = find_account_by_id(user["sub"]) or {}
    # Try to load linked Telegram registration record
    tg_chat_id = account.get("telegram_chat_id")
    tg_reg = None
    if tg_chat_id:
        try:
            from telegram.bot_users import _find_registration
            tg_reg = _find_registration(int(tg_chat_id))
        except Exception:
            pass
    return templates.TemplateResponse("profile.html", _ctx(
        request, user, "profile",
        account=account,
        tg_reg=tg_reg,
        msg=msg,
        error=error,
    ))


@app.post("/profile/name", response_class=HTMLResponse)
async def profile_update_name(request: Request, display_name: str = Form(...)):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    display_name = display_name.strip()
    if not display_name:
        return RedirectResponse("/profile?error=Name+cannot+be+empty", status_code=302)
    update_account(user["sub"], display_name=display_name)
    return RedirectResponse("/profile?msg=name_saved", status_code=302)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, msg: str = "", error: str = ""):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    account = find_account_by_id(user["sub"]) or {}
    current_lang = account.get("language", "en")
    return templates.TemplateResponse("settings.html", _ctx(
        request, user, "settings",
        current_lang=current_lang,
        supported_langs=_SUPPORTED_LANGS,
        msg=msg,
        error=error,
    ))


@app.post("/settings/language", response_class=HTMLResponse)
async def settings_set_language(request: Request, language: str = Form(...)):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if language not in _SUPPORTED_LANGS:
        return RedirectResponse("/settings?error=invalid_language", status_code=302)
    update_account(user["sub"], language=language)
    return RedirectResponse("/settings?msg=language_saved", status_code=302)


@app.post("/settings/password", response_class=HTMLResponse)
async def settings_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    account = find_account_by_id(user["sub"])
    current_lang = (account or {}).get("language", "en")
    ctx_error = lambda msg: templates.TemplateResponse("settings.html", _ctx(
        request, user, "settings",
        current_lang=current_lang,
        supported_langs=_SUPPORTED_LANGS,
        msg="",
        error=msg,
    ))
    if not account or not verify_password(account, current_password):
        return ctx_error("Current password is incorrect.")
    if len(new_password) < 4:
        return ctx_error("New password must be at least 4 characters.")
    if new_password != confirm_password:
        return ctx_error("New passwords do not match.")
    change_password(user["sub"], new_password)
    return RedirectResponse("/settings?msg=password_changed", status_code=302)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    uid = user["sub"]
    notes = _list_notes(uid)[:3]
    events = _cal_load(uid)
    now = datetime.now()
    today_events = []
    for ev in events:
        try:
            dt = datetime.fromisoformat(ev.get("dt_iso", ""))
            if dt.date() == now.date():
                today_events.append({
                    "time": dt.strftime("%H:%M"),
                    "title": ev.get("title", "?"),
                    "color": "#00b0ff",
                })
        except (ValueError, TypeError):
            continue

    quick_actions = [
        {"icon": "💬", "title": "Free Chat",   "sub": "Ask anything",            "href": "/chat"},
        {"icon": "📝", "title": "New Note",    "sub": f"{len(notes)} notes",     "href": "/notes"},
        {"icon": "🗓",  "title": "Calendar",   "sub": f"{len(today_events)} today", "href": "/calendar"},
        {"icon": "📧", "title": "Mail Digest", "sub": "View digest",             "href": "/mail"},
    ]

    recent_notes = [
        {"title": n["title"], "preview": n["preview"], "date": n["date"]}
        for n in notes[:3]
    ]

    return templates.TemplateResponse("dashboard.html", _ctx(
        request, user, "dashboard",
        quick_actions=quick_actions,
        todays_events=today_events,
        recent_notes=recent_notes,
        system_status=_system_status(),
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    uid = user["sub"]
    messages = _chat_history.get(uid, [])
    models_list = [m.get("model_name", m.get("model", "?")) for m in list_models()]
    if not models_list:
        models_list = ["default"]

    return templates.TemplateResponse("chat.html", _ctx(
        request, user, "chat",
        models=models_list,
        messages=messages,
    ))


@app.post("/chat/send", response_class=HTMLResponse)
async def chat_send(request: Request, message: str = Form(...)):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)

    uid = user["sub"]
    history = _chat_history.setdefault(uid, [])
    now_str = datetime.now().strftime("%H:%M")

    history.append({"role": "user", "text": message, "time": now_str})

    # Build LLM messages list from display history (convert "bot" role to "assistant")
    llm_messages = [
        {"role": "user" if e["role"] == "user" else "assistant", "content": e["text"]}
        for e in history
    ]
    reply = ask_llm_with_history(llm_messages, timeout=60)
    if not reply:
        reply = "No response from LLM."
    history.append({"role": "bot", "text": reply, "time": now_str})

    return templates.TemplateResponse("_chat_messages.html", {
        "request": request,
        "user_text": message,
        "user_time": now_str,
        "bot_text": reply,
        "bot_time": now_str,
    })


@app.delete("/chat/clear")
async def chat_clear(request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)
    _chat_history.pop(user["sub"], None)
    return Response(headers={"HX-Redirect": "/chat"})


# ─────────────────────────────────────────────────────────────────────────────
# Notes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/notes", response_class=HTMLResponse)
async def notes_page(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    uid = user["sub"]
    notes = _list_notes(uid)
    active_note = notes[0] if notes else None

    # Pass flat vars so _note_editor.html partial works on initial load
    slug = title = content = None
    if active_note:
        slug = active_note["slug"]
        title = active_note["title"]
        content = active_note["content"]

    return templates.TemplateResponse("notes.html", _ctx(
        request, user, "notes",
        notes=notes,
        active_note=active_note,
        slug=slug,
        title=title,
        content=content,
    ))


@app.get("/notes/{slug}", response_class=HTMLResponse)
async def note_detail(request: Request, slug: str):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)

    uid = user["sub"]
    content = _load_note(uid, slug)
    if content is None:
        raise HTTPException(404)

    title = slug.replace("_", " ").title()
    return templates.TemplateResponse("_note_editor.html", {
        "request": request,
        "slug": slug,
        "title": title,
        "content": content,
        "saved": False,
    })


@app.post("/notes/create", response_class=HTMLResponse)
async def note_create(request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)
    title = f"Note {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    slug = _slugify(title)
    if not slug:
        slug = "untitled"
    _save_note(user["sub"], slug, "")
    return Response(headers={"HX-Redirect": "/notes"})


@app.get("/notes/list", response_class=HTMLResponse)
async def notes_list_partial(request: Request):
    """Returns just the note-list sidebar partial (used by HTMX noteListRefresh event)."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)
    notes = _list_notes(user["sub"])
    return templates.TemplateResponse("_note_list.html", {
        "request": request,
        "notes": notes,
    })


@app.post("/notes/{slug}/save")
async def note_save(request: Request, slug: str, content: str = Form(...), title: str = Form(None)):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)
    uid = user["sub"]
    # Rename slug if title changed
    new_slug = slug
    slug_changed = False
    if title:
        new_slug = _slugify(title)
        if new_slug and new_slug != slug:
            old_path = _notes_dir_for(uid) / f"{slug}.md"
            new_path = _notes_dir_for(uid) / f"{new_slug}.md"
            if old_path.exists() and not new_path.exists():
                old_path.rename(new_path)
                slug_changed = True
            else:
                new_slug = slug  # keep old slug if conflict
    _save_note(uid, new_slug, content)
    # Slug changed → redirect so the sidebar re-renders with the new slug/title
    if slug_changed:
        return Response(headers={"HX-Redirect": "/notes"})
    display_title = title or new_slug.replace("_", " ").title()
    resp = templates.TemplateResponse("_note_editor.html", {
        "request": request,
        "slug": new_slug,
        "title": display_title,
        "content": content,
        "saved": True,
    })
    # Fire HTMX event so the sidebar refreshes its note list (updated dates etc.)
    resp.headers["HX-Trigger"] = "noteListRefresh"
    return resp


@app.delete("/notes/{slug}")
async def note_delete(request: Request, slug: str):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)
    _delete_note(user["sub"], slug)
    return Response(headers={"HX-Redirect": "/notes"})


# ─────────────────────────────────────────────────────────────────────────────
# Calendar
# ─────────────────────────────────────────────────────────────────────────────

# List of hex colours for event pills – indexed by position, not name
EVENT_COLORS = ["#5c6bc0", "#66bb6a", "#ab47bc", "#ffa726"]


def _new_ev_id() -> str:
    return uuid.uuid4().hex[:8]


def _cal_save(user_id: str, events: list[dict]) -> None:
    p = Path(_CALENDAR_DIR) / f"{user_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    if _STORE_OK:
        try:
            for ev in events:
                _store.save_event(user_id, ev)
        except Exception as _e:
            log.warning("[Cal/Web] _store.save_event failed: %s", _e)


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    uid = user["sub"]
    now = datetime.now()
    year, month, today = now.year, now.month, now.day
    weeks = cal_mod.monthcalendar(year, month)
    events = _cal_load(uid)
    ebd = _cal_events_by_day(events, year, month)
    month_name = cal_mod.month_name[month]

    # All future events sorted ascending, capped at 10 for the sidebar list
    upcoming: list[dict] = []
    for ev in events:
        try:
            dt = datetime.fromisoformat(ev.get("dt_iso", ""))
            if dt >= now:
                upcoming.append({
                    "id": ev.get("id", ""),
                    "title": ev.get("title", "?"),
                    "dt": dt.strftime("%Y-%m-%d %H:%M"),
                })
        except (ValueError, TypeError):
            continue
    upcoming.sort(key=lambda x: x["dt"])
    upcoming = upcoming[:10]

    return templates.TemplateResponse("calendar.html", _ctx(
        request, user, "calendar",
        year=year, month=month, month_name=month_name, today=today,
        weeks=weeks, events_by_day=ebd, event_colors=EVENT_COLORS,
        upcoming_events=upcoming,
    ))


@app.post("/calendar/add")
async def calendar_add(
    request: Request,
    title: str = Form(...),
    dt_str: str = Form(...),
    remind: int = Form(15),
):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    uid = user["sub"]
    events = _cal_load(uid)
    try:
        dt_iso = datetime.fromisoformat(dt_str).isoformat()
    except ValueError:
        dt_iso = dt_str
    events.append({
        "id": _new_ev_id(),
        "title": title,
        "dt_iso": dt_iso,
        "remind_before_min": remind,
        "reminded": False,
    })
    _cal_save(uid, events)
    return RedirectResponse("/calendar", status_code=303)


@app.post("/calendar/{ev_id}/delete")
async def calendar_delete(
    request: Request,
    ev_id: str,
):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    uid = user["sub"]
    events = _cal_load(uid)
    events = [e for e in events if e.get("id") != ev_id]
    _cal_save(uid, events)
    return RedirectResponse("/calendar", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Calendar — AI voice parse & console
# ─────────────────────────────────────────────────────────────────────────────

def _cal_parse_events_fallback(text: str) -> list[dict]:
    """Rule-based fallback: dateutil fuzzy parse extracts datetime; remaining text -> title.
    Used when LLM is unavailable (no API key configured).
    """
    try:
        from dateutil import parser as dparser
        now = datetime.now()
        default_dt = now.replace(hour=9, minute=0, second=0, microsecond=0)
        dt, tokens = dparser.parse(text, fuzzy_with_tokens=True, default=default_dt)
        # Build title from non-date tokens; strip dangling prepositions left by dateutil
        _DATE_PREPS = re.compile(
            r"\b(at|on|in|by|for|from|to|до|в|на|по|завтра|сегодня|послезавтра)\b",
            re.IGNORECASE | re.UNICODE,
        )
        title_parts = [t.strip(" ,;:-–/") for t in tokens if t.strip(" ,;:-–/")]
        title = " ".join(p for p in title_parts if p).strip()
        title = _DATE_PREPS.sub(" ", title).strip(" ,;:- ")
        title = re.sub(r"\s{2,}", " ", title).strip()
        if not title:
            title = text.strip()
        # If the parsed datetime is already in the past, nudge to next year
        if dt < now.replace(hour=0, minute=0, second=0, microsecond=0):
            try:
                dt = dt.replace(year=dt.year + 1)
            except ValueError:
                pass
        dt_iso = dt.strftime("%Y-%m-%dT%H:%M")
        return [{"title": title, "dt_iso": dt_iso, "remind_min": 15}]
    except Exception as exc:
        log.debug(f"[CalFallback] dateutil parse failed: {exc}")
        clean = text.strip()
        if clean:
            today_09 = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
            return [{"title": clean, "dt_iso": today_09.strftime("%Y-%m-%dT%H:%M"), "remind_min": 15}]
        return []


def _cal_parse_events_from_text(text: str) -> list[dict]:
    """Call LLM to extract event(s) from free-form text; falls back to rule-based parser.
    Returns a list of dicts: [{title, dt_iso, remind_min}, ...]
    """
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M")
    prompt = fmt_prompt(PROMPTS["web"]["cal_event_parse"], now_iso=now_iso, text=text)
    raw = ask_llm(prompt, timeout=30)
    try:
        m = re.search(r'\{.*\}', raw or "", re.DOTALL)
        parsed = json.loads(m.group()) if m else {"events": []}
        events = []
        for item in parsed.get("events", []):
            title = str(item.get("title", "")).strip()
            dt_str = str(item.get("dt", "")).strip()
            if title and dt_str:
                events.append({"title": title, "dt_iso": dt_str, "remind_min": 15})
        if events:
            return events
    except Exception as exc:
        log.warning(f"[CalParse] JSON parse failed: {exc}; raw={(raw or '')[:120]}")
    # LLM unavailable or returned no events — use rule-based fallback
    log.debug("[CalParse] LLM returned no events — using rule-based fallback")
    return _cal_parse_events_fallback(text)


@app.post("/calendar/parse-text")
async def calendar_parse_text(request: Request):
    """AI event parser used by voice recognition — returns JSON list of events."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"events": []}, status_code=401)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"events": []})
    events = _cal_parse_events_from_text(text)
    return JSONResponse({"events": events})


@app.post("/calendar/console")
async def calendar_console_route(request: Request):
    """AI calendar console — classify intent and route: add / query / delete / edit."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"action": "error", "message": "Not authenticated"}, status_code=401)
    uid = user["sub"]
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"action": "error", "message": "Empty input"})

    events = _cal_load(uid)
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M")
    event_hints = [f"id={e['id']} title={e.get('title','')!r}" for e in events[:10]]
    events_hint = "; ".join(event_hints) if event_hints else "none"

    intent_prompt = fmt_prompt(PROMPTS["web"]["cal_intent"], now_iso=now_iso, events_hint=events_hint, text=text)
    raw_intent = ask_llm(intent_prompt, timeout=20)
    intent = "add"
    ev_id: str | None = None
    if raw_intent:
        try:
            m = re.search(r'\{[^{}]+\}', raw_intent, re.DOTALL)
            if m:
                data = json.loads(m.group())
                intent = data.get("intent", "add")
                ev_id = data.get("ev_id") or None
        except Exception as exc:
            log.warning(f"[CalConsole] intent parse failed: {exc}; raw={raw_intent[:120]}")
    else:
        # LLM unavailable — keyword-based intent detection (Russian + English)
        tl = text.lower()
        if any(w in tl for w in ["show", "list", "what", "upcoming", "when", "schedule",
                                  "покажи", "список", "что", "когда", "расписание"]):
            intent = "query"
        elif any(w in tl for w in ["delete", "remove", "cancel",
                                    "удали", "отмени", "удалить", "отменить"]):
            intent = "delete"
        elif any(w in tl for w in ["edit", "change", "reschedule", "move", "modify",
                                    "перенеси", "измени", "перенести", "изменить"]):
            intent = "edit"

    # ── query ──────────────────────────────────────────────────────────────
    if intent == "query":
        upcoming = [
            {"id": e["id"], "title": e["title"], "dt_iso": e.get("dt_iso", "")}
            for e in events
            if e.get("dt_iso", "") >= now_iso
        ][:8]
        return JSONResponse({"action": "query", "events": upcoming})

    # ── delete / edit ───────────────────────────────────────────────────────
    if intent in ("delete", "edit"):
        ev = next((e for e in events if e.get("id") == ev_id), None)
        if not ev:
            tl = text.lower()
            ev = next((e for e in events if e.get("title", "").lower() in tl), None)
        if ev and intent == "delete":
            return JSONResponse({"action": "delete", "ev_id": ev["id"], "title": ev["title"]})
        if ev:
            return JSONResponse({
                "action": "edit",
                "ev_id": ev["id"],
                "title": ev.get("title", ""),
                "dt_iso": ev.get("dt_iso", ""),
                "remind_min": ev.get("remind_before_min", 15),
            })
        return JSONResponse({"action": "error", "message": "Event not found in your calendar"})

    # ── add (default) ───────────────────────────────────────────────────────
    parsed_events = _cal_parse_events_from_text(text)
    if not parsed_events:
        return JSONResponse({"action": "error",
                             "message": "Could not extract event details — please be more specific"})
    return JSONResponse({"action": "add", "events": parsed_events})


# ─────────────────────────────────────────────────────────────────────────────
# Gmail OAuth2 routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/mail/oauth/google/start")
async def google_oauth_start(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not _GOOGLE_AUTH_OK:
        return RedirectResponse("/mail?error=Google+auth+library+not+available", status_code=302)
    cs = _find_google_client_secret()
    if not cs:
        return RedirectResponse("/mail?error=Google+client_secret+file+not+found+on+server", status_code=302)
    redirect_uri = str(request.base_url).rstrip("/") + "/mail/oauth/google/callback"
    flow = _GoogleFlow.from_client_secrets_file(str(cs), scopes=_GMAIL_OAUTH_SCOPES,
                                                redirect_uri=redirect_uri)
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent",
                                             include_granted_scopes="true")
    _oauth_state[state] = {"uid": user["sub"], "redirect_uri": redirect_uri}
    return RedirectResponse(auth_url, status_code=302)


@app.get("/mail/oauth/google/callback")
async def google_oauth_callback(request: Request, code: str = "", state: str = "",
                                error: str = ""):
    if error:
        return RedirectResponse("/mail?error=Google+sign-in+was+cancelled", status_code=302)
    state_data = _oauth_state.pop(state, None)
    if not state_data:
        return RedirectResponse("/mail?error=OAuth+session+expired+-+please+try+again",
                                status_code=302)
    uid = state_data["uid"]
    cs = _find_google_client_secret()
    flow = _GoogleFlow.from_client_secrets_file(
        str(cs), scopes=_GMAIL_OAUTH_SCOPES,
        redirect_uri=state_data["redirect_uri"], state=state,
    )
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        log.warning(f"[Mail] OAuth2 token exchange failed: {exc}")
        return RedirectResponse("/mail?error=Token+exchange+failed+-+please+retry",
                                status_code=302)
    gc = flow.credentials
    # Get the user's email address from Gmail API
    email_addr = ""
    try:
        r = _requests_lib.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            headers={"Authorization": f"Bearer {gc.token}"}, timeout=10,
        )
        if r.ok:
            email_addr = r.json().get("emailAddress", "")
    except Exception:
        pass
    # Store tokens
    mail_dir = Path(_TARIS_DIR) / "mail_creds"
    mail_dir.mkdir(parents=True, exist_ok=True)
    creds_file = mail_dir / f"{uid}.json"
    creds_data = {
        "provider": "gmail", "email": email_addr, "auth_type": "oauth2",
        "access_token": gc.token, "refresh_token": gc.refresh_token,
        "token_expiry": gc.expiry.isoformat() if gc.expiry else None,
        "scopes": list(gc.scopes or _GMAIL_OAUTH_SCOPES),
        "imap_host": "imap.gmail.com", "imap_port": 993,
        "spam_folder": "[Google Mail]/Spam",
    }
    creds_file.write_text(json.dumps(creds_data, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    try:
        os.chmod(creds_file, 0o600)
    except Exception:
        pass
    if _STORE_OK:
        try:
            _store.save_mail_creds(uid, creds_data)
        except Exception as _e:
            log.warning("[Mail/Web] _store.save_mail_creds failed: %s", _e)
    log.info(f"[Mail] OAuth2 Gmail connected: {email_addr} for user {uid}")
    return RedirectResponse("/mail", status_code=302)


# ─────────────────────────────────────────────────────────────────────────────
# Contacts
# ─────────────────────────────────────────────────────────────────────────────

PAGE_SIZE = 20

def _contacts_for(chat_id: int, q: str = "", offset: int = 0) -> tuple[list[dict], int]:
    """Return (contacts, total) for a user. Optionally filtered by search query."""
    from features.bot_contacts import _contact_search, _contact_list, _contact_count
    if q:
        results = _contact_search(chat_id, q)
        return results, len(results)
    return _contact_list(chat_id, offset=offset, limit=PAGE_SIZE), _contact_count(chat_id)


@app.get("/contacts", response_class=HTMLResponse)
async def contacts_page(request: Request, q: str = "", page: int = 0):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    account = find_account_by_id(user["sub"])
    chat_id = (account or {}).get("telegram_chat_id") or 0
    offset = page * PAGE_SIZE
    contacts, total = _contacts_for(chat_id, q=q, offset=offset)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    return templates.TemplateResponse(
        "contacts.html",
        _ctx(request, user, "contacts",
             contacts=contacts, total=total, q=q,
             page=page, pages=pages, page_size=PAGE_SIZE),
    )


@app.get("/contacts/new", response_class=HTMLResponse)
async def contacts_new_form(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        "contacts.html",
        _ctx(request, user, "contacts",
             contacts=[], total=0, q="", page=0, pages=1, page_size=PAGE_SIZE,
             show_form=True, form_contact=None),
    )


@app.post("/contacts/new")
async def contacts_create(
    request: Request,
    name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    notes: str = Form(""),
):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    from features.bot_contacts import _contact_add
    account = find_account_by_id(user["sub"])
    chat_id = (account or {}).get("telegram_chat_id") or 0
    _contact_add(chat_id,
                 name=name.strip(),
                 phone=phone.strip() or None,
                 email=email.strip() or None,
                 address=address.strip() or None,
                 notes=notes.strip() or None)
    return RedirectResponse("/contacts", status_code=303)


@app.get("/contacts/{cid}", response_class=HTMLResponse)
async def contacts_detail(request: Request, cid: str):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    from features.bot_contacts import _contact_get
    account = find_account_by_id(user["sub"])
    chat_id = (account or {}).get("telegram_chat_id") or 0
    contact = _contact_get(chat_id, cid)
    if not contact:
        return RedirectResponse("/contacts", status_code=302)
    return templates.TemplateResponse(
        "contacts.html",
        _ctx(request, user, "contacts",
             contacts=[], total=0, q="", page=0, pages=1, page_size=PAGE_SIZE,
             show_form=True, form_contact=contact),
    )


@app.post("/contacts/{cid}")
async def contacts_update(
    request: Request,
    cid: str,
    name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    notes: str = Form(""),
):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    from features.bot_contacts import _contact_update
    account = find_account_by_id(user["sub"])
    chat_id = (account or {}).get("telegram_chat_id") or 0
    _contact_update(chat_id, cid,
                    name=name.strip(),
                    phone=phone.strip() or None,
                    email=email.strip() or None,
                    address=address.strip() or None,
                    notes=notes.strip() or None)
    return RedirectResponse(f"/contacts/{cid}", status_code=303)


@app.post("/contacts/{cid}/delete")
async def contacts_delete(request: Request, cid: str):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    from features.bot_contacts import _contact_delete
    account = find_account_by_id(user["sub"])
    chat_id = (account or {}).get("telegram_chat_id") or 0
    _contact_delete(chat_id, cid)
    return RedirectResponse("/contacts", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Mail
# ─────────────────────────────────────────────────────────────────────────────

def _waveform(n: int = 40, seed: int = 42) -> list[int]:
    rng = random.Random(seed)
    return [rng.randint(4, 44) for _ in range(n)]


_MAIL_PROVIDERS = {
    "gmail":  {"label": "Gmail",       "imap_host": "imap.gmail.com", "imap_port": 993, "spam_folder": "[Google Mail]/Spam"},
    "yandex": {"label": "Яндекс.Почта","imap_host": "imap.yandex.ru", "imap_port": 993, "spam_folder": "Spam"},
    "mailru": {"label": "Mail.ru",      "imap_host": "imap.mail.ru",  "imap_port": 993, "spam_folder": "Spam"},
    "custom": {"label": "Custom IMAP",  "imap_host": "",              "imap_port": 993, "spam_folder": None},
}


def _mail_creds_path(uid: str) -> Path:
    """Creds file for a web user ID."""
    return Path(_TARIS_DIR) / "mail_creds" / f"{uid}.json"


def _load_mail_creds_for_user(uid: str) -> Optional[dict]:
    """Load mail creds for a web user, falling back to their linked Telegram chat_id."""
    p = _mail_creds_path(uid)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Legacy fallback: Telegram-linked account may have creds under numeric chat_id
    acc = find_account_by_id(uid)
    if acc and acc.get("telegram_chat_id"):
        tp = Path(_TARIS_DIR) / "mail_creds" / f"{acc['telegram_chat_id']}.json"
        if tp.exists():
            try:
                return json.loads(tp.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


@app.get("/mail", response_class=HTMLResponse)
async def mail_page(request: Request, show_settings: bool = False, error: str = ""):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    uid = user["sub"]
    mail_dir = Path(_TARIS_DIR) / "mail_creds"

    # Load cached digest (web user_id first, then Telegram chat_id for legacy)
    digest_file = mail_dir / f"{uid}_last_digest.txt"
    if not digest_file.exists():
        acc = find_account_by_id(uid)
        if acc and acc.get("telegram_chat_id"):
            digest_file = mail_dir / f"{acc['telegram_chat_id']}_last_digest.txt"
    digest_text = ""
    if digest_file.exists():
        digest_text = digest_file.read_text(encoding="utf-8", errors="replace")

    creds = _load_mail_creds_for_user(uid)
    has_creds = creds is not None

    # Build a safe (masked) view of creds for display
    creds_display = None
    if creds:
        creds_display = {
            "provider":    creds.get("provider", "custom"),
            "email":       creds.get("email", ""),
            "imap_host":   creds.get("imap_host", ""),
            "imap_port":   creds.get("imap_port", 993),
            "spam_folder": creds.get("spam_folder", ""),
            "auth_type":   creds.get("auth_type", "password"),
            "provider_label": _MAIL_PROVIDERS.get(
                creds.get("provider", "custom"), _MAIL_PROVIDERS["custom"]
            )["label"],
        }

    return templates.TemplateResponse("mail.html", _ctx(
        request, user, "mail",
        digest_text=digest_text,
        waveform=_waveform(),
        has_creds=has_creds,
        creds=creds_display,
        show_settings=show_settings or not has_creds,
        providers=_MAIL_PROVIDERS,
        form_error=error,
        google_auth_ok=_GOOGLE_AUTH_OK,
        google_client_secret_ok=bool(_find_google_client_secret()),
    ))


@app.post("/mail/settings")
async def mail_settings_save(request: Request):
    """Save (and validate) IMAP credentials submitted from the web form."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)

    form = await request.form()
    provider    = (form.get("provider") or "gmail").strip()
    email_addr  = (form.get("email") or "").strip()
    app_password = (form.get("app_password") or "").strip()

    preset      = _MAIL_PROVIDERS.get(provider, _MAIL_PROVIDERS["custom"])
    if provider == "custom":
        imap_host   = (form.get("imap_host") or "").strip()
        imap_port   = int(form.get("imap_port") or 993)
        spam_folder = (form.get("spam_folder") or "Spam").strip() or None
    else:
        imap_host   = preset["imap_host"]
        imap_port   = preset["imap_port"]
        spam_folder = preset["spam_folder"]

    uid = user["sub"]
    # Block IMAP form submission for Gmail — should use OAuth2 flow instead
    if provider == "gmail":
        return RedirectResponse("/mail/oauth/google/start", status_code=302)
    # If password is blank, reuse the existing stored password (edit flow)
    if not app_password:
        existing = _load_mail_creds_for_user(uid)
        if existing and existing.get("app_password"):
            app_password = existing["app_password"]

    if not email_addr or not app_password:
        return RedirectResponse("/mail?show_settings=1&error=Email+and+app+password+are+required.", status_code=302)
    if provider == "custom" and not imap_host:
        return RedirectResponse("/mail?show_settings=1&error=IMAP+host+is+required+for+custom+provider.", status_code=302)

    # Test IMAP connection before saving
    def _imap_err_str(exc: Exception) -> str:
        """Return a clean human-readable string from an imaplib exception.
        imaplib wraps server responses as bytes — strip the b'...' repr."""
        raw = exc.args[0] if exc.args else str(exc)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        else:
            raw = str(raw)
        # Strip leading b' and trailing ' artefacts from Python repr
        raw = raw.strip().lstrip("b'\"").rstrip("'\"")
        # Friendly message for app-password requirement
        if "application-specific password" in raw.lower() or "app password" in raw.lower():
            return ("Gmail requires an App Password, not your regular password. "
                    "Go to myaccount.google.com → Security → 2-Step Verification → App Passwords.")
        return raw[:160]

    try:
        with imaplib.IMAP4_SSL(imap_host, imap_port) as conn:
            conn.login(email_addr, app_password)
    except imaplib.IMAP4.error as e:
        err = _imap_err_str(e).replace(" ", "+").replace("&", "and")
        return RedirectResponse(f"/mail?show_settings=1&error={err}", status_code=302)
    except Exception as e:
        err = _imap_err_str(e).replace(" ", "+").replace("&", "and")
        return RedirectResponse(f"/mail?show_settings=1&error=Connection+failed:+{err}", status_code=302)

    mail_dir = Path(_TARIS_DIR) / "mail_creds"
    mail_dir.mkdir(parents=True, exist_ok=True)
    creds_data = {
        "provider": provider, "email": email_addr, "app_password": app_password,
        "imap_host": imap_host, "imap_port": imap_port, "spam_folder": spam_folder,
    }
    creds_file = mail_dir / f"{uid}.json"
    creds_file.write_text(json.dumps(creds_data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(creds_file, 0o600)
    except Exception:
        pass
    if _STORE_OK:
        try:
            _store.save_mail_creds(uid, creds_data)
        except Exception as _e:
            log.warning("[Mail/Web] _store.save_mail_creds failed: %s", _e)

    log.info(f"[Mail] Web user {uid} saved IMAP creds (provider={provider}, email={email_addr})")
    return RedirectResponse("/mail", status_code=302)


@app.post("/mail/settings/delete")
async def mail_settings_delete(request: Request):
    """Delete stored IMAP credentials for the current web user."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)
    uid = user["sub"]
    mail_dir = Path(_TARIS_DIR) / "mail_creds"
    for fname in (f"{uid}.json", f"{uid}_last_digest.txt"):
        f = mail_dir / fname
        if f.exists():
            f.unlink(missing_ok=True)
    log.info(f"[Mail] Web user {uid} deleted IMAP creds")
    return RedirectResponse("/mail", status_code=302)


@app.post("/mail/refresh")
async def mail_refresh(request: Request):
    """Fetch fresh IMAP digest for this user and reload the page."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)
    uid = user["sub"]

    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _do_imap_fetch_and_save, uid)
    return RedirectResponse("/mail", status_code=302)


def _do_imap_fetch_and_save(uid: str) -> str:
    """Fetch recent emails via IMAP and save digest. Returns digest text."""
    creds = _load_mail_creds_for_user(uid)
    if not creds:
        return ""

    imap_host = creds.get("imap_host", "")
    imap_port = int(creds.get("imap_port", 993))
    user_email = creds.get("email", "")
    password = creds.get("app_password", "")
    spam_folder = creds.get("spam_folder")

    if not all([imap_host, user_email, password]):
        return ""

    all_msgs: list[dict] = []
    since_str = (datetime.now().replace(hour=0, minute=0, second=0)
                 .strftime("%d-%b-%Y"))  # today

    def _decode_hdr(h: str) -> str:
        parts = _email_header_mod.decode_header(h or "")
        out = []
        for raw, enc in parts:
            if isinstance(raw, bytes):
                out.append(raw.decode(enc or "utf-8", errors="replace"))
            else:
                out.append(str(raw))
        return "".join(out)

    def _fetch_folder(M: imaplib.IMAP4_SSL, folder: str, max_msgs: int = 25):
        try:
            status, _ = M.select(f'"{folder}"', readonly=True)
            if status != "OK":
                # Try without quotes
                status, _ = M.select(folder, readonly=True)
                if status != "OK":
                    return
            _, nums = M.search(None, f'SINCE "{since_str}"')
            ids = nums[0].split() if nums and nums[0] else []
            for num in ids[-max_msgs:]:
                try:
                    _, data = M.fetch(num, "(RFC822.HEADER)")
                    if not data or not data[0]:
                        continue
                    msg = _email_mod.message_from_bytes(data[0][1])
                    subj = _decode_hdr(msg.get("Subject", "(no subject)"))
                    sender = _decode_hdr(msg.get("From", ""))
                    date = msg.get("Date", "")[:16]
                    all_msgs.append({"subject": subj, "from": sender,
                                     "date": date, "folder": folder})
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"[MailFetch] folder {folder}: {e}")

    auth_type = creds.get("auth_type", "password")
    try:
        M = imaplib.IMAP4_SSL(imap_host, imap_port)
        if auth_type == "oauth2":
            gc = _get_google_creds_obj(creds)
            if not gc:
                log.error(f"[MailFetch] {uid}: OAuth2 token unavailable")
                return ""
            # Persist refreshed token back to disk
            if creds.get("access_token") != gc.token:
                creds["access_token"] = gc.token
                if gc.expiry:
                    creds["token_expiry"] = gc.expiry.isoformat()
                _mail_creds_path(uid).write_text(
                    json.dumps(creds, ensure_ascii=False, indent=2), encoding="utf-8")
                if _STORE_OK:
                    try:
                        _store.save_mail_creds(uid, creds)
                    except Exception as _e:
                        log.warning("[Mail/Web] _store.save_mail_creds (refresh) failed: %s", _e)
            xoauth2 = base64.b64encode(
                f"user={user_email}\x01auth=Bearer {gc.token}\x01\x01".encode()
            ).decode()
            M.authenticate("XOAUTH2", lambda _: xoauth2)
        else:
            M.login(user_email, password)
        _fetch_folder(M, "INBOX", 30)
        if spam_folder:
            _fetch_folder(M, spam_folder, 10)
        M.logout()
    except Exception as e:
        log.error(f"[MailFetch] {uid}: {e}")
        return ""

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not all_msgs:
        digest = f"💭 No new emails today.\n(Checked at {ts})"
    else:
        lines = [f"📧 Mail digest \u2014 {ts} ({len(all_msgs)} messages)\n"]
        for m in all_msgs:
            lines.append(f"\u2022 {m['subject']}\n  From: {m['from']}\n  {m['date']}")
        digest = "\n\n".join(lines)

        if len(all_msgs) > 5:
            try:
                summary_prompt = (
                    f"Summarize these {len(all_msgs)} emails in 3-5 bullet points. "
                    f"Reply in the same language as the email subjects:\n\n"
                    + "\n".join(f"- {m['subject']} from {m['from']}" for m in all_msgs)
                )
                summary = ask_llm(summary_prompt, timeout=60)
                if summary:
                    digest = (f"📧 Mail digest \u2014 {ts}\n\n**Summary:**\n{summary}"
                              f"\n\n---\n\n" + "\n\n".join(
                                  f"\u2022 {m['subject']} \u2014 {m['from']}"
                                  for m in all_msgs))
            except Exception:
                pass

    digest_file = _mail_creds_path(uid).parent / f"{uid}_last_digest.txt"
    digest_file.parent.mkdir(parents=True, exist_ok=True)
    digest_file.write_text(digest, encoding="utf-8")
    return digest


# ─────────────────────────────────────────────────────────────────────────────
# Voice
# ─────────────────────────────────────────────────────────────────────────────

_vosk_model_web: object = None   # singleton — loaded on first voice request


def _get_vosk_model_web():
    """Return cached Vosk model (loads once per process, avoids 5-10 s reload per call)."""
    global _vosk_model_web
    if _vosk_model_web is None:
        import vosk as _vosk_lib
        vosk_dir = str(Path(_TARIS_DIR) / "vosk-model-small-ru")
        if not Path(vosk_dir).is_dir():
            raise HTTPException(503, "Vosk model not installed")
        _vosk_model_web = _vosk_lib.Model(vosk_dir)
    return _vosk_model_web


def _voice_pipeline_status() -> list[dict]:
    """Check real filesystem to report component readiness."""
    d = Path(_TARIS_DIR)
    ffmpeg_ok = Path("/usr/bin/ffmpeg").exists()
    vosk_ok = (d / "vosk-model-small-ru").is_dir()
    taris_ok = Path(TARIS_BIN).exists()
    piper_bin_ok = Path("/usr/local/bin/piper").exists()
    piper_med = (d / "ru_RU-irina-medium.onnx").exists()
    piper_low = (d / "ru_RU-irina-low.onnx").exists()
    active_model = get_active_model() or "default"
    return [
        {
            "icon": "🎵", "name": "Audio (ffmpeg)",
            "status": "ready" if ffmpeg_ok else "missing",
            "detail": "OGG ↔ PCM conversion",
        },
        {
            "icon": "🎤", "name": "STT (Vosk)",
            "status": "ready" if vosk_ok else "missing",
            "detail": "vosk-model-small-ru" if vosk_ok else "Model not found",
        },
        {
            "icon": "🤖", "name": f"LLM ({active_model})",
            "status": "ready" if taris_ok else "missing",
            "detail": TARIS_BIN,
        },
        {
            "icon": "🔊", "name": "TTS (Piper)",
            "status": "ready" if (piper_bin_ok and (piper_med or piper_low))
                       else "partial" if piper_bin_ok else "missing",
            "detail": "irina-low" if piper_low else ("irina-medium" if piper_med else "no model"),
        },
    ]


@app.get("/voice", response_class=HTMLResponse)
async def voice_page(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    d = Path(_TARIS_DIR)

    # Read last transcript saved by telegram bot or web STT
    last_t_file = d / "last_transcript.txt"
    transcript = ""
    if last_t_file.exists():
        try:
            transcript = last_t_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    return templates.TemplateResponse("voice.html", _ctx(
        request, user, "voice",
        pipeline=_voice_pipeline_status(),
        transcript=transcript,
        languages=[
            {
                "code": "ru", "flag": "🇷🇺", "name": "Russian",
                "status": "ready" if (d / "vosk-model-small-ru").is_dir() else "missing",
            },
            {
                "code": "de", "flag": "🇩🇪", "name": "German",
                "status": "ready" if (d / "vosk-model-small-de").is_dir() else "optional",
            },
            {
                "code": "en", "flag": "🇬🇧", "name": "English",
                "status": "fallback",
            },
        ],
        waveform=_waveform(50, seed=7),
    ))


@app.get("/voice/last-transcript", response_class=HTMLResponse)
async def voice_last_transcript(request: Request):
    """HTMX partial — returns current transcript snippet."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)
    last_t_file = Path(_TARIS_DIR) / "last_transcript.txt"
    transcript = ""
    if last_t_file.exists():
        try:
            transcript = last_t_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    if transcript:
        return HTMLResponse(f'<p class="text-white">{html.escape(transcript)}</p>')
    return HTMLResponse('<p class="text-muted">No voice transcript yet.</p>')


@app.post("/voice/tts")
async def voice_tts_endpoint(request: Request, text: str = Form(...)):
    """Synthesise text with Piper TTS → return OGG Opus audio."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)

    text = text.strip()[:600]
    if not text:
        raise HTTPException(400, "No text")

    # Strip markdown / emoji for clean TTS input
    text = re.sub(r"[*_`#~]", "", text)
    text = re.sub(r"\[([^\]]*?)\]\([^)]*?\)", r"\1", text)  # [link](url)
    text = text.strip()
    if not text:
        raise HTTPException(400, "Text is empty after stripping")

    piper_bin = "/usr/local/bin/piper"
    if not Path(piper_bin).exists():
        raise HTTPException(503, "Piper TTS not installed")

    d = Path(_TARIS_DIR)
    tmpfs_model = Path("/dev/shm/piper/ru_RU-irina-medium.onnx")
    low_model   = d / "ru_RU-irina-low.onnx"
    med_model   = d / "ru_RU-irina-medium.onnx"
    if tmpfs_model.exists():
        model_path = str(tmpfs_model)
    elif low_model.exists():
        model_path = str(low_model)
    elif med_model.exists():
        model_path = str(med_model)
    else:
        raise HTTPException(503, "No Piper TTS voice model found")

    try:
        piper_result = subprocess.run(
            [piper_bin, "--model", model_path, "--output-raw"],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=120,
        )
        raw_pcm = piper_result.stdout
        if not raw_pcm:
            raise ValueError(f"Piper returned no output (rc={piper_result.returncode})")

        ff_result = subprocess.run(
            ["ffmpeg", "-y",
             "-f", "s16le", "-ar", "22050", "-ac", "1", "-i", "pipe:0",
             "-c:a", "libopus", "-b:a", "24k", "-f", "ogg", "pipe:1"],
            input=raw_pcm, capture_output=True, timeout=30,
        )
        ogg_bytes = ff_result.stdout
        if not ogg_bytes:
            raise ValueError(f"ffmpeg returned no output (rc={ff_result.returncode})")

        return Response(content=ogg_bytes, media_type="audio/ogg")

    except subprocess.TimeoutExpired:
        raise HTTPException(504, "TTS synthesis timed out")
    except Exception as e:
        log.warning(f"[Web/TTS] {e}")
        raise HTTPException(500, str(e))


@app.post("/voice/transcribe")
async def voice_transcribe_endpoint(request: Request, audio: UploadFile = File(...)):
    """Accept browser audio upload → Vosk STT → return transcript JSON."""
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)

    audio_data = await audio.read()
    if not audio_data:
        raise HTTPException(400, "Empty audio")

    tmp_in_path = None
    try:
        # Save uploaded audio to temp file
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
            tmp_in.write(audio_data)
            tmp_in_path = tmp_in.name

        # ffmpeg: WebM/OGG → 16 kHz mono S16LE PCM
        ff = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_in_path,
             "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"],
            capture_output=True, timeout=30,
        )
        raw_pcm = ff.stdout
        if not raw_pcm:
            raise ValueError(f"ffmpeg decode failed (rc={ff.returncode}): {ff.stderr[:200]}")

        duration_s = round(len(raw_pcm) / (16000 * 2), 1)

        # Vosk STT
        vosk_dir = str(Path(_TARIS_DIR) / "vosk-model-small-ru")
        if not Path(vosk_dir).is_dir():
            raise HTTPException(503, "Vosk model not installed")

        import vosk as _vosk_lib
        import json as _vj
        model = _vosk_lib.Model(vosk_dir)
        rec = _vosk_lib.KaldiRecognizer(model, 16000)
        rec.SetWords(True)

        CHUNK = 4000 * 2  # 4000 frames × 2 bytes
        for i in range(0, len(raw_pcm), CHUNK):
            rec.AcceptWaveform(raw_pcm[i:i + CHUNK])
        result = _vj.loads(rec.FinalResult())

        transcript = result.get("text", "").strip()
        # Strip low-confidence markers  [?word] → word
        transcript = re.sub(r"\[\?([^\]]+)\]", r"\1", transcript)

        # Save as last transcript
        last_t_file = Path(_TARIS_DIR) / "last_transcript.txt"
        ts_now = datetime.now().strftime("%Y-%m-%d %H:%M")
        last_t_file.write_text(f"[web] {ts_now}  {transcript}", encoding="utf-8")

        return {"transcript": transcript, "duration": duration_s}

    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"[Web/STT] {e}")
        raise HTTPException(500, str(e))
    finally:
        if tmp_in_path:
            try:
                os.unlink(tmp_in_path)
            except Exception:
                pass


@app.post("/voice/chat")
async def voice_chat_endpoint(request: Request, audio: UploadFile = File(...)):
    """Full voice conversation pipeline: browser audio → Vosk STT → LLM → Piper TTS.

    Returns JSON: {user_text, reply_text, audio_b64}
    Mirrors the Telegram bot's _handle_voice_message() flow.
    """
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)

    audio_data = await audio.read()
    if not audio_data:
        raise HTTPException(400, "Empty audio")

    tmp_in_path = None
    try:
        # ── Stage 1: decode browser audio → 16 kHz mono PCM ───────────────────
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
            tmp_in.write(audio_data)
            tmp_in_path = tmp_in.name

        ff = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_in_path,
             "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"],
            capture_output=True, timeout=30,
        )
        raw_pcm = ff.stdout
        if not raw_pcm:
            raise ValueError(f"ffmpeg decode failed (rc={ff.returncode}): {ff.stderr[:200]}")

        # ── Stage 2: Vosk STT ──────────────────────────────────────────────────
        import vosk as _vosk_lib
        import json as _vj
        vosk_model = _get_vosk_model_web()
        rec = _vosk_lib.KaldiRecognizer(vosk_model, 16000)
        rec.SetWords(True)
        CHUNK = 4000 * 2
        for i in range(0, len(raw_pcm), CHUNK):
            rec.AcceptWaveform(raw_pcm[i:i + CHUNK])
        stt_result = _vj.loads(rec.FinalResult())
        user_text = stt_result.get("text", "").strip()
        user_text = re.sub(r"\[\?([^\]]+)\]", r"\1", user_text)  # strip low-conf markers

        if not user_text:
            return {"user_text": "", "reply_text": "", "audio_b64": "", "error": "no_speech"}

        # Save for the last-transcript panel
        ts_now = datetime.now().strftime("%Y-%m-%d %H:%M")
        (Path(_TARIS_DIR) / "last_transcript.txt").write_text(
            f"[web] {ts_now}  {user_text}", encoding="utf-8"
        )

        # ── Stage 3: LLM ───────────────────────────────────────────────────────
        reply_text = ask_llm(user_text, timeout=90)
        if not reply_text:
            reply_text = "No response from LLM."

        # ── Stage 4: Piper TTS ─────────────────────────────────────────────────
        audio_b64 = ""
        tts_text = re.sub(r"[*_`#~]", "", reply_text)
        tts_text = re.sub(r"\[([^\]]*?)\]\([^)]*?\)", r"\1", tts_text)
        tts_text = tts_text.strip()[:600]

        if tts_text:
            d = Path(_TARIS_DIR)
            tmpfs_m   = Path("/dev/shm/piper/ru_RU-irina-medium.onnx")
            low_m     = d / "ru_RU-irina-low.onnx"
            med_m     = d / "ru_RU-irina-medium.onnx"
            piper_bin = "/usr/local/bin/piper"
            model_path = (
                str(tmpfs_m) if tmpfs_m.exists() else
                str(low_m)   if low_m.exists()   else
                str(med_m)   if med_m.exists()   else None
            )
            if model_path and Path(piper_bin).exists():
                try:
                    pr = subprocess.run(
                        [piper_bin, "--model", model_path, "--output-raw"],
                        input=tts_text.encode("utf-8"),
                        capture_output=True, timeout=180,
                    )
                    if pr.stdout:
                        ff2 = subprocess.run(
                            ["ffmpeg", "-y",
                             "-f", "s16le", "-ar", "22050", "-ac", "1", "-i", "pipe:0",
                             "-c:a", "libopus", "-b:a", "24k", "-f", "ogg", "pipe:1"],
                            input=pr.stdout, capture_output=True, timeout=30,
                        )
                        if ff2.stdout:
                            audio_b64 = base64.b64encode(ff2.stdout).decode()
                except Exception as tts_err:
                    log.warning(f"[Web/VoiceChat TTS] {tts_err}")

        return {"user_text": user_text, "reply_text": reply_text, "audio_b64": audio_b64}

    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"[Web/VoiceChat] {e}")
        raise HTTPException(500, str(e))
    finally:
        if tmp_in_path:
            try:
                os.unlink(tmp_in_path)
            except Exception:
                pass


@app.post("/voice/chat_text")
async def voice_chat_text_endpoint(request: Request, message: str = Form(...)):
    """Text input in voice-chat page: skip STT, run LLM + Piper TTS.

    Returns JSON: {user_text, reply_text, audio_b64}  (same shape as /voice/chat)
    """
    user = _get_current_user(request)
    if not user:
        raise HTTPException(401)

    user_text = message.strip()
    if not user_text:
        raise HTTPException(400, "Empty message")

    reply_text = ask_llm(user_text, timeout=90)
    if not reply_text:
        reply_text = "No response from LLM."

    # ── Piper TTS ──────────────────────────────────────────────────────────────
    audio_b64 = ""
    tts_text = re.sub(r"[*_`#~]", "", reply_text)
    tts_text = re.sub(r"\[([^\]]*?)\]\([^)]*?\)", r"\1", tts_text)
    tts_text = tts_text.strip()[:600]

    if tts_text:
        d = Path(_TARIS_DIR)
        tmpfs_m   = Path("/dev/shm/piper/ru_RU-irina-medium.onnx")
        low_m     = d / "ru_RU-irina-low.onnx"
        med_m     = d / "ru_RU-irina-medium.onnx"
        piper_bin = "/usr/local/bin/piper"
        model_path = (
            str(tmpfs_m) if tmpfs_m.exists() else
            str(low_m)   if low_m.exists()   else
            str(med_m)   if med_m.exists()   else None
        )
        if model_path and Path(piper_bin).exists():
            try:
                pr = subprocess.run(
                    [piper_bin, "--model", model_path, "--output-raw"],
                    input=tts_text.encode("utf-8"),
                    capture_output=True, timeout=180,
                )
                if pr.stdout:
                    ff2 = subprocess.run(
                        ["ffmpeg", "-y",
                         "-f", "s16le", "-ar", "22050", "-ac", "1", "-i", "pipe:0",
                         "-c:a", "libopus", "-b:a", "24k", "-f", "ogg", "pipe:1"],
                        input=pr.stdout, capture_output=True, timeout=30,
                    )
                    if ff2.stdout:
                        audio_b64 = base64.b64encode(ff2.stdout).decode()
            except Exception as tts_err:
                log.warning(f"[Web/VoiceChatText TTS] {tts_err}")

    return {"user_text": user_text, "reply_text": reply_text, "audio_b64": audio_b64}


# ─────────────────────────────────────────────────────────────────────────────
# Admin panel
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.get("role") != "admin":
        raise HTTPException(403, detail="Admin only")

    accounts = list_accounts()
    admin_users = []
    for a in accounts:
        role = a.get("role", "user").capitalize()
        admin_users.append({
            "username":    a.get("username", "?"),
            "display_name": a.get("display_name", a.get("username", "?")),
            "user_id":     a.get("user_id", ""),
            "role":        role,
            "badge":       "purple" if role == "Admin" else "blue",
            "chat_id":     a.get("telegram_chat_id"),
            "created":     a.get("created", "—")[:10] if a.get("created") else "—",
            "status":      a.get("status", "active"),
        })

    models_raw = list_models()
    active_model = get_active_model()
    llm_models = []
    for m in models_raw:
        name = m.get("model_name", m.get("model", "?"))
        llm_models.append({
            "name": name,
            "provider": m.get("model", "").split("/")[0] if "/" in m.get("model", "") else "custom",
            "desc": m.get("model", ""),
            "active": name == active_model,
        })

    vopts = _load_voice_opts()
    voice_opts = []
    for key, label, desc, gain in _VOICE_OPT_META:
        voice_opts.append({
            "key":         key,
            "label":       label,
            "description": desc,          # template uses {{ opt.description }}
            "gain":        gain,
            "enabled":     vopts.get(key, False),  # template uses opt.enabled
        })

    system_status = _system_status()
    msg   = request.query_params.get("msg", "")
    error = request.query_params.get("error", "")

    try:
        release_notes = json.loads(Path(RELEASE_NOTES_FILE).read_text(encoding="utf-8"))
    except Exception:
        release_notes = []

    return templates.TemplateResponse("admin.html", _ctx(
        request, user, "admin",
        stats=system_status,
        users=admin_users,
        llm_models=llm_models,
        voice_opts=voice_opts,
        release_notes=release_notes,
        msg=msg,
        error=error,
    ))


@app.post("/admin/llm/{model_name}")
async def admin_set_llm(request: Request, model_name: str):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(403)
    set_active_model(model_name)
    return Response(headers={"HX-Redirect": "/admin"})


@app.post("/admin/voice-opt/{key}")
async def admin_toggle_voice_opt(request: Request, key: str):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(403)
    opts = _load_voice_opts()
    opts[key] = not opts.get(key, False)
    _save_voice_opts(opts)
    return Response(headers={"HX-Redirect": "/admin"})


@app.delete("/admin/user/{user_id}")
async def admin_delete_user(request: Request, user_id: str):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(403)
    # Remove from accounts
    from security.bot_auth import _load_accounts, _save_accounts
    accounts = _load_accounts()
    accounts = [a for a in accounts if a.get("user_id") != user_id]
    _save_accounts(accounts)
    return Response(headers={"HX-Redirect": "/admin"})


@app.post("/admin/user/{user_id}/approve")
async def admin_approve_user(request: Request, user_id: str):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(403)
    update_account(user_id, status="active")
    log.info(f"[Admin] User {user_id} approved by {user.get('username')}")
    return Response(headers={"HX-Redirect": "/admin"})


@app.post("/admin/user/{user_id}/block")
async def admin_block_user(request: Request, user_id: str):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(403)
    update_account(user_id, status="blocked")
    log.info(f"[Admin] User {user_id} blocked by {user.get('username')}")
    return Response(headers={"HX-Redirect": "/admin"})


@app.post("/admin/user/{user_id}/reset-password")
async def admin_reset_password(
    request: Request,
    user_id: str,
    new_password: str = Form(...),
):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(403)
    if len(new_password) < 4:
        return Response(headers={"HX-Redirect": "/admin?error=Password+must+be+at+least+4+characters"})
    ok = change_password(user_id, new_password)
    if not ok:
        return Response(headers={"HX-Redirect": "/admin?error=User+not+found"})
    account = find_account_by_id(user_id)
    uname = account.get("username", user_id) if account else user_id
    log.info(f"[Admin] Password reset for user '{uname}' by admin '{user.get('username')}'")
    return Response(headers={"HX-Redirect": f"/admin?msg=Password+reset+for+{uname}"})


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Screen DSL route
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/screen/{screen_id}")
async def dynamic_screen(request: Request, screen_id: str):
    user = _require_auth(request)
    account = find_account_by_id(user["sub"]) or {}
    lang = account.get("language", "en")
    role = user.get("role", "user")
    ctx = UserContext(user_id=user["sub"], chat_id=0, lang=lang, role=role)
    screen = load_screen(f"screens/{screen_id}.yaml", ctx, t_func=_web_t)
    return templates.TemplateResponse(
        "dynamic.html", _ctx(request, user, screen_id, screen=screen),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    ensure_admin_account()
    log.info(f"[Web] Taris Bot Web UI v{BOT_VERSION} starting")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    # Auto-detect self-signed TLS certificate (required for getUserMedia in browsers)
    _ssl_key  = BASE / "ssl" / "key.pem"
    _ssl_cert = BASE / "ssl" / "cert.pem"
    _ssl_kwargs: dict = {}
    if _ssl_key.exists() and _ssl_cert.exists():
        _ssl_kwargs = {"ssl_keyfile": str(_ssl_key), "ssl_certfile": str(_ssl_cert)}
        log.info("[Web] TLS enabled — serving on https://0.0.0.0:8080")
    else:
        log.warning("[Web] No SSL cert found in ssl/key.pem + ssl/cert.pem — "
                    "serving plain HTTP (mic API will not work in browsers)")
    uvicorn.run("bot_web:app", host="0.0.0.0", port=8080, reload=False, **_ssl_kwargs)
