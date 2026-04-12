#!/usr/bin/env python3
"""Fix Parse Response: strip markdown code fences from OpenAI output."""
import json, os

BASE = os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'n8n', 'workflows')
sel_path = os.path.join(BASE, 'taris-campaign-select.json')

NEW_CODE = (
    "try {\n"
    "  // Propagate errors from Prepare Prompt (Demo Clients / GS Read Clients)\n"
    "  const prepareData = $('Prepare Prompt').first().json;\n"
    "  if (prepareData._error === true) return [{ json: prepareData }];\n"
    "\n"
    "  const item = items[0].json;\n"
    "  const allClients = prepareData.clients || [];\n"
    "\n"
    "  // Check if OpenAI node failed (onError: continueRegularOutput puts error in item.error)\n"
    "  if (item.error !== undefined && !item.choices) {\n"
    "    const errMsg = typeof item.error === 'string'\n"
    "      ? item.error\n"
    "      : (item.error && (item.error.message || item.error.description)) || 'OpenAI request failed';\n"
    "    return [{ json: { _error: true, step: \"OpenAI Select\", detail: errMsg } }];\n"
    "  }\n"
    "\n"
    "  let selected = [];\n"
    "  let template = '';\n"
    "\n"
    "  const rawData = item.data || item;\n"
    "  let parsed = typeof rawData === 'string' ? JSON.parse(rawData) : rawData;\n"
    "  let content = (parsed.choices && parsed.choices[0] && parsed.choices[0].message && parsed.choices[0].message.content)\n"
    "    ? parsed.choices[0].message.content\n"
    "    : JSON.stringify(parsed);\n"
    "\n"
    "  // Strip markdown code fences: model sometimes wraps JSON in ```json...```\n"
    "  content = content.trim();\n"
    "  if (content.startsWith('`')) {\n"
    "    content = content.replace(/^```(?:json)?\\s*\\n?/, '').replace(/\\n?```\\s*$/, '').trim();\n"
    "  }\n"
    "\n"
    "  const result = JSON.parse(content);\n"
    "  const indices = result.selected_indices || [];\n"
    "  template = result.template || '';\n"
    "  selected = indices.map(i => allClients[i]).filter(Boolean);\n"
    "\n"
    "  if (selected.length === 0) {\n"
    "    selected = allClients.slice(0, 5);\n"
    "    template = template || `\\u0423\\u0432\\u0430\\u0436\\u0430\\u0435\\u043c\\u044b\\u0439 {name}! \\u041f\\u0440\\u0438\\u0433\\u043b\\u0430\\u0448\\u0430\\u0435\\u043c \\u0432\\u0430\\u0441 \\u043f\\u0440\\u0438\\u043d\\u044f\\u0442\\u044c \\u0443\\u0447\\u0430\\u0441\\u0442\\u0438\\u0435 \\u0432 \\u043d\\u0430\\u0448\\u0435\\u0439 \\u043a\\u0430\\u043c\\u043f\\u0430\\u043d\\u0438\\u0438: ${prepareData.topic}`;\n"
    "  }\n"
    "\n"
    "  // Normalize client keys: always expose 'name' and 'email' for downstream nodes\n"
    "  selected = selected.map(c => ({\n"
    "    ...c,\n"
    "    name: c['\\u0418\\u043c\\u044f'] || c['\\u0424\\u0418\\u041e'] || c['name'] || c['Name'] || c['\\u0418\\u043c\\u044f \\u043a\\u043b\\u0438\\u0435\\u043d\\u0442\\u0430'] || '',\n"
    "    email: c['Email'] || c['email'] || c['\\u042d\\u043b\\u0435\\u043a\\u0442\\u0440\\u043e\\u043d\\u043d\\u0430\\u044f \\u043f\\u043e\\u0447\\u0442\\u0430'] || '',\n"
    "  }));\n"
    "\n"
    "  return [{ json: { clients: selected, template, count: selected.length } }];\n"
    "} catch(e) {\n"
    "  return [{ json: { _error: true, step: \"Parse Response\", detail: e.message } }];\n"
    "}"
)

with open(sel_path, encoding='utf-8') as f:
    w = json.load(f)

updated = False
for n in w['nodes']:
    if n['name'] == 'Parse Response':
        n['parameters']['jsCode'] = NEW_CODE
        updated = True
        print("[OK] Updated Parse Response: added markdown code-fence stripping")
        break

if not updated:
    print("[ERROR] Parse Response node not found!")
    raise SystemExit(1)

with open(sel_path, 'w', encoding='utf-8') as f:
    json.dump(w, f, ensure_ascii=False, indent=2)
print(f"[OK] Saved {sel_path}")
