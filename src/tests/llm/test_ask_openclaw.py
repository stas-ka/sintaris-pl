"""
Unit tests for the OpenClaw LLM provider (_ask_openclaw).

Tests are fully offline — no real OpenClaw gateway, no network.
All subprocess calls are mocked.

Run:
    cd /home/stas/projects/sintaris-pl
    WEB_ONLY=1 python -m pytest src/tests/llm/ -v
"""

import json
import os
import sys
import subprocess
from unittest.mock import patch, MagicMock

import pytest

# Make src/ importable
_SRC = os.path.join(os.path.dirname(__file__), "..", "..")
if _SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(_SRC))

os.environ.setdefault("WEB_ONLY", "1")


# ---------------------------------------------------------------------------
# Import helpers — lazy to avoid side-effects at collection time
# ---------------------------------------------------------------------------

def _import_llm():
    import core.bot_llm as llm
    return llm


def _import_config():
    import core.bot_config as cfg
    return cfg


# ===========================================================================
# 1.  _ask_openclaw — binary resolution
# ===========================================================================

class TestAskOpenclawBinary:
    """Binary-not-found raises FileNotFoundError → ask_llm() triggers fallback."""

    def test_missing_binary_raises_file_not_found(self):
        llm = _import_llm()
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            with pytest.raises(FileNotFoundError, match="openclaw binary not found"):
                llm._ask_openclaw("hello", 10)

    def test_binary_found_via_which(self, mock_proc_ok):
        """shutil.which finds binary → no FileNotFoundError raised."""
        llm = _import_llm()
        with patch("shutil.which", return_value="/usr/local/bin/openclaw"), \
             patch("os.path.isfile", return_value=False), \
             patch("subprocess.run", return_value=mock_proc_ok):
            result = llm._ask_openclaw("hello", 10)
        assert result == "Hello back!"

    def test_binary_found_via_isfile(self, mock_proc_ok):
        """Absolute path exists on disk → no FileNotFoundError raised."""
        llm = _import_llm()
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=True), \
             patch("subprocess.run", return_value=mock_proc_ok):
            result = llm._ask_openclaw("hello", 10)
        assert result == "Hello back!"


# ===========================================================================
# 2.  _ask_openclaw — JSON response parsing
# ===========================================================================

class TestAskOpenclawJsonParsing:
    """JSON response keys: content, text, response — plus plain-text fallback."""

    @pytest.fixture(autouse=True)
    def patch_binary(self):
        with patch("shutil.which", return_value="/bin/openclaw"), \
             patch("os.path.isfile", return_value=True):
            yield

    def _run(self, stdout_text, returncode=0):
        llm = _import_llm()
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout_text
        proc.stderr = ""
        with patch("subprocess.run", return_value=proc):
            return llm._ask_openclaw("ping", 10)

    def test_json_content_key(self):
        result = self._run(json.dumps({"content": "Answer via content"}))
        assert result == "Answer via content"

    def test_json_text_key(self):
        result = self._run(json.dumps({"text": "Answer via text"}))
        assert result == "Answer via text"

    def test_json_response_key(self):
        result = self._run(json.dumps({"response": "Answer via response"}))
        assert result == "Answer via response"

    def test_json_content_preferred_over_text(self):
        """content key wins when multiple keys present."""
        result = self._run(json.dumps({"content": "primary", "text": "secondary"}))
        assert result == "primary"

    def test_plain_text_fallback(self):
        """Non-JSON output falls back to _clean_output()."""
        result = self._run("This is a plain text answer")
        assert result == "This is a plain text answer"

    def test_invalid_json_falls_back_to_clean_output(self):
        result = self._run("{not valid json}")
        assert "not valid json" in result or len(result) > 0

    def test_empty_content_key_falls_back_to_clean_output(self):
        """JSON with empty content raises ValueError → falls back to _clean_output."""
        result = self._run(json.dumps({"content": ""}))
        assert isinstance(result, str)


# ===========================================================================
# 3.  _ask_openclaw — error handling
# ===========================================================================

class TestAskOpenclawErrors:
    """Non-zero exit codes and empty output raise RuntimeError."""

    @pytest.fixture(autouse=True)
    def patch_binary(self):
        with patch("shutil.which", return_value="/bin/openclaw"), \
             patch("os.path.isfile", return_value=True):
            yield

    def _make_proc(self, stdout="", stderr="", returncode=0):
        p = MagicMock()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = stderr
        return p

    def test_nonzero_exit_raises_runtime_error(self):
        llm = _import_llm()
        with patch("subprocess.run", return_value=self._make_proc(returncode=1, stderr="gateway error")):
            with pytest.raises(RuntimeError, match="openclaw exited rc=1"):
                llm._ask_openclaw("test", 10)

    def test_empty_stdout_raises_runtime_error(self):
        llm = _import_llm()
        with patch("subprocess.run", return_value=self._make_proc(stdout="", returncode=0)):
            with pytest.raises(RuntimeError, match="empty output"):
                llm._ask_openclaw("test", 10)

    def test_timeout_propagates(self):
        llm = _import_llm()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["openclaw"], 10)):
            with pytest.raises(subprocess.TimeoutExpired):
                llm._ask_openclaw("test", 10)


# ===========================================================================
# 4.  Dispatch routing
# ===========================================================================

class TestDispatch:
    """LLM_PROVIDER=openclaw routes to _ask_openclaw."""

    def test_openclaw_in_dispatch_table(self):
        llm = _import_llm()
        assert "openclaw" in llm._DISPATCH
        assert llm._DISPATCH["openclaw"] is llm._ask_openclaw

    def test_ask_llm_routes_to_openclaw(self):
        llm = _import_llm()
        ok_proc = MagicMock()
        ok_proc.returncode = 0
        ok_proc.stdout = json.dumps({"content": "mocked"})
        ok_proc.stderr = ""
        with patch.object(llm, "LLM_PROVIDER", "openclaw"), \
             patch("shutil.which", return_value="/bin/openclaw"), \
             patch("os.path.isfile", return_value=True), \
             patch("subprocess.run", return_value=ok_proc):
            result = llm.ask_llm("test prompt", timeout=10)
        assert result == "mocked"

    def test_ask_llm_falls_back_when_openclaw_not_found(self):
        """FileNotFoundError → ask_llm() returns '' (no local fallback configured)."""
        llm = _import_llm()
        with patch.object(llm, "LLM_PROVIDER", "openclaw"), \
             patch.object(llm, "_ask_openclaw", side_effect=FileNotFoundError("no binary")), \
             patch.object(llm, "LLM_LOCAL_FALLBACK", False), \
             patch("os.path.exists", return_value=False):
            result = llm.ask_llm("test", timeout=5)
        assert result == ""

    def test_all_providers_present(self):
        llm = _import_llm()
        expected = {"taris", "openclaw", "openai", "yandexgpt", "gemini", "anthropic", "local"}
        assert expected == set(llm._DISPATCH.keys())


# ===========================================================================
# 5.  ask_llm_with_history — openclaw path
# ===========================================================================

class TestAskLlmWithHistoryOpenclaw:
    """openclaw provider in ask_llm_with_history uses text-transcript format."""

    def test_history_formatted_as_text_transcript(self):
        llm = _import_llm()
        messages = [
            {"role": "user", "content": "Hallo"},
            {"role": "assistant", "content": "Hallo! Wie kann ich helfen?"},
            {"role": "user", "content": "Was ist 2+2?"},
        ]
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            # Extract the prompt (--message arg)
            idx = cmd.index("--message") + 1
            captured["prompt"] = cmd[idx]
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = json.dumps({"content": "4"})
            proc.stderr = ""
            return proc

        with patch.object(llm, "LLM_PROVIDER", "openclaw"), \
             patch.object(llm, "LLM_LOCAL_FALLBACK", False), \
             patch("shutil.which", return_value="/bin/openclaw"), \
             patch("os.path.isfile", return_value=True), \
             patch("os.path.exists", return_value=False), \
             patch("subprocess.run", side_effect=fake_run):
            result = llm.ask_llm_with_history(messages, timeout=10)

        assert result == "4"
        assert "[User]: Hallo" in captured["prompt"]
        assert "[Assistant]: Hallo! Wie kann ich helfen?" in captured["prompt"]
        assert "[User]: Was ist 2+2?" in captured["prompt"]


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_proc_ok():
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = json.dumps({"content": "Hello back!"})
    proc.stderr = ""
    return proc
