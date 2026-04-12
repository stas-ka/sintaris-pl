"""Update Prepare Prompt to handle HTTP GS API response format."""
import json

with open('src/n8n/workflows/taris-campaign-select.json', encoding='utf-8') as f:
    wf = json.load(f)

new_code = r"""try {
  // Propagate upstream error
  if (items.length === 1 && (items[0].json._error === true || items[0].json.error)) {
    const it = items[0].json;
    // HTTP Request node sends status code on error
    const httpErr = it.statusCode ? `HTTP ${it.statusCode}: ${it.message || JSON.stringify(it).substring(0,200)}` : null;
    const errMsg = httpErr || it.message || (typeof it.error === 'string' ? it.error : it.error?.message) || it.description || 'Google Sheets error';
    return [{ json: { _error: true, error: errMsg, step: 'GS Read Clients' } }];
  }

  const body = $('Webhook').first().json.body || $('Webhook').first().json;
  const topic = body.topic || '';
  const filters = body.filters || '';

  // Parse GS API HTTP response: {values: [[header, cols...], [row1...], ...]}
  // OR legacy GS node format: items is array of row objects with header keys
  let clients = [];
  if (items.length === 1 && items[0].json.values) {
    // HTTP Request to Google Sheets API: response has {values: [[header],[row1],[row2],...]}
    const rows = items[0].json.values || [];
    if (rows.length < 2) {
      return [{ json: { _error: true, error: 'Empty spreadsheet or no data rows', step: 'GS Read Clients' } }];
    }
    const headers = rows[0]; // first row = column headers
    clients = rows.slice(1).map((row, i) => {
      const obj = { _idx: i };
      headers.forEach((h, j) => { obj[h] = row[j] || ''; });
      return obj;
    });
  } else {
    // Legacy GS node format: each item is one row
    clients = items.map((item, i) => ({ _idx: i, ...item.json }));
  }

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

Выбери 3-10 наиболее подходящих клиентов. Шаблон письма - на русском языке.`;

  return [{ json: { prompt, clients, topic, filters } }];
} catch(e) {
  return [{ json: { _error: true, step: "Prepare Prompt", detail: e.message } }];
}"""

for node in wf['nodes']:
    if node['name'] == 'Prepare Prompt':
        node['parameters']['jsCode'] = new_code
        print(f'Updated Prepare Prompt code length: {len(new_code)}')
        break

with open('src/n8n/workflows/taris-campaign-select.json', 'w', encoding='utf-8') as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)
print('Saved.')

# Also update Merge Template to handle HTTP GS API format for templates
with open('src/n8n/workflows/taris-campaign-select.json', encoding='utf-8') as f:
    wf = json.load(f)

for node in wf['nodes']:
    if node['name'] == 'Merge Template':
        old_code = node['parameters']['jsCode']
        # Update the templateRows parsing to handle HTTP GS API format
        old_part = "try { templateRows = $('GS Read Templates').all().map(i => i.json); } catch(e) {}"
        new_part = """try {
    const gsResp = $('GS Read Templates').first().json;
    if (gsResp && gsResp.values && gsResp.values.length > 1) {
      // HTTP API format: {values: [[header,...],[row1,...],...]
      const hdrs = gsResp.values[0];
      templateRows = gsResp.values.slice(1).map(row => {
        const obj = {};
        hdrs.forEach((h, j) => { obj[h] = row[j] || ''; });
        return obj;
      });
    } else {
      templateRows = $('GS Read Templates').all().map(i => i.json);
    }
  } catch(e) { templateRows = []; }"""
        if old_part in old_code:
            node['parameters']['jsCode'] = old_code.replace(old_part, new_part)
            print('Updated Merge Template template parsing')
        else:
            print('Merge Template old part not found, checking...')
            print(old_code[:300])
        break

with open('src/n8n/workflows/taris-campaign-select.json', 'w', encoding='utf-8') as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)
print('Saved final.')
