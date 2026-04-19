---
mode: agent
description: Deploy the OpenClaw variant of taris to TariStation2 (local engineering), TariStation1/SintAItion (home production), or VPS-Supertaris (agents.sintaris.net, internet-facing production). TariStation2 is always deployed first; TariStation1 and VPS-Supertaris each require separate explicit owner confirmation. VPS-Supertaris is the highest-risk target — shared public internet VPS with N8N, PostgreSQL, Nginx, and other bots.
---

# Deploy OpenClaw Target (`/taris-deploy-openclaw-target`)

**Usage**: `/taris-deploy-openclaw-target [target]`

| Parameter | Values | Default |
|---|---|---|
| `target` | `ts2` \| `ts1` \| `vps` \| `all` | `ts2` (TariStation2 only) |

| Target ID | Host | Notes |
|---|---|---|
| `ts2` | TariStation2 / IniCoS-1 | Engineering — local LAN, any branch |
| `ts1` | TariStation1 / SintAItion | Home production — master branch, confirm required |
| `vps` | VPS-Supertaris / agents.sintaris.net | Internet production — 🔴 highest risk, separate confirm + pre-VPS checklist |

---

## 🚨 TariStation1 and VPS-Supertaris are Shared Production Hosts

**TariStation1 (SintAItion):** hosts Ollama LLM and accesses shared PostgreSQL via tunnel.  
**VPS-Supertaris (`agents.sintaris.net`):** public internet VPS hosting PostgreSQL, N8N, Nginx, and other bots. Any system operation here can affect ALL co-hosted services. Brief taris restarts are visible publicly.

**Every operation on TariStation1 or VPS-Supertaris** — including service restarts, service file changes, package installs, database migrations, and system config changes — requires **explicit confirmation from the user (stas) before execution.**  
Do NOT bundle multiple operations into a single confirmation; ask separately for each distinct action type.  
For VPS-Supertaris: present the mandatory pre-VPS checklist (from SKILL.md) before ANY operation.

---

## Read context first

Before executing any deploy step, read:
1. `.env` in workspace root — `OPENCLAW1_HOST`, `OPENCLAW1_USER`, `OPENCLAW1PWD`, `VPS_HOST`, `VPS_USER`, `VPS_PWD`
2. `.github/skills/taris-deploy-openclaw-target/SKILL.md` — full procedure reference (VPS safety rules + checklists)
3. `doc/quick-ref.md` — module map and deploy pipeline rules

**TariStation2-first rule**: ALWAYS deploy to TariStation2 (local) first and verify before deploying to TariStation1 or VPS-Supertaris.

**Branch rule**: TariStation1 and VPS-Supertaris only receive code from the **`master` branch**. Confirm `git branch --show-current` shows `master` before any TS1/VPS operation. If on a feature branch, abort and inform the user.

**Confirmation rule**: After TariStation2 is verified, **STOP and explicitly ask the user** before proceeding to TariStation1. After TariStation1 (or TS2 if skipping TS1), ask **separately** for VPS-Supertaris. Never auto-deploy to TariStation1 or VPS-Supertaris.

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

## Step 5 — Confirmation gate before TariStation1 / VPS-Supertaris

After TariStation2 passes all checks, **STOP and present this checklist to the user**:

> "✅ TariStation2 deployment verified (v2026.X.Y, tests pass).
>
> Shall I also:
> 1. Commit and push to git?
> 2. **Deploy to TariStation1 (SintAItion)?** *(shared home production — requires confirmation)*
> 3. **Deploy to VPS-Supertaris (agents.sintaris.net)?** *(🔴 shared public internet VPS — requires separate confirmation + pre-VPS checklist)*"

**Do NOT execute any command on TariStation1 until the user explicitly answers "yes" to option 2.**  
**Do NOT execute any command on VPS-Supertaris until the user explicitly answers "yes" to option 3 — then present the full pre-VPS checklist from SKILL.md before each individual operation.**

If the deploy includes service file changes, migrations, or package installs on either TS1 or VPS — ask for a **separate confirmation** for each after the user says yes to code deploy.

Also verify branch before TariStation1 or VPS:

```bash
git branch --show-current
# Must print: master
# If it prints anything else — inform the user and abort TS1/VPS deploy
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

## Step 9 — VPS-Supertaris Deploy (only after separate user confirmation)

> 🔴 Run only after explicit user confirmation for VPS-Supertaris. Present the pre-VPS checklist from SKILL.md first.

**Backup VPS before deploying:**

```bash
source /home/stas/projects/sintaris-pl/.env
TS=$(date +%Y%m%d_%H%M%S)
VER=$(sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST \
  "grep BOT_VERSION ~/.taris/core/bot_config.py | head -1 | cut -d'\"' -f2")
BNAME="taris_backup_VPS_v${VER}_${TS}"
sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST \
  "tar czf /tmp/${BNAME}.tar.gz -C ~/.taris \
   --exclude='vosk-model-*' --exclude='*.onnx' --exclude='ggml-*.bin' --exclude='*/__pycache__' \
   . 2>/dev/null && echo BACKUP_OK"
mkdir -p /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no \
  $VPS_USER@$VPS_HOST:/tmp/${BNAME}.tar.gz \
  /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}/
echo "Local backup: backup/snapshots/${BNAME}/"
```

**Deploy to VPS** (see Step 2c in SKILL.md for full commands).

**[SEPARATE CONFIRMATION] Restart on VPS:**

```bash
source /home/stas/projects/sintaris-pl/.env
sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST \
  "systemctl --user restart taris-telegram taris-web && sleep 4 && \
   journalctl --user -u taris-telegram -n 15 --no-pager"
```

**Verify public URL:**
```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://agents.sintaris.net/supertaris/
```

---

## Step 10 — Post-deploy report

```
✅ OpenClaw Deployment Complete
   TariStation2 (local)                :  Version 2026.X.Y — telegram ✅  web ✅
   TariStation1 (SintAItion)           :  Version 2026.X.Y — telegram ✅  web ✅
   VPS-Supertaris (agents.sintaris.net):  Version 2026.X.Y — telegram ✅  web ✅  public ✅
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
- **VPS-Supertaris = agents.sintaris.net** — public internet VPS; taris runs at `/supertaris/` behind Nginx. `ROOT_PATH=/supertaris` must be set in `~/.taris/bot.env` on the VPS.
- **No `sudo` needed** for taris services — all targets use `systemctl --user` (user-level systemd). Nginx/system changes DO require `sudo` and therefore explicit confirmation.
- **Models stay on device** — Piper `.onnx` and Whisper `.bin` models are NOT deployed. Run setup scripts only when model files need updating.
- **`bot_ui.py` is critical** — always sync `src/ui/bot_ui.py` together with any file that imports `UserContext`. Silent mismatch causes `TypeError` on startup.
- **`.env` vars**: `OPENCLAW1_HOST`, `OPENCLAW1_USER`, `OPENCLAW1PWD` for TS1; `VPS_HOST`, `VPS_USER`, `VPS_PWD` for VPS-Supertaris.
