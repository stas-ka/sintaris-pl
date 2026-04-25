---
name: taris-voicetests
description: >
  Run the full voice regression test suite (T01–T232+) on the Raspberry Pi
  or locally (source-inspection tests). Reports PASS/FAIL/WARN/SKIP per test.
  Hardware voice tests: T01–T16 (Pi only). Source inspection: T17–T55+ (any machine).
  OpenClaw STT/LLM tests: T27–T41. Full extended regression: T56–T232+.
argument-hint: >
  scope: all | source | pi1 | pi2 | openclaw (default: source for local, pi2 for full)
  filter: test name fragment (optional, e.g. "tts" runs only TTS tests)
---

## When to Use

Run voice regression tests after any change to:
- `src/features/bot_voice.py`
- `src/core/bot_config.py` (voice constants, language, STT/TTS paths)
- `src/telegram/bot_access.py` (`_escape_tts`)
- `src/setup/setup_voice.sh`
- Any bug fix in voice pipeline, TTS, STT, or language routing

**Full test range is T01–T232+, organized by scope:**

| Scope | T-range | Requires |
|-------|---------|---------|
| Hardware voice | T01–T16 | Pi (Vosk, Piper, ffmpeg, audio) |
| Source inspection core | T17–T55 | Local only |
| LLM/RAG/memory | T56–T116 | Local only |
| Gemma4/Ollama picker | T117–T122 | Local only |
| Guest/RBAC/CRM | T140–T172 | Local only |
| Remote KB / MCP | T200–T232 | VPS Postgres (live) / local (source) |

---

## Local Source-Inspection Run (no Pi needed)

Covers T17–T41 (structural tests, no hardware):

```bash
cd /home/stas/projects/sintaris-pl
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py \
  --test t_confidence_strip t_tts_escape t_i18n_string_coverage t_lang_routing \
  t_bot_name_injection t_profile_resilience t_note_edit_append_replace \
  t_calendar_tts_call_signature t_calendar_console_classifier \
  t_db_voice_opts_roundtrip t_db_migration_idempotent t_rag_lr_products \
  t_web_link_code_roundtrip t_system_chat_clean_output t_openclaw_stt_routing \
  t_openclaw_ollama_provider t_web_stt_provider_routing t_pipeline_logger \
  t_dual_stt_providers t_voice_debug_mode t_stt_language_routing_fw \
  t_stt_fallback_chain t_openai_whisper_stt t_tts_multilang t_voice_llm_routing \
  t_voice_system_mode_routing_guard t_voice_lang_stt_lang_priority
```

---

## Full Hardware Run (requires Pi)

### Engineering target (PI2 / OpenClawPI2) — run first

```bash
plink -pw "$HOSTPWD2" -batch stas@OpenClawPI2 \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"
```

### Production (PI1 / OpenClawPI) — only after PI2 passes + code on master

```bash
plink -pw "$HOSTPWD" -batch stas@OpenClawPI \
  "python3 /home/stas/.taris/tests/test_voice_regression.py"
```

### Verbose run

```bash
plink -pw "$HOSTPWD2" -batch stas@OpenClawPI2 \
  "python3 /home/stas/.taris/tests/test_voice_regression.py --verbose"
```

### Single test group

```bash
# Local
DEVICE_VARIANT=openclaw PYTHONPATH=src \
  python3 src/tests/test_voice_regression.py --test tts

# Pi
plink -pw "$HOSTPWD" -batch stas@OpenClawPI \
  "python3 /home/stas/.taris/tests/test_voice_regression.py --test tts"
```

---

## Deploy Test Assets (when fixtures change)

```bash
pscp -pw "$HOSTPWD" src/tests/test_voice_regression.py \
  stas@OpenClawPI:/home/stas/.taris/tests/
pscp -pw "$HOSTPWD" src/tests/voice/ground_truth.json \
  stas@OpenClawPI:/home/stas/.taris/tests/voice/
pscp -pw "$HOSTPWD" src/tests/voice/*.ogg \
  stas@OpenClawPI:/home/stas/.taris/tests/voice/
```

---

## Pass / Fail Rules

| Result | Action |
|---|---|
| `PASS` | ✅ All good |
| `FAIL` | Fix before committing. Never skip. |
| `WARN` | >30% slower than baseline. Investigate. If intentional: `--set-baseline`. |
| `SKIP` | Acceptable for optional components (Whisper, VAD, German models). |

After fixing a voice bug:
1. Re-run tests.
2. Paste the summary table in the commit message.
3. If timing changed intentionally: run `--set-baseline`.

---

## Test IDs — T01–T55+ (source-inspection range; hardware: T01–T16)

> Full extended registry (T56–T232) is in [`doc/test-suite.md`](../../../doc/test-suite.md) §2–§3.

| ID | Test | Pi? |
|---|---|---|
| T01 | `model_files_present` — Vosk, Piper, ffmpeg present | Yes |
| T02 | `piper_json_present` — .onnx.json alongside .onnx | Yes |
| T03 | `tmpfs_model_complete` — .onnx + .json in /dev/shm/piper/ | Yes |
| T04 | `ogg_decode` — ffmpeg decodes OGG → PCM | Yes |
| T05 | `vad_filter` — WebRTC VAD strips non-speech | Yes |
| T06 | `vosk_stt` — WER ≤ 30% | Yes |
| T07 | `confidence_strip` — `[?word] → word` regex | Local |
| T08 | `tts_escape` — emoji/Markdown removed | Local |
| T09 | `tts_synthesis` — Piper → OGG latency | Yes |
| T10 | `whisper_stt` — WER ≤ 40% (SKIP if absent) | Yes |
| T11 | `whisper_hallucination_guard` — sparse-output guard | Yes |
| T12 | `regression_check` — timings within 30% of baseline | Yes |
| T13 | `i18n_string_coverage` — ru/en/de key sets identical | Local |
| T14 | `lang_routing` — model path routing for ru/en/de | Local |
| T15 | `de_tts_synthesis` — German Piper TTS (SKIP if absent) | Yes |
| T16 | `de_vosk_model` — German Vosk model loads | Yes |
| T17 | `bot_name_injection` — BOT_NAME + placeholders | Local |
| T18 | `profile_resilience` — try/except in profile | Local |
| T19 | `note_edit_append_replace` — append/replace flow | Local |
| T20 | `calendar_tts_call_signature` — 2-arg signature | Local |
| T21 | `calendar_console_classifier` — JSON intent | Local |
| T22 | `db_voice_opts_roundtrip` — SQLite round-trip | Local |
| T23 | `db_migration_idempotent` — migration idempotent | Local |
| T24 | `rag_lr_products` — FTS5 retrieval | Local |
| T25 | `web_link_code_roundtrip` — code generate/validate | Local |
| T26 | `system_chat_clean_output` — clean system response | Local |
| T27 | `faster_whisper_stt` — fw model load (SKIP if absent) | Local |
| T28 | `openclaw_llm_connectivity` — LLM check (SKIP if offline) | Local |
| T29 | `openclaw_stt_routing` — DEVICE_VARIANT routing | Local |
| T30 | `openclaw_ollama_provider` — ollama in _DISPATCH | Local |
| T31 | `web_stt_provider_routing` — web endpoint uses STT_PROVIDER | Local |
| T32 | `pipeline_logger` — PipelineLogger timing stages | Local |
| T33 | `dual_stt_providers` — fallback chain activated | Local |
| T34 | `voice_debug_mode` — VOICE_DEBUG + LLM fallback | Local |
| T35 | `stt_language_routing_fw` — per-language hallucination guard | Local |
| T36 | `stt_fallback_chain` — primary fails → Vosk fallback | Local |
| T37 | `openai_whisper_stt` — OpenAI Whisper API provider present | Local |
| T38 | `tts_multilang` — ru/de TTS + EN fallback | Local |
| T39 | `voice_llm_routing` — ask_llm() used, not TARIS_BIN | Local |
| T40 | `voice_system_mode_routing_guard` — system mode routing | Local |
| T41 | `voice_lang_stt_lang_priority` — STT_LANG over UI lang | Local |
| T42 | `set_lang_default_not_hardcoded_en` — no hardcoded EN default | Local |
| T43 | `voice_system_admin_guard` — admin guard for system voice | Local |
| T44 | `openclaw_gateway_telegram_disabled` — gateway not in Telegram | Local |
| T45 | `taris_bin_configured` — picoclaw binary config | Local |
| T46 | `vosk_fallback_openclaw_default` — vosk fallback off on OpenClaw | Local |
| T47 | `faster_whisper_vad_retry` — VAD retry on empty result | Local |
| T48 | `system_chat_admin_menu_only` — system chat behind admin menu | Local |
| T49 | `stt_fast_speech_accuracy` — fast speech accuracy guard | Local |
| T50 | `voice_chat_config_disclosure` — voice config not in chat | Local |
| T51 | `note_delete_confirm` — note delete requires confirmation | Local |
| T52 | `note_rename_flow` — rename callbacks present | Local |
| T53 | `note_zip_download` — zip download flow | Local |
| T54 | `rag_context_injection` — RAG context injected in prompt | Local |
| T55 | `no_hardcoded_strings` — no hardcoded UI text | Local |

> **T56–T232+** (LLM context, RAG, memory, Postgres, Gemma4, guest/RBAC, KB) — see [`doc/test-suite.md`](../../../doc/test-suite.md) for full registry.

Baseline lives on Pi: `~/.taris/tests/voice/results/baseline.json`  
Re-establish after re-image: `python3 test_voice_regression.py --set-baseline`
