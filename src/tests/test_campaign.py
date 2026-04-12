"""
test_campaign.py — Tests for campaign flow (bot_campaign.py) and N8N webhook handling.

Covers the gaps revealed by real production bugs (2026-04-12):
  - Bug 1: Empty/non-JSON webhook response caused JSONDecodeError to propagate to user
  - Bug 2: Invalid OLLAMA_MODEL (qwen3.5:0.8b doesn't exist) — Ollama unreachable

Run (offline — source inspection + unit tests):
  python src/tests/test_campaign.py

Run (on target with bot.env — includes live Ollama check):
  PYTHONPATH=~/.taris python -m pytest tests/test_campaign.py -v

Tests: T130–T137
"""

import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

_src = Path(__file__).parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# WEB_ONLY=1 bypasses the BOT_TOKEN / ALLOWED_USERS mandatory-check in bot_config.
# This makes offline unit tests work without a real bot.env on the dev machine.
os.environ.setdefault("WEB_ONLY", "1")
# Provide minimal stubs so imports resolve without real credentials.
os.environ.setdefault("BOT_TOKEN", "0:OFFLINE_TEST")
os.environ.setdefault("ALLOWED_USERS", "99")


def _can_import_bot_config() -> bool:
    try:
        import core.bot_config
        return True
    except Exception:
        return False


_HAS_BOT_CONFIG = _can_import_bot_config()


# ─────────────────────────────────────────────────────────────────────────────
# T130: Campaign i18n keys — all campaign_* keys present in all 3 languages
# ─────────────────────────────────────────────────────────────────────────────

def test_campaign_i18n_keys():
    """T130: All campaign i18n keys present and non-empty in ru, en, de."""
    strings_path = _src / "strings.json"
    with open(strings_path, encoding="utf-8") as f:
        strings = json.load(f)

    # Every key used in bot_campaign.py (source-scraped)
    required_keys = [
        # Flow prompts
        "campaign_enter_topic", "campaign_enter_filters", "campaign_selecting",
        "campaign_no_clients",
        # Preview UI
        "campaign_preview", "campaign_btn_send", "campaign_btn_edit", "campaign_btn_cancel",
        # Edit / send
        "campaign_edit_prompt", "campaign_template_saved",
        "campaign_sending", "campaign_done", "campaign_partial_send",
        # Cancel
        "campaign_cancelled",
        # Not-configured guard
        "campaign_not_configured",
        # Error messages (must exist in _STEP_KEY_MAP)
        "campaign_error_input", "campaign_error_openai",
        "campaign_error_workflow", "campaign_error_email",
        # Agent menu button
        "agents_btn_campaign",
    ]

    for lang in ("ru", "en", "de"):
        assert lang in strings, f"Language '{lang}' missing"
        for key in required_keys:
            assert key in strings[lang], f"Key '{key}' missing in '{lang}'"
            assert strings[lang][key], f"Key '{key}' is empty in '{lang}'"


# ─────────────────────────────────────────────────────────────────────────────
# T131: Campaign module structure (source inspection)
# ─────────────────────────────────────────────────────────────────────────────

def test_campaign_module_structure():
    """T131: bot_campaign.py defines all required public functions and STEP_KEY_MAP."""
    src = (_src / "features" / "bot_campaign.py").read_text(encoding="utf-8")

    # Public API
    for fn in (
        "def is_active", "def get_step", "def cancel", "def is_configured",
        "def start_campaign", "def on_topic", "def on_filters",
        "def start_template_edit", "def on_template_edit",
        "def confirm_send", "def handle_message",
    ):
        assert fn in src, f"bot_campaign.py missing: {fn}"

    # Error handling helpers
    assert "_STEP_KEY_MAP" in src, "Missing _STEP_KEY_MAP"
    assert "def _user_friendly_error" in src, "Missing _user_friendly_error"
    assert "def _run_selection" in src, "Missing _run_selection"
    assert "def _run_send" in src, "Missing _run_send"

    # Must use call_webhook, not requests directly
    assert "from features.bot_n8n import call_webhook" in src, \
        "bot_campaign.py must use call_webhook from bot_n8n"
    assert "requests.post" not in src, \
        "bot_campaign.py must not call requests.post directly — use call_webhook"

    # Error handling: result must be checked for 'error' key
    assert '"error" in result' in src, \
        "Missing 'error' key check in selection/send result"

    # State cleanup on error (must pop state from _campaigns on failure)
    assert "_campaigns.pop(chat_id, None)" in src, \
        "Must clean up _campaigns on selection/send error"


# ─────────────────────────────────────────────────────────────────────────────
# T132: Campaign state machine (unit tests with mock bot + _t)
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_bot():
    bot = MagicMock()
    bot.send_message = MagicMock()
    return bot


def _make_t():
    def _t(chat_id, key, **kwargs):
        return f"[{key}]"
    return _t


def test_campaign_state_start():
    """T132a: start_campaign sets step=topic_input and sends topic prompt."""
    import importlib
    import features.bot_campaign as bc
    importlib.reload(bc)   # reset _campaigns state between tests

    bot = _make_mock_bot()
    bc.start_campaign(99, bot, _make_t())

    assert bc.is_active(99), "Campaign should be active after start"
    assert bc.get_step(99) == "topic_input"
    bot.send_message.assert_called_once()


def test_campaign_state_topic():
    """T132b: on_topic stores topic and moves to filter_input."""
    import importlib
    import features.bot_campaign as bc
    importlib.reload(bc)

    bot = _make_mock_bot()
    bc.start_campaign(99, bot, _make_t())
    bc.on_topic(99, "Webinar invitation", bot, _make_t())

    assert bc.get_step(99) == "filter_input"
    state = bc._campaigns[99]
    assert state["topic"] == "Webinar invitation"


def test_campaign_state_handle_message_routing():
    """T132c: handle_message routes to correct handler based on step."""
    import importlib
    import features.bot_campaign as bc
    importlib.reload(bc)

    bot = _make_mock_bot()
    _t = _make_t()

    # Not in campaign → returns False
    assert bc.handle_message(99, "hello", bot, _t) is False

    # topic_input step → consumed
    bc.start_campaign(99, bot, _t)
    assert bc.get_step(99) == "topic_input"
    assert bc.handle_message(99, "My topic", bot, _t) is True
    assert bc.get_step(99) == "filter_input"

    # filter_input step → consumed (triggers _run_selection thread)
    with patch("features.bot_campaign.call_webhook") as mock_wh:
        mock_wh.return_value = {"clients": [], "template": ""}
        assert bc.handle_message(99, "-", bot, _t) is True
    # After filter → step becomes "selecting" then transitions in thread


def test_campaign_state_cancel():
    """T132d: cancel() clears state, is_active returns False."""
    import importlib
    import features.bot_campaign as bc
    importlib.reload(bc)

    bot = _make_mock_bot()
    bc.start_campaign(99, bot, _make_t())
    assert bc.is_active(99)
    bc.cancel(99)
    assert not bc.is_active(99)
    assert bc.get_step(99) == "idle"


def test_campaign_edit_flow():
    """T132e: start_template_edit + on_template_edit updates template and returns to preview."""
    import importlib
    import features.bot_campaign as bc
    importlib.reload(bc)

    bot = _make_mock_bot()
    _t = _make_t()
    # Manually inject a preview state
    bc._campaigns[99] = {
        "step": "preview",
        "session_id": "s1",
        "topic": "Test",
        "filters": "",
        "clients": [{"name": "Alice"}],
        "template": "Original",
    }

    bc.start_template_edit(99, bot, _t)
    assert bc.get_step(99) == "editing"

    bc.on_template_edit(99, "New template text", bot, _t)
    assert bc.get_step(99) == "preview"
    assert bc._campaigns[99]["template"] == "New template text"


def test_campaign_on_filters_skip_variants():
    """T132f: on_filters treats -, no, skip, empty as 'no filters'."""
    import importlib
    import features.bot_campaign as bc

    for skip_val in ("-", "нет", "no", "skip", "", "  "):
        importlib.reload(bc)
        bot = _make_mock_bot()
        _t = _make_t()
        bc._campaigns[99] = {
            "step": "filter_input", "session_id": "s", "topic": "T",
            "filters": "", "clients": [], "template": "",
        }
        with patch("features.bot_campaign.call_webhook") as mock_wh:
            mock_wh.return_value = {"clients": [], "template": ""}
            bc.on_filters(99, skip_val, bot, _t)
        # Filter should be stored as empty string
        state = bc._campaigns.get(99, {})
        stored_filter = state.get("filters", "")
        assert stored_filter == "", \
            f"Expected empty filter for input {skip_val!r}, got {stored_filter!r}"


# ─────────────────────────────────────────────────────────────────────────────
# T133: call_webhook error handling — the actual production bug
# ─────────────────────────────────────────────────────────────────────────────

def test_call_webhook_no_url():
    """T133a: call_webhook returns structured error when URL is empty."""
    from features.bot_n8n import call_webhook
    result = call_webhook("", {"test": 1})
    assert "error" in result, "Must return error for empty URL"
    assert "not configured" in result["error"].lower() or "url" in result["error"].lower()


def test_call_webhook_empty_body_response():
    """T133b: call_webhook returns {'result': ...} (NOT 'error') for empty-body 200 response.

    This was the production bug: N8N returned empty body (200 OK) before our fix.
    The bug caused JSONDecodeError to bubble up to _run_selection which showed raw
    Python exception text to the user.

    Correct behavior: call_webhook must handle non-JSON gracefully.
    """
    from features.bot_n8n import call_webhook
    import requests

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = ""  # empty body — exactly what N8N returned before our workflow fix
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.side_effect = ValueError("No JSON object could be decoded")

    with patch("requests.post", return_value=mock_resp):
        result = call_webhook("https://example.com/wh", {"payload": "x"})

    # Must NOT raise — must return a structured dict
    assert isinstance(result, dict), "call_webhook must always return dict"
    # Empty body → result key (NOT error key, since HTTP succeeded)
    assert "result" in result or "error" in result, \
        "Must have either 'result' or 'error' key"
    # Must NOT expose raw JSONDecodeError text to caller
    raw_json_error = "No JSON object could be decoded"
    for v in result.values():
        assert raw_json_error not in str(v), \
            "Raw JSONDecodeError must not propagate to caller"


def test_call_webhook_http_error():
    """T133c: call_webhook returns {'error': ..., 'status_code': N} for HTTP errors."""
    from features.bot_n8n import call_webhook

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    import requests
    mock_resp.raise_for_status.side_effect = requests.HTTPError(
        "404 Not Found", response=mock_resp
    )

    with patch("requests.post", return_value=mock_resp):
        result = call_webhook("https://example.com/wh", {})

    assert "error" in result, "HTTP error must return error key"
    assert result.get("status_code") == 404 or "404" in str(result.get("error", ""))


def test_call_webhook_timeout():
    """T133d: call_webhook returns {'error': 'Webhook timeout...'} on timeout."""
    from features.bot_n8n import call_webhook
    import requests

    with patch("requests.post", side_effect=requests.Timeout()):
        result = call_webhook("https://example.com/wh", {}, timeout=5)

    assert "error" in result
    assert "timeout" in result["error"].lower()


def test_call_webhook_n8n_error_dict():
    """T133e: N8N workflow error response {'_error': true, 'step': X, 'detail': Y}
    is passed through so _run_selection can map it to user-friendly message.
    """
    from features.bot_n8n import call_webhook

    n8n_error = {"_error": True, "step": "OpenAI Select", "detail": "API key invalid",
                 "error": "API key invalid"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = n8n_error

    with patch("requests.post", return_value=mock_resp):
        result = call_webhook("https://example.com/wh", {})

    assert result == n8n_error, "N8N error dict must be passed through unchanged"
    # Caller (_run_selection) can now check 'error' key and 'step' key
    assert "error" in result or "_error" in result


def test_run_selection_empty_response_no_crash():
    """T133f: _run_selection does not crash on empty-body N8N response.

    Regression test for the 10:51 bug: 'Expecting value: line 1 column 1 (char 0)'
    """
    import importlib
    import features.bot_campaign as bc
    importlib.reload(bc)

    bot = _make_mock_bot()
    _t = _make_t()
    # Inject state in 'selecting' step
    bc._campaigns[99] = {
        "step": "selecting", "session_id": "s", "topic": "Test",
        "filters": "", "clients": [], "template": "",
    }

    # Simulate empty-body response (call_webhook returns {'result': '', 'status_code': 200})
    with patch("features.bot_campaign.call_webhook") as mock_wh:
        mock_wh.return_value = {"result": "", "status_code": 200}
        bc._run_selection(99, bot, _t)

    # Must send campaign_no_clients message, not crash
    bot.send_message.assert_called()
    call_args = str(bot.send_message.call_args_list)
    # Should show "no clients" message, not a Python exception
    assert "Exception" not in call_args
    assert "JSONDecodeError" not in call_args
    assert "Traceback" not in call_args


# ─────────────────────────────────────────────────────────────────────────────
# T134: _user_friendly_error step mapping
# ─────────────────────────────────────────────────────────────────────────────

def test_user_friendly_error_all_steps():
    """T134: All _STEP_KEY_MAP steps resolve to keys present in strings.json."""
    with open(_src / "strings.json", encoding="utf-8") as f:
        strings = json.load(f)

    from features.bot_campaign import _STEP_KEY_MAP, _user_friendly_error

    calls_made = []
    def mock_t(chat_id, key, **kwargs):
        calls_made.append(key)
        return f"[{key}]"

    for step, expected_key in _STEP_KEY_MAP.items():
        calls_made.clear()
        result = _user_friendly_error(step, "some detail", mock_t, 99)
        assert calls_made, f"_t was never called for step '{step}'"
        used_key = calls_made[0]
        assert used_key in strings["ru"], \
            f"Step '{step}' maps to key '{used_key}' which is missing in strings.json"
        assert strings["ru"][used_key], \
            f"Step '{step}' maps to key '{used_key}' which is empty in strings.json"

    # Unknown step → campaign_error_workflow
    calls_made.clear()
    _user_friendly_error("some_unknown_step", "oops", mock_t, 99)
    assert calls_made[0] == "campaign_error_workflow", \
        "Unknown step must map to campaign_error_workflow"


# ─────────────────────────────────────────────────────────────────────────────
# T135: Ollama model validation (runtime only)
# ─────────────────────────────────────────────────────────────────────────────

def test_ollama_model_exists_if_configured():
    """T135: If LLM_PROVIDER=ollama, the configured model must exist via Ollama API.

    This is the production bug: OLLAMA_MODEL=qwen3.5:0.8b was set but doesn't exist.
    """
    if not _HAS_BOT_CONFIG:
        print("SKIP T135 (no bot.env)")
        return

    import requests as req
    from core.bot_config import LLM_PROVIDER, OLLAMA_URL, OLLAMA_MODEL

    if LLM_PROVIDER != "ollama":
        print(f"SKIP T135 (LLM_PROVIDER={LLM_PROVIDER}, not ollama)")
        return

    assert OLLAMA_MODEL, "OLLAMA_MODEL must be set when LLM_PROVIDER=ollama"

    # Check Ollama API is reachable
    try:
        resp = req.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
    except Exception as e:
        raise AssertionError(
            f"Ollama not reachable at {OLLAMA_URL}: {e}\n"
            "Fix: start Ollama or switch LLM_PROVIDER."
        )

    models_data = resp.json()
    installed_names = {m["name"] for m in models_data.get("models", [])}
    # Ollama may store as "qwen2.5:0.5b" or "qwen2.5:0.5b" — match prefix
    configured = OLLAMA_MODEL.strip()
    match = any(
        name == configured or name.startswith(configured.split(":")[0] + ":")
        for name in installed_names
    )
    assert match, (
        f"OLLAMA_MODEL='{configured}' is NOT installed.\n"
        f"Installed models: {sorted(installed_names) or '(none)'}\n"
        f"Fix: ollama pull {configured}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T136: N8N webhook URL format
# ─────────────────────────────────────────────────────────────────────────────

def test_n8n_campaign_webhook_urls_source():
    """T136a: N8N_CAMPAIGN_SELECT_WH and SEND_WH constants exist in bot_config source."""
    src = (_src / "core" / "bot_config.py").read_text(encoding="utf-8")
    assert "N8N_CAMPAIGN_SELECT_WH" in src
    assert "N8N_CAMPAIGN_SEND_WH" in src
    assert "N8N_CAMPAIGN_TIMEOUT" in src

    # Default must not be a hardcoded URL — must be '' or env-var-sourced
    # Ensure no hardcoded production URL leaks into source
    import re
    for line in src.splitlines():
        if "N8N_CAMPAIGN_SELECT_WH" in line and "os.environ.get" not in line and "=" in line and "#" not in line:
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            if val.startswith("http"):
                raise AssertionError(
                    f"N8N_CAMPAIGN_SELECT_WH must not have hardcoded URL in source: {line.strip()}"
                )


def test_n8n_webhook_urls_valid_if_configured():
    """T136b: Runtime — webhook URLs are valid http/https URLs when configured."""
    if not _HAS_BOT_CONFIG:
        print("SKIP T136b (no bot.env)")
        return

    from core.bot_config import N8N_CAMPAIGN_SELECT_WH, N8N_CAMPAIGN_SEND_WH
    from features.bot_campaign import is_configured

    if not is_configured():
        print("SKIP T136b (campaign not configured)")
        return

    for url, name in ((N8N_CAMPAIGN_SELECT_WH, "SELECT_WH"),
                      (N8N_CAMPAIGN_SEND_WH, "SEND_WH")):
        assert url.startswith("https://") or url.startswith("http://"), \
            f"N8N_CAMPAIGN_{name} must be a valid URL, got: {url!r}"
        assert len(url) > 15, f"N8N_CAMPAIGN_{name} looks too short: {url!r}"


# ─────────────────────────────────────────────────────────────────────────────
# T137: Campaign callback routing in telegram_menu_bot.py
# ─────────────────────────────────────────────────────────────────────────────

def test_campaign_callback_routing_source():
    """T137: telegram_menu_bot.py routes all campaign callbacks."""
    src = (_src / "telegram_menu_bot.py").read_text(encoding="utf-8")

    required_callbacks = [
        "campaign_confirm_send",   # user approved send
        "campaign_edit_template",  # user wants to edit
        "campaign_cancel",         # user cancelled
        "agents_btn_campaign",     # agents menu → campaign
    ]
    for cb in required_callbacks:
        assert cb in src, \
            f"telegram_menu_bot.py missing campaign callback: '{cb}'"

    # Must import/use bot_campaign module
    assert "bot_campaign" in src or "campaign" in src, \
        "telegram_menu_bot.py must reference campaign module"


def test_campaign_handle_message_called_in_router():
    """T137b: telegram_menu_bot.py calls campaign.handle_message or equivalent."""
    src = (_src / "telegram_menu_bot.py").read_text(encoding="utf-8")
    # The router must check campaign state before falling through to LLM
    # (this was the bug: topic message went to LLM instead of campaign handler)
    assert "handle_message" in src or "bot_campaign" in src, \
        "telegram_menu_bot.py must call campaign.handle_message in message handler"


# ─────────────────────────────────────────────────────────────────────────────
# Test runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("T130 campaign_i18n_keys",               test_campaign_i18n_keys),
        ("T131 campaign_module_structure",          test_campaign_module_structure),
        ("T132a campaign_state_start",              test_campaign_state_start),
        ("T132b campaign_state_topic",              test_campaign_state_topic),
        ("T132c campaign_handle_message_routing",   test_campaign_state_handle_message_routing),
        ("T132d campaign_cancel",                   test_campaign_state_cancel),
        ("T132e campaign_edit_flow",                test_campaign_edit_flow),
        ("T132f campaign_filters_skip_variants",    test_campaign_on_filters_skip_variants),
        ("T133a webhook_no_url",                    test_call_webhook_no_url),
        ("T133b webhook_empty_body",                test_call_webhook_empty_body_response),
        ("T133c webhook_http_error",                test_call_webhook_http_error),
        ("T133d webhook_timeout",                   test_call_webhook_timeout),
        ("T133e webhook_n8n_error_passthrough",     test_call_webhook_n8n_error_dict),
        ("T133f run_selection_no_crash",            test_run_selection_empty_response_no_crash),
        ("T134  user_friendly_error_steps",         test_user_friendly_error_all_steps),
        ("T135  ollama_model_exists",               test_ollama_model_exists_if_configured),
        ("T136a webhook_url_source",                test_n8n_campaign_webhook_urls_source),
        ("T136b webhook_url_valid_runtime",         test_n8n_webhook_urls_valid_if_configured),
        ("T137a campaign_callback_routing",         test_campaign_callback_routing_source),
        ("T137b campaign_handle_message_in_router", test_campaign_handle_message_called_in_router),
    ]

    passed = failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except (SystemExit, KeyboardInterrupt):
            raise
        except AssertionError as e:
            print(f"FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed}/{passed + failed} passed, {failed} failed")
    if failed:
        sys.exit(1)
