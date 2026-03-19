# Vibe Coding Guidelines — picoclaw / Taris

**Audience:** Any developer using GitHub Copilot (VS Code Chat or CLI agent) on this project.  
**Goal:** Keep each Copilot session productive across 8–10 turns without hitting context-window limits.

---

## 1. Why Context Window Matters

Claude Sonnet 4.6 and Opus 4.6 have 200 K-token windows, but the effective **usable** budget per multi-turn session is far smaller:

| What consumes tokens | Approx. cost |
|---|---|
| Auto-loaded workspace instructions (`.github/copilot-instructions.md`) | ~500 tok |
| Scoped instruction files (`applyTo: src/*.py`) | ~600–1 100 tok each |
| One source file opened for editing (`bot_web.py`) | ~20 800 tok |
| One doc file read in full (`bot-code-map.md`) | ~9 800 tok |
| Conversation history (grows with each turn) | ~3 000 tok/turn |

A typical first request already uses 30 000–50 000 tokens before the AI has written a single line of code. After 2–3 turns the window compacts and context is degraded.

The guidelines below explain how to **structure project artifacts** and **use Copilot** to avoid this.

---

## 2. Artifact Structure Rules

### 2.1 Instruction Files — Stay Scoped, Stay Short

> **Rule:** Every instruction file must have a precise `applyTo:` glob that matches only the files where the instructions are relevant.

Bad:
```yaml
---
applyTo: "**"
---
# Safe Update Protocol
```
This loads a 4 KB schema-migration guide for every file, including `README.md` and `strings.json`.

Good:
```yaml
---
applyTo: "src/core/bot_db.py,tools/migrate_to_db.py,src/core/bot_state.py"
---
# Safe Update Protocol
```

**Size target:** Each instruction file < 2 KB (500 tokens). Compress by using bullet points and pointers to authoritative docs instead of repeating content.

### 2.2 The Always-Loaded File Must Be Tiny

> **Rule:** `.github/copilot-instructions.md` must stay under 2 KB (500 tokens).

This file is loaded with **every** request. Every extra line here costs tokens on every turn. It should contain:
- A one-paragraph project summary
- A table of reference docs with "when to use" column
- A 5-line mandatory rules summary
- Pointers to skills (not the skills themselves)

Everything else belongs in a scoped instruction file, prompt file, or domain doc.

### 2.3 Reference Docs — Index First, Details Later

> **Rule:** Large reference docs must have an index so Copilot can search and read only the relevant section.

| Anti-pattern | Better pattern |
|---|---|
| `doc/architecture.md` 55 KB monolith — read it all | `doc/arch/<topic>.md` 3–8 KB each — read only the matching topic |
| `doc/bot-code-map.md` — "ALWAYS read first" | `doc/bot-code-map.md` — "Search this for function names; read only the matching section" |
| `doc/dev-patterns.md` — "Before every feature" | `doc/dev-patterns.md` — "Read only the section matching your task type" |

**Size targets per file:**

| File type | Target size | Max size |
|---|---|---|
| Always-read index (`quick-ref.md`) | 3 KB | 5 KB |
| Domain topic doc (`doc/arch/*.md`) | 4–8 KB | 12 KB |
| Instruction file (`.github/instructions/*.md`) | 1–2 KB | 3 KB |
| Prompt / skill file (`.github/prompts/*.md`) | 1–3 KB | 5 KB |
| Source module (`src/**/*.py`) | < 40 KB | 60 KB |

### 2.4 Source Files — One Responsibility, One File

> **Rule:** Source files over 50 KB should be split by responsibility.

Large files cause two problems:
1. The entire file is loaded into context even for small edits.
2. Copilot generates longer responses to cover all edge cases visible in context.

Preferred structure: group by **domain** (features/, telegram/, ui/, core/) and keep each module under 40 KB.  
See `src/` package layout — each sub-package has a clear responsibility.

### 2.5 Skills Are Atomic Procedures

> **Rule:** Each skill (`.github/prompts/*.prompt.md`) should describe **one complete procedure** with a clear trigger and a verifiable output.

Good skill structure:
```
---
mode: agent
description: Deploy changed files to Pi, restart service, verify journal
---
## Trigger
User says: "deploy", "push to pi", or runs /skill-name

## Steps
1. ...
2. ...
3. ...

## Success Condition
Journal shows: [INFO] Version : X.Y.Z + Polling Telegram…
```

Skills must not duplicate content from instruction files. If a step is also described in an instruction file, link to the instruction file instead of repeating the text.

### 2.6 Separate Concerns in Root Files

> **Rule:** Root-level files (AGENTS.md, INSTRUCTIONS.md, SKILLS_AGENTS.md) must contain only content relevant to their purpose.

- `AGENTS.md` — bot version state, feature state, remote host config only. No accounting tasks.
- `INSTRUCTIONS.md` — project-level instructions only. Unrelated content goes to `concept/` or elsewhere.
- `SKILLS_AGENTS.md` — skill/agent registry only.

Mixing unrelated content causes Copilot to make incorrect cross-domain inferences.

---

## 3. Session Habits for Efficient Vibe Coding

### 3.1 Open Each Session With a Focused Reference

```
#file:doc/quick-ref.md  I want to add a reminder button to the calendar menu
```

This pins a 3 KB context instead of letting Copilot load multiple larger files.

### 3.2 Reference Specific File Sections, Not Whole Files

```
# Good — read only the voice section
#file:doc/arch/voice-pipeline.md

# Bad — loads 55 KB
#file:doc/architecture.md
```

For source files, reference the function's approximate line range:
```
#file:src/features/bot_calendar.py:260-310  fix date parsing in _finish_cal_add
```

### 3.3 Break Long Sessions Into Segments

Each VS Code Copilot Chat session has independent context. For complex tasks:
- **Session A:** Design + implement the core logic
- **Session B:** Write or update tests
- **Session C:** Deploy + verify + update docs

Use `AGENTS.md` (≤ 2 KB) to pass essential state between sessions.

### 3.4 Prefer `/skill-name` Over Typing Deployment Steps

Invoking `/taris-deploy-to-target` loads the skill prompt (~2 KB) as the task context.  
Typing "deploy the bot to pi with the full steps" causes Copilot to recall deployment content from multiple instruction files simultaneously — 3–4× the token cost.

### 3.5 Avoid `@workspace` Except for Discovery

`@workspace` scans all files and can inject 50 000+ tokens. Use it only for:
- Initial discovery: "what files are in src/features?"
- One-time questions you cannot answer from `doc/quick-ref.md`

For everything else, use `#file:specific-path.py`.

### 3.6 Vibe Coding Protocol — Log Every Session

After each completed request, append a row to `doc/vibe-coding-protocol.md`:
```
| HH:MM UTC | short description | complexity 1–5 | N turns | model-id | files changed | done |
```

This log is the primary dataset for measuring whether optimizations actually improve session length and turn count.

---

## 4. File Naming and Organization Conventions

### 4.1 Document Hierarchy

```
doc/
  quick-ref.md              ← single always-read index (~3 KB)
  architecture.md           ← index-only (links to doc/arch/*)
  bot-code-map.md           ← search index, not a reading doc
  dev-patterns.md           ← patterns grouped by task type
  test-suite.md             ← test reference
  vibe-coding-protocol.md   ← session log
  vibe-coding-guidelines.md ← this file
  arch/
    overview.md             ← system diagram + 3-channel summary
    voice-pipeline.md       ← audio, Vosk, VAD, Piper chain
    web-ui.md               ← FastAPI, JWT, templates, HTMX
    data-layer.md           ← SQLite, bot_db.py, migration
    security.md             ← RBAC, prompt injection guard
    deployment.md           ← services, systemd, PI1/PI2 pipeline
    llm-providers.md        ← OpenRouter, bot_llm.py, providers
    hardware.md             ← Pi specs, audio, benchmarks
  todo/
    *.md                    ← per-feature specs (linked from TODO.md)

concept/
  copilot_optimization.md   ← performance analysis and proposals
  *.md                      ← future-feature concepts (not loaded by Copilot)

.github/
  copilot-instructions.md   ← TINY always-loaded workspace instructions
  instructions/
    bot-coding.instructions.md      ← patterns for src/*.py (< 2 KB)
    bot-deploy.instructions.md      ← deploy summary for src/*.py (< 2 KB)
    safe-update.instructions.md     ← schema-change protocol (< 2 KB)
    voice-regression.instructions.md← voice test trigger (scoped to voice files)
  prompts/
    taris-*.prompt.md       ← skill files, one procedure per file
  agents/
    *.md                    ← agent definitions (not read by default)
```

### 4.2 Naming Conventions

| Artifact | Convention | Example |
|---|---|---|
| Domain docs | `doc/arch/<domain>.md` | `doc/arch/voice-pipeline.md` |
| Feature specs | `doc/todo/<topic>.md` | `doc/todo/5-voice-pipeline.md` |
| Skills | `taris-<action>.prompt.md` | `taris-deploy-to-target.prompt.md` |
| Instructions | `<domain>.instructions.md` | `bot-coding.instructions.md` |
| Concept docs | `concept/<topic>.md` | `concept/copilot_optimization.md` |
| Test files | `test_<module>.py` | `test_voice_regression.py` |

---

## 5. Optimization Checklist — Before Creating a New Artifact

Before creating any new doc, instruction file, or skill, answer:

1. **Who reads it?** Human only → `doc/` or `concept/`. Copilot auto-loads → `.github/instructions/` (keep tiny).
2. **When is it needed?** Always → `copilot-instructions.md` (< 500 tokens). Task-specific → scoped instruction or skill.
3. **Does this content already exist elsewhere?** If yes, add a pointer instead of duplicating.
4. **How large will it be?** > 5 KB → split into sections or use a summary + link pattern.
5. **Is the `applyTo:` glob as narrow as possible?** `"**"` is almost never the right answer.

---

## 6. Quick Reference — Token Budget by Artifact Type

| Artifact | Ideal tokens | Warning threshold |
|---|---|---|
| `copilot-instructions.md` | 400–600 | > 1 500 |
| Each `*.instructions.md` | 300–600 | > 1 000 |
| Each `*.prompt.md` (skill) | 400–800 | > 1 500 |
| `doc/quick-ref.md` | 600–800 | > 1 500 |
| Each `doc/arch/*.md` | 800–2 000 | > 3 000 |
| Each source module | 3 000–10 000 | > 15 000 |

**Total baseline per request (instructions only):** target < 2 000 tokens.  
**Total first-request budget (instructions + 1 source file):** target < 15 000 tokens.

---

## 7. Metrics and Review Cadence

Measure these at the end of each development sprint (every 10 sessions or 1 week):

| Metric | Target | How to measure |
|---|---|---|
| Baseline tokens per request | < 2 000 | Add up sizes of always-loaded files ÷ 4 |
| Turns before compaction | ≥ 8 | `doc/vibe-coding-protocol.md` session log |
| Largest instruction file | < 3 KB | `wc -c .github/instructions/*.md` |
| Largest always-loaded doc | < 5 KB | `wc -c .github/copilot-instructions.md` |
| Duplicate content instances | 0 | grep deploy steps across `.github/` |

Review `concept/copilot_optimization.md` quarterly to update the "before/after" budget table and close completed proposals.

---

*Last updated: 2026-03-19 by GitHub Copilot agent (issue: Optimization of performance using copilot)*
