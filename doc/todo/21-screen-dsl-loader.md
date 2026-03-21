# TODO §21 — Dynamic UI: Enhanced Screen DSL + JSON/YAML Loader

**Status:** 🔲 Planned  
**Research:** [research-dynamic-ui-scenarios.md](../research-dynamic-ui-scenarios.md) — Solution A ranked #1 (4.85/5.0)  
**Date added:** 2026-04

← [Back to TODO.md](../../TODO.md#21-dynamic-ui--enhanced-screen-dsl--jsonyaml-loader)

---

## Problem Statement

All screens are currently defined in Python (`bot_actions.py` + `bot_handlers.py`).
Adding or modifying a UI screen requires a code edit + deploy.
There is no way to preview, hot-reload, or edit a screen without restarting the service.

The Screen DSL (`bot_ui.py`) already makes channel-agnostic screens possible — the missing piece is
a **declarative loader** that reads screen definitions from YAML/JSON files at runtime.

---

## Architecture

Solution A keeps both renderers (`render_telegram.py`, Jinja2 Web) **unchanged**.
A new thin loader layer converts YAML/JSON files into the same `Screen` / widget objects the
renderers already consume:

```
src/screens/
    main_menu.yaml
    admin_menu.yaml
    help.yaml
    ...
         │
         ▼
src/ui/screen_loader.py          ← NEW ~100 lines
    _WIDGET_BUILDERS registry
    load_screen(path, user, vars, t_func) → Screen
    load_all_screens(dir) → dict
    reload_screens()               ← hot-reload: clears _screen_cache
         │
         ▼
bot_actions.py  (calls load_screen)
render_telegram.py   ← UNCHANGED
bot_web.py (Jinja2)  ← UNCHANGED
```

RAM overhead: **+0 MB** (same Screen/widget dataclasses).  
`_screen_cache` holds raw parsed dicts ~0.1 MB for 20 screens.

---

## YAML/JSON Format Specification

### YAML example (`screens/main_menu.yaml`)

```yaml
screen:
  id: main_menu
  title_key: menu_title

  widgets:
    - type: button_row
      buttons:
        - label_key: btn_chat
          action: mode_chat
          style: primary
        - label_key: btn_voice
          action: voice_session
          style: primary

    - type: button_row
      buttons:
        - label_key: btn_notes
          action: menu_notes
        - label_key: btn_calendar
          action: menu_calendar

    - type: button_row
      visible_roles: [admin, developer]
      buttons:
        - label_key: btn_admin
          action: admin_menu
          style: danger
```

### JSON example (`screens/note_view.json`)

```json
{
  "screen": {
    "id": "note_view",
    "title_key": "note_title",
    "widgets": [
      {
        "type": "card",
        "title": "{note_title}",
        "body":  "{note_body}"
      },
      {
        "type": "button_row",
        "buttons": [
          {"label_key": "btn_edit",   "action": "note_edit:{slug}"},
          {"label_key": "btn_delete", "action": "note_delete:{slug}", "style": "danger"}
        ]
      },
      {
        "type": "button_row",
        "buttons": [
          {"label_key": "btn_back", "action": "note_list"}
        ]
      }
    ]
  }
}
```

### Feature support table

| Feature | Syntax | Example |
|---------|--------|---------|
| i18n keys | `label_key` / `title_key` | `label_key: btn_chat` |
| Literal text | `label` / `title` | `label: "🔙 Back"` |
| Role visibility | `visible_roles: [admin]` | Widget hidden from non-admin |
| Conditional visibility | `visible_if: "has_notes"` | Boolean context variable |
| Dynamic variable | `{var_name}` in any text field | `text: "Notes: {count}"` |
| Parametric action | `action: "note_edit:{slug}"` | `{slug}` resolved from `variables` dict |
| Screen parse mode | `parse_mode: Markdown` | Screen-level setting |
| Ephemeral flag | `ephemeral: true` | Screen is not cached |

---

## Loader Implementation (`src/ui/screen_loader.py`)

~100 lines. Architecture — widget registry + thin core.

```python
"""screen_loader.py — Load Screen objects from JSON/YAML files."""
from __future__ import annotations
import json, pathlib
from typing import Any
from ui.bot_ui import (AudioPlayer, Button, ButtonRow, Card, Confirm,
    MarkdownBlock, Redirect, Screen, Spinner, TextInput, Toggle, UserContext)

try:
    import yaml; _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_WIDGET_BUILDERS: dict[str, callable] = {}
_screen_cache: dict[str, dict] = {}

def _register(name: str):
    def decorator(fn): _WIDGET_BUILDERS[name] = fn; return fn
    return decorator

# ── Widget builders ──────────────────────────────────────────────────────────

@_register("button")
def _build_button(data, ctx):
    return Button(label=_resolve_text(data, ctx),
                  action=_resolve_action(data.get("action"), ctx),
                  style=data.get("style", "primary"))

@_register("button_row")
def _build_button_row(data, ctx):
    return ButtonRow(buttons=[
        _build_button(b, ctx)
        for b in data.get("buttons", [])
        if _is_visible(b, ctx)
    ])

@_register("card")
def _build_card(data, ctx):
    return Card(title=_substitute(data.get("title", ""), ctx),
                subtitle=_substitute(data.get("subtitle", ""), ctx),
                body=_substitute(data.get("body", ""), ctx))

@_register("text_input")
def _build_text_input(data, ctx):
    return TextInput(label=_resolve_text(data, ctx), name=data.get("name", ""))

@_register("toggle")
def _build_toggle(data, ctx):
    return Toggle(label=_resolve_text(data, ctx),
                  key=data.get("key", ""),
                  value=bool(ctx.get("vars", {}).get(data.get("key", ""), False)))

@_register("audio_player")
def _build_audio_player(data, ctx):
    return AudioPlayer(url=data.get("url"), caption=_resolve_text(data, ctx))

@_register("markdown")
def _build_markdown(data, ctx):
    return MarkdownBlock(text=_substitute(data.get("text", ""), ctx))

@_register("spinner")
def _build_spinner(data, ctx):
    return Spinner(label=_resolve_text(data, ctx))

@_register("confirm")
def _build_confirm(data, ctx):
    return Confirm(message=_resolve_text(data, ctx),
                   confirm_action=data.get("confirm_action", ""),
                   cancel_action=data.get("cancel_action", "cancel"))

@_register("redirect")
def _build_redirect(data, ctx):
    return Redirect(action=_resolve_action(data.get("action"), ctx))

# ── Core loader ───────────────────────────────────────────────────────────────

def load_screen(path, user: UserContext,
                variables: dict | None = None,
                t_func=None) -> Screen:
    """Load and return a Screen from a YAML/JSON file."""
    p = pathlib.Path(path)
    data = _load_file(p)
    screen_data = data.get("screen", data)
    ctx = {"user": user, "lang": user.lang,
           "role": getattr(user, "role", None),
           "vars": variables or {}, "t": t_func}
    widgets = [
        _WIDGET_BUILDERS[w["type"]](w, ctx)
        for w in screen_data.get("widgets", [])
        if _is_visible(w, ctx) and w.get("type") in _WIDGET_BUILDERS
    ]
    return Screen(
        title=_resolve_text(screen_data, ctx, "title_key", "title"),
        widgets=widgets,
        parse_mode=screen_data.get("parse_mode", "Markdown"),
        ephemeral=screen_data.get("ephemeral", False),
    )

def load_all_screens(directory) -> dict[str, dict]:
    """Pre-load all YAML/JSON files in directory; return {name: raw_data}."""
    loaded = {}
    for p in pathlib.Path(directory).glob("*.[yj][as][om][lm]"):
        loaded[p.stem] = _load_file(p)
    return loaded

def reload_screens() -> None:
    """Clear the file cache so next load_screen() call re-reads disk."""
    _screen_cache.clear()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_file(path: pathlib.Path) -> dict:
    key = str(path)
    if key not in _screen_cache:
        text = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            if not _HAS_YAML:
                raise ImportError("pyyaml is required for .yaml screen files")
            _screen_cache[key] = yaml.safe_load(text)
        else:
            _screen_cache[key] = json.loads(text)
    return _screen_cache[key]

def _resolve_text(data: dict, ctx: dict,
                  key_field="label_key", text_field="label") -> str:
    if key_field in data and ctx.get("t"):
        return ctx["t"](ctx["lang"], data[key_field])
    return _substitute(data.get(text_field, ""), ctx)

def _resolve_action(action: str | None, ctx: dict) -> str:
    return _substitute(action or "", ctx)

def _substitute(text: str, ctx: dict) -> str:
    for k, v in (ctx.get("vars") or {}).items():
        text = text.replace(f"{{{k}}}", str(v))
    return text

def _is_visible(widget_data: dict, ctx: dict) -> bool:
    roles = widget_data.get("visible_roles")
    if roles and ctx.get("role") not in roles:
        return False
    cond = widget_data.get("visible_if")
    if cond and not ctx.get("vars", {}).get(cond, True):
        return False
    return True
```

---

## Integration Patterns

### Telegram (callback dispatcher in `telegram_menu_bot.py`)

```python
from ui.screen_loader import load_screen
from ui.render_telegram import render_screen
from ui.bot_ui import UserContext

elif data == "help":
    ctx = UserContext(chat_id=cid, lang=_lang(cid),
                      is_admin=_is_admin(cid), role=_role(cid))
    screen = load_screen("screens/help.yaml", ctx, t_func=_t_by_lang)
    render_screen(screen, cid, bot)
```

### Web UI (`bot_web.py`)

```python
from ui.screen_loader import load_screen

@app.get("/dynamic/{screen_id}")
async def dynamic_screen(screen_id: str, request: Request,
                          user=Depends(get_current_user)):
    ctx = _make_ctx(user)
    screen = load_screen(f"screens/{screen_id}.yaml", ctx,
                         t_func=lambda lang, key: _t_web(lang, key))
    return templates.TemplateResponse("dynamic.html",
                                      {"request": request, "screen": screen})
```

### Admin hot-reload command

```python
elif data == "admin_reload_screens":
    if _is_admin(cid):
        from ui.screen_loader import reload_screens
        reload_screens()
        bot.answer_callback_query(call.id, "✅ Screens reloaded")
```

---

## Migration Strategy

Incremental — complex Python screens stay in `bot_actions.py`; only simple UI screens migrate to YAML.

| Phase | Description | Effort | Risk |
|-------|-------------|--------|------|
| **1** | Core loader (`screen_loader.py` + unit tests) | 1 day | Low |
| **2** | PoC — `help` + `about` YAML, wire both channels, hot-reload cmd | 0.5 day | Low |
| **3** | Main menu + admin menu YAML (with `visible_roles`) | 0.5 day | Low |
| **4** | Feature screens: notes, calendar, mail, settings/profile | 2 days | Medium |
| **5** | JSON Schema + schema validation + doc update in `dev-patterns.md` | 1 day | Low |
| **6** | Visual editor (OpenClaw only) — CodeMirror + live preview | 3–5 days | Medium |

**Breakpoint:** Phase 1+2 (≈1.5 days) deliver a working PoC. Phases 3–6 can be deferred.

---

## Platform Compatibility

| Platform | Phases | Notes |
|----------|--------|-------|
| PicoClaw (Pi 3 B+) | 1–5 | Full support. PyYAML +0.5 MB, negligible on Pi 3. |
| ZeroClaw (Pi Zero) | 1–5 | Same. Visual editor N/A (no Web UI on 512 MB). |
| OpenClaw (Pi 5) | 1–6 | All phases. Visual editor viable on Pi 5 + NVMe. |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| PyYAML not installed | Low | Low | JSON fallback built-in; YAML optional; `deploy/requirements.txt` updated |
| YAML parsing security | Low | Low | `yaml.safe_load()` only — no arbitrary code execution |
| Widget type mismatch | Low | Medium | Unknown types silently skipped; logged as WARNING |
| Cache staleness | Low | Low | `reload_screens()` available via admin cmd + on every restart |
| Complex screens wrong format | Medium | Low | Hybrid OK — only simple screens need YAML; complex Python screens unchanged |

---

## Advantages of Solution A (vs. framework alternatives)

1. **Zero new dependencies** for JSON-only usage; PyYAML optional
2. **Both renderers unchanged** — zero risk of breaking Telegram or Web UI
3. **Incremental migration** — convert one screen at a time; Python fallback always available
4. **Hot-reload** — `reload_screens()` applies YAML changes without service restart
5. **i18n preserved** — `t_func` parameter resolves keys from existing `strings.json`
6. **RBAC preserved** — `visible_roles` replaces inline Python `_is_admin()` checks
7. **Lowest complexity** among all 8 evaluated solutions (4.85/5.0 overall score)
8. **No NiceGUI or React/Vue** required — avoids >100 MB RAM overhead on Pi 3
