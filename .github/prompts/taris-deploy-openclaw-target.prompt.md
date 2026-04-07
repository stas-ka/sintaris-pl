---
mode: agent
description: Deploy the OpenClaw variant of taris to TariStation2 (local engineering) and TariStation1/SintAItion (production). TariStation2 is always deployed first; TariStation1 requires explicit owner confirmation.
---

# Deploy OpenClaw Target (`/taris-deploy-openclaw-target`)

**Usage**: `/taris-deploy-openclaw-target [target]`

| Parameter | Values | Default |
|---|---|---|
| `target` | `ts2` \| `ts1` \| `both` | `ts2` (TariStation2 only) |

---

## Read context first

Before executing any deploy step, read:
1. `.env` in workspace root — `OPENCLAW1_HOST`, `OPENCLAW1_USER`, `OPENCLAW1PWD`
2. `.github/skills/taris-deploy-openclaw-target/SKILL.md` — full procedure reference
3. `doc/quick-ref.md` — module map and deploy pipeline rules

**TariStation2-first rule**: ALWAYS deploy to TariStation2 (local) first and verify before deploying to TariStation1 (SintAItion).

**TariStation1 branch rule**: TariStation1 (`SintAItion`) only receives code from the **`master` branch**. Before deploying to TariStation1, confirm `git branch --show-current` shows `master`. If on a feature branch, abort TariStation1 deploy and inform the user.

**TariStation1 confirmation rule**: After TariStation2 is verified, **STOP and explicitly ask the user** before proceeding to TariStation1. Never auto-deploy to TariStation1.

---

## Step 0 — Pre-flight check

```bash
# Confirm current local version
grep BOT_VERSION /home/stas/projects/sintaris-pl/src/core/bot_config.py

# Check git status and branch
cd /home/stas/projects/sintaris-pl && git status --short && git branch --show-current
git log --oneline -3
```

Report any uncommitted changes. Warn the user before proceeding if there are uncommitted files.

---

## Step 1 — Backup (TariStation2, local)

```bash
TS=$(date +%Y%m%d_%H%M%S)
VER=$(grep BOT_VERSION ~/.taris/core/bot_config.py | head -1 | cut -d'"' -f2)
BNAME="taris_backup_TariStation2_v${VER}_${TS}"
tar czf /tmp/${BNAME}.tar.gz \
  -C /home/stas/.taris \
  --exclude='vosk-model-*' --exclude='*.onnx' --exclude='ggml-*.bin' --exclude='*/__pycache__' \
  . 2>/dev/null && echo "BACKUP_OK"
mkdir -p /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}
cp /tmp/${BNAME}.tar.gz /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}/
```

Expected: `BACKUP_OK` and file present in `backup/snapshots/`. **Do not proceed without it.**

---

## Step 2 — Sync source to TariStation2 (local)

```bash
PROJECT=/home/stas/projects/sintaris-pl

# Python packages
cp $PROJECT/src/core/*.py       ~/.taris/core/
cp $PROJECT/src/telegram/*.py   ~/.taris/telegram/
cp $PROJECT/src/features/*.py   ~/.taris/features/
cp $PROJECT/src/ui/*.py         ~/.taris/ui/
cp $PROJECT/src/security/*.py   ~/.taris/security/

# Entry points
cp $PROJECT/src/bot_web.py $PROJECT/src/telegram_menu_bot.py \
   $PROJECT/src/voice_assistant.py $PROJECT/src/gmail_digest.py ~/.taris/

# Data and screens
cp $PROJECT/src/strings.json $PROJECT/src/release_notes.json ~/.taris/
cp $PROJECT/src/screens/*.yaml $PROJECT/src/screens/screen.schema.json ~/.taris/screens/ 2>/dev/null

# Web assets
cp -r $PROJECT/src/web/templates/. ~/.taris/web/templates/
cp -r $PROJECT/src/web/static/.    ~/.taris/web/static/
```

**Verify sync — all lines must say OK:**

```bash
PROJECT=/home/stas/projects/sintaris-pl
for f in src/bot_web.py src/core/bot_config.py src/ui/bot_ui.py src/ui/screen_loader.py; do
  diff "$PROJECT/$f" ~/.taris/"${f#src/}" > /dev/null 2>&1 \
    && echo "OK $f" || echo "DIFF $f — NOT SYNCED"
done
diff -rq $PROJECT/src/web/templates ~/.taris/web/templates 2>/dev/null && echo "OK templates" || echo "DIFF templates"
diff -rq $PROJECT/src/screens ~/.taris/screens 2>/dev/null && echo "OK screens" || echo "DIFF screens"
```

Fix any `DIFF` lines before restarting.

---

## Step 3 — Restart and verify (TariStation2)

```bash
systemctl --user restart taris-telegram taris-web && sleep 4
journalctl --user -u taris-telegram -n 15 --no-pager
```

**Pass criteria** (all must appear in journal):
- `[INFO] Version      : 2026.X.Y`
- `[INFO] DB init OK`
- `[INFO] Polling Telegram…`

If any criterion is missing — **STOP. Do not proceed to TariStation1.** Report the error and check:

```bash
journalctl --user -u taris-telegram -n 50 --no-pager | grep -i "error\|exception\|traceback"
```

---

## Step 4 — Run regression tests (TariStation2)

```bash
DEVICE_VARIANT=openclaw PYTHONPATH=/home/stas/projects/sintaris-pl/src \
  python3 /home/stas/projects/sintaris-pl/src/tests/test_voice_regression.py
```

T29/T30 must PASS. T27/T28 SKIP is OK. Any other FAIL → fix before proceeding.

Screen DSL tests (if screens changed):

```bash
DEVICE_VARIANT=openclaw PYTHONPATH=/home/stas/projects/sintaris-pl/src \
  python3 -m pytest /home/stas/projects/sintaris-pl/src/tests/screen_loader/ -v --tb=short
```

---

## Step 5 — Confirmation gate before TariStation1

After TariStation2 passes all checks, **STOP and ask the user**:

> "✅ TariStation2 deployment verified (v2026.X.Y, tests pass).  
> 
> Shall I also:  
> 1. Commit and push to git?  
> 2. Deploy to **TariStation1 (SintAItion)**? *(requires explicit confirmation)*"

**Do NOT proceed to TariStation1 without the user's explicit approval.**

Also verify branch before TariStation1:

```bash
git branch --show-current
# Must print: master
# If it prints anything else — inform the user and abort TariStation1 deploy
```

---

## Step 6 — Backup TariStation1 (before deploying)

```bash
source /home/stas/projects/sintaris-pl/.env
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST
TS=$(date +%Y%m%d_%H%M%S)
VER=$(sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "grep BOT_VERSION ~/.taris/core/bot_config.py | head -1 | cut -d'\"' -f2")
BNAME="taris_backup_TariStation1_v${VER}_${TS}"

sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "tar czf /tmp/${BNAME}.tar.gz -C /home/stas/.taris \
   --exclude='vosk-model-*' --exclude='*.onnx' --exclude='ggml-*.bin' --exclude='*/__pycache__' \
   . 2>/dev/null && echo BACKUP_OK"

mkdir -p /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  $U@$H:/tmp/${BNAME}.tar.gz \
  /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}/
echo "Local backup ready: backup/snapshots/${BNAME}/"
```

**Do not proceed until backup is confirmed on local disk.**

---

## Step 7 — Sync source to TariStation1 (SintAItion)

```bash
source /home/stas/projects/sintaris-pl/.env
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST; PROJECT=/home/stas/projects/sintaris-pl

# Create dirs (idempotent)
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "mkdir -p ~/.taris/core ~/.taris/telegram ~/.taris/features ~/.taris/ui ~/.taris/security ~/.taris/screens ~/.taris/web/templates ~/.taris/web/static && \
   touch ~/.taris/core/__init__.py ~/.taris/telegram/__init__.py ~/.taris/features/__init__.py ~/.taris/ui/__init__.py ~/.taris/security/__init__.py"

# Deploy packages
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/core/*.py       $U@$H:~/.taris/core/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/telegram/*.py   $U@$H:~/.taris/telegram/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/features/*.py   $U@$H:~/.taris/features/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/ui/*.py         $U@$H:~/.taris/ui/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/security/*.py   $U@$H:~/.taris/security/

# Entry points + data + screens
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/bot_web.py $PROJECT/src/telegram_menu_bot.py \
  $PROJECT/src/voice_assistant.py $PROJECT/src/gmail_digest.py \
  $PROJECT/src/strings.json $PROJECT/src/release_notes.json \
  $U@$H:~/.taris/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/screens/*.yaml $PROJECT/src/screens/screen.schema.json $U@$H:~/.taris/screens/

# Web assets
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no -r $PROJECT/src/web/templates/ $U@$H:~/.taris/web/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no -r $PROJECT/src/web/static/    $U@$H:~/.taris/web/
```

---

## Step 8 — Restart and verify (TariStation1)

```bash
source /home/stas/projects/sintaris-pl/.env
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "systemctl --user restart taris-telegram taris-web && sleep 4 && \
   journalctl --user -u taris-telegram -n 15 --no-pager"
```

Same pass criteria as Step 3. If startup fails, restore from the backup made in Step 6.

---

## Step 9 — Post-deploy report

```
✅ OpenClaw Deployment Complete
   TariStation2 (local)         :  Version 2026.X.Y — telegram ✅  web ✅
   TariStation1 (SintAItion)    :  Version 2026.X.Y — telegram ✅  web ✅
```

Then ask:
> "Deployment verified ✅. Shall I:  
> 1. Commit and push to git? (if not already done)  
> 2. Update `release_notes.json` with a new version entry?"

---

## Notes

- **Never skip TariStation2** — it is the engineering target. All changes must be validated there first.
- **TariStation2 = local machine** — uses `cp` and `systemctl --user`, no SSH.
- **TariStation1 = SintAItion** — uses `sshpass + scp/ssh`, `systemctl --user` on the remote host.
- **No `sudo` needed** — both targets use `systemctl --user` (user-level systemd).
- **Models stay on device** — Piper `.onnx` and Whisper `.bin` models are NOT deployed. Run setup scripts only when model files need updating.
- **`bot_ui.py` is critical** — always sync `src/ui/bot_ui.py` together with any file that imports `UserContext`. Silent mismatch causes `TypeError` on startup.
- **`.env` vars**: `OPENCLAW1_HOST`, `OPENCLAW1_USER`, `OPENCLAW1PWD` must be set in project `.env` before TariStation1 operations.
