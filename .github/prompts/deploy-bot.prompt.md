---
mode: agent
description: Deploy the Telegram bot (and companion files) to the Raspberry Pi and verify the service started correctly.
---

# Deploy Bot to Pi

Follow the standard Telegram Bot Deployment Workflow from `.github/copilot-instructions.md`:

## Step 1 — Check which files changed
Run `git status` and `git diff --name-only HEAD` to identify which source files were modified since the last deploy. Only copy files that actually changed.

## Step 2 — Copy changed files to the Pi
Use `pscp` for each changed file (adjust the list as needed):

```bat
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\strings.json         stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\release_notes.json   stas@OpenClawPI:/home/stas/.picoclaw/
```

Also copy any changed `src\bot_*.py` modules and `src\setup\*.sh` scripts.

## Step 3 — Restart the service
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S systemctl restart picoclaw-telegram"
```

## Step 4 — Verify
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "sleep 4 && journalctl -u picoclaw-telegram -n 20 --no-pager"
```

Look for:
- `[INFO] Version      : YYYY.M.D`
- `[INFO] Polling Telegram…`

If those lines are present → deployment is verified ✅.

## Step 5 — Post-deploy prompt (mandatory)
After confirming the journal shows the correct version, **always ask the user**:

> "Deployment verified ✅. Shall I also:
> 1. Commit and push to git? (if not already done)
> 2. Update `release_notes.json` with a new version entry? (if `BOT_VERSION` was bumped)"
