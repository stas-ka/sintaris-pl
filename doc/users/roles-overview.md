# Taris — Role & Feature Distribution Overview

**Version:** `2026.4.50`  
**Diagram:** [Taris конфигурация для эксперта по ролям.drawio](Taris%20конфигурация%20для%20эксперта%20по%20ролям.drawio)  
→ Architecture: [security.md](../architecture/security.md) · [TODO §1](../../TODO.md)

---

## User Roles — Summary

| Role | Auth Source | Guard function | Notes |
|---|---|---|---|
| **Admin** | `ADMIN_USERS` env var | `_is_admin()` | Static; also set dynamically via admin panel |
| **Developer** | `DEVELOPER_USERS` env var | `_is_developer()` | Static; also set dynamically |
| **Advanced** | Dynamic (`_advanced_users`) | `_is_advanced()` | Set by admin via role menu; gets Agents menu |
| **Full User** | `ALLOWED_USERS` env or dynamic approval | `_is_allowed()` | All personal features |
| **Approved Guest** | Dynamic (`_dynamic_users`) after admin approval | `_is_allowed()` | Same access as Full User (no restrictions) |
| **Limited Guest** | ⏳ Planned — `guest` status in registrations | `_is_guest()` | Chat-only, rate-limited, no personal data |
| **Pending** | `registrations` file, status=`pending` | `_is_pending_reg()` | Registration request sent; awaiting admin |
| **Blocked** | `registrations` file, status=`blocked` | — | Access denied permanently |

**Files:** `src/telegram/bot_access.py` · `src/telegram/bot_users.py` · `src/core/bot_state.py`

---

## Feature Matrix by Role

| Feature | Admin | Developer | Advanced | Full User | Approved Guest | Limited Guest ⏳ | Pending | Blocked |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **💬 Chat (LLM)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (rate-limited) | ❌ | ❌ |
| **📰 Digest** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **📝 Notes** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **📅 Calendar** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **👥 Contacts** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **📄 Documents** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **🎙️ Voice** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **👤 Profile (view)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **❓ Help** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **🤖 Agents / Campaigns** | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **🔒 Error Protocol** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **⚙️ Admin Panel** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **👥 User Management** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **🧠 LLM Settings** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **💬 System Chat (NL→bash)** | ✅ read+config | ✅ all | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **🛠️ Developer Menu** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **🔧 RAG / Doc Admin** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **🔐 Security Policy** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## Role Promotion Paths

```
New user sends /start
        │
        ▼
  Pending (registrations.json)
        │
    Admin decision
   ┌────┴────┐
   │         │
Approve   Block
   │         │
   ▼         ▼
Full User  Blocked
(dynamic)
   │
Admin can promote via Admin Panel → User Management
   │
   ├── promote to Advanced  →  Advanced User
   ├── promote to Admin     →  Dynamic Admin
   ├── promote to Developer →  Dynamic Developer
   └── demote to User       →  Full User (reset)
```

**⏳ Planned — Guest path:**
```
New user sends /start
        │
  [AUTO_GUEST_ENABLED=1]
        │
        ▼
  Guest (limited access, rate-limited)
        │
    Admin promotes → Full User
```

---

## Admin Panel: Role Management

**Entry:** Admin Panel → 👥 User Management → select user → set role

| Admin action | Result |
|---|---|
| Approve registration | Adds to `_dynamic_users` → Full User |
| Block registration | Sets `registrations` status = `blocked` |
| Set role: advanced | Adds to `_advanced_users` |
| Set role: admin | Adds to `_dynamic_admins` |
| Set role: developer | Adds to `_dynamic_devs` |
| Set role: user (reset) | Removes from advanced/admin/dev sets → Full User |

**File:** `src/telegram/bot_admin.py` — `_handle_set_role_*()` functions

---

## Guest User Feature Scope (Planned)

> ⏳ **OPEN:** Guest user implementation → See [doc/todo/1.2-guest-users.md](../todo/1.2-guest-users.md)

| Feature | Scope | Rationale |
|---|---|---|
| Chat (LLM) | ✅ allowed, rate-limited | Core demo value; shows assistant capability |
| Digest | ✅ read-only | Low risk, no personal data |
| Help | ✅ full | Onboarding |
| Profile | ✅ view only, no edits | Identity context |
| Notes | ❌ | Personal data; requires trust |
| Calendar | ❌ | Personal data; requires trust |
| Contacts | ❌ | Personal data; requires trust |
| Documents | ❌ | Personal data; requires trust |
| Voice | ❌ | Hardware resource; guest scope exceeded |
| Agents/Campaigns | ❌ | Business feature; requires explicit grant |

**Rate limits (proposed):** 20 messages/day · 5 messages/hour · max 500 tokens/response

---

## Configuration Constants (existing + planned)

| Constant | Source | Purpose |
|---|---|---|
| `ADMIN_USERS` | `bot.env` | Static admin set |
| `DEVELOPER_USERS` | `bot.env` | Static developer set |
| `ALLOWED_USERS` | `bot.env` | Static full-user set |
| `_dynamic_users` | `users.json` | Runtime-approved full users |
| `_advanced_users` | `bot_state.py` | Admin-promoted advanced users |
| `_dynamic_admins` | `bot_state.py` | Admin-promoted dynamic admins |
| `_dynamic_devs` | `bot_state.py` | Admin-promoted dynamic developers |
| `AUTO_GUEST_ENABLED` | ⏳ `bot.env` | If `1`: new registrants auto-get guest access |
| `GUEST_MSG_DAILY_LIMIT` | ⏳ `bot.env` | Max messages/day for guests (default: 20) |
| `GUEST_MSG_HOURLY_LIMIT` | ⏳ `bot.env` | Max messages/hour for guests (default: 5) |
