---
name: taris-test-software
description: >
  Determine which tests to run based on recently changed files and execute them.
  Use when the user says "test software", "run tests", or similar.
argument-hint: >
  Optional: list of changed files (space-separated). If omitted, reads git diff.
---

## Step 1 — Identify changed files

```bash
git diff --name-only HEAD~1 HEAD
# Or if changes are not yet committed:
git status --short
```

---

## Step 2 — Choose tests based on what changed

| Changed file(s) | Tests to run |
|---|---|
| `src/features/bot_voice.py`, `src/core/bot_config.py` | Voice regression T01–T41 |
| `src/telegram/bot_access.py` (`_escape_tts`) | T07, T08 |
| `src/setup/setup_voice.sh` | T01–T09 (after reinstall) |
| `src/strings.json` | T13 `i18n_string_coverage` + T17 `bot_name_injection` |
| `src/telegram_menu_bot.py` (calendar section) | T20, T21 |
| `src/telegram_menu_bot.py` (notes section) | T19 |
| `src/telegram_menu_bot.py` (profile section) | T18 |
| `src/telegram_menu_bot.py` (any callback) | Category F (telegram offline) |
| `src/core/bot_llm.py` | Category H (LLM tests) |
| `src/ui/*.py`, `src/screens/*.yaml` | Category G (screen loader) |
| `src/bot_web.py`, `src/web/` | Category B (Web UI Playwright) |
| `src/core/bot_state.py` | T25 `web_link_code` |
| `src/core/store_sqlite.py`, `src/core/bot_db.py` | T22, T23 |
| Any Python file | Full voice regression + Categories F, G, H as safety net |

---

## Step 3 — Run selected tests

### Quick local run (Categories F + G + H — always run first)

```bash
cd /home/stas/projects/sintaris-pl
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest \
  src/tests/telegram/ src/tests/screen_loader/ src/tests/llm/ \
  -q --tb=short
```

### Voice regression (source inspection, no Pi needed)

```bash
DEVICE_VARIANT=openclaw PYTHONPATH=src \
  python3 src/tests/test_voice_regression.py \
  --test t_confidence_strip t_tts_escape t_i18n_string_coverage t_lang_routing \
  t_bot_name_injection t_profile_resilience t_note_edit_append_replace \
  t_calendar_tts_call_signature t_calendar_console_classifier \
  t_db_voice_opts_roundtrip t_db_migration_idempotent \
  t_web_link_code_roundtrip t_system_chat_clean_output \
  t_openclaw_stt_routing t_openclaw_ollama_provider \
  t_voice_system_mode_routing_guard t_voice_lang_stt_lang_priority
```

### Full voice regression (requires Pi)

```bash
# Engineering target (always first)
plink -pw "$HOSTPWD" -batch stas@OpenClawPI2 \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"

# Production (only after engineering passes + code on master)
plink -pw "$HOSTPWD" -batch stas@OpenClawPI \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"
```

### Single test group

```bash
DEVICE_VARIANT=openclaw PYTHONPATH=src \
  python3 src/tests/test_voice_regression.py --test tts
```

### Web UI Playwright

```bash
python3 -m pytest src/tests/ui/test_ui.py -v \
  --base-url https://openclawpi2:8080 --browser chromium
```

---

## Step 4 — Interpret results

| Result | Action |
|---|---|
| All `PASS` | ✅ Done — commit or deploy as needed |
| Any `FAIL` | Fix before committing. Do NOT skip. |
| `WARN` | Performance regression. Investigate or update baseline. |
| `SKIP` | OK for optional components (Whisper, VAD, German models). |

---

## Step 5 — Report

Summarise results in response with pass/fail table.
If all pass → ask: **"Tests passed ✅. Ready to deploy?"**

---

## Continuous Test Improvement

Every bug fix **must** add a regression test. Every new feature **must** add tests covering the happy path and main failure modes. See `doc/test-suite.md` for test ID conventions and category table.
