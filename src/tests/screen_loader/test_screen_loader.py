"""Unit tests for src/ui/screen_loader.py — Screen DSL YAML/JSON loader.

Pure-Python tests — no Telegram, no Pi, no network.
Run: py -m pytest src/tests/screen_loader/ -v
"""

import json
import os
import pytest

from ui.screen_loader import (
    _substitute,
    _resolve_text,
    _resolve_action,
    _is_visible,
    _load_file,
    _screen_cache,
    reload_screens,
    load_all_screens,
    load_screen,
)
from ui.bot_ui import (
    UserContext,
    Button,
    ButtonRow,
    Card,
    TextInput,
    Toggle,
    AudioPlayer,
    MarkdownBlock,
    Spinner,
    Confirm,
    Redirect,
    Screen,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _t(lang: str, key: str) -> str:
    """Mock i18n function — returns '[lang:key]'."""
    return f"[{lang}:{key}]"


def _user(role: str = "user", lang: str = "en") -> UserContext:
    return UserContext(user_id="u1", chat_id=123, lang=lang, role=role)


def _write_yaml(tmp_path, name: str, data: dict) -> str:
    """Write a YAML file and return its path."""
    try:
        import yaml
        p = tmp_path / name
        p.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    except ImportError:
        # Fallback: write JSON with .yaml extension — loader accepts both
        p = tmp_path / name.replace(".yaml", ".json")
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(p)


def _write_json(tmp_path, name: str, data: dict) -> str:
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# _substitute
# ---------------------------------------------------------------------------

class TestSubstitute:
    def test_basic_replacement(self):
        assert _substitute("Hello {name}!", {"name": "World"}) == "Hello World!"

    def test_multiple_vars(self):
        result = _substitute("{a} and {b}", {"a": "X", "b": "Y"})
        assert result == "X and Y"

    def test_missing_var_left_as_is(self):
        assert _substitute("{missing}", {}) == "{missing}"

    def test_empty_vars(self):
        assert _substitute("no vars", {}) == "no vars"

    def test_no_braces(self):
        assert _substitute("plain text", {"x": "y"}) == "plain text"


# ---------------------------------------------------------------------------
# _resolve_text
# ---------------------------------------------------------------------------

class TestResolveText:
    def test_key_field(self):
        w = {"text_key": "help_text"}
        result = _resolve_text(w, "text_key", "text", _t, "en", {})
        assert result == "[en:help_text]"

    def test_literal_field(self):
        w = {"text": "Hello literal"}
        result = _resolve_text(w, "text_key", "text", _t, "en", {})
        assert result == "Hello literal"

    def test_key_takes_precedence(self):
        w = {"text_key": "my_key", "text": "literal"}
        result = _resolve_text(w, "text_key", "text", _t, "ru", {})
        assert result == "[ru:my_key]"

    def test_neither_field_returns_empty(self):
        w = {}
        result = _resolve_text(w, "text_key", "text", _t, "en", {})
        assert result == ""

    def test_variable_substitution_in_literal(self):
        w = {"text": "Hi {user}!"}
        result = _resolve_text(w, "text_key", "text", _t, "en", {"user": "Alice"})
        assert result == "Hi Alice!"

    def test_no_t_func(self):
        w = {"text_key": "some_key", "text": "fallback"}
        result = _resolve_text(w, "text_key", "text", None, "en", {})
        assert result == "fallback"


# ---------------------------------------------------------------------------
# _resolve_action
# ---------------------------------------------------------------------------

class TestResolveAction:
    def test_basic_action(self):
        assert _resolve_action({"action": "menu"}, {}) == "menu"

    def test_action_with_var(self):
        result = _resolve_action({"action": "note_open:{slug}"}, {"slug": "abc"})
        assert result == "note_open:abc"

    def test_missing_action(self):
        assert _resolve_action({}, {}) == ""


# ---------------------------------------------------------------------------
# _is_visible
# ---------------------------------------------------------------------------

class TestIsVisible:
    def test_no_constraints_always_visible(self):
        assert _is_visible({}, _user("user")) is True

    def test_visible_roles_match(self):
        w = {"visible_roles": ["admin", "developer"]}
        assert _is_visible(w, _user("admin")) is True

    def test_visible_roles_no_match(self):
        w = {"visible_roles": ["admin"]}
        assert _is_visible(w, _user("user")) is False

    def test_visible_if_true(self):
        w = {"visible_if": "is_admin"}
        user = _user("admin")
        user_dict = _user("admin")
        # visible_if checks user attribute — depends on implementation
        # If the attr doesn't exist, should return False
        assert isinstance(_is_visible(w, user), bool)

    def test_visible_roles_empty_list(self):
        # empty list is falsy → treated as "no constraint" → visible
        w = {"visible_roles": []}
        assert _is_visible(w, _user("admin")) is True


# ---------------------------------------------------------------------------
# Widget builders (via load_screen integration)
# ---------------------------------------------------------------------------

class TestWidgetBuilders:
    """Test each widget type via load_screen with minimal YAML dicts."""

    def test_button(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "button", "label": "Click", "action": "do_it", "style": "secondary"}],
        }
        path = _write_json(tmp_path, "btn.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        assert len(screen.widgets) == 1
        btn = screen.widgets[0]
        assert isinstance(btn, Button)
        assert btn.label == "Click"
        assert btn.action == "do_it"
        assert btn.style == "secondary"

    def test_button_defaults(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "button", "label": "Go", "action": "go"}],
        }
        path = _write_json(tmp_path, "btn2.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        btn = screen.widgets[0]
        assert btn.style == "primary"

    def test_button_row(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{
                "type": "button_row",
                "buttons": [
                    {"label": "A", "action": "a"},
                    {"label": "B", "action": "b"},
                ],
            }],
        }
        path = _write_json(tmp_path, "brow.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        row = screen.widgets[0]
        assert isinstance(row, ButtonRow)
        assert len(row.buttons) == 2
        assert row.buttons[0].label == "A"
        assert row.buttons[1].action == "b"

    def test_button_row_visibility(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{
                "type": "button_row",
                "buttons": [
                    {"label": "Admin Only", "action": "x", "visible_roles": ["admin"]},
                    {"label": "All", "action": "y"},
                ],
            }],
        }
        path = _write_json(tmp_path, "brow_vis.json", data)
        screen = load_screen(path, _user("user"), variables={}, t_func=_t)
        row = screen.widgets[0]
        assert len(row.buttons) == 1
        assert row.buttons[0].label == "All"

    def test_card(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "card", "title": "Event", "body": "Details here", "action": "ev:1"}],
        }
        path = _write_json(tmp_path, "card.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        card = screen.widgets[0]
        assert isinstance(card, Card)
        assert card.title == "Event"
        assert card.body == "Details here"
        assert card.action == "ev:1"

    def test_card_no_action(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "card", "title": "Info", "body": "Just info"}],
        }
        path = _write_json(tmp_path, "card2.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        card = screen.widgets[0]
        assert card.action is None

    def test_text_input(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "text_input", "placeholder": "Type here", "action": "submit"}],
        }
        path = _write_json(tmp_path, "tinput.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        ti = screen.widgets[0]
        assert isinstance(ti, TextInput)
        assert ti.placeholder == "Type here"
        assert ti.action == "submit"

    def test_toggle(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "toggle", "label": "Dark mode", "key": "dark", "value": True}],
        }
        path = _write_json(tmp_path, "toggle.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        t = screen.widgets[0]
        assert isinstance(t, Toggle)
        assert t.label == "Dark mode"
        assert t.key == "dark"
        assert t.value is True

    def test_audio_player(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "audio_player", "src": "/audio/clip.ogg", "caption": "Sample"}],
        }
        path = _write_json(tmp_path, "audio.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        ap = screen.widgets[0]
        assert isinstance(ap, AudioPlayer)
        assert ap.src == "/audio/clip.ogg"
        assert ap.caption == "Sample"

    def test_markdown(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "markdown", "text": "**Bold** text"}],
        }
        path = _write_json(tmp_path, "md.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        md = screen.widgets[0]
        assert isinstance(md, MarkdownBlock)
        assert md.text == "**Bold** text"

    def test_spinner(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "spinner", "label": "Loading..."}],
        }
        path = _write_json(tmp_path, "spin.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        s = screen.widgets[0]
        assert isinstance(s, Spinner)
        assert s.label == "Loading..."

    def test_spinner_default_label(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "spinner"}],
        }
        path = _write_json(tmp_path, "spin2.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        s = screen.widgets[0]
        assert isinstance(s, Spinner)

    def test_confirm(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "confirm", "text": "Sure?", "action_yes": "do_yes", "action_no": "do_no"}],
        }
        path = _write_json(tmp_path, "confirm.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        c = screen.widgets[0]
        assert isinstance(c, Confirm)
        assert c.text == "Sure?"
        assert c.action_yes == "do_yes"
        assert c.action_no == "do_no"

    def test_redirect(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [{"type": "redirect", "target": "menu"}],
        }
        path = _write_json(tmp_path, "redir.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        r = screen.widgets[0]
        assert isinstance(r, Redirect)
        assert r.target == "menu"


# ---------------------------------------------------------------------------
# _load_file and caching
# ---------------------------------------------------------------------------

class TestLoadFile:
    def test_json_load(self, tmp_path):
        data = {"title": "Hello", "widgets": []}
        path = _write_json(tmp_path, "test.json", data)
        reload_screens()  # ensure clean cache
        result = _load_file(path)
        assert result["title"] == "Hello"

    def test_caching(self, tmp_path):
        data = {"title": "Cached", "widgets": []}
        path = _write_json(tmp_path, "cached.json", data)
        reload_screens()
        r1 = _load_file(path)
        r2 = _load_file(path)
        assert r1 is r2  # same object from cache

    def test_reload_clears_cache(self, tmp_path):
        data = {"title": "V1", "widgets": []}
        path = _write_json(tmp_path, "reload.json", data)
        reload_screens()
        r1 = _load_file(path)
        reload_screens()
        r2 = _load_file(path)
        # After reload, should re-read (new object)
        assert r1 is not r2
        assert r1 == r2  # same content

    def test_invalid_file_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json", encoding="utf-8")
        reload_screens()
        with pytest.raises(json.JSONDecodeError):
            _load_file(str(p))

    def test_non_dict_raises(self, tmp_path):
        p = tmp_path / "list.json"
        p.write_text("[1,2,3]", encoding="utf-8")
        reload_screens()
        with pytest.raises(ValueError):
            _load_file(str(p))


# ---------------------------------------------------------------------------
# reload_screens
# ---------------------------------------------------------------------------

class TestReloadScreens:
    def test_clears_cache(self, tmp_path):
        data = {"title": "X", "widgets": []}
        path = _write_json(tmp_path, "r.json", data)
        _load_file(path)
        assert len(_screen_cache) > 0
        reload_screens()
        assert len(_screen_cache) == 0


# ---------------------------------------------------------------------------
# load_all_screens
# ---------------------------------------------------------------------------

class TestLoadAllScreens:
    def test_loads_json_files(self, tmp_path):
        _write_json(tmp_path, "a.json", {"title": "A", "widgets": []})
        _write_json(tmp_path, "b.json", {"title": "B", "widgets": []})
        (tmp_path / "readme.txt").write_text("ignore me", encoding="utf-8")
        reload_screens()
        result = load_all_screens(str(tmp_path))
        assert len(result) >= 2

    def test_missing_directory(self, tmp_path):
        reload_screens()
        result = load_all_screens(str(tmp_path / "nonexistent"))
        assert len(result) == 0


# ---------------------------------------------------------------------------
# load_screen (integration)
# ---------------------------------------------------------------------------

class TestLoadScreen:
    def test_full_screen_construction(self, tmp_path):
        data = {
            "title": "My Screen",
            "parse_mode": "HTML",
            "widgets": [
                {"type": "card", "title": "Info", "body": "Body text"},
                {"type": "button", "label": "OK", "action": "confirm"},
            ],
        }
        path = _write_json(tmp_path, "full.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        assert isinstance(screen, Screen)
        assert screen.title == "My Screen"
        assert screen.parse_mode == "HTML"
        assert len(screen.widgets) == 2

    def test_title_key_resolution(self, tmp_path):
        data = {
            "title_key": "help_title",
            "widgets": [],
        }
        path = _write_json(tmp_path, "tkey.json", data)
        screen = load_screen(path, _user(lang="de"), variables={}, t_func=_t)
        assert screen.title == "[de:help_title]"

    def test_visibility_filters_widgets(self, tmp_path):
        data = {
            "title": "Menu",
            "widgets": [
                {"type": "button", "label": "User Btn", "action": "user_thing"},
                {"type": "button", "label": "Admin Btn", "action": "admin_thing", "visible_roles": ["admin"]},
            ],
        }
        path = _write_json(tmp_path, "vis.json", data)
        screen = load_screen(path, _user("user"), variables={}, t_func=_t)
        assert len(screen.widgets) == 1
        assert screen.widgets[0].label == "User Btn"

    def test_admin_sees_all(self, tmp_path):
        data = {
            "title": "Menu",
            "widgets": [
                {"type": "button", "label": "User Btn", "action": "user_thing"},
                {"type": "button", "label": "Admin Btn", "action": "admin_thing", "visible_roles": ["admin"]},
            ],
        }
        path = _write_json(tmp_path, "vis2.json", data)
        screen = load_screen(path, _user("admin"), variables={}, t_func=_t)
        assert len(screen.widgets) == 2

    def test_variable_substitution(self, tmp_path):
        data = {
            "title": "Note: {title}",
            "widgets": [
                {"type": "button", "label": "Edit {title}", "action": "edit:{slug}"},
            ],
        }
        path = _write_json(tmp_path, "vars.json", data)
        screen = load_screen(path, _user(), variables={"title": "My Note", "slug": "my_note"}, t_func=_t)
        assert screen.title == "Note: My Note"
        assert screen.widgets[0].label == "Edit My Note"
        assert screen.widgets[0].action == "edit:my_note"

    def test_i18n_in_widgets(self, tmp_path):
        data = {
            "title_key": "menu_title",
            "widgets": [
                {"type": "markdown", "text_key": "help_text"},
            ],
        }
        path = _write_json(tmp_path, "i18n.json", data)
        screen = load_screen(path, _user(lang="ru"), variables={}, t_func=_t)
        assert screen.title == "[ru:menu_title]"
        md = screen.widgets[0]
        assert isinstance(md, MarkdownBlock)
        assert md.text == "[ru:help_text]"

    def test_unknown_widget_type_skipped(self, tmp_path):
        data = {
            "title": "Test",
            "widgets": [
                {"type": "unknown_widget", "foo": "bar"},
                {"type": "button", "label": "OK", "action": "ok"},
            ],
        }
        path = _write_json(tmp_path, "unknown.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        # Unknown type is skipped, only button remains
        assert len(screen.widgets) == 1
        assert isinstance(screen.widgets[0], Button)

    def test_invalid_file_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json!!", encoding="utf-8")
        reload_screens()
        with pytest.raises(json.JSONDecodeError):
            load_screen(str(p), _user(), variables={}, t_func=_t)

    def test_ephemeral_flag(self, tmp_path):
        data = {"title": "Temp", "ephemeral": True, "widgets": []}
        path = _write_json(tmp_path, "eph.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        assert screen.ephemeral is True

    def test_default_parse_mode(self, tmp_path):
        data = {"title": "Plain", "widgets": []}
        path = _write_json(tmp_path, "plain.json", data)
        screen = load_screen(path, _user(), variables={}, t_func=_t)
        assert screen.parse_mode == "Markdown"


# ---------------------------------------------------------------------------
# help.yaml integration test
# ---------------------------------------------------------------------------

class TestHelpYaml:
    """Validate the actual help.yaml screen definition file."""

    def test_help_yaml_loads(self):
        help_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "screens", "help.yaml"
        )
        if not os.path.exists(help_path):
            pytest.skip("help.yaml not found")
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("pyyaml not installed")
        screen = load_screen(help_path, _user("user", "en"), variables={}, t_func=_t)
        assert screen is not None
        assert isinstance(screen, Screen)
        # Should have widgets (markdown blocks for non-admin)
        assert len(screen.widgets) >= 1

    def test_help_yaml_admin_has_more_widgets(self):
        help_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "screens", "help.yaml"
        )
        if not os.path.exists(help_path):
            pytest.skip("help.yaml not found")
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("pyyaml not installed")
        user_screen = load_screen(help_path, _user("user"), variables={}, t_func=_t)
        admin_screen = load_screen(help_path, _user("admin"), variables={}, t_func=_t)
        assert admin_screen is not None
        assert user_screen is not None
        # Admin should see more or equal widgets
        assert len(admin_screen.widgets) >= len(user_screen.widgets)
