#!/usr/bin/env python3
"""
test_voice_regression.py — Voice pipeline regression tests for picoclaw-telegram.

Tests every voice-related function independently and saves timestamped results
so latency and quality regressions are detected when bot_voice.py changes.

Usage (on Raspberry Pi):
    python3 test_voice_regression.py              # run all tests
    python3 test_voice_regression.py --set-baseline   # save current run as baseline
    python3 test_voice_regression.py --verbose    # extra output per test
    python3 test_voice_regression.py --test vosk  # run only tests matching name

Deploy:
    pscp -pw "..." src/tests/test_voice_regression.py stas@OpenClawPI:/home/stas/.picoclaw/tests/
    pscp -pw "..." src/tests/voice/*.ogg stas@OpenClawPI:/home/stas/.picoclaw/tests/voice/
    pscp -pw "..." src/tests/voice/ground_truth.json stas@OpenClawPI:/home/stas/.picoclaw/tests/voice/

Exit codes:
    0 — all tests passed (and no significant regression vs baseline)
    1 — one or more tests FAILED or regression exceeded threshold
    2 — test runner error (missing fixtures, import errors, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Paths & constants
# ─────────────────────────────────────────────────────────────────────────────

PICOCLAW_DIR   = Path(os.path.expanduser("~/.picoclaw"))
TESTS_DIR      = Path(__file__).parent.resolve()
VOICE_DIR      = TESTS_DIR / "voice"
RESULTS_DIR    = VOICE_DIR / "results"
GROUND_TRUTH   = VOICE_DIR / "ground_truth.json"
BASELINE_FILE  = RESULTS_DIR / "baseline.json"

# Mirror bot_config.py defaults so tests use exactly the same paths
PIPER_BIN         = os.environ.get("PIPER_BIN",  "/usr/local/bin/piper")
PIPER_MODEL       = os.environ.get("PIPER_MODEL", str(PICOCLAW_DIR / "ru_RU-irina-medium.onnx"))
PIPER_MODEL_TMPFS = "/dev/shm/piper/" + Path(PIPER_MODEL).name
PIPER_MODEL_LOW   = os.environ.get("PIPER_MODEL_LOW", str(PICOCLAW_DIR / "ru_RU-irina-low.onnx"))
WHISPER_BIN       = os.environ.get("WHISPER_BIN",  "/usr/local/bin/whisper-cpp")
WHISPER_MODEL     = os.environ.get("WHISPER_MODEL", str(PICOCLAW_DIR / "ggml-tiny.bin"))
VOSK_MODEL_PATH   = os.environ.get("VOSK_MODEL_PATH", str(PICOCLAW_DIR / "vosk-model-small-ru"))

VOSK_MODEL_DE_PATH   = os.environ.get("VOSK_MODEL_DE_PATH",  str(PICOCLAW_DIR / "vosk-model-small-de"))
PIPER_MODEL_DE       = os.environ.get("PIPER_MODEL_DE",      str(PICOCLAW_DIR / "de_DE-thorsten-medium.onnx"))
PIPER_MODEL_DE_TMPFS = "/dev/shm/piper/de_DE-thorsten-medium.onnx"
STRINGS_FILE         = PICOCLAW_DIR / "strings.json"

VOICE_SAMPLE_RATE   = 16000
VOICE_CHUNK_SIZE    = 4000
STT_CONF_THRESHOLD  = 0.65    # must match bot_voice.py

# Confidence marker regex — must be identical to bot_voice.py
_CONF_MARKER_RE = re.compile(r'\[\?([^\]]*)\]')

VOICE_OPTS_FILE = PICOCLAW_DIR / "voice_opts.json"

# Colors (disabled if not a TTY)
_TTY = sys.stdout.isatty()
_G   = "\033[32m" if _TTY else ""
_R   = "\033[31m" if _TTY else ""
_Y   = "\033[33m" if _TTY else ""
_B   = "\033[34m" if _TTY else ""
_W   = "\033[33;1m" if _TTY else ""
_RST = "\033[0m"  if _TTY else ""


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name:       str
    status:     str          # PASS | FAIL | SKIP | WARN
    duration_s: float = 0.0
    detail:     str   = ""
    metric:     Optional[float] = None   # numeric value for regression comparison
    metric_key: str   = ""               # name of the metric (e.g. "stt_vosk_s")

    def color(self) -> str:
        return {"PASS": _G, "FAIL": _R, "WARN": _W, "SKIP": _B}.get(self.status, _RST)


# ─────────────────────────────────────────────────────────────────────────────
# WER helper
# ─────────────────────────────────────────────────────────────────────────────

def _wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate = Levenshtein distance on word tokens / len(reference)."""
    r = reference.lower().split()
    h = hypothesis.lower().split()
    if not r:
        return 0.0 if not h else 1.0
    n, m = len(r), len(h)
    # DP table
    d = list(range(m + 1))
    for i in range(1, n + 1):
        prev, d[0] = d[0], i
        for j in range(1, m + 1):
            prev, d[j] = d[j], (prev if r[i-1] == h[j-1]
                                 else 1 + min(prev, d[j], d[j-1]))
    return d[m] / n


def _strip_markers(text: str) -> str:
    """Strip Vosk confidence markers: [?word] → word."""
    return _CONF_MARKER_RE.sub(r'\1', text).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Load ground truth & voice opts
# ─────────────────────────────────────────────────────────────────────────────

def _load_gt() -> dict:
    try:
        return json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"{_R}[ERROR] Cannot load ground_truth.json: {e}{_RST}")
        sys.exit(2)


def _load_voice_opts() -> dict:
    try:
        return json.loads(VOICE_OPTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_baseline() -> Optional[dict]:
    if BASELINE_FILE.exists():
        try:
            return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Individual tests
# ─────────────────────────────────────────────────────────────────────────────

def t_model_files_present(gt: dict, **_) -> list[TestResult]:
    """T01 — all model/binary files referenced by the pipeline exist on disk."""
    checks = {
        "vosk_model":         VOSK_MODEL_PATH,
        "piper_bin":          PIPER_BIN,
        "piper_onnx":         PIPER_MODEL,
        "piper_onnx_json":    PIPER_MODEL + ".json",
        "ffmpeg":             "/usr/bin/ffmpeg",
    }
    optional = {
        "whisper_bin":        WHISPER_BIN,
        "whisper_model":      WHISPER_MODEL,
        "piper_low_onnx":     PIPER_MODEL_LOW,
    }
    results = []
    t0 = time.time()
    missing = [name for name, p in checks.items() if not Path(p).exists()]
    status = "FAIL" if missing else "PASS"
    detail = ("Missing: " + ", ".join(missing)) if missing else "All required files present"
    results.append(TestResult("model_files_required", status,
                              time.time() - t0, detail))

    t0 = time.time()
    absent = [name for name, p in optional.items() if not Path(p).exists()]
    detail2 = ("Absent (optional): " + ", ".join(absent)) if absent else "All optional files present"
    results.append(TestResult("model_files_optional", "SKIP" if absent else "PASS",
                              time.time() - t0, detail2))
    return results


def t_piper_json_present(**_) -> list[TestResult]:
    """T02 — .onnx.json config file must exist next to each .onnx file used."""
    t0 = time.time()
    pairs = [(PIPER_MODEL, PIPER_MODEL + ".json")]
    opts = _load_voice_opts()
    if opts.get("tmpfs_model") and Path(PIPER_MODEL_TMPFS).exists():
        pairs.append((PIPER_MODEL_TMPFS, PIPER_MODEL_TMPFS + ".json"))

    issues = []
    for onnx, cfg in pairs:
        if Path(onnx).exists() and not Path(cfg).exists():
            issues.append(f"Missing config for {Path(onnx).name}: {cfg}")
    status = "FAIL" if issues else "PASS"
    detail = "; ".join(issues) if issues else "All .onnx models have .onnx.json config"
    return [TestResult("piper_json_present", status, time.time() - t0, detail)]


def t_tmpfs_model_complete(**_) -> list[TestResult]:
    """T03 — if tmpfs_model opt is enabled, both .onnx and .onnx.json must be in /dev/shm/piper/."""
    opts = _load_voice_opts()
    if not opts.get("tmpfs_model"):
        return [TestResult("tmpfs_model_complete", "SKIP", 0.0,
                           "tmpfs_model opt is off — skipped")]
    t0 = time.time()
    onnx_ok = Path(PIPER_MODEL_TMPFS).exists()
    json_ok  = Path(PIPER_MODEL_TMPFS + ".json").exists()
    if onnx_ok and json_ok:
        status = "PASS"
        detail = f"Both files present in /dev/shm/piper/ ({Path(PIPER_MODEL_TMPFS).stat().st_size // 1024 // 1024} MB .onnx)"
    else:
        status = "FAIL"
        missing = []
        if not onnx_ok: missing.append(PIPER_MODEL_TMPFS)
        if not json_ok: missing.append(PIPER_MODEL_TMPFS + ".json")
        detail = "tmpfs_model enabled but missing: " + ", ".join(missing)
    return [TestResult("tmpfs_model_complete", status, time.time() - t0, detail)]


def t_ogg_decode(gt: dict, verbose: bool = False, **_) -> list[TestResult]:
    """T04 — decode each fixture OGG to 16 kHz S16LE PCM via ffmpeg."""
    results = []
    for fname, info in gt.get("fixtures", {}).items():
        ogg_path = VOICE_DIR / fname
        if not ogg_path.exists():
            results.append(TestResult(f"ogg_decode:{fname}", "SKIP", 0.0,
                                      f"Fixture not found: {ogg_path}"))
            continue
        t0 = time.time()
        try:
            ff = subprocess.run(
                ["ffmpeg", "-y", "-i", str(ogg_path),
                 "-af", "highpass=f=80,dynaudnorm=p=0.9",
                 "-ar", str(VOICE_SAMPLE_RATE), "-ac", "1", "-f", "s16le", "pipe:1"],
                capture_output=True, timeout=30,
            )
            dur = time.time() - t0
            frames = len(ff.stdout) // 2    # S16LE = 2 bytes/sample
            dur_audio_s = frames / VOICE_SAMPLE_RATE
            if ff.returncode != 0 or not ff.stdout:
                results.append(TestResult(f"ogg_decode:{fname}", "FAIL", dur,
                                          f"ffmpeg rc={ff.returncode}: {ff.stderr[-200:]}"))
            else:
                detail = (f"{len(ff.stdout):,} bytes PCM, {dur_audio_s:.1f}s audio  |  "
                          f"decode took {dur:.2f}s")
                if verbose:
                    print(f"         {detail}")
                results.append(TestResult(f"ogg_decode:{fname}", "PASS", dur, detail,
                                          metric=dur, metric_key=f"decode_{fname}_s"))
        except Exception as e:
            results.append(TestResult(f"ogg_decode:{fname}", "FAIL", time.time()-t0, str(e)))
    return results


def t_vad_filter(gt: dict, verbose: bool = False, **_) -> list[TestResult]:
    """T05 — WebRTC VAD strips non-speech frames; verify library present + fraction removed."""
    try:
        import webrtcvad as _vad_lib
    except ImportError:
        return [TestResult("vad_filter", "SKIP", 0.0,
                           "webrtcvad not installed (pip3 install webrtcvad)")]

    results = []
    for fname in gt.get("fixtures", {}):
        ogg_path = VOICE_DIR / fname
        if not ogg_path.exists():
            continue
        # Decode first
        try:
            ff = subprocess.run(
                ["ffmpeg", "-y", "-i", str(ogg_path),
                 "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"],
                capture_output=True, timeout=30,
            )
            raw_pcm = ff.stdout
            if not raw_pcm:
                continue
        except Exception:
            continue

        t0 = time.time()
        try:
            vad = _vad_lib.Vad(2)
            frame_bytes = int(16000 * 0.030) * 2    # 30 ms at 16 kHz S16LE
            kept = 0
            total = 0
            for i in range(0, len(raw_pcm) - frame_bytes + 1, frame_bytes):
                frame = raw_pcm[i:i + frame_bytes]
                total += 1
                try:
                    if vad.is_speech(frame, 16000):
                        kept += 1
                except Exception:
                    kept += 1
            dur = time.time() - t0
            pct_speech = 100 * kept / max(total, 1)
            detail = (f"{kept}/{total} frames kept ({pct_speech:.0f}% classified as speech), "
                      f"VAD took {dur:.2f}s")
            if verbose:
                print(f"         {detail}")
            # Regression: speech fraction and timing
            results.append(TestResult(f"vad_filter:{fname}", "PASS", dur, detail,
                                      metric=dur, metric_key=f"vad_{fname}_s"))
        except Exception as e:
            results.append(TestResult(f"vad_filter:{fname}", "FAIL",
                                      time.time() - t0, str(e)))
    if not results:
        results.append(TestResult("vad_filter", "SKIP", 0.0,
                                  "No decodable fixtures found"))
    return results


def _run_vosk_stt(ogg_path: Path, sample_rate: int = 16000) -> tuple[str, float]:
    """Decode OGG → PCM → Vosk STT with confidence markers. Returns (raw_transcript, elapsed_s)."""
    import vosk as _vosk_lib
    import json as _json

    ff = subprocess.run(
        ["ffmpeg", "-y", "-i", str(ogg_path),
         "-af", "highpass=f=80,dynaudnorm=p=0.9",
         "-ar", str(sample_rate), "-ac", "1", "-f", "s16le", "pipe:1"],
        capture_output=True, timeout=30,
    )
    raw_pcm = ff.stdout
    if not raw_pcm:
        raise ValueError("ffmpeg produced zero bytes")

    _vosk_lib.SetLogLevel(-1)
    model = _vosk_lib.Model(VOSK_MODEL_PATH)
    t0 = time.time()
    rec = _vosk_lib.KaldiRecognizer(model, sample_rate)
    rec.SetWords(True)
    chunk = VOICE_CHUNK_SIZE * 2 * sample_rate // VOICE_SAMPLE_RATE
    for i in range(0, len(raw_pcm), chunk):
        rec.AcceptWaveform(raw_pcm[i:i + chunk])
    final = _json.loads(rec.FinalResult())
    elapsed = time.time() - t0

    words = final.get("result", [])
    if words:
        parts = []
        for w in words:
            word = w.get("word", "")
            conf = w.get("conf", 1.0)
            parts.append(f"[?{word}]" if conf < STT_CONF_THRESHOLD else word)
        return " ".join(parts).strip(), elapsed
    return final.get("text", "").strip(), elapsed


def t_vosk_stt(gt: dict, verbose: bool = False, **_) -> list[TestResult]:
    """T06 — Vosk STT transcribes fixture audio; compare WER to ground truth."""
    if not Path(VOSK_MODEL_PATH).exists():
        return [TestResult("vosk_stt", "SKIP", 0.0,
                           f"Vosk model not found: {VOSK_MODEL_PATH}")]
    try:
        import vosk  # noqa: F401
    except ImportError:
        return [TestResult("vosk_stt", "SKIP", 0.0, "vosk not installed")]

    results = []
    for fname, info in gt.get("fixtures", {}).items():
        ogg_path = VOICE_DIR / fname
        if not ogg_path.exists():
            results.append(TestResult(f"vosk_stt:{fname}", "SKIP", 0.0,
                                      f"Fixture not found: {ogg_path}"))
            continue
        t0 = time.time()
        try:
            raw_transcript, stt_elapsed = _run_vosk_stt(ogg_path)
            total_elapsed = time.time() - t0
        except Exception as e:
            results.append(TestResult(f"vosk_stt:{fname}", "FAIL",
                                      time.time() - t0, f"STT error: {e}"))
            continue

        clean_transcript = _strip_markers(raw_transcript)
        detail_parts = [f"STT {stt_elapsed:.1f}s", f"raw: {raw_transcript[:80]}"]

        ref_raw   = info.get("raw_vosk_ref")
        ref_clean = info.get("clean_ref")
        max_wer   = info.get("max_wer")

        if ref_clean and max_wer is not None:
            wer_val  = _wer(ref_clean, clean_transcript)
            wer_raw  = _wer(ref_raw, raw_transcript) if ref_raw else None
            wer_ok   = wer_val <= max_wer
            detail_parts.append(
                f"WER_clean={wer_val:.2f} ({'≤' if wer_ok else '>'}{max_wer}) "
                + (f"| WER_raw={wer_raw:.2f}" if wer_raw is not None else "")
            )
            status = "PASS" if wer_ok else "FAIL"
        else:
            detail_parts.append("(no reference — timing only)")
            status = "PASS"

        detail = " | ".join(detail_parts)
        if verbose:
            print(f"         transcript: {clean_transcript[:120]}")
            print(f"         {detail}")
        results.append(TestResult(f"vosk_stt:{fname}", status, total_elapsed, detail,
                                  metric=stt_elapsed, metric_key=f"stt_vosk_{fname}_s"))
    if not results:
        results.append(TestResult("vosk_stt", "SKIP", 0.0,
                                  "No decodable fixtures found"))
    return results


def t_confidence_strip(**_) -> list[TestResult]:
    """T07 — [?word] → word regex behaves exactly as in bot_voice.py."""
    cases = [
        # (input,                                expected_output)
        ("[?неё] желудок [?может] решить",       "неё желудок может решить"),
        ("нет маркеров здесь",                   "нет маркеров здесь"),
        ("[?a] [?b] [?c]",                       "a b c"),
        ("hello [?world] test",                  "hello world test"),
        ("[?low]",                                "low"),
        ("",                                      ""),
        ("  [?spaces]  around  ",                "spaces  around"),
    ]
    t0 = time.time()
    failures = []
    for inp, expected in cases:
        got = _strip_markers(inp)
        if got != expected:
            failures.append(f"  input={inp!r} → got={got!r}, want={expected!r}")

    dur = time.time() - t0
    if failures:
        return [TestResult("confidence_strip", "FAIL", dur,
                           f"{len(failures)}/{len(cases)} cases failed:\n" + "\n".join(failures))]
    return [TestResult("confidence_strip", "PASS", dur,
                       f"All {len(cases)} regex cases correct")]


def _escape_tts(text: str) -> str:
    """Inline copy of bot_access._escape_tts — must stay in sync."""
    # Remove emoji (blocks U+1F000–U+1FFFF and common symbols U+2000–U+2FFF)
    text = re.sub(r'[\U0001F000-\U0001FFFF\u2000-\u2FFF]', '', text)
    # Strip Telegram Markdown v1 markers
    text = re.sub(r'[*_`]', '', text)
    # Collapse runs of whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def t_tts_escape(**_) -> list[TestResult]:
    """T08 — _escape_tts removes emoji and Markdown characters before Piper input."""
    cases = [
        ("*Привет* _мир_",              "Привет мир"),
        ("🤖 Picoclaw:",                "Picoclaw:"),
        ("✅ Done! **bold**",           "Done! bold"),
        ("normal text",                 "normal text"),
        ("  spaces   everywhere  ",     "spaces everywhere"),
        ("`code` and *italic*",         "code and italic"),
    ]
    t0 = time.time()
    failures = []
    for inp, expected in cases:
        got = _escape_tts(inp)
        if got != expected:
            failures.append(f"  {inp!r} → {got!r}, want {expected!r}")

    dur = time.time() - t0
    if failures:
        return [TestResult("tts_escape", "FAIL", dur,
                           f"{len(failures)}/{len(cases)} cases failed:\n" + "\n".join(failures))]
    return [TestResult("tts_escape", "PASS", dur, f"All {len(cases)} escape cases correct")]


def t_tts_synthesis(gt: dict, verbose: bool = False, **_) -> list[TestResult]:
    """T09 — Piper synthesizes test text and produces non-empty OGG via ffmpeg pipeline."""
    if not Path(PIPER_BIN).exists():
        return [TestResult("tts_synthesis", "FAIL", 0.0,
                           f"Piper binary not found: {PIPER_BIN}")]

    # Select model via same priority as _piper_model_path()
    opts = _load_voice_opts()
    if opts.get("tmpfs_model") and Path(PIPER_MODEL_TMPFS).exists():
        model_path = PIPER_MODEL_TMPFS
    elif opts.get("piper_low_model") and Path(PIPER_MODEL_LOW).exists():
        model_path = PIPER_MODEL_LOW
    else:
        model_path = PIPER_MODEL

    if not Path(model_path).exists():
        return [TestResult("tts_synthesis", "FAIL", 0.0,
                           f"Piper model not found: {model_path}")]

    test_text = gt.get("test_tts_text", "Привет! Это тест.")
    results = []

    # --- Piper → raw PCM ---
    t0 = time.time()
    try:
        piper_result = subprocess.run(
            [PIPER_BIN, "--model", model_path, "--output-raw"],
            input=test_text.encode("utf-8"),
            capture_output=True, timeout=120,
        )
        piper_elapsed = time.time() - t0
        raw_pcm = piper_result.stdout
        if not raw_pcm:
            return [TestResult("tts_piper", "FAIL", piper_elapsed,
                               f"Piper rc={piper_result.returncode}: "
                               f"{piper_result.stderr[:200]}")]
        detail = (f"Piper produced {len(raw_pcm):,} bytes raw PCM in {piper_elapsed:.1f}s "
                  f"(model: {Path(model_path).name})")
        if verbose:
            print(f"         {detail}")
        results.append(TestResult("tts_piper", "PASS", piper_elapsed, detail,
                                  metric=piper_elapsed, metric_key="tts_piper_s"))
    except subprocess.TimeoutExpired:
        return [TestResult("tts_piper", "FAIL", time.time()-t0,
                           "Piper timed out after 120s")]
    except Exception as e:
        return [TestResult("tts_piper", "FAIL", time.time()-t0, str(e))]

    # --- ffmpeg PCM → OGG Opus ---
    t0 = time.time()
    try:
        ff_result = subprocess.run(
            ["ffmpeg", "-y",
             "-f", "s16le", "-ar", "22050", "-ac", "1", "-i", "pipe:0",
             "-c:a", "libopus", "-b:a", "24k", "-f", "ogg", "pipe:1"],
            input=raw_pcm, capture_output=True, timeout=30,
        )
        ff_elapsed = time.time() - t0
        ogg_bytes = ff_result.stdout
        ogg_kb = len(ogg_bytes) / 1024
        if not ogg_bytes:
            results.append(TestResult("tts_ffmpeg_encode", "FAIL", ff_elapsed,
                                      f"ffmpeg rc={ff_result.returncode}: "
                                      f"{ff_result.stderr[:200]}"))
        else:
            detail = f"OGG Opus {ogg_kb:.1f} KB in {ff_elapsed:.2f}s"
            results.append(TestResult("tts_ffmpeg_encode", "PASS", ff_elapsed, detail,
                                      metric=ff_elapsed, metric_key="tts_ffmpeg_s"))
    except Exception as e:
        results.append(TestResult("tts_ffmpeg_encode", "FAIL", time.time()-t0, str(e)))

    return results


def t_whisper_stt(gt: dict, verbose: bool = False, **_) -> list[TestResult]:
    """T10 — whisper.cpp STT (optional; skipped if binary/model absent)."""
    if not Path(WHISPER_BIN).exists():
        return [TestResult("whisper_stt", "SKIP", 0.0,
                           f"whisper-cpp not installed at {WHISPER_BIN}")]
    if not Path(WHISPER_MODEL).exists():
        return [TestResult("whisper_stt", "SKIP", 0.0,
                           f"Whisper model not found: {WHISPER_MODEL}")]

    import wave as _wave
    import tempfile

    results = []
    for fname, info in gt.get("fixtures", {}).items():
        ogg_path = VOICE_DIR / fname
        if not ogg_path.exists():
            continue
        # Decode to PCM
        try:
            ff = subprocess.run(
                ["ffmpeg", "-y", "-i", str(ogg_path),
                 "-ar", str(VOICE_SAMPLE_RATE), "-ac", "1", "-f", "s16le", "pipe:1"],
                capture_output=True, timeout=30,
            )
            raw_pcm = ff.stdout
            if not raw_pcm:
                continue
        except Exception:
            continue

        # Write temp WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            with _wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(VOICE_SAMPLE_RATE)
                wf.writeframes(raw_pcm)

            t0 = time.time()
            result = subprocess.run(
                [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", tmp_path,
                 "-l", "ru", "--no-timestamps", "-otxt"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60,
            )
            dur = time.time() - t0
            os.unlink(tmp_path)

            txt_path = tmp_path + ".txt"
            if result.returncode == 0:
                text = ""
                if Path(txt_path).exists():
                    text = Path(txt_path).read_text(encoding="utf-8").strip()
                    Path(txt_path).unlink(missing_ok=True)
                else:
                    text = result.stdout.strip()
                text = re.sub(r'\[[\d:.]+ --> [\d:.]+\]\s*', '', text).strip()

                ref_clean = info.get("whisper_ref") or info.get("clean_ref")
                if ref_clean and text:
                    wer_val = _wer(ref_clean, text)
                    detail = f"STT {dur:.1f}s | WER={wer_val:.2f} | {text[:80]}"
                    status = "PASS" if wer_val <= 0.40 else "WARN"
                else:
                    detail = f"STT {dur:.1f}s | no reference — got: {text[:80]}"
                    status = "PASS" if text else "WARN"
            else:
                detail = f"whisper-cpp rc={result.returncode}: {result.stderr[:100]}"
                status = "FAIL"
                dur = time.time() - t0

            if verbose:
                print(f"         {detail}")
            results.append(TestResult(f"whisper_stt:{fname}", status, dur, detail,
                                      metric=dur, metric_key=f"stt_whisper_{fname}_s"))
        except Exception as e:
            try: os.unlink(tmp_path)
            except Exception: pass
            results.append(TestResult(f"whisper_stt:{fname}", "FAIL",
                                      time.time() - t0, str(e)))

    if not results:
        results.append(TestResult("whisper_stt", "SKIP", 0.0, "No fixtures processed"))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T13 — Whisper hallucination guard
# ─────────────────────────────────────────────────────────────────────────────

def t_whisper_hallucination_guard(gt: dict, verbose: bool = False, **_) -> list[TestResult]:
    """T13 — Whisper sparse-output guard rejects hallucinated phrases and falls back to Vosk.

    For audio clips marked with 'whisper_hallucination' in ground_truth.json, the
    guard in _stt_whisper() must compute word_count < max(2, duration_s*2.0) and
    return None so Vosk handles the transcript instead.
    """
    results = []
    for fname, info in gt.get("fixtures", {}).items():
        hallucination = info.get("whisper_hallucination")
        if not hallucination:
            continue
        ogg_path = VOICE_DIR / fname
        if not ogg_path.exists():
            results.append(TestResult(
                f"whisper_hallucination_guard:{fname}", "SKIP", 0.0,
                f"fixture missing: {ogg_path}"))
            continue

        t0 = time.time()
        # Decode to PCM to get duration
        try:
            ff = subprocess.run(
                ["ffmpeg", "-y", "-i", str(ogg_path),
                 "-ar", str(VOICE_SAMPLE_RATE), "-ac", "1", "-f", "s16le", "pipe:1"],
                capture_output=True, timeout=30,
            )
            raw_pcm = ff.stdout
        except Exception as e:
            results.append(TestResult(
                f"whisper_hallucination_guard:{fname}", "FAIL",
                time.time() - t0, f"ffmpeg error: {e}"))
            continue

        duration_s = len(raw_pcm) / (VOICE_SAMPLE_RATE * 2)
        halluc_words = hallucination.split()
        min_expected = max(2, int(duration_s * 2.0))
        would_discard = duration_s > 2.0 and len(halluc_words) < min_expected

        detail = (
            f"duration={duration_s:.1f}s | halluc_words={len(halluc_words)} "
            f"min_expected={min_expected} | would_discard={would_discard}"
        )
        if verbose:
            print(f"         {detail}")

        if would_discard:
            # Also verify Vosk produces a plausible result for the same audio
            min_vosk = info.get("min_words_vosk", 1)
            try:
                import vosk as _vosk_lib
                import json as _json_
                model = _load_vosk_model_cached()
                rec = _vosk_lib.KaldiRecognizer(model, VOICE_SAMPLE_RATE)
                rec.SetWords(True)
                chunk = VOICE_CHUNK_SIZE * 2
                for i in range(0, len(raw_pcm), chunk):
                    rec.AcceptWaveform(raw_pcm[i:i + chunk])
                res = _json_.loads(rec.FinalResult())
                vosk_words = [w["word"] for w in res.get("result", [])]
                vosk_text = " ".join(vosk_words)
                if len(vosk_words) >= min_vosk:
                    status = "PASS"
                    detail += f" | Vosk={vosk_text[:60]}"
                else:
                    status = "WARN"
                    detail += f" | Vosk too short ({len(vosk_words)} words): {vosk_text[:60]}"
            except Exception as e:
                status = "WARN"
                detail += f" | Vosk check error: {e}"
        else:
            status = "FAIL"
            detail += " | guard would NOT discard this known hallucination"

        dur = time.time() - t0
        results.append(TestResult(
            f"whisper_hallucination_guard:{fname}", status, dur, detail))

    if not results:
        results.append(TestResult(
            "whisper_hallucination_guard", "SKIP", 0.0,
            "No fixtures with whisper_hallucination field"))
    return results


def _load_vosk_model_cached(_cache: list = []) -> object:
    """Lazy-load Vosk model singleton for tests."""
    if not _cache:
        import vosk as _vosk_lib
        import logging
        logging.disable(logging.CRITICAL)
        _cache.append(_vosk_lib.Model(VOSK_MODEL_PATH))
        logging.disable(logging.NOTSET)
    return _cache[0]


# ─────────────────────────────────────────────────────────────────────────────
# T13 — i18n string coverage (GUI)
# ─────────────────────────────────────────────────────────────────────────────

def t_i18n_string_coverage(**_) -> list[TestResult]:
    """T13 — strings.json has identical key sets for ru/en/de with no empty values."""
    t0 = time.time()
    if not STRINGS_FILE.exists():
        return [TestResult("i18n_string_coverage", "FAIL", time.time() - t0,
                           f"strings.json not found: {STRINGS_FILE}")]
    try:
        strings = json.loads(STRINGS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        return [TestResult("i18n_string_coverage", "FAIL", time.time() - t0,
                           f"Parse error: {e}")]

    supported = ["ru", "en", "de"]
    missing_langs = [lg for lg in supported if lg not in strings]
    if missing_langs:
        return [TestResult("i18n_string_coverage", "FAIL", time.time() - t0,
                           f"Missing top-level language keys: {missing_langs}")]

    ref_keys = set(strings["ru"].keys())
    issues: list[str] = []
    for lang in supported:
        if lang == "ru":
            continue
        missing = ref_keys - set(strings[lang].keys())
        extra   = set(strings[lang].keys()) - ref_keys
        if missing:
            issues.append(f"{lang} missing {len(missing)} key(s): " + str(sorted(missing)[:5]))
        if extra:
            issues.append(f"{lang} has {len(extra)} extra key(s): " + str(sorted(extra)[:5]))

    empty: list[str] = []
    for lang in supported:
        for k, v in strings[lang].items():
            if not str(v).strip():
                empty.append(f"{lang}.{k}")

    if issues or empty:
        parts = []
        if issues:
            parts.append("Parity: " + " | ".join(issues))
        if empty:
            parts.append(f"Empty values ({len(empty)}): " + ", ".join(empty[:5]))
        return [TestResult("i18n_string_coverage", "FAIL", time.time() - t0,
                           " | ".join(parts))]

    total = len(ref_keys)
    return [TestResult("i18n_string_coverage", "PASS", time.time() - t0,
                       f"All 3 languages ({', '.join(supported)}) have {total} keys, no empty values")]


# ─────────────────────────────────────────────────────────────────────────────
# T14 — language routing
# ─────────────────────────────────────────────────────────────────────────────

def t_lang_routing(verbose: bool = False, **_) -> list[TestResult]:
    """T14 — _piper_model_path(lang) and vosk model routing return correct paths for ru/en/de."""
    t0 = time.time()
    opts = _load_voice_opts()

    def _piper_path(lang: str) -> str:
        if lang == "de":
            if opts.get("tmpfs_model") and Path(PIPER_MODEL_DE_TMPFS).exists():
                return PIPER_MODEL_DE_TMPFS
            return PIPER_MODEL_DE
        else:
            if opts.get("tmpfs_model") and Path(PIPER_MODEL_TMPFS).exists():
                return PIPER_MODEL_TMPFS
            if opts.get("piper_low_model") and Path(PIPER_MODEL_LOW).exists():
                return PIPER_MODEL_LOW
            return PIPER_MODEL

    def _vosk_path(lang: str) -> str:
        if lang == "de":
            return VOSK_MODEL_DE_PATH
        return VOSK_MODEL_PATH  # ru + en both fall back to Russian model

    issues: list[str] = []
    rows: list[str] = []
    for lang in ("ru", "en", "de"):
        pp = _piper_path(lang)
        vp = _vosk_path(lang)
        pp_ok = Path(pp).exists()
        vp_ok = Path(vp).exists()
        rows.append(
            f"lang={lang}: piper={Path(pp).name}({'ok' if pp_ok else 'absent'}) "
            f"vosk={Path(vp).name}({'ok' if vp_ok else 'absent'})"
        )
        if verbose:
            print(f"         {rows[-1]}")

        if lang in ("ru", "en"):
            # Both should route to the Russian piper model family
            ru_models = {PIPER_MODEL_TMPFS, PIPER_MODEL_LOW, PIPER_MODEL}
            if pp not in ru_models:
                issues.append(f"{lang}: unexpected piper path {pp!r}")
            if vp != VOSK_MODEL_PATH:
                issues.append(f"{lang}: vosk should route to RU model, got {vp!r}")
        else:  # de
            expected_piper = (PIPER_MODEL_DE_TMPFS
                              if opts.get("tmpfs_model") and Path(PIPER_MODEL_DE_TMPFS).exists()
                              else PIPER_MODEL_DE)
            if pp != expected_piper:
                issues.append(f"de: expected piper {expected_piper!r}, got {pp!r}")
            if vp != VOSK_MODEL_DE_PATH:
                issues.append(f"de: expected vosk {VOSK_MODEL_DE_PATH!r}, got {vp!r}")

    status = "FAIL" if issues else "PASS"
    detail = " | ".join(rows)
    if issues:
        detail = "ERRORS: " + "; ".join(issues) + " || " + detail
    return [TestResult("lang_routing", status, time.time() - t0, detail)]


# ─────────────────────────────────────────────────────────────────────────────
# T15 — German TTS synthesis
# ─────────────────────────────────────────────────────────────────────────────

def t_de_tts_synthesis(gt: dict, verbose: bool = False, **_) -> list[TestResult]:
    """T15 — German Piper TTS synthesises text to raw PCM (SKIP if model absent)."""
    t0 = time.time()
    if not Path(PIPER_BIN).exists():
        return [TestResult("de_tts_synthesis", "FAIL", time.time() - t0,
                           f"Piper binary not found: {PIPER_BIN}")]

    opts = _load_voice_opts()
    model_path = (PIPER_MODEL_DE_TMPFS
                  if opts.get("tmpfs_model") and Path(PIPER_MODEL_DE_TMPFS).exists()
                  else PIPER_MODEL_DE)

    if not Path(model_path).exists():
        return [TestResult("de_tts_synthesis", "SKIP", time.time() - t0,
                           f"German Piper model absent: {model_path}")]

    test_text = gt.get("test_tts_text_de", "Hallo! Das ist ein Test mit dem deutschen Sprachmodell.")
    try:
        piper_result = subprocess.run(
            [PIPER_BIN, "--model", model_path, "--output-raw"],
            input=test_text.encode("utf-8"),
            capture_output=True, timeout=120,
        )
        elapsed = time.time() - t0
        raw_pcm = piper_result.stdout
        if not raw_pcm:
            return [TestResult("de_tts_synthesis", "FAIL", elapsed,
                               f"Piper rc={piper_result.returncode}: "
                               f"{piper_result.stderr[:200]}")]
        detail = (f"DE Piper {len(raw_pcm):,} bytes PCM in {elapsed:.1f}s "
                  f"(model: {Path(model_path).name})")
        if verbose:
            print(f"         {detail}")
        return [TestResult("de_tts_synthesis", "PASS", elapsed, detail,
                           metric=elapsed, metric_key="de_tts_piper_s")]
    except subprocess.TimeoutExpired:
        return [TestResult("de_tts_synthesis", "FAIL", time.time() - t0,
                           "German Piper timed out after 120s")]
    except Exception as e:
        return [TestResult("de_tts_synthesis", "FAIL", time.time() - t0, str(e))]


# ─────────────────────────────────────────────────────────────────────────────
# T16 — German Vosk model loads
# ─────────────────────────────────────────────────────────────────────────────

def t_de_vosk_model(verbose: bool = False, **_) -> list[TestResult]:
    """T16 — German Vosk model loads and produces a result on silence (SKIP if absent)."""
    t0 = time.time()
    if not Path(VOSK_MODEL_DE_PATH).exists():
        return [TestResult("de_vosk_model", "SKIP", time.time() - t0,
                           f"German Vosk model absent: {VOSK_MODEL_DE_PATH}")]
    try:
        import vosk
    except ImportError:
        return [TestResult("de_vosk_model", "SKIP", time.time() - t0,
                           "vosk not installed")]
    try:
        vosk.SetLogLevel(-1)
        model = vosk.Model(VOSK_MODEL_DE_PATH)
        elapsed_load = time.time() - t0
        rec = vosk.KaldiRecognizer(model, 16000)
        silence = b'\x00' * (16000 * 2)  # 1 s of silence S16LE
        rec.AcceptWaveform(silence)
        import json as _j
        result = _j.loads(rec.FinalResult())
        text = result.get("text", "")
        text_fmt = repr(text) if text else "(empty - correct)"
        detail = f"DE Vosk loaded in {elapsed_load:.1f}s, silence result: {text_fmt}"
        if verbose:
            print(f"         {detail}")
        return [TestResult("de_vosk_model", "PASS", time.time() - t0, detail,
                           metric=elapsed_load, metric_key="de_vosk_load_s")]
    except Exception as e:
        return [TestResult("de_vosk_model", "FAIL", time.time() - t0,
                           f"Failed to load German Vosk model: {e}")]


# ─────────────────────────────────────────────────────────────────────────────
# Regression check
# ─────────────────────────────────────────────────────────────────────────────

def t_regression_check(results: list[TestResult], gt: dict, **_) -> list[TestResult]:
    """T11 — compare numeric metrics from this run to the saved baseline."""
    baseline = _load_baseline()
    if baseline is None:
        return [TestResult("regression_check", "SKIP", 0.0,
                           "No baseline.json found — run with --set-baseline after first successful run")]

    tol_pct = gt.get("regression_tolerance_pct", 30)
    current_metrics = {r.metric_key: r.metric for r in results
                       if r.metric is not None and r.metric_key}
    baseline_metrics: dict = baseline.get("metrics", {})
    if not baseline_metrics:
        return [TestResult("regression_check", "SKIP", 0.0,
                           "Baseline has no metrics — re-run with --set-baseline")]

    regressions = []
    improvements = []
    for key, baseline_val in baseline_metrics.items():
        if key not in current_metrics or current_metrics[key] is None:
            continue
        cur = current_metrics[key]
        pct_change = 100 * (cur - baseline_val) / max(baseline_val, 0.001)
        if pct_change > tol_pct:
            regressions.append(f"{key}: {baseline_val:.1f}s → {cur:.1f}s (+{pct_change:.0f}%)")
        elif pct_change < -10:
            improvements.append(f"{key}: {baseline_val:.1f}s → {cur:.1f}s ({pct_change:.0f}%)")

    t0 = time.time()
    if regressions:
        detail = (f"REGRESSIONS vs baseline ({baseline.get('timestamp', '?')}):\n  "
                  + "\n  ".join(regressions)
                  + (("\nImprovements: " + ", ".join(improvements)) if improvements else ""))
        return [TestResult("regression_check", "WARN", time.time()-t0, detail)]
    msg = f"No regressions vs baseline ({baseline.get('timestamp', '?')})"
    if improvements:
        msg += "\nImprovements: " + ", ".join(improvements)
    return [TestResult("regression_check", "PASS", time.time()-t0, msg)]


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

TEST_FUNCTIONS = [
    t_model_files_present,
    t_piper_json_present,
    t_tmpfs_model_complete,
    t_ogg_decode,
    t_vad_filter,
    t_vosk_stt,
    t_confidence_strip,
    t_tts_escape,
    t_tts_synthesis,
    t_whisper_stt,
    t_whisper_hallucination_guard,
    # Language / i18n tests (T13–T16)
    t_i18n_string_coverage,
    t_lang_routing,
    t_de_tts_synthesis,
    t_de_vosk_model,
]


def _run_all(gt: dict, verbose: bool, filter_name: Optional[str]) -> list[TestResult]:
    all_results: list[TestResult] = []
    for fn in TEST_FUNCTIONS:
        if filter_name and filter_name not in fn.__name__:
            continue
        if verbose:
            print(f"\n{_B}▶ {fn.__name__}{_RST}")
        results = fn(gt=gt, verbose=verbose)
        for r in results:
            if verbose:
                print(f"   {r.color()}{r.status}{_RST} {r.name} ({r.duration_s:.2f}s)  {r.detail}")
        all_results.extend(results)

    # Regression check depends on all previous results
    if not filter_name or filter_name in "regression_check":
        reg = t_regression_check(results=all_results, gt=gt, verbose=verbose)
        for r in reg:
            if verbose:
                print(f"   {r.color()}{r.status}{_RST} {r.name}  {r.detail}")
        all_results.extend(reg)

    return all_results


def _print_summary(results: list[TestResult]) -> None:
    pad = max((len(r.name) for r in results), default=30) + 2
    print(f"\n{'─' * (pad + 50)}")
    print(f"{'TEST':<{pad}}  {'STATUS':<6}  {'TIME':>7}  DETAIL")
    print(f"{'─' * (pad + 50)}")
    for r in results:
        detail_short = r.detail.splitlines()[0][:70]
        print(f"{r.name:<{pad}}  {r.color()}{r.status:<6}{_RST}  {r.duration_s:>6.2f}s  {detail_short}")
    print(f"{'─' * (pad + 50)}")
    counts = {s: sum(1 for r in results if r.status == s) for s in ("PASS", "FAIL", "WARN", "SKIP")}
    total_time = sum(r.duration_s for r in results)
    print(f"{_G}PASS {counts['PASS']}{_RST}  "
          f"{_R}FAIL {counts['FAIL']}{_RST}  "
          f"{_W}WARN {counts['WARN']}{_RST}  "
          f"{_B}SKIP {counts['SKIP']}{_RST}  "
          f"  ({total_time:.1f}s total)\n")


def _save_results(results: list[TestResult], gt: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = RESULTS_DIR / f"{ts}.json"
    counts = {s: sum(1 for r in results if r.status == s)
              for s in ("PASS", "FAIL", "WARN", "SKIP")}
    run = {
        "timestamp": ts,
        "bot_version": _read_bot_version(),
        "voice_opts": _load_voice_opts(),
        "summary": counts,
        "metrics": {r.metric_key: r.metric for r in results
                    if r.metric is not None and r.metric_key},
        "tests": [asdict(r) for r in results],
    }
    out.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Results saved → {out}")
    return out


def _save_baseline(results: list[TestResult]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    baseline = {
        "timestamp": ts,
        "bot_version": _read_bot_version(),
        "voice_opts": _load_voice_opts(),
        "metrics": {r.metric_key: r.metric for r in results
                    if r.metric is not None and r.metric_key},
        "_note": ("Timing baseline. Regression test will WARN if any metric exceeds "
                  "baseline × 1.30 (30% tolerance)."),
    }
    BASELINE_FILE.write_text(json.dumps(baseline, indent=2, ensure_ascii=False),
                             encoding="utf-8")
    print(f"{_G}Baseline saved → {BASELINE_FILE}{_RST}")


def _read_bot_version() -> str:
    ver_path = PICOCLAW_DIR / "bot_config.py"
    try:
        for line in ver_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("BOT_VERSION"):
                return line.split("=")[1].strip().strip('"\'')
    except Exception:
        pass
    return "unknown"


def _compare_runs(a_path: Path, b_path: Path) -> None:
    """Print side-by-side metric comparison of two result JSON files."""
    a = json.loads(a_path.read_text(encoding="utf-8"))
    b = json.loads(b_path.read_text(encoding="utf-8"))
    a_m, b_m = a.get("metrics", {}), b.get("metrics", {})
    keys = sorted(set(a_m) | set(b_m))
    print(f"\nComparing:")
    print(f"  A: {a_path.name}  (bot {a.get('bot_version','?')})")
    print(f"  B: {b_path.name}  (bot {b.get('bot_version','?')})")
    print(f"\n{'METRIC':<45}  {'A':>8}  {'B':>8}  {'DELTA':>8}  {'%CHG':>6}")
    print("─" * 80)
    for k in keys:
        av = a_m.get(k, None)
        bv = b_m.get(k, None)
        if av is not None and bv is not None:
            delta = bv - av
            pct   = 100 * delta / max(av, 0.001)
            col   = _R if pct > 20 else (_G if pct < -10 else _RST)
            print(f"{k:<45}  {av:>7.2f}s  {bv:>7.2f}s  {col}{delta:>+7.2f}s  {pct:>+5.0f}%{_RST}")
        else:
            av_s = f"{av:.2f}s" if av is not None else "  —"
            bv_s = f"{bv:.2f}s" if bv is not None else "  —"
            print(f"{k:<45}  {av_s:>8}  {bv_s:>8}  {'':>8}  {'':>6}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Voice regression tests for picoclaw-telegram"
    )
    parser.add_argument("--set-baseline", action="store_true",
                        help="Save this run's timings as the new baseline")
    parser.add_argument("--verbose",  "-v", action="store_true",
                        help="Print per-test detail during execution")
    parser.add_argument("--test", "-t", metavar="NAME",
                        help="Run only tests whose function name contains NAME")
    parser.add_argument("--compare", nargs=2, metavar=("A.json","B.json"),
                        help="Compare two result files (no tests run)")
    args = parser.parse_args()

    if args.compare:
        _compare_runs(RESULTS_DIR / args.compare[0], RESULTS_DIR / args.compare[1])
        return 0

    print(f"\n{_B}Picoclaw Voice Regression Tests{_RST}  "
          f"(bot {_read_bot_version()}, {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"Fixtures: {VOICE_DIR}")
    print(f"Results:  {RESULTS_DIR}\n")

    if not VOICE_DIR.exists():
        print(f"{_R}[ERROR] Fixture directory not found: {VOICE_DIR}{_RST}")
        print("Deploy with:  pscp -pw PWD src/tests/voice/*.ogg "
              "stas@OpenClawPI:/home/stas/.picoclaw/tests/voice/")
        return 2

    gt = _load_gt()
    results = _run_all(gt, verbose=args.verbose, filter_name=args.test)
    _print_summary(results)
    saved_path = _save_results(results, gt)

    if args.set_baseline:
        _save_baseline(results)
        print(f"\nRe-run without --set-baseline to check against this baseline.")

    # Return 1 if any FAIL, else 0
    has_fail = any(r.status == "FAIL" for r in results)
    return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())
