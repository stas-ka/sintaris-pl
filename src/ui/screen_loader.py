"""
screen_loader.py — Declarative Screen DSL loader (YAML / JSON)

Reads screen definitions from YAML or JSON files in src/screens/ and
returns Screen objects that existing renderers (render_telegram.py,
bot_web.py) consume unchanged.

Dependency position: bot_ui → screen_loader  (no other bot_* imports)
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

from ui.bot_ui import (
    AudioPlayer, Button, ButtonRow, Card, Confirm, MarkdownBlock,
    Redirect, Screen, Spinner, TextInput, Toggle, UserContext,
)

log = logging.getLogger("taris-tgbot")

# Optional YAML support — falls back to JSON-only if pyyaml absent
try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# Optional schema validation
try:
    import jsonschema
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

_SCHEMA: dict | None = None


def _get_schema() -> dict | None:
    """Lazy-load the JSON Schema from src/screens/screen.schema.json."""
    global _SCHEMA
    if _SCHEMA is not None:
        return _SCHEMA
    schema_path = Path(__file__).resolve().parent.parent / "screens" / "screen.schema.json"
    if not schema_path.exists():
        return None
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            _SCHEMA = json.load(f)
        return _SCHEMA
    except Exception as exc:
        log.warning("[ScreenLoader] Could not load schema: %s", exc)
        return None


def _validate_screen(data: dict, path: str) -> None:
    """Validate screen data against the JSON Schema. Logs warnings on failure."""
    if not _HAS_JSONSCHEMA:
        return
    schema = _get_schema()
    if schema is None:
        return
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        log.warning(
            "[ScreenLoader] Schema validation failed for %s: %s (path: %s)",
            path, exc.message, list(exc.absolute_path),
        )

# ---------------------------------------------------------------------------
# Widget builder registry
# ---------------------------------------------------------------------------

_WIDGET_BUILDERS: dict[str, Callable] = {}


def _register(type_name: str):
    """Decorator: register a builder function for a YAML widget type."""
    def decorator(fn):
        _WIDGET_BUILDERS[type_name] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Text resolution helpers
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"\{(\w+)\}")


def _substitute(text: str, variables: dict[str, str]) -> str:
    """Replace {var_name} placeholders with values from variables dict."""
    if not variables:
        return text
    def replacer(m):
        key = m.group(1)
        return variables.get(key, m.group(0))
    return _VAR_RE.sub(replacer, text)


def _resolve_text(
    w: dict,
    key_field: str,
    literal_field: str,
    t_func: Callable[[str, str], str] | None,
    lang: str,
    variables: dict[str, str],
) -> str:
    """Resolve a text value from either an i18n key or a literal string."""
    i18n_key = w.get(key_field)
    if i18n_key and t_func:
        text = t_func(lang, i18n_key)
    else:
        text = w.get(literal_field, "")
    return _substitute(str(text), variables)


def _resolve_action(w: dict, variables: dict[str, str]) -> str:
    """Resolve an action string with variable substitution."""
    action = w.get("action", "")
    return _substitute(str(action), variables)


def _is_visible(w: dict, user: UserContext, variables: dict | None = None) -> bool:
    """Check role-based and conditional visibility."""
    roles = w.get("visible_roles")
    if roles and user.role not in roles:
        return False
    cond = w.get("visible_if")
    if cond:
        if cond == "true":
            pass  # always visible
        elif not bool((variables or {}).get(cond)):
            return False
    return True


# ---------------------------------------------------------------------------
# Widget builders — one per type, field names match bot_ui.py exactly
# ---------------------------------------------------------------------------

@_register("button")
def _build_button(w: dict, **ctx) -> Button:
    label = _resolve_text(w, "label_key", "label", ctx["t_func"], ctx["lang"], ctx["vars"])
    action = _resolve_action(w, ctx["vars"])
    return Button(label=label, action=action, style=w.get("style", "primary"))


@_register("button_row")
def _build_button_row(w: dict, **ctx) -> ButtonRow:
    buttons = []
    for bw in w.get("buttons", []):
        if _is_visible(bw, ctx["user"], ctx.get("vars")):
            buttons.append(_build_button(bw, **ctx))
    return ButtonRow(buttons=buttons)


@_register("card")
def _build_card(w: dict, **ctx) -> Card:
    title = _resolve_text(w, "title_key", "title", ctx["t_func"], ctx["lang"], ctx["vars"])
    body = _resolve_text(w, "body_key", "body", ctx["t_func"], ctx["lang"], ctx["vars"])
    action = _resolve_action(w, ctx["vars"]) if w.get("action") else None
    return Card(title=title, body=body, action=action)


@_register("text_input")
def _build_text_input(w: dict, **ctx) -> TextInput:
    placeholder = _resolve_text(w, "placeholder_key", "placeholder", ctx["t_func"], ctx["lang"], ctx["vars"])
    action = _resolve_action(w, ctx["vars"])
    return TextInput(placeholder=placeholder, action=action)


@_register("toggle")
def _build_toggle(w: dict, **ctx) -> Toggle:
    label = _resolve_text(w, "label_key", "label", ctx["t_func"], ctx["lang"], ctx["vars"])
    return Toggle(label=label, key=w.get("key", ""), value=bool(w.get("value", False)))


@_register("audio_player")
def _build_audio_player(w: dict, **ctx) -> AudioPlayer:
    src = _substitute(w.get("src", ""), ctx["vars"])
    caption = _resolve_text(w, "caption_key", "caption", ctx["t_func"], ctx["lang"], ctx["vars"])
    return AudioPlayer(src=src, caption=caption)


@_register("markdown")
def _build_markdown(w: dict, **ctx) -> MarkdownBlock:
    text = _resolve_text(w, "text_key", "text", ctx["t_func"], ctx["lang"], ctx["vars"])
    return MarkdownBlock(text=text)


@_register("spinner")
def _build_spinner(w: dict, **ctx) -> Spinner:
    label = _resolve_text(w, "label_key", "label", ctx["t_func"], ctx["lang"], ctx["vars"])
    return Spinner(label=label or "Processing…")


@_register("confirm")
def _build_confirm(w: dict, **ctx) -> Confirm:
    text = _resolve_text(w, "text_key", "text", ctx["t_func"], ctx["lang"], ctx["vars"])
    action_yes = _substitute(w.get("action_yes", ""), ctx["vars"])
    action_no = _substitute(w.get("action_no", ""), ctx["vars"])
    return Confirm(text=text, action_yes=action_yes, action_no=action_no)


@_register("redirect")
def _build_redirect(w: dict, **ctx) -> Redirect:
    target = _substitute(w.get("target", ""), ctx["vars"])
    return Redirect(target=target)


# ---------------------------------------------------------------------------
# File loading and caching
# ---------------------------------------------------------------------------

_screen_cache: dict[str, dict] = {}


def _load_file(path: str) -> dict:
    """Load a YAML or JSON file, with caching."""
    abs_path = os.path.abspath(path)
    if abs_path in _screen_cache:
        return _screen_cache[abs_path]

    with open(abs_path, "r", encoding="utf-8") as f:
        text = f.read()

    if abs_path.endswith((".yaml", ".yml")):
        if not _HAS_YAML:
            raise ImportError("pyyaml is required for .yaml files: pip install pyyaml")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)

    if not isinstance(data, dict):
        raise ValueError(f"Screen file must be a JSON/YAML object: {path}")

    _validate_screen(data, path)
    _screen_cache[abs_path] = data
    return data


def reload_screens() -> None:
    """Clear the screen file cache — call from admin hot-reload."""
    _screen_cache.clear()
    log.info("[ScreenLoader] Cache cleared — screens will reload on next access")


def load_all_screens(directory: str) -> dict[str, dict]:
    """Pre-load all screen files from a directory. Returns {filename: raw_data}."""
    result = {}
    dirpath = Path(directory)
    if not dirpath.is_dir():
        log.warning("[ScreenLoader] Directory not found: %s", directory)
        return result
    for ext in (".yaml", ".yml", ".json"):
        for filepath in dirpath.glob(f"*{ext}"):
            try:
                data = _load_file(str(filepath))
                result[filepath.name] = data
            except Exception as e:
                log.warning("[ScreenLoader] Failed to load %s: %s", filepath.name, e)
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def load_screen(
    path: str,
    user: UserContext,
    variables: dict[str, str] | None = None,
    t_func: Callable[[str, str], str] | None = None,
) -> Screen:
    """
    Load a screen definition from a YAML/JSON file and return a Screen object.

    Parameters
    ----------
    path : str
        Path to the screen file (relative or absolute).
    user : UserContext
        Current user — used for role-based widget visibility.
    variables : dict, optional
        Substitution variables for {var_name} placeholders in text and actions.
    t_func : callable(lang, key) -> str, optional
        i18n translation function. Called as t_func(user.lang, i18n_key).
    """
    data = _load_file(path)
    lang = user.lang
    vars_ = variables or {}

    # Resolve screen title
    title_key = data.get("title_key")
    if title_key and t_func:
        title = t_func(lang, title_key)
    else:
        title = data.get("title", "")
    title = _substitute(title, vars_)

    # Build visible widgets
    widgets = []
    ctx = {"t_func": t_func, "lang": lang, "vars": vars_, "user": user}

    for w in data.get("widgets", []):
        if not _is_visible(w, user, vars_):
            continue

        wtype = w.get("type", "").lower()
        builder = _WIDGET_BUILDERS.get(wtype)
        if not builder:
            log.warning("[ScreenLoader] Unknown widget type '%s' in %s", wtype, path)
            continue

        try:
            widget = builder(w, **ctx)
            widgets.append(widget)
        except Exception as e:
            log.warning("[ScreenLoader] Error building %s widget in %s: %s", wtype, path, e)

    return Screen(
        title=title,
        widgets=widgets,
        parse_mode=data.get("parse_mode", "Markdown"),
        ephemeral=data.get("ephemeral", False),
    )
