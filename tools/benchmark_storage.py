"""
benchmark_storage.py — Taris storage backend benchmark

Compares JSON-file-based storage vs SQLite for the operations that the
taris Telegram bot actually performs.

COMPLETELY STANDALONE — zero imports from src/. Safe to run on Windows dev
machine (uses tempfile.mkdtemp() for all paths) and on the Pi target.

Usage:
  python tools/benchmark_storage.py
  python tools/benchmark_storage.py --iterations 500
  python tools/benchmark_storage.py --output tools/benchmark_results.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from datetime import datetime
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_N          = 1000   # iterations per operation group
DEFAULT_OUTPUT     = os.path.join(os.path.dirname(__file__), "benchmark_results.json")

# ─────────────────────────────────────────────────────────────────────────────
# SQLite schema (mirrors bot_db.py exactly)
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS registrations (
    chat_id     INTEGER PRIMARY KEY,
    username    TEXT    DEFAULT '',
    first_name  TEXT    DEFAULT '',
    last_name   TEXT    DEFAULT '',
    name        TEXT    DEFAULT '',
    timestamp   TEXT    DEFAULT '',
    status      TEXT    DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS notes (
    chat_id  INTEGER NOT NULL,
    slug     TEXT    NOT NULL,
    title    TEXT    DEFAULT '',
    content  TEXT    DEFAULT '',
    mtime    REAL    DEFAULT 0.0,
    PRIMARY KEY (chat_id, slug)
);
CREATE TABLE IF NOT EXISTS calendar_events (
    id                TEXT    NOT NULL,
    chat_id           INTEGER NOT NULL,
    title             TEXT    DEFAULT '',
    dt_iso            TEXT    DEFAULT '',
    remind_before_min INTEGER DEFAULT 15,
    reminded          INTEGER DEFAULT 0,
    PRIMARY KEY (id, chat_id)
);
CREATE TABLE IF NOT EXISTS mail_creds (
    chat_id      INTEGER PRIMARY KEY,
    provider     TEXT    DEFAULT '',
    email        TEXT    DEFAULT '',
    app_password TEXT    DEFAULT '',
    imap_host    TEXT    DEFAULT '',
    imap_port    INTEGER DEFAULT 993,
    spam_folder  TEXT    DEFAULT '[Gmail]/Spam',
    last_digest  TEXT    DEFAULT ''
);
CREATE TABLE IF NOT EXISTS voice_opts (
    id                  INTEGER PRIMARY KEY CHECK(id=1),
    silence_strip       INTEGER DEFAULT 0,
    low_sample_rate     INTEGER DEFAULT 0,
    warm_piper          INTEGER DEFAULT 0,
    parallel_tts        INTEGER DEFAULT 0,
    user_audio_toggle   INTEGER DEFAULT 0,
    tmpfs_model         INTEGER DEFAULT 0,
    vad_prefilter       INTEGER DEFAULT 0,
    whisper_stt         INTEGER DEFAULT 0,
    vosk_fallback       INTEGER DEFAULT 1,
    piper_low_model     INTEGER DEFAULT 0,
    persistent_piper    INTEGER DEFAULT 0,
    voice_timing_debug  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS guest_users (
    chat_id INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);
"""

_VOICE_OPTS_KEYS = [
    "silence_strip", "low_sample_rate", "warm_piper", "parallel_tts",
    "user_audio_toggle", "tmpfs_model", "vad_prefilter", "whisper_stt",
    "vosk_fallback", "piper_low_model", "persistent_piper", "voice_timing_debug",
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_userdir(base: str, chat_id: int) -> str:
    d = os.path.join(base, str(chat_id))
    os.makedirs(d, exist_ok=True)
    return d

def _slug(title: str) -> str:
    import re
    return re.sub(r"[^a-z0-9_]+", "_", title.lower())[:60].strip("_")


# ─────────────────────────────────────────────────────────────────────────────
# Timer
# ─────────────────────────────────────────────────────────────────────────────

class Timer:
    def __init__(self) -> None:
        self.elapsed = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        self.elapsed = time.perf_counter() - self._start


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark categories
# ─────────────────────────────────────────────────────────────────────────────

class BenchmarkSuite:
    def __init__(self, n: int, tmpdir: str) -> None:
        self.n       = n
        self.tmpdir  = tmpdir
        self.results: list[dict] = []

    # ── internal helpers ──────────────────────────────────────────────────────

    def _open_db(self, path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO voice_opts(id, vosk_fallback) VALUES(1,1)"
        )
        conn.commit()
        return conn

    def _record(self, name: str, file_s: float, db_s: float) -> None:
        ratio = db_s / file_s if file_s > 0 else float("inf")
        self.results.append(
            {
                "name":        name,
                "file_us":     round(file_s * 1e6 / self.n, 2),
                "db_us":       round(db_s  * 1e6 / self.n, 2),
                "ratio":       round(ratio, 3),
                "faster":      "file" if file_s < db_s else "db",
            }
        )

    # ── 1. Registrations ─────────────────────────────────────────────────────

    def bench_registrations(self) -> None:
        print("  [1] registrations …", end="", flush=True)
        n = self.n

        # ── file ──────────────────────────────────────────────────────────────
        reg_file = os.path.join(self.tmpdir, "registrations.json")
        with Timer() as t_file:
            for i in range(n):
                cid = i + 1
                record = {
                    "chat_id": cid, "username": f"u{cid}",
                    "first_name": "Test", "last_name": "User",
                    "name": f"Test User {cid}",
                    "timestamp": datetime.now().isoformat(),
                    "status": "pending",
                }
                # load
                regs = json.loads(open(reg_file).read()) if os.path.exists(reg_file) else []
                # upsert
                regs = [r for r in regs if r.get("chat_id") != cid]
                regs.append(record)
                # save
                with open(reg_file, "w", encoding="utf-8") as f:
                    json.dump(regs, f)

        # ── SQLite ────────────────────────────────────────────────────────────
        db_path = os.path.join(self.tmpdir, "bench_reg.db")
        conn = self._open_db(db_path)
        with Timer() as t_db:
            for i in range(n):
                cid = i + 1
                conn.execute(
                    """INSERT INTO registrations(chat_id,username,first_name,last_name,name,timestamp,status)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(chat_id) DO UPDATE SET
                         username=excluded.username, first_name=excluded.first_name,
                         last_name=excluded.last_name, name=excluded.name,
                         timestamp=excluded.timestamp, status=excluded.status""",
                    (cid, f"u{cid}", "Test", "User", f"Test User {cid}",
                     datetime.now().isoformat(), "pending"),
                )
            conn.commit()
        conn.close()
        print(" done")
        self._record("registrations upsert", t_file.elapsed, t_db.elapsed)

    # ── 2. Registration lookup by chat_id ─────────────────────────────────────

    def bench_reg_lookup(self) -> None:
        print("  [2] registration lookup …", end="", flush=True)
        n = self.n

        # prepare file
        reg_file = os.path.join(self.tmpdir, "reg_lookup.json")
        entries = [
            {"chat_id": i + 1, "username": f"u{i+1}", "first_name": "T",
             "last_name": "U", "name": f"U{i+1}",
             "timestamp": datetime.now().isoformat(), "status": "approved"}
            for i in range(n)
        ]
        with open(reg_file, "w") as f:
            json.dump(entries, f)

        # prepare db
        db_path = os.path.join(self.tmpdir, "bench_reg_lookup.db")
        conn = self._open_db(db_path)
        conn.executemany(
            "INSERT OR IGNORE INTO registrations(chat_id,username,first_name,last_name,name,timestamp,status) VALUES(?,?,?,?,?,?,?)",
            [(e["chat_id"], e["username"], e["first_name"], e["last_name"],
              e["name"], e["timestamp"], e["status"]) for e in entries],
        )
        conn.commit()

        # ── file ──────────────────────────────────────────────────────────────
        with Timer() as t_file:
            for i in range(n):
                cid = (i % n) + 1
                regs = json.loads(open(reg_file).read())
                _ = next((r for r in regs if r["chat_id"] == cid), None)

        # ── SQLite ────────────────────────────────────────────────────────────
        with Timer() as t_db:
            for i in range(n):
                cid = (i % n) + 1
                _ = conn.execute(
                    "SELECT * FROM registrations WHERE chat_id=?", (cid,)
                ).fetchone()
        conn.close()
        print(" done")
        self._record("registration lookup", t_file.elapsed, t_db.elapsed)

    # ── 3. Calendar events batch save ────────────────────────────────────────

    def bench_calendar(self) -> None:
        print("  [3] calendar events (batch save) …", end="", flush=True)
        n    = self.n
        cid  = 99999
        evts = [
            {
                "id":                uuid.uuid4().hex[:8],
                "title":             f"Event {j}",
                "dt_iso":            "2026-06-01T10:00",
                "remind_before_min": 15,
                "reminded":          False,
            }
            for j in range(10)        # 10 events per user — realistic size
        ]

        # ── file ──────────────────────────────────────────────────────────────
        cal_dir  = os.path.join(self.tmpdir, "calendar")
        os.makedirs(cal_dir, exist_ok=True)
        cal_file = os.path.join(cal_dir, f"{cid}.json")
        with Timer() as t_file:
            for _ in range(n):
                with open(cal_file, "w", encoding="utf-8") as f:
                    json.dump(evts, f, ensure_ascii=False)
                _ = json.loads(open(cal_file).read())

        # ── SQLite ────────────────────────────────────────────────────────────
        db_path = os.path.join(self.tmpdir, "bench_cal.db")
        conn = self._open_db(db_path)
        with Timer() as t_db:
            for _ in range(n):
                conn.execute("DELETE FROM calendar_events WHERE chat_id=?", (cid,))
                conn.executemany(
                    """INSERT INTO calendar_events(id,chat_id,title,dt_iso,remind_before_min,reminded)
                       VALUES(?,?,?,?,?,?)""",
                    [(e["id"], cid, e["title"], e["dt_iso"],
                      e["remind_before_min"], int(e["reminded"])) for e in evts],
                )
                conn.commit()
                _ = conn.execute(
                    "SELECT * FROM calendar_events WHERE chat_id=?", (cid,)
                ).fetchall()
        conn.close()
        print(" done")
        self._record("calendar batch save+load", t_file.elapsed, t_db.elapsed)

    # ── 4. Voice opts roundtrip ───────────────────────────────────────────────

    def bench_voice_opts(self) -> None:
        print("  [4] voice opts roundtrip …", end="", flush=True)
        n     = self.n
        flags = {k: False for k in _VOICE_OPTS_KEYS}
        flags["vosk_fallback"] = True

        # ── file ──────────────────────────────────────────────────────────────
        opts_file = os.path.join(self.tmpdir, "voice_opts.json")
        with Timer() as t_file:
            for i in range(n):
                # toggle one flag
                key            = _VOICE_OPTS_KEYS[i % len(_VOICE_OPTS_KEYS)]
                flags[key]     = not flags[key]
                with open(opts_file, "w", encoding="utf-8") as f:
                    json.dump(flags, f)
                loaded = json.loads(open(opts_file).read())
                _ = loaded.get("vosk_fallback", True)

        # ── SQLite ────────────────────────────────────────────────────────────
        db_path = os.path.join(self.tmpdir, "bench_vo.db")
        conn = self._open_db(db_path)
        with Timer() as t_db:
            for i in range(n):
                key        = _VOICE_OPTS_KEYS[i % len(_VOICE_OPTS_KEYS)]
                flags[key] = not flags[key]
                set_clause = ", ".join(f"{k}=?" for k in _VOICE_OPTS_KEYS)
                vals       = [int(flags[k]) for k in _VOICE_OPTS_KEYS]
                conn.execute(
                    f"UPDATE voice_opts SET {set_clause} WHERE id=1", vals
                )
                conn.commit()
                row  = conn.execute("SELECT * FROM voice_opts WHERE id=1").fetchone()
                _    = dict(row)
        conn.close()
        print(" done")
        self._record("voice opts roundtrip", t_file.elapsed, t_db.elapsed)

    # ── 5. Guest users set ───────────────────────────────────────────────────

    def bench_guest_users(self) -> None:
        print("  [5] guest users set save+load …", end="", flush=True)
        n     = self.n
        users: set[int] = set(range(1000, 1000 + min(n, 50)))  # up to 50 guests

        # ── file ──────────────────────────────────────────────────────────────
        users_file = os.path.join(self.tmpdir, "users.json")
        with Timer() as t_file:
            for i in range(n):
                # add/remove one user
                uid = 1000 + (i % 50)
                if uid in users:
                    users.discard(uid)
                else:
                    users.add(uid)
                with open(users_file, "w", encoding="utf-8") as f:
                    json.dump({"users": sorted(users)}, f)
                loaded = set(json.loads(open(users_file).read()).get("users", []))
                _ = len(loaded)

        # ── SQLite ────────────────────────────────────────────────────────────
        db_path = os.path.join(self.tmpdir, "bench_gu.db")
        conn = self._open_db(db_path)
        with Timer() as t_db:
            for i in range(n):
                uid = 1000 + (i % 50)
                if uid in users:
                    users.discard(uid)
                else:
                    users.add(uid)
                conn.execute("DELETE FROM guest_users")
                conn.executemany(
                    "INSERT OR IGNORE INTO guest_users(chat_id) VALUES(?)",
                    [(u,) for u in sorted(users)],
                )
                conn.commit()
                rows  = conn.execute("SELECT chat_id FROM guest_users").fetchall()
                _ = set(r[0] for r in rows)
        conn.close()
        print(" done")
        self._record("guest users set", t_file.elapsed, t_db.elapsed)

    # ── 6. Notes upsert ──────────────────────────────────────────────────────

    def bench_notes(self) -> None:
        print("  [6] notes upsert …", end="", flush=True)
        n   = self.n
        cid = 77777

        # ── file ──────────────────────────────────────────────────────────────
        note_dir = os.path.join(self.tmpdir, "notes", str(cid))
        os.makedirs(note_dir, exist_ok=True)
        with Timer() as t_file:
            for i in range(n):
                title   = f"Note {i % 20}"
                slug    = _slug(title)
                content = f"Content of note {i} with some text."
                fpath   = os.path.join(note_dir, f"{slug}.md")
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(f"# {title}\n\n{content}")
                _ = open(fpath, encoding="utf-8").read()

        # ── SQLite ────────────────────────────────────────────────────────────
        db_path = os.path.join(self.tmpdir, "bench_notes.db")
        conn = self._open_db(db_path)
        with Timer() as t_db:
            for i in range(n):
                title   = f"Note {i % 20}"
                slug    = _slug(title)
                content = f"Content of note {i} with some text."
                conn.execute(
                    """INSERT INTO notes(chat_id,slug,title,content,mtime)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(chat_id,slug) DO UPDATE SET
                         title=excluded.title, content=excluded.content, mtime=excluded.mtime""",
                    (cid, slug, title, content, time.time()),
                )
                conn.commit()
                _ = conn.execute(
                    "SELECT * FROM notes WHERE chat_id=? AND slug=?", (cid, slug)
                ).fetchone()
        conn.close()
        print(" done")
        self._record("notes upsert+load", t_file.elapsed, t_db.elapsed)

    # ─────────────────────────────────────────────────────────────────────────
    # Runner
    # ─────────────────────────────────────────────────────────────────────────

    def run_all(self) -> None:
        self.bench_registrations()
        self.bench_reg_lookup()
        self.bench_calendar()
        self.bench_voice_opts()
        self.bench_guest_users()
        self.bench_notes()


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def _verdict(ratio: float, faster: str) -> str:
    if faster == "db":
        pct = (1 - ratio) * 100 if ratio < 1 else (ratio - 1) * 100
        if ratio <= 0.5:
            return f"DB {pct:.0f}% faster ✓✓"
        return f"DB  {pct:.0f}% faster ✓"
    else:
        pct = (1 / ratio - 1) * 100 if ratio > 1 else (1 - ratio) * 100
        if ratio >= 2.0:
            return f"File {(ratio-1)*100:.0f}% faster !"
        return f"File {(ratio-1)*100:.0f}% faster"


def print_report(results: list[dict], n: int) -> None:
    col_w = [38, 11, 11, 9, 28]
    header = ["Operation", "File µs", "SQLite µs", "Ratio", "Verdict"]
    sep    = "+" + "+".join("-" * (w + 2) for w in col_w) + "+"
    fmt    = "| " + " | ".join(f"{{:<{w}}}" for w in col_w) + " |"

    print()
    print(f"  Benchmark results — N={n} iterations per operation")
    print(sep)
    print(fmt.format(*header))
    print(sep)
    for r in results:
        verdict = _verdict(r["ratio"], r["faster"])
        print(fmt.format(
            r["name"],
            f"{r['file_us']:.1f}",
            f"{r['db_us']:.1f}",
            f"{r['ratio']:.3f}",
            verdict,
        ))
    print(sep)

    # summary
    db_wins  = sum(1 for r in results if r["faster"] == "db")
    fil_wins = len(results) - db_wins
    print(f"\n  Summary: SQLite faster in {db_wins}/{len(results)} operations, "
          f"File faster in {fil_wins}/{len(results)} operations.")
    print()
    print("  Interpretation:")
    print("   ratio < 1  → SQLite is faster (lower is better for DB)")
    print("   ratio > 1  → File is faster (higher means DB is slower)")
    print("   For high-frequency ops (voice_opts, guest users), DB overhead matters most.")
    print("   For lookup-heavy ops (registration lookup), SQLite PRIMARY KEY shines.")
    print()


def save_json(results: list[dict], n: int, path: str) -> None:
    payload = {
        "timestamp": datetime.now().isoformat(),
        "n_iterations": n,
        "platform": {"os": os.name, "cpu_count": os.cpu_count()},
        "results": results,
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  Results saved → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Taris storage benchmark")
    parser.add_argument("--iterations", "-n", type=int, default=DEFAULT_N,
                        help=f"Iterations per operation (default: {DEFAULT_N})")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT,
                        help=f"JSON output path (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    tmpdir = tempfile.mkdtemp(prefix="picobench_")
    print(f"\nTaris storage benchmark — {args.iterations} iterations")
    print(f"  Temp dir: {tmpdir}")
    print()

    suite = BenchmarkSuite(n=args.iterations, tmpdir=tmpdir)
    try:
        suite.run_all()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print_report(suite.results, args.iterations)
    save_json(suite.results, args.iterations, args.output)


if __name__ == "__main__":
    main()
