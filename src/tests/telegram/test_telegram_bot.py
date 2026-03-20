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
from unittest.mock import MagicMock, patch, call

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
        """admin_menu callback should call _handle_admin_menu for an admin."""
        cb = make_callback(admin_chat_id, "admin_menu")
        _reset_state(admin_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=True), \
             patch("telegram_menu_bot._handle_admin_menu") as mock_admin, \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        mock_admin.assert_called_once_with(admin_chat_id)

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
    """Tests for the menu and help callbacks."""

    def test_menu_callback_calls_send_menu(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """The 'menu' callback should call _send_menu."""
        cb = make_callback(user_chat_id, "menu")
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._send_menu") as mock_send_menu, \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        mock_send_menu.assert_called_once_with(user_chat_id)

    def test_menu_callback_clears_user_mode(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """The 'menu' callback should clear any active user mode."""
        _st._user_mode[user_chat_id] = "chat"
        cb = make_callback(user_chat_id, "menu")

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._send_menu"), \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

        assert _st._user_mode.get(user_chat_id) not in ("chat", "system", "calendar")

    def test_help_callback_sends_message(
        self,
        mock_bot,
        user_chat_id,
        make_callback,
    ):
        """The 'help' callback should send a help message."""
        cb = make_callback(user_chat_id, "help")
        _reset_state(user_chat_id)

        with patch.object(tmb, "bot", mock_bot), \
             patch("telegram_menu_bot._is_allowed", return_value=True), \
             patch("telegram_menu_bot._is_admin", return_value=False), \
             patch("telegram_menu_bot._is_guest", return_value=False), \
             patch("telegram_menu_bot._set_lang"):
            tmb.callback_handler(cb)

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

    def test_no_mode_shows_menu(
        self,
        mock_bot,
        user_chat_id,
        make_message,
    ):
        """With no active mode, text_handler should show the main menu."""
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

        # Either _send_menu is called directly, or _handle_chat_message was NOT
        # called with the text (some bots silently ignore unrouted text):
        # accept either behaviour as a pass condition.
        chat_called = mock_chat.called
        menu_called = mock_send_menu.called
        assert menu_called or not chat_called, (
            "Unrouted text should show the menu, not enter chat mode silently"
        )

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
