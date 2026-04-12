# taris Quick Reference

**Always-read** — 3 KB index. Read this before any task. For full details, follow the links.

---

## Module Dependency Chain

```
core/bot_config → core/bot_state → core/bot_instance → security/bot_security → telegram/bot_access → telegram/bot_users
    → features/bot_voice → features/bot_calendar → features/bot_mail_creds → features/bot_email
    → telegram/bot_admin → telegram/bot_handlers → features/bot_error_protocol → telegram_menu_bot

core/bot_config → core/bot_llm          (shared by Telegram + Web)
core/bot_config → security/bot_auth     (Web UI only)
ui/bot_ui       → ui/bot_actions         (Screen DSL, shared)
ui/bot_actions ← ui/render_telegram · bot_web
```

---

## Key Functions by Task

| Task | Module | Function |
|---|---|---|
| Add calendar event | `features/bot_calendar.py` | `_finish_cal_add()` |
| Voice opt toggle | `telegram/bot_admin.py` | `_handle_voice_opt_toggle()` |
| New callback | `telegram_menu_bot.py` | `handle_callback()` |
| i18n string lookup | `telegram/bot_access.py` | `_t(chat_id, key)` |
| Access guard | `telegram/bot_access.py` | `_is_allowed()` / `_is_admin()` |
| Send menu | `telegram/bot_access.py` | `_send_menu(chat_id)` |
| Ask LLM | `telegram/bot_access.py` | `_ask_taris(prompt)` |
| Notes CRUD | `telegram/bot_users.py` | `_save_note_file()` / `_list_notes_for()` |
| Registration | `telegram/bot_users.py` | `_upsert_registration()` |
| TTS synthesis | `features/bot_voice.py` | `_tts_to_ogg(text)` |
| STT pipeline | `features/bot_voice.py` | `_handle_voice_message()` |
| Screen render | `ui/render_telegram.py` | `render_screen(screen, chat_id, bot)` |

For full function list → **search** `doc/bot-code-map.md` (don't read whole file).

---

## Version Bump (always 2 files)

1. `src/core/bot_config.py` → `BOT_VERSION = "YYYY.M.D"` (no zero-padding)
2. `src/release_notes.json` → **prepend** entry at top (never append; never use `\_` in JSON)

Validate: `python3 -c "import json,sys; json.load(sys.stdin)" < src/release_notes.json`

---

## Strings Rule

All user-visible text → `src/strings.json` under **all three** languages: `ru`, `en`, `de`.

```python
_t(chat_id, "my_key")               # looks up strings.json[lang][key]
_t(chat_id, "my_key", value=42)     # with format kwargs
```

---

## Test Trigger Table

| Changed file / area | Tests to run |
|---|---|
| `features/bot_voice.py` / `core/bot_config.py` (voice constants) | Voice regression T01–T21 |
| `telegram/bot_access.py` (`_escape_tts`) | T07, T08 |
| `strings.json` | T13, T17 |
| `features/bot_calendar.py` | T20, T21 |
| `bot_web.py` / `templates/` / `static/` | Web UI Playwright |
| Any deploy | Smoke: `journalctl -u taris-telegram -n 20` |

Full test reference → `doc/test-suite.md`

---

## Quick Run Commands

```bat
rem Voice regression — all T01–T21
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py"

rem Web UI Playwright
py -m pytest src/tests/ui/test_ui.py -v --base-url https://openclawpi2:8080 --browser chromium

rem Smoke check after deploy
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "journalctl -u taris-telegram -n 20 --no-pager"
```

---

## Deploy Pipeline

**Rule: PI2 → PI1 always.**

1. Deploy to **PI2** (`OpenClawPI2`) — engineering target
2. Verify journal: `[INFO] Version : X.Y.Z` + `[INFO] Polling Telegram…`
3. Run tests (use trigger table above)
4. Commit + push to git
5. Deploy to **PI1** (`OpenClawPI`) — production

```bat
rem Incremental deploy (changed files — include subdir in path)
rem core/: pscp -pw "%HOSTPWD%" src\core\<changed>.py stas@<HOST>:/home/stas/.taris/core/
rem telegram/: pscp -pw "%HOSTPWD%" src\telegram\<changed>.py stas@<HOST>:/home/stas/.taris/telegram/
rem features/: pscp -pw "%HOSTPWD%" src\features\<changed>.py stas@<HOST>:/home/stas/.taris/features/
rem root entries: pscp -pw "%HOSTPWD%" src\telegram_menu_bot.py stas@<HOST>:/home/stas/.taris/
plink -pw "%HOSTPWD%" -batch stas@<HOST> "echo %HOSTPWD% | sudo -S systemctl restart taris-telegram && sleep 3 && journalctl -u taris-telegram -n 12 --no-pager"
```

Full deploy steps → `.github/instructions/bot-deploy.instructions.md`

### User Data Directories (must survive every deploy)

| Path | Content | Backup? |
|------|---------|---------|
| `~/.taris/taris.db` | All user data (SQLite) | ✅ |
| `~/.taris/bot.env` | Secrets | ✅ |
| `~/.taris/notes/` | Note files (.md) | ✅ |
| `~/.taris/docs/` | Uploaded RAG documents (PDF/DOCX) | ✅ |
| `~/.taris/mail_creds/` | Email credentials | ✅ |
| `~/.taris/screens/` | Screen DSL YAML | ✅ |
| `~/.taris/error_protocols/` | Error reports | ✅ |
| `~/.taris/calendar/` | Legacy calendar JSON (migrated to DB) | ✅ |

After restore: run `python3 setup/migrate_to_db.py` to re-index docs and sync legacy JSON → DB.
Full data map → `doc/install-new-target.md §User Data: Storage, Backup & Migration`

---

## Remote Hosts

| Target | Host | Purpose |
|---|---|---|
| Engineering (PI2) | `OpenClawPI2` | Always deploy here first |
| Production (PI1) | `OpenClawPI` / `$PROD_TAILSCALE_IP` (see `.env`) | After PI2 confirmed |

- SSH: `plink -pw "%HOSTPWD%" -batch stas@<HOST> "<cmd>"`
- SCP: `pscp -pw "%HOSTPWD%" <file> stas@<HOST>:<remote-path>`

---

## Post-Deploy Rule

After every successful deploy, ask:
> "Deployment verified ✅. Shall I also: 1. Commit and push to git? 2. Update `release_notes.json`?"

---

## Vibe Log

After every completed request, append to `doc/vibe-coding-protocol.md`:
```
| HH:MM UTC | description | 1–5 | N turns | model-id | files changed | done |
```
