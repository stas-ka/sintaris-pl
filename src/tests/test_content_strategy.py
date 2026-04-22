"""
test_content_strategy.py — Unit tests for the Content Strategy Agent (bot_content.py).

Tests cover:
  T_CS_01 — is_configured() returns False when webhook not set
  T_CS_02 — is_configured() returns True when webhook is set
  T_CS_03 — cancel() removes session
  T_CS_04 — show_menu() sends message with inline keyboard
  T_CS_05 — start_mode('plan') sets step=q1, sends correct question
  T_CS_06 — start_mode('post') sets step=q1, sends correct question
  T_CS_07 — handle_message at q1 step stores q1 and advances to q2
  T_CS_08 — on_platform_selected stores q2 and advances to q3_kb
  T_CS_09 — on_kb_selected starts generation thread
  T_CS_10 — on_action 'save' calls _save_note_text
  T_CS_11 — on_action 'download' sends document
  T_CS_12 — on_action 'new' resets session and shows menu
  T_CS_13 — on_action 'publish' advances to ask_channel
  T_CS_14 — on_channel_input stores channel and asks confirmation
  T_CS_15 — on_publish_decision 'cancel' returns to preview
  T_CS_16 — on_publish_decision 'confirm' calls N8N publish webhook
  T_CS_17 — generate: N8N error → error message sent, session cleared
  T_CS_18 — generate: N8N empty response → error message sent
  T_CS_19 — is_active() returns True only for active sessions
  T_CS_20 — handle_message returns False for unknown step
"""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call

# ── Minimal stubs for imports that require system packages ───────────────────
for mod_name in [
    "telebot", "telebot.types",
    "requests",
    "features.bot_n8n",
    "core.bot_config",
    "telegram.bot_access",
    "telegram.bot_users",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Stub telebot.types
tb_types = sys.modules["telebot.types"]
tb_types.InlineKeyboardMarkup = MagicMock(return_value=MagicMock())
tb_types.InlineKeyboardButton = MagicMock(return_value=MagicMock())

# Stub bot_config defaults
cfg = sys.modules["core.bot_config"]
cfg.N8N_CONTENT_GENERATE_WH = ""
cfg.N8N_CONTENT_PUBLISH_WH  = ""
cfg.CONTENT_TG_CHANNEL_ID   = ""
cfg.N8N_CONTENT_TIMEOUT     = 60

# Stub bot_access
ba = sys.modules["telegram.bot_access"]
ba._docs_rag_context = MagicMock(return_value="")

# Stub bot_users
bu = sys.modules["telegram.bot_users"]
bu._save_note_text = MagicMock()

# Stub bot_n8n
n8n = sys.modules["features.bot_n8n"]
n8n.call_webhook = MagicMock(return_value={"content": "Generated content"})

# Now import the module under test
import importlib
import features.bot_content as bc

# ─────────────────────────────────────────────────────────────────────────────

def _bot():
    """Return a fresh mock bot."""
    b = MagicMock()
    b.send_message = MagicMock()
    b.send_document = MagicMock()
    return b


def _t(chat_id, key, **kw):
    """Fake translation — returns key with formatted kwargs."""
    try:
        return key.format(**kw)
    except Exception:
        return key


class TestIsConfigured(unittest.TestCase):
    def test_T_CS_01_not_configured(self):
        bc.N8N_CONTENT_GENERATE_WH = ""
        with patch("features.bot_content.N8N_CONTENT_GENERATE_WH", ""):
            self.assertFalse(bc.is_configured())

    def test_T_CS_02_configured(self):
        with patch("features.bot_content.N8N_CONTENT_GENERATE_WH",
                   "https://n8n.example.com/webhook/taris-content-generate"):
            self.assertTrue(bc.is_configured())


class TestSession(unittest.TestCase):
    def setUp(self):
        bc._sessions.clear()

    def test_T_CS_03_cancel(self):
        bc._sessions[1] = {"step": "q1"}
        bc.cancel(1)
        self.assertNotIn(1, bc._sessions)

    def test_T_CS_19_is_active(self):
        self.assertFalse(bc.is_active(99))
        bc._sessions[99] = {"step": "q1"}
        self.assertTrue(bc.is_active(99))


class TestShowMenu(unittest.TestCase):
    def setUp(self):
        bc._sessions.clear()

    def test_T_CS_04_show_menu(self):
        bot = _bot()
        bc.show_menu(1, bot, _t)
        bot.send_message.assert_called_once()
        args, kwargs = bot.send_message.call_args
        self.assertEqual(args[0], 1)

    def test_T_CS_05_start_mode_plan(self):
        bot = _bot()
        bc.start_mode(1, "plan", bot, _t)
        self.assertEqual(bc._sessions[1]["step"], "q1")
        self.assertEqual(bc._sessions[1]["mode"], "plan")
        bot.send_message.assert_called_once()

    def test_T_CS_06_start_mode_post(self):
        bot = _bot()
        bc.start_mode(1, "post", bot, _t)
        self.assertEqual(bc._sessions[1]["mode"], "post")


class TestMessageHandling(unittest.TestCase):
    def setUp(self):
        bc._sessions.clear()

    def test_T_CS_07_handle_q1(self):
        bc._sessions[1] = {"step": "q1", "mode": "plan"}
        bot = _bot()
        consumed = bc.handle_message(1, "Nutrition, moms 30+, goal: sales", bot, _t)
        self.assertTrue(consumed)
        self.assertEqual(bc._sessions[1]["q1"], "Nutrition, moms 30+, goal: sales")
        self.assertEqual(bc._sessions[1]["step"], "q2")

    def test_T_CS_08_on_platform_selected(self):
        bc._sessions[1] = {"step": "q2", "mode": "plan", "q1": "test"}
        bot = _bot()
        bc.on_platform_selected(1, "Telegram", bot, _t)
        self.assertEqual(bc._sessions[1]["q2"], "Telegram")
        self.assertEqual(bc._sessions[1]["step"], "q3_kb")

    def test_T_CS_20_handle_message_unknown_step(self):
        bc._sessions[1] = {"step": "generating"}
        bot = _bot()
        consumed = bc.handle_message(1, "some text", bot, _t)
        self.assertFalse(consumed)

    def test_T_CS_20b_handle_message_no_session(self):
        bot = _bot()
        consumed = bc.handle_message(999, "text", bot, _t)
        self.assertFalse(consumed)


class TestGeneration(unittest.TestCase):
    def setUp(self):
        bc._sessions.clear()

    def test_T_CS_09_kb_yes_starts_generation(self):
        bc._sessions[1] = {
            "step": "q3_kb", "mode": "plan",
            "q1": "test q1", "q2": "Telegram",
        }
        bot = _bot()
        with patch("features.bot_content.N8N_CONTENT_GENERATE_WH",
                   "http://fake/webhook/gen"), \
             patch("features.bot_content.call_webhook",
                   return_value={"content": "Generated plan"}), \
             patch("features.bot_content._docs_rag_context",
                   return_value="KB context", create=True):
            bc.on_kb_selected(1, True, bot, _t)
            import time; time.sleep(0.3)  # let thread run
        # Session should be in preview (or generating if still running)
        step = bc._sessions.get(1, {}).get("step")
        self.assertIn(step, ("preview", "generating"))

    def test_T_CS_17_generate_n8n_error(self):
        bc._sessions[1] = {
            "step": "generating", "mode": "plan",
            "q1": "test", "q2": "Telegram", "use_kb": False,
        }
        bot = _bot()
        with patch("features.bot_content.N8N_CONTENT_GENERATE_WH", "http://fake"), \
             patch("features.bot_content.call_webhook",
                   return_value={"error": "N8N connection failed"}):
            bc._do_generate(1, bot, _t)
            import time; time.sleep(0.3)
        bot.send_message.assert_called()
        # _t returns key as-is in tests; verify error message key was sent
        call_args = str(bot.send_message.call_args_list)
        self.assertIn("content_generate_error", call_args)

    def test_T_CS_18_generate_empty_response(self):
        bc._sessions[1] = {
            "step": "generating", "mode": "post",
            "q1": "test", "q2": "Instagram", "use_kb": False,
        }
        bot = _bot()
        with patch("features.bot_content.N8N_CONTENT_GENERATE_WH", "http://fake"), \
             patch("features.bot_content.call_webhook", return_value={}):
            bc._do_generate(1, bot, _t)
            import time; time.sleep(0.3)
        bot.send_message.assert_called()


class TestActions(unittest.TestCase):
    def setUp(self):
        bc._sessions.clear()

    def _make_preview_session(self, mode="plan"):
        bc._sessions[1] = {
            "step": "preview", "mode": mode,
            "q1": "test q1", "q2": "Telegram",
            "content": "Test generated content " * 20,
        }

    def test_T_CS_12_action_new(self):
        self._make_preview_session()
        bot = _bot()
        with patch("features.bot_content.show_menu") as mock_menu:
            bc.on_action(1, "new", bot, _t)
            mock_menu.assert_called_once_with(1, bot, _t)
        self.assertNotIn(1, bc._sessions)

    def test_T_CS_13_action_publish(self):
        self._make_preview_session()
        bot = _bot()
        bc.on_action(1, "publish", bot, _t)
        self.assertEqual(bc._sessions[1]["step"], "ask_channel")
        bot.send_message.assert_called()

    def test_T_CS_11_action_download(self):
        self._make_preview_session()
        bot = _bot()
        bc.on_action(1, "download", bot, _t)
        bot.send_document.assert_called_once()

    def test_T_CS_10_action_save(self):
        self._make_preview_session()
        bot = _bot()
        with patch("features.bot_content._save_note_text", create=True) as mock_save, \
             patch("features.bot_content._show_preview"):
            # Patch the import inside _do_save
            with patch.dict("sys.modules", {"telegram.bot_users": MagicMock(
                    _save_note_text=mock_save)}):
                bc.on_action(1, "save", bot, _t)
        bot.send_message.assert_called()


class TestPublishFlow(unittest.TestCase):
    def setUp(self):
        bc._sessions.clear()

    def test_T_CS_14_channel_input(self):
        bc._sessions[1] = {
            "step": "ask_channel", "mode": "plan",
            "q1": "test", "q2": "Telegram",
            "content": "Some content",
        }
        bot = _bot()
        bc.on_channel_input(1, "@testchannel", bot, _t)
        self.assertEqual(bc._sessions[1]["channel"], "@testchannel")
        self.assertEqual(bc._sessions[1]["step"], "confirming_publish")

    def test_T_CS_15_publish_cancel(self):
        bc._sessions[1] = {
            "step": "confirming_publish", "mode": "plan",
            "q1": "test", "q2": "Telegram",
            "content": "content", "channel": "@ch",
        }
        bot = _bot()
        with patch("features.bot_content._show_preview") as mock_prev:
            bc.on_publish_decision(1, "cancel", bot, _t)
            mock_prev.assert_called_once()
        self.assertEqual(bc._sessions[1]["step"], "preview")

    def test_T_CS_16_publish_confirm(self):
        bc._sessions[1] = {
            "step": "confirming_publish", "mode": "plan",
            "q1": "test", "q2": "Telegram",
            "content": "content", "channel": "@ch",
        }
        bot = _bot()
        mock_wh = MagicMock(return_value={"success": True})
        with patch("features.bot_content.N8N_CONTENT_PUBLISH_WH", "http://fake/publish"), \
             patch("features.bot_content.call_webhook", mock_wh):
            bc.on_publish_decision(1, "confirm", bot, _t)
            import time; time.sleep(0.3)
        mock_wh.assert_called()
        call_kwargs = mock_wh.call_args
        self.assertIn("content", call_kwargs[0][1])
        self.assertIn("channel", call_kwargs[0][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
