#!/usr/bin/env python3
"""Update campaign workflows to use native N8N nodes for OpenAI and Gmail."""
import json, sys, os

BASE = os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'n8n', 'workflows')

# === Campaign Select: replace OpenAI HTTP Request with native n8n-nodes-base.openAi ===
sel_path = os.path.join(BASE, 'taris-campaign-select.json')
with open(sel_path, encoding='utf-8') as f:
    sel = json.load(f)

for n in sel['nodes']:
    if n['name'] == 'OpenAI Select':
        n['type'] = 'n8n-nodes-base.openAi'
        n['typeVersion'] = 1.1
        n['parameters'] = {
            "resource": "chat",
            "operation": "complete",
            "model": "gpt-4o-mini",
            "simplifyOutput": False,
            "messages": {
                "values": [
                    {"role": "user", "content": "={{ $json.prompt }}"}
                ]
            },
            "options": {
                "temperature": 0.3
            }
        }
        n['credentials'] = {
            "openAiApi": {"id": "MHkmfl85kwu22LT8", "name": "OpenAI SINTARIS"}
        }
        n['onError'] = 'continueRegularOutput'
        print(f"[SELECT] Replaced OpenAI Select -> n8n-nodes-base.openAi v1.1")
        break

with open(sel_path, 'w', encoding='utf-8') as f:
    json.dump(sel, f, ensure_ascii=False, indent=2)
print(f"[SELECT] Saved {sel_path}")

# === Campaign Send: replace emailSend SMTP with native n8n-nodes-base.gmail ===
snd_path = os.path.join(BASE, 'taris-campaign-send.json')
with open(snd_path, encoding='utf-8') as f:
    snd = json.load(f)

OLD_NAME = 'Send Email SMTP'
NEW_NAME = 'Send Email Gmail'

for n in snd['nodes']:
    if n['name'] == OLD_NAME:
        n['name'] = NEW_NAME
        n['type'] = 'n8n-nodes-base.gmail'
        n['typeVersion'] = 2.1
        n['parameters'] = {
            "sendTo": "={{ $json.email }}",
            "subject": "={{ $json.topic || 'Einladung von Taris' }}",
            "message": "={{ $json.body_text }}",
            "options": {
                "senderName": "={{ $json.from_email || 'Taris' }}"
            }
        }
        n['credentials'] = {
            "gmailOAuth2": {"id": "OM7qAUKDjlYrrRsI", "name": "Gmail account devstar"}
        }
        n['onError'] = 'continueRegularOutput'
        print(f"[SEND] Renamed '{OLD_NAME}' -> '{NEW_NAME}', type=n8n-nodes-base.gmail v2.1")
        break

# Update connection keys: rename OLD_NAME -> NEW_NAME
conns = snd.get('connections', {})
if OLD_NAME in conns:
    conns[NEW_NAME] = conns.pop(OLD_NAME)
    print(f"[SEND] Connection key renamed")

# Update any edge targets pointing to OLD_NAME
for src, targets in conns.items():
    for port in targets.get('main', []):
        for edge in port:
            if edge.get('node') == OLD_NAME:
                edge['node'] = NEW_NAME
                print(f"[SEND] Edge updated: {src} -> {NEW_NAME}")

with open(snd_path, 'w', encoding='utf-8') as f:
    json.dump(snd, f, ensure_ascii=False, indent=2)
print(f"[SEND] Saved {snd_path}")
print("Done.")
