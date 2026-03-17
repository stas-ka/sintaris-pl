#!/usr/bin/env python3
"""
benchmark_suite.py — Picoclaw unified performance benchmark orchestrator.

Runs one or both benchmark suites (storage / menus) on one or more platforms
(local dev, PI1, PI2), then prints a cross-platform comparison summary.

Usage examples:
  python tools/benchmark_suite.py                      # all suites, local
  python tools/benchmark_suite.py --suite storage      # storage ops only
  python tools/benchmark_suite.py --suite menus        # menu handlers only
  python tools/benchmark_suite.py --platform pi1       # all suites on PI1
  python tools/benchmark_suite.py --platform all       # local + PI1 + PI2
  python tools/benchmark_suite.py --compare            # print comparison only
  python tools/benchmark_suite.py -n 50                # faster run (50 iters)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
TOOLS_DIR    = Path(__file__).parent
STORAGE_BIN  = TOOLS_DIR / "benchmark_storage.py"
MENUS_BIN    = TOOLS_DIR / "benchmark_menus.py"
RESULTS_FILE = TOOLS_DIR / "benchmark_results.json"

# ── Pi targets ────────────────────────────────────────────────────────────────
# Passwords read from env vars HOSTPWD (PI1) and HOSTPWD2 (PI2).
# Set them before running: set HOSTPWD=<pi1-password> && set HOSTPWD2=<pi2-password>
# Or define them in your shell profile / .env file.
PI_TARGETS: dict[str, dict] = {
    "pi1": {
        "host":       "OpenClawPI",
        "user":       "stas",
        "remote_dir": "/home/stas/.picoclaw/tools",
        "pw_env":     "HOSTPWD",
    },
    "pi2": {
        "host":       "OpenClawPI2",
        "user":       "stas",
        "remote_dir": "/home/stas/.picoclaw/tools",
        "pw_env":     "HOSTPWD2",
    },
}

# ── Iteration defaults ────────────────────────────────────────────────────────
DEFAULT_STORAGE_N   = 500
DEFAULT_MENUS_N     = 100

# ── Regression warning threshold ─────────────────────────────────────────────
WARN_REGRESSION_PCT = 20.0


# ─────────────────────────────────────────────────────────────────────────────
# .env loader — read HOSTPWD / HOSTPWD2 from workspace .env if not in environ
# ─────────────────────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from <workspace>/.env into os.environ (no overwrite)."""
    env_path = TOOLS_DIR.parent / ".env"
    if not env_path.exists():
        return
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


def _pi_password(target: str) -> str:
    """Return the SSH password for the given target (read from env)."""
    _load_dotenv()
    pw_env = PI_TARGETS[target]["pw_env"]
    pw = os.environ.get(pw_env, "")
    if not pw:
        print(f"  ⚠️  ${pw_env} is not set — plink/pscp may fail or prompt for a password.")
    return pw


# ─────────────────────────────────────────────────────────────────────────────
# Results helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    except (json.JSONDecodeError, OSError):
        return []


def _save_results(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(entries, f, indent=2)


def _merge_entries(local: list[dict], incoming: list[dict]) -> tuple[list[dict], int]:
    """Append entries from `incoming` not already in `local` (keyed by label+timestamp).
    Returns (merged_list, count_added)."""
    existing = {(e.get("label", ""), e.get("timestamp", "")) for e in local}
    to_add = [e for e in incoming
              if (e.get("label", ""), e.get("timestamp", "")) not in existing]
    return local + to_add, len(to_add)


# ─────────────────────────────────────────────────────────────────────────────
# Local runner
# ─────────────────────────────────────────────────────────────────────────────

def _run_local(suite: str, n: int, results_path: Path) -> bool:
    """Run a benchmark suite on the local machine. Returns True on success."""
    python = sys.executable
    if suite == "storage":
        cmd = [python, str(STORAGE_BIN),
               "--iterations", str(n),
               "--output", str(results_path)]
    else:
        cmd = [python, str(MENUS_BIN),
               "--iterations", str(n),
               "--outfile", str(results_path)]

    print(f"\n{'─' * 72}")
    print(f"  ▶  {suite} benchmark  ·  local  ·  {n} iterations")
    print(f"{'─' * 72}")
    result = subprocess.run(cmd, check=False)
    ok = result.returncode == 0
    print(f"\n  {'✅' if ok else '❌'}  {suite} local benchmark {'complete' if ok else 'FAILED'}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Pi runner
# ─────────────────────────────────────────────────────────────────────────────

def _plink(host: str, user: str, pw: str, cmd: str) -> int:
    return subprocess.run(
        ["plink", "-pw", pw, "-batch", f"{user}@{host}", cmd],
        check=False,
    ).returncode


def _pscp_put(src: Path, host: str, user: str, pw: str, dest: str) -> int:
    return subprocess.run(
        ["pscp", "-pw", pw, str(src), f"{user}@{host}:{dest}"],
        check=False,
    ).returncode


def _pscp_get(remote: str, host: str, user: str, pw: str, dest: Path) -> int:
    return subprocess.run(
        ["pscp", "-pw", pw, f"{user}@{host}:{remote}", str(dest)],
        check=False,
    ).returncode


def _run_on_pi(target: str, suite: str, n: int, results_path: Path) -> bool:
    """Deploy benchmark script to Pi, run it, merge latest result into local.
    Returns True on success."""
    cfg  = PI_TARGETS[target]
    host = cfg["host"]
    user = cfg["user"]
    rdir = cfg["remote_dir"]
    pw   = _pi_password(target)
    remote_results = f"{rdir}/benchmark_results.json"

    if suite == "storage":
        script_local  = STORAGE_BIN
        script_remote = f"{rdir}/benchmark_storage.py"
        run_cmd = (
            f"mkdir -p {rdir} && "
            f"python3 {script_remote} --iterations {n} --output {remote_results}"
        )
    else:
        script_local  = MENUS_BIN
        script_remote = f"{rdir}/benchmark_menus.py"
        run_cmd = (
            f"mkdir -p {rdir} && "
            f"python3 {script_remote} --iterations {n} --outfile {remote_results}"
        )

    print(f"\n{'─' * 72}")
    print(f"  ▶  {suite} benchmark  ·  {host}  ·  {n} iterations")
    print(f"{'─' * 72}")

    # Step 1 — deploy script
    print(f"  Deploying {script_local.name} → {host}:{script_remote}")
    rc = _pscp_put(script_local, host, user, pw, script_remote)
    if rc != 0:
        print(f"  ❌ Deploy failed (rc={rc})")
        return False

    # Step 2 — run benchmark
    print(f"  Running on {host} …")
    rc = _plink(host, user, pw, run_cmd)
    if rc != 0:
        print(f"  ❌ Benchmark failed on {host} (rc={rc})")
        return False

    print(f"  ✅ Benchmark complete on {host}")

    # Step 3 — fetch Pi results and merge latest entry
    tmp = TOOLS_DIR / f"_suite_tmp_{target}_{suite}.json"
    print(f"  Fetching results from {host} …")
    rc = _pscp_get(remote_results, host, user, pw, tmp)
    if rc != 0:
        print(f"  ⚠️  Could not fetch results (rc={rc}) — run --compare later to inspect")
        return True  # benchmark itself ran OK; merge is best-effort

    try:
        pi_entries = _load_results(tmp)
        local      = _load_results(results_path)
        merged, added = _merge_entries(local, pi_entries)
        if added:
            _save_results(results_path, merged)
            print(f"  Merged {added} new result(s) into {results_path.name}")
        else:
            print(f"  No new entries to merge (labels already present locally)")
    except Exception as exc:
        print(f"  ⚠️  Merge error: {exc}")
    finally:
        tmp.unlink(missing_ok=True)

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Comparison printer
# ─────────────────────────────────────────────────────────────────────────────

def _run_label(run: dict) -> str:
    node = run.get("platform", {}).get("node", run.get("label", "?"))
    ts   = run.get("timestamp", "")[:10]
    return f"{node[:14]}/{ts}"


def _print_comparison(results_path: Path, suite_filter: str | None = None) -> None:
    entries = _load_results(results_path)
    if not entries:
        print(f"\n  No benchmark results found in {results_path}")
        return

    # group by benchmark type; old storage-ops entries lack "benchmark" key
    by_suite: dict[str, list[dict]] = {}
    for e in entries:
        btype = e.get("benchmark", "storage_ops")
        if suite_filter and btype != suite_filter:
            continue
        by_suite.setdefault(btype, []).append(e)

    if not by_suite:
        print(f"\n  No results matching suite filter '{suite_filter}'.")
        return

    for btype, runs in sorted(by_suite.items()):
        print(f"\n{'═' * 72}")
        print(f"  Suite : {btype}   ({len(runs)} run{'s' if len(runs) != 1 else ''})")
        print(f"{'═' * 72}")

        # collect union of all metric names (preserves order from latest run first)
        all_names: list[str] = []
        seen: set[str] = set()
        for run in reversed(runs):
            for r in run.get("results", []):
                if r["name"] not in seen:
                    all_names.append(r["name"])
                    seen.add(r["name"])
        all_names = list(reversed(all_names))

        run_labels = [_run_label(r) for r in runs]
        col_w = 52
        hdr = f"  {'Metric':<{col_w}}" + "".join(f"  {lbl:>24}" for lbl in run_labels)
        print(hdr)
        print(f"  {'─' * col_w}" + "".join(f"  {'─' * 24}" for _ in runs))

        # track last avg per node for regression detection
        last_avg_by_node: dict[str, dict[str, float]] = {}

        for metric in all_names:
            row = f"  {metric:<{col_w}}"
            for run in runs:
                node = run.get("platform", {}).get("node", "?")
                by_name = {r["name"]: r for r in run.get("results", [])}
                if metric in by_name:
                    avg  = by_name[metric]["avg_us"]
                    prev = last_avg_by_node.get(node, {}).get(metric)
                    if prev is not None:
                        pct  = (avg - prev) / prev * 100.0
                        flag = "⚠️ " if pct > WARN_REGRESSION_PCT else "   "
                        row += f"   {avg:>8.0f}µs{flag:3}"
                    else:
                        row += f"   {avg:>8.0f}µs   "
                    last_avg_by_node.setdefault(node, {})[metric] = avg
                else:
                    row += f"  {'—':>26}"
            print(row)

        latest = runs[-1]
        print(
            f"\n  Latest : {latest.get('timestamp', '')[:19]}"
            f"  ·  {latest.get('platform', {}).get('node', '?')}"
            f"  ·  {latest.get('n_iterations', '?')} iterations"
        )


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Picoclaw unified performance benchmark runner + comparison printer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--suite", choices=["storage", "menus", "all"], default="all",
        help="Which benchmark suite to run (default: all)",
    )
    parser.add_argument(
        "--platform", choices=["local", "pi1", "pi2", "all"], default="local",
        help=(
            "Target platform: local dev machine, pi1 (OpenClawPI), "
            "pi2 (OpenClawPI2), or all three (default: local)"
        ),
    )
    parser.add_argument(
        "--iterations", "-n", type=int, default=None,
        help=(
            f"Number of iterations — overrides per-suite defaults "
            f"(storage={DEFAULT_STORAGE_N}, menus={DEFAULT_MENUS_N})"
        ),
    )
    parser.add_argument(
        "--compare", "-c", action="store_true",
        help="Print comparison table from existing results and exit (no benchmarks run)",
    )
    parser.add_argument(
        "--results", metavar="PATH", default=str(RESULTS_FILE),
        help=f"Results JSON file path (default: {RESULTS_FILE.name})",
    )
    args = parser.parse_args()

    results_path = Path(args.results)

    # ── Compare-only mode ────────────────────────────────────────────────────
    if args.compare:
        suite_f = None if args.suite == "all" else args.suite
        _print_comparison(results_path, suite_f)
        return

    # ── Build platform + suite lists ─────────────────────────────────────────
    platforms = ["local", "pi1", "pi2"] if args.platform == "all" else [args.platform]
    suites    = ["storage", "menus"]    if args.suite    == "all" else [args.suite]

    t_start = time.perf_counter()
    ok_list:   list[str] = []
    fail_list: list[str] = []

    for plat in platforms:
        for suite in suites:
            n = args.iterations or (
                DEFAULT_STORAGE_N if suite == "storage" else DEFAULT_MENUS_N
            )
            if plat == "local":
                ok = _run_local(suite, n, results_path)
            else:
                ok = _run_on_pi(plat, suite, n, results_path)
            key = f"{suite}@{plat}"
            (ok_list if ok else fail_list).append(key)

    elapsed = time.perf_counter() - t_start
    print(f"\n{'═' * 72}")
    print(
        f"  Done in {elapsed:.1f}s  —  "
        f"{len(ok_list)} passed, {len(fail_list)} failed"
    )
    if fail_list:
        print(f"  ❌ Failed: {', '.join(fail_list)}")
    print(f"{'═' * 72}")

    # Print comparison summary
    suite_f = None if args.suite == "all" else args.suite
    _print_comparison(results_path, suite_f)


if __name__ == "__main__":
    main()
