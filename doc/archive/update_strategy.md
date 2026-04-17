# Update & Deployment Strategy

**Scope:** taris Telegram bot (`telegram_menu_bot.py`) on Raspberry Pi 3 B+ (single-host, single-service deployment).

---

## 1. Guiding Principles

| Principle | Rationale |
|---|---|
| **Users are notified before any downtime** | The bot is conversational — a silent drop feels like a crash, not a restart |
| **Updates are small and frequent** | Incremental changes are safer and easier to roll back than big-bang releases |
| **Every release has a version + changelog** | Admins and users always know what changed |
| **Rollback is one command** | Any release must be revertable in under 60 seconds |
| **Restart is graceful** | Active sessions are allowed to finish or are cleanly interrupted with a message |

---

## 2. Release Workflow

```
1. dev  →  code change + tests
2.      →  bump BOT_VERSION (YYYY.M.D format)
3.      →  prepend entry to src/release_notes.json
4.      →  update TODO.md (collapse done items)
5.      →  git commit + push
6.      →  notify users (maintenance window open)
7.      →  deploy files to Pi (pscp)
8.      →  restart service (systemctl)
9.      →  verify: journal + bot responds
10.     →  admins auto-notified via release notes on first startup
```

### Version numbering

`BOT_VERSION = "YYYY.M.D"` — examples: `2026.3.17`, `2026.4.1`

For release candidates: `2026.3.15-rc1`

---

## 3. Pre-Update User Notification

Before restarting the service, the update script sends a maintenance notice to all approved users and admins.

### 3.1 Notification mechanism (planned enhancement)

Add a `--notify` mode to `src/setup/update.sh` or a standalone `src/setup/notify_maintenance.py`:

```bash
# Notify all users, then wait for grace period, then restart
python3 ~/.taris/notify_maintenance.py --message "🔧 Bot update in 30 seconds. Short interruption." --wait 30
echo "$HOSTPWD" | sudo -S systemctl restart taris-telegram
```

`notify_maintenance.py` should:
1. Read `~/.taris/registrations.json` for all `approved` users.
2. Send each user a Telegram message via the Bot API (`requests.post` to `api.telegram.org`).
3. Wait for the configured grace period (default: 30 s).
4. Exit with code 0 — restart is triggered by the calling script.

### 3.2 Message templates

```
🔧 System update
@smartpico_bot is restarting for a scheduled update.
Back online in ~30 seconds.
Version: 2026.3.17 — Admin menu Markdown fixes
```

```
⚠️ Maintenance window
Bot will be unavailable for ~2 minutes for a system update.
You will receive a message when it's back online.
```

### 3.3 Post-restart notification

The existing release-notes notification mechanism (`last_notified_version.txt`) already sends admins a changelog on first startup after a version bump. Extend this to optionally ping all approved users:

- Config flag: `NOTIFY_USERS_ON_UPDATE=1` in `bot.env`
- Message: `✅ Bot updated to v2026.3.17 — see /changelog`

---

## 4. Deploy Steps (Current)

### 4.1 Quick update (bot + companion files)

```bat
rem 1. Deploy files
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py stas@OpenClawPI:/home/stas/.taris/
pscp -pw "%HOSTPWD%" src\release_notes.json   stas@OpenClawPI:/home/stas/.taris/
pscp -pw "%HOSTPWD%" src\strings.json         stas@OpenClawPI:/home/stas/.taris/

rem 2. Restart service
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S systemctl restart taris-telegram"

rem 3. Verify
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "journalctl -u taris-telegram -n 15 --no-pager"
```

### 4.2 Full update via update.sh (executes on Pi)

```bash
# Run on Pi (or invoke via plink)
bash /home/stas/.taris/update.sh
```

This handles: file sync, diff-based service unit updates, daemon-reload, service restarts.

### 4.3 Full fresh install (disaster recovery)

```bash
bash /tmp/install.sh
```

Delivered via `src/setup/install.sh`. Installs all dependencies, system packages, models, services, and cron from scratch.

---

## 5. Rollback Strategy

### 5.1 Git-based rollback

Every deployed state is a git commit. To roll back:

```bat
rem Find the last good commit
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "git -C /home/stas/.taris log --oneline -10"

rem Roll back bot to previous version
git checkout <prev-commit-hash> -- src/telegram_menu_bot.py
pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py stas@OpenClawPI:/home/stas/.taris/
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "echo %HOSTPWD% | sudo -S systemctl restart taris-telegram"
```

### 5.2 Tagged releases

Tag every stable release in git:

```bash
git tag -a v2026.3.17 -m "Admin menu Markdown fixes"
git push --tags
```

Roll back to a tagged release:

```bash
git checkout v2026.3.15-rc1 -- src/telegram_menu_bot.py src/release_notes.json
# then deploy as above
```

### 5.3 Pi-side backup before update

Before each deploy, optionally save the current bot:

```bash
plink ... "cp ~/.taris/telegram_menu_bot.py ~/.taris/telegram_menu_bot.py.bak"
```

---

## 6. Parallel / Staged Deployment

For larger changes (new major features, architecture changes), use a staged approach:

### 6.1 Shadow mode (same Pi, different port/config)

1. Copy `bot.env` to `bot.env.staging`, change `BOT_TOKEN` to a staging bot token.
2. Launch `telegram_menu_bot.py --env bot.env.staging` as a separate process (manual, not via systemd).
3. Test all flows on the staging bot.
4. Stop staging, deploy to production, restart service.

### 6.2 Feature flags in bot.env

New features that are risky can be hidden behind env flags:

```bash
# bot.env
FEATURE_NEW_MENU=0          # 0 = disabled, 1 = enabled
FEATURE_RBAC=0
```

Enable for admins first, then roll out to all users:

```python
if os.environ.get("FEATURE_NEW_MENU") == "1":
    ...
```

### 6.3 Canary users

Approved users can be tagged as `"canary": true` in `registrations.json`. New features are only shown to canary users until stable.

---

## 7. Extension Deployment Checklist

When adding a **new service or systemd unit**:

- [ ] Write script in `src/` with its own log file
- [ ] Create `src/services/<name>.service` with `EnvironmentFile` pointing to `bot.env`
- [ ] Add env vars to `src/setup/bot.env.example`
- [ ] Deploy service file + `daemon-reload` + `enable` + `start`
- [ ] Verify with `journalctl -u <name> -n 30`
- [ ] Update `doc/architecture.md` (process hierarchy, file layout)
- [ ] Update `README.md` features list
- [ ] Add TODO entry and mark when done
- [ ] Commit everything in one changeSet

When updating the **bot only** (Python file changes):

- [ ] Bump `BOT_VERSION` in `telegram_menu_bot.py`
- [ ] Add entry at top of `src/release_notes.json`
- [ ] Update `TODO.md` — collapse done items, add new ones
- [ ] Deploy files + restart service
- [ ] Verify admin release note notification in journal
- [ ] Commit and tag

---

## 8. Service Restart Timing (Pi 3 B+)

| Phase | Duration |
|---|---|
| systemd sends SIGTERM | 0 s |
| Python exits (cleanup) | ~1 s |
| Bot token heartbeat timeout (Telegram detects offline) | ~30–60 s |
| systemd starts new process | ~2 s |
| Bot registers with Telegram, sends release note | ~5 s |
| **Total user-visible downtime** | **~5–15 s** (polling detects new process within seconds) |

> With a pre-restart notification sent 30 s before, users experience the downtime as intentional, not as a crash.

---

## 9. Planned Enhancements (Future)

| Enhancement | Priority | Effort |
|---|---|---|
| `notify_maintenance.py` script | High | Low |
| `NOTIFY_USERS_ON_UPDATE` flag | Medium | Low |
| Canary user tagging | Low | Medium |
| Feature flags in `bot.env` | Medium | Low |
| Staging bot token in `bot.env.staging` | Low | Low |
| `--dry-run` mode for update.sh | Low | Medium |

---

## 10. Production Update Procedure (SOP)

1. **Write code** — implement feature or fix in `src/`
2. **Bump version** — `BOT_VERSION = "YYYY.M.D"` in bot; prepend to `release_notes.json`
3. **Update docs** — `TODO.md`, `README.md`, `doc/architecture.md` in same commit
4. **Commit** — `git add -A && git commit -m "feat/fix: description (vYYYY.M.D)"` + `git push`
5. **Tag** — `git tag -a vYYYY.M.D -m "release message" && git push --tags`
6. **Notify users** *(when notify script is available)* — `python3 notify_maintenance.py --wait 30`
7. **Deploy** — `pscp` bot + companion files → Pi
8. **Restart** — `echo $HOSTPWD | sudo -S systemctl restart taris-telegram`
9. **Verify** — `journalctl -u taris-telegram -n 20 --no-pager` — check for startup + release note sent
10. **Confirm** — open Telegram, verify bot responds and admin received changelog notification
