---
mode: agent
description: Run the full taris test suite — telegram offline, screen loader, LLM, voice regression, and Web UI Playwright.
---

Run the full taris test suite as described in `.github/skills/taris-run-full-tests/SKILL.md`.

**Scope:** ${input:scope:all | quick | voice | llm | screen | telegram | ui | smoke (default: quick)}
**Target:** ${input:target:local | pi2 | pi1 (default: local)}

## Steps

1. Read `.github/skills/taris-run-full-tests/SKILL.md` and `doc/test-suite.md` for the complete test strategy.

2. Based on scope, select the categories to run using the Decision Table.

3. **Quick local run** (always run first, regardless of scope):
```bash
cd /home/stas/projects/sintaris-pl
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest \
  src/tests/telegram/ src/tests/screen_loader/ src/tests/llm/ \
  -q --tb=short
```

4. **Source-inspection voice regression** (categories T17–T41, no Pi needed):
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

5. **If scope includes voice or all AND target is pi2**: run full voice regression on TariStation2/OpenClawPI2:
```bash
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py
```

6. **If scope includes ui**: run Web UI Playwright:
```bash
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest \
  src/tests/ui/test_ui.py -v --base-url http://localhost:8080 --browser chromium
```

7. Report results:
   - Summarize pass/fail/warn/skip counts per category
   - List any FAIL with file and assertion details
   - Recommend action (fix, investigate, set-baseline, or deploy-ready)

## Pass Criteria

- Zero FAIL across all selected categories
- WARNs documented and either accepted or investigated
- SKIPs only for missing optional hardware/services
