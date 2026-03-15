"""
bot_users.py — User and registration file I/O.

Pure data layer — no Telegram API calls.  All functions here read/write JSON
files on disk and return plain Python objects.  Handler logic that displays
results to the user lives in bot_admin.py.
"""

import datetime
import json
from pathlib import Path
from typing import Optional

from bot_config import REGISTRATIONS_FILE, log


# ─────────────────────────────────────────────────────────────────────────────
# Registration record helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_registrations() -> list[dict]:
    """Load registration list from REGISTRATIONS_FILE; returns [] on error."""
    try:
        data = json.loads(Path(REGISTRATIONS_FILE).read_text(encoding="utf-8"))
        return data.get("registrations", [])
    except Exception:
        return []


def _save_registrations(regs: list[dict]) -> None:
    try:
        Path(REGISTRATIONS_FILE).write_text(
            json.dumps({"registrations": regs}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"[Reg] save failed: {e}")


def _find_registration(chat_id: int) -> Optional[dict]:
    """Return the registration record for chat_id, or None."""
    for r in _load_registrations():
        if r.get("chat_id") == chat_id:
            return r
    return None


def _upsert_registration(chat_id: int, username: str, name: str,
                         status: str = "pending",
                         first_name: str = "", last_name: str = "") -> None:
    """Add a new registration record, or update status/name if one exists."""
    regs = _load_registrations()
    for r in regs:
        if r.get("chat_id") == chat_id:
            r["status"]     = status
            r["username"]   = username
            r["first_name"] = first_name
            r["last_name"]  = last_name
            r["name"]       = name
            _save_registrations(regs)
            return
    regs.append({
        "chat_id":    chat_id,
        "username":   username,
        "first_name": first_name,
        "last_name":  last_name,
        "name":       name,
        "timestamp":  datetime.datetime.now().isoformat(timespec="seconds"),
        "status":     status,
    })
    _save_registrations(regs)


def _set_reg_status(chat_id: int, status: str) -> None:
    """Update the status field of an existing registration."""
    regs = _load_registrations()
    for r in regs:
        if r.get("chat_id") == chat_id:
            r["status"] = status
            _save_registrations(regs)
            return


def _get_pending_registrations() -> list[dict]:
    return [r for r in _load_registrations() if r.get("status") == "pending"]


def _is_blocked_reg(chat_id: int) -> bool:
    r = _find_registration(chat_id)
    return r is not None and r.get("status") == "blocked"


def _is_pending_reg(chat_id: int) -> bool:
    r = _find_registration(chat_id)
    return r is not None and r.get("status") == "pending"


# ─────────────────────────────────────────────────────────────────────────────
# Notes — per-user Markdown file storage (data layer only, no Telegram calls)
# ─────────────────────────────────────────────────────────────────────────────

import re as _notes_re
from bot_config import NOTES_DIR


def _resolve_storage_id(chat_id: int) -> str:
    """Return the web UUID for this Telegram chat_id if an account is linked,
    otherwise fall back to str(chat_id).

    Reads accounts.json and matches on the telegram_chat_id field so that
    Telegram and Web UI share the same notes/calendar directories.
    """
    try:
        from bot_auth import ACCOUNTS_FILE  # noqa: PLC0415  (local import avoids circular)
        data = json.loads(Path(ACCOUNTS_FILE).read_text(encoding="utf-8"))
        for acct in data.get("accounts", []):
            if acct.get("telegram_chat_id") == chat_id:
                return acct["user_id"]
    except Exception:
        pass
    return str(chat_id)


def _slug(title: str) -> str:
    """Convert a note title to a safe filename slug (lowercase, underscores)."""
    s = title.lower().strip()
    s = _notes_re.sub(r"[^\w\s\u0400-\u04ff-]", "", s)
    s = _notes_re.sub(r"[\s]+", "_", s)
    s = s.strip("_")
    return s[:60] or "note"


def _notes_user_dir(chat_id: int) -> Path:
    """Return (and create) the per-user notes directory.

    If the Telegram chat_id is linked to a web account, uses the web UUID
    so that notes are shared between Telegram and the Web UI.
    """
    p = Path(NOTES_DIR) / _resolve_storage_id(chat_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _list_notes_for(chat_id: int) -> list[dict]:
    """Return [{slug, title, mtime}] sorted by modification time (newest first)."""
    d = _notes_user_dir(chat_id)
    notes = []
    for f in sorted(d.glob("*.md"), key=lambda x: -x.stat().st_mtime):
        try:
            first_line = f.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        except Exception:
            first_line = f.stem
        notes.append({"slug": f.stem, "title": first_line, "mtime": f.stat().st_mtime})
    return notes


def _load_note_text(chat_id: int, slug: str) -> Optional[str]:
    """Return note file contents or None if not found."""
    p = _notes_user_dir(chat_id) / f"{slug}.md"
    return p.read_text(encoding="utf-8") if p.exists() else None


def _save_note_file(chat_id: int, slug: str, content: str) -> None:
    """Write note file (creates or overwrites)."""
    p = _notes_user_dir(chat_id) / f"{slug}.md"
    p.write_text(content, encoding="utf-8")
    log.info(f"[Notes] saved '{slug}' for user {chat_id}")


def _delete_note_file(chat_id: int, slug: str) -> bool:
    """Delete a note file. Returns True if deleted, False if not found."""
    p = _notes_user_dir(chat_id) / f"{slug}.md"
    if p.exists():
        p.unlink()
        log.info(f"[Notes] deleted '{slug}' for user {chat_id}")
        return True
    return False
