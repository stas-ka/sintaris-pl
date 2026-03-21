---
applyTo: "src/bot_voice.py,src/bot_config.py,src/bot_access.py,src/setup/setup_voice.sh"
---

# Voice Regression Tests — Skill

Run `test_voice_regression.py` on the Pi whenever any of these files change:
`src/bot_voice.py`, `src/bot_config.py`, `src/bot_access.py`, `src/setup/setup_voice.sh`

## Deploy Test Assets (once, when fixtures change)

```bat
pscp -pw "%HOSTPWD%" src\tests\test_voice_regression.py stas@OpenClawPI:/home/stas/.taris/tests/
pscp -pw "%HOSTPWD%" src\tests\voice\ground_truth.json  stas@OpenClawPI:/home/stas/.taris/tests/voice/
pscp -pw "%HOSTPWD%" src\tests\voice\*.ogg              stas@OpenClawPI:/home/stas/.taris/tests/voice/
```

## Run Tests

```bat
rem Standard run
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py"

rem Verbose
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --verbose"

rem Save new baseline (after a confirmed-good deployment)
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --set-baseline"

rem Single test group
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --test tts"
```

## Rules

- `FAIL` → fix before committing.
- `WARN` (>30% slower than baseline) → investigate; if intentional, run `--set-baseline`.
- `SKIP` is OK only for optional features (Whisper, VAD) not installed.
- After fixing a voice bug, paste the summary table in the commit message.
- Baseline lives on the Pi (`tests/voice/results/baseline.json`) — not in git. Re-establish after re-image.

## Tests Covered

| ID | Test | What it checks |
|---|---|---|
| T01 | `model_files_present` | Vosk model, Piper binary, .onnx, .onnx.json, ffmpeg |
| T02 | `piper_json_present` | `.onnx.json` alongside every `.onnx` in use |
| T03 | `tmpfs_model_complete` | Both `.onnx` + `.onnx.json` in `/dev/shm/piper/` when tmpfs enabled |
| T04 | `ogg_decode` | ffmpeg decodes OGG → S16LE PCM; latency |
| T05 | `vad_filter` | WebRTC VAD strips non-speech; retained fraction + latency |
| T06 | `vosk_stt` | Vosk transcribes fixture; WER ≤ 30%; latency |
| T07 | `confidence_strip` | `[?word] → word` regex (7 cases) |
| T08 | `tts_escape` | `_escape_tts()` removes emoji + Markdown (6 cases) |
| T09 | `tts_synthesis` | Piper synthesizes Russian + ffmpeg OGG encode; latency |
| T10 | `whisper_stt` | whisper.cpp WER ≤ 40% (SKIP if absent) |
| T11 | `whisper_hallucination_guard` | Sparse-output guard rejects hallucinations; Vosk fallback |
| T12 | `regression_check` | All timings within 30% of baseline |
| T13 | `i18n_string_coverage` | ru/en/de keys identical, no empty values, 188 keys |
| T14 | `lang_routing` | `_piper_model_path(lang)` + vosk routing for ru/en/de |
| T15 | `de_tts_synthesis` | German Piper TTS (SKIP if absent) |
| T16 | `de_vosk_model` | German Vosk model loads (SKIP if absent) |
| T17 | `bot_name_injection` | `BOT_NAME` in bot_config; `{bot_name}` placeholders work |
| T18 | `profile_resilience` | `_handle_profile()` has try/except around deferred import |
| T19 | `note_edit_append_replace` | Append/Replace callbacks and i18n keys present |
| T20 | `calendar_tts_call_signature` | `_cal_tts_text(chat_id, ev)` 2-arg signature |
| T21 | `calendar_console_classifier` | Console uses JSON intent classifier, not general LLM |
