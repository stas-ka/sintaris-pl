# Taris Bot — Completed Items

> All sections below were moved from `TODO.md`.
> Every item is fully implemented and verified.

---

### Bugs — Fixed in this Sprint ✅

| Bug | Fix | Version |
|---|---|---|
| 0.1 Profile menu silent crash | `try/except` guard around deferred import in `_handle_profile()` | v2026.3.29 |
| 0.2 Hardcoded bot name | `BOT_NAME` constant + `{bot_name}` in `strings.json` | v2026.3.29 |
| 0.3 Note edit loses content | Append / Replace mode buttons in note edit flow | v2026.3.29 |
| 0.4 Calendar voice deleted | Fixed orphan TTS cleanup guard — only deletes spinner messages | v2026.3.29 |
| 0.5 Calendar console ignores add | Intent classifier calls `_finish_cal_add()` directly | v2026.3.29 |
| 0.6 System Chat no role guards | `ADMIN_ALLOWED_CMDS` / `DEVELOPER_ALLOWED_CMDS` + `_classify_cmd_class()` | v2026.3.30 |
| 0.7 Add new Contact cancel shows "btn_cancel" | Added missing `btn_cancel` i18n key to ru/en/de in `strings.json` | v2026.3.31 |
| 0.8 Profile change password error | Fixed `account["id"]` → `account["user_id"]` key in `_finish_profile_change_pw()` | v2026.3.31 |
| 0.9 Telegram-Web link code HTTP 500 on `/register` | Codes persisted to `~/.taris/web_link_codes.json`; shared between Telegram and Web services | v2026.3.33 |
| 0.10 OpenAI model selection ignored active model | Fixed default `OPENAI_MODEL` + model catalog align in `bot_config.py` / `bot_llm.py`; admin model switch now reflected correctly | v2026.3.40 |
| 0.11 System Chat bypassed multi-LLM dispatch | `_handle_system_message()` now calls `ask_llm()` (bot_llm.py) instead of legacy `_ask_taris()` | v2026.3.41 |
| 0.12 Markdown parse_mode causes silent send failures | `bot_instance.py`: TeleBot default `parse_mode` changed to `None`; LLM/note responses in `bot_handlers.py` and voice fallback in `bot_voice.py` now use `parse_mode=None` | v2026.3.40 |
| 0.13 TTS speaks wrong language (Telegram UI lang vs voice lang) | `_voice_lang(chat_id)` helper added to `bot_voice.py`; TTS now uses `STT_LANG` (configured speech language) instead of Telegram client locale | v2026.3.41 |
| 0.14 Voice mode ignores user role in system chat | Voice pipeline checks `_cur_mode=="system"` and dispatches to `_handle_system_message()`, applying admin role guards and confirm gate | v2026.3.42 |
| 0.15 Bot 409 Conflict on restart | `_409Handler` exception handler in `bot_instance.py`; `TimeoutStopSec=25` in `taris-telegram.service`; SIGTERM/SIGINT handlers call `bot.stop_polling()` | v2026.3.39/v2026.3.40 |
| 0.16 System chat echo/wrong LLM | System Chat moved to Admin menu; `_handle_system_message()` uses `use_case="system"` for dedicated LLM; echo-proof confirm flow added | v2026.3.29+1 |
| 0.17 Welcome message leaks internals | Removed "using Vosk and Piper" from user welcome; voice diagnostics (STT/TTS/LLM model, timings) sent to admin only | v2026.3.29+3 |
| 0.18 STT shows "Vosk" in Web UI on OpenClaw | STT provider label in web UI now reads from `STT_PROVIDER` env var, not hardcoded | v2026.3.29+4 |
| 0.19 Notes "All Notes" button hangs / 400 BUTTON_DATA_INVALID | Cyrillic slugs exceeded 64-byte Telegram callback_data limit; fixed with SHA1 hash IDs (`_note_cb_id`) + reverse lookup; `_slug()` truncates at 48 bytes | v2026.3.29+7 |
| 0.20 Web TTS hardcoded Piper path | Fixed web TTS to use `PIPER_BIN` config constant instead of hardcoded path | v2026.3.29+4 |
| 0.21 Voice pipeline ignored conversation history | `bot_voice.py` called bare `ask_llm()` (stateless); fixed to use `ask_llm_with_history()` with system message + long-term memory + history + `_voice_user_turn_content()`; both user and assistant turns now saved to `chat_history` via `add_to_history()`; T59 regression test added | v2026.3.30+5 |
| 0.22 LLM context contamination (1837 year anchoring) | Added LLM call context trace tool: `llm_calls` table extended (model, temperature, system_chars, history_chars, rag_chunks, response_preview, context_snapshot); `db_get_llm_trace()`; Admin → LLM → 🔍 Context Trace panel shows last 5 calls with full breakdown; voice pipeline now logs to `llm_calls`; T60 (12 checks) | v2026.3.30+6 |
| 0.23 System chat "Could not generate a command" | Code rewritten: `_extract_bash_cmd()`, `_ask_llm_strict()`, role-aware RBAC guards; old error message eliminated | v2026.3.30 |
| 0.24 Delete personal context (memory) via Profile | `profile_clear_memory` button + handler wired in `profile.yaml` + `telegram_menu_bot.py` | v2026.3.30+ |
| 0.25 Static texts hardcoded in Python | `bot_calendar.py` `cal_event_saved_prefix`, `bot_voice.py` `audio_interrupted` + `voice_note_msg` moved to `strings.json`; T55 regression test | v2026.3.30+1 |
| 0.26 [BOT CAPABILITIES] tag not resolved in LLM response | `BOT_CAPABILITIES` placeholder replaced with resolved capabilities text at `ask_llm_with_history()` call time; tag no longer leaks to users | v2026.4.x |
| 0.27 load_system_docs.py crash — `vec_embeddings` relation missing | `upsert_chunk_text()` in `store_postgres.py` writes to `doc_chunks` when `_has_vec=False`; no crash when pgvector extension unavailable | v2026.4.x |
| 0.28 SintAItion voice LLM silently using Ollama (12–15 s lag) | `ask_llm_with_history()` defaulted to `use_case="chat"`; `per_func["chat"]="ollama"` routed voice to Ollama. Fix: `use_case="voice"` in voice pipeline | v2026.4.23 |
| 0.29 `active_model.txt` with `openai/` prefix → HTTP 400 → 14 s Ollama fallback | `get_active_model()` strips `provider/` prefix before API call | v2026.4.22 |
| 0.30 FasterWhisper thread cap silently ignored env var | Cap applied only on auto-detect; explicit `FASTER_WHISPER_THREADS` value now honoured | v2026.4.19 |
| 0.31 Embedding pre-warm missing — first RAG call cost 2–3 s | `_prewarm_embeddings()` background thread at startup; model warm before first request | v2026.4.20 |
---


---

## 1. Open Issues &amp; Roadmap

### 1.0 Profile Redesign ✅ Implemented (v2026.3.31)
Profile self-service hub — edit name, change password, open mailbox — in both Telegram and Web UI.

- [x] Crash guard: `try/except` in `_handle_profile()` around deferred import (Telegram) (v2026.3.29)
- [x] Profile inline keyboard: Edit name / Change password / Open mailbox / Web link (v2026.3.29)
- [x] `GET /profile` + `POST /profile/name` routes in `bot_web.py` (v2026.3.29)
- [x] `profile.html` template + `base.html` nav sidebar link (v2026.3.29)
- [x] Playwright test: `GET /profile` returns 200 — `TestProfile` class in `test_ui.py` (v2026.3.31)
- [x] Language selection in Profile: `_handle_profile_lang()` + `_set_profile_lang()` + `_set_reg_lang()` — persisted per user (v2026.3.31)
- [x] View stored data summary in Profile: `_handle_profile_my_data()` — notes, calendar, contacts, mail status (v2026.3.31)

---


---

## 3. LLM Provider Support
→ Document management and knowledge base features: see **§10** (Upload and Knowledge Documents).

### 3.1 Multi-LLM Provider Support ✅ Implemented (v2026.3.32)
OpenRouter ✅ · OpenAI direct ✅ · YandexGPT ✅ · Gemini ✅ · Anthropic ✅ · local llama.cpp ✅

- [x] `LLM_PROVIDER` env-var switch in `bot.env` (`taris` | `openai` | `yandexgpt` | `gemini` | `anthropic` | `local`)
- [x] `_DISPATCH` table + `ask_llm(prompt, timeout)` entry point in `src/core/bot_llm.py`
- [x] OpenAI direct client `_ask_openai()` — `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- [x] YandexGPT client `_ask_yandexgpt()` — `YANDEXGPT_API_KEY`, `YANDEXGPT_FOLDER_ID`, `YANDEXGPT_MODEL_URI`
- [x] Gemini client `_ask_gemini()` — `GEMINI_API_KEY`, `GEMINI_MODEL`
- [x] Anthropic client `_ask_anthropic()` — `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- [x] 14 provider constants added to `src/core/bot_config.py`
- [x] `taris` (default) provider wraps existing OpenRouter CLI — all existing behaviour unchanged

Emergency fallback via `llama.cpp`. Pi 3: Qwen2-0.5B (~1 tok/s); Pi 4/5: Phi-3-mini.
→ See: `doc/hardware-performance-analysis.md` §8.9
- [x] `taris-llm.service` systemd unit — llama-server on port 8081, `qwen2-0.5b-q4.gguf`, 4 threads, ctx 2048
- [x] `_ask_local()` client — OpenAI-compatible `/v1/chat/completions` against `LLAMA_CPP_URL` (default `http://127.0.0.1:8081`)
- [x] `LLM_LOCAL_FALLBACK=true` env-var — enables automatic fallback when primary provider fails
- [x] `ask_llm()` catches all primary errors; retries via `_ask_local()` when fallback enabled
- [x] Fallback responses prefixed with `⚠️ [local fallback]` label
- [x] Service staged on Pi2; starts automatically once `llama-server` binary is installed
- [x] Configurable, switchable via Admin Panel

### 3.2 Per-Function LLM Provider ✅ Implemented (v2026.3.29+8)
Different LLM providers for system chat vs. user chat, switchable at runtime from Admin panel.

- [x] `LLM_PER_FUNC_FILE = ~/.taris/llm_per_func.json` — runtime per-function provider overrides
- [x] `get_per_func_provider(use_case)` / `set_per_func_provider(use_case, provider)` in `bot_llm.py`
- [x] `_ask_with_fallback()` checks per-func overrides first, then global `LLM_PROVIDER`, then fallback chain
- [x] `ask_llm()` / `ask_llm_or_raise()` / `ask_llm_with_history()` all accept `use_case` parameter
- [x] `_handle_system_message()` uses `use_case="system"`; user chat uses `use_case="chat"`
- [x] Admin LLM menu redesigned: shows global + per-function status; provider switch buttons with ✅/⚠️ key availability; sub-menus for per-function picker
- [x] New Voice Config admin menu: STT provider switch (Vosk/Faster-Whisper), FW model selector (tiny/base/small/medium for OpenClaw), Piper model display

---


---

### 5.1 Whisper vs Vosk Decision ✅ Resolved (2026-03-21)

Full regression test run on both PIs. **Vosk wins decisively** on Raspberry Pi hardware.
→ [Test Protocol](doc/test-protocol-2026-03-21.md)

| Metric | Vosk (PI1) | Whisper (PI1) |
|---|---|---|
| Avg latency | 4–14 s | 25–45 s |
| WER (best) | 0.00 | 0.57 |
| Hallucination | None | Severe on short audio |

**Decision:** Keep Vosk as default STT. Whisper `whisper_stt` voice opt remains available but not recommended on Pi 3.
- [x] Fix test_voice_regression.py Whisper model path (ggml-tiny → ggml-base)
- [x] Run full regression on both PIs
- [x] Create test protocol (`doc/test-protocol-2026-03-21.md`)


---

### 8.2 Rename Assistant to Taris / TARIS and Platform to SINTA ✅ Implemented (v2026.4.7)

### 8.3 Offline Telegram Regression Suite ✅ Implemented (v2026.4.7)
31 offline unit tests (`src/tests/telegram/test_telegram_bot.py`) — 8 classes covering: CmdStart, CallbackMode, CallbackAdmin, CallbackMenu, VoiceHandler, TextHandlerNotes, TextHandlerAdmin, ChatMode. Runs locally, no Pi required.


---

### 19.1 Core Integration ✅ Implemented (v2026.4.13)

- [x] `DEVICE_VARIANT=openclaw` constant in `bot_config.py` (default: `picoclaw`)
- [x] `OPENCLAW_BIN` constant — `~/.local/bin/openclaw` (env override)
- [x] `LLM_PROVIDER=openclaw` — `_ask_openclaw()` in `bot_llm.py`; JSON output parsing; plaintext fallback
- [x] REST API: `POST /api/chat` + `GET /api/status` in `bot_web.py`; Bearer-token auth via `TARIS_API_TOKEN`
- [x] `skill-taris` in sintaris-openclaw calls these endpoints → bidirectional integration
- [x] Loop-prevention guard: documented in `doc/architecture/openclaw-integration.md`
- [x] Fallback chain: `openclaw` → `taris/picoclaw` → local `llama.cpp`
- [x] 18 unit tests for `_ask_openclaw()` in `src/tests/llm/` — all green
- [x] `TARIS_HOME` env var — configurable data directory for local dev and multi-instance

### 19.2 Infrastructure ✅ Implemented (v2026.4.13)

- [x] `src/core/store_postgres.py` — 696-line PostgreSQL + pgvector adapter (DataStore Protocol)
- [x] `src/core/bot_embeddings.py` — `EmbeddingService`: fastembed + sentence-transformers fallback; `EMBED_MODEL` / `EMBED_DIMENSION` constants
- [x] `src/setup/setup_voice_openclaw.sh` — x86_64 Vosk + Piper install; step 6/6 adds faster-whisper; `VOICE_BACKEND=cpu|cuda|openvino`
- [x] `src/setup/install_embedding_model.sh` — download + verify embedding model
- [x] `src/setup/setup_llm_openclaw.sh` — Ollama installer (qwen2:0.5b default); offline local LLM for OpenClaw (v2026.3.28-openclaw)
- [x] `bot.env.example` updated with `DEVICE_VARIANT`, `OPENCLAW_BIN`, `TARIS_API_TOKEN`

### 19.2b STT/LLM Extensions ✅ Implemented (v2026.3.28-openclaw)

- [x] `STT_PROVIDER` env var (`vosk` | `faster_whisper`); auto-default `faster_whisper` for openclaw
- [x] `FASTER_WHISPER_MODEL/DEVICE/COMPUTE` constants; `_stt_faster_whisper()` in `bot_voice.py`
- [x] `faster_whisper_stt` voice opt (True by default when DEVICE_VARIANT=openclaw)
- [x] `voice_assistant.py` standalone — `record_and_recognize_faster_whisper()` routing
- [x] `OLLAMA_URL` / `OLLAMA_MODEL` constants; `_ask_ollama()` in `bot_llm.py`; `LLM_PROVIDER=ollama` dispatch
- [x] `LLM_PROVIDER=ollama` as default in `~/.taris/bot.env` (fixes OPENAI_API_KEY not set error)
- [x] `src/tests/benchmark_stt.py` — Vosk vs faster-whisper benchmark script
- [x] T27–T30 OpenClaw regression tests in `test_voice_regression.py`

### 19.3 Local Development Deploy ✅ Implemented (v2026.4.13)

- [x] `sintaris-openclaw-local-deploy/` — symlink launcher for running Taris locally
- [x] `run_all.sh` / `run_telegram.sh` / `run_web.sh` — start/stop scripts with `TARIS_HOME` set
- [x] `sintaris-openclaw` (`skill-taris`) installed and connected to local Taris instance
- [x] Documentation: `doc/architecture/openclaw-integration.md`; `doc/architecture/deployment.md §13 Local Development Deploy`

### 19.5 Dual STT — Local + Remote ✅ Implemented (v2026.3.31)

- [x] `STT_PROVIDER=openai_whisper` — OpenAI Whisper API provider added to `bot_web.py`
- [x] `_stt_openai_whisper_web()` — PCM→WAV→POST to `/v1/audio/transcriptions`; reuses `OPENAI_API_KEY` + `OPENAI_BASE_URL`; graceful fallback to Vosk if key missing
- [x] `STT_OPENAI_MODEL` constant (default `whisper-1`); `STT_LANG` constant (default `ru`); supports ru/en/de/sl
- [x] `_stt_web()` updated: dispatch table `_STT_DISPATCH` + primary→fallback chain (mirrors LLM `_DISPATCH`)
- [x] `STT_FALLBACK_PROVIDER` constant (auto-default `vosk` when primary ≠ vosk)
- [x] `_voice_pipeline_status()` shows provider + fallback status; UI label shows `Primary → Fallback`
- [x] Slovenian (`sl`) added to `lang_map` in faster-whisper transcription

### 19.6 Voice Debug Mode + LLM Named Fallback ✅ Implemented (v2026.3.32)

- [x] `core/voice_debug.py` — `VoiceDebugSession`: saves all pipeline stages per request when `VOICE_DEBUG_MODE=1`:
  - `input.webm` raw audio · `decoded.pcm` + `decoded.wav` · `stt.txt` · `llm_answer.txt` · `tts_input.txt` · `tts_output.ogg` · `pipeline.json`
- [x] `VOICE_DEBUG_MODE` / `VOICE_DEBUG_DIR` constants in `bot_config.py`
- [x] `voice_chat_endpoint` + `voice_transcribe_endpoint` wired with `VoiceDebugSession`; return `debug_session_id` in JSON
- [x] `GET /voice/debug/sessions` — list recent sessions (auth required)
- [x] `GET /voice/debug/{session_id}/{filename}` — download any debug file (path traversal blocked)
- [x] `voice.html` — 📥 download button next to every TTS audio player (server link when debug active, blob URL otherwise)
- [x] `LLM_FALLBACK_PROVIDER` constant — named LLM fallback, mirrors `STT_FALLBACK_PROVIDER`
  - Example: `LLM_PROVIDER=ollama` + `LLM_FALLBACK_PROVIDER=openai` → local first, cloud on failure
- [x] `_ask_with_fallback()` in `bot_llm.py`: primary → named fallback → legacy `LLM_LOCAL_FALLBACK` chain
- [x] `ask_llm()` + `ask_llm_or_raise()` refactored onto `_ask_with_fallback()`
- [x] T34 `t_voice_debug_mode`: 3/3 PASS

**✅ LLM operational on SintAItion**: Ollama v0.18.3 with qwen3:14b in VRAM; `LLM_PROVIDER=openai` (OpenAI API primary), `LLM_FALLBACK_PROVIDER=ollama` (local fallback). Bot config block injected into all prompts so the bot can answer "which model are you using?" (v2026.3.29+10)

---


---

### 20.1 Quick wins ✅ All done

- [x] **P-4** Split `doc/architecture.md` into `doc/architecture/*.md` (8 topic files) — ✅ done
- [x] **P-3** Replace "ALWAYS read bot-code-map.md" with "search it" instruction — ✅ done
- [x] **P-8** Add `doc/quick-ref.md` — single 3 KB always-read index — ✅ done
- [x] **P-2** Slim `copilot-instructions.md` — remove T01–T21 table and duplicate patterns — ✅ done
- [x] **P-1** Fix `safe-update.instructions.md` `applyTo` glob → narrowed to 4 concrete paths — ✅ done
- [x] **P-7** Move accounting task from `INSTRUCTIONS.md` to `concept/` — ✅ done
- [x] **P-6** Shorten `bot-deploy.instructions.md` — §§2–5 condensed, pointer to `/taris-deploy-to-target` — ✅ done

### 20.2 Medium effort ✅ All done

- [x] **P-6b** Shorten `safe-update.instructions.md` — Steps 1–9 bat blocks → 9-item checklist — ✅ done
- [x] **P-6c** Shorten `bot-coding.instructions.md` — doc-maintenance + Piper chain removed, pointer to `/taris-update-doc` — ✅ done
- [x] **P-9** Update `doc/copilot-skills-guide.md` — `#file:` tip box + `@workspace` warning added — ✅ done
- [x] **P-10** Add token-budget review table to `doc/vibe-coding-guidelines.md` sprint checklist — ✅ done

### 20.4 Guidelines & Process ✅ All done

- [x] **G-1** Create `doc/vibe-coding-guidelines.md` — artifact structuring rules, session habits, naming conventions — ✅ done
- [x] **G-2** Add quarterly review section to `doc/vibe-coding-protocol.md` — ✅ done
- [x] **G-3** Add context-optimization bullet to session-start checklist in `AGENTS.md` — ✅ done

---


---

### 21.1 Phase 1 — Core Loader ✅ Implemented (v2026.3.43)

- [x] Create `src/ui/screen_loader.py` (288 lines): `_WIDGET_BUILDERS` registry, `load_screen()`, all 10 widget builders
- [x] JSON support (stdlib `json`) + YAML support (optional `pyyaml`)
- [x] i18n key resolution via `t_func(lang, key)` parameter
- [x] Role-based widget visibility (`visible_roles: [admin]` in YAML)
- [x] Variable substitution in text and actions (`{var_name}` → `variables` dict)
- [x] `load_all_screens(dir)` for preload at startup
- [x] `reload_screens()` for hot-reload (clears `_screen_cache`)
- [x] Add `pyyaml` to `deploy/requirements.txt`
- [x] Unit tests: 53 tests across 9 test classes — all pass on PI2

### 21.2 Phase 2 — Proof of Concept ✅ Implemented (v2026.3.43)

- [x] Create `src/screens/` directory for YAML/JSON screen definitions
- [x] Convert `help` screen to `screens/help.yaml`
- [x] Wire Telegram callback: `load_screen("screens/help.yaml", ctx, t_func=_t_by_lang)` + `render_screen()`
- [x] Add `GET /screen/{screen_id}` route in `bot_web.py` + `templates/dynamic.html`
- [x] Add `reload_screens` admin callback → "✅ Screens reloaded"
- [x] Smoke test: both services running v2026.3.43 on PI2, clean startup confirmed

### 21.3 Phase 3 — Main & Admin Menus ✅ Implemented (v2026.3.43)

- [x] Convert main menu to `screens/main_menu.yaml` (with `visible_roles` for admin button row)
- [x] Convert admin menu to `screens/admin_menu.yaml` (with `{pending_badge}` variable substitution)
- [x] Wire Telegram callbacks: `menu` and `admin_menu` use DSL `load_screen()` + `render_screen()`
- [x] Add 11 admin i18n keys to `strings.json` (ru/en/de)
- [x] Test: py_compile OK, YAML validation OK, IDE error-free

### 21.4 Phase 4 — Feature Screens ✅ Implemented (v2026.3.43)

- [x] Convert notes list + note view + note edit screens (`notes_menu.yaml`, `note_view.yaml`, `note_raw.yaml`, `note_edit.yaml`)
- [x] Convert settings/profile screen (`profile.yaml`, `profile_lang.yaml`, `profile_my_data.yaml`)
- [x] Wire all 7 handlers in `bot_handlers.py` via `_render()` + `_screen_ctx()` helpers
- [x] All 10 YAML screen files in `src/screens/`, validated with zero errors

### 21.5 Phase 5 — Validation & Docs ✅ Implemented (v2026.3.43)

- [x] Create `src/screens/screen.schema.json` JSON Schema (draft-07, 14 definitions, 10 widget types)
- [x] Add schema validation in `_load_file()` — log warning on invalid files
- [x] Document screen file format as new section §19 in `doc/dev-patterns.md`
- [x] Update `doc/bot-code-map.md` with `screen_loader.py` entry

---

## 2. Conversation & Memory

### 2.1 Conversation Memory System ✅ Implemented (v2026.3.33 / v2026.3.30+5)

Per-user sliding window history stored in SQLite `chat_history` table; injected as `role:system` + prior turns into every LLM call.

- [x] Store per-user conversation history (sliding window, default 15 messages)
- [x] Inject last N messages as context into LLM prompt
- [x] Persist across restarts — stored in SQLite `chat_history` (not JSON)
- [x] Delete personal context (memory) via Profile menu after confirmation (v2026.3.30+)
- [x] Voice pipeline uses `ask_llm_with_history()` with full system message + long-term memory + history + `_voice_user_turn_content()`; both user and assistant turns saved via `add_to_history()` (v2026.3.30+5)

---

## 20.3 Copilot Optimization — Larger Refactors ✅ All done

- [x] **P-5** ~~Split `src/bot_web.py`~~ — superseded by §21 (Screen DSL + YAML Loader): declarative screen files naturally modularize UI without risky file split. Screen logic migrates to `src/screens/*.yaml`; `bot_web.py` gains a single `/dynamic/{screen_id}` route instead of N hardcoded render blocks.
- [x] **P-11** Back-link footers added to all 9 `doc/todo/*.md` specs; `storage-architecture.md` noted as 18 KB (> 10 KB target, trimming deferred) — ✅ done

---

## 22. Notes ✅ All implemented (v2026.3.30)

### 22.1 Download, Upload, Edit Notes

- [x] Every user can download all Notes (in Zip) or every Note separately (v2026.3.30)
- [x] Deleting a Note requires confirmation from user (v2026.3.30)
- [x] Note title is changeable — function to change title of Note added (v2026.3.30)
- [x] Two-step add/change content flow eliminated — Append/Replace available in first step (v2026.3.30)
- [x] After updating Note, it is immediately visible with add/change buttons available (v2026.3.30)

---

## 4. Content & Knowledge ✅ All done (v2026.4.41)

- [x] Timeout monitoring — FTS search enforced with `rag_timeout` via `concurrent.futures` (v2026.3.30+4)
- [x] Settings for LLM+RAG configurable via Admin Panel: top-K, chunk size, timeout, **temperature** (0.0–2.0) editable at runtime (v2026.3.30+4)
- [x] Settings incl. credentials to connect to remote RAG MCP service via Admin panel (v2026.4.38, Admin → RAG → Remote MCP)
- [x] Information for the user about upload restrictions (Max 20 MB shown in docs menu; `MAX_DOC_SIZE_MB=20` constant) (v2026.3.30+4)
- [x] `store.log_rag_activity()` after every FTS retrieval — RAG log populated; Admin Panel shows last 20 queries (v2026.3.30+4)
- [x] After uploading: save parse/chunk/embed stats in DB; Admin → RAG → 📄 Doc Stats panel (v2026.4.41)

### 4.1 Local RAG Knowledge Base ✅ Implemented (v2026.3.43 / v2026.4.14)

- [x] RAG on/off toggle in Admin Panel via `RAG_FLAG_FILE`; `RAG_ENABLED`, `RAG_TOP_K`, `RAG_CHUNK_SIZE` constants; admin callbacks wired (v2026.3.43)
- [x] Configurable RAG settings from Admin Panel UI: top-K, chunk size, timeout, temperature at runtime (v2026.3.30+4)
- [x] Local LLM for RAG: `LLM_PROVIDER=local` via llama.cpp (v2026.3.32)
- [x] FTS5-only RAG pipeline: `_chunk_text()` (512-char) → `doc_chunks` FTS5 table → `search_fts()` → LLM injection (v2026.3.43)
- [x] `install_sqlite_vec.sh` + `vec_embeddings` table (sqlite-vec, 384-dim) + `upsert_embedding()` / `search_similar()` / `delete_embeddings()` in `store_sqlite.py` (v2026.4.13)
- [x] `all-MiniLM-L6-v2` embeddings via ONNX Runtime: `EMBED_MODEL` in `bot_config.py`; `EmbeddingService` in `bot_embeddings.py` (v2026.4.14)
- [x] pgvector HNSW — `ALTER TABLE ADD COLUMN embedding vector(384)` + HNSW index (`m=16, ef_construction=64`) in `store_postgres._init_schema`, gated on `_has_vec` (v2026.4.39)
- [x] Timeout monitoring via `concurrent.futures` with `RAG_TIMEOUT` constant (v2026.3.30+4)
- [x] RAG activity log (`rag_log` table) + Admin Panel: last 20 queries + chunks injected (v2026.3.30+4)

### 4.2 Remote RAG Service (MCP) ✅ Implemented (v2026.4.1 / v2026.4.38)

- [x] Expose `search_knowledge()` as MCP tool — `/mcp/search` endpoint in `bot_web.py` (Bearer-token auth) (v2026.4.1)
- [x] Connect to external MCP RAG services via `MCP_REMOTE_URL` — `bot_mcp_client.py` (v2026.4.1)
- [x] Circuit breaker + timeout (10 s default); 3 failures → 5 min cooldown; fallback to local KB (v2026.4.1)
- [x] Credentials and endpoint URL configurable in Admin Panel — Admin → RAG → 🔌 Remote MCP; stored in `system_settings`; applied at runtime (v2026.4.38)

---

## 6.1 Logging & Monitoring ✅ Implemented (v2026.3.42 / v2026.4.40)

- [x] Structured log categories: `assistant.log`, `security.log`, `voice.log`, `datastore.log` (`src/core/bot_logger.py`)
- [x] Admin Telegram UI: 📊 Logs button — tail last 50 lines per category
- [x] Log rotation (`src/services/taris-logrotate`) — daily, 7 days, compress, copytruncate
- [x] Telegram alert handler: CRITICAL/ERROR forwarded to admins on startup
- [x] `taris-download-logs` skill — `.github/skills/taris-download-logs/SKILL.md`; covers 5 log categories × 4 targets (v2026.4.40)

---

## 10.1 Short-, Middle- and Long-term Memories ✅ Implemented (v2026.3.30+5 / v2026.3.31)

- [x] Short-term memory: sliding window in `_conversation_history` (in-memory + `chat_history` DB); size: `CONVERSATION_HISTORY_MAX` (default 15) (v2026.3.30)
- [x] Mid-term summarization: `_summarize_session_async()` triggered at `CONV_SUMMARY_THRESHOLD` (v2026.3.30+5)
- [x] Long-term compaction: mid→long at `CONV_MID_MAX`; stored in `conversation_summaries` table (v2026.3.30+5)
- [x] Clearing all memory tiers: `clear_history()` + `profile_btn_clear_all_memory` button (v2026.3.30+5)
- [x] Memory parameters configurable in Admin panel: `system_settings` table; Admin → Memory Settings (v2026.3.31)
- [x] Memory context injection togglable per user: `memory_enabled` in `user_prefs`; Profile toggle (v2026.3.31)

---

## 19.4 OpenClaw Pending Items ✅ All done (v2026.3.29+10 / v2026.4.31)

- [x] **Install Ollama** — v0.18.3 on SintAItion; qwen3:14b fully in VRAM (14.8 GB AMD Radeon 890M); `~/.config/systemd/user/ollama.service`; `LLM_PROVIDER=openai`, `LLM_FALLBACK_PROVIDER=ollama` (v2026.3.29+10)
- [x] **Upgrade faster-whisper model** — `small` model (244M params, WER ~5–8%); `FASTER_WHISPER_THREADS=8`; `setup_voice_openclaw.sh` default updated (v2026.3.29+10)
- [x] **STT/LLM switch in admin menu** — `STT_PROVIDER` toggle (Vosk/FW) + FW model selector in Admin → Voice Config; LLM per-function switch in Admin → LLM Settings (v2026.3.29+8)
- [x] `migrate_sqlite_to_postgres.py` — taris.db → PostgreSQL; 316 rows migrated; idempotent (v2026.4.31)
- [x] pgvector HNSW + full RAG pipeline on PostgreSQL — `search_similar()` + HNSW in `store_postgres.py`; hybrid RRF in `bot_rag.py` (v2026.4.13)
- [x] Screen DSL: `visible_variants: [openclaw]` — implemented in `screen_loader.py`; used in `admin_menu.yaml` (v2026.4.13)

---

## 25. Deployment Plan: OpenClaw (TariStation2 + SintAItion) ✅ Implemented (v2026.4.50)

- [x] **25.1 Base System** — Ubuntu 24.04 LTS; `ffmpeg`, `git`, Python 3.12; source deployed to `~/.taris/` on both targets
- [x] **25.2 PostgreSQL + pgvector** — PostgreSQL 17 (TariStation2) + 16 (SintAItion); `CREATE EXTENSION IF NOT EXISTS vector;`; `STORE_BACKEND=postgres` + auto-table creation
- [x] **25.3 Local LLM (Ollama)** — SintAItion: `gemma4:e4b` (AMD ROCm GPU, 45 t/s); TariStation2: `qwen3.5:0.8b` (CPU-only); `LLM_PROVIDER=ollama`, `LLM_FALLBACK_PROVIDER=openai`
- [x] **25.4 Embedding Service** → `src/core/bot_embeddings.py` (v2026.4.13)
- [x] **25.5 Voice Pipeline** → faster-whisper STT + Piper TTS + Vosk hotword (v2026.3.28 / v2026.4.13)
- [x] **25.6 RAG A–D** → Memory, Enhanced RAG, Document Mgmt, Remote MCP (v2026.3.30–v2026.4.38)
- [x] **25.7 SQLite → PostgreSQL Migration** → `migrate_sqlite_to_postgres.py`; 316 rows; SQLite eliminated on OpenClaw (v2026.4.31)
- [x] **25.8 Services** → `taris-telegram`, `taris-web`, `taris-tunnel`, `taris-pg-tunnel`, `ollama` services on both targets; Playwright + offline tests passing
- [ ] **25.9 HNSW index** (optional perf improvement — not yet applied on either target)
- [ ] **doc_sharing ACL table** (§27.4 — fine-grained per-user ACL) — still open

---

## 26. Deployment Plan: VPS (Cloud Docker) ✅ Implemented (v2026.4.50)

- [x] **26.1 Provision** — Docker 28.3.2 on dev2null.de (Ubuntu aarch64, 6 vCPU, 7.7 GB RAM); `stas` user in docker group
- [x] **26.2 PostgreSQL + pgvector** — PG16 + pgvector 0.8.0; `taris_vps` database; `STORE_BACKEND=postgres`; tables auto-created
- [x] **26.3 TLS + nginx** — nginx proxies `/supertaris-vps/` → `http://127.0.0.1:8090/`; TLS via Let's Encrypt on `agents.sintaris.net`
- [x] **26.4 Telegram Bot** — @supetariss_bot (`supetariss_bot`) live; `BOT_TOKEN` set in `/opt/taris-docker/bot.env`; `Polling Telegram…` confirmed
- [x] **26.5 RAG + Embeddings** — `fastembed` + `pgvector` in Docker image; `LLM_PROVIDER=openai` (gpt-4o-mini); faster-whisper + Piper TTS pre-loaded
- [x] **26.6 User data migration** — SintAItion → `taris_vps`: 24 calendar, 162 chat_history, 13 notes, 4 contacts, 3 docs, 13 summaries migrated; persistent volumes for notes/docs/mail_creds added to docker-compose.yml
- [x] **26.6 Backup script** — `deploy/system-configs/vps/cron/backup-taris-vps.sh` created (cron install pending on VPS)
- [x] **26.7 Web access** — `https://agents.sintaris.net/supertaris-vps/`; login: stas / buerger (admin)
- [ ] **26.7 Security hardening** — SSH key-only login + fail2ban still open on VPS

---

`src/core/bot_embeddings.py` — `EmbeddingService`: fastembed-first, sentence-transformers fallback; `EMBED_MODEL` / `EMBED_KEEP_RESIDENT` / `EMBED_DIMENSION` constants in `bot_config.py`; wired into `bot_documents.py`; `src/setup/install_embedding_model.sh`; `bot.env.example` updated.

## 25.5 Voice Pipeline + NPU Acceleration ✅ Extended (v2026.3.28-openclaw / v2026.4.13)

- `STT_PROVIDER` env var (`vosk` | `faster_whisper` | `whisper_cpp`); auto-defaults to `faster_whisper` when `DEVICE_VARIANT=openclaw`
- `FASTER_WHISPER_MODEL/DEVICE/COMPUTE` constants; `faster_whisper_stt` voice opt (default True for openclaw)
- `_stt_faster_whisper()` in `bot_voice.py` — CTranslate2 backend, built-in VAD, language detection
- `voice_assistant.py` — `record_and_recognize_faster_whisper()` + STT routing by `STT_PROVIDER`
- `setup_voice_openclaw.sh` — step 6/6 installs faster-whisper + pre-downloads base model
- `src/tests/benchmark_stt.py` — Vosk vs faster-whisper benchmark (WER, RTF, latency)
- `VOICE_BACKEND=cpu|cuda|openvino` + whisper-cpp `--device cuda` support (v2026.4.13)

## 25.6 RAG Phases A, B, C, D ✅ Implemented

- [x] **Phase A — Memory System:** Tiered short/mid/long-term memory in `bot_state.py`; `conversation_summaries` DB table; `_summarize_session_async()` + `get_memory_context()`; per-user toggle + Admin panel config (v2026.3.31)
- [x] **Phase B — Enhanced RAG:** FTS5 BM25 + EmbeddingService (ONNX) + pgvector HNSW + `classify_query()` adaptive routing + RRF fusion (k=60) + hardware-tier detection + RAG monitoring dashboard + sqlite-vec for PicoClaw (v2026.3.30–v2026.4.13)
- [x] **Phase C — Document Management:** Upload/chunk pipeline + document sharing (`is_shared` flag) + admin sharing controls + `rag_settings` + deduplication + PyMuPDF + per-user rag_settings + admin-only documents (`is_shared=2`) + MCP Remote RAG admin UI (v2026.3.30–v2026.4.38) _(fine-grained per-user ACL tracked in §27.4)_
- [x] **Phase D — Remote RAG + MCP:** `/mcp/search` endpoint + `bot_mcp_client.py` circuit breaker + RRF merge (v2026.4.1)

---
