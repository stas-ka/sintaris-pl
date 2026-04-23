# N8N Setup Guide — KB MCP Server & Ingest

**Prerequisite:** N8N 2.2.3 ✅ (MCP Server Trigger supported)

---

## Step 1 — VPS: Create taris_kb database (requires confirmation)

```bash
source .env
bash deploy/system-configs/vps/mcp-kb/deploy.sh
```

This runs `init_taris_kb.sql` — creates DB, schema, roles. Idempotent.

---

## Step 2 — VPS: Deploy parse_doc.py + install Docling

```bash
# Copy parser to VPS
sshpass -p "$VPS_PWD" scp -o StrictHostKeyChecking=no \
  deploy/system-configs/vps/mcp-kb/parse_doc.py \
  $VPS_USER@$VPS_HOST:/opt/taris-mcp-kb/parse_doc.py

# Install Docling on VPS (requires confirmation — pip install)
# sshpass -p "$VPS_PWD" ssh $VPS_USER@$VPS_HOST \
#   "pip3 install --user docling pdfminer.six python-docx"
```

> ⚠️ `pip3 install` on VPS requires explicit confirmation before running.

Verify:
```bash
ssh $VPS_USER@$VPS_HOST "python3 /opt/taris-mcp-kb/parse_doc.py 2>&1 | head -3"
```
Expected: `{"ok": false, "error": "Usage: ..."}` (no crash = parser is present)

---

## Step 3 — N8N: Create Postgres credential

In N8N UI → **Credentials** → New → **Postgres**:

| Field | Value |
|---|---|
| Name | `KB Postgres` |
| Host | `127.0.0.1` |
| Port | `5432` |
| Database | `taris_kb` |
| User | `taris_kb_writer` |
| Password | *(from `.env` / `init_taris_kb.sql`)* |
| SSL | Disable (localhost) |

---

## Step 4 — N8N: Set workflow variables (N8N Variables)

In N8N UI → **Settings** → **Variables** → Add:

| Variable | Value | Notes |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Or remote Ollama URL if not on VPS |
| `EMBED_MODEL` | `multilingual-e5-small` | Must be pulled in Ollama: `ollama pull multilingual-e5-small` |
| `KB_INGEST_TOKEN` | *(value of `N8N_KB_TOKEN` from `.env`)* | Bearer token for ingest webhook auth |
| `KB_CHUNK_SIZE` | `512` | Chars per chunk |
| `KB_CHUNK_OVERLAP` | `50` | Overlap chars |

---

## Step 5 — N8N: Import and activate workflows

1. In N8N UI → **Workflows** → **Import from File**
2. Import `src/n8n/workflows/KB - MCP Server.json`
3. Import `src/n8n/workflows/KB - Ingest.json`
4. In each workflow, open the **Postgres** node → assign **KB Postgres** credential
5. **Activate** both workflows (toggle in top-right)

---

## Step 6 — Get the MCP Server SSE URL

After activating **KB - MCP Server**, open the MCP Server Trigger node.
Copy the **Production SSE URL** shown in the node (format: `https://agents.sintaris.net/n8n/mcp/kb-server/sse` or similar).

Set in Taris bot.env (all targets: TS2, TS1, VPS):
```bash
MCP_REMOTE_URL=https://agents.sintaris.net/n8n/mcp/kb-server/sse
```

Get the **N8N API Key**: N8N UI → Settings → API → Create key.
Set:
```bash
N8N_KB_API_KEY=<api-key>
```

Get the **Ingest webhook URL**: open KB - Ingest workflow → Ingest Webhook node → copy Production URL.
Set:
```bash
N8N_KB_WEBHOOK_INGEST=https://agents.sintaris.net/n8n/webhook/kb-ingest
```

---

## Step 7 — Smoke test

```bash
source .env

# 1. Test MCP Server health (tools/list via MCP protocol)
python3 -c "
import asyncio
from mcp.client.sse import sse_client
from mcp import ClientSession

async def test():
    url = '$MCP_REMOTE_URL'
    headers = {'X-N8N-API-Key': '$N8N_KB_API_KEY'}
    async with sse_client(url, headers=headers) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print('Tools:', [t.name for t in tools.tools])

asyncio.run(test())
"
# Expected: Tools: ['kb_search', 'kb_memory_get', 'kb_memory_append', ...]

# 2. Test ingest webhook (upload a test file)
curl -X POST "$N8N_KB_WEBHOOK_INGEST" \
  -H "Authorization: Bearer $N8N_KB_TOKEN" \
  -F "chat_id=1" \
  -F "filename=test.txt" \
  -F "mime=text/plain" \
  -F "file=@/tmp/test_kb.txt"
# Expected: {"doc_id": "...", "n_chunks": N, ...}
```

---

## Step 8 — Enable in Taris

On each target after tests pass:
```bash
# In ~/.taris/bot.env:
REMOTE_KB_ENABLED=1
MCP_REMOTE_URL=https://agents.sintaris.net/n8n/mcp/kb-server/sse
N8N_KB_API_KEY=<api-key>
N8N_KB_WEBHOOK_INGEST=https://agents.sintaris.net/n8n/webhook/kb-ingest
N8N_KB_TOKEN=<webhook-token>
```

Restart taris service after config change.

---

## Ollama: pull embedding model

If Ollama is available on VPS:
```bash
ollama pull multilingual-e5-small
```

If Ollama is NOT on VPS, point `OLLAMA_URL` to TariStation1:
```
OLLAMA_URL=http://<ts1-ip>:11434
```
(Set as N8N Variable, not hardcoded.)

---

## Troubleshooting

| Issue | Check |
|---|---|
| Embed Query fails | Ollama running? `curl $OLLAMA_URL/api/tags` |
| PG node fails | Credential correct? `taris_kb` DB exists? |
| `parse_doc.py` not found | Step 2 done? Check `/opt/taris-mcp-kb/parse_doc.py` |
| Ingest auth error | `KB_INGEST_TOKEN` N8N variable matches `N8N_KB_TOKEN` in bot.env |
| MCP SSE connect fails | Workflow activated? API key correct? |
| `multilingual-e5-small` unknown | `ollama pull multilingual-e5-small` on Ollama host |
