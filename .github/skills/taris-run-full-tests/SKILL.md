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

| Cat | Suite | Location | Command | Network/Hardware? |
|-----|-------|----------|---------|-----------------|
| F | Telegram offline | `src/tests/telegram/` | `pytest ... -q` | No |
| G | Screen DSL loader | `src/tests/screen_loader/` | `pytest ... -q` | No |
| H | LLM providers | `src/tests/llm/` | `pytest ... -q` | No |
| A0 | Voice regression (source inspection T17–T55+) | `src/tests/test_voice_regression.py` | `python3 ...` | No |
| A0+ | Extended source inspection (T56–T232) | `src/tests/test_voice_regression.py` | `python3 ... --test <name>` | No |
| A | Voice regression (hardware T01–T16) | Pi target | `plink ... python3 ...` | Pi required |
| N8N | CRM / N8N (T40–T49) | `src/tests/test_n8n_crm.py` | `python3 ...` | N8N (live) |
| KB | Remote KB / MCP (T200–T232) | `src/tests/test_remote_kb.py` | `python3 ...` | VPS Postgres (live) |
| CAMP | Campaign state machine (T130–T137) | `src/tests/test_campaign.py` | `pytest ... -m "not live"` | No (source) |
| CS | Content strategy (T_CS_01–T_CS_20) | `src/tests/test_content_strategy.py` | `pytest ... -q` | No (source) |
| CN | Content N8N live (T_CN_01–T_CN_12) | `src/tests/test_content_n8n.py` | `pytest ... -m live` | N8N (live) |
| J | Data consistency | `src/tests/test_data_consistency.py` | `python3 ...` | DB (target) |
| B | Web UI Playwright | `src/tests/ui/` | `pytest --base-url ... --browser chromium` | Web server |
| I | External internet UI | `src/tests/ui/test_external_ui.py` | `pytest ... --browser chromium` | VPS public |
| E | Smoke / deployment | journal + target test run | varies | Target SSH |

---

## Quick Local Run (No Pi, ~40s)

Runs categories F + G + H and source-inspection voice tests (T17–T55+):

```bash
cd /home/stas/projects/sintaris-pl
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest \
  src/tests/telegram/ src/tests/screen_loader/ src/tests/llm/ \
  -q --tb=short
```

Then source-inspection voice regression (core T-set):
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
  t_voice_system_mode_routing_guard t_voice_lang_stt_lang_priority \
  t_set_lang_default_not_hardcoded_en t_voice_system_admin_guard \
  t_rbac_allowlist_enforcement t_dev_menu_rbac t_security_events_logging \
  t_admin_only_rag_access t_migrate_postgres_structure t_contacts_store_parity \
  t_guest_user_feature t_prompt_templates t_variant_config
```

---

## Campaign / CRM / N8N Tests

Source inspection only (no network):
```bash
PYTHONPATH=src python3 -m pytest src/tests/test_campaign.py -m "not live" -q --tb=short
PYTHONPATH=src python3 -m pytest src/tests/test_content_strategy.py -m "not live" -q
```

Live integration (requires N8N credentials in .env):
```bash
source .env
PYTHONPATH=src python3 -m pytest src/tests/test_n8n_crm.py -v
PYTHONPATH=src python3 -m pytest src/tests/test_content_n8n.py -v -m live
```

---

## Remote KB / MCP Tests (T200–T232)

Source inspection only:
```bash
PYTHONPATH=src python3 src/tests/test_remote_kb.py --offline
```

Live (requires VPS Postgres):
```bash
source .env
KB_PG_DSN="$KB_PG_DSN" PYTHONPATH=src python3 src/tests/test_remote_kb.py
```

---

## Data Consistency Tests (Category J)

Run before any backup or after migration:
```bash
# Local / TariStation2
python3 ~/.taris/tests/test_data_consistency.py

# VPS Docker
sshpass -p "$VPS_PWD" ssh $VPS_USER@$VPS_HOST \
  "docker exec taris-vps-telegram python3 /app/tests/test_data_consistency.py"
```

---

## Full Voice Regression (Pi target required)

### On PI2 (engineering target) — run before committing

```bash
# TariStation2 (OpenClaw local):
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py

# Or on Taris PI2 (OpenClawPI2):
plink -pw "$HOSTPWD2" -batch stas@OpenClawPI2 \
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
| `src/features/bot_voice.py`, `src/core/bot_config.py` | A0 + F + H |
| `src/ui/*.py`, `src/screens/*.yaml` | G |
| `src/core/bot_llm.py` | H + A0 (T56–T57, T81–T83) |
| `src/telegram_menu_bot.py`, `src/telegram/` | F |
| `src/bot_web.py`, `src/web/` | B (Playwright) |
| `src/strings.json` | A0 (T13 only) |
| `src/features/bot_campaign.py` | CAMP + CS |
| `src/features/bot_crm.py`, `store_crm.py` | N8N + CAMP |
| `src/features/bot_remote_kb.py`, `bot_mcp_client.py` | KB (T200–T232) |
| `src/features/bot_content.py` | CS |
| `src/features/bot_n8n.py` | N8N + CN |
| `src/core/bot_db.py`, `store_*.py` | A0 (T22–T23, T111–T113) |
| `src/setup/migrate_*.py` | A0 (T111, T113, T23) + J (data consistency) |
| Any | Quick local run (F + G + H + A0 core set) first |

---

## Reporting

After a full run, paste summary table in commit message:
```
Tests: 40 F-pass | 64 G-pass | 18 H-pass | T17–T55 A0-pass (src-inspect) | T130–T137 CAMP-pass
```

Full test suite summary format:
```
Cat F (Telegram):     40/40 PASS
Cat G (Screen DSL):   64/64 PASS
Cat H (LLM):          18/18 PASS
Cat A0 (src-inspect): NN/NN PASS  [T17–T55+]
Cat CAMP (Campaign):   7/7  PASS  [T130–T137]
Cat N8N (CRM):         4/4  PASS  [T40–T43]  (if live)
Cat KB (Remote KB):   NN/NN PASS  [T200–T232] (if live)
Cat B (Playwright):   43/43 PASS  (if web running)
```

Baseline for voice hardware tests lives on Pi: `~/.taris/tests/voice/results/baseline.json`  
Reset after re-image: `python3 test_voice_regression.py --set-baseline`

> **Reference:** See [`doc/test-strategy.md`](../../../doc/test-strategy.md) for the full test layer strategy and decision matrix.
