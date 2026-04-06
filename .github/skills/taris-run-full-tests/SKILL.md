---
name: taris-run-full-tests
description: >
  Run the full taris test suite across all categories: offline unit tests
  (telegram, screen_loader, LLM), voice regression (local source-inspection
  and Pi), Web UI Playwright, and smoke tests. Reports pass/fail per category.
argument-hint: >
  Scope: all | quick | voice | llm | screen | telegram | ui | smoke
  Target: local | pi2 | pi1 (default: local for quick, pi2 for full voice)
---

## Test Categories

| Cat | Suite | Location | Command | Pi required? |
|-----|-------|----------|---------|-------------|
| F | Telegram offline | `src/tests/telegram/` | `pytest ... -q` | No |
| G | Screen DSL loader | `src/tests/screen_loader/` | `pytest ... -q` | No |
| H | LLM providers | `src/tests/llm/` | `pytest ... -q` | No |
| A | Voice regression (source inspection T01-T41) | `src/tests/test_voice_regression.py` | `python3 ...` | No (for source tests) |
| A | Voice regression (hardware T01-T16) | Pi target | `plink ... python3 ...` | Yes (Pi) |
| B | Web UI Playwright | `src/tests/ui/` | `pytest --base-url ... --browser chromium` | Yes (Web server) |
| E | Smoke | manual or Playwright smoke | varies | Yes |

---

## Quick Local Run (No Pi, ~5s)

Runs categories F + G + H and source-inspection voice tests (T17–T41):

```bash
cd /home/stas/projects/sintaris-pl
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest \
  src/tests/telegram/ src/tests/screen_loader/ src/tests/llm/ \
  -q --tb=short
```

Then source-inspection voice regression:
```bash
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py \
  --test t_confidence_strip t_tts_escape t_i18n_string_coverage t_lang_routing \
  t_bot_name_injection t_profile_resilience t_note_edit_append_replace \
  t_calendar_tts_call_signature t_calendar_console_classifier \
  t_db_voice_opts_roundtrip t_db_migration_idempotent t_rag_lr_products \
  t_web_link_code_roundtrip t_system_chat_clean_output t_openclaw_stt_routing \
  t_openclaw_ollama_provider t_web_stt_provider_routing t_pipeline_logger \
  t_dual_stt_providers t_voice_debug_mode t_stt_language_routing_fw \
  t_stt_fallback_chain t_tts_multilang t_voice_llm_routing \
  t_voice_system_mode_routing_guard t_voice_lang_stt_lang_priority
```

---

## Full Voice Regression (Pi target required)

### On PI2 (engineering target) — run before committing

```bash
# TariStation2 (OpenClaw local):
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py

# Or on Taris PI2 (OpenClawPI2):
plink -pw "$HOSTPWD" -batch stas@OpenClawPI2 \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"
```

### On PI1 (production) — run only after PI2 passes and code is on master

```bash
plink -pw "$HOSTPWD" -batch stas@OpenClawPI \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"
```

---

## Web UI Playwright (requires taris-web running)

```bash
# Target: TariStation2 (local web server at :8080)
DEVICE_VARIANT=openclaw PYTHONPATH=src \
  python3 -m pytest src/tests/ui/test_ui.py -v \
  --base-url http://localhost:8080 --browser chromium

# Target: OpenClawPI2
python3 -m pytest src/tests/ui/test_ui.py -v \
  --base-url https://openclawpi2:8080 --browser chromium
```

---

## Pass / Fail Rules

| Result | Action |
|--------|--------|
| All PASS | Proceed to commit / deploy |
| Any FAIL | Fix before committing — never deploy a failing test |
| WARN (>30% slower than baseline) | Investigate; if intentional run `--set-baseline` |
| SKIP | OK for optional features (Whisper, VAD, Ollama not running) |

---

## Decision Table — Which Categories to Run

| Changed files | Run categories |
|---|---|
| `src/features/bot_voice.py`, `src/core/bot_config.py` | A + F + H |
| `src/ui/*.py`, `src/screens/*.yaml` | G + F |
| `src/core/bot_llm.py` | H |
| `src/telegram_menu_bot.py`, `src/telegram/` | F |
| `src/bot_web.py`, `src/web/` | B |
| `src/strings.json` | T13 (i18n) + F |
| Any | Quick local run (F + G + H) first, then voice regression |

---

## Reporting

After a full run, paste summary table in commit message:
```
Tests: 40 F-pass | 64 G-pass | 18 H-pass | T01-T41 A-pass (src-inspect)
```

Baseline for voice hardware tests lives on Pi: `~/.taris/tests/voice/results/baseline.json`
Reset after re-image: `python3 test_voice_regression.py --set-baseline`
