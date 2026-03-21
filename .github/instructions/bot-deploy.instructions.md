---
applyTo: "src/telegram_menu_bot.py,src/bot_*.py,src/strings.json,src/release_notes.json,src/services/*.service"
---

# Bot Deploy — Skill

Use this skill whenever deploying bot changes to the Pi.

## ⚠️ Data Safety — Mandatory Rule

> **DATA SHALL ALWAYS BE BACKED UP AND MIGRATED ON EVERY SOFTWARE CHANGE ON TARGETS.**
>
> - **Before any deploy**: verify `~/.taris/calendar/`, `~/.taris/notes/`, `~/.taris/mail_creds/`, `~/.taris/taris.db`, `~/.taris/bot.env` are present and non-empty on the target.
> - **If changing data paths or service names**: migrate ALL user data from the old path to the new path BEFORE deploying new code.
> - **If in doubt**: run Step 0.5 (backup) + Step 0.6 (data directory migration check) from the `/taris-deploy-to-target` skill first.
> - **Data loss is never acceptable. Silent data loss is a critical bug.**

## Deployment Pipeline — MANDATORY ORDER

> **RULE: Engineering before Production — always.**
>
> 1. Deploy and test on **PI2** (`OpenClawPI2`) — engineering target.
> 2. **Only after** all tests pass and the change is committed and pushed to git:
> 3. Deploy to **PI1** (`OpenClawPI`) — production target.
>
> **NEVER** deploy directly to PI1 without prior validation on PI2.

## 1 — Version Bump

`BOT_VERSION = "YYYY.M.D"` in `src/core/bot_config.py` + prepend entry in `src/release_notes.json`. Never use `\_` in JSON. See `doc/quick-ref.md` §Version Bump.

## 2 — Deploy Files

Full deploy commands with package paths → `/taris-deploy-to-target` skill.

```bat
rem Incremental — only changed files (use package subdirectory)
rem core/:     pscp -pw "%HOSTPWD%" src\core\<file>.py stas@<HOST>:/home/stas/.taris/core/
rem telegram/: pscp -pw "%HOSTPWD%" src\telegram\<file>.py stas@<HOST>:/home/stas/.taris/telegram/
rem features/: pscp -pw "%HOSTPWD%" src\features\<file>.py stas@<HOST>:/home/stas/.taris/features/
pscp -pw "%HOSTPWD%" src\release_notes.json src\strings.json stas@<HOST>:/home/stas/.taris/
```

## 3 — Restart and Verify

```bat
plink -pw "%HOSTPWD%" -batch stas@<HOST> "echo %HOSTPWD% | sudo -S systemctl restart taris-telegram && sleep 3 && journalctl -u taris-telegram -n 12 --no-pager"
```

Expected: `[INFO] Version : 2026.X.Y` + `[INFO] Polling Telegram…`

## 4 — Service File Changes

```bat
pscp -pw "%HOSTPWD%" src\services\<name>.service stas@<HOST>:/tmp/<name>.service
plink -pw "%HOSTPWD%" -batch stas@<HOST> "echo %HOSTPWD% | sudo -S cp /tmp/<name>.service /etc/systemd/system/<name>.service && sudo systemctl daemon-reload && sudo systemctl restart <name>"
```

## 5 — UI Changes (both Telegram + Web UI)

```bat
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py src\strings.json stas@<HOST>:/home/stas/.taris/
pscp -pw "%HOSTPWD%" src\telegram\bot_access.py stas@<HOST>:/home/stas/.taris/telegram/
pscp -pw "%HOSTPWD%" src\bot_web.py stas@<HOST>:/home/stas/.taris/
pscp -pw "%HOSTPWD%" src\web\templates\*.html stas@<HOST>:/home/stas/.taris/web/templates/
pscp -pw "%HOSTPWD%" src\web\static\style.css src\web\static\manifest.json stas@<HOST>:/home/stas/.taris/web/static/
plink -pw "%HOSTPWD%" -batch stas@<HOST> "echo %HOSTPWD% | sudo -S systemctl restart taris-telegram taris-web"
```

## Runtime Files (auto-created on Pi — do NOT commit)

| File | Purpose |
|---|---|
| `~/.taris/bot.env` | `BOT_TOKEN` + `ALLOWED_USERS` (set manually) |
| `~/.taris/voice_opts.json` | Per-user voice flags |
| `~/.taris/taris.db` | SQLite data store |
