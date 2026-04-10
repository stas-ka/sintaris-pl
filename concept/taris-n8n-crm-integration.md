# Taris + N8N + CRM — Integration Architecture Concept

**Version:** 1.2 · **Date:** 2026-04-10  
**Author:** Architecture Proposal · **Status:** Concept  
**Scope:** Taris as central console for N8N workflow automation + CRM integration  
**References:** TODO.md §11, §13, §23 · `doc/todo/8.4-crm-platform.md` · `concept/additional/crm_system_requirements_full.md` · `Демонстрашка для работы с базой клиентов.drawio`

---

## 1. Executive Summary

This document proposes an architecture for integrating **Taris** (AI voice/chat assistant), **N8N** (workflow automation), and a **CRM** (EspoCRM or lightweight built-in) into a unified platform. The user interacts with Taris via Telegram, Web UI, or voice — and Taris acts as the **central operator console** for launching, monitoring, and controlling automated business processes.

### Key Principles

| # | Principle | Description |
|---|-----------|-------------|
| P1 | **Taris = Console** | All process control flows through Taris Dashboard (Telegram + Web UI) |
| P2 | **N8N = Engine** | N8N executes workflows; Taris triggers and monitors them |
| P3 | **Skills = Glue** | OpenClaw skills bridge Taris ↔ N8N ↔ CRM via REST/webhook |
| P4 | **LLM = Intelligence** | Ollama/OpenAI classifies user intents, generates scripts, analyzes data |
| P5 | **Voice-first** | All operations triggerable by voice or text — no mandatory GUI clicks |
| P6 | **Offline-capable** | Core CRM data in PostgreSQL; N8N on same host; works without internet |
| P7 | **MCP-ready** | Every service exposes MCP tools → one protocol, many clients (Taris, Copilot, Claude) |

---

## 2. Current State

### What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| Taris Telegram bot | ✅ Running | `src/telegram_menu_bot.py` |
| Taris Web UI (FastAPI) | ✅ Running | `src/bot_web.py`, port 8080 |
| Voice assistant | ✅ Running | `src/voice_assistant.py` |
| LLM backend (Ollama + OpenAI) | ✅ Running | `src/core/bot_llm.py` |
| PostgreSQL + pgvector | ✅ Running (SintAItion) | `src/core/store_postgres.py` |
| REST API (`/api/status`, `/api/chat`) | ✅ Running | `src/bot_web.py` |
| Screen DSL (YAML menus) | ✅ Running | `src/ui/`, `src/screens/` |
| Contacts module | ✅ Basic CRUD | `src/features/bot_contacts.py` |
| Calendar + reminders | ✅ Full | `src/features/bot_calendar.py` |
| Document RAG | ✅ FTS5 + pgvector | `src/features/bot_documents.py` |
| Admin panel (LLM switch, restart) | ✅ Running | `src/telegram/bot_admin.py` |
| sintaris-openclaw gateway | ✅ Installed | `~/projects/sintaris-openclaw/` |
| skill-taris (gateway → Taris API) | ✅ Connected | `skill-taris` in gateway |
| skill-postgres (pgvector RAG) | ✅ Connected | `skill-postgres` in gateway |
| **skill-n8n** | 🔲 Defined, not wired | `skill-n8n` in gateway |
| **skill-espocrm** | 🔲 Defined, not wired | `skill-espocrm` in gateway |
| **N8N instance** | 🔲 Not installed | — |
| **EspoCRM instance** | 🔲 Not installed | — |

### What's Missing

1. **N8N instance** running on SintAItion or TariStation2
2. **CRM** — either EspoCRM or a lightweight built-in module in Taris
3. **Taris ↔ N8N bridge** — skill to trigger/monitor N8N workflows
4. **Central Dashboard** — unified view of running processes, CRM data, tasks
5. **Workflow templates** — pre-built N8N flows for CRM scenarios

---

## 3. Target Architecture

### 3.1 System Overview Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                              │
│                                                                     │
│  📱 Telegram         🌐 Web UI (8080)        🎤 Voice Assistant    │
│  @taris_bot          Dashboard + Chat          Hotword → STT → LLM  │
│                                                                     │
└────────────┬──────────────────┬───────────────────────┬─────────────┘
             │                  │                       │
             ▼                  ▼                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     TARIS CORE (sintaris-pl)                        │
│                                                                     │
│  telegram_menu_bot.py ←→ bot_web.py ←→ voice_assistant.py          │
│         │                    │                    │                  │
│         ▼                    ▼                    ▼                  │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  🧠 LLM Intent Classifier (bot_llm.py)                 │       │
│  │  "запусти обзвон клиентов" → {intent: crm_campaign}    │       │
│  │  "покажи задачи на сегодня" → {intent: crm_tasks}      │       │
│  │  "статус рассылки" → {intent: n8n_status}              │       │
│  └─────────────────────┬───────────────────────────────────┘       │
│                        │                                            │
│  ┌─────────────────────▼───────────────────────────────────┐       │
│  │  📋 Action Router (bot_actions.py / bot_n8n.py)         │       │
│  │                                                         │       │
│  │  crm_* intents → CRM Adapter                           │       │
│  │  n8n_* intents → N8N Adapter                            │       │
│  │  dashboard_*   → Dashboard Renderer                     │       │
│  └────────┬──────────────┬──────────────────┬──────────────┘       │
│           │              │                  │                       │
└───────────┼──────────────┼──────────────────┼───────────────────────┘
            │              │                  │
            ▼              ▼                  ▼
┌───────────────┐ ┌────────────────┐ ┌────────────────────────────────┐
│ 🗃️ CRM       │ │ ⚙️ N8N         │ │ 🔗 OpenClaw Gateway            │
│ Adapter       │ │ Adapter        │ │ (sintaris-openclaw)            │
│               │ │                │ │                                │
│ Option A:     │ │ REST API       │ │ skill-n8n → N8N REST           │
│ Built-in      │ │ :5678          │ │ skill-espocrm → EspoCRM API   │
│ (PostgreSQL)  │ │                │ │ skill-postgres → pgvector RAG  │
│               │ │ Webhooks       │ │ skill-taris → Taris /api/chat  │
│ Option B:     │ │ :5678/webhook/ │ │                                │
│ EspoCRM API   │ │                │ │ MCP Server (stdio/SSE)         │
│ :8889         │ │                │ │                                │
└───────┬───────┘ └───────┬────────┘ └────────────────────────────────┘
        │                 │
        ▼                 ▼
┌─────────────────────────────────────┐
│  🐘 PostgreSQL (shared)             │
│                                     │
│  taris DB    — users, calendar,     │
│                notes, chat_history, │
│                documents, vectors   │
│                                     │
│  crm DB      — contacts, deals,    │
│                tasks, history,      │
│                campaigns            │
│                                     │
│  n8n DB      — workflows,          │
│                executions, creds    │
└─────────────────────────────────────┘
```

### 3.2 Component Roles

| Component | Role | Protocol | Port |
|-----------|------|----------|------|
| **Taris** (sintaris-pl) | Central console: UI, chat, voice, LLM, dashboard | Telegram API, HTTPS | 8080 |
| **OpenClaw Gateway** (sintaris-openclaw) | Skills hub, MCP server, agent routing | REST, MCP stdio/SSE | 18789 |
| **N8N** | Workflow automation engine | REST API + Webhooks | 5678 |
| **CRM** (EspoCRM or built-in) | Contact/deal/task data store | REST API (or direct SQL) | 8889 (EspoCRM) |
| **PostgreSQL** | Shared data layer | SQL | 5432 |
| **Ollama** | Local LLM (intent classification, text generation) | REST API | 11434 |

---

## 4. Integration Patterns

### 4.1 Pattern A: Direct REST (Recommended for MVP)

Taris calls N8N and CRM directly via REST API. No gateway intermediary needed for simple triggers.

```
User: "Запусти рассылку для клиентов из Москвы"
  │
  ▼
Taris LLM: classify intent → {action: "crm_campaign", filter: "city=Москва"}
  │
  ▼
Taris bot_n8n.py: POST http://localhost:5678/webhook/campaign-trigger
  Body: {"filter": "city=Москва", "user_id": 12345}
  │
  ▼
N8N workflow "campaign-trigger":
  1. Query CRM: GET contacts where city=Москва
  2. LLM: generate personalized message per contact
  3. Send via email/Telegram
  4. POST http://localhost:8080/api/n8n/callback
     Body: {"workflow_id": "abc", "status": "done", "sent": 42}
  │
  ▼
Taris: notify user "✅ Рассылка завершена: 42 контакта обработано"
```

### 4.2 Pattern B: Via OpenClaw Skills (For Complex Multi-Step)

For complex scenarios requiring tool chaining, RAG context, and multi-step reasoning:

```
User: "Подбери клиентов для мероприятия по AI-автоматизации"
  │
  ▼
Taris LLM: complex intent → route to OpenClaw agent
  │
  ▼
OpenClaw agent -m "Select clients for AI automation event" --json --session-id taris
  │
  ├── skill-postgres: vector search for relevant contacts
  ├── skill-espocrm: get contact details + history
  ├── skill-n8n: trigger "ai-client-matcher" workflow
  │     └── N8N: LLM scores each contact → returns ranked list
  └── return JSON results to Taris
  │
  ▼
Taris: display results in Dashboard card / Telegram message
```

### 4.3 Pattern C: N8N → Taris Callback (Event-Driven)

N8N workflows can push notifications back to Taris:

```
N8N cron job (daily 08:00):
  1. Query overdue tasks from CRM
  2. Compile daily summary
  3. POST http://localhost:8080/api/n8n/callback
     Body: {"type": "daily_digest", "data": {...}}
  │
  ▼
Taris /api/n8n/callback handler:
  → format message
  → send to all admin users via Telegram
  → display on Web UI dashboard
```

### 4.4 Pattern D: MCP-First Integration (Unified Protocol)

Instead of Taris calling N8N/CRM via bespoke REST adapters, **all services expose and consume tools via MCP** (Model Context Protocol). This creates a uniform, LLM-native integration layer.

```
User: "Подбери клиентов для мероприятия по AI"
  │
  ▼
Taris LLM (bot_llm.py) — with MCP tool-use capability
  │
  ├── MCP call: n8n_list_workflows()           ← N8N MCP Server
  ├── MCP call: crm_search("AI automation")    ← EspoMCP / built-in MCP
  ├── MCP call: n8n_trigger("event-matcher")   ← N8N MCP Server Trigger
  │
  ▼ (async — N8N workflow runs, calls back)
  │
  ├── N8N MCP Client Tool → taris_rag_search() ← Taris MCP Server
  │   (N8N enriches contacts with Taris knowledge base)
  │
  ▼
Taris: display results, ask user confirmation
```

**Three MCP integration vectors:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MCP INTEGRATION TOPOLOGY                             │
│                                                                         │
│  ┌─────────────────┐     MCP (SSE/stdio)      ┌───────────────────┐   │
│  │ Taris LLM       │ ─────────────────────────▶│ N8N MCP Server    │   │
│  │ (MCP Client)    │                           │ Trigger node      │   │
│  │                 │ ◀─────────────────────────│ (exposes workflows│   │
│  │ • bot_llm.py    │     MCP tool responses    │  as MCP tools)    │   │
│  │ • tool_use mode │                           └───────────────────┘   │
│  └───────┬─────────┘                                                    │
│          │                                                              │
│          │ MCP (SSE)        ┌───────────────────┐                      │
│          ├─────────────────▶│ EspoMCP Server    │                      │
│          │                  │ (31★ GitHub)       │                      │
│          │                  │ CRM CRUD tools     │                      │
│          │                  └───────────────────┘                      │
│          │                                                              │
│          │ MCP (SSE)        ┌───────────────────┐                      │
│          └─────────────────▶│ Taris MCP Server  │                      │
│                             │ (sintaris-openclaw)│                      │
│                             │ RAG, calendar,     │                      │
│  ┌─────────────────┐       │ notes, status      │                      │
│  │ N8N Workflows   │ ──────│                    │                      │
│  │ (MCP Client     │  MCP  └───────────────────┘                      │
│  │  Tool node)     │                                                    │
│  └─────────────────┘                                                    │
│                                                                         │
│  ┌─────────────────┐       ┌───────────────────┐                      │
│  │ VS Code Copilot │ ──MCP─│ n8n-mcp-server    │                      │
│  │ Claude Desktop  │       │ (1598★ GitHub)     │                      │
│  │ Any MCP client  │       │ manage workflows   │                      │
│  └─────────────────┘       └───────────────────┘                      │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key components:**

| Component | Role | Source | Transport |
|-----------|------|--------|-----------|
| **N8N MCP Server Trigger** | Exposes N8N workflows as MCP tools | Built-in N8N node | SSE `:5678/mcp/...` |
| **N8N MCP Client Tool** | N8N consumes external MCP tools | Built-in N8N node | SSE to any MCP server |
| **n8n-mcp-server** (npm) | External MCP server for N8N management API | [leonardsellem/n8n-mcp-server](https://github.com/leonardsellem/n8n-mcp-server) (1598★) | stdio/SSE |
| **N8N2MCP** | Converts any N8N workflow into standalone MCP server | [Super-Chain/N8N2MCP](https://github.com/Super-Chain/N8N2MCP) (130★) | SSE |
| **EspoMCP** | MCP server for EspoCRM CRUD | [zaphod-black/EspoMCP](https://github.com/zaphod-black/EspoMCP) (31★) | stdio/SSE |
| **Taris MCP Server** | Existing sintaris-openclaw gateway | `~/projects/sintaris-openclaw/` | SSE `:18789` |

### 4.5 How N8N's Built-in MCP Works

**N8N as MCP Server** (MCP Server Trigger node):
- Attach workflow tools to the MCP Server Trigger node
- Each workflow becomes a callable MCP tool
- Clients (Taris LLM, Claude, Copilot) discover and call tools dynamically
- Auth: Bearer token or Header auth
- Transport: SSE or Streamable HTTP
- Limitation: requires single webhook replica (no load balancing for MCP SSE)

**N8N as MCP Client** (MCP Client Tool node):
- Connect N8N AI Agent to external MCP servers
- N8N workflows can call Taris RAG search, calendar, CRM tools
- Auth: Bearer, Header, or OAuth2
- Selectable tool filtering (all / selected / all-except)

```
# Example: N8N workflow uses Taris knowledge for contact enrichment
N8N AI Agent node
  └── MCP Client Tool → http://localhost:18789/mcp/sse
       └── taris_rag_search("AI automation consulting")
       └── taris_calendar_events("next week")
```

---

## 4A. Comparison: Direct API vs MCP Integration

### Decision Matrix

| Criterion | Direct REST API (Patterns A–C) | MCP-First (Pattern D) |
|-----------|-------------------------------|----------------------|
| **Complexity** | Low — simple HTTP calls | Medium — MCP client/server setup |
| **Coupling** | Tight — Taris knows N8N/CRM API details | Loose — tools discovered dynamically |
| **Latency** | Low — direct HTTP, ~50ms | Medium — MCP overhead ~100-200ms |
| **Determinism** | High — code controls exact flow | Medium — LLM decides which tools |
| **Extensibility** | New service = new adapter code | New service = register MCP server |
| **Multi-client** | Taris only | Taris + Copilot + Claude + any MCP client |
| **LLM tool-use required** | No — code-driven routing | Yes — LLM must support tool calling |
| **Error handling** | Explicit try/catch per endpoint | MCP protocol error + LLM retry |
| **Offline support** | Full (localhost REST) | Full (localhost SSE) |
| **Debugging** | Easy — HTTP logs | Harder — MCP protocol traces |
| **N8N workflow changes** | Update webhook URL in code | N8N auto-exposes new tools |
| **Setup effort (N8N)** | API key + webhook URL | MCP Server Trigger node + auth |
| **Setup effort (CRM)** | REST adapter module | EspoMCP server (TypeScript) |
| **Ecosystem maturity** | Proven, stable | Young but growing fast (2024-2026) |

### When to Use Which

| Scenario | Recommended Pattern | Why |
|----------|-------------------|-----|
| Simple trigger (start workflow, get result) | **A: Direct REST** | Minimal overhead, deterministic |
| Complex multi-tool orchestration | **D: MCP-First** | LLM chains tools intelligently |
| N8N → Taris notifications (cron, events) | **C: Callback** | N8N pushes, no polling |
| VS Code / Claude also needs N8N access | **D: MCP-First** | Same tools, multiple clients |
| MVP / first integration | **A: Direct REST** | Fastest to implement |
| Production scale with many services | **D: MCP-First** | Uniform protocol, auto-discovery |
| Offline Pi (PicoClaw) | **A: Direct REST** | No MCP server overhead |
| OpenClaw with full stack | **D: MCP-First** | Leverages existing gateway |

### Hybrid Strategy (Recommended)

**Don't choose one — use both.** The patterns complement each other:

```
┌─────────────────────────────────────────────────────────┐
│                   HYBRID ARCHITECTURE                    │
│                                                         │
│  DETERMINISTIC PATH (Patterns A+C):                     │
│  ├── Taris bot_n8n.py → N8N webhook (trigger workflows) │
│  ├── N8N → Taris /api/n8n/callback (push events)        │
│  └── Taris bot_crm.py → PostgreSQL (direct CRUD)        │
│                                                         │
│  INTELLIGENT PATH (Pattern D):                          │
│  ├── Taris LLM → MCP → N8N MCP Server (complex tasks)   │
│  ├── Taris LLM → MCP → EspoMCP (smart CRM queries)      │
│  ├── N8N AI Agent → MCP → Taris (RAG enrichment)         │
│  └── Copilot/Claude → MCP → all services                │
│                                                         │
│  ROUTER LOGIC (bot_llm.py):                             │
│  if intent is simple_trigger → Pattern A (direct REST)   │
│  if intent is complex/multi_tool → Pattern D (MCP)       │
│  if event is push/cron → Pattern C (callback)            │
└─────────────────────────────────────────────────────────┘
```

**Phase 1 (MVP):** Direct REST (Patterns A+C) — fast, no MCP dependency  
**Phase 2:** Add MCP Server Trigger in N8N for tool exposure  
**Phase 3:** Taris LLM gains tool-use → routes complex queries via MCP  
**Phase 4:** Full MCP ecosystem (EspoMCP, n8n-mcp-server, Taris MCP)

### MCP Ecosystem — Ready-Made Servers

| Server | Stars | Language | What it does | Install |
|--------|-------|----------|-------------|---------|
| [n8n-mcp-server](https://github.com/leonardsellem/n8n-mcp-server) | 1598 | TypeScript | Manage N8N workflows/executions/webhooks via MCP | `npm i -g @leonardsellem/n8n-mcp-server` |
| [N8N2MCP](https://github.com/Super-Chain/N8N2MCP) | 130 | Python | Convert any N8N workflow into standalone MCP server | Docker or pip |
| [EspoMCP](https://github.com/zaphod-black/EspoMCP) | 31 | TypeScript | Full EspoCRM CRUD via MCP | npm/Docker |
| N8N built-in MCP Server Trigger | — | N8N node | Expose workflows as MCP tools natively | N8N workflow editor |
| N8N built-in MCP Client Tool | — | N8N node | Consume external MCP tools in workflows | N8N workflow editor |
| Taris MCP Server (sintaris-openclaw) | — | Node.js | RAG, calendar, chat, status | Already installed |

### Cost-Benefit per Service

| Service | Direct API effort | MCP effort | MCP benefit |
|---------|-----------------|-----------|-------------|
| **N8N trigger** | 1 day (bot_n8n.py) | 0.5 day (MCP Server Trigger in N8N) | Multi-client access, auto-discovery |
| **N8N management** | 2 days (full API wrapper) | 0.5 day (install n8n-mcp-server) | 17 tools pre-built, maintained by community |
| **CRM built-in** | 2 days (store_crm.py) | 2 days (same — custom code anyway) | No advantage — already in our stack |
| **EspoCRM** | 3 days (REST adapter) | 1 day (install EspoMCP) | Pre-built, well-tested CRUD |
| **RAG knowledge** | Already done | Already done (MCP Phase D) | N8N can query Taris knowledge |
| **Calendar** | Already done | 0.5 day (expose via MCP) | N8N workflows can read/write calendar |

### Implementation: Adding MCP Client to Taris LLM

For Pattern D, `bot_llm.py` needs MCP tool-use capability:

```python
# src/core/bot_llm.py — MCP tool-use extension

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client

# MCP servers registry (from bot.env)
_MCP_SERVERS = {
    "n8n": os.environ.get("MCP_N8N_URL", ""),          # N8N MCP Server Trigger
    "crm": os.environ.get("MCP_CRM_URL", ""),          # EspoMCP or built-in
    "n8n_mgmt": os.environ.get("MCP_N8N_MGMT_URL", ""), # n8n-mcp-server
}

async def _ask_llm_with_tools(prompt: str, chat_id: int) -> str:
    """LLM call with MCP tool-use. Ollama/OpenAI tool_call → MCP execution."""
    # 1. Discover available tools from all MCP servers
    tools = await _discover_mcp_tools()
    
    # 2. Ask LLM with tools (Ollama /api/chat with tools parameter)
    response = await _ask_ollama_with_tools(prompt, tools)
    
    # 3. If LLM requests tool calls, execute them via MCP
    while response.get("tool_calls"):
        results = await _execute_mcp_calls(response["tool_calls"])
        response = await _continue_with_results(prompt, results)
    
    return response["content"]
```

### New `bot.env` Variables for MCP Integration

```bash
# MCP Integration (Pattern D)
MCP_N8N_URL=http://localhost:5678/mcp/sse        # N8N MCP Server Trigger endpoint
MCP_N8N_MGMT_URL=                                 # n8n-mcp-server (stdio or SSE)
MCP_CRM_URL=                                      # EspoMCP SSE endpoint (if using Option B)
MCP_N8N_BEARER_TOKEN=                             # Auth token for N8N MCP Server Trigger
MCP_CRM_BEARER_TOKEN=                             # Auth token for EspoMCP
MCP_TOOL_USE_ENABLED=0                            # Enable LLM tool-use mode (0=off, 1=on)
MCP_TOOL_USE_THRESHOLD=complex                    # When to use tools: always|complex|never
```

---

## 4B. Adaptive LLM Workflows — OpenClaw with Flexible LLM

> **When to read:** When designing LLM-driven process automation, agent loops, or dynamic tool selection.

### The Vision: LLM as Workflow Orchestrator

Today Taris routes intents via **static code** (`if intent == "campaign": trigger_n8n()`).
The goal is **adaptive orchestration**: the LLM **reasons** about what tools to call, in what order, with what parameters — and adjusts its plan based on intermediate results.

```
┌─────────────────────────────────────────────────────────────────────┐
│  STATIC (today)                 ADAPTIVE (target)                  │
│                                                                     │
│  User → regex/keyword           User → LLM + tool-use              │
│    ↓                              ↓                                │
│  if "campaign" → n8n_hook       LLM sees tools: [crm_search,       │
│    ↓                            n8n_trigger, calendar_add, ...]     │
│  hardcoded workflow               ↓                                │
│    ↓                            LLM reasons: "need clients first"  │
│  fixed response                   ↓ calls crm_search(budget>10k)   │
│                                 LLM: "47 found, now send campaign" │
│                                   ↓ calls n8n_trigger(...)         │
│                                 LLM: "track results until Friday"  │
│                                   ↓ calls calendar_add(...)        │
│                                 LLM: "✅ Done. 47 clients, 3 tools"│
└─────────────────────────────────────────────────────────────────────┘
```

### How It Works: Agentic Loop in bot_llm.py

The core change is a new function `ask_llm_with_tools()` that implements a **ReAct-style loop**:

```
ask_llm_with_tools(messages, tools, max_iterations=10)
│
├─ Iteration 1: LLM receives [system + history + user] + tool definitions
│  └─ LLM returns: tool_call("crm_search", {filter: "budget>10k"})
│     └─ Execute tool → inject result as {"role": "tool", "content": "47 contacts..."}
│
├─ Iteration 2: LLM receives [previous context + tool result]
│  └─ LLM returns: tool_call("n8n_trigger", {workflow: "campaign", contacts: [...]})
│     └─ Execute tool → inject result
│
├─ Iteration 3: LLM receives [context + all prior results]
│  └─ LLM returns: text response "✅ Campaign started for 47 clients"
│     └─ Loop ends (text = final answer)
│
└─ Guards: max_iterations, per-tool timeout, total budget, error retry
```

### Provider Support for Tool-Use

| Provider | Native Tool-Use | Format | Status in Taris |
|----------|----------------|--------|-----------------|
| **OpenAI** (gpt-4o, gpt-4o-mini) | ✅ Full | `tools` param + `tool_calls` response | Ready to implement |
| **Anthropic** (claude-3.5+) | ✅ Full | `tools` param + `tool_use` content block | Ready to implement |
| **Ollama** (qwen3.5, gemma4) | ✅ Via `/api/chat` | `tools` param + `message.tool_calls` | Ready — qwen3.5 & gemma4 support this |
| **Gemini** (1.5 pro+) | ✅ Full | `function_declarations` + `function_call` | Ready to implement |
| **YandexGPT** | ❌ No | — | Text-only fallback |
| **Local llama.cpp** | ⚠️ Limited | Grammar-constrained JSON | Experimental |
| **OpenClaw CLI** | ❌ No (text-only) | — | Would need gateway-side tool-use |

**Model Requirements for Reliable Tool-Use:**
- OpenAI: gpt-4o-mini or better (gpt-3.5 tool-use is unreliable)
- Ollama: qwen3.5:latest (9B) — tested 100% quality, supports tool_call
- Ollama: gemma4:e2b / gemma4:e4b — supports tool_call natively
- Anthropic: claude-3.5-sonnet or better

### What OpenClaw Brings: Flexible Model Switching

OpenClaw's **dynamic model picker** (Admin → LLM → Switch Model) enables a unique advantage: **adapting the LLM to the workflow complexity live**.

| Scenario | Model | Why |
|----------|-------|-----|
| Simple Q&A chat | gemma4:e2b (2.3B) | Fast (3–5s), low memory, sufficient |
| CRM search + single action | qwen3.5:latest (9B) | Good tool-use, 100% quality |
| Multi-tool chain (3+ tools) | gpt-4o-mini via OpenAI | Best tool-use reliability, handles complex chains |
| Complex workflow creation | gpt-4o or claude-3.5 | Needed for generating N8N workflow JSON |
| Voice command → single tool | gemma4:e4b (4.5B) | Audio-native + tool-use in one call |

**Adaptive Model Selection (proposed):**

```python
def _select_model_for_tools(user_text: str, available_tools: list) -> str:
    """Choose model based on task complexity."""
    tool_count = len(available_tools)
    text_len = len(user_text)

    if tool_count == 0:
        return OLLAMA_MODEL                    # default chat model
    elif tool_count <= 3 and text_len < 200:
        return "gemma4:e4b"                    # local, fast, tool-capable
    elif tool_count <= 6:
        return "qwen3.5:latest"                # local, 100% quality
    else:
        return "gpt-4o-mini"                   # cloud, best tool-use
```

### Five Levels of Adaptive Workflow

| Level | Capability | LLM Role | Example |
|-------|-----------|----------|---------|
| **L0** (today) | Static routing | Intent classification only | "campaign" → fixed webhook |
| **L1** | Parameterized triggers | LLM extracts parameters | "send to budget > 10k" → webhook + params |
| **L2** | Single-tool selection | LLM chooses 1 tool from N | "find clients" → crm_search vs n8n_list |
| **L3** | Multi-tool chaining | LLM chains 2–5 tools | search → filter → trigger → schedule |
| **L4** | Workflow generation | LLM creates N8N workflows | "automate weekly report" → new N8N flow |
| **L5** | Self-improving agent | LLM optimizes workflows based on outcomes | A/B test campaigns, adjust targeting |

**Current state: L0. Realistic near-term target: L2–L3.**

### Implementation Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    Taris + OpenClaw Adaptive Stack                  │
│                                                                    │
│  ┌──────────────────────────────────────────────┐                  │
│  │  User Interface (Telegram / Web UI / Voice)   │                  │
│  └───────────────────┬──────────────────────────┘                  │
│                      │                                              │
│  ┌───────────────────▼──────────────────────────┐                  │
│  │  bot_llm.py — ask_llm_with_tools()            │                  │
│  │  • Tool schema registry                       │                  │
│  │  • Agentic loop (max 10 iterations)           │                  │
│  │  • Adaptive model selection                   │                  │
│  │  • Provider-specific tool-call parsing         │                  │
│  └───┬────────┬────────┬────────┬───────────────┘                  │
│      │        │        │        │                                   │
│  ┌───▼──┐ ┌──▼───┐ ┌──▼───┐ ┌──▼────┐  ← Tool Execution Layer    │
│  │ CRM  │ │ N8N  │ │ RAG  │ │Calendar│                             │
│  │search│ │trigger│ │query │ │ add   │                              │
│  └───┬──┘ └──┬───┘ └──┬───┘ └──┬────┘                             │
│      │        │        │        │                                   │
│  ┌───▼────────▼────────▼────────▼───────────┐                      │
│  │  Tool Registry (MCP or local function)    │                      │
│  │  • Local tools: calendar, notes, RAG      │                      │
│  │  • MCP tools: N8N, CRM, Nextcloud         │                      │
│  │  • Discovery: /tools/list endpoint         │                      │
│  └──────────────────────────────────────────┘                      │
│                                                                    │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐       │
│  │ Ollama (local)  │  │ OpenAI (cloud)  │  │ Anthropic      │       │
│  │ qwen3.5/gemma4  │  │ gpt-4o-mini     │  │ claude-3.5     │       │
│  └────────────────┘  └────────────────┘  └────────────────┘       │
└────────────────────────────────────────────────────────────────────┘
```

### Tool Schema Example

Each tool exposed to the LLM follows a standard schema:

```json
{
  "type": "function",
  "function": {
    "name": "crm_search_contacts",
    "description": "Search CRM contacts by criteria. Returns list of matching contacts with name, email, tags, budget.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "Search text or filter expression"},
        "segment": {"type": "string", "enum": ["all", "active", "lead", "partner"]},
        "limit": {"type": "integer", "default": 20}
      },
      "required": ["query"]
    }
  }
}
```

### Proposed Tool Registry (bot.env)

```bash
# Tool-use configuration
TOOL_USE_ENABLED=1                    # Master switch (0=disabled, 1=enabled)
TOOL_USE_MAX_ITERATIONS=10            # Max agentic loop iterations
TOOL_USE_TIMEOUT=120                  # Total timeout for tool-use chain (seconds)
TOOL_USE_PROVIDERS=ollama,openai,anthropic  # Providers supporting tool-use

# Tool categories (enable/disable per category)
TOOL_USE_CATEGORIES=crm,n8n,calendar,rag,notes
# Per-tool timeout (seconds)
TOOL_TIMEOUT_CRM=10
TOOL_TIMEOUT_N8N=30
TOOL_TIMEOUT_RAG=5
```

### Live Adaptation Scenarios

**Scenario 1: Voice → Adaptive CRM Action**
```
User (voice): "Найди клиентов с бюджетом больше 50 тысяч и отправь им приглашение"
  ↓ STT (faster-whisper) → text
  ↓ ask_llm_with_tools(text, tools=[crm_search, n8n_trigger, ...])
  ↓ LLM (qwen3.5): tool_call("crm_search", {query: "budget>50000"})
  ↓ Execute → 12 contacts found
  ↓ LLM: tool_call("n8n_trigger", {workflow: "send-invite", contacts: [...]})
  ↓ Execute → N8N workflow started
  ↓ LLM: "Найдено 12 клиентов, приглашения отправлены."
  ↓ TTS (Piper) → audio response
```

**Scenario 2: LLM Adjusts Mid-Flow**
```
User: "Запусти еженедельный отчет по продажам"
  ↓ LLM: tool_call("n8n_list_workflows", {tag: "report"})
  ↓ Execute → 3 workflows found: weekly-sales, monthly-summary, daily-digest
  ↓ LLM: tool_call("n8n_trigger", {workflow: "weekly-sales"})
  ↓ Execute → ERROR: "Data source not configured"
  ↓ LLM (adjusts): "Workflow 'weekly-sales' requires data source configuration.
                     Available alternative: 'daily-digest' works without setup.
                     Shall I run the daily digest instead?"
  ↓ User: "Да, запусти"
  ↓ LLM: tool_call("n8n_trigger", {workflow: "daily-digest"})
  ↓ Execute → SUCCESS
  ↓ LLM: "✅ Daily digest запущен. Результат будет через 2 минуты."
```

**Scenario 3: Dynamic Workflow via gemma4 Audio**
```
User (audio, German): "Erstelle einen neuen Kontakt Hans Müller, Telefon 0172..."
  ↓ gemma4:e4b (audio-native) → direct text extraction (no separate STT!)
  ↓ tool_call("crm_create_contact", {name: "Hans Müller", phone: "0172..."})
  ↓ Execute → contact created, id=42
  ↓ LLM: "✅ Kontakt Hans Müller erstellt (ID 42)."
  ↓ TTS → audio response
```

### Comparison: Static vs Adaptive

| Criterion | Static Routing (L0) | Adaptive LLM (L2–L3) |
|-----------|--------------------|-----------------------|
| **Setup effort** | Low (hardcode intents) | Medium (tool schemas + loop) |
| **Flexibility** | New intent = new code | New intent = LLM figures it out |
| **Error handling** | Explicit try/catch | LLM retries, suggests alternatives |
| **Multi-step tasks** | Separate buttons/screens | Single prompt chains tools |
| **Latency** | Fast (1 API call) | Slower (2–5 LLM calls in loop) |
| **Determinism** | High (same input → same action) | Medium (LLM may vary) |
| **Cost (cloud LLM)** | Low (1 call) | Higher (N calls per chain) |
| **Cost (local Ollama)** | Low | Low (Ollama is free) |
| **Maintenance** | High (update code per change) | Low (update tool schemas only) |
| **User experience** | Rigid menus | Natural language, feels intelligent |

### Recommended Hybrid Strategy

```
User request
    ↓
┌─────────────────────────────────┐
│ Intent Classifier (fast, local)  │
│ "Is this simple or complex?"     │
└──────┬──────────┬───────────────┘
       │          │
  simple│     complex│
       ↓          ↓
  Static Route    ask_llm_with_tools()
  (Pattern A/B)   (Agentic loop, Pattern D)
  ~50ms           ~3–15s (depends on tools)
```

**Rules:**
- `simple` = single action, deterministic (e.g. "show calendar", "restart service")
- `complex` = multi-step, parameters needed, or user intent ambiguous
- Admin toggle: `TOOL_USE_ENABLED=0` disables all tool-use (fallback to static)
- Per-user opt-in possible via `voice_opts.json` or admin settings

### Decision Points (extends §16)

| # | Question | Options |
|---|----------|---------|
| 10 | **Tool-use level target** | L1 (params only), L2 (single-tool), L3 (multi-chain) |
| 11 | **Default model for tool-use** | Local Ollama (free, 3–15s) vs Cloud (fast, paid) |
| 12 | **Tool categories for MVP** | CRM + N8N only, or include calendar/notes/RAG? |

---

## 5. CRM Strategy: Two Options

### Option A: Built-in CRM (PostgreSQL, Recommended for Sintaris)

Extend existing Taris PostgreSQL with CRM tables. No external dependency.

**Pros:** Single stack, offline-capable, voice-native, full control  
**Cons:** Must build UI from scratch, limited multi-user

```sql
-- Extend existing PostgreSQL schema
CREATE TABLE crm_contacts (
    id SERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    telegram TEXT,
    city TEXT,
    tags TEXT[],              -- AI-generated tags
    segment TEXT,             -- AI-classified segment
    summary TEXT,             -- AI-generated summary
    lead_source TEXT,
    status TEXT DEFAULT 'active',  -- active/in_progress/archive
    owner_user_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE crm_interactions (
    id SERIAL PRIMARY KEY,
    contact_id INT REFERENCES crm_contacts(id),
    type TEXT NOT NULL,       -- call/meeting/email/telegram/note
    content TEXT,
    result TEXT,
    author_user_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE crm_tasks (
    id SERIAL PRIMARY KEY,
    contact_id INT REFERENCES crm_contacts(id),
    title TEXT NOT NULL,
    description TEXT,
    due_date TIMESTAMPTZ,
    priority TEXT DEFAULT 'medium',  -- low/medium/high
    status TEXT DEFAULT 'active',    -- active/done/overdue
    owner_user_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE crm_campaigns (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    target_audience TEXT,     -- AI prompt for selection
    keywords TEXT[],
    status TEXT DEFAULT 'draft',  -- draft/approved/sending/done
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE crm_campaign_contacts (
    campaign_id INT REFERENCES crm_campaigns(id),
    contact_id INT REFERENCES crm_contacts(id),
    ai_score FLOAT,           -- AI relevance score 0.0-1.0
    ai_reason TEXT,           -- why recommended
    invite_status TEXT DEFAULT 'pending',  -- pending/invited/confirmed/declined
    PRIMARY KEY (campaign_id, contact_id)
);
```

**Taris modules to create:**

| Module | File | Purpose |
|--------|------|---------|
| `bot_crm.py` | `src/features/bot_crm.py` | CRM CRUD: contacts, tasks, interactions |
| `bot_n8n.py` | `src/features/bot_n8n.py` | N8N workflow trigger/monitor/callback |
| `crm_screens.yaml` | `src/screens/crm_*.yaml` | Screen DSL for CRM views |
| `store_crm.py` | `src/core/store_crm.py` | CRM data adapter (extends store_base) |

### Option B: EspoCRM (External, for Customer Projects)

Deploy EspoCRM as a separate Docker container. Taris connects via REST API.

**Pros:** Full-featured CRM out of the box, multi-user, proven  
**Cons:** Extra dependency, heavier (PHP+MySQL), online required, separate auth

```yaml
# docker-compose.yml on SintAItion
services:
  espocrm:
    image: espocrm/espocrm:latest
    ports: ["8889:80"]
    volumes:
      - espocrm_data:/var/www/html/data
    environment:
      ESPOCRM_DATABASE_HOST: postgres
      ESPOCRM_DATABASE_NAME: espocrm
```

**Integration via skill-espocrm:**
```
Taris → OpenClaw gateway → skill-espocrm → EspoCRM REST API
```

### Recommendation

**Phase 1 (MVP):** Built-in CRM (Option A) — minimal, voice-native, works on all targets  
**Phase 2 (Customer):** EspoCRM (Option B) — for customer projects needing full CRM features  
**Both phases** share the same Taris UI and N8N integration

---

## 6. N8N Integration Architecture

### 6.1 Installation on SintAItion

```bash
# Install N8N via Docker (recommended)
docker run -d --name n8n \
  -p 5678:5678 \
  -v n8n_data:/home/node/.n8n \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=<secret> \
  -e DB_TYPE=postgresdb \
  -e DB_POSTGRESDB_HOST=localhost \
  -e DB_POSTGRESDB_PORT=5432 \
  -e DB_POSTGRESDB_DATABASE=n8n \
  -e DB_POSTGRESDB_USER=taris \
  -e DB_POSTGRESDB_PASSWORD=<secret> \
  n8nio/n8n:latest

# Or install via npm (lighter, no Docker):
npm install -g n8n
N8N_PORT=5678 n8n start
```

### 6.2 Taris N8N Adapter (`bot_n8n.py`)

```python
# src/features/bot_n8n.py — N8N workflow adapter

import requests
from core.bot_config import N8N_URL, N8N_API_KEY

N8N_URL = os.environ.get("N8N_URL", "http://localhost:5678")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

def trigger_workflow(workflow_id: str, payload: dict) -> dict:
    """Trigger an N8N workflow via webhook."""
    resp = requests.post(
        f"{N8N_URL}/webhook/{workflow_id}",
        json=payload, timeout=30
    )
    return resp.json()

def get_workflow_status(execution_id: str) -> dict:
    """Get execution status from N8N API."""
    headers = {"X-N8N-API-KEY": N8N_API_KEY}
    resp = requests.get(
        f"{N8N_URL}/api/v1/executions/{execution_id}",
        headers=headers, timeout=10
    )
    return resp.json()

def list_workflows() -> list[dict]:
    """List all active workflows."""
    headers = {"X-N8N-API-KEY": N8N_API_KEY}
    resp = requests.get(
        f"{N8N_URL}/api/v1/workflows?active=true",
        headers=headers, timeout=10
    )
    return resp.json().get("data", [])
```

### 6.3 N8N Callback Endpoint in Taris

```python
# In bot_web.py — add callback route

@app.post("/api/n8n/callback")
async def n8n_callback(request: Request):
    """Receive completion/status updates from N8N workflows."""
    data = await request.json()
    event_type = data.get("type")  # daily_digest, campaign_done, task_alert
    
    if event_type == "daily_digest":
        _broadcast_digest(data["data"])
    elif event_type == "campaign_done":
        _notify_campaign_result(data["data"])
    elif event_type == "task_alert":
        _notify_task_alert(data["data"])
    
    return {"status": "ok"}
```

### 6.4 Pre-Built N8N Workflow Templates

| Workflow | Trigger | Actions | Taris Integration |
|----------|---------|---------|-------------------|
| **Daily Digest** | Cron 08:00 | Query overdue tasks → compile summary | POST `/api/n8n/callback` → Telegram broadcast |
| **New Contact AI** | Webhook from Taris | Receive contact data → LLM tags/summary → update CRM | Taris sends on contact create |
| **Campaign Sender** | Webhook from Taris | Get filtered contacts → generate personalized message → send email/TG | Taris triggers, receives report |
| **Event Matcher** | Webhook from Taris | Get event params → LLM scores contacts → return ranked list | Taris displays results |
| **Follow-up Reminder** | Cron hourly | Check upcoming follow-ups → notify assigned user | POST `/api/n8n/callback` → personal TG message |
| **Import Contacts** | Webhook (CSV upload) | Parse CSV → deduplicate → insert into CRM → report | Taris uploads file, receives report |

---

## 7. Central Dashboard (TODO §11)

### 7.1 Dashboard Concept

The Central Dashboard is a unified view accessible via Web UI and Telegram. It shows real-time status of all activities.

```
┌─────────────────────────────────────────────────────────────┐
│  🏠 TARIS DASHBOARD                        v2026.4.XX      │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ 📋 TASKS TODAY   │  │ ⚡ WORKFLOWS     │                │
│  │                  │  │                  │                │
│  │ 3 active         │  │ 2 running        │                │
│  │ 1 overdue ⚠️     │  │ 12 completed ✅  │                │
│  │ 5 completed ✅   │  │ 0 failed         │                │
│  └──────────────────┘  └──────────────────┘                │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ 👥 CRM           │  │ 📊 CAMPAIGNS     │                │
│  │                  │  │                  │                │
│  │ 142 contacts     │  │ "AI Event" 🟢    │                │
│  │ 8 new this week  │  │  42/50 sent      │                │
│  │ 3 need follow-up │  │  12 confirmed    │                │
│  └──────────────────┘  └──────────────────┘                │
│                                                             │
│  ┌──────────────────────────────────────────┐              │
│  │ 💬 QUICK ACTIONS                         │              │
│  │                                          │              │
│  │ [📞 New Contact]  [📨 New Campaign]      │              │
│  │ [▶️ Run Workflow]  [📊 Analytics]        │              │
│  │ [🎤 Voice Command]                       │              │
│  └──────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Dashboard Implementation

| Component | Telegram | Web UI |
|-----------|----------|--------|
| Tasks summary | Inline keyboard card | HTMX dashboard widget |
| Workflow status | Callback buttons | Real-time SSE updates |
| CRM summary | Inline keyboard card | HTMX dashboard widget |
| Quick actions | Button grid | Button row + voice input |
| Analytics | Text report | Chart.js / simple tables |

**Screen DSL definition:**

```yaml
# src/screens/crm_dashboard.yaml
screen: crm_dashboard
title_key: dashboard_title
layout: grid
cards:
  - id: tasks_today
    type: counter
    source: crm.tasks_today_count
    icon: "📋"
    label_key: dashboard_tasks_today
    action: navigate:crm_tasks
    
  - id: workflows_active
    type: counter
    source: n8n.active_executions_count
    icon: "⚡"
    label_key: dashboard_workflows
    action: navigate:n8n_workflows
    
  - id: crm_contacts
    type: counter
    source: crm.contacts_count
    icon: "👥"
    label_key: dashboard_contacts
    action: navigate:crm_contacts
    
  - id: campaigns
    type: status_card
    source: crm.active_campaign
    icon: "📊"
    action: navigate:crm_campaigns

actions:
  - id: new_contact
    label_key: btn_new_contact
    icon: "📞"
    action: navigate:crm_contact_new
    
  - id: new_campaign
    label_key: btn_new_campaign
    icon: "📨"
    action: navigate:crm_campaign_new
    
  - id: run_workflow
    label_key: btn_run_workflow
    icon: "▶️"
    action: navigate:n8n_workflow_list
    
  - id: voice_command
    label_key: btn_voice_command
    icon: "🎤"
    action: voice_input
```

---

## 8. "Демонстрашка" — Demo Scenario

Based on `Демонстрашка для работы с базой клиентов.drawio`:

### Scenario: AI-Powered Client Selection for Event

```
STEP 1: User (via voice or text in Taris)
   "Подбери клиентов для мероприятия по AI-автоматизации для малого бизнеса"

STEP 2: Taris LLM classifies intent
   → {action: "crm_campaign_match", 
      event: "AI-автоматизация для малого бизнеса",
      keywords: ["AI", "автоматизация", "малый бизнес"]}

STEP 3: Taris triggers N8N workflow "event-matcher"
   POST /webhook/event-matcher
   Body: {event_description, keywords, user_id}

STEP 4: N8N workflow:
   4a. Query CRM: SELECT * FROM crm_contacts WHERE status='active'
   4b. Filter: exclude archived, no-contact
   4c. For each contact batch (10): 
       → LLM prompt: "Score this contact for the event. Return JSON {score, reason, invite_format}"
   4d. Rank by score, return top N
   4e. POST /api/n8n/callback {type: "match_results", contacts: [...]}

STEP 5: Taris receives results, displays:
   "🎯 Найдено 15 подходящих клиентов:
    1. Иванов И.И. (0.95) — интересуется автоматизацией, покупал курсы
    2. Петрова А.С. (0.87) — владелец малого бизнеса, ищет решения
    ...
    [✅ Утвердить список] [✏️ Редактировать] [❌ Отмена]"

STEP 6: User approves → Taris triggers "campaign-send" workflow
   OPTIONS (from drawio):
   a) Output selection to file (for manual call in Russia)
   b) Agent generates personalized script per contact
      → Human approves script
   c) Automated send via email/Telegram

STEP 7: N8N sends invitations, reports back
   "✅ Рассылка завершена: 15 приглашений отправлено (12 email, 3 Telegram)"
```

---

## 9. MCP (Model Context Protocol) Integration

> **Full comparison of MCP vs Direct API is in §4A above.** This section focuses on the MCP architecture specific to the Taris+N8N+CRM stack.

### 9.1 MCP Architecture for Taris+N8N+CRM

MCP provides a standardized protocol for LLM ↔ tool communication. This enables Taris (or any MCP-compatible AI client) to discover and use CRM/N8N tools dynamically.

```
┌──────────────────────────────────────────────────────┐
│                   MCP Clients                         │
│                                                      │
│  Taris LLM  ←───→  VS Code Copilot  ←───→ Claude    │
│  (bot_llm.py)       (development)         (web)     │
└──────────┬──────────────────┬────────────────────────┘
           │                  │
           ▼                  ▼
┌──────────────────────────────────────────────────────┐
│              MCP Server (sintaris-openclaw)           │
│                                                      │
│  Tools exposed:                                      │
│  ├── taris_chat(message) → LLM response              │
│  ├── taris_status() → bot version, uptime            │
│  ├── crm_search(query) → contacts                    │
│  ├── crm_create_contact(data) → contact_id           │
│  ├── crm_create_task(data) → task_id                 │
│  ├── n8n_trigger(workflow, payload) → execution_id   │
│  ├── n8n_status(execution_id) → status               │
│  ├── n8n_list_workflows() → [workflows]              │
│  ├── rag_search(query) → relevant chunks             │
│  └── calendar_add(event) → event_id                  │
│                                                      │
│  Resources:                                          │
│  ├── crm://contacts → contact list                   │
│  ├── crm://tasks/today → today's tasks               │
│  ├── n8n://workflows → active workflows              │
│  └── taris://dashboard → dashboard data              │
└──────────────────────────────────────────────────────┘
```

### 9.2 MCP Benefit

With MCP, the same CRM/N8N tools become available to:
- **Taris LLM** — for processing voice/chat commands
- **VS Code Copilot** — for development and debugging
- **Any MCP client** — future integrations (Claude Desktop, custom agents)

---

## 10. Implementation Phases

### Phase 1: Foundation (MVP) — ~2 weeks

| Task | Description | Files |
|------|-------------|-------|
| Install N8N on SintAItion | Docker or npm, PostgreSQL backend | `docker-compose.yml` |
| Create `bot_n8n.py` | N8N REST adapter: trigger, status, list | `src/features/bot_n8n.py` |
| Create `/api/n8n/callback` | Webhook receiver in `bot_web.py` | `src/bot_web.py` |
| Create CRM tables | PostgreSQL schema (§5 above) | `src/core/store_crm.py` |
| Create `bot_crm.py` | Basic CRUD: contacts, tasks, interactions | `src/features/bot_crm.py` |
| Add CRM i18n strings | All 3 languages | `src/strings.json` |
| Add Dashboard screen | Screen DSL YAML | `src/screens/crm_dashboard.yaml` |
| N8N: Daily Digest workflow | Cron → query tasks → notify via callback | N8N JSON export |
| Wire `skill-n8n` | Connect OpenClaw gateway to N8N API | `sintaris-openclaw/skills/skill-n8n/` |

### Phase 2: CRM Intelligence — ~2 weeks

| Task | Description |
|------|-------------|
| LLM intent classifier for CRM | "new contact" / "search" / "campaign" routing |
| AI contact tagging | On create: LLM generates tags, summary, segment |
| Campaign manager | Create campaign → AI match contacts → approve → send |
| N8N: Campaign Sender workflow | Email/TG send with personalized messages |
| N8N: Event Matcher workflow | LLM-scored contact selection |
| Voice CRM commands | "Добавь контакт Иванов, телефон..." via voice |

### Phase 3: Full Dashboard — ~1 week

| Task | Description |
|------|-------------|
| Web UI dashboard widgets | HTMX cards with live counters |
| Telegram dashboard card | Inline keyboard summary |
| Workflow monitor | Real-time execution status display |
| Analytics basic | Contact count, task completion rate, campaign stats |

### Phase 4: MCP + Advanced — ~2 weeks

| Task | Description |
|------|-------------|
| **Install n8n-mcp-server** | `npm i -g @leonardsellem/n8n-mcp-server` — pre-built N8N management tools |
| **Configure N8N MCP Server Trigger** | Expose key workflows (daily-digest, campaign, event-matcher) as MCP tools |
| **Configure N8N MCP Client Tool** | Connect N8N AI Agent to Taris MCP Server for RAG enrichment |
| MCP tools for CRM | `crm_search`, `crm_create_contact`, `crm_create_task` |
| MCP tools for N8N | `n8n_trigger`, `n8n_status`, `n8n_list_workflows` |
| **LLM tool-use in bot_llm.py** | Ollama tool_call support → MCP tool execution loop |
| **MCP_TOOL_USE_THRESHOLD router** | Simple intents → Pattern A, complex → Pattern D |
| Install EspoMCP (optional) | For customer projects needing full CRM via MCP |
| EspoCRM adapter (opt.) | For customer projects needing full CRM |
| Import/export | CSV import contacts, export reports |
| Multi-user CRM | Role-based access (admin/operator) |

---

## 11. Configuration

### New `bot.env` Variables

```bash
# N8N Integration
N8N_URL=http://localhost:5678
N8N_API_KEY=<generated-api-key>
N8N_WEBHOOK_SECRET=<shared-secret>

# CRM Mode
CRM_BACKEND=builtin         # builtin | espocrm
ESPOCRM_URL=http://localhost:8889
ESPOCRM_API_KEY=<api-key>

# Dashboard
DASHBOARD_REFRESH_INTERVAL=60    # seconds
DASHBOARD_DAILY_DIGEST_TIME=08:00
```

### New OpenClaw Skills Configuration

```bash
# ~/.openclaw/skills/skill-n8n/config.json
{
  "n8n_url": "http://localhost:5678",
  "api_key": "<key>",
  "enabled_workflows": ["daily-digest", "campaign-sender", "event-matcher"]
}

# ~/.openclaw/skills/skill-espocrm/config.json  (if using Option B)
{
  "espocrm_url": "http://localhost:8889",
  "api_key": "<key>"
}
```

---

## 12. Hardware Requirements

### SintAItion (TariStation1) — Production

| Service | RAM | CPU | Disk |
|---------|-----|-----|------|
| Taris (Telegram + Web) | ~200 MB | Low | 500 MB |
| Ollama (qwen3.5:latest) | ~10 GB | Medium | 10 GB |
| PostgreSQL | ~300 MB | Low | 2 GB |
| N8N | ~300 MB | Low | 500 MB |
| EspoCRM (optional) | ~500 MB | Low | 1 GB |
| **Total** | **~11.3 GB** | | ~14 GB |

SintAItion has 48 GB RAM — **plenty of headroom**.

### TariStation2 (IniCoS-1) — Engineering

| Service | RAM | Constraint |
|---------|-----|-----------|
| Taris + PostgreSQL | ~500 MB | OK |
| Ollama (qwen2:0.5b) | ~1 GB | Tight on 7.6 GB with Copilot |
| N8N | ~300 MB | OK |
| **Total** | ~1.8 GB (without heavy LLM) | Feasible |

---

## 13. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| N8N webhook abuse | Shared secret in `N8N_WEBHOOK_SECRET`; validate on both sides |
| CRM data access | Same PostgreSQL auth; Taris RBAC (admin/user roles) |
| N8N API exposure | Bind to localhost only; no external port |
| EspoCRM API (if used) | API key auth; localhost only |
| Personal data in LLM | Obfuscate PII before sending to cloud LLM; local Ollama preferred |

---

## 14. Testing Strategy

| Test | Type | Tool |
|------|------|------|
| N8N adapter unit tests | Offline mock | `src/tests/test_n8n_adapter.py` |
| CRM CRUD tests | DB integration | `src/tests/test_crm.py` |
| N8N webhook callback | Integration | `src/tests/test_n8n_callback.py` |
| Dashboard rendering | Screen DSL | `src/tests/screen_loader/` |
| Demo scenario E2E | Manual + script | `src/tests/test_crm_demo.py` |
| Regression T-tests | Existing suite | T122+ for CRM/N8N features |

---

## 15. Relationship to Existing TODO Items

| TODO Item | How This Concept Addresses It |
|-----------|------------------------------|
| §8.4 CRM Platform Vision | Phase 1–2 implement C1 (contacts) and C2 (deals) |
| §11 Central Dashboard | Phase 3 implements the unified dashboard |
| §13 Smart CRM | Phase 2 adds AI tagging, matching, voice control |
| §23.2 N8N + PostgreSQL clone | Phase 1 installs N8N on SintAItion |
| §23.5 Clone Worksafety DB + N8N | Future: reuse same N8N integration for Worksafety |

---

## 16. Decision Points for Owner

Before implementation begins, decide:

1. **CRM backend:** Built-in PostgreSQL (lightweight, offline) or EspoCRM (full-featured, Docker)?
2. **N8N installation:** Docker container or npm global install?
3. **Target for MVP:** SintAItion only, or both TariStation2 + SintAItion?
4. **Demo data:** Import real client data or use synthetic test data?
5. **Campaign channel:** Email only, Telegram only, or both?
6. **Priority:** Start with CRM module or N8N integration first?
7. **Integration pattern:** Start with Direct REST only (Pattern A, fastest MVP) or Hybrid from day one?
8. **MCP for N8N:** Use N8N built-in MCP Server Trigger (zero-code) or external n8n-mcp-server (more tools)?
9. **LLM tool-use:** Enable Ollama tool_call for MCP integration? (requires qwen3.5+ or gemma4 with tool support)

---

→ [Back to TODO.md](../TODO.md) · [CRM spec](../doc/todo/8.4-crm-platform.md) · [OpenClaw integration](../doc/architecture/openclaw-integration.md)
