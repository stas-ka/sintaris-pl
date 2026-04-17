# Taris — Role & Feature Distribution Overview

**Version:** `2026.4.50`  
**Diagram:** [Taris конфигурация для эксперта по ролям.drawio](Taris%20конфигурация%20для%20эксперта%20по%20ролям.drawio)  
→ Architecture: [security.md](../architecture/security.md) · [TODO §1](../../TODO.md)  
→ Specs: [guest users](../todo/1.2-guest-users.md) · [prompt templates](../todo/1.5-prompt-templates.md)

---

## User Roles — Summary

| Role | Auth Source | Guard function | Notes |
|---|---|---|---|
| **Admin** | `ADMIN_USERS` env var | `_is_admin()` | Static; also set dynamically via admin panel |
| **Developer** | `DEVELOPER_USERS` env var | `_is_developer()` | Static; also set dynamically |
| **Advanced** | Dynamic (`_advanced_users`) | `_is_advanced()` | Set by admin via role menu; gets Agents menu |
| **User** | `ALLOWED_USERS` env or auto/dynamic approval | `_is_allowed()` | All personal features; formerly "Full User" |
| **Guest** | ⏳ Planned — `guest` status in registrations | `_is_limited_guest()` | Chat + meeting requests, rate-limited, no personal data |
| **Pending** | `registrations` file, status=`pending` | `_is_pending_reg()` | Registration sent; awaiting admin (when auto-registration off) |
| **Blocked** | `registrations` file, status=`blocked` | — | Access denied permanently |

> **Note:** "Approved Guest" (dynamic_users after admin approval) is merged into **User** — once approved, guests get full User access. The distinct "guest" status is the limited pre-approval role.

**Files:** `src/telegram/bot_access.py` · `src/telegram/bot_users.py` · `src/core/bot_state.py`

---

## Feature Matrix by Role

| Feature | Admin | Developer | Advanced | User | Guest ⏳ | Pending | Blocked |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **💬 Chat (LLM)** | ✅ | ✅ | ✅ | ✅ | ✅ rate-limited | ❌ | ❌ |
| **📝 Notes** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **📅 Calendar (full)** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **📅 Meeting request / invite expert** | ✅ | ✅ | ✅ | ✅ | ✅ ⏳ | ❌ | ❌ |
| **📅 View free time slots** | ✅ | ✅ | ✅ | ✅ | ✅ ⏳ | ❌ | ❌ |
| **📅 Confirm meeting invitations** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **👥 Contacts** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **📄 Documents menu** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **📄 Upload documents** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **📄 Shared docs as chat knowledge** | ✅ | ✅ | ✅ | ✅ | ✅ ⏳ | ❌ | ❌ |
| **📰 Digest** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **🎙️ Voice** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **👤 Profile (view)** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **❓ Help** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **🌐 Web UI access** | ✅ | ✅ | ✅ | ✅ | ⏳ request only | ❌ | ❌ |
| **🤖 Agents / Campaigns** | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **🔒 Error Protocol** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **⚙️ Admin Panel** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **👥 User Management** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **🧠 LLM Settings** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **💬 System Chat (NL→bash)** | ✅ read+config | ✅ all | ❌ | ❌ | ❌ | ❌ | ❌ |
| **🛠️ Developer Menu** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **🔧 RAG / Doc Admin** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **🔐 Security Policy** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## Role Promotion Paths

```
New user sends /start or registers via Web UI
        │
   ┌────┴──────────────────────┐
   │                           │
[AUTO_USER_ENABLED=1]    [AUTO_GUEST_ENABLED=1]    [default: pending]
   │                           │                           │
   ▼                           ▼                           ▼
  User                       Guest                     Pending
(immediate,              (limited access,          (admin approval
full access)              rate-limited)               required)
                               │
                         Admin promotes
                               │
                               ▼
                             User
                               │
              Admin can promote via Admin Panel → User Management
                               │
                  ├── promote to Advanced → Advanced User
                  ├── promote to Admin    → Dynamic Admin
                  ├── promote to Developer → Dynamic Developer
                  └── demote to User      → User (reset)
```

**Registration modes** (configurable via `bot.env`):

| Mode | Constant | Behavior |
|---|---|---|
| Pending (default) | — | Admin must approve each registration |
| Auto-Guest | `AUTO_GUEST_ENABLED=1` | New registrants immediately get Guest access |
| Auto-User | `AUTO_USER_ENABLED=1` | New registrants immediately get full User access |

---

## Admin Panel: Role Management

**Entry:** Admin Panel → 👥 User Management → select user → set role

| Admin action | Result |
|---|---|
| Approve registration (pending → User) | Adds to `_dynamic_users` → User |
| Approve registration (guest → User) | Changes status `guest` → `approved`; adds to `_dynamic_users` |
| Block | Sets `registrations` status = `blocked` |
| Set role: guest | Sets status `guest` (limited access) |
| Set role: advanced | Adds to `_advanced_users` |
| Set role: admin | Adds to `_dynamic_admins` |
| Set role: developer | Adds to `_dynamic_devs` |
| Set role: user (reset) | Removes from advanced/admin/dev sets → User |

**File:** `src/telegram/bot_admin.py` — `_handle_set_role_*()` functions

---

## Web UI Access Rights

Web UI is accessible to all approved users (User, Advanced, Admin, Developer).

| Role | Web UI | Auth method |
|---|---|---|
| Admin / Developer | ✅ Full | Local password (`WEBCHAT_PWD_HASH`) + JWT |
| Advanced / User | ✅ Full | Local password + JWT |
| Guest | ⏳ Request access only (web registration form) | N/A — not logged in |
| Pending / Blocked | ❌ | — |

> ⏳ **OPEN:** Guest web UI registration form → See [doc/todo/1.2-guest-users.md](../todo/1.2-guest-users.md)

---

## Guest User Feature Scope (Planned)

> ⏳ **OPEN:** Guest user implementation → See [doc/todo/1.2-guest-users.md](../todo/1.2-guest-users.md)

| Feature | Guest scope | Rationale |
|---|---|---|
| Chat (LLM) | ✅ rate-limited | Core value; demonstrates assistant capability |
| Shared docs as knowledge | ✅ RAG context injected automatically | Admin-curated public knowledge; no personal data exposed |
| Help | ✅ full | Onboarding |
| Profile | ✅ view only | Identity context |
| Request meeting / invite expert | ✅ ⏳ | Business scenario: guest schedules consultation |
| View free time slots | ✅ ⏳ | Guest can see expert availability before requesting |
| Digest | ❌ | Requires e-mail account integration |
| Notes | ❌ | Personal data; not applicable to guest |
| Calendar (own) | ❌ | Personal data; not applicable to guest |
| Contacts | ❌ | Personal data; requires trust |
| Documents menu | ❌ | Personal data; upload not applicable |
| Upload documents | ❌ | Not applicable to guest |
| Voice | ❌ | Hardware resource; out of guest scope |
| Agents/Campaigns | ❌ | Business feature; requires explicit grant |

**Rate limits (proposed):** 20 messages/day · 5 messages/hour · max 500 tokens/response

---

## Prompt Templates per Role

> ⏳ **OPEN:** Role-based prompt template system → See [doc/todo/1.5-prompt-templates.md](../todo/1.5-prompt-templates.md)

Different user types get different system prompts injected into each LLM call:

| Role | Template | Personal context injected |
|---|---|---|
| Admin / Developer | `prompts/admin_system.txt` | Notes, Calendar, Contacts, RAG (user + shared docs) |
| Advanced / User | `prompts/user_system.txt` | Notes, Calendar, Contacts, RAG (user + shared docs) |
| Guest | `prompts/guest_system.txt` | RAG (shared docs only); no personal data |
| Voice | `prompts/voice_system.txt` | Same as User, with STT hint |

Templates use `{variable}` placeholders filled at runtime: `{bot_name}`, `{user_name}`, `{calendar_summary}`, `{notes_summary}`, `{rag_context}`, `{language_instruction}`.

---

## Configuration Constants (existing + planned)

| Constant | Source | Purpose |
|---|---|---|
| `ADMIN_USERS` | `bot.env` | Static admin set |
| `DEVELOPER_USERS` | `bot.env` | Static developer set |
| `ALLOWED_USERS` | `bot.env` | Static user set |
| `_dynamic_users` | `users.json` | Runtime-approved users |
| `_advanced_users` | `bot_state.py` | Admin-promoted advanced users |
| `_dynamic_admins` | `bot_state.py` | Admin-promoted dynamic admins |
| `_dynamic_devs` | `bot_state.py` | Admin-promoted dynamic developers |
| `AUTO_GUEST_ENABLED` | ⏳ `bot.env` | If `1`: new registrants auto-get Guest access |
| `AUTO_USER_ENABLED` | ⏳ `bot.env` | If `1`: new registrants auto-get full User access |
| `GUEST_MSG_DAILY_LIMIT` | ⏳ `bot.env` | Max messages/day for guests (default: 20) |
| `GUEST_MSG_HOURLY_LIMIT` | ⏳ `bot.env` | Max messages/hour for guests (default: 5) |
| `GUEST_MAX_TOKENS` | ⏳ `bot.env` | Max LLM response tokens for guests (default: 500) |
| `PROMPT_TEMPLATES_DIR` | ⏳ `bot.env` | Directory containing role prompt templates |
