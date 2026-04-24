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
- You changed `src/n8n/workflows/` (N8N workflow JSON files)
- You changed `src/core/store_crm.py`, `src/features/bot_crm.py`, `src/features/bot_n8n.py`, `src/features/bot_campaign.py`
- You need to bump `BOT_VERSION` and push a release
- You are deploying CRM/N8N features to a target for the first time

## ⚠️ Target Priority Rule — MANDATORY

**ALWAYS deploy to TariStation2 first. TariStation1 (SintAItion) requires explicit confirmation from user/owner (stas) AFTER TariStation2 tests pass. VPS-Supertaris requires a separate explicit confirmation and is the highest-risk target.**

| Target | Alias | Type | Transport | Branch rule | Risk |
|---|---|---|---|---|---|
| TariStation2 (engineering) | local machine | `cp` + `systemctl --user` | local filesystem | any branch | Low |
| TariStation1 (SintAItion, production) | `SintAItion` | `scp` + `ssh` | remote SSH | `master` only | Medium |
| VPS-Supertaris (internet production) | `agents.sintaris.net` | `scp`/`ssh` | remote SSH | `master` only | 🔴 HIGH |

> ⚠️ **TariStation1 branch rule**: TariStation1 (`SintAItion`) only receives deployments from the **`master` branch**.  
> Before deploying to TariStation1, run `git branch --show-current` and confirm it shows `master`.  
> If on a feature branch — **STOP**. Do not deploy to TariStation1. Inform the user to merge to `master` first.

> ⚠️ **TariStation1 confirmation rule**: After TariStation2 tests pass, **STOP and ask the user**:  
> `"TariStation2 deployment verified ✅. Shall I also deploy to TariStation1 (SintAItion)?"`  
> Deploy to TariStation1 **only after explicit "yes" from the user/owner**.

> 🔴 **VPS-Supertaris confirmation rule**: VPS-Supertaris is an internet-facing shared production server. After TariStation1 (or TariStation2) is verified, **STOP and ask the user separately**:  
> `"Shall I also deploy to VPS-Supertaris (agents.sintaris.net)?"`  
> **NEVER auto-deploy to VPS-Supertaris. Every individual operation type requires its own confirmation.**

---

## 🚨 TariStation1 VPS Safety Rules — MANDATORY

> **TariStation1 (SintAItion) is a shared production machine.**  
> It runs other bots, databases, and services beyond taris. Any system-level change can affect those services.

### What is on this machine besides taris

- PostgreSQL database (shared, used by multiple services via SSH tunnel to VPS)
- N8N access via Tailscale
- Ollama LLM (local, for taris)

### TariStation1 operation rules

| Operation | Rule |
|---|---|
| **Code deploy** (`scp` Python files) | Requires TS2-verified + explicit user confirmation |
| **Service restart** (`systemctl --user restart`) | Requires explicit user confirmation per service |
| **Service file change** (`.service` deploy) | Requires **separate** explicit confirmation — state exactly what changes |
| **Database migration** (`migrate_to_db.py`) | Requires **separate** explicit confirmation + pre-migration backup |
| **Package install** (`pip install`, `apt install`) | Requires **separate** explicit confirmation |

---

## 🔴 VPS-Supertaris Safety Rules — MANDATORY (HIGHEST RISK)

> **VPS-Supertaris (`agents.sintaris.net`) is a PUBLIC INTERNET VPS hosting critical shared infrastructure.**  
> It serves multiple bots, N8N, PostgreSQL, and the Nginx reverse proxy for ALL apps.  
> A misconfigured Nginx restart or broken PostgreSQL query affects EVERY application on this server.  
> taris runs in **Docker** (`taris-vps-telegram`, `taris-vps-web` containers) at `/opt/taris-docker/`; sub-path `/supertaris-vps/`. **NOT systemctl --user.**

### What is on this VPS besides taris

- PostgreSQL database — shared by multiple applications (N8N, other bots, CRM)
- N8N workflow engine (production campaigns, webhooks)
- Nginx reverse proxy — serves ALL bots and apps via sub-paths (`/supertaris/`, `/taris/`, `/taris2/`, etc.)
- Other bots and web services (outages here are publicly visible)
- SSL certificates (Let's Encrypt via Certbot)

### Mandatory pre-VPS checklist (present and wait for "yes" before ANY VPS operation)

```
🔴 About to execute on VPS-Supertaris (agents.sintaris.net) — public internet VPS:

  [ ] 1. Change type: <code deploy | service restart | service file | migration | package install | nginx | system config>
  [ ] 2. taris services affected: taris-telegram, taris-web
  [ ] 3. Shared services potentially impacted: <PostgreSQL / Nginx / N8N / other bots — list>
  [ ] 4. Downtime: visible at https://agents.sintaris.net/supertaris/ (~N seconds)
  [ ] 5. Data at risk: <yes/no — what data, backup confirmed locally?>
  [ ] 6. Rollback plan: <backup name + exact restore command>

Shall I proceed? (yes/no)
```

**Never bundle multiple VPS operation types into one confirmation — ask separately for each.**

### Forbidden autonomous actions on VPS-Supertaris

- ❌ `apt upgrade`, `apt dist-upgrade`, `pip install --upgrade` — NEVER without confirmation
- ❌ Nginx config change (`/etc/nginx/`) — affects ALL apps on VPS
- ❌ PostgreSQL DDL (CREATE/DROP/ALTER/TRUNCATE TABLE) — always show SQL first, confirm + backup
- ❌ Restart shared services (PostgreSQL, Nginx, N8N) — confirm separately for each
- ❌ Firewall changes (`ufw`, `iptables`) — confirm separately
- ❌ `docker compose restart taris-telegram taris-web` — confirm separately (brief public downtime)
- ❌ `systemctl --user restart taris-*` — does NOT apply to VPS-Supertaris (uses Docker, not systemd)
- ❌ Cron / systemd timer changes — confirm separately
- ❌ Any `sudo` command — state exact command and reason, confirm before running

### VPS environment variables (from `.env`)

| Variable | Purpose |
|---|---|
| `VPS_HOST` | VPS hostname or IP (`agents.sintaris.net`) |
| `VPS_USER` | SSH user on VPS |
| `VPS_PWD` | SSH password |
| `VPS_HOSTKEY` | SSH hostkey fingerprint (SHA256) |

### VPS SSH/SCP commands

> ⚠️ **VPS-Supertaris uses Docker, NOT `~/.taris/` or `systemctl --user`.**  
> Source volume: `/opt/taris-docker/app/src/` · Config: `/opt/taris-docker/bot.env`  
> When working **from the VPS itself** (code-server on agents.sintaris.net), deploy directly with `sudo cp`. No SSH/SCP needed.

```bash
source /home/stas/projects/sintaris/sintaris-pl/.env

# SSH (from remote dev machine)
sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no -o "FingerprintHash=sha256" $VPS_USER@$VPS_HOST "<cmd>"

# Copy source files to Docker volume (from remote dev machine)
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no $PROJECT/src/core/*.py \
  $VPS_USER@$VPS_HOST:/opt/taris-docker/app/src/core/

# Copy on VPS directly (when working from VPS / code-server)
sudo cp /home/stas/projects/sintaris/sintaris-pl/src/features/bot_remote_kb.py \
  /opt/taris-docker/app/src/features/bot_remote_kb.py

# Restart containers (compose service names: taris-telegram, taris-web)
cd /opt/taris-docker && docker compose restart taris-telegram taris-web

# Verify
docker logs taris-vps-telegram --tail=10
```

---

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
mkdir -p /home/stas/projects/sintaris/sintaris-pl/backup/snapshots/${BNAME}
cp /tmp/${BNAME}.tar.gz /home/stas/projects/sintaris/sintaris-pl/backup/snapshots/${BNAME}/
ls -lh /home/stas/projects/sintaris/sintaris-pl/backup/snapshots/${BNAME}/
```

Expected: `BACKUP_OK`. **Do not proceed without a local backup copy.**

### TariStation1 (SintAItion) — before Step 5b

```bash
source /home/stas/projects/sintaris/sintaris-pl/.env
TS=$(date +%Y%m%d_%H%M%S)
VER=$(sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "grep BOT_VERSION ~/.taris/core/bot_config.py | head -1 | cut -d'\"' -f2")
BNAME="taris_backup_TariStation1_v${VER}_${TS}"

sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "tar czf /tmp/${BNAME}.tar.gz \
   -C /home/stas/.taris \
   --exclude='vosk-model-*' --exclude='*.onnx' --exclude='ggml-*.bin' --exclude='*/__pycache__' \
   . 2>/dev/null && echo BACKUP_OK"

mkdir -p /home/stas/projects/sintaris/sintaris-pl/backup/snapshots/${BNAME}
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST}:/tmp/${BNAME}.tar.gz \
  /home/stas/projects/sintaris/sintaris-pl/backup/snapshots/${BNAME}/
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
source /home/stas/projects/sintaris/sintaris-pl/.env
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
| CRM/N8N first deploy on target | [CRM/N8N First-Time Setup](#crm--n8n-first-time-setup-on-new-target) |
| N8N workflow JSON update | Sync `src/n8n/workflows/*.json` → `~/.taris/n8n/workflows/` |

---

## Step 2a — Incremental Deploy (TariStation2, local)

Replace `<package>` and `<file>` with changed paths:

```bash
# Sync changed files — adjust to which packages changed
PROJECT=/home/stas/projects/sintaris/sintaris-pl

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

# N8N workflows (if src/n8n/ changed)
mkdir -p ~/.taris/n8n/workflows
cp $PROJECT/src/n8n/workflows/*.json ~/.taris/n8n/workflows/ 2>/dev/null || true
```

**Verify sync before restart** (prevents stale deployment bugs):

```bash
PROJECT=/home/stas/projects/sintaris/sintaris-pl
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
> ⚠️ **Present the VPS pre-TS1 checklist above and wait for "yes" before executing any command.**

```bash
source /home/stas/projects/sintaris/sintaris-pl/.env
HOST=${OPENCLAW1_HOST}
USER=${OPENCLAW1_USER:-stas}
PROJECT=/home/stas/projects/sintaris/sintaris-pl

# Create target package dirs (idempotent)
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $USER@$HOST \
  "mkdir -p ~/.taris/core ~/.taris/telegram ~/.taris/features ~/.taris/ui ~/.taris/security ~/.taris/screens ~/.taris/web/templates ~/.taris/web/static ~/.taris/n8n/workflows && \
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

# N8N workflows (if changed)
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $USER@$HOST \
  "mkdir -p ~/.taris/n8n/workflows"
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/n8n/workflows/*.json $USER@$HOST:~/.taris/n8n/workflows/ 2>/dev/null || true

# Restart
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $USER@$HOST \
  "systemctl --user restart taris-telegram taris-web && sleep 4 && journalctl --user -u taris-telegram -n 15 --no-pager"
```

---

## Screens Deploy

When only `src/screens/*.yaml` or `src/screens/screen.schema.json` changed:

**TariStation2:**
```bash
cp /home/stas/projects/sintaris/sintaris-pl/src/screens/*.yaml ~/.taris/screens/
cp /home/stas/projects/sintaris/sintaris-pl/src/screens/screen.schema.json ~/.taris/screens/
systemctl --user restart taris-telegram taris-web && sleep 4
journalctl --user -u taris-telegram -n 10 --no-pager
```

**TariStation1:**
```bash
source /home/stas/projects/sintaris/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  /home/stas/projects/sintaris/sintaris-pl/src/screens/*.yaml \
  /home/stas/projects/sintaris/sintaris-pl/src/screens/screen.schema.json \
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
PROJECT=/home/stas/projects/sintaris/sintaris-pl
cp $PROJECT/src/bot_web.py ~/.taris/
cp -r $PROJECT/src/web/templates/. ~/.taris/web/templates/
cp -r $PROJECT/src/web/static/. ~/.taris/web/static/
systemctl --user restart taris-telegram taris-web && sleep 4
journalctl --user -u taris-telegram -n 5 --no-pager
journalctl --user -u taris-web -n 5 --no-pager
```

**TariStation1:**
```bash
source /home/stas/projects/sintaris/sintaris-pl/.env
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST; PROJECT=/home/stas/projects/sintaris/sintaris-pl
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
cp /home/stas/projects/sintaris/sintaris-pl/src/services/${SVCNAME}.service \
   /home/stas/.config/systemd/user/${SVCNAME}.service
systemctl --user daemon-reload
systemctl --user restart ${SVCNAME}
journalctl --user -u ${SVCNAME} -n 10 --no-pager
```

**TariStation1:**
```bash
source /home/stas/projects/sintaris/sintaris-pl/.env
SVCNAME=taris-telegram
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST; PROJECT=/home/stas/projects/sintaris/sintaris-pl
sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/services/${SVCNAME}.service $U@$H:/tmp/${SVCNAME}.service
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "cp /tmp/${SVCNAME}.service ~/.config/systemd/user/${SVCNAME}.service && \
   systemctl --user daemon-reload && systemctl --user restart ${SVCNAME} && \
   journalctl --user -u ${SVCNAME} -n 10 --no-pager"
```

> ⚠️ **Service file changes on TariStation1 require a separate explicit confirmation** — before running the above, tell the user exactly what changed in the `.service` file and wait for "yes".

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
source /home/stas/projects/sintaris/sintaris-pl/.env
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "systemctl --user stop taris-telegram taris-web && echo STOPPED"
# ... deploy files (Step 2b) ...
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "cd ~/.taris && python3 migrate_to_db.py --source=/home/stas/.taris && echo MIGRATION_OK"
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "systemctl --user start taris-telegram taris-web && sleep 4 && journalctl --user -u taris-telegram -n 12 --no-pager"
```

> ⚠️ **Migration on TariStation1 requires a separate explicit confirmation** — state the schema changes and confirm backup is local before running.

---

## Step 2c — Incremental Deploy (VPS-Supertaris / agents.sintaris.net)

> 🔴 **Only run AFTER TariStation1 (or TariStation2) is verified AND user/owner has explicitly confirmed VPS deploy.**  
> 🔴 **Only on `master` branch.** (`git branch --show-current` must show `master`).  
> 🔴 **Present the mandatory pre-VPS checklist above and wait for "yes" before any command.**  
> 🔴 **Ask for separate confirmation for code deploy, service restart — never bundle.**

> **VPS-Supertaris uses Docker**, NOT systemctl or `~/.taris/`.  
> Docker compose project: `/opt/taris-docker/`  
> Source volume: `/opt/taris-docker/app/src/` → mounted as `/app:ro` inside containers  
> Config: `/opt/taris-docker/bot.env` (env_file for both containers)  
> Compose service names: `taris-telegram`, `taris-web`  
> Container names: `taris-vps-telegram`, `taris-vps-web`  
> Web UI: port `8090`, ROOT_PATH=`/supertaris-vps` (nginx-only — uvicorn routes have no prefix)  
> Direct web test: `curl http://localhost:8090/login` (NOT `/supertaris-vps/login`)

---

### 🖥️ Scenario A — Deploying FROM the VPS itself (e.g. code-server on agents.sintaris.net)

This is the normal case when editing via VS Code/code-server on the VPS directly.  
**No SSH or SCP needed** — project is already at `/home/stas/projects/sintaris/sintaris-pl`.

**[SEPARATE CONFIRMATION REQUIRED]** Copy source files to Docker volume:

```bash
PROJECT=/home/stas/projects/sintaris/sintaris-pl
APP=/opt/taris-docker/app/src

# Core + telegram + features + entry points
sudo cp $PROJECT/src/core/*.py          $APP/core/
sudo cp $PROJECT/src/telegram/*.py      $APP/telegram/
sudo cp $PROJECT/src/features/*.py      $APP/features/
sudo cp $PROJECT/src/ui/*.py            $APP/ui/
sudo cp $PROJECT/src/security/*.py      $APP/security/
sudo cp $PROJECT/src/telegram_menu_bot.py $APP/
sudo cp $PROJECT/src/bot_web.py         $APP/
sudo cp $PROJECT/src/strings.json       $APP/
sudo cp $PROJECT/src/release_notes.json $APP/

# Web assets (if templates/static changed)
sudo cp -r $PROJECT/src/web/templates/. $APP/web/templates/
sudo cp -r $PROJECT/src/web/static/.    $APP/web/static/

# N8N workflows (if changed)
sudo mkdir -p $APP/n8n/workflows
sudo cp $PROJECT/src/n8n/workflows/*.json $APP/n8n/workflows/ 2>/dev/null || true

echo "✓ files copied to Docker volume"
```

**Verify sync before restarting:**

```bash
PROJECT=/home/stas/projects/sintaris/sintaris-pl
APP=/opt/taris-docker/app/src
for f in telegram_menu_bot.py core/bot_config.py features/bot_contacts.py telegram/bot_handlers.py; do
  diff "$PROJECT/src/$f" "$APP/$f" > /dev/null 2>&1 && echo "OK  $f" || echo "DIFF $f — NOT SYNCED"
done
```

All lines must show `OK`. Fix any `DIFF` lines before restarting.

**[SEPARATE CONFIRMATION REQUIRED]** Restart Docker containers (brief public downtime):

```bash
cd /opt/taris-docker && docker compose restart taris-telegram taris-web && sleep 8
docker logs taris-vps-telegram --tail=20
```

**Pass criteria:** `Version: 2026.X.Y`, `Polling Telegram…`

---

### 💻 Scenario B — Deploying FROM a remote dev machine (e.g. TariStation2, home laptop)

Use this when you are NOT on the VPS — copy files via SCP, then SSH to restart.

**[SEPARATE CONFIRMATION REQUIRED]** Copy source files to Docker volume on VPS:

```bash
source /home/stas/projects/sintaris/sintaris-pl/.env
U=$VPS_USER; H=$VPS_HOST
PROJECT=/home/stas/projects/sintaris/sintaris-pl
APP=/opt/taris-docker/app/src

# Core + telegram + features + entry points
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/core/*.py     $U@$H:$APP/core/
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/telegram/*.py $U@$H:$APP/telegram/
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/features/*.py $U@$H:$APP/features/
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/ui/*.py       $U@$H:$APP/ui/
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/security/*.py $U@$H:$APP/security/
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no \
  $PROJECT/src/telegram_menu_bot.py \
  $PROJECT/src/bot_web.py \
  $PROJECT/src/strings.json \
  $PROJECT/src/release_notes.json \
  $U@$H:$APP/

# Web assets (if templates/static changed)
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no -r \
  $PROJECT/src/web/templates/ $U@$H:$APP/web/
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no -r \
  $PROJECT/src/web/static/ $U@$H:$APP/web/

echo "✓ files uploaded to VPS Docker volume"
```

**Verify + restart via SSH:**

```bash
source /home/stas/projects/sintaris/sintaris-pl/.env
U=$VPS_USER; H=$VPS_HOST

# Verify key files are in sync
sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "grep BOT_VERSION /opt/taris-docker/app/src/core/bot_config.py"

# [SEPARATE CONFIRMATION REQUIRED] Restart containers
sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no $U@$H \
  "cd /opt/taris-docker && docker compose restart taris-telegram taris-web && sleep 8 && docker logs taris-vps-telegram --tail=20"
```

**Pass criteria:** `Version: 2026.X.Y`, `Polling Telegram…`

---

## Step 3 — Verify Deployment

```bash
# TariStation2 (local)
systemctl --user is-active taris-telegram taris-web
grep BOT_VERSION ~/.taris/core/bot_config.py

# TariStation1 (SintAItion)
source /home/stas/projects/sintaris/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "systemctl --user is-active taris-telegram taris-web && grep BOT_VERSION ~/.taris/core/bot_config.py"

# VPS-Supertaris (agents.sintaris.net) — uses Docker, NOT systemctl
# Run directly on VPS:
docker ps | grep taris-vps
docker logs taris-vps-telegram --tail=5
# Or from remote dev machine:
source /home/stas/projects/sintaris/sintaris-pl/.env
sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST \
  "docker ps | grep taris-vps && docker logs taris-vps-telegram --tail=5"
# Also verify public URL is reachable:
curl -s -o /dev/null -w "%{http_code}" https://agents.sintaris.net/supertaris-vps/  # expect 200 or 302
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
DEVICE_VARIANT=openclaw PYTHONPATH=/home/stas/projects/sintaris/sintaris-pl/src \
  python3 /home/stas/projects/sintaris/sintaris-pl/src/tests/test_voice_regression.py

# TariStation1 (SintAItion)
source /home/stas/projects/sintaris/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "DEVICE_VARIANT=openclaw PYTHONPATH=~/.taris python3 ~/.taris/tests/test_voice_regression.py"
```

T29/T30 must PASS. T27/T28 SKIP if packages not installed (OK).

### N8N / Campaign tests (mandatory if CRM_ENABLED=1)

```bash
# Local (TariStation2) — unit + integration
DEVICE_VARIANT=openclaw PYTHONPATH=/home/stas/projects/sintaris/sintaris-pl/src \
  python3 -m pytest /home/stas/projects/sintaris/sintaris-pl/src/tests/test_n8n_crm.py -v
DEVICE_VARIANT=openclaw PYTHONPATH=/home/stas/projects/sintaris/sintaris-pl/src \
  python3 -m pytest /home/stas/projects/sintaris/sintaris-pl/src/tests/test_campaign.py -v -k "not live"
```

T130–T140 campaign tests must PASS (live N8N tests SKIP if webhooks not reachable).

### Screen DSL tests (mandatory if screens changed)

```bash
DEVICE_VARIANT=openclaw PYTHONPATH=/home/stas/projects/sintaris/sintaris-pl/src \
  python3 -m pytest /home/stas/projects/sintaris/sintaris-pl/src/tests/screen_loader/ -v
```

All 64 tests must PASS.

### Web UI tests (mandatory if web files changed)

```bash
python3 -m pytest /home/stas/projects/sintaris/sintaris-pl/src/tests/ui/test_ui.py -v \
  --base-url http://localhost:8080 --browser chromium
```

---

## CRM / N8N First-Time Setup on New Target

Run this section **once** when deploying CRM+N8N features to a target that has never had them. Skip if the target already has `CRM_ENABLED=1` in `bot.env`.

### 1 — Required bot.env additions

Add to `~/.taris/bot.env` on the target (replace `***` with values from `.env`):

```bash
# N8N integration
N8N_URL=***                                  # VPS_N8N_URL from .env (e.g. https://<vps>/n8n)
N8N_API_KEY=***                              # VPS_N8N_API_KEY from .env
N8N_WEBHOOK_SECRET=***                       # N8N_WEBHOOK_SECRET from .env
N8N_TIMEOUT=30

# Campaign agent (N8N webhooks — set after workflows are active in N8N)
N8N_CAMPAIGN_SELECT_WH=***                   # ${N8N_URL}/webhook/taris-campaign-select
N8N_CAMPAIGN_SEND_WH=***                     # ${N8N_URL}/webhook/taris-campaign-send
CAMPAIGN_SHEET_ID=***                        # CAMPAIGN_SHEET_ID from .env
N8N_CAMPAIGN_TIMEOUT=90
CAMPAIGN_DEMO_MODE=false
CAMPAIGN_FROM_EMAIL=***                      # sender address

# CRM (PostgreSQL via SSH tunnel on port 15432)
CRM_ENABLED=1
CRM_PG_DSN=postgresql://taris:***@127.0.0.1:15432/taris   # VPS_POSTGRES_PASSWORD via tunnel
```

### 2 — Install psycopg3 (if not present)

```bash
# TariStation2
pip3 install "psycopg[binary,pool]" --quiet

# TariStation1 (via SSH)
source /home/stas/projects/sintaris/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "pip3 install 'psycopg[binary,pool]' --quiet && python3 -c 'import psycopg; print(psycopg.__version__)'"
```

Expected: psycopg version printed (e.g. `3.3.3`).

### 3 — Initialize CRM schema on VPS PostgreSQL

```bash
# From project root — creates crm_contacts, crm_interactions, crm_tasks,
# crm_campaigns, crm_campaign_contacts tables on VPS PostgreSQL
source .env
PGPASSWORD=$VPS_POSTGRES_PASSWORD psql \
  -h $VPS_HOST -U $VPS_POSTGRES_USER -d taris -p ${VPS_SSH_PORT:-5432} \
  -f src/setup/crm_schema.sql && echo "CRM_SCHEMA_OK"
```

> If `crm_schema.sql` does not exist, init via Python (auto-creates on first use):
> ```bash
> DEVICE_VARIANT=openclaw CRM_ENABLED=1 CRM_PG_DSN="postgresql://..." \
>   python3 -c "from core.store_crm import is_available; print('CRM:', is_available())"
> ```

### 4 — Migrate existing SQLite contacts to CRM (optional, run once)

Only needed if the target has contacts in `taris.db` (check: `contacts` table > 0 rows in Step 0.6).

```bash
# On TariStation2 (local):
DEVICE_VARIANT=openclaw PYTHONPATH=~/.taris \
  python3 -c "
import sqlite3, os, sys
sys.path.insert(0, os.path.expanduser('~/.taris'))
from core import store_crm as crm
conn = sqlite3.connect(os.path.expanduser('~/.taris/taris.db'))
rows = conn.execute('SELECT first_name, last_name, phone, email, telegram FROM contacts').fetchall()
print(f'Migrating {len(rows)} contacts...')
for r in rows:
    crm.create_contact(r[0], r[1] or '', phone=r[2] or '', email=r[3] or '', telegram=r[4] or '')
print('MIGRATION_OK')
"

# On TariStation1 (via SSH):
source /home/stas/projects/sintaris/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "DEVICE_VARIANT=openclaw PYTHONPATH=~/.taris python3 -c \"
import sqlite3, os, sys
sys.path.insert(0, os.path.expanduser('~/.taris'))
from core import store_crm as crm
conn = sqlite3.connect(os.path.expanduser('~/.taris/taris.db'))
rows = conn.execute('SELECT first_name, last_name, phone, email, telegram FROM contacts').fetchall()
print(f'Migrating {len(rows)} contacts...')
for r in rows:
    crm.create_contact(r[0], r[1] or '', phone=r[2] or '', email=r[3] or '', telegram=r[4] or '')
print('MIGRATION_OK')
\""
```

### 5 — Verify CRM is reachable

```bash
# TariStation2
DEVICE_VARIANT=openclaw PYTHONPATH=~/.taris python3 -c \
  "from core.store_crm import is_available, count_contacts; print('CRM:', is_available(), '| contacts:', count_contacts())"

# TariStation1
source /home/stas/projects/sintaris/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "DEVICE_VARIANT=openclaw PYTHONPATH=~/.taris python3 -c \
  'from core.store_crm import is_available, count_contacts; print(\"CRM:\", is_available(), \"| contacts:\", count_contacts())'"
```

Expected: `CRM: True | contacts: N`

### 6 — Verify N8N webhooks are active

```bash
# Check campaign workflows are active in N8N
source .env
curl -s -H "X-N8N-API-KEY: $VPS_N8N_API_KEY" \
  "${VPS_N8N_URL}/api/v1/workflows" \
  | python3 -c "import sys,json; wfs=json.load(sys.stdin)['data']; \
    [print(w['name'], '✅' if w['active'] else '❌') for w in wfs if 'Campaign' in w.get('name','')]"
```

Expected: `Taris - Campaign Select ✅` and `Taris - Campaign Send ✅`

---

## Step 5 — Post-Deploy Prompt *(always ask the user)*

After every successful TariStation2 deployment, ask:

> "Deployment to TariStation2 verified ✅. Shall I also:  
> 1. Commit and push to git? (if not already done)  
> 2. Update `release_notes.json` with a new version entry?  
> 3. **Deploy to TariStation1 (SintAItion)?** *(only after your confirmation)*  
> 4. **Deploy to VPS-Supertaris (agents.sintaris.net)?** *(only after your separate confirmation — highest risk)*"

**Do not deploy to TariStation1 until the user explicitly confirms option 3.**  
**Do not deploy to VPS-Supertaris until the user explicitly confirms option 4 — then also present the pre-VPS checklist.**

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
source /home/stas/projects/sintaris/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "systemctl --user status taris-telegram taris-web --no-pager"

# TariStation1 — check errors
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@${OPENCLAW1_HOST} \
  "journalctl --user -u taris-telegram -n 30 --no-pager | grep -i error"

# VPS-Supertaris — service status
source /home/stas/projects/sintaris/sintaris-pl/.env
sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST \
  "systemctl --user status taris-telegram taris-web --no-pager"

# VPS-Supertaris — check errors
sshpass -p "$VPS_PWD" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_HOST \
  "journalctl --user -u taris-telegram -n 30 --no-pager | grep -i error"

# VPS-Supertaris — public URL health check
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://agents.sintaris.net/supertaris/
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
| `core/store_crm.py`, `features/bot_crm.py`, `features/bot_n8n.py`, `features/bot_campaign.py` | `taris-telegram taris-web` |
| `n8n/workflows/*.json` | no restart needed (read at webhook call time) |

---

## References

- OpenClaw coding patterns: `.github/copilot-instructions.md` §OpenClaw Variant
- Architecture: `doc/architecture/deployment.md`
- Voice regression tests: `doc/test-suite.md`
- Screen DSL: `doc/architecture/web-ui.md` §18
- Safe update protocol: `.github/skills/taris-deploy-openclaw-target/SKILL.md` §Safe Update
