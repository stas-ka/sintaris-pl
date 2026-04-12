# Taris — Feature Domains

**Version:** `2026.4.50`  
→ Architecture index: [architecture.md](../architecture.md)

---

## 6. System Chat (Admin Panel)

> **Note:** System Chat was moved from the main menu to the **Admin Panel** in v2026.3.43. It is now accessible only to **Admin** and **Developer** users via Admin Panel → System → 🖥️ System Chat.

`_handle_system_chat(chat_id, text)` in `bot_handlers.py` — translates the user's plain-language request into a shell command via the LLM, shows the command for confirmation, then executes it with `_run_subprocess()` and returns the output.

---

## 7. Per-User Mail System (`bot_mail_creds.py`)

Each user configures their own IMAP mailbox. The legacy shared `gmail_digest.py` cron job is deprecated in favour of this module.

### 7.1 Setup Flow

```
User taps 📧 Mail → handle_digest_auth()
  → no creds: show consent gate (GDPR Art. 6(1)(a) + 152-FZ)
  → User agrees → provider selection: Gmail / Yandex / Mail.ru / Custom
  → User selects → prompt email address (ForceReply)
  → User types email → prompt App Password (ForceReply)
  → finish_mail_setup(): test IMAP → save creds → show digest
```

### 7.2 Storage

| File | Contents |
|---|---|
| `~/.taris/mail_creds/<chat_id>.json` | `{provider, email, password, imap_host, imap_port}` — chmod 600 |
| `~/.taris/mail_creds/<chat_id>_last_digest.txt` | Last digest text cache |
| `~/.taris/mail_creds/<chat_id>_target.txt` | SMTP send-to address |

### 7.3 Digest Pipeline

```
_fetch_and_summarize(chat_id)
  → IMAP4_SSL connect with stored creds
  → fetch INBOX + Spam/Junk (last 24h, max 50 each)
  → _build_digest_prompt() → _ask_taris(prompt, timeout=120)
  → cache to _last_digest_file(chat_id)
  → return summary text
```

Refresh runs in a background thread so the main bot thread is not blocked.

### 7.4 Providers

| Provider | IMAP Host | Notes |
|---|---|---|
| Gmail | `imap.gmail.com:993` | Requires App Password (2FA enabled) |
| Yandex | `imap.yandex.ru:993` | Requires App Password |
| Mail.ru | `imap.mail.ru:993` | Requires App Password |
| Custom | User-supplied | Arbitrary IMAP host + port |

---

## 8. Smart Calendar (`bot_calendar.py`)

### 8.1 Add Event Flow (single event)

```
User writes: "встреча с командой завтра в 11 утра"
  → _finish_cal_add(chat_id, text)
  → _ask_taris(): extract JSON {"events": [{title, dt}, ...]}
  → 1 event → _show_cal_confirm(): review card
    → User taps ✅ → _cal_do_confirm_save()
    → _cal_add_event(): save to calendar JSON
    → _schedule_reminder(): threading.Timer
```

### 8.2 Multi-Event Add Flow

```
User writes: "завтра в 10 команда, в 15 врач, в 19 ужин с Машей"
  → _finish_cal_add() → LLM returns {"events": [{...}, {...}, {...}]}
  → 3 events → _pending_cal = {step: "multi_confirm", events: [...], idx: 0}
  → _show_cal_confirm_multi(): "Event 1 of 3 — review:"
    → Save   → _cal_multi_save_one() → advance to next
    → Skip   → _cal_multi_skip()     → advance to next
    → Save All → _cal_multi_save_all() → save remaining without further confirmation
    → Cancel → discard all remaining
```

### 8.3 NL Query Flow

```
User writes: "что у меня на следующей неделе?"
  → _handle_calendar_query(chat_id, text)
  → _ask_taris(): extract {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "label": "..."}
  → filter _cal_load() by date range
  → display formatted list with countdown
```

### 8.4 Calendar Console

```
User taps 💬 Консоль → _start_cal_console()
  → _user_mode = "cal_console"
  → User types free-form command
  → _handle_cal_console(): LLM classifies intent
      add    → _finish_cal_add()
      query  → _handle_calendar_query()
      delete → _handle_cal_delete_request()  (confirmation required)
      edit   → _handle_cal_event_detail()
```

### 8.5 Delete Confirmation

```
User taps 🗑 Delete
  → _handle_cal_delete_request(): show event + ✅ Confirm / ❌ Cancel
  → User taps ✅ → _handle_cal_delete_confirmed(): remove + cancel timer
```

### 8.6 Background Threads

| Thread | Purpose |
|---|---|
| `threading.Timer` per event | Fire reminder at `event_dt − remind_before_min`; rebuilt on startup |
| `_cal_morning_briefing_loop()` | Daemon thread: sends today's event summary at `_BRIEFING_HOUR = 8` (08:00) |

### 8.7 Storage

`~/.taris/calendar/<chat_id>.json` — list of events: `[{id, title, dt_iso, remind_before_min, reminded}]`

---

## 9. Send as Email (`bot_email.py`)

Sends notes, digest, and calendar events to a target address using the user's own IMAP mailbox as the SMTP sender.

```
User taps 📧 Send as email
  → _get_target_email(chat_id)          ← read …_target.txt; prompt if absent
  → _load_creds(chat_id)
  → _smtp_host_port(imap_host)          ← infer smtp.*.* from imap.*.*
  → _send_in_thread(): smtplib SMTP_SSL connect → send MIMEText
  → show ✅ Sent confirmation
```

---

## 10. User Registration & Profile

### 10.1 Registration Flow

```
Unknown user sends /start
  → not in any allowed set → _user_mode[cid] = "reg_name"
  → prompt "Enter your name"
  → _finish_registration(): _upsert_registration(cid, name, "pending")
  → notify all admins with inline ✅ Approve / ❌ Block buttons

Admin approves → add to _dynamic_users; send approval message to user
Admin blocks   → set status "blocked"
```

### 10.2 Profile View

`_handle_profile(chat_id)` shows: full name, Telegram username, chat ID, role, registration date, masked email (if mail creds configured).

---

## 11. FTS5/RAG Knowledge Base (`bot_documents.py`, `store_sqlite.py`)

> 🧪 **BETA** — PicoClaw uses SQLite FTS5; OpenClaw uses PostgreSQL + pgvector.

### 11.1 Upload Flow

```
Admin opens Web UI → POST /admin/rag/upload (multipart file)
  → bot_documents.py: read file, split into chunks (RAG_CHUNK_SIZE chars)
  → store_sqlite.index_document(chunks): INSERT INTO fts_documents VALUES (...)
  → FTS5 virtual table auto-indexes content
```

### 11.2 Retrieval Flow (per chat message)

```
User sends message
  → bot_llm.py: if RAG_ENABLED and not flag-file present:
       store_sqlite.search_fts(query=text, top_k=RAG_TOP_K)
       → SELECT … FROM fts_documents WHERE fts_documents MATCH ?
       → returns top-K chunks sorted by BM25 rank
  → chunks prepended to LLM system prompt as "Context:"
  → LLM answer is grounded in uploaded documents
```

### 11.3 Runtime Toggle

The admin can enable/disable RAG at runtime without restarting the bot:

- Admin panel → 🔍 RAG / Knowledge Base button
- Writes or removes `RAG_FLAG_FILE` (`~/.taris/rag_disabled`)
- `bot_llm.py` checks flag-file presence on every request

### 11.4 Configuration Constants (`bot_config.py`)

| Constant | Default | Env var | Description |
|---|---|---|---|
| `RAG_ENABLED` | `true` | `RAG_ENABLED` | Master on/off switch |
| `RAG_TOP_K` | `3` | `RAG_TOP_K` | Max chunks injected per LLM request |
| `RAG_CHUNK_SIZE` | `512` | `RAG_CHUNK_SIZE` | Characters per chunk when indexing |
| `RAG_FLAG_FILE` | `~/.taris/rag_disabled` | — | Flag file; presence = RAG off (runtime toggle) |

### 11.5 Key Functions

| Function | Location | Description |
|---|---|---|
| `store_sqlite.index_document(chunks)` | `store_sqlite.py` | Insert chunked text into FTS5 table |
| `store_sqlite.search_fts(query, top_k)` | `store_sqlite.py` | BM25-ranked FTS5 search, returns top-K chunks |
| `store_sqlite.update_document_field(doc_id, field, value)` | `store_sqlite.py` | Update a single metadata field on a document row |
| `store_sqlite.get_document_by_hash(chat_id, doc_hash)` | `store_sqlite.py` | Lookup existing document by SHA256 hash (dedup) |
| `_rag_context(text)` | `bot_llm.py` | Calls `search_fts`, formats chunks for prompt injection |
| `POST /admin/rag/upload` | `bot_web.py` | Web UI upload endpoint (admin-only) |

### 11.6 Runtime RAG Settings (Admin Panel, v2026.3.30+2)

Admins can tune RAG parameters at runtime without restarting via **Admin Panel → 🔍 RAG Settings**:

| Setting | Callback | Default | Description |
|---|---|---|---|
| Top-K chunks | `admin_rag_set_topk` | `RAG_TOP_K` (env) | How many chunks to inject per LLM call |
| Chunk size | `admin_rag_set_chunk` | `RAG_CHUNK_SIZE` (env) | Characters per chunk during indexing |
| RAG timeout | `admin_rag_set_timeout` | `RAG_TIMEOUT` (env) | FTS search timeout (seconds) |

Settings are stored in `~/.taris/rag_settings.json` and read by `core/rag_settings.py` (`get(key)` / `set_value(key, val)`).

### 11.7 Document Admin (v2026.3.30+2)

| Feature | Description |
|---|---|
| Detail view | `doc_detail:<id>` → shows type, chunks, size, shared flag, created date |
| Rename | `doc_rename:<id>` → input mode `doc_rename` → `doc_rename_confirm:<id>` |
| Share toggle | `doc_share:<id>` → flips `shared` flag (shared docs visible to all users) |
| Delete | `doc_del:<id>` → confirm → `doc_del_confirm:<id>` |
| Hash dedup | SHA256 hash stored in `doc_hash` column; upload skipped if hash already exists for user |
| Upload stats | `char_count`, `n_chunks`, `file_size_bytes`, `parse_time_ms` stored in document metadata |

## 12. Notes (`bot_users.py`, `bot_handlers.py`)

Personal user notes stored as Markdown files under `~/.taris/notes/<chat_id>/`.

### 12.1 Note Actions

| Action | Callback | Description |
|---|---|---|
| View note | `note_open:<hash>` | Shows full note text with Edit/Delete/Download buttons |
| Append | `note_append:<hash>` → `note_append_content` mode | Appends text to existing note; returns to note view |
| Replace | `note_edit:<hash>` → `note_edit_content` mode | Replaces note body; returns to note view |
| Rename Title | `note_rename:<hash>` → `note_rename_title` mode | Sets new title (≤100 chars); rebuilds `# Title\n\nbody` format |
| Delete (confirm) | `note_delete:<hash>` → confirm dialog → `note_del_confirm:<hash>` | Two-step delete with Yes/Cancel |
| Download single | `note_download:<hash>` | Sends note as `.md` file |
| Download all (ZIP) | `note_download_zip` | Packs all user notes in-memory via `io.BytesIO` + `zipfile.ZipFile`; sent as `notes.zip` |

### 12.2 Storage

- Primary: `~/.taris/notes/<chat_id>/<slug>.md` (file)
- Index: `notes_index` SQLite table (`slug, chat_id, title, created_at, updated_at`)
- `_list_notes_for()` reads from DB first; falls back to file scan if DB empty
- `_save_note_file()` writes file + direct DB upsert (no double-write via `store.save_note()`)

### 12.3 Callback Hash IDs

Notes use `_note_cb_id(slug) → short_hex` to stay within Telegram's 64-byte callback_data limit.
A per-session dict `_note_cb_map` maps short IDs back to full slugs.

---

## 13. Campaign Email Agent (`bot_campaign.py`) ✅ v2026.4.50

**When to read:** When modifying the campaign workflow, N8N webhook integration, client selection, or email sending.

Taris provides an AI-assisted email broadcast agent accessible via the Agents menu (advanced/admin users only).

### 13.1 Trigger Flow

```
Agents menu → 📧 Campaign
  → Enter topic ("LR Webinar am 15.04")
  → Enter filters (e.g. "Interessen: Fitness") or "-" for all
  → Taris → POST /webhook/taris-campaign-select → N8N (sync)
  ← N8N returns {clients: [...], template: "...", count: N}
  → Taris shows preview: N clients + email template
  → Buttons: [✅ Send] [✏️ Edit template] [❌ Cancel]
  → User confirms → Taris → POST /webhook/taris-campaign-send → N8N (sync)
  ← N8N returns {sent_count: N, errors: [...], sheet_url: "..."}
  → Taris shows summary + Google Sheets status link
```

### 13.2 N8N Workflows

| Workflow | File | Webhook Path | ID |
|---|---|---|---|
| Campaign Select | `src/n8n/workflows/Taris - Campaign Select.json` | `/webhook/taris-campaign-select` | `YF9eU2H2N3Nr4j3O` |
| Campaign Send | `src/n8n/workflows/Taris - Campaign Send.json` | `/webhook/taris-campaign-send` | `AjIB5izjiCunMcp6` |

#### Campaign Select — 10 nodes

| Node | Type | What it does |
|---|---|---|
| Webhook | webhook | Receives `{session_id, topic, filters, sheet_id, demo_mode}` |
| Demo Mode? | if | Routes to Demo Clients (true) or GS Read Clients (false) |
| Demo Clients | code | Returns hardcoded demo client list |
| GS Read Clients | googleSheets | Reads "клиенты" tab from CAMPAIGN_SHEET_ID |
| Prepare Prompt | code | Builds GPT prompt: topic + filters + client list |
| OpenAI Select | openAi | gpt-4o-mini selects matching clients → JSON list |
| Parse Response | code | Strips markdown fences; parses JSON; checks `_error` |
| GS Read Templates | googleSheets | Reads "Шаблоны рассылки" tab; `onError=continueRegularOutput` |
| Merge Template | code | Prefers GS template over AI-generated when topic matches |
| Respond | respondToWebhook | Returns `{clients, template, count}` |

#### Campaign Send — 8 nodes

| Node | Type | What it does |
|---|---|---|
| Webhook Send | webhook | Receives `{session_id, topic, clients, template, sheet_id}` |
| Expand Clients | code | Creates one item per client; injects topic/template |
| GS Append Queued | googleSheets | Writes `Status="Gesendet wird..."` to "Status рассылок" **before** send; `onError=continueRegularOutput` |
| Send Email Gmail | gmail | Sends personalized email per client via Gmail OAuth2 |
| Prepare Sheet Row | code | Builds `{Datum, Empfaenger, Name, Firma, Thema, Status}` row |
| GS Append Status | googleSheets | Writes `Status="sent"/"ERROR:..."` to "Status рассылок" **after** send; `onError=continueRegularOutput` |
| Summary | code | Aggregates sent_count, errors, sheet_url |
| Respond Send | respondToWebhook | Returns summary to Taris |

### 13.3 Google Sheets Structure

**Spreadsheet ID:** `CAMPAIGN_SHEET_ID` env var (default: `1jQaJZA4cBS2sLtE42zpwDHMn6grvDBAqoK_8Sp6PmXA`)

| Tab | Columns | Purpose |
|---|---|---|
| `клиенты` | Имя, Email, Компания, Тип, Интересы, Теги, Комментарии | Source client data |
| `Шаблоны рассылки` | Тема, Шаблон | Pre-written email templates |
| `Status рассылок` | Datum, Empfaenger, Name, Firma, Thema, Status | Execution log (written by GS Append Queued + GS Append Status) |

> ⚠️ The "Status рассылок" tab must exist with headers: `Datum | Empfaenger | Name | Firma | Thema | Status`

### 13.4 Key Files

| File | Role |
|---|---|
| `src/features/bot_campaign.py` | Campaign state machine, `call_webhook()`, `_user_friendly_error()`, `_STEP_KEY_MAP` |
| `src/telegram_menu_bot.py` | `agents_menu`, `campaign_start`, `campaign_confirm_send`, `campaign_edit_template`, `campaign_cancel` callbacks |
| `src/strings.json` | 29 `campaign_*` i18n keys (ru/en/de) |
| `src/n8n/workflows/Taris - Campaign Select.json` | Campaign Select N8N workflow |
| `src/n8n/workflows/Taris - Campaign Send.json` | Campaign Send N8N workflow |
| `src/tests/test_campaign.py` | 40 unit tests (T50–T57 + runtime/e2e) |

### 13.5 Config Constants (`bot_config.py`)

```python
N8N_CAMPAIGN_SELECT_WH = os.environ.get("N8N_CAMPAIGN_SELECT_WH", "")
N8N_CAMPAIGN_SEND_WH   = os.environ.get("N8N_CAMPAIGN_SEND_WH", "")
CAMPAIGN_SHEET_ID      = os.environ.get("CAMPAIGN_SHEET_ID", "1jQaJZA4cBS2sLtE42zpwDHMn6grvDBAqoK_8Sp6PmXA")
CAMPAIGN_FROM_EMAIL    = os.environ.get("CAMPAIGN_FROM_EMAIL", "info@sintaris.net")
CAMPAIGN_DEMO_MODE     = os.environ.get("CAMPAIGN_DEMO_MODE", "false").lower() == "true"
```

### 13.6 Access Control

Only `advanced` and `admin` users can access the Agents menu and campaign workflows.  
Role set by admin via Admin Panel → Users → Set Role.
