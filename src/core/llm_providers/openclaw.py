"""openclaw.py — OpenClaw AI gateway LLM provider."""
from __future__ import annotations

import json
import os
import subprocess

from core.bot_config import OPENCLAW_BIN, OPENCLAW_SESSION, log_assistant as log
from core.llm_providers.base import clean_output


def ask(prompt: str, timeout: int) -> str:
    """Call OpenClaw AI gateway as an LLM provider (DEVICE_VARIANT=openclaw).

    Uses ``openclaw agent --message <prompt> --json --session-id <session>``
    and parses the JSON reply.  Raises FileNotFoundError when the binary is
    not found so ``ask_llm()`` can fall back gracefully.
    """
    import shutil
    bin_path = OPENCLAW_BIN
    if not os.path.isfile(bin_path) and not shutil.which(bin_path):
        raise FileNotFoundError(f"openclaw binary not found: {bin_path}")

    cmd = [bin_path, "agent", "--message", prompt, "--json", "--session-id", OPENCLAW_SESSION]
    env = {**os.environ, "NO_COLOR": "1"}
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    raw = (proc.stdout or "").strip()

    if proc.returncode != 0:
        err = (proc.stderr or raw or "")[:300]
        log.warning(f"[LLM] openclaw rc={proc.returncode}: {err}")
        raise RuntimeError(f"openclaw exited rc={proc.returncode}: {err[:80]}")

    if not raw:
        raise RuntimeError("openclaw returned empty output")

    try:
        data = json.loads(raw)
        text = (data.get("content") or data.get("text") or data.get("response") or "").strip()
        skill_result = data.get("skill_result")
        if skill_result and isinstance(skill_result, dict):
            from ui.render_telegram import render_skill_result
            rendered = render_skill_result(skill_result)
            if rendered:
                return f"{text}\n\n{rendered}" if text else rendered
        if not text:
            raise ValueError("no content key in openclaw JSON response")
        return text
    except (json.JSONDecodeError, ValueError):
        return clean_output(raw)
