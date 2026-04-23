# taris — Test Suite Overview

**Purpose:** This document is the single reference for Copilot (and human developers) on *which tests exist*, *where they live*, *what triggers them*, and *how to run them*.  
Use it any time a user says "test the software", "run tests", or asks whether something is covered.

---

## Quick-Reference: "I changed X — what do I run?"

| Changed file / area | Tests to run | Where |
|---|---|---|
| `src/bot_voice.py` | Voice regression T01–T21 | Pi (engineering or production) |
| `src/bot_config.py` (voice constants) | Voice regression T01–T21 | Pi |
| `src/bot_access.py` (`_escape_tts`) | Voice regression T07, T08 | Pi |
| `src/setup/setup_voice.sh` | Voice regression T01–T09 | Pi after reinstall |
| `src/strings.json` | Voice regression T13 (i18n) | Pi |
| `src/bot_handlers.py` | Voice regression T17–T21 (bug guards) | Pi |
| `src/bot_calendar.py` | Voice regression T20, T21 | Pi |
| `src/bot_web.py` / `src/templates/` / `src/static/` | Web UI tests (Playwright) | Local machine → Pi2 |
| Any audio hardware driver, ALSA, PipeWire | Hardware audio shell tests | Pi direct |
| Any deployment / infrastructure change | Smoke: service start + journal log check | Pi |
| Bug fix for known bug 0.1–0.5 | Matching regression test (T17–T21) | Pi |
| `src/core/store_sqlite.py` / `src/core/bot_db.py` | SQLite integration T22–T23 | Pi |
| RAG document upload / `bot_web.py` knowledge routes | RAG quality T24 | Pi |
| `src/core/bot_state.py` (`generate_web_link_code` / `validate_web_link_code`) | Web link code T25 | Pi |
| `src/tests/telegram/test_telegram_bot.py` or `src/tests/telegram/conftest.py` | Telegram offline regression (Category F — all 40 tests) | Local machine |
| `src/tests/screen_loader/` | Screen DSL loader regression (Category G — all 64 tests) | Local machine |
| `src/tests/llm/` | LLM provider tests (Category H — all 18 tests) | Local machine |
| **Before backup or after data migration** | Data consistency check (Category J) | Any target |

---

## 1. Test Categories Overview

| Category | Technology | Runs on | Automated? |
|---|---|---|---|
| **A — Voice regression** | Python (`test_voice_regression.py`) | Pi or local (source inspection) | Yes |
| **B — Web UI (E2E)** | Playwright + pytest (`test_ui.py`) | Local → Pi2 | Yes |
| **C — Hardware audio** | Bash shell scripts (`test_*.sh`, `check_*.sh`) | Pi (direct) | Manual/CI |
| **D — Mic capture** | Python (`test_mic.py`) | Pi (direct) | Manual |
| **E — Smoke / deployment** | `plink` + `journalctl` | Pi (remote) | Manual |
| **F — Offline Telegram regression** | pytest (`test_telegram_bot.py`) | Local machine | Yes |
| **G — Screen DSL loader** | pytest (`src/tests/screen_loader/`) | Local machine | Yes |
| **H — LLM provider tests** | pytest (`src/tests/llm/`) | Local machine | Yes |
| **I — External internet UI tests** | Playwright (`test_external_ui.py`) | Any machine → internet | Yes |
| **J — Data consistency check** | Python (`test_data_consistency.py`) | Any target (local or remote) | Yes — run before backup / after migration |

---

## 2. Category A — Voice Regression Tests

**File:** `src/tests/test_voice_regression.py`  
**Deploy path on Pi:** `~/.taris/tests/test_voice_regression.py`  
**Fixture audio:** `src/tests/voice/*.ogg` → `~/.taris/tests/voice/`  
**Ground truth:** `src/tests/voice/ground_truth.json` → `~/.taris/tests/voice/ground_truth.json`  
**Baseline file (Pi only):** `~/.taris/tests/voice/results/baseline.json`

### 2.1 Run commands

```bat
rem Standard run — all tests
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py"

rem Verbose — show per-test detail
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --verbose"

rem Run only tests matching a name fragment (e.g. only TTS tests)
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --test tts"

rem Save current run as new regression baseline
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --set-baseline"

rem Compare two saved result files
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --compare 2026-03-07_17-00-00.json 2026-03-10_10-00-00.json"
```

### 2.2 Deploy test assets (run once, or when fixtures change)

```bat
pscp -pw "%HOSTPWD%" src\tests\test_voice_regression.py stas@OpenClawPI:/home/stas/.taris/tests/
pscp -pw "%HOSTPWD%" src\tests\voice\ground_truth.json  stas@OpenClawPI:/home/stas/.taris/tests/voice/
pscp -pw "%HOSTPWD%" src\tests\voice\*.ogg              stas@OpenClawPI:/home/stas/.taris/tests/voice/
```

### 2.3 Exit codes

| Code | Meaning |
|---|---|
| 0 | All tests PASS or SKIP (and no significant regression vs baseline) |
| 1 | One or more tests FAIL or regression exceeded threshold |
| 2 | Test runner error (missing fixtures, import errors) |

> **Note:** A run where all tests are SKIP (e.g. no optional models installed) returns exit code 0 — no failures occurred. SKIP is acceptable for optional components and should not block a CI/CD pipeline.

### 2.4 Test status meanings

| Status | Meaning |
|---|---|
| PASS | Test passed within thresholds |
| FAIL | Test failed — must be fixed before committing |
| WARN | Regression > 30% slower than baseline — investigate; update baseline if intentional |
| SKIP | Optional component absent (Whisper, German models) — acceptable |

### 2.5 Individual test descriptions

| ID | Test name | What it checks | Trigger |
|---|---|---|---|
| T01 | `model_files_present` | Vosk model, Piper binary, `.onnx`, `.onnx.json`, ffmpeg; optional: Whisper, low-quality model | After `setup_voice.sh`, after `bot_config.py` path changes |
| T02 | `piper_json_present` | `.onnx.json` config exists alongside every `.onnx` in use (required for Piper to work) | After adding/swapping Piper models |
| T03 | `tmpfs_model_complete` | Both `.onnx` + `.onnx.json` present in `/dev/shm/piper/` when `tmpfs_model` voice opt is on | After enabling `tmpfs_model` opt |
| T04 | `ogg_decode` | ffmpeg decodes OGG fixture files to S16LE PCM; measures decode latency | After changing ffmpeg pipeline, after audio filter changes |
| T05 | `vad_filter` | WebRTC VAD (`webrtcvad`) strips non-speech frames; measures speech fraction + latency | After changing VAD settings in `bot_voice.py` |
| T06 | `vosk_stt` | Vosk transcribes fixture audio; WER ≤ 30% vs ground truth; measures STT latency | After changing Vosk model, STT pipeline, audio preprocessing |
| T07 | `confidence_strip` | `[?word] → word` regex (7 cases); must match `bot_voice.py` exactly | After changing `_CONF_MARKER_RE` or confidence logic |
| T08 | `tts_escape` | `_escape_tts()` removes emoji + Markdown before Piper (6 cases); must match `bot_access.py` | After changing `_escape_tts()` in `bot_access.py` |
| T09 | `tts_synthesis` | Piper synthesizes Russian test text to raw PCM, then ffmpeg encodes OGG; measures latency | After changing TTS pipeline, Piper model, or output format |
| T10 | `whisper_stt` | whisper.cpp transcribes fixture audio; WER ≤ 40% vs ground truth (SKIP if binary absent) | After upgrading Whisper model or binary |
| T11 | `whisper_hallucination_guard` | Sparse-output guard rejects known hallucinated phrases; Vosk fallback produces real words | After changing hallucination guard logic in `bot_voice.py` |
| T12 | `regression_check` | All timing metrics within 30% of saved baseline | After any voice pipeline change; always run with `--set-baseline` after hardware changes |
| T13 | `i18n_string_coverage` | `strings.json`: all 3 languages (ru/en/de) have identical key sets, no empty values, checks current key count | After adding/removing/renaming any string key |
| T14 | `lang_routing` | `_piper_model_path(lang)` and Vosk model routing return correct paths for ru/en/de; file existence checked | After adding language support or changing model-routing logic |
| T15 | `de_tts_synthesis` | German Piper TTS (`de_DE-thorsten-medium.onnx`) synthesizes to raw PCM (SKIP if model absent) | After adding German TTS model |
| T16 | `de_vosk_model` | German Vosk model loads and decodes silence without error (SKIP if absent) | After adding German STT model |
| T17 | `bot_name_injection` | `BOT_NAME` defined in `bot_config`; `{bot_name}` placeholders in `strings.json`; `format()` works (Bug 0.2) | After centralizing bot name references |
| T18 | `profile_resilience` | `_handle_profile()` has `try/except` around deferred `bot_mail_creds` import (Bug 0.1) | After fixing profile crash bug |
| T19 | `note_edit_append_replace` | Append/Replace functions, callbacks, and i18n keys all present (Bug 0.3) | After implementing note Append/Replace edit flow |
| T20 | `calendar_tts_call_signature` | `_cal_tts_text(chat_id, ev)` 2-arg signature; `ev_dict` has datetime object (Bug 0.4) | After fixing calendar TTS voice deletion bug |
| T21 | `calendar_console_classifier` | Console uses JSON intent classifier with `add` default, not general LLM (Bug 0.5) | After fixing calendar console "add" routing |
| T22 | `db_voice_opts_roundtrip` | SQLite store: write + read voice opts round-trip via `store_sqlite.py` | After changing `store_sqlite.py` or voice opts persistence |
| T23 | `db_migration_idempotent` | `migrate_to_db.py` run twice on same DB — row count stable, no duplicates | After changing migration script or DB schema |
| T24 | `rag_lr_products_fts` | FTS5 query for LR product keywords (алоэ, Mind Master, витамин, цинк, LR LIFETAKT) returns ≥2 expected keywords; SKIP if `taris.db`/`doc_chunks` absent | After uploading a knowledge document; after changing FTS5 index or `store_sqlite.search_fts()` |
| T24 | `rag_lr_products_llm` | Full RAG pipeline: chunks → LLM answer → LLM-as-judge verifies topical similarity (set `LLM_JUDGE=1`); SKIP otherwise | When `LLM_JUDGE=1` is set; after changing RAG prompt logic |
| T25 | `web_link_code:generate` | Generated code is 6 uppercase alphanumeric chars | After changing `generate_web_link_code()` |
| T25 | `web_link_code:validate` | `validate_web_link_code()` returns correct chat_id | After changing validate logic |
| T25 | `web_link_code:single_use` | Second validate of same code returns None (consumed) | After any single-use logic change |
| T25 | `web_link_code:invalid` | Unknown code returns None | — |
| T25 | `web_link_code:expired` | Code with past expiry returns None | After changing TTL or expiry check |
| T25 | `web_link_code:revoke_old` | generate() twice same chat_id: first code invalidated | After changing revocation logic |
| T25 | `web_link_code:cross_process` | Code present in file immediately after generate() | After changing persistence logic |
| T26 | `system_chat_clean_output` | `_handle_system_message` returns clean text (no raw LLM leak) | After changing system chat output handling |
| T27 | `faster_whisper_stt` | faster-whisper model loads and runs silent inference (SKIP if not installed) | After adding/upgrading faster-whisper |
| T28 | `openclaw_llm_connectivity` | LLM provider connectivity check for OpenClaw variant (SKIP if ollama not running) | After changing LLM config on OpenClaw |
| T29 | `openclaw_stt_routing` | `STT_PROVIDER` defaults correctly for openclaw (`faster_whisper`) vs taris (`vosk`) | After changing `DEVICE_VARIANT` / `STT_PROVIDER` defaults |
| T30 | `openclaw_ollama_provider` | `_ask_ollama` in `_DISPATCH` + constants present in `bot_llm.py` | After adding/removing LLM providers |
| T31 | `web_stt_provider_routing` | Web UI voice endpoints use `STT_PROVIDER` routing, not hardcoded Vosk | After changing web voice endpoint in `bot_web.py` |
| T32 | `pipeline_logger` | `PipelineLogger` class logs all timing stages; total time calculated | After changing timing/logging in voice pipeline |
| T33 | `dual_stt_providers` | Dual STT dispatch: primary provider called first; fallback activated on failure | After changing `_dual_stt_dispatch()` or `STT_FALLBACK_PROVIDER` |
| T34 | `voice_debug_mode` | `VOICE_DEBUG=1` env switches to debug logging; LLM named fallback reads `LLM_FALLBACK_PROVIDER` | After changing debug mode or fallback logic |
| T35 | `stt_language_routing_fw` | faster-whisper language routing for ru/en/de; hallucination guard per language | After changing language-aware STT in `bot_voice.py` |
| T36 | `stt_fallback_chain` | Primary STT fails → Vosk fallback activated; chain respects `STT_FALLBACK_PROVIDER` | After changing fallback chain in `bot_voice.py` |
| T37 | `openai_whisper_stt` | OpenAI Whisper API provider (`_stt_openai_whisper_web`) present and callable | After adding/changing remote STT provider |
| T38 | `tts_multilang` | Piper TTS works for ru/de; EN falls back to Russian model with WARN | After adding language models or changing `_piper_model_path()` |
| T39 | `voice_llm_routing` | Voice pipeline uses `ask_llm()` (not `TARIS_BIN` subprocess) for LLM calls | After changing how voice pipeline calls LLM |
| T40 | `voice_system_mode_routing_guard` | Source: `bot_voice.py` routes `mode=system` to `_handle_system_message`; admin check preserved | After changing voice routing or system mode handling |
| T41 | `voice_lang_stt_lang_priority` | `_voice_lang()` respects `STT_LANG` env override over Telegram UI language | After changing language detection in `_voice_lang()` |
| T42 | `set_lang_default_not_hardcoded_en` | `_set_lang()` uses `_DEFAULT_LANG` (not hardcoded `"en"`) as fallback for non-ru/non-de users | After changing language defaulting in `_set_lang()` |
| T43 | `voice_system_admin_guard` | Voice handler guards system-chat routing with `_is_admin()` at routing level | After changing voice→system-chat routing |
| T44 | `openclaw_gateway_telegram_disabled` | `~/.openclaw/openclaw.json` Telegram channel must be `enabled: false` to prevent 409 conflict with taris-telegram (same token → language mixing) | After any deploy or openclaw-gateway config change |
| T45 | `taris_bin_configured` | `TARIS_BIN` must point to an existing executable (picoclaw or taris). SKIP if `LLM_PROVIDER != "taris"`. Prevents silent LLM failures after STT. Also checks `~/.picoclaw/config.json` is present when binary is picoclaw. | After changing `TARIS_BIN` in bot.env or deploying to a new Pi device |
| T46 | `vosk_fallback_openclaw_default` | `_VOICE_OPTS_DEFAULTS['vosk_fallback']` must be `False` when `DEVICE_VARIANT=openclaw` (Vosk not installed), `True` on picoclaw. Prevents "Ошибка Vosk" crash on OpenClaw when faster-whisper returns empty. | After changing `_VOICE_OPTS_DEFAULTS` or adding a new DEVICE_VARIANT |
| T47 | `faster_whisper_vad_retry` | Source-inspects `_stt_faster_whisper()` for dual-pass transcription: first pass with VAD filter, retry with `vad_filter=False` when empty. Catches silent drop of short voice messages ("да", "нет"). | After any change to `_stt_faster_whisper()` |
| T48 | `system_chat_admin_menu_only` | `mode_system` absent from `main_menu.yaml` and `_menu_keyboard()`; present in `admin_menu.yaml`. Prevents System Chat leaking into the main menu. | After editing any menu YAML or `_menu_keyboard()` |
| T49 | `stt_fast_speech_accuracy` | FW small/medium model must correctly transcribe Russian at fast speaking speeds. Root cause: `base` model (74M params) mangled phonemes in clips <1.5s — "Сколько у тебя памяти" → "Куча панча". Generates Piper TTS audio at 4 speeds (0.65x/1.0x/1.5x/1.85x) via ffmpeg atempo, runs STT on each, asserts WER ≤ 35%. Also guards `FASTER_WHISPER_MODEL != "base"`. SKIP if Piper or faster-whisper not installed. | After changing `FASTER_WHISPER_MODEL`, upgrading model, or any STT accuracy fix |
| T50 | `voice_chat_config_disclosure` | `_bot_config_block()` injects [BOT CONFIG] (LLM/STT/version) into every normal+voice chat LLM prompt. Security preamble rule 5 allows model/version self-disclosure. Fixes: bot refused "which model are you using?" with "I cannot provide infrastructure details". | After editing `bot_access.py` prompt builders or `prompts.json` security preamble |
| T51 | `note_delete_confirm` | `note_del_confirm:` callback present in `bot_handlers.py` and wired in `telegram_menu_bot.py`. Guards that note deletion shows a confirmation dialog rather than deleting immediately. | After editing `_handle_note_delete()` or `bot_handlers.py` delete callbacks |
| T52 | `note_rename_flow` | `note_rename_title` mode present in message handler; `_start_note_rename()` handler exists. Guards the multi-step rename flow. | After editing note rename handlers in `bot_handlers.py` or `telegram_menu_bot.py` |
| T53 | `note_zip_download` | `_handle_note_download_zip`, `zipfile.ZipFile`, and `io.BytesIO` present in `bot_handlers.py`. Verifies in-memory ZIP generation for bulk note download. | After editing note download handlers |
| T54 | `rag_context_injection` | `_docs_rag_context()` is called in both `_with_lang()` and `_with_lang_voice()` in `bot_access.py`. Guards FTS5 RAG context being injected into LLM prompts. | After editing prompt builders in `bot_access.py` |
| T55 | `no_hardcoded_strings` | Key user-visible strings use `_t()` not hardcoded literals: `cal_event_saved_prefix` in `bot_calendar.py`, `audio_interrupted` and `voice_note_msg` in `bot_voice.py`. New i18n keys present in ru/en/de. | After editing bot_calendar.py, bot_voice.py, or strings.json |
| T73 | `doc_store_api_complete` | Both `store_sqlite.py` and `store_postgres.py` have all 5 required document methods (`save_document_meta`, `list_documents`, `delete_document`, `update_document_field`, `get_document_by_hash`) plus 3 RAG log methods (`log_rag_activity`, `list_rag_log`, `rag_stats`). Also does a live import check against the running store. Root-cause test for the PDF upload bug (Postgres was missing these methods). | After editing either store backend; after adding a new document method |
| T74 | `doc_upload_pipeline` | `bot_documents.py` has the complete upload pipeline: `_handle_doc_upload` entry point → `get_document_by_hash` dedup check → `_process_doc_file` worker → `save_document_meta` → `update_document_field` for doc_hash; `_pending_doc_replace` state dict; `_handle_doc_replace` and `_handle_doc_keep_both` confirm handlers. | After editing `bot_documents.py` upload or dedup flow |
| T76 | `rag_full_pipeline` | Full RAG pipeline: `RAG_ENABLED`/`RAG_TOP_K`/`RAG_CHUNK_SIZE`/`RAG_TIMEOUT` constants; `rag_settings` module has all 5 keys; `bot_rag.py` has `retrieve_context`, `classify_query`, `detect_rag_capability`, `reciprocal_rank_fusion`, FTS5+vector search; `_docs_rag_context()` returns `[KNOWLEDGE FROM USER DOCUMENTS]` format; `classify_query()` live routing (simple→skip, factual/contextual→RAG); `retrieve_context()` returns `"skipped"` strategy when user has no documents. | After editing `bot_rag.py`, `bot_access.py` RAG context builder, `rag_settings.py`, or `bot_config.py` RAG constants |
| T77 | `memory_context_assembly` | Multi-tier memory: `conversation_summaries` schema with `tier='mid'/'long'`; `get_memory_context()`, `_summarize_session_async()`, `add_to_history()` with threshold trigger, `get_conv_history_max()`; `memory_enabled` per-user pref wired with toggle + getter; i18n labels `profile_memory_enabled_label`/`profile_memory_disabled_label`; live `get_memory_context(999999)` returns `""` without crash. | After editing `bot_state.py`, `bot_db.py` `conversation_summaries` table, `bot_handlers.py` memory toggle, or `strings.json` memory labels |
| T78 | `rag_memory_combined_context` | Full context ordering contract: `_build_system_message()` (preamble+bot_config+memory_note) in `bot_access.py`; `get_memory_context()` appended in `bot_handlers.py`; `_user_turn_content()` = RAG + user text (no preamble); context assembled as `[system(preamble+LTM/MTM)] + [history(STM)] + [user(RAG+text)]`; `ask_llm_with_history()` used for multi-turn; live call validates structure and LLM response. | After editing any part of the multi-turn context assembly: `_build_system_message`, `_user_turn_content`, history assembly in `bot_handlers.py`, or `ask_llm_with_history` in `bot_llm.py` |
| T81 | `qwen35_ollama_available` | At least one `qwen3.5:*` model is pulled in Ollama on OpenClaw target (SKIP if `DEVICE_VARIANT != openclaw`). WARN if none found with pull hint. | After pulling or removing Qwen3.5 models on SintAItion/OpenClaw |
| T82 | `ollama_latency_regression` | Ollama `/api/generate` round-trip ≤ 30s, tps > 2 with `think=false` for qwen3+ models (SKIP if `DEVICE_VARIANT != openclaw` or Ollama unreachable). | After upgrading Ollama, changing `OLLAMA_MODEL`, or changing GPU/VRAM config |
| T83 | `ollama_quality_ru_calendar` | `OLLAMA_MODEL` extracts `{"title", "dt"}` JSON from a Russian calendar sentence with `think=false`; validates title non-empty + datetime format (SKIP if `DEVICE_VARIANT != openclaw` or Ollama unreachable). Catches thinking-model empty-response regression. | After changing `OLLAMA_MODEL`, Ollama version, or calendar intent prompt |
| T84 | `upload_stats_metadata` | Phase C: `_chunk_text()` filters chunks shorter than `_MIN_CHUNK_CHARS`; `_store_text_chunks()` returns `(n_chunks, n_embedded)`; `_process_doc_file()` stores `quality_pct`, `n_embedded`, `n_skipped` in metadata; `_handle_doc_detail()` shows embed count and quality; `docs_doc_embeds`/`docs_doc_quality` strings present in all 3 languages. | After editing `bot_documents.py` chunking, embedding, or doc detail view |
| T85 | `embeddings_import_fix` | `bot_embeddings.py` uses `from core.bot_config import` (not `from src.core.bot_config`) — production deploy fix. `EmbeddingService` importable. | After editing `bot_embeddings.py` or moving it between packages |
| T86 | `mcp_phase_d_structure` | Phase D: `MCP_SERVER_ENABLED`/`MCP_REMOTE_URL`/`MCP_TIMEOUT`/`MCP_REMOTE_TOP_K` in `bot_config.py`; `/mcp/search` endpoint registered in `bot_web.py` with Bearer-token auth + `retrieve_context()` call; `bot_mcp_client.py` has `query_remote()`, `circuit_status()`, circuit-breaker constants, stdlib HTTP client; `bot_rag.py` merges remote MCP chunks into RRF with `+mcp` strategy tag. | After editing any MCP Phase D code: `bot_mcp_client.py`, `/mcp/search` endpoint, MCP config constants |
| T87 | `embedding_pipeline_fix` | `_store_text_chunks()` passes `chunks[idx]` as chunk_text to `upsert_embedding()` (was missing — vectors silently never stored); `search_fts()` and `search_similar()` SELECT includes `chunk_idx` (was missing — RRF fusion broken). | After editing `bot_documents.py` embed loop, `store_sqlite.py` search methods |
| T88 | `shared_docs_search` | `search_fts()` and `search_similar()` include `is_shared=1` docs from all users; `_get_shared_doc_ids()` helper present; `list_documents()` returns own + shared docs. | After editing `store_sqlite.py` search or document listing methods |
| T89 | `rag_trace_fields` | `retrieve_context()` returns 4-tuple `(chunks, text, strategy, trace)`; trace has `n_fts5`/`n_vector`/`n_mcp`/`latency_ms`; `bot_access.py` unpacks 4-tuple + passes trace to `log_rag_activity()`; `rag_log` auto-migrated with `n_fts5`/`n_vector`/`n_mcp` columns. | After editing `bot_rag.py` retrieve_context(), `bot_access.py` RAG context path, or `store_sqlite.py` rag_log |
| T90 | `system_docs_structure` | `src/setup/load_system_docs.py` exists with `_load_docs()`, `_ingest()`, `_chunk()`, system tags, `is_shared=1`; `src/setup/migrate_reembed.py` exists with `_migrate()`, LEFT JOIN logic, `--dry-run`; `telegram_menu_bot.py` starts `_ensure_system_docs` thread at startup. | After editing system docs loader, migration script, or startup logic |
| T98 | `render_telegram_empty_block` | `render_telegram.py` replaces empty/whitespace `MarkdownBlock.text` with `"\u200b"` instead of sending empty string; `note_view.yaml` uses `{note_content}` variable; `bot_handlers.py` wraps text in `_escape_md()`. | After editing `render_telegram.py` MarkdownBlock handler, or `note_view.yaml` template |
| T99 | `admin_info_markdown_safe` | `_send_admin_info()` in `bot_voice.py` wraps STT/LLM/TTS labels in backticks — prevents Markdown entity injection from model names with `_` (e.g. `ru_RU-dmitri-medium.onnx`). | After editing `_send_admin_info()` or `_tts_label()` / `_llm_label()` |
| T100 | `doc_detail_datetime_safe` | `_handle_doc_detail()` in `bot_documents.py` converts `created_at` safely — Postgres returns `datetime.datetime`, SQLite returns ISO string. Raw `[:16]` slice on datetime raises `TypeError`. | After editing `_handle_doc_detail()` or `store_postgres.py` `list_documents()` |
| T101 | `note_open_empty_file` | `_handle_note_open()` in `bot_handlers.py` uses `note_empty_body` placeholder when note file is 0 bytes — prevents `"\n"` widget text that Telegram rejects as empty. | After editing `_handle_note_open()` or empty-note content handling |
| T102 | `store_postgres_notes_uuid_path` | `store_postgres.py` note methods use `_notes_storage_dir(chat_id)` for UUID path resolution — prevents notes being written/read from `str(chat_id)` dir when account is linked to a web UUID via `accounts.json`. | After editing `store_postgres.py` note methods or account-linking logic |
| T103 | `web_accounts_store_methods` | Both store backends have `get_web_account`, `set_web_account`, `generate_link_code`, `consume_link_code` methods. | After editing web auth / account linking in either store backend |
| T104 | `system_settings_json_file` | `db_get_system_setting` / `db_set_system_setting` use `SYSTEM_SETTINGS_PATH` (JSON file), not `get_db()` SQLite. | After editing system settings logic |
| T105 | `mail_creds_store_primary` | `bot_mail_creds._load_creds` tries `store.get_mail_creds()` first, then falls back to file — not get_db(). | After editing mail credentials loading |
| T106 | `postgres_no_sqlite_fallbacks` | On OpenClaw/Postgres, `bot_access.py` notes/contacts context functions and `telegram_menu_bot.py` `init_db` guard have no `get_db()` SQLite fallback. | After editing `bot_access.py` or `telegram_menu_bot.py` init logic |
| T107 | `postgres_dict_row_access` | `store_postgres.py` uses `dict_row` factory — all `row[col]` access uses named keys (`row["id"]`) not positional (`row[0]`). | After editing `store_postgres.py` or adding new queries |
| T108 | `llm_history_named_fallback` | `ask_llm_with_history` uses `LLM_FALLBACK_PROVIDER` named fallback (not legacy llama.cpp). | After editing `bot_llm.py` or LLM fallback chain |
| T109 | `llm_system_chat_fallback` | System chat handles Ollama timeout with guard + global default fallback provider. | After editing system chat LLM integration |
| T110 | `system_chat_host_context` | `_handle_system_message` injects `_HOST_CTX` (hostname, OS, CPU, temp-tools, pkg-mgr) into LLM system prompt. | After editing `bot_handlers.py` system prompt builders |
| T111 | `migrate_postgres_structure` | `migrate_sqlite_to_postgres.py` covers all 10 required tables; notes has no `WHERE content != ''` filter (critical bug — omits file-backed notes); contacts uses `save_contact()`; documents uses `save_document_meta()`. | After editing the migration script or adding new tables |
| T112 | `contacts_store_parity` | Both `store_sqlite.py` and `store_postgres.py` implement all 5 contacts methods: `save_contact`, `get_contact`, `list_contacts`, `delete_contact`, `search_contacts`. Live import check included. | After editing either store backend's contacts methods |
| T113 | `postgres_live_data` | When `STORE_BACKEND=postgres`, all 5 core tables (users, calendar_events, notes_index, chat_history, conversation_summaries) have ≥1 row. SKIP if not on Postgres or `STORE_PG_DSN` not set. | After SQLite → Postgres migration to verify data was populated |
| T114 | `admin_page_datetime_safe` | `bot_web.py` admin page uses `str(a.get('created', ''))[:10]` to safely handle `datetime.datetime` objects returned by Postgres backend. | After editing `bot_web.py` admin page handler |
| T115 | `bot_capabilities_tag_fix` | `prompts.json` rule 5 must NOT contain the phrase that caused LLM to output `[BOT CAPABILITIES]` literally; must warn against reproducing block markers. | After editing `prompts.json` security preamble |
| T158 | `inv_confirm_dual_save` | `_handle_inv_confirm()` in `bot_calendar.py` calls `_cal_add_event` for BOTH `admin_chat_id` and `guest_id`; guest save wrapped in try/except. Regression guard for v2026.4.59 fix. | After editing `_handle_inv_confirm()` in `bot_calendar.py` |
| T159 | `guest_my_data_meetings_count` | `bot_handlers.py` guest My Data branch calls `_cal_load(chat_id)` and passes `meetings_count=str(len(meetings))` — ensures confirmed meetings appear in guest profile. | After editing guest My Data handler in `bot_handlers.py` |
| T160 | `cal_inv_flow_functions` | `bot_calendar.py` has all required invitation functions: `_finish_guest_meeting_slot`, `_handle_inv_confirm`, `_handle_inv_decline`, `_pending_invitations`, `_schedule_reminder(guest_id`. | After editing `bot_calendar.py` invitation flow |
| T161 | `inv_strings_completeness` | All 9 invitation + guest-profile strings in all 3 languages (ru/en/de); `profile_my_data_guest_msg` contains `{meetings_count}` placeholder. | After editing `strings.json` invitation or guest profile keys |
| T116 | `admin_only_rag_access` | Full retrieval stack has `is_admin` param: `load_system_docs._ingest` uses `is_shared=2` for admin guide; `store_sqlite`/`store_postgres` `search_fts`/`search_similar` accept `is_admin`; `bot_rag.retrieve_context` propagates it; `bot_access._docs_rag_context` calls `_is_admin(chat_id)`. | After editing RAG retrieval stack or doc sharing logic |
| T117 | `gemma4_thinking_mode_fix` | `benchmark_ollama_models.py` `_run_prompt()` must list `gemma4` in `is_thinking_model` tags; Gemma4:e2b/e4b in `CANDIDATE_MODELS`; `--host` flag present. | After editing `benchmark_ollama_models.py` or adding LLM models |
| T118 | `gemma4_ollama_config` | `bot_llm.py` passes `think:OLLAMA_THINK` to Ollama API; `bot_config.py` defaults `OLLAMA_THINK=False`. Ensures Gemma4 thinking suppressed in production. | After editing `bot_llm.py` or `bot_config.py` LLM constants |
| T119 | `gemma4_live_availability` | Live Ollama API check: gemma4:e2b/e4b pulled and callable. SKIP if Ollama not running. | After pulling Gemma4 models; before switching `OLLAMA_MODEL` |
| T120 | `gemma4_benchmark_report` | Research doc, Linux eval script, and Windows PowerShell eval helper all present. | After adding Gemma4 evaluation infrastructure |
| T121 | `ollama_model_picker` | Admin Ollama model picker: `get_ollama_model`/`set_ollama_model` exist; admin UI handler + callback dispatch present. | After editing `bot_admin.py` LLM model picker |
| T122 | `rbac_allowlist_enforcement` | `ADMIN_ALLOWED_CMDS`, `DEVELOPER_ALLOWED_CMDS`, `_classify_cmd_class`, configurable extra blocklist, admin security policy UI present. | After editing RBAC enforcement in `bot_security.py` or `bot_admin.py` |

### 2.5c Guest User + Prompt Templates — `test_voice_regression.py --test t_guest_user_feature`

| ID | Test | What it checks | When to run |
|---|---|---|---|
| T140 | `guest_config_constants` | `AUTO_GUEST_ENABLED`, `GUEST_MSG_DAILY_LIMIT`, `GUEST_MSG_HOURLY_LIMIT`, `GUEST_MAX_TOKENS`, `SHARED_DOCS_OWNER` in `bot_config.py`. | After editing guest constants |
| T141 | `guest_state_fields` | `bot_state.py` has `_dynamic_guests` and `_guest_message_counts`. | After editing `bot_state.py` guest persistence |
| T142 | `guest_access_functions` | `bot_access.py` has `_is_guest()`, `_get_prompt_role_key()`, `_check_guest_rate_limit()`. | After editing `bot_access.py` access functions |
| T143 | `guest_system_message` | `_build_system_message()` uses `role_system_prompts` from `prompts.json`. | After editing system message builder |
| T144 | `guest_rate_limit_logic` | `_check_guest_rate_limit` uses hourly/daily count keys. | After editing rate limit logic |
| T145 | `guest_rate_limit_enforced` | Text handler in `telegram_menu_bot.py` calls `_check_guest_rate_limit` before LLM routing. | After editing message routing |
| T146 | `guest_auto_registration` | `/start` handler has `AUTO_GUEST_ENABLED` branch to register guests. | After editing `/start` handler |
| T147 | `guest_prompts_json` | `prompts.json` has `role_system_prompts`, `role_capabilities`, `role_styles` with `guest` key. | After editing `prompts.json` role prompts |
| T148 | `guest_strings` | `strings.json` has `guest_welcome` in all 3 languages. | After editing `strings.json` guest keys |
| T149 | `guest_env_example` | `.env.example` documents `AUTO_GUEST_ENABLED` and `SHARED_DOCS_OWNER`. | After adding guest constants to `.env.example` |

### 2.5d CRM + N8N + Advanced User — `test_voice_regression.py --test t_crm_n8n_advanced_user`

| ID | Test | What it checks | When to run |
|---|---|---|---|
| T150 | `n8n_adapter_source` | `bot_n8n.py` has `test_connection`, `trigger_workflow`, `list_workflows` + `N8N_URL`/`N8N_API_KEY` constants. | After editing `bot_n8n.py` |
| T151 | `crm_store_source` | `store_crm.py` has `create_contact`, `get_stats`, `seed_demo_contacts`, `list_contacts`, `search_contacts`, `count_contacts`. | After editing `store_crm.py` |
| T152 | `crm_intent_classifier` | `bot_crm.py` has `classify_intent()` + `CRM_INTENTS` set with `add_contact`/`search`/`campaign`. | After editing `bot_crm.py` intent classifier |
| T153 | `advanced_user_role_management` | `bot_admin.py` has 4-role system: `_is_advanced`, `_handle_admin_user_set_role`, `valid_roles`, `_advanced_users`. | After editing role management in `bot_admin.py` |
| T154 | `n8n_workflow_files` | `src/n8n/workflows/` contains ≥2 JSON workflow files. | After adding/removing N8N workflow definitions |
| T155 | `crm_web_api` | `bot_web.py` has `/api/crm/` route + `api_crm_contacts` + `CRM_ENABLED`. | After editing CRM API endpoints in `bot_web.py` |

### 2.5e Guest Approval + Role Management — `test_voice_regression.py --test t_guest_approval_role`

| ID | Test | What it checks | When to run |
|---|---|---|---|
| T156a | `guest_approval_fn` | `_do_approve_as_guest()` defined in `bot_admin.py`. | After editing admin registration approval |
| T156b | `guest_approval_button` | `reg_guest:` callback present in registration keyboard buttons. | After editing `_handle_admin_pending_users()` or `_notify_admins_new_registration()` |
| T156c | `guest_role_icon` | `'guest'` entry present in `_ROLE_ICONS` dict. | After editing `_ROLE_ICONS` |
| T156d | `guest_role_detection` | `_get_user_role()` checks `_dynamic_guests` and returns `"guest"`. | After editing `_get_user_role()` |
| T156e | `guest_role_set` | `_handle_admin_user_set_role()` handles `role == "guest"` case. | After editing `_handle_admin_user_set_role()` |
| T156f | `guest_approval_dispatch` | `telegram_menu_bot.py` imports `_do_approve_as_guest` and dispatches `reg_guest:` callback. | After editing callback routing |

### 2.5b Campaign Tests — `src/tests/test_campaign.py`

Run with: `python src/tests/test_campaign.py` (offline) or deploy to target and run with `PYTHONPATH=~/.taris python3 ~/.taris/tests/test_campaign.py`.

| ID | Test | What it checks | When to run |
|---|---|---|---|
| T130 | `campaign_i18n_keys` | All 19 campaign_* strings present and non-empty in ru/en/de. Catches missing translations for new campaign messages. | After editing `strings.json` campaign keys |
| T131 | `campaign_module_structure` | `bot_campaign.py` exports all required public functions; uses `call_webhook` not `requests.post`; has `_STEP_KEY_MAP`, `_user_friendly_error`, `_run_selection`, `_run_send`; checks `"error" in result`; calls `_campaigns.pop`. | After editing `bot_campaign.py` structure or imports |
| T132a | `campaign_state_start` | `start_campaign()` sets step=`topic_input` and sends topic prompt. | After editing `start_campaign()` |
| T132b | `campaign_state_topic` | `on_topic()` stores topic in state and advances to `filter_input`. | After editing `on_topic()` |
| T132c | `campaign_handle_message_routing` | `handle_message()` routes to `on_topic`/`on_filters`/`on_template_edit` by step. | After editing `handle_message()` routing |
| T132d | `campaign_cancel` | `cancel()` clears state, `is_active()` returns False. Root cause: leftover state caused stuck user sessions. | After editing `cancel()` or state dict management |
| T132e | `campaign_edit_flow` | `start_template_edit()` + `on_template_edit()` updates template and returns to preview. | After editing template edit flow |
| T132f | `campaign_filters_skip_variants` | `on_filters()` treats `-`, `no`, `skip`, empty, whitespace as "no filters" (pass-all). | After editing `on_filters()` skip logic |
| T133a | `webhook_no_url` | `call_webhook("")` returns `{"error": "Webhook URL not configured"}`. | After editing `call_webhook()` |
| T133b | `webhook_empty_body` | Empty 200 response returns `{"result": "", "status_code": 200}` — NOT an `"error"` key. Root cause of "Expecting value: line 1 column 1" production bug. | After editing `call_webhook()` empty-body handling |
| T133c | `webhook_http_error` | HTTP 4xx/5xx returns `{"error": ..., "status_code": N}`. | After editing `call_webhook()` error handling |
| T133d | `webhook_timeout` | Timeout returns `{"error": "Webhook timeout after Ns"}`. | After editing `call_webhook()` timeout handling |
| T133e | `webhook_n8n_error_passthrough` | N8N `{"_error": true, "step": X, "detail": Y}` response is passed through as dict (no error key) — `_user_friendly_error` handles it. | After editing N8N error response parsing |
| T133f | `run_selection_no_crash` | `_run_selection()` does not crash when N8N returns empty-body 200 (no clients path). | After editing `_run_selection()` |
| T134 | `user_friendly_error_steps` | All `_STEP_KEY_MAP` step names resolve to keys in `strings.json`. Prevents KeyError on error display. | After adding steps or i18n keys |
| T135 | `ollama_model_exists` | If `LLM_PROVIDER=ollama`, configured `OLLAMA_MODEL` exists in Ollama API. Root cause of "No response from LLM" production bug. SKIP if not ollama. | After changing `OLLAMA_MODEL` in bot.env |
| T136a | `webhook_url_source` | `N8N_CAMPAIGN_SELECT_WH` and `N8N_CAMPAIGN_SEND_WH` constants exist in `bot_config.py` source. | After editing `bot_config.py` N8N constants |
| T136b | `webhook_url_valid_runtime` | At runtime, webhook URLs start with `http://` or `https://`. SKIP if not configured. | After setting webhook URLs in bot.env |
| T137a | `campaign_callback_routing` | `telegram_menu_bot.py` routes all campaign callbacks: `campaign_confirm_send`, `campaign_cancel`, `campaign_edit`. | After editing callback routing in `telegram_menu_bot.py` |
| T137b | `campaign_handle_message_in_router` | Main message handler calls `campaign.handle_message()` or `campaign.is_active()` before LLM routing. | After editing `handle_message()` in `telegram_menu_bot.py` |

### 2.6 When specific tests are mandatory

| Scenario | Required tests |
|---|---|
| Before committing **any** voice-related change | T01–T12 (full suite) |
| After fixing a known bug (0.1–0.5) | Corresponding T17–T21 test |
| After changing `strings.json` | T13 |
| After adding a new language | T13, T14, matching Txx for new language |
| After `setup_voice.sh` re-run | T01–T09 minimum |
| After hardware change (Pi re-image, new Pi unit) | T01–T12 + `--set-baseline` |
| After changing `store_sqlite.py` or `bot_db.py` | T22, T23 |
| After uploading new RAG document | T24 (`--test rag_lr`) |
| After changing `generate_web_link_code()` / `validate_web_link_code()` / `bot_state.py` web link persistence | T25 (`--test web_link_code`) |
| After changing `_stt_faster_whisper()` language routing or hallucination guard | T35 (`--test stt_language`) |
| After changing STT fallback chain in `bot_voice.py` or `STT_FALLBACK_PROVIDER` config | T36 (`--test stt_fallback`) |
| After changing `_stt_openai_whisper_web` or OpenAI Whisper API config | T37 (`--test openai_whisper_stt`) |
| After adding/removing Piper models or changing `_piper_model_path()` | T38 (`--test tts_multilang`) |
| After any change to voice pipeline LLM call (ask_llm / TARIS_BIN) | T39 (`--test voice_llm_routing`) |
| After changing voice mode routing or system chat access in voice path | T40 (`--test voice_system_mode_routing_guard`) |
| After changing `_voice_lang()` or `STT_LANG` handling | T41 (`--test voice_lang_stt_lang_priority`) |
| After changing `_set_lang()` or language-defaulting logic in `bot_access.py` | T42 (`--test set_lang_default_not_hardcoded_en`) |
| After changing voice→system-chat routing or `_is_admin` import in `bot_voice.py` | T43 (`--test voice_system_admin_guard`) |
| After any change to `store_sqlite.py` or `store_postgres.py` document methods | T73 (`--test t_doc_store_api_complete`) |
| After editing `bot_documents.py` upload, dedup, or delete/rename flow | T74, T75 (`--test t_doc_upload_pipeline --test t_doc_list_delete_flow`) |
| After editing `bot_rag.py`, `rag_settings.py`, or RAG config constants | T76 (`--test t_rag_full_pipeline`) |
| After editing `bot_state.py`, `conversation_summaries` schema, or memory toggle | T77 (`--test t_memory_context_assembly`) |
| After editing multi-turn context assembly: `_build_system_message`, `_user_turn_content`, history assembly, or `ask_llm_with_history` | T78 (`--test t_rag_memory_combined_context`) |
| After pulling/removing Qwen3.5 models, upgrading Ollama, or changing `OLLAMA_MODEL` on OpenClaw | T81–T83 (`--test t_qwen35 --test t_ollama_latency --test t_ollama_quality_ru_calendar`) |
| After editing `bot_documents.py` chunking, embedding, or doc detail view | T84 (`--test t_upload_stats_metadata`) |
| After editing `bot_embeddings.py` or changing its import paths | T85 (`--test t_embeddings_import_fix`) |
| After editing any MCP Phase D code (`bot_mcp_client.py`, `/mcp/search`, MCP constants) | T86 (`--test t_mcp_phase_d_structure`) |
| After editing `bot_documents.py` embed loop or `store_sqlite.py` search methods | T87 (`--test t_embedding_pipeline_fix`) |
| After editing `store_sqlite.py` search or document listing | T88 (`--test t_shared_docs_search`) |
| After editing `bot_rag.py` retrieve_context, `bot_access.py` RAG path, or `rag_log` schema | T89 (`--test t_rag_trace_fields`) |
| After editing system docs loader, migration script, or startup sequence | T90 (`--test t_system_docs_structure`) |
| After editing `render_telegram.py` MarkdownBlock, or any note screen YAML | T98 (`--test t_render_telegram_empty_block`) |
| After editing `_send_admin_info()`, `_tts_label()`, `_llm_label()` in `bot_voice.py` | T99 (`--test t_admin_info_markdown_safe`) |
| After editing `_handle_doc_detail()` or `store_postgres.py` `list_documents()` | T100 (`--test t_doc_detail_datetime_safe`) |
| After editing `_handle_note_open()` or empty-note handling | T101 (`--test t_note_open_empty_file`) |
| After editing `store_postgres.py` note methods or `_notes_storage_dir` / account-linking | T102 (`--test t_store_postgres_notes_uuid_path`) |
| After editing `migrate_sqlite_to_postgres.py` or adding new tables to either store | T111 (`--test t_migrate_postgres_structure`) |
| After editing contacts methods in either `store_sqlite.py` or `store_postgres.py` | T112 (`--test t_contacts_store_parity`) |
| After running SQLite → Postgres migration on any target | T113 (`--test t_postgres_live_data`) with `STORE_BACKEND=postgres STORE_PG_DSN=...` |
| After any deploy or openclaw-gateway config change | T44 (`--test t_openclaw_gateway_telegram_disabled`) |
| After changing `TARIS_BIN` in bot.env or deploying to a new Pi with picoclaw | T45 (`--test t_taris_bin_configured`) |
| After changing `_VOICE_OPTS_DEFAULTS` or adding a new DEVICE_VARIANT | T46 (`--test t_vosk_fallback_openclaw_default`) |
| After any change to `_stt_faster_whisper()` in `bot_voice.py` | T47 (`--test t_faster_whisper_vad_retry`) |
| After changing `FASTER_WHISPER_MODEL` or any STT accuracy fix | T49 (`--test t_stt_fast_speech_accuracy`) |
| After editing any menu YAML (`main_menu.yaml`, `admin_menu.yaml`) or `_menu_keyboard()` | T48 (`--test t_system_chat_admin_menu_only`) |
| After editing `bot_campaign.py` state machine or `call_webhook()` | T130–T137 (`python src/tests/test_campaign.py`) |
| After changing `OLLAMA_MODEL` in bot.env on TariStation2 | T135 (`python src/tests/test_campaign.py`) |
| After editing `bot_calendar.py` invitation flow (`_handle_inv_confirm`, `_finish_guest_meeting_slot`) | T158–T161 (`--test guest_appointment`) |
| After editing guest My Data handler in `bot_handlers.py` | T159 (`--test guest_appointment`) |
| After editing invitation strings in `strings.json` | T161 (`--test guest_appointment`) |
| After editing campaign callbacks or `handle_message()` routing in `telegram_menu_bot.py` | T137a, T137b (`python src/tests/test_campaign.py`) |
| After editing guest user constants, `_is_guest()`, `_get_prompt_role_key()`, or `prompts.json` role prompts | T140–T149 (`--test t_guest_user_feature`) |
| After editing `bot_n8n.py`, `store_crm.py`, `bot_crm.py`, `bot_admin.py` role management, or N8N workflows | T150–T155 (`--test t_crm_n8n_advanced_user`) |
| After editing guest approval flow (`bot_admin.py`, `telegram_menu_bot.py`) | T156 (`--test t_guest_approval_role`) |

---

## 3. Category B — Web UI End-to-End Tests

**File:** `src/tests/ui/test_ui.py`  
**Config:** `src/tests/ui/conftest.py`  
**Pytest ini:** `src/tests/ui/pytest.ini`  
**Technology:** Playwright (Python sync API) + pytest  
**Target:** Pi2 web interface at `https://openclawpi2:8080` (self-signed TLS)

### 3.1 Run commands

```bat
rem Run all UI tests against default Pi2 target
py -m pytest src/tests/ui/test_ui.py -v --base-url https://openclawpi2:8080 --browser chromium

rem Run only one test class
py -m pytest src/tests/ui/test_ui.py::TestAuth -v --base-url https://openclawpi2:8080

rem Run via conftest default (uses TARIS_BASE_URL env var or default https://openclawpi2:8080)
py -m pytest src/tests/ui/ -v

rem Override credentials via env vars
set TARIS_BASE_URL=https://openclawpi2:8080
set TARIS_ADMIN_USER=admin
set TARIS_ADMIN_PASS=admin
set TARIS_USER=stas
set TARIS_USER_PASS=zusammen20192
py -m pytest src/tests/ui/ -v
```

### 3.2 Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `TARIS_BASE_URL` | `https://openclawpi2:8080` | Target Pi base URL |
| `TARIS_ADMIN_USER` | `admin` | Admin username |
| `TARIS_ADMIN_PASS` | `admin` | Admin password |
| `TARIS_USER` | `stas` | Regular user username |
| `TARIS_USER_PASS` | `zusammen20192` | Regular user password |

### 3.3 Test classes and what they cover

| Class | Tests | What it validates |
|---|---|---|
| `TestAuth` | 7 tests | Login/logout flow, invalid creds, session persistence, unauthenticated redirect |
| `TestDashboard` | 5 tests | Dashboard heading, sidebar nav links, admin panel link visibility, status cards |
| `TestChat` | 7 tests | Chat input/send button, button state during LLM request, model selector, message display |
| `TestNotes` | 4 tests | Notes page layout, create button, list panel, editor panel |
| `TestCalendar` | 5 tests | Calendar page, console toggle, add-event form fields, form submit, console NL parse |
| `TestVoice` | 3 tests | Voice page, settings panel, TTS input presence |
| `TestMail` | 2 tests | Mail page, setup/digest section |
| `TestAdmin` | 4 tests | Admin access for admin role, user list, LLM section, non-admin blocked |
| `TestNavigation` | 3 tests (+ parametrized) | All sidebar nav links load correct page, clicking nav, logout link |
| `TestRegistration` | 3 tests | Register form, login→register link, duplicate username error |
| `TestProfile` | 4 tests | Profile page, account info, display name form, unauthenticated redirect |
| `TestSettings` | 4 tests | Settings page, language buttons, password form, unauthenticated redirect |
| `TestContacts` | 5 tests | Contacts list, search form, new contact form, create flow, unauthenticated redirect |
| `TestN8NCallback` | 3 tests | POST `/api/n8n/callback`: auth (401/403), valid payload accepted (200) |
| `TestCRMApi` | 4 tests | GET `/api/crm/contacts`, GET `/api/crm/stats`, POST `/api/crm/contacts`, auth guard (401) |
| `TestCampaignWebUI` | 3 tests | Campaign is Telegram-only — verify Web UI does NOT expose campaign routes |

### 3.4 When to run

Run Web UI tests after any change to:
- `src/bot_web.py` (API routes, auth, HTMX endpoints)
- `src/templates/*.html` (Jinja2 templates)
- `src/static/` (CSS, JS)
- Any UI flow visible to users (login, dashboard, chat, notes, calendar, voice, mail, admin)

**Always run UI tests before deploying a Web UI change to a production Pi.**

### 3.5 Requirements

```bat
pip install pytest playwright pytest-playwright
playwright install chromium
```

---

## 4. Category C — Hardware Audio Shell Tests

**Location:** `src/tests/*.sh`  
**Run on:** Pi directly (SSH), or via `plink` from Windows  
**Purpose:** Low-level audio hardware diagnosis when microphone or speaker issues occur

### 4.1 Test scripts

| Script | Purpose | When to use |
|---|---|---|
| `test_tts.sh` | End-to-end TTS: Piper synthesizes Russian text → ALSA playback via 3.5mm jack | After hardware speaker change, after Piper reinstall |
| `test_alsa_direct.sh` | Test ALSA direct capture (`hw:2,0` and `plughw:2,0`) with PipeWire stopped | When microphone produces zero audio |
| `test_ffmpeg_audio.sh` | Test ffmpeg audio capture via ALSA | After ALSA config changes |
| `test_ffmpeg_pa.sh` | Test ffmpeg capture via PulseAudio (`parec` compat layer) | When PipeWire/PA routing issues suspected |
| `test_mic.py` | Python `sounddevice` mic capture test; lists all audio devices, records 1s, reports levels | After new USB mic connected |
| `test_after_reboot.sh` | Check ALSA cards and webcam mic availability after Pi reboot | After Pi OS update or reboot |
| `test_video_audio.sh` | Test webcam video + audio capture together | When USB webcam microphone issues occur |
| `test_webcam_mic.sh` | Test webcam mic capture via ALSA | USB webcam mic debugging |
| `test_webcam_mic2.sh` | Second webcam mic test variant with different ALSA params | USB webcam mic fallback |

### 4.2 Diagnostic / check scripts

| Script | Purpose |
|---|---|
| `check_kernel_audio.sh` | Check kernel audio driver modules and ALSA cards |
| `check_dmesg_during_rec.sh` | Monitor `dmesg` during recording to catch USB errors |
| `check_pcm_detailed.sh` | Detailed ALSA PCM status dump |
| `check_usb_stream.sh` | Check USB isochronous stream status |
| `check_wireplumber.sh` | Check WirePlumber (PipeWire session manager) state |
| `try_latency_fix.sh` | Try ALSA latency settings to reduce underruns |
| `try_native_rate.sh` | Try microphone at its native sample rate (48kHz) instead of 16kHz |

### 4.3 Run commands

```bat
rem Run TTS hardware test
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "bash /home/stas/.taris/tests/test_tts.sh"

rem Run mic capture test (Python)
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_mic.py"

rem Run ALSA direct test
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "bash /home/stas/.taris/tests/test_alsa_direct.sh"
```

### 4.4 When to run

Run hardware audio tests when:
- Microphone produces no audio or zero-level audio
- TTS voice playback fails or is silent
- After connecting a new USB microphone or speaker
- After Pi OS update (ALSA/PipeWire configuration may change)
- After reboot, if voice pipeline stops working (`test_after_reboot.sh`)

---

## 5. Category D — Mic Capture Test

**File:** `src/tests/test_mic.py`  
**Run on:** Pi directly

Captures 1 second of audio from the default/USB input device, reports levels and sample rate. Use when diagnosing a microphone that appears connected but produces no data.

```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_mic.py"
```

Expected output includes `MIC_OK`. If `ERROR:` appears, the input device or sounddevice library has a problem.

---

## 6. Category E — Smoke / Deployment Tests

**Technology:** `plink` + `journalctl`  
**Run on:** Pi (remote SSH)  
**Purpose:** Verify the bot service started correctly after a deployment

### 6.1 Telegram bot smoke check

```bat
rem After deploying telegram_menu_bot.py
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "journalctl -u taris-telegram -n 20 --no-pager"
```

**Pass criteria:**
```
[INFO] Version      : 2026.X.Y
[INFO] DB init OK   : /home/stas/.taris/taris.db
[INFO] Polling Telegram…
```

### 6.2 Web UI smoke check

```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "journalctl -u taris-web -n 20 --no-pager"
```

Expected: `Uvicorn running on https://0.0.0.0:8080`

### 6.3 Voice assistant smoke check

```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "journalctl -u taris-voice -n 20 --no-pager"
```

Expected: `[Voice] Ready — say "Пико" to activate`

### 6.4 LLM gateway smoke check

```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "journalctl -u taris-gateway -n 20 --no-pager"
```

### 6.5 When to run

Run smoke tests after every deployment. They are the fastest sanity check — if the journal shows errors, do not proceed to automated tests.

---

## 6b. Category F — Offline Telegram Regression Tests

**File:** `src/tests/telegram/test_telegram_bot.py`  
**Config:** `src/tests/telegram/conftest.py`  
**Pytest ini:** `src/tests/telegram/pytest.ini`  
**Technology:** pytest + `unittest.mock` (no Telegram API calls, no Pi required)  
**Target:** Runs entirely on the local development machine

### 6b.1 Run commands

```bash
# Run all 40 offline Telegram tests (Linux/macOS)
cd /home/stas/projects/sintaris-pl
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest src/tests/telegram/ -v

# Run a single class
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest src/tests/telegram/test_telegram_bot.py::TestCallbackAdmin -v

# Quick run with short output
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest src/tests/telegram/ -q --tb=short
```

```bat
rem Windows
cd d:\Projects\workspace\taris\src\tests\telegram && py -m pytest test_telegram_bot.py -v
```

### 6b.2 Test classes and what they cover

| Class | Tests | What it validates |
|---|---|---|
| `TestCmdStart` | 4 | `/start` — new user, allowed user, blocked user, pending registration |
| `TestCallbackMode` | 4 | Callback mode switches: `mode_chat`, `mode_system`, `voice_session`, `cancel` |
| `TestCallbackAdmin` | 9 | Admin panel: add/remove/list users, pending approvals, reg approve/block, voice opts menu, LLM menu |
| `TestCallbackMenu` | 3 | Core menu callbacks: `menu`, `help`, `profile` |
| `TestVoiceHandler` | 3 | Voice pipeline routing: allowed user, guest blocked, admin |
| `TestTextHandlerNotes` | 2 | Note creation multi-step flow: title input, content input |
| `TestTextHandlerAdmin` | 2 | Admin-mode text routing: pending LLM key, pending add-user |
| `TestChatMode` | 3 | Free-chat mode: allowed, denied, LLM response forwarded |
| `TestVoiceSystemModeRouting` | 3 | Voice+system mode: admin routed, non-admin still passed to pipeline, text path blocks non-admin |
| `TestScreenDSLRoleFiltering` | 2 | Screen DSL: menu callback calls `load_screen`; admin gets `role='admin'` in context |

### 6b.3 Architecture notes

- `conftest.py` sets `WEB_ONLY=1` environment variable to skip `bot_web.py` FastAPI import during module load.
- All Telegram API calls (`bot.send_message`, `bot.answer_callback_query`, etc.) are mocked via `unittest.mock.patch`.
- Module-level state dicts (`_user_mode`, `_pending_note`, etc.) are reset between tests via `autouse` fixtures.
- No network, no Pi, no credentials required — safe for CI / local dev.

### 6b.4 When to run

Run offline Telegram regression after any change to:
- `src/telegram_menu_bot.py` (handler dispatch, callback routing)
- `src/telegram/bot_access.py` (access control, keyboard builders)
- `src/telegram/bot_admin.py` (admin panel handlers)
- `src/telegram/bot_handlers.py` (user handlers, notes flow)
- `src/telegram/bot_users.py` (registration data layer)
- Any new callback key added to `handle_callback()`

These tests run in **< 1 second** locally and should be run before every commit involving the Telegram bot.

---

## 7. Targets: Engineering vs Production

| Target | Host | Purpose | Tests allowed |
|---|---|---|---|
| **TariStation2 / OpenClawPI2** | `OpenClawPI2` / local `~/.taris/` | Engineering — all test types | All categories A–H |
| **TariStation1 / OpenClawPI** | `OpenClawPI` / `SintAItion` | Production — stable deployments only | Category B (UI), Category E (smoke) |
| **Local dev machine** | `localhost` | Quick offline checks | Categories F, G, H; A source-inspection T17–T54 |

**Rules:**
- Run destructive tests (audio hardware, regression) on engineering target (TariStation2/OpenClawPI2) first.
- Run Web UI Playwright tests against TariStation2 (`http://localhost:8080`) unless told otherwise.
- Only deploy to production (TariStation1/OpenClawPI) after engineering tests pass **and** code is on `master` / `taris-openclaw`.

---

## 6c. Category G — Screen DSL Loader Tests

**File:** `src/tests/screen_loader/test_screen_loader.py`  
**Config:** `src/tests/telegram/conftest.py` (shared)  
**Technology:** pytest (no Pi, no Telegram API)  
**Target:** Runs entirely on the local development machine

### 6c.1 Run commands

```bash
cd /home/stas/projects/sintaris-pl
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest src/tests/screen_loader/ -q --tb=short
```

### 6c.2 What it covers

- YAML screen file loading (`screens/*.yaml`) for all variants (taris / openclaw / picoclaw)
- `UserContext` role filtering: admin-only buttons hidden from `user`/`guest`
- Button `callback_data` and `label` rendering for each screen
- Screen not-found → safe error; malformed YAML → clear exception

### 6c.3 When to run

Run after any change to:
- `src/screens/*.yaml` (screen definitions)
- `src/ui/screen_loader.py`
- `src/ui/bot_ui.py` (UserContext, variant field)
- `src/ui/render_telegram.py`

---

## 6d. Category H — LLM Provider Tests

**File:** `src/tests/llm/test_ask_openclaw.py`  
**Technology:** pytest + `unittest.mock` (no live API calls)  
**Target:** Runs entirely on the local development machine

### 6d.1 Run commands

```bash
cd /home/stas/projects/sintaris-pl
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 -m pytest src/tests/llm/ -q --tb=short
```

### 6d.2 What it covers

| Test | What it checks |
|---|---|
| `test_all_providers_present` | `_DISPATCH` dict contains `openai`, `ollama`, `openrouter`, `openai_compat` |
| `test_ask_openai_success` | `_ask_openai()` parses valid API response |
| `test_ask_openai_auth_error` | 401 → `LLMError` raised |
| `test_ask_openai_timeout` | `requests.Timeout` → `LLMError` raised |
| `test_ask_llm_dispatches` | `ask_llm()` routes to correct provider via `_DISPATCH` |
| `test_ask_llm_unknown_provider` | Unknown provider → `LLMError` |
| `test_ask_llm_falls_back` | Primary fails → fallback provider tried |
| `test_ask_llm_falls_back_when_openclaw_not_found` | Primary not found → fallback (with empty `LLM_FALLBACK_PROVIDER`) |
| + 10 more | Ollama provider, OpenRouter, OpenAI-compat, retry logic, model constants |

### 6d.3 When to run

Run after any change to:
- `src/core/bot_llm.py`
- `LLM_PROVIDER`, `OLLAMA_MODEL`, `LLM_FALLBACK_PROVIDER` constants in `bot_config.py`
- Adding or removing LLM providers in `_DISPATCH`

---

## 6e. Category I — External Internet-Facing UI Tests

**File:** `src/tests/ui/test_external_ui.py`  
**Runner:** `tools/run_external_ui_tests.py`  
**Technology:** Playwright + pytest (Chromium headless)  
**Target:** Internet-deployed taris instances (e.g. `https://agents.sintaris.net/supertaris/`)  
**Run from:** any machine with internet access — no local taris install needed

### 6e.1 Run commands

```powershell
# Single instance (Windows)
cd src\tests\ui
$env:TARIS_ADMIN_USER = "stas"
$env:TARIS_ADMIN_PASS = "yourpassword"
python -m pytest test_external_ui.py -v `
    --base-url https://agents.sintaris.net/supertaris `
    --browser chromium --tb=short

# Multi-instance runner (all configured targets)
python tools/run_external_ui_tests.py
```

```bash
# Linux/macOS
cd src/tests/ui
TARIS_ADMIN_USER=stas TARIS_ADMIN_PASS=yourpassword \
  python -m pytest test_external_ui.py -v \
    --base-url https://agents.sintaris.net/supertaris \
    --browser chromium
```

### 6e.2 Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TARIS_ADMIN_USER` | No | `stas` | Login username for auth tests |
| `TARIS_ADMIN_PASS` | No | — | Login password; auth tests SKIP if unset |
| `TARIS_INSTANCES` | No | `supertaris,supertaris2` | Comma-separated sub-paths for multi-instance runner |

### 6e.3 What it covers (43 tests)

| Class | Tests | What it checks |
|---|---|---|
| `TestExternalReachability` | 5 | HTTP 200, no 502, HTTPS cert valid, SSL, login page loads |
| `TestExternalAuth` | 5 | Login form, wrong password rejected, login succeeds, logout, protected pages redirect |
| `TestExternalDashboard` | 4 | Dashboard loads after login, nav links present, page title, no 500 errors |
| `TestExternalPages` | 10 | `/chat`, `/voice`, `/notes`, `/calendar`, `/contacts`, `/documents`, `/profile`, `/settings`, `/admin`, each with heading + no-500 checks |
| `TestExternalHTMX` | 4 | New note via HTMX, note list update, chat form, calendar HTMX form |
| `TestExternalAdmin` | 5 | Admin page only for admin users, non-admin denied, user list loads, Web-token generation |
| `TestExternalRegressions` | 10 | `manifest.json` valid JSON, icon URLs correct, icon files not 404, root_path prefix in nav links, no double-prefix, HTTPS cert expiry > 7 days, static assets load, no mixed content, sub-path links consistent, security headers present |

### 6e.4 When to run

- After every deployment to any internet-facing target
- After nginx config changes (sub-path, proxy, SSL)
- After web UI template or bot_web.py changes
- Run as part of post-deploy verification before marking a release done

### 6e.5 Notes

- Auth tests auto-skip if `TARIS_ADMIN_PASS` is not set (CI-safe)
- Sub-path aware: uses `href*=` selectors, not exact href matches
- Chat test uses `wait_for_selector` (not `networkidle`) — chat page uses streaming
- Calendar test uses `wait_for_timeout(3_000)` — not networkidle

---

## 6f. Category J — Data Consistency Check

**File:** `src/tests/test_data_consistency.py`  
**Deploy path:** `~/.taris/tests/test_data_consistency.py`  
**Technology:** Standalone Python (stdlib only + optional psycopg for PostgreSQL)  
**Backends:** SQLite (PicoClaw) and PostgreSQL (OpenClaw) — auto-detected from `STORE_BACKEND`  
**Run on:** Any target (local or remote) with access to the database  
**When to run:** **Before every backup** and **after every data migration**

### 6f.1 What it checks

| Domain | Checks |
|---|---|
| **users / profile** | role in valid set, language in valid set, name or username non-empty |
| **notes** | slug and title non-empty, index ↔ filesystem sync (SQLite), orphaned `.md` files |
| **calendar** | title non-empty, `dt_iso` parseable as ISO-8601, no duplicate event IDs |
| **contacts** | name non-empty, ID non-empty, email format (if present) |
| **documents** | title non-empty, doc_id non-empty, `file_path` points to existing file (if set) |
| **conversation** | `role` in `{user, assistant, system}`, content non-empty, summary tier valid |
| **prefs** | `user_prefs` / `voice_opts` rows reference registered users |
| **global** | cross-table orphan detection: data rows with no matching user |

### 6f.2 Run commands

```bash
# Check all users (local)
python3 src/tests/test_data_consistency.py

# Check a single user
python3 src/tests/test_data_consistency.py --chat-id 12345

# Machine-readable JSON output (for CI / scripts)
python3 src/tests/test_data_consistency.py --json

# Auto-repair fixable issues (orphaned prefs rows)
python3 src/tests/test_data_consistency.py --fix

# Run before a backup (exit 1 stops the backup pipeline)
python3 src/tests/test_data_consistency.py && ./backup.sh
```

```bash
# On a remote target (Pi)
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI \
  "python3 /home/stas/.taris/tests/test_data_consistency.py"

# On OpenClaw target
ssh stas@SintAItion.local \
  "cd ~/projects/sintaris-pl && PYTHONPATH=src python3 src/tests/test_data_consistency.py"
```

### 6f.3 Exit codes

| Code | Meaning |
|---|---|
| `0` | All checks passed — no ERRORs, no WARNs |
| `1` | One or more ERRORs or WARNs found |
| `2` | Runner error (DB connection failure, missing config) |

### 6f.4 Output format

Issues are grouped by user and colour-coded:
- 🔴 **ERROR** — data loss risk or structural corruption (e.g. invalid role, unparseable datetime)
- 🟡 **WARN** — inconsistency that should be reviewed (e.g. orphaned file, missing email format)
- 🔵 **INFO** — informational only

### 6f.5 Deploy

```bash
# Deploy to Pi target
pscp -pw "%HOSTPWD%" src\tests\test_data_consistency.py stas@OpenClawPI:/home/stas/.taris/tests/

# Deploy to OpenClaw target (TariStation2)
scp src/tests/test_data_consistency.py stas@IniCoS-1:/home/stas/.taris/tests/
```

---

## 8. Regression Tests vs Fix Tests

### Regression tests
Tests T01–T16 are **regression tests**: they check that existing functionality (voice pipeline quality, latency, model files) did not degrade. Always run on Pi before committing voice-related code.

### Fix / bug guard tests
Tests T17–T21 are **fix (bug guard) tests**: each corresponds to a specific known bug (0.1–0.5 in `TODO.md`). They verify that the fix was correctly implemented and check that the fix does not regress. Run the matching test whenever you implement or modify a bug fix.

| Bug | Test | Description |
|---|---|---|
| Bug 0.1 — Profile crash | T18 `profile_resilience` | `_handle_profile()` must have `try/except` around deferred import |
| Bug 0.2 — Hardcoded bot name | T17 `bot_name_injection` | `BOT_NAME` from config, `{bot_name}` in strings |
| Bug 0.3 — Note edit loses content | T19 `note_edit_append_replace` | Append/Replace flow implemented |
| Bug 0.4 — Calendar voice deleted | T20 `calendar_tts_call_signature` | Correct function signature + datetime object |
| Bug 0.5 — Calendar console ignores add | T21 `calendar_console_classifier` | JSON intent classifier with `add` default |

### SQLite integration tests
Tests T22–T23 validate the `store_sqlite.py` data layer. Run after any change to the storage adapter or database schema.

| Test | What it validates |
|---|---|
| T22 `db_voice_opts_roundtrip` | Write voice opts via adapter, read back, confirm values round-trip correctly |
| T23 `db_migration_idempotent` | Run `migrate_to_db.py` twice; verify row count is stable (no duplicate rows) |

### RAG quality tests
Tests T24 validate the RAG pipeline. They gracefully SKIP when no knowledge documents have been uploaded yet.

| Sub-test | Env var | What it validates |
|---|---|---|
| `rag_lr_products_fts` | (always) | FTS5 retrieves chunks for LR products query; ≥2 of 6 expected keywords present in combined chunks |
| `rag_lr_products_llm` | `LLM_JUDGE=1` | Full RAG: FTS5 chunks → LLM answer → second LLM-as-judge call verifies thematic correctness |

**Run command for T24 only:**
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --test rag_lr"
```
**With LLM judge:**
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "LLM_JUDGE=1 python3 /home/stas/.taris/tests/test_voice_regression.py --test rag_lr"
```

### Web link code tests
Test T25 validates the Telegram↔Web account linking pipeline (`generate_web_link_code` / `validate_web_link_code` in `bot_state.py`). Uses a temporary file for full isolation — safe to run on any Pi.

| Sub-test | What it validates |
|---|---|
| `web_link_code:generate` | Code is exactly 6 uppercase alphanumeric chars |
| `web_link_code:validate` | Returns correct `chat_id` on first use |
| `web_link_code:single_use` | Second validate of same code returns `None` (consumed) |
| `web_link_code:invalid` | Unknown code returns `None` |
| `web_link_code:expired` | Code with past expiry returns `None` |
| `web_link_code:revoke_old` | Calling generate twice with same `chat_id` invalidates the first code |
| `web_link_code:cross_process` | Code is persisted to file immediately after generate (readable by new process) |

**Run command for T25 only:**
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --test web_link_code --verbose"
```

---

### OpenClaw voice + LLM tests (T35–T39)

Tests T35–T39 cover STT/TTS multi-language correctness, fallback chains, remote STT, and the voice LLM routing fix.

| ID | Function | What it tests |
|----|----------|---------------|
| T35 | `t_stt_language_routing_fw` | faster-whisper accepts ru/en/de language codes; hallucination guard rejects false-positives per lang; live silence→None for each lang |
| T36 | `t_stt_fallback_chain` | Primary STT fails → `vosk_fallback` activated; `STT_FALLBACK_PROVIDER` constant wired; silence triggers fallback |
| T37 | `t_openai_whisper_stt` | OpenAI Whisper API provider: constants present, `_stt_openai_whisper_web` defined, live call if API key set (SKIP if no key) |
| T38 | `t_tts_multilang` | Piper `_piper_model_path()` routes ru/de correctly; EN falls back to ru model; ru/de synthesis produces OGG (SKIP if Piper binary missing) |
| T39 | `t_voice_llm_routing` | `bot_voice.py` imports `ask_llm` (not `_ask_taris`); no `TARIS_BIN` reference; `ask_llm` callable; fallback chain wired |

**Run commands:**
```bash
# All five new tests at once (use substring match):
PYTHONPATH=src python3 src/tests/test_voice_regression.py --test stt_language
PYTHONPATH=src python3 src/tests/test_voice_regression.py --test stt_fallback
PYTHONPATH=src python3 src/tests/test_voice_regression.py --test openai_whisper_stt
PYTHONPATH=src python3 src/tests/test_voice_regression.py --test tts_multilang
PYTHONPATH=src python3 src/tests/test_voice_regression.py --test voice_llm_routing
```

**Mandatory when:**
- After changing `_stt_faster_whisper()` language routing or hallucination guard → T35
- After changing STT fallback logic in `bot_voice.py` or `STT_FALLBACK_PROVIDER` config → T36
- After changing `_stt_openai_whisper_web` or OpenAI STT config → T37
- After adding/removing Piper language models or changing `_piper_model_path()` → T38
- After any change that touches the voice pipeline's LLM call (was TARIS_BIN, now ask_llm) → T39

---

## 9. Adding New Tests

### Adding a new voice regression test

1. Add a test function `t_my_test(**_) -> list[TestResult]:` in `test_voice_regression.py`
2. Register it in the `ALL_TESTS` list near the bottom of the file
3. If it has a new fixture audio file, add it to `src/tests/voice/` and update `ground_truth.json`
4. Deploy updated test file and fixtures to Pi
5. Run with `--set-baseline` after the first successful run

### Adding a new Web UI test

1. Add a test method inside the appropriate `Test*` class in `test_ui.py`
2. Use the `admin_page` or `user_page` fixtures for authenticated tests
3. Use `fresh_page(browser, base_url)` for unauthenticated tests
4. Run locally against Pi2 to verify

### When to add a fix test

Whenever a new known bug is discovered and filed in `TODO.md` (bugs 0.N), add a corresponding `t_*` test in `test_voice_regression.py` that will FAIL if the bug is present and PASS when it is fixed.

---

## 10. Copilot Chat Mode — "Test the Software" Protocol

When a user writes a plain-text request such as:

- *"test the software"*
- *"run the tests"*
- *"verify the changes"*
- *"check if it works"*
- *"validate this deployment"*

Copilot should:

1. **Check what changed** — look at recent git diff or deployment context to determine which areas changed.
2. **Select the relevant test category** from the quick-reference table in Section 1.
3. **Run smoke tests first** (Category E) — fastest check; if journal shows errors, stop and report.
4. **Run automated tests** (Category A for voice changes, Category B for UI changes) — deploy test assets if needed.
5. **Run hardware tests** (Category C/D) only if an audio hardware issue is suspected.
6. **Report results** — summarize PASS/FAIL/SKIP/WARN counts, paste the test summary table.

**Before backup or after migration:** always run Category J data consistency check first.

**Default when nothing specific changed:** run Category E smoke tests on Pi1 + Category A voice regression suite.

**Example session flow:**
```
User: "test software"
Copilot:
  1. Check what files changed since last deploy
  2. If voice-related → deploy + run test_voice_regression.py on Pi1
  3. If UI-related → run pytest src/tests/ui/ --base-url https://openclawpi2:8080
  4. Always finish with smoke check: journalctl -u taris-telegram -n 20
  5. Report: "All 21 voice tests PASS, smoke OK ✅" or list failures
```
