# §28–30 OpenClaw Extensions — Spec

**Version:** `2026.4.68` · **Created:** April 2026  
**Based on:** OpenClaw architecture research (session 2026-04-19)  
→ Architecture reference: [openclaw-integration.md](../architecture/openclaw-integration.md)  
→ Stacks reference: [stacks.md](../architecture/stacks.md)  
→ TODO entries: [TODO.md §28–30](../../TODO.md#28-openclaw-quick-wins)

---

## Context

OpenClaw variant (`DEVICE_VARIANT=openclaw`) already has significant infrastructure in place that is
not yet wired to the user-facing features. This spec covers three tiers of work to extend the
OpenClaw variant's functionality and make the overall architecture more modular.

**Assets already in code that are NOT yet wired:**

| Asset | Location | Status |
|---|---|---|
| `vec_embeddings` table (pgvector 1536-dim, HNSW index) | `src/core/store_postgres.py` | Schema exists; nothing populates it |
| `_ask_openclaw()` — gateway skill dispatch | `src/core/bot_llm.py` | Works for LLM; structured skill results ignored |
| `/webhook/n8n` inbound handler | `src/features/bot_n8n.py` | Receives payloads; no event routing table |
| `MCP_SERVER_ENABLED`, `MCP_REMOTE_URL` | `src/core/bot_config.py` | Constants exist; no endpoints |
| `get_ollama_model()` / `set_ollama_model()` | `src/core/bot_llm.py` | Works; no model list UI |
| `set_per_func_provider()` — per-function LLM routing | `src/core/bot_llm.py` | Defined; no admin UI |
| `bot_embeddings.py` — fastembed wrapper | `src/core/bot_embeddings.py` | Exists; not called at upload time |

---

## §28 Quick Wins (1–2 days each) — OpenClaw Extensions

### 28.1 RAG Document Embedding — wire upload → pgvector

**Goal:** When a document is uploaded on OpenClaw, auto-compute embeddings and store in `vec_embeddings`.
On each LLM call, retrieve top-3 semantically similar chunks and inject into system prompt.

**Implementation plan:**

| Step | File | Change |
|---|---|---|
| 1. Compute chunks + embeddings on upload | `features/bot_documents.py` | After `store.save_document()`, call `_embed_and_store_chunks(doc_id, text)` |
| 2. Embedding helper | `core/bot_embeddings.py` | Add `embed_and_store(doc_id, text, chat_id)` → chunks (600 words, 100 overlap) → fastembed → INSERT `vec_embeddings` |
| 3. Similarity search at LLM call | `core/bot_llm.py` | In `ask_llm_with_history()`: if `DEVICE_VARIANT=openclaw` + `RAG_ENABLED`, run `store.vector_search(embed(prompt), top_k=3)` → inject into system prompt |
| 4. Config constant | `core/bot_config.py` | `RAG_VECTOR_TOP_K = 3`, `RAG_INJECT_MAX_CHARS = 1500` |
| 5. Guard | | Only when `STORE_BACKEND=postgres` + `RAG_ENABLED=1` |

**Test:** T-new: upload PDF → send related question → verify LLM response cites document content.

**Effort:** ~1 day. Chunk + embed already implemented in `bot_embeddings.py`; only wiring needed.

---

### 28.2 Ollama Model List UI

**Goal:** Admin panel shows list of installed Ollama models with memory/speed info; admin can switch active model and trigger `ollama pull`.

**Implementation plan:**

| Step | File | Change |
|---|---|---|
| 1. List models | `core/bot_llm.py` | `list_ollama_models()` → `GET http://OLLAMA_HOST/api/tags` → parse JSON |
| 2. Admin Telegram UI | `telegram/bot_admin.py` | In LLM Settings menu: "🦙 Models" button → inline list with `[active]` marker + size + estimated RAM |
| 3. Pull model | `telegram/bot_admin.py` | "➕ Pull model" → text input → `POST /api/pull {"name": model}` → progress feedback via Telegram |
| 4. Web UI | `bot_web.py` | `/admin/llm` page: add model picker dropdown + pull input field |

**Test:** Admin selects different model → LLM response uses new model (`/api/show` confirms).

**Effort:** ~1 day. REST API calls to Ollama already pattern-established in `_ask_ollama()`.

---

### 28.3 N8N → Taris Inbound Event Router

**Goal:** N8N can push structured events to Taris (`/webhook/n8n`), which routes them to internal handlers.
Example: N8N posts `{"event": "lead_created", "data": {...}}` → Taris auto-creates contact.

**Implementation plan:**

| Step | File | Change |
|---|---|---|
| 1. Event dispatch table | `features/bot_n8n.py` | `_N8N_EVENT_HANDLERS = {"lead_created": _handle_lead_created, "note_added": _handle_note_added, ...}` |
| 2. Router in webhook handler | `features/bot_n8n.py` | Parse `event` field → call matching handler; unknown events → log + ignore |
| 3. Lead → contact handler | `features/bot_n8n.py` | `_handle_lead_created(data)` → validate fields → `store.upsert_contact(...)` → notify admin chat |
| 4. Config | `core/bot_config.py` | `N8N_INBOUND_EVENTS_ENABLED = bool(...)` — feature flag |
| 5. Security | | Reuse existing `verify_incoming_signature()` — already implemented |

**Test:** `curl -X POST /webhook/n8n -H "X-Signature: ..." -d '{"event":"lead_created","data":{"name":"Test","email":"..."}}' ` → contact appears in Taris.

**Effort:** ~1 day. Webhook endpoint and HMAC verification already exist.

---

### 28.4 Contact → N8N Sync Button

**Goal:** In Contacts detail view, a "Sync to CRM" button POSTs the contact to a configurable N8N webhook, triggering EspoCRM create/update.

**Implementation plan:**

| Step | File | Change |
|---|---|---|
| 1. Telegram button | `features/bot_contacts.py` | Add `[📤 Sync to CRM]` inline button → callback `cnt_sync_crm:<id>` |
| 2. Handler | `features/bot_contacts.py` | Load contact, call `bot_n8n.call_webhook(CRM_SYNC_WH, contact_dict)` |
| 3. Config | `core/bot_config.py` | `CRM_SYNC_WEBHOOK_URL = os.environ.get("CRM_SYNC_WEBHOOK_URL", "")` |
| 4. Web UI | `bot_web.py` | Contacts detail page: "Sync to CRM" button → `POST /api/contacts/{id}/sync` |
| 5. i18n | `strings.json` | `cnt_sync_crm_btn`, `cnt_sync_crm_ok`, `cnt_sync_crm_err` (ru/en/de) |

**Test:** Click Sync → N8N webhook receives contact JSON → EspoCRM creates/updates record.

**Effort:** ~0.5 day. Pattern from existing N8N webhook calls.

---

## §29 Medium Effort (3–5 days each) — OpenClaw Extensions

### 29.1 Per-User Ollama Model Preference

**Goal:** Users can choose their preferred Ollama model (fast vs. quality). Admin configures defaults per role.

**Implementation plan:**

| Step | File | Change |
|---|---|---|
| 1. Preference storage | `core/store_base.py` + adapters | Add `user_pref_llm_model` column to `users` table (migration) |
| 2. User UI | `telegram/bot_users.py` | Settings → "🤖 AI Model" → show available models → pick one → store preference |
| 3. LLM routing | `core/bot_llm.py` | `_ask_ollama()`: check `user_prefs.get("llm_model")` → override `OLLAMA_MODEL` |
| 4. Role defaults | `core/bot_config.py` | `ROLE_DEFAULT_OLLAMA_MODEL = {"guest": "qwen2:0.5b", "user": "qwen3:8b", "admin": "qwen3:8b"}` |
| 5. Admin control | `telegram/bot_admin.py` | Admin can reset any user's model preference |

**DB migration:** `ALTER TABLE users ADD COLUMN llm_model TEXT DEFAULT ''`  
**Test:** User selects `qwen2:0.5b` → fast responses; switches to `qwen3:8b` → better quality.  
**Effort:** ~2 days.

---

### 29.2 RAG in Voice Pipeline

**Goal:** Before calling LLM on a voice utterance, semantically search user's documents and inject top results into system prompt.

**Implementation plan:**

| Step | File | Change |
|---|---|---|
| 1. Embed voice utterance | `features/bot_voice.py` | After STT result: `rag_ctx = await _vector_rag_context(chat_id, stt_text)` |
| 2. RAG context builder | `core/bot_llm.py` | `_vector_rag_context(chat_id, query)` → embed query → `store.vector_search()` → format as injection |
| 3. Inject into voice LLM call | `core/bot_llm.py` | `_with_lang_voice()`: prepend rag_ctx to system prompt when non-empty |
| 4. Guard | | Only when `DEVICE_VARIANT=openclaw` + `RAG_ENABLED` + `STORE_BACKEND=postgres` |
| 5. Config | `core/bot_config.py` | `VOICE_RAG_ENABLED = bool(...)`, `VOICE_RAG_TOP_K = 2` (fewer chunks for latency) |

**Test:** Upload project timeline PDF → ask via voice "when is my project deadline?" → LLM cites document date.  
**Effort:** ~2 days (depends on §28.1 being done first).

---

### 29.3 OpenClaw Gateway Skill Result Rendering

**Goal:** When `_ask_openclaw()` returns structured JSON (skill result), parse and render as a Telegram card (formatted list/table) instead of raw text.

**Implementation plan:**

| Step | File | Change |
|---|---|---|
| 1. Parse gateway response | `core/bot_llm.py` | `_ask_openclaw()`: if response JSON has `skill_result` key → pass to renderer |
| 2. Renderer | `ui/render_telegram.py` | `render_skill_result(skill_name, result_dict)` → Markdown card with title + fields |
| 3. Known skill schemas | `core/bot_llm.py` | Registry: `{"list_notes": _render_notes_list, "search_contacts": _render_contact_list, ...}` |
| 4. Fallback | | Unknown skill → render as YAML code block |

**Test:** `_ask_openclaw("list my notes")` → Telegram shows formatted notes card, not JSON blob.  
**Effort:** ~1.5 days.

---

### 29.4 EspoCRM Two-Way Contact Sync (via N8N)

**Goal:** Changes in Taris contacts trigger N8N → EspoCRM update; N8N pushes EspoCRM changes → Taris (via §28.3 inbound router).

**Implementation plan:**

| Step | File | Change |
|---|---|---|
| 1. Outbound: contact change → N8N | `features/bot_contacts.py` | On `_save_contact()` / `_delete_contact()`: call `_maybe_sync_to_crm(contact, action)` |
| 2. Sync helper | `features/bot_contacts.py` | `_maybe_sync_to_crm()`: if `CRM_SYNC_WEBHOOK_URL` set → `call_webhook()` with `{"action":"upsert"/"delete","contact":{...}}` |
| 3. Inbound: N8N → Taris | (§28.3) | `_handle_contact_updated(data)` → find existing contact by email/phone → merge fields |
| 4. Duplicate detection | `core/store_postgres.py` | `find_contact_by_email_or_phone()` — needed for merge |
| 5. Admin toggle | `core/bot_config.py` | `CRM_SYNC_ENABLED`, `CRM_SYNC_DEDUPE_FIELD` (email/phone/name) |

**Effort:** ~3 days (§28.3 + §28.4 must be done first).

---

## §30 Architecture Flexibility Improvements

### 30.1 LLM Provider Plugin Extraction

**Goal:** Replace the monolithic 8-provider `_DISPATCH` dict in `bot_llm.py` (800+ lines) with a provider plugin pattern. Each provider becomes a separate module with a shared `Protocol`.

**Current state:** All providers (`_ask_taris`, `_ask_ollama`, `_ask_openclaw`, `_ask_openai`, …) are inline functions in `bot_llm.py`.

**Proposed structure:**
```
src/core/llm_providers/
  __init__.py       ← LLMProvider Protocol + registry loader
  ollama.py         ← OllamaProvider
  openclaw.py       ← OpenClawProvider
  openai_p.py       ← OpenAIProvider
  taris.py          ← TarisProvider (picoclaw binary)
```

**Protocol:**
```python
class LLMProvider(Protocol):
    name: str
    def call(self, prompt: str, chat_id: int, timeout: int) -> str: ...
    def is_available(self) -> bool: ...
```

**Migration strategy:** Incremental — extract one provider at a time; keep `_DISPATCH` as thin wrapper pointing to new modules.

**Benefits:**
- Each provider unit-testable in isolation
- New providers: add one file, register in `__init__.py`
- Per-variant defaults as data, not code

**Effort:** ~4 days (low risk; no behavior change).

---

### 30.2 STT Provider Protocol

**Goal:** Extract STT implementations from the 1600-line `bot_voice.py` into swappable provider objects.

**Proposed structure:**
```
src/core/stt_providers/
  __init__.py       ← STTProvider Protocol + factory
  vosk_stt.py       ← VoskSTT (streaming hotword + command)
  faster_whisper.py ← FasterWhisperSTT (batch, OpenClaw)
```

**Protocol:**
```python
class STTProvider(Protocol):
    def transcribe(self, pcm: bytes, lang: str = "ru") -> str: ...
    def is_available(self) -> bool: ...
```

**`bot_voice.py` after:** `stt = stt_factory(STT_PROVIDER)` → `result = stt.transcribe(pcm)` — no more if/else chains.

**Effort:** ~3 days. No behavior change; improves testability.

---

### 30.3 Variant as Composition (`VariantConfig` dataclass)

**Goal:** Replace scattered `if DEVICE_VARIANT == "openclaw"` checks with a single `VariantConfig` object constructed at startup.

**Proposed:**
```python
# src/core/device_variant.py
@dataclass
class VariantConfig:
    name: str
    stt_engine: str           # "vosk" | "faster_whisper"
    llm_default: str          # "taris" | "ollama"
    storage_backend: str      # "sqlite" | "postgres"
    has_rest_api: bool
    has_n8n: bool
    has_pgvector: bool
    has_session_context: bool

VARIANT_REGISTRY = {
    "picoclaw": VariantConfig("picoclaw", "vosk", "taris", "sqlite", False, False, False, False),
    "openclaw": VariantConfig("openclaw", "faster_whisper", "ollama", "postgres", True, True, True, True),
}

# loaded once at startup in bot_config.py:
VARIANT = VARIANT_REGISTRY.get(DEVICE_VARIANT, VARIANT_REGISTRY["picoclaw"])
```

**Usage in code:**
```python
# Before:
if DEVICE_VARIANT == "openclaw":
    ...

# After:
if VARIANT.has_pgvector:
    ...
```

**Benefits:** Adding a new variant (e.g., `pi5`, `vps-lite`) = one dict entry. No code changes needed.

**Migration:** Incremental — add `VariantConfig`, replace checks one module at a time.

**Effort:** ~2 days (pure refactor; test coverage required).

---

## Implementation Order (recommended)

```
Week 1 — Quick wins (no dependencies):
  28.1 RAG embedding wiring
  28.2 Ollama model list UI
  28.3 N8N inbound event router

Week 2 — Quick wins + medium start:
  28.4 Contact → N8N sync
  29.1 Per-user Ollama model preference
  29.3 Gateway skill result rendering

Week 3–4 — Medium effort:
  29.2 RAG in voice pipeline (needs 28.1)
  29.4 EspoCRM two-way sync (needs 28.3 + 28.4)

Parallel / background — Architecture:
  30.1 LLM provider plugin extraction (incremental, low risk)
  30.2 STT provider protocol (incremental, low risk)
  30.3 VariantConfig dataclass (incremental, low risk)
```

---

## Test Coverage Requirements

Every item above **must** add tests. New T-numbers to allocate:

| Test ID | Item | Type |
|---|---|---|
| T200 | 28.1 — RAG embedding written on upload | unit: store_postgres |
| T201 | 28.1 — RAG context injected into LLM prompt | integration: bot_llm |
| T202 | 28.2 — Ollama model list returned correctly | unit: bot_llm |
| T203 | 28.3 — Inbound N8N event `lead_created` → contact created | integration: bot_n8n |
| T204 | 28.3 — Unknown event ignored (no crash) | unit: bot_n8n |
| T205 | 28.4 — Contact sync button → webhook called | unit: bot_contacts |
| T210 | 29.1 — User model preference stored and used in LLM call | integration |
| T211 | 29.2 — Voice utterance triggers RAG context injection | integration |
| T220 | 30.1 — Each LLM provider returns non-empty string | unit per provider |
| T221 | 30.2 — STT provider factory returns correct class | unit |
| T222 | 30.3 — VariantConfig correct fields for each variant | unit |
