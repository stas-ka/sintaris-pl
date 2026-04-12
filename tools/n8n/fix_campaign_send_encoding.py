"""Fix encoding corruption in taris-campaign-send.json.

Expand Clients node has garbled UTF-8 (Russian chars stored as Latin-1 bytes).
Rewrite the affected nodes with proper Unicode strings.
"""
import json

with open('src/n8n/workflows/taris-campaign-send.json', encoding='utf-8') as f:
    wf = json.load(f)

EXPAND_CLIENTS_CODE = r"""try {
  const body = $('Webhook Send').first().json.body || $('Webhook Send').first().json;

  if (!body || !Array.isArray(body.clients) || body.clients.length === 0) {
    return [{ json: { _error: true, step: "Expand Clients", detail: "No clients provided in request" } }];
  }

  const clients = body.clients;
  const template = body.template || '\u0423\u0432\u0430\u0436\u0430\u0435\u043c\u044b\u0439 {name}!';
  const topic = body.topic || '';
  const sessionId = body.session_id || '';

  const expanded = clients.map(client => {
    // Support both Russian column names (from Google Sheets) and English fallbacks
    const name = client['\u0418\u043c\u044f'] || client['name'] || client['Name'] || '';
    const email = client['Email'] || client['email'] || '';
    const company = client['\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f'] || client['company'] || '';
    const interests = client['\u0418\u043d\u0442\u0435\u0440\u0435\u0441\u044b'] || client['interests'] || '';
    const body_text = template
      .replace(/{name}/g, name || '\u041a\u043b\u0438\u0435\u043d\u0442')
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
}"""

# Unicode escape sequences used above (for reference):
# \u0423\u0432\u0430\u0436\u0430\u0435\u043c\u044b\u0439 = Уважаемый
# \u0418\u043c\u044f = Имя
# \u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f = Компания
# \u0418\u043d\u0442\u0435\u0440\u0435\u0441\u044b = Интересы
# \u041a\u043b\u0438\u0435\u043d\u0442 = Клиент

for node in wf['nodes']:
    if node['name'] == 'Expand Clients':
        node['parameters']['jsCode'] = EXPAND_CLIENTS_CODE
        # Verify no garbling
        has_cyrillic = any(0x0400 <= ord(c) <= 0x04FF for c in EXPAND_CLIENTS_CODE)
        high_latin = sum(1 for c in EXPAND_CLIENTS_CODE if 0x00C0 <= ord(c) <= 0x00FF)
        print(f'Expand Clients: has_cyrillic={has_cyrillic}, high_latin={high_latin}')

with open('src/n8n/workflows/taris-campaign-send.json', 'w', encoding='utf-8') as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)
print('Saved.')
