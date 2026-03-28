# OpenClaw Integration Architecture

**Version:** `2026.4.13`  
→ Architecture index: [architecture.md](../architecture.md)  
→ Deployment variants: [deployment.md §Deployment Variants](deployment.md)  
→ Installation guide: [../install-new-target.md §Part B](../install-new-target.md)

## Overview

Taris (`sintaris-pl`) supports two deployment variants, controlled by `DEVICE_VARIANT` in `bot.env`:

| Variant | Hardware | LLM | REST API | Storage |
|---|---|---|---|---|
| **PicoClaw** | Raspberry Pi 3/4/5 | taris/picoclaw → openai/local | — | SQLite |
| **OpenClaw** | Laptop / AI PC (x86_64) | openclaw → GPT-5+/Codex | `/api/status` + `/api/chat` | SQLite or PostgreSQL+pgvector |

In the OpenClaw variant, Taris is bidirectionally integrated with `sintaris-openclaw` (Node.js AI gateway).

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

---

## STT Configuration for OpenClaw (Laptop/PC)

The OpenClaw variant uses **faster-whisper** as the default STT engine (instead of Vosk small model).

### STT Provider Comparison

| Engine | Model | WER (Russian) | RTF (i7-2640M, no GPU) | RAM | Recommendation |
|--------|-------|--------------|------------------------|-----|----------------|
| `vosk` | small-ru (48MB) | ~15–20% | ~0.1 | 200MB | Pi 3/4 only |
| `faster_whisper` | tiny | ~12–16% | ~0.15–0.3 | 150MB | Minimal HW |
| `faster_whisper` | base | ~8–12% | ~0.3–0.5 | 300MB | **Recommended OpenClaw** |
| `faster_whisper` | small | ~5–8% | ~0.8–1.2 | 500MB | Good laptop |
| `faster_whisper` | medium | ~3–5% | ~2.5–4.0 | 1.5GB | Fast CPU/GPU |

**Default for `DEVICE_VARIANT=openclaw`:** `STT_PROVIDER=faster_whisper`, `FASTER_WHISPER_MODEL=base`

### Config (`~/.taris/bot.env`)

```bash
# STT
STT_PROVIDER=faster_whisper       # vosk | faster_whisper | whisper_cpp
FASTER_WHISPER_MODEL=base          # tiny | base | small | medium | large-v3
FASTER_WHISPER_DEVICE=cpu          # cpu | cuda
FASTER_WHISPER_COMPUTE=int8        # int8 | float16 | float32

# For NVIDIA GPU (much faster):
FASTER_WHISPER_DEVICE=cuda
FASTER_WHISPER_COMPUTE=float16
```

### Install faster-whisper

```bash
bash src/setup/setup_voice_openclaw.sh   # includes faster-whisper step
# or manually:
pip install faster-whisper
```

### Run STT Benchmark

```bash
python3 src/tests/benchmark_stt.py --all
python3 src/tests/benchmark_stt.py --model tiny base small --audio test.ogg --text "привет пико"
```

---

## LLM Configuration for OpenClaw

### Recommended: Ollama (offline, no API key needed)

```bash
# Install and start
bash src/setup/setup_llm_openclaw.sh        # installs ollama + qwen2:0.5b

# In bot.env
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2:0.5b        # or: llama3.2:1b, phi3:mini, mistral:7b
OLLAMA_URL=http://127.0.0.1:11434
LLM_LOCAL_FALLBACK=1
```

### Alternative: OpenRouter / OpenAI

```bash
# In bot.env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-or-...        # OpenRouter key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openai/gpt-4o-mini
LLM_LOCAL_FALLBACK=1           # Ollama as fallback when cloud fails
```

### Ollama Model Recommendations for i7-2640M (4 cores, 7.6GB RAM, no GPU)

| Model | Size | Speed | Quality | Command |
|-------|------|-------|---------|---------|
| `qwen2:0.5b` | 512MB | ~1-2s | Good for simple commands | `ollama pull qwen2:0.5b` |
| `llama3.2:1b` | 1.3GB | ~3-5s | Better reasoning | `ollama pull llama3.2:1b` |
| `phi3:mini` | 2.3GB | ~5-10s | Strong small model | `ollama pull phi3:mini` |
| `mistral:7b` | 4.1GB | ~15-30s | Best quality | `ollama pull mistral:7b` |

### LLM Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `[LLM] openai failed: OPENAI_API_KEY not set` | Empty key in bot.env | Set `LLM_PROVIDER=ollama` or add `OPENAI_API_KEY` |
| `[LLM] ollama failed: connection refused` | Ollama not running | `systemctl --user start ollama` or `ollama serve &` |
| Empty LLM response | Provider not configured | Check `LLM_PROVIDER` in bot.env; run `bash src/setup/setup_llm_openclaw.sh` |
| Slow responses (~30s) | Using heavy model | Switch to `qwen2:0.5b` or use cloud API |

---

## Implementation Status (v2026.3.28-openclaw)

| Component | Status | Location |
|---|---|---|
| `DEVICE_VARIANT` constant | ✅ Implemented | `src/core/bot_config.py` |
| `OPENCLAW_BIN` constant | ✅ Implemented | `src/core/bot_config.py` |
| `TARIS_API_TOKEN` constant | ✅ Implemented | `src/core/bot_config.py` |
| `STT_PROVIDER` + `FASTER_WHISPER_*` constants | ✅ Implemented | `src/core/bot_config.py` |
| `OLLAMA_URL` + `OLLAMA_MODEL` constants | ✅ Implemented | `src/core/bot_config.py` |
| `faster_whisper_stt` voice opt (OpenClaw default) | ✅ Implemented | `src/core/bot_config.py` |
| `_ask_openclaw()` LLM provider | ✅ Implemented | `src/core/bot_llm.py` |
| `_ask_ollama()` LLM provider | ✅ Implemented | `src/core/bot_llm.py` |
| `LLM_PROVIDER=ollama` dispatch | ✅ Implemented | `src/core/bot_llm.py` |
| `_stt_faster_whisper()` function | ✅ Implemented | `src/features/bot_voice.py` |
| STT routing: faster_whisper → whisper → vosk | ✅ Implemented | `src/features/bot_voice.py` |
| `voice_assistant.py` faster-whisper support | ✅ Implemented | `src/voice_assistant.py` |
| `setup_voice_openclaw.sh` + faster-whisper step | ✅ Implemented | `src/setup/setup_voice_openclaw.sh` |
| `setup_llm_openclaw.sh` (Ollama installer) | ✅ Implemented | `src/setup/setup_llm_openclaw.sh` |
| STT benchmark script | ✅ Implemented | `src/tests/benchmark_stt.py` |
| T27–T30 OpenClaw regression tests | ✅ Implemented | `src/tests/test_voice_regression.py` |
| `GET /api/status` REST endpoint | ✅ Implemented | `src/bot_web.py` |
| `POST /api/chat` REST endpoint | ✅ Implemented | `src/bot_web.py` |
| Bearer-token authentication | ✅ Implemented | `src/bot_web.py` |
| Fallback chain (openclaw→taris→local) | ✅ Implemented | `src/core/bot_llm.py` |
| 18 unit tests for `_ask_openclaw()` | ✅ Implemented | `src/tests/llm/` |
| `store_postgres.py` PostgreSQL adapter | ✅ Implemented | `src/core/store_postgres.py` |
| `bot_embeddings.py` EmbeddingService | ✅ Implemented | `src/core/bot_embeddings.py` |
| `TARIS_HOME` configurable data dir | ✅ Implemented | `src/core/bot_config.py` |
| `sintaris-openclaw-local-deploy` | ✅ Implemented | `~/projects/sintaris-openclaw-local-deploy/` |
| `skill-taris` in sintaris-openclaw | ✅ Implemented | `sintaris-openclaw/skills/skill-taris/` |
| `migrate_sqlite_to_pg.py` | 🔲 Planned | §25.7 |
| pgvector HNSW RAG pipeline | 🔲 Planned | §25.6 Phase B |
| Screen DSL `visible_variants` | 🔲 Planned | §21.6 |
