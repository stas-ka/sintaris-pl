---
mode: agent
description: Run the voice regression test suite (T01–T21) on the Raspberry Pi and report results.
---

# Run Voice Regression Tests

Run the full voice regression test suite on the Pi. This covers T01–T21 (model files, STT, TTS, VAD, i18n, calendar, notes, and profile resilience checks).

## Standard run
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py"
```

## Verbose run (prints per-test detail)
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --verbose"
```

## Run a single test group (e.g. only TTS)
```bat
plink -pw "%HOSTPWD%" -batch stas@OpenClawPI "python3 /home/stas/.taris/tests/test_voice_regression.py --test tts"
```

## Pass/Fail rules

| Result | Action |
|--------|--------|
| `PASS` | All good — no action needed. |
| `FAIL` | Fix the issue before committing. Do NOT skip. |
| `WARN` | Performance regression >30% vs baseline. Investigate. If intentional, run `--set-baseline`. |
| `SKIP` | Acceptable only for optional components (Whisper, VAD) that are not installed. |

## After fixing a voice bug
1. Re-run the tests.
2. Paste the summary table into the commit message.
3. If timing changed intentionally: `plink ... "python3 ... --set-baseline"`

## Tests covered (T01–T21)

| ID | Test |
|----|------|
| T01 | `model_files_present` — Vosk, Piper, ffmpeg binaries present |
| T02 | `piper_json_present` — .onnx.json alongside every .onnx |
| T03 | `tmpfs_model_complete` — .onnx + .onnx.json in /dev/shm/piper/ |
| T04 | `ogg_decode` — ffmpeg decodes OGG → S16LE PCM |
| T05 | `vad_filter` — WebRTC VAD strips non-speech frames |
| T06 | `vosk_stt` — Vosk transcribes audio; WER ≤ 30% |
| T07 | `confidence_strip` — `[?word] → word` regex |
| T08 | `tts_escape` — `_escape_tts()` removes emoji + Markdown |
| T09 | `tts_synthesis` — Piper synthesizes Russian + ffmpeg OGG encode |
| T10 | `whisper_stt` — whisper.cpp WER ≤ 40% (SKIP if absent) |
| T11 | `whisper_hallucination_guard` — sparse-output guard + Vosk fallback |
| T12 | `regression_check` — all timings within 30% of baseline |
| T13 | `i18n_string_coverage` — ru/en/de key sets identical, 328 keys, no empties |
| T14 | `lang_routing` — model path routing for ru/en/de |
| T15 | `de_tts_synthesis` — German Piper TTS (SKIP if absent) |
| T16 | `de_vosk_model` — German Vosk model loads (SKIP if absent) |
| T17 | `bot_name_injection` — BOT_NAME + {bot_name} placeholders work |
| T18 | `profile_resilience` — try/except in _handle_profile() |
| T19 | `note_edit_append_replace` — append/replace flow present |
| T20 | `calendar_tts_call_signature` — _cal_tts_text(chat_id, ev) signature |
| T21 | `calendar_console_classifier` — console uses JSON intent classifier |
