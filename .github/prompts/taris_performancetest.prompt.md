---
mode: agent
description: Run taris performance benchmarks (storage ops, menu navigation) locally and/or on Pi targets, merge results, and print a cross-platform comparison.
---

# Taris Performance Test

Invoke this skill when the user says:
- "benchmark", "run benchmarks", "run perf tests"
- "measure performance", "check for regressions"
- "performance test suite", "benchmark on Pi"
- "compare storage vs SQLite performance"

---

## Quick Reference

| Command | What it does |
|---|---|
| `python tools\benchmark_suite.py` | All suites, local dev machine |
| `python tools\benchmark_suite.py --suite storage` | Storage ops only (local) |
| `python tools\benchmark_suite.py --suite menus` | Menu handler latency only (local) |
| `python tools\benchmark_suite.py --platform pi1` | All suites on PI1 (OpenClawPI) |
| `python tools\benchmark_suite.py --platform pi2` | All suites on PI2 (OpenClawPI2) |
| `python tools\benchmark_suite.py --platform all` | Local + PI1 + PI2 (full run) |
| `python tools\benchmark_suite.py --compare` | Print comparison table, no re-run |
| `python tools\benchmark_suite.py -n 50` | Quick run — 50 iterations per suite |

---

## Step-by-Step Protocol

### Step 1 — Sanity check (local, fast)

```bat
python tools\benchmark_suite.py --suite all --platform local -n 200
```

Inspect output:
- ✅ no `⚠️` flags → no regression detected
- ⚠️ flag on a metric → that metric is >20% slower than the previous same-platform run
- ❌ FAILED → script error; read stderr; check `src/` imports are resolving correctly

---

### Step 2 — PI1 run

Ensure `HOSTPWD` is set in your environment or in the workspace `.env`:

```bat
set HOSTPWD=<pi1-password>
python tools\benchmark_suite.py --platform pi1
```

The suite auto-deploys the script, runs it on PI1, and merges the result into
`tools/benchmark_results.json`.

---

### Step 3 — PI2 run

```bat
set HOSTPWD2=<pi2-password>
python tools\benchmark_suite.py --platform pi2
```

---

### Step 4 — Three-platform comparison (full report)

```bat
python tools\benchmark_suite.py --platform all
```

The comparison table at the end shows all platforms side-by-side. ⚠️ flags
appear where a metric degraded >20% from the previous run on the same node.

---

### Step 5 — View comparison without re-running

```bat
python tools\benchmark_suite.py --compare
```

Filter to one suite:

```bat
python tools\benchmark_suite.py --compare --suite storage
python tools\benchmark_suite.py --compare --suite menus
```

---

## Pass / Warn / Fail Thresholds

| Status | Condition |
|---|---|
| ✅ PASS | All metrics within 20% of previous same-platform run |
| ⚠️ WARN | Any metric >20% slower than previous same-platform run |
| ❌ FAIL | Script exits non-zero / benchmark crashes |

> A single ⚠️ is not necessarily a bug — re-run to confirm, or update the
> baseline by committing the new results file after investigation.

---

## What Each Suite Measures

### `storage` — JSON vs SQLite raw operations (default 500 iterations per op)

Tests file-based data stores used by the bot:

| Operation | Backend |
|---|---|
| Voice opts read / write | JSON file (`voice_opts.json`) |
| Registrations load | JSON file |
| Contact upsert / lookup | SQLite (`bot_db.py` schema) |
| Calendar load / save | JSON file |
| Note save / read | JSON file |
| Batch contact upsert (×10) | SQLite |

### `menus` — Menu handler latency (default 100 iterations per TC)

Runs real handler functions with mocked Telegram API:

| TC | Handler | I/O |
|---|---|---|
| TC01–02 | `_menu_keyboard` (admin / user) | None (pure compute) |
| TC03 | `_send_menu` | Mocked `send_message` |
| TC04 | `_handle_notes_menu` | None |
| TC05 | `_handle_note_list` — empty dir | JSON dir scan, 0 files |
| TC06 | `_handle_note_list` — 10 notes | JSON dir scan, 10 files |
| TC07 | `_handle_admin_menu` | JSON registrations |
| TC08 | `_handle_admin_list_users` | JSON registrations |
| TC09 | `_handle_calendar_menu` — empty | JSON calendar read |
| TC10 | `_handle_calendar_menu` — 10 events | JSON calendar read |
| TC11 | `_handle_contacts_menu` — 0 contacts | SQLite COUNT |
| TC12 | `_handle_contacts_menu` — 10 contacts | SQLite COUNT |
| TC13 | `_handle_contact_list` — 10 contacts | SQLite SELECT + paginate |

---

## Results File

All results are stored in `tools/benchmark_results.json` (JSON array, append-only).

Each entry structure:
```json
{
  "label":        "<suite> — <hostname> (<date>)",
  "timestamp":    "YYYY-MM-DDTHH:MM:SS",
  "benchmark":    "storage_ops | menu_navigation",
  "n_iterations": 500,
  "platform": {
    "node": "OpenClawPI",
    "system": "Linux",
    "release": "...",
    "machine": "aarch64",
    "python": "3.13.5"
  },
  "results": [
    {"name": "TC01 ...", "avg_us": 123.4, "min_us": 100.0, "max_us": 200.0}
  ]
}
```

---

## After Running

1. If ⚠️ regressions found — investigate before committing code changes.
2. Commit `tools/benchmark_results.json` together with any change that causes
   a measurable performance shift (so the baseline stays accurate).
3. To record a new baseline after intentional perf changes, just commit the
   updated results file — the comparison table always uses the *prior entry
   from the same node* as reference.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `plink` / `pscp` not found | Ensure PuTTY tools are on `PATH` |
| Pi deploy fails | Check `HOSTPWD` / `HOSTPWD2` env vars; verify Pi is reachable |
| Menu benchmark import error | Run from workspace root: `cd d:\Projects\workspace\picoclaw && python tools\...` |
| `ggml` / ONNX warnings in menus | Expected — bot patched to use mock LLM; warnings are non-fatal |
