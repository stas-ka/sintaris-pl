# Merge Proposal: Taris-UI-POC → taris-openclaw

**Date:** 2026-03-28  
**Author:** Copilot  
**Target branch:** `taris-openclaw` (primary development, both platforms)  
**Source branch:** `Taris-UI-POC` (picoclaw-only, Screen DSL + RAG features)  
**Goal:** Merge POC features into taris-openclaw while keeping all OpenClaw-specific fixes and supporting BOTH picoclaw and openclaw platforms.

---

## Executive Summary

| Metric | Value |
|---|---|
| Commits ahead (Taris-UI-POC vs openclaw) | 11 |
| Commits ahead (taris-openclaw vs Taris-UI-POC) | 42 |
| Files changed in diff | 59 |
| Net line delta | −6,922 insertions in POC (it removed most OpenClaw code) |
| Conflict risk files | 8 (bot_config.py, bot_voice.py, bot_auth.py, bot_web.py, strings.json, bot_admin.py, test_voice_regression.py, telegram_menu_bot.py) |

The branches diverged significantly. Taris-UI-POC **removed all OpenClaw-specific modules** 
(pipeline_logger, voice_debug, embeddings, openclaw setup scripts, benchmark tests, OpenClaw LLM tests) 
and is picoclaw-only. `taris-openclaw` is OpenClaw-focused but uses the same bot core.

---

## What Each Branch Has Uniquely

### Features ONLY in Taris-UI-POC (to bring in)

| # | Feature | Files | Priority |
|---|---|---|---|
| F1 | **Screen DSL Loader** (YAML UI screens, Phases 1–5) | `src/ui/screen_loader.py`, `src/ui/bot_ui.py`, `src/screens/*.yaml` | HIGH |
| F2 | **Admin menu fix**: System Chat moved to admin section; all admin labels use `_t(chat_id)` for i18n | `src/telegram/bot_admin.py`, `src/screens/admin_menu.yaml`, `src/strings.json` | HIGH (bug fix) |
| F3 | **FTS5 knowledge base / Document management** (RAG §4.1) | `src/features/bot_documents.py`, `src/core/store.py` | MEDIUM |
| F4 | **Whisper vs Vosk model path fix** (regression test + path correction) | `src/tests/test_voice_regression.py` (commit 4119d75) | HIGH (bug fix) |
| F5 | **Chat send button CSS fix** (oversized send button) | `src/web/templates/chat.html`, `src/web/static/style.css` | LOW |
| F6 | **Screen title no longer double-escaped** in render_telegram.py | `src/ui/render_telegram.py` | MEDIUM |
| F7 | **RAG research docs** (concept papers, TODO §23) | `doc/concept/`, `TODO.md §23` | LOW (docs only) |

### Features ONLY in taris-openclaw (to keep — NOT in POC)

| # | Feature | Files | Notes |
|---|---|---|---|
| K1 | OpenClaw variant support (DEVICE_VARIANT, faster-whisper routing, Vosk fallback) | `src/core/bot_config.py`, `src/features/bot_voice.py` | Core for OpenClaw platform |
| K2 | Pipeline analytics logger | `src/core/pipeline_logger.py` | OpenClaw feature |
| K3 | Voice debug mode + audio download | `src/core/voice_debug.py`, `src/bot_web.py` | OpenClaw feature |
| K4 | OpenClaw setup scripts | `src/setup/setup_llm_openclaw.sh`, `src/setup/setup_voice_openclaw.sh` | OpenClaw feature |
| K5 | Dual STT with fallback strategy (`_STT_DISPATCH`, `STT_FALLBACK_PROVIDER`) | `src/features/bot_voice.py`, `src/core/bot_config.py` | Core STT fix |
| K6 | STT language fix (`STT_LANG`, `_voice_lang()`) | `src/features/bot_voice.py` | Bug fix v2026.3.38+41 |
| K7 | LLM dual fallback chain (`LLM_FALLBACK_PROVIDER`, `_ask_with_fallback`) | `src/core/bot_llm.py` | Bug fix |
| K8 | **Password reset** (forgot/reset flow, SMTP, tokens) | `src/security/bot_auth.py`, `src/bot_web.py`, `src/web/templates/forgot_password.html`, `reset_password.html` | Bug fix v2026.3.35 |
| K9 | Username change + Telegram-Web account linking | `src/security/bot_auth.py`, `src/bot_web.py`, `src/web/templates/profile.html` | Feature v2026.3.36 |
| K10 | Unified user list (Telegram + Web accounts) | `src/telegram/bot_admin.py` | Feature v2026.3.35 |
| K11 | LLM badge in chat + Web UI stack info sidebar | `src/bot_web.py`, `src/web/templates/` | Feature v2026.3.35 |
| K12 | 409 Conflict fix + SIGTERM handler + `_409Handler` fast retry | `src/core/bot_instance.py`, `src/telegram_menu_bot.py`, `src/services/taris-telegram.service` | Bug fix v2026.3.39 |
| K13 | parse_mode=None fix (silent keyboard loss) | `src/core/bot_instance.py`, `src/telegram/bot_handlers.py`, `src/features/bot_voice.py` | Bug fix v2026.3.40 |
| K14 | Voice mode role check fix (admin in system chat via voice) | `src/features/bot_voice.py` | Bug fix v2026.3.42 |
| K15 | Regression tests T35–T39 (STT/TTS/voice/LLM) | `src/tests/test_voice_regression.py` | Tests |
| K16 | OpenClaw LLM tests (`test_ask_openclaw.py`) + benchmark_stt.py | `src/tests/llm/`, `src/tests/benchmark_stt.py` | Tests |
| K17 | OpenClaw documentation | `doc/architecture/openclaw-integration.md`, `doc/architecture/picoclaw.md`, `doc/install-new-target.md` | Docs |

---

## Conflict Analysis

These 8 files are changed in BOTH branches and require careful merging:

| File | taris-openclaw changes | Taris-UI-POC changes | Resolution strategy |
|---|---|---|---|
| `src/core/bot_config.py` | DEVICE_VARIANT, STT_LANG, FASTER_WHISPER_MODEL=small, LLM_PROVIDER routing, pipeline_logger constants, voice_debug constants | Screen DSL constants, RAG path fix, BOT_VERSION=2026.4.13, removed OpenClaw constants | **Merge**: keep all openclaw constants; take only Screen DSL + RAG additions from POC |
| `src/features/bot_voice.py` | _voice_lang(), _cur_mode=="system" dispatch, dual STT fallback, STT_LANG routing, parse_mode=None fixes, voice debug | Whisper model path fix; mostly reductions (removed openclaw code) | **Keep openclaw version**; cherry-pick only the Whisper model path fix from commit 4119d75 |
| `src/security/bot_auth.py` | Password reset tokens, SMTP, generate/validate_reset_token, username change, Telegram linking | Removed all password reset code, reduced to simpler auth | **Keep openclaw version** (POC removed features; do not regress) |
| `src/telegram/bot_admin.py` | Unified user list (_web_account_block), admin menu enhancements | Admin menus now use _t(chat_id, ...) for i18n (24 call sites); System Chat moved to admin section | **Merge carefully**: take POC's i18n fix + System Chat move; keep openclaw's _web_account_block |
| `src/tests/test_voice_regression.py` | Added T35–T39 + T27–T33 OpenClaw tests (1180 extra lines) | Removed all OpenClaw/faster-whisper tests (T27–T39) | **Keep openclaw version** (POC deleted tests; do not regress) |
| `src/strings.json` | LLM badge strings, password reset strings, profile strings, link-telegram strings | admin_btn_system key added, Screen DSL labels | **Merge**: take all new keys from POC; keep all openclaw additions |
| `src/bot_web.py` | Voice debug endpoints, pipeline logger, stack info, LLM badge, password reset routes, profile routes | FTS5 document routes, Screen DSL route; removed voice_debug/pipeline_logger references | **Merge**: take FTS5/document routes from POC; keep all openclaw routes/features |
| `src/telegram_menu_bot.py` | SIGTERM handler, signal import | System Chat removed from main menu (moved to admin via Screen DSL) | **Merge**: keep SIGTERM handler; take the System Chat menu move from POC |

---

## Recommended Merge Approach

**Strategy: Cherry-pick POC features onto taris-openclaw** (NOT git merge, to avoid reverting openclaw features)

### Phase 1 — Bug fixes from POC (LOW risk, HIGH priority)

| Step | Action | POC commit | Risk |
|---|---|---|---|
| 1.1 | Cherry-pick admin i18n fix (24 `_t()` call sites in bot_admin.py) | `333f210` | LOW |
| 1.2 | Cherry-pick System Chat move to admin section (admin_menu.yaml + strings.json) | `333f210` | LOW |
| 1.3 | Cherry-pick Whisper model path fix (regression + path) | `4119d75` | LOW |
| 1.4 | Cherry-pick chat send button CSS fix | `333f210` | LOW |

### Phase 2 — Screen DSL Loader (MEDIUM risk)

| Step | Action | POC commits | Risk |
|---|---|---|---|
| 2.1 | Add Screen DSL Loader Phase 1+2 (screen_loader.py + YAML parser) | `606ec57` | MEDIUM |
| 2.2 | Add Screen DSL Phase 3 (main_menu.yaml + admin_menu.yaml) | `7a48543` | MEDIUM |
| 2.3 | Add Screen DSL Phase 4+5 (notes/profile screens, schema validation) | `3628079` | MEDIUM |
| 2.4 | Verify both platforms (picoclaw + openclaw) render menus correctly | — | — |
| 2.5 | Ensure System Chat button only visible in admin menu (not main menu) | — | — |

### Phase 3 — FTS5 / Document Management (LOW risk, isolated module)

| Step | Action | POC commit | Risk |
|---|---|---|---|
| 3.1 | Cherry-pick bot_documents.py (document upload + FTS5) | `a39a368` | LOW |
| 3.2 | Cherry-pick store.py FTS5 additions (has_document_search, list_documents, etc.) | `a39a368` | LOW |
| 3.3 | Cherry-pick Web UI document routes from bot_web.py | `a39a368` | LOW |
| 3.4 | Merge strings.json keys for document feature | `a39a368` | LOW |

### Phase 4 — Research docs (NO risk)

| Step | Action | POC commit |
|---|---|---|
| 4.1 | Copy RAG/Memory concept papers | `b938b7e`, `38e4613` |
| 4.2 | Merge TODO §23 (research roadmap) | `38e4613`, `cfa03f5` |

---

## What NOT to merge from Taris-UI-POC

| Omission | Reason |
|---|---|
| Removal of `pipeline_logger.py` | openclaw needs it; POC deleted it |
| Removal of `voice_debug.py` | openclaw needs it; POC deleted it |
| Removal of `password reset` code | openclaw has better version; POC regressed |
| Removal of T27–T39 regression tests | openclaw has them; POC deleted them |
| Removal of OpenClaw setup scripts | needed for OpenClaw platform |
| Removal of `_web_account_block` in bot_admin.py | openclaw unified user list needs it |
| Removal of `forgot_password.html` / `reset_password.html` | openclaw needs them |
| Removal of username change + Telegram linking | openclaw has this feature |
| Taris-UI-POC BOT_VERSION=2026.4.13 | openclaw is currently at 2026.3.42; keep own versioning |

---

## Checklist for Copilot (merge execution)

When user confirms, Copilot should execute this checklist IN ORDER:

### ✅ Pre-merge validation
- [x] `C1` Run regression tests on taris-openclaw baseline: `PYTHONPATH=src python3 src/tests/test_voice_regression.py` — all T01–T39 pass (or SKIP for optional)
- [x] `C2` Confirm picoclaw clone is up to date: `git -C ../sintaris-pl-picoclaw fetch origin && git -C ../sintaris-pl-picoclaw status`
- [x] `C3` Create a pre-merge tag: `git tag pre-merge-ui-poc-2026-03-28`

### 🔧 Phase 1 — Bug fixes (cherry-pick)
- [x] `C4` Cherry-pick `333f210` from Taris-UI-POC: `git cherry-pick 333f210`
  - Expected: bot_admin.py (i18n fix), admin_menu.yaml (System Chat moved), strings.json (admin_btn_system key), chat.html (CSS fix), render_telegram.py (title fix)
  - After cherry-pick: resolve any conflicts in bot_admin.py (keep _web_account_block; take _t() i18n changes)
- [x] `C5` Verify admin menus show in user's language (ru/en/de) after cherry-pick
- [x] `C6` Cherry-pick `4119d75` from Taris-UI-POC (Whisper model path fix + regression analysis)
  - After cherry-pick: ensure T27 (faster_whisper_stt) still passes

### 🔧 Phase 2 — Screen DSL Loader
- [x] `C7` Cherry-pick `606ec57` (Screen DSL Phase 1+2 — screen_loader.py + YAML parser)
- [x] `C8` Cherry-pick `7a48543` (Screen DSL Phase 3 — main/admin menus)
- [x] `C9` Cherry-pick `3628079` (Screen DSL Phase 4+5 — notes/profile screens)
- [x] `C10` Verify YAML screens render correctly via: `PYTHONPATH=src python3 -c "from ui.screen_loader import load_screen; s=load_screen('main_menu'); print(s)"`
- [x] `C11` Verify System Chat is NOT in main_menu.yaml; IS in admin_menu.yaml
- [x] `C12` Verify both picoclaw and openclaw platforms (DEVICE_VARIANT=picoclaw / openclaw) render menus
- [x] `C13` Run regression tests: T01–T39 should still pass

### 🔧 Phase 3 — FTS5 / Document Management
- [x] `C14` Cherry-pick `a39a368` (FTS5 knowledge base + document management)
  - Resolve conflicts in: bot_web.py (keep voice_debug routes; take FTS5 routes), strings.json (merge all keys)
- [x] `C15` Validate bot_web.py document routes: `/api/documents`, `/documents` page accessible
- [x] `C16` Validate store.py: `PYTHONPATH=src python3 -c "from core.store import Store; s=Store('/tmp/test_fts5.db'); print(s.has_document_search())"`

### 🔧 Phase 4 — Research docs
- [x] `C17` Copy `doc/concept/` folder from picoclaw clone: `cp -r ../sintaris-pl-picoclaw/doc/concept/ doc/`
- [x] `C18` Merge TODO §23 research roadmap entries into TODO.md

### ✅ Post-merge validation
- [x] `C19` Validate JSON: `python3 -c "import json,sys; json.load(sys.stdin)" < src/strings.json`
- [x] `C20` Validate JSON: `python3 -c "import json,sys; json.load(sys.stdin)" < src/release_notes.json`
- [x] `C21` Bump version to `2026.3.43` (merge commit) in `src/core/bot_config.py` + `src/release_notes.json`
- [x] `C22` Run full regression suite: `PYTHONPATH=src python3 src/tests/test_voice_regression.py`
- [x] `C23` Deploy to PI2 (taris-openclaw branch): sync files + restart + verify journal
- [x] `C24` Push branch: `git push origin taris-openclaw`
- [x] `C25` Update `doc/vibe-coding-protocol.md` with merge session entry

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| bot_admin.py cherry-pick conflict (web_account_block removed in POC) | HIGH | MEDIUM | Manually keep _web_account_block; take only _t() i18n changes |
| Screen DSL Phase 3 removes System Chat from main menu callback routing | MEDIUM | HIGH | Verify `mode_system` still dispatched via admin_menu.yaml callback |
| FTS5 store.py conflict with openclaw store additions | MEDIUM | LOW | Run store.py tests after merge |
| strings.json key collision | LOW | LOW | Python json.load() validation catches syntax; run T13 for key coverage |
| Voice pipeline regression (bot_voice.py not cherry-picked) | LOW | HIGH | Don't touch bot_voice.py; openclaw version is correct |
| Password reset routes absent from POC bot_web.py | HIGH | HIGH | Do NOT use POC version of bot_web.py wholesale; cherry-pick only FTS5 routes |

---

## Files to NOT touch during merge (keep openclaw version)

```
src/features/bot_voice.py          ← openclaw has all fixes; POC has regressions
src/security/bot_auth.py           ← openclaw has password reset; POC removed it
src/core/bot_instance.py           ← openclaw has 409 fix; POC has old version
src/telegram_menu_bot.py           ← keep SIGTERM handler; only take System Chat removal
src/core/bot_llm.py                ← openclaw has dual fallback; POC has old version
src/core/pipeline_logger.py        ← only in openclaw; copy as-is
src/core/voice_debug.py            ← only in openclaw; copy as-is
src/core/bot_embeddings.py         ← only in openclaw; copy as-is
src/tests/test_voice_regression.py ← openclaw has T35–T39; POC deleted them
src/web/templates/forgot_password.html   ← only in openclaw
src/web/templates/reset_password.html    ← only in openclaw
```
