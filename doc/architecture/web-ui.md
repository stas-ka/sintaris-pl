# Taris — Web UI & Screen DSL Architecture

**Version:** `2026.4.24`  
→ Architecture index: [architecture.md](../architecture.md)

---

## 17. Web UI Channel (FastAPI)

**Service:** `taris-web.service` · **Port:** HTTPS 8080 · **Auth:** JWT cookie `taris_token`

The Web UI channel provides a browser-based interface with the same features as the Telegram bot, served from the Pi over HTTPS using a self-signed TLS certificate. The interface is PWA-installable.

### 17.1 Technology Stack

| Layer | Technology |
|---|---|
| Application server | FastAPI (Python) + uvicorn |
| Transport | HTTPS TLS (self-signed, port 8080) |
| Templates | Jinja2 (server-side rendering) |
| Interactivity | HTMX (partial HTML swaps, no full-page reloads) |
| Client state | Alpine.js (lightweight reactive JS) |
| CSS framework | Pico CSS + custom `style.css` |
| PWA | `static/manifest.json` + theme_color + shortcuts |

### 17.2 Authentication (`bot_auth.py`)

| Item | Detail |
|---|---|
| User accounts | `~/.taris/accounts.json` (username + bcrypt hash) |
| Token | JWT HS256, returned as `HttpOnly` cookie `taris_token` |
| Session | Cookie-based; re-login on expiry |
| Registration | Self-registration with admin approval flow |
| Admin check | `is_admin` flag in JWT claims |
| Dependency | FastAPI `Depends(get_current_user)` on every protected route |

**Auth flows:**
- **Flow A (login):** `POST /login` → verify bcrypt → issue JWT → set `taris_token` cookie → redirect `/`
- **Flow B (register):** `POST /register` → create pending account → admin notified → admin approves
- **Flow B2 (Telegram-linked register):** `POST /register` with `link_code` → `validate_web_link_code()` in `bot_state.py` → inherit role from Telegram account → status=active immediately (no admin approval needed)
- **Flow C (protected route):** incoming request → decode `taris_token` → raise 401 if missing/invalid → pass `UserContext` to handler
- **Flow D (logout):** `POST /logout` → delete cookie

### 17.3 Route Inventory

| Method | Path | Description | Auth |
|---|---|---|---|
| `GET` | `/login` | Login form | — |
| `POST` | `/login` | Verify creds, set JWT cookie | — |
| `GET` | `/register` | Registration form | — |
| `POST` | `/register` | Create pending account (optional `link_code` for Telegram-linked instant activation) | — |
| `GET` | `/logout` | Clear cookie, redirect to login | ✅ |
| `GET` | `/forgot-password` | Password reset request form | — |
| `POST` | `/forgot-password` | Send reset email | — |
| `GET` | `/reset-password/{token}` | Reset password form | — |
| `POST` | `/reset-password/{token}` | Apply new password | — |
| `GET` | `/` | Dashboard | ✅ |
| `GET` | `/profile` | Profile: name, username, Telegram link | ✅ |
| `POST` | `/profile/name` | Update display name | ✅ |
| `POST` | `/profile/change-username` | Change username | ✅ |
| `POST` | `/profile/link-telegram` | Link Telegram account via link code | ✅ |
| `GET` | `/settings` | Language + password settings | ✅ |
| `POST` | `/settings/language` | Save language | ✅ |
| `POST` | `/settings/password` | Change password | ✅ |
| `GET` | `/chat` | LLM chat page | ✅ |
| `POST` | `/chat/send` | Send message → LLM → HTML partial (HTMX) | ✅ |
| `DELETE` | `/chat/clear` | Clear chat history | ✅ |
| `GET` | `/notes` | Notes list + editor | ✅ |
| `GET` | `/notes/list` | Notes list partial (HTMX) | ✅ |
| `GET` | `/notes/{slug}` | Load note into editor | ✅ |
| `POST` | `/notes/create` | Create note | ✅ |
| `POST` | `/notes/{slug}/save` | Save note content | ✅ |
| `DELETE` | `/notes/{slug}` | Delete note | ✅ |
| `GET` | `/calendar` | Calendar month grid + upcoming events | ✅ |
| `POST` | `/calendar/add` | Add event from form | ✅ |
| `POST` | `/calendar/{ev_id}/delete` | Delete event | ✅ |
| `POST` | `/calendar/parse-text` | NL text → event JSON (LLM) | ✅ |
| `POST` | `/calendar/console` | NL intent → add/query/delete | ✅ |
| `GET` | `/contacts` | Contacts list with search + pagination | ✅ |
| `GET` | `/contacts/new` | New contact form | ✅ |
| `POST` | `/contacts/new` | Create contact | ✅ |
| `GET` | `/contacts/{cid}` | Contact detail / edit form | ✅ |
| `POST` | `/contacts/{cid}` | Update contact | ✅ |
| `POST` | `/contacts/{cid}/delete` | Delete contact | ✅ |
| `GET` | `/documents` | Documents list (RAG knowledge base) | ✅ |
| `POST` | `/documents/upload` | Upload PDF/TXT/MD/DOCX → chunk + embed | ✅ |
| `POST` | `/documents/{doc_id}/rename` | Rename document | ✅ |
| `POST` | `/documents/{doc_id}/share` | Toggle shared flag | ✅ |
| `POST` | `/documents/{doc_id}/delete` | Delete document + chunks | ✅ |
| `GET` | `/mail` | Mail digest + settings | ✅ |
| `POST` | `/mail/settings` | Save IMAP credentials | ✅ |
| `POST` | `/mail/settings/delete` | Delete mail credentials | ✅ |
| `POST` | `/mail/refresh` | Trigger IMAP refresh | ✅ |
| `GET` | `/mail/oauth/google/start` | Begin Google OAuth flow | ✅ |
| `GET` | `/mail/oauth/google/callback` | Google OAuth callback | — |
| `GET` | `/voice` | Voice: record, TTS, voice chat | ✅ |
| `GET` | `/voice/last-transcript` | Latest STT transcript (HTMX poll) | ✅ |
| `POST` | `/voice/tts` | Text → TTS audio (OGG) | ✅ |
| `POST` | `/voice/transcribe` | Audio → STT text | ✅ |
| `POST` | `/voice/chat` | Audio → STT → LLM → TTS | ✅ |
| `POST` | `/voice/chat_text` | Text → LLM → TTS | ✅ |
| `GET` | `/voice/debug/sessions` | Voice session debug list | ✅ admin |
| `GET` | `/admin` | Admin: users, LLM, voice opts, release notes | ✅ admin |
| `POST` | `/admin/llm/{model_name}` | Set active LLM model | ✅ admin |
| `POST` | `/admin/voice-opt/{key}` | Toggle voice opt flag | ✅ admin |
| `DELETE` | `/admin/user/{user_id}` | Delete user | ✅ admin |
| `POST` | `/admin/user/{user_id}/approve` | Approve pending user | ✅ admin |
| `POST` | `/admin/user/{user_id}/block` | Block user | ✅ admin |
| `POST` | `/admin/user/{user_id}/reset-password` | Reset user password | ✅ admin |
| `GET` | `/screen/{screen_id}` | Screen DSL renderer (YAML screen by ID) | ✅ |
| `POST` | `/mcp/search` | MCP RAG search (Bearer token, RRF-ranked chunks) | Bearer |
| `GET` | `/api/status` | Service health JSON | — |
| `GET` | `/api/version` | Bot version JSON | — |

### 17.4 Telegram↔Web Account Linking

Users with an existing Telegram account can link it to a new web account in one step.

- `generate_web_link_code(chat_id)` in `bot_state.py` — creates a 6-character uppercase alphanumeric code with a 15-minute TTL
- `validate_web_link_code(code)` — returns the `chat_id` if valid and not expired; one-time use
- Telegram callback `web_link` — triggered by Profile → **🔗 Link to Web** button
- `POST /register` with `link_code` → looks up Telegram role, creates web account with `status=active`

### 17.5 Templates

| Template | Purpose |
|---|---|
| `base.html` | Root layout: PWA meta tags, HTMX script, Alpine.js, Pico CSS, nav bar |
| `login.html` | Login form with error display |
| `register.html` | Self-registration form |
| `forgot_password.html` | Password reset request form |
| `reset_password.html` | Password reset form (token-based) |
| `dashboard.html` | Main dashboard: quick links to all sections |
| `chat.html` | Free-text LLM chat; message history HTMX-swapped |
| `_chat_messages.html` | Chat messages partial (returned by `POST /chat/send`) |
| `notes.html` | Notes list + inline editor |
| `_note_list.html` | Notes list partial (HTMX refresh) |
| `_note_editor.html` | HTMX note editor partial |
| `calendar.html` | Calendar month grid + event list + NL add form |
| `contacts.html` | Contacts list + create/edit form |
| `docs.html` | Document list: upload, rename inline, share toggle, delete |
| `mail.html` | Digest text + IMAP settings + Refresh button |
| `voice.html` | Voice orb UI: record button, waveform, TTS playback |
| `profile.html` | Profile: name, username, Telegram link |
| `settings.html` | Language selector + change password |
| `admin.html` | Admin: user list, approve/block, LLM switcher, voice opts, changelog |
| `dynamic.html` | Screen DSL dynamic renderer (used by `/screen/{screen_id}`) |

### 17.6 PWA Support

`static/manifest.json` provides PWA metadata:

| Field | Value |
|---|---|
| `name` | `"Taris Bot"` |
| `short_name` | `"Pico"` |
| `theme_color` | `"#7c4dff"` |
| `display` | `"standalone"` |
| `start_url` | `"/"` |
| `shortcuts` | Chat, Voice, Notes |

---

## 18. Screen DSL & Multi-Channel Rendering

### 18.1 Architecture Concept

The Screen DSL enables **write-once, render-anywhere** UI logic. Action functions in `bot_actions.py` describe *what* to show; renderers describe *how* for each channel.

```
Action request (e.g. "show notes list")
    │
    ▼
bot_actions.py → action_note_list(ctx) → Screen(
    title="My Notes",
    widgets=[
        Card(title=note.title, subtitle=note.mtime),
        Button(label="➕ New Note", action="note_create"),
        Button(label="🔙 Menu", action="menu"),
    ]
)
    │
    ├── render_telegram.py → InlineKeyboardMarkup + send_message()
    │
    └── bot_web.py (Jinja2) → notes.html template renders the same Screen object
```

### 18.2 Screen DSL Dataclasses (`bot_ui.py`)

| Class | Purpose |
|---|---|
| `UserContext` | Caller identity: `chat_id`, `lang`, `is_admin` |
| `Screen` | Top-level container: `title`, `body`, `widgets`, `parse_mode` |
| `Button` | Single action button: `label`, `action` (callback key), `url` |
| `ButtonRow` | Horizontal group of `Button`s |
| `Card` | Information card: `title`, `subtitle`, `body` |
| `TextInput` | Prompt for text input (ForceReply in Telegram; `<input>` in Web) |
| `Toggle` | Boolean toggle: `label`, `key`, `value` |
| `AudioPlayer` | Playback widget: `url` or `ogg_bytes`, `caption` |
| `MarkdownBlock` | Pre-formatted Markdown content |
| `Spinner` | Loading indicator (shown while async op runs) |
| `Confirm` | Yes/No confirmation: `message`, `confirm_action`, `cancel_action` |
| `Redirect` | Immediately redirect to another action |

### 18.3 Action Handlers (`bot_actions.py`)

| Function | Returns |
|---|---|
| `action_menu(ctx)` | Dashboard Screen with all menu buttons |
| `action_note_list(ctx)` | Notes list with per-note open/edit/delete buttons |
| `action_note_view(ctx, slug)` | Note detail: title, body (Markdown), action buttons |

### 18.4 Widget Rendering

**Telegram renderer (`render_telegram.py`):**

| Widget type | Telegram output |
|---|---|
| `Card` | Formatted text block in message body |
| `Button` / `ButtonRow` | `InlineKeyboardButton` row |
| `Toggle` | `InlineKeyboardButton` with ✅/⬜ prefix |
| `TextInput` | `bot.send_message(…, reply_markup=ForceReply())` |
| `AudioPlayer` | `bot.send_voice(…, ogg_bytes)` |
| `Spinner` | `bot.send_message("⏳ …")` — edited on completion |
| `Confirm` | Two-button ✅/❌ keyboard |
| `Redirect` | Immediately calls the target action handler |

**Web renderer (Jinja2 + HTMX):**

| Widget type | HTML output |
|---|---|
| `Card` | `<article>` with header + body |
| `Button` | `<a hx-post="…" hx-target="#content">` |
| `Toggle` | `<input type="checkbox" hx-post="…">` |
| `Spinner` | `<span aria-busy="true">` (Pico CSS spinner) |

### 18.5 Adding a New Screen

1. **Add action function in `bot_actions.py`:**
   ```python
   def action_my_feature(ctx: UserContext, **kwargs) -> Screen:
       return Screen(
           title="My Feature",
           widgets=[
               Card(title="Some info", body="Details here"),
               Button(label="🔙 Back", action="menu"),
           ]
       )
   ```

2. **Wire up in Telegram** (`telegram_menu_bot.py` callback dispatcher):
   ```python
   elif data == "my_feature":
       from render_telegram import render_screen
       from bot_actions import action_my_feature
       ctx = UserContext(chat_id=cid, lang=_lang(cid), is_admin=_is_admin(cid))
       render_screen(cid, action_my_feature(ctx), bot)
   ```

3. **Wire up in Web UI** (`bot_web.py`):
   ```python
   @app.get("/my-feature")
   async def my_feature_page(user=Depends(get_current_user)):
       ctx = UserContext(chat_id=user.chat_id, lang=user.lang, is_admin=user.is_admin)
       screen = action_my_feature(ctx)
       return templates.TemplateResponse("feature.html", {"screen": screen})
   ```

4. **Add Menu button** in `action_menu()` in `bot_actions.py`.

5. **Update `doc/bot-code-map.md`** callback key table.

**Rules:**
- **Never** call Telegram API directly from `bot_actions.py` — it must stay channel-agnostic.
- Each `Button.action` must map to a callback key in the Telegram dispatcher **and** a URL in the Web UI.
