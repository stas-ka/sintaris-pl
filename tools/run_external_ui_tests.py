#!/usr/bin/env python3
"""
run_external_ui_tests.py — Run internet-facing Playwright tests against all
configured Taris instances and print a consolidated pass/fail summary.

Usage:
    python tools/run_external_ui_tests.py

Env vars (all required for authenticated tests):
    TARIS_ADMIN_USER     admin username (default: stas)
    TARIS_ADMIN_PASS     admin password (REQUIRED for auth tests)
    TARIS_NORMAL_USER    regular user   (default: testuser)
    TARIS_NORMAL_PASS    regular user password (default: testpass456)

Instance configuration — edit INSTANCES below or set TARIS_INSTANCES env var:
    TARIS_INSTANCES="SintAItion:https://agents.sintaris.net/supertaris,TS2:https://agents.sintaris.net/supertaris2"
"""

import os
import subprocess
import sys

# ── Instance config ──────────────────────────────────────────────────────────

_DEFAULT_INSTANCES = [
    ("SintAItion (TariStation1)",  "https://agents.sintaris.net/supertaris"),
    ("TariStation2 (Engineering)", "https://agents.sintaris.net/supertaris2"),
]

def _load_instances():
    raw = os.environ.get("TARIS_INSTANCES", "")
    if not raw:
        return _DEFAULT_INSTANCES
    result = []
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            name, url = entry.split(":", 1)
            result.append((name.strip(), url.strip()))
    return result or _DEFAULT_INSTANCES

# ── Run ───────────────────────────────────────────────────────────────────────

def run_tests(name: str, base_url: str, extra_args: list[str]) -> int:
    """Run test suite against one instance, return exit code."""
    print(f"\n{'='*70}")
    print(f"  Instance: {name}")
    print(f"  URL:      {base_url}")
    print(f"{'='*70}")

    cmd = [
        sys.executable, "-m", "pytest",
        "src/tests/ui/test_external_ui.py",
        "-v",
        f"--base-url={base_url}",
        "--browser=chromium",
        "--tb=short",
        "-q",
    ] + extra_args

    env = os.environ.copy()
    result = subprocess.run(cmd, env=env)
    return result.returncode


def main():
    instances = _load_instances()
    extra_args = sys.argv[1:]  # pass-through to pytest

    print(f"Running external UI tests against {len(instances)} instance(s)")
    print(f"TARIS_ADMIN_USER = {os.environ.get('TARIS_ADMIN_USER', 'stas')}")
    cred_set = bool(os.environ.get("TARIS_ADMIN_PASS"))
    print(f"TARIS_ADMIN_PASS = {'*** (set)' if cred_set else '(not set — auth tests will be skipped)'}")

    results: list[tuple[str, int]] = []
    for name, url in instances:
        rc = run_tests(name, url, extra_args)
        results.append((name, rc))

    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    all_pass = True
    for name, rc in results:
        status = "✅ PASS" if rc == 0 else "❌ FAIL"
        print(f"  {status}  {name}")
        if rc != 0:
            all_pass = False

    print(f"{'='*70}\n")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
