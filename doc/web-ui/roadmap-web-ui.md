# PicoUI Platform — Implementation Roadmap

**Created:** March 2026  
**Updated:** March 2026 — multi-backend (PicoClaw / OpenClaw), multi-channel (Telegram + Web + messengers), CRM-ready; **Phases P0–P4 complete + Telegram↔Web account linking (Flow C), deployed to OpenClawPI2 (v2026.3.28)**  
**Primary framework:** FastAPI + Jinja2 + HTMX (as designed in `mockups-fastapi/`)  
**Future enhancement:** NiceGUI integration (nice-to-have, see §12)  
**LLM backends:** PicoClaw CLI (current), PicoClaw Gateway HTTP, OpenClaw Gateway WS — switchable via config  
**Rendering targets:** Telegram (existing), Web UI (FastAPI), additional messengers via renderer plugins  
**Key constraint:** Web authentication works WITHOUT Telegram — standalone login  
**Key constraint:** One user account works across both Telegram and Web  
**Long-term objective:** CRM platform core — reusable foundation for customer-specific CRM projects  
**References:** [concept-web-interface.md](concept-web-interface.md), [concept-vibe-coding-ui.md](concept-vibe-coding-ui.md), `mockups-fastapi/`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Authentication Architecture](#2-authentication-architecture)
3. [Unified User Identity Model](#3-unified-user-identity-model)
4. [P0 — Preparation: Extract UI Layer + LLM Backend Abstraction + Auth Foundation](#4-p0--preparation-extract-ui-layer--llm-backend-abstraction--auth-foundation)
5. [P1 — Web Core: FastAPI + Templates + Auth + Chat + Notes](#5-p1--web-core-fastapi--templates--auth--chat--notes)
6. [P2 — Calendar + Admin Dashboard](#6-p2--calendar--admin-dashboard)
7. [P3 — Voice: Browser Recording + Audio Playback](#7-p3--voice-browser-recording--audio-playback)
8. [P4 — Full Migration: All Screens Unified](#8-p4--full-migration-all-screens-unified)
9. [Multi-Channel Renderer Architecture](#9-multi-channel-renderer-architecture)
10. [Interactive Widget Patterns (NiceGUI-like in FastAPI)](#10-interactive-widget-patterns-nicegui-like-in-fastapi)
11. [File Structure](#11-file-structure)
12. [NiceGUI Integration — Future Enhancement](#12-nicegui-integration--future-enhancement)
13. [CRM Platform Vision](#13-crm-platform-vision)
14. [Deployment Architecture](#14-deployment-architecture)
15. [Risks & Mitigations](#15-risks--mitigations)
16. [Decision Log](#16-decision-log)

---

## 1. Executive Summary

### Problem

The Picoclaw bot currently exists only as a Telegram bot. All user identity is tied to Telegram `chat_id`. The LLM backend is hardcoded to PicoClaw CLI (`picoclaw agent -m`). To become a reusable platform — one that can render in Telegram, on the web, and eventually in other messengers, while connecting to different LLM backends — we need:

1. **Standalone web authentication** — users log in via username/password, no Telegram required.
2. **Unified identity** — a user who uses Telegram can also log into the web and see the same data (notes, calendar, mail config, preferences).
3. **Shared rendering** — one set of action handlers drives both Telegram and Web UI (and future messenger channels).
4. **Pluggable LLM backend** — switch between PicoClaw CLI, PicoClaw Gateway HTTP, OpenClaw Gateway WS, or direct OpenAI without changing business logic.
5. **CRM-ready core** — the current feature set (contacts, calendar, notes, mail, user roles) forms the foundation for customer-specific CRM projects.

### Solution — 5-Phase FastAPI-First Rollout

The existing `mockups-fastapi/` already demonstrates every screen (Dashboard, Chat, Notes, Calendar, Mail, Voice, Admin) with a polished dark theme, HTMX interactivity, and responsive CSS. We build directly on these mockups.

| Phase | Scope | Effort | Outcome | Status |
|---|---|---|---|---|
| **P0** | Extract `bot_ui.py` + `bot_actions.py` + `render_telegram.py` + `bot_llm.py`; `bot_auth.py`; migrate 3 screens internally | ~1 day | Telegram works via Screen objects; LLM backend abstracted; `accounts.json` identity store ready | ✅ Done |
| **P1** | FastAPI + Jinja2 templates + JWT auth + Dashboard + Chat + Notes | ~3–5 days | Web login, dashboard, real-time chat with LLM, notes with live Markdown editor | ✅ Done |
| **P2** | Calendar views + Mail digest + Admin dashboard | ~5–7 days | Month grid calendar, categorized mail digest, full admin panel with user/LLM/voice management | ✅ Done |
| **P3** | Browser voice recording via MediaRecorder, TTS audio playback, pipeline visualization | ~3–5 days | Voice orb recording, waveform display, STT/TTS in browser | ✅ Done |
| **P4** | All 19 Telegram keyboards → Screen objects; both channels unified; PWA | ~5–7 days | Single action layer drives Telegram + Web; no duplicated UI logic | ✅ Done |

**NiceGUI** is planned as a future nice-to-have enhancement (§12) — it can replace or complement the Jinja2 templates, reusing the same `bot_actions.py` backend.

### Architecture — Multi-Backend, Multi-Channel

```
   ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌────────────┐
   │ Telegram  │  │ Web (HTMX)│  │ WhatsApp* │  │ Discord*   │
   │ @smartpico│  │ :8080     │  │ (future)  │  │ (future)   │
   └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬──────┘
         │               │               │               │
   ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼──────┐
   │render_tg  │  │Jinja2 tmpl│  │render_wa* │  │render_dc*  │
   └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬──────┘
         │               │               │               │
         └───────────────┴───────┬───────┴───────────────┘
                                 │
                         ┌───────▼────────┐
                         │  bot_actions.py │  ← Screen DSL (one codebase)
                         │  (pure Python)  │
                         └───────┬────────┘
                                 │
             ┌───────────────────┼───────────────────┐
             │                   │                    │
     ┌───────▼──────┐   ┌───────▼──────┐   ┌────────▼────────┐
     │  bot_users   │   │bot_calendar  │   │ bot_mail_creds  │
     │  bot_access  │   │  bot_voice   │   │ bot_email       │
     └──────────────┘   └──────────────┘   └─────────────────┘
             │                   │                    │
     ┌───────▼──────────────────────────────────────────┐
     │                    bot_llm.py                     │
     │  Pluggable LLM: PicoClaw CLI | Gateway | OpenClaw│
     └──────────────────────────────────────────────────┘
```

`* = future renderers (see §9)`

### Architecture at a Glance

```
                    ┌──────────────┐     ┌─────────────────────┐
                    │  Telegram    │     │  Web Browser          │
                    │  @smartpico  │     │  FastAPI + HTMX       │
                    └──────┬───────┘     └───────┬──────────────┘
                           │                     │
                    ┌──────▼───────┐     ┌───────▼──────────────┐
                    │ render_tg.py │     │ Jinja2 templates      │
                    │              │     │ + HTMX partial renders│
                    └──────┬───────┘     └───────┬──────────────┘
                           │                     │
                           └──────────┬──────────┘
                                      │
                              ┌───────▼────────┐
                              │  bot_actions.py │  ← Screen DSL
                              │  (pure Python)  │
                              └───────┬────────┘
                                      │
                  ┌───────────────────┼───────────────────┐
                  │                   │                    │
          ┌───────▼──────┐   ┌───────▼──────┐   ┌────────▼────────┐
          │  bot_users.py │   │bot_calendar.py│   │ bot_mail_creds.py│
          │  bot_access.py│   │  bot_voice.py │   │ bot_email.py     │
          └──────────────┘   └──────────────┘   └──────────────────┘
                  │                   │                    │
          ┌───────▼─────────────────────────────────────────┐
          │                 bot_auth.py                      │
          │  Unified identity: accounts.json + JWT + bcrypt  │
          └─────────────────────────────────────────────────┘
```

### Why FastAPI-First (not NiceGUI-First)

| Criterion | FastAPI + Jinja2 + HTMX | NiceGUI |
|---|---|---|
| **Mockups exist** | ✅ All 8 screens designed and tested | ✅ All 8 screens designed |
| **Pi 3 RAM overhead** | ~20–30 MB (lightweight ASGI) | ~60–80 MB (Quasar JS, WebSocket per client) |
| **Widget-like interactivity** | HTMX + Alpine.js → sliding panels, toggles, live updates | Built-in Quasar components |
| **Custom CSS control** | Full control — 400-line `style.css` already polished | Quasar overrides needed |
| **Offline / CDN** | All assets can be self-hosted | Quasar CDN dependency (or bundle) |
| **Learning curve** | Standard web stack — HTML/CSS/JS | NiceGUI Python API (non-standard) |
| **Multi-channel rendering** | Screen DSL → any renderer (Telegram, Web, WhatsApp, …) | Locked to NiceGUI/Quasar (web only) |
| **CRM extensibility** | Jinja2 templates are standard — easy to customize per client | NiceGUI widgets are opinionated |
| **Future flexibility** | Can add any JS framework later (React, Vue, Svelte) | Locked into NiceGUI/Quasar |

---

## 2. Authentication Architecture

### 2.1 Design Principles

1. **Web-first auth** — username + password, no Telegram dependency.
2. **Telegram linking is optional** — an existing Telegram user can link their web account, or vice versa.
3. **Single identity store** — one `accounts.json` file maps user IDs to both Telegram and web credentials.
4. **Minimal dependencies** — bcrypt for password hashing, PyJWT for tokens. Both are pure Python.

### 2.2 Auth Flows

#### Flow A — Web Registration (new user, no Telegram)

```
User opens https://pi:8080/register
  → enters: username, display name, email, password
  → server: hash password (bcrypt), create account in accounts.json
  → account status: "email_pending"
  → server: generate one-time verification token (uuid4, 24h expiry)
  → server: send verification email via SMTP (reuses bot_email.py)
      Subject: "PicoUI — confirm your registration"
      Body: link https://pi:8080/verify?token=<token>
  → user clicks link → server verifies token + sets status: "pending"
  → admin notified (via Telegram and/or web admin panel)
  → admin approves → status: "approved"
  → user can log in
```

**Registration status lifecycle:**
```
email_pending  ──[email click]──▶  pending  ──[admin approves]──▶  approved
                                         └──[admin blocks]───▶  blocked
```

> **Why email first, then admin?** Email verification proves the user owns the address (prevents spam registrations with fake accounts). Admin approval provides the access control gate. Both steps are required — email alone does not grant access.

#### Flow A2 — Telegram Registration with Email Confirmation

```
Unknown user sends /start in Telegram
  → bot prompts: "Enter your name"
  → bot prompts: "Enter your email address"
  → server: create account with telegram_chat_id, status: "email_pending"
  → server: send verification email (same template as Flow A)
  → user clicks link → status: "pending"
  → admin notified with approve/block buttons
  → admin approves → status: "approved"
  → user receives welcome message + main menu
```

> **Existing Telegram registration** (current `/start` flow) is upgraded to include the email step. Users without email can still register — admin can approve without email verification if configured (`REQUIRE_EMAIL_VERIFICATION=false` in `bot.env`).

#### Flow B — Web Login (returning user)

```
User opens https://pi:8080/login
  → enters: username + password
  → server: verify bcrypt hash
  → success: issue JWT (stored in HTTP-only cookie, 24h expiry)
  → FastAPI dependency extracts user_id from cookie on each request
  → redirect to dashboard
```

#### Flow C — Telegram User Links Web Account ✅ Implemented (v2026.3.28)

```
Existing Telegram user taps "🔗 Link to Web" in Profile menu
  → bot dispatches "web_link" callback → _handle_web_link(chat_id)
  → bot generates a one-time 6-char alphanumeric code (uppercase), valid 15 minutes
      code stored in _web_link_codes dict: {code: {chat_id, expires_at}}
  → bot sends message with code, e.g.:
      "🔗 Web Account Link Code
       Your code: `ABC123`
       Valid for 15 minutes. Enter it on the registration page."
  → user opens https://agents.sintaris.net/picoassist2/register (PI2)
       or https://agents.sintaris.net/picoassist/register (PI1)
  → enters username + password + Telegram Link Code (optional field, auto-uppercased)
  → server: validates code via validate_web_link_code(code)
      → resolves telegram_chat_id
      → checks if chat_id is in ADMIN_USERS → sets role="admin" or role="user"
      → creates account with status="active" (no admin approval step for linked accounts)
      → code invalidated (single-use)
  → user now has both Telegram and Web access; profile shows linked Telegram identity
```

**Implementation notes vs original design:**
- Code format: **6 alphanumeric uppercase chars** (not 6-digit numeric)
- TTL: **15 minutes** (not 5 minutes)
- Entry point: **`/register` page optional field** (not a separate `/link` route)
- Status on success: **`active`** (not `approved`) — linked accounts bypass admin approval
- Role inheritance: Telegram ADMIN_USERS → web `admin` role automatically

**Files implementing Flow C:**
- `src/bot_state.py` — `generate_web_link_code()`, `validate_web_link_code()`, `_web_link_codes` dict, `WEB_LINK_CODE_TTL_MINUTES = 15`
- `src/bot_handlers.py` — `_handle_web_link(chat_id)`, Profile menu link button
- `src/telegram_menu_bot.py` — `web_link` callback dispatch
- `src/bot_web.py` — `register_submit()` accepts `link_code` Form field
- `src/templates/register.html` — optional Telegram Link Code input
- `src/strings.json` — `web_link_btn`, `web_link_code_msg` keys (ru/en/de)

#### Flow D — Web User Links Telegram 🔲 Planned

```
Web user opens Profile → "Link Telegram"
  → page shows: "Send /link to @smartpico_bot in Telegram"
  → user sends /link in Telegram
  → bot sends: "Enter your web username"
  → user types username
  → bot sends: "Enter your web password to confirm"
  → user types password → server verifies
  → link telegram_chat_id to existing account
```

### 2.3 JWT Token Design

| Field | Value |
|---|---|
| `sub` | `user_id` (UUID string) |
| `username` | Display username |
| `role` | `admin` / `user` / `guest` |
| `iat` | Issued-at timestamp |
| `exp` | Expiry: `iat + 24 hours` |

Token is stored in an HTTP-only, Secure, SameSite=Lax cookie named `pico_token`.

Secret key: generated once on first start, stored in `~/.picoclaw/web_secret.key` (32 random bytes, base64-encoded).

### 2.4 Session Management

FastAPI uses a JWT cookie for session state. A `get_current_user` dependency extracts and validates the token on every protected route:

```python
from fastapi import Depends, Request, HTTPException

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("pico_token")
    if not token:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    payload = _decode_jwt(token)
    return _find_account_by_id(payload["sub"])
```

Template context receives the user dict, enabling role-based rendering:

```python
@app.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})
```

### 2.5 Password Requirements

- Minimum 6 characters (this is a home Pi assistant, not a bank)
- Hashed with bcrypt (work factor 12)
- No password recovery (admin can reset via admin panel)

### 2.6 Email Verification

- **Required by default** for all new registrations (both Web and Telegram)
- Verification token: `uuid4`, stored in `accounts.json`, expires after 24 hours
- Email sent via `bot_email.py` (reuses existing SMTP infrastructure)
- Admin SMTP credentials (from `bot.env` or admin's mail creds) used as sender
- Configurable: `REQUIRE_EMAIL_VERIFICATION=true|false` in `bot.env` (default `true`)
- If disabled: registration skips email step, goes directly to `"pending"` (admin-only gate)
- Verification link format: `https://<host>:8080/verify?token=<uuid4>`
- On successful verification: token deleted, status changes `email_pending` → `pending`

---

## 3. Unified User Identity Model

### 3.1 Current State — Telegram-Coupled

Today, user identity is spread across multiple files keyed by `chat_id`:

| File | Key | Data |
|---|---|---|
| `bot.env` → `ALLOWED_USERS` | comma-separated chat_ids | Static allowed list |
| `bot.env` → `ADMIN_USERS` | comma-separated chat_ids | Static admin list |
| `users.json` | chat_id set | Dynamic approved guests |
| `registrations.json` | chat_id in each record | Registration status |
| `notes/<chat_id>/*.md` | directory name is chat_id | Notes |
| `calendar/<chat_id>.json` | file name is chat_id | Calendar events |
| `mail_creds/<chat_id>.json` | file name is chat_id | IMAP credentials |
| `voice_opts.json` | global (not per-user) | Voice flags |

**Problem:** A web-only user has no `chat_id`. We need a `user_id` that exists independently.

### 3.2 Target State — Unified Accounts

A single `~/.picoclaw/accounts.json` becomes the source of truth:

```json
{
  "accounts": [
    {
      "user_id": "u-a1b2c3d4",
      "username": "stas",
      "display_name": "Stas Ulmer",
      "email": "stas.ulmer@gmail.com",
      "email_verified": true,
      "password_hash": "$2b$12$...",
      "role": "admin",
      "status": "approved",
      "telegram_chat_id": 994963580,
      "lang": "ru",
      "created_at": "2026-03-01T12:00:00",
      "last_login_web": "2026-03-26T10:30:00",
      "last_login_tg": "2026-03-26T09:15:00"
    },
    {
      "user_id": "u-e5f6g7h8",
      "username": "maria",
      "display_name": "Maria",
      "email": "maria@example.de",
      "email_verified": true,
      "password_hash": "$2b$12$...",
      "role": "user",
      "status": "approved",
      "telegram_chat_id": null,
      "lang": "de",
      "created_at": "2026-03-20T14:00:00",
      "last_login_web": "2026-03-25T18:00:00",
      "last_login_tg": null
    }
  ]
}
```

### 3.3 User ID Format

`u-` prefix + 8 hex chars from `uuid4()`. Example: `u-a1b2c3d4`.

Short enough to use in file paths (`notes/u-a1b2c3d4/`) and JSON keys.

### 3.4 Identity Resolution

Every request (Telegram or Web) resolves to a `user_id` first:

```python
# Telegram handler
def resolve_tg_user(chat_id: int) -> Optional[str]:
    """Find account by telegram_chat_id → return user_id."""
    for acc in _load_accounts():
        if acc.get("telegram_chat_id") == chat_id:
            return acc["user_id"]
    return None

# Web handler  
def resolve_web_user(jwt_payload: dict) -> Optional[str]:
    """Extract user_id from JWT token."""
    return jwt_payload.get("sub")
```

All data modules (`bot_users`, `bot_calendar`, `bot_mail_creds`, etc.) accept `user_id` instead of `chat_id`.

### 3.5 Migration from chat_id to user_id

Existing users are migrated automatically:

1. On first bot start after upgrade, scan `registrations.json`.
2. For each registered `chat_id`, create an account in `accounts.json` with `user_id = "u-" + hex(chat_id)[:8]` (deterministic, reversible for debugging).
3. Rename data directories: `notes/994963580/` → `notes/u-3b4d91ac/` (or create symlinks for backward compat).
4. Keep `registrations.json` as read-only archive. New registrations go to `accounts.json`.

### 3.6 Backward Compatibility

During the migration period:

- `_is_allowed(chat_id)` still works — internally resolves `chat_id → user_id → role check`.
- `_is_admin(chat_id)` still works — same resolution.
- Data files accept both `chat_id` (legacy) and `user_id` (new) as directory/file names.
- Static `ALLOWED_USERS` and `ADMIN_USERS` in `bot.env` still respected — matched against `telegram_chat_id` field.

---

## 4. P0 — Preparation: Extract UI Layer + LLM Backend Abstraction + Auth Foundation

**Goal:** Extract the UI/action boundary from the Telegram bot; abstract the LLM backend into a pluggable module; introduce unified `accounts.json` and `bot_auth.py`. The Telegram bot works exactly as before — no user-visible changes.  
**Effort:** ~1 day

### 4.1 Create `src/bot_auth.py`

New module — root of auth logic, no Telegram imports.

```python
# bot_auth.py — Unified authentication & identity
#
# Dependency: bot_config only (root of tree)
# No imports from bot_instance, bot_access, or any Telegram modules.

import bcrypt, hashlib, json, os, secrets, time, uuid
from pathlib import Path
from typing import Optional
from bot_config import log

ACCOUNTS_FILE = os.path.expanduser("~/.picoclaw/accounts.json")
WEB_SECRET_FILE = os.path.expanduser("~/.picoclaw/web_secret.key")

def _gen_user_id() -> str: ...
def _load_accounts() -> list[dict]: ...
def _save_accounts(accounts: list[dict]) -> None: ...
def _find_account_by_tg(chat_id: int) -> Optional[dict]: ...
def _find_account_by_username(username: str) -> Optional[dict]: ...
def _find_account_by_id(user_id: str) -> Optional[dict]: ...
def _create_account(username, display_name, password, role, tg_chat_id=None) -> dict: ...
def _verify_password(account: dict, password: str) -> bool: ...
def _set_password(account: dict, password: str) -> None: ...
def _link_telegram(user_id: str, chat_id: int) -> bool: ...
def _generate_link_code(user_id: str) -> str: ...
def _verify_link_code(code: str) -> Optional[str]: ...
def _resolve_user(*, chat_id=None, user_id=None) -> Optional[dict]: ...
```

### 4.2 Create `src/bot_llm.py` — Pluggable LLM Backend

New module — abstracts the LLM call away from PicoClaw CLI. All business logic calls `ask_llm()` instead of `_ask_picoclaw()`.

**Current state:** `_ask_picoclaw()` in `bot_access.py` is the only function that calls the LLM — via subprocess to `/usr/bin/picoclaw agent -m "..."`. All other modules are already LLM-agnostic.

```python
# bot_llm.py — Pluggable LLM backend abstraction
#
# Dependency: bot_config only (root of tree)
# No imports from bot_instance, bot_access, or Telegram modules.

import os, subprocess, requests, json
from typing import Optional
from bot_config import log, PICOCLAW_BIN, PICOCLAW_CONFIG

# ── Backend selection ────────────────────────────────────

LLM_BACKEND = os.environ.get("LLM_BACKEND", "picoclaw_cli")
# Supported values:
#   "picoclaw_cli"     — subprocess: picoclaw agent -m  (default, current behaviour)
#   "picoclaw_gateway" — HTTP POST to PicoClaw Gateway (port 18790)
#   "openclaw_gateway" — HTTP POST to OpenClaw Gateway (port 18789)
#   "openai_direct"    — Direct OpenAI-compatible API call

PICOCLAW_GATEWAY_URL = os.environ.get(
    "PICOCLAW_GATEWAY_URL", "http://127.0.0.1:18790/v1/chat/completions")
OPENCLAW_GATEWAY_URL = os.environ.get(
    "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789/v1/chat/completions")
OPENAI_API_URL = os.environ.get(
    "OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")

LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "60"))

# ── Public interface ─────────────────────────────────────

def ask_llm(prompt: str, timeout: int = None) -> str:
    """Send prompt to configured LLM backend, return response text.

    This is the SINGLE function all modules call for LLM interaction.
    Backend selection is controlled by LLM_BACKEND env var.
    """
    t = timeout or LLM_TIMEOUT
    backend = LLM_BACKEND.lower().strip()

    if backend == "picoclaw_cli":
        return _ask_picoclaw_cli(prompt, t)
    elif backend == "picoclaw_gateway":
        return _ask_gateway(PICOCLAW_GATEWAY_URL, prompt, t)
    elif backend == "openclaw_gateway":
        return _ask_gateway(OPENCLAW_GATEWAY_URL, prompt, t)
    elif backend == "openai_direct":
        return _ask_openai_direct(prompt, t)
    else:
        log.error(f"[LLM] Unknown backend: {backend}")
        return f"❌ Unknown LLM backend: {backend}"

# ── Backend implementations ──────────────────────────────

def _ask_picoclaw_cli(prompt: str, timeout: int) -> str:
    """Subprocess: picoclaw agent -m '...' (current default)."""
    try:
        r = subprocess.run(
            [PICOCLAW_BIN, "agent", "-m", prompt],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "NO_COLOR": "1"},
        )
        return _clean_output(r.stdout) if r.returncode == 0 else f"⚠️ exit {r.returncode}"
    except subprocess.TimeoutExpired:
        return "⚠️ LLM timeout"
    except Exception as e:
        log.error(f"[LLM] picoclaw_cli error: {e}")
        return f"❌ {e}"

def _ask_gateway(url: str, prompt: str, timeout: int) -> str:
    """HTTP POST to PicoClaw or OpenClaw gateway (both use OpenAI-compatible API)."""
    try:
        resp = requests.post(url, json={
            "model": _get_active_model() or "default",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        }, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.error(f"[LLM] gateway error ({url}): {e}")
        return f"❌ {e}"

def _ask_openai_direct(prompt: str, timeout: int) -> str:
    """Direct OpenAI-compatible API call (no picoclaw/openclaw binary needed)."""
    api_key = os.environ.get("OPENAI_API_KEY") or _get_shared_openai_key()
    if not api_key:
        return "❌ No OPENAI_API_KEY configured"
    try:
        resp = requests.post(OPENAI_API_URL, json={
            "model": _get_active_model() or "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        }, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.error(f"[LLM] openai_direct error: {e}")
        return f"❌ {e}"

# ── Helpers (moved from bot_access.py) ───────────────────

def _clean_output(text: str) -> str:
    """Strip ANSI / spinner artefacts from CLI output."""
    # Same logic as current _clean_picoclaw_output()
    ...

def _get_active_model() -> Optional[str]:
    """Read active model name from active_model.txt / config.json."""
    ...

def _get_shared_openai_key() -> Optional[str]:
    """Read first OpenAI API key from config.json."""
    ...
```

**Migration path:** In `bot_access.py`, replace `_ask_picoclaw()` with a thin wrapper:

```python
# bot_access.py — after migration
from bot_llm import ask_llm

def _ask_picoclaw(prompt, timeout=60):
    """Backward-compatible wrapper — delegates to bot_llm."""
    return ask_llm(prompt, timeout)
```

All existing callers (`_handle_chat_message`, `_handle_voice_message`, `_finish_cal_add`, etc.) continue to work unchanged. Gradually replace `_ask_picoclaw()` calls with `ask_llm()` in subsequent phases.

### 4.3 Migrate Existing Users

Write a one-time migration function `_migrate_from_legacy()`:

1. Read `registrations.json` — create account for each approved/pending user.
2. Read `ALLOWED_USERS` and `ADMIN_USERS` from `bot.env` — ensure accounts exist with correct roles.
3. Read `users.json` (dynamic guests) — create accounts.
4. For each account, rename data directories (`notes/<chat_id>/` → `notes/<user_id>/`).
5. Write `accounts.json`.
6. Write `~/.picoclaw/.migration_done` marker to prevent re-running.

### 4.4 Add to Dependency Chain

```
bot_config → bot_llm → bot_auth → bot_state → bot_instance → ...
```

`bot_llm.py` imports only from `bot_config`. `bot_auth.py` imports only from `bot_config`. All other modules can import from both.

### 4.5 Extract `src/bot_ui.py` — Screen DSL

17 widget dataclasses + `Screen` + `UserContext`:

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class UserContext:
    user_id: str
    chat_id: int | None    # None for web-only users
    lang: str
    role: str               # "admin" | "user" | "guest"

@dataclass
class Button:
    label: str
    action: str             # callback data key / route path
    style: str = "primary"  # primary | secondary | danger

@dataclass
class ButtonRow:
    buttons: list[Button]

@dataclass
class Card:
    title: str
    body: str = ""
    action: str = ""        # tap → navigate

@dataclass
class TextInput:
    placeholder: str
    action: str             # on_submit route

@dataclass
class Toggle:
    label: str
    key: str
    value: bool

@dataclass
class AudioPlayer:
    src: str                # URL or file ref
    caption: str = ""

@dataclass
class MarkdownBlock:
    text: str

@dataclass
class Spinner:
    label: str = ""

@dataclass
class Confirm:
    text: str
    action_yes: str
    action_no: str

@dataclass
class Redirect:
    target: str

@dataclass
class Screen:
    title: str
    widgets: list = field(default_factory=list)
    parse_mode: str = "Markdown"
```

### 4.6 Extract `src/bot_actions.py` — 3 Proof-of-Concept Screens

```python
def action_menu(user: UserContext) -> Screen: ...
def action_note_list(user: UserContext) -> Screen: ...
def action_note_view(user: UserContext, slug: str) -> Screen: ...
```

Each returns a `Screen` object with the appropriate widgets.

### 4.7 Create `src/render_telegram.py`

```python
def render(screen: Screen, chat_id: int, bot) -> None:
    """Translate a Screen to Telegram API calls."""
    # Convert ButtonRow → InlineKeyboardMarkup
    # Convert Card → text block
    # Convert TextInput → ForceReply
    # Convert AudioPlayer → bot.send_voice()
```

Wire 3 screens in `bot_handlers.py`:
- Old: `_handle_notes_menu()` builds keyboard directly.
- New: `_handle_notes_menu()` calls `render(action_note_list(user), chat_id, bot)`.

### 4.8 Update Data Modules — Accept `user_id`

Modify file path functions:

| Module | Function | Change |
|---|---|---|
| `bot_users.py` | `_notes_user_dir(chat_id)` | Accept `user_id` string; fall back to `chat_id` if int |
| `bot_calendar.py` | `_cal_user_file(chat_id)` | Same |
| `bot_mail_creds.py` | `_creds_path(chat_id)` | Same |

Pattern:
```python
def _notes_user_dir(user_ref) -> Path:
    """Accept user_id (str: 'u-...') or legacy chat_id (int)."""
    if isinstance(user_ref, str) and user_ref.startswith("u-"):
        key = user_ref
    else:
        key = str(user_ref)
    d = Path(NOTES_DIR) / key
    d.mkdir(parents=True, exist_ok=True)
    return d
```

### 4.9 Deliverables

**Status: ✅ Deployed (v2026.3.28)**

| # | File | Status |
|---|---|---|
| 1 | `src/bot_auth.py` | ✅ New — unified identity + auth |
| 2 | `src/bot_llm.py` | ✅ New — pluggable LLM backend (PicoClaw/OpenClaw/OpenAI) |
| 3 | `src/bot_ui.py` | ✅ New — Screen DSL widget dataclasses |
| 4 | `src/bot_actions.py` | ✅ New — 3 proof-of-concept screen handlers |
| 5 | `src/render_telegram.py` | ✅ New — Screen → Telegram API |
| 6 | `src/bot_config.py` | ✅ Modified — add `ACCOUNTS_FILE`, `WEB_SECRET_FILE`, `LLM_BACKEND` |
| 7 | `src/bot_access.py` | ✅ Modified — `_ask_picoclaw()` delegates to `bot_llm.ask_llm()` |
| 8 | `src/bot_users.py` | ✅ Modified — accept `user_id` |
| 9 | `src/bot_calendar.py` | ✅ Modified — accept `user_id` |
| 10 | `src/bot_mail_creds.py` | ✅ Modified — accept `user_id` |

### 4.10 Verification

- Telegram bot starts and works identically.
- `accounts.json` is created with all existing users.
- Notes menu, note list, note view render via Screen objects.
- All voice regression tests pass.

---

## 5. P1 — Web Core: FastAPI + Templates + Auth + Chat + Notes

**Goal:** A running web server with login/register, dashboard, real-time chat with LLM, and full notes manager. Based directly on the `mockups-fastapi/` templates.  
**Effort:** ~3–5 days  
**Dependencies:** P0 complete

### 5.1 Create `src/bot_web.py` — FastAPI Application

```python
from fastapi import FastAPI, Request, Depends, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from bot_auth import (
    _find_account_by_username, _verify_password, _create_account,
    _find_account_by_id, _issue_jwt, _decode_jwt,
)

app = FastAPI(title="PicoUI")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

WEB_PORT = 8080
WEB_HOST = "0.0.0.0"

# ── Auth dependency ─────────────────────────────────────────

async def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get("pico_token")
    if not token:
        return None
    try:
        payload = _decode_jwt(token)
        return _find_account_by_id(payload["sub"])
    except Exception:
        return None

def require_auth(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user

# ── Login / Register ────────────────────────────────────────

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_submit(request: Request, username: str = Form(), password: str = Form()):
    acc = _find_account_by_username(username)
    if not acc or not _verify_password(acc, password):
        return templates.TemplateResponse("login.html",
            {"request": request, "error": "Invalid credentials"})
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("pico_token", _issue_jwt(acc), httponly=True, samesite="lax")
    return resp

@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register_submit(request: Request, ...):
    # Validate, create account (status="pending"), redirect to login

# ── Dashboard (from mockups-fastapi/templates/dashboard.html) ──

@app.get("/")
async def dashboard(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("dashboard.html",
        {"request": request, "user": user, "stats": _gather_stats(user)})

# ── Chat (HTMX-powered) ─────────────────────────────────────

@app.get("/chat")
async def chat_page(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("chat.html", {"request": request, "user": user})

@app.post("/api/chat/send")
async def chat_send(request: Request, user=Depends(require_auth)):
    data = await request.json()
    reply = _ask_picoclaw(data["message"])
    return HTMLResponse(f'<div class="msg bot">{reply}</div>')  # HTMX swap

# ── Notes (HTMX partial renders) ──────────────────────────────

@app.get("/notes")
async def notes_page(request: Request, user=Depends(require_auth)):
    notes = _list_notes_for(user["user_id"])
    return templates.TemplateResponse("notes.html",
        {"request": request, "user": user, "notes": notes})

@app.post("/api/notes/create")
async def note_create(request: Request, user=Depends(require_auth)):
    # HTMX: return partial HTML for new note in list

@app.get("/api/notes/{slug}/edit")
async def note_edit(request: Request, slug: str, user=Depends(require_auth)):
    # Return editor partial with split Markdown preview (from mockup)
```

### 5.2 Templates — Port from Mockups

Copy and adapt from `mockups-fastapi/templates/`:

| Template | Source Mockup | Adaptations |
|---|---|---|
| `base.html` | `mockups-fastapi/templates/base.html` | Add real auth check; dynamic sidebar per role |
| `login.html` | New (matches dark theme of `style.css`) | Login form + error flash |
| `register.html` | New | Registration form |
| `dashboard.html` | `mockups-fastapi/templates/dashboard.html` | Real stats from `_gather_stats()` |
| `chat.html` | `mockups-fastapi/templates/chat.html` | Wire `hx-post="/api/chat/send"` to real LLM |
| `notes.html` | `mockups-fastapi/templates/notes.html` | HTMX CRUD; split editor with live Markdown preview |

### 5.3 Static Assets

Copy from mockup:
- `static/style.css` — the 500-line dark theme (already polished)
- All CDN references already in `base.html`:
  - `htmx.org@2.0.4`
  - `alpinejs@3.14.8`
  - `picocss/pico@2`
  - `Material Icons`

For offline Pi usage, vendor these files into `static/vendor/`.

### 5.4 HTMX Interactivity Patterns

The mockups already demonstrate the HTMX patterns used:

```html
<!-- Chat: send message, swap response into container -->
<form hx-post="/api/chat/send" hx-target="#messages" hx-swap="beforeend">
  <input name="message" placeholder="Type a message..." />
</form>

<!-- Notes: load note content on click -->
<button hx-get="/api/notes/{{ slug }}" hx-target="#note-content" hx-swap="innerHTML">
  {{ title }}
</button>

<!-- Notes: live Markdown preview while editing -->
<textarea hx-post="/api/notes/preview" hx-trigger="input changed delay:300ms"
          hx-target="#preview" hx-swap="innerHTML">
</textarea>
```

### 5.5 HTTPS / TLS

**Option A — Tailscale HTTPS (recommended for home use):**
```bash
# Tailscale already installed; enable HTTPS
tailscale cert openclawpi.tail12345.ts.net
# Use uvicorn with SSL:
uvicorn bot_web:app --host 0.0.0.0 --port 8080 --ssl-certfile cert.pem --ssl-keyfile key.pem
```

**Option B — Caddy reverse proxy:**
```bash
sudo apt install caddy
# Forward 443 → 8080, auto-TLS via Let's Encrypt or self-signed
```

### 5.6 Create `src/services/picoclaw-web.service`

```ini
[Unit]
Description=PicoUI Web Interface (FastAPI)
After=network.target picoclaw-telegram.service

[Service]
Type=simple
User=stas
WorkingDirectory=/home/stas/.picoclaw
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/home/stas/.picoclaw/bot.env
ExecStart=/usr/bin/python3 -m uvicorn bot_web:app --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 5.7 Deliverables

**Status: ✅ Deployed (v2026.3.28)**

| # | File | Status |
|---|---|---|
| 1 | `src/bot_web.py` | ✅ New — FastAPI app with login/register/dashboard/chat/notes |
| 2 | `src/templates/base.html` | ✅ New — sidebar layout with HTMX |
| 3 | `src/templates/login.html` | ✅ New — auth form |
| 4 | `src/templates/register.html` | ✅ New — registration form |
| 5 | `src/templates/dashboard.html` | ✅ New — real stats |
| 6 | `src/templates/chat.html` | ✅ New — HTMX chat |
| 7 | `src/templates/notes.html` | ✅ New — HTMX CRUD + live preview |
| 8 | `src/static/style.css` | ✅ New — 500-line dark theme |
| 9 | `src/services/picoclaw-web.service` | ✅ New — systemd unit |
| 10 | `src/bot_auth.py` | ✅ Modified — add JWT issue/decode helpers |

### 5.8 Verification

- `https://openclawpi:8080/login` shows login page.
- Register a new user → appears in `accounts.json` with status "pending".
- Admin approves → user can log in → redirected to dashboard.
- Chat sends message to LLM, response appears via HTMX swap.
- Notes: create, list, view, edit (split Markdown preview), delete — all via HTMX.
- Cookie is HTTP-only; API access without cookie returns redirect to `/login`.

---

## 6. P2 — Calendar + Admin Dashboard

**Goal:** Calendar month grid view, mail digest, and full admin panel in the web UI.  
**Effort:** ~5–7 days  
**Dependencies:** P1 complete

### 6.1 Calendar Screens

| Screen | Template | Web Enhancement |
|---|---|---|
| Calendar main | `calendar.html` (from mockup) | **Month grid view** with event dots — already designed in mockup |
| Day detail | HTMX partial | Click a day → slide-in panel with events for that day |
| Add event | HTMX form | Text input + LLM preview card → confirm |
| Multi-event confirm | HTMX partial swap | Step-through cards: Save / Skip / Save All |
| Event detail | HTMX partial | Full card with Edit/Reschedule/Delete/TTS/Email buttons |
| Calendar console | Chat-like interface | Same HTMX pattern as main chat |

```html
<!-- Month grid: click day → load events via HTMX -->
<td class="calendar-day has-events"
    hx-get="/api/calendar/day/2026-04-15"
    hx-target="#day-detail"
    hx-swap="innerHTML transition:true">
  15
  <span class="event-dot"></span>
</td>
```

Action handlers added to `bot_actions.py`:

```python
def action_calendar_menu(user: UserContext) -> Screen: ...
def action_cal_add_confirm(user: UserContext, parsed_event: dict) -> Screen: ...
def action_cal_event_detail(user: UserContext, ev_id: str) -> Screen: ...
def action_cal_query(user: UserContext, text: str) -> Screen: ...
```

### 6.2 Mail Digest Screens

| Screen | Template | Web Enhancement |
|---|---|---|
| Digest view | `mail.html` (from mockup) | Categorized sections: Important, Regular, Promo, Spam |
| Mail setup wizard | HTMX multi-step form | Real-time IMAP connection test |
| Digest TTS | `<audio>` element inline | No separate voice message — play in-page |

### 6.3 Admin Dashboard

| Screen | Template | Web Enhancement |
|---|---|---|
| Admin panel | `admin.html` (from mockup) | Dashboard layout with sections |
| User management | HTMX table | Status badges + action buttons + search filter |
| Web user management | HTMX table | Manage web-only accounts (no Telegram) |
| LLM switcher | HTMX dropdown | Model selection + API key form (masked input) |
| Voice opts | Toggle switches | CSS animated toggles (see §9) |
| Release notes | Scrollable list | Version history from `release_notes.json` |
| Password reset | HTMX form | Admin resets any user's web password |

### 6.4 Deliverables

**Status: ✅ Deployed (v2026.3.28)**

| # | File | Status |
|---|---|---|
| 1 | `src/templates/calendar.html` | ✅ New — month grid + HTMX |
| 2 | `src/templates/mail.html` | ✅ New — categorized digest |
| 3 | `src/templates/admin.html` | ✅ New — full admin panel |
| 4 | `src/bot_web.py` | ✅ Modified — calendar/mail/admin routes |
| 5 | `src/bot_actions.py` | ✅ Modified — calendar + admin action handlers |

### 6.5 Verification

- Calendar month grid renders with event dots.
- Click day → HTMX loads day detail panel with smooth transition.
- Add event via NL input → LLM parses → confirm card → saved.
- Admin panel: list users, approve/block, switch LLM, toggle voice opts.
- Mail digest shows categorized summary.

---

## 7. P3 — Voice: Browser Recording + Audio Playback

**Goal:** Voice input/output in the browser via MediaRecorder API and `<audio>` playback.  
**Effort:** ~3–5 days  
**Dependencies:** P2 complete

### 7.1 Browser Voice Recording

```javascript
// static/voice.js — MediaRecorder → OGG Opus → upload
const startRecording = async () => {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
  const chunks = [];
  recorder.ondataavailable = e => chunks.push(e.data);
  recorder.onstop = async () => {
    const blob = new Blob(chunks, { type: 'audio/webm' });
    const form = new FormData();
    form.append('audio', blob, 'voice.webm');
    const resp = await fetch('/api/voice/send', { method: 'POST', body: form });
    // HTMX-compatible: insert response into #voice-result
  };
  recorder.start();
  return { recorder, stream };
};
```

### 7.2 Voice UI — Orb + Waveform (from mockup)

The `voice.html` mockup already includes:

- **Recording orb**: pulsating circle with Alpine.js `x-data` state toggle
- **Waveform visualization**: CSS-animated bars during recording
- **Pipeline timing**: stage-by-stage latency display (STT → LLM → TTS)

```html
<!-- From mockups-fastapi/templates/voice.html -->
<div class="voice-orb" :class="{ recording: isRecording }"
     @click="toggleRecording()" x-data="{ isRecording: false }">
  <span class="material-icons">mic</span>
</div>

<div class="waveform" x-show="isRecording">
  <div class="bar" style="--i:0"></div>
  <div class="bar" style="--i:1"></div>
  <!-- ... -->
</div>
```

### 7.3 Audio Playback

TTS outputs served as OGG via FastAPI:

```python
@app.get("/api/audio/{audio_id}")
async def get_audio(audio_id: str, user=Depends(require_auth)):
    path = Path(f"~/.picoclaw/audio_cache/{audio_id}.ogg").expanduser()
    return FileResponse(path, media_type="audio/ogg")
```

Template plays audio inline:
```html
<audio controls autoplay src="/api/audio/{{ audio_id }}"></audio>
```

### 7.4 Voice Pipeline (Web)

```
Browser MediaRecorder (WebM Opus)
      │
      ▼
 POST /api/voice/send (multipart upload)
      │
      ▼
 ffmpeg: WebM Opus → 16 kHz PCM S16LE
      │
      ▼
 [VAD filter] → [Vosk STT / Whisper] → transcript
      │
      ▼
 _ask_picoclaw(transcript) → LLM response
      │
      ▼
 _tts_to_ogg(response) → OGG file
      │
      ▼
 Return JSON: { text: "...", audio_url: "/api/audio/abc123" }
      │
      ▼
 HTMX inserts text + <audio> into page
```

### 7.5 Push Notifications (Optional)

Browser push notifications for calendar reminders:

1. Service Worker registered on first web visit.
2. Push subscription sent to server → stored in `accounts.json`.
3. When `threading.Timer` fires for a calendar reminder: check if user has web push subscription → send via `pywebpush`.

### 7.6 Deliverables

**Status: ✅ Deployed (v2026.3.28)**

| # | File | Status |
|---|---|---|
| 1 | `src/templates/voice.html` | ✅ New — orb + waveform + pipeline display |
| 2 | `src/static/voice.js` | ✅ New — MediaRecorder helper |
| 3 | `src/static/sw.js` | ✅ New — Service Worker for push (optional) |
| 4 | `src/bot_web.py` | ✅ Modified — voice upload/playback routes |

### 7.7 Verification

- Click voice orb → recording starts with visual feedback.
- Stop recording → audio uploaded → STT + LLM + TTS pipeline runs.
- Text response and audio player appear in page.
- Pipeline timing shows per-stage latency.

---

## 8. P4 — Full Migration: All Screens Unified

**Goal:** All 19 Telegram keyboards migrate to Screen objects. Both channels render from the same actions. PWA support.  
**Effort:** ~5–7 days  
**Dependencies:** P3 complete

### 8.1 Migrate Remaining Telegram Handlers

| Handler group | Action handlers to create |
|---|---|
| System chat | `action_system_prompt`, `action_system_confirm`, `action_system_result` |
| Error protocol | `action_errp_start`, `action_errp_collect`, `action_errp_send` |
| Voice session | `action_voice_session` (Telegram-specific wrapper) |
| Registration | `action_register` (unified for both channels) |
| Help | `action_help` (role-aware) |
| Profile | `action_profile` (with link/unlink Telegram) |

### 8.2 Remove Legacy Code

- Remove direct `bot.send_message()` calls from handler modules.
- Remove `InlineKeyboardMarkup` imports from action handler modules.
- Remove the 19 keyboard builder functions (replaced by Screen widget definitions).

### 8.3 Responsive Web Design

The mockup `style.css` already includes responsive breakpoints:

```css
/* From mockups-fastapi/static/style.css */
@media (max-width: 768px) {
  .sidebar { display: none; }
  .main-content { margin-left: 0; }
  .mobile-nav { display: flex; }
}
```

### 8.4 PWA Support

Add a web app manifest for "Add to Home Screen":

```json
// static/manifest.json
{
  "name": "PicoUI",
  "short_name": "Pico",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#121212",
  "theme_color": "#7c4dff",
  "icons": [{ "src": "/static/icon-192.png", "sizes": "192x192" }]
}
```

### 8.5 i18n for Web

`_t(user_id, key)` works for both channels — the `UserContext.lang` field is set from:
- **Telegram:** `from_user.language_code` (existing logic).
- **Web:** `accounts.json` → `lang` field (set at registration or in profile settings).

Language switcher in web profile updates `accounts.json` and refreshes the page.

### 8.6 Deliverables

**Status: ✅ Deployed (v2026.3.28)**

| # | File | Status |
|---|---|---|
| 1 | `src/bot_actions.py` | ✅ Complete — all screens |
| 2 | `src/bot_handlers.py` | ✅ Simplified — delegates to actions |
| 3 | `src/bot_admin.py` | ✅ Simplified — delegates to actions |
| 4 | `src/bot_calendar.py` | ✅ Storage only — UI migrated to actions |
| 5 | `src/render_telegram.py` | ✅ Complete — handles all widget types |
| 6 | `src/templates/*.html` | ✅ Complete — all 8+ pages |
| 7 | `src/static/manifest.json` | ✅ New — PWA manifest |

### 8.7 Verification

- All Telegram features work via Screen objects.
- All web features work via the same Screen objects.
- Create note in web → visible in Telegram. Add calendar event in Telegram → visible in web.
- PWA installable on mobile.
- i18n works in both channels.

---

## 9. Multi-Channel Renderer Architecture

The Screen DSL (§4.5) enables a **write-once, render-anywhere** approach. Each delivery channel gets a thin renderer that translates `Screen` objects into platform-specific API calls. The business logic in `bot_actions.py` never changes.

### 9.1 Renderer Interface

Every renderer implements the same contract:

```python
# render_<channel>.py
def render(screen: Screen, target, client) -> None:
    """Translate Screen widgets into platform-specific output.

    Args:
        screen: Screen object from bot_actions
        target: Recipient identifier (chat_id, HTTP response, channel_id, …)
        client: Platform client (TeleBot, FastAPI Response, WhatsApp client, …)
    """
    for widget in screen.widgets:
        if isinstance(widget, ButtonRow):
            _render_buttons(widget, target, client)
        elif isinstance(widget, Card):
            _render_card(widget, target, client)
        elif isinstance(widget, TextInput):
            _render_input(widget, target, client)
        elif isinstance(widget, AudioPlayer):
            _render_audio(widget, target, client)
        # ... etc.
```

### 9.2 Implemented Renderers (P0–P4)

| Renderer | File | Phase | Target |
|---|---|---|---|
| **Telegram** | `render_telegram.py` | P0 | `bot.send_message()` + `InlineKeyboardMarkup` |
| **Web (FastAPI)** | Jinja2 templates | P1 | HTML + HTMX partials |

### 9.3 Future Messenger Renderers

Adding a new messenger channel requires only a `render_<channel>.py` file (~50–100 lines) plus a thin entry-point adapter for receiving events from that platform.

| Messenger | Renderer file | Widget mapping | API |
|---|---|---|---|
| **WhatsApp** | `render_whatsapp.py` | Button → Interactive button (max 3), ButtonRow → List section (max 10), Card → Text body, AudioPlayer → Audio media message | WhatsApp Business API |
| **Discord** | `render_discord.py` | Button → Button component, ButtonRow → ActionRow (max 5), Card → Embed, AudioPlayer → File attachment, TextInput → Modal TextInput | discord.py |
| **Slack** | `render_slack.py` | Button → Block action, ButtonRow → Actions block, Card → Section block, TextInput → Modal input, AudioPlayer → File block | Slack Bolt SDK |
| **Matrix** | `render_matrix.py` | Button → `m.room.message` with fallback, Card → formatted body, AudioPlayer → `m.audio` | matrix-nio |

### 9.4 Widget Degradation Strategy

Not all widgets map 1:1 to every platform. Renderers handle missing capabilities gracefully:

| Widget | Full support | Degraded fallback |
|---|---|---|
| `TextInput` | Telegram (ForceReply), Web (`<input>`), Slack (Modal) | WhatsApp / Discord: "Reply with your text" prompt |
| `Toggle` | Web (checkbox), Telegram (callback button) | WhatsApp: simulate via numbered options ("1 = ON, 2 = OFF") |
| `MarkdownBlock` | Web (rendered HTML), Telegram (Markdown v1) | WhatsApp: plain text (strip formatting) |
| `Spinner` | Web (CSS animation), Telegram (edit → "⏳") | All messengers: "Processing…" text |
| `AudioPlayer` | Web (`<audio>`), Telegram (`send_voice`) | All messengers: send audio file |

### 9.5 Integration with PicoClaw Gateway Channels

PicoClaw's gateway (`picoclaw gateway`) already supports Telegram, WhatsApp, Discord, Feishu, and Slack via its own channel drivers (configured in `~/.picoclaw/config.json`). Two integration strategies:

**Strategy A — Direct renderers (recommended for full UI control):**
Each messenger gets its own Python renderer. The bot connects directly to each platform API. Full Screen DSL support, custom keyboards, rich widgets.

**Strategy B — PicoClaw/OpenClaw gateway passthrough:**
Route messages through PicoClaw or OpenClaw gateway. The gateway handles multi-channel delivery. Simpler setup, but limited to plain text — no custom keyboards, buttons, or rich widgets.

**Recommendation:** Use Strategy A for primary channels (Telegram, Web) where rich UI matters. Use Strategy B for secondary channels where plain text LLM chat is sufficient.

### 9.6 Adding a New Renderer — Checklist

1. Create `src/render_<channel>.py` implementing the `render(screen, target, client)` interface.
2. Map each widget type to the platform's equivalent (or degraded fallback).
3. Create an entry-point adapter (e.g., `bot_<channel>.py`) that receives platform events and calls `bot_actions` → `render`.
4. Add a systemd service file to `src/services/picoclaw-<channel>.service`.
5. Update `bot_config.py` with channel-specific constants.
6. Add to this roadmap's renderer table (§9.2).

---

## 10. Interactive Widget Patterns (NiceGUI-like in FastAPI)

NiceGUI provides rich widget interactivity (sliding panels, animated toggles, smooth transitions) via its Quasar component library. We achieve the same UX in FastAPI using **HTMX + Alpine.js + CSS transitions**. This section documents reusable patterns.

### 9.1 Sliding Panels

NiceGUI: `ui.drawer()` with `elevated=True` slides in from the side.

**FastAPI equivalent — Alpine.js + CSS:**

```html
<!-- Slide-in panel (calendar day detail, note editor, etc.) -->
<div x-data="{ open: false }" class="slide-panel-container">
  <button @click="open = true">Open Panel</button>

  <div class="slide-panel" :class="{ 'slide-open': open }">
    <button @click="open = false" class="close-btn">&times;</button>
    <div hx-get="/api/panel-content" hx-trigger="intersect once" hx-swap="innerHTML">
      <!-- HTMX loads content when panel becomes visible -->
    </div>
  </div>
</div>
```

```css
/* style.css addition */
.slide-panel {
  position: fixed;
  right: -400px;
  top: 0;
  width: 400px;
  height: 100vh;
  background: var(--bg-secondary);
  transition: right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 100;
  box-shadow: -4px 0 20px rgba(0,0,0,0.3);
  overflow-y: auto;
  padding: 1.5rem;
}
.slide-panel.slide-open { right: 0; }

@media (max-width: 768px) {
  .slide-panel { width: 100vw; right: -100vw; }
}
```

### 9.2 Animated Toggle Switches

NiceGUI: `ui.switch()` with Quasar styling.

**FastAPI equivalent — CSS-only:**

```html
<label class="toggle-switch">
  <input type="checkbox" checked
         hx-post="/api/voice-opts/toggle/warm_piper"
         hx-swap="outerHTML"
         hx-target="closest .toggle-row">
  <span class="toggle-slider"></span>
  <span class="toggle-label">Warm Piper Cache</span>
</label>
```

```css
.toggle-switch { display: flex; align-items: center; gap: 0.75rem; cursor: pointer; }
.toggle-switch input { display: none; }
.toggle-slider {
  width: 44px; height: 24px;
  background: var(--text-muted);
  border-radius: 12px;
  position: relative;
  transition: background 0.2s ease;
}
.toggle-slider::after {
  content: '';
  width: 20px; height: 20px;
  background: white;
  border-radius: 50%;
  position: absolute;
  top: 2px; left: 2px;
  transition: transform 0.2s ease;
}
.toggle-switch input:checked + .toggle-slider { background: var(--accent); }
.toggle-switch input:checked + .toggle-slider::after { transform: translateX(20px); }
```

### 9.3 Expandable / Collapsible Sections

NiceGUI: `ui.expansion()`.

**FastAPI equivalent — Alpine.js:**

```html
<div x-data="{ expanded: false }" class="expandable-section">
  <div class="expand-header" @click="expanded = !expanded">
    <span class="material-icons" x-text="expanded ? 'expand_less' : 'expand_more'"></span>
    <h3>Voice Optimization Settings</h3>
  </div>
  <div class="expand-body" x-show="expanded" x-collapse>
    <!-- Toggle switches, content loaded via HTMX if needed -->
  </div>
</div>
```

The `x-collapse` Alpine.js plugin provides smooth height animation.

### 9.4 Toast Notifications

NiceGUI: `ui.notify()`.

**FastAPI equivalent — HTMX OOB swap + CSS animation:**

```html
<!-- Server returns this as an Out-of-Band swap -->
<div id="toast-container" hx-swap-oob="beforeend">
  <div class="toast toast-success" x-data x-init="setTimeout(() => $el.remove(), 3000)">
    ✅ Note saved successfully
  </div>
</div>
```

```css
.toast {
  position: fixed; bottom: 2rem; right: 2rem;
  padding: 1rem 1.5rem;
  background: var(--bg-secondary);
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  animation: slideUp 0.3s ease, fadeOut 0.3s ease 2.7s;
  z-index: 200;
}
@keyframes slideUp { from { transform: translateY(20px); opacity: 0; } }
@keyframes fadeOut { to { opacity: 0; transform: translateY(-10px); } }
```

### 9.5 Loading Spinners / Skeleton Screens

NiceGUI: `ui.spinner()`.

**FastAPI equivalent — HTMX indicator:**

```html
<button hx-post="/api/chat/send" hx-indicator="#chat-spinner">
  Send
</button>
<div id="chat-spinner" class="htmx-indicator">
  <div class="spinner"></div>
</div>
```

```css
.htmx-indicator { display: none; }
.htmx-request .htmx-indicator { display: inline-flex; }
.spinner {
  width: 24px; height: 24px;
  border: 3px solid var(--text-muted);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
```

### 9.6 Modal Dialogs

NiceGUI: `ui.dialog()`.

**FastAPI equivalent — Alpine.js:**

```html
<div x-data="{ showModal: false }">
  <button @click="showModal = true">Delete Note</button>

  <div class="modal-overlay" x-show="showModal" x-transition.opacity @click.self="showModal = false">
    <div class="modal-card" x-transition.scale>
      <h3>Confirm Delete</h3>
      <p>Are you sure you want to delete this note?</p>
      <div class="modal-actions">
        <button @click="showModal = false">Cancel</button>
        <button hx-delete="/api/notes/my-note" hx-target="#note-list"
                @click="showModal = false" class="btn-danger">Delete</button>
      </div>
    </div>
  </div>
</div>
```

### 9.7 Live Data Tables with Sorting

NiceGUI: `ui.table()` with sorting/filtering.

**FastAPI equivalent — HTMX + Alpine.js:**

```html
<input type="search" name="q" placeholder="Filter users..."
       hx-get="/api/admin/users" hx-trigger="input changed delay:300ms"
       hx-target="#user-table-body" hx-swap="innerHTML">

<table class="data-table">
  <thead>
    <tr>
      <th hx-get="/api/admin/users?sort=name" hx-target="#user-table-body">Name ↕</th>
      <th hx-get="/api/admin/users?sort=role" hx-target="#user-table-body">Role ↕</th>
      <th>Actions</th>
    </tr>
  </thead>
  <tbody id="user-table-body">
    <!-- HTMX-loaded rows -->
  </tbody>
</table>
```

### 9.8 Tab Navigation

NiceGUI: `ui.tabs()` + `ui.tab_panels()`.

**FastAPI equivalent — Alpine.js:**

```html
<div x-data="{ tab: 'overview' }">
  <div class="tab-bar">
    <button :class="{ active: tab === 'overview' }" @click="tab = 'overview'">Overview</button>
    <button :class="{ active: tab === 'events' }" @click="tab = 'events'">Events</button>
    <button :class="{ active: tab === 'settings' }" @click="tab = 'settings'">Settings</button>
  </div>
  <div x-show="tab === 'overview'" x-transition><!-- content --></div>
  <div x-show="tab === 'events'" x-transition><!-- content --></div>
  <div x-show="tab === 'settings'" x-transition><!-- content --></div>
</div>
```

### 9.9 Pattern Summary

| NiceGUI Widget | FastAPI Equivalent | Mechanism |
|---|---|---|
| `ui.drawer()` | Slide-panel with CSS transform | Alpine.js + CSS transition |
| `ui.switch()` | Custom CSS toggle | Checkbox + CSS `:checked` |
| `ui.expansion()` | Collapsible section | Alpine.js `x-collapse` |
| `ui.notify()` | Toast with OOB swap | HTMX OOB + CSS animation |
| `ui.spinner()` | HTMX indicator | CSS spinner + `.htmx-indicator` |
| `ui.dialog()` | Modal overlay | Alpine.js `x-show` + CSS transition |
| `ui.table()` | Sortable/filterable table | HTMX partial load + Alpine.js |
| `ui.tabs()` | Tab bar | Alpine.js `x-show` |
| `ui.markdown()` | Server-rendered Markdown | `markdown` Python library → HTML |
| `ui.audio()` | `<audio>` element | Native HTML5 audio |

---

## 11. File Structure

### After Full Migration (P4 Complete)

```
src/
  ── Identity & Auth (P0) ──
  bot_auth.py               ← Unified accounts, bcrypt, JWT, link codes

  ── LLM Backend Abstraction (P0) ──
  bot_llm.py                ← ask_llm() — pluggable backend: PicoClaw CLI / Gateway, OpenClaw, OpenAI

  ── Shared Core (unchanged) ──
  bot_config.py             ← Constants + ACCOUNTS_FILE, WEB_SECRET_FILE, LLM_BACKEND
  bot_state.py              ← Mutable runtime state
  bot_instance.py           ← TeleBot singleton (Telegram only)
  bot_security.py           ← Prompt injection guard

  ── Data Layer (accept user_id) ──
  bot_users.py              ← Registration + notes file I/O
  bot_calendar.py           ← Calendar storage + reminders
  bot_mail_creds.py         ← IMAP credentials + digest
  bot_email.py              ← SMTP send
  bot_voice.py              ← STT/TTS pipeline (audio processing)

  ── Unified UI Layer (P0) ──
  bot_ui.py                 ← Screen, Button, Widget dataclasses
  bot_actions.py            ← All screen action handlers

  ── Channel Renderers ──
  render_telegram.py        ← Screen → bot.send_message() + InlineKeyboard

  ── Telegram Entry Point (simplified) ──
  telegram_menu_bot.py      ← Handler registration + dispatcher → render_telegram
  bot_access.py             ← i18n _t(), detection; keyboard builders removed
  bot_admin.py              ← Delegates to bot_actions
  bot_handlers.py           ← Delegates to bot_actions
  bot_error_protocol.py     ← Collection logic; UI via actions

  ── Web Entry Point (P1) ──
  bot_web.py                ← FastAPI app: routes, auth, API endpoints
  templates/
    base.html               ← Sidebar layout, HTMX/Alpine.js, dark theme
    login.html              ← Authentication form
    register.html           ← Account creation form
    dashboard.html          ← Stats overview
    chat.html               ← HTMX real-time LLM chat
    notes.html              ← Split editor + live Markdown preview
    calendar.html           ← Month grid + HTMX day detail panels
    mail.html               ← Categorized digest view
    voice.html              ← Recording orb + waveform + pipeline timing
    admin.html              ← User management + LLM + voice opts
  static/
    style.css               ← 500-line dark theme (from mockups)
    voice.js                ← MediaRecorder helper
    sw.js                   ← Service Worker for push (optional)
    manifest.json           ← PWA manifest
    vendor/                 ← Self-hosted HTMX, Alpine.js, Pico CSS, icons

  ── Services ──
  services/
    picoclaw-telegram.service
    picoclaw-voice.service
    picoclaw-web.service    ← NEW — FastAPI/uvicorn
```

### Runtime Files on Pi

New files introduced:

| File | Purpose |
|---|---|
| `~/.picoclaw/accounts.json` | Unified user identity store |
| `~/.picoclaw/web_secret.key` | JWT signing secret (generated once) |
| `~/.picoclaw/link_codes.json` | Temporary Telegram↔Web link codes |
| `~/.picoclaw/.migration_done` | Marker: legacy→unified migration completed |
| `~/.picoclaw/audio_cache/` | TTS audio cache for web playback |

---

## 12. NiceGUI Integration — Future Enhancement

> **Status:** 💡 Nice to have — planned after P4 is complete and stable.

NiceGUI can be added as an alternative (or replacement) web frontend, reusing the same `bot_actions.py` backend. This is attractive because:

- **Python-only UI definition** — no HTML/CSS/JS editing needed
- **Rich Quasar components** — data tables, charts, drag-and-drop, complex forms
- **WebSocket bi-directional updates** — real-time LLM streaming without SSE
- **Built-in `app.storage`** — user session persistence across reloads

### Implementation approach

1. Create `src/render_nicegui.py` — translates `Screen` objects to `ui.*` calls.
2. Create `src/bot_web_nicegui.py` — NiceGUI app entry point using `render_nicegui`.
3. Add `picoclaw-web-nicegui.service` — runs on a different port (e.g. 8081).
4. Both FastAPI and NiceGUI web servers can coexist, sharing the same data layer.

### NiceGUI-specific widgets to port

| Widget | NiceGUI API | Notes |
|---|---|---|
| Sidebar drawer | `ui.left_drawer()` | Auto-collapsible on mobile |
| Dark mode toggle | `ui.dark_mode()` | Built-in |
| Drag-and-drop upload | `ui.upload()` | For error protocol attachments |
| Charts / plots | `ui.chart()` (Apache ECharts) | Admin dashboard analytics |
| Table with pagination | `ui.table()` | User management, notes list |
| Keyboard shortcuts | `ui.keyboard()` | Power-user navigation |

### RAM considerations

NiceGUI adds ~60 MB RAM per running instance (Quasar JS + WebSocket). On Pi 3 B+ (1 GB), this is tight alongside the Telegram bot + Vosk. Consider running NiceGUI only on Pi 4 B+ (2–4 GB), or as a replacement for FastAPI (not alongside it).

### pip dependency

```bash
pip3 install nicegui   # ~40 MB installed
```

---

## 13. CRM Platform Vision

> **Status:** Long-term objective. Current focus is building the core platform and prototype. Concrete CRM customer projects will customize on top.

### 13.1 Feature Mapping: Current System → CRM Concepts

The existing PicoClaw bot already implements several core CRM primitives. The platform architecture (Screen DSL + pluggable backends + multi-channel rendering) makes it straightforward to extend toward a full CRM system.

| Current feature | Module(s) | CRM concept | Extension needed |
|---|---|---|---|
| **User management** (registration, roles, admin panel) | `bot_users.py`, `bot_admin.py`, `bot_auth.py` | **Contacts / Accounts** | Add contact fields (company, phone, tags, custom fields) |
| **Notes** (create, edit, per-user Markdown) | `bot_users.py`, `bot_handlers.py` | **Activities / Notes** | Link notes to contacts; add activity types (call, meeting, task) |
| **Calendar** (NL add, reminders, morning briefing) | `bot_calendar.py` | **Meetings / Tasks** | Link events to contacts; shared team calendars; recurring events |
| **Mail digest** (IMAP fetch, LLM summary) | `bot_mail_creds.py`, `bot_email.py` | **Email integration** | Link emails to contacts; track threads; template replies |
| **Admin panel** (user CRUD, LLM config, voice opts) | `bot_admin.py` | **CRM Admin** | Custom field editor; workflow builder; import/export |
| **LLM chat** (free chat, system chat) | `bot_handlers.py`, `bot_access.py` | **AI assistant / Copilot** | Context-aware: inject contact history into LLM prompts |
| **Profile** (name, role, registration date) | `bot_handlers.py` | **User profile / My account** | Extended profile; team membership; permissions |
| **Error protocol** | `bot_error_protocol.py` | **Support tickets** | Ticket lifecycle (open → assigned → resolved → closed) |

### 13.2 CRM Platform Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     PicoUI Platform Core                    │
│                                                             │
│  bot_actions.py ─── Screen DSL ─── Renderers (Telegram/Web) │
│       ↑                                                     │
│  bot_auth.py ─── bot_users.py ─── bot_calendar.py ───  …   │
│       ↑                                                     │
│  bot_llm.py ─── PicoClaw / OpenClaw / OpenAI                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                   CRM Extension Layer                       │
│                                                             │
│  crm_contacts.py      ← contact/account CRUD + search      │
│  crm_deals.py         ← sales pipeline stages              │
│  crm_workflows.py     ← automation rules (LLM-assisted)    │
│  crm_fields.py        ← custom field definitions           │
│  crm_reports.py       ← dashboard / KPI aggregation        │
│  crm_import.py        ← CSV/vCard bulk import              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│              Customer-Specific CRM Project                  │
│                                                             │
│  project_config.json   ← custom fields, pipelines, roles   │
│  project_workflows/    ← customer-specific automations      │
│  project_templates/    ← branded email/message templates    │
│  project_integrations/ ← customer ERP/API adapters          │
└─────────────────────────────────────────────────────────────┘
```

### 13.3 LLM-Powered CRM Features

The pluggable LLM backend (`bot_llm.py`) enables AI-native CRM capabilities:

| Feature | LLM usage | Backend requirement |
|---|---|---|
| **Auto-classify contacts** | Analyze email/chat → assign category, priority, sentiment | Any backend |
| **Meeting summary** | Transcribe voice note → extract action items → link to contact | Voice pipeline + LLM |
| **Email draft** | Generate context-aware reply using contact history + notes | Any backend |
| **Deal scoring** | Analyze interactions → predict close probability | Requires conversation memory (§2.1 in TODO) |
| **Smart search** | Natural language query: "show me all leads from last week" → calendar + contacts filter | Any backend |
| **Workflow trigger** | "When a new email arrives from a VIP contact, summarize and notify" | PicoClaw gateway or OpenClaw automation |

### 13.4 Implementation Phases for CRM

| Phase | Scope | Depends on |
|---|---|---|
| **C0** (current) | Core platform: Screen DSL, auth, multi-channel, LLM backend | P0–P1 of this roadmap |
| **C1** | Contact management: CRUD, search, link to notes/calendar/mail | P2 (calendar + admin done) |
| **C2** | Deals pipeline: stages, Kanban board in Web UI | P2 + C1 |
| **C3** | Custom fields + workflows: admin-defined field schema + automation | P4 + C2 |
| **C4** | Customer project template: config-driven customization, white-label UI | C3 |

> **Current focus (C0):** Build the core platform (P0–P1) and prove it works as a prototype for concrete CRM customer projects. CRM-specific modules (C1+) are added per customer need, not speculatively.

---

## 14. Deployment Architecture

### 14.1 Process Hierarchy After Full Implementation

```
systemd
  ├── picoclaw-telegram.service
  │     └── python3 telegram_menu_bot.py
  │           ├── telebot polling thread
  │           ├── calendar reminder threads
  │           └── mail refresh threads
  │
  ├── picoclaw-web.service               ← NEW (FastAPI)
  │     └── uvicorn bot_web:app
  │           ├── ASGI worker
  │           ├── HTMX partial responses
  │           └── SSE streams (optional, for LLM chat)
  │
  ├── picoclaw-voice.service
  │     └── python3 voice_assistant.py
  │
  └── picoclaw-gateway.service (disabled)
```

### 14.2 Shared State Between Processes

Both `picoclaw-telegram` and `picoclaw-web` need access to the same data:

| Data | Storage | Concurrency |
|---|---|---|
| `accounts.json` | File | File-lock (`fcntl.flock`) — low contention |
| Notes `*.md` | Files | File-lock per write |
| Calendar `*.json` | Files | File-lock per write |
| Mail creds | Files | File-lock per write |
| `voice_opts.json` | File | Write-rarely (admin toggles only) |
| `active_model.txt` | File | Write-rarely |

Since both processes are single-threaded for writes and write rarely, file-level locking is sufficient. No database needed.

### 14.3 Deploy Commands

```bat
rem Deploy web server files
pscp -pw "%HOSTPWD%" src\bot_auth.py src\bot_web.py src\bot_ui.py stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\bot_actions.py src\render_telegram.py stas@OpenClawPI:/home/stas/.picoclaw/

rem Deploy templates + static assets
pscp -pw "%HOSTPWD%" -r src\templates stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" -r src\static stas@OpenClawPI:/home/stas/.picoclaw/

rem Deploy service
pscp -pw "%HOSTPWD%" src\services\picoclaw-web.service stas@OpenClawPI:/tmp/
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S cp /tmp/picoclaw-web.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now picoclaw-web"

rem Install Python dependencies
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "pip3 install fastapi uvicorn[standard] jinja2 bcrypt PyJWT python-multipart"

rem Verify
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "systemctl status picoclaw-web --no-pager"
```

### 14.4 Network Access

| Access method | URL | Notes |
|---|---|---|
| LAN | `http://openclawpi:8080` | Same network only |
| Tailscale | `https://openclawpi.tail*.ts.net:8080` | Anywhere with Tailscale |
| Tailscale Funnel | `https://openclawpi.tail*.ts.net` | Public internet (if enabled) |

### 14.5 RAM Budget

| Component | RAM |
|---|---|
| OS + kernel | ~250 MB |
| Telegram bot (Python + telebot) | ~60 MB |
| Vosk model (lazy-loaded) | ~180 MB |
| Piper ONNX (lazy-loaded) | ~150 MB |
| **FastAPI + uvicorn** | **~25 MB** |
| ffmpeg subprocesses | ~20 MB |
| **Total peak** | **~685 MB** |
| **Remaining** | **~315 MB** |

FastAPI is significantly lighter than NiceGUI (~25 MB vs ~60 MB), leaving more headroom for the voice pipeline on Pi 3 B+.

---

## 15. Risks & Mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | Pi 3 B+ RAM under pressure with web + Vosk + Piper | OOM kill | FastAPI is 25 MB (light); monitor RSS; `gpu_mem=16`; consider Pi 4 upgrade |
| R2 | Two processes writing same JSON concurrently | Data corruption | File-level `fcntl.flock` on every write |
| R3 | HTMX + Alpine.js CDN dependencies offline | Web UI fails to load | Vendor all JS/CSS into `static/vendor/` for self-hosted operation |
| R4 | bcrypt slow on ARM (work factor 12) | Login takes 2–3 s | Accept it (security > speed); JWT caches session for 24h |
| R5 | Web-only users have no push channel for reminders | Missed reminders | Browser Push Notifications via Service Worker (P3) |
| R6 | Migration from chat_id to user_id breaks existing data | Data loss | Backup before migration; keep symlinks; dry-run mode first |
| R7 | HTTPS required for secure cookies | Can't deploy auth without TLS | Use Tailscale built-in HTTPS (free, automatic) |
| R8 | Dual-renderer drift (Web shows different data than Telegram) | User confusion | Both renderers call same action handlers; automated smoke test |
| R9 | HTMX partial rendering complexity grows | Hard to maintain | Keep partials small; one partial per action; documented patterns (§10) |
| R10 | Multi-backend LLM complexity (4 backends to maintain) | Bug surface grows | All backends share `ask_llm()` interface; integration tests per backend; start with picoclaw_cli, add others on demand |
| R11 | CRM scope creep — building features before customer need | Wasted effort | CRM modules (C1+) added only per concrete customer project, never speculatively |
| R12 | OpenClaw gateway dependency on external project | Breaking API changes | Pin gateway API version; abstract behind `bot_llm.py`; PicoClaw CLI as always-available fallback |

---

## 16. Decision Log

| # | Decision | Rationale | Alternatives considered |
|---|---|---|---|
| **D1** | **FastAPI + Jinja2 + HTMX** as primary web framework | Mockups already designed and tested; 25 MB RAM; full CSS control; standard web stack | NiceGUI: richer widgets but 60 MB RAM, locked to Quasar, less CSS control |
| D2 | **Username/password** as primary web auth | User requirement: no Telegram dependency for web login | Telegram Login Widget: requires Telegram account |
| D3 | **accounts.json** instead of SQLite | Consistent with existing JSON-based storage; sufficient for <100 users | SQLite: better concurrency but adds complexity |
| D4 | **UUID-based user_id** replacing chat_id as primary key | Telegram-independent identity; web-only users need an ID | Keep chat_id: would not support web-only users |
| D5 | **JWT in HTTP-only cookie** for web sessions | Stateless; no server-side session store needed; secure against XSS | Session tokens in DB: more complex |
| D6 | **Separate systemd services** for bot and web | Process isolation; independent restart; independent logging | Same process: simpler state sharing but coupled failure modes |
| D7 | **File-level locking** for shared data | Simple; sufficient for 2 writers with low contention | Redis/SQLite: overkill for this scale |
| D8 | **NiceGUI as future enhancement** (§11) | Lower priority; valuable for complex admin UIs; can reuse `bot_actions.py` | NiceGUI-first: higher RAM, fewer mockups ready |
| D9 | **Screen DSL as abstraction layer** | Write once, render in both channels; type-safe; testable; future-proof | Direct Jinja2 rendering: faster initially but duplicates Telegram logic |
| D10 | **Self-hosted vendor assets** | Pi may not have internet; CDN adds latency | CDN-only: simpler but fragile offline |
| D11 | **Pluggable LLM backend (`bot_llm.py`)** | PicoClaw CLI is current default; OpenClaw/OpenAI needed for flexibility and CRM projects | Hardcode picoclaw: locks to one backend forever |
| D12 | **Multi-channel renderer pattern** (§9) | Screen DSL enables adding WhatsApp/Discord/Slack as thin renderers; no business logic duplication | Per-channel full implementation: massive code duplication |
| D13 | **CRM-ready core architecture** (§13) | Current features (users, notes, calendar, mail) already map to CRM primitives; designing for extensibility costs nothing now | Build CRM later from scratch: loses existing foundation |

---

## Appendix A — Phase Summary

| Phase | Prerequisites | New files | Modified files | Dependencies added |
|---|---|---|---|---|
| **P0** | None | `bot_auth.py`, `bot_llm.py`, `bot_ui.py`, `bot_actions.py`, `render_telegram.py` | `bot_config.py`, `bot_access.py`, `bot_users.py`, `bot_calendar.py`, `bot_mail_creds.py`, `bot_handlers.py` | `bcrypt`, `PyJWT` |
| **P1** | P0 | `bot_web.py`, `templates/*`, `static/*`, `picoclaw-web.service` | `bot_auth.py` | `fastapi`, `uvicorn`, `jinja2`, `python-multipart` |
| **P2** | P1 | `templates/calendar.html`, `templates/mail.html`, `templates/admin.html` | `bot_web.py`, `bot_actions.py` | None |
| **P3** | P2 | `templates/voice.html`, `static/voice.js`, `static/sw.js` | `bot_web.py` | `pywebpush` (optional) |
| **P4** | P3 | `static/manifest.json` | All handler modules simplified | None |

## Appendix B — Dependency Installation

```bash
# P0: Auth
pip3 install bcrypt PyJWT

# P1: Web server
pip3 install fastapi uvicorn[standard] jinja2 python-multipart

# P3: Push notifications (optional)
pip3 install pywebpush

# Future: NiceGUI (nice-to-have, §11)
# pip3 install nicegui

# Total new pip dependencies: 6 (+ 1 optional)
# Total disk: ~30 MB
# Total runtime RAM: ~25 MB (FastAPI + uvicorn)
```

## Appendix C — Quick Start After P1

```bash
# On the Pi, after deployment:

# 1. Start web server
sudo systemctl start picoclaw-web

# 2. Open browser
# http://openclawpi:8080/register → create account → wait for admin approval

# 3. Admin approves (via Telegram admin panel or direct accounts.json edit)

# 4. Login
# http://openclawpi:8080/login → enter username/password → dashboard

# 5. Link Telegram (optional)
# In web Profile → "Link Telegram" → follow instructions
```

## Appendix D — Design Token Reference

Shared between FastAPI templates and any future NiceGUI theme:

```css
:root {
  --accent:       #7c4dff;
  --accent-hover: #9e7bff;
  --bg-primary:   #121212;
  --bg-secondary: #1e1e1e;
  --bg-tertiary:  #2a2a2a;
  --text-primary: #e0e0e0;
  --text-secondary: #b0b0b0;
  --text-muted:   #757575;
  --border-color: #333;
  --success:      #81c784;
  --warning:      #ffb74d;
  --error:        #e57373;
  --sidebar-width: 260px;
}
```

---

*This roadmap is self-contained. Implementation starts with P0 — creating `bot_auth.py`, the Screen DSL, and the unified identity model. Each phase is independently deployable and testable. NiceGUI integration (§11) is deferred as a future enhancement after the FastAPI web UI is stable.*
