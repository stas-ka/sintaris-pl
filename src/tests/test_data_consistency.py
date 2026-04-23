#!/usr/bin/env python3
"""
test_data_consistency.py — Data integrity checks for all taris user data.

Verifies consistency across all data domains for every registered user:
  • users        – valid role/language, non-empty identifier
  • notes        – index ↔ filesystem sync, non-null slugs/titles
  • calendar     – ISO-8601 datetimes, non-empty titles
  • contacts     – non-empty names, basic email format
  • documents    – non-empty titles, file presence when file_path is set
  • conversation – valid message roles, non-empty content, summary tiers
  • prefs        – all user_prefs/voice_opts reference registered users

Run BEFORE a data backup or AFTER a data migration:
    python3 src/tests/test_data_consistency.py
    python3 src/tests/test_data_consistency.py --chat-id 12345
    python3 src/tests/test_data_consistency.py --verbose
    python3 src/tests/test_data_consistency.py --fix     # repair minor issues
    python3 src/tests/test_data_consistency.py --json    # machine-readable output

Exit codes:
    0  all checks passed (zero ERRORs, zero WARNs — or only INFO)
    1  one or more ERRORs or WARNs found
    2  test runner error (DB connection failure, missing config)

Deploy path: ~/.taris/tests/test_data_consistency.py
Run on target:
    python3 ~/.taris/tests/test_data_consistency.py
"""

from __future__ import annotations

import argparse
import json as _json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap — env loading (mirrors bot_config._load_env_file, no bot imports)
# ─────────────────────────────────────────────────────────────────────────────

TARIS_DIR = Path(os.environ.get("TARIS_HOME") or Path.home() / ".taris")


def _load_env(path: Path) -> None:
    """Load KEY=VALUE pairs into os.environ (skip comments, no overwrite)."""
    try:
        with open(path) as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


_load_env(TARIS_DIR / "bot.env")
_load_env(TARIS_DIR / ".taris_env")

BACKEND = os.environ.get("STORE_BACKEND", "sqlite").lower()
NOTES_DIR = Path(os.environ.get("NOTES_DIR") or str(TARIS_DIR / "notes"))
DB_PATH = Path(os.environ.get("DB_PATH") or str(TARIS_DIR / "taris.db"))
PG_DSN = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL", "")

# ── Valid domain values (mirrors bot_admin.py / store_base.py) ───────────────
_VALID_ROLES = {"pending", "guest", "user", "advanced", "admin", "developer", "owner"}
_VALID_LANGUAGES = {"ru", "en", "de"}
_VALID_HISTORY_ROLES = {"user", "assistant", "system"}
_VALID_SUMMARY_TIERS = {"short", "mid", "long"}
# Basic email pattern — not RFC-strict, just catches obviously broken values
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SLUG_RE = re.compile(r"^[a-z0-9_\-]+$")  # acceptable slug characters

# ─────────────────────────────────────────────────────────────────────────────
# Issue dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Issue:
    domain: str       # profile | notes | calendar | contacts | documents | conversation | prefs | global
    chat_id: int      # 0 = global / cross-user
    severity: str     # ERROR | WARN | INFO
    message: str
    fixable: bool = False

    def __str__(self) -> str:
        who = f"user={self.chat_id}" if self.chat_id else "global"
        fix = " [fixable]" if self.fixable else ""
        return f"[{self.severity}] [{self.domain}] {who}: {self.message}{fix}"


# ─────────────────────────────────────────────────────────────────────────────
# DB wrapper — normalises SQLite / PostgreSQL differences
# ─────────────────────────────────────────────────────────────────────────────

class DB:
    """Minimal read-only query wrapper; normalises placeholder syntax."""

    def __init__(self) -> None:
        if BACKEND == "postgres":
            self._conn = self._connect_postgres()
            self._ph = "%s"
        else:
            self._conn = self._connect_sqlite()
            self._ph = "?"

    # ── Connection ────────────────────────────────────────────────────────────

    def _connect_sqlite(self) -> Any:
        import sqlite3
        if not DB_PATH.exists():
            raise FileNotFoundError(f"SQLite DB not found: {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_postgres(self) -> Any:
        if not PG_DSN:
            raise ValueError(
                "POSTGRES_DSN or DATABASE_URL must be set in bot.env "
                "for the PostgreSQL backend"
            )
        try:
            import psycopg
            from psycopg.rows import dict_row
            return psycopg.connect(PG_DSN, row_factory=dict_row)
        except ImportError:
            pass
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(PG_DSN)
            conn.cursor_factory = psycopg2.extras.RealDictCursor
            return conn
        except ImportError as exc:
            raise ImportError(
                "Install psycopg[binary] or psycopg2-binary for PostgreSQL checks"
            ) from exc

    # ── Query helpers ─────────────────────────────────────────────────────────

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self._conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], dict):
            return list(rows)
        return [dict(r) for r in rows]

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self.fetchall(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: tuple = ()) -> Any:
        row = self.fetchone(sql, params)
        return None if row is None else next(iter(row.values()))

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Execute a write statement (used by --fix only)."""
        cur = self._conn.cursor()
        cur.execute(sql, params)
        self._conn.commit()

    def table_exists(self, name: str) -> bool:
        if BACKEND == "postgres":
            r = self.scalar(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=%s", (name,)
            )
        else:
            r = self.scalar(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (name,)
            )
        return bool(r)

    def ph(self) -> str:
        return self._ph

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Check helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_valid_iso(dt_str: str) -> bool:
    """Return True if dt_str is parseable as an ISO 8601 datetime."""
    if not dt_str:
        return False
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            datetime.strptime(dt_str[:19], fmt[:len(fmt.replace("%z","").replace("Z",""))])
            return True
        except ValueError:
            continue
    return False


def _note_file(chat_id: int, slug: str) -> Path:
    return NOTES_DIR / str(chat_id) / f"{slug}.md"


# ─────────────────────────────────────────────────────────────────────────────
# Domain check functions — each yields Issue objects
# ─────────────────────────────────────────────────────────────────────────────

def check_profile(db: DB, user_ids: list[int]) -> Iterator[Issue]:
    """Users table: valid roles, languages, non-empty identifier."""
    ph = db.ph()
    for uid in user_ids:
        row = db.fetchone(f"SELECT * FROM users WHERE chat_id = {ph}", (uid,))
        if not row:
            yield Issue("profile", uid, "ERROR", "user row missing from users table")
            continue

        role = (row.get("role") or "").strip()
        if role not in _VALID_ROLES:
            yield Issue("profile", uid, "ERROR",
                        f"invalid role '{role}' (valid: {sorted(_VALID_ROLES)})")

        lang = (row.get("language") or "").strip()
        if lang and lang not in _VALID_LANGUAGES:
            yield Issue("profile", uid, "WARN",
                        f"unknown language '{lang}' (valid: {sorted(_VALID_LANGUAGES)})")

        name = (row.get("name") or "").strip()
        username = (row.get("username") or "").strip()
        if not name and not username:
            yield Issue("profile", uid, "WARN",
                        "both name and username are empty — user has no display identifier")

        if (row.get("chat_id") or 0) <= 0:
            yield Issue("profile", uid, "ERROR", "chat_id is not a positive integer")


def check_notes(db: DB, user_ids: list[int], verbose: bool = False) -> Iterator[Issue]:
    """notes_index: slugs, titles, DB↔filesystem sync."""
    if not db.table_exists("notes_index"):
        return
    ph = db.ph()

    for uid in user_ids:
        rows = db.fetchall(
            f"SELECT slug, title, content FROM notes_index WHERE chat_id = {ph}",
            (uid,),
        )
        index_slugs: set[str] = set()

        for r in rows:
            slug = (r.get("slug") or "").strip()
            title = (r.get("title") or "").strip()
            content_in_db = (r.get("content") or "").strip()

            if not slug:
                yield Issue("notes", uid, "ERROR", "notes_index row with empty slug")
                continue
            index_slugs.add(slug)

            if not title:
                yield Issue("notes", uid, "WARN", f"note '{slug}' has empty title")

            if not _SLUG_RE.match(slug):
                yield Issue("notes", uid, "WARN",
                            f"note slug '{slug}' contains unexpected characters")

            # File presence check (SQLite target where files are on disk)
            fpath = _note_file(uid, slug)
            if NOTES_DIR.exists():
                if not fpath.exists():
                    if content_in_db:
                        # Content is safe in DB, file is just missing
                        yield Issue("notes", uid, "WARN",
                                    f"note '{slug}' has no .md file but content is in DB",
                                    fixable=True)
                    else:
                        yield Issue("notes", uid, "ERROR",
                                    f"note '{slug}' has no .md file and no content in DB — data may be lost")

        # Orphaned .md files — exist on filesystem but not in index
        if NOTES_DIR.exists():
            user_note_dir = NOTES_DIR / str(uid)
            if user_note_dir.exists():
                for fpath in user_note_dir.glob("*.md"):
                    slug = fpath.stem
                    if slug not in index_slugs:
                        yield Issue("notes", uid, "WARN",
                                    f"orphaned note file '{fpath.name}' has no notes_index entry",
                                    fixable=True)


def check_calendar(db: DB, user_ids: list[int]) -> Iterator[Issue]:
    """calendar_events: non-empty titles, valid ISO datetimes."""
    if not db.table_exists("calendar_events"):
        return
    ph = db.ph()

    for uid in user_ids:
        rows = db.fetchall(
            f"SELECT id, title, dt_iso FROM calendar_events WHERE chat_id = {ph}",
            (uid,),
        )
        seen_ids: set[str] = set()

        for r in rows:
            ev_id = (r.get("id") or "").strip()
            title = (r.get("title") or "").strip()
            dt_iso = (r.get("dt_iso") or "").strip()

            if not ev_id:
                yield Issue("calendar", uid, "ERROR", "calendar event with empty id")

            if ev_id in seen_ids:
                yield Issue("calendar", uid, "ERROR",
                            f"duplicate calendar event id '{ev_id}'")
            seen_ids.add(ev_id)

            if not title:
                yield Issue("calendar", uid, "WARN",
                            f"calendar event '{ev_id}' has empty title")

            if not dt_iso:
                yield Issue("calendar", uid, "ERROR",
                            f"calendar event '{ev_id}' ('{title}') has empty dt_iso")
            elif not _is_valid_iso(dt_iso):
                yield Issue("calendar", uid, "ERROR",
                            f"calendar event '{ev_id}' has unparseable dt_iso: '{dt_iso}'")


def check_contacts(db: DB, user_ids: list[int]) -> Iterator[Issue]:
    """contacts: non-empty names, valid IDs, email format."""
    if not db.table_exists("contacts"):
        return
    ph = db.ph()

    for uid in user_ids:
        rows = db.fetchall(
            f"SELECT id, name, email FROM contacts WHERE chat_id = {ph}",
            (uid,),
        )
        for r in rows:
            cid = (r.get("id") or "").strip()
            name = (r.get("name") or "").strip()
            email = (r.get("email") or "").strip()

            if not cid:
                yield Issue("contacts", uid, "ERROR", "contact with empty id")

            if not name:
                yield Issue("contacts", uid, "ERROR",
                            f"contact '{cid}' has empty name")

            if email and not _EMAIL_RE.match(email):
                yield Issue("contacts", uid, "WARN",
                            f"contact '{name}' has malformed email: '{email}'")


def check_documents(db: DB, user_ids: list[int]) -> Iterator[Issue]:
    """documents: non-empty title/id, file presence when file_path is set."""
    if not db.table_exists("documents"):
        return
    ph = db.ph()

    for uid in user_ids:
        rows = db.fetchall(
            f"SELECT doc_id, title, file_path FROM documents WHERE chat_id = {ph}",
            (uid,),
        )
        for r in rows:
            doc_id = (r.get("doc_id") or "").strip()
            title = (r.get("title") or "").strip()
            file_path = (r.get("file_path") or "").strip()

            if not doc_id:
                yield Issue("documents", uid, "ERROR", "document with empty doc_id")

            if not title:
                yield Issue("documents", uid, "WARN",
                            f"document '{doc_id}' has empty title")

            if file_path and not Path(file_path).exists():
                yield Issue("documents", uid, "WARN",
                            f"document '{title}' references missing file: '{file_path}'")


def check_conversation(db: DB, user_ids: list[int]) -> Iterator[Issue]:
    """chat_history and conversation_summaries: valid roles, non-empty content."""
    ph = db.ph()

    if db.table_exists("chat_history"):
        for uid in user_ids:
            rows = db.fetchall(
                f"SELECT id, role, content FROM chat_history WHERE chat_id = {ph}",
                (uid,),
            )
            for r in rows:
                role = (r.get("role") or "").strip()
                content = (r.get("content") or "").strip()
                row_id = r.get("id", "?")

                if role not in _VALID_HISTORY_ROLES:
                    yield Issue("conversation", uid, "ERROR",
                                f"chat_history row {row_id} has invalid role '{role}'")

                if not content:
                    yield Issue("conversation", uid, "WARN",
                                f"chat_history row {row_id} has empty content (role='{role}')")

    if db.table_exists("conversation_summaries"):
        for uid in user_ids:
            rows = db.fetchall(
                f"SELECT id, summary, tier FROM conversation_summaries "
                f"WHERE chat_id = {ph}",
                (uid,),
            )
            for r in rows:
                row_id = r.get("id", "?")
                summary = (r.get("summary") or "").strip()
                tier = (r.get("tier") or "").strip()

                if not summary:
                    yield Issue("conversation", uid, "WARN",
                                f"conversation_summaries row {row_id} has empty summary")

                if tier and tier not in _VALID_SUMMARY_TIERS:
                    yield Issue("conversation", uid, "WARN",
                                f"conversation_summaries row {row_id} has unknown tier '{tier}'")


def check_prefs(db: DB, user_ids: list[int]) -> Iterator[Issue]:
    """user_prefs and voice_opts: all rows reference registered users."""
    ph = db.ph()
    uid_set = set(user_ids)

    if db.table_exists("user_prefs"):
        pref_ids = {
            r["chat_id"]
            for r in db.fetchall("SELECT DISTINCT chat_id FROM user_prefs")
        }
        for cid in pref_ids - uid_set:
            yield Issue("prefs", cid, "WARN",
                        f"user_prefs has rows for unregistered chat_id={cid}",
                        fixable=True)

    if db.table_exists("voice_opts"):
        vo_ids = {
            r["chat_id"]
            for r in db.fetchall("SELECT DISTINCT chat_id FROM voice_opts")
        }
        for cid in vo_ids - uid_set:
            yield Issue("prefs", cid, "WARN",
                        f"voice_opts has rows for unregistered chat_id={cid}",
                        fixable=True)


def check_global_orphans(db: DB, user_ids: list[int]) -> Iterator[Issue]:
    """Cross-table: detect rows in data tables whose chat_id has no users entry."""
    uid_set = set(user_ids)
    ph = db.ph()

    for table, label in [
        ("notes_index", "notes"),
        ("calendar_events", "calendar"),
        ("contacts", "contacts"),
        ("documents", "documents"),
        ("chat_history", "conversation"),
    ]:
        if not db.table_exists(table):
            continue
        rows = db.fetchall(f"SELECT DISTINCT chat_id FROM {table}")
        for r in rows:
            cid = r.get("chat_id")
            if cid and cid not in uid_set:
                yield Issue("global", 0, "WARN",
                            f"{table}: {label} data for unregistered chat_id={cid}")


# ─────────────────────────────────────────────────────────────────────────────
# Auto-fix actions
# ─────────────────────────────────────────────────────────────────────────────

def fix_issues(db: DB, issues: list[Issue]) -> list[str]:
    """Apply safe auto-repairs for fixable issues. Returns list of actions taken."""
    actions: list[str] = []
    ph = db.ph()

    for issue in issues:
        if not issue.fixable:
            continue

        # Orphaned user_prefs rows
        if issue.domain == "prefs" and "user_prefs" in issue.message:
            db.execute(
                f"DELETE FROM user_prefs WHERE chat_id = {ph}",
                (issue.chat_id,),
            )
            actions.append(f"Deleted orphaned user_prefs rows for chat_id={issue.chat_id}")

        # Orphaned voice_opts rows
        elif issue.domain == "prefs" and "voice_opts" in issue.message:
            db.execute(
                f"DELETE FROM voice_opts WHERE chat_id = {ph}",
                (issue.chat_id,),
            )
            actions.append(f"Deleted orphaned voice_opts rows for chat_id={issue.chat_id}")

        # Orphaned .md files — safe to leave; only report as action taken
        elif issue.domain == "notes" and "orphaned note file" in issue.message:
            # Extract filename from message
            m = re.search(r"'([^']+\.md)'", issue.message)
            if m:
                fpath = NOTES_DIR / str(issue.chat_id) / m.group(1)
                actions.append(
                    f"[manual] Review orphaned file: {fpath} — delete manually if unwanted"
                )

    return actions


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_checks(
    db: DB,
    chat_id_filter: Optional[int],
    verbose: bool,
) -> list[Issue]:
    """Run all checks and return collected issues."""

    # Gather user IDs to check
    if chat_id_filter:
        if db.fetchone(
            f"SELECT 1 FROM users WHERE chat_id = {db.ph()}", (chat_id_filter,)
        ):
            user_ids = [chat_id_filter]
        else:
            print(f"[WARN] chat_id={chat_id_filter} not found in users table", file=sys.stderr)
            user_ids = [chat_id_filter]  # still run checks — may surface the reason
    else:
        rows = db.fetchall("SELECT chat_id FROM users ORDER BY chat_id")
        user_ids = [r["chat_id"] for r in rows]

    if not user_ids:
        print("[INFO] No users found in database.", file=sys.stderr)
        return []

    issues: list[Issue] = []

    checkers = [
        ("profile",      lambda: check_profile(db, user_ids)),
        ("notes",        lambda: check_notes(db, user_ids, verbose)),
        ("calendar",     lambda: check_calendar(db, user_ids)),
        ("contacts",     lambda: check_contacts(db, user_ids)),
        ("documents",    lambda: check_documents(db, user_ids)),
        ("conversation", lambda: check_conversation(db, user_ids)),
        ("prefs",        lambda: check_prefs(db, user_ids)),
    ]
    if not chat_id_filter:
        checkers.append(("global", lambda: check_global_orphans(db, user_ids)))

    for _name, fn in checkers:
        issues.extend(fn())

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def print_report(issues: list[Issue], verbose: bool, user_count: int) -> None:
    errors   = [i for i in issues if i.severity == "ERROR"]
    warnings = [i for i in issues if i.severity == "WARN"]
    infos    = [i for i in issues if i.severity == "INFO"]

    if not issues:
        print(f"✅  All checks passed — {user_count} user(s), 0 issues.")
        return

    # Group by user for readable output
    by_user: dict[int, list[Issue]] = {}
    for i in issues:
        by_user.setdefault(i.chat_id, []).append(i)

    for chat_id in sorted(by_user.keys()):
        label = f"user={chat_id}" if chat_id else "global"
        print(f"\n── {label} ──")
        for issue in by_user[chat_id]:
            marker = "🔴" if issue.severity == "ERROR" else ("🟡" if issue.severity == "WARN" else "🔵")
            fix_tag = " [fixable with --fix]" if issue.fixable else ""
            print(f"  {marker} [{issue.domain}] {issue.message}{fix_tag}")

    print()
    print(f"{'─'*60}")
    print(f"Users checked : {user_count}")
    print(f"Errors        : {len(errors)}")
    print(f"Warnings      : {len(warnings)}")
    print(f"Info          : {len(infos)}")
    fixable_count = sum(1 for i in issues if i.fixable)
    if fixable_count:
        print(f"Fixable       : {fixable_count}  (run with --fix to auto-repair)")


def print_json_report(issues: list[Issue], user_count: int) -> None:
    out = {
        "users_checked": user_count,
        "backend": BACKEND,
        "summary": {
            "errors":   sum(1 for i in issues if i.severity == "ERROR"),
            "warnings": sum(1 for i in issues if i.severity == "WARN"),
            "infos":    sum(1 for i in issues if i.severity == "INFO"),
        },
        "issues": [asdict(i) for i in issues],
    }
    print(_json.dumps(out, indent=2, ensure_ascii=False))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="taris data consistency check — run before backup or after migration"
    )
    parser.add_argument(
        "--chat-id", type=int, default=None,
        help="check only this user (default: all users)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="show per-file notes detail"
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="auto-repair fixable issues (orphaned prefs rows)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="output results as JSON (for CI / scripts)"
    )
    args = parser.parse_args()

    # ── Connect ───────────────────────────────────────────────────────────────
    try:
        db = DB()
    except Exception as exc:
        print(f"[FATAL] Cannot connect to database: {exc}", file=sys.stderr)
        return 2

    # ── Count total users ─────────────────────────────────────────────────────
    try:
        user_count = db.scalar("SELECT COUNT(*) FROM users") or 0
    except Exception as exc:
        print(f"[FATAL] Cannot query users table: {exc}", file=sys.stderr)
        db.close()
        return 2

    # ── Run checks ────────────────────────────────────────────────────────────
    try:
        issues = run_checks(db, args.chat_id, args.verbose)
    except Exception as exc:
        print(f"[FATAL] Check runner failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        db.close()
        return 2

    # ── Fix mode ──────────────────────────────────────────────────────────────
    if args.fix:
        actions = fix_issues(db, issues)
        if actions:
            print("── Auto-fix actions ──")
            for a in actions:
                print(f"  ✔  {a}")
            # Re-run checks after fixes to verify
            issues = run_checks(db, args.chat_id, args.verbose)
        else:
            print("[fix] No auto-fixable issues found.")

    db.close()

    # ── Report ────────────────────────────────────────────────────────────────
    if args.json:
        print_json_report(issues, user_count)
    else:
        print(f"\ntaris data consistency check — backend={BACKEND}, db={DB_PATH if BACKEND != 'postgres' else 'PostgreSQL'}")
        print_report(issues, args.verbose, user_count)

    # Exit code: 0=clean, 1=issues found
    has_problems = any(i.severity in ("ERROR", "WARN") for i in issues)
    return 1 if has_problems else 0


if __name__ == "__main__":
    sys.exit(main())
