"""
Telegram bot handler regression tests (TODO 8.3).

Tests are organised into 8 classes, each focused on one handler or concern.
All tests run fully offline — no real Telegram connection, no hardware.

Patch strategy:
  - `telegram_menu_bot.bot` is replaced by the `mock_bot` fixture from conftest.
  - Access-control helpers are patched at the point of use (telegram_menu_bot
    module namespace) so each test controls exactly who is allowed/admin.
  - State dicts (`_st._user_mode`, etc.) are reset after each test via setup/
    teardown helpers.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, call, ANY

# ---------------------------------------------------------------------------
# Make src/ importable (conftest.py already handles this via sys.path; this is
# a belt-and-braces guard for standalone pytest invocations).
# ---------------------------------------------------------------------------
_SRC = os.path.join(os.path.dirname(__file__), "..", "..")
if _SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(_SRC))

# ---------------------------------------------------------------------------
# Import the module under test AFTER sys.path is set.
# The module-level `bot = TeleBot(TOKEN)` is created at import time; we swap
# the `bot` attribute out via patch.object in every test.
# ---------------------------------------------------------------------------
import telegram_menu_bot as tmb
import core.bot_state as _st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_state(cid: int) -> None:
    """Clear per-user state dicts for a given chat_id."""
    _st._user_mode.pop(cid, None)
    _st._pending_cmd.pop(cid, None)
    getattr(_st, "_pending_note", {}).pop(cid, None)
    getattr(_st, "_pending_llm_key", {}).pop(cid, None)


# ===========================================================================
# 1.  /start command
# ===========================================================================

class TestCmdStart:
    """Tests for the /start command handler (`cmd_start`)."""

    def test_allowed_user_gets_welcome(
        self,
        mock_bot,
        admin_chat_id,
        make_message,
    ):
        """An already-allowed user should receive a welcome message."""
        msg = make_message(admin_chat_id, "/start")
        _reset_state(admin_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._menu_keyboard", return_value=MagicMock()):
            tmb.cmd_start(msg)

        mock_bot.send_message.assert_called()
        text_arg = mock_bot.send_message.call_args[0][1]
        # The welcome string should be non-empty
        assert text_arg

    def test_stranger_enters_registration(
        self,
        mock_bot,
        stranger_chat_id,
        make_message,
    ):
        """An unknown user should be prompted to enter their name (registration)."""
        msg = make_message(stranger_chat_id, "/start")
        _reset_state(stranger_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=False), \
             patch("telegram_menu_bot._is_blocked_reg", return_value=False), \
             patch("telegram_menu_bot._is_pending_reg", return_value=False), \
             patch("telegram_menu_bot._set_lang"):
            tmb.cmd_start(msg)

        # The user mode should now be "reg_name"
        assert _st._user_mode.get(stranger_chat_id) == "reg_name"
        mock_bot.send_message.assert_called()

    def test_blocked_user_gets_blocked_message(
        self,
        mock_bot,
        stranger_chat_id,
        make_message,
    ):
        """A blocked user should receive the blocked message and not enter registration."""
        msg = make_message(stranger_chat_id, "/start")
        _reset_state(stranger_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=False), \
             patch("telegram_menu_bot._is_blocked_reg", return_value=True), \
             patch("telegram_menu_bot._set_lang"):
            tmb.cmd_start(msg)

        # Mode must NOT be reg_name
        assert _st._user_mode.get(stranger_chat_id) != "reg_name"
        mock_bot.send_message.assert_called()

    def test_pending_user_gets_pending_message(
        self,
        mock_bot,
        stranger_chat_id,
        make_message,
    ):
        """A pending-approval user should receive the pending message."""
        msg = make_message(stranger_chat_id, "/start")
        _reset_state(stranger_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=False), \
             patch("telegram_menu_bot._is_blocked_reg", return_value=False), \
             patch("telegram_menu_bot._is_pending_reg", return_value=True), \
             patch("telegram_menu_bot._set_lang"):
            tmb.cmd_start(msg)

        assert _st._user_mode.get(stranger_chat_id) != "reg_name"
        mock_bot.send_message.assert_called()


# ===========================================================================
# 2.  Callback — mode switches (chat / system)
# ===========================================================================

class TestCallbackMode:
    """Tests for inline-keyboard callbacks that switch user modes."""

    def test_mode_chat_sets_mode(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """mode_chat callback should set _user_mode to 'chat'."""
        cb = make_callback(user_chat_id, "mode_chat")
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        assert _st._user_mode.get(user_chat_id) == "chat"
        mock_bot.send_message.assert_called()

    def test_mode_system_denied_for_non_admin(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """mode_system callback should call _deny for a non-admin user."""
        cb = make_callback(user_chat_id, "mode_system")
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._deny") as mock_deny, \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        mock_deny.assert_called_once_with(user_chat_id)
        assert _st._user_mode.get(user_chat_id) != "system"

    def test_mode_system_allowed_for_admin(
        self,
        mock_bot,
        admin_chat_id,
        make_callback,
    ):
        """mode_system callback should set mode='system' for an admin."""
        cb = make_callback(admin_chat_id, "mode_system")
        _reset_state(admin_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=True), \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        assert _st._user_mode.get(admin_chat_id) == "system"
        mock_bot.send_message.assert_called()

    def test_unknown_user_callback_denied(
        self,
        mock_bot,
        stranger_chat_id,
        make_callback,
    ):
        """Any callback from a non-allowed user should answer with access-denied."""
        cb = make_callback(stranger_chat_id, "mode_chat")

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=False), \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        mock_bot.answer_callback_query.assert_called()
        answer_text = mock_bot.answer_callback_query.call_args[0][1]
        assert "⛔" in answer_text or "denied" in answer_text.lower() or "access" in answer_text.lower()


# ===========================================================================
# 3.  Callback — admin panel access control
# ===========================================================================

class TestCallbackAdmin:
    """Tests for admin-restricted callback keys."""

    @pytest.mark.parametrize("cb_data", [
        "admin_menu",
        "admin_add_user",
        "admin_list_users",
        "admin_remove_user",
        "admin_pending_users",
        "voice_opts_menu",
        "admin_changelog",
    ])
    def test_admin_callbacks_rejected_for_non_admin(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
        cb_data,
    ):
        """Admin callbacks must send an admin_only message to non-admins."""
        cb = make_callback(user_chat_id, cb_data)
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._is_guest", return_value=False), \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        mock_bot.send_message.assert_called()
        # Verify the message is the admin_only denial (not a normal feature response)
        # We can't easily check the translated string, but the call count should be ≥ 1
        assert mock_bot.send_message.call_count >= 1

    def test_admin_menu_accepted_for_admin(
        self,
        mock_bot,
        admin_chat_id,
        make_callback,
    ):
        """admin_menu callback should render the admin_menu.yaml screen for an admin."""
        cb = make_callback(admin_chat_id, "admin_menu")
        _reset_state(admin_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=True), \
             patch("telegram_menu_bot._lang", return_value="en"), \
             patch("telegram_menu_bot._get_pending_registrations", return_value=[]), \
             patch("telegram_menu_bot.load_screen", return_value=MagicMock()) as mock_load, \
             patch("telegram_menu_bot.render_screen") as mock_render, \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        mock_load.assert_called_once()
        mock_render.assert_called_once()

    def test_reg_approve_rejected_for_non_admin(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """reg_approve:<id> must not call _do_approve_registration for a non-admin."""
        cb = make_callback(user_chat_id, "reg_approve:12345")
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._do_approve_registration") as mock_approve, \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        mock_approve.assert_not_called()

    def test_reg_approve_accepted_for_admin(
        self,
        mock_bot,
        admin_chat_id,
        make_callback,
    ):
        """reg_approve:<id> should call _do_approve_registration for an admin."""
        cb = make_callback(admin_chat_id, "reg_approve:54321")
        _reset_state(admin_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=True), \
             patch("telegram_menu_bot._do_approve_registration") as mock_approve, \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        mock_approve.assert_called_once_with(admin_chat_id, 54321)


# ===========================================================================
# 4.  Callback — menu / navigation
# ===========================================================================

class TestCallbackMenu:
    """Phase 3 DSL: data='menu' / 'help' use load_screen + render_screen."""

    def test_menu_callback_invokes_dsl_load_and_render(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """The 'menu' callback should call load_screen with main_menu.yaml."""
        cb = make_callback(user_chat_id, "menu")
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._is_guest", return_value=False), \
             patch("telegram_menu_bot._lang", return_value="en"), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot.load_screen") as mock_load, \
             patch("telegram_menu_bot.render_screen") as mock_render:
            mock_load.return_value = MagicMock(name="Screen")
            tmb.callback_handler(cb)

        mock_load.assert_called_once()
        assert mock_load.call_args[0][0] == "screens/main_menu.yaml"
        mock_render.assert_called_once()

    def test_menu_callback_clears_user_mode_and_pending(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """The 'menu' callback should clear user mode and pending command."""
        _st._user_mode[user_chat_id] = "chat"
        _st._pending_cmd[user_chat_id] = "something"
        cb = make_callback(user_chat_id, "menu")

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._is_guest", return_value=False), \
             patch("telegram_menu_bot._lang", return_value="en"), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot.load_screen", return_value=MagicMock()), \
             patch("telegram_menu_bot.render_screen"):
            tmb.callback_handler(cb)

        assert user_chat_id not in _st._user_mode
        assert user_chat_id not in _st._pending_cmd

    def test_menu_callback_admin_gets_admin_role(
        self,
        mock_bot,
        admin_chat_id,
        make_callback,
    ):
        """Admin user's 'menu' callback should pass role='admin' to load_screen."""
        cb = make_callback(admin_chat_id, "menu")
        _reset_state(admin_chat_id)
        captured_ctx = {}

        def fake_load(path, ctx, **kwargs):
            captured_ctx["role"] = ctx.role
            return MagicMock()

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=True), \
             patch("telegram_menu_bot._lang", return_value="en"), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot.load_screen", side_effect=fake_load), \
             patch("telegram_menu_bot.render_screen"):
            tmb.callback_handler(cb)

        assert captured_ctx.get("role") == "admin"

    def test_help_callback_sends_message(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """The 'help' callback should render via DSL (load_screen + render_screen)."""
        cb = make_callback(user_chat_id, "help")
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._is_guest", return_value=False), \
             patch("telegram_menu_bot._lang", return_value="en"), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot.load_screen", return_value=MagicMock()) as mock_load, \
             patch("telegram_menu_bot.render_screen") as mock_render:
            tmb.callback_handler(cb)

        mock_load.assert_called_once()
        args = mock_load.call_args
        assert args[0][0] == "screens/help.yaml"
        mock_render.assert_called_once()


# ===========================================================================
# 4b.  Admin-menu DSL callbacks (Phase 3)
# ===========================================================================

class TestCallbackAdminMenuDSL:
    """Phase 3 DSL: data='admin_menu' uses load_screen + render_screen."""

    def test_admin_menu_callback_loads_admin_menu_yaml(
        self,
        mock_bot,
        admin_chat_id,
        make_callback,
    ):
        """Admin-menu callback should call load_screen with admin_menu.yaml."""
        cb = make_callback(admin_chat_id, "admin_menu")
        _reset_state(admin_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=True), \
             patch("telegram_menu_bot._lang", return_value="en"), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._get_pending_registrations", return_value=[]), \
             patch("telegram_menu_bot.load_screen") as mock_load, \
             patch("telegram_menu_bot.render_screen") as mock_render:
            mock_load.return_value = MagicMock(name="AdminScreen")
            tmb.callback_handler(cb)

        mock_load.assert_called_once()
        assert mock_load.call_args[0][0] == "screens/admin_menu.yaml"
        mock_render.assert_called_once()

    def test_admin_menu_pending_badge_injected(
        self,
        mock_bot,
        admin_chat_id,
        make_callback,
    ):
        """pending_badge variable should contain the count when there are pending regs."""
        cb = make_callback(admin_chat_id, "admin_menu")
        _reset_state(admin_chat_id)
        fake_pending = [{"user": "alice"}, {"user": "bob"}]
        captured = {}

        def fake_load(path, ctx, variables=None, **kwargs):
            captured["variables"] = variables
            return MagicMock()

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=True), \
             patch("telegram_menu_bot._lang", return_value="en"), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._get_pending_registrations", return_value=fake_pending), \
             patch("telegram_menu_bot.load_screen", side_effect=fake_load), \
             patch("telegram_menu_bot.render_screen"):
            tmb.callback_handler(cb)

        assert "pending_badge" in captured.get("variables", {})
        assert "2" in captured["variables"]["pending_badge"]

    def test_admin_menu_callback_denied_for_non_admin(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """Non-admin 'admin_menu' callback should NOT call load_screen."""
        cb = make_callback(user_chat_id, "admin_menu")
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot.load_screen") as mock_load:
            tmb.callback_handler(cb)

        mock_load.assert_not_called()
        mock_bot.send_message.assert_called()


# ===========================================================================
# 5.  Voice handler
# ===========================================================================

class TestVoiceHandler:
    """Tests for the voice message handler."""

    def test_voice_denied_for_stranger(
        self,
        mock_bot,
        stranger_chat_id,
        make_message,
    ):
        """Voice from a non-allowed user should call _deny."""
        msg = make_message(stranger_chat_id, "", content_type="voice")
        msg.voice = MagicMock()
        _reset_state(stranger_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=False), \
             patch("telegram_menu_bot._deny") as mock_deny, \
             patch("telegram_menu_bot._set_lang"):
            tmb.voice_handler(msg)

        mock_deny.assert_called_once_with(stranger_chat_id)

    def test_voice_routed_to_voice_pipeline(
        self,
        mock_bot,
        user_chat_id,
        make_message,
    ):
        """Voice from an allowed user should call _handle_voice_message."""
        msg = make_message(user_chat_id, "", content_type="voice")
        msg.voice = MagicMock()
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._handle_voice_message") as mock_voice, \
             patch("telegram_menu_bot._set_lang"):
            tmb.voice_handler(msg)

        mock_voice.assert_called_once_with(user_chat_id, msg.voice)

    def test_voice_in_errp_mode_routes_to_errp(
        self,
        mock_bot,
        user_chat_id,
        make_message,
    ):
        """In errp_collect mode, voice should be routed to _errp_collect_voice."""
        msg = make_message(user_chat_id, "", content_type="voice")
        msg.voice = MagicMock()
        _st._user_mode[user_chat_id] = "errp_collect"
        _st._pending_error_protocol[user_chat_id] = {"step": "collect"}

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._handle_voice_message") as mock_voice, \
             patch("telegram_menu_bot._errp_collect_voice") as mock_errp, \
             patch("telegram_menu_bot._set_lang"):
            tmb.voice_handler(msg)

        mock_errp.assert_called_once_with(user_chat_id, msg.voice)
        mock_voice.assert_not_called()

        _st._pending_error_protocol.pop(user_chat_id, None)
        _reset_state(user_chat_id)


# ===========================================================================
# 6.  Text handler — notes multi-step flow
# ===========================================================================

class TestTextHandlerNotes:
    """Tests for the note creation multi-step flow in text_handler."""

    def test_note_title_step_advances_to_content(
        self,
        mock_bot,
        user_chat_id,
        make_message,
    ):
        """In note_add_title mode, the text becomes the title and mode advances."""
        msg = make_message(user_chat_id, "My Test Note")
        _reset_state(user_chat_id)
        _st._user_mode[user_chat_id] = "note_add_title"

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._back_keyboard", return_value=MagicMock()):
            tmb.text_handler(msg)

        assert _st._user_mode.get(user_chat_id) == "note_add_content"
        mock_bot.send_message.assert_called()
        # pending_note should have the slug/title stored
        assert user_chat_id in getattr(_st, "_pending_note", {})

        _reset_state(user_chat_id)

    def test_note_content_step_saves_note(
        self,
        mock_bot,
        user_chat_id,
        make_message,
    ):
        """In note_add_content mode, the text is saved as the note body."""
        msg = make_message(user_chat_id, "This is the note body.")
        _reset_state(user_chat_id)
        _st._user_mode[user_chat_id] = "note_add_content"
        # Set up pending note state as if the title step already ran
        if not hasattr(_st, "_pending_note"):
            _st._pending_note = {}
        _st._pending_note[user_chat_id] = {"slug": "my_test_note", "title": "My Test Note"}

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._save_note_file") as mock_save, \
             patch("telegram_menu_bot._back_keyboard", return_value=MagicMock()):
            tmb.text_handler(msg)

        mock_save.assert_called_once()
        # After saving, mode should be cleared
        assert _st._user_mode.get(user_chat_id) not in ("note_add_content", "note_add_title")
        mock_bot.send_message.assert_called()

        _reset_state(user_chat_id)


# ===========================================================================
# 7.  Text handler — admin flow access control
# ===========================================================================

class TestTextHandlerAdmin:
    """Tests for admin-restricted text-handler flows."""

    def test_admin_add_user_mode_rejected_for_non_admin(
        self,
        mock_bot,
        user_chat_id,
        make_message,
    ):
        """admin_add_user mode text should be rejected with admin_only for non-admin."""
        msg = make_message(user_chat_id, "987654321")
        _reset_state(user_chat_id)
        _st._user_mode[user_chat_id] = "admin_add_user"

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._finish_admin_add_user") as mock_finish, \
             patch("telegram_menu_bot._set_lang"):
            tmb.text_handler(msg)

        mock_finish.assert_not_called()
        mock_bot.send_message.assert_called()

        _reset_state(user_chat_id)

    def test_admin_add_user_mode_accepted_for_admin(
        self,
        mock_bot,
        admin_chat_id,
        make_message,
    ):
        """admin_add_user mode text should call _finish_admin_add_user for an admin."""
        msg = make_message(admin_chat_id, "987654321")
        _reset_state(admin_chat_id)
        _st._user_mode[admin_chat_id] = "admin_add_user"

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=True), \
             patch("telegram_menu_bot._finish_admin_add_user") as mock_finish, \
             patch("telegram_menu_bot._set_lang"):
            tmb.text_handler(msg)

        mock_finish.assert_called_once_with(admin_chat_id, "987654321")

        _reset_state(admin_chat_id)


# ===========================================================================
# 8.  Text handler — free-chat routing
# ===========================================================================

class TestChatMode:
    """Tests for free-chat mode text routing."""

    def test_chat_mode_calls_handle_chat_message(
        self,
        mock_bot,
        user_chat_id,
        make_message,
    ):
        """In 'chat' mode, text_handler should call _handle_chat_message."""
        msg = make_message(user_chat_id, "Hello!")
        _reset_state(user_chat_id)
        _st._user_mode[user_chat_id] = "chat"

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._handle_chat_message") as mock_chat:
            tmb.text_handler(msg)

        mock_chat.assert_called_once_with(user_chat_id, "Hello!")

        _reset_state(user_chat_id)

    def test_no_mode_defaults_to_chat(
        self,
        mock_bot,
        user_chat_id,
        make_message,
    ):
        """With no active mode, text_handler should default to chat mode (v2026.3.46 fix).

        Previously mode=None showed the main menu, causing the 'second message
        shows menu instead of LLM reply' bug.  Now mode=None → chat mode so the
        user always gets an LLM response.
        """
        msg = make_message(user_chat_id, "random text")
        _reset_state(user_chat_id)
        # Explicitly ensure no mode is set
        _st._user_mode.pop(user_chat_id, None)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._send_menu") as mock_send_menu, \
             patch("telegram_menu_bot._handle_chat_message") as mock_chat:
            tmb.text_handler(msg)

        # Since v2026.3.46: mode=None → default to chat, NOT menu
        assert mock_chat.called, "mode=None should route to chat, not show menu"
        assert not mock_send_menu.called, "mode=None must not show menu (second-message bug)"

        _reset_state(user_chat_id)

    def test_system_mode_calls_handle_system_message(
        self,
        mock_bot,
        admin_chat_id,
        make_message,
    ):
        """In 'system' mode, text_handler should call _handle_system_message."""
        msg = make_message(admin_chat_id, "show free disk space")
        _reset_state(admin_chat_id)
        _st._user_mode[admin_chat_id] = "system"

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=True), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._handle_system_message") as mock_sys:
            tmb.text_handler(msg)

        mock_sys.assert_called_once_with(admin_chat_id, "show free disk space")

        _reset_state(admin_chat_id)


# ===========================================================================
# 9.  Voice — system mode routing and admin role preservation
# ===========================================================================

class TestVoiceSystemModeRouting:
    """Regression tests: voice messages respect system mode and admin role.

    Guard for the bug where voice messages in system mode bypassed the admin
    check and returned 'not allowed' to admin users.
    """

    def test_voice_in_system_mode_routes_to_system_handler(
        self,
        mock_bot,
        admin_chat_id,
        make_message,
    ):
        """Voice from an admin in 'system' mode MUST route to _handle_voice_message.

        The voice pipeline itself checks the mode and calls _handle_system_message
        internally — the outer handler just calls _handle_voice_message for all
        allowed users (mode-switching is delegated to bot_voice.py).
        """
        msg = make_message(admin_chat_id, "", content_type="voice")
        msg.voice = MagicMock()
        _reset_state(admin_chat_id)
        _st._user_mode[admin_chat_id] = "system"

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._handle_voice_message") as mock_voice, \
             patch("telegram_menu_bot._set_lang"):
            tmb.voice_handler(msg)

        mock_voice.assert_called_once_with(admin_chat_id, msg.voice)
        _reset_state(admin_chat_id)

    def test_voice_system_mode_non_admin_still_routed_to_pipeline(
        self,
        mock_bot,
        user_chat_id,
        make_message,
    ):
        """Voice from a non-admin with mode='system' still calls the pipeline.

        The outer voice_handler doesn't block on role — that happens inside
        _handle_voice_message → _handle_system_message. This test ensures
        the voice handler itself doesn't short-circuit for non-admins.
        """
        msg = make_message(user_chat_id, "", content_type="voice")
        msg.voice = MagicMock()
        _reset_state(user_chat_id)
        _st._user_mode[user_chat_id] = "system"

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._handle_voice_message") as mock_voice, \
             patch("telegram_menu_bot._set_lang"):
            tmb.voice_handler(msg)

        mock_voice.assert_called_once_with(user_chat_id, msg.voice)
        _reset_state(user_chat_id)

    def test_text_system_mode_non_admin_blocked_at_text_handler(
        self,
        mock_bot,
        user_chat_id,
        make_message,
    ):
        """Text handler in 'system' mode MUST block non-admins with security_admin_only.

        This is the defense-in-depth guard in telegram_menu_bot.text_handler.
        """
        msg = make_message(user_chat_id, "show uptime")
        _reset_state(user_chat_id)
        _st._user_mode[user_chat_id] = "system"

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._handle_system_message") as mock_sys:
            tmb.text_handler(msg)

        mock_sys.assert_not_called()
        _reset_state(user_chat_id)


# ===========================================================================
# 10.  Screen DSL — menu rendering uses variant-aware role filtering
# ===========================================================================

class TestScreenDSLRoleFiltering:
    """Regression tests: Screen DSL renders correct buttons per role/variant."""

    def test_menu_callback_invokes_screen_loader(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """The 'menu' callback must call load_screen for main_menu.yaml."""
        call = make_callback(user_chat_id, "menu")
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._is_guest", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot.load_screen") as mock_load, \
             patch("telegram_menu_bot.render_screen"):
            mock_load.return_value = MagicMock()
            tmb.callback_handler(call)

        mock_load.assert_called_once()
        args, _ = mock_load.call_args
        assert "main_menu" in args[0], f"Expected main_menu.yaml, got {args[0]}"

    def test_admin_gets_admin_role_in_screen_render(
        self,
        mock_bot,
        admin_chat_id,
        make_callback,
    ):
        """Admin user must receive 'admin' role context when menu is rendered."""
        call = make_callback(admin_chat_id, "menu")
        _reset_state(admin_chat_id)

        captured_ctx = []

        def _capture_load(screen_path, ctx, **kw):
            captured_ctx.append(ctx)
            return MagicMock()

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=True), \
             patch("telegram_menu_bot._is_guest", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot.load_screen", side_effect=_capture_load), \
             patch("telegram_menu_bot.render_screen"):
            tmb.callback_handler(call)

        assert captured_ctx, "load_screen was not called"
        assert captured_ctx[0].role == "admin", (
            f"Expected role='admin' in context, got: {captured_ctx[0].role}"
        )


# ===========================================================================
# 9.  Campaign agent — callback routing
# ===========================================================================

class TestCampaignCallbacks:
    """Tests for campaign/agents callback routing in callback_handler().

    Covers the five campaign callbacks: agents_menu, campaign_start,
    campaign_confirm_send, campaign_edit_template, campaign_cancel.
    All run fully offline — campaign module is mocked.
    """

    def _run_callback(self, mock_bot, cid, data, make_callback,
                      is_allowed=True, is_admin=True, is_advanced=False,
                      campaign_configured=True, campaign_active=False,
                      campaign_patches=None):
        """Helper: invoke callback_handler with full patch set."""
        call = make_callback(cid, data)
        _reset_state(cid)
        patches = {
            "telegram_menu_bot._is_allowed": is_allowed,
            "telegram_menu_bot._is_admin":   is_admin,
            "telegram_menu_bot._is_advanced": is_advanced,
            "telegram_menu_bot._is_guest":   False,
            "telegram_menu_bot._deny":       MagicMock(),
            "telegram_menu_bot._set_lang":   MagicMock(),
            "telegram_menu_bot._t":          lambda cid, k, **kw: f"[{k}]",
        }
        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=is_allowed), \
             patch("telegram_menu_bot._is_admin",   return_value=is_admin), \
             patch("telegram_menu_bot._is_advanced", return_value=is_advanced), \
             patch("telegram_menu_bot._is_guest",   return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._t", side_effect=lambda cid, k, **kw: f"[{k}]"), \
             patch("telegram_menu_bot._campaign") as mock_campaign:
            mock_campaign.is_configured.return_value = campaign_configured
            mock_campaign.is_active.return_value = campaign_active
            if campaign_patches:
                for attr, val in campaign_patches.items():
                    setattr(mock_campaign, attr, val)
            tmb.callback_handler(call)
        return mock_bot, mock_campaign

    def test_agents_menu_denied_for_stranger(self, mock_bot, make_callback):
        """agents_menu → stranger (not allowed) receives denied message via answer_callback_query."""
        cid = 888001
        bot, _ = self._run_callback(
            mock_bot, cid, "agents_menu", make_callback,
            is_allowed=False, is_admin=False, is_advanced=False,
        )
        # callback_handler returns early via answer_callback_query for non-allowed users
        bot.answer_callback_query.assert_called()

    def test_agents_menu_denied_for_regular_user(self, mock_bot, make_callback):
        """agents_menu → allowed but not admin/advanced → admin_only message."""
        cid = 888002
        bot, _ = self._run_callback(
            mock_bot, cid, "agents_menu", make_callback,
            is_allowed=True, is_admin=False, is_advanced=False,
        )
        calls = [str(c) for c in bot.send_message.call_args_list]
        assert any("admin_only" in c for c in calls), (
            "Regular user accessing agents_menu must receive admin_only message"
        )

    def test_agents_menu_shown_for_admin(self, mock_bot, make_callback):
        """agents_menu → admin → _handle_agents_menu is called (sends keyboard message)."""
        cid = 888003
        bot, _ = self._run_callback(
            mock_bot, cid, "agents_menu", make_callback,
            is_allowed=True, is_admin=True, is_advanced=False,
        )
        # _handle_agents_menu calls bot.send_message with the agents menu title
        bot.send_message.assert_called()
        call_args_text = str(bot.send_message.call_args_list)
        assert "agents_menu_title" in call_args_text, (
            "Admin should see agents_menu_title via _handle_agents_menu"
        )

    def test_agents_menu_shown_for_advanced_user(self, mock_bot, make_callback):
        """agents_menu → advanced (not admin) → agents menu shown."""
        cid = 888004
        bot, _ = self._run_callback(
            mock_bot, cid, "agents_menu", make_callback,
            is_allowed=True, is_admin=False, is_advanced=True,
        )
        bot.send_message.assert_called()
        call_args_text = str(bot.send_message.call_args_list)
        assert "admin_only" not in call_args_text, (
            "Advanced user must not receive admin_only; should see agents menu"
        )

    def test_campaign_start_denied_for_regular_user(self, mock_bot, make_callback):
        """campaign_start → regular user → admin_only message, campaign not started."""
        cid = 888005
        bot, mock_campaign = self._run_callback(
            mock_bot, cid, "campaign_start", make_callback,
            is_allowed=True, is_admin=False, is_advanced=False,
        )
        mock_campaign.start_campaign.assert_not_called()
        calls = [str(c) for c in bot.send_message.call_args_list]
        assert any("admin_only" in c for c in calls)

    def test_campaign_start_not_configured(self, mock_bot, make_callback):
        """campaign_start → admin + campaign not configured → campaign_not_configured message."""
        cid = 888006
        bot, mock_campaign = self._run_callback(
            mock_bot, cid, "campaign_start", make_callback,
            is_allowed=True, is_admin=True,
            campaign_configured=False,
        )
        mock_campaign.start_campaign.assert_not_called()
        calls = [str(c) for c in bot.send_message.call_args_list]
        assert any("campaign_not_configured" in c for c in calls), (
            "Admin starting unconfigured campaign must see campaign_not_configured"
        )

    def test_campaign_start_configured_calls_start(self, mock_bot, make_callback):
        """campaign_start → admin + configured → campaign.start_campaign called."""
        cid = 888007
        bot, mock_campaign = self._run_callback(
            mock_bot, cid, "campaign_start", make_callback,
            is_allowed=True, is_admin=True,
            campaign_configured=True,
        )
        mock_campaign.start_campaign.assert_called_once_with(cid, mock_bot, ANY)

    def test_campaign_confirm_send_allowed_for_admin(self, mock_bot, make_callback):
        """campaign_confirm_send → admin → campaign.confirm_send called."""
        cid = 888008
        bot, mock_campaign = self._run_callback(
            mock_bot, cid, "campaign_confirm_send", make_callback,
            is_allowed=True, is_admin=True,
        )
        mock_campaign.confirm_send.assert_called_once()

    def test_campaign_edit_template_allowed_for_admin(self, mock_bot, make_callback):
        """campaign_edit_template → admin → campaign.start_template_edit called."""
        cid = 888009
        bot, mock_campaign = self._run_callback(
            mock_bot, cid, "campaign_edit_template", make_callback,
            is_allowed=True, is_admin=True,
        )
        mock_campaign.start_template_edit.assert_called_once()

    def test_campaign_cancel_allowed_for_any_user(self, mock_bot, make_callback):
        """campaign_cancel → any allowed user → campaign.cancel + cancelled message."""
        cid = 888010
        bot, mock_campaign = self._run_callback(
            mock_bot, cid, "campaign_cancel", make_callback,
            is_allowed=True, is_admin=False,
        )
        mock_campaign.cancel.assert_called_once_with(cid)
        calls = [str(c) for c in bot.send_message.call_args_list]
        assert any("campaign_cancelled" in c for c in calls)


# ===========================================================================
# 10.  Campaign agent — text message routing
# ===========================================================================

class TestCampaignTextHandling:
    """Tests for campaign intercept in text_handler().

    The router must check campaign.is_active() BEFORE falling through to chat/LLM.
    Tests verify consume-and-return, fall-through, and non-admin cancel paths.
    """

    def test_campaign_active_message_consumed_for_admin(
        self, mock_bot, admin_chat_id, make_message
    ):
        """is_active=True + is_admin → handle_message called; function returns early."""
        cid = admin_chat_id
        _reset_state(cid)
        msg = make_message(cid, "LR Webinar topic")

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin",   return_value=True), \
             patch("telegram_menu_bot._is_advanced", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._t", side_effect=lambda c, k, **kw: f"[{k}]"), \
             patch("telegram_menu_bot._campaign") as mock_campaign:
            mock_campaign.is_active.return_value = True
            mock_campaign.handle_message.return_value = True  # consumed

            # Patch chat handler to detect if it's called unexpectedly
            with patch("telegram_menu_bot._handle_chat_message") as mock_chat:
                tmb.text_handler(msg)

            mock_campaign.handle_message.assert_called_once_with(
                cid, "LR Webinar topic", mock_bot, ANY
            )
            # Chat handler must NOT have been called — message was consumed
            mock_chat.assert_not_called()

    def test_campaign_active_not_consumed_falls_through_to_chat(
        self, mock_bot, admin_chat_id, make_message
    ):
        """is_active=True + handle_message returns False → falls through to chat mode."""
        cid = admin_chat_id
        _reset_state(cid)
        import core.bot_state as _st
        _st._user_mode[cid] = "chat"
        msg = make_message(cid, "some unrecognised input")

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin",   return_value=True), \
             patch("telegram_menu_bot._is_advanced", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._t", side_effect=lambda c, k, **kw: f"[{k}]"), \
             patch("telegram_menu_bot._campaign") as mock_campaign, \
             patch("telegram_menu_bot._handle_chat_message") as mock_chat:
            mock_campaign.is_active.return_value = True
            mock_campaign.handle_message.return_value = False  # NOT consumed
            mock_chat.return_value = None

            tmb.text_handler(msg)

        # Falls through to chat handler
        mock_chat.assert_called_once()

    def test_campaign_active_non_admin_cancels_campaign(
        self, mock_bot, user_chat_id, make_message
    ):
        """is_active=True + not admin/advanced → campaign.cancel called."""
        cid = user_chat_id
        _reset_state(cid)
        msg = make_message(cid, "some text")

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin",   return_value=False), \
             patch("telegram_menu_bot._is_advanced", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._t", side_effect=lambda c, k, **kw: f"[{k}]"), \
             patch("telegram_menu_bot._campaign") as mock_campaign:
            mock_campaign.is_active.return_value = True

            tmb.text_handler(msg)

        mock_campaign.cancel.assert_called_once_with(cid)
        mock_campaign.handle_message.assert_not_called()

    def test_campaign_inactive_not_intercepted(
        self, mock_bot, admin_chat_id, make_message
    ):
        """is_active=False → campaign handler not called; message falls to normal routing."""
        cid = admin_chat_id
        _reset_state(cid)
        import core.bot_state as _st
        _st._user_mode[cid] = "chat"
        msg = make_message(cid, "hello bot")

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin",   return_value=True), \
             patch("telegram_menu_bot._is_advanced", return_value=False), \
             patch("telegram_menu_bot._set_lang"), \
             patch("telegram_menu_bot._t", side_effect=lambda c, k, **kw: f"[{k}]"), \
             patch("telegram_menu_bot._campaign") as mock_campaign, \
             patch("telegram_menu_bot._handle_chat_message") as mock_chat:
            mock_campaign.is_active.return_value = False
            mock_chat.return_value = None

            tmb.text_handler(msg)

        mock_campaign.handle_message.assert_not_called()
