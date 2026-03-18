"""Prompt-template loader — loaded once at import, stays in memory.

Usage:
    from core.bot_prompts import PROMPTS, fmt_prompt

    prompt = fmt_prompt(PROMPTS["calendar"]["event_parse"],
                        now_iso=now_iso, text=text)

fmt_prompt uses a regex {identifier} replacement so that user-supplied
text containing literal { } characters is always safe.
"""
import json
import os
import re as _re
from pathlib import Path

_PROMPTS_FILE = os.environ.get(
    "PROMPTS_FILE",
    str(Path(__file__).parent.parent / "prompts.json"),
)

with open(_PROMPTS_FILE, encoding="utf-8") as _f:
    PROMPTS: dict = json.load(_f)

_PLACEHOLDER = _re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def fmt_prompt(template: str, **kwargs) -> str:
    """Substitute {key} placeholders in *template* using regex.

    Only tokens that look like Python identifiers (``{now_iso}``, ``{text}``,
    ``{bot_name}`` …) are replaced.  Literal JSON braces such as
    ``{"events": []}`` are left untouched, and user-provided text that happens
    to contain ``{word}`` patterns is substituted as-is without raising errors.
    """
    def _replace(m: "_re.Match[str]") -> str:
        key = m.group(1)
        return str(kwargs[key]) if key in kwargs else m.group(0)

    return _PLACEHOLDER.sub(_replace, template)
