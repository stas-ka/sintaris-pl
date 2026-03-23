# OpenClaw Integration Architecture

## Overview

Taris (sintaris-pl) ist bidirektional mit OpenClaw (sintaris-openclaw) integriert.

```
┌─────────────────────────────────────────────────────────────────┐
│  sintaris-pl (Taris AI Voice Assistant)                        │
│                                                                 │
│  LLM_PROVIDER=openclaw                                          │
│  bot_llm.py::_ask_openclaw()                                    │
│    └─ subprocess: openclaw agent -m "..." --json --session-id taris │
│                         │                                       │
└─────────────────────────┼───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  sintaris-openclaw (OpenClaw AI Gateway)                        │
│                                                                 │
│  skills:                                                        │
│  skill-taris    → POST http://localhost:8080/api/chat           │
│  skill-postgres → pgvector RAG (1665 chunks, §4.2)             │
│  skill-n8n      → N8N Workflows                                 │
│  skill-espocrm  → CRM                                           │
│  skill-nextcloud→ Files                                         │
└─────────────────────────────────────────────────────────────────┘
```

## Picoclaw vs OpenClaw — Vergleich

| Merkmal | picoclaw / taris (`_ask_taris`) | openclaw (`_ask_openclaw`) |
|---------|--------------------------------|---------------------------|
| **Aufruf** | `taris agent -m "<prompt>"` | `openclaw agent -m "<prompt>" --json --session-id taris` |
| **Output-Format** | Plaintext (ANSI-gefiltert) | JSON (`content` / `text` / `response`) → plaintext Fallback |
| **Skills / Tools** | Keine | N8N, PostgreSQL/pgvector, EspoCRM, Nextcloud, Taris selbst |
| **RAG-Unterstützung** | ❌ | ✅ via `skill-postgres` (pgvector, 1665 Chunks, 1536-dim) |
| **Session-Kontext** | ❌ (zustandslos) | ✅ `--session-id taris` — persistenter Kontext im Gateway |
| **Streaming** | ❌ | ✅ (WebSocket, nicht in subprocess genutzt) |
| **Latenz (lokal)** | ~1–5s (Pi 3/4 mit OpenRouter) | ~2–8s (Gateway + Model-Dispatch) |
| **Verfügbarkeit** | Immer (binary lokal) | Nur wenn Gateway läuft (`openclaw-gateway.service`) |
| **TODO §4.2 (Remote RAG)** | ❌ | ✅ erfüllt über `skill-postgres` |
| **Fallback** | → local llama.cpp | → taris/picoclaw → local llama.cpp |

## Fallback-Kette

```
LLM_PROVIDER=openclaw
        │
        ▼ FileNotFoundError (binary nicht gefunden) oder RuntimeError
        │
LLM_PROVIDER=taris (picoclaw)
        │
        ▼ LLM_LOCAL_FALLBACK=1 oder ~/.taris/llm_fallback_enabled vorhanden
        │
local llama.cpp (llama-server auf :8081)
```

**Raspberry Pi ohne OpenClaw:** Fällt automatisch auf `taris` zurück — kein Code-Änderung nötig.  
**Dev-Maschine mit OpenClaw:** `LLM_PROVIDER=openclaw` in `~/.taris/bot.env` aktivieren.

## API-Endpunkte (Taris → OpenClaw-Richtung)

Die `/api/*` Routen werden von `skill-taris` (in sintaris-openclaw) genutzt.

| Method | Endpoint | Auth | Body | Response |
|--------|----------|------|------|----------|
| GET | `/api/status` | Bearer Token | — | `{"status":"ok","version":"...","provider":"..."}` |
| POST | `/api/chat` | Bearer Token | `{"message":"...","timeout":60}` | `{"reply":"..."}` |

**Token-Konfiguration:**
```bash
# Token generieren
python3 -c "import secrets; print(secrets.token_hex(32))"

# In Taris setzen
echo "TARIS_API_TOKEN=<token>" >> ~/.taris/bot.env

# In skill-taris setzen
echo "<token>" > ~/.openclaw/skills/skill-taris/api-keys.txt
```

## Loop-Schutz

⚠️ **Zirkuläre Abhängigkeit vermeiden:**

| Szenario | Risiko | Lösung |
|----------|--------|--------|
| Taris nutzt `LLM_PROVIDER=openclaw` UND skill-taris sendet Chat an Taris | Endlosschleife | skill-taris nur für Status/Datenabfragen nutzen; Taris-LLM auf separaten Provider konfigurieren |
| OpenClaw → skill-taris → Taris-LLM → OpenClaw | Loop | skill-taris Anfragen vermeiden wenn Taris `LLM_PROVIDER=openclaw` hat |

## Konfiguration aktivieren

### Schritt 1: Token generieren und setzen
```bash
TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "TARIS_API_TOKEN=$TOKEN" >> ~/.taris/bot.env
echo "$TOKEN" > ~/.openclaw/skills/skill-taris/api-keys.txt
chmod 600 ~/.openclaw/skills/skill-taris/api-keys.txt
```

### Schritt 2: LLM_PROVIDER aktivieren (optional)
```bash
echo "LLM_PROVIDER=openclaw" >> ~/.taris/bot.env
# Dienste neu starten:
systemctl --user restart taris-web.service taris-telegram.service
```

### Schritt 3: Verifikation
```bash
# Taris API erreichbar?
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/status | python3 -m json.tool

# OpenClaw kann Taris abfragen?
openclaw agent -m "Was ist der Status von Taris?" --json
```

## Test-Suite

Unit-Tests für `_ask_openclaw()`:
```bash
cd /home/stas/projects/sintaris-pl
WEB_ONLY=1 PYTHONPATH=src python3 -m pytest src/tests/llm/ -v
# → 18 Tests, alle grün
```

Getestete Szenarien:
- Binary nicht gefunden → `FileNotFoundError` (ask_llm Fallback greift)
- Binary via `shutil.which` oder absoluter Pfad gefunden
- JSON-Parsing: `content`, `text`, `response` Keys; Priorität `content`
- Plaintext-Fallback bei nicht-JSON Output
- Fehlerbehandlung: rc≠0, leerer Output, Timeout
- Dispatch-Routing: `LLM_PROVIDER=openclaw` → `_ask_openclaw`
- `ask_llm_with_history`: Conversation als Text-Transcript formatiert
