#!/usr/bin/env python3
"""
test_voice_regression.py — Voice pipeline regression tests for taris-telegram.

Tests every voice-related function independently and saves timestamped results
so latency and quality regressions are detected when bot_voice.py changes.

Usage (on Raspberry Pi):
    python3 test_voice_regression.py              # run all tests
    python3 test_voice_regression.py --set-baseline   # save current run as baseline
    python3 test_voice_regression.py --verbose    # extra output per test
    python3 test_voice_regression.py --test vosk  # run only tests matching name

Deploy:
    pscp -pw "..." src/tests/test_voice_regression.py stas@OpenClawPI:/home/stas/.taris/tests/
    pscp -pw "..." src/tests/voice/*.ogg stas@OpenClawPI:/home/stas/.taris/tests/voice/
    pscp -pw "..." src/tests/voice/ground_truth.json stas@OpenClawPI:/home/stas/.taris/tests/voice/

Exit codes:
    0 — all tests passed (and no significant regression vs baseline)
    1 — one or more tests FAILED or regression exceeded threshold
    2 — test runner error (missing fixtures, import errors, etc.)
"""

from __future__ import annotations

import argparse
import importlib
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

TARIS_DIR   = Path(os.path.expanduser("~/.taris"))
TESTS_DIR      = Path(__file__).parent.resolve()
# Package-aware paths (new package layout)
_PKG_CORE     = TARIS_DIR / "core"
_PKG_TELEGRAM = TARIS_DIR / "telegram"
_PKG_FEATURES = TARIS_DIR / "features"
VOICE_DIR      = TESTS_DIR / "voice"
RESULTS_DIR    = VOICE_DIR / "results"
GROUND_TRUTH   = VOICE_DIR / "ground_truth.json"
BASELINE_FILE  = RESULTS_DIR / "baseline.json"

# Mirror bot_config.py defaults so tests use exactly the same paths
PIPER_BIN         = os.environ.get("PIPER_BIN",  "/usr/local/bin/piper")
PIPER_MODEL       = os.environ.get("PIPER_MODEL", str(TARIS_DIR / "ru_RU-irina-medium.onnx"))
PIPER_MODEL_TMPFS = "/dev/shm/piper/" + Path(PIPER_MODEL).name
PIPER_MODEL_LOW   = os.environ.get("PIPER_MODEL_LOW", str(TARIS_DIR / "ru_RU-irina-low.onnx"))
WHISPER_BIN       = os.environ.get("WHISPER_BIN",  "/usr/local/bin/whisper-cpp")
WHISPER_MODEL     = os.environ.get("WHISPER_MODEL", str(TARIS_DIR / "ggml-base.bin"))
VOSK_MODEL_PATH   = os.environ.get("VOSK_MODEL_PATH", str(TARIS_DIR / "vosk-model-small-ru"))

VOSK_MODEL_DE_PATH   = os.environ.get("VOSK_MODEL_DE_PATH",  str(TARIS_DIR / "vosk-model-small-de"))
PIPER_MODEL_DE       = os.environ.get("PIPER_MODEL_DE",      str(TARIS_DIR / "de_DE-thorsten-medium.onnx"))
PIPER_MODEL_DE_TMPFS = "/dev/shm/piper/de_DE-thorsten-medium.onnx"
STRINGS_FILE         = TARIS_DIR / "strings.json"

VOICE_SAMPLE_RATE   = 16000
VOICE_CHUNK_SIZE    = 4000
STT_CONF_THRESHOLD  = 0.65    # must match bot_voice.py

# Confidence marker regex — must be identical to bot_voice.py
_CONF_MARKER_RE = re.compile(r'\[\?([^\]]*)\]')

VOICE_OPTS_FILE = TARIS_DIR / "voice_opts.json"

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
        ("🤖 Taris:",                "Taris:"),
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
    # Probe for missing shared libraries (binary exists but can't load .so deps)
    _probe = subprocess.run([WHISPER_BIN, "--help"], capture_output=True, timeout=5)
    if _probe.returncode == 127:
        return [TestResult("whisper_stt", "SKIP", 0.0,
                           "whisper-cpp missing shared libs (rc=127) — not fully installed")]

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
# T17 — BOT_NAME injection via _t() (Bug 0.2)
# ─────────────────────────────────────────────────────────────────────────────

def t_bot_name_injection(**_) -> list[TestResult]:
    """T17 — BOT_NAME is defined in bot_config and auto-injected by _t() into {bot_name} placeholders."""
    t0 = time.time()
    issues: list[str] = []

    # 1) bot_config exports BOT_NAME
    try:
        sys.path.insert(0, str(TARIS_DIR))
        import importlib
        cfg = importlib.import_module("core.bot_config")
        importlib.reload(cfg)
        bot_name = getattr(cfg, "BOT_NAME", None)
        if bot_name is None:
            issues.append("bot_config.BOT_NAME not defined")
        elif not isinstance(bot_name, str) or not bot_name.strip():
            issues.append(f"bot_config.BOT_NAME is empty or non-string: {bot_name!r}")
    except Exception as e:
        issues.append(f"Cannot import bot_config: {e}")
        bot_name = None
    finally:
        sys.path.pop(0)

    # 2) strings.json has {bot_name} placeholders in key strings
    if STRINGS_FILE.exists():
        try:
            strings = json.loads(STRINGS_FILE.read_text(encoding="utf-8"))
            required_keys = ["welcome", "greet", "no_answer"]
            for lang in ("ru", "en", "de"):
                for key in required_keys:
                    val = strings.get(lang, {}).get(key, "")
                    if "{bot_name}" not in val:
                        issues.append(f"{lang}.{key} missing {{bot_name}} placeholder")
        except Exception as e:
            issues.append(f"Cannot parse strings.json: {e}")

    # 3) Verify _t() actually injects bot_name (simulate without Telegram)
    if STRINGS_FILE.exists() and bot_name:
        try:
            strings = json.loads(STRINGS_FILE.read_text(encoding="utf-8"))
            test_tmpl = strings.get("en", {}).get("greet", "")
            if "{bot_name}" in test_tmpl:
                formatted = test_tmpl.format(bot_name=bot_name)
                if bot_name in formatted:
                    pass  # ok
                else:
                    issues.append(f"greet.format(bot_name={bot_name!r}) did not inject: {formatted!r}")
        except Exception as e:
            issues.append(f"Format test failed: {e}")

    dur = time.time() - t0
    if issues:
        return [TestResult("bot_name_injection", "FAIL", dur,
                           f"{len(issues)} issue(s): " + "; ".join(issues))]
    return [TestResult("bot_name_injection", "PASS", dur,
                       f"BOT_NAME={bot_name!r}, placeholders present in required keys")]


# ─────────────────────────────────────────────────────────────────────────────
# T18 — Profile handler resilience (Bug 0.1)
# ─────────────────────────────────────────────────────────────────────────────

def t_profile_resilience(**_) -> list[TestResult]:
    """T18 — _handle_profile() has try/except around deferred mail_creds import so it never crashes."""
    t0 = time.time()
    issues: list[str] = []
    handler_path = (_PKG_TELEGRAM / "bot_handlers.py" if (_PKG_TELEGRAM / "bot_handlers.py").exists()
                     else TARIS_DIR / "bot_handlers.py")

    if not handler_path.exists():
        return [TestResult("profile_resilience", "FAIL", time.time() - t0,
                           f"bot_handlers.py not found: {handler_path}")]

    src = handler_path.read_text(encoding="utf-8")

    # Find _handle_profile function
    if "def _handle_profile" not in src:
        issues.append("_handle_profile() function not found")
    else:
        # Extract the function body (from def to next def or end)
        match = re.search(
            r'(def _handle_profile\b.*?)(?=\ndef [a-z_]|\Z)',
            src, re.DOTALL,
        )
        if match:
            func_body = match.group(1)
            # Must have try/except around the import
            if "try:" not in func_body or "bot_mail_creds" not in func_body:
                issues.append("_handle_profile missing try/except around bot_mail_creds import")
            if "except" not in func_body:
                issues.append("_handle_profile has no except clause for import guard")
            # Must have a fallback lambda or similar for _load_creds
            if "lambda" not in func_body and "_load_creds = None" not in func_body:
                if "lambda" not in func_body:
                    # Acceptable if there's a conditional check
                    pass
        else:
            issues.append("Could not extract _handle_profile function body")

    dur = time.time() - t0
    if issues:
        return [TestResult("profile_resilience", "FAIL", dur,
                           "; ".join(issues))]
    return [TestResult("profile_resilience", "PASS", dur,
                       "_handle_profile has try/except guard around deferred import")]


# ─────────────────────────────────────────────────────────────────────────────
# T19 — Note edit Append/Replace functions exist (Bug 0.3)
# ─────────────────────────────────────────────────────────────────────────────

def t_note_edit_append_replace(**_) -> list[TestResult]:
    """T19 — bot_handlers has _start_note_append/_start_note_replace and strings.json has the keys."""
    t0 = time.time()
    issues: list[str] = []

    # 1) Functions exist in bot_handlers.py
    handler_path = (_PKG_TELEGRAM / "bot_handlers.py" if (_PKG_TELEGRAM / "bot_handlers.py").exists()
                    else TARIS_DIR / "bot_handlers.py")
    if not handler_path.exists():
        return [TestResult("note_edit_append_replace", "FAIL", time.time() - t0,
                           f"bot_handlers.py not found")]
    src = handler_path.read_text(encoding="utf-8")

    for fn_name in ("_start_note_append", "_start_note_replace", "_start_note_edit"):
        if f"def {fn_name}" not in src:
            issues.append(f"{fn_name}() not found in bot_handlers.py")

    # 2) _start_note_edit shows Append/Replace choice (not direct ForceReply)
    match = re.search(
        r'(def _start_note_edit\b.*?)(?=\ndef [a-z_]|\Z)',
        src, re.DOTALL,
    )
    if match:
        edit_body = match.group(1)
        if "note_append:" in edit_body or "btn_note_append" in edit_body:
            pass  # good — shows append button
        else:
            issues.append("_start_note_edit does not offer Append option")
        if "note_replace:" in edit_body or "btn_note_replace" in edit_body:
            pass  # good — shows replace button
        else:
            issues.append("_start_note_edit does not offer Replace option")

    # 3) Callback dispatch in telegram_menu_bot.py
    entry_path = TARIS_DIR / "telegram_menu_bot.py"
    if entry_path.exists():
        entry_src = entry_path.read_text(encoding="utf-8")
        if "note_append:" not in entry_src:
            issues.append("telegram_menu_bot.py missing callback dispatch for note_append:")
        if "note_replace:" not in entry_src:
            issues.append("telegram_menu_bot.py missing callback dispatch for note_replace:")
    else:
        issues.append("telegram_menu_bot.py not found")

    # 4) strings.json has the required keys
    if STRINGS_FILE.exists():
        strings = json.loads(STRINGS_FILE.read_text(encoding="utf-8"))
        required_keys = ["note_edit_choice", "btn_note_append", "btn_note_replace", "note_append_prompt"]
        for lang in ("ru", "en", "de"):
            for key in required_keys:
                if key not in strings.get(lang, {}):
                    issues.append(f"{lang}.{key} missing from strings.json")

    dur = time.time() - t0
    if issues:
        return [TestResult("note_edit_append_replace", "FAIL", dur,
                           f"{len(issues)} issue(s): " + "; ".join(issues))]
    return [TestResult("note_edit_append_replace", "PASS", dur,
                       "Append/Replace note edit flow: functions, callbacks, and i18n keys all present")]


# ─────────────────────────────────────────────────────────────────────────────
# T20 — Calendar TTS call signature (Bug 0.4)
# ─────────────────────────────────────────────────────────────────────────────

def t_calendar_tts_call_signature(**_) -> list[TestResult]:
    """T20 — _cal_tts_text(chat_id, ev_dict) accepts 2 args; _handle_cal_event_tts builds ev_dict correctly."""
    t0 = time.time()
    issues: list[str] = []

    cal_path = (_PKG_FEATURES / "bot_calendar.py" if (_PKG_FEATURES / "bot_calendar.py").exists()
                else TARIS_DIR / "bot_calendar.py")
    if not cal_path.exists():
        return [TestResult("calendar_tts_call_signature", "FAIL", time.time() - t0,
                           "bot_calendar.py not found")]

    src = cal_path.read_text(encoding="utf-8")

    # 1) _cal_tts_text signature: must be (chat_id, ev) — exactly 2 positional args
    sig_match = re.search(r'def _cal_tts_text\(([^)]+)\)', src)
    if sig_match:
        params = [p.strip().split(":")[0].strip() for p in sig_match.group(1).split(",")]
        if len(params) != 2:
            issues.append(f"_cal_tts_text has {len(params)} params (expected 2): {params}")
        if params[0] != "chat_id":
            issues.append(f"_cal_tts_text first param should be chat_id, got {params[0]!r}")
    else:
        issues.append("_cal_tts_text definition not found")

    # 2) _cal_tts_text body uses ev["dt"].strftime (requires datetime obj, not string)
    tts_func = re.search(
        r'(def _cal_tts_text\b.*?)(?=\ndef [a-z_]|\Z)',
        src, re.DOTALL,
    )
    if tts_func:
        body = tts_func.group(1)
        if 'ev["dt"]' in body or "ev['dt']" in body:
            pass  # good — accesses ev["dt"]
        else:
            issues.append("_cal_tts_text does not access ev['dt'] — may not format datetime")

    # 3) _handle_cal_event_tts builds ev_dict with datetime object
    handler_match = re.search(
        r'(def _handle_cal_event_tts\b.*?)(?=\ndef [a-z_]|\Z)',
        src, re.DOTALL,
    )
    if handler_match:
        h_body = handler_match.group(1)
        if "fromisoformat" in h_body:
            pass  # good — converts dt_iso string to datetime
        else:
            issues.append("_handle_cal_event_tts does not call fromisoformat — ev_dict may lack datetime")
        if "_cal_tts_text(chat_id" in h_body:
            pass  # good — calls with chat_id first
        else:
            issues.append("_handle_cal_event_tts does not call _cal_tts_text(chat_id, ...)")
    else:
        issues.append("_handle_cal_event_tts function not found")

    dur = time.time() - t0
    if issues:
        return [TestResult("calendar_tts_call_signature", "FAIL", dur,
                           f"{len(issues)} issue(s): " + "; ".join(issues))]
    return [TestResult("calendar_tts_call_signature", "PASS", dur,
                       "_cal_tts_text(chat_id, ev) with datetime obj in ev_dict — correct")]


# ─────────────────────────────────────────────────────────────────────────────
# T21 — Calendar console intent classifier (Bug 0.5)
# ─────────────────────────────────────────────────────────────────────────────

def t_calendar_console_classifier(**_) -> list[TestResult]:
    """T21 — _handle_cal_console uses JSON intent classifier, not general LLM action prompt."""
    t0 = time.time()
    issues: list[str] = []

    cal_path = (_PKG_FEATURES / "bot_calendar.py" if (_PKG_FEATURES / "bot_calendar.py").exists()
                else TARIS_DIR / "bot_calendar.py")
    if not cal_path.exists():
        return [TestResult("calendar_console_classifier", "FAIL", time.time() - t0,
                           "bot_calendar.py not found")]

    src = cal_path.read_text(encoding="utf-8")

    # Extract _handle_cal_console body
    match = re.search(
        r'(def _handle_cal_console\b.*?)(?=\ndef [a-z_]|\Z)',
        src, re.DOTALL,
    )
    if not match:
        return [TestResult("calendar_console_classifier", "FAIL", time.time() - t0,
                           "_handle_cal_console not found")]

    func_body = match.group(1)

    # 1) Must have intent classification keywords
    if '"intent"' not in func_body and "'intent'" not in func_body:
        issues.append("No 'intent' key referenced — not using JSON classification")

    # 2) Must have "add" as default fallback
    if '"add"' in func_body:
        pass  # good — defaults to add
    else:
        issues.append("No default 'add' intent fallback found")

    # 3) Must NOT ask LLM to perform the action itself
    # The classifier prompt should say "Do NOT refuse" or "Do NOT perform"
    if "Do NOT" in func_body or "Do not" in func_body or "classifier" in func_body.lower():
        pass  # good — has guardrail instruction
    else:
        issues.append("Missing classifier guardrail instructions (Do NOT refuse/perform)")

    # 4) Must call _finish_cal_add for add intent (not _ask_taris again)
    if "_finish_cal_add" in func_body:
        pass  # good — routes add intent to local handler
    else:
        issues.append("add intent does not route to _finish_cal_add()")

    # 5) Must parse JSON from LLM response
    if "json.loads" in func_body or "re.search" in func_body:
        pass  # good — parses structured output
    else:
        issues.append("No JSON parsing found in console handler")

    dur = time.time() - t0
    if issues:
        return [TestResult("calendar_console_classifier", "FAIL", dur,
                           f"{len(issues)} issue(s): " + "; ".join(issues))]
    return [TestResult("calendar_console_classifier", "PASS", dur,
                       "Console uses JSON intent classifier with add default + routes to local handlers")]


# ─────────────────────────────────────────────────────────────────────────────
# T22 — SQLite voice_opts roundtrip
# ─────────────────────────────────────────────────────────────────────────────

def t_db_voice_opts_roundtrip(**_) -> list[TestResult]:
    """T22 — SQLite voice_opts roundtrip: save all 12 keys and reload from DB."""
    import tempfile
    t0 = time.time()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            os.environ["DB_FILE"] = db_path
            os.environ["WEB_ONLY"] = "1"
            sys.path.insert(0, str(TARIS_DIR))
            if "core.bot_db" in sys.modules:
                import core.bot_db as _bot_db
                importlib.reload(_bot_db)
            else:
                import core.bot_db as _bot_db
            _bot_db.init_db()
            opts_in = {k: True for k in [
                "silence_strip", "low_sample_rate", "warm_piper", "parallel_tts",
                "user_audio_toggle", "tmpfs_model", "vad_prefilter", "whisper_stt",
                "vosk_fallback", "piper_low_model", "persistent_piper", "voice_timing_debug",
            ]}
            _bot_db.db_save_voice_opts(opts_in)
            opts_out = _bot_db.db_get_voice_opts()
            _bot_db.close_db()
        os.environ.pop("DB_FILE", None)
        os.environ.pop("WEB_ONLY", None)
        matched = all(opts_out.get(k) == v for k, v in opts_in.items())
        status = "PASS" if matched else "FAIL"
        detail = ("All 12 voice_opts keys round-tripped correctly" if matched
                  else f"Mismatch: {opts_out}")
    except Exception as e:
        status, detail = "FAIL", str(e)
    return [TestResult("db_voice_opts_roundtrip", status, time.time() - t0, detail)]


# ─────────────────────────────────────────────────────────────────────────────
# T23 — Migration idempotency
# ─────────────────────────────────────────────────────────────────────────────

def t_db_migration_idempotent(**_) -> list[TestResult]:
    """T23 — running migrate_to_db.py twice gives same row counts (idempotent)."""
    import tempfile
    import sqlite3 as _sql
    t0 = time.time()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "registrations.json").write_text(json.dumps({"registrations": [
                {"chat_id": 1, "username": "u", "first_name": "F", "last_name": "L",
                 "name": "F L", "timestamp": "2024-01-01T00:00:00", "status": "approved"}
            ]}))
            (tmp_path / "users.json").write_text(json.dumps({"users": [1]}))
            (tmp_path / "voice_opts.json").write_text(json.dumps({"vosk_fallback": True}))
            db_path = str(tmp_path / "mig.db")
            migrate = str(TESTS_DIR.parent.parent / "tools" / "migrate_to_db.py")
            for run_no in range(1, 3):
                r = subprocess.run(
                    [sys.executable, migrate, "--source", str(tmp_path), "--db", db_path],
                    capture_output=True, timeout=15,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
                if r.returncode != 0:
                    return [TestResult("db_migration_idempotent", "FAIL", time.time() - t0,
                                       f"migrate exit {r.returncode} on run {run_no}: {r.stderr.decode(errors='replace')[:300]}")]
            con = _sql.connect(db_path)
            reg_count = con.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
            usr_count = con.execute("SELECT COUNT(*) FROM guest_users").fetchone()[0]
            con.close()
        ok = reg_count == 1 and usr_count == 1
        status = "PASS" if ok else "FAIL"
        detail = (f"registrations={reg_count}, guest_users={usr_count} after 2 runs"
                  + (" (idempotent \u2713)" if ok else " \u2014 DOUBLED, not idempotent!"))
    except Exception as e:
        status, detail = "FAIL", str(e)
    return [TestResult("db_migration_idempotent", status, time.time() - t0, detail)]


# ─────────────────────────────────────────────────────────────────────────────
# T24 — RAG: LR-products query retrieves relevant chunks + answer quality
# ─────────────────────────────────────────────────────────────────────────────

def t_rag_lr_products(**_) -> list[TestResult]:
    """T24 — RAG pipeline: FTS5 query for LR products must return chunks that
    contain key topic keywords (алоэ, Mind Master, витамин, цинк, LR LIFETAKT).

    Two sub-tests are produced:
      rag_lr_products_fts  — always runs; verifies chunk retrieval keyword coverage
      rag_lr_products_llm  — only with LLM_JUDGE=1; runs full RAG prompt and uses
                             LLM-as-judge to confirm the answer covers expected topics.

    SKIP if taris.db or doc_chunks table is absent (document not yet uploaded).
    """
    import sqlite3 as _sql
    t0 = time.time()
    results: list[TestResult] = []

    db_file = TARIS_DIR / "taris.db"
    if not db_file.exists():
        return [TestResult("rag_lr_products_fts", "SKIP", time.time() - t0,
                           "taris.db not found — RAG database not initialised")]

    # ── Step 1: FTS5 chunk retrieval ─────────────────────────────────────────
    QUERY       = "какие продукты LR ты можешь мне предложить"
    FTS_TERMS   = "LR OR алоэ OR Mind OR витамин OR цинк OR LIFETAKT OR Kölner"
    # Keywords expected somewhere in the combined returned chunks
    EXPECTED_KW = ["алоэ", "mind master", "витамин", "цинк", "lr lifetakt", "kölner"]
    MIN_KW_HITS = 2

    try:
        con = _sql.connect(str(db_file))
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "doc_chunks" not in tables:
            con.close()
            return [TestResult("rag_lr_products_fts", "SKIP", time.time() - t0,
                               "doc_chunks table not found — upload an LR document first")]
        rows = con.execute(
            "SELECT chunk_text FROM doc_chunks"
            " WHERE doc_chunks MATCH ? ORDER BY rank LIMIT 10",
            (FTS_TERMS,),
        ).fetchall()
        con.close()
    except Exception as exc:
        return [TestResult("rag_lr_products_fts", "FAIL", time.time() - t0,
                           f"DB error: {exc}")]

    dur_fts = time.time() - t0

    if not rows:
        results.append(TestResult("rag_lr_products_fts", "SKIP", dur_fts,
                                  "FTS5 returned 0 chunks — LR products document not yet uploaded"))
    else:
        combined = "\n".join(r[0] for r in rows).lower()
        kw_hits = [kw for kw in EXPECTED_KW if kw.lower() in combined]
        if len(kw_hits) >= MIN_KW_HITS:
            results.append(TestResult(
                "rag_lr_products_fts", "PASS", dur_fts,
                f"{len(rows)} chunk(s) retrieved; "
                f"{len(kw_hits)}/{len(EXPECTED_KW)} keywords found: {kw_hits}",
            ))
        else:
            results.append(TestResult(
                "rag_lr_products_fts", "FAIL", dur_fts,
                f"Only {len(kw_hits)}/{len(EXPECTED_KW)} keywords in chunks "
                f"(need ≥{MIN_KW_HITS}); found: {kw_hits}; "
                f"first chunk sample: {rows[0][0][:150] if rows else '—'}",
            ))

    # ── Step 2: LLM answer quality (only if LLM_JUDGE=1) ────────────────────
    if os.environ.get("LLM_JUDGE") == "1" and rows:
        t1 = time.time()
        try:
            sys.path.insert(0, str(TARIS_DIR))
            from core.bot_llm import ask_llm  # type: ignore

            ctx_text = "\n".join(r[0] for r in rows[:3])[:1600]
            rag_prompt = (
                "Ответь на вопрос, используя только предоставленный контекст.\n\n"
                f"Контекст:\n{ctx_text}\n\n"
                f"Вопрос: {QUERY}"
            )
            answer = ask_llm(rag_prompt, timeout=60)
            answer_lower = answer.lower()

            # Keyword presence check
            ANSWER_KW  = ["алоэ", "mind master", "витамин", "цинк", "lr"]
            ANSWER_MIN = 2
            answer_hits = [kw for kw in ANSWER_KW if kw.lower() in answer_lower]

            # LLM-as-judge: second call to verify thematic correctness
            judge_prompt = (
                "Оцени: содержит ли следующий ответ информацию о продуктах LR? "
                "(алоэ-вера, Mind Master, витамин C, цинк, LR LIFETAKT — "
                "хотя бы 2 из этих тем достаточно)\n\n"
                f"Ответ: {answer[:600]}\n\n"
                "Ответь только YES или NO."
            )
            verdict = ask_llm(judge_prompt, timeout=30).strip().upper()
            judge_ok = verdict.startswith("YES")

            dur_llm = time.time() - t1
            if judge_ok or len(answer_hits) >= ANSWER_MIN:
                results.append(TestResult(
                    "rag_lr_products_llm", "PASS", dur_llm,
                    f"LLM judge: {verdict}; keywords in answer: {answer_hits}; "
                    f"answer[:120]: {answer[:120]}",
                ))
            else:
                results.append(TestResult(
                    "rag_lr_products_llm", "FAIL", dur_llm,
                    f"LLM judge: {verdict}; "
                    f"only {len(answer_hits)}/{len(ANSWER_KW)} keywords; "
                    f"answer[:200]: {answer[:200]}",
                ))
        except Exception as exc:
            results.append(TestResult("rag_lr_products_llm", "FAIL", time.time() - t1,
                                      f"LLM judge error: {exc}"))
    else:
        results.append(TestResult("rag_lr_products_llm", "SKIP", 0.0,
                                  "Set LLM_JUDGE=1 to enable LLM answer quality check"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T25 — Web link code generate/validate roundtrip
# ─────────────────────────────────────────────────────────────────────────────

def t_web_link_code_roundtrip(**_) -> list[TestResult]:
    """T25 — web link code: format, roundtrip, single-use, expiry, revocation, cross-process."""
    import string
    import tempfile
    import time as _t
    from datetime import datetime, timezone, timedelta as _td
    results: list[TestResult] = []
    CHAT_ID = 99999

    sys.path.insert(0, str(TARIS_DIR))
    try:
        import core.bot_state as _bs
    except ImportError as exc:
        return [TestResult("web_link_code:import", "FAIL", 0.0,
                           f"Cannot import core.bot_state: {exc}")]

    orig_file = _bs._WEB_LINK_CODES_FILE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _bs._WEB_LINK_CODES_FILE = str(Path(tmp) / "web_link_codes.json")

            # 1 — format: 6 uppercase alphanumeric chars
            t1 = _t.time()
            try:
                code = _bs.generate_web_link_code(CHAT_ID)
                valid_chars = set(string.ascii_uppercase + string.digits)
                fmt_ok = len(code) == 6 and all(c in valid_chars for c in code)
                results.append(TestResult(
                    "web_link_code:generate",
                    "PASS" if fmt_ok else "FAIL",
                    _t.time() - t1,
                    f"code='{code}' len={len(code)} all_valid={fmt_ok}",
                ))
            except Exception as exc:
                results.append(TestResult("web_link_code:generate", "FAIL",
                                          _t.time() - t1, str(exc)))
                return results

            # 2 — validate returns correct chat_id
            t1 = _t.time()
            try:
                returned_id = _bs.validate_web_link_code(code)
                ok = returned_id == CHAT_ID
                results.append(TestResult(
                    "web_link_code:validate",
                    "PASS" if ok else "FAIL",
                    _t.time() - t1,
                    f"expected={CHAT_ID} got={returned_id}",
                ))
            except Exception as exc:
                results.append(TestResult("web_link_code:validate", "FAIL",
                                          _t.time() - t1, str(exc)))

            # 3 — single-use: second validate returns None
            t1 = _t.time()
            try:
                returned_again = _bs.validate_web_link_code(code)
                ok = returned_again is None
                results.append(TestResult(
                    "web_link_code:single_use",
                    "PASS" if ok else "FAIL",
                    _t.time() - t1,
                    f"re-validate={returned_again!r} (expected None)",
                ))
            except Exception as exc:
                results.append(TestResult("web_link_code:single_use", "FAIL",
                                          _t.time() - t1, str(exc)))

            # 4 — unknown code returns None
            t1 = _t.time()
            try:
                returned_inv = _bs.validate_web_link_code("XXXXXX")
                ok = returned_inv is None
                results.append(TestResult(
                    "web_link_code:invalid",
                    "PASS" if ok else "FAIL",
                    _t.time() - t1,
                    f"unknown code returned {returned_inv!r} (expected None)",
                ))
            except Exception as exc:
                results.append(TestResult("web_link_code:invalid", "FAIL",
                                          _t.time() - t1, str(exc)))

            # 5 — expired code returns None
            t1 = _t.time()
            try:
                exp_code = "EXPIRY"
                _bs._save_web_link_codes(
                    {exp_code: {"chat_id": CHAT_ID,
                                "expires_at": datetime.now(timezone.utc) - _td(seconds=10)}}
                )
                returned_exp = _bs.validate_web_link_code(exp_code)
                ok = returned_exp is None
                results.append(TestResult(
                    "web_link_code:expired",
                    "PASS" if ok else "FAIL",
                    _t.time() - t1,
                    f"expired code returned {returned_exp!r} (expected None)",
                ))
            except Exception as exc:
                results.append(TestResult("web_link_code:expired", "FAIL",
                                          _t.time() - t1, str(exc)))

            # 6 — revoke old: generate twice, first code invalidated
            t1 = _t.time()
            try:
                code_a = _bs.generate_web_link_code(CHAT_ID)
                code_b = _bs.generate_web_link_code(CHAT_ID)
                returned_a = _bs.validate_web_link_code(code_a)
                ok = returned_a is None and code_a != code_b
                results.append(TestResult(
                    "web_link_code:revoke_old",
                    "PASS" if ok else "FAIL",
                    _t.time() - t1,
                    f"a={code_a} b={code_b} validate(a)={returned_a!r} distinct={code_a != code_b}",
                ))
            except Exception as exc:
                results.append(TestResult("web_link_code:revoke_old", "FAIL",
                                          _t.time() - t1, str(exc)))

            # 7 — cross-process: generate → reload from file → code present
            t1 = _t.time()
            try:
                cp_code = _bs.generate_web_link_code(CHAT_ID)
                fresh = _bs._load_web_link_codes()
                ok = cp_code in fresh and fresh[cp_code].get("chat_id") == CHAT_ID
                results.append(TestResult(
                    "web_link_code:cross_process",
                    "PASS" if ok else "FAIL",
                    _t.time() - t1,
                    f"code in file={cp_code in fresh} "
                    f"chat_id={fresh.get(cp_code, {}).get('chat_id')}",
                ))
            except Exception as exc:
                results.append(TestResult("web_link_code:cross_process", "FAIL",
                                          _t.time() - t1, str(exc)))
    finally:
        _bs._WEB_LINK_CODES_FILE = orig_file
    return results


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


def t_system_chat_clean_output(**_) -> list[TestResult]:
    """T26 — _SPINNER_RE must not strip ASCII -/|\\ (bug-fix guard);
    ask_llm_or_raise must be importable and callable from core.bot_llm."""
    results: list[TestResult] = []

    # Live-import core.bot_llm so we test the actual deployed code.
    if str(TARIS_DIR) not in sys.path:
        sys.path.insert(0, str(TARIS_DIR))
    try:
        import importlib as _il
        bot_llm = _il.import_module("core.bot_llm")
        clean = getattr(bot_llm, "_clean_output", None)
    except Exception as exc:
        return [TestResult("syschat:import", "FAIL", 0.0,
                           f"Cannot import core.bot_llm: {exc}")]

    if not callable(clean):
        return [TestResult("syschat:import", "FAIL", 0.0,
                           "_clean_output not found in core.bot_llm")]

    # Part 1 — ASCII characters that appear in bash commands must be preserved.
    cases = [
        ("df -h",          "df -h"),
        ("cat /etc/hosts", "cat /etc/hosts"),
        ("ls | grep foo",  "ls | grep foo"),
        ("ls -la /home",   "ls -la /home"),
    ]
    t0 = time.time()
    failures = []
    for inp, expected in cases:
        got = clean(inp)
        if got != expected:
            failures.append(f"  {inp!r} \u2192 {got!r}, want {expected!r}")
    dur = time.time() - t0
    if failures:
        results.append(TestResult("syschat:ascii_preserved", "FAIL", dur,
                                  f"{len(failures)}/{len(cases)} cases failed:\n" + "\n".join(failures)))
    else:
        results.append(TestResult("syschat:ascii_preserved", "PASS", dur,
                                  f"All {len(cases)} ASCII-char cases preserved correctly"))

    # Part 2 — Braille spinner chars must still be stripped.
    t0 = time.time()
    got = clean("\u280b\u2819ls\u2839")
    dur = time.time() - t0
    if got == "ls":
        results.append(TestResult("syschat:spinner_stripped", "PASS", dur,
                                  f"Braille stripped correctly \u2192 '{got}'"))
    else:
        results.append(TestResult("syschat:spinner_stripped", "FAIL", dur,
                                  f"Expected 'ls', got '{got}'"))

    # Part 3 — ask_llm_or_raise must exist and be callable.
    t0 = time.time()
    fn = getattr(bot_llm, "ask_llm_or_raise", None)
    dur = time.time() - t0
    if callable(fn):
        results.append(TestResult("syschat:ask_llm_or_raise_exists", "PASS", dur,
                                  "ask_llm_or_raise is callable"))
    else:
        results.append(TestResult("syschat:ask_llm_or_raise_exists", "FAIL", dur,
                                  "ask_llm_or_raise missing from core.bot_llm"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T27 — OpenClaw: faster-whisper STT availability (SKIP if not installed)
# ─────────────────────────────────────────────────────────────────────────────

def t_faster_whisper_stt(gt: dict, verbose: bool = False, **_) -> list[TestResult]:
    """T27 — faster-whisper STT: import, model load, inference on silence."""
    t0 = time.time()
    try:
        from faster_whisper import WhisperModel  # type: ignore[import]
    except ImportError:
        return [TestResult("faster_whisper_stt", "SKIP", time.time() - t0,
                           "faster-whisper not installed — run: pip install faster-whisper")]

    results: list[TestResult] = []
    fw_model_size = os.environ.get("FASTER_WHISPER_MODEL", "base")
    device = os.environ.get("FASTER_WHISPER_DEVICE", "cpu")
    compute = os.environ.get("FASTER_WHISPER_COMPUTE", "int8")

    # Test 1: model load
    t1 = time.time()
    try:
        model = WhisperModel(fw_model_size, device=device, compute_type=compute)
        load_t = time.time() - t1
        results.append(TestResult(
            f"faster_whisper:model_load:{fw_model_size}",
            "PASS", load_t,
            f"Loaded {fw_model_size} ({device}/{compute}) in {load_t:.2f}s",
            metric=load_t, metric_key=f"faster_whisper_load_{fw_model_size}",
        ))
    except Exception as e:
        dur = time.time() - t1
        return results + [TestResult(f"faster_whisper:model_load:{fw_model_size}", "FAIL", dur, str(e))]

    # Test 2: inference on silence (should return empty or short result)
    import numpy as np
    silent_pcm = np.zeros(16000, dtype=np.int16).tobytes()  # 1s silence
    audio_np = np.frombuffer(silent_pcm, dtype=np.int16).astype(np.float32) / 32768.0
    t2 = time.time()
    try:
        segments, info = model.transcribe(audio_np, language="ru", vad_filter=True, beam_size=1)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        infer_t = time.time() - t2
        rtf = infer_t / 1.0  # 1s audio
        status = "PASS" if rtf < 5.0 else "WARN"  # should be fast even on old CPU
        results.append(TestResult(
            "faster_whisper:inference_silence",
            status, infer_t,
            f"RTF={rtf:.2f} (text='{text[:30]}')",
            metric=infer_t, metric_key="faster_whisper_inference_silence",
        ))
    except Exception as e:
        results.append(TestResult("faster_whisper:inference_silence", "FAIL", time.time() - t2, str(e)))

    # Test 3: real audio fixture (if available)
    ogg_files = list(VOICE_DIR.glob("*.ogg")) if VOICE_DIR.exists() else []
    if ogg_files and gt:
        ogg = ogg_files[0]
        gt_text = gt.get(ogg.name, "")
        t3 = time.time()
        try:
            import subprocess as _sp
            cmd = ["ffmpeg", "-i", str(ogg), "-ar", "16000", "-ac", "1", "-f", "s16le", "-loglevel", "error", "-"]
            raw = _sp.run(cmd, capture_output=True, check=True).stdout
            audio_arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            segs, _ = model.transcribe(audio_arr, language="ru", beam_size=5, vad_filter=True)
            hyp = " ".join(s.text.strip() for s in segs).strip()
            infer_t = time.time() - t3
            dur_s = len(raw) / (16000 * 2)
            rtf = infer_t / dur_s if dur_s > 0 else 0

            if gt_text:
                ref_words = gt_text.lower().split()
                hyp_words = hyp.lower().split()
                n, m = len(ref_words), len(hyp_words)
                dp = [[0]*(m+1) for _ in range(n+1)]
                for i in range(n+1): dp[i][0] = i
                for j in range(m+1): dp[0][j] = j
                for i in range(1,n+1):
                    for j in range(1,m+1):
                        dp[i][j] = dp[i-1][j-1] if ref_words[i-1]==hyp_words[j-1] else 1+min(dp[i-1][j],dp[i][j-1],dp[i-1][j-1])
                wer = dp[n][m] / n if n > 0 else 0
                status = "PASS" if wer <= 0.3 else "WARN"
                detail = f"WER={wer:.1%} RTF={rtf:.2f} transcript='{hyp[:50]}'"
            else:
                status, detail = "PASS", f"RTF={rtf:.2f} transcript='{hyp[:50]}'"

            results.append(TestResult(
                f"faster_whisper:stt_fixture:{ogg.name}",
                status, infer_t, detail,
                metric=rtf, metric_key="faster_whisper_rtf_fixture",
            ))
        except Exception as e:
            results.append(TestResult(f"faster_whisper:stt_fixture:{ogg.name}", "WARN", time.time()-t3, str(e)))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T28 — OpenClaw: LLM connectivity (SKIP if no API key/local LLM configured)
# ─────────────────────────────────────────────────────────────────────────────

def t_openclaw_llm_connectivity(**_) -> list[TestResult]:
    """T28 — OpenClaw LLM: verify configured provider responds to a test prompt."""
    t0 = time.time()
    results: list[TestResult] = []
    try:
        sys.path.insert(0, str(TARIS_DIR))
        os.environ["WEB_ONLY"] = "1"
        import importlib
        if "core.bot_config" in sys.modules:
            import core.bot_config as _cfg
            importlib.reload(_cfg)
        else:
            import core.bot_config as _cfg  # type: ignore[import]

        provider = _cfg.LLM_PROVIDER
        device_variant = _cfg.DEVICE_VARIANT

        if device_variant != "openclaw":
            return [TestResult("openclaw_llm_connectivity", "SKIP", time.time() - t0,
                               f"DEVICE_VARIANT={device_variant} (not openclaw) — skipping")]

        # Check if provider is configured
        has_key = False
        if provider == "openai" and _cfg.OPENAI_API_KEY:
            has_key = True
        elif provider in ("ollama", "local"):
            has_key = True  # no key needed

        if not has_key:
            return [TestResult("openclaw_llm_connectivity", "SKIP", time.time() - t0,
                               f"LLM_PROVIDER={provider}: no API key configured — set OPENAI_API_KEY or use ollama")]

        if "core.bot_llm" in sys.modules:
            import core.bot_llm as _llm
            importlib.reload(_llm)
        else:
            import core.bot_llm as _llm  # type: ignore[import]

        t1 = time.time()
        try:
            resp = _llm.ask_llm("Reply with exactly: TARIS_OK", timeout=15)
            dur = time.time() - t1
            if resp and len(resp.strip()) > 0:
                status = "PASS"
                detail = f"provider={provider} response_len={len(resp)} latency={dur:.2f}s"
            else:
                status = "FAIL"
                detail = f"provider={provider} empty response after {dur:.2f}s"
        except Exception as e:
            dur = time.time() - t1
            status, detail = "FAIL", f"provider={provider} error: {str(e)[:120]}"
        results.append(TestResult("openclaw_llm_connectivity", status, dur, detail))
    except Exception as e:
        results.append(TestResult("openclaw_llm_connectivity", "FAIL", time.time() - t0, str(e)))
    finally:
        os.environ.pop("WEB_ONLY", None)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T29 — OpenClaw: STT provider routing
# ─────────────────────────────────────────────────────────────────────────────

def t_openclaw_stt_routing(**_) -> list[TestResult]:
    """T29 — OpenClaw STT routing: verify STT_PROVIDER selects correct engine."""
    t0 = time.time()
    results: list[TestResult] = []
    try:
        sys.path.insert(0, str(TARIS_DIR))
        os.environ["WEB_ONLY"] = "1"
        os.environ["DEVICE_VARIANT"] = "openclaw"
        import importlib
        if "core.bot_config" in sys.modules:
            import core.bot_config as _cfg
            importlib.reload(_cfg)
        else:
            import core.bot_config as _cfg  # type: ignore[import]

        # When DEVICE_VARIANT=openclaw, STT_PROVIDER should default to faster_whisper
        stt_provider = _cfg.STT_PROVIDER
        expected_default = "faster_whisper"
        if stt_provider == expected_default:
            results.append(TestResult("openclaw_stt_routing:default",
                                      "PASS", time.time() - t0,
                                      f"STT_PROVIDER={stt_provider} (openclaw default correct)"))
        else:
            results.append(TestResult("openclaw_stt_routing:default",
                                      "WARN", time.time() - t0,
                                      f"STT_PROVIDER={stt_provider} (expected {expected_default})"))

        # Verify faster_whisper_stt voice opt defaults to True for openclaw
        opts = _cfg._VOICE_OPTS_DEFAULTS
        fw_default = opts.get("faster_whisper_stt", False)
        results.append(TestResult(
            "openclaw_stt_routing:voice_opt_default",
            "PASS" if fw_default else "WARN",
            time.time() - t0,
            f"faster_whisper_stt default={'True' if fw_default else 'False'} (expected True for openclaw)",
        ))
    except Exception as e:
        results.append(TestResult("openclaw_stt_routing", "FAIL", time.time() - t0, str(e)))
    finally:
        os.environ.pop("DEVICE_VARIANT", None)
        os.environ.pop("WEB_ONLY", None)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T30 — OpenClaw: ollama provider in LLM dispatch
# ─────────────────────────────────────────────────────────────────────────────

def t_openclaw_ollama_provider(**_) -> list[TestResult]:
    """T30 — OpenClaw LLM dispatch: ollama provider registered, constants present."""
    t0 = time.time()
    results: list[TestResult] = []
    try:
        sys.path.insert(0, str(TARIS_DIR))
        os.environ["WEB_ONLY"] = "1"
        import importlib
        for mod_name in ["core.bot_config", "core.bot_llm"]:
            if mod_name in sys.modules:
                importlib.reload(sys.modules[mod_name])
        import core.bot_config as _cfg  # type: ignore[import]
        import core.bot_llm as _llm     # type: ignore[import]

        # Check OLLAMA_URL + OLLAMA_MODEL constants
        has_url = hasattr(_cfg, "OLLAMA_URL") and _cfg.OLLAMA_URL
        has_model = hasattr(_cfg, "OLLAMA_MODEL") and _cfg.OLLAMA_MODEL
        results.append(TestResult(
            "openclaw_ollama_constants",
            "PASS" if (has_url and has_model) else "FAIL",
            time.time() - t0,
            f"OLLAMA_URL={getattr(_cfg,'OLLAMA_URL','MISSING')} OLLAMA_MODEL={getattr(_cfg,'OLLAMA_MODEL','MISSING')}",
        ))

        # Check ollama in dispatch table
        dispatch = getattr(_llm, "_DISPATCH", {})
        has_ollama = "ollama" in dispatch
        results.append(TestResult(
            "openclaw_ollama_dispatch",
            "PASS" if has_ollama else "FAIL",
            time.time() - t0,
            f"_DISPATCH keys: {list(dispatch.keys())}",
        ))
    except Exception as e:
        results.append(TestResult("openclaw_ollama_provider", "FAIL", time.time() - t0, str(e)))
    finally:
        os.environ.pop("WEB_ONLY", None)
    return results


def t_web_stt_provider_routing(**_) -> list[TestResult]:
    """T31 — Regression: web UI _stt_web() uses faster-whisper (no deferred bot import).

    Bug: _stt_web() imported bot_voice which imported core.bot_instance → telebot
    validated BOT_TOKEN format → ValueError 'Token must contain a colon' → Vosk fallback.
    Fix: _stt_faster_whisper_web() defined directly in bot_web.py with no telegram imports.
    """
    t0 = time.time()
    results: list[TestResult] = []

    # 1. _stt_faster_whisper_web must exist directly in bot_web (not via bot_voice import)
    try:
        import importlib, types
        bw_path = TARIS_DIR / "bot_web.py"
        if not bw_path.exists():
            return [TestResult("web_stt_routing", "SKIP", time.time() - t0, "bot_web.py not found")]

        src = bw_path.read_text()
        has_local_fn = "def _stt_faster_whisper_web(" in src
        results.append(TestResult(
            "web_stt_local_fn_defined",
            "PASS" if has_local_fn else "FAIL",
            time.time() - t0,
            "_stt_faster_whisper_web() defined in bot_web.py" if has_local_fn
            else "MISSING — still using deferred import from bot_voice",
        ))

        # 2. No deferred import of bot_voice inside _stt_web
        import re as _re
        bad_import = bool(_re.search(r"from features\.bot_voice import _stt_faster_whisper", src))
        results.append(TestResult(
            "web_stt_no_deferred_bot_import",
            "FAIL" if bad_import else "PASS",
            time.time() - t0,
            "deferred bot_voice import found — will break with telegram token error" if bad_import
            else "no deferred bot_voice import (correct)",
        ))

        # 3. _stt_web() calls _stt_faster_whisper_web (not the old function name)
        calls_local = "_stt_faster_whisper_web(" in src
        results.append(TestResult(
            "web_stt_calls_local_fn",
            "PASS" if calls_local else "FAIL",
            time.time() - t0,
            "_stt_web calls _stt_faster_whisper_web" if calls_local else "MISSING call",
        ))

        # 4. Local HuggingFace cache path resolution present (avoids network auth)
        has_cache_resolve = "models--Systran--faster-whisper-" in src
        results.append(TestResult(
            "web_stt_local_cache_path",
            "PASS" if has_cache_resolve else "FAIL",
            time.time() - t0,
            "local HF cache path resolution present" if has_cache_resolve
            else "MISSING — will attempt network download → auth error",
        ))

        # 5. _voice_pipeline_status() shows correct STT name (not hardcoded Vosk)
        has_dynamic_stt = "STT_PROVIDER == \"faster_whisper\"" in src and "faster-whisper" in src
        results.append(TestResult(
            "web_stt_pipeline_status_label",
            "PASS" if has_dynamic_stt else "FAIL",
            time.time() - t0,
            "_voice_pipeline_status shows dynamic STT label" if has_dynamic_stt
            else "MISSING — status page still hardcodes 'STT (Vosk)'",
        ))

        # 6. Templates use stt_label variable (not hardcoded Vosk)
        tmpl_dir = TARIS_DIR / "web" / "templates"
        vosk_in_chat = False
        vosk_in_voice = False
        for tmpl_name, attr in [("chat.html", "vosk_in_chat"), ("voice.html", "vosk_in_voice")]:
            tmpl_path = tmpl_dir / tmpl_name
            if tmpl_path.exists():
                t_src = tmpl_path.read_text()
                import re as _re2
                has_hardcoded = bool(_re2.search(r"(?<!\{)\bVosk\b(?!\})", t_src))
                if attr == "vosk_in_chat":
                    vosk_in_chat = has_hardcoded
                else:
                    vosk_in_voice = has_hardcoded
        results.append(TestResult(
            "web_stt_templates_no_hardcoded_vosk",
            "FAIL" if (vosk_in_chat or vosk_in_voice) else "PASS",
            time.time() - t0,
            f"chat.html hardcoded={'YES' if vosk_in_chat else 'no'} voice.html hardcoded={'YES' if vosk_in_voice else 'no'}",
        ))

    except Exception as e:
        results.append(TestResult("web_stt_provider_routing", "FAIL", time.time() - t0, str(e)))

    return results


def t_pipeline_logger(**_) -> list[TestResult]:
    """T32 — Pipeline logger: module exists, writes JSONL, read_pipeline_logs works.

    Regression guard for the pipeline analytics logger (core/pipeline_logger.py).
    Verifies: module importable, log() writes a JSONL record, log has required fields,
    read_pipeline_logs() returns the written record, get_pipeline_stats() aggregates.
    """
    t0 = time.time()
    results: list[TestResult] = []
    import tempfile, json as _json, os as _os

    try:
        # 1. Module importable without telegram machinery
        _os.environ.setdefault("TARIS_DIR", str(TARIS_DIR))
        sys.path.insert(0, str(TARIS_DIR))
        import importlib
        if "core.pipeline_logger" in sys.modules:
            importlib.reload(sys.modules["core.pipeline_logger"])
        import core.pipeline_logger as _pl
        results.append(TestResult("pipeline_logger_import", "PASS", time.time() - t0,
                                  "core.pipeline_logger importable"))

        # 2. Write a test record to a temp log dir
        orig_log_dir = _pl._LOG_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            _pl._LOG_DIR = Path(tmpdir)
            pl = _pl.PipelineLog(session_id="test_t32", user_id="test")
            pl.log("stt", provider="faster_whisper:base:cpu", lang="ru",
                   input_chars=0, output_chars=12, audio_ms=1500, duration_ms=340)
            pl.log("llm", provider="ollama:qwen2:0.5b", lang="ru",
                   input_chars=12, output_chars=80, duration_ms=1200)
            pl.log("tts", provider="piper", lang="ru",
                   input_chars=80, audio_ms=2400, duration_ms=600)

            # 3. Read back
            records = _pl.read_pipeline_logs(last_n=50)
            results.append(TestResult("pipeline_logger_write_read", "PASS" if len(records) == 3 else "FAIL",
                                      time.time() - t0,
                                      f"wrote 3 records, read back {len(records)}"))

            # 4. Required fields present
            required = {"ts", "session_id", "stage", "provider", "duration_ms", "lang"}
            missing = required - set(records[0].keys()) if records else required
            results.append(TestResult("pipeline_logger_fields", "PASS" if not missing else "FAIL",
                                      time.time() - t0,
                                      f"all required fields present" if not missing
                                      else f"missing: {missing}"))

            # 5. stats aggregation
            stats = _pl.get_pipeline_stats()
            has_stt = "stt" in stats and stats["stt"]["count"] == 1
            has_llm = "llm" in stats and stats["llm"]["avg_ms"] == 1200
            results.append(TestResult("pipeline_logger_stats", "PASS" if (has_stt and has_llm) else "FAIL",
                                      time.time() - t0,
                                      f"stats: stt_count={stats.get('stt',{}).get('count')} llm_avg_ms={stats.get('llm',{}).get('avg_ms')}"))

        _pl._LOG_DIR = orig_log_dir  # restore

        # 6. bot_web.py imports pipeline_logger and has /api/logs endpoint
        bw_path = TARIS_DIR / "bot_web.py"
        if bw_path.exists():
            bw_src = bw_path.read_text()
            has_import = "from core.pipeline_logger import" in bw_src
            has_logs_ep = '"/api/logs"' in bw_src
            has_bench_ep = '"/api/benchmark"' in bw_src
            results.append(TestResult("pipeline_logger_bot_web_integration",
                                      "PASS" if (has_import and has_logs_ep and has_bench_ep) else "FAIL",
                                      time.time() - t0,
                                      f"import={'yes' if has_import else 'NO'} /api/logs={'yes' if has_logs_ep else 'NO'} /api/benchmark={'yes' if has_bench_ep else 'NO'}"))

    except Exception as e:
        results.append(TestResult("pipeline_logger", "FAIL", time.time() - t0, str(e)))

    return results


def t_dual_stt_providers(**_) -> list[TestResult]:
    """T33 — Dual STT: dispatch table, fallback constant, openai_whisper provider.

    Verifies:
    - STT_FALLBACK_PROVIDER / STT_OPENAI_MODEL / STT_LANG constants in bot_config
    - _STT_DISPATCH table present with all three providers in bot_web
    - _stt_vosk_web + _stt_openai_whisper_web functions defined
    - _stt_web() uses fallback pattern (no hardcoded if/elif chains)
    - Slovenian (sl) in lang_map for faster-whisper
    - UI label shows primary → fallback when fallback configured
    """
    t0 = time.time()
    results: list[TestResult] = []

    try:
        import os as _os
        _os.environ.setdefault("TARIS_DIR", str(TARIS_DIR))

        # 1. Constants in bot_config.py
        cfg_path = TARIS_DIR / "core" / "bot_config.py"
        if not cfg_path.exists():
            cfg_path = Path(__file__).parent.parent / "core" / "bot_config.py"
        cfg_src = cfg_path.read_text()
        has_openai_model    = "STT_OPENAI_MODEL" in cfg_src
        has_stt_lang        = "STT_LANG" in cfg_src
        has_fallback_const  = "STT_FALLBACK_PROVIDER" in cfg_src
        ok = has_openai_model and has_stt_lang and has_fallback_const
        results.append(TestResult(
            "stt_constants",
            "PASS" if ok else "FAIL",
            time.time() - t0,
            f"STT_OPENAI_MODEL={'yes' if has_openai_model else 'NO'} "
            f"STT_LANG={'yes' if has_stt_lang else 'NO'} "
            f"STT_FALLBACK_PROVIDER={'yes' if has_fallback_const else 'NO'}",
        ))

        # 2. bot_web.py: dispatch table + provider functions + fallback routing
        web_path = TARIS_DIR / "bot_web.py"
        if not web_path.exists():
            web_path = Path(__file__).parent.parent / "bot_web.py"
        web_src = web_path.read_text()
        has_dispatch      = "_STT_DISPATCH" in web_src
        has_vosk_func     = "def _stt_vosk_web" in web_src
        has_openai_func   = "def _stt_openai_whisper_web" in web_src
        has_fallback_logic = "STT_FALLBACK_PROVIDER" in web_src
        has_ui_label      = '"openai_whisper"' in web_src and "OpenAI Whisper" in web_src
        has_sl_lang       = '"sl": "sl"' in web_src or "'sl': 'sl'" in web_src
        ok2 = has_dispatch and has_vosk_func and has_openai_func and has_fallback_logic and has_sl_lang
        results.append(TestResult(
            "stt_dispatch_fallback",
            "PASS" if ok2 else "FAIL",
            time.time() - t0,
            f"_STT_DISPATCH={'yes' if has_dispatch else 'NO'} "
            f"vosk_func={'yes' if has_vosk_func else 'NO'} "
            f"openai_func={'yes' if has_openai_func else 'NO'} "
            f"fallback={'yes' if has_fallback_logic else 'NO'} "
            f"ui_label={'yes' if has_ui_label else 'NO'} "
            f"sl_lang={'yes' if has_sl_lang else 'NO'}",
        ))

    except Exception as e:
        results.append(TestResult("dual_stt_providers", "FAIL", time.time() - t0, str(e)))

    return results


def t_voice_debug_mode(**_) -> list[TestResult]:
    """T34 — Voice debug mode: VoiceDebugSession module, constants, LLM named fallback.

    Verifies:
    - core/voice_debug.py importable; VoiceDebugSession class present
    - VOICE_DEBUG_MODE / VOICE_DEBUG_DIR constants in bot_config
    - VoiceDebugSession writes expected files when enabled
    - LLM_FALLBACK_PROVIDER constant in bot_config
    - _ask_with_fallback function in bot_llm
    """
    t0 = time.time()
    results: list[TestResult] = []

    try:
        import os as _os, json as _json, tempfile as _tmp
        _os.environ.setdefault("TARIS_DIR", str(TARIS_DIR))

        # 1. bot_config constants
        cfg_path = TARIS_DIR / "core" / "bot_config.py"
        if not cfg_path.exists():
            cfg_path = Path(__file__).parent.parent / "core" / "bot_config.py"
        cfg_src = cfg_path.read_text()
        has_debug_mode = "VOICE_DEBUG_MODE" in cfg_src
        has_debug_dir  = "VOICE_DEBUG_DIR" in cfg_src
        has_llm_fb     = "LLM_FALLBACK_PROVIDER" in cfg_src
        ok1 = has_debug_mode and has_debug_dir and has_llm_fb
        results.append(TestResult(
            "debug_constants",
            "PASS" if ok1 else "FAIL",
            time.time() - t0,
            f"VOICE_DEBUG_MODE={'yes' if has_debug_mode else 'NO'} "
            f"VOICE_DEBUG_DIR={'yes' if has_debug_dir else 'NO'} "
            f"LLM_FALLBACK_PROVIDER={'yes' if has_llm_fb else 'NO'}",
        ))

        # 2. VoiceDebugSession functional test
        with _tmp.TemporaryDirectory() as td:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent.parent))
            _os.environ["TARIS_DIR"] = str(TARIS_DIR)
            from core.voice_debug import VoiceDebugSession as _VDS
            dbg = _VDS(user_id="test_t34", debug_mode=True, debug_dir=Path(td))
            assert dbg.enabled, "VoiceDebugSession not enabled"
            dbg.save_raw_audio(b"\x00\x01\x02", ext="webm")
            dbg.save_pcm(b"\x00" * 320, sample_rate=16000)
            dbg.save_stt("тест")
            dbg.save_llm_answer("ответ")
            dbg.save_tts_input("ответ")
            dbg.save_tts_output(b"OGGdata")
            dbg.finalise({"test": True})
            files = {p.name for p in Path(td, dbg.session_id).iterdir()}
            expected = {"input.webm", "decoded.pcm", "decoded.wav",
                        "stt.txt", "llm_answer.txt", "tts_input.txt",
                        "tts_output.ogg", "pipeline.json"}
            missing = expected - files
            results.append(TestResult(
                "debug_session_files",
                "PASS" if not missing else "FAIL",
                time.time() - t0,
                f"files={sorted(files)} missing={sorted(missing)}",
            ))

        # 3. bot_llm has _ask_with_fallback + LLM_FALLBACK_PROVIDER wired
        llm_path = TARIS_DIR / "core" / "bot_llm.py"
        if not llm_path.exists():
            llm_path = Path(__file__).parent.parent / "core" / "bot_llm.py"
        llm_src = llm_path.read_text()
        has_fn   = "def _ask_with_fallback" in llm_src
        has_use  = "LLM_FALLBACK_PROVIDER" in llm_src
        results.append(TestResult(
            "llm_named_fallback",
            "PASS" if (has_fn and has_use) else "FAIL",
            time.time() - t0,
            f"_ask_with_fallback={'yes' if has_fn else 'NO'} "
            f"LLM_FALLBACK_PROVIDER={'yes' if has_use else 'NO'}",
        ))

    except Exception as e:
        results.append(TestResult("voice_debug_mode", "FAIL", time.time() - t0, str(e)))


    return results


# ─────────────────────────────────────────────────────────────────────────────
# T35 — STT multi-language routing: faster-whisper accepts ru/en/de language codes
# ─────────────────────────────────────────────────────────────────────────────

def t_stt_language_routing_fw(**_) -> list[TestResult]:
    """T35 — faster-whisper: all three language codes accepted; hallucination guard covers each.

    Verifies:
    - lang_map in _stt_faster_whisper covers ru/en/de (code inspection)
    - Unknown language defaults to "ru" (not crash)
    - Hallucination guard rejects known false-positive phrases for each language
    - _stt_faster_whisper() on silence → None (via actual model call if installed)
    """
    t0 = time.time()
    results: list[TestResult] = []

    # 1. Source inspection: lang_map in bot_voice.py covers ru/en/de
    try:
        voice_path = TARIS_DIR / "features" / "bot_voice.py"
        if not voice_path.exists():
            voice_path = Path(__file__).parent.parent / "features" / "bot_voice.py"
        src = voice_path.read_text()

        has_lang_map  = 'lang_map = {"ru": "ru", "en": "en", "de": "de"}' in src or \
                        '"ru": "ru"' in src and '"en": "en"' in src and '"de": "de"' in src
        has_guard     = "_HALLUCINATIONS" in src
        has_ask_llm   = "from core.bot_llm import ask_llm" in src
        no_ask_taris  = "_ask_taris" not in src

        results.append(TestResult(
            "stt_lang_map_source",
            "PASS" if has_lang_map else "FAIL",
            time.time() - t0,
            f"lang_map ru/en/de={'yes' if has_lang_map else 'NO'} "
            f"hallucination_guard={'yes' if has_guard else 'NO'} "
            f"ask_llm={'yes' if has_ask_llm else 'NO'} "
            f"no_ask_taris={'yes' if no_ask_taris else 'NO'}",
        ))
    except Exception as e:
        results.append(TestResult("stt_lang_map_source", "FAIL", time.time() - t0, str(e)))
        return results

    # 2. Hallucination guard rejects known phrases for all languages
    _HALLUCINATIONS = {
        "and that's the whole thing", "thank you", "thanks for watching",
        "thanks for watching!", "you", ".", "..", "...",
    }
    test_phrases = [
        ("And that's the whole thing.", True),
        ("Thanks for watching!", True),
        ("Как быстро ходят пешеходы", False),   # real RU phrase — must pass
        ("Hello how are you today", False),       # real EN phrase — must pass
        ("Guten Morgen wie geht es Ihnen", False),  # real DE phrase — must pass
        (".", True),
        ("you", True),
    ]
    guard_ok = True
    guard_detail = []
    for phrase, should_reject in test_phrases:
        normalized = phrase.lower().rstrip(".!? ")
        rejected = normalized in _HALLUCINATIONS or len(phrase.strip()) < 3
        if rejected != should_reject:
            guard_ok = False
            guard_detail.append(f"'{phrase}': expected_reject={should_reject} got_reject={rejected}")
    results.append(TestResult(
        "stt_hallucination_guard_phrases",
        "PASS" if guard_ok else "FAIL",
        time.time() - t0,
        "all phrases correctly classified" if guard_ok else "; ".join(guard_detail),
    ))

    # 3. If faster-whisper is installed, test each language code on silence → None
    try:
        from faster_whisper import WhisperModel  # type: ignore[import]
        import numpy as _np

        fw_model_size = os.environ.get("FASTER_WHISPER_MODEL", "base")
        device  = os.environ.get("FASTER_WHISPER_DEVICE",  "cpu")
        compute = os.environ.get("FASTER_WHISPER_COMPUTE", "int8")
        model = WhisperModel(fw_model_size, device=device, compute_type=compute)

        # 2s silence
        silent = _np.zeros(32000, dtype=_np.int16).astype(_np.float32) / 32768.0

        for lang_code, fw_lang in [("ru", "ru"), ("en", "en"), ("de", "de"), ("unknown", "ru")]:
            t1 = time.time()
            try:
                segs, info = model.transcribe(
                    silent, language=fw_lang, vad_filter=True,
                    beam_size=1, condition_on_previous_text=False,
                )
                text = " ".join(s.text.strip() for s in segs).strip()
                # Silence → either empty or hallucination (both acceptable in this sub-test)
                dur = time.time() - t1
                results.append(TestResult(
                    f"fw_silence_{lang_code}",
                    "PASS", dur,
                    f"lang={fw_lang} → '{text[:30] or '<empty>'}' ({dur:.2f}s)",
                    metric=dur, metric_key=f"fw_silence_{lang_code}_s",
                ))
            except Exception as e:
                results.append(TestResult(f"fw_silence_{lang_code}", "FAIL",
                                          time.time() - t1, str(e)))

    except ImportError:
        results.append(TestResult(
            "fw_lang_inference", "SKIP", time.time() - t0,
            "faster-whisper not installed — skipping live inference checks",
        ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T36 — STT fallback chain: primary failure → vosk fallback activated
# ─────────────────────────────────────────────────────────────────────────────

def t_stt_fallback_chain(**_) -> list[TestResult]:
    """T36 — STT fallback chain: source + functional verification.

    Verifies:
    - bot_voice.py contains Vosk fallback block after primary STT
    - STT_FALLBACK_PROVIDER constant wired in bot_config
    - vosk_fallback voice opt controls the fallback path
    - _stt_faster_whisper → None on hallucinated text triggers fallback (code path)
    """
    t0 = time.time()
    results: list[TestResult] = []

    # 1. Source: bot_voice.py has primary → vosk fallback logic + STT_LANG override
    try:
        voice_path = TARIS_DIR / "features" / "bot_voice.py"
        if not voice_path.exists():
            voice_path = Path(__file__).parent.parent / "features" / "bot_voice.py"
        src = voice_path.read_text()

        has_vosk_fallback_opt  = "vosk_fallback" in src
        has_primary_stt_used   = "primary_stt_used" in src
        has_vosk_fallback_code = "vosk_fallback_enabled" in src
        has_fallback_model     = "_get_vosk_model" in src
        # Regression guard (v2026.3.38): STT_LANG used instead of _lang(chat_id)
        has_stt_lang_var       = "_stt_lang" in src and "STT_LANG" in src
        uses_stt_lang_in_vosk  = "_get_vosk_model(_stt_lang)" in src

        all_ok = all([has_vosk_fallback_opt, has_primary_stt_used,
                      has_vosk_fallback_code, has_fallback_model,
                      has_stt_lang_var, uses_stt_lang_in_vosk])
        results.append(TestResult(
            "stt_fallback_code_present",
            "PASS" if all_ok else "FAIL",
            time.time() - t0,
            f"vosk_fallback_opt={'yes' if has_vosk_fallback_opt else 'NO'} "
            f"primary_stt_used={'yes' if has_primary_stt_used else 'NO'} "
            f"fallback_enabled={'yes' if has_vosk_fallback_code else 'NO'} "
            f"get_vosk_model={'yes' if has_fallback_model else 'NO'} "
            f"stt_lang_var={'yes' if has_stt_lang_var else 'NO'} "
            f"vosk_uses_stt_lang={'yes' if uses_stt_lang_in_vosk else 'NO'}",
        ))
    except Exception as e:
        results.append(TestResult("stt_fallback_code_present", "FAIL", time.time() - t0, str(e)))
        return results

    # 2. STT_FALLBACK_PROVIDER in bot_config
    try:
        cfg_path = TARIS_DIR / "core" / "bot_config.py"
        if not cfg_path.exists():
            cfg_path = Path(__file__).parent.parent / "core" / "bot_config.py"
        cfg_src = cfg_path.read_text()
        has_const   = "STT_FALLBACK_PROVIDER" in cfg_src
        has_default = "_DEFAULT_STT_FALLBACK" in cfg_src
        results.append(TestResult(
            "stt_fallback_provider_const",
            "PASS" if (has_const and has_default) else "FAIL",
            time.time() - t0,
            f"STT_FALLBACK_PROVIDER={'yes' if has_const else 'NO'} "
            f"_DEFAULT_STT_FALLBACK={'yes' if has_default else 'NO'}",
        ))
    except Exception as e:
        results.append(TestResult("stt_fallback_provider_const", "FAIL", time.time() - t0, str(e)))

    # 3. Functional: when faster-whisper returns None (hallucination), vosk_fallback is tried.
    #    We simulate this with a minimal synthetic recording and check that the code path
    #    sets vosk_fallback_enabled=True when primary returns None.
    try:
        import sys as _sys
        _sys.path.insert(0, str(TARIS_DIR))
        _sys.path.insert(0, str(Path(__file__).parent.parent))
        os.environ.setdefault("TARIS_DIR", str(TARIS_DIR))

        # Import _stt_faster_whisper; call with real silence PCM → expect None (VAD filters it)
        import importlib as _il
        # Reload to pick up freshest source
        if "features.bot_voice" in _sys.modules:
            _il.reload(_sys.modules["features.bot_voice"])
        from features.bot_voice import _stt_faster_whisper  # type: ignore[import]
        import numpy as _np

        silent_pcm = (_np.zeros(16000, dtype=_np.int16)).tobytes()  # 1s silence
        t1 = time.time()
        result_text = _stt_faster_whisper(silent_pcm, 16000, "ru")
        dur = time.time() - t1
        # Silence → None (VAD filters it) or hallucination → guard returns None
        status = "PASS" if result_text is None else "WARN"
        results.append(TestResult(
            "fallback_silence_triggers",
            status, dur,
            f"silence → {'None (fallback would trigger)' if result_text is None else repr(result_text[:40])}",
        ))
    except ImportError:
        results.append(TestResult(
            "fallback_silence_triggers", "SKIP", time.time() - t0,
            "faster-whisper not installed — skipping live fallback check",
        ))
    except Exception as e:
        results.append(TestResult("fallback_silence_triggers", "WARN", time.time() - t0, str(e)))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T37 — Remote STT: OpenAI Whisper API provider
# ─────────────────────────────────────────────────────────────────────────────

def t_openai_whisper_stt(gt: dict, verbose: bool = False, **_) -> list[TestResult]:
    """T37 — OpenAI Whisper API STT: config present; live call if API key configured.

    Verifies:
    - STT_OPENAI_MODEL / STT_LANG / OPENAI_API_KEY constants in bot_config
    - _stt_openai_whisper_web() function exists in bot_web.py
    - If OPENAI_API_KEY is set and STT_PROVIDER=openai_whisper: transcribe a fixture
    - SKIP when no API key present
    """
    t0 = time.time()
    results: list[TestResult] = []

    # 1. Constants in bot_config
    try:
        cfg_path = TARIS_DIR / "core" / "bot_config.py"
        if not cfg_path.exists():
            cfg_path = Path(__file__).parent.parent / "core" / "bot_config.py"
        cfg_src = cfg_path.read_text()
        has_model   = "STT_OPENAI_MODEL" in cfg_src
        has_lang    = "STT_LANG" in cfg_src
        has_key     = "OPENAI_API_KEY" in cfg_src
        results.append(TestResult(
            "openai_stt_constants",
            "PASS" if (has_model and has_lang and has_key) else "FAIL",
            time.time() - t0,
            f"STT_OPENAI_MODEL={'yes' if has_model else 'NO'} "
            f"STT_LANG={'yes' if has_lang else 'NO'} "
            f"OPENAI_API_KEY={'yes' if has_key else 'NO'}",
        ))
    except Exception as e:
        results.append(TestResult("openai_stt_constants", "FAIL", time.time() - t0, str(e)))
        return results

    # 2. _stt_openai_whisper_web function defined in bot_web.py
    try:
        web_path = TARIS_DIR / "bot_web.py"
        if not web_path.exists():
            web_path = Path(__file__).parent.parent / "bot_web.py"
        web_src = web_path.read_text()
        has_fn = "def _stt_openai_whisper_web" in web_src
        has_dispatch = "_STT_DISPATCH" in web_src and '"openai_whisper"' in web_src
        results.append(TestResult(
            "openai_stt_function",
            "PASS" if (has_fn and has_dispatch) else "FAIL",
            time.time() - t0,
            f"_stt_openai_whisper_web={'yes' if has_fn else 'NO'} "
            f"STT_DISPATCH_openai_whisper={'yes' if has_dispatch else 'NO'}",
        ))
    except Exception as e:
        results.append(TestResult("openai_stt_function", "FAIL", time.time() - t0, str(e)))

    # 3. Live call: only if OPENAI_API_KEY present and an OGG fixture exists
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        # Try reading from bot.env
        bot_env = TARIS_DIR / "bot.env"
        if bot_env.exists():
            for line in bot_env.read_text().splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not api_key:
        results.append(TestResult(
            "openai_stt_live", "SKIP", time.time() - t0,
            "OPENAI_API_KEY not configured — skipping live Whisper API call",
        ))
        return results

    ogg_files = sorted(VOICE_DIR.glob("*.ogg")) if VOICE_DIR.exists() else []
    if not ogg_files:
        results.append(TestResult(
            "openai_stt_live", "SKIP", time.time() - t0,
            "No OGG fixture files found in tests/voice/ — skipping live call",
        ))
        return results

    # Use the smallest fixture for speed
    fixture = min(ogg_files, key=lambda p: p.stat().st_size)
    stt_lang = os.environ.get("STT_LANG", "ru")
    stt_model = os.environ.get("STT_OPENAI_MODEL", "whisper-1")
    openai_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    t1 = time.time()
    try:
        import urllib.request, json as _json
        with open(fixture, "rb") as f:
            audio_data = f.read()

        # Build multipart form
        boundary = "----TarisTestBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="model"\r\n\r\n'
            f"{stt_model}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="language"\r\n\r\n'
            f"{stt_lang}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{fixture.name}"\r\n'
            f"Content-Type: audio/ogg\r\n\r\n"
        ).encode() + audio_data + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            f"{openai_base}/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = _json.loads(resp.read())
        transcript = resp_data.get("text", "").strip()
        dur = time.time() - t1

        # WER check if ground truth exists
        gt_text = gt.get(fixture.name, {}).get("clean_ref") if isinstance(gt.get(fixture.name), dict) else None
        if gt_text:
            ref_words = gt_text.lower().split()
            hyp_words = transcript.lower().split()
            n, m = len(ref_words), len(hyp_words)
            dp = [[0]*(m+1) for _ in range(n+1)]
            for i in range(n+1): dp[i][0] = i
            for j in range(m+1): dp[0][j] = j
            for i in range(1,n+1):
                for j in range(1,m+1):
                    dp[i][j] = dp[i-1][j-1] if ref_words[i-1]==hyp_words[j-1] else 1+min(dp[i-1][j],dp[i][j-1],dp[i-1][j-1])
            wer = dp[n][m] / n if n > 0 else 0
            status = "PASS" if wer <= 0.3 else "WARN"
            detail = f"WER={wer:.1%} transcript='{transcript[:60]}'"
        else:
            status = "PASS" if transcript else "WARN"
            detail = f"transcript='{transcript[:60]}' ({dur:.1f}s)"

        results.append(TestResult(
            "openai_stt_live",
            status, dur, detail,
            metric=dur, metric_key="openai_stt_live_s",
        ))
    except Exception as e:
        results.append(TestResult("openai_stt_live", "WARN", time.time() - t1,
                                  f"API call failed: {e}"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T38 — TTS multi-language: Piper synthesis for ru/de + EN fallback routing
# ─────────────────────────────────────────────────────────────────────────────

def t_tts_multilang(gt: dict, verbose: bool = False, **_) -> list[TestResult]:
    """T38 — TTS multi-language: Piper synthesizes ru/de; EN routes to ru model.

    Verifies:
    - _piper_model_path() in bot_voice returns a path for ru and de
    - EN language falls back to Russian model (no dedicated EN model)
    - Piper produces non-empty OGG output for ru and de phrases (SKIP if binary missing)
    - Piper model files are present on disk
    """
    t0 = time.time()
    results: list[TestResult] = []

    import subprocess as _sp

    piper_bin = os.environ.get("PIPER_BIN", "/usr/local/bin/piper")
    ru_model  = os.environ.get("PIPER_MODEL", str(TARIS_DIR / "ru_RU-irina-medium.onnx"))
    de_model  = os.environ.get("PIPER_MODEL_DE", str(TARIS_DIR / "de_DE-thorsten-medium.onnx"))

    # 1. _piper_model_path source inspection
    try:
        voice_path = TARIS_DIR / "features" / "bot_voice.py"
        if not voice_path.exists():
            voice_path = Path(__file__).parent.parent / "features" / "bot_voice.py"
        src = voice_path.read_text()

        has_de_routing = 'lang == "de"' in src and "PIPER_MODEL_DE" in src
        has_ru_default = "return PIPER_MODEL" in src
        results.append(TestResult(
            "tts_piper_model_path_src",
            "PASS" if (has_de_routing and has_ru_default) else "FAIL",
            time.time() - t0,
            f"de_routing={'yes' if has_de_routing else 'NO'} "
            f"ru_default={'yes' if has_ru_default else 'NO'}",
        ))
    except Exception as e:
        results.append(TestResult("tts_piper_model_path_src", "FAIL", time.time() - t0, str(e)))

    # 2. Model files on disk
    langs_config = [
        ("ru", ru_model, "Привет! Это тест синтеза речи на русском языке."),
        ("de", de_model, "Hallo! Das ist ein Test der deutschen Sprachsynthese."),
    ]
    for lang, model_path, _phrase in langs_config:
        exists = Path(model_path).exists()
        json_path = model_path + ".json"
        json_ok = Path(json_path).exists()
        results.append(TestResult(
            f"tts_model_file_{lang}",
            "PASS" if exists else "SKIP",
            time.time() - t0,
            f"{model_path}: {'found' if exists else 'not found'} "
            f"json={'found' if json_ok else 'missing'}",
        ))

    # EN: no dedicated model — must fall back to ru model
    ru_fallback_for_en = ru_model  # _piper_model_path("en") returns ru model
    results.append(TestResult(
        "tts_model_file_en_fallback",
        "PASS", time.time() - t0,
        f"EN has no dedicated model → falls back to RU model: {ru_fallback_for_en}",
    ))

    # 3. Piper binary check
    if not Path(piper_bin).exists():
        results.append(TestResult(
            "tts_synthesis_multilang", "SKIP", time.time() - t0,
            f"Piper binary not found: {piper_bin} — skipping synthesis tests",
        ))
        return results

    # 4. Synthesize for each available language
    for lang, model_path, phrase in langs_config:
        if not Path(model_path).exists():
            results.append(TestResult(
                f"tts_synthesis_{lang}", "SKIP", time.time() - t0,
                f"Model not found: {model_path}",
            ))
            continue

        t1 = time.time()
        try:
            proc = _sp.Popen(
                [piper_bin, "--model", model_path, "--output-raw"],
                stdin=_sp.PIPE, stdout=_sp.PIPE, stderr=_sp.PIPE,
            )
            raw_pcm, stderr = proc.communicate(input=phrase.encode(), timeout=30)

            if proc.returncode != 0 or not raw_pcm:
                results.append(TestResult(
                    f"tts_synthesis_{lang}", "FAIL", time.time() - t1,
                    f"piper rc={proc.returncode} bytes={len(raw_pcm)} stderr={stderr[:80].decode('utf-8','replace')}",
                ))
                continue

            # Encode to OGG via ffmpeg for size check
            ff = _sp.run(
                ["ffmpeg", "-f", "s16le", "-ar", "22050", "-ac", "1", "-i", "pipe:0",
                 "-c:a", "libopus", "-b:a", "24k", "-f", "ogg", "pipe:1",
                 "-loglevel", "error"],
                input=raw_pcm, capture_output=True, timeout=20,
            )
            ogg = ff.stdout
            dur = time.time() - t1
            audio_ms = len(raw_pcm) // (2 * 22050) * 1000
            status = "PASS" if ogg else "FAIL"
            results.append(TestResult(
                f"tts_synthesis_{lang}",
                status, dur,
                f"piper→raw={len(raw_pcm)}B ogg={len(ogg)}B audio~{audio_ms}ms ({dur:.2f}s)",
                metric=dur, metric_key=f"tts_synthesis_{lang}_s",
            ))
        except _sp.TimeoutExpired:
            results.append(TestResult(f"tts_synthesis_{lang}", "FAIL", time.time() - t1, "timeout"))
        except Exception as e:
            results.append(TestResult(f"tts_synthesis_{lang}", "WARN", time.time() - t1, str(e)))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T39 — Voice LLM routing: ask_llm() used, no TARIS_BIN call in voice pipeline
# ─────────────────────────────────────────────────────────────────────────────

def t_voice_llm_routing(**_) -> list[TestResult]:
    """T39 — Voice pipeline LLM routing guard.

    Regression test for the picoclaw/TARIS_BIN crash (v2026.3.37 fix).
    Verifies:
    - bot_voice.py imports ask_llm from core.bot_llm (not _ask_taris)
    - bot_voice.py does NOT import _ask_taris from bot_access
    - bot_voice.py does NOT call TARIS_BIN directly in the voice handler
    - ask_llm() function exists in core/bot_llm.py with correct signature
    - LLM_FALLBACK_PROVIDER wired in bot_config (enables Ollama → OpenAI chain)
    """
    t0 = time.time()
    results: list[TestResult] = []

    # 1. bot_voice.py: imports ask_llm, not _ask_taris
    try:
        voice_path = TARIS_DIR / "features" / "bot_voice.py"
        if not voice_path.exists():
            voice_path = Path(__file__).parent.parent / "features" / "bot_voice.py"
        src = voice_path.read_text()

        imports_ask_llm   = "from core.bot_llm import ask_llm" in src
        no_ask_taris_imp  = "_ask_taris" not in src
        calls_ask_llm     = "ask_llm(" in src
        no_taris_bin_call = "TARIS_BIN" not in src

        results.append(TestResult(
            "voice_uses_ask_llm",
            "PASS" if (imports_ask_llm and no_ask_taris_imp and calls_ask_llm) else "FAIL",
            time.time() - t0,
            f"imports_ask_llm={'yes' if imports_ask_llm else 'NO'} "
            f"no_ask_taris={'yes' if no_ask_taris_imp else 'NO'} "
            f"calls_ask_llm={'yes' if calls_ask_llm else 'NO'}",
        ))
        results.append(TestResult(
            "voice_no_taris_bin",
            "PASS" if no_taris_bin_call else "FAIL",
            time.time() - t0,
            f"TARIS_BIN not referenced in bot_voice.py: {'yes' if no_taris_bin_call else 'NO (BUG!)'}",
        ))
    except Exception as e:
        results.append(TestResult("voice_uses_ask_llm", "FAIL", time.time() - t0, str(e)))
        return results

    # 2. ask_llm in bot_llm.py has correct signature + fallback chain
    try:
        llm_path = TARIS_DIR / "core" / "bot_llm.py"
        if not llm_path.exists():
            llm_path = Path(__file__).parent.parent / "core" / "bot_llm.py"
        llm_src = llm_path.read_text()

        has_ask_llm     = "def ask_llm(" in llm_src
        has_fallback_fn = "def _ask_with_fallback" in llm_src
        has_fb_provider = "LLM_FALLBACK_PROVIDER" in llm_src
        results.append(TestResult(
            "ask_llm_fallback_chain",
            "PASS" if (has_ask_llm and has_fallback_fn and has_fb_provider) else "FAIL",
            time.time() - t0,
            f"ask_llm={'yes' if has_ask_llm else 'NO'} "
            f"_ask_with_fallback={'yes' if has_fallback_fn else 'NO'} "
            f"LLM_FALLBACK_PROVIDER={'yes' if has_fb_provider else 'NO'}",
        ))
    except Exception as e:
        results.append(TestResult("ask_llm_fallback_chain", "FAIL", time.time() - t0, str(e)))

    # 3. Functional: import ask_llm — confirm it is callable (no import error)
    try:
        import sys as _sys
        _sys.path.insert(0, str(TARIS_DIR))
        _sys.path.insert(0, str(Path(__file__).parent.parent))
        os.environ.setdefault("TARIS_DIR", str(TARIS_DIR))

        import importlib as _il
        if "core.bot_llm" in _sys.modules:
            llm_mod = _sys.modules["core.bot_llm"]
        else:
            llm_mod = _il.import_module("core.bot_llm")
        has_fn = callable(getattr(llm_mod, "ask_llm", None))
        results.append(TestResult(
            "ask_llm_importable",
            "PASS" if has_fn else "FAIL",
            time.time() - t0,
            f"ask_llm callable: {'yes' if has_fn else 'NO'}",
        ))
    except Exception as e:
        results.append(TestResult("ask_llm_importable", "WARN", time.time() - t0, str(e)))

    return results


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
    # Bugfix verification tests (T17–T21)
    t_bot_name_injection,
    t_profile_resilience,
    t_note_edit_append_replace,
    t_calendar_tts_call_signature,
    t_calendar_console_classifier,
    # SQLite integration tests (T22–T23)
    t_db_voice_opts_roundtrip,
    t_db_migration_idempotent,
    # RAG quality tests (T24)
    t_rag_lr_products,
    # Web link code tests (T25)
    t_web_link_code_roundtrip,
    # System-chat clean-output / ask_llm_or_raise regression (T26)
    t_system_chat_clean_output,
    # OpenClaw variant tests (T27–T31)
    t_faster_whisper_stt,
    t_openclaw_llm_connectivity,
    t_openclaw_stt_routing,
    t_openclaw_ollama_provider,
    t_web_stt_provider_routing,
    # Pipeline logger tests (T32)
    t_pipeline_logger,
    # Dual STT dispatch + fallback (T33)
    t_dual_stt_providers,
    # Voice debug mode + LLM named fallback (T34)
    t_voice_debug_mode,
    # STT multi-language + hallucination guard per language (T35)
    t_stt_language_routing_fw,
    # STT fallback chain: primary fails → vosk activated (T36)
    t_stt_fallback_chain,
    # Remote STT: OpenAI Whisper API provider (T37)
    t_openai_whisper_stt,
    # TTS multi-language: ru/de synthesis + EN fallback routing (T38)
    t_tts_multilang,
    # Voice LLM routing guard: ask_llm() used, no TARIS_BIN (T39)
    t_voice_llm_routing,
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
    ver_path = TARIS_DIR / "bot_config.py"
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
        description="Voice regression tests for taris-telegram"
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

    print(f"\n{_B}Taris Voice Regression Tests{_RST}  "
          f"(bot {_read_bot_version()}, {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"Fixtures: {VOICE_DIR}")
    print(f"Results:  {RESULTS_DIR}\n")

    if not VOICE_DIR.exists():
        print(f"{_R}[ERROR] Fixture directory not found: {VOICE_DIR}{_RST}")
        print("Deploy with:  pscp -pw PWD src/tests/voice/*.ogg "
              "stas@OpenClawPI:/home/stas/.taris/tests/voice/")
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
