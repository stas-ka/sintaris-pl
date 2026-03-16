# Vibe Coding Protocol — picoclaw / Pico Bot

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
| 10:00 | implement copilot_optimizations.md — P1–P4, P6–P8: slim instructions, split architecture.md into 8 topic files, create doc/quick-ref.md | 4 | 12 | claude-sonnet-4-5 | .github/copilot-instructions.md, safe-update.instructions.md, bot-deploy.instructions.md, INSTRUCTIONS.md, doc/quick-ref.md, doc/architecture.md, doc/arch/overview.md, doc/arch/voice-pipeline.md, doc/arch/telegram-bot.md, doc/arch/security.md, doc/arch/features.md, doc/arch/deployment.md, doc/arch/multilanguage.md, doc/arch/web-ui.md, concept/accounting_2025.md | done |
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
| **Total** | | **48** | **~156** | | |

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
| — | Fix HTTPS 'Not Secure' warning on both Pi targets: create setup_ssl.sh with SAN (hostname+all IPs+Tailscale), deploy+run on both Pis, restart picoclaw-web on Pi2, download certs for Windows trust store | 3 | ~6 | claude-sonnet-4.6 | src/setup/setup_ssl.sh | done |
| — | Write doc/install-new-target.md: 13-step complete fresh-install guide (system pkgs, Python pkgs, picoclaw binary, Piper TTS, source deploy, voice models, bot.env, picoclaw config, SSL, systemd services, verify checklist) | 3 | ~2 | claude-sonnet-4.6 | doc/install-new-target.md | done |
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
| — | VPS internet exposure: design reverse SSH autossh tunnel architecture (no Fritz.Box changes, dynamic IP irrelevant); create nginx-vps.conf with sub_filter path rewriting, install_vps.sh, picoclaw-tunnel.service, setup_tunnel_key.sh | 4 | ~6 | claude-sonnet-4.6 | src/setup/nginx-vps.conf, src/setup/install_vps.sh, src/setup/setup_tunnel_key.sh, src/services/picoclaw-tunnel.service | done |
| 11:00 UTC | User settings page: language selector (EN/RU/DE) + change password form; add `change_password()` to bot_auth.py; add GET /settings + POST /settings/language + POST /settings/password routes; create settings.html; add ⚙️ Settings link in sidebar nav; deploy to both Pis | 3 | ~3 | claude-sonnet-4.6 | src/bot_auth.py, src/bot_web.py, src/templates/settings.html, src/templates/base.html | done |

**Session 21 total: 6 items, ~21 requests**

---

## Session 22 — 2026-03-14 (UTC+1)

**Focus:** Telegram↔Web account linking feature + documentation sync + PI2 deployment

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| 21:00 UTC | Implement Telegram↔Web account linking: 6-char alphanumeric code with 15 min TTL, "🔗 Link to Web" button in Profile, /register optional link_code field, status=active + role inheritance on link, strings.json in ru/en/de | 4 | ~8 | claude-sonnet-4.6 | src/bot_state.py, src/bot_handlers.py, src/telegram_menu_bot.py, src/bot_web.py, src/templates/register.html, src/strings.json | done |
| 21:10 UTC | Documentation: update roadmap Flow C with actual implementation details (vs old 6-digit/5-min/`/link` plan); mark Flow D as 🔲 Planned; update TODO.md Completed line; update roadmap "Updated:" header | 2 | ~3 | claude-sonnet-4.6 | doc/web-ui/roadmap-web-ui.md, TODO.md | done |
| 21:15 UTC | Deploy to OpenClawPI2: upload 6 files (5 src + register.html template), restart picoclaw-telegram + picoclaw-web, verify both services active (v2026.3.28, Polling Telegram, TLS :8080) | 2 | ~2 | claude-sonnet-4.6 | — (remote deploy) | done |

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
| 05:35 UTC | Update `README.md`: 5 stale sections fixed — (1) directory structure expanded to all 20 modules + web UI files; (2) Step 5 deploy commands updated from 3 files to full 20-module + web templates deploy; (3) Step 9 description changed from "3-mode interface" to full-featured 20-module description; (4) Step 12 verification added picoclaw-web service; (5) Service Management added picoclaw-web block | 3 | ~3 | claude-sonnet-4.6 | README.md | done |

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
| ~UTC | Commit and push all changes: update .gitignore (IDE/certs/backups/test-results), stage 69 files (new: bot_ui.py, bot_actions.py, render_telegram.py, manifest.json, picoclaw-tunnel.service, VPS setup scripts, settings.html, benchmark tools; modified: bot_auth.py + change_password(), bot_web.py + settings routes + admin reset, bot_state.py + account linking, templates; deleted: obsolete files/mockups), rebase on Copilot PR #4 (list-open-issues), resolve vibe-coding-protocol.md conflict, push 69b3a2a to origin/master | 2 | 4 | claude-sonnet-4.6 | .gitignore, doc/vibe-coding-protocol.md | done |

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

## Notes on Measurement

- "Requests" = user→assistant conversation turns, not API calls.
- Time estimates for sessions 1–4 reconstructed from git commit timestamps.
- Session 5 onward: tracked from message metadata (UTC timestamps recorded above).
- Update this file at the end of each session with actual turn counts.
