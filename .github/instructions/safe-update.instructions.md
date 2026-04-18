---
applyTo: "src/core/bot_db.py,src/core/bot_state.py,src/core/bot_config.py,src/setup/migrate_to_db.py"
---

# Safe Update Protocol — Skill

Use this protocol for any update that changes data formats, adds/removes modules, or modifies the SQLite schema. For pure code hotfixes with no schema change, the [bot-deploy](bot-deploy.instructions.md) workflow is sufficient.

## Pre-Update Checklist

1. All local changes committed to git
2. Target host reachable: `plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo ok"`
3. Backup location exists: `backup/snapshots/`

## Steps (9-step protocol)

Full commands → `/taris-deploy-to-target` skill or `doc/quick-ref.md` §Deploy Pipeline.

**Condensed checklist:**
1. Create backup on Pi → expect `BACKUP_OK`
2. Verify backup contents (bot.env, taris.db, config.json present)
3. Download backup: `pscp … backup\snapshots\%BNAME%\` — **DO NOT PROCEED** until local
4. Stop services: `systemctl stop taris-telegram taris-web taris-voice`
5. Deploy changed files (see `doc/quick-ref.md` §Deploy Pipeline for pscp commands)
6. Run migration if schema changed: `python3 migrate_to_db.py → MIGRATION_OK`
7. Start services + verify journal: `[INFO] Version : X.Y.Z` + `Polling Telegram…`
8. Run regression tests: `test_voice_regression.py` + UI Playwright
9. On failure: restore from backup → `RESTORE_OK`

## Rules

- **NEVER** deploy without a local backup downloaded first.
- **NEVER** run migration before stopping services (race condition).
- **NEVER** skip regression tests after a schema change.
- Keep the last 3 backup archives locally; delete older ones after successful tests.
- After a successful update: `git tag deploy/YYYY.M.D`
- **Deployment pipeline:** ALL changes MUST be deployed and tested on the engineering target **PI2** (`OpenClawPI2`) first. Only after tests pass and the change is committed and pushed to git may it be deployed to the production target **PI1** (`OpenClawPI`). Never deploy directly to PI1 without prior PI2 validation.
- **TariStation1 (SintAItion) is a shared production VPS** — every individual action (stop services, migrate, start services, package install) requires **explicit confirmation from the user (stas)** before execution. State the schema changes and confirm backup exists before running any migration on TS1. See the VPS safety rules in `.github/skills/taris-deploy-openclaw-target/SKILL.md`.
