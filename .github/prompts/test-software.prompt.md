---
mode: agent
description: Determine which tests to run based on recent changes and execute them. Use this when the user says "test software", "run tests", or similar plain-text requests.
---

# Test Software — Automatic Test Selector

Inspect recent changes and choose the right tests automatically.

## Step 1 — Identify changed files
```bash
git diff --name-only HEAD~1 HEAD
```
(Or `git status` if changes are not yet committed.)

## Step 2 — Choose tests based on what changed

| Changed file(s) | Tests to run |
|---|---|
| `src/bot_voice.py`, `src/bot_config.py`, `src/bot_access.py`, `src/setup/setup_voice.sh` | **Voice regression T01–T21** → use `run-tests` prompt |
| `src/strings.json` | **T13** `i18n_string_coverage` + **T17** `bot_name_injection` |
| `src/telegram_menu_bot.py` (calendar section) | **T20** `calendar_tts_call_signature`, **T21** `calendar_console_classifier` |
| `src/telegram_menu_bot.py` (notes section) | **T19** `note_edit_append_replace` |
| `src/telegram_menu_bot.py` (profile section) | **T18** `profile_resilience` |
| `src/bot_web.py`, `src/templates/`, `src/static/` | **Web UI Playwright tests** (run locally vs. live Pi) |
| Any Python file | **Full voice regression suite** as a safety net |

## Step 3 — Run selected tests

### Voice regression (default safety net)
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.picoclaw/tests/test_voice_regression.py"
```

### Single test group (replace `tts` with the group name from T01–T21)
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.picoclaw/tests/test_voice_regression.py --test tts"
```

### Web UI tests (run locally, target must be reachable)
```bat
py -m pytest src/tests/ui/test_ui.py -v --base-url https://openclawpi:8080 --browser chromium
```

## Step 4 — Interpret results

| Result | Action |
|--------|--------|
| All `PASS` | ✅ Done — commit or deploy as needed. |
| Any `FAIL` | Fix before committing. Do NOT skip. |
| `WARN` | Performance regression. Investigate or update baseline. |
| `SKIP` | OK for optional components (Whisper, VAD, German models). |

## Step 5 — Report

Summarise the test results in your response with the pass/fail table.  
If all pass → ask the user: "Tests passed ✅. Ready to deploy?"
