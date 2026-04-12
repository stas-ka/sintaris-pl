"""Fix Respond node expression to use single quotes and correct field order."""
import json

with open('src/n8n/workflows/taris-campaign-select.json', encoding='utf-8') as f:
    wf = json.load(f)

for node in wf['nodes']:
    if node['name'] == 'Respond':
        # Use single quotes inside JS to avoid JSON escaping issues
        node['parameters']['responseBody'] = (
            "={{ $json._error === true"
            " ? JSON.stringify({ error: $json.error || $json.detail || 'Workflow error', step: $json.step || 'unknown' })"
            " : JSON.stringify({ clients: $json.clients, template: $json.template }) }}"
        )
        print('Respond fixed:', node['parameters']['responseBody'][:80])

    if node['name'] == 'Prepare Prompt':
        code = node['parameters']['jsCode']
        # Improve nested error extraction
        old = "const errMsg = httpErr || it.message || (typeof it.error === 'string' ? it.error : it.error?.message) || it.description || 'Google Sheets error';"
        new = ("const nestedMsg = (it.error && typeof it.error === 'object')"
               " ? (it.error.message || it.error.description || JSON.stringify(it.error).substring(0,300))"
               " : null;\n"
               "    const errMsg = httpErr || it.message || (typeof it.error === 'string' ? it.error : nestedMsg) || it.description || 'Google Sheets error';")
        if old in code:
            node['parameters']['jsCode'] = code.replace(old, new)
            print('Prepare Prompt error extraction improved')
        else:
            print('Prepare Prompt old pattern not found (already updated?)')

with open('src/n8n/workflows/taris-campaign-select.json', 'w', encoding='utf-8') as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)
print('Saved.')
