# Copilot Instructions — picoclaw workspace

## Project Overview

picoclaw is a Raspberry Pi–based Telegram bot + offline voice assistant (Russian/German/English). Bot source lives in `src/`. The Pi target host is `OpenClawPI`. All secrets are in `.credentials/` (git-ignored).

## Reference Docs — Read First
| Document | When to use |
|---|---|
| [`doc/bot-code-map.md`](../doc/bot-code-map.md) | **Always** — find any function by name/line before searching the file. Maps every function in `telegram_menu_bot.py` with its line number and purpose. Also lists all callback `data=` keys and all runtime files on the Pi. |
| [`doc/dev-patterns.md`](../doc/dev-patterns.md) | **Before adding any feature** — exact copy-paste patterns for: voice opts, callbacks, multi-step input flows, i18n strings, access guards, versioning, subprocess calls, session state, deployment, service files. |
| [`doc/architecture.md`](../doc/architecture.md) | When adding components, services, or changing the pipeline. Keep it in sync. |
| [`doc/hardware-performance-analysis.md`](../doc/hardware-performance-analysis.md) | Before choosing algorithms, models, or suggesting hardware upgrades. |
| [`doc/test-suite.md`](../doc/test-suite.md) | **Before running or extending tests** — complete reference for all test categories (voice regression T01–T21, Web UI Playwright, hardware audio, smoke), trigger rules, run commands, and Copilot chat-mode "test software" protocol. |
| [`TODO.md`](../TODO.md) | **Session start** — check what is planned/in-progress/done before proposing work. |

### Quick rules from the patterns doc

- Voice opts: 6-step pattern — defaults `False`, toggle row, opt-in side-effect in `_handle_voice_opt_toggle()` and `main()`
- New callback: handler function + button in keyboard + dispatch branch in `handle_callback()`
- Version bump: always `BOT_VERSION = "YYYY.M.D"` + prepend entry in `release_notes.json` (never use `\_` in JSON — invalid escape)
- Deploy: pscp all changed files → plink restart → verify `Version : X.Y.Z` in journal
- Strings: always add to both `"ru"` and `"en"` in `src/strings.json`
- **Testing ("test software" / "run tests" / "verify"):** consult `doc/test-suite.md` — it has the complete decision table (Section 1), all run commands, and the Copilot chat-mode protocol (Section 10). Do **not** scan test files manually every time.

### Post-deploy rule — ALWAYS ask after every successful deploy to the Pi

After every successful deployment to the host (confirmed by journal showing `Version : X.Y.Z` and `Polling Telegram…`), **always ask the user**:

 "Deployment verified ✅. Shall I also:
 1. Commit and push to git? (if not already done)
 2. Update `release_notes.json` with a new version entry? (if `BOT_VERSION` was bumped)"

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

## Remote Host

| Key | Value |
|---|---|
| Host | `OpenClawPI` (LAN) / `100.81.143.126` (Tailscale) |
| User | `stas` |
| Password | see `.env` → `%HOSTPWD%` |
| SSH | `plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "<cmd>"` |
| SCP | `pscp -pw "%HOSTPWD%" <file> stas@OpenClawPI:<remote-path>` |

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
- **Docs:** update `doc/architecture.md`, `README.md` etc. in the same commit as the code change.
- **TODO.md:** keep current; collapse completed items to `✅ Implemented (vX.Y.Z)`.

## Post-Deploy Rule

After every successful deployment (journal shows `Version : X.Y.Z` and `Polling Telegram…`), ask:
> "Deployment verified ✅. Shall I also: 1. Commit and push to git? 2. Update `release_notes.json`?"

## Vibe Coding Protocol

After every completed request, append a row to `doc/vibe-coding-protocol.md`:
```
| HH:MM UTC | description | complexity 1–5 | N turns | model-id | files changed | done |
```
