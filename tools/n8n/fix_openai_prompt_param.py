#!/usr/bin/env python3
"""Fix OpenAI Select node: correct 'prompt' fixedCollection parameter structure."""
import json, os

BASE = os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'n8n', 'workflows')
path = os.path.join(BASE, 'taris-campaign-select.json')

with open(path, encoding='utf-8') as f:
    w = json.load(f)

for n in w['nodes']:
    if n['name'] == 'OpenAI Select':
        n['parameters'] = {
            "resource": "chat",
            "operation": "complete",
            "model": "gpt-4o-mini",
            "simplifyOutput": False,
            "prompt": {
                "messages": [
                    {"role": "user", "content": "={{ $json.prompt }}"}
                ]
            },
            "options": {
                "temperature": 0.3
            }
        }
        print("[OK] Fixed OpenAI Select parameters:")
        print(json.dumps(n['parameters'], indent=2, ensure_ascii=False))
        break

with open(path, 'w', encoding='utf-8') as f:
    json.dump(w, f, ensure_ascii=False, indent=2)
print(f"[OK] Saved {path}")
