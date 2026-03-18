# Copilot Instructions — picoclaw workspace

## Available Skills (Prompt Files)

These reusable task prompts live in `.github/prompts/`. Invoke them with `/skill-name` in VS Code Copilot Chat (requires VS Code 1.99+ with `chat.promptFiles: true` — already set in `.vscode/settings.json`).

| `/skill-name` | What it does |
|---|---|
| `/taris_deploy_to_target` | Copy changed files to Pi, restart service, verify journal |
| `/taris_backup_target` | Backup a Raspberry Pi target (data, software, system config, binaries, or all) |
| `/taris_performancetest` | Run taris performance benchmarks (storage ops, menu navigation) locally and/or on Pi targets, merge results, and print a cross-platform comparison |
| `/run-tests` | Run voice regression T01–T21 on Pi, report results |
| `/bump-version` | Update `BOT_VERSION`, prepend release note, commit |
| `/test-software` | Auto-select tests based on changed files (also triggered by plain "test software") |
| `/taris_update_doc` | Sync project documentation (`doc/arch/`, code-map, TODO, README) with current implementation |
| `/taris_test_ui` | Run Web UI Playwright + Telegram smoke tests; detect and fill coverage gaps via playwright-mcp |

📖 Full usage guide: [`doc/copilot-skills-guide.md`](../doc/copilot-skills-guide.md)

---

## Project

picoclaw is a Raspberry Pi–based Telegram bot + offline voice assistant (Russian/German/English). Bot source lives in `src/`. The Pi target host is `OpenClawPI`. All secrets are in `.credentials/` (git-ignored).

## Reference Docs — Read on Demand

| Document | When to use |
|---|---|
| [`doc/quick-ref.md`](../doc/quick-ref.md) | **Always-read first** — module map, key functions, test triggers, deploy pipeline (~3 KB) |
| [`doc/bot-code-map.md`](../doc/bot-code-map.md) | **Search, don't read whole** — grep/search for function names, callback keys, or file names; read only the matching section (~2 KB). Do NOT load the full 39 KB file. |
| [`doc/dev-patterns.md`](../doc/dev-patterns.md) | **Before adding any feature** — exact copy-paste patterns for: voice opts, callbacks, multi-step input flows, i18n strings, access guards, versioning, subprocess calls, session state, deployment, service files. |
| [`doc/architecture.md`](../doc/architecture.md) | **Search, don't read whole** — index of eight topic files in `doc/arch/`. Read only the relevant topic: [overview](../doc/arch/overview.md) · [voice-pipeline](../doc/arch/voice-pipeline.md) · [telegram-bot](../doc/arch/telegram-bot.md) · [security](../doc/arch/security.md) · [features](../doc/arch/features.md) · [deployment](../doc/arch/deployment.md) · [multilanguage](../doc/arch/multilanguage.md) · [web-ui](../doc/arch/web-ui.md) |
| [`doc/hardware-performance-analysis.md`](../doc/hardware-performance-analysis.md) | Before choosing algorithms, models, or suggesting hardware upgrades. |
| [`doc/test-suite.md`](../doc/test-suite.md) | **Before running or extending tests** — complete reference for all test categories (voice regression T01–T21, Web UI Playwright, hardware audio, smoke), trigger rules, run commands, and Copilot chat-mode "test software" protocol. |
| [`TODO.md`](../TODO.md) | **Session start** — check what is planned/in-progress/done before proposing work. |

## Workspace Layout

```
picoclaw/
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

- **Secrets:** never hard-code; keep in `.credentials/.pico_env` and `.env` only.
- **Source files:** all target-side sources go in `src/`; `.credentials/` holds secrets only.
- **Version bump:** `BOT_VERSION = "YYYY.M.D"` + prepend entry in `src/release_notes.json`. Never use `\_` in JSON strings.
- **Strings:** add to all three languages (`ru`, `en`, `de`) in `src/strings.json`.
- **Service files:** always deploy to Pi in the same commit/operation as code changes. See [bot-deploy](.github/instructions/bot-deploy.instructions.md).
- **UI changes:** apply to both Telegram and Web UI simultaneously. See [bot-coding](.github/instructions/bot-coding.instructions.md).
- **Docs:** update the relevant `doc/arch/<topic>.md` file and `README.md` in the same commit as the code change.
- **TODO.md:** keep current; collapse completed items to `✅ Implemented (vX.Y.Z)`.
- **Deployment pipeline:** ALL changes MUST be deployed and tested on the engineering target **PI2** (`OpenClawPI2`) first. Only after tests pass and the change is committed and pushed to git may it be deployed to the production target **PI1** (`OpenClawPI`). Never deploy directly to PI1 without prior PI2 validation.

## Post-Deploy Rule

After every successful deployment (journal shows `Version : X.Y.Z` and `Polling Telegram…`), ask:
> "Deployment verified ✅. Shall I also: 1. Commit and push to git? 2. Update `release_notes.json`?"

## Vibe Coding Protocol

After every completed request, append a row to `doc/vibe-coding-protocol.md`:
```
| HH:MM UTC | description | complexity 1–5 | N turns | model-id | files changed | done |
```

