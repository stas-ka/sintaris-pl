---
name: taris-n8n
description: >
  Manage N8N workflows on the configured VPS (VPS_N8N_HOST from .env): list, create,
  activate/deactivate, test webhooks, inspect executions, and create campaign workflows.
  Use when: creating/updating N8N workflows, debugging webhook calls, setting up
  campaign automation, testing N8N connectivity, managing workflow lifecycle.
argument-hint: 'task: status | list | create-campaign | test-webhook | create <file> | executions | activate/deactivate <id>'
---

# N8N Admin Skill — taris

Manages N8N workflows via the **`tools/n8n/n8n_admin.py`** CLI.  
All credentials and URLs are read from `.env` in the project root automatically.

---

## Quick Reference

| Command | What it does |
|---|---|
| `python tools/n8n/n8n_admin.py status` | Connectivity check + workflow count |
| `python tools/n8n/n8n_admin.py list` | List all workflows (id, active, name) |
| `python tools/n8n/n8n_admin.py list --active` | Active workflows only |
| `python tools/n8n/n8n_admin.py show <id>` | Full workflow JSON |
| `python tools/n8n/n8n_admin.py activate <id>` | Activate workflow |
| `python tools/n8n/n8n_admin.py deactivate <id>` | Deactivate workflow |
| `python tools/n8n/n8n_admin.py delete <id>` | Delete workflow (prompts confirmation) |
| `python tools/n8n/n8n_admin.py create <file.json>` | Create workflow from JSON file |
| `python tools/n8n/n8n_admin.py create-campaign` | Create campaign select+send workflows |
| `python tools/n8n/n8n_admin.py test-webhook <url> [json]` | POST to webhook + show response |
| `python tools/n8n/n8n_admin.py executions [--wf <id>] [--limit N]` | Recent executions |

---

## Environment (from `.env`)

| Variable | Purpose |
|---|---|
| `VPS_N8N_HOST` | N8N base URL (e.g. `https://<your-vps-hostname>`) |
| `VPS_N8N_API_KEY` | N8N API key (JWT) |
| `VPS_N8N_API_BASE` | Legacy — `n8n_admin.py` builds its own from `VPS_N8N_HOST` |

---

## N8N Direct API (when using `_api()` in Python code)

```
Base: ${VPS_N8N_HOST}/api/v1
Auth: X-N8N-API-KEY header

GET  /workflows?limit=200          — list workflows
GET  /workflows/<id>               — get single workflow
POST /workflows                    — create workflow
POST /workflows/<id>/activate      — activate
POST /workflows/<id>/deactivate    — deactivate
DELETE /workflows/<id>             — delete
GET  /executions?limit=N&workflowId=<id>&status=<s>  — list executions
GET  /executions/<id>              — get execution detail

Webhook trigger (production mode, no auth):
POST ${VPS_N8N_HOST}/webhook/<path>

Test webhook (test mode, no activation needed):
POST ${VPS_N8N_HOST}/webhook-test/<path>
```

---

## Reusable N8N Credential IDs

> Credential IDs are specific to your N8N instance. Find them via:  
> `python tools/n8n/n8n_admin.py status` → check N8N UI under Credentials.

| Service | Variable in `.env` | Purpose |
|---|---|---|
| Google Sheets | `VPS_N8N_CRED_GSHEETS` | Google Sheets OAuth credential |
| OpenAI | `VPS_N8N_CRED_OPENAI` | OpenAI API credential |
| Gmail | `VPS_N8N_CRED_GMAIL` | Gmail OAuth credential |

Always reference these by their N8N-assigned IDs when creating workflows — do NOT create new credentials.

---

## Campaign Workflows (Taris Integration)

### What they do

| Workflow | Webhook path | Input | Output |
|---|---|---|---|
| **Taris - Campaign Select** | `/webhook/taris-campaign-select` | `{session_id, topic, filters}` | `{clients: [...], template: "..."}` |
| **Taris - Campaign Send** | `/webhook/taris-campaign-send` | `{session_id, topic, clients: [...], template}` | `{sent_count: N, sheet_url: "..."}` |

Both use **synchronous response mode** (N8N `Respond to Webhook` node) — Taris POSTs and waits for the JSON reply.

### Create/Recreate Campaign Workflows

```bash
python tools/n8n/n8n_admin.py create-campaign
```

This creates both workflows and activates them. If they already exist, delete them first:

```bash
# Find IDs
python tools/n8n/n8n_admin.py list | grep -i campaign

# Delete old ones
python tools/n8n/n8n_admin.py delete <SELECT_ID>
python tools/n8n/n8n_admin.py delete <SEND_ID>

# Recreate
python tools/n8n/n8n_admin.py create-campaign
```

### Test Campaign Webhooks

Read webhook URLs from `.env` (`N8N_CAMPAIGN_SELECT_WH`, `N8N_CAMPAIGN_SEND_WH`) or use:

```bash
# After create-campaign, the URLs are printed — copy from there
# Test SELECT (expects clients + template in response)
python tools/n8n/n8n_admin.py test-webhook \
  "${VPS_N8N_HOST}/webhook/taris-campaign-select" \
  '{"session_id":"test-1","topic":"Приглашение на вебинар","filters":""}'

# Test SEND (expects sent_count + sheet_url)
python tools/n8n/n8n_admin.py test-webhook \
  "${VPS_N8N_HOST}/webhook/taris-campaign-send" \
  '{"session_id":"test-1","topic":"Тест","clients":[{"Имя":"Тест","Email":"test@example.com"}],"template":"Привет {name}!"}'
```

---

## Creating Custom Workflows

### 1. Define in Python (preferred — avoids shell escaping)

Add workflow definition function to `tools/n8n/n8n_admin.py` following the pattern of `_campaign_select_workflow()`:

```python
def _my_workflow() -> dict:
    return {
        "name": "My Workflow",
        "nodes": [...],       # list of node dicts
        "connections": {...}, # dict of node-name → connections
        "settings": {"executionOrder": "v1"}
    }
```

Node structure:
```python
{
    "id": "unique-id",
    "name": "Node Name",              # must match connection keys
    "type": "n8n-nodes-base.webhook", # node type
    "typeVersion": 2,
    "position": [x, y],
    "parameters": {...},
    "credentials": {"credType": {"id": "...", "name": "..."}}  # optional
}
```

### 2. Define in JSON file and create

```bash
python tools/n8n/n8n_admin.py create my_workflow.json
python tools/n8n/n8n_admin.py activate <returned-id>
```

---

## Webhook Node Pattern

```python
# Webhook trigger with synchronous response (Respond to Webhook)
{
    "type": "n8n-nodes-base.webhook",
    "typeVersion": 2,
    "parameters": {
        "httpMethod": "POST",
        "path": "my-unique-path",
        "responseMode": "responseNode",   # wait for Respond node
        "options": {}
    }
}

# Respond node (must be last in chain)
{
    "type": "n8n-nodes-base.respondToWebhook",
    "typeVersion": 1,
    "parameters": {
        "respondWith": "json",
        "responseBody": '={{ JSON.stringify($json) }}',
        "options": {}
    }
}
```

---

## Google Sheets Node Pattern

```python
# Read sheet
{
    "type": "n8n-nodes-base.googleSheets",
    "typeVersion": 4,
    "parameters": {
        "operation": "read",
        "documentId": {"__rl": True, "value": "SHEET_ID", "mode": "id"},
        "sheetName": {"__rl": True, "value": "Tab Name", "mode": "name"},
        "options": {}
    },
    "credentials": {"googleSheetsOAuth2Api": {"id": "j36NScu4bpqsYJKT", "name": "Google Sheets account 3"}}
}

# Append row
{
    "parameters": {
        "operation": "append",
        "documentId": {"__rl": True, "value": "SHEET_ID", "mode": "id"},
        "sheetName": {"__rl": True, "value": "Tab Name", "mode": "name"},
        "columns": {"mappingMode": "autoMapInputData", "value": {}},
        "options": {}
    },
    ...
}
```

---

## Code Node Pattern

```python
{
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "parameters": {
        "mode": "runOnceForAllItems",   # or "runOnceForEachItem"
        "jsCode": "..."                 # JavaScript string
    }
}
```

In `jsCode` — access previous nodes via:
- `$('Node Name').first().json`  — first item from node
- `items` — all input items (as `[{json: {...}}]`)
- `$json` — shorthand for current item's json

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Workflow not found | Use `list` command to find correct ID |
| Webhook 404 | Workflow must be **active** (not just created) |
| Webhook times out | N8N has `responseMode: "responseNode"` — check last node is Respond |
| N8N API 401 | Check `VPS_N8N_API_KEY` in `.env` |
| Code node error | Check N8N execution log: `executions --wf <id> --limit 5` |
| Google Sheets auth | Credential `j36NScu4bpqsYJKT` must have valid OAuth token |
| Campaign SELECT returns empty | Check Google Sheet tab name is exactly "клиенты" |

---

## Post-Create Checklist

After creating or modifying any workflow:

1. `python tools/n8n/n8n_admin.py list --active` — confirm workflow appears
2. `python tools/n8n/n8n_admin.py test-webhook <url> '{...}'` — smoke test
3. If test fails, check: `python tools/n8n/n8n_admin.py executions --wf <id> --limit 3`
4. Update `bot.env` on TariStation2 if webhook URLs changed
5. Verify Taris can reach the webhook: send a test campaign from the Agents menu

---

## Files

| File | Purpose |
|---|---|
| `tools/n8n/n8n_admin.py` | CLI tool — all workflow management commands |
| `src/features/bot_n8n.py` | Taris-side N8N adapter (REST API calls, callback registry) |
| `src/features/bot_campaign.py` | Campaign agent (orchestrates select+send webhooks) |
| `src/core/bot_config.py` | N8N_URL, N8N_API_KEY, N8N_CAMPAIGN_SELECT_WH, N8N_CAMPAIGN_SEND_WH |
| `doc/todo/2-n8n-campaign-workflow.md` | Campaign workflow concept + algorithm |
