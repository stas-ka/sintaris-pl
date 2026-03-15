---
name: deploy-to-target
description: 'Deploy picoclaw bot to Raspberry Pi targets (OpenClawPI2 / OpenClawPI). Use when: deploying bot updates, pushing new features, deploying service files, restarting services, verifying deployment, running post-deploy tests, safe update with backup, incremental file deploy, full module deploy, release version bump, checking journal logs after restart.'
argument-hint: 'Which files changed? (e.g. all, bot_admin.py, strings.json) and target (pi2/pi1/both)'
---

# Deploy to Target — Picoclaw Raspberry Pi

## When to Use

- You changed one or more `src/*.py`, `src/strings.json`, `src/release_notes.json`
- You changed a `src/services/*.service` file
- You changed a `src/templates/*.*` file
- You need to bump `BOT_VERSION` and push a release
- You need to run a safe update with backup + migration
- You want to verify the current deployed state of a target

## ⚠️ Target Priority Rule

**ALWAYS deploy to PI2 first. PI1 requires project lead (stas) confirmation after PI2 tests pass.**

| Target | Hostname | Env var |
|---|---|---|
| PI2 (engineering) | `OpenClawPI2` | `%TARGET2PWD%` |
| PI1 (production) | `OpenClawPI` | `%HOSTPWD%` |

---

## Procedure

### Step 0 — Pre-Deploy: Version Bump & Release Notes *(mandatory for user-facing changes)*

> ⚠️ **Do this BEFORE deploying.** Skipping this means `BOT_VERSION` stays unchanged, `last_notified_version.txt` matches it, and **no Telegram notification fires** — admins never learn about the deployed fix.

For any user-facing change (bug fix, feature, UI/text change, voice change, string update):

1. **Bump `BOT_VERSION`** in `src/bot_config.py` — format `YYYY.M.D` (e.g., `"2026.3.29"`). Same-day second release: append `+1` (e.g., `"2026.3.29+1"`).
2. **Prepend** a new entry to `src/release_notes.json` (top of array):
   ```json
   {
     "version": "2026.X.Y",
     "date":    "2026-0X-0Y",
     "title":   "Short description of the change",
     "notes":   "- Bullet 1\n- Bullet 2"
   }
   ```
   Validate: `python3 -c "import json,sys; json.load(sys.stdin)" < src/release_notes.json`
3. **Always include** `bot_config.py` and `release_notes.json` in the deploy file list (Step 1).
4. After restart, the bot **automatically** sends a Telegram notification to all admins — no manual step needed.

> ✅ Skip this step **only** for infrastructure-only changes (service files, tests, secrets) with no user-visible effect.

---

### Step 1 — Classify the change

Ask or determine:

| Change type | Deploy path |
|---|---|
| Python module(s) only | [Incremental deploy](#incremental-deploy) |
| `strings.json` / `release_notes.json` | [Incremental deploy](#incremental-deploy) + version bump |
| `.service` file | [Service file deploy](#service-file-deploy) |
| Schema / data format change | [Safe update with backup](#safe-update-with-backup) |
| Web UI templates / static | [Web UI deploy](#web-ui-deploy) |

---

### Incremental Deploy

Replace `<files>` with the changed files. Always restart after.

```bat
rem PI2 (always first)
pscp -pw "%TARGET2PWD%" src\<file1.py> src\<file2.py> stas@OpenClawPI2:/home/stas/.picoclaw/
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "echo %TARGET2PWD% | sudo -S systemctl restart picoclaw-telegram && sleep 3 && journalctl -u picoclaw-telegram -n 12 --no-pager"
```

**Expected journal output (success):**
```
[INFO] Version      : 2026.X.Y
[INFO] Polling Telegram…
```

If `strings.json` or `release_notes.json` changed, also deploy those:
```bat
pscp -pw "%TARGET2PWD%" src\strings.json src\release_notes.json stas@OpenClawPI2:/home/stas/.picoclaw/
```

---

### Full Module Deploy

Use after a major refactor or first-time deploy to a target.

```bat
pscp -pw "%TARGET2PWD%" src\bot_config.py src\bot_state.py src\bot_instance.py stas@OpenClawPI2:/home/stas/.picoclaw/
pscp -pw "%TARGET2PWD%" src\bot_security.py src\bot_access.py src\bot_users.py stas@OpenClawPI2:/home/stas/.picoclaw/
pscp -pw "%TARGET2PWD%" src\bot_voice.py src\bot_calendar.py src\bot_admin.py stas@OpenClawPI2:/home/stas/.picoclaw/
pscp -pw "%TARGET2PWD%" src\bot_handlers.py src\bot_mail_creds.py src\bot_email.py stas@OpenClawPI2:/home/stas/.picoclaw/
pscp -pw "%TARGET2PWD%" src\bot_error_protocol.py src\bot_llm.py src\bot_web.py stas@OpenClawPI2:/home/stas/.picoclaw/
pscp -pw "%TARGET2PWD%" src\bot_actions.py src\bot_ui.py src\render_telegram.py stas@OpenClawPI2:/home/stas/.picoclaw/
pscp -pw "%TARGET2PWD%" src\telegram_menu_bot.py stas@OpenClawPI2:/home/stas/.picoclaw/
pscp -pw "%TARGET2PWD%" src\strings.json src\release_notes.json stas@OpenClawPI2:/home/stas/.picoclaw/
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "echo %TARGET2PWD% | sudo -S systemctl restart picoclaw-telegram picoclaw-web && sleep 3 && journalctl -u picoclaw-telegram -n 12 --no-pager"
```

---

### Web UI Deploy

Use when `bot_web.py`, templates, or static assets changed.

```bat
pscp -pw "%TARGET2PWD%" src\bot_web.py stas@OpenClawPI2:/home/stas/.picoclaw/
pscp -pw "%TARGET2PWD%" src\templates\*.html stas@OpenClawPI2:/home/stas/.picoclaw/templates/
pscp -pw "%TARGET2PWD%" src\static\style.css stas@OpenClawPI2:/home/stas/.picoclaw/static/
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "echo %TARGET2PWD% | sudo -S systemctl restart picoclaw-telegram picoclaw-web && sleep 3 && journalctl -u picoclaw-telegram -n 5 --no-pager && journalctl -u picoclaw-web -n 5 --no-pager"
```

---

### Service File Deploy

Required after any change to `src/services/*.service`. Run for the affected service name.

```bat
set SVCNAME=picoclaw-telegram
pscp -pw "%TARGET2PWD%" src\services\%SVCNAME%.service stas@OpenClawPI2:/tmp/%SVCNAME%.service
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "echo %TARGET2PWD% | sudo -S cp /tmp/%SVCNAME%.service /etc/systemd/system/%SVCNAME%.service && sudo systemctl daemon-reload && sudo systemctl restart %SVCNAME%"
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "journalctl -u %SVCNAME% -n 10 --no-pager"
```

---

### Safe Update with Backup

Required when data format, schema, or new modules are added. See full protocol in [`doc/architecture.md`](../../doc/architecture.md).

**Step 1 — Create timestamped backup on Pi:**
```bat
for /f %%i in ('powershell -c "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
for /f %%v in ('plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "grep BOT_VERSION /home/stas/.picoclaw/bot_config.py | head -1 | cut -d'\"' -f2"') do set VER=%%v
set BNAME=picoclaw_backup_OpenClawPI2_v%VER%_%TS%
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "tar czf /tmp/%BNAME%.tar.gz -C /home/stas/.picoclaw --exclude=vosk-model-small-ru --exclude=vosk-model-small-de --exclude='*.onnx' --exclude='ggml-*.bin' . 2>/dev/null && echo BACKUP_OK"
```

**Step 2 — Download backup locally:**
```bat
if not exist backup\snapshots\%BNAME% mkdir backup\snapshots\%BNAME%
pscp -pw "%TARGET2PWD%" stas@OpenClawPI2:/tmp/%BNAME%.tar.gz backup\snapshots\%BNAME%\
```

**Step 3 — Stop services, deploy, migrate, restart:**
```bat
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "echo %TARGET2PWD% | sudo -S systemctl stop picoclaw-telegram picoclaw-web 2>/dev/null; echo STOPPED"
rem ... deploy files (pscp) ...
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "echo %TARGET2PWD% | sudo -S systemctl start picoclaw-telegram picoclaw-web && sleep 3 && journalctl -u picoclaw-telegram -n 12 --no-pager"
```

---

## Step 2 — Verify Deployment

Check the journal after restart:

```bat
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "journalctl -u picoclaw-telegram -n 20 --no-pager"
```

✅ **Pass criteria:**
- `[INFO] Version      : 2026.X.Y` — correct version shown
- `[INFO] Polling Telegram…` — bot is listening
- No `ERROR` or `Exception` lines

❌ **If startup fails:**
```bat
rem Check full error
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "journalctl -u picoclaw-telegram -n 50 --no-pager | grep -i error"
```

---

## Step 3 — Run Post-Deploy Tests

### Voice regression tests (mandatory if voice files changed)

```bat
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "python3 /home/stas/.picoclaw/tests/test_voice_regression.py"
```

Tests T01–T21 cover: model files, STT/TTS pipelines, i18n coverage, bot name injection, calendar/note callbacks.

### Web UI tests (mandatory if web files changed)

```bat
py -m pytest src/tests/ui/test_ui.py -v --base-url https://openclawpi2:8080 --browser chromium
```

---

## Step 4 — Version Bump Checklist

If `BOT_VERSION` was changed, always:

1. **`src/bot_config.py`** — update `BOT_VERSION = "YYYY.M.D"`
2. **`src/release_notes.json`** — prepend new entry at top of array:
   ```json
   {
     "version": "2026.X.Y",
     "date":    "2026-0X-0Y",
     "title":   "Short feature name",
     "notes":   "- Bullet 1\n- Bullet 2"
   }
   ```
   Validate JSON: `python3 -c "import json,sys; json.load(sys.stdin)" < src/release_notes.json`

3. Deploy both files, restart, verify admin notification in journal:
   ```bat
   plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "journalctl -u picoclaw-telegram -n 20 --no-pager | grep -i release"
   ```
   Expected: `[ReleaseNotes] notified admin 994963580 (v2026.X.Y)`

---

## Step 5 — Post-Deploy Prompt *(always ask the user)*

After every successful deployment, ask:

> "Deployment verified ✅. Shall I also:
> 1. Commit and push to git? (if not already done)
> 2. Update `release_notes.json` with a new version entry? (if `BOT_VERSION` was bumped)"

---

## Step 6 — PI1 Promotion (after PI2 confirmed)

Only after project lead (stas) confirms PI2 tests pass:

```bat
rem Replace TARGET2PWD → HOSTPWD, OpenClawPI2 → OpenClawPI
pscp -pw "%HOSTPWD%" src\<changed-files> stas@OpenClawPI:/home/stas/.picoclaw/
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S systemctl restart picoclaw-telegram && sleep 3 && journalctl -u picoclaw-telegram -n 12 --no-pager"
```

---

## Quick Diagnostics

```bat
rem Check service status
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "systemctl status picoclaw-telegram picoclaw-web --no-pager"

rem Check current deployed version
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "grep BOT_VERSION /home/stas/.picoclaw/bot_config.py"

rem Tail live log
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "journalctl -u picoclaw-telegram -f --no-pager"

rem Check all picoclaw services
plink -pw "%TARGET2PWD%" -batch stas@OpenClawPI2 "systemctl list-units picoclaw-* --no-pager"
```

---

## File → Service Mapping

| Changed file(s) | Services to restart |
|---|---|
| `bot_*.py`, `telegram_menu_bot.py` | `picoclaw-telegram` |
| `bot_web.py`, `templates/`, `static/` | `picoclaw-telegram picoclaw-web` |
| `voice_assistant.py` | `picoclaw-voice` |
| `src/services/*.service` | the changed service (+ `daemon-reload`) |
| `strings.json`, `release_notes.json` | `picoclaw-telegram` |

## VPS Deployment (separate concern)

`src/setup/deploy_vps.sh` is **not** part of the bot deployment flow.
It is used exclusively to deploy the **nginx reverse proxy** on the dedicated VPS server (`agents.sintaris.net`) so the Pi web UI is reachable over the internet via HTTPS. Run it only when the VPS config or nginx setup changes:

```bash
bash src/setup/deploy_vps.sh
```

This reads all config from `.env` and has no effect on the Pi bot services.

---

## References

- Full deployment workflow: [copilot-instructions.md](../../.github/copilot-instructions.md)
- Architecture & services: [doc/architecture.md](../../doc/architecture.md)
- Voice regression tests: [copilot-instructions.md — Voice regression section](../../.github/copilot-instructions.md)
- Safe update protocol: [copilot-instructions.md — Safe Update section](../../.github/copilot-instructions.md)
- Dev patterns: [doc/dev-patterns.md](../../doc/dev-patterns.md)
- Data migration tool: [tools/migrate_to_db.py](../../tools/migrate_to_db.py) — optional, run only when schema changes
