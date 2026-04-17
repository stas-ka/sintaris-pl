# Merge Report: Taris-UI-POC → taris-openclaw
**Date:** 2026-03-28  
**Merged into:** `taris-openclaw` branch  
**Resulting version:** `v2026.3.43`  
**Method:** Cherry-pick (not `git merge`, to preserve all OpenClaw-specific fixes)  
**Pre-merge tag:** `pre-merge-ui-poc-2026-03-28`

---

## Summary

Successfully merged 9 POC commits from `Taris-UI-POC` (v2026.4.13) into `taris-openclaw` using selective cherry-pick. All OpenClaw-specific features were preserved; Screen DSL, FTS5/RAG, and admin i18n fixes were integrated.

---

## What Was Merged ✅

### Phase 1 — Admin & UI Fixes (`333f210`)
| Item | Detail |
|---|---|
| Admin menu i18n fix | `_admin_keyboard(chat_id)` — all 24 button labels now use `_t(chat_id, ...)` instead of hardcoded English |
| System Chat moved to admin | Removed from `main_menu.yaml`, added to `admin_menu.yaml` as admin-only |
| `admin_btn_system` i18n key | Added to `strings.json` (ru/en/de) |
| `render_telegram.py` fix | Screen title no longer double-escaped/bold-wrapped |
| `chat.html` layout fix | Send button oversized by Pico CSS; explicit flex constraints added |
| `.github/` PI1/PI2 rules | Deploy branch rules added to bot-deploy instructions |

### Phase 2 — Screen DSL (`606ec57`, `7a48543`, `3628079`)
| Item | Detail |
|---|---|
| `src/ui/screen_loader.py` | Confirmed/stabilized: YAML/JSON declarative loader, variant support (`visible_variants`), schema validation |
| `_render()` + `_screen_ctx()` | DSL render helpers in `bot_handlers.py` |
| `screen.schema.json` | JSON Schema draft-07 for all 10 widget types |
| YAML screens confirmed | `notes_menu`, `note_view`, `note_raw`, `note_edit`, `profile`, `profile_lang`, `profile_my_data`, `help`, `main_menu`, `admin_menu` |
| Screen DSL unit tests | 64 tests — all pass locally |
| `GET /screen/{screen_id}` | Web UI dynamic screen route in `bot_web.py` |
| pyyaml | Added to `deploy/requirements.txt` |

### Phase 3 — FTS5/RAG Knowledge Base (`a39a368`)
| Item | Detail |
|---|---|
| `bot_config.py` constants | `RAG_ENABLED`, `RAG_TOP_K`, `RAG_CHUNK_SIZE`, `RAG_FLAG_FILE` |
| `bot_documents.py` | Document upload / list / delete pipeline (already in HEAD) |
| `store_sqlite.search_fts()` | FTS5 full-text search (already in HEAD) |
| RAG context injection | Free-chat and voice handlers |
| Admin RAG panel | 📚 Knowledge button in admin menu |
| RAG i18n keys | 16+ keys in `strings.json` (ru/en/de) |

### Phase 4 — Research Docs (`b938b7e`)
| Item | Detail |
|---|---|
| `concept/rag-memory-architecture.md` | RAG & memory architecture concept paper |
| `concept/rag-memory-extended-research.md` | Extended research with Karpathy AutoResearch section |
| `TODO.md §23` | Research roadmap added |

---

## What Was NOT Merged ❌

| Item | Reason | Priority |
|---|---|---|
| POC's `bot_config.py` version `2026.4.x` numbers | OpenClaw uses its own version sequence (`2026.3.x`) | n/a — intentional |
| POC's `release_notes.json` 2026.4.x entries | History kept in POC branch only; not relevant for openclaw sequence | Low |
| POC's simplified `_admin_keyboard()` (without RAG/openclaw buttons) | OpenClaw has additional buttons: RAG menu, OpenClaw gateway | Kept openclaw version |
| POC's `bot_handlers.py` without `DEVICE_VARIANT` import | OpenClaw needs variant-based routing | Kept openclaw version |
| POC's `screen_loader.py` without `visible_variants` | OpenClaw screens use `visible_variants: [openclaw]` | Kept openclaw version |
| POC's `UserContext` without `variant` field | OpenClaw uses `variant=DEVICE_VARIANT` | Kept openclaw version |
| `38e4613`, `cfa03f5` (Karpathy research additions) | Empty cherry-picks — content already in HEAD | n/a — already merged |

---

## Conflict Resolution Summary

| File | Conflict Type | Resolution |
|---|---|---|
| `src/telegram/bot_admin.py` | `_admin_keyboard()` layout | Keep HEAD (i18n buttons), add `admin_btn_system` from POC, remove duplicate |
| `src/ui/screen_loader.py` (5 conflicts) | add/add + variant support | Keep HEAD (advanced: `visible_variants`, `_validate_screen`, `_HAS_JSONSCHEMA`) |
| `src/bot_web.py` (3 conflicts) | imports + REST API section | Keep HEAD (all OpenClaw imports + REST API routes) |
| `src/tests/screen_loader/test_screen_loader.py` | add/add (3 conflicts) | Keep HEAD (TestMainMenuYaml + TestAdminMenuYaml + variant tests) |
| `src/telegram/bot_handlers.py` | `UserContext` constructor | Keep HEAD (`variant=DEVICE_VARIANT`) |
| `src/strings.json` (3×3 conflicts) | RAG + openclaw keys | Keep HEAD (has openclaw-specific keys) |
| `src/core/bot_config.py` (multiple) | BOT_VERSION | Keep HEAD version sequence |
| `src/release_notes.json` (multiple) | Release history | Keep HEAD (openclaw 2026.3.x sequence at top) |
| `TODO.md` (multiple) | Section additions | Keep HEAD content |

---

## Test Results (Post-Merge)

| Suite | Result |
|---|---|
| Voice regression (`test_voice_regression.py`) | **62 PASS** / 5 FAIL (pre-existing) / 20 SKIP |
| Screen DSL (`test_screen_loader.py`) | **64 PASS** / 0 FAIL |
| Pre-merge baseline | 61 PASS / 5 FAIL / 21 SKIP |
| Delta | +1 PASS, 0 new FAILs |

Pre-existing FAILs (not caused by merge):
- `t_piper_model_files` — piper binary path mismatch (`/usr/local/bin/piper` vs actual)
- `note_edit_append_replace` — Append option missing
- `db_migration_idempotent` — migration script path issue

---

## Commits Created

| Commit | Message |
|---|---|
| `e5ff54b` | cherry-pick 333f210: Fix admin menu i18n, move System Chat to admin, fix chat layout |
| `0d9c6c5` | cherry-pick 606ec57: Screen DSL Loader Phase 1+2 (TODO 21.1-21.2) |
| `64a5a36` | cherry-pick a39a368: FTS5/RAG knowledge base + document management |
| `0e835db` | docs: RAG & Memory Architecture concept papers + TODO §23 research roadmap |
| `b83b04b` | v2026.3.43: Merge Taris-UI-POC features (Screen DSL + RAG + admin i18n) |

---

## OpenClaw-Specific Features Preserved ✅

All of the following were present in `taris-openclaw` before the merge and are still intact:

- `DEVICE_VARIANT` constant and `visible_variants` screen filtering
- `UserContext(variant=DEVICE_VARIANT)` in all DSL render calls
- Password reset flow (`/admin` route, `_web_account_block()`, `bot_users.py`)
- Voice debug mode (`VOICE_DEBUG_MODE`, debug session endpoints)
- Dual STT pipeline: faster-whisper primary + Vosk fallback
- `_voice_lang()` helper (TTS uses STT language, not Telegram UI language)
- Voice mode system chat dispatch (`_cur_mode == "system"` → `_handle_system_message()`)
- OpenAI LLM provider (gpt-4o-mini) with Ollama fallback
- `_409Handler` fast-retry (1s sleep)
- Unified user list (Telegram + Web accounts in admin panel)
- OpenClaw gateway panel (`admin_btn_openclaw`, `openclaw_status_*` i18n keys)
- RAG admin panel (`admin_btn_rag`, FTS5 search)
- T29–T39 regression tests for OpenClaw-specific features

---

## Next Steps

1. Deploy v2026.3.43 to PI2 (OpenClawPI2) for verification
2. Run `/taris-deploy-to-target` skill  
3. After PI2 tests pass: merge to `master` and deploy to PI1
