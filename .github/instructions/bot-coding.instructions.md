---
applyTo: "src/*.py,src/bot_*.py,src/strings.json"
---

# Bot Coding Patterns — Skill

Exact patterns for adding features to the taris bot. Always check `doc/bot-code-map.md` first to find the relevant function by name/line.

## Adding a Voice Opt Toggle (6 steps)

```python
# 1. Add constant (~line 237)
MY_THING_BIN = os.environ.get("MY_THING_BIN", "/usr/local/bin/my-thing")

# 2. Add to _VOICE_OPTS_DEFAULTS (~line 263) — always False
_VOICE_OPTS_DEFAULTS: dict = { ..., "my_opt": False }

# 3. Add toggle row in _handle_voice_opts_menu()
("my_opt", f"{_flag('my_opt')}  My feature  ·  −Xs something")

# 4. Handle side-effect in _handle_voice_opt_toggle()
if key == "my_opt":
    threading.Thread(target=_start_my_thing if _voice_opts[key] else _stop_my_thing, daemon=True).start()

# 5. Handle startup in main()
if _voice_opts.get("my_opt"):
    threading.Thread(target=_start_my_thing, daemon=True).start()

# 6. Use the opt in the pipeline
if _voice_opts.get("my_opt"):
    result = _do_my_thing(data)
```

## Adding a Callback Handler (3 steps)

```python
# 1. Handler function
def _handle_my_feature(chat_id: int) -> None:
    if not _is_allowed(chat_id): return _deny(chat_id)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(_t(chat_id, "back"), callback_data="menu")]])
    bot.send_message(chat_id, "...", reply_markup=keyboard)

# 2. Add button in a keyboard builder
InlineKeyboardButton("My Feature", callback_data="my_feature")

# 3. Dispatch in handle_callback()
elif data == "my_feature":
    if not _is_allowed(chat_id): return _deny(chat_id)
    _handle_my_feature(chat_id)

# Parametrised callbacks — use startswith:
elif data.startswith("my_feature_"):
    _handle_my_feature_item(chat_id, data[len("my_feature_"):])
```

## Multi-Step Input Flow

```python
_pending_foo: dict[int, dict] = {}   # global, keyed by chat_id

def _start_foo(chat_id): _pending_foo[chat_id] = {"step": "name"}; bot.send_message(chat_id, "Enter name:")
def _finish_foo(chat_id, text):
    state = _pending_foo.pop(chat_id, {}); step = state.get("step")
    if step == "name": ...

# In handle_message() — check BEFORE routing to chat/system:
if chat_id in _pending_foo: return _finish_foo(chat_id, text)
```

## i18n Strings

```json
// src/strings.json — add to ALL three languages: "ru", "en", "de"
{ "ru": {"my_key": "Текст"}, "en": {"my_key": "Text"}, "de": {"my_key": "Text"} }
```

```python
title = _t(chat_id, "my_key")
body  = _t(chat_id, "my_key_body", value=42)   # supports format kwargs
```

## Access Guards

```python
def _handle_something(chat_id): 
    if not _is_allowed(chat_id): return _deny(chat_id)   # user access
def _handle_admin_something(chat_id):
    if not _is_admin(chat_id): return _deny(chat_id)     # admin only
```

## Subprocess Pattern

```python
out, rc = _run_subprocess(["/usr/bin/taris", "agent", "-m", prompt], timeout=60)
if rc != 0: log.warning(f"[MyFeature] exit {rc}: {out[:120]}")
```

Never use `os.system()` or `subprocess.run()` directly — always `_run_subprocess`.

## Safe Message Edit

```python
_safe_edit(chat_id, call.message.message_id, new_text, reply_markup=new_keyboard, parse_mode="Markdown")
```

## Calendar Feature Pattern (prompt → LLM → confirm → execute)

All calendar mutations require explicit confirmation before executing.

```python
# Handler for action
def _handle_cal_my_action(chat_id, ev_id):
    ...
    kb.add(InlineKeyboardButton("✅ Confirm", callback_data=f"cal_my_action_confirm:{ev_id}"),
           InlineKeyboardButton("❌ Cancel",  callback_data="menu_calendar"))
    bot.send_message(chat_id, "...", reply_markup=kb)

def _handle_cal_my_action_confirmed(chat_id, ev_id): ...  # actual mutation
```

Callbacks in `telegram_menu_bot.py`:
```python
elif data.startswith("cal_my_action:"):         _handle_cal_my_action(cid, data[len("cal_my_action:"):])
elif data.startswith("cal_my_action_confirm:"): _handle_cal_my_action_confirmed(cid, data[len("cal_my_action_confirm:"):])
```

Also update `doc/bot-code-map.md` callback key table.

## UI Sync Rule

Any UI change (screen, button, string) must be applied to **both** Telegram and Web UI simultaneously:
- Telegram: `src/telegram_menu_bot.py` + `src/bot_*.py` + `src/strings.json`
- Web UI: `src/bot_web.py` + `src/web/templates/*.html` + `src/web/static/`

Before deploying, ask: *"Which target(s) shall I deploy to? (OpenClawPI / OpenClawPI2 / both)"*

## Documentation Maintenance

When adding features: update `doc/arch/<topic>.md` + `README.md` in same commit.  
Full doc update: use `/taris-update-doc` skill.
