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
| **Total** | | **47** | **~141** | | |

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

## Session 19 — 2026-03-15 (UTC)

**Focus:** Test suite overview document for Copilot

| Time (UTC) | Request | Complexity | Requests | Model | Files changed | Status |
|---|---|---|---|---|---|---|
| 22:46 UTC | Create test suite description for Copilot: doc/test-suite.md covering all test categories (voice regression T01–T21, Web UI Playwright, hardware audio, mic capture, smoke/deployment), trigger rules, run commands, engineering vs production targets, regression vs fix tests, and chat-mode "test software" protocol | 3 | 1 | claude-sonnet-4-5 | doc/test-suite.md, .github/copilot-instructions.md, AGENTS.md | done |

**Session 19 total: 1 item, 1 request**

---

- "Requests" = user→assistant conversation turns, not API calls.
- Time estimates for sessions 1–4 reconstructed from git commit timestamps.
- Session 5 onward: tracked from message metadata (UTC timestamps recorded above).
- Update this file at the end of each session with actual turn counts.
