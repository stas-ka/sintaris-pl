# 2. N8N Workflow — Рассылка по отобранным клиентам

**When to read:** When modifying the campaign workflow, N8N webhook integration, or the Taris campaign agent.

## Overview

Taris acts as a console for triggering AI-assisted email campaigns via N8N.  
Data source: Google Sheets `1jQaJZA4cBS2sLtE42zpwDHMn6grvDBAqoK_8Sp6PmXA`

---

## Algorithm

```
User → Taris Agents menu → "Рассылка"
  ↓
Step 1: Enter campaign topic (e.g. "Приглашение на вебинар по LR")
  ↓
Step 2: Optional client filters (type, interests, tags — or skip)
  ↓
Taris → POST /webhook/taris-campaign-select (synchronous, waits for N8N response)
  N8N workflow:
    1. Read all clients from Google Sheets tab "клиенты"
    2. GPT-4o-mini: select matching clients based on topic + filters → JSON list
    3. Check "Шаблоны рассылки" tab for existing template matching topic
    4. If no template: GPT-4o-mini generates personalized template with {{name}}, {{company}} placeholders
    5. Return JSON: {clients: [...], template: "...", session_id: "..."}
  ↓ (HTTP response from N8N)
Taris shows preview:
  - "Found N clients"
  - Template preview
  - Buttons: [✅ Send] [✏️ Edit template] [❌ Cancel]
  ↓ (user may edit template)
User confirms → Taris → POST /webhook/taris-campaign-send (synchronous)
  N8N workflow:
    1. Parse approved clients list + template from request
    2. For each client: fill template with {{name}}, {{company}}, etc.
    3. Send Gmail
    4. Append row to "Статус рассылок" tab: date, topic, name, email, status, sent_at
    5. Return JSON: {sent_count: N, errors: [...], sheet_url: "..."}
  ↓
Taris notifies user: "Sent N emails. Status: [Google Sheets link]"
```

---

## N8N Workflows

| Workflow | Webhook Path | Credentials Used |
|---|---|---|
| Taris Campaign Select | `/webhook/taris-campaign-select` | Google Sheets (j36NScu4bpqsYJKT), OpenAI (MHkmfl85kwu22LT8) |
| Taris Campaign Send | `/webhook/taris-campaign-send` | Google Sheets (j36NScu4bpqsYJKT), Gmail (OM7qAUKDjlYrrRsI) |

Both use **Respond to Webhook** mode (synchronous response, no callback URL needed).

---

## Google Sheets Structure

**Spreadsheet ID:** `1jQaJZA4cBS2sLtE42zpwDHMn6grvDBAqoK_8Sp6PmXA`

| Tab | Columns | Purpose |
|---|---|---|
| `клиенты` | Имя, Фамилия, Email, Телефон, Компания, Тип, Интересы, Комментарии, Теги | Source client data |
| `Шаблоны рассылки` | Тема, Шаблон, Дата | Email templates per campaign topic |
| `Статус рассылок` | Дата, Тема, Имя, Email, Статус, Дата отправки | Campaign execution log |

---

## Taris Components

| File | Role |
|---|---|
| `src/features/bot_campaign.py` | Campaign agent: state tracking, N8N calls, Telegram UI flow |
| `src/telegram_menu_bot.py` | Agents menu + callbacks: `agents_menu`, `campaign_start`, `campaign_confirm_send`, `campaign_edit_template`, `campaign_cancel` |
| `src/strings.json` | i18n keys: `agents_menu_*`, `campaign_*` |
| `src/tests/test_campaign.py` | Tests T50-T59 (source inspection + runtime) |

**Key constants in `bot_config.py`:**
```python
N8N_CAMPAIGN_SELECT_WH = os.environ.get("N8N_CAMPAIGN_SELECT_WH", "")   # webhook URL
N8N_CAMPAIGN_SEND_WH   = os.environ.get("N8N_CAMPAIGN_SEND_WH", "")
CAMPAIGN_SHEET_ID      = os.environ.get("CAMPAIGN_SHEET_ID", "1jQaJZA4cBS2sLtE42zpwDHMn6grvDBAqoK_8Sp6PmXA")
```

**In `bot.env` on TariStation2:**
```
N8N_CAMPAIGN_SELECT_WH=${N8N_URL}/webhook/taris-campaign-select
N8N_CAMPAIGN_SEND_WH=${N8N_URL}/webhook/taris-campaign-send
CAMPAIGN_SHEET_ID=***  # from .env CAMPAIGN_SHEET_ID
```

---

## Campaign State Machine (in Taris memory)

```
IDLE → topic_input → filter_input → waiting_preview → preview_shown → template_edit → sending → done
```

State stored in `_campaigns: dict[int, dict]` keyed by chat_id:
```python
{
  "step": "topic_input",       # current step
  "topic": "...",              # campaign topic
  "filters": "...",            # optional filters
  "clients": [...],            # list from N8N preview
  "template": "...",           # current template text
  "session_id": "uuid",        # links to N8N execution
}
```

---

## What was NOT implemented (simplifications vs. original spec)

| Original spec | Actual implementation | Reason |
|---|---|---|
| Template stored back to Google Sheets | Only status rows saved | Reduces complexity, templates are generated each time |
| Link with filter pre-applied | Generic status sheet URL | Google Sheets filter URLs are complex |
| Taris tells N8N about new template | Template passed directly in send request | Simpler, avoids two-phase template save |
| `info@sintaris.net` as From: address | Gmail OAuth2 sends from the OAuth account | Gmail node cannot override From: for OAuth credentials |

## What IS implemented (v2026.4.50)

| Feature | Status |
|---|---|
| GS Append Queued (Status="Gesendet wird..." BEFORE send) | ✅ v2026.4.50 |
| GS Append Status (Status="sent"/"ERROR:..." AFTER send) | ✅ v2026.4.50 |
| demo_mode IF branch in Campaign Select | ✅ v2026.4.48 |
| Native N8N nodes: OpenAI, Gmail, Google Sheets | ✅ v2026.4.48 |
| Parse Response: strip markdown fences before JSON.parse | ✅ v2026.4.47 |
| Error handling in Parse Response (returns `{_error: true}`) | ✅ v2026.4.47 |
| CAMPAIGN_FROM_EMAIL + CAMPAIGN_DEMO_MODE env vars | ✅ v2026.4.46 |
| `_STEP_KEY_MAP` with GS Append Queued + Send Email Gmail | ✅ v2026.4.50 |

## N8N Workflow Files (v2026.4.50)

| File | Workflow Name | Nodes |
|---|---|---|
| `src/n8n/workflows/Taris - Campaign Select.json` | Taris - Campaign Select | 10 |
| `src/n8n/workflows/Taris - Campaign Send.json` | Taris - Campaign Send | 8 |

> **Note:** Old filenames `taris-campaign-select.json` / `taris-campaign-send.json` were renamed by user in v2026.4.50. Webhook URL paths (`/webhook/taris-campaign-select`, `/webhook/taris-campaign-send`) are unchanged.

---

## Tests

| ID | Name | What it checks |
|---|---|---|
| T50 | campaign_config_constants | N8N_CAMPAIGN_SELECT_WH, N8N_CAMPAIGN_SEND_WH, CAMPAIGN_SHEET_ID in bot_config.py |
| T51 | campaign_module_functions | start_campaign, on_topic, on_filter, on_preview, confirm_send in bot_campaign.py |
| T52 | campaign_state_machine | _campaigns dict, step transitions defined |
| T53 | campaign_i18n_keys | All campaign_* keys in ru/en/de |
| T54 | campaign_callbacks | campaign_start, campaign_confirm, campaign_cancel in telegram_menu_bot.py |
| T55 | agents_menu | agents_menu callback + 📧 button present |
| T56 | n8n_select_webhook_url | N8N_CAMPAIGN_SELECT_WH format validation |
| T57 | n8n_send_webhook_url | N8N_CAMPAIGN_SEND_WH format validation |
| T58 | campaign_runtime_n8n | Live connection to N8N select webhook (SKIP if not configured) |
| T59 | campaign_runtime_send | Live send test (SKIP always unless explicit flag set) |
