# taris — Quality Assurance Test Strategy

**When to read:** Before adding tests · When deciding which tests to run · After a production bug · Code review involving test changes  
**See also:** [`doc/test-suite.md`](test-suite.md) for full test registry · [`doc/lessons-learned.md`](lessons-learned.md) for historic bug patterns  
**Version:** 2026.4.75

---

## 1. Philosophy and Research Basis

### 1.1 Core Principles

taris is an **AI-augmented system** combining a Telegram bot, offline voice pipeline, LLM inference, RAG retrieval, and multi-target deployment across two hardware variants. Standard software testing principles apply, extended for AI-specific challenges.

| Principle | Source | Application to taris |
|-----------|--------|----------------------|
| **Test Pyramid** | "Software Testing at Google" (SRE Book §11), Google Testing Blog | Majority = fast local (layers 0–3). Fewer slow E2E + hardware. |
| **Hermetic tests** | Google Testing Blog "Hermetic servers" (2012) | Source-inspection tests T17–T55 run offline with zero external deps. |
| **Fail-fast** | XP/Agile practices | Quick local run (layers 0+1+3, ~40s) always before slower Pi tests. |
| **Test as documentation** | Kent Beck "TDD by Example" | Every T-number docstring states exactly what behavior it guards. |
| **LLM-as-judge evaluation** | Zheng et al. "MT-Bench" (2023), HELM benchmark | T81–T83 pattern: quality evaluation for LLM responses. |
| **RAG evaluation** | RAGAS framework (Es et al. 2023) | `bench_remote_kb.py`: Recall@5, MRR@10, faithfulness. |
| **Property-based testing** | QuickCheck / Hypothesis concepts | T67 (RRF math), T17 (bot_name injection). |
| **Chaos / fault injection** | Netflix Chaos Engineering (2011) | T33 (STT fallback chain), T36 (fallback on primary failure). |
| **Source-inspection testing** | Custom pattern (taris) | AST/regex-based code property checks run offline. |
| **Shift-left security** | OWASP SAMM, "Threat Modeling" (Shostack 2014) | T71 (security_events logging), T116 (RAG admin-only access). |
| **Lessons-learned regression** | Defect prevention (Crosby 1979), "Zero Bug Policy" | Every production bug adds a T-numbered regression test. |

### 1.2 Vibe Coding QA Concept

When LLM-assisted development ("vibe coding") is the primary workflow, specific QA risks increase and require targeted mitigations:

| Vibe-coding risk | How it manifests | Mitigation |
|-----------------|-----------------|------------|
| **Hallucinated API signatures** | Wrong arg count or missing keyword | T20 (calendar TTS sig), T50–T55 function signature checks |
| **Silent behavior regressions** | "Looks right" but breaks edge cases | Source inspection T17+ catches structural invariants |
| **Incomplete RBAC** | LLM forgets `_is_allowed()` guard | T70 (dev menu), T116 (RAG admin), Layer 10 security tests |
| **Stale i18n keys** | New feature, missing translation | T13 runs on every strings.json change |
| **Missing variant guards** | Code ignores `DEVICE_VARIANT` | T29–T30 (OpenClaw routing), T46 (vosk fallback default) |
| **Silent errors swallowed** | `except ImportError: pass` pattern | Regression tests verify error propagation (e.g., T226) |
| **Deploy without restart** | Old code still in memory | Smoke test Layer 7 after every deploy |

**Mandatory QA workflow for every vibe-coded change:**
1. Run Layer 0 (source inspection) locally — catches structural errors in <10s
2. Run Layer 1 (unit tests) — catches mock-level behavior regressions
3. Deploy to engineering target → run Smoke (Layer 7)
4. If bug found after deploy → add regression test BEFORE fixing

---

## 2. Test Layers — Master Table

| # | Layer | Test Files | Runner | Network | Hardware | Speed |
|---|-------|-----------|--------|---------|----------|-------|
| **0** | **Source Inspection** | `test_voice_regression.py` T17–T55+ | custom | ❌ | ❌ | <10s |
| **1** | **Unit / Component** | `telegram/`, `screen_loader/`, `llm/` | pytest | ❌ | ❌ | <30s |
| **2** | **Integration** | `test_n8n_crm.py`, `test_campaign.py`, `test_remote_kb.py` | custom+pytest | ✅ live | ❌ | 30s–2min |
| **3** | **UI Component (DSL)** | `screen_loader/test_screen_loader.py` | pytest | ❌ | ❌ | <10s |
| **4a** | **E2E Web UI** | `ui/test_ui.py` | Playwright | ✅ web | ❌ | 2–5min |
| **4b** | **E2E Internet UI** | `ui/test_external_ui.py` | Playwright | ✅ VPS | ❌ | 2–5min |
| **4c** | **E2E Hardware Voice** | `test_voice_regression.py` T01–T16 | custom | ✅ SSH | ✅ Pi | 2–5min |
| **5** | **Performance / Benchmark** | `benchmark_stt.py`, `bench_remote_kb.py`, `llm/benchmark_ollama_models.py` | custom | ✅ models | Optional | 5–30min |
| **6** | **AI / LLM Evaluation** | T81–T83, `autoresearch_kb/evaluate.py`, T_CS | custom | ✅ Ollama | ❌ | 1–5min |
| **7** | **Deployment / Smoke** | `test_voice_regression.py` on target + journal | custom+SSH | ✅ SSH | ✅ target | 1–3min |
| **8** | **Migration** | T111, T113, T23 | custom | Optional | ❌ | <10s |
| **9** | **Data Consistency** | `test_data_consistency.py` | custom | ✅ DB | ❌ | 30s |
| **10** | **Security / RBAC** | T70–T71, T116, `test_telegram_bot.py` | custom+pytest | ❌ | ❌ | <10s |
| **11** | **Content / Campaign** | `test_content_strategy.py`, `test_content_n8n.py`, `test_campaign.py` | custom+pytest | ✅ N8N | ❌ | 30s–5min |

**Quick Local Run = Layers 0 + 1 + 3 = always run before commit (~40s total)**  
**Full Suite = All 12 layers (some require target + credentials)**

---

## 3. Layer Detail

### Layer 0 — Source Inspection

**Purpose:** Verify code structure, constants, callback keys, function signatures, i18n coverage, import paths — all without running any service or external dependency.  
**When to run:** Before every commit. Fastest safety net against vibe-coding errors.  
**Tool:** `test_voice_regression.py` with named test functions (source-inspection subset).

| T-range | Domain |
|---------|--------|
| T07–T08 | TTS/STT text escaping |
| T13–T14 | i18n string coverage (ru/en/de) + language routing |
| T17–T26 | Bot config, profile, notes, calendar, DB, RAG, web-link |
| T29–T41 | OpenClaw STT/LLM routing, variant config, voice guards |
| T42–T55 | Voice pipeline guards, admin guards, note flows |
| T56–T72 | LLM multi-turn, RAG pipeline, RBAC, security events |
| T73–T116 | Document store, memory context, Postgres, migration, Gemma4 |
| T117–T122 | Ollama model picker |
| T140–T172 | Guest user, RBAC, CRM, appointment flow, prompt templates |
| T200–T211 | OpenClaw extensions: RAG embedding, N8N router, CRM sync, variant config |

**Full source-inspection command:**
```bash
DEVICE_VARIANT=openclaw PYTHONPATH=src \
  python3 src/tests/test_voice_regression.py \
  --test t_confidence_strip t_tts_escape t_i18n_string_coverage t_lang_routing \
  t_bot_name_injection t_profile_resilience t_note_edit_append_replace \
  t_calendar_tts_call_signature t_calendar_console_classifier \
  t_db_voice_opts_roundtrip t_db_migration_idempotent t_rag_lr_products \
  t_web_link_code_roundtrip t_system_chat_clean_output t_openclaw_stt_routing \
  t_openclaw_ollama_provider t_web_stt_provider_routing t_pipeline_logger \
  t_dual_stt_providers t_voice_debug_mode t_stt_language_routing_fw \
  t_stt_fallback_chain t_tts_multilang t_voice_llm_routing \
  t_voice_system_mode_routing_guard t_voice_lang_stt_lang_priority \
  t_set_lang_default_not_hardcoded_en t_voice_system_admin_guard \
  t_rbac_allowlist_enforcement t_dev_menu_rbac t_security_events_logging \
  t_admin_only_rag_access t_doc_store_api_complete t_doc_upload_pipeline \
  t_rag_full_pipeline t_memory_context_assembly t_migrate_postgres_structure \
  t_contacts_store_parity t_guest_user_feature t_crm_n8n_advanced_user \
  t_guest_appointment_flow t_prompt_templates t_rag_embedding_wired \
  t_n8n_event_router t_contact_crm_sync t_variant_config
```

**Key invariants protected by source inspection:**
- All strings.json keys exist in ru/en/de with no empty values
- Every RBAC guard (`_is_allowed`, `_is_admin`, `_is_guest`) present at entry points
- Database adapter methods present for both SQLite + Postgres backends
- Callback data format matches handler dispatch keys
- Voice pipeline uses `ask_llm()` not deprecated `TARIS_BIN` direct calls

---

### Layer 1 — Unit / Component Tests

**Purpose:** Test individual modules in isolation with mocked dependencies.  
**Tool:** pytest with conftest.py stubs (TeleBot, vosk, sounddevice, psycopg2).

| File | Tests | Coverage |
|------|-------|----------|
| `src/tests/telegram/test_telegram_bot.py` | 40+ Telegram handler tests | Bot handlers, callbacks, access control |
| `src/tests/screen_loader/test_screen_loader.py` | 64 Screen DSL tests | Screen YAML/JSON → keyboard rendering |
| `src/tests/llm/test_ask_openclaw.py` | 18 LLM provider tests | ask_llm routing, provider dispatch |

**Command:**
```bash
DEVICE_VARIANT=openclaw PYTHONPATH=src \
  python3 -m pytest src/tests/telegram/ src/tests/screen_loader/ src/tests/llm/ \
  -q --tb=short
```

**Coverage gaps (planned):**
- `bot_calendar.py` unit tests — calendar CRUD operations
- `bot_contacts.py` unit tests — contact create/search/merge
- `bot_security.py` unit tests — `_is_allowed`, `_is_admin`, `_is_guest` under various user states
- `store_postgres.py` unit tests — adapter method contracts with mocked psycopg2
- `bot_email.py` unit tests — email parsing, credential storage

---

### Layer 2 — Integration Tests

**Purpose:** Test module interactions with real external services (N8N, Postgres, MCP).

| File | Tests | External Deps | Offline mode |
|------|-------|---------------|-------------|
| `test_n8n_crm.py` | T40–T43 | N8N webhooks, Postgres CRM | Source check only |
| `test_campaign.py` | T130–T137 | CRM data, N8N campaign workflow | Source check + state machine |
| `test_remote_kb.py` | T200–T232 | VPS PostgreSQL KB, MCP client | `--offline` flag |

**Offline run (no network):**
```bash
PYTHONPATH=src python3 src/tests/test_remote_kb.py --offline
PYTHONPATH=src python3 -m pytest src/tests/test_campaign.py -m "not live" -q
```

**Live run (requires credentials):**
```bash
source .env
PYTHONPATH=src python3 src/tests/test_remote_kb.py
```

---

### Layer 3 — UI Component Tests (Screen DSL)

**Purpose:** Validate Screen DSL loader: YAML/JSON → keyboard/text rendering.  
**File:** `src/tests/screen_loader/test_screen_loader.py` (64 tests)

```bash
PYTHONPATH=src python3 -m pytest src/tests/screen_loader/ -q
```

---

### Layer 4 — End-to-End Tests

#### 4a — Web UI E2E (Playwright, internal)

**File:** `src/tests/ui/test_ui.py` (43+ tests)  
**Prerequisites:** taris-web running on target  
**Coverage:** login/logout, profile, notes CRUD, calendar, document upload, admin panel, voice settings, i18n

```bash
python3 -m pytest src/tests/ui/test_ui.py -v \
  --base-url https://openclawpi2:8080 --browser chromium
```

#### 4b — External UI Tests (VPS-Supertaris)

**File:** `src/tests/ui/test_external_ui.py` (43 tests)

```bash
PICO_BASE_URL=https://agents.sintaris.net/supertaris-vps \
  python3 -m pytest src/tests/ui/test_external_ui.py -v --browser chromium
```

#### 4c — Hardware Voice (Raspberry Pi)

**File:** `test_voice_regression.py` T01–T16 (hardware only)  
**Prerequisites:** Pi with Vosk + Piper installed, audio hardware

```bash
# PI2 engineering target
plink -pw "$HOSTPWD2" -batch stas@OpenClawPI2 \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"

# PI1 production (only after PI2 passes + code on master)
plink -pw "$HOSTPWD" -batch stas@OpenClawPI \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"
```

---

### Layer 5 — Performance / Benchmark Tests

**Purpose:** Track latency regressions; compare models for STT/LLM.  
**⚠ Do NOT run in CI** — takes 5–30min, requires GPU/STT models.

| File | Metrics | When to run |
|------|---------|-------------|
| `benchmark_stt.py` | WER, RTF, load time by model | After faster-whisper model/config change |
| `bench_remote_kb.py` | Recall@5, MRR@10, p50/p95 latency | After KB pipeline changes |
| `llm/benchmark_ollama_models.py` | Latency, tokens/s, quality | After Ollama model change |

**STT benchmark command:**
```bash
DEVICE_VARIANT=openclaw PYTHONPATH=src \
  python3 src/tests/benchmark_stt.py --models tiny,base,small
```

**Output:** Saved to `doc/research/bench-*.md` (append-only, never overwrite).

**Research basis:** Metrics follow ASR evaluation standard WER (Word Error Rate) and RTF (Real-Time Factor). RAG metrics follow RAGAS (Es et al. 2023): Recall@K, MRR, Faithfulness, Answer Relevancy.

---

### Layer 6 — AI / LLM Evaluation Tests

**Purpose:** Verify LLM response quality: correctness, language, format, no hallucination.

**Research basis:**  
- **HELM** (Holistic Eval of Language Models, Liang et al. 2022) — accuracy + calibration + robustness  
- **RAGAS** (Es et al. 2023) — Faithfulness, Answer Relevancy, Context Precision/Recall  
- **MT-Bench / LLM-as-Judge** (Zheng et al. 2023) — pairwise model quality evaluation  

| Test | What it checks | Research pattern |
|------|---------------|------------------|
| T82 `ollama_latency_regression` | Response time within baseline | Performance regression |
| T83 `ollama_quality_ru_calendar` | Russian calendar intent → valid JSON | Format + semantic correctness |
| `autoresearch_kb/evaluate.py` | RAG Recall@5, MRR@10 | RAGAS-inspired |
| `test_content_strategy.py` T_CS_01–T_CS_20 | Content plan quality + N8N routing | LLM-as-judge pattern |

**Planned extensions (roadmap):**
- T_EVAL_01: Multi-language response correctness (ru/en/de comparative)
- T_EVAL_02: Calendar intent → JSON schema validation (systematic)
- T_EVAL_03: RAG faithfulness (answer grounded in retrieved context)
- T_EVAL_04: "I don't know" guard — no hallucination for out-of-scope queries

---

### Layer 7 — Deployment / Smoke Tests

**Purpose:** Verify the running process is healthy after every deploy.

**Success criteria in journal:**
```
[INFO] Version : 2026.X.Y
[INFO] Polling Telegram…
```

| Target | Smoke command |
|--------|--------------|
| TariStation2 | `PYTHONPATH=~/.taris python3 ~/.taris/tests/test_voice_regression.py --test t_variant_config t_openclaw_stt_routing t_i18n_string_coverage` |
| TariStation1 | SSH + same command |
| VPS-Supertaris | `docker exec taris-vps-telegram python3 /app/tests/test_voice_regression.py --test t_variant_config` |
| PI2 / PI1 | `plink ... python3 /home/stas/.taris/tests/test_voice_regression.py --test t_model_files_present t_i18n_string_coverage` |

**Rule:** A deploy is not complete until smoke tests PASS on the deployed target.

---

### Layer 8 — Migration Tests

**Purpose:** Verify data migration scripts are complete, idempotent, and preserve all rows.

| Test | Scope |
|------|-------|
| T23 `db_migration_idempotent` | Migration SQL is safe to run multiple times |
| T111 `migrate_postgres_structure` | All 10 tables present in migration script |
| T113 `postgres_live_data` | Postgres has non-empty live data (SKIP on SQLite) |

**Mandatory migration checklist:**
1. Run T111 (source inspection) — verify migration script completeness
2. Take backup via `/taris-backup-target`
3. Run on engineering target first; verify T113 passes
4. Run on production only after explicit user confirmation

---

### Layer 9 — Data Consistency Tests

**Purpose:** Detect data corruption, orphaned files, schema violations.  
**File:** `src/tests/test_data_consistency.py`  
**Run before:** taking a backup, major deploy, after migration.

**Domains:** users (roles/language), notes (index↔fs sync), calendar (ISO-8601), contacts (email format), documents (file presence), conversation (valid roles), prefs (registered users).

```bash
# On target (SSH or local):
python3 ~/.taris/tests/test_data_consistency.py

# Via VPS Docker:
docker exec taris-vps-telegram python3 /app/tests/test_data_consistency.py
```

**Exit codes:** 0 = PASS, 1 = ERROR/WARN, 2 = runner error.

---

### Layer 10 — Security / RBAC Tests

**Purpose:** Verify access control guards are present and correct for all sensitive operations.

| Test | What is guarded |
|------|----------------|
| T70 `dev_menu_rbac` | Developer menu requires admin role |
| T71 `security_events_logging` | Security events logged to DB |
| T116 `admin_only_rag_access` | RAG retrieval checks is_admin param throughout stack |
| `test_telegram_bot.py` | _is_allowed, _is_admin in handler conftest |
| T140–T157 | Guest user role RBAC, approval flow |

**Known gaps (add to roadmap):**
- `_is_guest()` unit test under various user states
- Rate limiting / abuse prevention test
- Prompt injection defense test in `bot_security.py`
- OAuth/Web session expiry test

---

### Layer 11 — Content / Campaign Integration Tests

**Purpose:** Verify N8N workflow integration, content strategy generation, campaign state machine.

| File | Tests | Mode |
|------|-------|------|
| `test_content_strategy.py` | T_CS_01–T_CS_20 | Source inspection + live |
| `test_content_n8n.py` | T_CN_01–T_CN_12 | Live only (requires VPS N8N) |
| `test_campaign.py` | T130–T137 | Source inspection + state machine |

```bash
# Source inspection (no network)
PYTHONPATH=src python3 -m pytest src/tests/test_content_strategy.py \
  src/tests/test_campaign.py -q --tb=short -m "not live"

# Live N8N tests (requires .env with N8N credentials)
source .env
PYTHONPATH=src python3 -m pytest src/tests/test_content_n8n.py -v -m live
```

---

## 4. Test ID Conventions and Registry

### T-number Allocation

| Range | Domain | File |
|-------|--------|------|
| T01–T16 | **Hardware voice** (Pi only): STT/TTS/VAD/models | `test_voice_regression.py` |
| T17–T55 | **Source inspection**: core bot structure | `test_voice_regression.py` |
| T56–T72 | **LLM context, RAG pipeline, RBAC** | `test_voice_regression.py` |
| T73–T116 | **Document store, memory, Postgres, migration** | `test_voice_regression.py` |
| T117–T122 | **Ollama model picker, Gemma4** | `test_voice_regression.py` |
| T123–T129 | *(reserved)* | — |
| T130–T137 | **Campaign state machine** | `test_campaign.py` |
| T138–T139 | *(reserved)* | — |
| T140–T172 | **Guest user, RBAC, CRM, appointment flow** | `test_voice_regression.py` |
| T173–T199 | *(reserved — next features)* | — |
| T200–T232 | **Remote KB / MCP agent** | `test_remote_kb.py` |
| T_CS_01–T_CS_20 | **Content strategy** (new naming scheme) | `test_content_strategy.py` |
| T_CN_01–T_CN_12 | **Content N8N integration** (live) | `test_content_n8n.py` |
| T_EVAL_01+ | **LLM/AI quality evaluation** | *(future: `test_llm_eval.py`)* |
| T_SEC_01+ | **Security-specific tests** | *(future: `test_security.py`)* |

### Naming Rules

1. Functions in `test_voice_regression.py`: `t_<domain>_<what>()` with `# T<n> —` comment
2. pytest functions: `test_<what>()` in pytest-based files
3. New T-numbers: append sequentially at end of existing range; **never reuse**
4. For every new T: update (a) this file §4, (b) `doc/test-suite.md` §2/§3 table, (c) the test file docstring

### ⚠ Known Naming Collision

`test_remote_kb.py` docstring header references stale labels **T50–T65** — these are from an old version. The canonical T-numbers are **T200–T232** as used throughout `doc/test-suite.md` and the skills. The docstring should be updated to remove the T50–T65 references.

---

## 5. Variant-Aware Testing

| Aspect | PicoClaw (Pi / ARM) | OpenClaw (x86_64) |
|--------|--------------------|--------------------|
| STT | Vosk (T06, T16) | faster-whisper (T27, T35–T37) |
| TTS | Piper irina-medium | Piper irina-medium |
| LLM | picoclaw CLI / llama.cpp | Ollama (T28, T30, T81–T83) |
| Storage | SQLite + FTS5 (T22, T24) | PostgreSQL (T112–T113) |
| Hardware tests T01–T16 | Run on Pi | SKIP |
| OpenClaw tests T27–T41 | SKIP | Run locally |
| `DEVICE_VARIANT` | not set / `picoclaw` | `openclaw` |
| Run env var for local | *(auto-detected)* | `DEVICE_VARIANT=openclaw` |

**Variant-aware test decisions:**
- Always set `DEVICE_VARIANT=openclaw` for local source-inspection runs on x86_64 dev machines
- T29/T30 (OpenClaw routing) must PASS in all environments (source inspection only)
- T113 (live Postgres) SKIPs automatically when `STORE_BACKEND != postgres`

---

## 6. Decision Matrix — Changed File → Tests to Run

| Changed files / area | Layers | Specific tests |
|----------------------|--------|----------------|
| `src/features/bot_voice.py` | 0 + 1 + 7 | T07–T41, cat F |
| `src/core/bot_config.py` | 0 + 1 | T17, T29–T30, T42–T46 |
| `src/core/bot_llm.py` | 0 + 1 + 6 | T56–T57, cat H, T81–T83 |
| `src/core/bot_db.py`, `store_*.py` | 0 + 2 + 8 | T22–T23, T73, T111–T113 |
| `src/strings.json` | 0 | T13 (i18n coverage) — **always** |
| `src/prompts.json` | 0 | T115 (prompts structure) |
| `src/telegram_menu_bot.py` (any) | 1 | cat F (all telegram tests) |
| `src/telegram_menu_bot.py` (calendar) | 0 + 1 | T20–T21, T158–T161, cat F |
| `src/telegram_menu_bot.py` (notes) | 0 + 1 | T19, T51–T53, cat F |
| `src/telegram_menu_bot.py` (RBAC/security) | 0 + 10 | T70–T71, T116, cat F |
| `src/telegram_menu_bot.py` (guest/roles) | 0 + 1 | T140–T157, cat F |
| `src/bot_web.py`, `src/web/` | 3 + 4a | cat G, cat B (Playwright) |
| `src/ui/*.py`, `src/screens/*.yaml` | 3 | cat G (Screen DSL) |
| `src/features/bot_campaign.py` | 0 + 2 + 11 | T130–T137, T_CS tests |
| `src/features/bot_remote_kb.py` | 0 + 2 | T200–T232 |
| `src/core/bot_mcp_client.py` | 0 + 2 | T200–T232 (T202, T220–T224) |
| `src/features/bot_crm.py`, `store_crm.py` | 0 + 2 | T40–T49, T130–T137 |
| `src/features/bot_content.py` | 0 + 11 | T_CS_01–T_CS_20 |
| `src/features/bot_n8n.py` | 0 + 2 + 11 | T40–T43, T_CN_01–T_CN_12 |
| `src/core/bot_embeddings.py`, `bot_rag.py` | 0 + 2 | T76–T80, T200–T205 |
| `src/core/bot_security.py` | 0 + 10 | T70–T71, T116, cat F |
| `src/setup/migrate_*.py` | 8 | T111, T113, T23 |
| `src/services/*.service` | 7 | Smoke on deployed target |
| Any Python file | 0 + 1 | Quick run (40s) — **always before commit** |
| After any deploy | 7 | Smoke on deployed target — **mandatory** |
| Before backup | 9 | `test_data_consistency.py` |
| After migration | 8 + 9 | T111–T113 + data consistency |
| STT/LLM model change | 5 + 6 | `benchmark_stt.py` or `benchmark_ollama_models.py` + T81–T83 |

---

## 7. Copilot Execution Guide

### Standard workflow for "test software" / "run tests"

```
1. Quick Local Run (Layers 0+1+3) — ~40s — ALWAYS first
2. Apply Decision Matrix (§6) — add layer-specific tests per changed files
3. After deploy → Smoke on target (Layer 7) — MANDATORY
4. For KB/CRM/Campaign → Layer 2 + 11 integration tests
5. For voice/STT/TTS → Layer 4c (Pi hardware tests)
6. For Playwright → only if taris-web is running on target
```

### Fast paths

| Scenario | Layers | Time |
|----------|--------|------|
| Pre-commit safety check | 0 + 1 + 3 | ~40s |
| Voice pipeline change | 0 + T07–T41 + Pi T01–T16 | 3–7min |
| LLM routing change | 0 + cat H + T56–T57 + T81–T83 | 1–2min |
| Full pre-release (PI2) | All layers on PI2 | 15–30min |
| After VPS deploy | Layer 7 + T_CS + T200+ | 3–5min |
| After migration | 8 + 9 | 2–5min |

### What Copilot must NEVER skip

1. **Layer 0** (source inspection) before any commit
2. **Smoke test (Layer 7)** after any deploy
3. **T13** (i18n) when `strings.json` changes
4. **Layer 10** (security tests) when RBAC/access code changes
5. **Layer 9** (data consistency) before any production backup
6. **E2E on deployed target** — local tests passing is NOT sufficient

---

## 8. Lessons Learned Protocol — How Tests Grow

Every production bug MUST produce a T-numbered regression test before the fix is deployed.

### Process (MANDATORY)

1. **Root cause in one sentence** — what code property was violated?
2. **Write test FIRST** — name it, place it in the right layer, verify it FAILS on broken code
3. **Fix the bug** — test turns green
4. **Update test-suite.md** — add T-number + description + run command
5. **Update §4 of this document** — add to T-number registry if new range
6. **Append to lessons-learned.md** — one row per bug
7. **Update relevant skill SKILL.md** — if test needs a new run step

### Pattern examples from taris history

| Bug | Root cause | Test added | Layer |
|-----|-----------|------------|-------|
| Calendar TTS wrong call signature | LLM generated `(ev)` not `(chat_id, ev)` | T20 | 0 |
| Note edit missing Append/Replace | LLM omitted callbacks | T19 | 0 |
| RTF KB upload returned nothing | `striprtf` not installed in Docker | T225 | 2 |
| Files deployed before restart → old code | Deploy order wrong | Smoke Layer 7 | 7 |
| `_extract_to_text` silently passed binary | `except ImportError: pass` swallowed | T226 | 0 |
| gemma4 thinking mode leaked `<think>` | Thinking mode not stripped | T117 | 0 |
| RAG log datetime serialization error | Postgres returns datetime obj not str | T79 | 0 |
| Multi-turn context duplicated system msg | System message injected twice | T57 | 0 |

---

## 9. Source File → Test File Matrix

Given a changed file, which test files check it?

| Source file | Primary test file(s) |
|-------------|---------------------|
| `src/features/bot_voice.py` | `test_voice_regression.py` T07–T41 |
| `src/features/bot_calendar.py` | `test_voice_regression.py` T20–T21, T158–T161; `test_telegram_bot.py` |
| `src/features/bot_contacts.py` | `test_voice_regression.py` T112; `test_telegram_bot.py` |
| `src/features/bot_documents.py` | `test_voice_regression.py` T73–T75 |
| `src/features/bot_remote_kb.py` | `test_remote_kb.py` T200–T232 |
| `src/features/bot_campaign.py` | `test_campaign.py` T130–T137 |
| `src/features/bot_crm.py` | `test_n8n_crm.py` T40–T49; `test_campaign.py` |
| `src/features/bot_content.py` | `test_content_strategy.py` T_CS_01–T_CS_20 |
| `src/features/bot_n8n.py` | `test_n8n_crm.py`; `test_content_n8n.py` T_CN_01–T_CN_12 |
| `src/features/bot_dev.py` | `test_voice_regression.py` T70 (dev menu RBAC) |
| `src/core/bot_llm.py` | `llm/test_ask_openclaw.py`; `test_voice_regression.py` T56–T57, T81–T83 |
| `src/core/bot_config.py` | `test_voice_regression.py` T17, T29–T30, T42–T46 |
| `src/core/bot_db.py` | `test_voice_regression.py` T22–T23, T111–T113 |
| `src/core/bot_rag.py` | `test_voice_regression.py` T24, T59, T76–T80 |
| `src/core/bot_embeddings.py` | `test_voice_regression.py` T85, T200–T204 |
| `src/core/bot_mcp_client.py` | `test_remote_kb.py` T202, T220–T224 |
| `src/core/store_postgres.py` | `test_voice_regression.py` T112–T113 |
| `src/core/store_sqlite.py` | `test_voice_regression.py` T22–T23 |
| `src/core/bot_security.py` | `test_voice_regression.py` T70–T71, T116; `test_telegram_bot.py` |
| `src/core/bot_prompts.py` | `test_voice_regression.py` T115, T168–T172 |
| `src/telegram_menu_bot.py` | `telegram/test_telegram_bot.py` (all F-cat) |
| `src/bot_web.py` | `ui/test_ui.py` (all B-cat) |
| `src/ui/*.py`, `src/screens/*.yaml` | `screen_loader/test_screen_loader.py` (all G-cat) |
| `src/strings.json` | `test_voice_regression.py` T13 |
| `src/prompts.json` | `test_voice_regression.py` T115 |
| `src/setup/migrate_*.py` | `test_voice_regression.py` T111, T113, T23 |

---

## 10. Coverage Gaps and Roadmap

### High Priority

| Gap | Layer | Suggested test file | T-range |
|-----|-------|---------------------|---------|
| `bot_security.py` unit tests | 10 | `test_security.py` (new) | T_SEC_01+ |
| `bot_calendar.py` CRUD unit tests | 1 | `test_telegram_bot.py` | next F-cat |
| `bot_contacts.py` create/search/merge | 1 | `test_telegram_bot.py` | next F-cat |
| LLM quality evaluation (systematic) | 6 | `test_llm_eval.py` (new) | T_EVAL_01+ |
| Postgres adapter method contracts | 1 | `test_store_postgres.py` (new) | T_SEC or new |
| `bot_email.py` unit tests | 1 | `test_telegram_bot.py` | next F-cat |
| Fix T50–T65 stale docstring in `test_remote_kb.py` | — | docstring fix | — |

### Medium Priority

| Gap | Layer | Notes |
|-----|-------|-------|
| N8N webhook offline mock | 2 | Stub N8N for CI without live network |
| Prompt injection defense test | 10 | Verify `bot_security.py` sanitization |
| RAG faithfulness evaluation | 6 | Extend `autoresearch_kb/evaluate.py` |
| Performance regression CI gate | 5 | Auto-compare `benchmark_stt.py` baseline |
| PicoClaw hardware baseline re-establishment | 4c | After Pi re-image: `--set-baseline` |

### Low Priority (nice to have)

- Chaos test: Postgres unavailable → graceful SQLite fallback behavior
- Load test: 100 concurrent Telegram messages (stress test `num_threads`)
- Contract test: MCP API version compatibility between client and server
