"""Add GS Append Queued (before send) and GS Append Status (after send) nodes to Campaign Send workflow."""
import json, copy, sys, os

WORKFLOW_FILE = os.path.join(os.path.dirname(__file__), '../../src/n8n/workflows/taris-campaign-send.json')
SHEET_TAB = 'Status рассылок'
GS_CRED_ID = 'j36NScu4bpqsYJKT'
GS_CRED_NAME = 'Google Sheets account 3'
SHEET_ID_EXPR = "={{ $('Webhook Send').first().json.body.sheet_id || '1jQaJZA4cBS2sLtE42zpwDHMn6grvDBAqoK_8Sp6PmXA' }}"


def make_gs_append_node(node_id, name, position, columns_value):
    return {
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.googleSheets",
        "typeVersion": 4.5,
        "position": position,
        "onError": "continueRegularOutput",
        "credentials": {
            "googleSheetsOAuth2Api": {"id": GS_CRED_ID, "name": GS_CRED_NAME}
        },
        "parameters": {
            "operation": "append",
            "documentId": {"__rl": True, "value": SHEET_ID_EXPR, "mode": "id"},
            "sheetName": {"__rl": True, "value": SHEET_TAB, "mode": "name"},
            "columns": {
                "mappingMode": "defineBelow",
                "value": columns_value,
                "matchingColumns": [],
                "schema": []
            },
            "options": {}
        }
    }


gs_queued = make_gs_append_node(
    node_id="gs-append-queued-001",
    name="GS Append Queued",
    position=[580, 304],
    columns_value={
        "Datum": "={{ new Date().toISOString().replace('T',' ').slice(0,19) }}",
        "Empfaenger": "={{ $json.email || $json.Email || '' }}",
        "Name": "={{ $json.name || '' }}",
        "Firma": "={{ $json.company || '' }}",
        "Thema": "={{ $json.topic || '' }}",
        "Status": "Gesendet wird..."
    }
)

gs_status = make_gs_append_node(
    node_id="gs-append-status-001",
    name="GS Append Status",
    position=[1070, 300],
    columns_value={
        "Datum": "={{ $json.Datum }}",
        "Empfaenger": "={{ $json.Empfaenger }}",
        "Name": "={{ $json.Name }}",
        "Firma": "={{ $json.Firma }}",
        "Thema": "={{ $json.Thema }}",
        "Status": "={{ $json.Status }}"
    }
)

with open(WORKFLOW_FILE, encoding='utf-8') as f:
    w = json.load(f)

# Remove any stale versions of these nodes
w['nodes'] = [n for n in w['nodes'] if n['name'] not in ('GS Append Queued', 'GS Append Status')]

# Add the two new nodes
w['nodes'].append(gs_queued)
w['nodes'].append(gs_status)

# Reposition existing nodes to make room
for n in w['nodes']:
    if n['name'] == 'Send Email Gmail':
        n['position'] = [760, 304]
    elif n['name'] == 'Prepare Sheet Row':
        n['position'] = [940, 300]
    elif n['name'] == 'Summary':
        n['position'] = [1260, 300]
    elif n['name'] == 'Respond Send':
        n['position'] = [1460, 300]

# Update connections:
#   Expand Clients  → GS Append Queued
#   GS Append Queued → Send Email Gmail
#   Send Email Gmail → Prepare Sheet Row  (already set)
#   Prepare Sheet Row → GS Append Status
#   GS Append Status → Summary
#   Summary → Respond Send               (already set)
conns = w['connections']
conns['Expand Clients']['main'][0] = [{"node": "GS Append Queued", "type": "main", "index": 0}]
conns['GS Append Queued'] = {"main": [[{"node": "Send Email Gmail", "type": "main", "index": 0}]]}
conns['Prepare Sheet Row']['main'][0] = [{"node": "GS Append Status", "type": "main", "index": 0}]
conns['GS Append Status'] = {"main": [[{"node": "Summary", "type": "main", "index": 0}]]}

with open(WORKFLOW_FILE, 'w', encoding='utf-8') as f:
    json.dump(w, f, ensure_ascii=False, indent=2)

print("Updated workflow nodes:")
for n in w['nodes']:
    print(f"  {n['name']} @ {n.get('position')}")
print("\nConnection chain:")
for src, data in w['connections'].items():
    for t in data.get('main', [[]])[0]:
        print(f"  {src} → {t['node']}")
print("\nDone.")
