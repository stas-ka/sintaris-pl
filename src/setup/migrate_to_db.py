#!/usr/bin/env python3
"""migrate_to_db.py — Idempotent JSON → SQLite migration for picoclaw.

Reads all legacy JSON data files from ~/.picoclaw/ and writes them into the
picoclaw SQLite database (pico.db).  Safe to run multiple times — every
INSERT uses INSERT OR IGNORE or INSERT OR REPLACE so existing rows are not
duplicated.

Usage (on Pi, from ~/.picoclaw/ directory):
    python3 setup/migrate_to_db.py            # apply migration
    python3 setup/migrate_to_db.py --dry-run  # print what would happen, no writes

Usable on both PI1 and PI2 — reads/writes ~/.picoclaw/pico.db.

Skipped sources:
  contacts — already live in SQLite (bot_contacts.py uses get_db() directly).
  last_digest.txt — transient cache, not worth migrating.

Password encryption:
  Mail credentials (app_password) are stored in plaintext in JSON.  If the
  environment variable STORE_ENCRYPTION_KEY is set to a valid Fernet key,
  the password is encrypted before being written to mail_creds.password_enc.
  Otherwise it is stored as-is with a warning.

  Generate a key once and store it in ~/.picoclaw/bot.env:
      python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Allow running directly or as a module from the repo root
# ---------------------------------------------------------------------------
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.bot_config import (
    CALENDAR_DIR,
    MAIL_CREDS_DIR,
    NOTES_DIR,
    REGISTRATIONS_FILE,
    USERS_FILE,
    _PENDING_TTS_FILE,
    _VOICE_OPTS_DEFAULTS,
    _VOICE_OPTS_FILE,
    log as _bot_log,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
log = logging.getLogger("migrate")

# ---------------------------------------------------------------------------
# DB path — matches store.py / bot_db.py defaults
# ---------------------------------------------------------------------------
_PICOCLAW_DIR = Path(os.path.expanduser("~/.picoclaw"))
DB_PATH = Path(os.environ.get("STORE_DB_PATH", str(_PICOCLAW_DIR / "pico.db")))
ACCOUNTS_FILE = _PICOCLAW_DIR / "accounts.json"


# ============================================================
# Helpers
# ============================================================

def _get_conn() -> sqlite3.Connection:
    """Return a synchronous WAL connection used only in this migration."""
    conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _fernet_encrypt(plaintext: str) -> str:
    """Fernet-encrypt *plaintext* if STORE_ENCRYPTION_KEY is set; else return as-is."""
    key = os.environ.get("STORE_ENCRYPTION_KEY", "")
    if not key:
        return plaintext
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key.encode())
        return f.encrypt(plaintext.encode()).decode()
    except Exception as exc:
        log.warning(f"[encrypt] failed: {exc}; storing plaintext")
        return plaintext


def _build_storage_id_map() -> dict[str, int]:
    """Build a {storage_id: chat_id} reverse map from accounts.json.

    storage_id is either a web UUID (when a Telegram account is linked to a web
    account) or str(chat_id) (the fallback).  This covers both cases.
    """
    result: dict[str, int] = {}
    try:
        data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        for acct in data.get("accounts", []):
            uid = acct.get("user_id")
            cid = acct.get("telegram_chat_id")
            if uid and cid:
                result[str(uid)] = int(cid)
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.warning(f"[accounts] could not read {ACCOUNTS_FILE}: {exc}")
    return result


def _chat_id_from_storage_id(storage_id: str, sid_map: dict[str, int]) -> Optional[int]:
    """Resolve a storage_id (UUID or str int) back to a Telegram chat_id.

    1. Check the UUID→chat_id map (accounts.json-derived).
    2. Try to parse it as a plain int (the str(chat_id) fallback case).
    Returns None if neither succeeds.
    """
    if storage_id in sid_map:
        return sid_map[storage_id]
    try:
        return int(storage_id)
    except ValueError:
        return None


# ============================================================
# Migration functions
# ============================================================

def _migrate_users(conn: sqlite3.Connection, dry_run: bool) -> int:
    """registrations.json + USERS_FILE → users table.

    Status mapping:
      "approved" → role = "user"
      "blocked"  → role = "blocked"
      "pending"  → role = "pending"
      (anything else) → role = "user"

    Dynamic guest users (USERS_FILE) are inserted with role = "user" unless a
    registration record already exists (INSERT OR IGNORE avoids overwriting).
    """
    count = 0

    # 1. Registrations
    try:
        data = json.loads(Path(REGISTRATIONS_FILE).read_text(encoding="utf-8"))
        regs = data.get("registrations", [])
    except FileNotFoundError:
        log.warning(f"[users] {REGISTRATIONS_FILE} not found — skipping registrations")
        regs = []
    except Exception as exc:
        log.warning(f"[users] could not read registrations: {exc}")
        regs = []

    for r in regs:
        cid = r.get("chat_id")
        if not cid:
            continue
        status = r.get("status", "pending")
        role_map = {"approved": "user", "blocked": "blocked", "pending": "pending"}
        role = role_map.get(status, "user")
        name = r.get("name") or r.get("first_name") or ""
        username = r.get("username") or ""
        created_at = r.get("timestamp", "")
        approved_at = created_at if status == "approved" else None

        log.info(f"  [users] chat_id={cid} username={username!r} role={role}")
        if not dry_run:
            conn.execute(
                """
                INSERT OR IGNORE INTO users
                    (chat_id, username, name, role, language, audio_on, created_at, approved_at)
                VALUES (?, ?, ?, ?, 'ru', 0, ?, ?)
                """,
                (cid, username, name, role, created_at, approved_at),
            )
        count += 1

    # 2. Dynamic guest users (set of chat_ids)
    try:
        users_raw = json.loads(Path(USERS_FILE).read_text(encoding="utf-8"))
        # May be {"users": [...]} or just [...]
        if isinstance(users_raw, dict):
            guest_ids = [int(x) for x in users_raw.get("users", [])]
        else:
            guest_ids = [int(x) for x in users_raw]
    except FileNotFoundError:
        guest_ids = []
    except Exception as exc:
        log.warning(f"[users] could not read {USERS_FILE}: {exc}")
        guest_ids = []

    for cid in guest_ids:
        log.info(f"  [users] dynamic guest chat_id={cid}")
        if not dry_run:
            conn.execute(
                """
                INSERT OR IGNORE INTO users
                    (chat_id, username, name, role, language, audio_on, created_at)
                VALUES (?, '', '', 'user', 'ru', 0, '')
                """,
                (cid,),
            )
        count += 1

    return count


def _migrate_voice_opts(conn: sqlite3.Connection, dry_run: bool) -> int:
    """voice_opts.json → global_voice_opts table (key/value)."""
    try:
        saved = json.loads(Path(_VOICE_OPTS_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.warning(f"[voice_opts] {_VOICE_OPTS_FILE} not found — skipping")
        return 0
    except Exception as exc:
        log.warning(f"[voice_opts] could not read: {exc}")
        return 0

    merged = dict(_VOICE_OPTS_DEFAULTS)
    merged.update({k: v for k, v in saved.items() if k in merged})

    count = 0
    for key, value in merged.items():
        str_val = "1" if value else "0"
        log.info(f"  [voice_opts] {key} = {str_val}")
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO global_voice_opts (key, value) VALUES (?, ?)",
                (key, str_val),
            )
        count += 1

    return count


def _migrate_calendar(conn: sqlite3.Connection, dry_run: bool) -> int:
    """CALENDAR_DIR/<storage_id>.json → calendar_events table."""
    cal_dir = Path(CALENDAR_DIR)
    if not cal_dir.exists():
        log.warning(f"[calendar] {cal_dir} does not exist — skipping")
        return 0

    sid_map = _build_storage_id_map()
    count = 0

    for json_file in cal_dir.glob("*.json"):
        storage_id = json_file.stem
        chat_id = _chat_id_from_storage_id(storage_id, sid_map)
        if chat_id is None:
            log.warning(f"  [calendar] cannot resolve storage_id={storage_id!r} → skipping")
            continue

        try:
            events = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning(f"  [calendar] could not read {json_file}: {exc}")
            continue

        if not isinstance(events, list):
            log.warning(f"  [calendar] unexpected format in {json_file} — skipping")
            continue

        for ev in events:
            ev_id = ev.get("id") or ev.get("ev_id")
            title = ev.get("title", "")
            dt_iso = ev.get("dt_iso") or ev.get("dt") or ""
            remind = ev.get("remind_before_min", 15)
            reminded = 1 if ev.get("reminded") else 0
            created_at = ev.get("created_at", "")

            if not ev_id or not dt_iso:
                log.info(f"    [calendar] skipping incomplete event {ev_id!r} in {json_file.name}")
                continue

            log.info(f"  [calendar] chat_id={chat_id} ev_id={ev_id!r} title={title!r}")
            if not dry_run:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO calendar_events
                        (id, chat_id, title, dt_iso, remind_before_min, reminded, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (ev_id, chat_id, title, dt_iso, remind, reminded, created_at),
                )
            count += 1

    return count


def _migrate_notes_index(conn: sqlite3.Connection, dry_run: bool) -> int:
    """notes/<storage_id>/*.md → notes_index table.

    Note content stays on disk; we only migrate the index metadata.
    Title is extracted from the first `# ` heading in the file, or falls back
    to the filename stem.
    """
    notes_root = Path(NOTES_DIR)
    if not notes_root.exists():
        log.warning(f"[notes] {notes_root} does not exist — skipping")
        return 0

    sid_map = _build_storage_id_map()
    count = 0

    for user_dir in notes_root.iterdir():
        if not user_dir.is_dir():
            continue
        storage_id = user_dir.name
        chat_id = _chat_id_from_storage_id(storage_id, sid_map)
        if chat_id is None:
            log.warning(f"  [notes] cannot resolve storage_id={storage_id!r} → skipping")
            continue

        for md_file in user_dir.glob("*.md"):
            slug = md_file.stem
            # Extract title from first # heading
            title = slug.replace("_", " ").title()
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
            except Exception as exc:
                log.warning(f"    [notes] could not read {md_file}: {exc}")

            mtime = md_file.stat().st_mtime
            import datetime
            created_at = datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")

            log.info(f"  [notes] chat_id={chat_id} slug={slug!r} title={title!r}")
            if not dry_run:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO notes_index
                        (slug, chat_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (slug, chat_id, title, created_at, created_at),
                )
            count += 1

    return count


def _migrate_mail_creds(conn: sqlite3.Connection, dry_run: bool) -> int:
    """MAIL_CREDS_DIR/<chat_id>.json → mail_creds table.

    Also reads <chat_id>_target.txt for the SMTP send-to address.
    Passwords are Fernet-encrypted if STORE_ENCRYPTION_KEY is set.
    """
    mail_dir = Path(MAIL_CREDS_DIR)
    if not mail_dir.exists():
        log.warning(f"[mail] {mail_dir} does not exist — skipping")
        return 0

    count = 0
    no_key = not os.environ.get("STORE_ENCRYPTION_KEY", "")
    if no_key:
        log.warning("[mail] STORE_ENCRYPTION_KEY not set — storing passwords in plaintext")

    for json_file in mail_dir.glob("*.json"):
        # Skip non-numeric basenames (target.txt companion files have different pattern)
        stem = json_file.stem
        # Files may be named <chat_id>.json only
        try:
            chat_id = int(stem)
        except ValueError:
            log.info(f"  [mail] skipping non-chat_id file: {json_file.name}")
            continue

        try:
            creds = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning(f"  [mail] could not read {json_file}: {exc}")
            continue

        email = creds.get("email", "")
        if not email:
            log.info(f"  [mail] skipping {json_file.name} — no email field")
            continue

        provider = creds.get("provider", "custom")
        imap_host = creds.get("imap_host", "")
        imap_port = int(creds.get("imap_port", 993))
        plainpw = creds.get("app_password", "")
        password_enc = _fernet_encrypt(plainpw) if plainpw else ""

        # Read target email if present
        target_file = mail_dir / f"{chat_id}_target.txt"
        target_email = ""
        try:
            target_email = target_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            pass
        except Exception as exc:
            log.warning(f"  [mail] could not read target file: {exc}")

        log.info(f"  [mail] chat_id={chat_id} email={email!r} provider={provider!r}")
        if not dry_run:
            conn.execute(
                """
                INSERT OR REPLACE INTO mail_creds
                    (chat_id, provider, email, imap_host, imap_port,
                     password_enc, target_email, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (chat_id, provider, email, imap_host, imap_port, password_enc, target_email),
            )
        count += 1

    return count


def _migrate_tts_pending(conn: sqlite3.Connection, dry_run: bool) -> int:
    """pending_tts.json → tts_pending table.

    JSON format: {"<chat_id_str>": <msg_id_int>, ...}
    """
    tts_file = Path(_PENDING_TTS_FILE)
    if not tts_file.exists():
        log.info("[tts_pending] file not found — nothing to migrate")
        return 0

    try:
        data = json.loads(tts_file.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning(f"[tts_pending] could not read: {exc}")
        return 0

    count = 0
    for chat_id_str, msg_id in data.items():
        try:
            chat_id = int(chat_id_str)
            msg_id = int(msg_id)
        except (ValueError, TypeError):
            log.warning(f"  [tts_pending] skipping invalid entry {chat_id_str!r}={msg_id!r}")
            continue

        log.info(f"  [tts_pending] chat_id={chat_id} msg_id={msg_id}")
        if not dry_run:
            conn.execute(
                """
                INSERT OR IGNORE INTO tts_pending (chat_id, msg_id, created_at)
                VALUES (?, ?, datetime('now'))
                """,
                (chat_id, msg_id),
            )
        count += 1

    return count


# ============================================================
# Entry point
# ============================================================

def main() -> int:
    global DB_PATH
    parser = argparse.ArgumentParser(
        description="Migrate picoclaw JSON files → SQLite (pico.db). Idempotent.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be migrated without writing anything",
    )
    parser.add_argument(
        "--db", default=str(DB_PATH),
        help=f"Path to pico.db (default: {DB_PATH})",
    )
    args = parser.parse_args()

    DB_PATH = Path(args.db)

    mode = "DRY-RUN" if args.dry_run else "APPLY"
    log.info(f"=== picoclaw JSON → SQLite migration ({mode}) ===")
    log.info(f"    DB:          {DB_PATH}")
    log.info(f"    picoclaw dir: {_PICOCLAW_DIR}")

    if not DB_PATH.exists() and not args.dry_run:
        log.error(f"Database {DB_PATH} does not exist.  Run the bot once first so init_db() creates the schema.")
        return 1

    conn = _get_conn() if not args.dry_run else None  # type: ignore[assignment]

    try:
        results: dict[str, int] = {}

        log.info("\n--- Users & Registrations ---")
        results["users"] = _migrate_users(conn, args.dry_run)

        log.info("\n--- Voice Options ---")
        results["voice_opts"] = _migrate_voice_opts(conn, args.dry_run)

        log.info("\n--- Calendar Events ---")
        results["calendar_events"] = _migrate_calendar(conn, args.dry_run)

        log.info("\n--- Notes Index ---")
        results["notes_index"] = _migrate_notes_index(conn, args.dry_run)

        log.info("\n--- Mail Credentials ---")
        results["mail_creds"] = _migrate_mail_creds(conn, args.dry_run)

        log.info("\n--- Pending TTS ---")
        results["tts_pending"] = _migrate_tts_pending(conn, args.dry_run)

        if not args.dry_run and conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()

        # Summary table
        log.info("\n=== Migration Summary ===")
        log.info(f"{'Table':<25} {'Rows':>6}")
        log.info("-" * 33)
        for table, n in results.items():
            log.info(f"  {table:<23} {n:>6}")
        log.info("-" * 33)
        log.info(f"  {'TOTAL':<23} {sum(results.values()):>6}")
        log.info(
            f"\n{'[DRY-RUN — no data written]' if args.dry_run else '[Done — data written to pico.db]'}"
        )

    except Exception as exc:
        log.exception(f"Migration failed: {exc}")
        if conn:
            conn.close()
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
