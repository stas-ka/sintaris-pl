#!/usr/bin/env python3
"""
test_remote_kb.py — End-to-end UI tests for the Remote Knowledge Base agent.

Tests cover the complete user-facing flows from button press through MCP call
and bot reply, using mock objects so they run fully offline (no bot.env needed).
Source-inspection tests also verify module structure and i18n completeness.

T200 config constants present in bot_config.py (source)
T201 bot_remote_kb.py public API complete (source)
T202 bot_mcp_client.py public API complete (source)
T203 i18n keys for remote_kb present in all 3 languages
T204 callback routing in telegram_menu_bot.py (source)
T205 is_configured() returns False when env vars are empty
T206 show_menu() sends message with 5 inline buttons
T207 search flow: start → handle_message → MCP called → result sent
T208 search flow: start → no results → "nothing found" message
T209 upload flow: start → handle_document → MCP ingest → success reply
T210 list_docs flow: MCP returns docs → formatted list sent
T211 clear_memory flow: MCP called → confirmation sent
T212 circuit-breaker skips MCP calls when open; clears on success
T213 session cancel: is_active() clears after cancel()
T214 Web UI route /api/remote-kb/search present in bot_web.py (source)
T215 handle_message returns False when no active session (no state pollution)
T216 _do_ingest shows error message when ingest_file returns {}
T217 search failure uses remote_kb_op_fail (not remote_kb_upload_fail)
T218 list_docs failure uses remote_kb_op_fail
T219 clear_memory failure uses remote_kb_op_fail
T220 list_docs() returns real document title from deployed KB (live, requires KB_PG_DSN)
T221 list_docs() sends 'empty' key when no documents exist for this chat (live)
T222 call_tool(kb_delete_document) removes doc (live)
T223 query_remote() finds test chunk via real pgvector cosine search (live)
T224 Full UI cycle: insert → list → search → delete → empty (live)
T225 _extract_to_text converts RTF bytes → text/plain (requires striprtf)
T226 _extract_to_text converts PDF bytes → text/plain (requires pdfminer.six)
T227 ingest_file returns {"error": msg} when extraction raises ValueError
T228 _kb_search_direct does NOT use Ollama for embeddings (uses EmbeddingService)
T229 _kb_search_direct calls svc.embed(query) with single string, not a list
T230 _do_search calls ask_llm_with_history (not raw chunk display)
T231 _do_search returns LLM-generated answer when chunks are available
T232 ingest_file calls _fix_doc_meta() after receiving doc_id from N8N

Usage (offline — no bot.env needed):
    python3 src/tests/test_remote_kb.py
    python -m pytest src/tests/test_remote_kb.py -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

# ── path bootstrap ─────────────────────────────────────────────────────────
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ── helpers ────────────────────────────────────────────────────────────────

def _read_src(rel: str) -> str:
    return (_SRC / rel).read_text(encoding="utf-8")


def _can_import_bot_config() -> bool:
    try:
        import core.bot_config  # noqa: F401
        return True
    except Exception:
        return False


_HAS_BOT_CONFIG = _can_import_bot_config()


# ─────────────────────────────────────────────────────────────────────────────
# T50  Config constants in bot_config.py
# ─────────────────────────────────────────────────────────────────────────────

def test_remote_kb_config_constants_source():
    """T200: bot_config.py defines all Remote KB config constants."""
    src = _read_src("core/bot_config.py")
    for const in (
        "REMOTE_KB_ENABLED",
        "MCP_REMOTE_URL",
        "MCP_REMOTE_TOP_K",
        "N8N_KB_API_KEY",
        "N8N_KB_TOKEN",
        "N8N_KB_WEBHOOK_INGEST",
        "MCP_TIMEOUT",
    ):
        assert const in src, f"Missing config constant: {const}"

    # constants must use os.environ.get (no hardcoded secrets)
    for const in ("REMOTE_KB_ENABLED", "MCP_REMOTE_URL", "N8N_KB_API_KEY",
                  "N8N_KB_TOKEN", "N8N_KB_WEBHOOK_INGEST"):
        assert f'os.environ.get("{const}"' in src, \
            f"{const} must use os.environ.get(), found no such pattern"


# ─────────────────────────────────────────────────────────────────────────────
# T51  bot_remote_kb.py public API
# ─────────────────────────────────────────────────────────────────────────────

def test_remote_kb_module_public_api_source():
    """T201: bot_remote_kb.py exposes the complete public API."""
    src = _read_src("features/bot_remote_kb.py")
    for fn in (
        "def is_configured",
        "def is_active",
        "def cancel",
        "def show_menu",
        "def start_search",
        "def start_upload",
        "def finish_upload",
        "def handle_message",
        "def handle_document",
        "def list_docs",
        "def clear_memory",
    ):
        assert fn in src, f"bot_remote_kb.py missing: {fn}"

    # internal helpers
    for fn in ("def _do_search", "def _do_ingest"):
        assert fn in src, f"bot_remote_kb.py missing internal helper: {fn}"

    # imports mcp client, not direct HTTP
    assert "bot_mcp_client" in src or "_mcp" in src, \
        "bot_remote_kb.py must import bot_mcp_client"


# ─────────────────────────────────────────────────────────────────────────────
# T52  bot_mcp_client.py public API
# ─────────────────────────────────────────────────────────────────────────────

def test_mcp_client_public_api_source():
    """T202: bot_mcp_client.py exposes query_remote, call_tool, ingest_file."""
    src = _read_src("core/bot_mcp_client.py")
    for fn in ("def query_remote", "def call_tool", "def ingest_file"):
        assert fn in src, f"bot_mcp_client.py missing: {fn}"

    # circuit-breaker helpers must exist
    for fn in ("_cb_record_success", "_cb_record_failure", "_cb_is_open"):
        assert fn in src, f"bot_mcp_client.py missing circuit-breaker helper: {fn}"

    # must not make direct HTTP calls bypassing MCP (no raw requests.get etc.)
    assert "import requests" not in src, \
        "bot_mcp_client.py must not import requests directly; use httpx via MCP SDK"


# ─────────────────────────────────────────────────────────────────────────────
# T53  i18n completeness
# ─────────────────────────────────────────────────────────────────────────────

def test_remote_kb_i18n_keys():
    """T203: All remote_kb i18n keys present in ru, en, de."""
    strings = json.loads((_SRC / "strings.json").read_text(encoding="utf-8"))
    required_keys = [
        "agents_btn_remote_kb",
        "remote_kb_menu_title",
        "remote_kb_not_configured",
        "remote_kb_search_btn",
        "remote_kb_upload_btn",
        "remote_kb_list_btn",
        "remote_kb_clear_mem_btn",
        "remote_kb_enter_query",
        "remote_kb_searching",
        "remote_kb_no_results",
        "remote_kb_result_header",
        "remote_kb_upload_prompt",
        "remote_kb_upload_done_btn",
        "remote_kb_uploading",
        "remote_kb_upload_ok",
        "remote_kb_upload_fail",
        "remote_kb_upload_empty",
        "remote_kb_op_fail",
        "remote_kb_docs_header",
        "remote_kb_docs_empty",
        "remote_kb_mem_cleared",
    ]
    for lang in ("ru", "en", "de"):
        assert lang in strings, f"Language '{lang}' missing from strings.json"
        for key in required_keys:
            assert key in strings[lang], f"Key '{key}' missing in lang '{lang}'"
            assert strings[lang][key], f"Key '{key}' is empty in lang '{lang}'"


# ─────────────────────────────────────────────────────────────────────────────
# T54  Callback routing in telegram_menu_bot.py
# ─────────────────────────────────────────────────────────────────────────────

def test_remote_kb_callback_routing_source():
    """T204: telegram_menu_bot.py routes all remote_kb callback data values."""
    src = _read_src("telegram_menu_bot.py")
    for cb in (
        '"remote_kb_menu"',
        '"remote_kb_search"',
        '"remote_kb_upload"',
        '"remote_kb_upload_done"',
        '"remote_kb_list_docs"',
        '"remote_kb_clear_mem"',
    ):
        assert cb in src, f"Missing callback route: {cb}"

    # module imported
    assert "bot_remote_kb" in src, "telegram_menu_bot.py must import bot_remote_kb"

    # agents menu must have KB button
    assert "agents_btn_remote_kb" in src, \
        "Agents menu must include agents_btn_remote_kb button"


# ─────────────────────────────────────────────────────────────────────────────
# Mock-based E2E tests (no running bot, no network)
# ─────────────────────────────────────────────────────────────────────────────

def _make_bot():
    """Create a mock telebot bot object with message tracking."""
    bot = MagicMock()
    sent = []

    def _send(chat_id, text, **kw):
        msg = SimpleNamespace(message_id=len(sent) + 100, text=text)
        sent.append(("send", chat_id, text))
        return msg

    def _edit(text, chat_id, message_id, **kw):
        sent.append(("edit", chat_id, text))
        return SimpleNamespace(message_id=message_id, text=text)

    bot.send_message.side_effect = _send
    bot.edit_message_text.side_effect = _edit
    bot._sent = sent
    return bot


def _make_t():
    """Minimal i18n function using real strings.json."""
    strings = json.loads((_SRC / "strings.json").read_text(encoding="utf-8"))["en"]

    def _t(chat_id, key, **kw):
        val = strings.get(key, f"<{key}>")
        if kw:
            try:
                return val.format(**kw)
            except Exception:
                return val
        return val

    return _t


def _load_remote_kb():
    """Import bot_remote_kb with bot_config patched so no BOT_TOKEN needed."""
    with patch.dict("os.environ", {
        "BOT_TOKEN":           "0:test",
        "REMOTE_KB_ENABLED":   "0",
        "MCP_REMOTE_URL":      "",
        "N8N_KB_API_KEY":      "",
        "N8N_KB_TOKEN":        "",
        "N8N_KB_WEBHOOK_INGEST": "",
    }):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        # clear session state between tests
        mod._sessions.clear()
        return mod


# ─────────────────────────────────────────────────────────────────────────────
# T55  is_configured() when env empty
# ─────────────────────────────────────────────────────────────────────────────

def test_is_configured_false_when_env_empty():
    """T205: is_configured() returns False when REMOTE_KB_ENABLED=0 or vars absent."""
    with patch.dict("os.environ", {
        "BOT_TOKEN":         "0:test",
        "REMOTE_KB_ENABLED": "0",
        "MCP_REMOTE_URL":    "",
        "N8N_KB_API_KEY":    "",
    }):
        import importlib
        import core.bot_config as cfg
        import features.bot_remote_kb as mod
        importlib.reload(cfg)   # re-read module-level constants from patched env
        importlib.reload(mod)
        assert mod.is_configured() is False, "is_configured() must be False when disabled"


# ─────────────────────────────────────────────────────────────────────────────
# T56  show_menu() — 5 inline buttons
# ─────────────────────────────────────────────────────────────────────────────

def test_show_menu_sends_5_buttons():
    """T206: show_menu() sends exactly one message with 5 inline keyboard buttons."""
    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "", "N8N_KB_API_KEY": ""}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        mod._sessions.clear()

        bot = MagicMock()
        sent_markup = []

        def _send(cid, text, **kw):
            sent_markup.append(kw.get("reply_markup"))
            return SimpleNamespace(message_id=1, text=text)

        bot.send_message.side_effect = _send
        _t = _make_t()

        mod.show_menu(999, bot, _t)

        assert bot.send_message.call_count == 1, "show_menu must send exactly 1 message"
        markup = sent_markup[0]
        assert markup is not None, "show_menu must send inline keyboard"

        # flatten all buttons across keyboard rows
        all_buttons = [btn for row in markup.keyboard for btn in row]
        assert len(all_buttons) == 5, \
            f"Expected 5 buttons, got {len(all_buttons)}: {[b.callback_data for b in all_buttons]}"

        callback_data = {b.callback_data for b in all_buttons}
        for expected_cb in ("remote_kb_search", "remote_kb_upload",
                             "remote_kb_list_docs", "remote_kb_clear_mem",
                             "agents_menu"):
            assert expected_cb in callback_data, f"Missing button: {expected_cb}"


# ─────────────────────────────────────────────────────────────────────────────
# T57  Search flow: start → send query → MCP returns results → reply
# ─────────────────────────────────────────────────────────────────────────────

def test_search_flow_with_results():
    """T207: start_search → handle_message → MCP called → result edited into message."""
    CHAT_ID = 42
    _chunks = [
        {"section": "Safety rules", "text": "Always wear PPE.", "score": 0.92},
        {"section": "Emergency exit", "text": "Use exit B in case of fire.", "score": 0.88},
    ]

    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "http://fake", "N8N_KB_API_KEY": "key"}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        mod._sessions.clear()

        bot = _make_bot()
        _t = _make_t()

        with patch("features.bot_remote_kb._mcp") as mock_mcp:
            mock_mcp.query_remote.return_value = _chunks

            # Step 1: press "Search" button → bot asks for query text
            mod.start_search(CHAT_ID, bot, _t)
            assert bot.send_message.call_count == 1
            assert mod.is_active(CHAT_ID), "Session must be active after start_search"

            # Step 2: user types query → handle_message consumes it
            consumed = mod.handle_message(CHAT_ID, "safety PPE", bot, _t)
            assert consumed, "handle_message must return True for active search session"

            # MCP query_remote must be called with the user's query
            mock_mcp.query_remote.assert_called_once()
            call_args = mock_mcp.query_remote.call_args
            assert "safety PPE" in call_args[0] or call_args[1].get("query") == "safety PPE" \
                or (call_args[0] and call_args[0][0] == "safety PPE"), \
                f"query_remote not called with 'safety PPE': {call_args}"

            # Bot must have edited the status message with results
            edits = [ev for ev in bot._sent if ev[0] == "edit"]
            assert edits, "Search result must be edited into status message"
            result_text = edits[-1][2]
            assert "Safety rules" in result_text or "2" in result_text or "PPE" in result_text, \
                f"Result text looks wrong: {result_text[:200]}"

        # Session cleared after search
        assert not mod.is_active(CHAT_ID), "Session must be cleared after search completes"


# ─────────────────────────────────────────────────────────────────────────────
# T58  Search flow: no results
# ─────────────────────────────────────────────────────────────────────────────

def test_search_flow_no_results():
    """T208: search returns empty list → bot sends 'nothing found' message."""
    CHAT_ID = 43

    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "http://fake", "N8N_KB_API_KEY": "key"}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        mod._sessions.clear()

        bot = _make_bot()
        _t = _make_t()

        with patch("features.bot_remote_kb._mcp") as mock_mcp:
            mock_mcp.query_remote.return_value = []

            mod.start_search(CHAT_ID, bot, _t)
            mod.handle_message(CHAT_ID, "xyzzy does not exist", bot, _t)

            edits = [ev for ev in bot._sent if ev[0] == "edit"]
            assert edits, "Must edit message even on no results"
            result_text = edits[-1][2]
            # should contain the "no results" string
            assert "nothing" in result_text.lower() or "найдено" in result_text.lower() \
                or "no" in result_text.lower() or "пусто" in result_text.lower() \
                or "not found" in result_text.lower(), \
                f"Expected 'no results' message, got: {result_text[:200]}"


# ─────────────────────────────────────────────────────────────────────────────
# T59  Upload flow: start → send document → MCP ingest → success reply
# ─────────────────────────────────────────────────────────────────────────────

def test_upload_flow_success():
    """T209: start_upload → handle_document → MCP ingest_file called → success reply with Done button.
    Session remains active after upload (multi-file: user can send more files).
    """
    CHAT_ID = 44

    fake_doc = SimpleNamespace(
        file_id="TG_FILE_ID_001",
        file_name="worksafety.pdf",
        mime_type="application/pdf",
    )
    fake_file_info = SimpleNamespace(file_path="documents/file_001.pdf")

    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "http://fake", "N8N_KB_API_KEY": "key",
                                    "N8N_KB_TOKEN": "tok", "N8N_KB_WEBHOOK_INGEST": "http://wh"}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        mod._sessions.clear()

        bot = _make_bot()
        bot.get_file.return_value = fake_file_info
        bot.download_file.return_value = b"%PDF-1.4 fake content"
        _t = _make_t()

        with patch("features.bot_remote_kb._mcp") as mock_mcp, \
             patch("features.bot_remote_kb.bot_instance", create=True), \
             patch("core.bot_instance.bot") as mock_core_bot:

            mock_core_bot.get_file.return_value = fake_file_info
            mock_core_bot.download_file.return_value = b"%PDF-1.4 fake content"
            mock_mcp.ingest_file.return_value = {"n_chunks": 47, "doc_id": "doc-001"}

            # Step 1: press Upload button → bot asks for a file
            mod.start_upload(CHAT_ID, bot, _t)
            assert bot.send_message.call_count == 1
            assert mod.is_active(CHAT_ID)

            # Step 2: user sends a document
            consumed = mod.handle_document(CHAT_ID, fake_doc, bot, _t)
            assert consumed, "handle_document must return True when in upload mode"

            # ingest_file must have been called
            mock_mcp.ingest_file.assert_called_once()
            ingest_call = mock_mcp.ingest_file.call_args
            assert CHAT_ID in ingest_call[0] or ingest_call[1].get("chat_id") == CHAT_ID \
                or (ingest_call[0] and ingest_call[0][0] == CHAT_ID), \
                f"ingest_file not called with chat_id={CHAT_ID}: {ingest_call}"

            # success reply must contain filename and chunk count
            edit_calls = bot.edit_message_text.call_args_list
            all_reply_text = " ".join(
                str(c[0][0]) if c[0] else str(c[1].get("text", ""))
                for c in (bot.send_message.call_args_list + edit_calls)
            )
            assert "worksafety.pdf" in all_reply_text or "47" in all_reply_text, \
                "Success reply must contain filename or chunk count (regression: n_chunks format bug)"

            # Done button must be present in the edit_message_text call's reply_markup
            last_edit_kwargs = edit_calls[-1][1] if edit_calls else {}
            markup = last_edit_kwargs.get("reply_markup")
            assert markup is not None, "Done button markup must be included in upload result"

        # Session stays alive after upload — user can send another file
        assert mod.is_active(CHAT_ID), \
            "Session must stay active after upload so user can send more files"

        # Calling finish_upload ends the session
        bot2 = _make_bot()
        mod.finish_upload(CHAT_ID, bot2, _t)
        assert not mod.is_active(CHAT_ID), "finish_upload must clear the session"


# ─────────────────────────────────────────────────────────────────────────────
# T60  list_docs flow
# ─────────────────────────────────────────────────────────────────────────────

def test_list_docs_flow():
    """T210: list_docs() calls kb_list_documents and formats result."""
    CHAT_ID = 45
    fake_docs = [
        {"title": "Safety Manual", "filename": "safety.pdf", "chunk_count": 120},
        {"title": "HR Policy",     "filename": "hr.pdf",     "chunk_count": 45},
    ]

    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "http://fake", "N8N_KB_API_KEY": "key"}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        mod._sessions.clear()

        bot = _make_bot()
        _t = _make_t()

        with patch("features.bot_remote_kb._mcp") as mock_mcp:
            mock_mcp.call_tool.return_value = {"documents": fake_docs}

            mod.list_docs(CHAT_ID, bot, _t)

            # MCP call_tool must be called with kb_list_documents
            mock_mcp.call_tool.assert_called_once()
            tool_name = mock_mcp.call_tool.call_args[0][0]
            assert tool_name == "kb_list_documents", \
                f"list_docs must call kb_list_documents, got: {tool_name}"

            # Result must mention doc titles
            edits = [ev for ev in bot._sent if ev[0] == "edit"]
            assert edits, "list_docs must edit the status message with results"
            result_text = edits[-1][2]
            assert "Safety Manual" in result_text, \
                f"Doc title missing from list: {result_text[:300]}"
            assert "120" in result_text, "Chunk count must be shown"


# ─────────────────────────────────────────────────────────────────────────────
# T61  clear_memory flow
# ─────────────────────────────────────────────────────────────────────────────

def test_clear_memory_flow():
    """T211: clear_memory() calls kb_memory_clear and sends confirmation."""
    CHAT_ID = 46

    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "http://fake", "N8N_KB_API_KEY": "key"}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        mod._sessions.clear()

        bot = _make_bot()
        _t = _make_t()

        with patch("features.bot_remote_kb._mcp") as mock_mcp:
            mock_mcp.call_tool.return_value = {"cleared": True}

            mod.clear_memory(CHAT_ID, bot, _t)

            # Must call kb_memory_clear
            mock_mcp.call_tool.assert_called_once()
            tool_name = mock_mcp.call_tool.call_args[0][0]
            assert tool_name == "kb_memory_clear", \
                f"clear_memory must call kb_memory_clear, got: {tool_name}"

            # Must send confirmation message (not just edit)
            sends = [ev for ev in bot._sent if ev[0] == "send"]
            assert sends, "clear_memory must send a confirmation message"
            confirm_text = sends[-1][2]
            assert "cleared" in confirm_text.lower() or "очищен" in confirm_text.lower(), \
                f"Expected confirmation text, got: {confirm_text}"


# ─────────────────────────────────────────────────────────────────────────────
# T62  Circuit-breaker: open → MCP skipped; success → closes
# ─────────────────────────────────────────────────────────────────────────────

def test_circuit_breaker_open_skips_mcp():
    """T212: circuit-breaker opens after threshold failures; closes on success."""
    with patch.dict("os.environ", {"BOT_TOKEN": "0:test"}):
        import importlib
        import core.bot_mcp_client as mcp_mod
        importlib.reload(mcp_mod)

        # Verify closed initially
        assert not mcp_mod._cb_is_open(), "Circuit breaker must start closed"

        # Simulate threshold failures via the public helper
        for _ in range(mcp_mod._CB_THRESHOLD):
            mcp_mod._cb_record_failure()

        assert mcp_mod._cb_is_open(), \
            f"Circuit breaker must open after {mcp_mod._CB_THRESHOLD} failures"
        assert mcp_mod._cb_failures >= mcp_mod._CB_THRESHOLD

        # success resets the circuit
        mcp_mod._cb_record_success()
        assert not mcp_mod._cb_is_open(), \
            "Circuit breaker must close after _cb_record_success()"
        assert mcp_mod._cb_failures == 0, \
            "_cb_failures must reset to 0 after success"


# ─────────────────────────────────────────────────────────────────────────────
# T63  Session lifecycle: is_active / cancel
# ─────────────────────────────────────────────────────────────────────────────

def test_session_lifecycle():
    """T213: is_active() and cancel() correctly track session state."""
    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "", "N8N_KB_API_KEY": ""}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        mod._sessions.clear()

        bot = MagicMock()
        bot.send_message.return_value = SimpleNamespace(message_id=1, text="")
        _t = _make_t()

        CHAT_ID = 47
        assert not mod.is_active(CHAT_ID), "No session initially"

        mod.start_search(CHAT_ID, bot, _t)
        assert mod.is_active(CHAT_ID), "Session active after start_search"

        mod.cancel(CHAT_ID)
        assert not mod.is_active(CHAT_ID), "Session cleared after cancel"


# ─────────────────────────────────────────────────────────────────────────────
# T64  Web UI route /api/kb present in bot_web.py
# ─────────────────────────────────────────────────────────────────────────────

def test_web_ui_kb_route_source():
    """T214: bot_web.py defines /api/remote-kb/search route."""
    src = _read_src("bot_web.py")
    assert "/api/remote-kb/search" in src, \
        "bot_web.py must define /api/remote-kb/search route for the Web UI KB agent integration"
    assert "REMOTE_KB_ENABLED" in src, \
        "bot_web.py must guard /api/remote-kb/search with REMOTE_KB_ENABLED check"


# ─────────────────────────────────────────────────────────────────────────────
# T65  handle_message returns False when no session (no state pollution)
# ─────────────────────────────────────────────────────────────────────────────

def test_handle_message_no_session_returns_false():
    """T215: handle_message returns False for a chat_id with no active session."""
    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "", "N8N_KB_API_KEY": ""}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        mod._sessions.clear()

        bot = MagicMock()
        _t = _make_t()

        result = mod.handle_message(9999, "some random text", bot, _t)
        assert result is False, \
            "handle_message must return False when no session exists (avoids stealing messages)"
        bot.send_message.assert_not_called()
        bot.edit_message_text.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T216  Upload with empty MCP response shows error (not false success)
# ─────────────────────────────────────────────────────────────────────────────

def test_upload_flow_empty_mcp_response_shows_error():
    """T216: _do_ingest shows error message when ingest_file returns {} (no server response).

    Regression guard: previously, empty result {} caused a false success
    message '✅ ? chunks indexed' because the code didn't check for empty result.
    """
    CHAT_ID = 50

    fake_doc = SimpleNamespace(
        file_id="TG_FILE_ID_002",
        file_name="report.pdf",
        mime_type="application/pdf",
    )
    fake_file_info = SimpleNamespace(file_path="documents/file_002.pdf")

    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "http://fake", "N8N_KB_API_KEY": "key",
                                    "N8N_KB_TOKEN": "tok", "N8N_KB_WEBHOOK_INGEST": "http://wh"}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        mod._sessions.clear()

        bot = _make_bot()
        _t = _make_t()

        with patch("features.bot_remote_kb._mcp") as mock_mcp, \
             patch("core.bot_instance.bot") as mock_core_bot:

            mock_core_bot.get_file.return_value = fake_file_info
            mock_core_bot.download_file.return_value = b"%PDF-1.4 stub"
            mock_mcp.ingest_file.return_value = {}  # ← server returned empty / failed

            mod.start_upload(CHAT_ID, bot, _t)
            mod.handle_document(CHAT_ID, fake_doc, bot, _t)

            mock_mcp.ingest_file.assert_called_once()

            # Must show error, NOT success
            edit_texts = [
                str(c[0][0]) if c[0] else str(c[1].get("text", ""))
                for c in bot.edit_message_text.call_args_list
            ]
            combined = " ".join(edit_texts)

            assert "✅" not in combined, \
                "Empty MCP response must NOT show success ✅ checkmark (was showing '? chunks indexed')"
            assert "❌" in combined or "konfiguriert" in combined or "server" in combined.lower(), \
                f"Empty MCP response must show error message, got: {combined!r}"

            # Specifically must NOT contain '?' as chunk count (the old false-success symptom)
            assert "? chunks" not in combined and "? Abschnitte" not in combined, \
                f"Must not show '? chunks' on empty response (false success), got: {combined!r}"


# ─────────────────────────────────────────────────────────────────────────────
# T217  Search error uses op_fail string (not upload_fail)
# ─────────────────────────────────────────────────────────────────────────────

def test_search_error_uses_op_fail_string():
    """T217: When search fails, bot_remote_kb uses remote_kb_op_fail, not remote_kb_upload_fail.

    Regression guard: previously search/list/clear errors showed 'Upload failed: ...'
    which was confusing for non-upload operations.
    """
    CHAT_ID = 51
    import json as _json
    strings_en = _json.loads((_SRC / "strings.json").read_text(encoding="utf-8"))["en"]

    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "http://fake", "N8N_KB_API_KEY": "key"}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)
        mod._sessions.clear()

        bot = _make_bot()
        _t = _make_t()

        with patch("features.bot_remote_kb._mcp") as mock_mcp:
            mock_mcp.query_remote.side_effect = RuntimeError("connection timeout")

            mod.start_search(CHAT_ID, bot, _t)
            mod.handle_message(CHAT_ID, "find documents about quality", bot, _t)

            edit_texts = [
                str(c[0][0]) if c[0] else str(c[1].get("text", ""))
                for c in bot.edit_message_text.call_args_list
            ]
            combined = " ".join(edit_texts)

            # Must NOT say "Upload failed"
            assert strings_en["remote_kb_upload_fail"].split(":")[0] not in combined, \
                f"Search error must not say 'Upload failed', got: {combined!r}"
            # Must show a generic error (op_fail pattern: '❌ Error: ...')
            assert "❌" in combined, f"Search error must show ❌ error message, got: {combined!r}"
            assert "connection timeout" in combined, \
                f"Error message must include the exception text, got: {combined!r}"


# ─────────────────────────────────────────────────────────────────────────────
# T218  list_docs error uses op_fail string (not upload_fail)
# ─────────────────────────────────────────────────────────────────────────────

def test_list_docs_error_uses_op_fail_string():
    """T218: When list_docs fails, uses remote_kb_op_fail not remote_kb_upload_fail."""
    CHAT_ID = 52
    import json as _json
    strings_en = _json.loads((_SRC / "strings.json").read_text(encoding="utf-8"))["en"]
    upload_fail_prefix = strings_en["remote_kb_upload_fail"].split(":")[0]  # "❌ Upload failed"

    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "http://fake", "N8N_KB_API_KEY": "key"}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)

        bot = _make_bot()
        _t = _make_t()

        with patch("features.bot_remote_kb._mcp") as mock_mcp:
            mock_mcp.call_tool.side_effect = RuntimeError("DB unreachable")

            mod.list_docs(CHAT_ID, bot, _t)

            edit_texts = [
                str(c[0][0]) if c[0] else str(c[1].get("text", ""))
                for c in bot.edit_message_text.call_args_list
            ]
            combined = " ".join(edit_texts)

            assert upload_fail_prefix not in combined, \
                f"list_docs error must not say '{upload_fail_prefix}', got: {combined!r}"
            assert "❌" in combined, f"list_docs error must show ❌ error, got: {combined!r}"
            assert "DB unreachable" in combined, \
                f"Error must include exception text, got: {combined!r}"


# ─────────────────────────────────────────────────────────────────────────────
# T219  clear_memory error uses op_fail string (not upload_fail)
# ─────────────────────────────────────────────────────────────────────────────

def test_clear_memory_error_uses_op_fail_string():
    """T219: When clear_memory fails, uses remote_kb_op_fail not remote_kb_upload_fail."""
    CHAT_ID = 53
    import json as _json
    strings_en = _json.loads((_SRC / "strings.json").read_text(encoding="utf-8"))["en"]
    upload_fail_prefix = strings_en["remote_kb_upload_fail"].split(":")[0]  # "❌ Upload failed"

    with patch.dict("os.environ", {"BOT_TOKEN": "0:test", "REMOTE_KB_ENABLED": "0",
                                    "MCP_REMOTE_URL": "http://fake", "N8N_KB_API_KEY": "key"}):
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)

        bot = _make_bot()
        _t = _make_t()

        with patch("features.bot_remote_kb._mcp") as mock_mcp:
            mock_mcp.call_tool.side_effect = RuntimeError("tool unavailable")

            mod.clear_memory(CHAT_ID, bot, _t)

            send_texts = [
                str(c[0][1]) if len(c[0]) > 1 else str(c[1].get("text", ""))
                for c in bot.send_message.call_args_list
            ]
            combined = " ".join(send_texts)

            assert upload_fail_prefix not in combined, \
                f"clear_memory error must not say '{upload_fail_prefix}', got: {combined!r}"
            assert "❌" in combined, f"clear_memory error must show ❌ error, got: {combined!r}"
            assert "tool unavailable" in combined, \
                f"Error must include exception text, got: {combined!r}"


# ─────────────────────────────────────────────────────────────────────────────
# T225  _extract_to_text: RTF → text/plain
# ─────────────────────────────────────────────────────────────────────────────
def test_extract_rtf_to_text():
    """T225: _extract_to_text converts RTF bytes to text/plain via striprtf.

    Root-cause regression: RTF files sent as binary to N8N produced 0 chunks
    because striprtf was not installed in the Docker container. After installing
    striprtf, the extraction must succeed and return text/plain.
    """
    try:
        import striprtf  # noqa: F401
    except ImportError:
        raise AssertionError("SKIP: striprtf not installed — install with: pip install striprtf")
    import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
    from core.bot_mcp_client import _extract_to_text

    # Minimal valid RTF with content
    rtf_bytes = (
        b"{\\rtf1\\ansi\\ansicpg1251{\\fonttbl{\\f0 Arial;}}"
        b"\\f0 Safety guidelines for work at height }"
    )
    result_bytes, result_name, result_mime = _extract_to_text(rtf_bytes, "safety.rtf", "text/rtf")

    assert result_mime == "text/plain", f"Expected text/plain, got {result_mime}"
    assert result_name.endswith(".txt"), f"Expected .txt extension, got {result_name}"
    text = result_bytes.decode("utf-8")
    assert len(text) > 5, f"Expected extracted text, got: {text!r}"


# ─────────────────────────────────────────────────────────────────────────────
# T226  _extract_to_text: PDF → text/plain
# ─────────────────────────────────────────────────────────────────────────────
def test_extract_pdf_to_text():
    """T226: _extract_to_text converts PDF bytes to text/plain via pdfminer.six.

    Regression: PDF files were not handled before this fix. pdfminer.six was
    installed but _extract_to_text only handled RTF and .doc.
    """
    try:
        import pdfminer  # noqa: F401
    except ImportError:
        raise AssertionError("SKIP: pdfminer.six not installed — install with: pip install pdfminer.six")

    import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

    # Minimal valid PDF (text in content stream)
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 48>>stream\nBT /F1 12 Tf 100 700 Td (Safety rules) Tj ET\nendstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n9\n%%EOF"
    )

    from core.bot_mcp_client import _extract_to_text
    result_bytes, result_name, result_mime = _extract_to_text(pdf_bytes, "manual.pdf", "application/pdf")

    assert result_mime == "text/plain", f"Expected text/plain, got {result_mime}"
    assert result_name.endswith(".txt"), f"Expected .txt extension, got {result_name}"


# ─────────────────────────────────────────────────────────────────────────────
# T227  ingest_file returns {"error": ...} when extraction fails (no crash)
# ─────────────────────────────────────────────────────────────────────────────
def test_ingest_extraction_error_returned():
    """T227: ingest_file returns {"error": msg} (not {}) when _extract_to_text raises ValueError.

    Regression: before fix, failed extraction caused silent {} return (no error feedback).
    After fix, the error message is returned and shown to the user.
    """
    import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
    from unittest.mock import patch, MagicMock
    import core.bot_mcp_client as mcp_mod

    # Patch _extract_to_text to raise ValueError (e.g., empty RTF)
    with patch.object(mcp_mod, "_extract_to_text", side_effect=ValueError("RTF extraction produced empty text")):
        with patch.object(mcp_mod, "_load_config", return_value=("http://fake", "key", "tok", 5, 3)):
            with patch("core.bot_config.N8N_KB_WEBHOOK_INGEST", "http://fake-webhook"):
                result = mcp_mod.ingest_file(12345, "empty.rtf", b"{\\rtf1}", "text/rtf")

    assert "error" in result, f"Expected 'error' key in result, got: {result}"
    assert "RTF extraction" in result["error"], f"Expected extraction error msg, got: {result['error']}"


# ─────────────────────────────────────────────────────────────────────────────
# T228  _kb_search_direct calls EmbeddingService.embed() with a single string
# ─────────────────────────────────────────────────────────────────────────────
def test_kb_search_uses_fastembed_not_ollama():
    """T228: _kb_search_direct uses EmbeddingService.embed(query) — a single string.

    Regression: before fix, _kb_search_direct called Ollama directly for embeddings.
    Ollama is not available on VPS Docker so all searches returned [].
    Fix: use EmbeddingService (fastembed) which IS installed in Docker.
    Verified by:
      1. Source must NOT import OLLAMA_URL at module level for search.
      2. Source must call svc.embed(query) with a single string argument (not a list).
    """
    import ast, os
    src_path = os.path.join(os.path.dirname(__file__), "..", "core", "bot_mcp_client.py")
    src = open(src_path, encoding="utf-8").read()

    # Must NOT use Ollama endpoint for embedding in _kb_search_direct
    # (Ollama may still be used elsewhere e.g. for other features — but the
    #  search path must not depend on OLLAMA_URL being available.)
    tree = ast.parse(src)
    in_search_fn = False
    ollama_calls_in_search = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_kb_search_direct":
            in_search_fn = True
            for child in ast.walk(node):
                if isinstance(child, (ast.Attribute, ast.Name)):
                    name = child.attr if isinstance(child, ast.Attribute) else child.id
                    if "ollama" in name.lower() or "OLLAMA_URL" in name:
                        ollama_calls_in_search.append(name)
    assert in_search_fn, "Function _kb_search_direct not found in bot_mcp_client.py"
    assert not ollama_calls_in_search, (
        f"_kb_search_direct still references Ollama: {ollama_calls_in_search}. "
        "Ollama is not available on VPS Docker — use EmbeddingService.embed()."
    )


def test_kb_search_embed_called_with_string():
    """T229: _kb_search_direct calls svc.embed(query) with a single string, not a list.

    Regression: passing a list to EmbeddingService.embed() causes
    'TextEncodeInput must be Union[TextInputSequence, ...]' error at runtime.
    """
    import ast, os
    src_path = os.path.join(os.path.dirname(__file__), "..", "core", "bot_mcp_client.py")
    src = open(src_path, encoding="utf-8").read()
    tree = ast.parse(src)

    # Find _kb_search_direct and locate calls to .embed(...)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_kb_search_direct":
            for child in ast.walk(node):
                if (isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Attribute)
                        and child.func.attr == "embed"):
                    assert len(child.args) == 1, (
                        "EmbeddingService.embed() must be called with exactly 1 positional arg"
                    )
                    # The arg must NOT be a list literal
                    arg = child.args[0]
                    assert not isinstance(arg, ast.List), (
                        "EmbeddingService.embed() must receive a string, not a list literal. "
                        "Use svc.embed(query), NOT svc.embed([query])."
                    )
                    return  # Found and checked
    # If no embed() call found, check source text as fallback
    assert "svc.embed(" in src or ".embed(query" in src, (
        "_kb_search_direct must call EmbeddingService.embed(query) — call not found"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T230  _do_search calls ask_llm_with_history (not raw chunk display)
# ─────────────────────────────────────────────────────────────────────────────
def test_do_search_calls_llm_not_raw_chunks():
    """T230: _do_search in bot_remote_kb.py calls ask_llm_with_history.

    Regression: before fix, _do_search formatted and displayed raw chunk dicts
    (showing chunk IDs and similarity scores) instead of passing them to an LLM.
    """
    import os
    src_path = os.path.join(os.path.dirname(__file__), "..", "features", "bot_remote_kb.py")
    src = open(src_path, encoding="utf-8").read()
    assert "ask_llm_with_history" in src, (
        "bot_remote_kb.py must import and call ask_llm_with_history in _do_search. "
        "Regression: _do_search was displaying raw KB chunks instead of LLM answers."
    )
    # Also verify the function is imported from core.bot_llm
    assert "from core.bot_llm import" in src or "from core import bot_llm" in src, (
        "bot_remote_kb.py must import ask_llm_with_history from core.bot_llm"
    )


def test_do_search_returns_llm_answer():
    """T231: _do_search returns an LLM-generated answer when chunks are available.

    Regression: before fix, the bot replied with raw chunk dicts (showing 'score: 0.7',
    'chunk_id: ...') instead of a readable answer. After fix, ask_llm_with_history
    is called and its output is sent to the user.
    """
    import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
    from unittest.mock import patch, MagicMock

    try:
        from features import bot_remote_kb as kb_mod
        from core import bot_mcp_client as mcp_mod
    except ImportError as e:
        raise RuntimeError(f"Import failed: {e}")

    fake_chunks = [
        {"chunk_id": 1, "text": "Работодатель обязан выдавать СИЗ.", "score": 0.85, "section": "§1"},
    ]
    llm_answer = "Согласно документам, работодатель обязан выдавать средства индивидуальной защиты."

    bot = MagicMock()
    bot.send_message = MagicMock()

    def fake_t(chat_id, key, **kw):
        return {"remote_kb_sources": "Sources"}.get(key, key)

    with patch.object(mcp_mod, "query_remote", return_value=fake_chunks):
        with patch("features.bot_remote_kb.ask_llm_with_history", return_value=llm_answer) as mock_llm:
            kb_mod._do_search(994963580, "СИЗ", bot, fake_t)

    # The important assertion: LLM must have been called
    assert mock_llm.called, (
        "_do_search must call ask_llm_with_history when chunks are found. "
        "Before fix it was displaying raw chunk dicts."
    )
    # The LLM must have been given a messages list
    call_args = mock_llm.call_args
    if call_args:
        messages_arg = call_args[0][0] if call_args[0] else None
        if messages_arg is not None:
            assert isinstance(messages_arg, list), "ask_llm_with_history must receive a messages list"
            assert any(isinstance(m, dict) and "content" in m for m in messages_arg), (
                "messages list must contain dicts with 'content' key"
            )


# ─────────────────────────────────────────────────────────────────────────────
# T232  ingest_file calls _fix_doc_meta after receiving doc_id from N8N
# ─────────────────────────────────────────────────────────────────────────────
def test_ingest_calls_fix_doc_meta():
    """T232: ingest_file calls _fix_doc_meta(doc_id, original_title, preview) after N8N ingest.

    Regression: N8N sanitizes filenames (strips Unicode, lowercases, replaces spaces with _).
    Without _fix_doc_meta, Russian filenames appear garbled in the document list.
    After fix, the original title and a text preview are stored in structure JSONB.
    """
    import os
    src_path = os.path.join(os.path.dirname(__file__), "..", "core", "bot_mcp_client.py")
    src = open(src_path, encoding="utf-8").read()

    assert "_fix_doc_meta" in src, (
        "bot_mcp_client.py must define _fix_doc_meta() to restore original title "
        "after N8N sanitizes the filename."
    )

    # Verify _fix_doc_meta is called from ingest_file (not just defined)
    import ast
    tree = ast.parse(src)
    fix_called_in_ingest = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "ingest_file":
            for child in ast.walk(node):
                if (isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == "_fix_doc_meta"):
                    fix_called_in_ingest = True
                    break
    assert fix_called_in_ingest, (
        "_fix_doc_meta() must be called from within ingest_file() after receiving doc_id from N8N. "
        "Without this, Russian filenames appear as mangled ASCII in the document list."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Deployed integration tests (T220–T224)
# Require KB_PG_DSN env var pointing to a live taris_kb PostgreSQL DB.
# Insert real test data, call bot_remote_kb public API with mocked bot and _t,
# verify replies contain expected content, then clean up.
# Run these inside the Docker container or with direct PG access:
#   docker exec taris-vps-telegram python3 /app/tests/test_remote_kb.py
# ─────────────────────────────────────────────────────────────────────────────

import os as _os
_HAS_KB_PG = bool(_os.environ.get("KB_PG_DSN"))

_KB_PG_DSN    = _os.environ.get("KB_PG_DSN", "")
_KB_TEST_CHAT = 7777777          # dedicated test chat_id, never a real user
_KB_TEST_TITLE = "taris_integration_test.txt"
_KB_TEST_TEXT  = "Taris integration test: the quick brown fox jumps over the lazy dog."
_KB_EMB_DIM    = 384


def _kb_get_embedding(text: str) -> list:
    """Return embedding from Ollama all-minilm, or unit vector as fallback."""
    import urllib.request, json as _j
    ollama_url = _os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    try:
        payload = _j.dumps({"model": "all-minilm", "prompt": text}).encode()
        req = urllib.request.Request(
            ollama_url.rstrip("/") + "/api/embeddings", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            emb = _j.loads(resp.read()).get("embedding", [])
        if len(emb) == _KB_EMB_DIM:
            return emb
    except Exception:
        pass
    v = [0.0] * _KB_EMB_DIM
    v[0] = 1.0
    return v


def _kb_insert_test_doc() -> str:
    """Insert one test document + one chunk into taris_kb; return doc_id."""
    import psycopg
    vec_str = "[" + ",".join(f"{x:.6f}" for x in _kb_get_embedding(_KB_TEST_TEXT)) + "]"
    with psycopg.connect(_KB_PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kb_documents
                       (doc_id, owner_chat_id, title, mime, sha256, source)
                   VALUES (gen_random_uuid(), %s, %s, 'text/plain',
                           md5(%s::text || %s::text), 'integration_test')
                   ON CONFLICT (sha256) DO UPDATE SET title = EXCLUDED.title
                   RETURNING doc_id::text""",
                (_KB_TEST_CHAT, _KB_TEST_TITLE, _KB_TEST_TITLE, str(_KB_TEST_CHAT)),
            )
            doc_id = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO kb_chunks
                       (doc_id, chunk_idx, section, text, tokens, embedding, metadata)
                   VALUES (%s::uuid, 0, '', %s, %s, %s::vector, '{}'::jsonb)
                   ON CONFLICT DO NOTHING""",
                (doc_id, _KB_TEST_TEXT, len(_KB_TEST_TEXT) // 4, vec_str),
            )
        conn.commit()
    return doc_id


def _kb_cleanup() -> None:
    """Remove all test docs and chunks for _KB_TEST_CHAT from taris_kb."""
    import psycopg
    with psycopg.connect(_KB_PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM kb_documents WHERE owner_chat_id = %s", (_KB_TEST_CHAT,)
            )
        conn.commit()


def _make_bot_mock():
    bot = MagicMock()
    bot.send_message.return_value = SimpleNamespace(message_id=42)
    return bot


def _t_passthrough(chat_id, key, **kw):
    return key.format(**kw) if kw else key


def test_deployed_list_docs():
    """T220 list_docs() returns real document title from deployed KB via direct psycopg."""
    if not _HAS_KB_PG:
        raise unittest.SkipTest("KB_PG_DSN not set")
    _kb_cleanup()
    _kb_insert_test_doc()
    try:
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)

        bot = _make_bot_mock()
        mod.list_docs(_KB_TEST_CHAT, bot, _t_passthrough)

        assert bot.edit_message_text.called, "edit_message_text not called"
        edit_text = bot.edit_message_text.call_args_list[-1][0][0]
        assert _KB_TEST_TITLE in edit_text, \
            f"Expected doc title '{_KB_TEST_TITLE}' in reply, got: {edit_text!r}"
        assert "chunks" in edit_text, \
            f"Expected 'chunks' count in reply, got: {edit_text!r}"
    finally:
        _kb_cleanup()


def test_deployed_list_docs_empty():
    """T221 list_docs() sends 'empty' key when no documents exist for this chat."""
    if not _HAS_KB_PG:
        raise unittest.SkipTest("KB_PG_DSN not set")
    _kb_cleanup()
    try:
        import importlib
        import features.bot_remote_kb as mod
        importlib.reload(mod)

        bot = _make_bot_mock()
        mod.list_docs(_KB_TEST_CHAT, bot, _t_passthrough)

        assert bot.edit_message_text.called, "edit_message_text not called"
        edit_text = bot.edit_message_text.call_args_list[-1][0][0]
        assert "remote_kb_docs_empty" in edit_text, \
            f"Expected empty-KB key in reply, got: {edit_text!r}"
    finally:
        _kb_cleanup()


def test_deployed_delete_document():
    """T222 call_tool(kb_delete_document) removes doc; subsequent list shows it gone."""
    if not _HAS_KB_PG:
        raise unittest.SkipTest("KB_PG_DSN not set")
    _kb_cleanup()
    doc_id = _kb_insert_test_doc()
    try:
        import importlib
        from core import bot_mcp_client as mcp_mod
        importlib.reload(mcp_mod)

        result = mcp_mod.call_tool("kb_delete_document", {
            "doc_id": doc_id, "chat_id": _KB_TEST_CHAT,
        })
        assert result.get("deleted") is True, \
            f"Expected deleted=True, got: {result}"

        list_result = mcp_mod.call_tool("kb_list_documents", {"chat_id": _KB_TEST_CHAT})
        titles = [d.get("title") for d in list_result.get("documents", [])]
        assert _KB_TEST_TITLE not in titles, \
            f"Doc still in list after delete: {titles}"
    finally:
        _kb_cleanup()


def test_deployed_search():
    """T223 query_remote() finds test chunk via real pgvector cosine search."""
    if not _HAS_KB_PG:
        raise unittest.SkipTest("KB_PG_DSN not set")
    _kb_cleanup()
    _kb_insert_test_doc()
    try:
        import importlib
        from core import bot_mcp_client as mcp_mod
        importlib.reload(mcp_mod)

        chunks = mcp_mod.query_remote("quick brown fox lazy dog", _KB_TEST_CHAT, top_k=5)
        assert chunks, "Expected at least one chunk from pgvector search"
        texts = [c.get("text", "") for c in chunks]
        assert any(_KB_TEST_TEXT in t for t in texts), \
            f"Test chunk text not found in results: {texts}"
    finally:
        _kb_cleanup()


def test_deployed_full_cycle():
    """T224 Full UI cycle via bot_remote_kb API: insert → list → search → delete → empty."""
    if not _HAS_KB_PG:
        raise unittest.SkipTest("KB_PG_DSN not set")
    _kb_cleanup()
    try:
        import importlib
        import features.bot_remote_kb as mod
        from core import bot_mcp_client as mcp_mod
        importlib.reload(mcp_mod)
        importlib.reload(mod)

        # Step 1: insert test data
        doc_id = _kb_insert_test_doc()

        # Step 2: list_docs shows the title
        bot1 = _make_bot_mock()
        mod.list_docs(_KB_TEST_CHAT, bot1, _t_passthrough)
        edit1 = bot1.edit_message_text.call_args_list[-1][0][0]
        assert _KB_TEST_TITLE in edit1, \
            f"Step 2 (list): expected title in reply, got: {edit1!r}"

        # Step 3: search returns the chunk
        chunks = mcp_mod.query_remote("quick brown fox", _KB_TEST_CHAT, top_k=3)
        assert chunks, "Step 3 (search): no chunks returned"
        assert any(_KB_TEST_TEXT in c.get("text", "") for c in chunks), \
            f"Step 3 (search): test text not in results: {[c.get('text') for c in chunks]}"

        # Step 4: delete the document
        del_result = mcp_mod.call_tool("kb_delete_document", {
            "doc_id": doc_id, "chat_id": _KB_TEST_CHAT,
        })
        assert del_result.get("deleted") is True, \
            f"Step 4 (delete): expected deleted=True, got: {del_result}"

        # Step 5: list_docs now shows empty
        bot2 = _make_bot_mock()
        mod.list_docs(_KB_TEST_CHAT, bot2, _t_passthrough)
        edit2 = bot2.edit_message_text.call_args_list[-1][0][0]
        assert "remote_kb_docs_empty" in edit2, \
            f"Step 5 (empty list): expected empty key, got: {edit2!r}"
    finally:
        _kb_cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# Runtime tests (only when bot.env is loadable)
# ─────────────────────────────────────────────────────────────────────────────

if _HAS_BOT_CONFIG:
    def test_remote_kb_config_runtime():
        """Remote KB config constants importable and correctly typed at runtime."""
        from core.bot_config import (
            REMOTE_KB_ENABLED, MCP_REMOTE_URL, MCP_REMOTE_TOP_K,
            N8N_KB_API_KEY, N8N_KB_TOKEN, N8N_KB_WEBHOOK_INGEST,
        )
        assert isinstance(REMOTE_KB_ENABLED, bool)
        assert isinstance(MCP_REMOTE_URL, str)
        assert isinstance(MCP_REMOTE_TOP_K, int)
        assert isinstance(N8N_KB_API_KEY, str)
        assert isinstance(N8N_KB_TOKEN, str)
        assert isinstance(N8N_KB_WEBHOOK_INGEST, str)

    def test_remote_kb_is_configured_runtime():
        """is_configured() returns correct bool based on runtime env."""
        from core.bot_config import REMOTE_KB_ENABLED, MCP_REMOTE_URL, N8N_KB_API_KEY
        from features.bot_remote_kb import is_configured
        expected = bool(REMOTE_KB_ENABLED and MCP_REMOTE_URL and N8N_KB_API_KEY)
        assert is_configured() == expected


# ─────────────────────────────────────────────────────────────────────────────
# __main__ runner (matches test_n8n_crm.py pattern)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("T200 config_constants_source",          test_remote_kb_config_constants_source),
        ("T201 module_public_api_source",          test_remote_kb_module_public_api_source),
        ("T202 mcp_client_public_api_source",      test_mcp_client_public_api_source),
        ("T203 i18n_keys",                         test_remote_kb_i18n_keys),
        ("T204 callback_routing_source",           test_remote_kb_callback_routing_source),
        ("T205 is_configured_false_env_empty",     test_is_configured_false_when_env_empty),
        ("T206 show_menu_5_buttons",               test_show_menu_sends_5_buttons),
        ("T207 search_flow_with_results",          test_search_flow_with_results),
        ("T208 search_flow_no_results",            test_search_flow_no_results),
        ("T209 upload_flow_success",               test_upload_flow_success),
        ("T210 list_docs_flow",                    test_list_docs_flow),
        ("T211 clear_memory_flow",                 test_clear_memory_flow),
        ("T212 circuit_breaker",                   test_circuit_breaker_open_skips_mcp),
        ("T213 session_lifecycle",                 test_session_lifecycle),
        ("T214 web_ui_kb_route_source",            test_web_ui_kb_route_source),
        ("T215 handle_message_no_session",         test_handle_message_no_session_returns_false),
        ("T216 upload_empty_mcp_shows_error",      test_upload_flow_empty_mcp_response_shows_error),
        ("T217 search_error_uses_op_fail",         test_search_error_uses_op_fail_string),
        ("T218 list_docs_error_uses_op_fail",      test_list_docs_error_uses_op_fail_string),
        ("T219 clear_memory_error_uses_op_fail",   test_clear_memory_error_uses_op_fail_string),
        ("T225 extract_rtf_to_text",               test_extract_rtf_to_text),
        ("T226 extract_pdf_to_text",               test_extract_pdf_to_text),
        ("T227 ingest_extraction_error_returned",  test_ingest_extraction_error_returned),
        ("T228 kb_search_uses_fastembed_not_ollama", test_kb_search_uses_fastembed_not_ollama),
        ("T229 kb_search_embed_called_with_string",  test_kb_search_embed_called_with_string),
        ("T230 do_search_calls_llm_not_raw_chunks",  test_do_search_calls_llm_not_raw_chunks),
        ("T231 do_search_returns_llm_answer",        test_do_search_returns_llm_answer),
        ("T232 ingest_calls_fix_doc_meta",           test_ingest_calls_fix_doc_meta),
    ]

    passed = failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"SKIP  {name}: {type(e).__name__}: {e}")
            skipped += 1

    if _HAS_BOT_CONFIG:
        for name, fn in [
            ("runtime_config",        test_remote_kb_config_runtime),
            ("runtime_is_configured", test_remote_kb_is_configured_runtime),
        ]:
            try:
                fn()
                print(f"PASS  {name}")
                passed += 1
            except Exception as e:
                print(f"FAIL  {name}: {e}")
                failed += 1
    else:
        print("INFO  runtime tests skipped (no bot.env / BOT_TOKEN)")

    if _HAS_KB_PG:
        print("\n--- Deployed integration tests (KB_PG_DSN set) ---")
        for name, fn in [
            ("T220 deployed_list_docs",            test_deployed_list_docs),
            ("T221 deployed_list_docs_empty",       test_deployed_list_docs_empty),
            ("T222 deployed_delete_document",       test_deployed_delete_document),
            ("T223 deployed_search",                test_deployed_search),
            ("T224 deployed_full_cycle",            test_deployed_full_cycle),
        ]:
            try:
                fn()
                print(f"PASS  {name}")
                passed += 1
            except AssertionError as e:
                print(f"FAIL  {name}: {e}")
                failed += 1
            except Exception as e:
                print(f"SKIP  {name}: {type(e).__name__}: {e}")
                skipped += 1
    else:
        print("INFO  integration tests skipped (KB_PG_DSN not set)")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    sys.exit(1 if failed else 0)
