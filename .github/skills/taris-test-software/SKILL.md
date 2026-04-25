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
| `src/features/bot_voice.py`, `src/core/bot_config.py` | Voice regression T07–T41, cat F |
| `src/telegram/bot_access.py` (`_escape_tts`) | T07, T08 |
| `src/setup/setup_voice.sh` | T01–T09 (after reinstall on Pi) |
| `src/strings.json` | T13 `i18n_string_coverage` — **always** |
| `src/prompts.json` | T115 `bot_capabilities_tag_fix` |
| `src/telegram_menu_bot.py` (calendar) | T20, T21, T158–T161, cat F |
| `src/telegram_menu_bot.py` (notes) | T19, T51–T53, cat F |
| `src/telegram_menu_bot.py` (profile) | T18, cat F |
| `src/telegram_menu_bot.py` (RBAC/security) | T70, T71, T116, cat F |
| `src/telegram_menu_bot.py` (guest/roles) | T140–T157, cat F |
| `src/telegram_menu_bot.py` (any callback) | cat F (all telegram offline tests) |
| `src/core/bot_llm.py` | cat H + T56–T57 + T81–T83 |
| `src/ui/*.py`, `src/screens/*.yaml` | cat G (screen DSL loader) |
| `src/bot_web.py`, `src/web/` | cat B (Web UI Playwright) |
| `src/core/bot_state.py` | T25 `web_link_code` |
| `src/core/bot_db.py`, `src/core/store_sqlite.py` | T22, T23 |
| `src/core/store_postgres.py` | T112–T113 |
| `src/core/bot_rag.py`, `src/core/bot_embeddings.py` | T76–T80, T200–T205 |
| `src/core/bot_security.py` | T70–T71, T116, cat F |
| `src/core/bot_mcp_client.py` | T200–T232 (KB tests) |
| `src/features/bot_campaign.py` | T130–T137, T_CS_01–T_CS_20 |
| `src/features/bot_crm.py`, `src/core/store_crm.py` | T40–T49, T130–T137 |
| `src/features/bot_remote_kb.py` | T200–T232 (`test_remote_kb.py`) |
| `src/features/bot_content.py` | T_CS_01–T_CS_20 |
| `src/features/bot_n8n.py` | T40–T43, T_CN_01–T_CN_12 |
| `src/setup/migrate_*.py` | T111, T113, T23 (migration tests) |
| Any Python file | Quick local run (cat F + G + H + source inspection) always |

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
  t_voice_system_mode_routing_guard t_voice_lang_stt_lang_priority \
  t_set_lang_default_not_hardcoded_en t_voice_system_admin_guard \
  t_rbac_allowlist_enforcement t_dev_menu_rbac t_security_events_logging \
  t_admin_only_rag_access t_migrate_postgres_structure t_contacts_store_parity \
  t_guest_user_feature t_prompt_templates t_variant_config
```

### Campaign / CRM / Content tests (source inspection)

```bash
PYTHONPATH=src python3 -m pytest \
  src/tests/test_campaign.py src/tests/test_content_strategy.py \
  -q --tb=short -m "not live"
```

### Remote KB tests (source inspection / offline)

```bash
PYTHONPATH=src python3 src/tests/test_remote_kb.py --offline
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
| All `PASS` | ✅ Proceed to Step 5 — E2E on deployed target |
| Any `FAIL` | Fix before committing. Do NOT skip. |
| `WARN` | Performance regression. Investigate or update baseline. |

---

## Step 5 — E2E Tests on Deployed Target *(mandatory)*

> **Local tests passing is NOT sufficient. After any deploy, run the E2E test suite on the target itself. The task is not complete until deployed-target tests pass.**

If the change has already been deployed to a target, run the appropriate E2E tests:

### OpenClaw targets

```bash
source /home/stas/projects/sintaris/sintaris-pl/.env

# TariStation2 (local — after local deploy)
DEVICE_VARIANT=openclaw PYTHONPATH=~/.taris python3 ~/.taris/tests/test_voice_regression.py

# TariStation1 / SintAItion (after TS1 deploy)
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@$OPENCLAW1_HOST \
  "PYTHONPATH=~/.taris python3 ~/.taris/tests/test_voice_regression.py"

# VPS-Supertaris (Docker — after VPS deploy)
sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST \
  "docker exec taris-vps-telegram python3 /app/tests/test_voice_regression.py"

# VPS-Supertaris KB tests (if KB / bot_remote_kb.py changed)
sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST \
  "docker exec -e KB_PG_DSN=postgresql://taris:zusammen2019@127.0.0.1:5432/taris_kb \
   taris-vps-telegram python3 /app/tests/test_remote_kb.py"
```

### Raspberry Pi targets

```bash
# PI2 (engineering — after PI2 deploy)
plink -pw "$TARGET2PWD" -batch stas@OpenClawPI2 \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"

# PI1 (production — after PI1 deploy)
plink -pw "$HOSTPWD" -batch stas@OpenClawPI \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"
```

**Report to user:** `"E2E on <target>: N/N pass ✅"` or list failures.  
**If tests fail on target:** stop, diagnose, fix, redeploy, re-run before marking task done.
| `SKIP` | OK for optional components (Whisper, VAD, German models). |

---

## Step 5 — Report

Summarise results in response with pass/fail table.
If all pass → ask: **"Tests passed ✅. Ready to deploy?"**

---

## Continuous Test Improvement

Every bug fix **must** add a regression test. Every new feature **must** add tests covering the happy path and main failure modes.

See [`doc/test-strategy.md`](../../../doc/test-strategy.md) for:
- Full test layer strategy and decision matrix
- T-number allocation registry
- Coverage gaps and roadmap
- Lessons-learned protocol for extending tests

See [`doc/test-suite.md`](../../../doc/test-suite.md) for the complete T-number registry with run commands.
