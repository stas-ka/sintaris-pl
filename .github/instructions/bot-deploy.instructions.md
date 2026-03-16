---
applyTo: "src/telegram_menu_bot.py,src/bot_*.py,src/strings.json,src/release_notes.json,src/services/*.service"
---

# Bot Deploy — Skill

Use this skill whenever deploying bot changes to the Pi.

## Deployment Pipeline — MANDATORY ORDER

> **RULE: Engineering before Production — always.**
>
> 1. Deploy and test on **PI2** (`OpenClawPI2`) — engineering target.
> 2. **Only after** all tests pass and the change is committed and pushed to git:
> 3. Deploy to **PI1** (`OpenClawPI`) — production target.
>
> **NEVER** deploy directly to PI1 without prior validation on PI2.

## 1 — Version Bump and Release Notes

Every user-visible change needs a version bump.

```python
# src/bot_config.py  (canonical location — telegram_menu_bot.py imports it from there)
BOT_VERSION = "2026.3.X"   # YYYY.M.D — no zero-padding
```

```json
// src/release_notes.json — prepend at top; never append
[
  {
    "version": "2026.3.X",
    "date":    "2026-03-XX",
    "title":   "Short feature name",
    "notes":   "- Item 1\n- Item 2"
  }
]
```

- Never use `\_` in JSON — invalid escape. Validate: `python3 -c "import json,sys; json.load(sys.stdin)" < src/release_notes.json`

## 2 — Deploy Files

```bat
rem Incremental — only changed files
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\release_notes.json src\strings.json stas@OpenClawPI:/home/stas/.picoclaw/

rem Full deploy (first-time or major refactor)
pscp -pw "%HOSTPWD%" src\bot_config.py src\bot_state.py src\bot_instance.py stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\bot_access.py src\bot_users.py src\bot_voice.py    stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\bot_admin.py  src\bot_handlers.py                  stas@OpenClawPI:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py src\release_notes.json src\strings.json stas@OpenClawPI:/home/stas/.picoclaw/
```

## 3 — Restart and Verify

```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S systemctl restart picoclaw-telegram && sleep 3 && journalctl -u picoclaw-telegram -n 12 --no-pager"
```

Expected log: `[INFO] Version : 2026.X.Y` and `[INFO] Polling Telegram…`

## 4 — Service File Changes

When a `.service` file in `src/services/` changes, deploy it in the same operation:

```bat
pscp -pw "%HOSTPWD%" src\services\<name>.service stas@OpenClawPI:/tmp/<name>.service
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S cp /tmp/<name>.service /etc/systemd/system/<name>.service && sudo systemctl daemon-reload && sudo systemctl restart <name>"
```

## 5 — UI Changes (Telegram + Web UI)

Any UI change must be deployed to both variants:

```bat
rem Telegram
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py src\bot_access.py src\strings.json stas@<HOST>:/home/stas/.picoclaw/

rem Web UI
pscp -pw "%HOSTPWD%" src\bot_web.py stas@<HOST>:/home/stas/.picoclaw/
pscp -pw "%HOSTPWD%" src\templates\*.html stas@<HOST>:/home/stas/.picoclaw/templates/
pscp -pw "%HOSTPWD%" src\static\style.css stas@<HOST>:/home/stas/.picoclaw/static/

rem Restart both
plink -pw "%HOSTPWD%" -batch stas@<HOST> "echo %HOSTPWD% | sudo -S systemctl restart picoclaw-telegram picoclaw-web"
```

## picoclaw Binary (sipeed/picoclaw)

The Go AI agent binary at `/usr/bin/picoclaw` is a separate project from the bot.

```bat
rem Upgrade
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "wget -q https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_aarch64.deb -O /tmp/picoclaw_aarch64.deb && echo %HOSTPWD% | sudo -S dpkg -i /tmp/picoclaw_aarch64.deb"

rem One-shot chat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "picoclaw agent -m \"Hello!\""
```

Config: `~/.picoclaw/config.json` — requires at least one `model_list` entry with an OpenRouter API key.

## Gmail Digest Agent

Daily digest runs at 19:00 Pi local time via cron (`0 19 * * *`).

```bat
rem Run manually
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.picoclaw/gmail_digest.py"

rem Update script
pscp -pw "%HOSTPWD%" src\gmail_digest.py stas@OpenClawPI:/home/stas/.picoclaw/gmail_digest.py
```

## Runtime Files (auto-created on Pi — do NOT commit)

| File | Purpose |
|---|---|
| `~/.picoclaw/voice_opts.json` | Per-user voice flags |
| `~/.picoclaw/last_notified_version.txt` | Tracks notified `BOT_VERSION` |
| `~/.picoclaw/bot.env` | `BOT_TOKEN` + `ALLOWED_USER` (set manually) |
| `~/.picoclaw/pico.db` | SQLite data store |
