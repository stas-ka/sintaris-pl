#!/usr/bin/env python3
"""
benchmark_menus.py — Menu navigation performance benchmark for taris.

Simulates user-facing Telegram menu handler calls with no real network I/O.
All bot.send_message() / bot.edit_message_text() calls are replaced with no-ops.

Test cases:
  TC01  main_menu_keyboard (admin)      — pure computation, no I/O
  TC02  main_menu_keyboard (user)       — pure computation, no I/O
  TC03  send_menu                       — keyboard build + mocked send_message
  TC04  notes_submenu                   — no storage I/O
  TC05  notes_list — empty dir          — scan empty notes dir
  TC06  notes_list — 10 files           — read 10 .md filenames
  TC07  admin_menu                      — read registrations.json (badge count)
  TC08  admin_user_list                 — read all registrations
  TC09  calendar_menu — empty           — read empty/missing calendar JSON
  TC10  calendar_menu — 10 events       — read + parse 10-event calendar JSON
  TC11  contacts_menu — 0 contacts      — SQLite COUNT (empty)
  TC12  contacts_menu — 10 contacts     — SQLite COUNT (10 rows)
  TC13  contacts_list — 10 contacts     — SQLite SELECT + paginate

Run:
    python tools/benchmark_menus.py
    python tools/benchmark_menus.py --iterations 100
    python tools/benchmark_menus.py --outfile tools/my_results.json
"""

import argparse
import json
import os
import platform
import shutil
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

# ── Parse args early (before any imports that print to stderr) ────────────────
parser = argparse.ArgumentParser(description="Menu navigation benchmark")
parser.add_argument("--iterations", type=int, default=200, help="Iterations per test case")
parser.add_argument("--outfile", type=str, default=None, help="Override output JSON file path")
args = parser.parse_args()

N_ITER = args.iterations

# ── Test user IDs ─────────────────────────────────────────────────────────────
ADMIN_ID         = 11_111_111
USER_ID          = 22_222_222
NOTES_USER_EMPTY = 33_333_333
NOTES_USER_10    = 44_444_444
CAL_USER_EMPTY   = 55_555_555
CAL_USER_10      = 66_666_666
CONT_USER_EMPTY  = 77_777_777
CONT_USER_10     = 88_888_888

ALL_TEST_USERS = [
    ADMIN_ID, USER_ID,
    NOTES_USER_EMPTY, NOTES_USER_10,
    CAL_USER_EMPTY, CAL_USER_10,
    CONT_USER_EMPTY, CONT_USER_10,
]

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Create temp directory and set env vars BEFORE any src imports
# bot_config.py reads constants from os.environ at module import time.
# ══════════════════════════════════════════════════════════════════════════════
_TMPDIR      = tempfile.mkdtemp(prefix="taris_benchmenus_")
_NOTES_DIR   = os.path.join(_TMPDIR, "notes")
_CAL_DIR     = os.path.join(_TMPDIR, "calendar")
_REGS_FILE   = os.path.join(_TMPDIR, "registrations.json")
_USERS_FILE  = os.path.join(_TMPDIR, "users.json")
_DB_FILE     = os.path.join(_TMPDIR, "bench.db")

os.makedirs(_NOTES_DIR, exist_ok=True)
os.makedirs(_CAL_DIR, exist_ok=True)

# Seed empty state files so import-time loaders don't crash
with open(_REGS_FILE, "w") as _f: json.dump([], _f)
with open(_USERS_FILE, "w") as _f: json.dump([], _f)

# Set all env vars before importing any src module
os.environ.setdefault("BOT_TOKEN", "0:dummy_benchmark_token")
os.environ["ALLOWED_USERS"]      = f"{ADMIN_ID},{USER_ID}"
os.environ["ADMIN_USERS"]        = str(ADMIN_ID)
os.environ["NOTES_DIR"]          = _NOTES_DIR
os.environ["CALENDAR_DIR"]       = _CAL_DIR
os.environ["REGISTRATIONS_FILE"] = _REGS_FILE
os.environ["USERS_FILE"]         = _USERS_FILE
os.environ["STORE_DB_PATH"]      = _DB_FILE   # for store.py singleton
os.environ["STORE_BACKEND"]      = "sqlite"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Add src to path, import bot_db first, patch DB_PATH to temp file
# bot_db.py hardcodes DB_PATH (not env-configurable); must patch after import.
# ══════════════════════════════════════════════════════════════════════════════
# Support both dev-workspace layout (tools/ → ../src/) and Pi layout (tools/ → ../)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))
_SRC = os.path.join(_PARENT_DIR, "src")
if not os.path.isdir(os.path.join(_SRC, "core")):
    # Pi layout: modules are directly in parent dir (e.g. ~/.taris/core/)
    _SRC = _PARENT_DIR
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Ensure relative paths like "screens/..." resolve from the taris root dir
os.chdir(_PARENT_DIR)

import core.bot_db as bot_db  # noqa: E402

# Redirect DB_PATH and force fresh thread-local connections
bot_db.DB_PATH = _DB_FILE
bot_db._TARIS_DIR = _TMPDIR
bot_db._local = threading.local()  # reset so next get_db() opens temp file

# Initialize schema in the temp DB now (before other modules use it)
bot_db.init_db()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Import all required modules (store singleton created here)
# ══════════════════════════════════════════════════════════════════════════════
import core.bot_config as bot_config  # noqa: E402
from core import bot_state as _st     # noqa: E402
from core.bot_instance import bot      # noqa: E402

from telegram.bot_access import _menu_keyboard, _send_menu  # noqa: E402
from telegram.bot_handlers import (                           # noqa: E402
    _handle_notes_menu, _handle_note_list,
)
from telegram.bot_admin import (                              # noqa: E402
    _handle_admin_menu, _handle_admin_list_users,
)
from features.bot_calendar import _handle_calendar_menu      # noqa: E402
from features.bot_contacts import (                           # noqa: E402
    _handle_contacts_menu, _handle_contact_list,
)

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Mock Telegram API calls to no-ops
# ══════════════════════════════════════════════════════════════════════════════
_fake_msg = type("_Msg", (), {"message_id": 1, "chat": type("_Chat", (), {"id": ADMIN_ID})()})()

bot.send_message          = lambda *a, **kw: _fake_msg
bot.edit_message_text     = lambda *a, **kw: _fake_msg
bot.answer_callback_query = lambda *a, **kw: None
bot.delete_message        = lambda *a, **kw: None
bot.send_voice            = lambda *a, **kw: _fake_msg

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Register test users and set their language
# bot_config.ALLOWED_USERS is the same mutable set object that bot_access
# imported, so .add() here is visible to _is_allowed() everywhere.
# ══════════════════════════════════════════════════════════════════════════════
for _uid in ALL_TEST_USERS:
    bot_config.ALLOWED_USERS.add(_uid)
    _st._user_lang[_uid] = "ru"

bot_config.ADMIN_USERS.add(ADMIN_ID)

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Seed test data
# ══════════════════════════════════════════════════════════════════════════════

def _seed_notes(chat_id: int, count: int) -> None:
    """Create `count` .md note files for chat_id."""
    user_dir = os.path.join(_NOTES_DIR, str(chat_id))
    os.makedirs(user_dir, exist_ok=True)
    for i in range(count):
        path = os.path.join(user_dir, f"note_{i:03d}.md")
        with open(path, "w") as f:
            f.write(f"# Note {i}\n\nContent of note {i}.\n")


def _seed_calendar(chat_id: int, count: int) -> None:
    """Create calendar JSON with `count` future events for chat_id."""
    now = datetime.now()
    events = [
        {
            "id": str(uuid.uuid4()),
            "title": f"Event {i}",
            "dt_iso": (now + timedelta(days=i + 1, hours=i % 5)).strftime("%Y-%m-%dT%H:%M"),
            "remind_before_min": 15,
            "reminded": False,
        }
        for i in range(count)
    ]
    with open(os.path.join(_CAL_DIR, f"{chat_id}.json"), "w") as f:
        json.dump(events, f)


def _seed_contacts_sqlite(chat_id: int, count: int) -> None:
    """Insert `count` contacts directly into SQLite for chat_id."""
    db = bot_db.get_db()
    db.executemany(
        "INSERT INTO contacts (id, chat_id, name, phone, email) VALUES (?,?,?,?,?)",
        [
            (str(uuid.uuid4()), chat_id, f"Contact {i}",
             f"+7900{i:07d}", f"contact{i}@example.com")
            for i in range(count)
        ],
    )
    db.commit()


def _seed_registrations(count: int) -> None:
    """Write `count` pending registrations to REGISTRATIONS_FILE."""
    now = datetime.now().isoformat()
    regs = [
        {
            "chat_id": 90_000_000 + i,
            "username": f"pending_user_{i}",
            "name": f"Pending User {i}",
            "status": "pending",
            "registered_at": now,
        }
        for i in range(count)
    ]
    with open(_REGS_FILE, "w") as f:
        json.dump(regs, f)


# Apply seeds
_seed_notes(NOTES_USER_10, 10)
_seed_calendar(CAL_USER_10, 10)
_seed_contacts_sqlite(CONT_USER_10, 10)
_seed_registrations(5)  # 5 pending registrations shown in admin badge

# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — Benchmark runner
# ══════════════════════════════════════════════════════════════════════════════

def _bench(label: str, fn, n: int = N_ITER) -> dict:
    """Run `fn` n times with a warm-up phase; return timing stats in µs."""
    warmup = max(n // 10, 3)
    for _ in range(warmup):
        fn()

    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)

    avg_us = sum(times) / len(times) * 1_000_000
    min_us = min(times) * 1_000_000
    max_us = max(times) * 1_000_000

    print(
        f"  {label:<50}  avg={avg_us:8.0f}µs  "
        f"min={min_us:7.0f}µs  max={max_us:8.0f}µs"
    )
    return {
        "name":   label,
        "avg_us": round(avg_us, 1),
        "min_us": round(min_us, 1),
        "max_us": round(max_us, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# STEP 8 — Run all test cases
# ══════════════════════════════════════════════════════════════════════════════
try:
    import subprocess as _sp
    _node_info = _sp.check_output(["uname", "-a"], text=True).strip()
except Exception:
    _node_info = f"{platform.node()} {platform.system()} {platform.release()}"

print()
print("─── Menu Navigation Benchmark ─────────────────────────────────────────────")
print(f"    Host    : {_node_info}")
print(f"    Python  : {sys.version.split()[0]}")
print(f"    N iter  : {N_ITER}")
print(f"    Temp DB : {_DB_FILE}")
print()

results = []

# — Pure computation (no storage) ─────────────────────────────────────────────
results.append(_bench(
    "TC01 main_menu_keyboard admin  [no I/O]",
    lambda: _menu_keyboard(ADMIN_ID),
))
results.append(_bench(
    "TC02 main_menu_keyboard user   [no I/O]",
    lambda: _menu_keyboard(USER_ID),
))
results.append(_bench(
    "TC03 send_menu admin           [mocked send_message]",
    lambda: _send_menu(ADMIN_ID, greeting=True),
))
results.append(_bench(
    "TC04 notes_submenu             [no I/O]",
    lambda: _handle_notes_menu(USER_ID),
))

# — JSON file reads (notes) ───────────────────────────────────────────────────
results.append(_bench(
    "TC05 notes_list empty dir      [JSON: scan dir]",
    lambda: _handle_note_list(NOTES_USER_EMPTY),
))
results.append(_bench(
    "TC06 notes_list 10 files       [JSON: scan + stat 10 files]",
    lambda: _handle_note_list(NOTES_USER_10),
))

# — JSON file reads (admin / registrations) ───────────────────────────────────
results.append(_bench(
    "TC07 admin_menu                [JSON: read registrations badge]",
    lambda: _handle_admin_menu(ADMIN_ID),
))
results.append(_bench(
    "TC08 admin_user_list           [JSON: read all registrations]",
    lambda: _handle_admin_list_users(ADMIN_ID),
))

# — JSON file reads (calendar) ────────────────────────────────────────────────
results.append(_bench(
    "TC09 calendar_menu empty       [JSON: missing file → []]",
    lambda: _handle_calendar_menu(CAL_USER_EMPTY),
))
results.append(_bench(
    "TC10 calendar_menu 10 events   [JSON: read+parse 10-event file]",
    lambda: _handle_calendar_menu(CAL_USER_10),
))

# — SQLite reads (contacts) ───────────────────────────────────────────────────
results.append(_bench(
    "TC11 contacts_menu 0 contacts  [SQLite: COUNT=0]",
    lambda: _handle_contacts_menu(CONT_USER_EMPTY),
))
results.append(_bench(
    "TC12 contacts_menu 10 contacts [SQLite: COUNT=10]",
    lambda: _handle_contacts_menu(CONT_USER_10),
))
results.append(_bench(
    "TC13 contacts_list 10 contacts [SQLite: SELECT+paginate]",
    lambda: _handle_contact_list(CONT_USER_10),
))

# ══════════════════════════════════════════════════════════════════════════════
# STEP 9 — Save results
# ══════════════════════════════════════════════════════════════════════════════
_label = (
    f"menu_navigation — {platform.node()} "
    f"({datetime.now(timezone.utc).strftime('%Y-%m-%d')})"
)
output = {
    "label":       _label,
    "timestamp":   datetime.now(timezone.utc).isoformat(),
    "benchmark":   "menu_navigation",
    "n_iterations": N_ITER,
    "platform": {
        "node":    platform.node(),
        "system":  platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python":  sys.version.split()[0],
    },
    "results": results,
}

_results_file = args.outfile or os.path.join(
    os.path.dirname(__file__), "benchmark_results.json"
)

try:
    with open(_results_file) as _f:
        _all = json.load(_f)
    if not isinstance(_all, list):
        _all = [_all]
except (FileNotFoundError, json.JSONDecodeError):
    _all = []

_all.append(output)

with open(_results_file, "w") as _f:
    json.dump(_all, _f, indent=2)

print()
print(f"✅  Results appended to {_results_file}")

# ── Cleanup temp dir ──────────────────────────────────────────────────────────
shutil.rmtree(_TMPDIR, ignore_errors=True)
