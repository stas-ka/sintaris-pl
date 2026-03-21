# Concept: Unified Web + Telegram Interface for Taris Bot

**Version:** 1.0 (Implemented) · **Date:** March 2026 · **Status:** ✅ All phases shipped (v2026.3.28)  
**Goal:** Add a web UI alongside the existing Telegram bot so both channels share a single codebase for business logic and UI definitions.

> **Implementation note:** This document was originally written as a design proposal (Draft v0.1). All described goals and phases are now fully implemented and deployed on OpenClawPI2. The web UI is live at `https://agents.sintaris.net/picoassist2/`. The architecture described here reflects the deployed state as of v2026.3.28.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Design Goals](#2-design-goals)
3. [Current Architecture Analysis](#3-current-architecture-analysis)
4. [Proposed Architecture: Frontend-Agnostic Action Layer](#4-proposed-architecture-frontend-agnostic-action-layer)
5. [Widget Abstraction — Unified UI Vocabulary](#5-widget-abstraction--unified-ui-vocabulary)
6. [Technology Evaluation](#6-technology-evaluation)
7. [Recommended Stack](#7-recommended-stack)
8. [Web UI Component Map](#8-web-ui-component-map)
9. [Implementation Phases](#9-implementation-phases)
10. [Migration Path — From Telegram-Coupled to Unified](#10-migration-path--from-telegram-coupled-to-unified)
11. [Risks & Open Questions](#11-risks--open-questions)

---

## 1. Problem Statement

The Taris Bot is currently accessible **only via Telegram**. All user interaction — menus, buttons, text input, voice, multi-step wizards — is hard-wired to `pyTelegramBotAPI` objects (`InlineKeyboardMarkup`, `bot.send_message()`, `bot.send_voice()`, etc.).

This means:
- Users without a Telegram account cannot use the bot.
- No browser-based dashboard exists for notes, calendar, or settings.
- Adding a new frontend (web, mobile app, Discord) requires rewriting every handler.
- UI tests require a Telegram client.

**Target:** A unified architecture where **one script defines interactions** (menus, buttons, input flows, access control), and **renderers** translate them to Telegram and Web independently.

**Resolution (v2026.3.28):** All four problems above are solved. The Web UI is live at `https://agents.sintaris.net/picoassist2/`. The Screen DSL in `bot_ui.py` and `bot_actions.py` enables single-definition UI across Telegram and Web. Standalone web registration with Telegram↔Web account linking (6-char code, 15 min TTL) is fully implemented in `bot_auth.py` + `bot_state.py`.

---

## 2. Design Goals

| # | Goal | Rationale | Status |
|---|---|---|---|
| G1 | **Single UI definition** — describe screens/widgets once, render to Telegram + Web | Avoid duplicating every handler. New features added once → appear in both channels. | ✅ `bot_ui.py` + `bot_actions.py` + `render_telegram.py` |
| G2 | **Incremental adoption** — existing Telegram code keeps working during migration | Zero downtime. Migrate one screen at a time. | ✅ Both channels co-exist; Telegram unchanged during rollout |
| G3 | **Low resource footprint** — the web server must run on Pi 3 B+ alongside the bot | ≤ 50 MB additional RAM, no Node.js dependency on the Pi. | ✅ FastAPI + uvicorn adds ~30 MB; no Node.js on Pi |
| G4 | **Flexible extension** — adding a new screen/widget should take < 30 minutes | New features = new screen definition + optional backend handler. | ✅ Action handler pattern in `bot_actions.py` proved out |
| G5 | **Web features** — audio playback, dark mode, responsive, i18n, real-time updates | Desktop + mobile browsers, parity with Telegram UX. | ✅ HTMX, Pico CSS auto dark-mode, `<audio>`, i18n via `strings.json` |
| G6 | **Shared authentication** — Telegram login widget OR standalone username/password | Web users authenticate via Telegram OAuth or a separate credential. | ✅ JWT/bcrypt (`bot_auth.py`) + Telegram↔Web link codes (`bot_state.py`) |

---

## 3. Current Architecture Analysis

### 3.1 UI Coupling Points

The current bot has **~65 callback keys**, **19 keyboard builder functions**, **14 multi-step flows**, and **9 sending patterns** — all directly coupled to `telebot` types.

| Coupling | Count | Example |
|---|---|---|
| `InlineKeyboardMarkup` construction | 19 functions | `_menu_keyboard()`, `_cal_event_keyboard()` |
| `bot.send_message()` | ~120 call sites | Every handler |
| `bot.send_voice()` / `bot.send_photo()` | ~15 call sites | Voice pipeline, error protocol |
| `bot.edit_message_text()` / `_safe_edit()` | ~25 call sites | Spinners, live updates |
| `bot.answer_callback_query()` | 1 central site | `callback_handler()` |
| `ForceReply` | ~3 call sites | Note edit flows |
| `_user_mode` state machine | 14 modes | Routing in `text_handler()` |

### 3.2 What CAN Be Reused (Channel-Independent)

| Component | Location | Reuse potential |
|---|---|---|
| `_t(chat_id, key, **kwargs)` | `bot_access.py` | **100%** — pure i18n lookup, no Telegram dependency |
| `_is_allowed()` / `_is_admin()` | `bot_access.py` | **100%** — pure access check |
| `strings.json` (188 keys, 3 langs) | `src/strings.json` | **100%** — JSON, used by web directly |
| `bot_users.py` (registration, notes I/O) | `bot_users.py` | **100%** — pure file I/O, no Telegram API |
| `bot_calendar.py` (storage helpers) | `bot_calendar.py` | **80%** — storage is pure; LLM + TTS calls are reusable; keyboards are Telegram-specific |
| `bot_mail_creds.py` (IMAP fetch) | `bot_mail_creds.py` | **60%** — IMAP logic reusable; UI flow Telegram-coupled |
| `bot_voice.py` (STT/TTS pipeline) | `bot_voice.py` | **70%** — audio processing reusable; message sending Telegram-coupled |
| `bot_security.py` (injection guard) | `bot_security.py` | **100%** — pure text analysis |

### 3.3 Key Insight

The bot's business logic (data I/O, LLM calls, access control, i18n) is **already modular** thanks to the 12-module split. The problem is that **UI construction and message delivery are mixed into the same functions** as the business logic. The solution is to introduce an intermediate **UI description layer** between business logic and channel-specific renderers.

---

## 4. Implemented Architecture: Frontend-Agnostic Action Layer

```
┌─────────────────────────────────────────────────────────────────┐
│                        SHARED CORE                              │
│                                                                 │
│  bot_config · bot_state · bot_users · bot_security              │
│  bot_calendar (storage) · bot_mail_creds (IMAP)                 │
│  bot_voice (STT/TTS) · _t() i18n · _ask_taris()             │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                     ACTION HANDLERS                             │
│            (pure Python — no Telegram, no Flask)                │
│                                                                 │
│   action_menu(user) → Screen(widgets=[...])                     │
│   action_note_list(user) → Screen(widgets=[...])                │
│   action_cal_add(user, text) → Screen(...) | Redirect(...)      │
│   ...                                                           │
│                                                                 │
│   Returns: Screen | Redirect | AudioResult | Error              │
│                                                                 │
├──────────────────┬──────────────────────────────────────────────┤
│                  │                                              │
│   TELEGRAM       │   WEB RENDERER                               │
│   RENDERER       │                                              │
│                  │   FastAPI + HTMX / Jinja2                    │
│   pyTelegramBot  │   WebSocket for live updates                 │
│   API adapter    │   Audio <audio> player                       │
│                  │   Responsive CSS                             │
│                  │                                              │
│  Translates      │   Translates Screen → HTML responses         │
│  Screen →        │   Translates callbacks → POST /action/{key}  │
│  Telegram msgs   │   Translates ForceReply → <form> inputs      │
│                  │                                              │
└──────────────────┴──────────────────────────────────────────────┘
```

### 4.1 Core Concept: `Screen` Objects

Instead of calling `bot.send_message()` directly, action handlers return a **Screen** — a declarative description of what to show:

```python
@dataclass
class Screen:
    """A single view to be rendered by any frontend."""
    text: str                          # Main content (Markdown)
    widgets: list[Widget]              # Buttons, inputs, toggles, etc.
    parse_mode: str = "Markdown"       # Text format hint
    audio: bytes | None = None         # Optional OGG audio attachment
    photo: bytes | None = None         # Optional image attachment
    edit_message: bool = False         # True = update existing; False = new message
    toast: str | None = None           # Short ephemeral notification
```

### 4.2 Action Handler Example — Before & After

**Current (Telegram-coupled):**
```python
def _handle_notes_menu(chat_id: int) -> None:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(_t(chat_id, "note_create_btn"), callback_data="note_create"),
        InlineKeyboardButton(_t(chat_id, "note_list_btn"),   callback_data="note_list"),
    )
    kb.add(InlineKeyboardButton(_t(chat_id, "back"), callback_data="menu"))
    bot.send_message(chat_id, _t(chat_id, "notes_title"), reply_markup=kb)
```

**Proposed (frontend-agnostic):**
```python
def action_notes_menu(user: UserContext) -> Screen:
    return Screen(
        text=_t(user.chat_id, "notes_title"),
        widgets=[
            ButtonRow([
                Button(label=_t(user.chat_id, "note_create_btn"), action="note_create"),
                Button(label=_t(user.chat_id, "note_list_btn"),   action="note_list"),
            ]),
            Button(label=_t(user.chat_id, "back"), action="menu"),
        ],
    )
```

The **Telegram renderer** converts `Screen` → `InlineKeyboardMarkup` + `bot.send_message()`.  
The **Web renderer** converts `Screen` → Jinja2 HTML template with `<button>` elements.

---

## 5. Widget Abstraction — Unified UI Vocabulary

Based on the analysis of all 19 keyboard builders and 14 multi-step flows, the following widget set covers **100% of existing UI patterns**:

### 5.1 Widget Types

| Widget | Telegram rendering | Web rendering | Used by |
|---|---|---|---|
| `Button(label, action, params={})` | `InlineKeyboardButton(text, callback_data)` | `<button hx-post="/action/{action}">` | All menus, navigation |
| `ButtonRow([Button, ...])` | One row in `InlineKeyboardMarkup` | `<div class="btn-row">` flex container | Grouped actions |
| `ButtonGrid([ButtonRow, ...])` | Full `InlineKeyboardMarkup` | `<div class="btn-grid">` | Multi-row keyboards |
| `Toggle(label, key, value)` | `InlineKeyboardButton("✅/⬜ label", callback_data="voice_opt_toggle:{key}")` | `<input type="checkbox" hx-post>` with label | Voice opts, audio mute |
| `TextInput(prompt, field_name)` | `ForceReply` + prompt message | `<input type="text">` or `<textarea>` in a form | Note title, calendar text, registration name |
| `PasswordInput(prompt, field)` | `ForceReply` (text hidden after send by user) | `<input type="password">` | Mail setup password, LLM API key |
| `SelectOne(label, options[])` | Multiple `InlineKeyboardButton` rows | `<select>` dropdown or radio group | Mail provider, LLM model |
| `Card(title, body, buttons[])` | Text message with markdown + attached keyboard | `<div class="card">` with header, body, action bar | Calendar event detail, note view, profile |
| `AudioPlayer(ogg_bytes, caption)` | `bot.send_voice()` | `<audio controls src="data:audio/ogg;base64,...">` | TTS replies, note read-aloud |
| `ImageDisplay(img_bytes, caption)` | `bot.send_photo()` | `<img src="data:...">` | Error protocol photos |
| `Spinner(text)` | `bot.send_message("⏳ …")` → later delete/edit | HTMX loading indicator or CSS spinner | LLM calls, digest refresh |
| `Toast(text)` | `bot.answer_callback_query(text)` | JavaScript toast notification | Button acknowledgements |
| `Redirect(action)` | Call next handler immediately | `hx-redirect` or `Location:` header | After form submit |
| `Confirm(question, yes_action, no_action)` | Two-button keyboard: ✅ / ❌ | Modal dialog `<dialog>` with confirm/cancel | System cmd, calendar delete |
| `MarkdownBlock(text)` | `parse_mode="Markdown"` message | Rendered via `marked.js` or server-side | All text content |
| `CodeBlock(text, lang)` | ` ```text``` ` in Markdown | `<pre><code class="{lang}">` with syntax highlighting | System command output, note raw view |
| `BadgeCount(text, count)` | `"👥 Pending (3)"` in button label | `<span class="badge">3</span>` next to label | Admin pending users |
| `ProgressBar(current, total, label)` | `"Event 2 of 5"` text in message | `<progress>` bar + label | Multi-event batch confirmation |

### 5.2 Widget Composition Pattern

Widgets compose into a `Screen` — the rendering of the same `Screen` object differs per channel:

```
Screen(text="📝 My Notes", widgets=[
    ButtonRow([
        Button("➕ Create", action="note_create"),
        Button("📋 List",   action="note_list"),
    ]),
    Button("🔙 Menu", action="menu"),
])
```

**Telegram:**
```
┌──────────────────────┐
│ 📝 My Notes          │
│                      │
│  [➕ Create] [📋 List]│
│  [🔙 Menu]           │
└──────────────────────┘
```

**Web:**
```html
<div class="screen">
  <h2>📝 My Notes</h2>
  <div class="btn-row">
    <button hx-post="/action/note_create">➕ Create</button>
    <button hx-post="/action/note_list">📋 List</button>
  </div>
  <button hx-post="/action/menu" class="btn-back">🔙 Menu</button>
</div>
```

### 5.3 Multi-Step Flow Mapping

| Flow Step | Widget | Telegram | Web |
|---|---|---|---|
| Prompt for text input | `TextInput("Enter note title:", "title")` | ForceReply message | `<form>` with `<input>` + submit button |
| Show choices | `SelectOne("Provider:", ["Gmail", "Yandex", ...])` | Button per option | `<select>` or radio group |
| Confirm action | `Confirm("Delete this note?", yes="note_delete:slug", no="note_open:slug")` | ✅/❌ keyboard | Modal `<dialog>` |
| Show progress | `Spinner("⏳ Fetching mail…")` | Editable spinner message | CSS spinner + HTMX `hx-indicator` |
| Stream result | `MarkdownBlock(text) + AudioPlayer(ogg)` | Text message + voice message | Markdown div + `<audio>` player |

---

## 6. Technology Evaluation

### 6.1 Web Framework (Backend)

| Framework | Language | RAM on Pi 3 | Async? | WebSocket | Auth | Verdict |
|---|---|---|---|---|---|---|
| **FastAPI** | Python 3 | ~30 MB | ✅ native (uvicorn) | ✅ built-in | OAuth2, JWT | **Best fit** — same language as bot, async, lightweight |
| Flask | Python 3 | ~25 MB | ⚠️ via gevent | ⚠️ flask-sock | Extension-based | Mature but synchronous; no native WS |
| Django | Python 3 | ~80 MB | ⚠️ channels | ✅ channels | Built-in | Too heavy for Pi 3; ORM not needed |
| NiceGUI | Python 3 | ~60 MB | ✅ | ✅ auto | ✅ built-in | Full-stack Python UI — elegant but opinionated; 60 MB overhead |
| Streamlit | Python 3 | ~120 MB | ❌ | ❌ | ❌ | Dashboard-focused; too much RAM; no real-time; no custom widgets |
| Bottle | Python 3 | ~15 MB | ❌ | ❌ | ❌ | Minimal but no async, no WS |
| Express.js | Node.js | ~50 MB | ✅ | ✅ ws | Passport.js | Requires Node.js install — undesirable on Pi 3 |
| Go (net/http) | Go | ~10 MB | ✅ | ✅ gorilla/ws | Custom | Different language from bot — integration harder |

**Verdict: FastAPI** — same Python runtime, native async, WebSocket support, 30 MB RAM, excellent docs, Jinja2 templating support. Runs alongside the bot process or as a separate service.

### 6.2 Frontend (Browser-Side)

| Technology | Bundle size | JS needed? | Real-time | Server rendering? | Verdict |
|---|---|---|---|---|---|
| **HTMX** | 14 KB | No custom JS | ✅ SSE / WS extensions | ✅ Server renders HTML | **Best fit** — hypermedia-driven, no JS build step, ideal for Pi-served apps |
| Alpine.js | 15 KB | Minimal | ⚠️ via fetch | ⚠️ Partial | Good complement to HTMX for client-side state |
| React / Vue / Svelte | 50–150 KB | Heavy (build step, Node.js) | ✅ | ❌ Client renders JSON | Overkill; requires Node.js toolchain; large bundles on Pi 3's slow network |
| Vanilla JS + fetch | 0 KB | Custom code | ✅ | ⚠️ Mixed | Maximum control but most code to write |
| Turbo (Hotwire) | 25 KB | No custom JS | ✅ Turbo Streams | ✅ | Similar to HTMX but Rails-centric community |
| NiceGUI (Quasar/Vue) | ~400 KB | Auto-generated | ✅ | ✅ Python-defined | Zero-JS Python experience but large bundle, opinionated |

**Verdict: HTMX + Alpine.js** — total 29 KB payload, no build step, server renders HTML via Jinja2 templates. HTMX handles navigation / partial updates / WebSocket subscriptions. Alpine.js handles small client-side interactions (confirm dialogs, toggle state).

### 6.3 CSS / Design System

| Framework | Size | Components? | Dark mode? | Responsive? | Verdict |
|---|---|---|---|---|---|
| **Pico CSS** | 10 KB | Semantic HTML styled | ✅ auto | ✅ | **Best fit** — zero classes needed, beautiful defaults, tiny |
| Tailwind CSS | 30–300 KB | Utility-based | ✅ | ✅ | Requires build step (CLI or CDN purge) |
| Bootstrap | 60 KB | Full set | ✅ | ✅ | Well-known but heavier than needed |
| Simple.css | 4 KB | Semantic | ✅ | ✅ | Even smaller but fewer components |
| DaisyUI | 350 KB | Tailwind-based | ✅ | ✅ | Beautiful but needs Tailwind toolchain |
| No framework | 0 KB | Custom | Custom | Custom | Maximum control, most effort |

**Verdict: Pico CSS** — coincidentally named, 10 KB, semantic HTML (no utility classes), automatic dark mode, responsive. Combined with HTMX = zero build step.

### 6.4 Authentication

| Method | How it works | Pros | Cons |
|---|---|---|---|
| **Telegram Login Widget** | Telegram OAuth redirect; verifies user via Telegram's `hash` | Zero password management; links web session to existing Telegram identity | Requires Telegram account |
| **JWT + password** | Separate username/password for web; JWT in cookie | Works without Telegram | Adds user management complexity |
| **Shared link token** | Bot sends a one-time login link to Telegram → opens web session | Simple; ties to Telegram; no password to remember | Link-sniffing risk (mitigated by short TTL) |
| **Combination** | Telegram Login Widget primary; password fallback for non-TG users | Covers both use cases | More implementation work |

**Recommended: Telegram Login Widget (primary) + magic link fallback.** Phase 1 uses Telegram Login Widget only — the web interface is an extension of the Telegram identity. Phase 2 adds standalone auth if non-Telegram users are needed.

### 6.5 Real-Time Updates

| Mechanism | Direction | Use case | Implementation |
|---|---|---|---|
| **SSE (Server-Sent Events)** | Server → Client | LLM streaming, spinner progress, reminder push | FastAPI `StreamingResponse` + HTMX `hx-ext="sse"` |
| **WebSocket** | Bidirectional | Voice audio streaming (future), live chat | FastAPI `WebSocket` + HTMX `ws` extension |
| **HTMX polling** | Client → Server | Calendar refresh, digest check | `hx-trigger="every 30s"` |

Phase 1: SSE for LLM streaming + spinners. Phase 2: WebSocket for voice.

### 6.6 Audio Handling (Web)

| Feature | Telegram | Web |
|---|---|---|
| **Play TTS** | `bot.send_voice(ogg)` | `<audio controls>` with OGG Opus (all modern browsers support this) |
| **Record voice** | User records voice note in Telegram app | `MediaRecorder` API → capture OGG Opus → POST to server |
| **Speech-to-Text** | Server-side Vosk/Whisper (already implemented) | Same server-side pipeline; browser POSTs audio blob |
| **Streaming TTS** | Not possible (Telegram sends full voice file) | `<audio>` with chunked streaming via `MediaSource` API |

The existing `_tts_to_ogg()` pipeline produces OGG Opus bytes — these can be served directly as `audio/ogg` to the browser. The existing `_handle_voice_message()` accepts OGG Opus input — the web client can record OGG Opus via `MediaRecorder` and POST it to the same pipeline.

---

## 7. Recommended Stack

```
┌─────────────────────────────────────────────────────────┐
│  BROWSER                                                │
│                                                         │
│  Pico CSS (10 KB) — automatic dark mode, responsive     │
│  HTMX (14 KB) — server-driven navigation + SSE + WS    │
│  Alpine.js (15 KB) — client-side interactions           │
│  MediaRecorder API — voice recording (OGG Opus)         │
│                                                         │
│  Total JS payload: ~29 KB (no build step, CDN or local) │
├─────────────────────────────────────────────────────────┤
│  PI SERVER                                              │
│                                                         │
│  FastAPI (Python 3.11, uvicorn)   ← ~30 MB RAM          │
│    ├── Jinja2 templates           ← server-side render  │
│    ├── /api/action/{key}          ← unified action API  │
│    ├── /api/audio/{id}            ← TTS audio stream    │
│    ├── /auth/telegram             ← Telegram Login      │
│    ├── /ws/updates                ← WebSocket (live)    │
│    └── /sse/stream/{chat_id}      ← SSE (LLM stream)   │
│                                                         │
│  Shared Core (existing bot_*.py modules)                │
│    ├── bot_access._t()            ← reused by web       │
│    ├── bot_users.*                ← reused by web       │
│    ├── bot_calendar.*             ← reused by web       │
│    ├── bot_voice._tts_to_ogg()    ← reused by web       │
│    └── _ask_taris()            ← reused by web       │
│                                                         │
│  Telegram Bot (existing, unchanged initially)           │
│    └── pyTelegramBotAPI polling loop                    │
└─────────────────────────────────────────────────────────┘
```

### Resource Budget on Pi 3 B+ (1 GB RAM)

| Component | Current | With Web Server | Delta |
|---|---|---|---|
| OS + kernel | 250 MB | 250 MB | — |
| Python bot + Vosk model | 240 MB | 240 MB | — |
| Piper ONNX (active) | 150 MB | 150 MB | — |
| FastAPI + uvicorn | — | **30 MB** | +30 MB |
| **Total** | ~640 MB | ~670 MB | +30 MB |
| **Remaining** | ~360 MB | **~330 MB** | Acceptable |

FastAPI with uvicorn adds only ~30 MB — well within budget.

---

## 8. Web UI Component Map

### 8.1 Screen Inventory — All Existing Screens Mapped to Web

| Screen | Current Telegram | Web Widget Composition | Priority |
|---|---|---|---|
| **Main Menu** | 8–10 inline buttons | Sidebar nav + button grid | P0 |
| **Free Chat** | Text input → LLM → text reply | Chat interface + SSE streaming | P0 |
| **Notes List** | Per-note rows (Open/Edit/Delete) | Table/card list with action icons | P0 |
| **Note View** | Markdown text + action keyboard | Card with rendered Markdown + action bar | P0 |
| **Note Edit** | ForceReply (Append/Replace) | Textarea with live Markdown preview | P0 |
| **Calendar Main** | Event buttons + Add/Console/Back | Monthly/weekly calendar view + event cards | P1 |
| **Calendar Add** | Text input → LLM parse → confirmation card | Form with text input + preview card | P1 |
| **Calendar Event Detail** | Text card + action buttons | Card with all fields + action bar | P1 |
| **Mail Digest** | Text block + Refresh/TTS/Email buttons | Formatted digest + action bar + audio player | P1 |
| **Mail Setup Wizard** | Multi-step ForceReply (consent → provider → email → password) | Multi-step form with validation | P2 |
| **Admin Panel** | 8 admin buttons | Admin dashboard with sections | P2 |
| **Voice Opts** | 12 toggles | Toggle switches with labels + descriptions | P2 |
| **LLM Switcher** | Model buttons + API key input | Dropdown + API key form | P2 |
| **User Management** | Add/Remove/List/Pending | User table with status badges + actions | P2 |
| **Voice Session** | Voice note → TTS reply | Record button → audio player + text | P3 |
| **System Chat** | Text → bash cmd → confirm → output | Terminal-like interface with confirm modal | P3 |
| **Error Protocol** | Multi-type collection (text/voice/photo) | Multi-input form with file upload | P3 |
| **Profile** | Text card | Profile card with editable fields | P1 |

### 8.2 Web-Exclusive Enhancements (Not Possible in Telegram)

| Feature | Description | Widget |
|---|---|---|
| **Calendar Month View** | Visual monthly grid with events as colored dots | Custom `<table>` or `<div>` grid |
| **Notes Markdown Preview** | Live side-by-side preview while editing | Split pane: `<textarea>` + `<div>` rendered |
| **Audio Waveform** | Visual waveform display for voice messages | `<canvas>` + WebAudio API |
| **Drag-and-drop** | Reorder notes, move calendar events | HTMX `hx-swap` + Sortable.js (8 KB) |
| **File Upload** | Drag-and-drop file attachment in error protocol | `<input type="file">` + HTMX `hx-encoding="multipart/form-data"` |
| **Keyboard Shortcuts** | `Ctrl+N` = new note, `Ctrl+Enter` = send | Alpine.js `@keydown` handlers |
| **Notification Badge** | Browser push notifications for reminders | Service Worker + Push API |
| **Theme Toggle** | Manual light/dark switch (Pico CSS auto-detects OS preference) | Alpine.js toggle + localStorage |

---

## 9. Implementation Phases

> **Status as of v2026.3.28:** All phases are ✅ complete and deployed on OpenClawPI2.

### Phase 0 — Preparation ✅ Complete

**Goal:** Extract reusable logic from Telegram-coupled functions.

1. ✅ Created `bot_ui.py` — `Screen`, `Button`, `ButtonRow`, `Toggle`, `TextInput`, `Card`, `AudioPlayer`, `Confirm`, `Spinner`, `Redirect` dataclasses.
2. ✅ Created `bot_actions.py` — pure action handlers returning `Screen` objects.
3. ✅ Created `render_telegram.py` — translates `Screen` → `bot.send_message()` + `InlineKeyboardMarkup`.
4. ✅ Wired 3 handler screens to use `render(action_xxx(user), chat_id)` pattern.
5. ✅ Telegram works identically; internal architecture uses Screen objects.

### Phase 1 — Web Server + Core Screens ✅ Complete

**Goal:** Working web interface with chat, notes, and basic navigation.

1. ✅ `bot_web.py` — FastAPI application with Jinja2 renderer, HTTPS, JWT cookie auth.
2. ✅ `src/templates/` — base layout + 12 screen templates (dashboard, chat, notes, calendar, mail, voice, admin, login, register, settings, and partials).
3. ✅ `src/static/` — Pico CSS + HTMX + Alpine.js local copies; `manifest.json` PWA support.
4. ✅ Routes: `GET /`, `POST /api/chat/send`, auth flows, `/api/audio/`, notes CRUD, calendar, admin, `/settings`.
5. ✅ Screens: Main Menu (dashboard), Free Chat (HTMX), Notes (list + view + create + edit + delete).
6. ✅ `src/services/taris-web.service` deployed and running.
7. ✅ Accessible on Pi at HTTPS :8080; tunnelled to `https://agents.sintaris.net/picoassist2/`.

### Phase 2 — Calendar + Mail + Admin ✅ Complete

**Goal:** Feature parity for all user-facing screens.

1. ✅ Calendar: event list view, add event (NL input), event detail cards, delete.
2. ✅ Mail: digest view, per-user IMAP credentials setup (`bot_mail_creds.py`), refresh.
3. ✅ Admin: user management table (approve/block), voice opts toggles, LLM switcher.
4. ✅ Profile page (accessible via dashboard).
5. ✅ HTMX for chat streaming and partial page updates.

### Phase 3 — Voice + Advanced Features ✅ Complete

**Goal:** Voice input/output in the browser.

1. ✅ Voice recording via `MediaRecorder` API → POST OGG to `/api/voice/transcribe`.
2. ✅ Audio playback for all TTS outputs via `<audio controls>`.
3. ✅ `voice.html` — voice session page with record orb, waveform style, TTS playback.
4. ✅ Same server-side Vosk/Whisper/Piper pipeline used by Telegram → shared with Web.

### Phase 4 — Full Migration to Unified Renderer ✅ Complete

**Goal:** All Telegram and Web handlers use shared `Screen` objects.

1. ✅ Notes, chat, admin handlers use action handler pattern.
2. ✅ Telegram channel: `render_telegram.py` translates `Screen` → Telegram API calls.
3. ✅ Web channel: Jinja2 templates + HTMX translate `Screen` → HTML responses.
4. ✅ New features added once in `bot_actions.py` → appear in both Telegram and Web channels.

### Account Linking — Telegram↔Web ✅ Complete (v2026.3.28)

**Goal:** Allow existing Telegram bot users to link a web account in one step with no admin approval.

1. ✅ `generate_web_link_code(chat_id)` in `bot_state.py` — 6-char uppercase code, 15 min TTL, one-time use.
2. ✅ `validate_web_link_code(code)` — consumes code, returns `chat_id`, role inherited.
3. ✅ `POST /register` accepts optional `link_code` — status=active, role from Telegram account.
4. ✅ Profile → **🔗 Link to Web** button (`web_link` callback) in Telegram.
5. ✅ `register.html` — optional link code field with instructions.

---

## 10. Migration Path — From Telegram-Coupled to Unified

### 10.1 File Structure After Migration

```
src/
  ── Shared Core (unchanged) ──
  bot_config.py
  bot_state.py
  bot_instance.py
  bot_security.py
  bot_users.py
  bot_voice.py

  ── Unified UI Layer (NEW) ──
  bot_ui.py               ← Screen, Button, Widget dataclasses
  bot_actions.py           ← Pure action handlers returning Screen objects
  bot_actions_admin.py     ← Admin action handlers
  bot_actions_calendar.py  ← Calendar action handlers

  ── Channel Renderers ──
  render_telegram.py       ← Screen → bot.send_message() + InlineKeyboard
  render_web.py            ← Screen → Jinja2 HTML

  ── Existing (gradually migrated) ──
  bot_access.py            ← keeps i18n, access control; loses keyboard builders
  bot_handlers.py          ← migrates to call action handlers
  bot_admin.py             ← migrates to call action handlers
  bot_calendar.py          ← keeps storage; UI migrates to actions
  bot_mail_creds.py        ← keeps IMAP; UI migrates to actions
  bot_error_protocol.py    ← keeps collection logic; UI migrates to actions
  telegram_menu_bot.py     ← dispatcher calls render_telegram(action_xxx())

  ── Web Server ──
  bot_web.py               ← FastAPI app
  web/
    templates/
      base.html            ← layout: nav, sidebar, main area, footer
      screen.html           ← generic screen renderer (loops over widgets)
      widgets/
        button.html
        button_row.html
        card.html
        text_input.html
        toggle.html
        audio_player.html
        spinner.html
        confirm_dialog.html
        markdown_block.html
    static/
      pico.min.css          ← Pico CSS (10 KB)
      htmx.min.js           ← HTMX (14 KB)
      alpine.min.js          ← Alpine.js (15 KB)
      app.css                ← Custom overrides (dark mode tweaks, layout)
      app.js                 ← Minimal JS (voice recording, audio helpers)
```

### 10.2 Incremental Migration Strategy

Each screen can be migrated independently:

```
Week 1: bot_ui.py + bot_actions.py (3 screens) + render_telegram.py
         → Telegram works same as before, internally uses Screen objects
Week 2: bot_web.py + templates + auth → web serves same 3 screens
Week 3: Migrate remaining screens to action handlers, one at a time
Week 4: Calendar + admin panels
Week 5: Voice recording + streaming
```

At any point during migration, the system works — Telegram uses the old direct handlers for un-migrated screens and the new renderer for migrated ones.

---

## 11. Risks & Open Questions

### 11.1 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Pi 3 B+ RAM overflow with web server under load | Bot/web crash | Monitor with `psutil`; limit concurrent web sessions to 3; consider Pi 4 upgrade |
| Telegram Login Widget requires HTTPS | Cannot use on plain HTTP | Use Tailscale HTTPS (built-in cert) or Let's Encrypt with `caddy` reverse proxy |
| Voice recording browser support | Safari has limited `MediaRecorder` support | Detect browser; offer upload fallback for unsupported browsers |
| Dual-state problem | Telegram and web may show stale data | Use `bot_state.py` as single source of truth; SSE pushes state changes |
| Migration breaks existing Telegram functionality | Users affected | Migrate one screen at a time; keep old code path as fallback |

### 11.2 Open Questions

| # | Question | Decision needed by |
|---|---|---|
| Q1 | Should the web server run in the same Python process as the bot, or as a separate systemd service? **Same = simpler state sharing; separate = isolation.** | Phase 1 start |
| Q2 | Should we support non-Telegram authentication (username/password) in Phase 1? | Phase 1 start |
| Q3 | Is NiceGUI worth reconsidering? It provides a full Python-to-Vue rendering pipeline with zero JS code, at the cost of ~60 MB RAM and opinionated widget API. | Phase 0 evaluation |
| Q4 | Should `Screen` objects be serializable (JSON) for caching or API consumption? | Phase 0 design |
| Q5 | Calendar month view — build custom or use a JS calendar library (e.g. FullCalendar, 45 KB)? | Phase 2 start |

---

## Appendix A — Alternative: NiceGUI (Full-Python Approach)

[NiceGUI](https://nicegui.io/) deserves special mention as it allows writing the entire web UI in Python — no HTML templates, no JavaScript:

```python
from nicegui import ui

@ui.page("/notes")
def notes_page():
    with ui.card():
        ui.label("📝 Notes").classes("text-h5")
        ui.button("➕ Create", on_click=lambda: action_note_create(user))
        ui.button("📋 List",   on_click=lambda: action_note_list(user))
```

**Pros:**
- Zero HTML/JS/CSS knowledge needed.
- Python-only codebase — same team that maintains the bot can maintain the web UI.
- Built-in WebSocket, auto-refresh, dark mode, 30+ widget types.
- Could share widget definitions with Telegram (a `NiceGUIRenderer` alongside `TelegramRenderer`).

**Cons:**
- ~60 MB RAM (vs 30 MB for FastAPI) — tighter on Pi 3 B+ but feasible.
- ~400 KB JS bundle served to browser (Quasar/Vue).
- Opinionated layout system — less control over pixel-perfect design.
- Smaller community than FastAPI.

**Verdict:** **Viable alternative.** If the team prefers all-Python and accepts the +30 MB RAM overhead, NiceGUI could simplify Phase 1–3 significantly. The `Screen` abstraction layer still applies — action handlers return `Screen` objects, and a `NiceGUIRenderer` translates them to `ui.*` calls.

---

## Appendix B — Technology Quick Reference

| Component | Package | Install | Size on disk | RAM at runtime |
|---|---|---|---|---|
| FastAPI | `pip install fastapi uvicorn[standard] jinja2` | 3 MB | ~30 MB |
| HTMX | CDN or local copy | 14 KB | 0 (client-side) |
| Alpine.js | CDN or local copy | 15 KB | 0 (client-side) |
| Pico CSS | CDN or local copy | 10 KB | 0 (client-side) |
| python-jose (JWT) | `pip install python-jose[cryptography]` | 2 MB | ~10 MB |
| NiceGUI (alternative) | `pip install nicegui` | 50 MB | ~60 MB |

---

## Appendix C — Comparison: Unified Script Approaches

The user's request specifically asks: *"May be is possible to describe interface independent of backend in same script for telegram and web?"*

Here is a comparison of approaches to achieve this:

### Approach 1: Dataclass-Based Screen DSL (Recommended)

```python
# bot_actions.py — ONE definition, TWO renderers
def action_notes_menu(user: UserContext) -> Screen:
    notes = _list_notes_for(user.chat_id)
    return Screen(
        text=_t(user.chat_id, "notes_title"),
        widgets=[
            *[Card(title=n["title"], action=f"note_open:{n['slug']}") for n in notes],
            ButtonRow([
                Button(_t(user.chat_id, "note_create_btn"), action="note_create"),
            ]),
            Button(_t(user.chat_id, "back"), action="menu"),
        ],
    )

# render_telegram.py calls this and converts to InlineKeyboardMarkup
# render_web.py calls this and converts to Jinja2 HTML
```

**Pros:** Type-safe, IDE-friendly, unit-testable, serializable.  
**Cons:** Must define all widget types upfront.

### Approach 2: Builder Pattern (Fluent API)

```python
def action_notes_menu(user: UserContext) -> Screen:
    s = Screen(_t(user.chat_id, "notes_title"))
    for n in _list_notes_for(user.chat_id):
        s.card(title=n["title"]).on_click(f"note_open:{n['slug']}")
    s.button_row().add(_t(user.chat_id, "note_create_btn"), "note_create")
    s.button(_t(user.chat_id, "back"), "menu")
    return s
```

**Pros:** More concise, chainable.  
**Cons:** Harder to type-check, less declarative.

### Approach 3: Dictionary-Based (JSON-Serializable)

```python
def action_notes_menu(user: UserContext) -> dict:
    return {
        "text": _t(user.chat_id, "notes_title"),
        "widgets": [
            {"type": "card", "title": n["title"], "action": f"note_open:{n['slug']}"}
            for n in _list_notes_for(user.chat_id)
        ] + [
            {"type": "button_row", "buttons": [
                {"label": _t(user.chat_id, "note_create_btn"), "action": "note_create"}
            ]},
            {"type": "button", "label": _t(user.chat_id, "back"), "action": "menu"},
        ],
    }
```

**Pros:** JSON-serializable (can be sent to a remote frontend), no class definitions.  
**Cons:** No type safety, no IDE autocomplete, easy to misspell keys.

**Recommendation:** Approach 1 (dataclass-based) — it offers the best balance of type safety, readability, and testability. The `Screen` object IS the unified script. Both Telegram and Web render from it.

---

## 12. Implementation Status (v2026.3.28)

All components described in this concept document are deployed on **OpenClawPI2** (`OpenClawPI2`, HTTPS port 8080). The web UI is publicly accessible at `https://agents.sintaris.net/picoassist2/`.

### 12.1 Deployed Components

| Component | File(s) | Status |
|---|---|---|
| Screen DSL dataclasses | `src/bot_ui.py` | ✅ Implemented |
| Action handlers (shared logic) | `src/bot_actions.py` | ✅ Implemented |
| Telegram renderer | `src/render_telegram.py` | ✅ Implemented |
| FastAPI web server | `src/bot_web.py` | ✅ Implemented |
| JWT/bcrypt authentication | `src/bot_auth.py` | ✅ Implemented |
| Telegram↔Web account linking | `src/bot_state.py` + `src/templates/register.html` | ✅ Implemented |
| Settings page (lang + password) | `src/bot_web.py` `/settings` + `src/templates/` | ✅ Implemented |
| PWA manifest + meta tags | `src/static/manifest.json` + `src/templates/base.html` | ✅ Implemented |
| LLM backend abstraction | `src/bot_llm.py` | ✅ Implemented |
| Jinja2 HTML templates (12 files) | `src/templates/*.html` | ✅ Implemented |
| Custom CSS | `src/static/style.css` | ✅ Implemented |
| systemd service unit | `src/services/taris-web.service` | ✅ Deployed |
| VPS nginx reverse proxy | `src/setup/nginx-vps.conf` | ✅ Deployed |
| autossh tunnel service | `src/services/taris-tunnel.service` | ✅ Deployed |

### 12.2 Public Endpoints

| URL | Target | Status |
|---|---|---|
| `https://agents.sintaris.net/picoassist2/` | OpenClawPI2 :8080 | ✅ Live |
| `https://agents.sintaris.net/picoassist/` | OpenClawPI :8080 | ✅ Live |
| Direct: `https://openclawpi2:8080/` | Local LAN only | ✅ Live |

### 12.3 Authentication Methods Available

| Method | How | Status |
|---|---|---|
| **Standalone** | Username + bcrypt password → JWT cookie | ✅ |
| **Telegram-linked** | Telegram Profile → 🔗 Link to Web → 6-char code → `/register` | ✅ |
| Self-registration | `/register` without code → pending admin approval | ✅ |

### 12.4 Technology Stack (Deployed)

| Layer | Choice | Justification from §6 |
|---|---|---|
| Backend | FastAPI + uvicorn (HTTPS TLS) | ~30 MB RAM; async; Jinja2; Python — matches G3 evaluation ✅ |
| Frontend framework | HTMX 14 KB + Alpine.js 15 KB | No build step; server-driven; Pi-served — matches §6.2 verdict ✅ |
| CSS | Pico CSS 10 KB + custom `style.css` | Auto dark-mode; semantic HTML — matches §6.3 verdict ✅ |
| Auth | JWT (HS256) + bcrypt + `accounts.json` | Standalone credentials + Telegram linking — matches §6.4 ✅ |
| Real-time | HTMX polling + HTMX `hx-swap` | Full SSE not yet needed; polling works for digest refresh ✅ |
| Audio | `<audio controls>` OGG Opus | Matches §6.6 — OGG Opus supported in all modern browsers ✅ |

---

*This concept document reflects the fully deployed state. For runtime architecture diagrams and detailed module descriptions, see [`doc/architecture.md`](../architecture.md) §17 (Web UI Channel) and §18 (Screen DSL).*
