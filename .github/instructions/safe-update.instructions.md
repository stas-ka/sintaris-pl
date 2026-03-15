---
applyTo: "**"
---

# Safe Update Protocol — Skill

Use this protocol for any update that changes data formats, adds/removes modules, or modifies the SQLite schema. For pure code hotfixes with no schema change, the [bot-deploy](bot-deploy.instructions.md) workflow is sufficient.

## Pre-Update Checklist

1. All local changes committed to git
2. Target host reachable: `plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo ok"`
3. Backup location exists: `backup/snapshots/`

## Step 1 — Create Backup on Pi

```bat
for /f %%i in ('powershell -c "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
for /f %%v in ('plink -pw "%HOSTPWD%" -batch stas@%TARGETHOST% "grep BOT_VERSION /home/stas/.picoclaw/bot_config.py ^| head -1 ^| cut -d'\"' -f2"') do set VER=%%v
set BNAME=picoclaw_backup_%TARGETHOST%_v%VER%_%TS%

plink -pw "%HOSTPWD%" -batch stas@%TARGETHOST% ^
  "tar czf /tmp/%BNAME%.tar.gz -C /home/stas/.picoclaw ^
    --exclude=vosk-model-small-ru --exclude=vosk-model-small-de ^
    --exclude='*.onnx' --exclude='ggml-*.bin' ^
    . 2>/dev/null && echo BACKUP_OK"
```

Expected: `BACKUP_OK`. If not — **stop, do not proceed**.

## Step 2 — Verify Backup

```bat
plink -pw "%HOSTPWD%" -batch stas@%TARGETHOST% ^
  "tar tzf /tmp/%BNAME%.tar.gz | grep -E '\.(json|db|txt|env)$' | head -30"
```

Confirm you see: `bot.env`, `config.json`, `pico.db`, `voice_opts.json`.

## Step 3 — Download Backup Locally

```bat
if not exist backup\snapshots\%BNAME% mkdir backup\snapshots\%BNAME%
pscp -pw "%HOSTPWD%" stas@%TARGETHOST%:/tmp/%BNAME%.tar.gz backup\snapshots\%BNAME%\
```

**Do not proceed until the backup is on local disk.**

## Step 4 — Stop Services

```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI ^
  "echo %HOSTPWD% | sudo -S systemctl stop picoclaw-telegram picoclaw-web picoclaw-voice 2>/dev/null; echo STOPPED"
```

## Step 5 — Deploy New Code

```bat
pscp -pw "%HOSTPWD%" src\bot_config.py src\bot_state.py src\bot_instance.py stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\bot_access.py src\bot_users.py src\bot_voice.py    stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\bot_admin.py  src\bot_handlers.py                  stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py src\strings.json src\release_notes.json stas@OpenClawPI:/home/stas/.picoclaw/
```

## Step 6 — Run Migration (schema changes only)

```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI ^
  "python3 /home/stas/.picoclaw/migrate_to_db.py --source=/home/stas/.picoclaw && echo MIGRATION_OK"
```

Expected: `MIGRATION_OK`. If not — **rollback immediately** (Step 9).

## Step 7 — Start Services

```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI ^
  "echo %HOSTPWD% | sudo -S systemctl start picoclaw-telegram picoclaw-web 2>/dev/null && sleep 3 && journalctl -u picoclaw-telegram -n 12 --no-pager"
```

Expected: `[INFO] Version : 2026.X.Y`, `[INFO] Polling Telegram…`

## Step 8 — Run Regression Tests

```bat
rem Voice regression
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.picoclaw/tests/test_voice_regression.py"

rem Web UI
python -m pytest src/tests/ui/test_ui.py -v --base-url https://openclawpi:8080 --browser chromium
```

## Step 9 — Rollback (if tests fail)

```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S systemctl stop picoclaw-telegram picoclaw-web 2>/dev/null"
pscp -pw "%HOSTPWD%" backup\snapshots\%BNAME%\%BNAME%.tar.gz stas@OpenClawPI:/tmp/
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "tar xzf /tmp/%BNAME%.tar.gz -C /home/stas/.picoclaw --overwrite && echo RESTORE_OK"
```

Then redeploy the previous code version from git and restart services.

## Rules

- **NEVER** deploy without a local backup downloaded first.
- **NEVER** run migration before stopping services (race condition).
- **NEVER** skip regression tests after a schema change.
- Keep the last 3 backup archives locally; delete older ones after successful tests.
- After a successful update: `git tag deploy/YYYY.M.D`
