# Taris Bot — Developer Patterns & Conventions

This document describes the exact patterns used across the taris codebase.
The bot is split into 20 modules (`bot_*.py`, `render_telegram.py`, `bot_web.py`, etc.).
Follow these patterns precisely when adding features to keep the codebase consistent.

---

## 1. Adding a Voice Opt Toggle

Voice opts are feature flags that persist in `~/.taris/voice_opts.json`.
All default to `False` so existing behaviour is never changed.

### Step 1 — Add constant (if the opt needs a path/binary)

```python
# after PIPER_MODEL_LOW / WHISPER_MODEL lines (~237)
MY_THING_BIN = os.environ.get("MY_THING_BIN", "/usr/local/bin/my-thing")
```

### Step 2 — Add to `_VOICE_OPTS_DEFAULTS` (~line 263)

```python
_VOICE_OPTS_DEFAULTS: dict = {
    ...
    "my_opt": False,   # §X.Y: one-line description
}
```

### Step 3 — Add toggle row in `_handle_voice_opts_menu()` (~line 1091)

```python
opts_rows = [
    ...
    ("my_opt", f"{_flag('my_opt')}  My feature description  ·  −Xs something"),
]
```

`_flag(key)` returns `"✅"` / `"⬜"` based on `_voice_opts[key]`.

### Step 4 — Handle startup side-effect in `_handle_voice_opt_toggle()` (~line 1132)

Only needed if the opt starts/stops a background process:

```python
if key == "my_opt":
    if _voice_opts[key]:
        threading.Thread(target=_start_my_thing, daemon=True).start()
    else:
        threading.Thread(target=_stop_my_thing, daemon=True).start()
```

### Step 5 — Handle startup side-effect in `main()` (~line 2690)

```python
if _voice_opts.get("my_opt"):
    log.info("[VoiceOpt] my_opt enabled — starting background thing")
    threading.Thread(target=_start_my_thing, daemon=True).start()
```

### Step 6 — Use the opt in the voice pipeline

```python
# In _handle_voice_message() or a helper it calls:
if _voice_opts.get("my_opt"):
    result = _do_my_thing(data)
```

---

## 2. Adding a Callback Handler

The bot uses a single dispatcher `handle_callback(call)`. Every inline button action is a string `data=`.

### Step 1 — Create a handler function

```python
def _handle_my_feature(chat_id: int) -> None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(chat_id, "back"), callback_data="menu")],
    ])
    bot.send_message(chat_id, "My feature content", reply_markup=keyboard)
```

### Step 2 — Add button to a keyboard

```python
# In _menu_keyboard() or _admin_keyboard() etc.
InlineKeyboardButton("My Feature", callback_data="my_feature")
```

### Step 3 — Add dispatch branch in `handle_callback(call)`

```python
elif data == "my_feature":
    if not _is_allowed(chat_id): return _deny(chat_id)
    _handle_my_feature(chat_id)
```

For parametrised callbacks use `startswith`:

```python
elif data.startswith("my_feature_"):
    slug = data[len("my_feature_"):]
    _handle_my_feature_item(chat_id, slug)
```

---

## 3. Adding a Multi-Step Input Flow

Some features require multiple text inputs (e.g., note creation: title → content).
The state is stored in `_pending_note[chat_id]` (or add a new `dict[int, ...]` global).

### Pattern

```python
# State dict — defined at top of file with other globals
_pending_foo: dict[int, dict] = {}

def _start_foo_step1(chat_id: int) -> None:
    _pending_foo[chat_id] = {"step": "name"}
    bot.send_message(chat_id, "Enter name:")

def _finish_foo(chat_id: int, text: str) -> None:
    state = _pending_foo.pop(chat_id, {})
    step = state.get("step")
    if step == "name":
        # ... store name, move to step 2 or finish
        pass
```

In `handle_message()`, check pending state BEFORE routing to chat/system:

```python
if chat_id in _pending_foo:
    return _finish_foo(chat_id, text)
```

---

## 4. i18n / String Lookup Pattern

All user-visible text must be in `src/strings.json` under both `"ru"` and `"en"` keys.

### strings.json structure

```json
{
  "ru": {
    "my_feature_title": "Мой функционал",
    "my_feature_body":  "Данные: {value}"
  },
  "en": {
    "my_feature_title": "My Feature",
    "my_feature_body":  "Data: {value}"
  }
}
```

### Usage in code

```python
title = _t(chat_id, "my_feature_title")
body  = _t(chat_id, "my_feature_body", value=42)
```

`_t()` does `strings[lang][key].format(**kwargs)`, falls back to key name if missing.

---

## 5. Admin vs User Access Guard Pattern

Always check access at the top of every handler:

```python
def _handle_something(chat_id: int) -> None:
    if not _is_allowed(chat_id):
        return _deny(chat_id)
    ...

def _handle_admin_something(chat_id: int) -> None:
    if not _is_admin(chat_id):          # stricter — admin-only
        return _deny(chat_id)
    ...
```

In `handle_callback`:
```python
elif data == "something":
    if not _is_allowed(chat_id): return _deny(chat_id)
    _handle_something(chat_id)
```

---

## 6. Versioning & Release Notes

### Version format: `YYYY.M.D` (no zero-padding)

```python
BOT_VERSION = "2026.3.19"
```

### release_notes.json — prepend, never append

```json
[
  {
    "version": "2026.3.19",
    "date":    "2026-03-19",
    "title":   "Short name",
    "notes":   "- Item 1\n- Item 2"
  },
  ...older entries...
]
```

**JSON escape rules:**
- Never use `\_` in JSON — it is not a valid escape. Use plain `_`.
- Use `\n` for newlines inside `"notes"` strings.
- Validate with `python3 -c "import json, sys; json.load(sys.stdin)" < src/release_notes.json`

---

## 7. Subprocess / Shell Command Pattern

All subprocesses go through `_run_subprocess(cmd, timeout, env)`:

```python
out, rc = _run_subprocess(
    ["/usr/bin/picoclaw", "agent", "-m", prompt],
    timeout=60,
    env={**os.environ, "EXTRA_VAR": "value"},
)
if rc != 0:
    log.warning(f"[MyFeature] exit {rc}: {out[:120]}")
```

**Never** use `os.system()` or `subprocess.run()` directly — always `_run_subprocess`.

---

## 8. Telegram Message Edit Pattern

To update an existing message (e.g., after an action):

```python
_safe_edit(chat_id, call.message.message_id, new_text,
           reply_markup=new_keyboard, parse_mode="Markdown")
```

`_safe_edit` suppresses `telebot.apihelper.ApiTelegramException` for "message is not modified".

---

## 9. Per-User Session State Pattern

Use module-level dicts keyed by `chat_id`:

```python
# At top of file, with other session state dicts:
_my_state: dict[int, SomeType] = {}

# Clear state when done:
_my_state.pop(chat_id, None)
```

Never use class instances — the bot is single-threaded sequential handlers.

---

## 10. Deploying After Changes

### Full deploy (all bot modules — required for first-time or major refactor)

```bat
pscp -pw "%HOSTPWD%" src\bot_config.py src\bot_state.py src\bot_instance.py stas@OpenClawPI:/home/stas/.taris/
pscp -pw "%HOSTPWD%" src\bot_access.py src\bot_users.py src\bot_voice.py    stas@OpenClawPI:/home/stas/.taris/
pscp -pw "%HOSTPWD%" src\bot_admin.py  src\bot_handlers.py                  stas@OpenClawPI:/home/stas/.taris/
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py                                stas@OpenClawPI:/home/stas/.taris/
pscp -pw "%HOSTPWD%" src\release_notes.json  src\strings.json                stas@OpenClawPI:/home/stas/.taris/
```

### Incremental deploy (only changed files)

```bat
rem Example: only bot_admin.py + release notes changed
pscp -pw "%HOSTPWD%" src\bot_admin.py stas@OpenClawPI:/home/stas/.taris/
pscp -pw "%HOSTPWD%" src\release_notes.json stas@OpenClawPI:/home/stas/.taris/
```

### Restart and verify

```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S systemctl restart taris-telegram && sleep 3 && journalctl -u taris-telegram -n 12 --no-pager"
```

Expected log after clean start:
```
[INFO] Version      : 2026.X.Y
[INFO] Polling Telegram…
```

**Service restart is REQUIRED** after every deploy. The bot does not hot-reload.

---

## 11. Adding a New Source File

All target-side sources belong in `src/`. Never in `.credentials/` or root.

| Type | Location |
|---|---|
| Python scripts (run on Pi) | `src/` |
| Shell setup scripts | `src/setup/` |
| Systemd service units | `src/services/` |
| Hardware / diagnostic tests | `src/tests/` |

When adding a `.service` file, deploy it in the same operation:
```bat
pscp -pw "%HOSTPWD%" src\services\taris-new.service stas@OpenClawPI:/tmp/
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S cp /tmp/taris-new.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now taris-new"
```

---

## 12. Voice Opt `_piper_model_path()` Priority Chain

```
tmpfs_model enabled AND /dev/shm/piper/... exists → use tmpfs path  (fastest)
    ↓ else
piper_low_model enabled AND ~/.taris/ru_RU-irina-low.onnx exists → use low model
    ↓ else
default → ~/.taris/ru_RU-irina-medium.onnx
```

When adding a new model priority level, insert it between the existing checks
in `_piper_model_path()` (line 1726).

---

## 13. TODO.md Maintenance

- Planned work: `🔲 Planned`
- In-progress: `🔄 In progress`
- Complete: collapse all `[x]` bullets into `✅ Implemented (vX.Y.Z)` — one line only
- Update TODO.md **in the same session** as implementing the feature
- Check TODO.md at session start to understand current state

---

## 14. Adding a Calendar Feature

All new calendar operations follow this pattern: **prompt → LLM parse → confirmation card → execute**.

### Add a new calendar action (e.g. "duplicate event")

**Step 1 — Handler function in `bot_calendar.py`**

```python
def _handle_cal_my_action(chat_id: int, ev_id: str) -> None:
    lang   = _st._user_lang.get(chat_id, "ru")
    events = _cal_load(chat_id)
    ev     = next((e for e in events if e.get("id") == ev_id), None)
    if not ev:
        _handle_calendar_menu(chat_id)
        return
    # ... build confirmation card ...
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Confirm" if lang == "en" else "✅ Подтвердить",
                             callback_data=f"cal_my_action_confirm:{ev_id}"),
        InlineKeyboardButton("❌ Cancel"  if lang == "en" else "❌ Отмена",
                             callback_data="menu_calendar"),
    )
    bot.send_message(chat_id, "...", reply_markup=kb)

def _handle_cal_my_action_confirmed(chat_id: int, ev_id: str) -> None:
    # ... actual mutation ...
    _handle_calendar_menu(chat_id)
```

**Step 2 — Button in `_cal_event_keyboard()`**

```python
kb.add(InlineKeyboardButton(
    "⬛  " + ("Моя функция" if lang == "ru" else "My action"),
    callback_data=f"cal_my_action:{ev_id}",
))
```

**Step 3 — Callbacks in `telegram_menu_bot.py`**

```python
elif data.startswith("cal_my_action:"):
    if not _is_guest(cid):
        _handle_cal_my_action(cid, data[len("cal_my_action:"):])

elif data.startswith("cal_my_action_confirm:"):
    if not _is_guest(cid):
        _handle_cal_my_action_confirmed(cid, data[len("cal_my_action_confirm:"):])
```

**Step 4 — Update imports in `telegram_menu_bot.py`**

```python
from bot_calendar import (
    ...,
    _handle_cal_my_action, _handle_cal_my_action_confirmed,
)
```

**Step 5 — Update `doc/bot-code-map.md` callback key table**

```markdown
| `cal_my_action:<id>`         | `_handle_cal_my_action`           |
| `cal_my_action_confirm:<id>` | `_handle_cal_my_action_confirmed` |
```

### Multi-event batch state shape (`_pending_cal`)

```python
# Single confirm (step "confirm")
_pending_cal[chat_id] = {
    "step":              "confirm",
    "title":             "Meeting",
    "dt_iso":            "2026-04-01T10:00",
    "remind_before_min": 15,
}

# Multi-event confirm (step "multi_confirm")
_pending_cal[chat_id] = {
    "step":   "multi_confirm",
    "events": [
        {"title": "Meeting", "dt_iso": "2026-04-01T10:00", "remind_before_min": 15},
        {"title": "Doctor",  "dt_iso": "2026-04-01T15:00", "remind_before_min": 15},
    ],
    "idx": 0,   # index of event currently being confirmed
}
```

### NL date range query pattern

```python
_handle_calendar_query(chat_id, user_text)
# LLM returns {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "label": "..."}
# Falls back to: from=today, to=today+7, label="next 7 days"
```

### Console intent classification pattern

```python
# LLM prompt returns one of:
{"intent": "add"}
{"intent": "query"}
{"intent": "delete", "ev_id": "<id or empty>"}
{"intent": "edit",   "ev_id": "<id or empty>"}
# Unknown ev_id → _cal_find_by_text(chat_id, user_text) for fuzzy title match
```

---

## 15. Screen DSL Pattern

The Screen DSL (`bot_ui.py` + `bot_actions.py` + `render_telegram.py`) enables write-once, render-anywhere UI logic. Action handlers return `Screen` objects; renderers convert them to channel-specific output.

### Define a screen in `bot_actions.py`

```python
from bot_ui import Screen, Card, Button, ButtonRow, UserContext

def action_my_feature(ctx: UserContext, **kwargs) -> Screen:
    return Screen(
        title="My Feature",
        widgets=[
            Card(title="Some info", subtitle="2026-04-01", body="Details here"),
            ButtonRow(buttons=[
                Button(label="✅ Do it",  action="my_feature_confirm"),
                Button(label="🔙 Back",   action="menu"),
            ]),
        ],
    )
```

### Render in Telegram (`telegram_menu_bot.py` callback dispatcher)

```python
elif data == "my_feature":
    from render_telegram import render_screen
    from bot_actions import action_my_feature
    ctx = UserContext(chat_id=cid, lang=_lang(cid), is_admin=_is_admin(cid))
    render_screen(action_my_feature(ctx), cid, bot)
```

### Render in Web UI (`bot_web.py`)

```python
@app.get("/my-feature")
async def my_feature_page(request: Request, user=Depends(get_current_user)):
    from bot_actions import action_my_feature
    from bot_ui import UserContext
    ctx = UserContext(chat_id=user.chat_id, lang=user.lang, is_admin=user.is_admin)
    screen = action_my_feature(ctx)
    return templates.TemplateResponse("my_feature.html",
                                      {"request": request, "screen": screen, "user": user})
```

### Widget → Telegram mapping (from `render_telegram.py`)

| Widget | Telegram output |
|---|---|
| `Card` | Formatted text block in message body |
| `Button` / `ButtonRow` | `InlineKeyboardButton` row |
| `Toggle` | `InlineKeyboardButton` with ✅/⬜ prefix |
| `TextInput` | `bot.send_message(reply_markup=ForceReply())` |
| `AudioPlayer` | `bot.send_voice(ogg_bytes)` |
| `Spinner` | `bot.send_message("⏳ …")` — edited on completion |
| `Confirm` | Two-button ✅/❌ keyboard |
| `Redirect` | Immediately calls the target action handler |

### Rules

- **Never** call Telegram API directly from `bot_actions.py` — it must stay channel-agnostic.
- Each `Button.action` must map to a callback key in the Telegram dispatcher **and** a URL in the Web UI.
- Add new `Screen` dataclass variants to `bot_ui.py` only if no existing widget satisfies the need.

---

## 16. Adding a Web UI Route

### Full page route (Jinja2 template)

```python
# In bot_web.py — at the end of the route roster
@app.get("/my-feature")
async def my_feature_page(request: Request, user=Depends(get_current_user)):
    """Full page render — navigated to directly."""
    ctx = _make_ctx(user)          # helper already defined in bot_web.py
    screen = action_my_feature(ctx)
    return templates.TemplateResponse(
        "my_feature.html",
        {"request": request, "screen": screen, "user": user},
    )
```

### HTMX partial route (returns HTML fragment, no full page)

```python
@app.post("/my-feature/action")
async def my_feature_action(request: Request,
                             ev_id: str = Form(...),
                             user=Depends(get_current_user)):
    """HTMX partial — replaces a div, no page reload."""
    # ... do the work ...
    return templates.TemplateResponse(
        "_my_feature_result.html",           # name starts with _ by convention
        {"request": request, "result": result},
    )
```

### Auth guard

Every protected route uses the `Depends(get_current_user)` FastAPI dependency (defined in `bot_web.py`). It reads the `taris_token` JWT cookie and raises `401` on failure. Admin-only routes additionally check `user.is_admin`:

```python
@app.post("/admin/my-admin-action")
async def admin_action(request: Request, user=Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    # ...
```

### Template convention

- Full-page templates: `src/templates/<feature>.html` — extend `base.html`
- HTMX partials: `src/templates/_<feature>_<variant>.html` — standalone fragment (no `{% extends %}`)
- Add a nav link in `base.html` for any new top-level page visible in the sidebar
- HTMX swap target: `hx-target="#content"` on interactive elements inside `base.html`'s main area

### Checklist

1. Add route(s) to `bot_web.py`
2. Create template file(s) in `src/templates/`
3. Add nav entry to `base.html` if this is a top-level page
4. Add corresponding Playwright test in `src/tests/ui/test_ui.py` (at minimum: page loads, no 500)
5. Update `doc/bot-code-map.md` route inventory table

---

## 17. Telegram ↔ Web Shared Action Pattern

When a feature must appear in **both** Telegram and the Web UI, put all logic in `bot_actions.py` and render it in each channel separately.

### Decision guide

| Where does the logic go? | When |
|---|---|
| `bot_actions.py` + `Screen` DSL | Any UI state that both channels show |
| `bot_handlers.py` (Telegram only) | Voice pipeline, ForceReply multi-step flows |
| `bot_calendar.py` / `bot_notes.py` etc. | Domain-specific mutations (data layer) |
| `bot_web.py` (Web only) | HTMX fragments, file uploads, OAuth2 flow |

### Implementation steps

**Step 1 — Write the action handler in `bot_actions.py`**

```python
def action_my_shared_feature(ctx: UserContext, slug: str = "") -> Screen:
    # pure logic — no Telegram API, no HTTP response
    data = _load_my_data(ctx.chat_id, slug)     # from bot_users, bot_calendar, etc.
    return Screen(
        title=_t_str(ctx.lang, "my_feature_title"),
        widgets=[
            Card(title=data["title"], body=data["body"]),
            ButtonRow(buttons=[Button(label="🔙", action="menu")]),
        ],
    )
```

**Step 2 — Telegram callback dispatch in `telegram_menu_bot.py`**

```python
elif data.startswith("my_shared:"):
    slug = data[len("my_shared:"):]
    ctx  = UserContext(chat_id=cid, lang=_lang(cid), is_admin=_is_admin(cid))
    render_screen(action_my_shared_feature(ctx, slug=slug), cid, bot)
```

**Step 3 — Web route in `bot_web.py`**

```python
@app.get("/my-shared/{slug}")
async def my_shared_page(slug: str, request: Request, user=Depends(get_current_user)):
    ctx    = _make_ctx(user)
    screen = action_my_shared_feature(ctx, slug=slug)
    return templates.TemplateResponse("my_shared.html",
                                      {"request": request, "screen": screen})
```

**Step 4 — Template: iterate `screen.widgets` in Jinja2**

```html
{# src/templates/my_shared.html #}
{% extends "base.html" %}
{% block content %}
  <h2>{{ screen.title }}</h2>
  {% for widget in screen.widgets %}
    {% if widget.__class__.__name__ == 'Card' %}
      <article><h3>{{ widget.title }}</h3><p>{{ widget.body }}</p></article>
    {% elif widget.__class__.__name__ == 'ButtonRow' %}
      <div class="grid">
        {% for btn in widget.buttons %}
          <a href="{{ btn.url or ('#' + btn.action) }}">{{ btn.label }}</a>
        {% endfor %}
      </div>
    {% endif %}
  {% endfor %}
{% endblock %}
```

**Step 5 — Add strings to `strings.json`**

All title/label strings must exist in `ru`, `en`, and `de`. Use `_t(chat_id, key)` in Telegram code and `{{ t("key") }}` (or equivalent) in Jinja2 templates.

---

## 18. Password Reset Pattern

Password management follows a **role-aware** model:
- Any user can reset their **own** password via the Web UI settings page.
- Admin can reset **any** user's password via the Web admin panel **or** via the Telegram admin panel.

### Core function — `bot_auth.py`

```python
change_password(user_id: str, new_password: str) -> bool
# Re-hashes with bcrypt, updates accounts.json, returns True if user_id found.
```

### Web UI — user self-service (already wired)

`POST /settings/password` in `bot_web.py` — requires `current_password` verification first:

```python
@app.post("/settings/password")
async def change_own_password(request: Request,
                               current_password: str = Form(...),
                               new_password: str     = Form(...),
                               user=Depends(get_current_user)):
    account = find_account_by_id(user.user_id)
    if not verify_password(account, current_password):
        return templates.TemplateResponse("settings.html",
            {"request": request, "error": "Current password incorrect", "user": user})
    change_password(user.user_id, new_password)
    return RedirectResponse("/settings", status_code=303)
```

### Web UI — admin reset (route to add in `bot_web.py`)

```python
@app.post("/admin/user/{user_id}/reset-password")
async def admin_reset_password(user_id: str,
                                new_password: str = Form(...),
                                user=Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403)
    ok = change_password(user_id, new_password)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return templates.TemplateResponse("_admin_user_row.html",
                                      {"request": Request, "message": "Password reset"})
```

### Telegram — admin reset (pattern for `bot_admin.py` + dispatcher)

**Step 1 — Add to admin keyboard**

```python
# In _admin_keyboard() in bot_admin.py
InlineKeyboardButton("🔑 Reset password", callback_data="admin_reset_pw_menu")
```

**Step 2 — Handler function in `bot_admin.py`**

```python
def _start_admin_reset_password(chat_id: int) -> None:
    """Show user list with 'reset pw' buttons for each approved web account."""
    from bot_auth import list_accounts
    accounts = [a for a in list_accounts() if a["role"] != "admin" or True]  # show all
    if not accounts:
        bot.send_message(chat_id, "No web accounts found.")
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for acc in accounts:
        kb.add(InlineKeyboardButton(
            f"🔑 {acc['username']} ({acc['role']})",
            callback_data=f"admin_reset_pw:{acc['id']}",
        ))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_menu"))
    bot.send_message(chat_id, "Select account to reset password:", reply_markup=kb)

def _start_admin_reset_pw_input(admin_id: int, target_user_id: str) -> None:
    """Prompt admin for new password."""
    _pending_reset_pw[admin_id] = {"target_id": target_user_id}
    bot.send_message(admin_id, "Enter new password for the selected account:")

def _finish_admin_reset_password(admin_id: int, new_pw: str) -> None:
    """Apply the password change."""
    state = _pending_reset_pw.pop(admin_id, {})
    from bot_auth import change_password
    ok = change_password(state["target_id"], new_pw)
    msg = "✅ Password changed." if ok else "❌ User not found."
    bot.send_message(admin_id, msg)
    _handle_admin_menu(admin_id)
```

**Step 3 — Module-level state dict in `bot_admin.py`**

```python
_pending_reset_pw: dict[int, dict] = {}   # admin_chat_id → {target_id: str}
```

**Step 4 — Dispatch in `telegram_menu_bot.py`**

```python
elif data == "admin_reset_pw_menu":
    if _is_admin(cid): _start_admin_reset_password(cid)

elif data.startswith("admin_reset_pw:"):
    if _is_admin(cid): _start_admin_reset_pw_input(cid, data[len("admin_reset_pw:"):])
```

In the text handler, before mode-routing:

```python
if cid in _pending_reset_pw:
    return _finish_admin_reset_password(cid, text)
```

**Step 5 — User self-service via Telegram (optional)**

Add a `🔑 Change password` button to the Profile screen. The flow follows the Web UI self-service model: prompt current password → prompt new password → `change_password(user_id, new_pw)`. Both prompts use `ForceReply` and `_pending_pw_change[chat_id]` session state.

### Security rules

- Minimum password length: 8 characters (enforce in `change_password()` or caller)
- Admin cannot change their own password via the admin reset route — only via the settings route (forces current-password check)
- Log every password reset to `telegram_bot.log` with admin's chat_id + target account username (never log the password itself)

---

## 19. YAML Screen File Format (Declarative Screen DSL)

Screen definitions can be written as YAML (or JSON) files in `src/screens/`. The loader module `src/ui/screen_loader.py` parses these files into the same `Screen` dataclass objects used by the programmatic approach (§15), so both Telegram and Web renderers work unchanged.

**When to use YAML screens:** Static or semi-static UI — menus, help pages, profile views, note detail cards. Any screen whose layout is fixed and whose content varies only through i18n keys or variable substitution.

**When to keep programmatic screens:** Complex multi-step flows (calendar add/edit, mail setup wizard) where control flow depends on runtime state. These remain in `bot_actions.py` or their feature module.

### 19.1 File Location & Format

```
src/screens/
  main_menu.yaml       ← main user menu
  admin_menu.yaml      ← admin panel menu
  help.yaml            ← role-filtered help text
  notes_menu.yaml      ← notes submenu
  note_view.yaml       ← single note detail
  note_raw.yaml        ← raw text view
  note_edit.yaml       ← note edit options
  profile.yaml         ← user profile card
  profile_lang.yaml    ← language selection
  profile_my_data.yaml ← stored data summary
```

Both YAML (requires `pyyaml`) and JSON (stdlib) are supported. YAML is preferred for readability. If `pyyaml` is not installed, only `.json` files can be loaded.

### 19.2 Screen-Level Properties

```yaml
# Required
widgets:              # list of widget objects (see §19.4)
  - type: button_row
    ...

# Title — one of:
title: "📄 My Screen"             # literal text (may contain {variables})
title_key: my_screen_title         # i18n key resolved via t_func

# Optional
parse_mode: Markdown               # "Markdown" (default) | "HTML" | null (plain text)
ephemeral: false                   # default false; if true, message is auto-deleted
```

### 19.3 i18n Key Resolution

Every text-bearing property has two variants: a literal and a `_key` form.

| Literal | i18n key variant | Resolution |
|---|---|---|
| `title` | `title_key` | Screen title |
| `label` | `label_key` | Button label, toggle label, spinner text |
| `text` | `text_key` | Markdown body, card body, confirm message |

The `_key` variant is resolved via the `t_func(lang, key)` callback passed to `load_screen()`. If `t_func` is `None` or the key is absent, the raw key string is returned as fallback.

```yaml
# i18n — key looked up in strings.json
- type: button_row
  buttons:
    - label_key: btn_chat        # → _t(lang, "btn_chat") → "💬 Chat"
      action: mode_chat

# Literal — used as-is
- type: markdown
  text: "Welcome to taris!"
```

### 19.4 Widget Reference

#### `button_row` — Horizontal row of buttons

```yaml
- type: button_row
  visible_roles: [admin]          # optional — RBAC filter
  buttons:
    - label_key: btn_admin        # i18n key
      action: admin_menu          # callback data string
      style: primary              # optional: "primary" | "danger"
    - label: "🔗 Website"        # literal label
      url: "https://example.com"  # external URL (instead of action)
```

Each button in the `buttons` array can have its own `visible_roles` / `visible_if`.

#### `card` — Information card

```yaml
- type: card
  title: "{user_name}"           # variable substitution
  title_key: profile_title       # OR i18n key (title_key takes priority)
  body: "Role: {role}"
  body_key: profile_body         # OR i18n key
  action: profile                # optional tap action
```

#### `markdown` — Pre-formatted Markdown block

```yaml
- type: markdown
  text_key: help_text_admin      # i18n key
  visible_roles: [admin]         # only shown to admins
```

Or with literal text:

```yaml
- type: markdown
  text: "\n{note_content}"       # variable substitution
```

#### `text_input` — Prompt for user text

```yaml
- type: text_input
  placeholder: "Enter title..."
  placeholder_key: note_title_prompt  # OR i18n key
  action: note_create_title           # callback on submit
```

#### `toggle` — Boolean switch

```yaml
- type: toggle
  label_key: opt_silence_strip
  key: silence_strip             # voice opt key
  value: true                    # current state
```

#### `audio_player` — Audio playback widget

```yaml
- type: audio_player
  src: "/voice/tts/latest.ogg"
  caption: "Voice reply"
  caption_key: voice_reply_caption   # OR i18n key
```

#### `spinner` — Loading indicator

```yaml
- type: spinner
  label_key: loading              # i18n key
```

#### `confirm` — Yes/No confirmation gate

```yaml
- type: confirm
  text: "Delete this note?"
  text_key: confirm_delete        # OR i18n key
  action_yes: "note_delete_confirmed:{slug}"
  action_no: menu_notes
```

#### `redirect` — Immediate redirect to another action

```yaml
- type: redirect
  target: menu                    # callback key to dispatch
```

### 19.5 Variable Substitution

Any `{var_name}` pattern in text, title, label, or action strings is replaced with the value from the `variables` dict passed to `load_screen()`.

```yaml
title: "📄 *{note_title}*"
widgets:
  - type: button_row
    buttons:
      - label_key: btn_edit
        action: "note_edit:{slug}"      # slug is substituted at render time
```

```python
screen = load_screen(
    "screens/note_view.yaml",
    user=ctx,
    variables={"slug": "my_note", "note_title": "My Note", "note_content": "..."},
    t_func=_t_by_lang,
)
```

### 19.6 Visibility Rules

Two mechanisms control whether a widget is rendered:

**Role-based (`visible_roles`)** — widget shown only if `user.role` matches:

```yaml
- type: button_row
  visible_roles: [admin]          # only admin sees this row
  buttons:
    - label_key: btn_admin
      action: admin_menu
```

**Condition-based (`visible_if`)** — widget shown only if a variable with that name is truthy:

```yaml
- type: markdown
  text_key: notes_empty_hint
  visible_if: "no_notes"          # shown only when variables["no_notes"] is truthy
```

Both can be applied to individual buttons within a `button_row`, not just the row itself.

### 19.7 Schema Validation

Screen files are validated against `src/screens/screen.schema.json` (JSON Schema draft-07) at load time. Validation requires the `jsonschema` package; if absent, validation is silently skipped.

- Validation errors produce `log.warning()` messages but **never crash** the loader.
- The schema enforces `additionalProperties: false` on all widgets — typos in property names are caught.
- The schema is lazy-loaded and cached in memory.

### 19.8 API Reference (`screen_loader.py`)

#### `load_screen(path, user, variables=None, t_func=None) → Screen`

Main entry point. Loads a YAML/JSON file, resolves i18n keys and variables, filters widgets by visibility, and returns a `Screen` dataclass.

| Parameter | Type | Description |
|---|---|---|
| `path` | `str` | Relative path to screen file (e.g. `"screens/help.yaml"`) |
| `user` | `UserContext` | Caller identity — `chat_id`, `lang`, `role`, `is_admin` |
| `variables` | `dict[str, Any]` | Optional variable substitution map |
| `t_func` | `Callable[[str, str], str]` | Optional i18n function: `t_func(lang, key) → text` |

#### `load_all_screens(directory) → dict[str, dict]`

Pre-load all YAML/JSON files in a directory. Returns raw parsed data (not `Screen` objects). Useful for startup cache warming.

#### `reload_screens() → None`

Clears the internal `_screen_cache`. Call after editing screen files for hot-reload without restarting.

### 19.9 Wiring a YAML Screen — Telegram + Web

**Telegram callback dispatcher** (`telegram_menu_bot.py`):

```python
elif data == "help":
    from ui.screen_loader import load_screen
    from ui.render_telegram import render_screen
    ctx = UserContext(chat_id=cid, lang=_lang(cid), is_admin=_is_admin(cid))
    screen = load_screen("screens/help.yaml", ctx, t_func=_t_by_lang)
    render_screen(screen, cid, bot)
```

**Web route** (`bot_web.py`):

```python
@app.get("/screen/{screen_id}")
async def dynamic_screen(screen_id: str, request: Request, user=Depends(get_current_user)):
    from ui.screen_loader import load_screen
    ctx = _make_ctx(user)
    screen = load_screen(f"screens/{screen_id}.yaml", ctx, t_func=_t_by_lang)
    return templates.TemplateResponse("dynamic.html",
                                      {"request": request, "screen": screen, "user": user})
```

**Admin hot-reload** (Telegram):

```python
elif data == "reload_screens":
    if _is_admin(cid):
        from ui.screen_loader import reload_screens
        reload_screens()
        bot.send_message(cid, "✅ Screens reloaded")
```

### 19.10 Complete Example — `main_menu.yaml`

```yaml
title_key: choose
parse_mode: Markdown

widgets:
  - type: button_row
    buttons:
      - label_key: btn_digest
        action: digest

  - type: button_row
    buttons:
      - label_key: btn_chat
        action: mode_chat

  - type: button_row
    visible_roles: [admin]
    buttons:
      - label_key: btn_system
        action: mode_system

  - type: button_row
    visible_roles: [admin, developer, user]
    buttons:
      - label_key: btn_notes
        action: menu_notes

  - type: button_row
    visible_roles: [admin, developer, user]
    buttons:
      - label_key: btn_calendar
        action: menu_calendar

  - type: button_row
    visible_roles: [admin, developer, user]
    buttons:
      - label_key: btn_contacts
        action: menu_contacts

  - type: button_row
    visible_roles: [admin, developer, user]
    buttons:
      - label_key: btn_docs
        action: menu_docs

  - type: button_row
    buttons:
      - label_key: btn_profile
        action: profile

  - type: button_row
    buttons:
      - label_key: btn_help
        action: help

  - type: button_row
    visible_roles: [admin]
    buttons:
      - label_key: btn_error_protocol
        action: errp_start

  - type: button_row
    visible_roles: [admin]
    buttons:
      - label_key: btn_admin
        action: admin_menu
```

### 19.11 Checklist — Adding a New YAML Screen

1. Create `src/screens/my_feature.yaml` following the format above
2. Add all `_key` strings to `src/strings.json` under `ru`, `en`, `de`
3. Wire the Telegram callback in `telegram_menu_bot.py` (see §19.9)
4. Wire the Web route in `bot_web.py` or use the generic `/screen/{screen_id}` route
5. Validate: `python3 -c "from ui.screen_loader import load_screen; print(load_screen('screens/my_feature.yaml', None))"`
6. Update `doc/bot-code-map.md` callback key table if a new callback was added

### 19.12 Hybrid Pattern for Multi-Step Flows

Complex multi-step flows (calendar add/edit, contact wizard, mail setup, error protocol) **cannot be fully expressed in YAML** because they involve LLM calls, IMAP tests, or state machine transitions. Use the **Hybrid Screen Pattern**: YAML defines the layout and text of each step; Python handles the logic and transitions.

→ Full proposal: [`doc/todo/21.6-multistep-yaml-proposal.md`](todo/21.6-multistep-yaml-proposal.md)

**Pattern A — YAML Layout Screen per step:**

```yaml
# screens/cal_confirm.yaml — calendar single-event confirmation card
title: "📅 {event_title}"
parse_mode: Markdown

widgets:
  - type: card
    title: "{event_title}"
    body: "🕒 {event_dt}\n⏰ {remind_text}"

  - type: button_row
    buttons:
      - label_key: cal_btn_save
        action: cal_confirm_save
      - label_key: btn_cancel
        action: menu_calendar
        style: danger
```

```python
def _show_cal_confirm(chat_id: int) -> None:
    state = _pending_cal[chat_id]
    screen = load_screen("screens/cal_confirm.yaml",
        user=_screen_ctx(chat_id),
        variables={
            "event_title": _escape_md(state["title"]),
            "event_dt":    _format_dt(state["dt_iso"]),
            "remind_text": _format_remind(state.get("remind_before_min", 15)),
        },
        t_func=_t_by_lang,
    )
    render_screen(screen, chat_id, bot)
```

**Pattern B — Dynamic List via pre-built Markdown variable:**

For data-driven lists (events, contacts), build the list as a Markdown string in Python and inject it:

```yaml
# screens/cal_menu.yaml
widgets:
  - type: markdown
    text: "{events_list}"
    visible_if: has_events
  - type: markdown
    text_key: cal_no_events
    visible_if: no_events
```

Per-item buttons can be injected by appending `ButtonRow` objects to `screen.widgets` from Python before rendering.

**Rule of thumb:** If it involves I/O, LLM, or flow control → **Python**. If it involves text, layout, or buttons → **YAML**.
