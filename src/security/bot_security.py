"""
bot_security.py — Prompt injection protection and LLM security guard.

Three-layer defense applied to all user-originated text (chat, voice, calendar):

  L1 — Input validation (pre-LLM):
         Pattern-based scan of every incoming message.  If an injection
         signature is detected the message is blocked immediately — the LLM
         is never called.

  L2 — User input delimiting:
         User text is wrapped in [USER] … [/USER] markers so the LLM
         treats it as data, not as instructions it must follow.

  L3 — Security preamble (appended to every regular-chat / voice prompt):
         A policy block at the top of every LLM call that explicitly
         instructs the model to refuse credential/path disclosure,
         persona-override attempts, and command generation.

Access restriction (enforced by callers):
  - System Chat mode → admin-only (command execution blocked for regular users).
  - Injection-blocked messages are never forwarded to the LLM.
"""

import json
import re

from core.bot_config import BOT_NAME, log_security as log
from core.bot_prompts import PROMPTS, fmt_prompt


# ─────────────────────────────────────────────────────────────────────────────
# L3 — Security preamble (prefix for all regular chat / voice LLM calls)
# ─────────────────────────────────────────────────────────────────────────────

SECURITY_PREAMBLE = fmt_prompt(PROMPTS["security_preamble"], bot_name=BOT_NAME)


# ─────────────────────────────────────────────────────────────────────────────
# L2 — User-input wrapping
# ─────────────────────────────────────────────────────────────────────────────

def _wrap_user_input(text: str) -> str:
    """Enclose user text in hard delimiters so the LLM treats it as data."""
    return f"[USER]\n{text}\n[/USER]"


# ─────────────────────────────────────────────────────────────────────────────
# L1 — Injection / exfiltration pattern detection
# ─────────────────────────────────────────────────────────────────────────────

# Each tuple: (compiled regex, human-readable attack category)
_INJECTION_RULES: list[tuple[re.Pattern, str]] = [

    # ── Instruction override / persona hijack (Russian) ──────────────────────
    (re.compile(
        r"\bигнорир\w{1,8}\b.{0,60}\b(систем|инструкц|правил)\w*\b",
        re.I | re.S), "instruction override (ru)"),
    (re.compile(
        r"\bзабудь\b.{0,60}\b(инструкц|правил|систем|задани)\w*\b",
        re.I | re.S), "instruction override (ru)"),
    (re.compile(
        r"\bпритворис[ьh]\b.{0,40}\bты\b",
        re.I | re.S), "persona hijack (ru)"),
    (re.compile(
        r"\bсделай\s+вид\b.{0,40}\bбудто\b",
        re.I | re.S), "persona hijack (ru)"),
    (re.compile(
        r"\bты\s+(теперь|сейчас|отныне)\s+(не\s+)?(бот|ассистент|ии)\b",
        re.I | re.S), "persona hijack (ru)"),
    (re.compile(
        r"\bновые\s+инструкци\w*\s*:",
        re.I), "instruction injection (ru)"),

    # ── Instruction override / persona hijack (English) ──────────────────────
    (re.compile(
        r"\bignore\b.{0,60}\b(previous|prior|above|all)\b.{0,40}\b(instruction|rule|prompt|system)s?\b",
        re.I | re.S), "instruction override (en)"),
    (re.compile(
        r"\bdisregard\b.{0,60}\b(instruction|rule|system\s+prompt)s?\b",
        re.I | re.S), "instruction override (en)"),
    (re.compile(
        r"\bforget\b.{0,60}\b(instruction|rule|prompt)s?\b",
        re.I | re.S), "instruction override (en)"),
    (re.compile(
        r"\byou\s+are\s+now\b.{0,50}\b(not|no\s+longer|free|unfiltered|different)\b",
        re.I | re.S), "persona hijack (en)"),
    (re.compile(
        r"\bact\s+as\b.{0,40}\b(unfiltered|unrestricted|without\s+restriction)\b",
        re.I | re.S), "persona hijack (en)"),
    (re.compile(
        r"\bpretend\b.{0,40}\b(you\s+are|to\s+be)\b.{0,30}\b(not|free|different|without)\b",
        re.I | re.S), "persona hijack (en)"),
    (re.compile(
        r"\bfrom\s+now\s+on\b.{0,60}\b(ignore|forget|disregard|bypass)\b",
        re.I | re.S), "instruction override (en)"),
    (re.compile(
        r"\bnew\s+instructions?\s*:",
        re.I), "instruction injection (en)"),
    (re.compile(
        r"\bsystem\s+prompt\s*:",
        re.I), "system prompt injection"),

    # ── Prompt / instruction extraction ──────────────────────────────────────
    (re.compile(
        r"\b(системн\w+|первоначальн\w+|исходн\w+)\s+(промпт|инструкц|задани)\w*\b",
        re.I), "prompt extraction (ru)"),
    (re.compile(
        r"\b(system|initial|original)\b.{0,20}\b(prompt|instruction)s?\b",
        re.I), "prompt extraction (en)"),
    (re.compile(
        r"\b(repeat|print|show|tell\s+me|reveal|output|display)\b.{0,40}\b(instructions?|prompt|rules?)\b",
        re.I), "prompt extraction (en)"),
    (re.compile(
        r"\b(повтори|покажи|напечатай|выведи)\b.{0,40}\b(инструкц|правила|промпт)\w*\b",
        re.I), "prompt extraction (ru)"),

    # ── Credential / sensitive-data extraction ────────────────────────────────
    (re.compile(
        r"\b(reveal|show|print|tell\s+me|display|output)\b.{0,60}"
        r"\b(api[\s_-]?key|bot[\s_-]?token|password|secret|credential|chat[\s_-]?id)\b",
        re.I), "credential extraction (en)"),
    (re.compile(
        r"\b(api[\s_-]?key|bot[\s_-]?token|пароль|password|секрет|secret|bearer)\b"
        r".{0,40}\b(what|is|are|какой|скажи|покажи)\b",
        re.I), "credential query"),
    (re.compile(
        r"\b(покажи|скажи|выведи|напечатай)\b.{0,60}"
        r"\b(токен|ключ|пароль|api\s*ключ|credentials?)\b",
        re.I), "credential extraction (ru)"),

    # ── File path / environment disclosure ───────────────────────────────────
    (re.compile(
        r"\b(cat|read|open|print|show|output)\b\s*.{0,40}"
        r"(/etc/|/home/|bot\.env|\.env\b|\.taris|config\.json)",
        re.I), "path disclosure"),
    (re.compile(
        r"\bbot\.env\b|\b/home/stas\b",
        re.I), "path disclosure (hardcoded)"),

    # ── Shell command injection syntax ────────────────────────────────────────
    (re.compile(r"`[^`]{3,150}`"),
     "shell backtick injection"),
    (re.compile(r"\$\([^)]{3,150}\)"),
     "shell subshell injection"),
    (re.compile(
        r";\s*(rm\b|chmod\b|wget\b|curl\b|nc\b|ncat\b|bash\b|sh\b|python\b|perl\b|dd\b|mkfs\b)"),
     "dangerous shell command"),

    # ── Known jailbreak keywords ──────────────────────────────────────────────
    (re.compile(r"\bDAN\b"),
     "jailbreak (DAN)"),
    (re.compile(r"\bjailbreak\b", re.I),
     "jailbreak keyword"),
    (re.compile(r"\bdeveloper\s+mode\b", re.I),
     "jailbreak (dev mode)"),
]


def _check_injection(text: str) -> tuple[bool, str]:
    """
    Scan *text* for known injection / exfiltration attack patterns.

    Returns:
        (True, reason_string)  — if a suspicious pattern is detected.
        (False, "")            — if the text appears clean.

    The first matching rule wins; subsequent rules are not evaluated.
    Logs a WARNING for every positive match (chat_id logged by the caller).
    """
    for pattern, reason in _INJECTION_RULES:
        if pattern.search(text):
            log.warning(f"[Security] injection pattern matched ({reason}): {text[:120]!r}")
            return True, reason
    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# System-chat command allowlists (used by bot_handlers._handle_system_message)
# ─────────────────────────────────────────────────────────────────────────────

# Admin: read-only monitoring + config inspection
ADMIN_ALLOWED_CMDS: set[str] = {
    "cat", "head", "tail", "grep", "ls", "find", "pwd", "du", "df", "free",
    "ps", "top", "htop", "uptime", "uname", "date", "hostname", "id", "who",
    "systemctl status", "journalctl", "ping", "curl", "dmesg", "lsblk",
    "vcgencmd", "lscpu", "lsusb", "env", "printenv", "stat", "wc", "sort",
    "echo",  # knowledge answers: LLM may return echo "answer text" for informational questions
}

# Developer: all admin commands + service control + code/file operations
DEVELOPER_ALLOWED_CMDS: set[str] = ADMIN_ALLOWED_CMDS | {
    "systemctl restart", "systemctl stop", "systemctl start",
    "sudo systemctl",
    "cp", "mv", "mkdir", "rm", "touch", "chmod", "chown",
    "python3", "pip3", "pip", "git", "nano", "vi", "vim",
    "pscp", "plink", "scp", "rsync",
    "tar", "unzip", "zip", "wget", "apt",
}


SYSCHAT_EXTRA_BLOCKED_KEY = "syschat_blocked_cmds"


def get_extra_blocked_cmds() -> list[str]:
    """Return admin-configured extra blocked commands (stored in system_settings.json).

    Commands in this list override the built-in allowlists and are denied for all roles.
    """
    try:
        from core.bot_db import db_get_system_setting
        raw = db_get_system_setting(SYSCHAT_EXTRA_BLOCKED_KEY, "[]")
        result = json.loads(raw) if raw else []
        return result if isinstance(result, list) else []
    except Exception:
        return []


def _classify_cmd_class(cmd: str) -> str:
    """Return 'admin', 'developer', or 'blocked' for *cmd*.

    'admin'     — command is allowed for the admin role (read-only + inspection)
    'developer' — command requires the developer role (service control / writes)
    'blocked'   — command is not on any allowlist or is in the extra blocklist
    """
    cmd_lower = cmd.strip().lower()
    # Extra blocklist has highest priority — overrides allowlists for all roles
    for blocked in get_extra_blocked_cmds():
        b = blocked.strip().lower()
        if b and (cmd_lower == b or cmd_lower.startswith(b + " ")):
            return "blocked"
    # Check admin allowlist (read-only + inspection)
    for allowed in ADMIN_ALLOWED_CMDS:
        if cmd_lower == allowed or cmd_lower.startswith(allowed + " "):
            return "admin"
    # Check developer-only additions
    for allowed in DEVELOPER_ALLOWED_CMDS - ADMIN_ALLOWED_CMDS:
        if cmd_lower == allowed or cmd_lower.startswith(allowed + " "):
            return "developer"
    return "blocked"
