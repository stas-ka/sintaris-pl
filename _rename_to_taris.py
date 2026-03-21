"""
One-shot rename script: picoclaw -> taris project-wide.

Rules:
  • picoclaw / PICOCLAW / Picoclaw  ->  taris / TARIS / Taris
  • ~/.picoclaw/  ->  ~/.taris/
  • /home/stas/.picoclaw  ->  /home/stas/.taris
  • pico-tgbot  ->  taris-tgbot
  • pico_token  ->  taris_token
  • pico.db     ->  taris.db
  • "pico." / f"pico.  ->  "taris." / f"taris.   (logger hierarchy prefix)
  • Pico Bot    ->  Taris Bot
  • Pico Russian  ->  Taris Russian

PROTECTED (never changed):
  • Lines containing cdn.jsdelivr.net or @picocss  (Pico CSS framework CDN)
  • Lines containing sipeed/picoclaw                (external GitHub URL)
  • The literal string /usr/bin/picoclaw            (external binary – keep default value)

Usage:
    python _rename_to_taris.py [--dry-run]
"""

import os
import re
import sys
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

ROOT = Path(__file__).parent  # workspace root

# File extensions to process
TEXT_EXTENSIONS = {
    ".py", ".sh", ".service", ".json", ".html", ".md",
    ".txt", ".env", ".yaml", ".yml", ".cfg", ".ini", ".conf", ".rst",
}
# Files with no extension but known to be text
NAMED_FILES = {
    "picoclaw-logrotate", "taris-logrotate",
    "Makefile", "Dockerfile", "AGENTS.md",
}

# Directories to skip entirely
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "backup"}

# Lines containing these patterns are left completely untouched
SKIP_LINE_PATTERNS = [
    re.compile(r"cdn\.jsdelivr\.net"),   # Pico CSS CDN
    re.compile(r"@picocss"),             # Pico CSS reference
    re.compile(r"sipeed/picoclaw"),      # External GitHub URL
]

# ── ordered replacements (longest / most specific FIRST) ──────────────────────
REPLACEMENTS: list[tuple[str, str]] = [
    # Paths — do very first so picoclaw in path is caught
    ("~/.picoclaw/",             "~/.taris/"),
    ("/home/stas/.picoclaw/",    "/home/stas/.taris/"),
    ("/home/stas/.picoclaw",     "/home/stas/.taris"),

    # Compound identifiers before plain picoclaw/pico
    ("PICOCLAW_CONFIG",         "TARIS_CONFIG"),
    ("picoclaw_config",         "taris_config"),
    ("PICOCLAW_BIN",            "TARIS_BIN"),
    ("picoclaw_bin",            "taris_bin"),
    ("_PICOCLAW_DIR",           "_TARIS_DIR"),
    ("_picoclaw_dir",           "_taris_dir"),
    ("picoclaw_ok",             "taris_ok"),
    ("picoclaw-telegram",       "taris-telegram"),
    ("picoclaw-voice",          "taris-voice"),
    ("picoclaw-web",            "taris-web"),
    ("picoclaw-llm",            "taris-llm"),
    ("picoclaw-tunnel",         "taris-tunnel"),
    ("picoclaw-gateway",        "taris-gateway"),
    ("picoclaw-logrotate",      "taris-logrotate"),

    # Main identifier
    ("PICOCLAW",                "TARIS"),
    ("Picoclaw",                "Taris"),
    ("picoclaw",                "taris"),      # catches ~/.picoclaw, service names, function names

    # pico sub-names (after main picoclaw sweep)
    ("pico-tgbot",              "taris-tgbot"),
    ("pico_token",              "taris_token"),
    ("pico.db",                 "taris.db"),

    # Logger hierarchy prefix  "pico.access"  f"pico.{name}"
    ('"pico.',                  '"taris.'),
    ("f\"pico.",                'f"taris.'),
    ("'pico.",                  "'taris."),

    # Display / description strings
    ("Pico Bot",                "Taris Bot"),
    ("Pico Russian",            "Taris Russian"),

    # Misc: taris-tgbot module docstring logger name if still raw
    ("pico-tgbot",              "taris-tgbot"),  # idempotent safety
]

# Protect the actual default VALUE "/usr/bin/picoclaw" — it's the external binary path.
# We replace the VARIABLE NAMES (PICOCLAW_BIN, picoclaw_bin) but keep the binary path value.
_BINARY_PLACEHOLDER = "\x00BINARY_PATH\x00"

def protect_binary_path(line: str) -> str:
    """Temporarily conceal /usr/bin/picoclaw so substitutions don't touch it."""
    return line.replace("/usr/bin/picoclaw", _BINARY_PLACEHOLDER)

def restore_binary_path(line: str) -> str:
    return line.replace(_BINARY_PLACEHOLDER, "/usr/bin/picoclaw")


def process_line(line: str) -> str:
    # Skip protected lines completely
    for pat in SKIP_LINE_PATTERNS:
        if pat.search(line):
            return line

    # Protect external binary path
    line = protect_binary_path(line)

    # Apply ordered replacements
    for old, new in REPLACEMENTS:
        if old in line:
            line = line.replace(old, new)

    # Restore binary path
    line = restore_binary_path(line)
    return line


def process_file(path: Path) -> bool:
    """Process a single file. Returns True if the file was modified."""
    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        print(f"  SKIP (read error): {path}  — {exc}")
        return False

    lines = original.splitlines(keepends=True)
    new_lines = [process_line(l) for l in lines]
    new_content = "".join(new_lines)

    if new_content == original:
        return False

    if not DRY_RUN:
        path.write_text(new_content, encoding="utf-8")

    return True


def should_process(path: Path) -> bool:
    # Skip hidden files except .env
    if path.name.startswith(".") and path.name != ".env":
        return False
    # Skip skip-dirs in any ancestor
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    # Skip this script itself
    if path.name == "_rename_to_taris.py":
        return False
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return True
    if path.name in NAMED_FILES:
        return True
    return False


def walk_and_process(base: Path) -> list[Path]:
    modified: list[Path] = []
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        if not should_process(p):
            continue
        if process_file(p):
            modified.append(p)
            rel = p.relative_to(ROOT)
            print(f"  {'[DRY] ' if DRY_RUN else ''}EDITED  {rel}")
    return modified


def rename_service_files(services_dir: Path):
    """Rename picoclaw-*.service  ->  taris-*.service (and logrotate)."""
    if not services_dir.exists():
        return
    for p in sorted(services_dir.iterdir()):
        if "picoclaw" not in p.name:
            continue
        new_name = p.name.replace("picoclaw", "taris")
        new_path = p.parent / new_name
        if new_path.exists():
            print(f"  [SKIP rename] target already exists: {new_name}")
            continue
        print(f"  {'[DRY] ' if DRY_RUN else ''}RENAME  {p.name}  ->  {new_name}")
        if not DRY_RUN:
            p.rename(new_path)


if __name__ == "__main__":
    mode = "DRY RUN" if DRY_RUN else "LIVE"
    print(f"\n=== rename picoclaw->taris  [{mode}] ===\n")

    modified = walk_and_process(ROOT)

    print(f"\n---\nRenaming service files …")
    rename_service_files(ROOT / "src" / "services")

    print(f"\n=== Done.  {len(modified)} file(s) edited. ===\n")
    if DRY_RUN:
        print("Re-run without --dry-run to apply changes.\n")
