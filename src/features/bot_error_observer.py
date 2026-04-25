"""
bot_error_observer.py — Error Observer Agent.

Monitors the bot's log file for ERROR/CRITICAL entries and auto-generates
structured error reports in the git-tracked errors/ directory (GIT_ERRORS_DIR).
User-reported errors from bot_error_protocol.py are also routed here for git
commit/push.

Public API:
  start_observer()              — register logging handler + start background watcher
  stop_observer()               — stop the watcher thread cleanly
  get_recent_log_errors(n)      — last n WARNING/ERROR/CRITICAL lines from log file
  get_buffered_error_lines()    — recent error lines from in-memory capture buffer
  write_error_to_git_dir(...)   — write a structured report to GIT_ERRORS_DIR
  commit_and_push_error(...)    — git add/commit/push the named error folder
  make_description_md(...)      — render a Markdown description for a report
  update_errors_index(dir)      — regenerate errors/README.md
"""

import json
import logging
import os
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.bot_config import (
    BOT_VERSION,
    DEVICE_VARIANT,
    ERROR_GIT_AUTO_PUSH,
    GIT_ERRORS_DIR,
    LOG_FILE,
    log,
)

# ─────────────────────────────────────────────────────────────────────────────
# Internal error capture buffer (ring buffer, last 500 records)
# ─────────────────────────────────────────────────────────────────────────────

_error_buffer: deque = deque(maxlen=500)
_observer_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

# Minimum distinct error records in one observation window to trigger auto-report
_AUTO_REPORT_THRESHOLD = int(os.environ.get("ERROR_AUTO_THRESHOLD", "3"))
# Seconds between auto-reports (cooldown prevents report floods)
_AUTO_REPORT_COOLDOWN = int(os.environ.get("ERROR_AUTO_COOLDOWN", "300"))
_last_auto_report_ts: float = 0.0


class ErrorCaptureHandler(logging.Handler):
    """Logging handler that captures WARNING+ records into _error_buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%dT%H:%M:%S")
            _error_buffer.append((ts, record.levelname, self.format(record)))
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Log file reader
# ─────────────────────────────────────────────────────────────────────────────

def get_recent_log_errors(n: int = 50) -> list:
    """Return last n WARNING/ERROR/CRITICAL lines from the telegram_bot.log file."""
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        error_lines = [
            l.rstrip() for l in lines
            if any(kw in l for kw in (" ERROR ", " CRITICAL ", " WARNING "))
        ]
        return error_lines[-n:]
    except (OSError, IOError):
        return []


def get_buffered_error_lines(n: int = 30) -> list:
    """Return last n error records from the in-memory capture buffer."""
    return [
        f"[{ts}] {lvl}: {msg}"
        for ts, lvl, msg in list(_error_buffer)[-n:]
        if lvl in ("ERROR", "CRITICAL", "WARNING")
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Report formatting
# ─────────────────────────────────────────────────────────────────────────────

def make_description_md(manifest: dict, user_texts: list) -> str:
    """Render a Markdown description.md for an error report."""
    sev = manifest.get("severity", "medium")
    sev_icon = {"critical": "🚨", "high": "❗", "medium": "⚠️", "low": "ℹ️"}.get(sev, "⚠️")
    lines = [
        f"# {sev_icon} Error Report: {manifest.get('name', 'Unknown')}",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| **ID** | `{manifest.get('id', '?')}` |",
        f"| **Status** | {manifest.get('status', 'open')} |",
        f"| **Severity** | {sev_icon} {sev} |",
        f"| **Reporter** | {manifest.get('reporter_type', 'user')} |",
        f"| **Created** | {manifest.get('created', '?')[:19]} |",
        f"| **Bot version** | `{manifest.get('bot_version', '?')}` |",
        f"| **Target** | `{manifest.get('target', '?')}` |",
        "",
    ]
    if user_texts:
        lines += ["## User Description", ""]
        for i, t in enumerate(user_texts, 1):
            lines += [f"**Text {i}:**", "", t, ""]
    log_lines = manifest.get("log_lines", [])
    if log_lines:
        lines += [
            "## Log Excerpt",
            "",
            "```",
            *log_lines[-20:],
            "```",
            "",
        ]
    lines += [
        "## Resolution Checklist",
        "",
        "- [ ] Root cause identified",
        "- [ ] Fix implemented in source",
        "- [ ] Regression test added",
        "- [ ] Deployed and verified on engineering target",
        "- [ ] Deployed and verified on production target",
        "",
        "_Resolved commit: (fill in after fixing)_",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Git errors/ directory writer
# ─────────────────────────────────────────────────────────────────────────────

def write_error_to_git_dir(
    folder_name: str,
    name: str,
    reporter_type: str,
    reporter_chat_id,
    severity: str,
    user_texts: list,
    voices: list,
    photos: list,
    errors_dir: str = "",
) -> Optional[str]:
    """
    Write a structured error report to GIT_ERRORS_DIR (or errors_dir override).
    Returns the full folder path on success, None on failure.
    """
    target_dir = errors_dir or GIT_ERRORS_DIR
    if not target_dir:
        return None

    folder_path = os.path.join(target_dir, folder_name)
    try:
        os.makedirs(folder_path, exist_ok=True)
    except OSError as e:
        log.warning(f"[ErrObs] cannot create errors dir {folder_path}: {e}")
        return None

    log_lines = get_recent_log_errors(50)

    manifest = {
        "id": folder_name,
        "name": name,
        "status": "open",
        "severity": severity,
        "reporter_type": reporter_type,
        "reporter_chat_id": reporter_chat_id,
        "created": datetime.now().isoformat(),
        "bot_version": BOT_VERSION,
        "target": DEVICE_VARIANT,
        "log_lines": log_lines[-30:],
        "texts": [f"text_{i+1:02d}.txt" for i in range(len(user_texts))],
        "voices": voices,
        "photos": photos,
    }

    # Write manifest
    Path(os.path.join(folder_path, "manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Write description.md
    Path(os.path.join(folder_path, "description.md")).write_text(
        make_description_md(manifest, user_texts), encoding="utf-8"
    )
    # Write log excerpt
    if log_lines:
        Path(os.path.join(folder_path, "log_excerpt.txt")).write_text(
            "\n".join(log_lines), encoding="utf-8"
        )
    # Write user texts
    for i, txt in enumerate(user_texts):
        Path(os.path.join(folder_path, f"text_{i+1:02d}.txt")).write_text(
            txt, encoding="utf-8"
        )

    update_errors_index(target_dir)
    log.info(f"[ErrObs] error report written: {folder_name}")
    return folder_path


def commit_and_push_error(folder_name: str, errors_dir: str = "") -> tuple:
    """
    Git add + commit + push for the named error folder.
    Returns (success: bool, message: str).
    Fails silently if git is not configured or push credentials are missing.
    """
    target_dir = errors_dir or GIT_ERRORS_DIR
    if not target_dir:
        return False, "GIT_ERRORS_DIR not configured"

    # Determine the git repo root (parent of errors/ dir)
    repo_root = os.path.dirname(os.path.abspath(target_dir))

    def _run(args: list) -> tuple:
        try:
            result = subprocess.run(
                args,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            return -1, "", str(e)

    errors_rel = os.path.relpath(target_dir, repo_root)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_msg = (
        f"error: {folder_name} ({ts})\n\n"
        f"Auto-committed by bot_error_observer on {DEVICE_VARIANT}\n"
        f"Bot version: {BOT_VERSION}\n\n"
        f"Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
    )

    rc, _, err = _run(["git", "add", errors_rel])
    if rc != 0:
        log.warning(f"[ErrObs] git add failed: {err}")
        return False, f"git add failed: {err}"

    rc, _, err = _run(["git", "commit", "-m", commit_msg])
    if rc != 0:
        log.warning(f"[ErrObs] git commit failed: {err}")
        return False, f"git commit failed: {err}"

    if not ERROR_GIT_AUTO_PUSH:
        return True, "committed (push disabled)"

    rc, out, err = _run(["git", "push"])
    if rc != 0:
        log.warning(f"[ErrObs] git push failed (saved locally): {err}")
        return True, f"committed but push failed: {err}"

    log.info(f"[ErrObs] pushed error report: {folder_name}")
    return True, "committed and pushed"


# ─────────────────────────────────────────────────────────────────────────────
# errors/README.md index generator
# ─────────────────────────────────────────────────────────────────────────────

def update_errors_index(errors_dir: str = "") -> None:
    """Regenerate errors/README.md with a table of all error reports."""
    target_dir = errors_dir or GIT_ERRORS_DIR
    if not target_dir or not os.path.isdir(target_dir):
        return

    entries = []
    try:
        for entry in sorted(os.scandir(target_dir), key=lambda e: e.name, reverse=True):
            if not entry.is_dir():
                continue
            mpath = os.path.join(entry.path, "manifest.json")
            if not os.path.isfile(mpath):
                continue
            try:
                m = json.loads(Path(mpath).read_text(encoding="utf-8"))
                entries.append({
                    "id": entry.name,
                    "name": m.get("name", entry.name),
                    "status": m.get("status", "open"),
                    "severity": m.get("severity", "medium"),
                    "reporter": m.get("reporter_type", "user"),
                    "created": m.get("created", "")[:19],
                    "version": m.get("bot_version", "?"),
                })
            except Exception:
                pass
    except OSError:
        return

    open_n = sum(1 for e in entries if e["status"] == "open")
    inv_n = sum(1 for e in entries if e["status"] == "investigating")
    res_n = sum(1 for e in entries if e["status"] == "resolved")

    _STATUS_ICON = {"open": "🔴", "investigating": "🟡", "resolved": "✅"}
    _SEV_ICON = {"critical": "🚨", "high": "❗", "medium": "⚠️", "low": "ℹ️"}

    lines = [
        "# Error Reports Index",
        "",
        f"**Open:** {open_n} &nbsp;|&nbsp; **Investigating:** {inv_n} "
        f"&nbsp;|&nbsp; **Resolved:** {res_n} &nbsp;|&nbsp; **Total:** {len(entries)}",
        "",
        "Use `/taris-error-review` Copilot skill to review and resolve open errors.",
        "",
        "| # | Folder | Name | Severity | Status | Reporter | Created | Version |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, e in enumerate(entries, 1):
        si = _STATUS_ICON.get(e["status"], "❓")
        sev_i = _SEV_ICON.get(e["severity"], "⚠️")
        lines.append(
            f"| {i} | `{e['id']}` | {e['name']} "
            f"| {sev_i} {e['severity']} | {si} {e['status']} "
            f"| {e['reporter']} | {e['created']} | {e['version']} |"
        )
    lines += [
        "",
        "---",
        "",
        "_Auto-generated by `bot_error_observer.py`. "
        "Do not edit manually — regenerated on every new error report._",
    ]
    try:
        Path(os.path.join(target_dir, "README.md")).write_text(
            "\n".join(lines), encoding="utf-8"
        )
    except OSError as e:
        log.warning(f"[ErrObs] cannot write errors/README.md: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Auto-report from log observer
# ─────────────────────────────────────────────────────────────────────────────

def _write_auto_report(error_records: list) -> None:
    """Create an automatic error report from buffered log error records."""
    if not GIT_ERRORS_DIR:
        return
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder_name = f"{ts}_auto_{len(error_records)}errors"
    severity = "critical" if any(lvl == "CRITICAL" for _, lvl, _ in error_records) else "high"
    log_lines = [f"[{t}] {lvl}: {msg}" for t, lvl, msg in error_records]
    path = write_error_to_git_dir(
        folder_name=folder_name,
        name=f"Auto-detected: {len(error_records)} log error(s)",
        reporter_type="log_observer",
        reporter_chat_id=None,
        severity=severity,
        user_texts=[],
        voices=[],
        photos=[],
        errors_dir=GIT_ERRORS_DIR,
    )
    if path:
        threading.Thread(
            target=commit_and_push_error,
            args=(folder_name, GIT_ERRORS_DIR),
            daemon=True,
        ).start()


def _observer_loop() -> None:
    """Background thread: scan buffer every 5 minutes, fire auto-reports."""
    global _last_auto_report_ts
    while not _stop_event.wait(300):
        now = time.time()
        if now - _last_auto_report_ts < _AUTO_REPORT_COOLDOWN:
            continue
        # Collect ERROR/CRITICAL from the last observation window
        cutoff = time.time() - 300  # last 5 minutes
        recent = [
            (ts, lvl, msg)
            for ts, lvl, msg in list(_error_buffer)
            if lvl in ("ERROR", "CRITICAL")
        ]
        if len(recent) >= _AUTO_REPORT_THRESHOLD:
            _last_auto_report_ts = now
            try:
                _write_auto_report(recent)
            except Exception as exc:
                log.warning(f"[ErrObs] auto-report failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Public lifecycle API
# ─────────────────────────────────────────────────────────────────────────────

def start_observer() -> None:
    """
    Register the ErrorCaptureHandler on the taris logger and start the
    background auto-report watcher thread.
    """
    global _observer_thread

    handler = ErrorCaptureHandler()
    handler.setLevel(logging.WARNING)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    # Attach to root taris logger (propagates to all taris.* children)
    taris_log = logging.getLogger("taris-tgbot")
    # Avoid duplicate handlers on hot-reload
    if not any(isinstance(h, ErrorCaptureHandler) for h in taris_log.handlers):
        taris_log.addHandler(handler)

    if _observer_thread and _observer_thread.is_alive():
        return

    _stop_event.clear()
    _observer_thread = threading.Thread(
        target=_observer_loop, daemon=True, name="err-observer"
    )
    _observer_thread.start()
    log.debug("[ErrObs] observer started (auto_threshold=%d, cooldown=%ds)",
              _AUTO_REPORT_THRESHOLD, _AUTO_REPORT_COOLDOWN)


def stop_observer() -> None:
    """Stop the observer thread cleanly."""
    _stop_event.set()
    log.debug("[ErrObs] observer stopped")
