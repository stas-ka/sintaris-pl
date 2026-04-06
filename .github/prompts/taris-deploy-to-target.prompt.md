---
mode: agent
description: Deploy taris software to a Raspberry Pi target (PI2 first, then PI1).
---

# Deploy to Target (`/taris-deploy-to-target`)

**Usage**: `/taris-deploy-to-target [host]`

| Parameter | Values | Default |
|---|---|---|
| `host` | `OpenClawPI` \| `OpenClawPI2` \| `both` | `both` (PI2 first, then PI1) |

---

## Read context first

Before executing any deploy step, read:
1. `.env` in workspace root — `HOSTPWD`, `HOSTPWD2`
2. `doc/quick-ref.md` — deploy pipeline rules
3. `.github/instructions/bot-deploy.instructions.md` — authoritative pscp commands

**PI2-first rule**: ALWAYS deploy to PI2 (`OpenClawPI2`) first and verify before deploying to PI1 (`OpenClawPI`).

**PI1 branch rule**: PI1 (`OpenClawPI`) only receives code from the **`master` branch**. NEVER deploy a feature branch to PI1. Before deploying to PI1, confirm `git branch` shows `master`. If on a feature branch, abort PI1 deploy and inform the user to merge first.

---

## Step 0 — Pre-flight check

```bat
rem Confirm current local version
findstr /C:"BOT_VERSION" src\core\bot_config.py

rem Check git status
git status --short
git log --oneline -3
```

Report any uncommitted changes. If `git status` shows changes, warn the user before proceeding.

---

## Step 1 — Backup data on target (safety first)

Before any deploy, run a quick data backup:

```bat
plink -pw "PASS" -batch stas@HOST ^
  "TS=$(date +%%Y%%m%%d_%%H%%M%%S); ^
   tar czf /tmp/taris_predeploy_${TS}.tar.gz ^
   -C /home/stas ^
   .taris/taris.db .taris/*.json .taris/bot.env .taris/config.json ^
   --exclude='.taris/*/__pycache__' 2>/dev/null; ^
   ls -lh /tmp/taris_predeploy_${TS}.tar.gz"
```

---

## Step 2 — Deploy Python packages

Deploy all source packages to the target. Use exact paths from `bot-deploy.instructions.md`.

**Package directories** (copy entire directory contents):

```bat
rem core package
pscp -pw "PASS" -r src\core stas@HOST:/home/stas/.taris/

rem telegram package
pscp -pw "PASS" -r src\telegram stas@HOST:/home/stas/.taris/

rem features package
pscp -pw "PASS" -r src\features stas@HOST:/home/stas/.taris/

rem security package
pscp -pw "PASS" -r src\security stas@HOST:/home/stas/.taris/

rem ui package
pscp -pw "PASS" -r src\ui stas@HOST:/home/stas/.taris/

rem web templates + static
pscp -pw "PASS" -r src\web stas@HOST:/home/stas/.taris/
```

**Entry point files** (root-level, copy individually):

```bat
pscp -pw "PASS" src\telegram_menu_bot.py stas@HOST:/home/stas/.taris/
pscp -pw "PASS" src\bot_web.py stas@HOST:/home/stas/.taris/
pscp -pw "PASS" src\voice_assistant.py stas@HOST:/home/stas/.taris/
pscp -pw "PASS" src\gmail_digest.py stas@HOST:/home/stas/.taris/
```

**Data files**:

```bat
pscp -pw "PASS" src\strings.json stas@HOST:/home/stas/.taris/
pscp -pw "PASS" src\release_notes.json stas@HOST:/home/stas/.taris/
```

---

## Step 3 — Deploy setup scripts

```bat
pscp -pw "PASS" -r src\setup stas@HOST:/home/stas/.taris/
```

---

## Step 4 — Deploy systemd service files (if changed)

Only if any `.service` file changed since last deploy:

```bat
rem Copy to tmp then move to system dir with sudo
pscp -pw "PASS" src\services\taris-telegram.service stas@HOST:/tmp/
pscp -pw "PASS" src\services\taris-web.service stas@HOST:/tmp/
pscp -pw "PASS" src\services\taris-voice.service stas@HOST:/tmp/

plink -pw "PASS" -batch stas@HOST ^
  "echo PASS | sudo -S cp /tmp/taris-telegram.service /etc/systemd/system/ && ^
   echo PASS | sudo -S cp /tmp/taris-web.service /etc/systemd/system/ && ^
   echo PASS | sudo -S cp /tmp/taris-voice.service /etc/systemd/system/ && ^
   echo PASS | sudo -S systemctl daemon-reload && ^
   echo 'Service files deployed'"
```

---

## Step 5 — Restart services

```bat
plink -pw "PASS" -batch stas@HOST ^
  "echo PASS | sudo -S systemctl restart taris-telegram taris-web && ^
   sleep 4 && ^
   journalctl -u taris-telegram -n 15 --no-pager"
```

**Pass criteria** in journal:
- `[INFO] Version      : YYYY.M.D`
- `[INFO] DB init OK`
- `[INFO] Polling Telegram…`

If ANY of these lines is missing, STOP. Do not proceed to PI1. Report the error.

---

## Step 6 — Verify deployment

```bat
rem Check telegram bot service
plink -pw "PASS" -batch stas@HOST "systemctl is-active taris-telegram"

rem Check web service
plink -pw "PASS" -batch stas@HOST "systemctl is-active taris-web"

rem Confirm version on target
plink -pw "PASS" -batch stas@HOST "grep BOT_VERSION ~/.taris/core/bot_config.py"
```

---

## Step 7 — (If `host=both`) Repeat Steps 1–6 for PI1

> ⚠️ **Branch gate**: Before deploying to PI1, check the current git branch:
> ```bat
> git branch --show-current
> ```
> If the output is **not `master`**, **STOP**. Do NOT deploy to PI1. Inform the user:
> "PI1 only receives the master branch. Please merge to master first."

Only proceed to PI1 after:
1. PI2 verification passes all checks in Step 5.
2. Current branch is `master`.

PI1 credentials: `OpenClawPI` / password from `%HOSTPWD%`

---

## Step 8 — Post-deploy report

Report:
```
✅ Deployment complete
   PI2 (OpenClawPI2) :  Version YYYY.M.D — telegram ✅  web ✅
   PI1 (OpenClawPI)  :  Version YYYY.M.D — telegram ✅  web ✅
```

Then ask:
> "Deployment verified ✅. Shall I also: 1. Commit and push to git? 2. Update `release_notes.json`?"

---

## Troubleshooting

### Service fails to start

```bat
plink -pw "PASS" -batch stas@HOST "journalctl -u taris-telegram -n 30 --no-pager"
```

Common causes:
- Missing `__init__.py` in a package dir → check `core/__init__.py`, `telegram/__init__.py`, etc.
- Wrong import path — old flat imports vs new package imports
- Missing Python dependency → `sudo pip3 install <package>`

### Check imports on target

```bat
plink -pw "PASS" -batch stas@HOST ^
  "cd ~/.taris && python3 -c 'from core.bot_config import BOT_VERSION; print(BOT_VERSION)'"
```

---

## Notes

- **Never skip PI2** — PI2 is the engineering target. All changes must be validated there first.
- **Models are not deployed** — Piper `.onnx` and Whisper `.bin` models stay on device. Run `setup/setup_voice.sh` only when model files need updating.
- **If only data/strings changed** — you may skip package dirs and deploy only: `strings.json`, `release_notes.json`. But still restart the service.
