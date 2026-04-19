#!/usr/bin/env python3
"""
n8n_admin.py — CLI tool for managing N8N workflows via the N8N API.

Usage:
  python tools/n8n/n8n_admin.py list                       # list all workflows
  python tools/n8n/n8n_admin.py list --active              # active only
  python tools/n8n/n8n_admin.py show <id>                  # show workflow JSON
  python tools/n8n/n8n_admin.py activate <id>              # activate workflow
  python tools/n8n/n8n_admin.py deactivate <id>            # deactivate workflow
  python tools/n8n/n8n_admin.py delete <id>                # delete workflow
  python tools/n8n/n8n_admin.py create <file.json>         # create from JSON file
  python tools/n8n/n8n_admin.py test-webhook <url> [json]  # test webhook POST
  python tools/n8n/n8n_admin.py executions [--wf <id>]     # list recent executions
  python tools/n8n/n8n_admin.py create-campaign            # create campaign select+send workflows
  python tools/n8n/n8n_admin.py create-notify              # create Notify Send workflow (Notifications to Users agent)
  python tools/n8n/n8n_admin.py status                     # N8N connectivity + workflow count

Credentials are read from .env in the project root (auto-detected).
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Config — load from .env
# ─────────────────────────────────────────────────────────────────────────────

def _load_env(path: Path) -> dict:
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


# Find project root (.env)
_here = Path(__file__).resolve()
_root = _here
for _ in range(6):
    if (_root / ".env").exists():
        break
    _root = _root.parent

_env = _load_env(_root / ".env")

N8N_BASE    = _env.get("VPS_N8N_HOST", "").rstrip("/")
N8N_API_KEY = _env.get("VPS_N8N_API_KEY", "")
N8N_API_V1  = f"{N8N_BASE}/api/v1"

# N8N Credential objects — IDs and names read from .env (instance-specific)
CRED_GSHEETS = {
    "id":   _env.get("VPS_N8N_CRED_GSHEETS", ""),
    "name": _env.get("VPS_N8N_CRED_GSHEETS_NAME", "Google Sheets"),
}
CRED_OPENAI = {
    "id":   _env.get("VPS_N8N_CRED_OPENAI", ""),
    "name": _env.get("VPS_N8N_CRED_OPENAI_NAME", "OpenAI"),
}
CRED_GMAIL = {
    "id":   _env.get("VPS_N8N_CRED_GMAIL", ""),
    "name": _env.get("VPS_N8N_CRED_GMAIL_NAME", "Gmail"),
}
CAMPAIGN_SHEET_ID = _env.get("VPS_GSHEET_CAMPAIGN_ID", "")


def _h() -> dict:
    return {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def _req(method: str, path: str, **kwargs):
    url = f"{N8N_API_V1}{path}"
    headers = _h()
    # Always serialize with ensure_ascii=False so Cyrillic/Unicode chars
    # are sent as actual UTF-8, not \uXXXX escape sequences.
    if "json" in kwargs:
        body = json.dumps(kwargs.pop("json"), ensure_ascii=False)
        kwargs["data"] = body.encode("utf-8")
        headers = {**headers, "Content-Type": "application/json; charset=utf-8"}
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_status():
    t0 = time.time()
    data = _req("GET", "/workflows?limit=1")
    ms = int((time.time() - t0) * 1000)
    all_wf = _req("GET", "/workflows?limit=200")
    total = len(all_wf.get("data", []))
    active = sum(1 for w in all_wf.get("data", []) if w.get("active"))
    print(f"✅ N8N reachable: {N8N_BASE}  ({ms}ms)")
    print(f"   Workflows: {total} total, {active} active")


def cmd_list(active_only: bool = False):
    data = _req("GET", "/workflows?limit=200")
    workflows = data.get("data", [])
    if active_only:
        workflows = [w for w in workflows if w.get("active")]
    print(f"{'ID':<25} {'ACTIVE':<8} NAME")
    print("-" * 80)
    for w in sorted(workflows, key=lambda x: x.get("name", "")):
        flag = "✅" if w.get("active") else "  "
        print(f"{w['id']:<25} {flag:<8} {w.get('name', '?')}")
    print(f"\n{len(workflows)} workflows")


def cmd_show(wf_id: str):
    data = _req("GET", f"/workflows/{wf_id}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_activate(wf_id: str):
    _req("POST", f"/workflows/{wf_id}/activate")
    print(f"✅ Activated: {wf_id}")


def cmd_deactivate(wf_id: str):
    _req("POST", f"/workflows/{wf_id}/deactivate")
    print(f"⏸  Deactivated: {wf_id}")


def cmd_delete(wf_id: str):
    confirm = input(f"Delete workflow {wf_id}? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return
    _req("DELETE", f"/workflows/{wf_id}")
    print(f"🗑  Deleted: {wf_id}")


def cmd_create(json_file: str):
    data = json.loads(Path(json_file).read_text(encoding="utf-8"))
    resp = _req("POST", "/workflows", json=data)
    wf_id = resp.get("id")
    print(f"✅ Created: id={wf_id} name={resp.get('name')}")
    return wf_id


def cmd_test_webhook(url: str, payload_str: str | None = None):
    payload = json.loads(payload_str) if payload_str else {"test": True}
    print(f"POST {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    t0 = time.time()
    resp = requests.post(url, json=payload, timeout=60)
    ms = int((time.time() - t0) * 1000)
    print(f"Status: {resp.status_code}  ({ms}ms)")
    try:
        print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
    except ValueError:
        print(resp.text[:500])


def cmd_executions(wf_id: str | None = None, limit: int = 10):
    path = f"/executions?limit={limit}"
    if wf_id:
        path += f"&workflowId={wf_id}"
    data = _req("GET", path)
    execs = data.get("data", [])
    print(f"{'ID':<30} {'STATUS':<12} {'WF_ID':<25} STARTED")
    print("-" * 90)
    for ex in execs:
        print(f"{ex.get('id','?'):<30} {ex.get('status','?'):<12} {ex.get('workflowId','?'):<25} {ex.get('startedAt','?')}")
    print(f"\n{len(execs)} executions")


# ─────────────────────────────────────────────────────────────────────────────
# Campaign workflow definitions
# ─────────────────────────────────────────────────────────────────────────────

def _campaign_select_workflow() -> dict:
    """N8N workflow: Taris Campaign Select.
    
    Receives: {session_id, topic, filters}
    Loads demo client data (Code node) → GPT-4o-mini selects audience + generates template
    Returns: {clients: [...], template: "..."}
    NOTE: Replace 'Demo Clients' Code node with real Google Sheets node when OAuth is fixed.
    """
    js_demo_clients = r"""
// DEMO DATA — replace with Google Sheets node when OAuth credential is refreshed
// Credential to fix: j36NScu4bpqsYJKT "Google Sheets account 3"
try {
  const demoClients = [
    { "Имя": "Алексей Петров",   "Email": "alex.petrov@example.com",    "Компания": "ТехноСтарт",      "Интересы": "IT-решения, автоматизация" },
    { "Имя": "Марина Соколова",  "Email": "m.sokolova@example.com",     "Компания": "Медиа Груп",      "Интересы": "маркетинг, контент" },
    { "Имя": "Дмитрий Кузнецов", "Email": "d.kuznetsov@example.com",    "Компания": "СтройИнвест",     "Интересы": "строительство, инвестиции" },
    { "Имя": "Анна Иванова",     "Email": "a.ivanova@example.com",      "Компания": "Финтех Решения",  "Интересы": "финансы, стартапы" },
    { "Имя": "Сергей Новиков",   "Email": "s.novikov@example.com",      "Компания": "АгроПром",        "Интересы": "сельское хозяйство, экспорт" },
    { "Имя": "Елена Морозова",   "Email": "e.morozova@example.com",     "Компания": "EduTech",         "Интересы": "образование, EdTech" },
    { "Имя": "Павел Волков",     "Email": "p.volkov@example.com",       "Компания": "КиберЗащита",     "Интересы": "кибербезопасность, IT" },
    { "Имя": "Ольга Лебедева",   "Email": "o.lebedeva@example.com",     "Компания": "GreenEnergy",     "Интересы": "возобновляемая энергия, ESG" },
    { "Имя": "Иван Козлов",      "Email": "i.kozlov@example.com",       "Компания": "LogisticsPro",    "Интересы": "логистика, цепочки поставок" },
    { "Имя": "Татьяна Смирнова", "Email": "t.smirnova@example.com",     "Компания": "HealthAI",        "Интересы": "медицина, AI, данные" }
  ];
  return demoClients.map((c, i) => ({ json: { ...c, _idx: i } }));
} catch(e) {
  return [{ json: { _error: true, step: "Demo Clients", detail: e.message } }];
}
"""

    js_prepare = r"""
try {
  // Propagate upstream error (e.g. Demo Clients failed)
  if (items.length === 1 && items[0].json._error === true) {
    return [{ json: items[0].json }];
  }

  const body = $('Webhook').first().json.body || $('Webhook').first().json;
  const topic = body.topic || '';
  const filters = body.filters || '';

  const clients = items.map((item, i) => ({ _idx: i, ...item.json }));
  const clientsStr = clients.map(c =>
    `${c._idx}: Имя=${c['Имя']||c['name']||c['Name']||'?'}, Email=${c['Email']||c['email']||''}, Компания=${c['Компания']||c['company']||''}, Интересы=${c['Интересы']||c['interests']||''}`
  ).join('\n');

  const prompt = `Ты маркетинговый ассистент. Выбери клиентов из списка, наиболее подходящих для кампании на тему: "${topic}".
${filters ? `Дополнительные критерии: ${filters}` : ''}

Список клиентов:
${clientsStr}

Верни ТОЛЬКО валидный JSON (без комментариев):
{
  "selected_indices": [0, 2, 5],
  "template": "Уважаемый {name}!\\n\\nМы рады предложить вам..."
}

Выбери 3-10 наиболее подходящих клиентов. Шаблон письма — на русском языке.`;

  return [{ json: { prompt, clients, topic, filters } }];
} catch(e) {
  return [{ json: { _error: true, step: "Prepare Prompt", detail: e.message } }];
}
"""

    js_parse = r"""
try {
  // Check if an upstream jsCode node returned an error (Demo Clients or Prepare Prompt)
  const prepareData = $('Prepare Prompt').first().json;
  if (prepareData._error === true) return [{ json: prepareData }];

  const item = items[0].json;
  const allClients = prepareData.clients || [];

  // Check if OpenAI HTTP node failed (continueOnFail passes error in item.json.error)
  if (item.error !== undefined && !item.choices) {
    const errMsg = typeof item.error === 'string'
      ? item.error
      : (item.error && (item.error.message || item.error.description)) || 'OpenAI request failed';
    return [{ json: { _error: true, step: "OpenAI Select", detail: errMsg } }];
  }

  let selected = [];
  let template = '';

  const rawData = item.data || item;
  let parsed = typeof rawData === 'string' ? JSON.parse(rawData) : rawData;
  const content = (parsed.choices && parsed.choices[0] && parsed.choices[0].message && parsed.choices[0].message.content)
    ? parsed.choices[0].message.content
    : JSON.stringify(parsed);
  const result = JSON.parse(content);
  const indices = result.selected_indices || [];
  template = result.template || '';
  selected = indices.map(i => allClients[i]).filter(Boolean);

  if (selected.length === 0) {
    selected = allClients.slice(0, 5);
    template = template || `Уважаемый {name}! Приглашаем вас принять участие в нашей кампании: ${prepareData.topic}`;
  }

  return [{ json: { clients: selected, template, count: selected.length } }];
} catch(e) {
  return [{ json: { _error: true, step: "Parse Response", detail: e.message } }];
}
"""

    return {
        "name": "Taris - Campaign Select",
        "nodes": [
            {
                "id": "n-webhook",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [200, 300],
                "webhookId": "taris-campaign-select-wh",
                "parameters": {
                    "httpMethod": "POST",
                    "path": "taris-campaign-select",
                    "responseMode": "responseNode",
                    "options": {}
                }
            },
            {
                "id": "n-demo-clients",
                "name": "Demo Clients",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [450, 300],
                "parameters": {
                    "mode": "runOnceForAllItems",
                    "jsCode": js_demo_clients
                }
            },
            {
                "id": "n-prepare",
                "name": "Prepare Prompt",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [700, 300],
                "parameters": {
                    "mode": "runOnceForAllItems",
                    "jsCode": js_prepare
                }
            },
            {
                "id": "n-openai",
                "name": "OpenAI Select",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4,
                "position": [950, 300],
                "onError": "continueRegularOutput",
                "parameters": {
                    "method": "POST",
                    "url": "https://api.openai.com/v1/chat/completions",
                    "authentication": "predefinedCredentialType",
                    "nodeCredentialType": "openAiApi",
                    "sendBody": True,
                    "contentType": "raw",
                    "rawContentType": "application/json",
                    "body": '={{ JSON.stringify({ model: "gpt-4o-mini", messages: [{ role: "user", content: $json.prompt }], response_format: { type: "json_object" }, temperature: 0.3 }) }}',
                    "options": {}
                },
                "credentials": {"openAiApi": CRED_OPENAI}
            },
            {
                "id": "n-parse",
                "name": "Parse Response",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1200, 300],
                "parameters": {
                    "mode": "runOnceForAllItems",
                    "jsCode": js_parse
                }
            },
            {
                "id": "n-respond",
                "name": "Respond",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1,
                "position": [1450, 300],
                "parameters": {
                    "respondWith": "json",
                    "responseBody": '={{ $json._error === true ? JSON.stringify({ error: $json.detail || "Workflow error", step: $json.step || "unknown" }) : JSON.stringify({ clients: $json.clients, template: $json.template }) }}',
                    "options": {"responseCode": 200}
                }
            }
        ],
        "connections": {
            "Webhook":       {"main": [[{"node": "Demo Clients",    "type": "main", "index": 0}]]},
            "Demo Clients":  {"main": [[{"node": "Prepare Prompt",  "type": "main", "index": 0}]]},
            "Prepare Prompt":{"main": [[{"node": "OpenAI Select",   "type": "main", "index": 0}]]},
            "OpenAI Select": {"main": [[{"node": "Parse Response",  "type": "main", "index": 0}]]},
            "Parse Response":{"main": [[{"node": "Respond",         "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"}
    }


def _campaign_send_workflow() -> dict:
    """N8N workflow: Taris Campaign Send.

    Receives: {session_id, topic, clients: [...], template}
    Sends Gmail to each client substituting {name}, {company}, {interests}
    Logs results to Google Sheets "Статус рассылок" tab
    Returns: {sent_count: N, sheet_url: "..."}
    """
    sheet_url = f"https://docs.google.com/spreadsheets/d/{CAMPAIGN_SHEET_ID}/edit#gid=0"

    js_expand = r"""
try {
  const body = $('Webhook Send').first().json.body || $('Webhook Send').first().json;

  if (!body || !Array.isArray(body.clients) || body.clients.length === 0) {
    return [{ json: { _error: true, step: "Expand Clients", detail: "No clients provided in request" } }];
  }

  const clients = body.clients;
  const template = body.template || 'Уважаемый {name}!';
  const topic = body.topic || '';
  const sessionId = body.session_id || '';

  const expanded = clients.map(client => {
    const name = client['Имя'] || client['name'] || client['Name'] || 'Клиент';
    const email = client['Email'] || client['email'] || '';
    const company = client['Компания'] || client['company'] || '';
    const interests = client['Интересы'] || client['interests'] || '';
    const body_text = template
      .replace(/{name}/g, name)
      .replace(/{company}/g, company)
      .replace(/{interests}/g, interests);
    return { json: { email, name, company, interests, body_text, topic, sessionId } };
  }).filter(item => item.json.email);

  if (expanded.length === 0) {
    return [{ json: { _error: true, step: "Expand Clients", detail: "No clients with valid email addresses" } }];
  }

  return expanded;
} catch(e) {
  return [{ json: { _error: true, step: "Expand Clients", detail: e.message } }];
}
"""

    js_log_row = r"""
try {
  const now = new Date().toISOString().replace('T', ' ').slice(0, 19);
  return items.map(item => {
    // Get original client data from Expand Clients (Gmail output doesn't include it)
    let clientData = {};
    try { clientData = $('Expand Clients').item.json || {}; } catch(e2) {}

    // Propagate early error from Expand Clients
    if (clientData._error === true) return { json: clientData };

    // Detect Gmail send failure (continueRegularOutput adds error field to item)
    const sendError = item.json.error
      ? (typeof item.json.error === 'string'
          ? item.json.error
          : item.json.error.message || item.json.error.description || 'Email sending failed')
      : null;

    return {
      json: {
        Дата: now,
        Кампания: clientData.topic || '',
        Получатель: clientData.name || '',
        Email: clientData.email || '',
        Статус: sendError ? 'Ошибка' : 'Отправлено',
        'Session ID': clientData.sessionId || '',
        _send_error: sendError
      }
    };
  });
} catch(e) {
  return [{ json: { _error: true, step: "Prepare Sheet Row", detail: e.message } }];
}
"""

    js_summary = (
        r"""
try {
  // Propagate early error from Expand Clients (single error item that survived log_row)
  if (items.length === 1 && items[0].json._error === true) {
    return [{ json: items[0].json }];
  }

  const sent   = items.filter(i => !i.json._send_error && !i.json._error).length;
  const failed = items.filter(i =>  i.json._send_error ||  i.json._error).length;
  const total  = items.length;

  const failedEmails = items
    .filter(i => i.json._send_error || i.json._error)
    .map(i => i.json.Email || i.json.email || '?')
    .slice(0, 5)
    .join(', ');

  if (sent === 0 && total > 0) {
    const firstErr = (items[0] && items[0].json._send_error) || 'All emails failed to send';
    return [{ json: {
      _error: true, step: "Send Gmail",
      detail: `${total} email(s) failed. ${firstErr}`,
      failed_count: total, failed_emails: failedEmails
    }}];
  }

  return [{ json: {
    sent_count:   sent,
    failed_count: failed,
    total_count:  total,
    sheet_url:    """
        + f'"{sheet_url}"'
        + r""",
    failed_emails: failedEmails
  }}];
} catch(e) {
  return [{ json: { _error: true, step: "Summary", detail: e.message } }];
}
"""
    )

    return {
        "name": "Taris - Campaign Send",
        "nodes": [
            {
                "id": "n-webhook-send",
                "name": "Webhook Send",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [200, 300],
                "webhookId": "taris-campaign-send-wh",
                "parameters": {
                    "httpMethod": "POST",
                    "path": "taris-campaign-send",
                    "responseMode": "responseNode",
                    "options": {}
                }
            },
            {
                "id": "n-expand",
                "name": "Expand Clients",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [450, 300],
                "parameters": {
                    "mode": "runOnceForAllItems",
                    "jsCode": js_expand
                }
            },
            {
                "id": "n-gmail",
                "name": "Send Gmail",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2,
                "position": [700, 300],
                "onError": "continueRegularOutput",
                "parameters": {
                    "operation": "send",
                    "toList": "={{ $json.email }}",
                    "subject": "={{ $json.topic || 'Письмо от Sintaris' }}",
                    "message": "={{ $json.body_text }}",
                    "options": {}
                },
                "credentials": {"gmailOAuth2": CRED_GMAIL}
            },
            {
                "id": "n-log-prep",
                "name": "Prepare Sheet Row",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [950, 300],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": js_log_row
                }
            },
            {
                "id": "n-summary",
                "name": "Summary",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1200, 300],
                "parameters": {
                    "mode": "runOnceForAllItems",
                    "jsCode": js_summary
                }
            },
            {
                "id": "n-respond-send",
                "name": "Respond Send",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1,
                "position": [1450, 300],
                "parameters": {
                    "respondWith": "json",
                    "responseBody": '={{ $json._error === true ? JSON.stringify({ error: $json.detail || "Workflow error", step: $json.step || "unknown" }) : JSON.stringify({ sent_count: $json.sent_count, failed_count: $json.failed_count, total_count: $json.total_count, sheet_url: $json.sheet_url, failed_emails: $json.failed_emails }) }}',
                    "options": {"responseCode": 200}
                }
            }
        ],
        "connections": {
            "Webhook Send":      {"main": [[{"node": "Expand Clients",    "type": "main", "index": 0}]]},
            "Expand Clients":    {"main": [[{"node": "Send Gmail",         "type": "main", "index": 0}]]},
            "Send Gmail":        {"main": [[{"node": "Prepare Sheet Row",  "type": "main", "index": 0}]]},
            "Prepare Sheet Row": {"main": [[{"node": "Summary",            "type": "main", "index": 0}]]},
            "Summary":           {"main": [[{"node": "Respond Send",       "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"}
    }


def cmd_put_workflow(wf_id: str, file_path: str, activate: bool = True):
    """Replace an existing workflow with a definition from a JSON file.

    Steps:
    1. Deactivate the workflow (required before PUT in N8N).
    2. PUT the new definition (nodes + connections + settings).
    3. Re-activate if it was active before (or --activate flag).
    """
    wf_file = Path(file_path)
    if not wf_file.exists():
        print(f"ERROR: file not found: {wf_file}", file=sys.stderr)
        sys.exit(1)

    raw = wf_file.read_text(encoding="utf-8")
    new_def = json.loads(raw)

    existing = _req("GET", f"/workflows/{wf_id}")
    was_active = existing.get("active", False)

    if was_active:
        _req("POST", f"/workflows/{wf_id}/deactivate")
        print(f"  ⏸  Deactivated {wf_id}")

    body = {
        "name": new_def.get("name", existing["name"]),
        "nodes": new_def["nodes"],
        "connections": new_def["connections"],
        "settings": new_def.get("settings", existing.get("settings", {})),
        "staticData": existing.get("staticData"),
    }
    _req("PUT", f"/workflows/{wf_id}", json=body)
    print(f"  ✅ Updated workflow {wf_id} from {wf_file.name}")

    if was_active or activate:
        _req("POST", f"/workflows/{wf_id}/activate")
        webhook_nodes = [n for n in new_def["nodes"] if "webhook" in n.get("type", "").lower() and n.get("parameters", {}).get("path")]
        if webhook_nodes:
            path = webhook_nodes[0]["parameters"]["path"]
            print(f"  ✅ Activated → {N8N_BASE}/webhook/{path}")
        else:
            print(f"  ✅ Activated")


def cmd_create_campaign():
    """Create and activate both campaign workflows."""
    print("Creating Taris Campaign Select workflow...")
    wf_select = _campaign_select_workflow()
    resp = _req("POST", "/workflows", json=wf_select)
    sel_id = resp["id"]
    _req("POST", f"/workflows/{sel_id}/activate")
    print(f"  ✅ SELECT: id={sel_id}  webhook={N8N_BASE}/webhook/taris-campaign-select")

    print("Creating Taris Campaign Send workflow...")
    wf_send = _campaign_send_workflow()
    resp = _req("POST", "/workflows", json=wf_send)
    snd_id = resp["id"]
    _req("POST", f"/workflows/{snd_id}/activate")
    print(f"  ✅ SEND:   id={snd_id}  webhook={N8N_BASE}/webhook/taris-campaign-send")

    print()
    print("Add to ~/.taris/bot.env on TariStation2:")
    print(f"  N8N_CAMPAIGN_SELECT_WH={N8N_BASE}/webhook/taris-campaign-select")
    print(f"  N8N_CAMPAIGN_SEND_WH={N8N_BASE}/webhook/taris-campaign-send")


def _decode_unicode_escapes(val: str) -> str:
    """Replace literal \\uXXXX sequences with actual Unicode characters.

    Needed when N8N stored node code with escape sequences instead of
    the actual UTF-8 characters (caused by json.dumps ensure_ascii=True).
    """
    return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), val)


def _walk_decode(obj):
    """Recursively decode \\uXXXX sequences in all string values of a nested structure."""
    if isinstance(obj, str):
        return _decode_unicode_escapes(obj)
    if isinstance(obj, dict):
        return {k: _walk_decode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_decode(v) for v in obj]
    return obj


def cmd_fix_unicode(wf_id: str):
    """Fetch workflow, decode literal \\uXXXX in all node code strings, PUT it back.

    Use this to fix a workflow that was created before the ensure_ascii=False fix.
    """
    print(f"Fetching workflow {wf_id}...")
    wf = _req("GET", f"/workflows/{wf_id}")
    print(f"  Name: {wf.get('name', '?')}")

    was_active = wf.get("active", False)
    if was_active:
        _req("POST", f"/workflows/{wf_id}/deactivate")
        print("  Deactivated (will reactivate after update)")

    fixed = _walk_decode(wf)
    # N8N PUT /workflows/{id}: only include safe fields (tags/pinData format differs GET vs PUT)
    body = {
        "name": fixed["name"],
        "nodes": fixed["nodes"],
        "connections": fixed["connections"],
        "settings": fixed.get("settings", {}),
        "staticData": fixed.get("staticData"),
    }
    _req("PUT", f"/workflows/{wf_id}", json=body)
    print("  ✅ Updated: \\uXXXX sequences decoded to readable Unicode")

    if was_active:
        _req("POST", f"/workflows/{wf_id}/activate")
        print("  ✅ Reactivated")

    print(f"Done: {wf.get('name')}")


def cmd_update_campaign(which: str = "send"):
    """Find and update campaign workflow(s) with current node code (unicode-clean).

    which: 'send' | 'select' | 'both'
    Matches workflow names with or without the dash variant (live workflows may
    be named 'Taris Campaign Send' instead of 'Taris - Campaign Send').
    """
    all_wf = _req("GET", "/workflows?limit=200")
    wf_map = {w["name"]: w for w in all_wf.get("data", [])}

    # Support both dash and no-dash name variants used in live N8N
    def _find(base_name: str):
        return wf_map.get(base_name) or wf_map.get(base_name.replace(" - ", " "))

    targets = []
    if which in ("send", "both"):
        targets.append(("Taris - Campaign Send", _campaign_send_workflow))
    if which in ("select", "both"):
        targets.append(("Taris - Campaign Select", _campaign_select_workflow))

    for name, builder in targets:
        found = _find(name)
        if not found:
            print(f"  ⚠️  Not found: {name!r} (or no-dash variant). Run create-campaign first.")
            print(f"       Available: {[w for w in wf_map if 'ampaign' in w]}")
            continue

        wf_id = found["id"]
        was_active = found.get("active", False)
        print(f"Updating '{found['name']}' (id={wf_id})...")

        if was_active:
            _req("POST", f"/workflows/{wf_id}/deactivate")

        existing = _req("GET", f"/workflows/{wf_id}")
        new_def = builder()
        body = {
            "name": new_def["name"],
            "nodes": new_def["nodes"],
            "connections": new_def["connections"],
            "settings": new_def.get("settings", {}),
            "staticData": existing.get("staticData"),
        }
        _req("PUT", f"/workflows/{wf_id}", json=body)
        print(f"  ✅ Node code updated (error handling + unicode-clean)")

        if was_active:
            _req("POST", f"/workflows/{wf_id}/activate")
            print(f"  ✅ Reactivated → {N8N_BASE}/webhook/{new_def['nodes'][0]['parameters']['path']}")


# ─────────────────────────────────────────────────────────────────────────────
# Notify Send workflow (Notifications to Users agent)
# ─────────────────────────────────────────────────────────────────────────────

def _notify_send_workflow() -> dict:
    """N8N workflow: Taris - Notify Send.

    Receives: {recipients: [{chat_id: int, name: str, message: str}]}
    Sends Telegram message to each recipient via Bot API HTTP Request.
    Returns: {sent: N, failed: N, errors: ["name: reason", ...]}

    The bot_token is read from the BOT_TOKEN env var set in the N8N environment,
    or passed in the request as {bot_token: "..."} (fallback for testing).
    """
    js_expand = r"""
try {
  const body = $('Webhook').first().json.body || $('Webhook').first().json;

  if (!body || !Array.isArray(body.recipients) || body.recipients.length === 0) {
    return [{ json: { _error: true, step: "Expand", detail: "No recipients provided" } }];
  }

  const botToken = body.bot_token || $env.BOT_TOKEN || '';
  if (!botToken) {
    return [{ json: { _error: true, step: "Expand", detail: "bot_token not provided and BOT_TOKEN env not set" } }];
  }

  return body.recipients.map(r => ({
    json: {
      chat_id: r.chat_id || r.telegram_id,
      name: r.name || String(r.chat_id || ''),
      message: r.message || body.message || '',
      bot_token: botToken
    }
  })).filter(r => r.json.chat_id && r.json.message);
} catch(e) {
  return [{ json: { _error: true, step: "Expand", detail: e.message } }];
}
"""

    js_summary = r"""
try {
  if (items.length === 1 && items[0].json._error === true) {
    return [{ json: items[0].json }];
  }

  const sent   = items.filter(i => i.json._ok === true).length;
  const failed = items.filter(i => i.json._ok !== true).length;
  const errors = items
    .filter(i => i.json._ok !== true)
    .map(i => `${i.json.name || i.json.chat_id}: ${i.json._err || 'send failed'}`)
    .slice(0, 10);

  return [{ json: { sent, failed, total: items.length, errors } }];
} catch(e) {
  return [{ json: { _error: true, step: "Summary", detail: e.message } }];
}
"""

    js_mark_result = r"""
try {
  const item = items[0].json;
  // item.statusCode is set by the HTTP Request node on success/failure
  const ok = item.ok === true;
  const name = $('Expand').item.json.name || '';
  const chat_id = $('Expand').item.json.chat_id || '';
  return [{
    json: {
      chat_id,
      name,
      _ok: ok,
      _err: ok ? null : (item.description || item.error_code || 'Telegram API error')
    }
  }];
} catch(e) {
  return [{ json: { chat_id: '', name: '', _ok: false, _err: e.message } }];
}
"""

    return {
        "name": "Taris - Notify Send",
        "nodes": [
            {
                "id": "n-webhook-notify",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [200, 300],
                "webhookId": "taris-notify-send-wh",
                "parameters": {
                    "httpMethod": "POST",
                    "path": "taris-notify-send",
                    "responseMode": "responseNode",
                    "options": {}
                }
            },
            {
                "id": "n-expand-notify",
                "name": "Expand",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [450, 300],
                "parameters": {
                    "mode": "runOnceForAllItems",
                    "jsCode": js_expand
                }
            },
            {
                "id": "n-tg-send",
                "name": "Send Telegram",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4,
                "position": [700, 300],
                "onError": "continueRegularOutput",
                "parameters": {
                    "method": "POST",
                    "url": "=https://api.telegram.org/bot{{ $json.bot_token }}/sendMessage",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify({ chat_id: $json.chat_id, text: $json.message, parse_mode: 'HTML' }) }}",
                    "options": {"response": {"response": {"responseFormat": "json"}}}
                }
            },
            {
                "id": "n-mark-result",
                "name": "Mark Result",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [950, 300],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": js_mark_result
                }
            },
            {
                "id": "n-summary-notify",
                "name": "Summary",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1200, 300],
                "parameters": {
                    "mode": "runOnceForAllItems",
                    "jsCode": js_summary
                }
            },
            {
                "id": "n-respond-notify",
                "name": "Respond",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1,
                "position": [1450, 300],
                "parameters": {
                    "respondWith": "json",
                    "responseBody": '={{ $json._error === true ? JSON.stringify({ error: $json.detail || "Workflow error" }) : JSON.stringify({ sent: $json.sent, failed: $json.failed, total: $json.total, errors: $json.errors }) }}',
                    "options": {"responseCode": 200}
                }
            }
        ],
        "connections": {
            "Webhook":       {"main": [[{"node": "Expand",         "type": "main", "index": 0}]]},
            "Expand":        {"main": [[{"node": "Send Telegram",  "type": "main", "index": 0}]]},
            "Send Telegram": {"main": [[{"node": "Mark Result",    "type": "main", "index": 0}]]},
            "Mark Result":   {"main": [[{"node": "Summary",        "type": "main", "index": 0}]]},
            "Summary":       {"main": [[{"node": "Respond",        "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"}
    }


def cmd_create_notify():
    """Create and activate the Taris Notify Send workflow."""
    print("Creating Taris Notify Send workflow...")
    wf = _notify_send_workflow()
    resp = _req("POST", "/workflows", json=wf)
    wf_id = resp["id"]
    _req("POST", f"/workflows/{wf_id}/activate")
    print(f"  ✅ id={wf_id}  webhook={N8N_BASE}/webhook/taris-notify-send")

    print()
    print("Add to /opt/taris-docker/bot.env:")
    print(f"  N8N_NOTIFY_SEND_WH={N8N_BASE}/webhook/taris-notify-send")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if not N8N_API_KEY:
        print("ERROR: VPS_N8N_API_KEY not found in .env", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="N8N admin CLI for taris")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status")
    p_list = sub.add_parser("list")
    p_list.add_argument("--active", action="store_true")

    p_show = sub.add_parser("show")
    p_show.add_argument("id")

    p_act = sub.add_parser("activate")
    p_act.add_argument("id")

    p_deact = sub.add_parser("deactivate")
    p_deact.add_argument("id")

    p_del = sub.add_parser("delete")
    p_del.add_argument("id")

    p_create = sub.add_parser("create")
    p_create.add_argument("file")

    p_wh = sub.add_parser("test-webhook")
    p_wh.add_argument("url")
    p_wh.add_argument("payload", nargs="?", default=None)

    p_ex = sub.add_parser("executions")
    p_ex.add_argument("--wf", default=None)
    p_ex.add_argument("--limit", type=int, default=10)

    sub.add_parser("create-campaign")

    sub.add_parser("create-notify")

    p_fix = sub.add_parser("fix-unicode", help="Decode \\uXXXX sequences in workflow node code")
    p_fix.add_argument("id", help="Workflow ID (from 'list')")

    p_put = sub.add_parser("put-workflow", help="Replace an existing workflow with a JSON file")
    p_put.add_argument("id", help="Workflow ID")
    p_put.add_argument("file", help="Path to workflow JSON file")
    p_put.add_argument("--no-activate", action="store_true", help="Leave deactivated after update")

    p_upd = sub.add_parser("update-campaign", help="Update campaign workflow(s) with current node code")
    p_upd.add_argument("--which", choices=["send", "select", "both"], default="send")

    args = parser.parse_args()

    try:
        if args.cmd == "status":          cmd_status()
        elif args.cmd == "list":          cmd_list(args.active)
        elif args.cmd == "show":          cmd_show(args.id)
        elif args.cmd == "activate":      cmd_activate(args.id)
        elif args.cmd == "deactivate":    cmd_deactivate(args.id)
        elif args.cmd == "delete":        cmd_delete(args.id)
        elif args.cmd == "create":        cmd_create(args.file)
        elif args.cmd == "test-webhook":  cmd_test_webhook(args.url, args.payload)
        elif args.cmd == "executions":    cmd_executions(args.wf, args.limit)
        elif args.cmd == "put-workflow":       cmd_put_workflow(args.id, args.file, activate=not args.no_activate)
        elif args.cmd == "create-campaign":   cmd_create_campaign()
        elif args.cmd == "create-notify":      cmd_create_notify()
        elif args.cmd == "fix-unicode":        cmd_fix_unicode(args.id)
        elif args.cmd == "update-campaign":    cmd_update_campaign(args.which)
        else:
            parser.print_help()
    except requests.HTTPError as e:
        print(f"HTTP error: {e.response.status_code} {e.response.text[:300]}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
