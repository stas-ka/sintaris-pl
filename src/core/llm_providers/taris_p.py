"""taris.py — taris CLI LLM provider (wraps OpenRouter or configured LLM)."""
from __future__ import annotations

import os
import subprocess

from core.bot_config import TARIS_BIN, TARIS_CONFIG, log_assistant as log
from core.llm_providers.base import clean_output, get_active_model, raise_if_http_error


def ask(prompt: str, timeout: int) -> str:
    """Call taris CLI (wraps OpenRouter or configured LLM)."""
    model = get_active_model()
    cmd = [TARIS_BIN, "agent"]
    if model:
        cmd += ["--model", model]
    cmd += ["-m", prompt]

    env = {**os.environ, "NO_COLOR": "1"}
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env,
    )
    if proc.returncode != 0:
        err_text = (proc.stderr or proc.stdout or "").strip()
        log.warning(f"[LLM] taris rc={proc.returncode}: {err_text[:300]}")
        raise_if_http_error(err_text)
        raise RuntimeError(f"taris exited rc={proc.returncode}: {err_text[:80]}")
    raw = proc.stdout or proc.stderr or ""
    result = clean_output(raw)
    if not result:
        raise RuntimeError("taris returned empty output")
    raise_if_http_error(result)
    return result
