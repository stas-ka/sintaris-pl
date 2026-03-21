# Taris — Feature Domains

**Version:** `2026.3.28`  
→ Architecture index: [architecture.md](../architecture.md)

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
