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

from core.bot_config import REGISTRATIONS_FILE, log


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
            try:
                from core.store import store
                store.upsert_user(chat_id, username=username,
                                  name=name or f"{first_name} {last_name}".strip(),
                                  role=status)
            except Exception as _e:
                log.debug("[Users] store.upsert_user failed: %s", _e)
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
    try:
        from core.store import store
        store.upsert_user(chat_id, username=username,
                          name=name or f"{first_name} {last_name}".strip(),
                          role=status)
    except Exception as _e:
        log.debug("[Users] store.upsert_user failed: %s", _e)


def _set_reg_status(chat_id: int, status: str) -> None:
    """Update the status field of an existing registration."""
    regs = _load_registrations()
    for r in regs:
        if r.get("chat_id") == chat_id:
            r["status"] = status
            _save_registrations(regs)
            try:
                from core.store import store
                store.set_user_role(chat_id, status)
            except Exception as _e:
                log.debug("[Users] store.set_user_role failed: %s", _e)
            return


def _set_reg_lang(chat_id: int, lang: str) -> None:
    """Persist the user's chosen interface language to the registration record."""
    regs = _load_registrations()
    for r in regs:
        if r.get("chat_id") == chat_id:
            r["lang"] = lang
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
from core.bot_config import NOTES_DIR
from core.store import store


def _resolve_storage_id(chat_id: int) -> str:
    """Return the web UUID for this Telegram chat_id if an account is linked,
    otherwise fall back to str(chat_id).

    Reads accounts.json and matches on the telegram_chat_id field so that
    Telegram and Web UI share the same notes/calendar directories.
    """
    try:
        from security.bot_auth import ACCOUNTS_FILE  # noqa: PLC0415  (local import avoids circular)
        data = json.loads(Path(ACCOUNTS_FILE).read_text(encoding="utf-8"))
        for acct in data.get("accounts", []):
            if acct.get("telegram_chat_id") == chat_id:
                return acct["user_id"]
    except Exception:
        pass
    return str(chat_id)


def _slug(title: str) -> str:
    """Convert a note title to a safe filename slug (lowercase, underscores).

    Limits to 48 bytes so that 'note_delete:{slug}' stays under Telegram's
    64-byte callback_data limit (12 byte prefix + 48 byte slug = 60 bytes).
    """
    s = title.lower().strip()
    s = _notes_re.sub(r"[^\w\s\u0400-\u04ff-]", "", s)
    s = _notes_re.sub(r"[\s]+", "_", s)
    s = s.strip("_")
    # Truncate by bytes — Cyrillic chars are 2 bytes each, pure char limit is wrong
    encoded = s.encode("utf-8")
    if len(encoded) > 48:
        encoded = encoded[:48]
        s = encoded.decode("utf-8", errors="ignore").rstrip("_")
    return s or "note"


def _notes_user_dir(chat_id: int) -> Path:
    """Return (and create) the per-user notes directory.

    If the Telegram chat_id is linked to a web account, uses the web UUID
    so that notes are shared between Telegram and the Web UI.

    Auto-migration: if notes exist under the old str(chat_id) directory and
    the resolved storage_id is a UUID (account was linked after notes were
    created), the files are moved transparently so existing notes remain visible.
    """
    import shutil as _shutil
    storage_id = _resolve_storage_id(chat_id)
    p = Path(NOTES_DIR) / storage_id
    p.mkdir(parents=True, exist_ok=True)

    # Migrate notes created before account linking from chat_id dir → UUID dir
    if storage_id != str(chat_id):
        old_dir = Path(NOTES_DIR) / str(chat_id)
        if old_dir.exists() and any(old_dir.glob("*.md")):
            for src in sorted(old_dir.glob("*.md")):
                dst = p / src.name
                if not dst.exists():
                    _shutil.move(str(src), str(dst))
                    log.info(f"[Notes] migrated '{src.name}' {old_dir.name} → {p.name}")
            if not any(old_dir.glob("*.md")):
                try:
                    old_dir.rmdir()
                    log.info(f"[Notes] removed empty old dir {old_dir.name}")
                except Exception:
                    pass
    return p


def _list_notes_for(chat_id: int) -> list[dict]:
    """Return [{slug, title, mtime}] sorted newest-first. DB-only (store.list_notes)."""
    db_notes = store.list_notes(chat_id)
    return [{"slug": n["slug"], "title": n["title"], "mtime": 0} for n in db_notes]


def _load_note_text(chat_id: int, slug: str) -> Optional[str]:
    """Return note contents from the DB store."""
    note = store.load_note(chat_id, slug)
    return note.get("content") if note else None


def _save_note_file(chat_id: int, slug: str, content: str) -> None:
    """Save note to the DB store."""
    _title = (content.splitlines()[0].lstrip("# ").strip()
              if content.strip() else slug.replace("_", " "))
    store.save_note(chat_id, slug, _title, content)
    log.info(f"[Notes] saved '{slug}' for user {chat_id}")


def _delete_note_file(chat_id: int, slug: str) -> bool:
    """Delete note from the DB store. Returns True if deleted."""
    deleted = store.delete_note(chat_id, slug)
    if deleted:
        log.info(f"[Notes] deleted '{slug}' for user {chat_id}")
    return bool(deleted)
