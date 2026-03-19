# Copilot Optimization Proposal — picoclaw

**Date:** 2026-03-16 (updated 2026-03-19)  
**Author:** GitHub Copilot (analysis) / stas-ka (owner)  
**Status:** Partially implemented — see §9 for implementation tracker  
**Related:** [Vibe Coding Guidelines](../doc/vibe-coding-guidelines.md) · [TODO.md §20](../TODO.md)

---

## 1. Problem Statement

After the **first or second task** in a GitHub Copilot session (Sonnet or Opus model), the context window fills to capacity and Copilot is forced to compact the conversation. This makes multi-task coding sessions impractical and degrades response quality as earlier context is lost.

---

## 2. Root-Cause Analysis

### 2.1 Token Budget Snapshot

The table below estimates the number of LLM tokens consumed per category in a typical feature-coding request (e.g. "add a calendar reminder"). One token ≈ 4 characters.

| Source | Size | Tokens | Load trigger |
|---|---|---|---|
| `copilot-instructions.md` | 6.4 KB | ~1 600 | **Every request** (auto-loaded by VS Code) |
| `safe-update.instructions.md` | 4.4 KB | ~1 100 | **Every request** (`applyTo: "**"`) |
| `bot-coding.instructions.md` | 5.2 KB | ~1 300 | Every `src/*.py` edit |
| `bot-deploy.instructions.md` | 4.5 KB | ~1 100 | Every `src/*.py` edit |
| `voice-regression.instructions.md` | 3.4 KB | ~860 | `src/bot_voice.py` + 3 other files |
| **Instruction overhead** | **~24 KB** | **~6 000** | **per request (baseline)** |
| `doc/bot-code-map.md` | 39 KB | ~9 800 | "ALWAYS read first" instruction |
| `doc/architecture.md` | 55 KB | ~13 800 | "When adding components" instruction |
| `doc/dev-patterns.md` | 24 KB | ~6 200 | "Before adding any feature" instruction |
| `doc/test-suite.md` | 19 KB | ~4 900 | "Before running tests" instruction |
| **Doc-pull overhead** | **~137 KB** | **~34 700** | per task if all instructions followed |
| `src/bot_web.py` (edit context) | 83 KB | ~20 800 | When editing web UI |
| `src/bot_calendar.py` (edit context) | 49 KB | ~12 300 | When editing calendar |
| `src/bot_voice.py` (edit context) | 46 KB | ~11 500 | When editing voice |
| **Worst-case single file** | 83 KB | ~20 800 | — |

**Worst-case first request:** 6 000 (instructions) + 34 700 (docs) + 20 800 (file) = **~61 500 tokens**.  
A 100K context window is exhausted before the second task even begins, especially as conversation history accumulates.

Even with Claude Sonnet/Opus 200K windows, the combination of instructions + docs + file + conversation history + response reaches the limit in 2–3 turns when editing large modules.

---

### 2.2 Identified Root Causes

#### RC-1: `safe-update.instructions.md` loaded for every file

```yaml
applyTo: "**"
```

This 4.4 KB file is injected into context for **every single file** opened or edited, even for unrelated changes (e.g. editing `README.md`, `strings.json`). The safe-update protocol is only needed when schema or data-format changes occur — approximately 5% of all requests.

#### RC-2: `copilot-instructions.md` duplicates content from other files

The always-on workspace instructions contain content that is **already present in dedicated files**:

| Duplicated content | Original location |
|---|---|
| Voice regression T01–T21 table (~900 tokens) | `voice-regression.instructions.md`, `test-suite.md`, `run-tests.prompt.md` |
| Bot coding patterns summary (~400 tokens) | `bot-coding.instructions.md`, `dev-patterns.md` |
| Remote host table (~200 tokens) | `bot-deploy.instructions.md`, `deploy-to-target/SKILL.md` |
| Post-deploy rule (~150 tokens) | `bot-deploy.instructions.md`, `deploy-to-target/SKILL.md` |

Removing duplicates from `copilot-instructions.md` alone saves ~1 650 tokens from every request.

#### RC-3: "ALWAYS read X" instructions pull 39 KB into context

The instruction `doc/bot-code-map.md — ALWAYS — find any function before searching` causes Copilot to read 39 KB before every task, even when the task does not involve locating functions (e.g. bumping version, editing strings).

Better pattern: instruct Copilot to **search the map file** rather than read it whole. The map is an index — it should be queried, not consumed.

#### RC-4: `doc/architecture.md` is 55 KB — a monolith

The architecture document has grown to 55 KB across 1 202 lines. It covers the voice pipeline, web UI, data layer, deployment, security, LLM providers, hardware, and more. Reading it to answer a question about, say, the calendar module forces all 55 KB into context.

#### RC-5: Large source modules

Several source files are very large:

| File | Size | Recommendation |
|---|---|---|
| `src/bot_web.py` | 83 KB | Split into sub-modules |
| `src/bot_calendar.py` | 49 KB | Extract NL parser and reminder loop |
| `src/bot_voice.py` | 46 KB | Already modular; acceptable |
| `src/telegram_menu_bot.py` | 40 KB | Already used as entry-point; acceptable |

When Copilot opens `bot_web.py` for any web UI change, it puts 83 KB (20 800 tokens) into context. That is 20% of a 100K window for a single file.

#### RC-6: Unrelated content in workspace instructions

`INSTRUCTIONS.md` (1.7 KB) contains an **accounting task for Sintaris d.o.o.** — completely unrelated to bot development. Although it does not use `applyTo`, it lives at the workspace root and is visible to Copilot in chat if the user asks about instructions.

`AGENTS.md` stores bot version state plus accounting task context in the same file. These are semantically unrelated.

#### RC-7: Deploy-step content duplicated across 4 locations

The Pi deployment procedure is fully described in:
1. `bot-deploy.instructions.md`
2. `safe-update.instructions.md`
3. `deploy-bot.prompt.md`
4. `deploy-to-target/SKILL.md`

Each copy drifts slightly. When Copilot reads multiple of these (e.g. both instruction files for `src/*.py`), it loads the same 100+ lines of `pscp`/`plink` commands repeatedly.

---

## 3. Optimization Proposals

The proposals are ordered by **impact / effort** ratio. Each proposal is independent — implement any subset.

---

### P-1 · Fix `safe-update.instructions.md` scope (CRITICAL, 1 min)

**Impact:** −1 100 tokens per request  
**Risk:** None

Change the `applyTo` frontmatter from the wildcard to the specific files that actually trigger a safe update:

```yaml
# BEFORE (current — loaded for every file)
applyTo: "**"

# AFTER (proposed — only loaded when relevant)
applyTo: "src/bot_db.py,tools/migrate_to_db.py,src/bot_state.py,src/bot_config.py"
```

**Rationale:** The safe-update protocol is about schema migrations and data-format changes. The only files that trigger it are `bot_db.py`, `migrate_to_db.py`, `bot_state.py`, and `bot_config.py`. Loading it for `README.md`, `strings.json`, or test files is wasteful.

---

### P-2 · Slim `copilot-instructions.md` — remove duplicated content (HIGH, 30 min)

**Impact:** −1 650 tokens per request  
**Risk:** None (content exists in authoritative locations)

Remove these sections from `.github/copilot-instructions.md` and replace with one-line pointers:

| Section to remove | Replacement pointer |
|---|---|
| Full T01–T21 regression table | `Run /run-tests or see doc/test-suite.md §2` |
| "Quick rules from the patterns doc" block | `See .github/instructions/bot-coding.instructions.md` |
| Full remote host table (duplicated from AGENTS.md) | Remove; already in AGENTS.md and bot-deploy instructions |
| "Skills — Use These" table (duplicated from SKILLS_AGENTS.md) | Remove; SKILLS_AGENTS.md is the canonical reference |

**Proposed new structure for `copilot-instructions.md`** (~2 KB, ~500 tokens):

```markdown
# Copilot Instructions — picoclaw workspace

## Project
picoclaw is a Raspberry Pi–based Telegram bot + offline voice assistant (ru/de/en).
Source: `src/`. Targets: OpenClawPI2 (test) → OpenClawPI (production).

## Reference Documents (read on demand — do NOT pre-load all)
| Document | When to use |
|---|---|
| `doc/bot-code-map.md` | Finding a specific function — **search it, don't read it whole** |
| `doc/architecture.md` | When adding new services or pipeline stages |
| `doc/dev-patterns.md` | When adding a new feature type (voice opt, callback, flow) |
| `doc/test-suite.md` | Before running tests — has the trigger table |
| `TODO.md` | Session start — check what is planned |

## Skills (invoke with /skill-name or #file)
deploy-to-target · run-tests · bump-version · test-software · deploy-bot

## Mandatory Rules (summary — full rules in instructions/)
- Secrets: never hard-code; use `.credentials/.pico_env` and `.env`
- Version: `BOT_VERSION = "YYYY.M.D"` + prepend to `release_notes.json`
- Strings: add to ru + en + de in `src/strings.json`
- Deploy: PI2 first → PI1 only after PI2 passes. See /deploy-to-target
- Vibe log: append row to `doc/vibe-coding-protocol.md` after each request
```

---

### P-3 · Replace "ALWAYS read bot-code-map.md" with "search it" (HIGH, 10 min)

**Impact:** −9 800 tokens per request (when Copilot obeys the "always" instruction)  
**Risk:** None

**Current instruction:**
> `doc/bot-code-map.md — ALWAYS — find any function by name/line before searching the file`

**Proposed replacement:**
> `doc/bot-code-map.md — Search this file for function names / line numbers rather than reading it whole. Example: search for "handle_calendar" or "bot_voice.py" to find the right section.`

The code map is an *index*. Copilot's code search and grep capabilities make reading it completely unnecessary. The only value is when a human wants to browse it. For the AI, a targeted read of the relevant section (< 2 KB) is sufficient.

---

### P-4 · Split `doc/architecture.md` into domain files (MEDIUM, 2–4 h)

**Impact:** Reduces context load from 13 800 tokens to 1 500–3 000 tokens per query  
**Risk:** Low — restructuring only, no source code changes

Split the 55 KB monolith into focused topic files in `doc/arch/`:

```
doc/arch/
  overview.md        (~3 KB)  — system diagram + 3-channel summary
  voice-pipeline.md  (~8 KB)  — audio capture, Vosk, VAD, Piper, TTS chain
  web-ui.md          (~6 KB)  — FastAPI, JWT, templates, HTMX, PWA
  data-layer.md      (~5 KB)  — SQLite, bot_db.py, migration plan
  security.md        (~4 KB)  — prompt injection, RBAC, security preamble
  deployment.md      (~4 KB)  — services, systemd, PI1/PI2 pipeline
  llm-providers.md   (~3 KB)  — OpenRouter, bot_llm.py, model selection
  hardware.md        (~5 KB)  — Pi 3 specs, audio, benchmarks
```

Update `copilot-instructions.md` to point to the relevant sub-file instead of `architecture.md`.

---

### P-5 · Split `src/bot_web.py` (83 KB → 3×30 KB) (HIGH IMPACT, 4–8 h)

**Impact:** −13 000 tokens when editing web files (83 KB → ~30 KB per module)  
**Risk:** Medium — refactoring requires testing

The 83 KB `bot_web.py` is the largest source file. It contains three conceptually distinct layers:

| Proposed module | Responsibility | Estimated size |
|---|---|---|
| `bot_web_app.py` | FastAPI app factory, auth middleware, static files, login/register routes | ~25 KB |
| `bot_web_api.py` | API endpoints: chat, notes, calendar, mail, voice, admin | ~40 KB |
| `bot_web_render.py` | HTML fragment rendering helpers, Jinja2 context builders | ~18 KB |

When editing a calendar route, Copilot only needs `bot_web_api.py` (40 KB, ~10 000 tokens) — not the full 83 KB.

**Note:** This is the highest-effort change and should be done as a dedicated task with full test coverage.

---

### P-6 · Eliminate deploy-step duplication — make skills the single source of truth (MEDIUM, 1–2 h)

**Impact:** Prevents context pollution, eliminates drift  
**Risk:** Low

The deployment steps exist in 4 locations. Proposed canonical structure:

| File | Purpose | Action |
|---|---|---|
| `.github/skills/deploy-to-target/SKILL.md` | **Canonical** — full procedure | Keep as-is |
| `.github/instructions/bot-deploy.instructions.md` | Inline auto-load for `src/*.py` | **Shorten** to 20-line summary + `See /deploy-to-target for full steps` |
| `.github/instructions/safe-update.instructions.md` | Schema-change protocol | **Shorten** to checklist + pointer to SKILL.md |
| `.github/prompts/deploy-bot.prompt.md` | Quick deploy prompt | Keep (it is minimal already) |

Shortening the two instruction files saves ~1 500 tokens from every `src/*.py` context.

---

### P-7 · Separate accounting task from bot-dev memory (LOW, 10 min)

**Impact:** Prevents context confusion  
**Risk:** None

Move the Sintaris accounting task from `INSTRUCTIONS.md` to `concept/accounting_2025.md` (or another non-root location). It is unrelated to the bot and should not appear in Copilot's workspace instruction index.

Similarly, if `AGENTS.md` is used as a session-state file by Copilot agents, split it into:
- `AGENTS.md` — bot state only (version, feature state)
- `.github/agents/accounting-agent.md` — accounting task (if agents need it)

---

### P-8 · Add a `doc/quick-ref.md` — the single "always read" doc (MEDIUM, 1 h)

**Impact:** Replaces multi-file "read first" with a single 3 KB doc  
**Risk:** None

Create `doc/quick-ref.md` (~3 KB, ~750 tokens) as the **only** document that copilot-instructions.md tells Copilot to always check:

```markdown
# picoclaw Quick Reference

## Module Map (one-liner per file)
bot_config → bot_state → bot_instance → ... → telegram_menu_bot
(full chain: doc/bot-code-map.md §"Module Dependency Chain")

## Key Functions by Task
| Task | Module | Function |
|---|---|---|
| Add calendar event | bot_calendar.py | `_finish_cal_add()` (~line 280) |
| Voice opt toggle | bot_voice.py | `_handle_voice_opt_toggle()` (~line 430) |
| New callback | telegram_menu_bot.py | `handle_callback()` (~line 190) |
| i18n string | src/strings.json | Add to ru + en + de |
| Access guard | bot_access.py | `_is_allowed()` / `_is_admin()` |

## Version Bump (2 files)
1. `src/bot_config.py` → `BOT_VERSION = "YYYY.M.D"`
2. `src/release_notes.json` → prepend entry at top

## Test Trigger Table
| Changed | Test |
|---|---|
| bot_voice.py / bot_config.py | Voice T01–T21 |
| strings.json | T13, T17 |
| bot_calendar.py | T20, T21 |
| bot_web.py / templates | Web UI Playwright |

## Deploy Pipeline
PI2 first → PI1 only after PI2 confirmed + git push. Use /deploy-to-target.
```

This replaces the combined 137 KB "read these docs first" burden with a single 3 KB reference.

---

### P-9 · Use `#file:` section anchors in prompts instead of whole-file reads (LOW, ongoing)

**Impact:** Reduces per-task context by 50–80% for doc reads  
**Risk:** None

Instead of loading full files, VS Code Copilot can be directed to specific sections using `#file:doc/architecture.md` in the chat. Teach this pattern via the skills guide and an example in `copilot-instructions.md`:

```markdown
# Good — read only the voice section
#file:doc/arch/voice-pipeline.md

# Bad — loads 55 KB
#file:doc/architecture.md
```

Also applicable to large source files:
```markdown
# Good — read only the calendar CRUD section
#file:src/bot_calendar.py#CRUD
```

Update the skills guide (`doc/copilot-skills-guide.md`) with this pattern.

---

## 4. Recommended Implementation Order

| Priority | Proposal | Effort | Token saving per request |
|---|---|---|---|
| **P-1** | Fix `safe-update` `applyTo` scope | 1 min | ~1 100 |
| **P-2** | Slim `copilot-instructions.md` | 30 min | ~1 650 |
| **P-3** | Replace "ALWAYS read bot-code-map" | 10 min | ~9 800 (when triggered) |
| **P-8** | Add `doc/quick-ref.md` | 1 h | replaces up to ~34 700 |
| **P-6** | Shorten instruction file deploy sections | 1–2 h | ~1 500 |
| **P-7** | Separate accounting task | 10 min | clarity |
| **P-4** | Split `architecture.md` | 2–4 h | ~10 000 when triggered |
| **P-5** | Split `bot_web.py` | 4–8 h | ~13 000 when editing web |
| **P-9** | `#file:` anchor pattern in prompts | ongoing | ~50–80% for doc reads |

**Recommended quick-win session (< 2 h):** P-1, P-2, P-3, P-8, P-7.  
These alone reduce baseline context from **~6 000 tokens to ~2 500 tokens** per request, and eliminate the 34 700-token "always read all docs" trap.

---

## 5. Before / After Context Budget Comparison

### Before (current state) — editing `bot_calendar.py` for a new feature

| Item | Tokens |
|---|---|
| `copilot-instructions.md` (always loaded) | 1 600 |
| `safe-update.instructions.md` (`applyTo: "**"`) | 1 100 |
| `bot-coding.instructions.md` (loaded for `src/*.py`) | 1 300 |
| `bot-deploy.instructions.md` (loaded for `src/*.py`) | 1 100 |
| `doc/bot-code-map.md` (Copilot follows "ALWAYS" rule) | 9 800 |
| `doc/dev-patterns.md` (Copilot follows "Before adding any feature") | 6 200 |
| `src/bot_calendar.py` (edit context) | 12 300 |
| **Request 1 total** | **~33 400** |
| Copilot response + conversation history | ~3 000 |
| **Request 2 starts at** | **~36 400** |
| Adding another file for context + further doc reads | +10 000–20 000 |
| **Context exhausted after ~3–4 turns** | — |

### After (with P-1, P-2, P-3, P-8) — same task

| Item | Tokens |
|---|---|
| `copilot-instructions.md` (slim version) | 500 |
| `bot-coding.instructions.md` (short summary) | 600 |
| `bot-deploy.instructions.md` (short summary) | 600 |
| `doc/quick-ref.md` (on demand, ~3 KB) | 750 |
| `src/bot_calendar.py` (edit context) | 12 300 |
| **Request 1 total** | **~14 750** |
| Copilot response + conversation history | ~3 000 |
| **Request 2 starts at** | **~17 750** |
| **Context sustained for 8–10 turns** before compaction | — |

---

## 6. Structural Change Summary (file-level)

```
CHANGES NEEDED (no source code modified):

.github/copilot-instructions.md              → SLIM (remove T01-T21, patterns, remote host)
.github/instructions/safe-update.instructions.md  → FIX applyTo: "**" → narrow glob
.github/instructions/bot-deploy.instructions.md   → SHORTEN (remove full deploy steps)
.github/instructions/bot-coding.instructions.md   → SHORTEN (keep essential, pointer to dev-patterns)

NEW files:
concept/copilot_optimization.md             → THIS FILE (proposal only)
doc/quick-ref.md                             → New 3 KB always-read reference
doc/arch/overview.md                         → Split from architecture.md
doc/arch/voice-pipeline.md                   → Split from architecture.md
doc/arch/web-ui.md                           → Split from architecture.md
...

SPLIT:
doc/architecture.md → doc/arch/*.md (keep architecture.md as index + pointers)

OPTIONAL SPLIT (separate task):
src/bot_web.py → src/bot_web_app.py + src/bot_web_api.py + src/bot_web_render.py

MOVE:
INSTRUCTIONS.md accounting section → concept/accounting_2025.md
```

---

## 7. Additional Patterns for Daily Use

Beyond structural changes, these **habits** significantly reduce context pressure during a session:

### 7.1 Start each session with a focused `#file:` directive
```
#file:doc/quick-ref.md  I want to add a reminder button to the calendar menu
```
Instead of letting Copilot auto-load all instruction files.

### 7.2 Reference specific sections, not whole files
```
#file:src/bot_calendar.py:260-310  fix the date parsing in _finish_cal_add
```

### 7.3 Break long sessions into multiple short sessions
Each VS Code Copilot Chat session has independent context. For complex tasks:
- Session 1: design + implement
- Session 2: test + refine
- Session 3: deploy + document

Use `AGENTS.md` to pass state between sessions (keep it short — under 2 KB).

### 7.4 Avoid attaching large files via `@workspace` unless necessary
`@workspace` scans all files and can inject tens of thousands of tokens. Prefer `#file:specific-file.py` when you know which file to edit.

### 7.5 Use `/deploy-to-target` for all deployments
The skill contains the complete procedure. Using the skill means the system prompt for that turn is the skill (small) rather than all the instruction files.

---

## 8. Metrics to Track Progress

After implementing the proposals, measure:

| Metric | Before | Target after P-1..P-8 |
|---|---|---|
| Baseline tokens per request (instructions only) | ~6 000 | ~1 700 |
| Typical first-request tokens (with 1 source file) | ~33 400 | ~15 000 |
| Turns before context compaction needed | 2–3 | 8–10 |
| Duplicate content instances (deploy steps) | 4 locations | 1 location |
| Size of largest always-loaded doc (`copilot-instructions.md`) | 6.4 KB | ~2 KB |

---

*This document contains proposals only. No changes have been made to the project.*

---

## 9. Implementation Tracker (updated 2026-03-19)

| Proposal | Description | Status |
|---|---|---|
| P-1 | Fix `safe-update` `applyTo: "**"` → narrow glob | 🔲 Pending |
| P-2 | Slim `copilot-instructions.md` — remove T01–T21 table, patterns, remote host | ✅ Done |
| P-3 | Replace "ALWAYS read bot-code-map.md" with "search it" | ✅ Done |
| P-4 | Split `doc/architecture.md` into `doc/arch/*.md` (8 topic files) | ✅ Done |
| P-5 | Split `src/bot_web.py` (83 KB → 3 modules) | 🔲 Pending |
| P-6 | Shorten `bot-deploy.instructions.md` + `safe-update.instructions.md` | 🔲 Pending |
| P-7 | Move accounting task from `INSTRUCTIONS.md` to `concept/` | 🔲 Pending |
| P-8 | Add `doc/quick-ref.md` — single 3 KB always-read index | ✅ Done |
| P-9 | Add `#file:` anchor pattern to skills guide | 🔲 Pending |
| G-1 | Create `doc/vibe-coding-guidelines.md` — artifact structuring rules | ✅ Done (2026-03-19) |

**Baseline tokens (current estimate after P-2, P-3, P-4, P-8):**  
Instructions ~1 200 tok + 1 source file ~12 000 tok = ~13 200 tok first request.  
Sessions sustain ~6–8 turns before compaction (up from 2–3 turns before optimizations).

**Remaining quick wins:** P-1, P-6, P-7 (combined effort < 1 h).  
**Major remaining work:** P-5 (split `bot_web.py`) — high impact, 4–8 h, dedicated task required.
