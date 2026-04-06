#!/usr/bin/env python3
"""
benchmark_suite.py — Taris unified performance benchmark orchestrator.

Runs storage / menus / voice / conversation suites on one or more targets
(ts2, sintaition/ts1, pi1, pi2), then prints a cross-platform comparison.

Usage examples:
  python tools/benchmark_suite.py                           # all suites, ts2 (local)
  python tools/benchmark_suite.py --suite storage           # storage ops only
  python tools/benchmark_suite.py --suite conversation      # LLM conversation quality
  python tools/benchmark_suite.py --target sintaition       # all suites on SintAItion
  python tools/benchmark_suite.py --target all              # ts2 + sintaition + pi1 + pi2
  python tools/benchmark_suite.py --target all-openclaw     # ts2 + sintaition
  python tools/benchmark_suite.py --compare ts2 sintaition  # print comparison, no re-run
  python tools/benchmark_suite.py -n 50                     # faster run (50 iterations)
  python tools/benchmark_suite.py --yes                     # non-interactive
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
TOOLS_DIR        = Path(__file__).parent
STORAGE_BIN      = TOOLS_DIR / "benchmark_storage.py"
MENUS_BIN        = TOOLS_DIR / "benchmark_menus.py"
VOICE_BIN        = TOOLS_DIR / "benchmark_voice.py"
CONV_BIN         = TOOLS_DIR / "benchmark_conversation.py"
RESULTS_FILE     = TOOLS_DIR / "benchmark_results.json"
VOICE_RESULTS    = TOOLS_DIR / "benchmark_voice_results.json"
CONV_RESULTS     = TOOLS_DIR / "benchmark_conv_results.json"

# ── All targets ───────────────────────────────────────────────────────────────
# Aliases resolve to another key string; real entries are dicts.
ALL_TARGETS: dict[str, object] = {
    "ts2": {
        "label":      "TariStation2 (local, OpenClaw)",
        "type":       "openclaw",
        "ssh":        False,
        "host":       "localhost",
        "user":       None,
        "pw_env":     None,
        "remote_dir": None,
    },
    "sintaition": {
        "label":      "SintAItion / TariStation1 (OpenClaw)",
        "type":       "openclaw",
        "ssh":        True,
        "host":       "SintAItion",
        "user":       "stas",
        "pw_env":     "OPENCLAW1PWD",
        "remote_dir": "/home/stas/.taris/tools",
    },
    "ts1":   "sintaition",   # alias
    "pi2": {
        "label":      "OpenClawPI2 / TariStation2-Pi (PicoClaw)",
        "type":       "picoclaw",
        "ssh":        True,
        "host":       "OpenClawPI2.local",
        "user":       "stas",
        "pw_env":     "DEV_HOST_PWD",
        "remote_dir": "/home/stas/.taris/tools",
    },
    "pi1": {
        "label":      "OpenClawPI / TariStation1-Pi (PicoClaw)",
        "type":       "picoclaw",
        "ssh":        True,
        "host":       "OpenClawPI.local",
        "user":       "stas",
        "pw_env":     "PROD_HOST_PWD",
        "remote_dir": "/home/stas/.taris/tools",
    },
    "local": "ts2",          # legacy alias
}

# Legacy PI_TARGETS kept for backward-compatibility with older code paths
PI_TARGETS: dict[str, dict] = {
    "pi1": {
        "host":       "OpenClawPI",
        "user":       "stas",
        "remote_dir": "/home/stas/.taris/tools",
        "pw_env":     "PROD_HOST_PWD",
    },
    "pi2": {
        "host":       "OpenClawPI2",
        "user":       "stas",
        "remote_dir": "/home/stas/.taris/tools",
        "pw_env":     "DEV_HOST_PWD",
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


def _resolve_target(name: str) -> dict:
    """Resolve a target name (including aliases) to its config dict."""
    _load_dotenv()
    entry = ALL_TARGETS.get(name)
    if entry is None:
        raise ValueError(f"Unknown target: {name!r}. "
                         f"Valid: {', '.join(k for k in ALL_TARGETS if not isinstance(ALL_TARGETS[k], str))}")
    if isinstance(entry, str):
        entry = ALL_TARGETS[entry]
    return entry  # type: ignore[return-value]


def _get_password(target_cfg: dict) -> str:
    """Return the SSH password for a target config (read from .env)."""
    _load_dotenv()
    pw_env = target_cfg.get("pw_env") or ""
    if not pw_env:
        return ""
    pw = os.environ.get(pw_env, "")
    if not pw:
        print(f"  ⚠️  ${pw_env} is not set — SSH may fail or prompt for a password.")
    return pw


def _pi_password(target: str) -> str:
    """Legacy helper — return SSH password for a PI_TARGETS entry."""
    _load_dotenv()
    pw_env = PI_TARGETS[target]["pw_env"]
    pw = os.environ.get(pw_env, "")
    if not pw:
        print(f"  ⚠️  ${pw_env} is not set — sshpass may fail.")
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

def _run_local(suite: str, n: int, results_path: Path,
               target_type: str = "openclaw") -> bool:
    """Run a benchmark suite on the local machine. Returns True on success."""
    python = sys.executable

    if suite == "storage":
        cmd = [python, str(STORAGE_BIN), "--iterations", str(n), "--output", str(results_path)]
    elif suite == "menus":
        cmd = [python, str(MENUS_BIN), "--iterations", str(n), "--outfile", str(results_path)]
    elif suite == "voice":
        if target_type != "openclaw":
            print(f"  ⚠️  voice suite requires OpenClaw target — skipping for {target_type}")
            return True
        cmd = [python, str(VOICE_BIN), "--output", str(VOICE_RESULTS), "-n", str(n)]
    elif suite == "conversation":
        if target_type != "openclaw":
            print(f"  ⚠️  conversation suite requires OpenClaw target (Ollama) — skipping")
            return True
        cmd = [python, str(CONV_BIN), "--output", str(CONV_RESULTS), "-n", str(n)]
    else:
        print(f"  ❌ Unknown suite: {suite!r}")
        return False

    print(f"\n{'─' * 72}")
    print(f"  ▶  {suite} benchmark  ·  local  ·  n={n}")
    print(f"{'─' * 72}")
    result = subprocess.run(cmd, check=False)
    ok = result.returncode == 0
    print(f"\n  {'✅' if ok else '❌'}  {suite} local benchmark {'complete' if ok else 'FAILED'}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# SSH helpers (sshpass + ssh/scp for OpenClaw and PicoClaw remote targets)
# ─────────────────────────────────────────────────────────────────────────────

def _ssh(host: str, user: str, pw: str, cmd: str) -> int:
    return subprocess.run(
        ["sshpass", "-p", pw, "ssh", "-o", "StrictHostKeyChecking=no",
         f"{user}@{host}", cmd],
        check=False,
    ).returncode


def _scp_put(src: Path, host: str, user: str, pw: str, dest: str) -> int:
    return subprocess.run(
        ["sshpass", "-p", pw, "scp", "-o", "StrictHostKeyChecking=no",
         str(src), f"{user}@{host}:{dest}"],
        check=False,
    ).returncode


def _scp_get(remote: str, host: str, user: str, pw: str, dest: Path) -> int:
    return subprocess.run(
        ["sshpass", "-p", pw, "scp", "-o", "StrictHostKeyChecking=no",
         f"{user}@{host}:{remote}", str(dest)],
        check=False,
    ).returncode


def _plink(host: str, user: str, pw: str, cmd: str) -> int:
    """Legacy plink helper (Pi targets on Windows-originated deploys)."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Remote runner (SSH — covers OpenClaw and PicoClaw remote targets)
# ─────────────────────────────────────────────────────────────────────────────

def _run_on_target(target_name: str, suite: str, n: int, results_path: Path) -> bool:
    """Deploy and run a benchmark suite on a remote SSH target. Returns True on success."""
    cfg = _resolve_target(target_name)
    host = cfg["host"]
    user = cfg["user"]
    rdir = cfg["remote_dir"]
    pw   = _get_password(cfg)
    target_type = cfg.get("type", "picoclaw")

    # OpenClaw-only suites
    if suite in ("voice", "conversation") and target_type != "openclaw":
        print(f"  ⚠️  {suite} requires OpenClaw (Ollama) — skipping {target_name} ({target_type})")
        return True

    # Map suite → local script + remote filenames + run command
    if suite == "storage":
        script_local  = STORAGE_BIN
        remote_script = f"{rdir}/benchmark_storage.py"
        remote_out    = f"{rdir}/benchmark_results.json"
        run_cmd = (f"mkdir -p {rdir} && "
                   f"python3 {remote_script} --iterations {n} --output {remote_out}")
    elif suite == "menus":
        script_local  = MENUS_BIN
        remote_script = f"{rdir}/benchmark_menus.py"
        remote_out    = f"{rdir}/benchmark_results.json"
        run_cmd = (f"mkdir -p {rdir} && "
                   f"python3 {remote_script} --iterations {n} --outfile {remote_out}")
    elif suite == "voice":
        script_local  = VOICE_BIN
        remote_script = f"{rdir}/benchmark_voice.py"
        remote_out    = f"{rdir}/benchmark_voice_results.json"
        run_cmd = (f"mkdir -p {rdir} && "
                   f"python3 {remote_script} --output {remote_out} -n {n}")
    elif suite == "conversation":
        script_local  = CONV_BIN
        remote_script = f"{rdir}/benchmark_conversation.py"
        remote_out    = f"{rdir}/benchmark_conv_results.json"
        run_cmd = (f"mkdir -p {rdir} && "
                   f"python3 {remote_script} --output {remote_out} -n {n}")
    else:
        print(f"  ❌ Unknown suite: {suite!r}")
        return False

    print(f"\n{'─' * 72}")
    print(f"  ▶  {suite} benchmark  ·  {host}  ·  n={n}")
    print(f"{'─' * 72}")

    print(f"  Deploying {script_local.name} → {host}:{remote_script}")
    rc = _scp_put(script_local, host, user, pw, remote_script)
    if rc != 0:
        print(f"  ❌ Deploy failed (rc={rc})")
        return False

    print(f"  Running on {host} …")
    rc = _ssh(host, user, pw, run_cmd)
    if rc != 0:
        print(f"  ❌ Benchmark failed on {host} (rc={rc})")
        return False

    print(f"  ✅ Benchmark complete on {host}")

    # Fetch remote results and merge into local file
    tmp = TOOLS_DIR / f"_suite_tmp_{target_name}_{suite}.json"
    print(f"  Fetching results from {host} …")
    rc = _scp_get(remote_out, host, user, pw, tmp)
    if rc != 0:
        print(f"  ⚠️  Could not fetch results (rc={rc}) — run --compare later")
        return True

    try:
        remote_entries = _load_results(tmp)
        local_entries  = _load_results(results_path)
        merged, added  = _merge_entries(local_entries, remote_entries)
        if added:
            _save_results(results_path, merged)
            print(f"  Merged {added} new result(s) into {results_path.name}")
        else:
            print(f"  No new entries to merge")
    except Exception as exc:
        print(f"  ⚠️  Merge error: {exc}")
    finally:
        tmp.unlink(missing_ok=True)

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Comparison printer
# ─────────────────────────────────────────────────────────────────────────────

def _run_label(run: dict) -> str:
    plat = run.get("platform", {})
    # Support both "node" (conversation format) and "hostname" (storage format)
    node = plat.get("node", plat.get("hostname", run.get("label", "?")))
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
                    r_entry = by_name[metric]
                    # Support result formats from all benchmark scripts:
                    # storage:  db_us / file_us    (benchmark_storage.py)
                    # menus:    avg_ms             (benchmark_menus.py)
                    # legacy:   avg_us
                    if "db_us" in r_entry:
                        avg = r_entry["db_us"]
                        unit = "µs"
                    elif "avg_us" in r_entry:
                        avg = r_entry["avg_us"]
                        unit = "µs"
                    elif "avg_ms" in r_entry:
                        avg = r_entry["avg_ms"] * 1000  # normalise to µs
                        unit = "µs"
                    else:
                        avg = float(r_entry.get("avg", r_entry.get("latency_ms", 0)))
                        unit = "  "
                    prev = last_avg_by_node.get(node, {}).get(metric)
                    if prev is not None and prev > 0:
                        pct  = (avg - prev) / prev * 100.0
                        flag = "⚠️ " if pct > WARN_REGRESSION_PCT else "   "
                        row += f"   {avg:>8.0f}{unit}{flag:3}"
                    else:
                        row += f"   {avg:>8.0f}{unit}   "
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

# Expand multi-target group keywords to concrete target lists
_TARGET_GROUPS: dict[str, list[str]] = {
    "all":            ["ts2", "sintaition", "pi1", "pi2"],
    "all-openclaw":   ["ts2", "sintaition"],
    "all-picoclaw":   ["pi1", "pi2"],
}

_SUITE_CHOICES = ["storage", "menus", "voice", "conversation", "all"]
_TARGET_CHOICES = (
    list(_TARGET_GROUPS.keys())
    + [k for k in ALL_TARGETS if not isinstance(ALL_TARGETS[k], str)]
    + ["ts1"]  # alias
)


def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="Taris unified performance benchmark runner + comparison printer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--suite",
        choices=_SUITE_CHOICES,
        default="all",
        help="Benchmark suite(s) to run (default: all = storage+menus+voice+conversation)",
    )
    parser.add_argument(
        "--target",
        default="ts2",
        metavar="TARGET",
        help=(
            "Target: ts2 | ts1 | sintaition | pi1 | pi2 | "
            "all | all-openclaw | all-picoclaw  (default: ts2)"
        ),
    )
    parser.add_argument(
        "--platform",
        default=None,
        metavar="PLATFORM",
        help="Legacy alias for --target (local|pi1|pi2|all); --target takes priority",
    )
    parser.add_argument(
        "--iterations", "-n", type=int, default=None,
        help=(
            f"Number of iterations/repeats — overrides per-suite defaults "
            f"(storage={DEFAULT_STORAGE_N}, menus={DEFAULT_MENUS_N}, voice/conv=2)"
        ),
    )
    parser.add_argument(
        "--compare", nargs="*", metavar="TARGET",
        help=(
            "Print cross-target comparison from latest saved results, no re-run. "
            "Optionally list targets to compare (default: ts2 sintaition pi1 pi2)"
        ),
    )
    parser.add_argument(
        "--results", metavar="PATH", default=str(RESULTS_FILE),
        help=f"Results JSON file path (default: {RESULTS_FILE.name})",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Non-interactive mode — skip all confirmation prompts",
    )
    args = parser.parse_args()

    results_path = Path(args.results)

    # ── Compare-only mode ────────────────────────────────────────────────────
    if args.compare is not None:
        suite_f = None if args.suite == "all" else args.suite
        _print_comparison(results_path, suite_f)
        return

    # ── Resolve --target (--platform as legacy fallback) ─────────────────────
    raw_target = args.target
    if raw_target == "ts2" and args.platform and args.platform != "local":
        raw_target = args.platform  # honour legacy --platform flag

    if raw_target in _TARGET_GROUPS:
        target_list = _TARGET_GROUPS[raw_target]
    else:
        # Resolve aliases like "ts1", "local" to canonical keys
        resolved = raw_target
        entry = ALL_TARGETS.get(resolved)
        if isinstance(entry, str):
            resolved = entry
        target_list = [resolved]

    # ── Resolve suites ───────────────────────────────────────────────────────
    if args.suite == "all":
        suites = ["storage", "menus", "voice", "conversation"]
    else:
        suites = [args.suite]

    t_start = time.perf_counter()
    ok_list:   list[str] = []
    fail_list: list[str] = []

    for tgt in target_list:
        cfg = _resolve_target(tgt)
        is_local = not cfg.get("ssh", True)
        tgt_type = cfg.get("type", "picoclaw")

        for suite in suites:
            n = args.iterations or (
                DEFAULT_STORAGE_N if suite == "storage"
                else DEFAULT_MENUS_N if suite == "menus"
                else 2
            )
            if is_local:
                ok = _run_local(suite, n, results_path, tgt_type)
            else:
                ok = _run_on_target(tgt, suite, n, results_path)
            key = f"{suite}@{tgt}"
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

    # Print storage/menus comparison summary
    suite_f = None if args.suite == "all" else args.suite
    if suite_f in (None, "storage", "menus"):
        _print_comparison(results_path, suite_f)


if __name__ == "__main__":
    main()
