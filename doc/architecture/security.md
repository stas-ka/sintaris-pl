# Taris — Security Architecture

**Version:** `2026.4.50`  
→ Architecture index: [architecture.md](../architecture.md)

## When to read this file
Modifying user roles, adding access guards, changing `bot_security.py`, `bot_access.py` or any `_is_*()` helper.

---

## 6.1 Three-Layer Prompt Injection Defense

**File:** `src/security/bot_security.py`

| Layer | Function | What it does |
|---|---|---|
| L1 — Pre-LLM scan | `_check_injection(text)` | Blocks ~25 regex patterns: instruction overrides, persona hijack, prompt extraction, credential leak, shell injection, jailbreak keywords (Russian+English). LLM never called on match. |
| L2 — User input delimiting | `_wrap_user_input(text)` | Wraps `[USER]\n{text}\n[/USER]` so LLM treats user text as data, not instructions. Called by `_user_turn_content()` in `bot_access.py`. |
| L3 — Security preamble | `SECURITY_PREAMBLE` constant | Prepended to every LLM call (role:system). Instructs model to not reveal credentials/paths, not generate shell commands, ignore role-override attempts. |

---

## 6.2 Role-Based Access Control

| Role | Guard function | Config source | Permissions |
|---|---|---|---|
| **Admin** | `_is_admin(chat_id)` | `ADMIN_USERS` in `bot.env` | All features + Admin panel + System chat + LLM settings |
| **Developer** | `_is_developer(chat_id)` | `DEVELOPER_USERS` in `bot.env` | Admin features + diagnostic tools + raw system info (since v2026.3.30) |
| **Full user** | `_is_allowed(chat_id)` | `ALLOWED_USERS` in `bot.env` | All user features (chat, voice, notes, calendar, contacts) |
| **Approved guest** | `_is_allowed(chat_id)` | `_dynamic_users` (DB) | All user features, dynamically approved by admin |
| **Pending** | `_is_pending(chat_id)` | `registrations` DB table | Registration confirmation only |
| **Blocked** | `reg.status == "blocked"` | `registrations` DB table | Blocked message only |

**File:** `src/telegram/bot_access.py` — all `_is_*()` functions.  
**File:** `src/telegram/bot_admin.py` — Admin panel entry point.

### System-Chat Command Allowlists (since v2026.4.50)

**File:** `src/security/bot_security.py` — `ADMIN_ALLOWED_CMDS`, `DEVELOPER_ALLOWED_CMDS`, `_classify_cmd_class()`

| Constant | Contents | Who can run |
|---|---|---|
| `ADMIN_ALLOWED_CMDS` | `cat`, `grep`, `ls`, `find`, `ps`, `systemctl status`, `journalctl`, `ping`, `curl`, `echo`, + monitoring | admin + developer |
| `DEVELOPER_ALLOWED_CMDS` | All of above + `systemctl restart/stop/start`, `cp`, `mv`, `rm`, `git`, `python3`, `apt`, `scp`, etc. | developer only |
| Extra blocklist | Admin-configurable via Security Policy UI → stored in `system_settings.json` as `syschat_blocked_cmds` | Blocked for ALL roles |

`get_extra_blocked_cmds()` reads `system_settings.json["syschat_blocked_cmds"]` at runtime.  
`_classify_cmd_class(cmd)` checks the extra blocklist first (highest priority), then admin allowlist, then developer-only allowlist.  
Admin UI: Admin panel → 🔒 Security Policy → add/remove custom blocked commands.

> ⏳ **OPEN:** Full per-feature RBAC (e.g. calendar-only users) → See [TODO.md §1.1](../TODO.md)

---

## 6.3 Admin Panel Access

| Feature | Role required | Guard |
|---|---|---|
| Admin panel button visible | admin | `_is_admin()` |
| System chat (NL→bash) | admin | `_is_admin()` + `_user_mode == "system"` |
| LLM settings (provider/model override) | admin | `_is_admin()` |
| Voice config admin view | admin | `_is_admin()` |
| User registration approval | admin | `_is_admin()` |
| RAG settings | admin | `_is_admin()` |
| Document admin (list/delete shared docs) | admin | `_is_admin()` |
| Diagnostic / raw system info | developer | `_is_developer()` |

---

## 6.5 RBAC Extensions

### System-Chat Allowlist Enforcement — ✅ Implemented (v2026.4.50)

| Item | Status |
|---|---|
| `ADMIN_ALLOWED_CMDS` + `DEVELOPER_ALLOWED_CMDS` defined | ✅ |
| `_classify_cmd_class()` checks extra blocklist first | ✅ |
| `get_extra_blocked_cmds()` reads from `system_settings.json` | ✅ |
| Admin UI: 🔒 Security Policy button + add/remove flow | ✅ |
| T122 regression test | ✅ PASS |

### Full Role Model (Target)

| Role | Status | System Chat | Admin Panel | Dev Menu | Features |
|---|---|---|---|---|---|
| **Admin** | ✅ Implemented | ✅ Read + config ops | ✅ Full | ❌ No | ✅ Full |
| **Developer** | ✅ Implemented | ✅ All ops + restart | ✅ Full | ✅ bot_dev.py (v2026.3.32) | ✅ Full |
| **Full User** | ✅ Implemented | ❌ No | ❌ No | ❌ No | ✅ Full |
| **Approved Guest** | ✅ Implemented | ❌ No | ❌ No | ❌ No | ✅ Full (dynamic) |
| **Limited Guest** | 🔲 Planned | ❌ No | ❌ No | ❌ No | ⏳ Chat + Digest only, rate-limited |
| **Read-only** | ⏳ Planned | ❌ No | ❌ No | ❌ No | ⏳ View only, no writes |
| **Per-feature user** | ⏳ Planned | ❌ No | ❌ No | ❌ No | ⏳ e.g. calendar-only |
| **Group/shared** | ⏳ Planned | ❌ No | ❌ No | ❌ No | ⏳ Shared chat_id namespace |

→ Spec: [doc/archive/todo/1.1-rbac.md](../archive/todo/1.1-rbac.md) · [doc/archive/todo/1.3-developer-role.md](../archive/todo/1.3-developer-role.md)
→ Guest spec: [doc/todo/1.2-guest-users.md](../todo/1.2-guest-users.md) · [doc/users/roles-overview.md](../users/roles-overview.md)

### Developer Menu — ✅ Implemented (v2026.3.32)

Module: `src/features/bot_dev.py`  · Entry point: `dev_menu` callback

| Button | Callback key | Action |
|---|---|---|
| 💬 Dev Chat | `dev_chat` | LLM chat with role = developer context |
| 🔄 Restart Bot | `dev_restart` → `dev_restart_confirmed` | `systemctl restart taris-telegram` + confirm gate |
| 📋 View Log | `dev_log` | Last 30 lines `telegram_bot.log` |
| 🐛 Last Error | `dev_error` | Last ERROR line from journal |
| 📂 File List | `dev_files` | `~/.taris/*.py` with sizes + mtimes |
| 🔒 Security Log | `dev_security_log` | Last 20 `security_events` rows |

Security event logging functions:
- `log_security_event(chat_id, event_type, detail)` → `security_events` table
- `log_access_denied(chat_id, resource)` → records denied access attempts

### MicoGuard — Central Security Layer (Planned)

> ⏳ **OPEN:** Not started. → [TODO.md §1.2](../TODO.md)

| Feature | Description |
|---|---|
| Centralised role check | Every callback/command validated at a single entry point |
| Security event logging | Separate `security.log`, not mixed with `telegram_bot.log` |
| Configurable policies | Access rules via admin UI + config file |
| Runtime policy updates | No service restart needed |

### Web UI Auth (Planned)

> ⏳ **OPEN:** Current Web UI uses local password hash. OAuth2/SSO planned. → [TODO.md §1](../TODO.md)

| Feature | Status |
|---|---|
| Local password (`WEBCHAT_PWD_HASH` bcrypt) | ✅ Implemented |
| JWT session tokens | ✅ Implemented (`python-jose`) |
| OAuth2 / OIDC | ⏳ Planned |
| Telegram Login Widget | ⏳ Planned |

Secrets never in source code. All loaded from `~/.taris/bot.env` via `os.environ.get()` with safe defaults.

| Secret | Used by |
|---|---|
| `BOT_TOKEN` | `telebot.TeleBot(BOT_TOKEN)` |
| `ADMIN_USERS` | `_is_admin()` |
| `DEVELOPER_USERS` | `_is_developer()` |
| `ALLOWED_USERS` | `_is_allowed()` |
| `OPENAI_API_KEY` | `bot_llm.py` OpenAI provider |
| `DATABASE_URL` | `core/store_postgres.py` |
| `JWT_SECRET` | `src/security/bot_auth.py` (Web UI sessions) |
| `WEBCHAT_PWD_HASH` | Web UI local password auth |

> ⏳ **OPEN:** OAuth2 for Web UI → See [TODO.md §1](../TODO.md)

