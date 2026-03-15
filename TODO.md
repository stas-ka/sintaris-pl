# Pico Bot — TODO & Roadmap

**Legend:** ✅ Done · 🔄 In progress · 🔲 Planned · 💡 Idea / future

**Completed:** Registration workflow (v2026.3.15) · Notes system · Per-user mail digest · Voice opts (silence_strip, VAD, whisper, piper_low, persistent_piper, tmpfs_model, warm_piper) · Smart calendar with NL input + reminders + morning briefing · Voice regression tests T01–T12 · Backup system · 3-layer prompt injection guard · Whisper hallucination guard (v2026.3.24) · Calendar multi-event, NL query, delete confirmation, console mode (v2026.3.25) · Web UI P0–P4: FastAPI+HTMX, Screen DSL, JWT auth, PWA manifest; `picoclaw-web.service` live on OpenClawPI2 (v2026.3.28) · Login UX fix: username preserved on failed attempt, password autofocus (v2026.3.28) · **Telegram↔Web account linking**: 6-char code, 15 min TTL, `/register` integration, role inheritance, status=active for linked accounts (v2026.3.28)

---

## 0. Known Bugs 🐛

### 0.1 Profile menu not functional — missing actions in Telegram and Web UI 🔲

**Observed (2026-03-08 / 2026-03-15):** Tapping 👤 Profile in the Telegram client sends no reply — silently fails. Additionally the profile section is missing key self-service actions in both Telegram and Web UI.

**Root cause (silent failure):** `_handle_profile()` in `src/bot_handlers.py` does a deferred `from bot_mail_creds import _load_creds` inside the function body. If the import throws, `telebot` swallows the exception silently.

#### Fix — crash guard (immediate)

- [ ] Wrap deferred import + `_load_creds()` in `try/except` — degrade gracefully (show profile without email line, log warning)
- [ ] Verify: `journalctl -u picoclaw-telegram -n 50 | grep -i profile`

#### Feature — Profile screen redesign (Telegram + Web UI both)

The profile menu must be a proper self-service hub. All actions below must be accessible from **both** the Telegram 👤 Profile button **and** the Web UI `/settings`+`/profile` pages.

**Required profile actions:**

| Action | Telegram | Web UI |
|---|---|---|
| View personal info (name, username, chat ID, role, registration date) | ✅ already shown (when profile works) | 🔲 `/profile` page |
| Update display name | 🔲 `profile_edit_name` callback → ForceReply | 🔲 Inline edit form |
| Update email address (IMAP send-to target) | 🔲 `profile_edit_email` → `finish_email_set_target()` | 🔲 Settings form field |
| Access mailbox / digest | 🔲 Button → `digest` callback | 🔲 Link to `/mail` |
| Change password | 🔲 `profile_change_pw` → 2-step ForceReply (current → new) | ✅ `/settings/password` already exists |
| Reset password (admin on behalf of user) | 🔲 Admin panel → `admin_reset_pw_menu` | 🔲 `/admin/user/{id}/reset-password` |

**Telegram implementation checklist:**

- [ ] Fix silent crash first (try/except guard above)
- [ ] Replace current static text reply with an inline keyboard:
  ```
  👤 Profile — @username
  ─────────────────────
  [✏️ Edit name]  [📧 Email settings]
  [🔑 Change password]  [📬 Open mailbox]
  [🔙 Menu]
  ```
- [ ] Add `_profile_keyboard(chat_id)` to `bot_handlers.py`
- [ ] Add `profile_edit_name` callback → ForceReply → `_finish_profile_edit_name(chat_id, text)` → update `registrations.json` name field
- [ ] Add `profile_edit_email` callback → reuse `handle_email_change_target(chat_id)` from `bot_email.py` (shows current masked address + ForceReply for new one)
- [ ] Add `profile_change_pw` callback → 2-step ForceReply: prompt current password → prompt new password → `change_password(user_id, new_pw)` from `bot_auth.py`
- [ ] Add `profile_open_mail` callback → forward to `handle_digest_auth(chat_id)`
- [ ] Register all new `profile_*` callbacks in `telegram_menu_bot.py` dispatcher
- [ ] Add `_pending_profile[chat_id]` session dict for multi-step flows (edit name, change password)
- [ ] Add all new string keys to `src/strings.json` (ru / en / de)

**Web UI implementation checklist:**

- [ ] Add `GET /profile` route in `bot_web.py` — show name, username, chat ID, role, registration date, masked email
- [ ] Add `POST /profile/name` — update display name (writes to `registrations.json`)
- [ ] Add `POST /profile/email` — update send-to email (writes `_target.txt` via `_set_target_email()`)
- [ ] Link to mailbox: `/profile` page shows a "📬 Open mailbox" button → `/mail`
- [ ] Password change already at `POST /settings/password` — ensure it is linked from `/profile`
- [ ] Add `profile.html` template (or extend `settings.html`) with all fields in editable form
- [ ] Add 👤 Profile link to `base.html` nav sidebar
- [ ] Add Playwright test: `GET /profile` returns 200; name field is visible; password change link present

**UI sync rule:** changes to profile actions must be applied in both Telegram **and** Web UI in the same commit — see `.github/copilot-instructions.md` §UI Sync Rule.

### 0.2 Rename bot / assistant — centralise all user-facing name references 🔲

**Affected locations:**
- `src/strings.json` — `welcome` (lines 10/140), `help_text*` ("Pico Bot"), `you_said`/`no_answer` ("picoclaw")
- `src/bot_config.py` — add `BOT_NAME = os.environ.get("BOT_NAME", "Pico")`
- `src/bot_access.py`, `src/bot_security.py` — hardcoded name in prompts/preamble

- [ ] Add `BOT_NAME=Pico` to `src/setup/bot.env.example`
- [ ] Add `BOT_NAME` constant to `bot_config.py`
- [ ] Replace hardcoded names in `strings.json` with `{bot_name}` placeholder; inject via `_t()` kwargs
- [ ] Grep for stragglers: `grep -rn "Pico\b\|picoclaw" src/ --include="*.py"`

### 0.3 Note edit loses existing content 🔲

**Observed (2026-03-08):** When a user taps ✏️ Edit on a note, the current note body is sent back as a Telegram quote (Zitat/ForceReply), but whatever the user types **replaces** the note entirely — the old content is lost. There is no way to edit only part of the note.

**Root cause:** `_start_note_edit()` in `src/bot_handlers.py` sends the current body via `ForceReply` for display only; when the reply arrives, `_save_note_file()` overwrites the file with the new text verbatim. There is no merge/patch step.

- [ ] Send current note body as pre-filled text the user can modify (Telegram `ForceReply` does not support pre-filled text — need a different UX)
- [ ] Option A: send note body in a code block + instruct user to copy-edit-paste; note is saved only when the reply contains the full replacement text (current behaviour, but clarify in UI)
- [ ] Option B: add inline edit buttons — ➕ Append / 🔄 Replace / ✂️ Prepend — so the user explicitly chooses whether to replace or add to existing content
- [ ] Option C: support a simple diff syntax — lines starting with `+` are appended, other lines replace (power-user only)
- [ ] Recommended: implement Option B (Append / Replace) as it covers the most common cases with no learning curve

### 0.4 🔴 Calendar: voice reply deleted before user can hear it 🔲

**Observed (2026-03-12):** After the bot sends an audio voice message in the calendar context (e.g. reading back an event or TTS confirmation), the message is automatically deleted before the user has a chance to listen to it.

**Likely cause:** `_save_pending_tts()` / orphan-cleanup logic in `bot_voice.py` (`_cleanup_orphaned_tts()`) is erroneously marking the calendar TTS message as an orphan and deleting it on the next bot restart or cleanup pass. Alternatively, the calendar handler deletes the "Generating audio…" placeholder but also inadvertently removes the final voice message.

- [ ] Reproduce: add a calendar event via voice → note the message ID of the sent voice note → check if it is deleted
- [ ] Check `_cleanup_orphaned_tts()` — ensure it only deletes "Generating audio…" spinner messages, not completed voice notes
- [ ] Check `_clear_pending_tts()` call sites in `bot_calendar.py` — confirm it is called **after** `bot.send_voice()` returns, not before
- [ ] Add a guard: only delete the pending TTS record after the voice message is confirmed sent (non-None file_id)

### 0.6 🔴 System Chat has no role-differentiated guards — Admin and Developer get same (insufficient) rights 🔲

**Observed (2026-03-14):** System Chat (`mode_system`) is currently gated by `_is_admin()` only. Both Admin and Developer users enter the same unrestricted bash-command flow with identical guards. There is no role-aware permission boundary — the guard structure does not reflect the intended role model:

| Role | Intended System Chat rights |
|---|---|
| **User** | No access to System Chat |
| **Admin** | Monitor, view, and change configuration — `read`, `ls`, `cat`, `systemctl status`, `journalctl`, config file edits. No code execution, no service restart, no file writes outside config dirs |
| **Developer** | Full system access — all Admin rights + file writes, code patches, service restart/redeploy. All destructive operations require explicit confirmation |

**Root cause:** `_handle_system_message()` and `_execute_pending_cmd()` in `src/bot_handlers.py` call `_is_admin()` as the single guard — treating all admins as equivalent. No Developer role exists (`DEVELOPER_USERS` not yet implemented). No command-class filtering is applied per role.

**Required changes:**

- [ ] Add `DEVELOPER_USERS` set to `bot_config.py` (env var `DEVELOPER_USERS`) — see §1.3
- [ ] Add `_is_developer(chat_id)` to `bot_access.py`
- [ ] Define **command class allowlists** per role in `bot_security.py` or `bot_config.py`:
  - `ADMIN_ALLOWED_CMDS` — read-only + config ops: `cat`, `ls`, `head`, `tail`, `grep`, `systemctl status`, `journalctl`, `df`, `free`, `ps`, `uname`, `ping`, `curl` (GET only)
  - `DEVELOPER_ALLOWED_CMDS` — extends Admin: adds `systemctl restart/stop/start`, `cp`, `mv`, `rm`, `python3`, `pip3`, `git`, `pscp`, `plink`
- [ ] In `_handle_system_message()`: branch on `_is_developer()` vs `_is_admin()` vs user:
  - User → `_deny()`
  - Admin → extract command → validate against `ADMIN_ALLOWED_CMDS` allowlist → confirm gate
  - Developer → extract command → validate against `DEVELOPER_ALLOWED_CMDS` allowlist → **always** confirm gate (no auto-run)
- [ ] In `_execute_pending_cmd()`: re-check role at execution time (not just at LLM-extract time) — defence in depth
- [ ] Add `_classify_cmd_class(cmd)` helper — returns `"read"` / `"config"` / `"destructive"` / `"code_change"` based on the bash command
- [ ] Adjust confirm-gate message to show the command class: `⚠️ Destructive command — run as Developer?` vs `ℹ️ Read-only — run as Admin?`
- [ ] For Admin: if `_classify_cmd_class()` returns `"destructive"` or `"code_change"` → reject with explanation, do not show confirm gate
- [ ] Add regression test T22 (or extend T18): `_is_admin` / `_is_developer` / allowlist enforcement unit tests
- [ ] Update `src/strings.json` with role-specific System Chat prompt strings (ru/en/de)

**Related:** §1.1 RBAC, §1.3 Developer Role & Dev Menu

---

### 0.5 🔴 Calendar console ignores "add event" requests — LLM refuses with policy message 🔲

**Observed (2026-03-12):** Sending a multi-event natural language request via the calendar console:

> "добавь сегодня обед в двенадцать тридцать обед заканчивается в тринадцать тридцать и завтра я начинаю работать в восемь часов утра"

The assistant responds with a refusal ("Я не могу добавлять события или управлять расписанием…") instead of extracting and adding the events.

**Root cause:** `_handle_cal_console()` → `_ask_picoclaw()` calls the LLM without any system prompt override.  The **security preamble** (`SECURITY_PREAMBLE`) instructs the model not to perform actions — so the model correctly refuses when the calendar intent is sent as a plain user message. The calendar console must call `_finish_cal_add()` **directly** (local Python logic) rather than asking the LLM to "add the event" in free-form chat mode.

- [ ] In `_handle_cal_console()` (`bot_calendar.py`): after LLM classifies intent as `"add"`, call `_finish_cal_add(chat_id, text)` immediately — do **not** re-route through `_ask_picoclaw()` for the add step
- [ ] Verify the intent-classification prompt returns a clean `{"intent": "add"}` without also asking the LLM to perform the action
- [ ] Test with the exact Russian phrase above — should produce a multi-event confirmation card, not a refusal
- [ ] Also test `"query"` and `"delete"` intents to ensure they are similarly safe from the security preamble block

---

## 1. Access & Security

### 1.1 Role-Based Access Control (RBAC) 🔲

| Role | System Chat | Admin Panel | Dev Menu | User features |
|---|---|---|---|---|
| **Admin** | ✅ Read + config ops only (allowlist) | ✅ Full | ❌ No | ✅ Full |
| **Developer** | ✅ All ops incl. restart/deploy (allowlist + confirm) | ✅ Full | ✅ Full | ✅ Full |
| **User** | ❌ No access | ❌ No | ❌ No | ✅ Full |
| **Guest** | ❌ No access | ❌ No | ❌ No | ⚠️ Pending approval |

**See Bug 0.6** for the current missing guard implementation.

- [ ] Add `DEVELOPER_USERS` set to `bot_config.py` (env var `DEVELOPER_USERS`)
- [ ] Add `_is_developer(chat_id)` to `bot_access.py`
- [ ] Implement per-role command allowlists (`ADMIN_ALLOWED_CMDS`, `DEVELOPER_ALLOWED_CMDS`) in `bot_security.py`
- [ ] Role-aware `_handle_system_message()` — Admin vs Developer vs User branches
- [ ] Admin-only panel items gated by `_is_admin()` check
- [ ] Guest mode: only `/start` + "registration sent"

### 1.3 Developer Role & Dev Menu 🔲

**Concept:** Developer users get a dedicated 🛠 Developer menu that opens a specialised LLM chat session pre-primed with the bot's source code context and dev patterns. The LLM acts as a coding assistant — it can propose code changes, explain implementation options, and generate patches. The developer can then apply them and restart the bot, all from within Telegram.

**Admin vs Developer distinction (System Chat):**

| Capability | Admin | Developer |
|---|---|---|
| Read files, view logs, check status | ✅ | ✅ |
| Change config files (edit settings) | ✅ | ✅ |
| Restart / stop / start services | ❌ Blocked | ✅ Confirm gate |
| Write / patch source code | ❌ Blocked | ✅ Confirm gate |
| Install packages, run `pip3`/`git` | ❌ Blocked | ✅ Confirm gate |
| Deploy files (`pscp`, `mv`) | ❌ Blocked | ✅ Confirm gate |
| Describe new feature → agent implements | ❌ Blocked | ✅ Dev Chat mode |

**Guards are flexible by design:** allowlists defined per role in `ADMIN_ALLOWED_CMDS` / `DEVELOPER_ALLOWED_CMDS` constants — adding a new command class to a role requires only updating the list, no code changes.

**See Bug 0.6** for the current guard gap that must be fixed as part of implementation.

**Dev menu buttons:**
| Button | Action |
|---|---|
| 💬 Dev Chat | LLM chat with source context injected (bot_config, bot_handlers, dev-patterns.md) |
| 🔄 Restart Bot | `systemctl restart picoclaw-telegram` with confirmation gate |
| 📋 View Log | Last 30 lines of `telegram_bot.log` |
| 🐛 Last Error | Last ERROR/EXCEPTION line from journal |
| 📂 File List | List `~/.picoclaw/*.py` with sizes + mtimes |

- [ ] Add `DEVELOPER_USERS` set to `bot_config.py` (env var `DEVELOPER_USERS`)
- [ ] Add `_is_developer(chat_id)` to `bot_access.py`
- [ ] Add dev menu keyboard + `_handle_dev_menu()` to `bot_handlers.py`
- [ ] Dev Chat: inject system prompt with `dev-patterns.md` + key source file snippets
- [ ] Restart button: confirm gate → `systemctl restart picoclaw-telegram`
- [ ] View Log / Last Error: `_run_subprocess(["journalctl", "-u", "picoclaw-telegram", "-n", "30"])`
- [ ] File List: `os.listdir(PICOCLAW_DIR)` filtered to `*.py` with size + mtime
- [ ] Add 🛠 Developer button to main menu (visible to developer role only)

### 1.2 Central Security Layer — MicoGuard 🔲

- [ ] Role validation on every command/callback
- [ ] Security event logging (`security.log`)
- [ ] Configurable access rules (admin UI + config file)
- [ ] Runtime policy updates without restart

---

## 2. Conversation & Memory

### 2.1 Conversation Memory System 🔲

- [ ] Store per-user conversation history (sliding window, default 15 messages)
- [ ] Inject last N messages as context into LLM prompt
- [ ] Optional: persist across restarts (JSON / SQLite)

---

## 3. LLM Provider Support

### 3.1 Multi-LLM Provider Support 🔄

| Provider | Status |
|---|---|
| OpenRouter (via picoclaw) | ✅ Default, running |
| OpenAI (direct) + key management | ✅ Admin UI implemented |
| YandexGPT | 🔲 Planned |
| Gemini | 🔲 Planned |
| Anthropic | 🔲 Planned |
| Local LLM (llama.cpp) | 🔲 See §3.2 |

- [ ] Add `LLM_PROVIDER` env-var switch in `bot.env`
- [ ] Implement YandexGPT client with API key from `bot.env`

### 3.2 Local LLM — Offline Fallback 🔲

See: `doc/hardware-performance-analysis.md` §8.9

- Pi 3 B+: Qwen2-0.5B Q4 (~350 MB, ~1 tok/s) — emergency fallback only
- Pi 4 B (4 GB): Phi-3-mini Q4 (~2.5 GB, ~2 tok/s) — usable
- Pi 5 (8 GB): Llama-3.2-3B Q4 — good

- [ ] Build `llama.cpp` on Pi, store on USB SSD
- [ ] Download model to `/mnt/ssd/models/`
- [ ] Create `picoclaw-llm.service` systemd unit
- [ ] `try/except` fallback in `_ask_picoclaw()` → redirect to `localhost:8080`
- [ ] Label fallback responses with `⚠️ [local fallback]`

---

## 4. Content & Knowledge

### 4.0 Contact Book 🔲

Personal address book — add, update, remove and view contacts via text or voice in both Telegram and Web UI channels.

#### 4.0.1 Data Schema

```sql
-- SQLite table (part of pico.db and §9.3 schema)
CREATE TABLE IF NOT EXISTS contacts (
    id          TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(4)))),
    chat_id     INTEGER NOT NULL REFERENCES users(chat_id),
    name        TEXT    NOT NULL,
    phone       TEXT,
    email       TEXT,
    address     TEXT,
    notes       TEXT,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_contacts_chat_name ON contacts(chat_id, name COLLATE NOCASE);
```

Storage: `~/.picoclaw/pico.db` `contacts` table (same DB as calendar + users).  
No separate JSON/file store needed — SQLite handles all CRUD.

#### 4.0.2 Operations

| Operation | Trigger (Telegram) | Trigger (Voice) | Trigger (Web) |
|---|---|---|---|
| **Add** contact | Button ➕ → multi-step ForceReply (name → phone → email → notes) | "добавь контакт Иван Иванов телефон ..."; NL → LLM extracts fields | Web form on `/contacts/new` |
| **View** one | `contact_open:<id>` button or NL "найди Ивана" | "позвони Ивану" / "покажи Ивана" → lookup + TTS | `/contacts/<id>` detail page |
| **List** all / filtered | `contact_list` button; inline search by name | "кто у меня в контактах?" → TTS list | `/contacts` paginated table |
| **Update** | `contact_edit:<id>` → ForceReply for changed field | "обнови телефон Ивана на ..." | Edit form (HTMX in-place) |
| **Delete** | `contact_del:<id>` → confirm card → `contact_del_confirm:<id>` | "удали контакт Ивана" + confirm | Delete button + confirmation modal |
| **Search** | NL text in console mode or inline search | "найди контакт с почтой gmail" | `/contacts?q=` query param |

#### 4.0.3 Telegram Implementation Checklist

- [ ] Create `src/bot_contacts.py` module (no circular imports — imports `bot_config`, `bot_state`, `bot_instance`, `bot_access`)
- [ ] `_contacts_user_dir(chat_id)` — use DB not files; CRUD helpers: `_contact_add()`, `_contact_get()`, `_contact_update()`, `_contact_delete()`, `_contact_search()`
- [ ] `_contacts_menu_keyboard(chat_id)` — ➕ Add / 🔍 Search / 📋 List / 🔙 Back  
- [ ] `_contacts_list_keyboard(chat_id, contacts)` — per-contact open/edit/delete inline buttons (paginated: max 8 per page)
- [ ] `_start_contact_add(chat_id)` — enter `contact_add` mode; ForceReply: name → phone → email → address → notes (each optional except name)
- [ ] `_finish_contact_add(chat_id, text)` — multi-step state machine via `_pending_contact[chat_id]`
- [ ] `_handle_contact_open(chat_id, cid)` — show detail card: name, phone (tap-to-copy hint), email, address, notes
- [ ] `_start_contact_edit(chat_id, cid)` — show field selector (6 buttons); targeted ForceReply for chosen field
- [ ] `_handle_contact_delete(chat_id, cid)` — confirm card → `contact_del_confirm:<id>`
- [ ] `_handle_contact_search(chat_id)` — enter `contact_search` mode; text → `_contact_search()` → paginated results
- [ ] NL voice integration: in `_handle_voice_message()`, detect "добавь контакт / найди контакт / удали контакт" intent → route to contacts handlers
- [ ] Add `📇 Contacts` button to `_menu_keyboard()` in `bot_access.py`
- [ ] Register all `contact_*` callbacks in `telegram_menu_bot.py` dispatcher
- [ ] Add to `src/strings.json`: all contact UI keys in `ru`, `en`, `de`
- [ ] Add DB init: `contacts` table in `bot_db.py` `init_db()` (§9.3)

#### 4.0.4 Web UI Implementation Checklist

- [ ] Add routes to `src/bot_web.py`:
  - `GET /contacts` — list with search (`?q=`) + pagination
  - `GET /contacts/new` — create form
  - `POST /contacts` — create contact
  - `GET /contacts/{id}` — detail view
  - `PUT /contacts/{id}` — update (HTMX form submit)
  - `DELETE /contacts/{id}` — delete (HTMX confirm)
- [ ] Create `src/templates/contacts.html` — list + search bar + "New contact" button
- [ ] Create `src/templates/_contact_editor.html` — HTMX partial: create/edit form
- [ ] Add 📇 Contacts link to `src/templates/dashboard.html` and `base.html` nav
- [ ] Voice add via web: record button on contacts page → STT → NL parse → pre-fill form fields (uses existing `/api/voice/transcribe` endpoint + client-side form fill)

#### 4.0.5 Voice Parsing Pattern (NL → Contact Fields)

```python
# LLM prompt in _finish_contact_add() voice path:
CONTACT_EXTRACT_PROMPT = """
Extract contact details from the text. Return ONLY JSON:
{"name": "...", "phone": "...", "email": "...", "address": "...", "notes": "..."}
Use null for absent fields. Name is required.
Text: {text}
"""
# If name is null → ask user to repeat with name
# All other fields optional — save partial contact
```

#### 4.0.6 `_user_mode` Values

| Value | Set by | Cleared by |
|---|---|---|
| `"contact_add"` | `_start_contact_add()` | `_finish_contact_add()` on last step |
| `"contact_edit"` | `_start_contact_edit()` | `_handle_contact_edit_input()` |
| `"contact_search"` | `_handle_contact_search()` | after results sent |

#### 4.0.7 Callback Keys (add to dispatcher and `doc/bot-code-map.md`)

| Key / Prefix | Handler |
|---|---|
| `menu_contacts` | `_handle_contacts_menu` |
| `contact_list` | `_handle_contact_list` |
| `contact_create` | `_start_contact_add` |
| `contact_open:<id>` | `_handle_contact_open` |
| `contact_edit:<id>` | `_start_contact_edit` |
| `contact_del:<id>` | `_handle_contact_delete` (confirm card) |
| `contact_del_confirm:<id>` | `_handle_contact_delete_confirmed` |
| `contact_search` | `_handle_contact_search` |
| `contact_page:<n>` | `_handle_contact_list` with offset |

---

### 4.1 Local RAG Knowledge Base 🔲

- [ ] Embed documents with `all-MiniLM-L6-v2`
- [ ] Vector similarity search → inject top-k context into LLM prompt
- [ ] Commands: `/rag_on`, `/rag_off`
- [ ] Storage: `~/.picoclaw/knowledge_base/` (documents + `embeddings.db`)

---

## 5. Voice Pipeline

### 5.1 Baseline (Pi 3 B+ with all opts OFF)

| Stage | Time | Status |
|---|---|---|
| OGG → PCM (ffmpeg) | ~1 s | ✅ |
| STT (Vosk small-ru) | **~15 s** | ❌ bottleneck |
| LLM (OpenRouter) | ~2 s | ✅ |
| TTS cold load (Piper medium, microSD) | **~15 s** | ❌ bottleneck |
| TTS inference (~600 chars) | **~80–95 s** | ❌ bottleneck |
| **Total** | **~115 s** | ❌ target: <15 s |

With `persistent_piper` + `tmpfs_model` + `piper_low_model` all ON: estimated **~20–25 s**.

### 5.2 TTS 110 s bottleneck 🔲

**Root cause:** Cold Piper ONNX load (~15 s) + ONNX inference at `TTS_MAX_CHARS=600` (~80–95 s) on Pi 3 B+.

| Priority | Fix | Where | Expected gain |
|---|---|---|---|
| 🔴 | Add `TTS_VOICE_MAX_CHARS = 300`; use for real-time path | `bot_config.py`, `_tts_to_ogg()` | TTS −50% |
| 🔴 | Document `persistent_piper` + `tmpfs_model` as recommended defaults | Admin panel help | −35 s |
| 🟡 | Enable `piper_low_model` | Voice Opts | −13 s |
| 🟢 | Auto-truncate at sentence boundary ≤ 300 chars | `_tts_to_ogg()` | smooth cuts |

- [ ] Add `TTS_VOICE_MAX_CHARS = 300` to `bot_config.py`
- [ ] Use it in `_tts_to_ogg()` when `_trim=True`
- [ ] Document recommended opt settings in bot help / admin panel

### 5.3 STT/TTS Detailed Improvements Backlog 🔲

**STT issues:**
- [ ] Vosk (180 MB) + Piper (150 MB) both active during voice reply — only ~310 MB headroom on Pi 3
- [ ] Whisper temp WAV written to SD-backed `/tmp` — move to `/dev/shm` (−0.5 s per call)
- [ ] Hallucination threshold (2 words/s) fixed — needs per-length tuning for short commands
- [ ] Add `STT_CONF_THRESHOLD` config constant for Vosk confidence strip (currently implicit)

**TTS issues:**
- [ ] "Read aloud" 1200-char chunks → ~180–200 s synthesis on Pi 3; needs progressive delivery
- [ ] OGG Opus bitrate 24 kbit/s hardcoded — expose as voice opt (16/24/32 kbit/s)
- [ ] Two `subprocess.run()` (Piper → ffmpeg) adds ~0.1 s; Popen pipe avoids this

**Measurement plan (add to `voice_timing_debug`):**
- [ ] ffmpeg OGG→PCM wall time (currently missing from debug output)
- [ ] Split Piper timer: model load time vs inference time
- [ ] Log char count going into Piper (correlate input length with inference time)
- [ ] Collect 10-run timing sample per STT/TTS path on Pi 3 B+

---

## 6. Infrastructure & Operations

### 6.1 Logging & Monitoring 🔲

- [ ] Structured log categories: `assistant.log`, `security.log`, `voice.log`
- [ ] Admin Telegram UI: view last N log lines per category
- [ ] Log rotation (`logrotate` config)

### 6.2 Host–Project Synchronization 🔲

- [ ] rsync-based sync script `src/` → Pi
- [ ] Git-based deployment hook

### 6.3 Deployment Workflow Enhancements 🔲

- [ ] `src/setup/notify_maintenance.py` — pre-restart user notification
- [ ] `NOTIFY_USERS_ON_UPDATE` flag in `bot.env` — ping approved users on startup after version bump
- [ ] Feature flags pattern in `bot.env` for gradual rollout

### 6.4 Hardware Upgrades 💡

- [ ] Pi 4 B upgrade — drops total latency ~115 s → ~15 s
- [ ] Pi 5 + NVMe upgrade — ~8 s total; full local LLM viable
- [ ] USB SSD — eliminates Piper model cold-start (15 s → 2 s), zero code changes

### 6.5 Recovery Testing 🔲

- [ ] Test full recovery on a different hardware device — flash image backup, restore all services, verify bot + voice + calendar come up cleanly on fresh Pi

---

## 7. Demo Features for Client Presentations 🔲

> Goal: demonstrate the assistant live via Telegram without needing guest user credentials.

### Level A — LLM only, <2 h each

| # | Feature | Button | Implementation |
|---|---|---|---|
| A1 | Weather — current weather for any city | 🌤 Weather | `curl wttr.in/<city>?format=3` — no API key |
| A2 | Translator — translate to any language | 🌍 Translate | LLM prompt |
| A3 | Date counter — days until event, day of week | 📅 Date | LLM + `datetime` |
| A4 | Calculator / converter — "100 lbs to kg" | 🧮 Calc | LLM reasoning |
| A5 | Idea generator — gifts, article topics, names | 💡 Ideas | LLM prompt |
| A6 | Fun fact on any topic | 🎲 Fact | LLM prompt |
| A7 | Joke / riddle | 😄 Joke | LLM prompt |

- [ ] A1: 🌤 button → city input → `subprocess curl wttr.in` → text + voice
- [ ] A2: 🌍 button → user types "to English: Привет мир" → LLM translates
- [ ] A3–A7: quick menu buttons → LLM one-shot generation

### Level B — Small helper, 2–4 h each

| # | Feature | Button | Implementation |
|---|---|---|---|
| B1 | Web search — find + summarise | 🔍 Search | `duckduckgo_search` pip, LLM summarises top-3 |
| B2 | Pi system status — CPU, RAM, temp, uptime | 📡 System | `psutil` + `/sys/class/thermal` |
| B3 | Timer / reminder — "remind me in 15 min" | ⏰ Timer | `threading.Timer` → Telegram push |
| B4 | Text summariser — paste long text → summary | 📊 Summary | LLM prompt via ForceReply |
| B5 | Text corrector — spelling, style, punctuation | ✏️ Correct | LLM prompt |
| B6 | Note formatter — draft → structured doc | 📋 Format | LLM prompt |
| B7 | Password generator — strong password by params | 🔐 Password | Python `secrets` |
| B8 | News headlines — top-5 from open RSS | 📰 News | `feedparser` pip, RSS lenta.ru / BBC-RU |

- [ ] B1: `pip install duckduckgo_search`; LLM summarises top-3 results
- [ ] B2: `psutil.cpu_percent()`, `psutil.virtual_memory()`, thermal zone → reply + voice
- [ ] B3: `threading.Timer(N*60, callback)` per user; `_pending_timers: dict[int, Timer]`
- [ ] B4–B6: ForceReply input → LLM prompt → formatted output
- [ ] B7: `secrets.choice` over character classes → show in `code` block
- [ ] B8: `feedparser.parse(RSS_URL)` → top-5 headlines → LLM summary

### Level C — Impressive, 4–8 h each

| # | Feature | Button | Implementation |
|---|---|---|---|
| C1 | Image analysis — user sends photo → description | 🖼 Photo | Multimodal LLM via OpenRouter (gpt-4o) |
| C2 | Interview trainer — practice Q&A by topic | 🎓 Interview | LLM dialog mode + voice |
| C3 | QR code generator — text/URL → image | 📷 QR | `qrcode` pip → PNG → `bot.send_photo()` |
| C4 | Mini quiz — 5 questions + inline answer buttons | 🏆 Quiz | LLM generates `{question, options[4], correct}` → InlineKeyboard |

- [ ] C1: photo handler → base64 → LLM vision prompt → text + voice
- [ ] C2: `_user_mode='interview'`; LLM asks questions and scores answers
- [ ] C3: `pip install qrcode pillow` → `qrcode.make(text)` → BytesIO → `send_photo()`
- [ ] C4: LLM generates JSON → `InlineKeyboardMarkup` with 4 options → score tracking

### Demo priority order

**Minimum (1 day):** A1 + A2 + B2 + B3 + C3 → shows voice, text, offline status, push notifications, multimedia
**Extended (2–3 days):** above + B1 + B4 + C1 + C4
**Flagship (already implemented):** Smart calendar — user says "remind me tomorrow at 10 for a team meeting", bot replies by voice "saved", sends reminder + morning briefing

---

## 8. Web UI & CRM Platform 💡

### 8.1 PicoUI Platform — FastAPI Web Interface ✅ Implemented (v2026.3.28)

All 5 phases deployed. New files: `bot_web.py`, `bot_auth.py`, `bot_llm.py`, `bot_ui.py`, `bot_actions.py`, `render_telegram.py`, 12 Jinja2 templates, `static/manifest.json`, `picoclaw-web.service` — running on OpenClawPI2 (HTTPS :8080).
See: `doc/architecture.md` §17 (Web UI Channel) and §18 (Screen DSL), `doc/web-ui/roadmap-web-ui.md`.

### 8.2 Multi-Channel Rendering ✅ Implemented (v2026.3.28)

Telegram (`render_telegram.py`) and Web (Jinja2 + HTMX via `bot_web.py`) renderers deployed. WhatsApp / Discord / Slack remain 💡 future ideas.

### 8.3 LLM Backend Abstraction ✅ Implemented (v2026.3.28)

`bot_llm.py` deployed. `picoclaw_cli` (default) and `openai_direct` backends live. `picoclaw_gateway` / `openclaw_gateway` HTTP backends 🔲 planned.

### 8.4 CRM Platform Vision 💡

**Long-term objective.** Core platform C0 — Screen DSL, auth, multi-channel rendering, LLM backend — complete (v2026.3.28). CRM-specific modules added per concrete customer project, never speculatively.

| CRM Phase | Scope | Depends on | Status |
|---|---|---|---|
| C0 | Core platform: Screen DSL, auth, multi-channel, LLM backend | P0–P4 | ✅ Done |
| C1 | Contact management: CRUD, search, link to notes/calendar/mail | P2 + C0 |
| C2 | Deals pipeline: stages, Kanban board in Web UI | C1 |
| C3 | Custom fields + workflows: admin-defined schema + automation | P4 + C2 |
| C4 | Customer project template: config-driven customization, white-label UI | C3 |

See: `doc/web-ui/roadmap-web-ui.md` §13 — CRM Platform Vision.

### 8.5 NiceGUI Integration 💡

**Nice to have — after FastAPI web UI is stable.**

Replace Jinja2 templates with NiceGUI for richer interactivity (sliders, live data binding, drag-and-drop). See `doc/web-ui/roadmap-web-ui.md` §12 and `doc/web-ui/mockups-nicegui/` for concept.

- [ ] Evaluate NiceGUI RAM footprint on Pi 3 B+ (~60 MB vs FastAPI ~25 MB)
- [ ] Prototype single page (e.g. Voice Opts toggles) in NiceGUI
- [ ] If viable: migrate pages incrementally behind feature flag

---

## 9. SQLite Data Layer 🔲

### 9.1 Decision: SQLite vs Files

Keep this decision matrix in mind when storing any new data:

| Data type | Store in | Reason |
|---|---|---|
| User records, roles, registration | ✅ **SQLite** | Filtering by status, relational joins, transactional approval |
| Calendar events | ✅ **SQLite** | Date-range queries, reminder scheduling, multi-user access |
| Notes metadata (title, mtime, tags) | ✅ **SQLite** | Fast listing, search/sort by title or date |
| Notes content | ✅ **files** (.md) | Git-trackable, rendered directly, binary-safe, no advantage in DB |
| Mail credentials | ✅ **SQLite** | Transactional updates, relational to users, simpler than per-user JSON |
| Chat history / conversation window | ✅ **SQLite** | Time-ordered queries, per-user windowed retrieval, large volume |
| Voice opts flags | ✅ **SQLite** | Per-user row in `voice_opts` table, merged with user record |
| TTS orphan tracker | ✅ **SQLite** | ACID guarantees for cleanup state |
| Bot secrets (`bot.env`) | ✅ **files** | Version-controlled template, never in DB |
| picoclaw config (`config.json`) | ✅ **files** | Owned by picoclaw binary, not our schema |
| LLM model selection (`active_model.txt`) | ✅ **files** | Single global value, changes rarely |
| Voice/audio model files (`.onnx`, Vosk) | ✅ **files** | Binary blobs, no query benefit |
| Error protocol bundles | 🔀 **hybrid** | Files stay on disk; manifest metadata row in SQLite |
| Static assets (CSS, JS, templates) | ✅ **files** | Served directly by FastAPI/Jinja2 |

**Guiding rule:** Use SQLite when you need to filter, sort, join, or update data across multiple users. Use files when data is a blob, config/secret, or benefits from git history.

### 9.2 Database File Location

| Environment | Path |
|---|---|
| Pi (production) | `~/.picoclaw/pico.db` |
| Local dev / tests | `~/.picoclaw/pico_test.db` (or `:memory:`) |

SQLite is ideal for Pi 3 B+: zero server process, single file, ~150 kB library overhead, ACID-safe. For the current user count (<10) and data volume (<10 MB) it is more than sufficient.

### 9.3 Schema Design 🔲

```sql
-- Core user table (replaces registrations.json + users.json)
CREATE TABLE IF NOT EXISTS users (
    chat_id     INTEGER PRIMARY KEY,
    username    TEXT,
    name        TEXT,
    role        TEXT    DEFAULT 'pending',  -- pending | approved | blocked | admin
    language    TEXT    DEFAULT 'ru',
    audio_on    INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    approved_at TEXT
);

-- Voice optimisation flags (replaces voice_opts.json)
CREATE TABLE IF NOT EXISTS voice_opts (
    chat_id          INTEGER PRIMARY KEY REFERENCES users(chat_id),
    silence_strip    INTEGER DEFAULT 0,
    low_sample_rate  INTEGER DEFAULT 0,
    warm_piper       INTEGER DEFAULT 0,
    parallel_tts     INTEGER DEFAULT 0,
    user_audio_toggle INTEGER DEFAULT 0,
    tmpfs_model      INTEGER DEFAULT 0,
    vad_prefilter    INTEGER DEFAULT 0,
    whisper_stt      INTEGER DEFAULT 0,
    piper_low_model  INTEGER DEFAULT 0,
    persistent_piper INTEGER DEFAULT 0,
    voice_timing_debug INTEGER DEFAULT 0
);

-- Calendar events (replaces calendar/<chat_id>.json)
CREATE TABLE IF NOT EXISTS calendar_events (
    id                TEXT    PRIMARY KEY,
    chat_id           INTEGER REFERENCES users(chat_id),
    title             TEXT    NOT NULL,
    dt_iso            TEXT    NOT NULL,
    remind_before_min INTEGER DEFAULT 15,
    reminded          INTEGER DEFAULT 0,
    created_at        TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_calendar_chat_dt ON calendar_events(chat_id, dt_iso);

-- Notes metadata index (content stays in .md files)
CREATE TABLE IF NOT EXISTS notes_index (
    slug        TEXT,
    chat_id     INTEGER REFERENCES users(chat_id),
    title       TEXT    NOT NULL,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (slug, chat_id)
);

-- Per-user mail credentials (replaces mail_creds/<chat_id>.json)
CREATE TABLE IF NOT EXISTS mail_creds (
    chat_id      INTEGER PRIMARY KEY REFERENCES users(chat_id),
    provider     TEXT,
    email        TEXT,
    imap_host    TEXT,
    imap_port    INTEGER DEFAULT 993,
    password_enc TEXT,     -- base64-encoded (obfuscation only; key in bot.env)
    target_email TEXT,
    updated_at   TEXT    DEFAULT (datetime('now'))
);

-- Conversation history per user (new — needed for memory feature)
CREATE TABLE IF NOT EXISTS chat_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER REFERENCES users(chat_id),
    role       TEXT    NOT NULL,  -- 'user' | 'assistant'
    content    TEXT    NOT NULL,
    created_at TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_history_chat_time ON chat_history(chat_id, created_at);

-- TTS orphan cleanup tracker (replaces pending_tts.json)
CREATE TABLE IF NOT EXISTS tts_pending (
    chat_id    INTEGER PRIMARY KEY,
    msg_id     INTEGER NOT NULL,
    created_at TEXT    DEFAULT (datetime('now'))
);
```

### 9.4 Migration Plan (files → SQLite) 🔲

Migration uses a **dual-write / read-prefer-DB** strategy to avoid data loss:

| Phase | Description | Risk |
|---|---|---|
| **Phase 1** — Schema creation | `CREATE TABLE IF NOT EXISTS` on startup; existing files untouched | Zero |
| **Phase 2** — Dual-write | New writes go to both DB and legacy files; reads from DB with file fallback | Zero |
| **Phase 3** — Migrate existing data | `src/setup/migrate_to_db.py --source=~/.picoclaw` reads all JSON files, inserts into DB | Low (idempotent) |
| **Phase 4** — DB-only reads | Remove file fallback; legacy files kept as read-only backup | Low |
| **Phase 5** — Archive legacy files | Move old JSONs to `~/.picoclaw/legacy_json_backup/` | Zero |

- [ ] Create `src/bot_db.py` — SQLite connection singleton, all CRUD helpers, `init_db()`, `migrate_from_files()`
- [ ] Schema: all 7 tables above with `CREATE TABLE IF NOT EXISTS` in `init_db()`
- [ ] `migrate_from_files()` — idempotent: skip rows that already exist in DB
- [ ] Call `init_db()` in `main()` before any handler registration
- [ ] Phase 2: dual-write wrappers for `_upsert_registration`, `_save_voice_opts`, `_cal_save`, `_save_note_file`, mail creds
- [ ] Phase 3: `src/setup/migrate_to_db.py` script (run once on first deploy with DB support)
- [ ] Add `pico.db` to `.gitignore` (runtime data — never committed)

### 9.5 New `bot_db.py` Module 🔲

```python
# Dependency chain position: bot_config → bot_db → bot_state → ...
import sqlite3, threading
_DB_PATH = os.path.join(PICOCLAW_DIR, 'pico.db')
_local = threading.local()   # per-thread connection (telebot uses threadpool)

def get_db() -> sqlite3.Connection:
    """Return thread-local SQLite connection, creating it if needed."""
    if not getattr(_local, 'conn', None):
        _local.conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

def init_db() -> None:
    """Create all tables on startup. Safe to call every time."""
    conn = get_db()
    conn.executescript(SCHEMA_SQL)   # SCHEMA_SQL = all CREATE TABLE IF NOT EXISTS
    conn.commit()
```

- [ ] `get_user(chat_id)` → Row or None
- [ ] `upsert_user(chat_id, username, name, role)` → replaces `_upsert_registration()`
- [ ] `get_voice_opts(chat_id)` → dict with defaults if no row
- [ ] `set_voice_opt(chat_id, key, value)` → replaces `_save_voice_opts()`
- [ ] `get_calendar_events(chat_id, from_dt, to_dt)` → list
- [ ] `upsert_calendar_event(chat_id, ev_dict)` → replaces `_cal_save()`
- [ ] `delete_calendar_event(ev_id)` → returns bool
- [ ] `get_chat_history(chat_id, limit=15)` → list of dicts (role, content)
- [ ] `append_history(chat_id, role, content)` → insert row
- [ ] `trim_history(chat_id, keep=15)` → delete oldest beyond window

### 9.6 Testing Changes 🔲

- [ ] Add voice regression test **T22 `sqlite_schema`**: `init_db()` creates all tables; `get_user()` / `upsert_user()` round-trips correctly; `get_calendar_events()` with date filter returns correct subset
- [ ] Add **T23 `migration_idempotent`**: run `migrate_from_files()` twice on same source → no duplicate rows, no error
- [ ] Update T18 (`profile_resilience`) to test that `_handle_profile()` reads from DB when available
- [ ] All existing tests must pass with DB initialised (use `:memory:` DB for test isolation)
