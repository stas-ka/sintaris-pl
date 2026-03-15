# Copilot Instructions — picoclaw workspace

## Project Overview

picoclaw is a Raspberry Pi–based Telegram bot + offline voice assistant (Russian/German/English). Bot source lives in `src/`. The Pi target host is `OpenClawPI`. All secrets are in `.credentials/` (git-ignored).

## Reference Docs — Read First

| Document | When to use |
|---|---|
| [`doc/bot-code-map.md`](../doc/bot-code-map.md) | **Always** — function index, callback `data=` keys, runtime files on Pi |
| [`doc/dev-patterns.md`](../doc/dev-patterns.md) | Before adding any feature — voice opts, callbacks, i18n, versioning, subprocess, session state |
| [`doc/architecture.md`](../doc/architecture.md) | When adding components, services, or changing the pipeline |
| [`doc/hardware-performance-analysis.md`](../doc/hardware-performance-analysis.md) | Before choosing algorithms, models, or hardware upgrades |
| [`TODO.md`](../TODO.md) | **Session start** — check planned/in-progress/done work before proposing work |

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
