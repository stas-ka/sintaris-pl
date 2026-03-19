---
mode: agent
description: Backup a Raspberry Pi target (data, software, system config, binaries, or all).
---

# Backup Pi Target (`/taris_backup_target`)

**Usage**: `/taris_backup_target [host] [type] [path]`

| Parameter | Values | Default |
|---|---|---|
| `host` | `OpenClawPI` \| `OpenClawPI2` | `OpenClawPI` |
| `type` | `data` \| `software` \| `system` \| `binaries` \| `all` | `all` |
| `path` | local destination directory | `./backup/snapshots/` |

---

## Read context first

Before executing any backup step, read:
1. `.env` in workspace root — provides `HOSTPWD`, `HOSTPWD2`, remote host addresses
2. `backup/snapshots/` — existing snapshots to avoid duplicates
3. `doc/quick-ref.md` — remote host reference

If no parameters provided, ask: "Back up which host? (OpenClawPI / OpenClawPI2)"

---

## Step 0 — Determine credentials

```
host = OpenClawPI  → user=stas  password=%HOSTPWD%   (from .env)
host = OpenClawPI2 → user=stas  password=%HOSTPWD2%  (from .env)
```

Generate a timestamp label: run `plink` to get the remote date:
```bat
for /f %%T in ('plink -pw "PASS" -batch stas@HOST "date +%%Y%%m%%d_%%H%%M%%S"') do set TS=%%T
```
Local snapshot name: `picoclaw_backup_HOST_vVERSION_TIMESTAMP`

---

## Step 1 — Create local backup directory

```bat
mkdir "PATH\picoclaw_backup_HOST_TIMESTAMP"
```

---

## Step 2 — Backup by type

Execute the steps relevant to the requested type. For `all`, run all steps below.

### type: `data` — Application data

Creates a tar.gz of all persistent user data and configuration:

```bat
rem Create archive on Pi (excluding binary models and __pycache__)
plink -pw "PASS" -batch stas@HOST ^
  "tar czf /tmp/picoclaw_data_TS.tar.gz ^
    -C /home/stas ^
    --exclude='.picoclaw/__pycache__' ^
    --exclude='.picoclaw/*/__pycache__' ^
    --exclude='.picoclaw/*.onnx' ^
    --exclude='.picoclaw/*.bin' ^
    --exclude='.picoclaw/*.log' ^
    .picoclaw/pico.db ^
    .picoclaw/*.json ^
    .picoclaw/*.txt ^
    .picoclaw/bot.env ^
    .picoclaw/config.json ^
    .picoclaw/calendar/ ^
    .picoclaw/mail_creds/ ^
    .picoclaw/notes/ ^
    .picoclaw/error_protocols/ ^
    2>/dev/null; echo done"

rem Pull the archive to local path
pscp -pw "PASS" stas@HOST:/tmp/picoclaw_data_TS.tar.gz "PATH\picoclaw_backup_HOST_TS\"

rem Cleanup temp file on Pi
plink -pw "PASS" -batch stas@HOST "rm -f /tmp/picoclaw_data_TS.tar.gz"
```

Contents of data backup:
- `pico.db` — SQLite main database
- `*.json` — runtime JSON (voice_opts, users, registrations, pending_tts, web_link_codes, accounts)
- `bot.env` — secrets (BOT_TOKEN, ALLOWED_USERS, ADMIN_USERS)
- `config.json` — picoclaw LLM config
- `calendar/` — per-user calendar event files
- `mail_creds/` — per-user IMAP credentials + digest cache
- `notes/` — per-user Markdown notes
- `error_protocols/` — admin error reports (if any)

---

### type: `software` — Application sources

The software is already in the local git repository. However, to capture the exact deployed version on the Pi:

```bat
rem Backup all Python sources and data files currently deployed
plink -pw "PASS" -batch stas@HOST ^
  "tar czf /tmp/picoclaw_software_TS.tar.gz ^
    -C /home/stas ^
    --exclude='.picoclaw/*/__pycache__' ^
    .picoclaw/*.py ^
    .picoclaw/strings.json ^
    .picoclaw/release_notes.json ^
    .picoclaw/core/*.py ^
    .picoclaw/security/*.py ^
    .picoclaw/telegram/*.py ^
    .picoclaw/features/*.py ^
    .picoclaw/ui/*.py ^
    .picoclaw/web/templates/ ^
    .picoclaw/web/static/ ^
    .picoclaw/setup/ ^
    .picoclaw/services/ ^
    2>/dev/null; echo done"

pscp -pw "PASS" stas@HOST:/tmp/picoclaw_software_TS.tar.gz "PATH\picoclaw_backup_HOST_TS\"
plink -pw "PASS" -batch stas@HOST "rm -f /tmp/picoclaw_software_TS.tar.gz"
```

---

### type: `system` — System configuration

Backs up systemd service units, crontab, and audio/modprobe config:

```bat
plink -pw "PASS" -batch stas@HOST ^
  "tar czf /tmp/picoclaw_system_TS.tar.gz ^
    /etc/systemd/system/picoclaw*.service ^
    /etc/systemd/system/picoclaw*.timer ^
    /etc/cron.d/ ^
    /etc/modprobe.d/ ^
    2>/dev/null; echo done"

pscp -pw "PASS" stas@HOST:/tmp/picoclaw_system_TS.tar.gz "PATH\picoclaw_backup_HOST_TS\"
plink -pw "PASS" -batch stas@HOST "rm -f /tmp/picoclaw_system_TS.tar.gz"
```

Also capture crontab:
```bat
plink -pw "PASS" -batch stas@HOST "crontab -l 2>/dev/null" > "PATH\picoclaw_backup_HOST_TS\crontab.txt"
```

---

### type: `binaries` — Installed packages and binary info

Creates a manifest of installed Python packages, system packages, and binary versions:

```bat
plink -pw "PASS" -batch stas@HOST ^
  "pip3 freeze > /tmp/pip_freeze.txt 2>&1; ^
   picoclaw version >> /tmp/pip_freeze.txt 2>/dev/null; ^
   echo '---dpkg---' >> /tmp/pip_freeze.txt; ^
   dpkg -l | grep -E 'python3|piper|vosk|ffmpeg|libopus|zram' >> /tmp/pip_freeze.txt 2>/dev/null; ^
   echo done"

pscp -pw "PASS" stas@HOST:/tmp/pip_freeze.txt "PATH\picoclaw_backup_HOST_TS\installed_packages.txt"
plink -pw "PASS" -batch stas@HOST "rm -f /tmp/pip_freeze.txt"
```

---

## Step 3 — Verify backup

List the backup directory contents:
```bat
dir "PATH\picoclaw_backup_HOST_TS\"
```

Report:
- Total size of backup files
- Which types were captured
- Any errors encountered

---

## Step 4 — Summary report

After backup completes, report:
```
✅ Backup complete
   Host    : HOST
   Type    : TYPE
   Path    : PATH\picoclaw_backup_HOST_TS\
   Files   : list of .tar.gz files + sizes
   DB rows : (from Step 2 data) users / calendar_events / notes_index / chat_history counts
```

To show DB row counts for the data backup:
```bat
plink -pw "PASS" -batch stas@HOST ^
  "python3 -c \"import sqlite3; ^
    c=sqlite3.connect('/home/stas/.picoclaw/pico.db'); ^
    [print(t,c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) ^
    for t in ['users','calendar_events','notes_index','chat_history','contacts','documents','doc_chunks']]\""
```

---

## Notes

- **Never commit** backup archives to git — they contain secrets (`bot.env`, IMAP passwords).
- The backup snapshot path `backup/snapshots/` is git-ignored.
- Models (`.onnx`, `.bin`) are excluded from backups — they are large (66–142 MB) and downloadable via `setup/setup_voice.sh`.
- Run `type=data` before any migration or deploy operation to ensure you can roll back.
