---
name: taris-download-logs
description: >
  Download or tail log files from any taris target (TariStation2, TariStation1/SintAItion,
  OpenClawPI2, OpenClawPI). Supports all log categories: main, assistant, security, voice,
  datastore. Downloads are saved to logs/<target>/ in the project directory.
argument-hint: >
  target: ts2 | ts1 | pi2 | pi1
  log: all | main | assistant | security | voice | datastore (default: all)
  action: tail | download (default: tail)
  lines: N (default: 100, for tail only)
---

# Download / Tail Logs — All Targets

## When to Use

| Trigger | Recommended action |
|---|---|
| Bot behaving unexpectedly | `tail` the main log (`telegram_bot.log`) |
| Access / injection issues | `tail` `security.log` |
| STT/TTS broken | `tail` `voice.log` |
| DB errors or slow queries | `tail` `datastore.log` |
| Post-incident audit | `download` all logs |
| Daily monitoring | `tail all` — last 50 lines each |

---

## Log Files (all targets)

| Category | File path on target | Bot constant |
|---|---|---|
| Main | `~/.taris/telegram_bot.log` | `_LOG_FILE` |
| Assistant | `~/.taris/assistant.log` | `_ASSISTANT_LOG_FILE` |
| Security | `~/.taris/security.log` | `_SECURITY_LOG_FILE` |
| Voice | `~/.taris/voice.log` | `_VOICE_LOG_FILE` |
| Datastore | `~/.taris/datastore.log` | `_DATASTORE_LOG_FILE` |

---

## 🚀 Quick Actions via Script (Recommended)

```bash
# Tail last 100 lines of all logs — TariStation2 (local)
bash src/setup/taris_deploy.sh --action logs --target ts2

# Tail last 100 lines of all logs — TariStation1 (SintAItion)
bash src/setup/taris_deploy.sh --action logs --target ts1

# Tail — Pi engineering target
bash src/setup/taris_deploy.sh --action logs --target pi2

# Tail — Pi production target
bash src/setup/taris_deploy.sh --action logs --target pi1
```

> **Note:** If `taris_deploy.sh --action logs` is not yet implemented, use the manual commands below.

---

## Manual: TariStation2 (local, no SSH)

```bash
TARIS_DIR=~/.taris
LINES=${LINES:-100}

echo "=== telegram_bot.log ==="; tail -n $LINES $TARIS_DIR/telegram_bot.log 2>/dev/null || echo "(not found)"
echo "=== assistant.log ===";   tail -n $LINES $TARIS_DIR/assistant.log    2>/dev/null || echo "(not found)"
echo "=== security.log ===";    tail -n $LINES $TARIS_DIR/security.log     2>/dev/null || echo "(not found)"
echo "=== voice.log ===";       tail -n $LINES $TARIS_DIR/voice.log        2>/dev/null || echo "(not found)"
echo "=== datastore.log ===";   tail -n $LINES $TARIS_DIR/datastore.log    2>/dev/null || echo "(not found)"
```

**Download to project (for archiving):**

```bash
PROJECT=/home/stas/projects/sintaris-pl
TS=$(date +%Y%m%d_%H%M%S)
DEST=$PROJECT/logs/TariStation2_$TS
mkdir -p $DEST
for f in telegram_bot assistant security voice datastore; do
  [ -f ~/.taris/${f}.log ] && cp ~/.taris/${f}.log $DEST/ || \
  [ -f ~/.taris/telegram_bot.log ] && [ "$f" = "telegram_bot" ] && cp ~/.taris/telegram_bot.log $DEST/
done
ls -lh $DEST/
echo "Logs saved to: $DEST"
```

---

## Manual: TariStation1 / SintAItion (remote SSH)

```bash
source /home/stas/projects/sintaris-pl/.env
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST
LINES=100

# Tail all logs in one SSH session
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no $U@$H bash <<'EOF'
LINES=100
TARIS=~/.taris
echo "=== telegram_bot.log ==="; tail -n $LINES $TARIS/telegram_bot.log 2>/dev/null || echo "(not found)"
echo "=== assistant.log ===";   tail -n $LINES $TARIS/assistant.log    2>/dev/null || echo "(not found)"
echo "=== security.log ===";    tail -n $LINES $TARIS/security.log     2>/dev/null || echo "(not found)"
echo "=== voice.log ===";       tail -n $LINES $TARIS/voice.log        2>/dev/null || echo "(not found)"
echo "=== datastore.log ===";   tail -n $LINES $TARIS/datastore.log    2>/dev/null || echo "(not found)"
EOF
```

**Download all logs to project:**

```bash
source /home/stas/projects/sintaris-pl/.env
U=${OPENCLAW1_USER:-stas}; H=$OPENCLAW1_HOST
TS=$(date +%Y%m%d_%H%M%S)
DEST=/home/stas/projects/sintaris-pl/logs/TariStation1_$TS
mkdir -p $DEST

for f in telegram_bot assistant security voice datastore; do
  sshpass -p "$OPENCLAW1PWD" scp -o StrictHostKeyChecking=no \
    $U@$H:~/.taris/${f}.log $DEST/ 2>/dev/null || true
done
ls -lh $DEST/
echo "Logs saved to: $DEST"
```

**Single category (fast):**

```bash
source /home/stas/projects/sintaris-pl/.env
# Change CATEGORY to: telegram_bot | assistant | security | voice | datastore
CATEGORY=security
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@$OPENCLAW1_HOST \
  "tail -n 200 ~/.taris/${CATEGORY}.log"
```

---

## Manual: Pi targets (plink/pscp from Windows)

### Tail (view only)

```bat
rem Change HOST to OpenClawPI2 (dev) or OpenClawPI (prod)
rem Change LOG to: telegram_bot | assistant | security | voice | datastore

set HOST=OpenClawPI2
set LOG=telegram_bot
set LINES=100

plink -pw "%DEV_HOSTPWD%" -batch stas@%HOST% "tail -n %LINES% ~/.taris/%LOG%.log 2>/dev/null || echo (not found)"
```

### Tail all logs

```bat
set HOST=OpenClawPI2
plink -pw "%DEV_HOSTPWD%" -batch stas@%HOST% ^
  "for f in telegram_bot assistant security voice datastore; do echo \"=== ${f}.log ===\"; tail -n 100 ~/.taris/${f}.log 2>/dev/null || echo '(not found)'; done"
```

### Download all logs to local

```bat
set HOST=OpenClawPI2
set DEST=logs\%HOST%_%date:~10,4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set DEST=%DEST: =0%

md "%DEST%"
for %%F in (telegram_bot assistant security voice datastore) do (
  pscp -pw "%DEV_HOSTPWD%" stas@%HOST%:~/.taris/%%F.log "%DEST%\%%F.log" 2>nul
)
dir /b "%DEST%"
echo Logs saved to: %DEST%
```

---

## Tail a Single Log File (quick reference)

| Log | What to look for |
|---|---|
| `telegram_bot.log` | Startup sequence, version, `Polling Telegram…`, handler errors |
| `assistant.log` | LLM calls, intent classification, response generation |
| `security.log` | `DENIED`, injection blocked, unknown users |
| `voice.log` | STT WER, TTS latency, hotword triggers, pipeline errors |
| `datastore.log` | DB query times, upsert errors, connection failures |

**Filter for errors only:**

```bash
# TariStation2 (local)
grep -i "error\|exception\|traceback\|critical" ~/.taris/telegram_bot.log | tail -50

# TariStation1 (remote)
source /home/stas/projects/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@$OPENCLAW1_HOST \
  "grep -i 'error\|exception\|traceback\|critical' ~/.taris/telegram_bot.log | tail -50"

# Pi target (Windows)
plink -pw "%DEV_HOSTPWD%" -batch stas@OpenClawPI2 ^
  "grep -i 'error\|exception\|traceback\|critical' ~/.taris/telegram_bot.log | tail -50"
```

---

## Log Rotation (reference)

Taris does **not** auto-rotate logs. Files grow unbounded until manually cleared.

**Clear a log file (preserves empty file, keeps service running):**

```bash
# TariStation2
truncate -s 0 ~/.taris/telegram_bot.log && echo CLEARED

# TariStation1
source /home/stas/projects/sintaris-pl/.env
sshpass -p "$OPENCLAW1PWD" ssh -o StrictHostKeyChecking=no ${OPENCLAW1_USER:-stas}@$OPENCLAW1_HOST \
  "truncate -s 0 ~/.taris/telegram_bot.log && echo CLEARED"
```

> **Never `rm` log files while the service is running.** The file handle stays open, logging silently goes to `/dev/null`. Use `truncate -s 0` instead.

---

## Local Log Storage Layout

Downloaded logs are saved to:

```
sintaris-pl/logs/
  TariStation2_YYYYMMDD_HHMMSS/
    telegram_bot.log
    assistant.log
    security.log
    voice.log
    datastore.log
  TariStation1_YYYYMMDD_HHMMSS/
    ...
```

> `logs/` is git-ignored — log files are never committed.

---

## References

- Category logger source: `src/core/bot_logger.py`
- Log file path constants: `src/core/bot_config.py` (`_LOG_FILE`, `_ASSISTANT_LOG_FILE`, …)
- Alert handler (ERROR → Telegram): `bot_logger.configure_alert_handler()`
- Deploy skill: `.github/skills/taris-deploy-openclaw-target/SKILL.md`
