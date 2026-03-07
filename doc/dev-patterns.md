# Picoclaw Bot — Developer Patterns & Conventions

This document describes the exact patterns used throughout `telegram_menu_bot.py`.
Follow them precisely when adding features to keep the codebase consistent.

---

## 1. Adding a Voice Opt Toggle

Voice opts are feature flags that persist in `~/.picoclaw/voice_opts.json`.
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

```bat
rem Copy bot + companion files
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\release_notes.json   stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\strings.json         stas@OpenClawPI:/home/stas/.picoclaw/

rem Restart and verify
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S systemctl restart picoclaw-telegram && sleep 3 && journalctl -u picoclaw-telegram -n 12 --no-pager"
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
pscp -pw "%HOSTPWD%" src\services\picoclaw-new.service stas@OpenClawPI:/tmp/
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S cp /tmp/picoclaw-new.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now picoclaw-new"
```

---

## 12. Voice Opt `_piper_model_path()` Priority Chain

```
tmpfs_model enabled AND /dev/shm/piper/... exists → use tmpfs path  (fastest)
    ↓ else
piper_low_model enabled AND ~/.picoclaw/ru_RU-irina-low.onnx exists → use low model
    ↓ else
default → ~/.picoclaw/ru_RU-irina-medium.onnx
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
