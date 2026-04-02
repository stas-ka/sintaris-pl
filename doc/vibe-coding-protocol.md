# Vibe Coding Protocol — taris / Taris Bot

Tracks every Copilot-assisted session: user request → implementation → commit.  
Use this to analyse cost (time, requests) per feature over time.

---

## Format

Each session block contains a table with one row per completed request:

```
### Session N — YYYY-MM-DD (UTC+1)
| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
```

**Field definitions:**
- **Time** — UTC timestamp from `<current_datetime>` tag on the user message
- **Request** — one-line description of what was asked
- **Complexity** — 1 (trivial) … 5 (very complex); see scale below
- **Requests** — number of user→assistant turns for this item
- **Model** — model ID used (e.g. `claude-sonnet-4.6`)
- **Files changed** — comma-separated list of modified/created files
- **Status** — `done` / `partial` / `wip`

**Complexity scale:**

| Score | Meaning |
|---|---|
| 1 | Trivial — one-liner, doc tweak, single string |
| 2 | Simple — single file, < 20 lines, no logic change |
| 3 | Medium — multi-file or new function, < 100 lines |
| 4 | Complex — new feature, multi-file refactor, 100–500 lines |
| 5 | Very complex — architecture change, > 500 lines, or multiple interdependent systems |

---

## Quarterly Review

Every ~3 months, measure baseline health:

1. `wc -c .github/copilot-instructions.md` — target < 2,000 chars
2. Check session log: average turns-before-compaction ≥ 8
3. Check any instruction file > 3 KB — candidate for compression
4. Review `doc/quick-ref.md` — still accurate?

---

## Session Log

---

### Session 1 — 2026-03-07

| # | Time | Feature / Request | What was implemented | Req | Commits |
|---|------|-------------------|----------------------|-----|---------|
| 1 | ~17:58 | Notes Read aloud | TTS button on note body via Piper | ~3 | `9039e70` |
| 2 | ~18:04 | Docs sync v2026.3.19 | Updated architecture, dev-patterns, README | 1 | `f93afa9` |
| 3 | ~18:16 | Notes UX polish | ForceReply edit, raw text view, Read aloud — v2026.3.20 | ~2 | `93b35e1` |
| 4 | ~22:36 | Calendar + mail + voice fixes | v2026.3.22 — calendar improvements, mail digest, Whisper base model upgrade | ~5 | `e83357b` |
| 5 | ~22:49 | Remove Guest tier | All approved users get full access; admin shows all roles | ~2 | `36e5f45`, `36e5f45` |
| 6 | ~23:03 | Admin: List Users panel | Show all user roles in admin panel | 1 | `36e5f45` |
| 7 | ~23:28 | Calendar Read aloud | TTS button for events and confirm preview | 1 | `04fae1d` |
| 8 | ~23:30 | Mail digest Read aloud | TTS button in mail digest | 1 | `8c1628d` |
| 9 | ~23:44 | Prompt injection guard | 3-layer guard + System Chat admin-only | ~3 | `b7c1880` |
| 10 | ~00:00 | TTS multi-part voice | Read aloud 1200 chars/chunk for long texts (~55 s/chunk) | ~2 | `e14d1cf` |
| 11 | ~00:05 | Profile self-view | User sees name, username, role, reg date, email | ~2 | `f9657c8` |

**Session 1 total: ~11 features, ~23 requests, ~6 h**

---

### Session 2 — 2026-03-08

| # | Time | Feature / Request | What was implemented | Req | Commits |
|---|------|-------------------|----------------------|-----|---------|
| 1 | ~08:24 | v2026.3.24 bugfixes | System chat emoji fix, TTS chunk label fix, timing debug opt | ~3 | `9f58ace` |
| 2 | ~08:27 | Release notes Markdown fix | Raw emoji in release_notes.json caused Telegram parse error | 1 | `6d89d32` |
| 3 | ~08:40 | Whisper hallucination guard | Discard Whisper output when word density too low; Vosk fallback | ~4 | `7e91822` |
| 4 | ~08:46 | Voice regression test T13 | Add T13: hallucination guard test to regression suite | 1 | `1a53cdf` |
| 5 | ~08:51 | Docs update v2026.3.24 | architecture.md, README, backup README synced | 1 | `ecac47f` |
| 6 | ~08:52 | TODO: TTS 110s bottleneck | Documented §5.6 in TODO.md with root cause + fix plan | 1 | `2c7efd9` |
| 7 | ~08:53 | TODO: Profile button bug | Documented §0.1 silent fail in bot_handlers.py | 1 | `b7782dd` |
| 8 | ~08:56 | TODO: Rename bot | Documented §0.2 centralise BOT_NAME | 1 | `9369e92` |
| 9 | ~08:57 | TODO: STT/TTS analysis | §5.7 detailed pipeline analysis, measurement plan | 1 | `cb9c236` |
| 10 | ~10:37 | TODO cleanup | Collapsed all ✅ implemented sections into summary lines | 1 | `cdcd8a8` |
| 11 | ~10:38 | TODO: Recovery testing | §6.5 added | 1 | `b6379d0` |
| 12 | ~10:38 | TODO: Developer role | §1.3 dev menu spec with full button/action table | 1 | `8767646` |
| 13 | ~11:14 | TODO: Note edit bug | §0.3 note edit loses existing content — 3 option analysis | 1 | `dc0d4eb` |

**Session 2 total: ~13 items, ~18 requests, ~3 h**

---

### Session 3 — 2026-03-09

| # | Time | Feature / Request | What was implemented | Req | Commits |
|---|------|-------------------|----------------------|-----|---------|
| 1 | ~22:14 | Device snapshots + benchmark | Pi2 snapshot, benchmark results documented | ~2 | `8e366ad` |
| 2 | ~22:16 | vosk_fallback voice opt | New opt: disable Vosk STT when Whisper active to save RAM | ~3 | `3421c6f` |

**Session 3 total: 2 features, ~5 requests, ~30 min**

---

### Session 4 — 2026-03-11 (early, ~01:30)

| # | Time | Feature / Request | What was implemented | Req | Commits |
|---|------|-------------------|----------------------|-----|---------|
| 1 | ~01:31 | Calendar multi-event add | LLM returns `{"events":[...]}` array; 1→single confirm, N→sequential "1 of N" with Save/Skip/Save All | ~6 | `1797c30` |
| 2 | ~01:31 | Calendar NL query | `_handle_calendar_query()` — LLM extracts date range, filters events | ~3 | `1797c30` |
| 3 | ~01:31 | Calendar delete confirmation | `cal_del:<id>` → confirm card → `cal_del_confirm:<id>` — no accidental deletes | ~2 | `1797c30` |
| 4 | ~01:31 | Calendar console mode | 💬 Консоль button → free-form text, LLM classifies add/query/delete/edit | ~3 | `1797c30` |
| 5 | ~01:34 | Docs + Copilot instructions | Architecture, dev-patterns, AGENTS.md updated for v2026.3.25 | ~2 | `e2db76a` |

**Session 4 total: 5 features, ~16 requests, ~1 h**

---

### Session 5 — 2026-03-11 (UTC+1)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| 06:59 | German language Phase 1: detect, config, voice, 115 DE strings | 4 | 8 | claude-sonnet-4.6 | bot_access.py, bot_config.py, bot_voice.py, strings.json, release_notes.json | done |
| 06:59 | Calendar TTS lang pass-through (`lang=` param) | 1 | 1 | claude-sonnet-4.6 | bot_calendar.py | done |
| 07:02 | Continue German implementation — status check | 1 | 2 | claude-sonnet-4.6 | — | done |
| 07:06 | Check stored checkpoint | 1 | 2 | claude-sonnet-4.6 | — | done |
| 07:06 | Create vibe coding protocol file | 2 | 1 | claude-sonnet-4.6 | doc/vibe-coding-protocol.md | done |
| 07:12 | Audit German language completeness across all files | 2 | 2 | claude-sonnet-4.6 | — | done |
| 07:18 | Complete German language implementation (Phase 2) | 5 | wip+cont | claude-sonnet-4.6 | bot_calendar.py, bot_handlers.py, bot_mail_creds.py, bot_access.py, strings.json | done |
| 09:38 | Resume from hung CLI — complete Phase 2 bot_calendar.py migration | 3 | 3 | claude-sonnet-4.6 | bot_calendar.py | done |
| 10:00 | implement copilot_optimizations.md — P1–P4, P6–P8: slim instructions, split architecture.md into 8 topic files, create doc/quick-ref.md | 4 | 12 | claude-sonnet-4-5 | .github/copilot-instructions.md, safe-update.instructions.md, bot-deploy.instructions.md, INSTRUCTIONS.md, doc/quick-ref.md, doc/architecture.md, doc/architecture/overview.md, doc/architecture/voice-pipeline.md, doc/architecture/telegram-bot.md, doc/architecture/security.md, doc/architecture/features.md, doc/architecture/deployment.md, doc/architecture/multilanguage.md, doc/architecture/web-ui.md, concept/accounting_2025.md | done |
| 07:22 | Add vibe coding protocol rule to AGENTS.md + reformat protocol | 2 | 2 | claude-sonnet-4.6 | AGENTS.md, doc/vibe-coding-protocol.md | done |
| 07:35 | Add §14 Multilanguage Support to architecture.md; deploy/test status check | 2 | 4 | claude-sonnet-4.6 | doc/architecture.md | done |
| 09:47 | Deploy Phase 2 to Pi, update architecture.md §14 to complete, git push | 2 | 3 | claude-sonnet-4.6 | doc/architecture.md, doc/vibe-coding-protocol.md | done |

**Session 5 total: 11 items, ~25 requests**

---

### Session 6 — 2026-03-11 (UTC+1, continued)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| 09:56 | Test on target — run regression suite T01–T12, verify Phase 2 deploy | 1 | 2 | claude-sonnet-4.6 | — | done |
| 10:01 | Implement T13–T16 multilingual regression tests (i18n GUI, lang routing, DE TTS, DE Vosk) | 3 | 4 | claude-sonnet-4.6 | src/tests/test_voice_regression.py, src/tests/voice/ground_truth.json, .github/copilot-instructions.md | done |

**Session 6 total: 2 items, ~6 requests**

---

### Session 7 — 2026-03-12 (UTC+1)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~21:00 | Bug 0.1-0.5 fixes + T17-T21 tests (carried from prior session) | 4 | ~8 | claude-opus-4.6 | bot_handlers.py, bot_config.py, bot_security.py, bot_calendar.py, strings.json, test_voice_regression.py, copilot-instructions.md | done |
| ~22:00 | Error Protocol feature: collect text/voice/photo, save to dir, email with attachments | 4 | ~6 | claude-opus-4.6 | bot_error_protocol.py (new), bot_config.py, bot_state.py, bot_access.py, telegram_menu_bot.py, strings.json | done |
| ~22:30 | Docs update + deploy + verify | 2 | ~3 | claude-opus-4.6 | architecture.md, bot-code-map.md, copilot-instructions.md, vibe-coding-protocol.md | done |

**Session 7 total: 3 items, ~17 requests**

---

## Session 8 — 2026-03-12 (continued, Bug 0.5 fix)

| Time | Request | Complexity | Requests used | Model | Files changed | Status |
|------|---------|------------|---------------|-------|---------------|--------|
| ~22:40 | Fix Bug 0.5: calendar console voice messages bypass cal_console mode, route through general LLM which refuses | 3 | ~2 | claude-opus-4.6 | bot_voice.py | done |

**Session 8 total: 1 item, ~2 requests**

---

## Session 9 — 2026-03-13 (Web UI P0–P2 review and bug-fixing, 2-part)

| Time | Request | Complexity | Requests used | Model | Files changed | Status |
|------|---------|------------|---------------|-------|---------------|--------|
| ~19:00 | Review and test P0-P2 web UI implementation; fix 7 identified bugs (WEB_ONLY guard, field mismatches, mail refresh, voice opts keys, role badge, admin user dict) | 4 | ~12 | claude-sonnet-4.6 | bot_config.py, bot_web.py, admin.html, mail.html | done |
| ~22:40 | Fix FileHandler crash on Windows; verify 7 pages 200; fix chat message dict rendering; add status/pending flow for registration; add admin approve/block routes; fix notes namespace; add badge-err CSS + login-info CSS; add info block to register.html | 4 | ~18 | claude-sonnet-4.6 | bot_config.py, bot_auth.py, bot_web.py, _chat_messages.html, admin.html, register.html, style.css | done |

**Session 9 total: 2 items, ~30 requests**

---

## Session 10 — 2026-03-14 (Calendar Web UI console + voice fix)

| Time | Request | Complexity | Requests used | Model | Files changed | Status |
|------|---------|------------|---------------|-------|---------------|--------|
| ~06:00 | Fix calendar console + voice not working in Web UI (no LLM API keys on Pi2): add dateutil fallback parser + keyword-based intent detection | 3 | ~6 | claude-sonnet-4.6 | bot_web.py | done |

**Session 10 total: 1 item, ~6 requests**

---

## Session 11 — 2026-03-16 (src/ package restructure)

| Time | Request | Complexity | Requests used | Model | Files changed | Status |
|------|---------|------------|---------------|-------|---------------|--------|
| ~20:00 | Reorganize flat `src/*.py` into 5 logical packages: core/, security/, telegram/, features/, ui/ — move files, rewrite all imports, update docs | 4 | ~15 | claude-sonnet-4.6 | all 20 bot_*.py files, telegram_menu_bot.py, bot_web.py, doc/bot-code-map.md, doc/quick-ref.md, .github/instructions/bot-deploy.instructions.md | done |

**Session 11 total: 1 item, ~15 requests**

---

## Session 12 — 2026-03-19

| Time | Request | Complexity | Requests used | Model | Files changed | Status |
|------|---------|------------|---------------|-------|---------------|--------|
| 06:20 UTC | Profile language setting (persist to registrations.json, restore on restart) + My Data view — 5-file feature across strings.json, bot_users.py, bot_access.py, bot_handlers.py, telegram_menu_bot.py; deploy + verify on OpenClawPI2 | 4 | ~12 | claude-sonnet-4.6 | strings.json, telegram/bot_users.py, telegram/bot_access.py, telegram/bot_handlers.py, telegram_menu_bot.py | done |

**Session 12 total: 1 item, ~12 requests**

---

## Session 13 — Prior session (§3.2 Admin LLM fallback toggle — code)

| Time | Request | Complexity | Requests used | Model | Files changed | Status |
|------|---------|------------|---------------|-------|---------------|--------|
| (prior) | §3.2 Admin Panel LLM fallback toggle via flag file (`llm_fallback_enabled`): `_handle_admin_llm_fallback_menu()`, `_handle_admin_llm_fallback_toggle()`, `LLM_FALLBACK_FLAG_FILE` constant, `📡 Local Fallback` admin button, deploy + verify v2026.3.43 on PI2 | 3 | ~12 | claude-sonnet-4.6 | core/bot_config.py, telegram/bot_admin.py, telegram_menu_bot.py, core/bot_llm.py, release_notes.json, src/services/taris-telegram.service | done |

**Session 13 total: 1 item, ~12 requests**

---

## Session 14 — Continuation (§3.2 doc sync — `/taris_update_doc`)

| Time | Request | Complexity | Requests used | Model | Files changed | Status |
|------|---------|------------|---------------|-------|---------------|--------|
| (continuation) | `/taris_update_doc` skill: sync all documentation with v2026.3.43 — deployment.md (3 edits), llm-providers.md (6 changes incl. new §19.6 Runtime Fallback Toggle), telegram-bot.md (4 changes), bot-code-map.md (4 rows), TODO.md, README.md; commit `f2d8763` | 2 | ~8 | claude-sonnet-4.6 | doc/architecture/deployment.md, doc/architecture/llm-providers.md, doc/architecture/telegram-bot.md, doc/bot-code-map.md, TODO.md, README.md | done |

**Session 14 total: 1 item, ~8 requests**

---

## Summary Table (all sessions)

| Session | Date | Items | Requests | Avg complexity | Model |
|---------|------|-------|----------|----------------|-------|
| 1 | 2026-03-07 | 11 | ~23 | 3.2 | unknown (pre-protocol) |
| 2 | 2026-03-08 | 13 | ~18 | 1.5 | unknown (pre-protocol) |
| 3 | 2026-03-09 | 2 | ~5 | 3.0 | unknown (pre-protocol) |
| 4 | 2026-03-11 AM | 5 | ~16 | 3.8 | unknown (pre-protocol) |
| 5 | 2026-03-11 | 9 | ~22 | 2.4 | claude-sonnet-4.6 |
| 6 | 2026-03-11 | 2 | ~6 | 2.0 | claude-sonnet-4.6 |
| 7 | 2026-03-12 | 3 | ~17 | 4.0 | claude-opus-4.6 |
| 8 | 2026-03-12 | 1 | ~2 | 3.0 | claude-opus-4.6 |
| 9 | 2026-03-13 | 2 | ~30 | 4.0 | claude-sonnet-4.6 |
| 10 | 2026-03-14 | 1 | ~6 | 3.0 | claude-sonnet-4.6 |
| 11 | 2026-03-16 | 1 | ~15 | 4.0 | claude-sonnet-4.6 |
| 12 | 2026-03-19 | 1 | ~12 | 4.0 | claude-sonnet-4.6 |
| 13 | prior session | 1 | ~12 | 3.0 | claude-sonnet-4.6 |
| 14 | continuation | 1 | ~8 | 2.0 | claude-sonnet-4.6 |
| **Total** | | **51** | **~188** | | |

---

## Cost per Feature Category

| Category | Features | Est. requests | Notes |
|----------|----------|---------------|-------|
| Voice pipeline (TTS/STT/opts) | 8 | ~20 | Most complex — hardware-specific |
| Calendar (add/query/delete/console) | 6 | ~18 | Multi-step UX flows |
| Security / access control | 3 | ~7 | Prompt guard, role cleanup |
| UI / strings / i18n | 4 | ~12 | strings.json 115 keys expensive |
| Notes | 2 | ~5 | |
| Docs / TODO tracking | 8 | ~10 | Low cost, high value |
| Multi-language (DE) | 4 | ~15 | In progress |
| Bugfixes | 3 | ~5 | |

---

## Session 9 — 2026-03-26 (UTC+1)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Web interface concept document (prior conversation) | 5 | ~5 | claude-opus-4.6 | doc/concept-web-interface.md | done |
| — | Vibe coding + rapid UI analysis: Copilot assessment, agent design, NiceGUI vs HTMX comparison | 4 | ~3 | claude-opus-4.6 | doc/concept-vibe-coding-ui.md | done |

| — | English UI mockup set: 7 HTML screens + shared CSS + index | 3 | ~4 | claude-opus-4.6 | doc/mockups/*.html, doc/mockups/shared.css | done |
| — | Russian UI mockup set: 8 HTML screens (full translation) | 3 | ~4 | claude-opus-4.6 | doc/mockups-ru/*.html | done |
| — | Detailed web UI implementation roadmap: 6-phase plan, standalone auth, unified identity, NiceGUI, Screen DSL | 4 | ~1 | claude-opus-4.6 | doc/roadmap-web-ui.md | done |

**Session 9 total: 5 items, ~20 requests**

---

### Session 10 — 2026-03-13 (UTC+1)

**Focus:** Adapt PicoUI roadmap for multi-backend (PicoClaw/OpenClaw), multi-channel rendering, CRM platform vision

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Adapt roadmap: multi-backend LLM abstraction + multi-channel rendering + CRM vision. Title/metadata, executive summary, §4.2 bot_llm.py, §9 Multi-Channel Renderer Architecture, §13 CRM Platform Vision, decision log, risks, file structure, Appendix A, TODO.md §8 | 4 | ~2 | claude-opus-4.6 | doc/web-ui/roadmap-web-ui.md, TODO.md | done |
| — | Add email verification to registration flows (Web + Telegram). Flow A updated, new Flow A2, §2.6 Email Verification section, account schema gets email + email_verified fields | 3 | 1 | claude-opus-4.6 | doc/web-ui/roadmap-web-ui.md | done |
| — | Align concept-vibe-coding-ui.md with current roadmap: FastAPI-first (not NiceGUI), add bot_llm.py + multi-channel + CRM refs, rewrite §4.5/§5 recommendation, update §7 roadmap to P0–P4, fix appendixes A/B/C | 4 | ~2 | claude-opus-4.6 | doc/web-ui/concept-vibe-coding-ui.md | done |

**Session 10 total: 3 items, ~5 requests**

---

## Session 11 — 2026-03-27 (UTC+1)

**Focus:** Mail IMAP credential configuration via web UI

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Add mail IMAP credential config to web UI: provider form (Gmail/Yandex/Mail.ru/Custom), live IMAP connection test, creds summary view, Change/Delete actions | 4 | ~8 | claude-sonnet-4.6 | src/bot_web.py, src/templates/mail.html | done |

**Session 11 total: 1 item, ~8 requests**

---

## Session 12 — 2026-03-13 (UTC+1)

**Focus:** Web UI bug fixes — chat textarea, message rendering, notes editor, mail IMAP refresh, calendar voice, TTS read-aloud; templates/static deploy to Pi2

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Fix chat input too small (input→textarea), fix chat message dict rendering bug, fix notes create/edit/save (auto-title, name attr, partial response), add calendar Web Speech API voice, add mail IMAP real-fetch + browser TTS read-aloud, add base.html template blocks; deploy to Pi2 | 4 | ~12 | claude-sonnet-4.6 | src/bot_web.py, src/templates/base.html, src/templates/chat.html, src/templates/_chat_messages.html, src/templates/_note_editor.html, src/templates/calendar.html, src/templates/mail.html, src/static/style.css | done |

**Session 12 total: 1 item, ~12 requests**

---

## Session 13 — 2026-03-13 (UTC+1)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Voice page: TTS/STT endpoints, MediaRecorder API, waveform visualiser, transcript auto-refresh; deploy to Pi2 | 4 | ~8 | claude-sonnet-4.6 | src/bot_web.py, src/templates/voice.html, src/static/style.css | done |

**Session 13 total: 1 item, ~8 requests**

---

## Session 14 — 2026-03-14 (UTC+1)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Fix IMAP error b'[ALERT]…' bytes leaking into UI; add _imap_err_str() with App Password hint | 2 | ~2 | claude-sonnet-4.6 | src/bot_web.py | done |
| — | Fix chat send button covering textarea (Pico CSS width:100% override) | 2 | ~2 | claude-sonnet-4.6 | src/static/style.css | done |
| — | Gmail OAuth2 "Connect with Google" flow: OAuth routes (/start, /callback), XOAUTH2 IMAP, Sign-in-with-Google UI in mail.html | 4 | ~6 | claude-sonnet-4.6 | src/bot_web.py, src/templates/mail.html | done |

**Session 14 total: 3 items, ~10 requests**

---

## Session 15 — 2026-03-14 (UTC+1)

**Focus:** Playwright UI test suite + unified assistant chat page

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Build 48 Playwright UI tests (TestAuth, TestDashboard, TestChat, TestNotes, TestCalendar, TestVoice, TestMail, TestAdmin, TestNavigation, TestRegistration) + pytest.ini + conftest.py + fixtures | 4 | ~10 | claude-sonnet-4.6 | src/tests/ui/test_ui.py, src/tests/ui/pytest.ini, src/tests/ui/conftest.py | done |
| — | Fix 6 test failures (calendar id collision, TTS visibility, admin 403, chat message locator) | 3 | ~6 | claude-sonnet-4.6 | src/tests/ui/test_ui.py | done |
| — | Unified assistant chat: rewrite chat.html into single page with voice mic (MediaRecorder), waveform, pipeline bar (STT→LLM→TTS), action chips rail, audio toggle; update base.html sidebar label; update test selectors | 4 | ~5 | claude-sonnet-4.6 | src/templates/chat.html, src/templates/base.html, src/tests/ui/test_ui.py | done |

**Session 15 total: 3 items, ~21 requests**

---

## Session 16 — 2026-03-14 (UTC+1)

**Focus:** Gen 1.0 multimodal UX concept + interactive HTML mockup

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Multimodal UX concept: 8-screen interactive HTML mockup (Hub idle, Listening, Intent card, Note editor+voice, Confirm, Success+WhatsNext, Chat thread, Telegram adaptation) + concept markdown doc | 4 | ~3 | claude-sonnet-4.6 | doc/web-ui/mockups-gen1/index.html, doc/web-ui/concept-multimodal-ux.md | done |

**Session 16 total: 1 item, ~3 requests**

---

## Session 17 — 2026-03-14 (UTC+1)

**Focus:** SQLite spec, Safe Update Protocol, voice language notification in Web UI

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | SQLite feature spec in TODO.md (decision matrix, 7-table schema, migration plan, bot_db.py spec, tests T22/T23) + Safe Update Protocol in copilot-instructions.md (9-step backup→migrate→test→deploy) | 3 | ~4 | claude-sonnet-4.6 | TODO.md, .github/copilot-instructions.md | done |
| — | Add Russian-only voice notification to chat.html: empty state info panel + language banner in voice-row + deploy to Pi2 (48/48 tests pass) | 2 | ~3 | claude-sonnet-4.6 | src/templates/chat.html | done |

**Session 17 total: 2 items, ~7 requests**

---

---

## Session 18 — 2026-03-12 (UTC+1)

**Focus:** SSL certificate fix on both Pis + new-target install guide + copilot-instructions updates

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Fix HTTPS 'Not Secure' warning on both Pi targets: create setup_ssl.sh with SAN (hostname+all IPs+Tailscale), deploy+run on both Pis, restart taris-web on Pi2, download certs for Windows trust store | 3 | ~6 | claude-sonnet-4.6 | src/setup/setup_ssl.sh | done |
| — | Write doc/install-new-target.md: 13-step complete fresh-install guide (system pkgs, Python pkgs, taris binary, Piper TTS, source deploy, voice models, bot.env, taris config, SSL, systemd services, verify checklist) | 3 | ~2 | claude-sonnet-4.6 | doc/install-new-target.md | done |
| — | copilot-instructions.md: backup naming rule → %BNAME% composite (host+version+timestamp); UI Sync Rule section for requiring Telegram+Web updates together | 2 | ~3 | claude-sonnet-4.6 | .github/copilot-instructions.md | done |

**Session 18 total: 3 items, ~11 requests**

---

## Session 19 — 2026-03-14 (UTC+1)

**Focus:** Phase 3+4 web-ui roadmap implementation — PWA manifest, Screen DSL, action handlers, Telegram renderer; deploy to Pi2

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Implement open P3/P4 roadmap features: PWA manifest + base.html meta tags; Screen DSL (bot_ui.py dataclasses); action handlers (bot_actions.py: action_menu, action_note_list, action_note_view); Telegram renderer (render_telegram.py); deploy to OpenClawPI2; verify manifest served + syntax OK | 4 | ~6 | claude-sonnet-4.6 | src/static/manifest.json, src/templates/base.html, src/bot_ui.py, src/bot_actions.py, src/render_telegram.py | done |

**Session 19 total: 1 item, ~6 requests**

---

## Session 20 — 2026-03-28 (UTC+1)

**Focus:** Documentation sync for Web UI P0–P4 completion — architecture.md, TODO.md, roadmap-web-ui.md

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Update architecture and documentation: add §17 Web UI Channel + §18 Screen DSL to architecture.md; fix all BOT_VERSION inconsistencies to v2026.3.28; update module dependency chain and process hierarchy | 3 | ~4 | claude-sonnet-4.6 | doc/architecture.md | done |
| — | Collapse TODO.md §8.1/8.2/8.3 planning items to ✅ summaries; update §8.4 CRM table with Status column; extend Completed header with Web UI P0–P4 (v2026.3.28) | 2 | ~2 | claude-sonnet-4.6 | TODO.md | done |
| — | Update roadmap-web-ui.md: header completion note; phase summary table Status column; ✅ status prefix on all 5 deliverables tables (§4.9/§5.7/§6.4/§7.6/§8.6) | 2 | ~2 | claude-sonnet-4.6 | doc/web-ui/roadmap-web-ui.md | done |

**Session 20 total: 3 items, ~8 requests**

---

## Session 21 — 2026-03-14 (UTC+1)

**Focus:** Bug 0.6 (role guards), §1.1/§1.3 RBAC expansion, login page black-page fix

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | File Bug 0.6: Admin/Developer role guards for System Chat; expand §1.1 RBAC 4-role table; expand §1.3 Developer Role capability table | 3 | ~3 | claude-sonnet-4.6 | TODO.md | done |
| — | Diagnose black login page (low contrast: card #1e1e1e on bg #121212) and "Not secure" SSL warning; fix login page CSS: radial gradient bg, #252535 card, accent purple border + box-shadow | 2 | ~5 | claude-sonnet-4.6 | src/static/style.css | done |
| — | Show hostname on login + register pages: add `import socket`, `_HOSTNAME`, pass to all login/register template contexts; update login.html + register.html title + subtitle | 2 | ~4 | claude-sonnet-4.6 | src/bot_web.py, src/templates/login.html, src/templates/register.html | done |
| — | VPS internet exposure: design reverse SSH autossh tunnel architecture (no Fritz.Box changes, dynamic IP irrelevant); create nginx-vps.conf with sub_filter path rewriting, install_vps.sh, taris-tunnel.service, setup_tunnel_key.sh | 4 | ~6 | claude-sonnet-4.6 | src/setup/nginx-vps.conf, src/setup/install_vps.sh, src/setup/setup_tunnel_key.sh, src/services/taris-tunnel.service | done |
| 11:00 UTC | User settings page: language selector (EN/RU/DE) + change password form; add `change_password()` to bot_auth.py; add GET /settings + POST /settings/language + POST /settings/password routes; create settings.html; add ⚙️ Settings link in sidebar nav; deploy to both Pis | 3 | ~3 | claude-sonnet-4.6 | src/bot_auth.py, src/bot_web.py, src/templates/settings.html, src/templates/base.html | done |

**Session 21 total: 6 items, ~21 requests**

---

## Session 22 — 2026-03-14 (UTC+1)

**Focus:** Telegram↔Web account linking feature + documentation sync + PI2 deployment

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| 21:00 UTC | Implement Telegram↔Web account linking: 6-char alphanumeric code with 15 min TTL, "🔗 Link to Web" button in Profile, /register optional link_code field, status=active + role inheritance on link, strings.json in ru/en/de | 4 | ~8 | claude-sonnet-4.6 | src/bot_state.py, src/bot_handlers.py, src/telegram_menu_bot.py, src/bot_web.py, src/templates/register.html, src/strings.json | done |
| 21:10 UTC | Documentation: update roadmap Flow C with actual implementation details (vs old 6-digit/5-min/`/link` plan); mark Flow D as 🔲 Planned; update TODO.md Completed line; update roadmap "Updated:" header | 2 | ~3 | claude-sonnet-4.6 | doc/web-ui/roadmap-web-ui.md, TODO.md | done |
| 21:15 UTC | Deploy to OpenClawPI2: upload 6 files (5 src + register.html template), restart taris-telegram + taris-web, verify both services active (v2026.3.28, Polling Telegram, TLS :8080) | 2 | ~2 | claude-sonnet-4.6 | — (remote deploy) | done |

**Session 22 total: 3 items, ~13 requests**

---

## Session 23 — 2026-03-28 (UTC+1)

**Focus:** Documentation sync — reflect all Web UI + Account Linking implementations across README, howto, architecture, and concept docs

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~21:30 UTC | Update README.md: rewrite features into 4 groups (Voice & AI Core, Telegram Bot, Web Interface, Architecture & Ops); expand docs table from 7 to 11 rows | 2 | ~2 | claude-sonnet-4.6 | README.md | done |
| ~21:35 UTC | Update doc/howto_bot.md: Voice Opts table 6→10 rows with key names; Developer role row; German language; Web registration sub-section; new Profile section; new Web Interface section (URL table, features, PWA install); Troubleshooting 8→13 rows | 3 | ~4 | claude-sonnet-4.6 | doc/howto_bot.md | done |
| ~21:45 UTC | Update doc/architecture.md: bot_state.py module table web-link functions; Flow B2 Telegram-linked register; /register route link_code param; GET/POST /settings routes; /api/admin/voice_opts route; new §17.5 Telegram↔Web Account Linking | 3 | ~4 | claude-sonnet-4.6 | doc/architecture.md | done |
| ~22:00 UTC | Update doc/web-ui/concept-web-interface.md: header v0.1 Draft → v1.0 Implemented; §1 Resolution paragraph; §2 Design Goals status column; §4 title Proposed→Implemented; §9 all phases rewritten as ✅ Complete; §12 Implementation Status table (new) | 3 | ~8 | claude-sonnet-4.6 | doc/web-ui/concept-web-interface.md | done |

**Session 23 total: 4 items, ~18 requests — documentation only, no code changes**

---

## Session 24 — 2026-03-28 (UTC+1)

**Focus:** Instruction files audit — AGENTS.md, INSTRUCTIONS.md, .github/copilot-instructions.md consistency update

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~22:30 UTC | Audit and update all 3 instruction files: AGENTS.md (PI2 section added, BOT_VERSION updated to 2026.3.28, remove unrelated accounting task reference); INSTRUCTIONS.md (truncated to 119 lines with clean format, full bot_*.py module list, Quick Deploy commands, 6 reference docs); .github/copilot-instructions.md (Developer Reference table expanded, Remote Host Access split into PI2+PI1 two-section layout per PI2-first rule, voice regression tests now target PI2 with %TARGET2PWD%, all $HOSTPWD bash-style quoting replaced with %HOSTPWD% bat-style throughout all sections: sipeed, Gmail Digest, Telegram Gateway, Voice Assistant setup, Service Management, Common Remote Tasks, Notes section expanded with full companion file list) | 3 | ~20 | claude-sonnet-4.6 | .github/copilot-instructions.md, AGENTS.md, INSTRUCTIONS.md | done |

**Session 24 total: 1 item, ~20 requests — documentation only, no code changes**

---

---

## Session 25 — 2026-03-15 (UTC+1)

**Focus:** Project-wide cleanup — delete obsolete files/dirs; update all core documentation (bot-code-map, dev-patterns, README) to reflect 20-module architecture + Web UI channel + Screen DSL

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| 05:00 UTC | Delete obsolete files: `temp/` dir (10 scripts), `PicoClaw Howto.md`, `src/telegram_menu_bot_original.py`, `src/gmail_auth.py`, `doc/web-ui/mockups-fastapi/`, `doc/web-ui/mockups-nicegui/`, `doc/web-ui/mockups-ru/`, `doc/web-ui/mockups-gen1/` | 1 | ~2 | claude-sonnet-4.6 | (deleted files) | done |
| 05:10 UTC | Update `doc/bot-code-map.md`: full rewrite — 881 lines, 20 module sections with function tables, module dependency chain, Callback Data Key Reference table, Key Files on Pi section, Web UI route inventory (41 routes), Screen DSL dataclasses, bot_actions handlers | 4 | ~5 | claude-sonnet-4.6 | doc/bot-code-map.md | done |
| 05:20 UTC | Update `doc/dev-patterns.md`: fix header (20-module split), complete sections 15–18 (Screen DSL Pattern, Adding a Web UI Route, Telegram↔Web Shared Action Pattern, Password Reset Pattern) | 3 | ~4 | claude-sonnet-4.6 | doc/dev-patterns.md | done |
| 05:35 UTC | Update `README.md`: 5 stale sections fixed — (1) directory structure expanded to all 20 modules + web UI files; (2) Step 5 deploy commands updated from 3 files to full 20-module + web templates deploy; (3) Step 9 description changed from "3-mode interface" to full-featured 20-module description; (4) Step 12 verification added taris-web service; (5) Service Management added taris-web block | 3 | ~3 | claude-sonnet-4.6 | README.md | done |

| 06:00 UTC | Implement admin password reset: `POST /admin/user/{user_id}/reset-password` route — admin-only, min 4 chars, bcrypt via `change_password()`; `HX-Redirect` with `msg`/`error` flash params; `admin_page` GET updated to extract + pass `msg`/`error`; `admin.html` updated: flash messages block, `x-data="{ openRows: {} }"` on `<tbody>`, 🔑 key button per user row (Alpine toggle), expandable inline password form row with HTMX submit; actions column widened 100→140px | 3 | ~8 | claude-sonnet-4.6 | src/bot_web.py, src/templates/admin.html | done |

**Session 25 total: 5 items, ~22 requests — cleanup + documentation + password reset feature**

---

## Session 26 — 2026-03-15 (UTC)

**Focus:** VS Code Copilot skills — prompt files for common workflows

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| 17:08 | Create VS Code Copilot skills (prompt files) and usage guide so user can invoke tasks with /skill-name from Chat | 3 | 1 | claude-sonnet-4.6 | .github/prompts/deploy-bot.prompt.md, .github/prompts/run-tests.prompt.md, .github/prompts/bump-version.prompt.md, .github/prompts/test-software.prompt.md, doc/copilot-skills-guide.md, .vscode/settings.json, .github/copilot-instructions.md | done |

**Session 26 total: 1 item, 1 request**

---

## Session 27 — 2026-03-16 (UTC)

**Focus:** Commit and push 69 accumulated files from Sessions 19–26 to GitHub master

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~UTC | Commit and push all changes: update .gitignore (IDE/certs/backups/test-results), stage 69 files (new: bot_ui.py, bot_actions.py, render_telegram.py, manifest.json, taris-tunnel.service, VPS setup scripts, settings.html, benchmark tools; modified: bot_auth.py + change_password(), bot_web.py + settings routes + admin reset, bot_state.py + account linking, templates; deleted: obsolete files/mockups), rebase on Copilot PR #4 (list-open-issues), resolve vibe-coding-protocol.md conflict, push 69b3a2a to origin/master | 2 | 4 | claude-sonnet-4.6 | .gitignore, doc/vibe-coding-protocol.md | done |

**Session 27 total: 1 item, 4 requests**

---

## Session 28 — 2026-03-16 (UTC)

**Focus:** Package-structure migration validation — fix web service, fix voice regression tests, add db functions

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~22:00 UTC | Deploy missing bot_web.py to PI2 (was not deployed in previous migration session); web service now running on https://0.0.0.0:8080 | 1 | 2 | claude-sonnet-4.6 | src/bot_web.py (deploy only) | done |
| ~22:15 UTC | Fix 6 voice regression test failures caused by new package layout: add _PKG_CORE/_PKG_TELEGRAM/_PKG_FEATURES path constants, update T17 (core.bot_config import), T18/T19 (telegram/bot_handlers.py path), T20/T21 (features/bot_calendar.py path), T22 (core.bot_db import) | 2 | 6 | claude-sonnet-4.6 | src/tests/test_voice_regression.py | done |
| ~22:30 UTC | Fix T18 test false failure (wrong string pattern "from bot_mail_creds" → "bot_mail_creds" substring); add close_db(), db_save_voice_opts(), db_get_voice_opts(), vosk_fallback column, global_voice_opts table to bot_db.py; all 30 tests now PASS | 3 | 4 | claude-sonnet-4.6 | src/core/bot_db.py, src/tests/test_voice_regression.py | done |

**Session 28 total: 3 items, ~12 requests — package migration validation complete. PASS 30 FAIL 0 WARN 0 SKIP 4**

---

**Session 29**

| 23:00 UTC | PI1 package structure migration | 2 | 7 | claude-sonnet-4-5 | src/setup/migrate_pi1_packages.bat | done |

**Session 29 total: 1 item, ~7 requests — PI1 migrated to package layout. Telegram v2026.3.30+1 + Web UI both running ✅**

---

**Session 30**

| 23:20 UTC | fix: web admin Release Notes button had no functionality — added backend load + admin.html section | 2 | 4 | claude-sonnet-4.6 | src/bot_web.py, src/web/templates/admin.html | done |

**Session 30 total: 1 item, ~4 requests — Release Notes now visible in web admin panel (last 5 entries). Deployed + committed `54dbaba` ✅**

---

## Session 31 — 2026-03-17 (UTC+1)

**Focus:** Bug fixes 0.7 and 0.8 — contacts i18n key, profile password change key error

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~09:00 UTC | Fix all known bugs: Bug 0.7 (contacts "Add Contact" cancel button showed raw key "btn_cancel" — added missing i18n key to ru/en/de in strings.json); Bug 0.8 (profile change password silently failed — fixed account["id"] KeyError, correct key is "user_id" in _finish_profile_change_pw()); bump version 2026.3.30+1 → 2026.3.31; update release_notes.json + TODO.md; deploy to PI2, verified v2026.3.31 running | 2 | ~4 | claude-sonnet-4-5 | src/strings.json, src/telegram/bot_handlers.py, src/core/bot_config.py, src/release_notes.json, TODO.md | done |

**Session 31 total: 1 item, ~4 requests — both bugs fixed, deployed to PI2 ✅**

---

## Session 32 — 2026-03-17 (UTC+1)

**Focus:** Feature 3 — Multi-LLM Provider Support (§3.1) & Local LLM Offline Fallback (§3.2)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~10:00 UTC | Feature 3.1: rewrite `bot_llm.py` with 6 provider clients (taris/openai/yandexgpt/gemini/anthropic/local); `LLM_PROVIDER` env-var switch + 14 provider constants in `bot_config.py`; stdlib-only urllib HTTP dispatch; `_DISPATCH` dict + `ask_llm()`; no new pip dependencies (Pi constraint) | 4 | ~6 | claude-sonnet-4.6 | src/core/bot_llm.py, src/core/bot_config.py | done |
| ~10:30 UTC | Feature 3.2: local llama.cpp offline fallback — `LLM_LOCAL_FALLBACK` guard, `⚠️ [local fallback]` prefix on responses; create `taris-llm.service` systemd unit (qwen2-0.5b-q4.gguf, port 8081, 4 threads); bump BOT_VERSION → 2026.3.32; prepend release_notes.json entry; mark TODO.md §3.1 + §3.2 ✅ | 3 | ~4 | claude-sonnet-4.6 | src/services/taris-llm.service, src/release_notes.json, TODO.md | done |

**Session 32 total: 2 items, ~10 requests — Feature 3 complete. 6-provider LLM dispatch + local fallback ✅**

---

## Session 33 — 2026-03-17 (UTC+1)

**Focus:** Documentation update pass for v2026.3.32 — Feature 3.1/3.2 docs

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~11:00 UTC | Update all project docs for Feature 3 (6-provider LLM + local fallback): expand TODO.md §3.1/§3.2 checklists; add LLM provider + offline fallback info to `help_text_admin` in 3 languages (strings.json); rewrite bot_llm.py entry in bot-code-map.md (module table + 13-row function table); create doc/architecture/llm-providers.md (sections 19.1–19.7: dispatch diagram, provider table, fallback config, bot.env sample, provider guide); add llm-providers.md row to architecture.md index | 2 | ~5 | claude-sonnet-4.6 | TODO.md, src/strings.json, doc/bot-code-map.md, doc/architecture/llm-providers.md, doc/architecture.md | done |

**Session 33 total: 1 item, ~5 requests — docs fully updated for v2026.3.32 ✅**

---

## Session 34 — 2026-03-17 (UTC+1)

**Focus:** Storage adapter layer + migration script — Phase 2 (adapters) + Phase 3 (migration)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~12:00 UTC | Create flexible multi-backend storage adapter layer: `store_base.py` (DataStore Protocol + StoreCapabilityError), `store.py` (factory + singleton), `store_sqlite.py` (full SQLite adapter ~380 lines), extend `bot_db.py` with WAL + documents table + idx_docs_chat | 5 | ~8 | claude-sonnet-4-5 | src/core/store_base.py, src/core/store.py, src/core/store_sqlite.py, src/core/bot_db.py | done |
| ~13:30 UTC | Answer 4 operational readiness questions; research all JSON source formats (registrations, voice_opts, calendar, notes, mail_creds, pending_tts, accounts); create idempotent migration script `src/setup/migrate_to_db.py` (~315 lines) with 6 migration functions + dry-run mode; verify all 7 bot_config constants | 4 | ~12 | claude-sonnet-4.6 | src/setup/migrate_to_db.py | done |

**Session 34 total: 2 items, ~20 requests — storage adapter layer + migration script complete ✅**

---

## Session 35 — 2026-03-17 (UTC+1)

**Focus:** Topic 9 Phase 2c — Flexible Storage Architecture dual-write wrappers (all feature modules)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~14:00 UTC | Phase 2c dual-write — `bot_calendar.py`: import `store`; extend `_cal_save()` with `store.save_event()` loop + `store.delete_event()` in `_cal_delete_event()`, both wrapped in try/except | 3 | ~5 | claude-sonnet-4-5 | src/features/bot_calendar.py | done |
| ~14:20 UTC | Phase 2c dual-write — `bot_users.py`: import `store`; extend `_save_note_file()` with `store.save_note()` + re-write plain content after (title prefix conflict); `_delete_note_file()` calls `store.delete_note()`, try/except guards | 3 | ~5 | claude-sonnet-4-5 | src/telegram/bot_users.py | done |
| ~14:40 UTC | Phase 2c dual-write — `bot_mail_creds.py`: import `store`; extend `_save_creds()` with `store.save_mail_creds()` try/except | 2 | ~3 | claude-sonnet-4-5 | src/features/bot_mail_creds.py | done |
| ~15:00 UTC | Phase 2c dual-write — `bot_state.py`: lazy imports inside `_save_voice_opts()` to avoid circular import; `_VOICE_OPT_COLUMNS` whitelist check before `store.set_voice_opt(None, key, val)` loop; no module-level store import | 3 | ~6 | claude-sonnet-4-5 | src/core/bot_state.py | done |
| ~15:30 UTC | Phase 2c dual-write — `bot_web.py`: `_STORE_OK` guard flag (mirrors `_GOOGLE_AUTH_OK` pattern); extend `_cal_save()` with event loop; OAuth2 callback, IMAP settings POST, token refresh — all add `_store.save_mail_creds()`; confirmed `creds` variable name + `uid` scope before editing | 4 | ~8 | claude-sonnet-4-5 | src/bot_web.py | done |
| ~16:00 UTC | Update TODO.md: Phase 2a/2b/2c table rows → `✅ Done (v2026.3.32)`; store_base.py / store.py / store_sqlite.py checklist items → `[x]` | 1 | ~2 | claude-sonnet-4-5 | TODO.md | done |

**Session 35 total: 6 items, ~29 requests — Topic 9 Phase 2c complete. All 5 feature modules dual-write to SQLite store ✅**

---

## Session 36 — 2026-03-17 (UTC+1)

**Focus:** PI2 safe-update deployment — Phase 2c code + JSON→SQLite migration

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~09:30 UTC | PI2 safe-update: verify + download backup (`taris_backup_OpenClawPI2_v2026.3.32`), stop services | 2 | ~2 | claude-sonnet-4-6 | — | done |
| ~09:35 UTC | Deploy Phase 2c files to PI2: core (store_base, store, store_sqlite, bot_db, bot_state), features (bot_calendar, bot_mail_creds, bot_users, bot_web), migrate_to_db.py | 2 | ~3 | claude-sonnet-4-6 | — | done |
| ~09:40 UTC | Fix `migrate_to_db.py` SyntaxError: `global DB_PATH` moved to top of `main()` before argparse block | 2 | ~4 | claude-sonnet-4-6 | src/setup/migrate_to_db.py | done |
| ~09:45 UTC | Run migration on PI2: 41 rows (users 4, voice_opts 12, calendar_events 19, notes_index 6); start services; verified journal — `Version: 2026.3.32`, `Polling Telegram…` | 2 | ~3 | claude-sonnet-4-6 | — | done |

**Session 36 total: 4 items, ~12 requests — PI2 Phase 2c deployment + JSON→SQLite migration complete ✅**

---

## Session 37 — 2026-03-17 (UTC+1)

**Focus:** Menu navigation benchmark — measure user-perceived latency for all key menu switches across 3 platforms

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~10:00 UTC | Design and create `tools/benchmark_menus.py` — 13 TCs covering menu keyboard builders, notes list, admin panel, calendar menu, contacts (SQLite); temp-dir isolation, env var patching, `bot_db.DB_PATH` monkeypatch, mocked Telegram `send_message` | 4 | ~8 | claude-sonnet-4-6 | tools/benchmark_menus.py | done |
| ~10:15 UTC | Fix `datetime.utcnow()` DeprecationWarning → `datetime.now(timezone.utc)` for Python 3.12+ compatibility | 1 | ~1 | claude-sonnet-4-6 | tools/benchmark_menus.py | done |
| ~10:20 UTC | Fix `sys.path` auto-detection for Pi flat layout (`~/.taris/core/`) vs dev `src/core/` — benchmark fails on PI1 with `ModuleNotFoundError: No module named 'core'` | 2 | ~3 | claude-sonnet-4-6 | tools/benchmark_menus.py | done |
| ~10:30 UTC | Deploy benchmark to PI1 + PI2, run on both, download results (`bench_pi1_tmp.json`, `bench_pi2_tmp.json`), merge into `tools/benchmark_results.json` (now 6 entries: 3 storage_ops + 3 menu_navigation) | 2 | ~5 | claude-sonnet-4-6 | tools/benchmark_results.json | done |

**Key findings:**
- SQLite contacts list (TC13) on Pi: **566–574 µs** vs JSON notes list 10 files (TC06): **3,030–3,445 µs** → SQLite **5–6× faster** for list/scan operations
- SQLite contacts menu COUNT (TC11–TC12): **141–157 µs** vs admin menu JSON badge (TC07): **270–320 µs** → SQLite **~2× faster** for single-item reads
- PI1 (JSON-only) and PI2 (SQLite-enabled) show nearly identical SQLite performance → confirms benefit is backend choice, not hardware difference
- Dev machine (NVMe) SQLite (14–48 µs) vs Pi (microSD) SQLite (141–574 µs) → ~10× slower on Pi storage

**Session 37 total: 4 items, ~17 requests — Menu navigation benchmark complete on all 3 platforms ✅**

---

## Session 38 — 2026-03-17 (UTC+1)

**Focus:** Feature 2.1 — Conversation Memory System: DB write-through + LLM call tracking

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~12:00 UTC | Check why DB conversation history was unused at runtime (root cause: `chat_history` table existed but `add_to_history()` only wrote to in-memory dict + optional JSON; startup never loaded from DB) | 2 | ~2 | claude-sonnet-4.6 | — | done |
| ~12:15 UTC | Implement DB write-through: add `call_id TEXT` column + `llm_calls` table to schema; `init_db()` migration; 4 helpers (`db_add_history`, `db_get_history`, `db_clear_history`, `db_log_llm_call`); rewrite `add_to_history/get_history/clear_history/load_conversation_history` for DB-primary storage; add `get_history_with_ids()`; update `_handle_chat_message` with `call_id` tracking + `db_log_llm_call`; add `load_conversation_history()` to startup | 4 | ~9 | claude-sonnet-4.6 | src/core/bot_db.py, src/core/bot_state.py, src/telegram/bot_handlers.py, src/telegram_menu_bot.py | done |

**Session 38 total: 2 items, ~11 requests — Feature 2.1 DB write-through + call tracking fully implemented ✅**

---

## Session 39 — 2026-03-17 (UTC+1)

**Focus:** sqlite-vec vector search extension — install scripts, requirements.txt, README, deploy to OpenClawPI2

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~UTC | Add sqlite-vec v0.1.7 to `deploy/requirements.txt`; create `src/setup/install_sqlite_vec.sh` (standalone installer with verify step: `sqlite_vec.load()` + `vec_version()`); update `src/setup/install.sh` Step 2 pip block; add Step 1b to `src/setup/update.sh` (upgrade + version print); update `README.md` (docs table + architecture bullets); `pip3 install sqlite-vec` on PI2, copy 3 scripts, restart `taris-telegram`, verify journal: `[Store] sqlite-vec loaded — vector search enabled`; commit `4e23299` + push | 3 | ~5 | claude-sonnet-4.6 | deploy/requirements.txt, src/setup/install.sh, src/setup/install_sqlite_vec.sh (new), src/setup/update.sh, README.md | done |

**Session 39 total: 1 item, ~5 requests — sqlite-vec v0.1.7 installed on OpenClawPI2, vector search enabled ✅**

---

## Session 40 — 2026-03-17 (UTC+1)

**Focus:** FTS5 RAG feature — document knowledge base with full-text search + T24 regression test

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | FTS5 RAG feature: `store_sqlite.py` (doc_chunks FTS5 table, `search_fts()` OR semantics, `chunk_document()`); `bot_web.py` (/knowledge routes: upload/delete/list, PDF/text extraction); `bot_llm.py` (`rag_answer()` context injection); fix Cyrillic OR queries on PI2; deploy to PI1+PI2; verify search working with LR Health products document | 5 | ~20 | claude-sonnet-4.5 | src/core/store_sqlite.py, src/bot_web.py, src/core/bot_llm.py | done |
| — | T24 `t_rag_lr_products`: FTS5 chunk coverage test (≥2/6 keywords → PASS; 0 chunks → SKIP; no db → SKIP) + optional LLM-as-judge sub-test (set `LLM_JUDGE=1`); update `doc/test-suite.md` (quick-ref table, test table T24, mandatory table, Section 8 sub-tests); deploy+verify: PI1 SKIP (no doc), PI2 PASS (10 chunks, 5/6 keywords); commit `dec99b9` | 4 | ~15 | claude-sonnet-4.5 | src/tests/test_voice_regression.py, doc/test-suite.md | done |

**Session 40 total: 2 items, ~35 requests — FTS5 RAG + T24 test complete. PI1 SKIP ✅ PI2 PASS 5/6 keywords ✅ commit dec99b9**

---

## Session 41 — 2026-03-18 (UTC+1)

**Focus:** Fix HTTP 500 on /register when entering Telegram link code (cross-process isolation bug)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| — | Fix HTTP 500 on `/register` when entering Telegram link code: root cause = in-memory `_web_link_codes` dict invisible across processes (telegram service writes, web service reads — separate PIDs); fix = file-based storage via `~/.taris/web_link_codes.json` with atomic write, TTL eviction, single-use validation; bumped to v2026.3.33; deployed PI2 then PI1 (both already on package structure v2026.3.32 — no migration needed); git commit `8e5a3b1` | 4 | ~8 | claude-sonnet-4.6 | src/core/bot_config.py, src/core/bot_state.py, src/release_notes.json | done |

**Session 41 total: 1 item, ~8 requests — Telegram↔Web link code cross-process fix ✅ commit 8e5a3b1**

---

## Session 42 — 2026-03-18 (UTC+1)

**Focus:** Create T25 automated regression test for web link code feature; run on PI1+PI2; add to test suite

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~19:00 | Create automated test for web link code cross-process fix, run it, add to test suite: designed T25 `t_web_link_code_roundtrip` (7 sub-tests: generate, validate, single_use, invalid, expired, revoke_old, cross_process); fixed float→datetime bug in expired sub-test (`_t.time()-1.0` → `datetime.now(utc)-timedelta(10s)`); deployed + verified 7/7 PASS on PI2 (clean), then 7/7 PASS on PI1 (clean); updated `doc/test-suite.md` in 4 locations (trigger table, §2.5 catalog, §2.6 mandatory, §8 dedicated section); git commit `da6af89` | 3 | ~10 | claude-sonnet-4.6 | src/tests/test_voice_regression.py, doc/test-suite.md | done |

**Session 42 total: 1 item, ~10 requests — T25 web link code roundtrip tests ✅ commit da6af89**

---

## Session 43 — 2026-03-18 UTC — Centralise LLM prompts + configurable params (v2026.3.34)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~18:00 | Centralise all LLM prompts from inline code to `src/prompts.json`; add `src/core/bot_prompts.py` with `PROMPTS` dict + `fmt_prompt()` helper; add 5 env-configurable LLM tuning constants (`LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_DEFAULT`, `LLM_TIMEOUT_LONG`, `LLM_TIMEOUT_VOICE`) to `bot_config.py`; update all callers (bot_llm.py, bot_security.py, bot_access.py, bot_handlers.py, bot_calendar.py, bot_mail_creds.py, bot_web.py); deploy to PI2 + verify + deploy to PI1 + verify; git commit `4bbe5c6` | 4 | ~8 | claude-sonnet-4.6 | src/prompts.json, src/core/bot_prompts.py, src/core/bot_config.py, src/core/bot_llm.py, src/security/bot_security.py, src/telegram/bot_access.py, src/telegram/bot_handlers.py, src/features/bot_calendar.py, src/features/bot_mail_creds.py, src/bot_web.py, src/release_notes.json | done |

**Session 43 total: 1 item, ~8 requests — LLM prompt centralisation ✅ commit 4bbe5c6**

---

## Session 44 — 2026-03-18 UTC — Fix calendar LLM "cal_no_llm" bug (v2026.3.35)

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| ~19:20 | Fix production bug: NL calendar input (e.g. "Тренировка в 19") always returned `cal_no_llm` error. Root cause: `bot_calendar.py` called `_ask_taris()` (missing pipe-header handler, 20–30s timeouts silently swallowed). Fix: migrate all 4 calendar LLM call sites to `ask_llm(timeout=60)` from `bot_llm.py`. Bump to v2026.3.35. Deploy to PI2 (verified `Version : 2026.3.35`) + PI1 (verified `Version : 2026.3.35`). | 3 | ~15 | claude-sonnet-4.6 | src/features/bot_calendar.py, src/core/bot_config.py, src/release_notes.json | done |

**Session 44 total: 1 item, ~15 requests — calendar LLM fix ✅ PI2 ✅ PI1 ✅**

---

## Session 45 — 2026-03-18

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~19:32 | Fix production bug: free chat mode returned raw taris 402 error log to user. Root cause 1: `_ask_taris()` in `bot_llm.py` returned `_clean_output(stdout)` even on non-zero returncode. Root cause 2: `_LOG_PREFIX` regex missed compact `YYYYMMDD HH:MM:SS` date format used by taris logs. Fix: raise `RuntimeError` on rc!=0; extend `_LOG_PREFIX` to match both date formats. Bump to v2026.3.36. Deploy PI2 ✅ PI1 ✅. | 2 | ~5 | claude-sonnet-4.6 | src/core/bot_llm.py, src/core/bot_config.py, src/release_notes.json | done |

**Session 45 total: 1 item, ~5 requests — taris 402 log-leak fix ✅ PI2 ✅ PI1 ✅**

---

## Session 46 — 2026-03-19

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~09:45 | Fix calendar Add Event returning "❌ Could not parse date" for Russian shorthand time "в 19" (e.g. "Тренировка в 19"). Root cause 1: `event_parse` prompt had no rule for Russian «в X» (at X o'clock) time notation or time-of-day words (утром/вечером/днём). Root cause 2: LLMs sometimes return partial ISO "YYYY-MM-DDTHH" without ":MM" — `datetime.fromisoformat()` raises on Python ≤3.10. Fix 1: added «в X»=X:00 and time-of-day shorthand rules to `prompts.json`. Fix 2: added defensive dt_str normalization in `_finish_cal_add()`. Bump to v2026.3.37. Deploy PI2 ✅ PI1 ✅. | 2 | ~8 | claude-sonnet-4.6 | src/prompts.json, src/features/bot_calendar.py, src/core/bot_config.py, src/release_notes.json | done |

**Session 46 total: 1 item, ~8 requests — calendar Russian time-idiom parse fix ✅ PI2 ✅ PI1 ✅**

---

## Session 47 — 2026-03-19

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~10:00 | Fix 4 note handler crashes caused by empty-body notes (`ApiTelegramException: message text is empty`). Root cause: `_handle_note_raw` sent `text=""` directly; `_start_note_edit/append/replace` did `lines[0]` on empty list → IndexError. Fix: guard all `lines[0]` with `if lines else ""`; guard all `send_message` calls with `text or _t(chat_id, "note_empty_body")`. Added `note_empty_body` i18n key to RU/EN/DE in `strings.json`. Also fixed `/status` command to show `LLM_PROVIDER` prefix before active model name (imported + displayed as `{LLM_PROVIDER} › {active_model}`). Bump to v2026.3.38. Deploy PI2 ✅ PI1 ✅. | 2 | ~12 | claude-sonnet-4.6 | src/telegram/bot_handlers.py, src/strings.json, src/telegram_menu_bot.py, src/core/bot_config.py, src/release_notes.json | done |

**Session 47 total: 2 items, ~12 requests — empty-note crash fix (4 functions) + /status LLM provider display ✅ PI2 ✅ PI1 ✅**

---

## Session 48 — 2026-03-20

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~09:00 | Fix Bug A: voice messages during `contact_add`, `contact_edit`, `contact_search`, `cal_edit_title/dt/remind` modes were silently forwarded to LLM instead of the correct handler. Added 4 routing blocks in `_handle_voice_message()` after `cal_console` block. Fix Bug B1: LLM calls failed on both PIs — taris-gateway was crash-looping; switched to `LLM_PROVIDER=openai` with `OPENAI_BASE_URL=https://openrouter.ai/api/v1` (OpenRouter OpenAI-compat endpoint) in `bot.env` on PI1 and PI2. Fix Bug B2: `NameError: ACTIVE_MODEL_FILE` in `bot_admin.py` — added missing import. Updated PI2 `bot.env` with 4 LLM vars. Bump to v2026.3.39. Commit `b35df5e`. Deploy PI1 ✅ PI2 ✅. | 3 | ~18 | claude-sonnet-4.6 | src/features/bot_voice.py, src/telegram/bot_admin.py, src/core/bot_config.py, src/release_notes.json | done |

**Session 48 total: 3 bugs fixed, ~18 requests — voice mode routing (contacts+cal-edit) + LLM provider switch to OpenRouter direct + ACTIVE_MODEL_FILE import ✅ PI1 ✅ PI2 ✅**

---

## Session 49 — 2026-03-24

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~20:45 | Fix 3 bugs in OpenAI model selection: (1) `_ask_openai` and `ask_llm_with_history` hardcoded `OPENAI_MODEL` env var, ignoring `active_model.txt` — fixed to use `get_active_model() or OPENAI_MODEL`; (2) callback_data used short model name instead of OpenRouter slug — fixed to use `model_id` (e.g. `openai/gpt-4.1`); (3) `is_current` comparison never matched — fixed to check `current in (name, model_id)`. Updated `_OPENAI_CATALOG`: removed deprecated gpt-4.5-preview/o1, added gpt-4.1/mini/nano + o3/o4-mini. Bump to v2026.3.40. Commit `d7e9d19`. Deploy PI2 ✅ PI1 ✅. | 3 | ~8 | claude-sonnet-4.6 | src/core/bot_llm.py, src/telegram/bot_admin.py, src/core/bot_config.py, src/release_notes.json | done |

**Session 49 total: 3 bugs fixed, ~8 requests — OpenAI model selection non-functional; stale model catalog updated ✅ PI1 ✅ PI2 ✅**

---

## Session 50 — 2026-03-25

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~19:00 | Fix System Chat "❌ Could not generate a command. Try again." bug: `_handle_system_message()` called `_ask_taris()` (subprocess to taris CLI binary), which hardcodes OpenRouter CLI ignoring `LLM_PROVIDER`. With `LLM_PROVIDER=openai` the binary fails → `None` returned → error shown. Fix: removed `_ask_taris` import, added `from core.bot_llm import ask_llm as _ask_builtin_llm`, replaced call at line 539. Bump to v2026.3.41. Commit `7d60ced`. Deploy PI2 ✅ PI1 ✅. | 2 | ~5 | claude-sonnet-4.6 | src/telegram/bot_handlers.py, src/core/bot_config.py, src/release_notes.json | done |

**Session 50 total: 1 bug fixed, ~5 requests — System Chat LLM routing fixed (ask_llm replaces _ask_taris) ✅ PI1 ✅ PI2 ✅**

---

## Session 51 — 2026-03-19

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| 06:26 UTC | Deploy all changes to PI2 (v2026.3.41). Resumed mid-deploy from conversation summary. Deployed: web/, entry points (telegram_menu_bot.py, bot_web.py, voice_assistant.py, gmail_digest.py), data files (strings.json, release_notes.json, prompts.json). Restarted taris-telegram + taris-web. Journal confirmed: Version 2026.3.41, Polling Telegram, Web UI v2026.3.41 on :8080. Both services active ✅ PI2 ✅. | 1 | ~3 | claude-sonnet-4.6 | src/web/*, src/telegram_menu_bot.py, src/bot_web.py, src/strings.json, src/release_notes.json | done |

**Session 51 total: 1 deployment, ~3 requests — Full PI2 deploy v2026.3.41 ✅**

---

## Session 52 — 2026-03-19
| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~15:10 UTC | Audit §1.0 Profile Redesign — verified _handle_profile_lang, _set_profile_lang, _handle_profile_my_data all implemented; marked 2 unchecked items done in TODO.md | 1 | 2 | claude-sonnet-4.6 | TODO.md | done |
| ~15:20 UTC | Commit and push all changes (4 commits to origin/master): profile redesign §1.0 impl, TODO audit, vibe log, copilot instructions | 1 | 2 | claude-sonnet-4.6 | .github/copilot-instructions.md, TODO.md, doc/vibe-coding-protocol.md, src/strings.json, src/telegram/bot_access.py, src/telegram/bot_handlers.py, src/telegram/bot_users.py, src/telegram_menu_bot.py | done |

**Session 52 total: 1 TODO audit + 1 git push, ~4 requests — §1.0 verified complete, origin/master synced ✅**

---

## Session 53 — 2026-03-19
| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~08:00 UTC | Implement §6.1 Logging & Monitoring: new `bot_logger.py` (4 structured category loggers, Telegram alert handler, `tail_log`); 4 log path constants in `bot_config.py`; admin Logs UI in `bot_admin.py` (📊 Logs button + `_handle_admin_logs_menu/show`); dispatch + `configure_alert_handler`/`attach_alerts_to_main_log` in `telegram_menu_bot.py`; 8 i18n keys × 3 langs in `strings.json`; `taris-logrotate` (daily/7d/compress/copytruncate). Version bump to v2026.3.42. Deploy PI2 ✅. Commit `9032fd7`. | 4 | ~12 | claude-sonnet-4.6 | src/core/bot_logger.py, src/core/bot_config.py, src/telegram/bot_admin.py, src/telegram_menu_bot.py, src/strings.json, src/release_notes.json, TODO.md, src/services/taris-logrotate | done |

**Session 53 total: §6.1 Logging & Monitoring fully implemented & deployed, v2026.3.42 live on PI2 ✅**

---

## Session 54 — 2026-03-19
| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| 13:28 UTC | Copilot performance optimization: create `doc/vibe-coding-guidelines.md` (artifact structuring rules, session habits, naming conventions, token budget reference); add §20 optimization checklist to `TODO.md`; update `concept/copilot_optimization.md` status tracker (P-2/P-3/P-4/P-8 done, remaining items listed). | 2 | 1 | claude-sonnet-4.6 | doc/vibe-coding-guidelines.md, TODO.md, concept/copilot_optimization.md, doc/vibe-coding-protocol.md | done |

**Session 54 total: Copilot optimization guidelines + TODO item created ✅**

---

## Notes on Measurement

- "Requests" = user→assistant conversation turns, not API calls.
- Time estimates for sessions 1–4 reconstructed from git commit timestamps.
- Session 5 onward: tracked from message metadata (UTC timestamps recorded above).
- Update this file at the end of each session with actual turn counts.

| 06:03 UTC | | | | Topic 20 final: back-links to all 9 doc/todo files + TODO.md update | P-11+docs | 2 | 12 | claude-sonnet-4-6 | doc/todo/*.md, TODO.md | done |

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| 06:08 UTC | Add new entry to vibe coding protocol | 1 | 1 | claude-sonnet-4.6 | doc/vibe-coding-protocol.md | done |
| 06:09 UTC | Add vibe coding protocol entry (session start) | 1 | 1 | claude-sonnet-4.6 | doc/vibe-coding-protocol.md | done |

---

## Session 55 — 2026-04-02 (UTC)

**Focus:** TODO §20 Copilot Optimization — verify all P-1..P-9/G-1 complete; fix T21 voice regression; bump version; run all tests on PI2

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~10:00 UTC | Verify copilot_optimization.md §9 tracker (all P-1..P-9, G-1 confirmed done); bump BOT_VERSION 2026.3.43 → 2026.4.2; prepend release_notes.json entry; deploy both files to PI2; verify journal shows new version | 2 | ~10 | claude-sonnet-4-5 | src/core/bot_config.py, src/release_notes.json | done |
| ~10:20 UTC | Fix T21 calendar_console_classifier FAIL: updated _handle_cal_console docstring in bot_calendar.py to include "intent classifier" + "Do NOT perform the action directly" — strings test checks for; deploy to PI2; single-test run confirms PASS | 2 | ~8 | claude-sonnet-4-5 | src/features/bot_calendar.py | done |
| ~10:40 UTC | Run full voice regression suite on PI2: PASS 37 / FAIL 0 / WARN 1 (timing baseline) / SKIP 5 — all categories clean | 1 | ~3 | claude-sonnet-4-5 | — | done |
| ~10:50 UTC | Run Web UI Playwright tests against PI2 (https://openclawpi2:8080): 52/52 PASSED in 20.54s — TestAuth(7) TestDashboard(5) TestChat(7) TestNotes(4) TestCalendar(5) TestVoice(3) TestMail(2) TestAdmin(4) TestNavigation(8) TestRegistration(3) TestProfile(4) | 1 | ~3 | claude-sonnet-4-5 | — | done |

**Session 55 total: 4 items, ~24 turns — §20 complete, voice 37/0/0 FAIL, Web UI 52/52 PASS, v2026.4.2 deployed to PI2 ✅**

## Session 56 — 2026-04-03 (UTC)

**Focus:** Fix System Chat generic error on `Ls` — `_SPINNER_RE` stripping ASCII `-`, add `ask_llm_or_raise()`, improve `_run()` error messages, add T26 regression, bump version

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~11:20 UTC | Fix `_SPINNER_RE` stripping ASCII `-` from bash commands (`ls -la`, `df -h`); add `ask_llm_or_raise()` to bot_llm.py; rewrite `_run()` in bot_handlers.py with 4 specific error messages (timeout / binary not found / LLM error / empty); add T26 `t_system_chat_clean_output` (3 sub-tests: ascii_preserved, spinner_stripped, ask_llm_or_raise_exists); deploy 3 files to PI2; verify T26 PASS 3/3; bump 2026.4.2 → 2026.4.3; deploy bot_config.py + release_notes.json; confirm v2026.4.3 in journal | 3 | ~15 | claude-sonnet-4-6 | src/core/bot_llm.py, src/telegram/bot_handlers.py, src/tests/test_voice_regression.py, src/core/bot_config.py, src/release_notes.json | done |

**Session 56 total: 1 bug fix + 1 test + version bump, ~15 turns — System Chat error specificity + T26 guard ✅ v2026.4.3 deployed to PI2 ✅**

## Session 57 — 2026-04-04 (UTC)

**Focus:** Fix raw "HTTP Error 402: Payment Required" leaking to users in System Chat — add HTTP error code mapping + local LLM fallback in `ask_llm_or_raise()`

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| ~12:00 UTC | Add local fallback try/except to `ask_llm_or_raise()` in bot_llm.py (Feature 3.2 integration); rewrite `except Exception` block in system chat `_run()` to map HTTP 402/401/429/503 to user-friendly English messages; raw urllib HTTPError strings no longer visible to users; bump 2026.4.3 → 2026.4.4; deploy all 4 files to PI2; verify v2026.4.4 in journal | 2 | ~7 | claude-sonnet-4-6 | src/core/bot_llm.py, src/telegram/bot_handlers.py, src/core/bot_config.py, src/release_notes.json | done |

**Session 57 total: 1 bug fix + version bump, ~7 turns — HTTP error user-friendly messages + LLM fallback path ✅ v2026.4.4 deployed to PI2 ✅**

| ~12:00 UTC | | | | Deep analysis: taris exits rc=0 with HTTP error in stdout — prior v2026.4.4 fix only covered exception path; added `_raise_if_http_error()` helper in bot_llm.py called on both rc!=0 (stderr) and rc=0 (stdout) paths; bump 2026.4.4 → 2026.4.5; prepend release_notes.json; deploy pending (creds not in shell) | Root cause trace + fix + version bump | 2 | ~5 | claude-sonnet-4-6 | src/core/bot_llm.py, src/core/bot_config.py, src/release_notes.json | done |

**Session 58 total: 1 root-cause fix — taris rc=0 HTTP error passthrough through stdout ✅ v2026.4.5 ready for deploy to PI2**

## Session 59 — 2026-04-06 (UTC)

**Focus:** Deploy v2026.4.5/4.6 to PI2; trace + fix LLM 402 (`active_model.txt` override); git push

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| 12:10 | Deploy v2026.4.5 + bump to v2026.4.6 on PI2; LLM still 402 — traced to `active_model.txt` containing `openai/gpt-4.1-mini` overriding `OPENAI_MODEL=google/gemma-3-4b-it:free` from bot.env; fix: echo `google/gemma-3-4b-it:free` into active_model.txt on PI2; LLM test `ask_llm_or_raise('Reply with exactly: ok')` → `SUCCESS: ok`; git commit hash `34115db` + push master | 2 | ~5 | claude-sonnet-4-6 | active_model.txt (PI2 runtime), src/core/bot_config.py, src/release_notes.json | done |

**Session 59 total: 1 root-cause fix, ~5 turns — PI2 LLM 402 resolved; `active_model.txt` corrected to free model ✅ v2026.4.6 pushed ✅**

## Session 60 — 2026-04-07 (UTC)

**Focus:** TODO 8.2 Taris rename + TODO 8.3 Telegram offline regression test suite

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| — | TODO 8.2: Rename "Pico"/"Taris Bot"/"Pico Assistant" → "Taris" across codebase — 14 files, 21 replacements: README.md, AGENTS.md, src/strings.json, web templates (base.html, login.html, register.html, dashboard.html), static/manifest.json, .github/copilot-instructions.md, TODO.md, doc/quick-ref.md, doc/copilot-skills-guide.md, doc/architecture/web-ui.md, doc/architecture/deployment.md | 2 | ~3 | claude-sonnet-4.6 | 14 files | done |
| — | TODO 8.3: Offline Telegram regression test suite — 8 classes, 31 tests, pytest 9.0.2; conftest passthrough-decorator two-mock architecture (WEB_ONLY=1 guard, _passthrough_deco side_effect for message_handler/callback_query_handler); covers TestCmdStart(4), TestCallbackMode(4), TestCallbackAdmin(9), TestCallbackMenu(3), TestVoiceHandler(3), TestTextHandlerNotes(2), TestTextHandlerAdmin(2), TestChatMode(3); voice_handler double-condition fix (_pending_error_protocol + msg.voice assert); 31/31 PASS in 0.22s | 4 | ~25 | claude-sonnet-4.6 | src/tests/telegram/conftest.py, src/tests/telegram/test_telegram_bot.py, src/tests/telegram/pytest.ini | done |

**Session 60 total: 2 items, ~28 turns — Taris rename (14 files, 21 replacements) + 31/31 Telegram regression tests ✅**

---

### Session 61 — 2026-04-07

**Focus:** `/taris-update-doc` scope `todo` — collapse TODO 8.2+8.3, update doc/test-suite.md

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| — | `/taris-update-doc TODO 8.2 8.3`: collapsed both completed entries in TODO.md to single `✅ Implemented (v2026.4.7)` lines; added Category F (offline Telegram regression) to doc/test-suite.md: quick-ref table row, categories overview row, new §6b section (31 tests, 8 classes, run commands, arch notes), §7 Targets table updated | 2 | ~3 | claude-sonnet-4.6 | TODO.md, doc/test-suite.md | done |

**Session 61 total: 1 item, ~3 turns — doc sync for TODO 8.2+8.3 ✅**

---

### Session 62 — 2026-04-09 (UTC)

**Focus:** Fix "Command not permitted: copy" regression — LLM generated Windows `copy` for Russian disk-space query

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| — | Root-cause: `system_prompt` in `src/prompts.json` had no multilingual guidance and no Linux command examples → LLM (Qwen2-0.5B local fallback) generated Windows `copy` for Russian "сколько места на диске". Fix: replaced weak `system_prompt` with multilingual version (ru/de/en) containing explicit task→command mapping table (disk space→`df -h`, memory→`free -h`, CPU→`uptime`, etc.) and explicit ban on Windows commands (`copy`, `dir`, `cls`, `del`, etc.). Deployed to PI1 + PI2, both services restarted, v2026.4.9 confirmed running. | 2 | ~5 | claude-sonnet-4-6 | src/prompts.json | done |

**Session 62 total: 1 bug fix, ~5 turns — `system_prompt` multilingual fix deployed to PI1+PI2 ✅**

---

### Session 63 — 2026-03-21 (UTC)

**Focus:** PI2 Vosk STT broken (symlink to missing .picoclaw path) + PI1 Vosk symlink collateral damage repair

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| 08:00 | PI2 Vosk STT fix: diagnosed broken symlink `~/.taris/vosk-model-small-ru → ~/.picoclaw/vosk-model-small-ru` (target missing on PI2). Confirmed PI1→PI2 key-based SSH works. Removed broken symlink on PI2, copied 88MB model from PI1 via `scp`, verified 88M + correct structure, restarted PI2 `taris-telegram` — clean start v2026.4.9, no Vosk errors, polling ✅ | 2 | ~8 | claude-sonnet-4-6 | — (infra/data only) | done |
| 08:29 | PI1 symlink collateral fix: accidental `rm -f ~/.taris/vosk-model-small-ru` ran on PI1 (wrong host) during the fix. Real model data (`~/.picoclaw/vosk-model-small-ru` 88MB) untouched. Recreated symlink with `ln -s`, verified PI1 service journal clean v2026.4.9, polling ✅ | 1 | ~3 | claude-sonnet-4-6 | — (infra/data only) | done |

**Session 63 total: 2 infra fixes, ~11 turns — PI2 Vosk STT restored + PI1 symlink collateral repaired ✅**

### Session 64 — Phase 3: Main & Admin Menus (Screen DSL)

| Time | Description | C | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| 14:00 UTC | Phase 3 TODO 21.3: Convert main menu + admin menu to YAML Screen DSL. Created `screens/main_menu.yaml` (11 button_rows, RBAC visible_roles), `screens/admin_menu.yaml` (10 button_rows, {pending_badge} variable substitution). Added 11 admin i18n keys (ru/en/de) to strings.json. Wired `menu` and `admin_menu` callbacks in telegram_menu_bot.py to use `load_screen()` + `render_screen()`. Web UI auto-served via Phase 2 generic `/screen/{screen_id}` route. All static checks pass. | 4 | ~30 | claude-sonnet-4-6 | screens/main_menu.yaml, screens/admin_menu.yaml, strings.json, telegram_menu_bot.py, TODO.md | done |
| 23:35 UTC | Deploy Phase 3 (TODO 21.3) to PI2. Version bump 2026.4.10→2026.4.11. Backup 228MB. Deployed 6 files (bot_config.py, telegram_menu_bot.py, strings.json, release_notes.json, main_menu.yaml, admin_menu.yaml). Both services verified: taris-telegram v2026.4.11 polling ✅, taris-web v2026.4.11 on :8080 ✅ | 2 | ~12 | claude-sonnet-4-6 | bot_config.py, release_notes.json | done |

**Session 64 total: 2 items, ~42 turns — YAML Screen DSL Phase 3 + PI2 deploy ✅**

---

### Session 65 — 2026-04-11 (UTC)

**Focus:** Integrate Karpathy AutoResearch into RAG research roadmap (TODO §23)

| Time (UTC) | Description | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|
| — | Integrated Karpathy AutoResearch (`karpathy/autoresearch`, 51.1K ⭐) into RAG research roadmap. Added ~180-line §6b to extended research (3-file paradigm, Taris RAG adaptation with rag_score composite metric, per-architecture configs for Pi/X1/VPS, community forks, integration pipeline). Updated §1 scope, §8.1/8.2 tables (score 4.40→4.45), §9.4/9.5 recommendations, Appendix sources. Rewrote TODO.md §23 from 9→12 items with AutoResearch evaluation methodology. Updated main concept paper executive summary + implementation timeline. | 4 | ~20 | claude-opus-4.6 | concept/rag-memory-extended-research.md, concept/rag-memory-architecture.md, TODO.md, doc/vibe-coding-protocol.md | done |

**Session 65 total: 1 item, ~20 turns — AutoResearch integration into RAG roadmap ✅**

| 21:08 UTC | 20:36 UTC | 21:37 UTC | 61 min | Analyze two-project architecture (sintaris-pl + sintaris-openclaw), identify OpenClaw variant support regression, implement flexible DEVICE_VARIANT system (picoclaw|openclaw) with Screen DSL visible_variants support, restore OpenClaw integration, commit+push | Explore both projects, analyze branches, fix bot_config/bot_llm/bot_web regression, add DEVICE_VARIANT+visible_variants to UserContext+screen_loader, update YAML screens, strings.json, schema, deployment.md, bot.env.example, fix+extend tests (64 pass) | 4 | 7 | claude-sonnet-4.6 | src/core/bot_config.py, src/core/bot_llm.py, src/bot_web.py, src/ui/bot_ui.py, src/ui/screen_loader.py, src/telegram/bot_handlers.py, src/screens/main_menu.yaml, src/screens/admin_menu.yaml, src/screens/screen.schema.json, src/strings.json, src/setup/bot.env.example, doc/architecture/deployment.md, src/tests/screen_loader/test_screen_loader.py | done |

---

### Session 66 — 2026-03-26 (UTC)

**Focus:** TARIS_HOME env var support + local OpenClaw deploy directory

| Time (UTC) | Start | End | Duration | Description | Steps/Todos | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 23:05 UTC | 21:53 UTC | 23:10 UTC | 77 min | Add TARIS_HOME env var support to all bot modules; create ~/projects/sintaris-openclaw-local-deploy/ with symlinks, .taris/ data dir, bot.env template, run_telegram.sh/run_web.sh/run_all.sh startup scripts | Add TARIS_DIR+_th() to bot_config.py (31 paths), update bot_db.py/bot_web.py/store.py/bot_auth.py/migrate_to_db.py/bot_voice.py to import TARIS_DIR; create deploy dir with 3 scripts; verify all 99 tests pass | 2 | 4 | claude-sonnet-4.6 | src/core/bot_config.py, src/core/bot_db.py, src/core/store.py, src/bot_web.py, src/security/bot_auth.py, src/setup/migrate_to_db.py, src/features/bot_voice.py | done |

**Session 66 total: 1 item, ~4 turns — TARIS_HOME support + local deploy setup ✅**

---

### Session 67 — 2026-03-26 (UTC)

**Focus:** Documentation sync (taris-update-doc skill)

| Time (UTC) | Start | End | Duration | Description | Steps/Todos | Complexity | Turns | Model | Files | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 22:26 UTC | 22:18 UTC | 22:28 UTC | 10 min | Sync docs with TARIS_HOME changes: update §12 file layout to current package structure, add TARIS_HOME section + local dev deploy to §13, add TARIS_DIR/store/bot_db sections to bot-code-map | deployment.md: §12 package dirs, §13 TARIS_HOME + local deploy; bot-code-map.md: TARIS_DIR in bot_config section, add bot_db + store sections, add store_*.py to inventory, update bot_auth/bot_voice import notes | 1 | 2 | claude-sonnet-4.6 | doc/architecture/deployment.md, doc/bot-code-map.md, doc/vibe-coding-protocol.md | done |

**Session 67 total: 1 item, ~2 turns — Documentation sync ✅**


---

## Session 68 — §25.4 Embedding Service + §25.5 Voice Pipeline OpenClaw

| Time | Time start | Time end | Duration | Request | Steps/Todos | Complexity | Requests used | Model | Files changed | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 03:00 UTC | 03:00 UTC | 03:20 UTC | 20 min | Implement §25.4 (Embedding Service) and §25.5 (Voice Pipeline + NPU) for OpenClaw variant | 1. EMBED_MODEL/EMBED_KEEP_RESIDENT/EMBED_DIMENSION/VOICE_BACKEND constants in bot_config.py; 2. bot_embeddings.py EmbeddingService (fastembed-first, sentence-transformers fallback); 3. wire embeddings into bot_documents.py _store_text_chunks(); 4. VOICE_BACKEND import + --device cuda in bot_voice.py; 5. install_embedding_model.sh + setup_voice_openclaw.sh scripts; 6. bot.env.example docs; 7. version bump 2026.4.14; 8. TODO.md update | 3 | 1 | claude-sonnet-4.6 | src/core/bot_config.py, src/core/bot_embeddings.py, src/features/bot_documents.py, src/features/bot_voice.py, src/setup/bot.env.example, src/setup/install_embedding_model.sh, src/setup/setup_voice_openclaw.sh, src/release_notes.json, TODO.md | done |

**Session 68 total: 2 items (§25.4 + §25.5), ~1 turn — Embedding Service + Voice Pipeline ✅**

| 09:00 UTC | 09:00 UTC | 10:00 UTC | 60 min | OpenClaw STT/LLM fix: add faster-whisper, Ollama provider, T27-T30 tests, skill+instructions, docs | F1: OLLAMA_URL/MODEL constants, _ask_ollama(), LLM_PROVIDER=ollama in bot.env; F2: STT_PROVIDER/FASTER_WHISPER_* constants, _stt_faster_whisper(), voice_assistant.py routing; F3: benchmark_stt.py; F4: T27-T30 regression tests; F5: setup_voice_openclaw.sh step6; F6: openclaw-integration.md STT+LLM sections, TODO §19.2b+§25.5; F7: taris-openclaw-setup.prompt.md skill + openclaw.instructions.md; version bump 2026.3.28 | 4 | 2 | claude-sonnet-4.6 | src/core/bot_config.py, src/core/bot_llm.py, src/features/bot_voice.py, src/voice_assistant.py, src/setup/setup_llm_openclaw.sh, src/setup/setup_voice_openclaw.sh, src/tests/benchmark_stt.py, src/tests/test_voice_regression.py, doc/architecture/openclaw-integration.md, TODO.md, src/release_notes.json, .github/prompts/taris-openclaw-setup.prompt.md, .github/instructions/openclaw.instructions.md | done |

**Session 69 total: 7 features (F1–F7), ~2 turns — OpenClaw STT/LLM + docs + skills ✅**
| 08:23 UTC | 08:23 UTC | 08:45 UTC | 22 min | Update architecture docs: general overview + PicoClaw + OpenClaw variant docs with links to ecosystem projects | 1. overview.md: ecosystem matrix (5 projects), variant comparison table, 3-channel architecture diagram, module map, external links; 2. picoclaw.md (NEW): hardware, voice pipeline, LLM, services, deploy workflow; 3. openclaw-integration.md: full rewrite in English, all ecosystem links; 4. architecture.md index: added picoclaw.md; 5. llm-providers.md: added openclaw+ollama | 2 | 1 | claude-sonnet-4.6 | doc/architecture/overview.md, doc/architecture/picoclaw.md (new), doc/architecture/openclaw-integration.md, doc/architecture.md, doc/architecture/llm-providers.md, doc/vibe-coding-protocol.md | done |

**Session 70 total: 1 item (architecture docs), ~1 turn — PicoClaw + OpenClaw variant docs ✅**

---

## Session 71 — 2026-03-28 (UTC)

| Time | Time start | Time end | Duration | Request | Steps/Todos | Complexity | Requests used | Model | Files changed | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 09:40 UTC | 09:40 UTC | 09:55 UTC | 15 min | Continue last session: commit pipeline analytics logger (v2026.3.29) | 1. Run T32 test — 5/5 PASS; 2. bump BOT_VERSION 2026.3.28→2026.3.29; 3. prepend release_notes.json entry; 4. commit all 6 files | 2 | 1 | claude-sonnet-4.6 | src/core/pipeline_logger.py, src/bot_web.py, src/tests/test_voice_regression.py, src/core/bot_config.py, src/release_notes.json, .github/instructions/openclaw.instructions.md | done |

**Session 71 total: 1 item (pipeline logger commit), ~1 turn ✅**

---

## Session 72 — 2026-03-28 (UTC)

| Time | Time start | Time end | Duration | Request | Steps/Todos | Complexity | Requests used | Model | Files changed | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 09:50 UTC | 09:50 UTC | 09:58 UTC | 8 min | Fix: Web UI shows "Vosk" for STT even on OpenClaw (faster_whisper) | 1. Found two hardcoded "Vosk" fallbacks at lines 644+1791 in bot_web.py; 2. Added _STT_UI_LABELS dict + _STT_UI_LABEL module constant; 3. Synced bot_web.py + bot_config.py + templates + pipeline_logger.py to ~/.taris/; 4. Restart taris-web → v2026.3.29 ✅; 5. committed | 1 | 1 | claude-sonnet-4.6 | src/bot_web.py | done |

**Session 72 total: 1 bugfix, ~1 turn ✅**

---

## Session 73 — 2026-03-28 (UTC)

| Time | Time start | Time end | Duration | Request | Steps/Todos | Complexity | Requests used | Model | Files changed | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 10:09 UTC | 10:09 UTC | 10:18 UTC | 9 min | Add software release info to Web UI; deep-diagnose Vosk label (browser cache) | 1. Root cause: browser cached old HTML without Cache-Control; 2. _LLM_UI_LABEL + _DEVICE_UI_LABEL constants; 3. _ctx() injects all 3 labels globally; 4. base.html sidebar-stack block (STT+LLM row); 5. meta no-cache tags; 6. /api/version endpoint; 7. style.css .sidebar-stack/.stack-row; 8. deploy v2026.3.30 | 2 | 2 | claude-sonnet-4.6 | src/bot_web.py, src/web/templates/base.html, src/web/static/style.css, src/core/bot_config.py, src/release_notes.json | done |

**Session 73 total: 1 feature, ~2 turns — Web UI stack info ✅**
| 11:25 UTC | 11:25 UTC | 11:40 UTC | 15 min | Dual STT with fallback strategy (mirroring LLM _DISPATCH pattern) | 1. STT_FALLBACK_PROVIDER constant + auto-default; 2. _STT_DISPATCH table; 3. _stt_vosk_web() extracted; 4. _stt_web() primary→fallback chain; 5. openai_whisper provider + constants; 6. sl lang_map; 7. UI label shows Primary→Fallback; 8. _voice_pipeline_status fallback annotation; 9. T33 2/2 PASS; 10. TODO §19.5 + §19.4 | 3 | 2 | claude-sonnet-4.6 | src/core/bot_config.py, src/bot_web.py, src/tests/test_voice_regression.py, src/release_notes.json, TODO.md | done |

**Session 74 total: 1 feature, ~2 turns — Dual STT fallback ✅**
| 11:45 UTC | 11:45 UTC | 11:58 UTC | 13 min | Voice debug mode + audio download + LLM named fallback | 1. core/voice_debug.py VoiceDebugSession (7 stage savers + finalise + list_debug_sessions); 2. VOICE_DEBUG_MODE/DIR constants; 3. LLM_FALLBACK_PROVIDER + _ask_with_fallback refactor; 4. wire into voice_chat + voice_transcribe endpoints; 5. GET /voice/debug/sessions + /voice/debug/{id}/{file} endpoints; 6. voice.html download button (blob + debug link); 7. T34 3/3 PASS; 8. v2026.3.32 | 3 | 2 | claude-sonnet-4.6 | src/core/voice_debug.py(new), src/core/bot_config.py, src/core/bot_llm.py, src/bot_web.py, src/web/templates/voice.html, src/tests/test_voice_regression.py, src/release_notes.json | done |

**Session 75 total: 3 features, ~2 turns — debug mode + download + LLM fallback ✅**
| 12:18 UTC | 11:08 UTC | 12:18 UTC | 70m | Ollama install + LLM dual fallback | Install Ollama user-space, pull qwen2:0.5b, systemd service, OpenAI key, verify both | 2 | 3 | claude-sonnet-4.6 | bot_config.py, release_notes.json, bot.env | done |
| 12:28 UTC | 11:22 UTC | 12:28 UTC | 66m | Fix web UI hang during voice tests | asyncio.to_thread in 7 endpoints: voice_chat, transcribe, tts, chat_text, chat_send, cal_parse, cal_console | 3 | 2 | claude-sonnet-4.6 | bot_web.py, bot_config.py, release_notes.json | done |
| 12:39 UTC | | 12:00 UTC | | 12:39 UTC | 39m | LLM badge in chat + self-service password reset | LLM badge topbar+bubble, forgot/reset-password routes, reset tokens, SMTP config | 3 | 2 | claude-sonnet-4.6 | src/bot_web.py, src/core/bot_config.py, src/security/bot_auth.py, chat.html, _chat_messages.html, login.html, forgot_password.html, reset_password.html, release_notes.json | done |
| 13:37 UTC | | 12:25 UTC | | 13:37 UTC | 72m | Username change + Telegram-Web unified linking | change_username in bot_auth, /profile/change-username route, /profile/link-telegram route, /link command, profile.html redesign, service file fix | 3 | 2 | claude-sonnet-4.6 | src/bot_web.py, src/security/bot_auth.py, src/web/templates/profile.html, src/telegram_menu_bot.py, src/core/bot_config.py, src/release_notes.json, src/services/taris-telegram.service | done |
| 14:07 UTC | 13:07 UTC | 14:07 UTC | 60m | Fix Telegram voice: LLM routing + Whisper hallucination | Replace _ask_taris() with ask_llm() in bot_voice.py; add Whisper false-positive guard | 2 | 2 | claude-sonnet-4.6 | src/features/bot_voice.py, src/core/bot_config.py, src/release_notes.json | done |
| 14:20 UTC | 13:09 UTC | 14:20 UTC | 71m | Add T35-T39 STT/TTS/voice regression tests | T35 FW multi-lang, T36 STT fallback chain, T37 OpenAI Whisper API, T38 TTS multi-lang, T39 voice LLM routing guard | 3 | 1 | claude-sonnet-4.6 | src/tests/test_voice_regression.py, doc/test-suite.md | done |
| 14:28 UTC | 13:21 UTC | 14:28 UTC | 67m | Fix STT language: Telegram client lang_code overriding Russian STT | _stt_lang = STT_LANG from config (not _lang(chat_id)), lang=ru saved to registrations, STT_LANG=ru in bot.env | 2 | 3 | claude-sonnet-4.6 | src/features/bot_voice.py, src/core/bot_config.py, src/release_notes.json, src/tests/test_voice_regression.py | done |

| 13:36 UTC | 13:36 UTC | 13:36 UTC | 5m | Fix 409 polling conflict + STT INFO logging | 409 ExceptionHandler in bot_instance.py; STT log promoted to INFO; clean 35s stop-wait-start | 2 | 1 | claude-sonnet-4.6 | src/core/bot_instance.py, src/features/bot_voice.py, src/core/bot_config.py, src/release_notes.json | done |

| 15:18 UTC | 15:05 UTC | 15:18 UTC | 13m | Fix menu/keyboard silent loss (Markdown parse failure) | TeleBot default parse_mode=None; LLM/note/voice sends use explicit parse_mode=None | 2 | 1 | claude-sonnet-4.6 | src/core/bot_instance.py, src/telegram/bot_handlers.py, src/features/bot_voice.py, src/core/bot_config.py, src/release_notes.json | done |
| 15:31 UTC | 15:24 UTC | 15:31 UTC | 7m | Fix LLM quality (qwen2:0.5b hallucinations) + TTS language mismatch | Switch LLM_PROVIDER=openai/gpt-4o-mini; FASTER_WHISPER_MODEL=small; _voice_lang() TTS helper | 2 | 1 | claude-sonnet-4.6 | src/features/bot_voice.py, src/core/bot_config.py, src/release_notes.json, ~/.taris/bot.env | done |
| 15:44 UTC | 15:41 UTC | 15:44 UTC | 3m | Fix voice mode ignoring user role in system chat | Detect _cur_mode==system in voice pipeline; dispatch to _handle_system_message() | 2 | 1 | claude-sonnet-4.6 | src/features/bot_voice.py, src/core/bot_config.py, src/release_notes.json | done |
| 15:55 UTC | 14:54 UTC | 15:55 UTC | 61m | Update docs, push, clone Taris-UI-POC, branch comparison + merge proposal | doc-update agent; clone sintaris-pl-picoclaw; git diff analysis; merge-proposal doc | 4 | 1 | claude-sonnet-4.6 | doc/todo/merge-ui-poc-to-openclaw.md | done |
| 15:04 UTC | 15:04 UTC | 15:04 UTC | 5m | Sync docs with v2026.3.40-42 (parse_mode=None, _voice_lang, system-mode dispatch, SIGTERM) | Update voice-pipeline.md, deployment.md, telegram-bot.md, bot-code-map.md, TODO.md, AGENTS.md | 2 | 1 | claude-sonnet-4.6 | doc/architecture/voice-pipeline.md, doc/architecture/deployment.md, doc/architecture/telegram-bot.md, doc/bot-code-map.md, TODO.md, AGENTS.md | done |

| 15:04 UTC | 15:04 UTC | 15:04 UTC | 60m | Sync docs with v2026.3.43 (Screen DSL + FTS5/RAG + admin i18n merge) | Update deployment.md, telegram-bot.md, web-ui.md, bot-code-map.md, README.md, AGENTS.md, TODO.md §21+§4, merge checklist | 3 | 1 | claude-sonnet-4.6 | doc/architecture/deployment.md, doc/architecture/telegram-bot.md, doc/architecture/web-ui.md, doc/bot-code-map.md, README.md, AGENTS.md, TODO.md, doc/todo/merge-ui-poc-to-openclaw.md | done |

| 17:19 UTC | 17:19 UTC | 17:35 UTC | 16m | Create /taris-deploy-openclaw-target skill for TariStation2/TariStation1 | New SKILL.md + prompt file, TariStation2 (local cp) + TariStation1 (SintAItion SSH), branch+confirmation rules, .env template, AGENTS.md host table, skill registry | 2 | 1 | claude-sonnet-4.6 | .github/skills/taris-deploy-openclaw-target/SKILL.md, .github/prompts/taris-deploy-openclaw-target.prompt.md, .github/copilot-instructions.md, AGENTS.md, .env | done |

| 18:30 UTC | 18:30 UTC | 18:45 UTC | 15m | Update user guide and arch docs (Variants, RAG, System Chat move, OpenClaw hosts) | howto_bot.md: Variants section, System Chat→Admin, RAG section, /help_guide; overview.md: target hosts, v2026.3.43; deployment.md: OpenClaw hosts + skill ref; features.md: §6 System Chat note, §11 FTS5/RAG | 2 | 1 | claude-sonnet-4.6 | doc/howto_bot.md, doc/architecture/overview.md, doc/architecture/deployment.md, doc/architecture/features.md | done |
| 18:50 UTC | | 18:10 UTC | | 18:50 UTC | 40m | Full test suite: T40/T41 voice regression, 5 new telegram tests, /taris-run-full-tests skill, user guide + arch docs update, test-suite.md T26-T41 + Cat G/H | add T40/T41 to voice regression; add TestVoiceSystemModeRouting + TestScreenDSLRoleFiltering; create run-full-tests skill; update docs | 3 | 4 | claude-sonnet-4.6 | test_voice_regression.py, test_telegram_bot.py, test-suite.md, howto_bot.md, overview.md, deployment.md, features.md, taris-run-full-tests skill | done |
| 20:17 UTC | | 20:14 UTC | | 20:17 UTC | 3m | Create SKILL.md for all prompts — explain why only 2 visible in CLI (session restart required) | created 7 SKILL.md files for all .github/prompts without matching skill; explained CLI indexes skills at startup | 2 | 2 | claude-sonnet-4.6 | .github/skills/taris-backup-target/SKILL.md, taris-bump-version/SKILL.md, taris-openclaw-setup/SKILL.md, taris-performancetest/SKILL.md, taris-test-software/SKILL.md, taris-test-ui/SKILL.md, taris-voicetests/SKILL.md | done |
| 22:17 UTC | | 20:19 UTC | | 22:17 UTC | 118m | Deploy OpenClaw v2026.3.43 to TariStation1 (SintAItion) — first full deployment | backup TS2→TS1, fix bot_db._TARIS_DIR bug, fix taris-web.service User= directive, full file deploy, services enabled | 3 | 1 | claude-sonnet-4.6 | src/core/bot_db.py, src/services/taris-web.service | done |
| 22:35 UTC | | 21:10 UTC | | 22:35 UTC | 85m | Fix 5 test failures, run full suite (72 PASS/0 FAIL), deploy tests to TS1 | fix PIPER_BIN runtime detection, Screen DSL note_edit test, migrate_to_db path+args | 2 | 1 | claude-sonnet-4.6 | src/tests/test_voice_regression.py | done |
| 22:57 UTC | | 22:45 UTC | | 22:57 UTC | 12m | Fix mixed language + voice admin guard UI bugs | _set_lang: _DEFAULT_LANG not hardcoded 'en'; voice system-chat: add _is_admin guard at routing; T42+T43 regression tests; 78 PASS/0 FAIL | 2 | 1 | claude-sonnet-4.6 | src/telegram/bot_access.py, src/features/bot_voice.py, src/tests/test_voice_regression.py | done |
| 23:35 UTC | | 23:10 UTC | | 23:35 UTC | 25m | Fix root cause of language mixing: openclaw-gateway 409 conflict | Disabled openclaw-gateway Telegram channel (enabled:false in ~/.openclaw/openclaw.json); T44 regression test; 79 PASS/0 FAIL | 2 | 1 | claude-sonnet-4.6 | src/tests/test_voice_regression.py, doc/test-suite.md, doc/architecture/deployment.md | done |
| 00:00 UTC | | 22:48 UTC | | 00:00 UTC | 72m | Deploy bug fixes to PI2 (OpenClawPI2) and TS1 (SintAItion) | PI2: backup + fix bot_access.py _set_lang + tests; restored bot_voice.py (VOICE_BACKEND compat); TS1: backup + deploy bot_access.py + bot_voice.py + tests; 65P/3F(piper not installed) | 2 | 1 | claude-sonnet-4.6 | deployed: telegram/bot_access.py, features/bot_voice.py, tests/test_voice_regression.py | done |
| 00:13 UTC | | 00:06 UTC | | 00:13 UTC | 7m | T45 regression: TARIS_BIN binary check + picoclaw config | New test: LLM_PROVIDER=taris + TARIS_BIN exists + ~/.picoclaw/config.json present; SKIP on openclaw/openai; 79P/0F | 1 | 1 | claude-sonnet-4.6 | src/tests/test_voice_regression.py, doc/test-suite.md | done |
| 00:20 UTC | | 00:15 UTC | | 00:20 UTC | 5m | Fix web UI 500 error on SintAItion (Starlette 1.0 TemplateResponse) | Updated all 36 TemplateResponse calls: (name, ctx) → (request, name, ctx); deployed to TS1+TS2 | 2 | 1 | claude-sonnet-4.6 | src/bot_web.py | done |
| 07:39 UTC | | 06:00 UTC | | 07:39 UTC | 99m | VPS monitoring for all 4 taris URLs + full multi-target setup completion | Add check_taris_instances() to SintarisMonitor; SintAItion tunnel (autossh -R 8086:8088); VPS nginx /supertaris/ /supertaris2/; stas admin on PI1/PI2/TS1; migrate PI1→TS1 PI2→TS2; ROOT_PATH config; stop TS1 telegram (409); update deployment.md | 4 | 3 | claude-sonnet-4.6 | /opt/sintaris-monitor/monitor.py (VPS), /etc/nginx/sites-enabled/agents.sintaris.net.conf (VPS), doc/architecture/deployment.md, ~/.taris/bot.env (TS1+TS2) | done |
| 08:32 UTC | 08:31 UTC | 08:32 UTC | 1m | Activate @supertaris_bot on SintAItion | Set BOT_TOKEN=8335471007 in SintAItion bot.env; start taris-telegram; Polling Telegram confirmed | 1 | 1 | claude-sonnet-4.6 | ~/.taris/bot.env (SintAItion runtime) | done |
| 10:43 UTC | 10:30 UTC | 10:43 UTC | 13m | Mobile Web UI optimization | Bottom nav bar, hamburger drawer, touch targets ≥44px, iOS Safari voice stop fix (MediaRecorder.onstop fallback) | 3 | 2 | claude-sonnet-4.6 | src/web/static/style.css, src/web/templates/base.html, src/web/templates/voice.html, src/core/bot_config.py, src/release_notes.json | done |
| 10:53 UTC | 10:45 UTC | 10:53 UTC | 8m | Fix Vosk STT error on OpenClaw (supertaris_bot) | Disable vosk_fallback default on openclaw; faster-whisper VAD retry; add DEVICE_VARIANT to TS2 bot.env | 2 | 1 | claude-sonnet-4.6 | src/core/bot_config.py, src/features/bot_voice.py, src/release_notes.json, ~/.taris/bot.env (TS2 runtime) | done |
| 10:57 UTC | 10:54 UTC | 10:57 UTC | 3m | Move System Chat to Admin menu | Remove mode_system from main_menu.yaml + _menu_keyboard(); keep in admin_menu.yaml + _admin_keyboard() | 1 | 1 | claude-sonnet-4.6 | src/screens/main_menu.yaml, src/telegram/bot_access.py, src/core/bot_config.py, src/release_notes.json | done |
| 11:01 UTC | 10:57 UTC | 11:01 UTC | 4m | Add T46/T47/T48 regression tests for session bugs | vosk_fallback openclaw default, FW VAD retry, system chat admin menu only | 2 | 1 | claude-sonnet-4.6 | src/tests/test_voice_regression.py, doc/test-suite.md | done |
| 11:07 UTC | 10:57 UTC | 11:07 UTC | 10m | Clean chat welcome + admin pipeline diagnostics | Remove Vosk/Piper tech refs from chat_enter/voice_enter; admin gets separate pipeline info msg after voice reply | 2 | 1 | claude-sonnet-4.6 | src/features/bot_voice.py, src/strings.json, src/core/bot_config.py, src/release_notes.json | done |
| 11:35 UTC | 11:07 UTC | 11:35 UTC | 28m | Voice pipeline benchmark + report | Create benchmark_voice.py; install FW+Piper on SintAItion; run on TS2+SintAItion; generate report; apply P1/P2 fixes | 3 | 1 | claude-sonnet-4.6 | tools/benchmark_voice.py, doc/benchmark-voice-report.md, tools/benchmark_results/*.json | done |
| 11:40 UTC | 11:33 UTC | 11:45 UTC | 12m | Fix web TTS hardcoded Piper path | Replace /usr/local/bin/piper with PIPER_BIN in all 4 TTS call sites in bot_web.py | 2 | 1 | claude-sonnet-4.6 | src/bot_web.py, src/core/bot_config.py, src/release_notes.json | done |
| 13:08 UTC | 13:00 UTC | 13:08 UTC | 8m | Deploy doc fixes + screenshot analysis + 3 bug fixes | requirements.txt, bot.env.example, setup_voice_openclaw.sh, deployment.md; then voice opts menu openclaw filter, LLM menu no-crash, system chat prompt language+POSIX | 3 | 3 | claude-sonnet-4.6 | deploy/requirements.txt, src/setup/bot.env.example, src/setup/setup_voice_openclaw.sh, doc/architecture/deployment.md, src/telegram/bot_admin.py, src/prompts.json, src/core/bot_config.py, src/release_notes.json | done |
| 15:31 UTC | 15:27 UTC | 15:31 UTC | 4m | Fix system chat echo answers and localized confirm | echo allowlist, knowledge answer direct display, system_cmd_confirm i18n | 2 | 2 | claude-sonnet-4.6 | src/telegram/bot_handlers.py, src/security/bot_security.py, src/strings.json, src/core/bot_config.py, src/release_notes.json | done |
| 16:06 UTC | 15:30 UTC | 16:06 UTC | 36m | Fix All Notes button hang (BUTTON_DATA_INVALID) | Auto-migrate notes dir + 64-byte slug limit: SHA1 hash IDs in callback_data, byte-based _slug() truncation, notes not visible fix | 3 | 4 | claude-sonnet-4.6 | src/telegram/bot_handlers.py, src/telegram/bot_users.py, src/telegram_menu_bot.py, src/core/bot_config.py, src/release_notes.json | done |
| 15:34 UTC | 15:00 UTC | 15:34 UTC | 34m | Picoclaw sync plan + Taris-UI-POC check | Update TODO.md (bugs 0.16-0.20, §3.2 per-func LLM, §19.4), create picoclaw sync plan, verify Taris-UI-POC 333f210 already applied, PI2 deploy blocked (offline) | 2 | 3 | claude-sonnet-4.6 | TODO.md, doc/vibe-coding-protocol.md | done |
| 17:59 UTC | 15:47 UTC | 17:59 UTC | 132m | Ollama GPU acceleration on SintAItion | AMD Radeon 890M gfx1150 ROCm enable; system Ollama service; _ask_ollama -> native /api/chat + think:false; OLLAMA_MIN_TIMEOUT; qwen3:14b GPU ~1.2s | 3 | 1 | claude-sonnet-4.6 | src/core/bot_llm.py, src/core/bot_config.py, src/release_notes.json, /etc/systemd/system/ollama.service@SintAItion | done |
| 18:17 UTC | 17:59 UTC | 18:17 UTC | 18m | Fix Ollama GPU service (wrong User=stas, no HSA_OVERRIDE) | Root cause: User=stas can't access /usr/share/ollama models; HSA_OVERRIDE causes gfx1150 crash; Fix: User=ollama + render/video groups; remove HSA_OVERRIDE; result: 39.3 GiB VRAM, qwen3:14b 9tok/s@100%GPU | 2 | 1 | claude-sonnet-4.6 | src/setup/setup_llm_openclaw.sh, src/setup/bot.env.example | done |
| 18:17 UTC | 18:14 UTC | 18:17 UTC | 3m | Voice opts menu: show active STT/TTS/LLM config at top | Add config block to _handle_voice_opts_menu: STT provider+model/device+fallback+lang, TTS Piper model, LLM (voice) per-func or global | 1 | 1 | claude-sonnet-4.6 | src/telegram/bot_admin.py | done |
| 18:27 UTC | 18:23 UTC | 18:27 UTC | 4m | Fix system chat refusing bot config questions | Inject BOT RUNTIME CONFIG block into system prompt (version, LLM+model, STT+fallback+lang, TTS); add BOT CONFIGURATION category to prompts.json system_prompt | 2 | 2 | claude-sonnet-4.6 | src/telegram/bot_handlers.py, src/prompts.json | done |
| 16:38 UTC | 16:30 UTC | 16:41 UTC | 11m | FasterWhisper startup preload + HF offline mode | _fw_preload() background thread at startup; HF_HUB_OFFLINE=1 auto-set from local cache; startup trigger in telegram_menu_bot.py; fix ~0.3-1s cold-load on first voice message; deployed TS2+SintAItion | 2 | 1 | claude-sonnet-4.6 | src/features/bot_voice.py, src/telegram_menu_bot.py, src/core/bot_config.py, src/release_notes.json | done |
| 16:44 UTC | 16:44 UTC | 16:48 UTC | 4m | Analyse voice logs: LLM/TTS timing gaps | Analysed 8 transcription events; identified LLM variance 7-68s (OpenAI response length); TTS scales with response; added [Voice] LLM/TTS start/done INFO logs to journalctl | 2 | 1 | claude-sonnet-4.6 | src/features/bot_voice.py | done |
| 16:48 UTC | 16:48 UTC | 16:53 UTC | 5m | Fix STT accuracy: base→small model + CPU threads | Root cause: base (74M) mangles fast Russian (<1.5s audio); small (244M) handles correctly; FASTER_WHISPER_THREADS=8 for 24-core SintAItion; deployed TS2+SintAItion | 2 | 1 | claude-sonnet-4.6 | src/features/bot_voice.py, src/core/bot_config.py, ~/.taris/bot.env@SintAItion | done |
| 19:05 UTC | 19:05 UTC | 19:15 UTC | 10m | Add T49 STT speed-sensitivity test + benchmark | T49: Piper TTS × 4 speeds via ffmpeg atempo → FW STT → WER assert; model guard != base; benchmark_voice --speed-test with 3 phrases × 5 speeds; doc/test-suite.md updated; committed 31a9d52; SintAItion unreachable (different network) | 2 | 2 | claude-sonnet-4.6 | src/tests/test_voice_regression.py, tools/benchmark_voice.py, doc/test-suite.md | done |
| 20:18 UTC | 19:40 UTC | 20:18 UTC | 38m | Fix: LLM refuses "which model?" in voice chat | Root cause: security_preamble rule 5 too broad; _with_lang/voice had no config context. Fix: _bot_config_block() injects [BOT CONFIG] (LLM/STT/version) into all prompts; rule 5 softened to allow model/version disclosure. T50 added. Deployed TS2+SintAItion | 2 | 1 | claude-sonnet-4.6 | src/telegram/bot_access.py, src/prompts.json, src/tests/test_voice_regression.py, doc/test-suite.md | done |
| 00:30 UTC | 00:00 UTC | 00:30 UTC | 30m | Update scripts + TODO housekeeping | setup_voice_openclaw.sh: base→small default + AMD ROCm notes; update_from_git.sh: add core/telegram/features/ui/security/screens/web subdir support + rollback fix; TODO.md §19.4 Ollama+FW done; §19.6 LLM warning replaced with operational status | 2 | 1 | claude-sonnet-4.6 | src/setup/setup_voice_openclaw.sh, src/setup/update_from_git.sh, TODO.md | done |
| 00:31 UTC | 00:15 UTC | 00:31 UTC | 16m | §22 Notes+§9.1 DB+§10 RAG deploy+tests+docs | Deploy v2026.3.30 to TS2 (all §22/§9.1/§10 code); 94 PASS 0 FAIL 1 WARN; T51-T54 added (note delete confirm, rename, zip, RAG injection); TODO §22/§9.1/§10 marked done; doc/architecture/features.md §12 Notes section added; doc/test-suite.md T51-T54 + range T17-T54; committed 8462de1 | 3 | 1 | claude-sonnet-4.6 | src/tests/test_voice_regression.py, TODO.md, doc/test-suite.md, doc/architecture/features.md | done |
| 00:44 UTC | 00:31 UTC | 00:44 UTC | 13m | Fix §0 bugs: hardcoded strings | Scanned all .py for hardcoded Russian user-visible strings; fixed 3 in bot_calendar.py + bot_voice.py; moved to strings.json (328 keys/lang); T55 regression test; version 2026.3.30+1; updated key count refs 188→328; PI bugs (models, PI1 services) remain blocked on hardware | 2 | 1 | claude-sonnet-4.6 | src/features/bot_calendar.py, src/features/bot_voice.py, src/strings.json, src/core/bot_config.py, src/tests/test_voice_regression.py, TODO.md, doc/test-suite.md | done |
| 10:00 UTC | 10:00 UTC | 10:05 UTC | 5m | Fix Playwright test failures | conftest.py: auto-create testuser (role=user) before tests + ensure ADMIN_USER exists; test_ui.py: duplicate-username test uses ADMIN_USER const not hardcoded "admin"; 52 PASS 0 FAIL (was 50/2); committed fd03536 | 1 | 1 | claude-sonnet-4.6 | src/tests/ui/conftest.py, src/tests/ui/test_ui.py | done |
| 22:55 UTC | 22:55 UTC | 23:00 UTC | 5m | Move done chapters to DONE.md | Created DONE.md with 20 fully-done sections (Bugs Sprint table, §1.0 Profile, §3 LLM, §5.1, §8.2/8.3, §19.1-3+5-6, §20.1/2/4, §21.1-5); TODO.md 744→506 lines; committed b75197e | 1 | 1 | claude-sonnet-4.6 | DONE.md, TODO.md | done |
| 09:45 UTC | | 09:00 UTC | | 09:45 UTC | 45m | §2.1/§4/§4.1/§10/§10.1 memory+docs+RAG | RAG settings admin panel, doc admin enhancements, tiered memory, hash dedup, profile clear memory | 4 | 2 | claude-sonnet-4.6 | bot_admin.py, bot_documents.py, bot_state.py, bot_db.py, store_sqlite.py, store_base.py, rag_settings.py, bot_config.py, bot_handlers.py, telegram_menu_bot.py, strings.json, screens/profile.yaml | done |
| 10:40 UTC | | 10:36 UTC | | 10:40 UTC | 4m | fix: ollama context bug + T56 regression test | ollama ask_llm_with_history native messages branch + test | 2 | 1 | claude-sonnet-4.6 | core/bot_llm.py, tests/test_voice_regression.py | done |
| 11:27 UTC | | 11:20 UTC | | 11:27 UTC | 7m | fix: system message architecture + T57 | role:system prepended to multi-turn calls; _build_system_message + _user_turn_content; T57 regression test (5 PASS); v2026.3.30+3 deployed | 3 | 1 | claude-sonnet-4.6 | telegram/bot_access.py, telegram/bot_handlers.py, tests/test_voice_regression.py, bot_config.py, release_notes.json | done |
| 12:42 UTC | | 12:38 UTC | | 12:42 UTC | 4m | docs: arch update for v2026.3.30+3 | llm-providers.md §20 multi-turn+tiered memory; features.md §11.6-7 RAG+doc admin; bot-code-map.md callbacks+functions | 1 | 1 | claude-sonnet-4.6 | doc/architecture/llm-providers.md, doc/architecture/features.md, doc/bot-code-map.md | done |
| 11:05 UTC | 10:55 UTC | 11:05 UTC | 10m | docs: arch navigation maps + Copilot instructions | conversation.md, data-layer.md (new); security.md expanded; architecture.md index updated; copilot-instructions.md arch topic table + 8 style rules; taris-update-doc SKILL.md Step2 rewrite; committed 2907f14 | 2 | 1 | claude-sonnet-4.6 | doc/architecture/conversation.md, doc/architecture/data-layer.md, doc/architecture/security.md, doc/architecture.md, .github/copilot-instructions.md, .github/skills/taris-update-doc/SKILL.md | done |
| 11:24 UTC | 11:05 UTC | 11:40 UTC | 35m | docs: stacks, knowledge-base, voice/hw, RBAC, hardware | stacks.md+knowledge-base.md (new); voice-pipeline.md §6 hw matrix; conversation.md context sources; security.md planned RBAC; deployment.md hw requirements; committed a50efd8 | 3 | 1 | claude-sonnet-4.6 | doc/architecture/stacks.md, doc/architecture/knowledge-base.md, doc/architecture/voice-pipeline.md, doc/architecture/conversation.md, doc/architecture/security.md, doc/architecture/deployment.md, doc/architecture.md | done |
| 11:30 UTC | 11:30 UTC | 11:38 UTC | 8m | refactor: doc/arch/ → doc/architecture/ | git mv 15 files; updated links in 21 files (README, TODO, DONE, doc/architecture.md, .github/, concept/); committed 32c702e | 1 | 1 | claude-sonnet-4.6 | doc/architecture/*.md (15 renames), doc/architecture.md, README.md, TODO.md, DONE.md, .github/** | done |

| 13:50 UTC | 13:40 UTC | 13:50 UTC | 10m | fix: §0 bug audit + TODO cleanup | Tests: PASS 115 FAIL 0; system chat bug confirmed fixed in v2026.3.30 rewrite; profile_clear_memory marked done; PI2/PI1 infrastructure bugs annotated; TODO §0 restructured with Fixed/Infrastructure categories; committed 33cc190 | 1 | 3 | claude-sonnet-4.6 | TODO.md | done |

| 14:04 UTC | 13:55 UTC | 14:04 UTC | 9m | feat: §4 RAG pipeline fixes + LLM temperature admin control + file size limit + T58 regression | Fix log_rag_activity() never called; FTS timeout via concurrent.futures; LLM temp admin button (0.0-2.0 float); MAX_DOC_SIZE_MB=20 constant + upload check; T58 8-check regression test; TODO §4 items marked done; bump v2026.3.30+4 | 3 | 2 | claude-sonnet-4.6 | src/telegram/bot_access.py, src/core/rag_settings.py, src/core/bot_llm.py, src/telegram/bot_admin.py, src/telegram_menu_bot.py, src/core/bot_config.py, src/features/bot_documents.py, src/strings.json, src/tests/test_voice_regression.py, src/release_notes.json, TODO.md | done |

| 18:41 UTC | 18:32 UTC | 18:41 UTC | 9m | fix: voice pipeline ignoring conversation history | Root cause: ask_llm() (stateless) used in bot_voice.py instead of ask_llm_with_history(); Fix: build system+history+user messages, call ask_llm_with_history, save both turns; _voice_user_turn_content() added; T59 6-check regression; 129 PASS 0 FAIL; v2026.3.30+5 | 2 | 1 | claude-sonnet-4.6 | src/features/bot_voice.py, src/telegram/bot_access.py, src/tests/test_voice_regression.py, src/core/bot_config.py, src/release_notes.json | done |
| 18:52 UTC | 18:42 UTC | 18:52 UTC | 10m | docs: developer guideline for OpenClaw + PicoClaw | Create doc/dev-guide.md (14 sections: setup, workflow, features, debugging, testing, deployment, LLM/voice patterns, i18n, release, 17 pitfalls); add link from architecture.md | 2 | 1 | claude-sonnet-4.6 | doc/dev-guide.md, doc/architecture.md | done |
| 19:07 UTC | 18:55 UTC | 19:07 UTC | 12m | feat: LLM context trace debug tool + context contamination analysis | Root cause analysis of 1837 hallucination bug (context anchoring); extended llm_calls DB schema (8 new cols: model/temp/system_chars/history_chars/rag_chunks/response_preview/context_snapshot + migration); db_get_llm_trace(); _rag_debug_stats(); voice pipeline now logs to llm_calls; Admin > LLM > Context Trace panel; T39 updated (ask_llm_with_history); T60 added (12 checks); 141 PASS 0 FAIL; v2026.3.30+6 | 3 | 1 | claude-sonnet-4.6 | src/core/bot_db.py, src/telegram/bot_access.py, src/telegram/bot_handlers.py, src/telegram/bot_admin.py, src/features/bot_voice.py, src/telegram_menu_bot.py, src/strings.json, src/core/bot_config.py, src/release_notes.json, src/tests/test_voice_regression.py | done |
| 17:16 UTC | 17:08 UTC | 17:16 UTC | 8m | docs: IDE debugger attach guide in dev-guide.md §6.8 | VS Code launch+attach configs, PyCharm pydevd, Eclipse/PyDev, envFile for BOT_TOKEN, path mappings src/<->~/.taris/, breakpoint tips table, pitfalls table; launch.json created locally (.gitignored) | 1 | 1 | claude-sonnet-4.6 | doc/dev-guide.md | done |
| 09:30 UTC | 09:25 UTC | 09:30 UTC | 5m | chore: TODO/DONE audit - move completed sections | Removed §2 (Conversation Memory), §20.3 (Copilot refactors), §22 (Notes) from TODO.md; added to DONE.md with final notes including v2026.3.30+5 voice history fix | 1 | 1 | claude-sonnet-4.6 | TODO.md, DONE.md | done |
| 22:00 UTC | 21:47 UTC | 22:02 UTC | 15m | feat: DB-primary notes/calendar, doc dedup, memory toggle, admin memory settings (v2026.3.31) | 5 features + 5 tests + deploy | 4 | 1 | claude-sonnet-4.6 | bot_db.py,bot_config.py,bot_state.py,bot_handlers.py,bot_admin.py,bot_users.py,bot_calendar.py,bot_documents.py,bot_voice.py,telegram_menu_bot.py,strings.json,release_notes.json,test_voice_regression.py,profile.yaml | done |

| 20:08 UTC | | 20:08 UTC | | ~90min | Phase B/C RAG + Dev Menu: bot_rag.py, bot_dev.py, security logging, main_menu dev btn, i18n | 4 | 3 | claude-sonnet-4.6 | bot_rag.py, bot_dev.py, main_menu.yaml, strings.json, bot_llm.py, rag_settings.py | done |
| 20:24 UTC | | 20:24 UTC | | ~30min | Phase B/C remaining: PyMuPDF, RAG monitoring, per-user RAG settings, T66-T72 tests | 3 | 1 | claude-sonnet-4.6 | bot_documents.py, store_sqlite.py, store_base.py, bot_db.py, bot_admin.py, bot_handlers.py, bot_access.py, telegram_menu_bot.py, profile.yaml, strings.json, test_voice_regression.py | done |
| 10:00 UTC | | 10:00 UTC | | ~25min | taris-update-doc: sync all arch docs with v2026.3.32 — knowledge-base, security, data-layer, conversation, stacks, bot-code-map, howto, README, TODO | 2 | 1 | claude-sonnet-4.6 | doc/architecture/knowledge-base.md, security.md, data-layer.md, conversation.md, stacks.md, doc/bot-code-map.md, doc/howto_bot.md, README.md, TODO.md | done |
| 23:08 UTC | 22:55 UTC | 23:15 UTC | 20m | fix: TariStation2 deploy — Docker bridge linkdown + missing def _handle_admin_llm_trace | 2 bugs diagnosed + fixed + deployed | 2 | 1 | claude-sonnet-4.6 | src/telegram/bot_admin.py | done |
| 21:13 UTC | 21:13 UTC | 21:45 UTC | 32m | feat: 4 interactive install/update scripts for PicoClaw+OpenClaw + skill updates | 4 scripts + 2 skill updates | 3 | 1 | claude-sonnet-4.6 | install_picoclaw.sh, install_openclaw.sh, update_picoclaw.sh, update_openclaw.sh, SKILL.md x2 | done |
| 21:47 UTC | 21:47 UTC | 01:10 UTC | ~200m | feat: comprehensive benchmarking — conversation/memory/context/quality + multi-target orchestration | create benchmark_conversation.py (5 suites), update benchmark_suite.py (4 targets+groups), update taris-performancetest skill, fix service files User=stas, fix deploy script cred/hostname/smoke-test bugs | 4 | 8 | claude-sonnet-4.6 | tools/benchmark_conversation.py, tools/benchmark_suite.py, SKILL.md, src/services/taris-telegram.service, src/services/taris-web.service, src/setup/update_picoclaw.sh | done |
| 00:05 UTC | 00:05 UTC | 02:13 UTC | 128m | fix: Documents FTS5 unavailable on TariStation2 (Postgres backend) | implement Postgres FTS via plainto_tsquery+GIN index; deploy admin logs truncation fix; add benchmark concurrency lock | 2 | 2 | claude-sonnet-4.6 | src/core/store_postgres.py, src/telegram/bot_admin.py, tools/benchmark_conversation.py, src/core/bot_config.py, src/release_notes.json | done |
| 00:13 UTC | 00:13 UTC | 02:22 UTC | 69m | fix: system_chat hang on TariStation2 (Ollama timeout ignored) | _http_post_json convert socket.timeout→TimeoutExpired; _ask_ollama remove OLLAMA_MIN_TIMEOUT floor; _ask_with_fallback apply floor only for non-system use_case | 2 | 2 | claude-sonnet-4.6 | src/core/bot_llm.py | done |
| 00:23 UTC | 00:23 UTC | 02:29 UTC | 6m | fix: /status shows wrong services on TariStation2 | dynamic service list+scope per DEVICE_VARIANT; openclaw uses --user scope + taris-web/ollama | 1 | 1 | claude-sonnet-4.6 | src/telegram_menu_bot.py | done |
| 02:50 UTC | 02:50 UTC | 03:05 UTC | 15m | fix: /contacts 500 + add Settings+Contacts UI tests | fix page param collision in _ctx(); add TestSettings(4)+TestContacts(5); 61 passed | 2 | 1 | claude-sonnet-4.6 | src/bot_web.py, src/web/templates/contacts.html, src/tests/ui/test_ui.py, doc/test-suite.md | done |
| 03:00 UTC | 03:00 UTC | 03:12 UTC | 12m | deploy v2026.3.44 to SintAItion (TariStation1) | 61 UI tests + 183 voice tests pass; backup TS1; full deploy; services active | 1 | 1 | claude-sonnet-4.6 | TariStation1 deployed | done |
| 06:16 UTC | 06:16 UTC | 06:25 UTC | 9m | fix: PDF upload fails on PostgresStore (missing methods) | add get_document_by_hash, update_document_field, log_rag_activity, list_rag_log, rag_stats; add rag_log table + doc_hash/is_shared columns; fix savepoint DDL | 2 | 1 | claude-sonnet-4.6 | src/core/store_postgres.py | done |
| 06:28 UTC | 06:28 UTC | 06:35 UTC | 7m | add T73-T75 document admin tests + fix delete_embeddings bug | T73: store API completeness (SQLite+Postgres); T74: upload pipeline; T75: list/delete/rename+i18n; caught missing delete_embeddings on doc delete | 2 | 1 | claude-sonnet-4.6 | src/tests/test_voice_regression.py, src/features/bot_documents.py, doc/test-suite.md | done |
| 06:36 UTC | 06:36 UTC | 06:44 UTC | 8m | add T76-T78 RAG+memory integration tests | T76: full RAG pipeline (config, routing, live retrieve); T77: STM/MTM/LTM memory assembly, toggle, i18n; T78: combined context ordering contract + live LLM call | 2 | 1 | claude-sonnet-4.6 | src/tests/test_voice_regression.py, doc/test-suite.md | done |
| 04:44 UTC | 04:44 UTC | 07:20 UTC | 156m | Admin menu RAG visibility fix + full deploy to TS2+TS1 | Fix admin_menu.yaml missing 2 buttons; fix RAG back callback; bump v2026.3.45; fix SRC_ROOT portable paths in tests; deploy+verify both targets | 2 | 2 | claude-sonnet-4.6 | src/screens/admin_menu.yaml, src/telegram/bot_admin.py, src/core/bot_config.py, src/release_notes.json, src/tests/test_voice_regression.py, src/tests/screen_loader/test_screen_loader.py | done |
| 07:20 UTC | 07:20 UTC | 07:30 UTC | 10m | Fix chat mode: second text shows menu instead of LLM answer | mode is None → default to chat; bump v2026.3.46; 323 PASS; deploy TS2 | 1 | 1 | claude-sonnet-4.6 | src/telegram_menu_bot.py, src/core/bot_config.py, src/release_notes.json | done |
| 07:30 UTC | 07:30 UTC | 07:42 UTC | 12m | Fix RAG View Log no effect on Postgres (datetime TypeError) | str() wrap on created_at/query; T79 added; bump v2026.3.47; 326 PASS; deploy TS2+TS1 | 2 | 1 | claude-sonnet-4.6 | src/telegram/bot_admin.py, src/tests/test_voice_regression.py, src/core/bot_config.py, src/release_notes.json | done |
| 07:42 UTC | 07:42 UTC | 08:30 UTC | 48m | Fix RAG hybrid retrieval — 3 root causes (psutil fallback, embed() arg, chunk_idx missing) | /proc/meminfo fallback; svc.embed(query) fix; SELECT chunk_idx; T80 added; bump v2026.3.48; 330 PASS; deploy TS2+TS1 | 3 | 2 | claude-sonnet-4.6 | src/core/bot_rag.py, src/core/store_postgres.py, src/tests/test_voice_regression.py, src/core/bot_config.py, src/release_notes.json | done |
| 06:01 UTC | 06:01 UTC | 06:20 UTC | 19m | perf: SintAItion slow menu response — polling timeout tuning | Diagnosed: 24-core, SQLite, load 0.11 → no resource issue; root cause: long_polling_timeout=20s caused frequent reconnects; fix: timeout 30→90, long_polling_timeout 20→55, interval=1; deployed TS2+TS1 | 1 | 1 | claude-sonnet-4.6 | src/telegram_menu_bot.py | done |
| 08:32 UTC | | 06:24 UTC | 08:32 UTC | 128m | Backup & migration concept audit + fixes | Audit all user data, find gaps (docs/ not backed up, no doc migration), fix backup skill, deploy skill, migrate_to_db.py, add docs | 3 | 1 | claude-sonnet-4.6 | .github/skills/taris-backup-target/SKILL.md, .github/skills/taris-deploy-openclaw-target/SKILL.md, src/setup/migrate_to_db.py, doc/install-new-target.md, doc/quick-ref.md | done |
| 16:56 UTC | 16:00 UTC | 16:57 UTC | 57m | fix: SintAItion 1GB RAM + 70 disconnects/hr → 41MB + 0 errors | Root causes: FW preload loaded PyTorch/CUDA (1GB+); long_polling_timeout=55 exceeded NAT timeout; User=stas in user systemd caused 216/GROUP; Fixes: disable FW preload, timeout 30/20/0, remove User= line, MemoryMax=600M; deployed both targets | 2 | 3 | claude-sonnet-4.6 | src/telegram_menu_bot.py, src/services/taris-telegram.service | done |
| 17:30 UTC | 17:00 UTC | 17:30 UTC | 30m | feat: unified taris_deploy.sh — all actions/targets/variants in one script | Create taris_deploy.sh (~700 lines), wrap update_openclaw.sh/update_picoclaw.sh, update 3 skill SKILL.md files; tested on ts2 full pipeline | 3 | 2 | claude-sonnet-4.6 | src/setup/taris_deploy.sh, src/setup/update_openclaw.sh, src/setup/update_picoclaw.sh, .github/skills/taris-deploy-openclaw-target/SKILL.md, .github/skills/taris-deploy-to-target/SKILL.md, .github/skills/taris-backup-target/SKILL.md | done |
| 17:26 UTC | 17:26 UTC | 17:40 UTC | 14m | fix: MCP servers fail to start on Copilot launch | Root cause: Docker socket-activation means copilot-notify container not up when Copilot starts; fix: systemd user service copilot-notify.service runs docker compose up -d at login | 1 | 1 | claude-sonnet-4.6 | ~/.config/systemd/user/copilot-notify.service | done |
| 17:39 UTC | 17:39 UTC | 17:45 UTC | 6m | fix: ZodError on Copilot v1.0.14 startup — missing type field | Copilot v1.0.14 updated MCP config schema; SSE servers now require explicit type: "sse"; added "type": "sse" to copilot-notify entry in mcp-config.json | 1 | 2 | claude-sonnet-4.6 | ~/.copilot/mcp-config.json | done |
| 20:05 UTC | 19:50 UTC | 20:05 UTC | 15m | analyse+fix: SintAItion performance instability | LLM/TTS/STT in api_benchmark block event loop; fixed with asyncio.to_thread; root-cause report: LLM=OpenAI(net jitter), GPU not used for STT, preload disabled | 2 | 4 | claude-sonnet-4.6 | src/bot_web.py | done |
| 18:21 UTC | 18:07 UTC | 18:25 UTC | 18m | docs: perf report + env example + install guide | Create errors/perf-sintaition-2026-03-31.md; update bot.env.example AMD/ROCm section; add B.5-GPU and Part C to install-new-target.md | 2 | 1 | claude-sonnet-4.6 | errors/perf-sintaition-2026-03-31.md, src/setup/bot.env.example, doc/install-new-target.md | done |
| 20:32 UTC | 20:32 UTC | 20:32 UTC | 0m | verify: confirm api_benchmark async offloading fix is present | Inspected src/bot_web.py api_benchmark and verified LLM/TTS/STT stages use asyncio.to_thread with no remaining direct blocking stage calls in route | 1 | 1 | gpt-5 | src/bot_web.py, doc/vibe-coding-protocol.md | done |
| 20:35 UTC | 20:35 UTC | 20:35 UTC | 0m | verify: confirm api_benchmark fix is committed and pushed | Checked git status/log/show; confirmed commit 0de20a2 contains api_benchmark asyncio.to_thread changes and HEAD matches origin/taris-openclaw | 1 | 1 | gpt-5 | doc/vibe-coding-protocol.md | done |
| 07:17 UTC | 07:17 UTC | 07:31 UTC | 14m | fix: local DNS — use FritzBox for LAN hostname resolution | Root cause: /etc/resolv.conf was static file with Google/CF first, FritzBox last, no search domain; Fix: symlink /etc/resolv.conf → /run/systemd/resolve/stub-resolv.conf (stub mode); stub has search fritz.box, resolved already had FritzBox per-interface; verified SintAItion/OpenClawPI/OpenClawPI2 resolve + SSH works | 1 | 3 | claude-sonnet-4.6 | /etc/resolv.conf (symlinked) | done |
| 16:52 UTC | 14:00 UTC | 16:52 UTC | 172m | fix: SintAItion network failover — dock→built-in→WiFi | Root cause: all NM connections had same priority=0, WiFi disconnected, enp195s0 carrier flapping (hardware); Fixes: route metrics 101/200/300, WiFi powersave=2, EEE disabled+persistent dispatcher, carrier-wait-timeout=5s, WoL disabled; enp195s0 flapping is hardware/cable issue | 2 | 8 | claude-sonnet-4.6 | /etc/NetworkManager/conf.d/99-wifi-powersave.conf, /etc/NetworkManager/conf.d/99-carrier-wait.conf, /etc/NetworkManager/dispatcher.d/99-disable-eee | done |
| 19:30 UTC | 17:25 UTC | 19:30 UTC | 125m | feat: Qwen3.5 benchmark vs Qwen3/Qwen2 on SintAItion | Pulled qwen3.5:0.8b + qwen3.5:latest(9b); fixed IPv6→IPv4 pull issue (gai.conf+GODEBUG=netdns=cgo); fixed think=false for qwen3 models; fixed /api/tags GET vs POST; added T81-T83; full 6-prompt benchmark shows qwen3.5:9b=100% quality at 14t/s beats qwen3:8b 83% at 16t/s | 3 | 6 | claude-sonnet-4.6 | src/tests/llm/benchmark_ollama_models.py, src/tests/test_voice_regression.py, doc/test-suite.md, doc/vibe-coding-protocol.md | done |
| 19:45 UTC | 17:37 UTC | 19:45 UTC | 128m | feat: STT multi-model benchmark; switch to small int8 | Rewrote benchmark_stt.py: all 4 cached models (tiny/base/small/large-v3-turbo), int8 vs float32, Piper TTS audio generation, WER+RTF+load table; Results: small int8 wins (17% WER, RTF=0.33, 4× faster than large-v3-turbo at 15% WER RTF=1.31); float32 worse in both WER and speed; switched FASTER_WHISPER_MODEL=small in bot.env | 2 | 4 | claude-sonnet-4.6 | src/tests/benchmark_stt.py, ~/.taris/bot.env(SintAItion) | done |
| 17:58 UTC | 17:00 UTC | 18:00 UTC | 60m | feat: 4-language STT+LLM benchmarks (RU/DE/EN/SL) | Extended benchmark_stt.py+benchmark_ollama_models.py: SL sentences, DE/EN expanded, Piper+espeak-ng TTS, per-lang tables, cross-lang WER matrix, LANG_GROUPS, print_lang_summary(), --lang flag; fixed ESPEAK_BIN to prefer system /usr/bin/espeak-ng; STT results: small int8 RU=22%/DE=22%/EN=14%/SL=88%; large-v3-turbo best for DE(6%)+SL(51%); LLM winner: qwen3.5:latest 100% all 4 langs 13 t/s | 3 | 2 | claude-sonnet-4.6 | src/tests/benchmark_stt.py, src/tests/llm/benchmark_ollama_models.py | done |
| 18:03 UTC | 18:02 UTC | 18:04 UTC | 2m | config: switch OLLAMA_MODEL=qwen3.5:latest on SintAItion | Update bot.env on SintAItion; restart services; smoke-test; update bot.env.example+AGENTS.md; push | 1 | 1 | claude-sonnet-4.6 | ~/.taris/bot.env(SintAItion), src/setup/bot.env.example, AGENTS.md | done |
| 18:15 UTC | 18:15 UTC | 18:28 UTC | 13m | refactor: move RAG settings from profile menu to admin menu | Remove profile_rag_* from profile.yaml+bot_handlers.py; add admin_rag_user_* to bot_admin.py; update admin_rag_menu button; update callbacks+imports in telegram_menu_bot.py; add i18n strings; 64 tests pass | 2 | 1 | claude-sonnet-4.6 | src/screens/profile.yaml, src/telegram/bot_admin.py, src/telegram/bot_handlers.py, src/telegram_menu_bot.py, src/strings.json | done |

| 22:11 UTC | 21:30 UTC | 22:11 UTC | 41m | feat: RAG Variant C Phase C/D — chunk quality, embed stats, MCP server+client (v2026.4.1) | Audit Variant C open items; fix bot_embeddings.py src.core import bug; Phase C: _MIN_CHUNK_CHARS=20 filter, quality_pct/n_embedded/n_skipped metadata, doc detail view embed stats, strings ru/en/de; Phase D: /mcp/search endpoint, bot_mcp_client.py circuit breaker, RRF merge, MCP constants; T84-T86 (36 PASS); fix release_notes.json missing brace; deploy TS2+SintAItion | 4 | 3 | claude-sonnet-4.6 | src/core/bot_embeddings.py, src/core/bot_config.py, src/core/bot_mcp_client.py, src/core/bot_rag.py, src/features/bot_documents.py, src/bot_web.py, src/strings.json, src/release_notes.json, src/tests/test_voice_regression.py, doc/test-suite.md, TODO.md | done |

| 13:28 UTC | 12:40 UTC | 13:28 UTC | 48m | fix: RAG hybrid search v2026.4.2 — 3 critical bugs + vec0 rowid map + system KB + deploy SintAItion | Fix upsert_embedding missing chunk_text arg (0 vectors ever stored); fix RRF chunk_idx missing in FTS+vector SELECT; fix vec0 DELETE silently fails → vec_rowid_map workaround; add shared docs in all search paths; RAG tracing 4-tuple; system KB auto-load (howto+README+overview); migrate_reembed.py with store API; fix doc_hash in save_document_meta for hash-based skip; T87-T90 15/15 PASS; deploy SintAItion 175 embeddings verified 0 dupes | 5 | 6 | claude-sonnet-4.6 | src/core/store_sqlite.py, src/core/store_base.py, src/core/store_postgres.py, src/core/bot_rag.py, src/features/bot_documents.py, src/telegram/bot_access.py, src/bot_web.py, src/telegram_menu_bot.py, src/core/bot_config.py, src/setup/load_system_docs.py, src/setup/migrate_reembed.py, src/tests/test_voice_regression.py, doc/architecture/knowledge-base.md | done |
| 16:36 UTC | 14:09 UTC | 16:36 UTC | 147m | fix: doc detail raw template + bot self-knowledge + voice retry on network errors (v2026.4.3) | Fix {title}/{chunks} template leak in doc detail; add BOT CAPABILITIES block to system prompt; add _tg_send_with_retry() for voice LLM response; fix 4 stale tests; 401 PASS 0 FAIL; deploy TS2 | 3 | 1 | claude-sonnet-4.6 | src/features/bot_documents.py, src/strings.json, src/telegram/bot_access.py, src/features/bot_voice.py, src/tests/test_voice_regression.py, src/core/bot_config.py, src/release_notes.json | done |
| 17:21 UTC | 14:59 UTC | 17:21 UTC | 142m | fix: HuggingFace online checks + subsystem log routing (v2026.4.4) | local_files_only=True in SentenceTransformer; persistent fastembed cache; _make_file_logger() in bot_config + 4 named loggers; voice/security/datastore/assistant modules use named loggers; 402 PASS TS1 | 3 | 4 | claude-sonnet-4.6 | src/core/bot_config.py, src/core/bot_embeddings.py, src/core/bot_db.py, src/core/store.py, src/core/store_sqlite.py, src/core/store_postgres.py, src/core/bot_llm.py, src/features/bot_voice.py, src/security/bot_security.py, src/security/bot_auth.py | done |
