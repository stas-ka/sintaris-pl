---
name: taris-deploy-openclaw-target
description: >
  Deploy the OpenClaw variant of taris to local target TariStation2 (engineering)
  and remote target TariStation1 / SintAItion (production). Use when: deploying
  bot updates, pushing new features, deploying service files, restarting services,
  verifying deployment, running post-deploy tests, full module deploy, release
  version bump. TariStation2 is always deployed first; TariStation1 requires
  explicit user/owner confirmation after TariStation2 tests pass.
argument-hint: 'Which files changed? (e.g. all, bot_web.py, strings.json) and target (ts2/ts1/both)'
---

# Deploy to Target — OpenClaw Variant

## When to Use

- You changed one or more `src/*.py`, `src/core/`, `src/features/`, `src/telegram/`, `src/ui/`, `src/security/`
- You changed `src/strings.json` or `src/release_notes.json`
- You changed a `src/services/*.service` file
- You changed `src/web/templates/` or `src/web/static/`
- You changed `src/screens/*.yaml` (Screen DSL menus)
- You need to bump `BOT_VERSION` and push a release

## ⚠️ Target Priority Rule — MANDATORY

**ALWAYS deploy to TariStation2 first. TariStation1 (SintAItion) requires explicit confirmation from user/owner (stas) AFTER TariStation2 tests pass.**

| Target | Alias | Type | Transport | Branch rule |
|---|---|---|---|---|
| TariStation2 (engineering) | local machine | `cp` + `systemctl --user` | local filesystem | any branch |
| TariStation1 (SintAItion, production) | `SintAItion` | `scp` + `ssh` | remote SSH | `master` only |

> ⚠️ **TariStation1 branch rule**: TariStation1 (`SintAItion`) only receives deployments from the **`master` branch**.  
> Before deploying to TariStation1, run `git branch --show-current` and confirm it shows `master`.  
> If on a feature branch — **STOP**. Do not deploy to TariStation1. Inform the user to merge to `master` first.

> ⚠️ **TariStation1 confirmation rule**: After TariStation2 tests pass, **STOP and ask the user**:  
> `"TariStation2 deployment verified ✅. Shall I also deploy to TariStation1 (SintAItion)?"`  
> Deploy to TariStation1 **only after explicit "yes" from the user/owner**.

---

## Environment Variables (read from `.env` in project root)

| Variable | Purpose |
|---|---|
| `OPENCLAW1_HOST` | TariStation1 hostname or IP (e.g. `SintAItion`) |
| `OPENCLAW1_USER` | SSH user on TariStation1 (default: `stas`) |
| `OPENCLAW1PWD` | SSH password for TariStation1 |

TariStation2 is the local machine — no SSH credentials needed.

---

## 🚀 Quick Deploy via Script (Recommended)

All deployment operations use the unified `taris_deploy.sh` script:

```bash
# Deploy to TariStation2 (local engineering target) — ALWAYS first
bash src/setup/taris_deploy.sh --action deploy --target ts2

# Deploy to TariStation1 (remote production) — only after TS2 verified + user confirmed
bash src/setup/taris_deploy.sh --action deploy --target ts1

# Patch specific files only (fast iteration)
bash src/setup/taris_deploy.sh --action patch --target ts2 \
  --files "core/bot_llm.py,telegram_menu_bot.py"

# Backup only (before risky changes)
bash src/setup/taris_deploy.sh --action backup --target ts2 --backup-type all

# Run migration only (after schema change)
bash src/setup/taris_deploy.sh --action migrate --target ts2

# Verify service status + journal
bash src/setup/taris_deploy.sh --action verify --target ts2

# Restart services only
bash src/setup/taris_deploy.sh --action restart --target ts2

# Full install (first-time setup on new TariStation machine)
bash src/setup/taris_deploy.sh --action install --target ts2

# Options:
#   --yes            Non-interactive (CI mode)
#   --no-backup      Skip pre-deploy backup (rapid iteration only)
#   --no-tests       Skip smoke tests
#   --no-migrate     Skip migration step
#   --force-restart  Restart even if no change detected
#   --git-ref TAG    Checkout specific commit/tag before deploy
```

The script handles: backup → data check → deploy all packages → service files → migration → restart → journal verify → smoke tests → summary.

> **Legacy wrappers** (backward compat, delegate to taris_deploy.sh):
> - `bash src/setup/update_openclaw.sh --target ts2`
> - `bash src/setup/update_openclaw.sh --target ts1`

---

## Manual Step-by-Step (for partial deploys / debugging)

Use the steps below when you need fine-grained control (e.g. deploying only web templates, or debugging a specific package). For full deploys, prefer the script above.

---

## Step 0 — Pre-Deploy: Version Bump & Release Notes *(mandatory for user-facing changes)*

> ⚠️ Do this **BEFORE** deploying. If skipped, `BOT_VERSION` stays unchanged and no Telegram notification fires.

1. **Bump `BOT_VERSION`** in `src/core/bot_config.py` — format `YYYY.M.D`. Same-day second release: append `+1`.
2. **Prepend** a new entry to `src/release_notes.json`:
   ```json
   {
     "version": "2026.X.Y",
     "date":    "2026-0X-0Y",
     "title":   "Short description",
     "notes":   "- Bullet 1\n- Bullet 2"
   }
   ```
3. Validate JSON:
   ```bash
   python3 -c "import json,sys; json.load(sys.stdin)" < src/release_notes.json
   python3 -c "import json,sys; json.load(sys.stdin)" < src/strings.json
   ```
4. Always include `core/bot_config.py` and `release_notes.json` in the deploy file list.

> ✅ Skip only for infrastructure-only changes (service files, tests) with no user-visible effect.

---

## Step 0.5 — Pre-Deploy Backup *(mandatory before every deploy)*

### TariStation2 (local)

```bash
TS=$(date +%Y%m%d_%H%M%S)
VER=$(grep BOT_VERSION ~/.taris/core/bot_config.py | head -1 | cut -d'"' -f2)
BNAME="taris_backup_TariStation2_v${VER}_${TS}"

tar czf /tmp/${BNAME}.tar.gz \
  -C /home/stas/.taris \
  --exclude='vosk-model-*' --exclude='*.onnx' --exclude='ggml-*.bin' --exclude='*/__pycache__' \
  . 2>/dev/null && echo "BACKUP_OK: /tmp/${BNAME}.tar.gz"

# Download to project backup dir
mkdir -p /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}
cp /tmp/${BNAME}.tar.gz /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}/
ls -lh /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}/
```

Expected: `BACKUP_OK`. **Do not proceed without a local backup copy.**

### TariStation1 (SintAItion) — before Step 5b

```bash
source /home/stas/projects/sintaris-pl/.env
TS=$(date +%Y%m%d_%H%M%S)
VER=$(sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "grep BOT_VERSION ~/.taris/core/bot_config.py | head -1 | cut -d'\"' -f2")
BNAME="taris_backup_TariStation1_v${VER}_${TS}"

sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "tar czf /tmp/${BNAME}.tar.gz \
   -C /home/stas/.taris \
   --exclude='vosk-model-*' --exclude='*.onnx' --exclude='ggml-*.bin' --exclude='*/__pycache__' \
   . 2>/dev/null && echo BACKUP_OK"

mkdir -p /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST}:/tmp/${BNAME}.tar.gz \
  /home/stas/projects/sintaris-pl/backup/snapshots/${BNAME}/
echo "Local backup: backup/snapshots/${BNAME}/"
```

> Keep the last 3 backup archives; delete older ones after a successful deploy.

---

## Step 0.6 — Data Directory Check *(mandatory)*

> **DATA SHALL ALWAYS BE BACKED UP AND MIGRATED ON EVERY SOFTWARE CHANGE.**

### TariStation2 (local)

```bash
# Directories that must exist (docs/ = uploaded RAG knowledge base)
for d in calendar notes docs mail_creds error_protocols screens; do
  echo "=== $d ==="; ls -la ~/.taris/$d/ 2>/dev/null || echo MISSING
done
# Core files + DB row counts
ls -la ~/.taris/taris.db ~/.taris/bot.env ~/.taris/voice_opts.json 2>/dev/null || echo SOME_FILES_MISSING
python3 -c "import sqlite3; c=sqlite3.connect(os.path.expanduser('~/.taris/taris.db')); [print(t, c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ['users','calendar_events','notes_index','contacts','documents','chat_history','conversation_summaries']]" 2>/dev/null
```

> Note: `contacts` is stored in SQLite only (no `contacts/` directory). `docs/` holds uploaded RAG document files.

### TariStation1 (SintAItion)

```bash
source /home/stas/projects/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "for d in calendar notes docs mail_creds error_protocols screens; do echo \"=== \$d ===\"; ls -la ~/.taris/\$d/ 2>/dev/null || echo MISSING; done && ls -la ~/.taris/taris.db ~/.taris/bot.env 2>/dev/null || echo SOME_FILES_MISSING"
```

---

## Step 1 — Classify the Change

| Change type | Deploy path |
|---|---|
| Python module(s) only | [Incremental deploy](#incremental-deploy) |
| `strings.json` / `release_notes.json` | [Incremental deploy](#incremental-deploy) + version bump |
| `.service` file | [Service file deploy](#service-file-deploy) |
| Screen DSL YAML (`src/screens/*.yaml`) | [Screens deploy](#screens-deploy) |
| Web UI templates / static | [Web UI deploy](#web-ui-deploy) |
| Schema / data format change | [Safe update with backup](#safe-update-with-backup) |

---

## Step 2a — Incremental Deploy (TariStation2, local)

Replace `<package>` and `<file>` with changed paths:

```bash
# Sync changed files — adjust to which packages changed
PROJECT=/home/stas/projects/sintaris-pl

# Core package
cp $PROJECT/src/core/*.py ~/.taris/core/

# Telegram package
cp $PROJECT/src/telegram/*.py ~/.taris/telegram/

# Features package
cp $PROJECT/src/features/*.py ~/.taris/features/

# UI package (IMPORTANT: bot_ui.py defines UserContext — always sync with bot_handlers.py)
cp $PROJECT/src/ui/*.py ~/.taris/ui/

# Security package
cp $PROJECT/src/security/*.py ~/.taris/security/

# Entry points
cp $PROJECT/src/bot_web.py $PROJECT/src/telegram_menu_bot.py \
   $PROJECT/src/voice_assistant.py $PROJECT/src/gmail_digest.py ~/.taris/

# Data files
cp $PROJECT/src/strings.json $PROJECT/src/release_notes.json ~/.taris/
```

**Verify sync before restart** (prevents stale deployment bugs):

```bash
PROJECT=/home/stas/projects/sintaris-pl
for f in src/bot_web.py src/core/bot_config.py src/core/bot_llm.py src/ui/bot_ui.py; do
  diff "$PROJECT/$f" ~/.taris/"${f#src/}" > /dev/null 2>&1 && echo "OK $f" || echo "DIFF $f — NOT SYNCED"
done
diff -rq $PROJECT/src/web/templates ~/.taris/web/templates && echo "OK templates" || echo "DIFF templates"
diff -rq $PROJECT/src/screens ~/.taris/screens && echo "OK screens" || echo "DIFF screens"
```

All lines must show `OK`. Fix any `DIFF` lines before restarting.

**Restart (TariStation2):**

```bash
systemctl --user restart taris-telegram taris-web && sleep 4
journalctl --user -u taris-telegram -n 15 --no-pager
```

**Pass criteria:**
```
[INFO] Version      : 2026.X.Y
[INFO] DB init OK
[INFO] Polling Telegram…
```

If ANY pass criterion is missing — **STOP. Do not proceed to TariStation1.**

---

## Step 2b — Incremental Deploy (TariStation1 / SintAItion)

> ⚠️ **Only run this after TariStation2 is verified AND user/owner has confirmed.**  
> ⚠️ **Only run on the `master` branch** (`git branch --show-current` must show `master`).

```bash
source /home/stas/projects/sintaris-pl/.env
HOST=${OPENCLAW1_HOST}
USER=${OPENCLAW1_USER:-stas}
PROJECT=/home/stas/projects/sintaris-pl

# Create target package dirs (idempotent)
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $USER@$HOST \
  "mkdir -p ~/.taris/core ~/.taris/telegram ~/.taris/features ~/.taris/ui ~/.taris/security ~/.taris/screens ~/.taris/web/templates ~/.taris/web/static && \
   touch ~/.taris/core/__init__.py ~/.taris/telegram/__init__.py ~/.taris/features/__init__.py ~/.taris/ui/__init__.py ~/.taris/security/__init__.py"

# Deploy Python packages
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/core/*.py       $USER@$HOST:~/.taris/core/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/telegram/*.py   $USER@$HOST:~/.taris/telegram/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/features/*.py   $USER@$HOST:~/.taris/features/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/ui/*.py         $USER@$HOST:~/.taris/ui/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/security/*.py   $USER@$HOST:~/.taris/security/

# Entry points
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/bot_web.py $PROJECT/src/telegram_menu_bot.py \
  $PROJECT/src/voice_assistant.py $PROJECT/src/gmail_digest.py \
  $USER@$HOST:~/.taris/

# Data files
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/strings.json $PROJECT/src/release_notes.json $USER@$HOST:~/.taris/

# Screens (Screen DSL YAML)
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/screens/*.yaml $PROJECT/src/screens/*.json $USER@$HOST:~/.taris/screens/

# Restart
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $USER@$HOST \
  "systemctl --user restart taris-telegram taris-web && sleep 4 && journalctl --user -u taris-telegram -n 15 --no-pager"
```

---

## Screens Deploy

When only `src/screens/*.yaml` or `src/screens/screen.schema.json` changed:

**TariStation2:**
```bash
cp /home/stas/projects/sintaris-pl/src/screens/*.yaml ~/.taris/screens/
cp /home/stas/projects/sintaris-pl/src/screens/screen.schema.json ~/.taris/screens/
systemctl --user restart taris-telegram taris-web && sleep 4
journalctl --user -u taris-telegram -n 10 --no-pager
```

**TariStation1:**
```bash
source /home/stas/projects/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  /home/stas/projects/sintaris-pl/src/screens/*.yaml \
  /home/stas/projects/sintaris-pl/src/screens/screen.schema.json \
  ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST}:~/.taris/screens/
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no \
  ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "systemctl --user restart taris-telegram && sleep 3 && journalctl --user -u taris-telegram -n 10 --no-pager"
```

---

## Web UI Deploy

When `src/bot_web.py`, templates, or static assets changed:

**TariStation2:**
```bash
PROJECT=/home/stas/projects/sintaris-pl
cp $PROJECT/src/bot_web.py ~/.taris/
cp -r $PROJECT/src/web/templates/. ~/.taris/web/templates/
cp -r $PROJECT/src/web/static/. ~/.taris/web/static/
systemctl --user restart taris-telegram taris-web && sleep 4
journalctl --user -u taris-telegram -n 5 --no-pager
journalctl --user -u taris-web -n 5 --no-pager
```

**TariStation1:**
```bash
source /home/stas/projects/sintaris-pl/.env
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST; PROJECT=/home/stas/projects/sintaris-pl
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/bot_web.py $U@$H:~/.taris/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no -r $PROJECT/src/web/templates/ $U@$H:~/.taris/web/
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no -r $PROJECT/src/web/static/ $U@$H:~/.taris/web/
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "systemctl --user restart taris-telegram taris-web && sleep 4 && journalctl --user -u taris-web -n 10 --no-pager"
```

---

## Service File Deploy

Required after any change to `src/services/*.service`.

**TariStation2:**
```bash
SVCNAME=taris-telegram   # change as needed
cp /home/stas/projects/sintaris-pl/src/services/${SVCNAME}.service \
   /home/stas/.config/systemd/user/${SVCNAME}.service
systemctl --user daemon-reload
systemctl --user restart ${SVCNAME}
journalctl --user -u ${SVCNAME} -n 10 --no-pager
```

**TariStation1:**
```bash
source /home/stas/projects/sintaris-pl/.env
SVCNAME=taris-telegram
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST; PROJECT=/home/stas/projects/sintaris-pl
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/services/${SVCNAME}.service $U@$H:/tmp/${SVCNAME}.service
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "cp /tmp/${SVCNAME}.service ~/.config/systemd/user/${SVCNAME}.service && \
   systemctl --user daemon-reload && systemctl --user restart ${SVCNAME} && \
   journalctl --user -u ${SVCNAME} -n 10 --no-pager"
```

---

## Safe Update with Backup

For schema changes, new modules, or data format changes. Run Steps 0.5 and 0.6 first, then:

**TariStation2 — stop before deploying:**
```bash
systemctl --user stop taris-telegram taris-web && echo STOPPED
# ... deploy files (Step 2a) ...
# Run migration if schema changed:
cd ~/.taris && python3 migrate_to_db.py --source=/home/stas/.taris && echo MIGRATION_OK
# Restart:
systemctl --user start taris-telegram taris-web && sleep 4
journalctl --user -u taris-telegram -n 12 --no-pager
```

**TariStation1 — same protocol via SSH:**
```bash
source /home/stas/projects/sintaris-pl/.env
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "systemctl --user stop taris-telegram taris-web && echo STOPPED"
# ... deploy files (Step 2b) ...
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "cd ~/.taris && python3 migrate_to_db.py --source=/home/stas/.taris && echo MIGRATION_OK"
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "systemctl --user start taris-telegram taris-web && sleep 4 && journalctl --user -u taris-telegram -n 12 --no-pager"
```

---

## Step 3 — Verify Deployment

```bash
# TariStation2 (local)
systemctl --user is-active taris-telegram taris-web
grep BOT_VERSION ~/.taris/core/bot_config.py

# TariStation1 (SintAItion)
source /home/stas/projects/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "systemctl --user is-active taris-telegram taris-web && grep BOT_VERSION ~/.taris/core/bot_config.py"
```

✅ **Pass criteria:**
- `[INFO] Version      : 2026.X.Y`
- `[INFO] Polling Telegram…`
- No `ERROR` or `Exception` lines

---

## Step 4 — Run Post-Deploy Tests

### OpenClaw regression tests (mandatory)

```bash
# TariStation2 (local)
DEVICE_VARIANT=openclaw PYTHONPATH=/home/stas/projects/sintaris-pl/src \
  python3 /home/stas/projects/sintaris-pl/src/tests/test_voice_regression.py

# TariStation1 (SintAItion)
source /home/stas/projects/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "DEVICE_VARIANT=openclaw PYTHONPATH=~/.taris python3 ~/.taris/tests/test_voice_regression.py"
```

T29/T30 must PASS. T27/T28 SKIP if packages not installed (OK).

### Screen DSL tests (mandatory if screens changed)

```bash
DEVICE_VARIANT=openclaw PYTHONPATH=/home/stas/projects/sintaris-pl/src \
  python3 -m pytest /home/stas/projects/sintaris-pl/src/tests/screen_loader/ -v
```

All 64 tests must PASS.

### Web UI tests (mandatory if web files changed)

```bash
python3 -m pytest /home/stas/projects/sintaris-pl/src/tests/ui/test_ui.py -v \
  --base-url http://localhost:8080 --browser chromium
```

---

## Step 5 — Post-Deploy Prompt *(always ask the user)*

After every successful TariStation2 deployment, ask:

> "Deployment to TariStation2 verified ✅. Shall I also:  
> 1. Commit and push to git? (if not already done)  
> 2. Update `release_notes.json` with a new version entry?  
> 3. **Deploy to TariStation1 (SintAItion)?** *(only after your confirmation)*"

**Do not deploy to TariStation1 until the user explicitly confirms option 3.**

---

## Quick Diagnostics

```bash
# TariStation2 (local) — service status
systemctl --user status taris-telegram taris-web --no-pager

# TariStation2 — tail live log
journalctl --user -u taris-telegram -f --no-pager

# TariStation2 — check all taris services
systemctl --user list-units taris-* --no-pager

# TariStation2 — verify imports
cd ~/.taris && python3 -c "from core.bot_config import BOT_VERSION; print(BOT_VERSION)"

# TariStation1 — service status
source /home/stas/projects/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "systemctl --user status taris-telegram taris-web --no-pager"

# TariStation1 — check errors
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "journalctl --user -u taris-telegram -n 30 --no-pager | grep -i error"
```

---

## File → Service Mapping

| Changed file(s) | Services to restart |
|---|---|
| `core/*.py`, `telegram/*.py`, `features/*.py`, `security/*.py` | `taris-telegram` |
| `ui/bot_ui.py`, `ui/screen_loader.py`, `screens/*.yaml` | `taris-telegram taris-web` |
| `bot_web.py`, `web/templates/`, `web/static/` | `taris-web` (+ `taris-telegram` if bot_web.py) |
| `voice_assistant.py`, `features/bot_voice.py` | `taris-voice` |
| `src/services/*.service` | the changed service (+ `daemon-reload`) |
| `strings.json`, `release_notes.json` | `taris-telegram` |

---

## References

- OpenClaw coding patterns: `.github/copilot-instructions.md` §OpenClaw Variant
- Architecture: `doc/architecture/deployment.md`
- Voice regression tests: `doc/test-suite.md`
- Screen DSL: `doc/architecture/web-ui.md` §18
- Safe update protocol: `.github/skills/taris-deploy-openclaw-target/SKILL.md` §Safe Update
