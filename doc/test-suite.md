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
| **Local dev machine** | `localhost` | Quick offline checks | Categories F, G, H; A source-inspection T17–T43 |

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
