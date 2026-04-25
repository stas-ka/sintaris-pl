---
name: taris-error-review
description: >
  Review open error reports in errors/, guide root-cause analysis, implement fixes,
  add regression tests, and mark errors as resolved with a commit. Use when:
  reviewing reported bugs, diagnosing log errors, running post-deploy error triage,
  or starting a new development session to check for pending issues.
argument-hint: >
  all | open | <folder-name> | since:<YYYY-MM-DD>
---

# taris-error-review Skill

## Purpose

Review error reports committed to `errors/` by the Taris Error Observer Agent,
diagnose root causes, implement fixes, and mark them as resolved.

---

## Step 1 — Scan for Open Reports

```powershell
# List all open/unresolved error folders
Get-ChildItem errors\ -Directory | ForEach-Object {
  $mf = Join-Path $_.FullName "manifest.json"
  if (Test-Path $mf) {
    $m = Get-Content $mf | ConvertFrom-Json
    if ($m.status -ne "resolved") {
      Write-Host "🔴 $($_.Name)  [$($m.severity)]  $($m.created)"
    }
  }
}
```

Or use git log to see recent error commits:
```bash
git log --oneline --grep="^error:" -- errors/
```

---

## Step 2 — Read Each Open Error

For each open report `errors/<folder>/`:

```powershell
# Read description
Get-Content "errors\<folder>\description.md"
# Read log excerpt
Get-Content "errors\<folder>\log_excerpt.txt"
# Read user text messages
Get-ChildItem "errors\<folder>\text_*.txt" | ForEach-Object { Get-Content $_ }
```

**Required reading order:**
1. `description.md` — summary, severity, reporter, bot version, resolution checklist
2. `log_excerpt.txt` — actual log lines around the error
3. `text_*.txt` — user description if reporter_type = "user"
4. Photos/screenshots if present

---

## Step 3 — Diagnose Root Cause

Use grep/glob to find the relevant code:

```bash
# Find the function/module mentioned in the log
grep -n "ErrorKeyword\|FunctionName" src/ -r

# Check recent commits that touched related files
git log --oneline -10 -- src/features/<module>.py

# Check if a test already covers this path
grep -n "def t_.*keyword" src/tests/test_voice_regression.py
```

**Lessons Learned checklist (from `doc/lessons-learned.md`):**
- Was the error a missing dependency? → add install check test
- Was the error a silent failure? → add error surfacing + test
- Was the error format/type mismatch? → add validation + test
- Was the error caused by stale deployed code? → check service restart rule

---

## Step 4 — Implement the Fix

Follow patterns from `.github/instructions/bot-coding.instructions.md`:

```python
# Example fix pattern
def _handle_something(chat_id: int) -> None:
    try:
        result = _do_operation()
    except SpecificError as e:
        log.error(f"[Module] operation failed for {chat_id}: {e}")
        bot.send_message(chat_id, _t(chat_id, "error_generic"))
        return
```

**Mandatory with every fix:**
1. Add regression test (next T-number in `test_voice_regression.py` or appropriate test file)
2. Update `doc/lessons-learned.md` with one row
3. Update `doc/test-suite.md` if a new test ID is added

---

## Step 5 — Run Tests

```bash
# Quick offline suite
cd D:\Projects\workspace\sintaris-openclaw
PYTHONPATH=src python -m pytest src/tests/telegram/ src/tests/screen_loader/ src/tests/llm/ -q --tb=short

# Targeted test for the specific fix
PYTHONPATH=src python src/tests/test_voice_regression.py --test <test_func_name>
```

---

## Step 6 — Mark as Resolved

Update the manifest.json:

```powershell
$mf = "errors\<folder>\manifest.json"
$m = Get-Content $mf | ConvertFrom-Json
$m.status = "resolved"
$m.resolved_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
$m.resolved_commit = (git rev-parse HEAD)
$m | ConvertTo-Json -Depth 5 | Set-Content $mf
```

Or let the bot regenerate: update only `manifest.json` status field.

---

## Step 7 — Commit the Fix

```bash
git add errors/<folder>/manifest.json doc/lessons-learned.md src/tests/...
git commit -m "fix: resolve <error-name>

- Root cause: <one line>
- Fix: <what was changed>
- Test: T<NNN> added (<test_func_name>)
- Ref: errors/<folder>

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

---

## Error Report Structure

```
errors/
  README.md                      ← auto-generated index (do not edit)
  YYYYMMDD-HHMMSS_error_name/
    manifest.json                ← {id, name, status, severity, reporter_type,
    │                               reporter_chat_id, created, bot_version,
    │                               target, log_lines, texts, voices, photos,
    │                               resolved_at, resolved_commit}
    description.md               ← human-readable summary + resolution checklist
    log_excerpt.txt              ← ERROR/WARNING/CRITICAL lines from bot log
    text_01.txt                  ← user description text (if reporter_type=user)
    photo_01.jpg                 ← screenshot (if submitted)
    voice_01.ogg                 ← voice note (if submitted)
```

### Status values

| Status | Meaning |
|---|---|
| `open` | New error, not yet investigated |
| `investigating` | Developer is actively working on it |
| `resolved` | Fix deployed and verified |

### Severity values

| Severity | Icon | Meaning |
|---|---|---|
| `critical` | 🚨 | Bot crash, data loss, security issue |
| `high` | ❗ | Feature broken for all users |
| `medium` | ⚠️ | Feature broken for some users |
| `low` | ℹ️ | Minor inconvenience or cosmetic |

---

## Reporter Types

| reporter_type | Source |
|---|---|
| `user` | Admin submitted via Telegram → Admin menu → Report Error |
| `log_observer` | Auto-detected by `bot_error_observer.py` background thread |

---

## Configuration (bot.env)

| Variable | Default | Description |
|---|---|---|
| `GIT_ERRORS_DIR` | `` (empty) | Absolute path to `errors/` in project repo. Enable to activate git integration. |
| `ERROR_GIT_AUTO_PUSH` | `1` | Set to `0` to commit but not push automatically. |
| `ERROR_AUTO_THRESHOLD` | `3` | Number of ERROR records in one window before auto-report. |
| `ERROR_AUTO_COOLDOWN` | `300` | Seconds between auto-reports (flood prevention). |

### Setting GIT_ERRORS_DIR on targets

```bash
# TariStation2 (IniCoS-1)
echo "GIT_ERRORS_DIR=/home/stas/projects/sintaris-pl/errors" >> ~/.taris/bot.env

# TariStation1 (SintAItion)
echo "GIT_ERRORS_DIR=/home/stas/projects/sintaris-pl/errors" >> ~/.taris/bot.env

# VPS Docker (needs git credentials in container — optional)
# Set in /opt/taris-docker/bot.env:
# GIT_ERRORS_DIR=/opt/taris-docker/app/errors
```

---

## Quick Triage View

```bash
# All open errors sorted newest first
for d in errors/*/; do
  status=$(python3 -c "import json; m=json.load(open('${d}manifest.json')); print(m.get('status','?'))")
  if [ "$status" = "open" ]; then
    echo "🔴 $d — $(python3 -c "import json; m=json.load(open('${d}manifest.json')); print(m['name'])")"
  fi
done 2>/dev/null

# PowerShell equivalent
Get-ChildItem errors -Directory | ForEach-Object {
  $m = Get-Content "$($_.FullName)\manifest.json" -ErrorAction SilentlyContinue | ConvertFrom-Json
  if ($m -and $m.status -ne "resolved") { "🔴 $($_.Name): $($m.name) [$($m.severity)]" }
}
```

---

> **Reference:** `src/features/bot_error_observer.py` · `src/features/bot_error_protocol.py` · `doc/lessons-learned.md`
