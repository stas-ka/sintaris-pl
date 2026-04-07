#!/usr/bin/env python3
"""
migrate_sqlite_to_postgres.py — Migrate all taris data from SQLite to Postgres.

Designed for the OpenClaw variant where STORE_BACKEND=postgres.
Safe to run multiple times — uses upsert/INSERT OR IGNORE semantics.

Usage:
    STORE_BACKEND=postgres DATABASE_URL=<pg-url> \
    PYTHONPATH=src python3 src/setup/migrate_sqlite_to_postgres.py [--dry-run]
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

# ── Setup path ───────────────────────────────────────────────────────────────
SRC_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_ROOT))

TARIS_DIR = Path(os.environ.get("TARIS_DIR", Path.home() / ".taris"))
DB_PATH = TARIS_DIR / "taris.db"

import argparse

parser = argparse.ArgumentParser(description="Migrate taris SQLite → Postgres")
parser.add_argument("--dry-run", action="store_true", help="Read-only, no writes to Postgres")
args = parser.parse_args()

DRY_RUN = args.dry_run

# ── Init ─────────────────────────────────────────────────────────────────────
if not DB_PATH.exists():
    print(f"❌  SQLite DB not found: {DB_PATH}")
    sys.exit(1)

sq = sqlite3.connect(str(DB_PATH))
sq.row_factory = sqlite3.Row

from core.bot_config import log
from core.store import store as pg

print(f"{'[DRY-RUN] ' if DRY_RUN else ''}Migrating {DB_PATH} → Postgres")

migrated = {k: 0 for k in [
    "users", "calendar_events", "chat_history", "conversation_summaries",
    "documents", "contacts", "notes", "user_prefs", "security_events",
    "global_voice_opts", "llm_calls"
]}

# ── 1. Users ─────────────────────────────────────────────────────────────────
rows = sq.execute("SELECT * FROM users").fetchall()
print(f"  users: {len(rows)} rows")
_ALLOWED_USER_FIELDS = {"role", "username", "display_name", "language",
                        "is_approved", "status", "approved_by", "created_at"}
for r in rows:
    d = dict(r)
    chat_id = d.pop("chat_id")
    fields = {k: v for k, v in d.items() if k in _ALLOWED_USER_FIELDS and v is not None}
    if not DRY_RUN:
        try:
            pg.upsert_user(chat_id, **fields)
            migrated["users"] += 1
        except Exception as e:
            print(f"    ⚠️  user {chat_id}: {e}")
    else:
        migrated["users"] += 1

# ── 2. Calendar events ───────────────────────────────────────────────────────
rows = sq.execute("SELECT * FROM calendar_events").fetchall()
print(f"  calendar_events: {len(rows)} rows")
for r in rows:
    d = dict(r)
    chat_id = d.pop("chat_id", None)
    if chat_id is None:
        continue
    if not DRY_RUN:
        try:
            pg.save_event(chat_id, d)
            migrated["calendar_events"] += 1
        except Exception as e:
            print(f"    ⚠️  calendar {d.get('id')}: {e}")
    else:
        migrated["calendar_events"] += 1

# ── 3. Chat history ──────────────────────────────────────────────────────────
rows = sq.execute(
    "SELECT chat_id, role, content, call_id, created_at FROM chat_history ORDER BY id"
).fetchall()
print(f"  chat_history: {len(rows)} rows")
if not DRY_RUN:
    with pg._pool.connection() as conn:
        for r in rows:
            d = dict(r)
            try:
                conn.execute(
                    "INSERT INTO chat_history (chat_id, role, content, call_id, created_at)"
                    " VALUES (%s, %s, %s, %s, %s)"
                    " ON CONFLICT DO NOTHING",
                    (d["chat_id"], d["role"], d["content"],
                     d.get("call_id"), d.get("created_at")),
                )
                migrated["chat_history"] += 1
            except Exception as e:
                print(f"    ⚠️  history: {e}")
        conn.commit()
else:
    migrated["chat_history"] = len(rows)

# ── 4. Conversation summaries ────────────────────────────────────────────────
rows = sq.execute(
    "SELECT chat_id, tier, summary, msg_count, created_at FROM conversation_summaries ORDER BY id"
).fetchall()
print(f"  conversation_summaries: {len(rows)} rows")
if not DRY_RUN:
    with pg._pool.connection() as conn:
        for r in rows:
            d = dict(r)
            try:
                conn.execute(
                    "INSERT INTO conversation_summaries (chat_id, tier, summary, msg_count, created_at)"
                    " VALUES (%s, %s, %s, %s, %s)"
                    " ON CONFLICT DO NOTHING",
                    (d["chat_id"], d["tier"], d["summary"],
                     d.get("msg_count", 0), d.get("created_at")),
                )
                migrated["conversation_summaries"] += 1
            except Exception as e:
                print(f"    ⚠️  summary: {e}")
        conn.commit()
else:
    migrated["conversation_summaries"] = len(rows)

# ── 5. Documents ─────────────────────────────────────────────────────────────
rows = sq.execute(
    "SELECT doc_id, chat_id, title, file_path, doc_type, metadata, doc_hash FROM documents"
).fetchall()
print(f"  documents: {len(rows)} rows")
import json as _json
for r in rows:
    d = dict(r)
    if not DRY_RUN:
        try:
            meta = _json.loads(d["metadata"]) if d.get("metadata") else None
            pg.save_document_meta(
                d["doc_id"], d["chat_id"], d["title"] or "",
                d["file_path"] or "", d["doc_type"] or "file",
                metadata=meta, doc_hash=d.get("doc_hash"),
            )
            migrated["documents"] += 1
        except Exception as e:
            print(f"    ⚠️  document {d.get('doc_id')}: {e}")
    else:
        print(f"    [dry] doc chat_id={d['chat_id']} title={d['title']!r}")
        migrated["documents"] += 1

# ── 5b. Contacts ─────────────────────────────────────────────────────────────
_contacts_tbl = [r[1] for r in sq.execute("PRAGMA table_info(contacts)").fetchall()]
if _contacts_tbl:
    rows = sq.execute(
        "SELECT id, chat_id, name, phone, email, address, notes FROM contacts"
    ).fetchall()
    print(f"  contacts: {len(rows)} rows")
    for r in rows:
        d = dict(r)
        chat_id = d.pop("chat_id")
        if not DRY_RUN:
            try:
                d["id"] = d.get("id") or None
                pg.save_contact(chat_id, d)
                migrated["contacts"] += 1
            except Exception as e:
                print(f"    ⚠️  contact {d.get('name')}: {e}")
        else:
            print(f"    [dry] contact chat_id={chat_id} name={d.get('name')!r}")
            migrated["contacts"] += 1
else:
    print("  contacts: table not found — skipping")

# ── 6. Notes ─────────────────────────────────────────────────────────────────
# Migrate ALL notes — most notes on SintAItion have content in .md files, not SQLite.
# For empty-content rows: read content from ~/.taris/notes/<chat_id>/<slug>.md
rows = sq.execute(
    "SELECT chat_id, slug, title, content FROM notes_index"
).fetchall()
print(f"  notes_index: {len(rows)} rows")
_notes_dir = TARIS_DIR / "notes"
for r in rows:
    d = dict(r)
    content = d.get("content") or ""
    if not content:
        # Content lives in the .md file on disk — read it
        note_path = _notes_dir / str(d["chat_id"]) / f"{d['slug']}.md"
        if note_path.exists():
            try:
                content = note_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"    ⚠️  note file read {note_path}: {e}")
    if not DRY_RUN:
        try:
            pg.save_note(d["chat_id"], d["slug"], d["title"] or d["slug"], content)
            migrated["notes"] += 1
        except Exception as e:
            print(f"    ⚠️  note {d['slug']}: {e}")
    else:
        print(f"    [dry] note chat_id={d['chat_id']} slug={d['slug']!r} content_len={len(content)}")
        migrated["notes"] += 1

# ── 6. User prefs ────────────────────────────────────────────────────────────
rows = sq.execute("SELECT chat_id, key, value FROM user_prefs").fetchall()
print(f"  user_prefs: {len(rows)} rows")
for r in rows:
    d = dict(r)
    if not DRY_RUN:
        try:
            pg.set_user_pref(d["chat_id"], d["key"], str(d["value"]))
            migrated["user_prefs"] += 1
        except Exception as e:
            print(f"    ⚠️  pref {d['key']}: {e}")
    else:
        migrated["user_prefs"] += 1

# ── 7. Security events ───────────────────────────────────────────────────────
rows = sq.execute(
    "SELECT chat_id, event_type, detail, created_at FROM security_events"
).fetchall()
print(f"  security_events: {len(rows)} rows")
if not DRY_RUN:
    with pg._pool.connection() as conn:
        for r in rows:
            d = dict(r)
            try:
                conn.execute(
                    "INSERT INTO security_events (chat_id, event_type, detail, created_at)"
                    " VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (d.get("chat_id"), d.get("event_type", ""),
                     d.get("detail", ""), d.get("created_at")),
                )
                migrated["security_events"] += 1
            except Exception as e:
                print(f"    ⚠️  security_event: {e}")
        conn.commit()
else:
    migrated["security_events"] = len(rows)

# ── 8. Global voice opts ─────────────────────────────────────────────────────
rows = sq.execute("SELECT key, value FROM global_voice_opts").fetchall()
print(f"  global_voice_opts: {len(rows)} rows")
if not DRY_RUN:
    with pg._pool.connection() as conn:
        for r in rows:
            try:
                conn.execute(
                    "INSERT INTO global_voice_opts (key, value) VALUES (%s, %s)"
                    " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (r["key"], bool(r["value"])),
                )
                migrated["global_voice_opts"] += 1
            except Exception as e:
                print(f"    ⚠️  voice_opt {r['key']}: {e}")
        conn.commit()
else:
    migrated["global_voice_opts"] = len(rows)

# ── 9. LLM calls ─────────────────────────────────────────────────────────────
rows = sq.execute(
    "SELECT call_id, chat_id, provider, history_count, history_ids, prompt_chars,"
    " response_ok, model, temperature, system_chars, history_chars,"
    " rag_chunks_count, rag_context_chars, response_preview, context_snapshot,"
    " created_at"
    " FROM llm_calls ORDER BY created_at"
).fetchall()
print(f"  llm_calls: {len(rows)} rows")
if not DRY_RUN:
    with pg._pool.connection() as conn:
        for r in rows:
            d = dict(r)
            try:
                conn.execute(
                    "INSERT INTO llm_calls"
                    " (call_id, chat_id, provider, history_count, history_ids,"
                    "  prompt_chars, response_ok, model, temperature, system_chars,"
                    "  history_chars, rag_chunks_count, rag_context_chars,"
                    "  response_preview, context_snapshot, created_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    " ON CONFLICT (call_id) DO NOTHING",
                    (
                        d.get("call_id"), d.get("chat_id"), d.get("provider",""),
                        d.get("history_count", 0), d.get("history_ids","[]"),
                        d.get("prompt_chars", 0), bool(d.get("response_ok", 0)),
                        d.get("model",""), d.get("temperature", 0.0),
                        d.get("system_chars", 0), d.get("history_chars", 0),
                        d.get("rag_chunks_count", 0), d.get("rag_context_chars", 0),
                        d.get("response_preview","")[:300],
                        d.get("context_snapshot",""),
                        d.get("created_at"),
                    ),
                )
                migrated["llm_calls"] += 1
            except Exception as e:
                print(f"    ⚠️  llm_call {d.get('call_id')}: {e}")
        conn.commit()
else:
    migrated["llm_calls"] = len(rows)

# ── Summary ───────────────────────────────────────────────────────────────────
sq.close()
print()
print("─" * 50)
print(f"{'[DRY-RUN] ' if DRY_RUN else ''}Migration complete:")
for k, v in migrated.items():
    print(f"  {k:<30} {v:>5} rows migrated")
print("─" * 50)
if DRY_RUN:
    print("  (no data written — re-run without --dry-run to apply)")
