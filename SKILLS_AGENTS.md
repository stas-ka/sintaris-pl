# Skills & Agents — Quick Reference

## How to invoke

| Type | Invocation | Example |
|---|---|---|
| **Skill** | `/skill-name` in Copilot Chat | `/taris_deploy-to-target bot_admin.py changed, deploy to pi2` |
| **Agent** | `@agent-name` in Copilot Chat | `@su-first-copilot-agent review the voice pipeline` |

---

## Skills

| Skill | Invocation | Purpose |
|---|---|---|
| **taris_deploy-to-target** | `/taris_deploy-to-target` | Full Pi deployment lifecycle — incremental file deploy, full module deploy, Web UI deploy, service file deploy, safe update with backup, voice regression tests, post-deploy verification, PI1 promotion. Covers **OpenClawPI2 (test)** and **OpenClawPI (production)**. |

Skill files: [`.github/skills/`](.github/skills/)

---

## Agents

| Agent | Invocation | Purpose |
|---|---|---|
| **SU first Copilot Agent** | `@SU first Copilot Agent` | Review and test PicoClaw — uses shell, search, edit, web, SSH tools. Good for end-to-end code review, test execution, and debugging. |

Agent files: [`.github/agents/`](.github/agents/)

---

## Standalone Tools (not skills)

| Tool | Location | Use |
|---|---|---|
| VPS nginx deploy | `src/setup/deploy_vps.sh` | **One-time only** — provisions nginx reverse proxy + Let's Encrypt SSL on `agents.sintaris.net`. Not related to Pi bot deploy. |
| DB migration | `tools/migrate_to_db.py` | **Optional** — run `--dry-run` first; only execute when Pi data schema changes. |
