# Copilot Instructions — taris workspace

## Available Skills (Prompt Files)

These reusable task prompts live in `.github/prompts/`. Invoke them with `/skill-name` in VS Code Copilot Chat (requires VS Code 1.99+ with `chat.promptFiles: true` — already set in `.vscode/settings.json`).

| `/skill-name` | What it does |
|---|---|
| `/taris-deploy-to_target` | Copy changed files to Pi, restart service, verify journal |
| `/taris-deploy-openclaw-target` | Deploy OpenClaw variant locally to TariStation2 (engineering) and remote TariStation1/SintAItion (production) |
| `/taris-backup-target` | Backup a Raspberry Pi target (data, software, system config, binaries, or all) |
| `/taris-performancetest` | Run taris performance benchmarks (storage ops, menu navigation) locally and/or on Pi targets, merge results, and print a cross-platform comparison |
| `/taris-test-run-tests` | Run voice regression T01–T41 on Pi, report results |
| `/taris-run-full-tests` | Run full test suite: telegram offline, screen loader, LLM, voice regression (local + Pi), Web UI Playwright |
| `/taris-bump-version` | Update `BOT_VERSION`, prepend release note, commit |
| `/taris-test-software` | Auto-select tests based on changed files (also triggered by plain "test software") |
| `/taris-update-doc` | Sync project documentation (`doc/arch/`, code-map, TODO, README) with current implementation |
| `/taris-test-ui` | Run Web UI Playwright + Telegram smoke tests; detect and fill coverage gaps via playwright-mcp |
| `/taris-openclaw-setup` | Setup, configure, troubleshoot, and extend the OpenClaw variant (STT, LLM, sync, tests) |

📖 Full usage guide: [`doc/copilot-skills-guide.md`](../doc/copilot-skills-guide.md)

---

## Project

taris is a Raspberry Pi–based Telegram bot + offline voice assistant (Russian/German/English). Bot source lives in `src/`. The Pi target host is `OpenClawPI`. All secrets are in `.credentials/` (git-ignored).

## Reference Docs — Read on Demand

**Architecture docs are Copilot navigation maps — not textbooks. Use them to locate the right file and function, then go there. Never read an arch doc in full when you only need one section.**

| Document | When to use |
|---|---|
| [`doc/quick-ref.md`](../doc/quick-ref.md) | **Always-read first** — module map, key functions, test triggers, deploy pipeline (~3 KB) |
| [`doc/bot-code-map.md`](../doc/bot-code-map.md) | **Search, don't read whole** — grep for function name, callback key, or file name; read only the matching section. Do NOT load the full file. |
| [`doc/dev-patterns.md`](../doc/dev-patterns.md) | **Before adding any feature** — copy-paste patterns for callbacks, voice opts, multi-step flows, i18n, access guards, subprocess, session state. |
| [`doc/architecture.md`](../doc/architecture.md) | **Index only** — find the right topic file, then read only that file. Never load the index AND the topic file. |
| [`doc/hardware-performance-analysis.md`](../doc/hardware-performance-analysis.md) | Before choosing algorithms, models, or suggesting hardware upgrades. |
| [`doc/test-suite.md`](../doc/test-suite.md) | **Before running or extending tests** — all test categories, run commands, trigger rules. |
| [`TODO.md`](../TODO.md) | **Session start** — check planned/in-progress/done before proposing work. |

### Architecture Topic Files — use the right one, read only the relevant section

| Topic | File | Read when |
|---|---|---|
| System overview, variant comparison, module map | [`doc/arch/overview.md`](../doc/arch/overview.md) | Understanding overall structure, adding a new service |
| PicoClaw variant (Pi, Vosk, Piper, systemd) | [`doc/arch/picoclaw.md`](../doc/arch/picoclaw.md) | Pi-specific code, service files, audio HAT |
| OpenClaw variant (faster-whisper, Ollama, REST) | [`doc/arch/openclaw-integration.md`](../doc/arch/openclaw-integration.md) | OpenClaw-specific code, skill integration |
| Voice pipeline (STT/TTS/VAD/hotword) | [`doc/arch/voice-pipeline.md`](../doc/arch/voice-pipeline.md) | Modifying `bot_voice.py` or `voice_assistant.py` |
| Telegram bot modules, routing, callbacks | [`doc/arch/telegram-bot.md`](../doc/arch/telegram-bot.md) | Adding handlers, callbacks, menu buttons |
| Security, RBAC, user roles, prompt injection | [`doc/arch/security.md`](../doc/arch/security.md) | Modifying access logic, roles, `bot_security.py` |
| Feature domains (mail, calendar, contacts, docs) | [`doc/arch/features.md`](../doc/arch/features.md) | Adding or modifying user features |
| **Conversation, memory, multi-turn context, RAG** | [`doc/arch/conversation.md`](../doc/arch/conversation.md) | Modifying LLM call structure, history, memory, RAG injection |
| **Data layer (SQLite/Postgres, schema, stores)** | [`doc/arch/data-layer.md`](../doc/arch/data-layer.md) | Adding DB columns, switching backends, data file paths |
| **Software stacks (all libs, binaries, third-party)** | [`doc/arch/stacks.md`](../doc/arch/stacks.md) | Checking deps, upgrading packages, adding third-party tools |
| **Knowledge base (RAG, documents, KB sources)** | [`doc/arch/knowledge-base.md`](../doc/arch/knowledge-base.md) | Modifying RAG pipeline, document indexing, notes/calendar as KB |
| Deployment, file layout, config, backup | [`doc/arch/deployment.md`](../doc/arch/deployment.md) | Deploying or changing config constants |
| Multilanguage / i18n, `_t()` | [`doc/arch/multilanguage.md`](../doc/arch/multilanguage.md) | Adding i18n strings or a new language |
| Web UI (FastAPI, routes, auth, Screen DSL) | [`doc/arch/web-ui.md`](../doc/arch/web-ui.md) | Modifying `bot_web.py` or templates |
| LLM providers, multi-turn, tiered memory | [`doc/arch/llm-providers.md`](../doc/arch/llm-providers.md) | Modifying `bot_llm.py` or adding providers |

### Architecture Doc Style Rules (enforced when writing or updating arch docs)

These rules ensure docs stay useful as Copilot navigation tools and don't waste tokens:

1. **Tables over prose.** Every section must lead with a table (functions, files, config constants, routing rules). Prose only for decisions that can't be expressed as a table.
2. **File + function pointers are mandatory.** Every documented behaviour must reference the exact file and function name where the code lives.
3. **"When to read this file" header required.** Every `doc/arch/*.md` file must open with a 1–2 line "When to read" statement so Copilot can decide whether to load it.
4. **No background or history.** Don't explain why something was built this way. Only document what it is and where to change it.
5. **⏳ OPEN labels for unimplemented items.** Any feature that is planned but not yet in code gets `> ⏳ **OPEN:** <one line description> → See [TODO.md §N](../TODO.md#section)`. This lets Copilot know not to rely on it.
6. **Version header must match `BOT_VERSION`.** Update `**Version:**` on every edit.
7. **Keep each topic file under 250 lines.** If a file grows beyond that, split into sub-topic files and add links from the parent.
8. **Don't duplicate.** If information lives in `bot-code-map.md`, link to it from the arch doc rather than repeating it.

## Workspace Layout

```
taris/
  src/            ← ALL target-side sources (Python, shell, services, tests)
    setup/        ← shell scripts (run on Pi)
    services/     ← systemd .service units
    tests/        ← hardware & regression tests
  backup/device/  ← sanitized Pi config snapshot
  doc/            ← architecture, code map, dev patterns
  .credentials/   ← secrets ONLY (never scripts or code)
  .env            ← remote host vars (gitignored)
```

## Skills — Use These for Specific Tasks

| Task | Skill file |
|---|---|
| Deploy bot to Pi | [bot-deploy](.github/instructions/bot-deploy.instructions.md) |
| Voice file changes | [voice-regression](.github/instructions/voice-regression.instructions.md) |
| Major update (schema/modules change) | [safe-update](.github/instructions/safe-update.instructions.md) |
| Adding/editing bot features | [bot-coding](.github/instructions/bot-coding.instructions.md) |

## Mandatory Rules

- **Secrets:** never hard-code; keep in `.credentials/.taris_env` and `.env` only.
- **Source files:** all target-side sources go in `src/`; `.credentials/` holds secrets only.
- **Version bump:** `BOT_VERSION = "YYYY.M.D"` + prepend entry in `src/release_notes.json`. Never use `\_` in JSON strings.
- **Strings:** add to all three languages (`ru`, `en`, `de`) in `src/strings.json`.
- **Service files:** always deploy to Pi in the same commit/operation as code changes. See [bot-deploy](.github/instructions/bot-deploy.instructions.md).
- **UI changes:** apply to both Telegram and Web UI simultaneously. See [bot-coding](.github/instructions/bot-coding.instructions.md).
- **Docs:** update the relevant `doc/arch/<topic>.md` file and `README.md` in the same commit as the code change.
- **TODO.md:** keep current; collapse completed items to `✅ Implemented (vX.Y.Z)`.
- **Deployment pipeline:** ALL changes MUST be deployed and tested on the engineering target **PI2** (`OpenClawPI2`) first. Only after tests pass and the change is committed and pushed to git may it be deployed to the production target **PI1** (`OpenClawPI`). Never deploy directly to PI1 without prior PI2 validation.
- **Continuous test improvement:** Every bug fix MUST add a regression test that would have caught the bug. Every new feature MUST add tests covering the happy path and the main failure modes. Tests live in `src/tests/test_voice_regression.py` (T-numbered) for voice/config/LLM; add new test IDs sequentially. Update `doc/test-suite.md` with the new test IDs in the same commit. No exceptions.

## Post-Deploy Rule

After every successful deployment (journal shows `Version : X.Y.Z` and `Polling Telegram…`), ask:
> "Deployment verified ✅. Shall I also: 1. Commit and push to git? 2. Update `release_notes.json`?"

## Vibe Coding Protocol

After every completed request, append a row to `doc/vibe-coding-protocol.md`:
```
| HH:MM UTC | description | complexity 1–5 | N turns | model-id | files changed | done |
```

