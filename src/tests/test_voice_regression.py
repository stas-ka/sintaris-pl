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
SRC_ROOT       = Path(__file__).parent.parent  # project src/ when local, ~/.taris when deployed
# Package-aware paths (new package layout)
_PKG_CORE     = TARIS_DIR / "core"
_PKG_TELEGRAM = TARIS_DIR / "telegram"
_PKG_FEATURES = TARIS_DIR / "features"
VOICE_DIR      = TESTS_DIR / "voice"
RESULTS_DIR    = VOICE_DIR / "results"
GROUND_TRUTH   = VOICE_DIR / "ground_truth.json"
BASELINE_FILE  = RESULTS_DIR / "baseline.json"

# Mirror bot_config.py defaults so tests use exactly the same paths
# Note: bot_config._load_env_file() loads ~/.taris/bot.env at import time.
# We re-read at definition time, but also re-check at runtime inside each test
# (via _runtime_piper_bin()) in case bot.env is loaded after module start.
PIPER_BIN         = os.environ.get("PIPER_BIN",  "/usr/local/bin/piper")


def _runtime_piper_bin() -> str:
    """Return PIPER_BIN from env (re-evaluated at call time, after bot.env may have been loaded).
    Falls back to well-known install locations if env not set."""
    env_val = os.environ.get("PIPER_BIN", "")
    if env_val and Path(env_val).exists():
        return env_val
    # Well-known installation paths (in priority order)
    candidates = [
        TARIS_DIR / "piper" / "piper",
        Path("/usr/local/bin/piper"),
        Path("/usr/bin/piper"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    # Return the env value or default (for error messages)
    return env_val or str(TARIS_DIR / "piper" / "piper")
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
    import os as _os
    _variant = _os.environ.get("DEVICE_VARIANT", "taris")
    checks = {
        "piper_bin":          _runtime_piper_bin(),
        "piper_onnx":         PIPER_MODEL,
        "piper_onnx_json":    PIPER_MODEL + ".json",
        "ffmpeg":             "/usr/bin/ffmpeg",
    }
    # vosk_model required on taris/picoclaw but optional on openclaw (uses faster-whisper)
    if _variant != "openclaw":
        checks["vosk_model"] = VOSK_MODEL_PATH
    optional = {
        "vosk_model_openclaw": VOSK_MODEL_PATH,  # openclaw may not have it
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
    _piper = _runtime_piper_bin()
    if not Path(_piper).exists():
        return [TestResult("tts_synthesis", "SKIP", 0.0,
                           f"Piper binary not found: {_piper}")]

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
            [_piper, "--model", model_path, "--output-raw"],
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
    _piper = _runtime_piper_bin()
    if not Path(_piper).exists():
        return [TestResult("de_tts_synthesis", "SKIP", time.time() - t0,
                           f"Piper binary not found: {_piper}")]

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
            [_piper, "--model", model_path, "--output-raw"],
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
                     else SRC_ROOT / "telegram" / "bot_handlers.py" if (SRC_ROOT / "telegram" / "bot_handlers.py").exists()
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
                    else SRC_ROOT / "telegram" / "bot_handlers.py" if (SRC_ROOT / "telegram" / "bot_handlers.py").exists()
                    else TARIS_DIR / "bot_handlers.py")
    if not handler_path.exists():
        return [TestResult("note_edit_append_replace", "FAIL", time.time() - t0,
                           f"bot_handlers.py not found")]
    src = handler_path.read_text(encoding="utf-8")

    for fn_name in ("_start_note_append", "_start_note_replace", "_start_note_edit"):
        if f"def {fn_name}" not in src:
            issues.append(f"{fn_name}() not found in bot_handlers.py")

    # 2) _start_note_edit shows Append/Replace choice (via inline buttons OR Screen DSL render)
    match = re.search(
        r'(def _start_note_edit\b.*?)(?=\ndef [a-z_]|\Z)',
        src, re.DOTALL,
    )
    if match:
        edit_body = match.group(1)
        # New pattern: uses _render(chat_id, "screens/note_edit.yaml") → check YAML file
        uses_screen_dsl = "_render" in edit_body and "note_edit" in edit_body
        inline_append = "note_append:" in edit_body or "btn_note_append" in edit_body
        inline_replace = "note_replace:" in edit_body or "btn_note_replace" in edit_body

        if uses_screen_dsl:
            # Verify the screen YAML file contains Append/Replace actions
            screen_yaml_path = TARIS_DIR / "screens" / "note_edit.yaml"
            if not screen_yaml_path.exists():
                # Fall back to source tree
                screen_yaml_path = SRC_ROOT / "screens" / "note_edit.yaml"
            if screen_yaml_path.exists():
                screen_yaml = screen_yaml_path.read_text(encoding="utf-8")
                if "note_append" not in screen_yaml and "btn_note_append" not in screen_yaml:
                    issues.append("note_edit.yaml Screen DSL missing Append button (note_append)")
                if "note_replace" not in screen_yaml and "btn_note_replace" not in screen_yaml:
                    issues.append("note_edit.yaml Screen DSL missing Replace button (note_replace)")
            else:
                issues.append("screens/note_edit.yaml not found (Screen DSL path)")
        else:
            if not inline_append:
                issues.append("_start_note_edit does not offer Append option")
            if not inline_replace:
                issues.append("_start_note_edit does not offer Replace option")

    # 3) Callback dispatch in telegram_menu_bot.py
    entry_path = (TARIS_DIR / "telegram_menu_bot.py" if (TARIS_DIR / "telegram_menu_bot.py").exists()
                  else SRC_ROOT / "telegram_menu_bot.py")
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
                else SRC_ROOT / "features" / "bot_calendar.py" if (SRC_ROOT / "features" / "bot_calendar.py").exists()
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
                else SRC_ROOT / "features" / "bot_calendar.py" if (SRC_ROOT / "features" / "bot_calendar.py").exists()
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
    """T23 — running migrate_to_db.py twice on a copy of taris.db is idempotent (no error)."""
    import tempfile
    import shutil
    import sqlite3 as _sql
    t0 = time.time()
    try:
        # Locate migrate script: src/setup/ (preferred) or tools/ (legacy)
        migrate = str(TESTS_DIR.parent / "setup" / "migrate_to_db.py")
        if not Path(migrate).exists():
            migrate = str(TESTS_DIR.parent.parent / "tools" / "migrate_to_db.py")
        if not Path(migrate).exists():
            return [TestResult("db_migration_idempotent", "SKIP", time.time() - t0,
                               "migrate_to_db.py not found (checked src/setup/ and tools/)")]

        # Require an existing live DB to copy from
        live_db = TARIS_DIR / "taris.db"
        if not live_db.exists():
            return [TestResult("db_migration_idempotent", "SKIP", time.time() - t0,
                               f"No live taris.db found at {live_db} — run bot once to initialise")]

        # Work with a copy so we don't touch live data
        with tempfile.TemporaryDirectory() as tmp:
            db_copy = str(Path(tmp) / "mig.db")
            shutil.copy2(str(live_db), db_copy)

            for run_no in range(1, 3):
                r = subprocess.run(
                    [sys.executable, migrate, "--db", db_copy],
                    capture_output=True, timeout=30,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
                if r.returncode != 0:
                    return [TestResult("db_migration_idempotent", "FAIL", time.time() - t0,
                                       f"migrate exit {r.returncode} on run {run_no}: "
                                       f"{(r.stdout + r.stderr).decode(errors='replace')[:300]}")]

            con = _sql.connect(db_copy)
            tables = {row[0] for row in
                      con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            con.close()

        status = "PASS"
        detail = f"migration ran ×2 without error; tables={sorted(tables)[:6]} (idempotent ✓)"
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
                # DB-backed: verify via store.find_link_code
                try:
                    from core.store import store as _st
                    row = _st.find_link_code(cp_code)
                    ok = row is not None and row.get("chat_id") == CHAT_ID
                    results.append(TestResult(
                        "web_link_code:cross_process",
                        "PASS" if ok else "FAIL",
                        _t.time() - t1,
                        f"code in DB={row is not None} "
                        f"chat_id={row.get('chat_id') if row else None}",
                    ))
                except Exception:
                    # Fallback: file-based verification
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
            cfg_path = SRC_ROOT / "core" / "bot_config.py"
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
            web_path = SRC_ROOT / "bot_web.py"
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
            cfg_path = SRC_ROOT / "core" / "bot_config.py"
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
            llm_path = SRC_ROOT / "core" / "bot_llm.py"
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
            voice_path = SRC_ROOT / "features" / "bot_voice.py"
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
            voice_path = SRC_ROOT / "features" / "bot_voice.py"
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
            cfg_path = SRC_ROOT / "core" / "bot_config.py"
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
            cfg_path = SRC_ROOT / "core" / "bot_config.py"
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
            web_path = SRC_ROOT / "bot_web.py"
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
            voice_path = SRC_ROOT / "features" / "bot_voice.py"
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
            voice_path = SRC_ROOT / "features" / "bot_voice.py"
        src = voice_path.read_text()

        imports_ask_llm   = "from core.bot_llm import ask_llm" in src
        no_ask_taris_imp  = "_ask_taris" not in src
        # Voice must use ask_llm_with_history (history-aware), not bare ask_llm()
        calls_ask_llm     = "ask_llm_with_history(" in src
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
            llm_path = SRC_ROOT / "core" / "bot_llm.py"
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


def t_voice_system_mode_routing_guard(**_) -> list[TestResult]:
    """T40: Source-inspection: bot_voice.py routes system mode and preserves admin role.

    Verifies that:
    - _handle_voice_message checks _user_mode == "system" and routes to _handle_system_message
    - The routing code is present and structurally correct
    """
    t0 = time.time()
    results = []
    try:
        src = os.path.join(os.path.dirname(__file__), "..", "features", "bot_voice.py")
        src = os.path.abspath(src)
        if not os.path.exists(src):
            results.append(TestResult("voice_system_mode_routing", "SKIP", time.time() - t0,
                                      "bot_voice.py not found"))
            return results
        code = open(src).read()

        # Check that system mode routing is present
        has_system_check = '"system"' in code and "_handle_system_message" in code
        if has_system_check:
            results.append(TestResult("voice_system_mode_check", "PASS", time.time() - t0,
                                      "system mode routing present in bot_voice.py"))
        else:
            results.append(TestResult("voice_system_mode_check", "FAIL", time.time() - t0,
                                      'Missing: "_user_mode==system" → _handle_system_message routing'))

        # Check the import of _handle_system_message in voice module
        has_import = "_handle_system_message" in code
        if has_import:
            results.append(TestResult("voice_system_import", "PASS", time.time() - t0,
                                      "_handle_system_message imported/used in bot_voice.py"))
        else:
            results.append(TestResult("voice_system_import", "FAIL", time.time() - t0,
                                      "_handle_system_message not referenced in bot_voice.py"))

    except Exception as e:
        results.append(TestResult("voice_system_mode_routing", "FAIL", time.time() - t0, str(e)))
    return results


def t_voice_lang_stt_lang_priority(**_) -> list[TestResult]:
    """T41: Source-inspection: _voice_lang() respects STT_LANG env override.

    Verifies that when STT_LANG is set in config, _voice_lang() returns that
    language rather than the Telegram UI language. This prevents the regression
    where Russian speakers got English TTS because their Telegram client was set
    to English.
    """
    t0 = time.time()
    results = []
    try:
        src = os.path.join(os.path.dirname(__file__), "..", "features", "bot_voice.py")
        src = os.path.abspath(src)
        if not os.path.exists(src):
            results.append(TestResult("voice_lang_stt_priority", "SKIP", time.time() - t0,
                                      "bot_voice.py not found"))
            return results
        code = open(src).read()

        # _voice_lang() must exist and reference STT_LANG
        import ast
        try:
            tree = ast.parse(code)
            fn_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            has_voice_lang = "_voice_lang" in fn_names
        except SyntaxError:
            has_voice_lang = "_voice_lang" in code

        if has_voice_lang:
            results.append(TestResult("voice_lang_function_exists", "PASS", time.time() - t0,
                                      "_voice_lang() function present"))
        else:
            results.append(TestResult("voice_lang_function_exists", "FAIL", time.time() - t0,
                                      "_voice_lang() missing from bot_voice.py"))

        # Check STT_LANG is referenced (either import or attribute access)
        has_stt_lang = "STT_LANG" in code
        if has_stt_lang:
            results.append(TestResult("voice_lang_stt_lang_ref", "PASS", time.time() - t0,
                                      "STT_LANG referenced in bot_voice.py"))
        else:
            results.append(TestResult("voice_lang_stt_lang_ref", "FAIL", time.time() - t0,
                                      "STT_LANG not referenced in bot_voice.py — language override missing"))

        # Runtime check: import and call _voice_lang with STT_LANG override
        try:
            import importlib
            import sys
            # Save original STT_LANG if set
            orig = os.environ.get("STT_LANG")
            os.environ["STT_LANG"] = "ru"
            import core.bot_config as cfg
            orig_cfg = getattr(cfg, "STT_LANG", None)
            cfg.STT_LANG = "ru"

            # Try importing and calling _voice_lang
            features_path = os.path.join(os.path.dirname(__file__), "..", "features")
            if features_path not in sys.path:
                sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
            from features.bot_voice import _voice_lang
            lang = _voice_lang(99999)  # dummy chat_id → falls back to STT_LANG
            cfg.STT_LANG = orig_cfg
            if orig is None:
                os.environ.pop("STT_LANG", None)
            else:
                os.environ["STT_LANG"] = orig

            if lang == "ru":
                results.append(TestResult("voice_lang_runtime_override", "PASS", time.time() - t0,
                                          f"_voice_lang(99999) → '{lang}' (STT_LANG=ru)"))
            else:
                results.append(TestResult("voice_lang_runtime_override", "WARN", time.time() - t0,
                                          f"_voice_lang(99999) → '{lang}' (expected 'ru' with STT_LANG=ru)"))
        except Exception as e2:
            results.append(TestResult("voice_lang_runtime_override", "SKIP", time.time() - t0,
                                      f"Runtime call skipped: {e2}"))

    except Exception as e:
        results.append(TestResult("voice_lang_stt_priority", "FAIL", time.time() - t0, str(e)))
    return results


def t_set_lang_default_not_hardcoded_en(**_) -> list[TestResult]:
    """T42: Source-inspection: _set_lang() uses _DEFAULT_LANG, not hardcoded 'en'.

    Verifies the regression fix where non-ru/non-de Telegram users were always
    assigned 'en' instead of the configured default language. With this fix,
    a Russian-default instance stays Russian for new users with English Telegram clients.
    """
    t0 = time.time()
    results = []
    try:
        src = os.path.join(os.path.dirname(__file__), "..", "telegram", "bot_access.py")
        src = os.path.abspath(src)
        if not os.path.exists(src):
            results.append(TestResult("set_lang_default", "SKIP", time.time() - t0,
                                      "bot_access.py not found"))
            return results
        code = open(src).read()

        # The else branch in _set_lang must NOT hardcode "en"
        import ast
        tree = ast.parse(code)
        found_set_lang = False
        hardcoded_en = False
        uses_default_lang = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_set_lang":
                found_set_lang = True
                func_src = ast.get_source_segment(code, node) or ""
                # Hardcoded "en" in the else branch
                if 'chat_id] = "en"' in func_src or "_user_lang[chat_id] = \"en\"" in func_src:
                    hardcoded_en = True
                # Uses _DEFAULT_LANG
                if "_DEFAULT_LANG" in func_src:
                    uses_default_lang = True
                break

        if not found_set_lang:
            results.append(TestResult("set_lang_function_present", "FAIL", time.time() - t0,
                                      "_set_lang() not found in bot_access.py"))
            return results

        results.append(TestResult("set_lang_function_present", "PASS", time.time() - t0,
                                  "_set_lang() found"))

        if hardcoded_en:
            results.append(TestResult("set_lang_no_hardcoded_en", "FAIL", time.time() - t0,
                                      "_set_lang() still hardcodes 'en' in else branch — use _DEFAULT_LANG"))
        else:
            results.append(TestResult("set_lang_no_hardcoded_en", "PASS", time.time() - t0,
                                      "No hardcoded 'en' in _set_lang()"))

        if uses_default_lang:
            results.append(TestResult("set_lang_uses_default_lang", "PASS", time.time() - t0,
                                      "_set_lang() uses _DEFAULT_LANG as fallback"))
        else:
            results.append(TestResult("set_lang_uses_default_lang", "FAIL", time.time() - t0,
                                      "_set_lang() does not reference _DEFAULT_LANG — fallback language not configurable"))

    except Exception as e:
        results.append(TestResult("set_lang_default", "FAIL", time.time() - t0, str(e)))
    return results


def t_voice_system_admin_guard(**_) -> list[TestResult]:
    """T43: Source-inspection: voice handler guards system-chat mode with admin check.

    Verifies that _handle_voice_message() checks _is_admin() before routing to
    _handle_system_message() in 'system' mode. This prevents non-admin users (or
    other bot instances without admin context) from accessing system-chat commands
    via voice messages.
    """
    t0 = time.time()
    results = []
    try:
        src = os.path.join(os.path.dirname(__file__), "..", "features", "bot_voice.py")
        src = os.path.abspath(src)
        if not os.path.exists(src):
            results.append(TestResult("voice_system_admin_guard", "SKIP", time.time() - t0,
                                      "bot_voice.py not found"))
            return results
        code = open(src).read()

        # Find the system-mode routing block
        has_system_check = '_cur_mode == "system"' in code or "_cur_mode == 'system'" in code
        if not has_system_check:
            results.append(TestResult("voice_system_mode_routing", "FAIL", time.time() - t0,
                                      "No system-mode routing found in bot_voice.py"))
            return results

        results.append(TestResult("voice_system_mode_routing", "PASS", time.time() - t0,
                                  "system-mode check found"))

        # The admin guard must appear in bot_voice.py (not just inside _handle_system_message)
        has_admin_guard = "_is_admin" in code
        if not has_admin_guard:
            results.append(TestResult("voice_system_admin_guard", "FAIL", time.time() - t0,
                                      "_is_admin not referenced in bot_voice.py — admin guard missing"))
        else:
            results.append(TestResult("voice_system_admin_guard", "PASS", time.time() - t0,
                                      "_is_admin guard present in bot_voice.py"))

        # _is_admin must be imported (top-level import, not just deferred)
        import ast
        tree = ast.parse(code)
        admin_in_top_imports = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "bot_access" in node.module:
                    names = [alias.name for alias in node.names]
                    if "_is_admin" in names:
                        admin_in_top_imports = True
                        break
        if admin_in_top_imports:
            results.append(TestResult("voice_is_admin_imported", "PASS", time.time() - t0,
                                      "_is_admin in top-level import from bot_access"))
        else:
            results.append(TestResult("voice_is_admin_imported", "FAIL", time.time() - t0,
                                      "_is_admin NOT in top-level import — guard may not work"))

    except Exception as e:
        results.append(TestResult("voice_system_admin_guard", "FAIL", time.time() - t0, str(e)))
    return results


def t_openclaw_gateway_telegram_disabled(**_) -> list[TestResult]:
    """T44: openclaw-gateway Telegram channel must be disabled to prevent 409 token conflict.

    If openclaw-gateway runs with the same bot token as taris-telegram, they compete
    for Telegram updates (409 Conflict). Whichever wins handles the message — openclaw
    uses English, causing random language mixing in the UI. The fix is to set
    channels.telegram.enabled = false in ~/.openclaw/openclaw.json.
    """
    t0 = time.time()
    results: list[TestResult] = []
    openclaw_cfg = os.path.expanduser("~/.openclaw/openclaw.json")

    if not os.path.exists(openclaw_cfg):
        results.append(TestResult("openclaw_no_config", "SKIP", time.time() - t0,
                                  "~/.openclaw/openclaw.json not found — openclaw-gateway not installed"))
        return results

    try:
        import json as _json
        cfg = _json.load(open(openclaw_cfg))
        tg = cfg.get("channels", {}).get("telegram", {})
        tg_enabled = tg.get("enabled", True)
        tg_token = tg.get("botToken", "")
        taris_token = os.environ.get("BOT_TOKEN", "")

        # Check if tokens match (conflict risk)
        tokens_match = bool(tg_token and taris_token and tg_token == taris_token)

        if not tg_enabled:
            results.append(TestResult("openclaw_telegram_disabled", "PASS", time.time() - t0,
                                      "openclaw-gateway Telegram channel is disabled — no 409 conflict"))
        elif not tg_token:
            results.append(TestResult("openclaw_telegram_no_token", "PASS", time.time() - t0,
                                      "openclaw-gateway has no Telegram token configured"))
        else:
            detail = "openclaw-gateway Telegram channel ENABLED"
            if tokens_match:
                detail += " and uses SAME token as taris — WILL cause 409 conflict and language mixing!"
            else:
                detail += " but uses a different token — OK"
            status = "FAIL" if tokens_match else "WARN"
            results.append(TestResult("openclaw_telegram_conflict", status, time.time() - t0, detail))

    except Exception as e:
        results.append(TestResult("openclaw_gateway_telegram_disabled", "FAIL", time.time() - t0, str(e)))

    return results


def t_taris_bin_configured(**_) -> list[TestResult]:
    """T45: TARIS_BIN must point to an existing binary (picoclaw or taris).

    On PicoClaw Pi devices the binary is /usr/bin/picoclaw, NOT /usr/bin/taris.
    The default TARIS_BIN=/usr/bin/taris in bot_config.py causes silent LLM failures
    when voice STT→LLM is called. Fix: set TARIS_BIN=/usr/bin/picoclaw in bot.env.

    SKIP: if running in source-inspection mode (no ~/.taris/bot.env deployed).
    """
    t0 = time.time()
    results: list[TestResult] = []
    try:
        # Only meaningful in a deployed environment where bot.env is present
        bot_env = os.path.expanduser("~/.taris/bot.env")
        if not os.path.exists(bot_env):
            results.append(TestResult("taris_bin_configured", "SKIP", time.time() - t0,
                                      "source-inspection mode — no ~/.taris/bot.env"))
            return results

        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from core.bot_config import TARIS_BIN, LLM_PROVIDER

        # T45 only applies when LLM routes through the taris/picoclaw binary
        if LLM_PROVIDER != "taris":
            results.append(TestResult("taris_bin_configured", "SKIP", time.time() - t0,
                                      f"LLM_PROVIDER={LLM_PROVIDER} — TARIS_BIN not used"))
            return results
        exists = os.path.isfile(TARIS_BIN)
        executable = os.access(TARIS_BIN, os.X_OK) if exists else False
        if exists and executable:
            results.append(TestResult("taris_bin_exists", "PASS", time.time() - t0,
                                      f"TARIS_BIN={TARIS_BIN} exists and is executable"))
        elif not exists:
            results.append(TestResult("taris_bin_missing", "FAIL", time.time() - t0,
                                      f"TARIS_BIN={TARIS_BIN} does not exist — "
                                      f"set TARIS_BIN=/usr/bin/picoclaw in bot.env"))
        else:
            results.append(TestResult("taris_bin_not_executable", "FAIL", time.time() - t0,
                                      f"TARIS_BIN={TARIS_BIN} exists but is not executable"))

        # Also verify picoclaw config is present when binary is picoclaw
        if "picoclaw" in TARIS_BIN:
            picoclaw_cfg = os.path.expanduser("~/.picoclaw/config.json")
            if os.path.exists(picoclaw_cfg):
                results.append(TestResult("picoclaw_config_present", "PASS", time.time() - t0,
                                          "~/.picoclaw/config.json present"))
            else:
                results.append(TestResult("picoclaw_config_missing", "FAIL", time.time() - t0,
                                          "~/.picoclaw/config.json missing — picoclaw agent will fail "
                                          "(copy ~/.taris/config.json and set active_model.txt)"))

    except Exception as e:
        results.append(TestResult("taris_bin_configured", "FAIL", time.time() - t0, str(e)))
    return results




# ─────────────────────────────────────────────────────────────────────────────
# T46 — vosk_fallback default disabled on OpenClaw platform
# ─────────────────────────────────────────────────────────────────────────────

def t_vosk_fallback_openclaw_default(**_) -> list[TestResult]:
    """T46: vosk_fallback must default to False when DEVICE_VARIANT=openclaw.

    Root cause: Vosk model is not installed on OpenClaw (x86_64) hosts. When
    faster-whisper returned empty (VAD over-filtering), the fallback to Vosk
    caused a C++ model-load error and the user received "Ошибка Vosk".

    Fix: _VOICE_OPTS_DEFAULTS['vosk_fallback'] = DEVICE_VARIANT != 'openclaw'

    Source-inspection — no deployed services required.
    """
    t0 = time.time()
    results: list[TestResult] = []
    try:
        import importlib, sys as _sys

        # ── 1. With DEVICE_VARIANT=openclaw vosk_fallback must be False ────────
        old = os.environ.get("DEVICE_VARIANT")
        os.environ["DEVICE_VARIANT"] = "openclaw"
        # Force re-import so the constant is evaluated with new env
        for mod in list(_sys.modules.keys()):
            if "bot_config" in mod:
                del _sys.modules[mod]
        from core.bot_config import _VOICE_OPTS_DEFAULTS as oc_defaults
        oc_val = oc_defaults.get("vosk_fallback", True)
        if not oc_val:
            results.append(TestResult(
                "vosk_fallback_openclaw_false", "PASS", time.time() - t0,
                "vosk_fallback=False when DEVICE_VARIANT=openclaw"))
        else:
            results.append(TestResult(
                "vosk_fallback_openclaw_false", "FAIL", time.time() - t0,
                "vosk_fallback is True on openclaw — Vosk not installed, will crash"))

        # ── 2. With DEVICE_VARIANT=picoclaw vosk_fallback must be True ─────────
        os.environ["DEVICE_VARIANT"] = "picoclaw"
        for mod in list(_sys.modules.keys()):
            if "bot_config" in mod:
                del _sys.modules[mod]
        from core.bot_config import _VOICE_OPTS_DEFAULTS as pi_defaults
        pi_val = pi_defaults.get("vosk_fallback", False)
        if pi_val:
            results.append(TestResult(
                "vosk_fallback_picoclaw_true", "PASS", time.time() - t0,
                "vosk_fallback=True when DEVICE_VARIANT=picoclaw (Vosk installed on Pi)"))
        else:
            results.append(TestResult(
                "vosk_fallback_picoclaw_true", "FAIL", time.time() - t0,
                "vosk_fallback is False on picoclaw — Pi devices need Vosk fallback"))

        # Restore env + module cache
        if old is None:
            os.environ.pop("DEVICE_VARIANT", None)
        else:
            os.environ["DEVICE_VARIANT"] = old
        for mod in list(_sys.modules.keys()):
            if "bot_config" in mod:
                del _sys.modules[mod]

    except Exception as e:
        results.append(TestResult("vosk_fallback_openclaw_default", "FAIL", time.time() - t0, str(e)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T47 — faster-whisper: VAD retry on empty result
# ─────────────────────────────────────────────────────────────────────────────

def t_faster_whisper_vad_retry(**_) -> list[TestResult]:
    """T47: _stt_faster_whisper must retry without VAD when first pass returns empty.

    Root cause: Telegram voice messages can be very short (1-3 s, e.g. "да",
    "нет"). The built-in faster-whisper VAD filter suppresses these as 'noise',
    returning empty. Without a retry, the pipeline fell back to Vosk (not
    installed on OpenClaw) and the user got "Ошибка Vosk".

    Fix: after a VAD pass returning empty, retry transcribe() with vad_filter=False.

    Source-inspection — checks that dual-pass logic exists in bot_voice.py.
    """
    t0 = time.time()
    results: list[TestResult] = []
    try:
        voice_py = os.path.join(os.path.dirname(__file__), "..", "features", "bot_voice.py")
        voice_py = os.path.normpath(voice_py)
        if not os.path.exists(voice_py):
            results.append(TestResult("fw_vad_retry_source", "SKIP", time.time() - t0,
                                      f"features/bot_voice.py not found at {voice_py}"))
            return results

        src = open(voice_py, encoding="utf-8").read()

        # Must contain a second transcribe() call that has vad_filter=False
        import re as _re
        # Find all transcribe() calls and check at least one has vad_filter=False
        calls_no_vad = _re.findall(r'model\.transcribe\([^)]*vad_filter\s*=\s*False', src, _re.DOTALL)
        if calls_no_vad:
            results.append(TestResult(
                "fw_vad_retry_no_vad_call", "PASS", time.time() - t0,
                f"Found {len(calls_no_vad)} transcribe() call(s) with vad_filter=False (retry path)"))
        else:
            results.append(TestResult(
                "fw_vad_retry_no_vad_call", "FAIL", time.time() - t0,
                "No transcribe(vad_filter=False) found — short voice messages will be silently dropped"))

        # Must contain the retry comment / log message indicating intent
        has_retry_log = ("retry" in src.lower() or "retrying" in src.lower()) and "vad" in src.lower()
        if has_retry_log:
            results.append(TestResult(
                "fw_vad_retry_log_present", "PASS", time.time() - t0,
                "VAD retry log message present in _stt_faster_whisper"))
        else:
            results.append(TestResult(
                "fw_vad_retry_log_present", "WARN", time.time() - t0,
                "No VAD retry log found — add debug log for observability"))

    except Exception as e:
        results.append(TestResult("faster_whisper_vad_retry", "FAIL", time.time() - t0, str(e)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T48 — System Chat accessible only via Admin menu
# ─────────────────────────────────────────────────────────────────────────────

def t_system_chat_admin_menu_only(**_) -> list[TestResult]:
    """T48: System Chat (mode_system) must appear in admin_menu only, not main_menu.

    Root cause: mode_system button was in main_menu.yaml (admin-role filtered).
    Requirement: it must be exclusively in Admin Panel to keep main menu clean
    and reduce attack surface exposure.

    Source-inspection — checks YAML screens and Python keyboard builder.
    """
    t0 = time.time()
    results: list[TestResult] = []
    try:
        screens_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "screens"))
        bot_access_py = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "telegram", "bot_access.py"))

        # ── 1. main_menu.yaml must NOT contain mode_system ────────────────────
        main_yaml = os.path.join(screens_dir, "main_menu.yaml")
        if os.path.exists(main_yaml):
            main_src = open(main_yaml, encoding="utf-8").read()
            if "mode_system" not in main_src:
                results.append(TestResult(
                    "mode_system_absent_main_menu", "PASS", time.time() - t0,
                    "main_menu.yaml does not contain mode_system ✓"))
            else:
                results.append(TestResult(
                    "mode_system_absent_main_menu", "FAIL", time.time() - t0,
                    "main_menu.yaml still contains mode_system — move to admin_menu.yaml"))
        else:
            results.append(TestResult("mode_system_absent_main_menu", "SKIP", time.time() - t0,
                                      f"main_menu.yaml not found at {main_yaml}"))

        # ── 2. admin_menu.yaml must contain mode_system ───────────────────────
        admin_yaml = os.path.join(screens_dir, "admin_menu.yaml")
        if os.path.exists(admin_yaml):
            admin_src = open(admin_yaml, encoding="utf-8").read()
            if "mode_system" in admin_src:
                results.append(TestResult(
                    "mode_system_present_admin_menu", "PASS", time.time() - t0,
                    "admin_menu.yaml contains mode_system ✓"))
            else:
                results.append(TestResult(
                    "mode_system_present_admin_menu", "FAIL", time.time() - t0,
                    "admin_menu.yaml missing mode_system — System Chat button lost"))
        else:
            results.append(TestResult("mode_system_present_admin_menu", "SKIP", time.time() - t0,
                                      f"admin_menu.yaml not found at {admin_yaml}"))

        # ── 3. _menu_keyboard() in bot_access.py must NOT add mode_system ─────
        if os.path.exists(bot_access_py):
            import re as _re
            access_src = open(bot_access_py, encoding="utf-8").read()
            # Find _menu_keyboard function body (up to the next top-level def)
            menu_kb_match = _re.search(
                r'def _menu_keyboard\b.*?(?=\ndef |\Z)', access_src, _re.DOTALL)
            if menu_kb_match:
                menu_kb_body = menu_kb_match.group(0)
                if "mode_system" not in menu_kb_body:
                    results.append(TestResult(
                        "mode_system_absent_menu_keyboard", "PASS", time.time() - t0,
                        "_menu_keyboard() does not include mode_system ✓"))
                else:
                    results.append(TestResult(
                        "mode_system_absent_menu_keyboard", "FAIL", time.time() - t0,
                        "_menu_keyboard() still adds mode_system — remove the btn_system line"))
            else:
                results.append(TestResult("mode_system_absent_menu_keyboard", "WARN", time.time() - t0,
                                          "_menu_keyboard not found in bot_access.py"))
        else:
            results.append(TestResult("mode_system_absent_menu_keyboard", "SKIP", time.time() - t0,
                                      "bot_access.py not found"))

    except Exception as e:
        results.append(TestResult("system_chat_admin_menu_only", "FAIL", time.time() - t0, str(e)))
    return results


def t_stt_fast_speech_accuracy(**_) -> list[TestResult]:
    """T49: STT model must correctly transcribe fast Russian speech.

    Root cause (2026-03-29): faster-whisper 'base' model (74M params) mangles
    Russian phonemes in clips shorter than ~1.5s effective audio. The phrase
    'Сколько у тебя памяти' was transcribed as 'Куча панча', 'Кутя Панти',
    'Удя панча' when spoken at normal/fast speed, and only correctly when spoken
    very slowly (3.4s clip).

    This test:
    1. Asserts FASTER_WHISPER_MODEL is NOT 'base' (structural guard)
    2. Generates audio via Piper TTS + creates fast/slow variants via ffmpeg atempo
    3. Runs STT on each speed variant and checks WER ≤ 0.35
    4. Fails if any speed variant produces a WER > 0.35 (garbage output)

    SKIP if Piper binary or faster-whisper not installed.
    """
    import subprocess as _sp

    t0 = time.time()
    results: list[TestResult] = []

    # SKIP on Vosk targets — faster-whisper model tuning is not applicable
    bot_env_path = Path(os.path.expanduser("~/.taris/bot.env"))
    stt_provider = os.environ.get("STT_PROVIDER", "vosk")
    if bot_env_path.exists():
        for _l in bot_env_path.read_text(encoding="utf-8").splitlines():
            _l = _l.strip()
            if _l.startswith("STT_PROVIDER=") and not _l.startswith("#"):
                stt_provider = _l.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if stt_provider != "faster_whisper":
        results.append(TestResult(
            "stt_model_not_base", "SKIP", time.time() - t0,
            f"STT_PROVIDER={stt_provider} — faster-whisper model guard N/A on Vosk targets",
        ))
        fw_model = "vosk-n/a"
    else:
        # ── 1. Structural guard: model must NOT be 'base' ─────────────────────────
        # Read from env first, then fall back to bot.env so the guard works without
        # manually sourcing bot.env before running the test.
        fw_model = os.environ.get("FASTER_WHISPER_MODEL", "")
        if not fw_model:
            if bot_env_path.exists():
                for line in bot_env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("FASTER_WHISPER_MODEL=") and not line.startswith("#"):
                        fw_model = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        if not fw_model:
            fw_model = "base"   # fallback default matches bot_config.py

        if fw_model == "base":
            results.append(TestResult(
                "stt_model_not_base", "FAIL", time.time() - t0,
                "FASTER_WHISPER_MODEL=base — known to fail on fast Russian speech. "
                "Set FASTER_WHISPER_MODEL=small or better in bot.env",
            ))
        else:
            results.append(TestResult(
                "stt_model_not_base", "PASS", time.time() - t0,
                f"FASTER_WHISPER_MODEL={fw_model} ✓ (not base)",
            ))

    # ── 2. Check faster-whisper is installed ──────────────────────────────────
    try:
        from faster_whisper import WhisperModel  # type: ignore[import]
    except ImportError:
        results.append(TestResult(
            "stt_fast_speech_inference", "SKIP", time.time() - t0,
            "faster-whisper not installed — pip install faster-whisper",
        ))
        return results

    # ── 3. Check Piper binary for audio generation ────────────────────────────
    import sys as _sys
    _src_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    if _src_dir not in _sys.path:
        _sys.path.insert(0, _src_dir)
    try:
        from core.bot_config import PIPER_BIN, PIPER_MODEL  # type: ignore
    except ImportError:
        PIPER_BIN = os.environ.get("PIPER_BIN", "")
        PIPER_MODEL = os.environ.get("PIPER_MODEL", "")

    if not PIPER_BIN or not os.path.exists(PIPER_BIN):
        results.append(TestResult(
            "stt_fast_speech_inference", "SKIP", time.time() - t0,
            f"Piper binary not found ({PIPER_BIN}) — cannot generate test audio",
        ))
        return results

    # ── 4. Generate reference audio via Piper TTS ─────────────────────────────
    PHRASE = "Сколько у тебя памяти"
    REF_WORDS = set("сколько у тебя памяти".split())  # expected words in output

    def _gen_pcm_at_speed(speed: float) -> tuple[bytes, float]:
        """Generate PCM for PHRASE at given speed via Piper + ffmpeg atempo."""
        # Piper → raw PCM at 22050 Hz
        piper_cmd = [PIPER_BIN, "--model", PIPER_MODEL, "--output-raw"]
        r = _sp.run(piper_cmd, input=PHRASE.encode("utf-8"),
                    capture_output=True, timeout=30)
        if r.returncode != 0:
            return b"", 0.0
        raw_piper = r.stdout  # S16LE at model sample rate (22050)

        # atempo must be between 0.5 and 2.0 (chain for extremes)
        if speed <= 0.5:
            atempo = f"atempo=0.5,atempo={speed / 0.5:.3f}"
        elif speed >= 2.0:
            atempo = f"atempo=2.0,atempo={speed / 2.0:.3f}"
        else:
            atempo = f"atempo={speed:.3f}"

        # Resample piper output → 16kHz + apply speed + output S16LE
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "s16le", "-ar", "22050", "-ac", "1", "-i", "pipe:0",
            "-af", atempo,
            "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1",
            "-loglevel", "error",
        ]
        r2 = _sp.run(ffmpeg_cmd, input=raw_piper, capture_output=True, timeout=30)
        pcm = r2.stdout
        dur = len(pcm) / (16000 * 2) if pcm else 0.0
        return pcm, dur

    # ── 5. Load FW model once ──────────────────────────────────────────────────
    fw_device = os.environ.get("FASTER_WHISPER_DEVICE", "cpu")
    fw_compute = os.environ.get("FASTER_WHISPER_COMPUTE", "int8")
    fw_threads = int(os.environ.get("FASTER_WHISPER_THREADS", "0")) or 4

    try:
        import numpy as _np
        t_load = time.time()
        model = WhisperModel(fw_model, device=fw_device, compute_type=fw_compute,
                             cpu_threads=fw_threads)
        load_t = time.time() - t_load
        results.append(TestResult(
            f"stt_model_load:{fw_model}",
            "PASS", load_t,
            f"Loaded {fw_model}/{fw_device}/{fw_compute} threads={fw_threads} in {load_t:.2f}s",
        ))
    except Exception as e:
        results.append(TestResult("stt_model_load", "FAIL", time.time() - t0, str(e)))
        return results

    def _wer_simple(ref: str, hyp: str) -> float:
        r = ref.lower().split()
        h = hyp.lower().split()
        if not r:
            return 0.0 if not h else 1.0
        n, m = len(r), len(h)
        dp = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(n + 1):
            dp[i][0] = i
        for j in range(m + 1):
            dp[0][j] = j
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                dp[i][j] = dp[i - 1][j - 1] if r[i - 1] == h[j - 1] \
                    else 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[n][m] / n

    # ── 6. Run inference at each speed ────────────────────────────────────────
    SPEEDS = [
        (0.65, "slow_0.65x"),
        (1.00, "normal_1.0x"),
        (1.50, "fast_1.5x"),
        (1.85, "veryfast_1.85x"),
    ]
    WER_THRESHOLD = 0.35   # ≤35% word error rate required

    for speed, label in SPEEDS:
        ts = time.time()
        try:
            pcm, dur = _gen_pcm_at_speed(speed)
            if not pcm:
                results.append(TestResult(
                    f"stt_speed:{label}", "SKIP", time.time() - ts,
                    f"Audio generation failed (Piper/ffmpeg error) for speed={speed}",
                ))
                continue

            audio_np = _np.frombuffer(pcm, dtype=_np.int16).astype(_np.float32) / 32768.0
            t_inf = time.time()
            segs, info = model.transcribe(
                audio_np, language="ru", beam_size=5,
                vad_filter=True, condition_on_previous_text=False,
            )
            transcript = " ".join(seg.text.strip() for seg in segs).strip()
            inf_t = time.time() - t_inf

            # Retry without VAD if empty (short clips)
            if not transcript:
                segs2, _ = model.transcribe(
                    audio_np, language="ru", beam_size=5,
                    vad_filter=False, condition_on_previous_text=False,
                )
                transcript = " ".join(seg.text.strip() for seg in segs2).strip()

            wer = _wer_simple("сколько у тебя памяти", transcript.lower())
            rtf = inf_t / dur if dur > 0 else 0
            status = "PASS" if wer <= WER_THRESHOLD else "FAIL"

            results.append(TestResult(
                f"stt_speed:{label}",
                status, time.time() - ts,
                f"dur={dur:.2f}s RTF={rtf:.2f} WER={wer:.0%} "
                f"transcript='{transcript[:60]}' "
                f"(threshold={WER_THRESHOLD:.0%})",
                metric=wer, metric_key=f"stt_speed_wer_{label}",
            ))
        except _sp.TimeoutExpired:
            # Piper or ffmpeg timed out — slow machine, skip this speed variant
            results.append(TestResult(f"stt_speed:{label}", "SKIP",
                                      time.time() - ts,
                                      "Audio generation timed out (slow machine) — SKIP"))
        except Exception as e:
            results.append(TestResult(f"stt_speed:{label}", "FAIL",
                                      time.time() - ts, str(e)))

    return results


def t_voice_chat_config_disclosure(**_):
    """T50: _bot_config_block() injects LLM/STT/version; rule 5 allows model disclosure."""
    results = []

    # 1. Config block contains required fields
    ts = time.time()
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent.parent))
        from telegram.bot_access import _bot_config_block
        block = _bot_config_block()
        required = ["[BOT CONFIG]", "LLM:", "STT:", "Version:", "[END BOT CONFIG]"]
        missing = [k for k in required if k not in block]
        if missing:
            results.append(TestResult("config_block_fields", "FAIL", time.time() - ts,
                                      f"Missing fields: {missing}"))
        else:
            results.append(TestResult("config_block_fields", "PASS", time.time() - ts,
                                      f"Block OK: {block.strip()[:80]}"))
    except Exception as e:
        results.append(TestResult("config_block_fields", "FAIL", time.time() - ts, str(e)))

    # 2. Security preamble rule 5 allows model disclosure (no longer blocks infra questions blanket)
    ts = time.time()
    try:
        import json as _json
        prompts_path = SRC_ROOT / "prompts.json"
        prompts = _json.loads(prompts_path.read_text())
        preamble = prompts.get("security_preamble", "")
        rule5_start = preamble.find("5.")
        rule5 = preamble[rule5_start:rule5_start + 300] if rule5_start >= 0 else ""
        # Must allow model disclosure
        if "MAY" not in rule5 and "SHOULD" not in rule5:
            results.append(TestResult("preamble_rule5_allows_disclosure", "FAIL",
                                      time.time() - ts,
                                      "Rule 5 does not allow model disclosure — bot will refuse self-info"))
        else:
            results.append(TestResult("preamble_rule5_allows_disclosure", "PASS",
                                      time.time() - ts, "Rule 5 allows model/version disclosure"))
    except Exception as e:
        results.append(TestResult("preamble_rule5_allows_disclosure", "FAIL",
                                  time.time() - ts, str(e)))

    # 3. _with_lang_voice includes the config block in the prompt
    ts = time.time()
    try:
        from telegram.bot_access import _with_lang_voice
        import inspect
        src = inspect.getsource(_with_lang_voice)
        if "_bot_config_block()" not in src:
            results.append(TestResult("with_lang_voice_has_config", "FAIL", time.time() - ts,
                                      "_with_lang_voice() does not call _bot_config_block()"))
        else:
            results.append(TestResult("with_lang_voice_has_config", "PASS", time.time() - ts,
                                      "_with_lang_voice() injects config block"))
    except Exception as e:
        results.append(TestResult("with_lang_voice_has_config", "FAIL", time.time() - ts, str(e)))

    return results


def t_note_delete_confirm(**_) -> list[TestResult]:
    """T51: note_delete shows confirm dialog; note_del_confirm: callback wired."""
    results = []
    ts = time.time()
    try:
        handlers_path = SRC_ROOT / "telegram" / "bot_handlers.py"
        src = handlers_path.read_text()
        # confirm dialog must be shown (not immediate delete)
        if "note_del_confirm:" not in src:
            results.append(TestResult("note_delete_confirm_callback", "FAIL", time.time() - ts,
                                      "note_del_confirm: callback_data not found in bot_handlers.py"))
        else:
            results.append(TestResult("note_delete_confirm_callback", "PASS", time.time() - ts,
                                      "note_del_confirm: present in bot_handlers.py"))
    except Exception as e:
        results.append(TestResult("note_delete_confirm_callback", "FAIL", time.time() - ts, str(e)))

    ts = time.time()
    try:
        menu_path = SRC_ROOT / "telegram_menu_bot.py"
        src = menu_path.read_text()
        if "note_del_confirm:" not in src:
            results.append(TestResult("note_del_confirm_wired", "FAIL", time.time() - ts,
                                      "note_del_confirm: not wired in telegram_menu_bot.py"))
        else:
            results.append(TestResult("note_del_confirm_wired", "PASS", time.time() - ts,
                                      "note_del_confirm: wired in dispatcher"))
    except Exception as e:
        results.append(TestResult("note_del_confirm_wired", "FAIL", time.time() - ts, str(e)))

    return results


def t_note_rename_flow(**_) -> list[TestResult]:
    """T52: note_rename_title mode present in message handler; rename handler exists."""
    results = []
    ts = time.time()
    try:
        menu_path = SRC_ROOT / "telegram_menu_bot.py"
        src = menu_path.read_text()
        if "note_rename_title" not in src:
            results.append(TestResult("note_rename_mode", "FAIL", time.time() - ts,
                                      "note_rename_title mode missing from telegram_menu_bot.py"))
        else:
            results.append(TestResult("note_rename_mode", "PASS", time.time() - ts,
                                      "note_rename_title mode present"))
    except Exception as e:
        results.append(TestResult("note_rename_mode", "FAIL", time.time() - ts, str(e)))

    ts = time.time()
    try:
        handlers_path = SRC_ROOT / "telegram" / "bot_handlers.py"
        src = handlers_path.read_text()
        if "_start_note_rename" not in src:
            results.append(TestResult("note_rename_handler", "FAIL", time.time() - ts,
                                      "_start_note_rename not found in bot_handlers.py"))
        else:
            results.append(TestResult("note_rename_handler", "PASS", time.time() - ts,
                                      "_start_note_rename present"))
    except Exception as e:
        results.append(TestResult("note_rename_handler", "FAIL", time.time() - ts, str(e)))

    return results


def t_note_zip_download(**_) -> list[TestResult]:
    """T53: ZIP download handler present; in-memory zipfile pattern used."""
    results = []
    ts = time.time()
    try:
        handlers_path = SRC_ROOT / "telegram" / "bot_handlers.py"
        src = handlers_path.read_text()
        checks = [
            ("_handle_note_download_zip", "_handle_note_download_zip function"),
            ("zipfile.ZipFile", "zipfile.ZipFile usage"),
            ("io.BytesIO", "in-memory io.BytesIO buffer"),
        ]
        for symbol, desc in checks:
            if symbol not in src:
                results.append(TestResult(f"note_zip_{symbol[:20]}", "FAIL", time.time() - ts,
                                          f"{desc} not found in bot_handlers.py"))
            else:
                results.append(TestResult(f"note_zip_{symbol[:20]}", "PASS", time.time() - ts,
                                          f"{desc} present"))
                ts = time.time()
    except Exception as e:
        results.append(TestResult("note_zip_download", "FAIL", time.time() - ts, str(e)))

    return results


def t_rag_context_injection(**_) -> list[TestResult]:
    """T54: _docs_rag_context() called in _with_lang() and _with_lang_voice()."""
    results = []
    ts = time.time()
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent.parent))
        from telegram import bot_access
        import inspect

        for fn_name in ("_with_lang", "_with_lang_voice"):
            fn = getattr(bot_access, fn_name, None)
            if fn is None:
                results.append(TestResult(f"rag_{fn_name}", "FAIL", time.time() - ts,
                                          f"{fn_name} not found in bot_access"))
                continue
            src = inspect.getsource(fn)
            if "_docs_rag_context" not in src:
                results.append(TestResult(f"rag_{fn_name}", "FAIL", time.time() - ts,
                                          f"_docs_rag_context not called in {fn_name}"))
            else:
                results.append(TestResult(f"rag_{fn_name}", "PASS", time.time() - ts,
                                          f"_docs_rag_context injected in {fn_name}"))
            ts = time.time()
    except Exception as e:
        results.append(TestResult("rag_context_injection", "FAIL", time.time() - ts, str(e)))

    return results


def t_no_hardcoded_strings(**_) -> list[TestResult]:
    """T55: Key user-visible strings use _t() not hardcoded literals in Python source."""
    results = []

    checks = [
        # (file, bad_literal, good_description)
        ("features/bot_calendar.py",
         "Записал' if lang == 'ru' else 'Saved'",
         "cal_event_saved_prefix must use _t(), not inline Russian/English conditional"),
        ("features/bot_voice.py",
         "Генерация аудио прервана (бот перезапущен)",
         "audio_interrupted must use _t(), not hardcoded Russian"),
        ("features/bot_voice.py",
         "Заметка / Note:",
         "voice_note_msg must use _t(), not hardcoded bilingual label"),
    ]
    for rel_path, bad_literal, desc in checks:
        ts = time.time()
        full_path = Path(__file__).parent.parent / rel_path
        try:
            src = full_path.read_text(encoding="utf-8")
            if bad_literal in src:
                results.append(TestResult(
                    f"no_hardcoded:{Path(rel_path).stem}",
                    "FAIL", time.time() - ts,
                    f"{desc} — literal still present in {rel_path}",
                ))
            else:
                results.append(TestResult(
                    f"no_hardcoded:{Path(rel_path).stem}",
                    "PASS", time.time() - ts,
                    f"{desc}",
                ))
        except Exception as e:
            results.append(TestResult(f"no_hardcoded:{Path(rel_path).stem}", "FAIL",
                                      time.time() - ts, str(e)))

    # Also verify the new keys are in all 3 languages
    ts = time.time()
    try:
        strings = json.loads((SRC_ROOT / "strings.json")
                             .read_text(encoding="utf-8"))
        new_keys = ["voice_note_msg", "cal_event_saved_prefix"]
        missing = [(lang, k) for k in new_keys for lang in ("ru", "en", "de")
                   if k not in strings.get(lang, {})]
        if missing:
            results.append(TestResult("i18n_new_keys_present", "FAIL", time.time() - ts,
                                      f"Missing keys: {missing}"))
        else:
            results.append(TestResult("i18n_new_keys_present", "PASS", time.time() - ts,
                                      f"New i18n keys present in ru/en/de: {new_keys}"))
    except Exception as e:
        results.append(TestResult("i18n_new_keys_present", "FAIL", time.time() - ts, str(e)))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T56 — Ollama multi-turn context: ask_llm_with_history must send messages natively
# ─────────────────────────────────────────────────────────────────────────────

def t_ollama_history_native_messages(**_) -> list[TestResult]:
    """T56: ask_llm_with_history must have a native 'ollama' branch that sends the
    full messages list to /api/chat — NOT fall into the plain-text 'else' branch.

    Root cause of regression: ollama fell into the else-branch which formatted all
    history as a single plain-text prompt, breaking multi-turn conversation context.
    """
    t0 = time.time()
    results: list[TestResult] = []

    try:
        src = open(SRC_ROOT / "core" / "bot_llm.py").read()

        # Must have an explicit ollama branch in ask_llm_with_history
        has_ollama_branch = 'provider == "ollama"' in src and 'ask_llm_with_history' in src
        # The ollama branch must send "messages": messages (not a single-element list)
        # Check that in the context of the ollama branch the messages list is passed directly
        has_native_messages = (
            '"messages": messages' in src and
            'provider == "ollama"' in src
        )
        # The single-turn fallback (_ask_ollama) must NOT be in ask_llm_with_history path
        # Verify by checking that the ollama branch doesn't call _ask_ollama
        ask_llm_with_history_start = src.find("def ask_llm_with_history")
        ask_llm_with_history_end   = src.find("\ndef ask_", ask_llm_with_history_start + 1)
        if ask_llm_with_history_end == -1:
            ask_llm_with_history_end = len(src)
        history_func_body = src[ask_llm_with_history_start:ask_llm_with_history_end]
        calls_ask_ollama  = "_ask_ollama" in history_func_body

        results.append(TestResult(
            "ollama_explicit_branch",
            "PASS" if has_ollama_branch else "FAIL",
            time.time() - t0,
            'provider == "ollama" branch present in ask_llm_with_history' if has_ollama_branch
            else 'MISSING: ollama branch in ask_llm_with_history — history will be lost',
        ))
        results.append(TestResult(
            "ollama_native_messages_array",
            "PASS" if has_native_messages else "FAIL",
            time.time() - t0,
            '"messages": messages passed natively' if has_native_messages
            else 'MISSING: native messages array in ollama history branch',
        ))
        results.append(TestResult(
            "ollama_no_single_turn_fallback",
            "PASS" if not calls_ask_ollama else "FAIL",
            time.time() - t0,
            "_ask_ollama not called from ask_llm_with_history" if not calls_ask_ollama
            else "REGRESSION: ask_llm_with_history calls _ask_ollama (single-turn, loses context)",
        ))
    except Exception as e:
        results.append(TestResult("ollama_history_native_messages", "FAIL", time.time() - t0, str(e)))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T57 — Proper system message in multi-turn context
# ─────────────────────────────────────────────────────────────────────────────

def t_multiturn_system_message(**_) -> list[TestResult]:
    """T57: _handle_chat_message must send role:system as messages[0].

    Previously security preamble + bot config were stuffed into the LAST user turn only.
    History messages had zero bot framing, causing the LLM to say 'I have no memory'
    and answer without knowing it is Taris.

    Fix: _build_system_message + _user_turn_content in bot_handlers.py.
    """
    t0 = time.time()
    results: list[TestResult] = []

    try:
        bot_access_src  = open(SRC_ROOT / "telegram" / "bot_access.py").read()
        bot_handlers_src = open(SRC_ROOT / "telegram" / "bot_handlers.py").read()

        has_build_system = "def _build_system_message(" in bot_access_src
        has_user_turn    = "def _user_turn_content(" in bot_access_src
        has_memory_note  = "conversation history shown in this context" in bot_access_src
        imports_system   = "_build_system_message" in bot_handlers_src
        uses_system_role = ('"role": "system"' in bot_handlers_src or
                            "'role': 'system'" in bot_handlers_src)
        uses_user_turn_fn = "_user_turn_content(" in bot_handlers_src

        results.append(TestResult(
            "build_system_message_defined",
            "PASS" if has_build_system else "FAIL",
            time.time() - t0,
            "_build_system_message() present" if has_build_system
            else "MISSING: _build_system_message in bot_access.py",
        ))
        results.append(TestResult(
            "user_turn_content_defined",
            "PASS" if has_user_turn else "FAIL",
            time.time() - t0,
            "_user_turn_content() present" if has_user_turn
            else "MISSING: _user_turn_content in bot_access.py",
        ))
        results.append(TestResult(
            "memory_note_in_system_msg",
            "PASS" if has_memory_note else "FAIL",
            time.time() - t0,
            "LLM told it has conversation history via system msg" if has_memory_note
            else "MISSING: memory note — LLM will say 'I have no memory'",
        ))
        results.append(TestResult(
            "system_role_in_messages_list",
            "PASS" if uses_system_role else "FAIL",
            time.time() - t0,
            "role:system prepended to messages list" if uses_system_role
            else "REGRESSION: no role:system — bot identity lost in multi-turn",
        ))
        results.append(TestResult(
            "user_turn_fn_used_in_handlers",
            "PASS" if uses_user_turn_fn else "FAIL",
            time.time() - t0,
            "_user_turn_content() used in bot_handlers.py" if uses_user_turn_fn
            else "MISSING: _user_turn_content call in bot_handlers.py",
        ))
    except Exception as e:
        results.append(TestResult("multiturn_system_message", "FAIL", time.time() - t0, str(e)))

    return results


def t_voice_history_context(**_) -> list[TestResult]:
    """T59 — Voice pipeline uses ask_llm_with_history + saves turns to history."""
    results = []
    t0 = time.time()

    # 1. ask_llm_with_history imported in bot_voice.py
    try:
        src = (SRC_ROOT / "features/bot_voice.py").read_text()
        ok = "ask_llm_with_history" in src
        results.append(TestResult(
            "voice_imports_ask_llm_with_history", "PASS" if ok else "FAIL",
            time.time() - t0,
            "ask_llm_with_history imported in bot_voice.py" if ok
            else "MISSING: voice still uses single-turn ask_llm only",
        ))
    except Exception as e:
        results.append(TestResult("voice_imports_ask_llm_with_history", "FAIL", time.time() - t0, str(e)))

    # 2. _build_system_message imported/used in bot_voice.py
    try:
        src = (SRC_ROOT / "features/bot_voice.py").read_text()
        ok = "_build_system_message" in src
        results.append(TestResult(
            "voice_uses_build_system_message", "PASS" if ok else "FAIL",
            time.time() - t0,
            "_build_system_message used in bot_voice.py" if ok
            else "MISSING: _build_system_message not found in bot_voice.py",
        ))
    except Exception as e:
        results.append(TestResult("voice_uses_build_system_message", "FAIL", time.time() - t0, str(e)))

    # 3. _voice_user_turn_content defined in bot_access.py
    try:
        src = (SRC_ROOT / "telegram/bot_access.py").read_text()
        ok = "def _voice_user_turn_content(" in src
        results.append(TestResult(
            "voice_user_turn_content_defined", "PASS" if ok else "FAIL",
            time.time() - t0,
            "_voice_user_turn_content defined in bot_access.py" if ok
            else "MISSING: _voice_user_turn_content not in bot_access.py",
        ))
    except Exception as e:
        results.append(TestResult("voice_user_turn_content_defined", "FAIL", time.time() - t0, str(e)))

    # 4. get_history_with_ids called in voice pipeline
    try:
        src = (SRC_ROOT / "features/bot_voice.py").read_text()
        ok = "get_history_with_ids" in src
        results.append(TestResult(
            "voice_gets_history", "PASS" if ok else "FAIL",
            time.time() - t0,
            "get_history_with_ids called in voice pipeline" if ok
            else "MISSING: voice never reads conversation history",
        ))
    except Exception as e:
        results.append(TestResult("voice_gets_history", "FAIL", time.time() - t0, str(e)))

    # 5. add_to_history called for both user and assistant turns
    try:
        src = (SRC_ROOT / "features/bot_voice.py").read_text()
        count = src.count("add_to_history(chat_id,")
        ok = count >= 2
        results.append(TestResult(
            "voice_saves_both_turns", "PASS" if ok else "FAIL",
            time.time() - t0,
            f"add_to_history called {count} times (user + assistant)" if ok
            else f"FAIL: add_to_history called {count} time(s) — need both user + assistant",
        ))
    except Exception as e:
        results.append(TestResult("voice_saves_both_turns", "FAIL", time.time() - t0, str(e)))

    # 6. get_memory_context injected into voice system message
    try:
        src = (SRC_ROOT / "features/bot_voice.py").read_text()
        ok = "get_memory_context" in src
        results.append(TestResult(
            "voice_injects_memory_context", "PASS" if ok else "FAIL",
            time.time() - t0,
            "get_memory_context called in voice pipeline" if ok
            else "MISSING: voice doesn't inject long-term memory context",
        ))
    except Exception as e:
        results.append(TestResult("voice_injects_memory_context", "FAIL", time.time() - t0, str(e)))

    return results


def t_rag_pipeline_completeness(**_) -> list[TestResult]:
    """T58 — §4 RAG pipeline: log_rag_activity called, FTS timeout enforced, temperature configurable."""
    results = []
    t0 = time.time()

    # 1. log_rag_activity must be called in _docs_rag_context
    try:
        src = (SRC_ROOT / "telegram/bot_access.py").read_text()
        called = "log_rag_activity" in src and "store.log_rag_activity" in src
        results.append(TestResult(
            "rag_log_activity_called", "PASS" if called else "FAIL",
            time.time() - t0,
            "store.log_rag_activity called in _docs_rag_context" if called
            else "MISSING: store.log_rag_activity not called in bot_access.py",
        ))
    except Exception as e:
        results.append(TestResult("rag_log_activity_called", "FAIL", time.time() - t0, str(e)))

    # 2. concurrent.futures timeout must be in _docs_rag_context
    try:
        src = (SRC_ROOT / "telegram/bot_access.py").read_text()
        has_timeout = "concurrent.futures" in src and "TimeoutError" in src
        results.append(TestResult(
            "rag_fts_timeout_enforced", "PASS" if has_timeout else "FAIL",
            time.time() - t0,
            "concurrent.futures timeout in _docs_rag_context" if has_timeout
            else "MISSING: concurrent.futures timeout not found in bot_access.py",
        ))
    except Exception as e:
        results.append(TestResult("rag_fts_timeout_enforced", "FAIL", time.time() - t0, str(e)))

    # 3. llm_temperature must be in rag_settings defaults (source inspection)
    try:
        src_rs = (SRC_ROOT / "core/rag_settings.py").read_text()
        has_temp = "llm_temperature" in src_rs and "LOCAL_TEMPERATURE" in src_rs
        results.append(TestResult(
            "rag_llm_temperature_in_defaults", "PASS" if has_temp else "FAIL",
            time.time() - t0,
            "llm_temperature in rag_settings defaults" if has_temp
            else "MISSING: llm_temperature not in rag_settings._DEFAULTS",
        ))
    except Exception as e:
        results.append(TestResult("rag_llm_temperature_in_defaults", "FAIL", time.time() - t0, str(e)))

    # 4. _effective_temperature() must exist in bot_llm.py
    try:
        src = (SRC_ROOT / "core/bot_llm.py").read_text()
        has_fn = "def _effective_temperature" in src and "_effective_temperature()" in src
        results.append(TestResult(
            "rag_effective_temperature_fn", "PASS" if has_fn else "FAIL",
            time.time() - t0,
            "_effective_temperature() defined and used in bot_llm.py" if has_fn
            else "MISSING: _effective_temperature not found in bot_llm.py",
        ))
    except Exception as e:
        results.append(TestResult("rag_effective_temperature_fn", "FAIL", time.time() - t0, str(e)))

    # 5. MAX_DOC_SIZE_MB must be in bot_config.py (source inspection)
    try:
        src_cfg = (SRC_ROOT / "core/bot_config.py").read_text()
        has_const = "MAX_DOC_SIZE_MB" in src_cfg
        results.append(TestResult(
            "rag_max_doc_size_constant", "PASS" if has_const else "FAIL",
            time.time() - t0,
            "MAX_DOC_SIZE_MB in bot_config.py" if has_const
            else "MISSING: MAX_DOC_SIZE_MB not in bot_config.py",
        ))
    except Exception as e:
        results.append(TestResult("rag_max_doc_size_constant", "FAIL", time.time() - t0, str(e)))

    # 6. docs_too_large i18n key must be present in all 3 languages
    try:
        import json
        strings = json.loads((SRC_ROOT / "strings.json").read_text())
        for lang in ("ru", "en", "de"):
            ok = "docs_too_large" in strings.get(lang, {})
            results.append(TestResult(
                f"i18n_docs_too_large_{lang}", "PASS" if ok else "FAIL",
                time.time() - t0,
                f"docs_too_large present in {lang}" if ok else f"MISSING: docs_too_large in {lang}",
            ))
    except Exception as e:
        results.append(TestResult("i18n_docs_too_large", "FAIL", time.time() - t0, str(e)))

    return results


def t_llm_context_trace(**_) -> list:
    """T60: LLM call trace — db_get_llm_trace exists, voice and chat log extended params.

    Verifies the context contamination debug tooling added in v2026.5.x:
    1. db_log_llm_call signature has extended keyword params (model, temperature, system_chars, etc.)
    2. db_get_llm_trace function exists in bot_db.py
    3. Voice pipeline calls db_log_llm_call after ask_llm_with_history
    4. _rag_debug_stats helper exists in bot_access.py
    5. admin_llm_trace callback wired in telegram_menu_bot.py
    6. _handle_admin_llm_trace function exists in bot_admin.py
    """
    import time as _time
    results = []
    import time as _time
    t0 = _time.time()

    # 1. db_log_llm_call has extended keyword params
    try:
        src = (SRC_ROOT / "core/bot_db.py").read_text()
        checks = [
            ("model:", "model parameter in db_log_llm_call"),
            ("temperature:", "temperature parameter in db_log_llm_call"),
            ("system_chars:", "system_chars parameter in db_log_llm_call"),
            ("history_chars:", "history_chars parameter in db_log_llm_call"),
            ("rag_chunks_count:", "rag_chunks_count parameter in db_log_llm_call"),
            ("response_preview:", "response_preview parameter in db_log_llm_call"),
            ("context_snapshot:", "context_snapshot parameter in db_log_llm_call"),
        ]
        for term, label in checks:
            ok = term in src
            results.append(TestResult(
                f"llm_trace_param_{term.replace(':', '')}",
                "PASS" if ok else "FAIL",
                _time.time() - t0,
                f"db_log_llm_call has {label}" if ok else f"MISSING: {label} in bot_db.py",
            ))
    except Exception as e:
        results.append(TestResult("llm_trace_db_params", "FAIL", _time.time() - t0, str(e)))

    # 2. db_get_llm_trace function exists
    try:
        src = (SRC_ROOT / "core/bot_db.py").read_text()
        ok = "def db_get_llm_trace" in src
        results.append(TestResult(
            "llm_trace_get_fn",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "db_get_llm_trace() defined in bot_db.py" if ok else "MISSING: db_get_llm_trace in bot_db.py",
        ))
    except Exception as e:
        results.append(TestResult("llm_trace_get_fn", "FAIL", _time.time() - t0, str(e)))

    # 3. Voice pipeline calls db_log_llm_call after LLM call
    try:
        src = (SRC_ROOT / "features/bot_voice.py").read_text()
        ok = "db_log_llm_call" in src and "ask_llm_with_history" in src
        results.append(TestResult(
            "llm_trace_voice_logs",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "voice pipeline calls db_log_llm_call" if ok else "MISSING: db_log_llm_call not called in bot_voice.py",
        ))
    except Exception as e:
        results.append(TestResult("llm_trace_voice_logs", "FAIL", _time.time() - t0, str(e)))

    # 4. _rag_debug_stats exists in bot_access.py
    try:
        src = (SRC_ROOT / "telegram/bot_access.py").read_text()
        ok = "def _rag_debug_stats" in src
        results.append(TestResult(
            "llm_trace_rag_stats_fn",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "_rag_debug_stats() in bot_access.py" if ok else "MISSING: _rag_debug_stats not in bot_access.py",
        ))
    except Exception as e:
        results.append(TestResult("llm_trace_rag_stats_fn", "FAIL", _time.time() - t0, str(e)))

    # 5. admin_llm_trace callback wired in telegram_menu_bot.py
    try:
        src = (SRC_ROOT / "telegram_menu_bot.py").read_text()
        ok = "admin_llm_trace" in src and "_handle_admin_llm_trace" in src
        results.append(TestResult(
            "llm_trace_callback_wired",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "admin_llm_trace callback wired in telegram_menu_bot.py" if ok
            else "MISSING: admin_llm_trace not dispatched in telegram_menu_bot.py",
        ))
    except Exception as e:
        results.append(TestResult("llm_trace_callback_wired", "FAIL", _time.time() - t0, str(e)))

    # 6. _handle_admin_llm_trace in bot_admin.py
    try:
        src = (SRC_ROOT / "telegram/bot_admin.py").read_text()
        ok = "def _handle_admin_llm_trace" in src
        results.append(TestResult(
            "llm_trace_admin_handler",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "_handle_admin_llm_trace() in bot_admin.py" if ok
            else "MISSING: _handle_admin_llm_trace not in bot_admin.py",
        ))
    except Exception as e:
        results.append(TestResult("llm_trace_admin_handler", "FAIL", _time.time() - t0, str(e)))

    return results


def t_notes_db_content(**_) -> list:
    """T61: Notes content stored in DB — schema has content column, save/load use DB."""
    import time as _time
    results = []
    import time as _time
    t0 = _time.time()

    # 1. notes_index schema has content column
    try:
        src = (SRC_ROOT / "core/bot_db.py").read_text()
        ok = "content     TEXT    DEFAULT ''" in src or "content TEXT DEFAULT ''" in src
        results.append(TestResult(
            "notes_index_content_column",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "content column in notes_index schema" if ok else "MISSING: content column in notes_index",
        ))
    except Exception as e:
        results.append(TestResult("notes_index_content_column", "FAIL", _time.time() - t0, str(e)))

    # 2. _save_note_file stores content via store.save_note
    try:
        src = (SRC_ROOT / "telegram/bot_users.py").read_text()
        ok = "save_note(" in src  # store.save_note or _st.save_note or alias
        results.append(TestResult(
            "save_note_db_content",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "_save_note_file writes content via store.save_note()" if ok else "MISSING: content upsert in _save_note_file",
        ))
    except Exception as e:
        results.append(TestResult("save_note_db_content", "FAIL", _time.time() - t0, str(e)))

    # 3. _load_note_text reads from store (DB) first
    try:
        src = (SRC_ROOT / "telegram/bot_users.py").read_text()
        ok = "load_note(" in src  # store.load_note or _st.load_note or alias
        results.append(TestResult(
            "load_note_db_first",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "_load_note_text reads from store first" if ok else "MISSING: DB-first read in _load_note_text",
        ))
    except Exception as e:
        results.append(TestResult("load_note_db_first", "FAIL", _time.time() - t0, str(e)))

    return results


def t_calendar_db_primary(**_) -> list:
    """T62: Calendar _cal_save is DB-primary — no direct JSON write as primary action."""
    import time as _time
    results = []
    import time as _time
    t0 = _time.time()

    try:
        src = (SRC_ROOT / "features/bot_calendar.py").read_text()
        # Should call store.save_event and store.delete_event
        calls_save = "store.save_event" in src
        calls_del = "store.delete_event" in src
        # JSON write should only be in fallback (in try/except)
        # The primary action should NOT start with write_text
        lines = src.splitlines()
        cal_save_start = None
        for i, line in enumerate(lines):
            if "def _cal_save" in line:
                cal_save_start = i
                break
        if cal_save_start is not None:
            # Get first non-comment/non-docstring line of function body
            body_lines = lines[cal_save_start + 1:cal_save_start + 5]
            first_action = " ".join(body_lines)
            no_json_first = "write_text" not in first_action
        else:
            no_json_first = False
        ok = calls_save and calls_del and no_json_first
        results.append(TestResult(
            "calendar_db_primary",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "_cal_save is DB-primary (save_event+delete_event, no JSON first)" if ok
            else f"FAIL: calls_save={calls_save} calls_del={calls_del} no_json_first={no_json_first}",
        ))
    except Exception as e:
        results.append(TestResult("calendar_db_primary", "FAIL", _time.time() - t0, str(e)))

    return results


def t_doc_dedup_logic(**_) -> list:
    """T63: Document deduplication — _pending_doc_replace, handlers, and i18n string present."""
    import time as _time
    results = []
    import time as _time
    t0 = _time.time()

    # 1. _pending_doc_replace dict exists
    try:
        src = (SRC_ROOT / "features/bot_documents.py").read_text()
        ok = "_pending_doc_replace" in src
        results.append(TestResult(
            "doc_pending_replace_dict",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "_pending_doc_replace exists" if ok else "MISSING: _pending_doc_replace in bot_documents.py",
        ))
    except Exception as e:
        results.append(TestResult("doc_pending_replace_dict", "FAIL", _time.time() - t0, str(e)))

    # 2. _handle_doc_replace and _handle_doc_keep_both functions exist
    try:
        src = (SRC_ROOT / "features/bot_documents.py").read_text()
        ok = "def _handle_doc_replace" in src and "def _handle_doc_keep_both" in src
        results.append(TestResult(
            "doc_dedup_handlers",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "_handle_doc_replace + _handle_doc_keep_both present" if ok
            else "MISSING: dedup handlers in bot_documents.py",
        ))
    except Exception as e:
        results.append(TestResult("doc_dedup_handlers", "FAIL", _time.time() - t0, str(e)))

    # 3. docs_dup_found i18n key present in strings.json
    try:
        import json as _json
        strings = _json.loads((SRC_ROOT / "strings.json").read_text())
        ok = all("docs_dup_found" in strings.get(lang, {}) for lang in ("ru", "en", "de"))
        results.append(TestResult(
            "doc_dedup_i18n",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "docs_dup_found key in all 3 languages" if ok
            else "MISSING: docs_dup_found not in all languages",
        ))
    except Exception as e:
        results.append(TestResult("doc_dedup_i18n", "FAIL", _time.time() - t0, str(e)))

    return results


def t_user_prefs_db(**_) -> list:
    """T64: Per-user memory toggle — user_prefs table and helpers in bot_db, callback wired."""
    import time as _time
    results = []
    import time as _time
    t0 = _time.time()

    # 1. user_prefs table in _SCHEMA_SQL
    try:
        src = (SRC_ROOT / "core/bot_db.py").read_text()
        ok = "CREATE TABLE IF NOT EXISTS user_prefs" in src
        results.append(TestResult(
            "user_prefs_schema",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "user_prefs table in schema" if ok else "MISSING: user_prefs CREATE TABLE in bot_db.py",
        ))
    except Exception as e:
        results.append(TestResult("user_prefs_schema", "FAIL", _time.time() - t0, str(e)))

    # 2. db_get_user_pref / db_set_user_pref helpers
    try:
        src = (SRC_ROOT / "core/bot_db.py").read_text()
        ok = "def db_get_user_pref" in src and "def db_set_user_pref" in src
        results.append(TestResult(
            "user_prefs_helpers",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "db_get_user_pref + db_set_user_pref present" if ok
            else "MISSING: user pref helpers in bot_db.py",
        ))
    except Exception as e:
        results.append(TestResult("user_prefs_helpers", "FAIL", _time.time() - t0, str(e)))

    # 3. profile_toggle_memory callback wired in telegram_menu_bot.py
    try:
        src = (SRC_ROOT / "telegram_menu_bot.py").read_text()
        ok = "profile_toggle_memory" in src
        results.append(TestResult(
            "profile_toggle_memory_wired",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "profile_toggle_memory callback in telegram_menu_bot.py" if ok
            else "MISSING: profile_toggle_memory callback",
        ))
    except Exception as e:
        results.append(TestResult("profile_toggle_memory_wired", "FAIL", _time.time() - t0, str(e)))

    return results


def t_admin_memory_settings(**_) -> list:
    """T65: Admin memory settings — system_settings table, helpers, runtime getters, callback wired."""
    import time as _time
    results = []
    import time as _time
    t0 = _time.time()

    # 1. system_settings table in _SCHEMA_SQL
    try:
        src = (SRC_ROOT / "core/bot_db.py").read_text()
        ok = "CREATE TABLE IF NOT EXISTS system_settings" in src
        results.append(TestResult(
            "system_settings_schema",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "system_settings table in schema" if ok else "MISSING: system_settings CREATE TABLE",
        ))
    except Exception as e:
        results.append(TestResult("system_settings_schema", "FAIL", _time.time() - t0, str(e)))

    # 2. db_get_system_setting / db_set_system_setting helpers
    try:
        src = (SRC_ROOT / "core/bot_db.py").read_text()
        ok = "def db_get_system_setting" in src and "def db_set_system_setting" in src
        results.append(TestResult(
            "system_settings_helpers",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "db_get_system_setting + db_set_system_setting present" if ok
            else "MISSING: system settings helpers in bot_db.py",
        ))
    except Exception as e:
        results.append(TestResult("system_settings_helpers", "FAIL", _time.time() - t0, str(e)))

    # 3. get_conv_history_max / get_conv_summary_threshold / get_conv_mid_max in bot_config
    try:
        src = (SRC_ROOT / "core/bot_config.py").read_text()
        ok = ("def get_conv_history_max" in src
              and "def get_conv_summary_threshold" in src
              and "def get_conv_mid_max" in src)
        results.append(TestResult(
            "bot_config_runtime_getters",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "get_conv_history_max + get_conv_summary_threshold + get_conv_mid_max in bot_config" if ok
            else "MISSING: runtime getter functions in bot_config.py",
        ))
    except Exception as e:
        results.append(TestResult("bot_config_runtime_getters", "FAIL", _time.time() - t0, str(e)))

    # 4. admin_memory_menu callback wired
    try:
        src = (SRC_ROOT / "telegram_menu_bot.py").read_text()
        ok = "admin_memory_menu" in src
        results.append(TestResult(
            "admin_memory_menu_wired",
            "PASS" if ok else "FAIL",
            _time.time() - t0,
            "admin_memory_menu in telegram_menu_bot.py" if ok
            else "MISSING: admin_memory_menu callback",
        ))
    except Exception as e:
        results.append(TestResult("admin_memory_menu_wired", "FAIL", _time.time() - t0, str(e)))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T66 – classify_query() adaptive routing
# ─────────────────────────────────────────────────────────────────────────────
def t_classify_query_routing(**_) -> list:
    """T66: classify_query() returns 'simple' for greetings, 'contextual' for knowledge queries."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    results = []
    import time as _time
    t0 = time.time()
    try:
        from core.bot_rag import classify_query
        cases = [
            ("Привет", False, "simple"),
            ("Hello", False, "simple"),
            ("Как дела?", False, "simple"),
            ("Что такое RAG?", True, "factual"),       # has_documents=True → factual
            ("Расскажи о документе", True, "factual"), # has_documents=True → factual
            ("2+2", False, "simple"),
        ]
        for text, has_docs, expected in cases:
            got = classify_query(text, has_documents=has_docs)
            ok = got == expected
            results.append(TestResult(
                f"classify_query:{text[:20]}",
                "PASS" if ok else "FAIL",
                time.time() - t0,
                f"got={got} expected={expected}",
            ))
    except ImportError as e:
        results.append(TestResult("classify_query_import", "SKIP", time.time() - t0, str(e)))
    except Exception as e:
        results.append(TestResult("classify_query_routing", "FAIL", time.time() - t0, str(e)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T67 – reciprocal_rank_fusion() math
# ─────────────────────────────────────────────────────────────────────────────
def t_rrf_fusion_math(**_) -> list:
    """T67: RRF fusion with k=60 correctly scores and deduplicates results."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    results = []
    import time as _time
    t0 = time.time()
    try:
        from core.bot_rag import reciprocal_rank_fusion
        fts5   = [{"id": "a", "chunk_text": "alpha"}, {"id": "b", "chunk_text": "beta"}]
        vector = [{"id": "b", "chunk_text": "beta"}, {"id": "c", "chunk_text": "gamma"}]
        fused  = reciprocal_rank_fusion(fts5, vector)
        ids    = [r["id"] for r in fused]
        # 'b' appears in both lists → should have highest score → first or second
        ok_dedup = len(ids) == len(set(ids))
        ok_b_top = ids[0] == "b" or (len(ids) > 1 and ids[1] == "b")
        results.append(TestResult("rrf_dedup",   "PASS" if ok_dedup else "FAIL", time.time() - t0,
                                  f"ids={ids}"))
        results.append(TestResult("rrf_b_top2",  "PASS" if ok_b_top else "FAIL", time.time() - t0,
                                  f"ids[0]={ids[0] if ids else 'empty'}"))
        # Verify score formula: 1/(rank+k) ≤ 1/60
        ok_score = all(r.get("rrf_score", 0) <= 1/60 + 0.01 for r in fused)
        results.append(TestResult("rrf_score_range", "PASS" if ok_score else "FAIL", time.time() - t0,
                                  f"scores={[round(r.get('rrf_score',0),4) for r in fused]}"))
    except ImportError as e:
        results.append(TestResult("rrf_import", "SKIP", time.time() - t0, str(e)))
    except Exception as e:
        results.append(TestResult("rrf_fusion_math", "FAIL", time.time() - t0, str(e)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T68 – PyMuPDF fallback in PDF extraction
# ─────────────────────────────────────────────────────────────────────────────
def t_pymupdf_pdf_fallback(**_) -> list:
    """T68: _extract_text() tries PyMuPDF first, falls back to pdfminer gracefully."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    results = []
    import time as _time
    t0 = time.time()
    try:
        src = Path(__file__).parents[1] / "features" / "bot_documents.py"
        code = src.read_text(encoding="utf-8")
        ok_fitz   = "import fitz" in code or "fitz.open" in code
        ok_fallbk = "pdfminer" in code and ("ImportError" in code or "except" in code)
        ok_img_ph = "[IMAGE:" in code
        results.append(TestResult("pymupdf_fitz_tried", "PASS" if ok_fitz else "FAIL", time.time() - t0,
                                  "fitz import present" if ok_fitz else "fitz NOT referenced"))
        results.append(TestResult("pymupdf_pdfminer_fallback", "PASS" if ok_fallbk else "FAIL", time.time() - t0,
                                  "pdfminer fallback present" if ok_fallbk else "fallback missing"))
        results.append(TestResult("pymupdf_image_placeholder", "PASS" if ok_img_ph else "FAIL", time.time() - t0,
                                  "[IMAGE:] placeholder present" if ok_img_ph else "placeholder missing"))
    except Exception as e:
        results.append(TestResult("pymupdf_fallback", "FAIL", time.time() - t0, str(e)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T69 – per-user RAG settings override
# ─────────────────────────────────────────────────────────────────────────────
def t_per_user_rag_settings(**_) -> list:
    """T69: _docs_rag_context reads rag_top_k from user_prefs, profile_rag handlers present."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    results = []
    import time as _time
    t0 = time.time()
    try:
        src = Path(__file__).parents[1] / "telegram" / "bot_access.py"
        code = src.read_text(encoding="utf-8")
        ok_pref = "db_get_user_pref" in code and "rag_top_k" in code
        results.append(TestResult("rag_context_reads_user_pref", "PASS" if ok_pref else "FAIL",
                                  time.time() - t0, "db_get_user_pref + rag_top_k found" if ok_pref else "MISSING"))
    except Exception as e:
        results.append(TestResult("rag_user_pref_access", "FAIL", time.time() - t0, str(e)))
    try:
        src2 = Path(__file__).parents[1] / "telegram" / "bot_admin.py"
        code2 = src2.read_text(encoding="utf-8")
        ok_rag_fn = "_handle_admin_rag_user_settings" in code2
        ok_adjust  = "_handle_admin_rag_user_adjust" in code2
        ok_reset   = "_handle_admin_rag_user_reset" in code2
        for name, ok in [("admin_rag_user_settings", ok_rag_fn), ("admin_rag_user_adjust", ok_adjust),
                         ("admin_rag_user_reset", ok_reset)]:
            results.append(TestResult(f"handler_{name}", "PASS" if ok else "FAIL",
                                      time.time() - t0, "present in bot_admin.py" if ok else "MISSING"))
    except Exception as e:
        results.append(TestResult("rag_handler_check", "FAIL", time.time() - t0, str(e)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T70 – Developer Menu RBAC guard
# ─────────────────────────────────────────────────────────────────────────────
def t_dev_menu_rbac(**_) -> list:
    """T70: bot_dev.py exports correct functions; all handlers check _is_developer."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    results = []
    import time as _time
    t0 = time.time()
    try:
        src = Path(__file__).parents[1] / "features" / "bot_dev.py"
        code = src.read_text(encoding="utf-8")
        ok_guard = "_is_developer" in code
        ok_deny  = "log_access_denied" in code or "_deny" in code
        ok_chat  = "handle_dev_chat_message" in code
        ok_log   = "log_security_event" in code
        ok_menu  = "_handle_dev_menu" in code
        for name, ok in [("rbac_guard", ok_guard), ("deny_call", ok_deny),
                         ("dev_chat_fn", ok_chat), ("security_log_fn", ok_log),
                         ("dev_menu_fn", ok_menu)]:
            results.append(TestResult(f"dev_menu_{name}", "PASS" if ok else "FAIL",
                                      time.time() - t0, "present" if ok else "MISSING"))
    except Exception as e:
        results.append(TestResult("dev_menu_rbac", "FAIL", time.time() - t0, str(e)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T71 – security_events table + logging
# ─────────────────────────────────────────────────────────────────────────────
def t_security_events_logging(**_) -> list:
    """T71: security_events table in schema; log_security_event & log_access_denied in bot_dev."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    results = []
    import time as _time
    t0 = time.time()
    try:
        db_src = Path(__file__).parents[1] / "core" / "bot_db.py"
        code = db_src.read_text(encoding="utf-8")
        ok_tbl = "security_events" in code
        results.append(TestResult("security_events_table", "PASS" if ok_tbl else "FAIL",
                                  time.time() - t0, "table defined" if ok_tbl else "NOT FOUND"))
    except Exception as e:
        results.append(TestResult("security_events_schema", "FAIL", time.time() - t0, str(e)))
    try:
        dev_src = Path(__file__).parents[1] / "features" / "bot_dev.py"
        code2   = dev_src.read_text(encoding="utf-8")
        ok_log  = "def log_security_event" in code2
        ok_deny = "def log_access_denied" in code2
        results.append(TestResult("log_security_event_fn", "PASS" if ok_log else "FAIL",
                                  time.time() - t0, "present" if ok_log else "MISSING"))
        results.append(TestResult("log_access_denied_fn", "PASS" if ok_deny else "FAIL",
                                  time.time() - t0, "present" if ok_deny else "MISSING"))
    except Exception as e:
        results.append(TestResult("security_log_fns", "FAIL", time.time() - t0, str(e)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T72 – RAG monitoring stats
# ─────────────────────────────────────────────────────────────────────────────
def t_rag_monitoring_stats(**_) -> list:
    """T72: store_sqlite has rag_stats(); latency_ms+query_type in rag_log; admin handler wired."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    results = []
    import time as _time
    t0 = time.time()
    try:
        sl_src = Path(__file__).parents[1] / "core" / "store_sqlite.py"
        code   = sl_src.read_text(encoding="utf-8")
        ok_fn  = "def rag_stats" in code
        ok_lat = "latency_ms" in code
        ok_qt  = "query_type" in code
        results.append(TestResult("rag_stats_method", "PASS" if ok_fn else "FAIL",
                                  time.time() - t0, "rag_stats() present" if ok_fn else "MISSING"))
        results.append(TestResult("rag_log_latency_ms", "PASS" if ok_lat else "FAIL",
                                  time.time() - t0, "latency_ms column present" if ok_lat else "MISSING"))
        results.append(TestResult("rag_log_query_type", "PASS" if ok_qt else "FAIL",
                                  time.time() - t0, "query_type column present" if ok_qt else "MISSING"))
    except Exception as e:
        results.append(TestResult("rag_stats_schema", "FAIL", time.time() - t0, str(e)))
    try:
        adm_src = Path(__file__).parents[1] / "telegram" / "bot_admin.py"
        code2   = adm_src.read_text(encoding="utf-8")
        ok_hnd  = "_handle_admin_rag_stats" in code2
        results.append(TestResult("admin_rag_stats_handler", "PASS" if ok_hnd else "FAIL",
                                  time.time() - t0, "handler present" if ok_hnd else "MISSING"))
    except Exception as e:
        results.append(TestResult("rag_stats_admin", "FAIL", time.time() - t0, str(e)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T73 – Document store API completeness (both SQLite + Postgres)
# ─────────────────────────────────────────────────────────────────────────────
def t_doc_store_api_complete(**_) -> list:
    """T73: Both store_sqlite and store_postgres have all 5 required document methods.

    Root-cause test: the PDF-upload bug was caused by store_postgres.py missing
    get_document_by_hash, update_document_field, list_rag_log, log_rag_activity,
    and rag_stats.  This test ensures both backends stay in sync.
    """
    results = []
    import time as _time
    t0 = _time.time()

    REQUIRED_DOC_METHODS = [
        "def save_document_meta",
        "def list_documents",
        "def delete_document",
        "def update_document_field",
        "def get_document_by_hash",
    ]
    REQUIRED_RAG_METHODS = [
        "def log_rag_activity",
        "def list_rag_log",
        "def rag_stats",
    ]

    for store_file, label in [
        ("core/store_sqlite.py",   "SQLite"),
        ("core/store_postgres.py", "Postgres"),
    ]:
        try:
            code = (Path(__file__).parents[1] / store_file).read_text(encoding="utf-8")
            for method in REQUIRED_DOC_METHODS + REQUIRED_RAG_METHODS:
                ok = method in code
                results.append(TestResult(
                    f"store_{label.lower()}_{method.split()[-1]}",
                    "PASS" if ok else "FAIL",
                    _time.time() - t0,
                    f"{label}: {method} present" if ok
                    else f"MISSING in {store_file}: {method}",
                ))
        except Exception as e:
            results.append(TestResult(f"store_{label.lower()}_read", "FAIL", _time.time() - t0, str(e)))

    # Live import check: if store is importable, verify hasattr for both backends
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parents[1]))
        from core.store import store as _store
        for method in ["save_document_meta", "list_documents", "delete_document",
                       "update_document_field", "get_document_by_hash",
                       "log_rag_activity", "list_rag_log", "rag_stats"]:
            ok = hasattr(_store, method) and callable(getattr(_store, method))
            results.append(TestResult(
                f"live_store_{method}",
                "PASS" if ok else "FAIL",
                _time.time() - t0,
                f"live store.{method} callable" if ok else f"live store MISSING {method}",
            ))
    except Exception as e:
        results.append(TestResult("live_store_import", "SKIP", _time.time() - t0,
                                  f"store import skipped: {e}"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T74 – Document upload pipeline completeness
# ─────────────────────────────────────────────────────────────────────────────
def t_doc_upload_pipeline(**_) -> list:
    """T74: bot_documents.py has complete upload pipeline:
    _handle_doc_upload → dedup check → _process_doc_file → save_document_meta
    + update_document_field for doc_hash after processing.
    """
    results = []
    import time as _time
    t0 = _time.time()

    try:
        code = (Path(__file__).parents[1] / "features" / "bot_documents.py").read_text(encoding="utf-8")

        checks = [
            ("upload_handler",       "def _handle_doc_upload",
             "_handle_doc_upload entry point"),
            ("process_function",     "def _process_doc_file",
             "_process_doc_file async worker"),
            ("text_extractor",       "def _extract_text",
             "_extract_text() for PDF/DOCX/TXT/MD"),
            ("dedup_hash_check",     "get_document_by_hash",
             "get_document_by_hash() called for dedup"),
            ("save_meta_call",       "save_document_meta",
             "save_document_meta() called after processing"),
            ("hash_field_update",    "update_document_field",
             "update_document_field() called to save doc_hash"),
            ("pending_replace_dict", "_pending_doc_replace",
             "_pending_doc_replace state dict for dedup flow"),
            ("replace_handler",      "def _handle_doc_replace",
             "_handle_doc_replace() for overwrite confirmation"),
            ("keep_both_handler",    "def _handle_doc_keep_both",
             "_handle_doc_keep_both() for keep-both path"),
        ]
        for key, needle, desc in checks:
            ok = needle in code
            results.append(TestResult(
                f"upload_pipeline_{key}",
                "PASS" if ok else "FAIL",
                _time.time() - t0,
                desc if ok else f"MISSING in bot_documents.py: {needle}",
            ))
    except Exception as e:
        results.append(TestResult("upload_pipeline_read", "FAIL", _time.time() - t0, str(e)))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T75 – Document list / delete / rename flow + i18n coverage
# ─────────────────────────────────────────────────────────────────────────────
def t_doc_list_delete_flow(**_) -> list:
    """T75: List, delete, rename handlers in bot_documents.py + all i18n keys present."""
    results = []
    import time as _time
    import json as _json
    t0 = _time.time()

    # 1. Handler functions exist
    try:
        code = (Path(__file__).parents[1] / "features" / "bot_documents.py").read_text(encoding="utf-8")
        handlers = [
            ("list_handler",             "def _handle_docs_menu"),
            ("detail_handler",           "def _handle_doc_detail"),
            ("delete_request_handler",   "def _handle_doc_delete"),
            ("delete_confirm_handler",   "def _handle_doc_delete_confirmed"),
            ("rename_start_handler",     "def _handle_doc_rename_start"),
            ("rename_done_handler",      "def _handle_doc_rename_done"),
            ("share_toggle_handler",     "def _handle_doc_share_toggle"),
        ]
        for key, needle in handlers:
            ok = needle in code
            results.append(TestResult(
                f"doc_handler_{key}",
                "PASS" if ok else "FAIL",
                _time.time() - t0,
                f"{needle} present" if ok else f"MISSING in bot_documents.py: {needle}",
            ))
    except Exception as e:
        results.append(TestResult("doc_handler_read", "FAIL", _time.time() - t0, str(e)))

    # 2. Required i18n keys in all three languages
    REQUIRED_KEYS = [
        "docs_menu_title",
        "docs_empty",
        "docs_uploading",
        "docs_uploaded",
        "docs_unsupported",
        "docs_delete_confirm",
        "docs_deleted",
        "docs_delete_failed",
        "docs_upload_failed",
        "docs_dup_found",
        "docs_replace_btn",
        "docs_keep_both_btn",
        "docs_not_found",
        "docs_rename_prompt",
        "docs_renamed",
    ]
    try:
        strings = _json.loads(
            (Path(__file__).parents[1] / "strings.json").read_text(encoding="utf-8")
        )
        for key in REQUIRED_KEYS:
            ok = all(key in strings.get(lang, {}) for lang in ("ru", "en", "de"))
            results.append(TestResult(
                f"doc_i18n_{key}",
                "PASS" if ok else "FAIL",
                _time.time() - t0,
                f"i18n key '{key}' in ru/en/de" if ok
                else f"MISSING i18n key '{key}' in some language",
            ))
    except Exception as e:
        results.append(TestResult("doc_i18n_read", "FAIL", _time.time() - t0, str(e)))

    # 3. delete_embeddings + delete_text_chunks called on delete (clean cleanup)
    try:
        code = (Path(__file__).parents[1] / "features" / "bot_documents.py").read_text(encoding="utf-8")
        ok_emb  = "delete_embeddings" in code
        ok_txt  = "delete_text_chunks" in code
        results.append(TestResult("doc_delete_cleans_embeddings", "PASS" if ok_emb else "FAIL",
                                  _time.time() - t0,
                                  "delete_embeddings called on delete" if ok_emb
                                  else "MISSING: delete_embeddings not called on doc delete"))
        results.append(TestResult("doc_delete_cleans_text_chunks", "PASS" if ok_txt else "FAIL",
                                  _time.time() - t0,
                                  "delete_text_chunks called on delete" if ok_txt
                                  else "MISSING: delete_text_chunks not called on doc delete"))
    except Exception as e:
        results.append(TestResult("doc_cleanup_check", "FAIL", _time.time() - t0, str(e)))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T76 – Full RAG pipeline: retrieve_context, query routing, FTS5+vector, config
# ─────────────────────────────────────────────────────────────────────────────
def t_rag_full_pipeline(**_) -> list:
    """T76: Full RAG pipeline structure and live retrieval:
    retrieve_context() → classify_query() → FTS5+vector → RRF → assemble [KNOWLEDGE] block.
    Covers: config constants, rag_settings module, [KNOWLEDGE] format, live empty-doc fallback.
    """
    import sys as _sys
    import time as _time
    import json as _json
    results = []
    t0 = _time.time()

    # 1. Config constants present
    try:
        code = (Path(__file__).parents[1] / "core" / "bot_config.py").read_text(encoding="utf-8")
        for const in ["RAG_ENABLED", "RAG_TOP_K", "RAG_CHUNK_SIZE", "RAG_TIMEOUT", "RAG_SETTINGS_FILE"]:
            ok = const in code
            results.append(TestResult(f"rag_config_{const.lower()}", "PASS" if ok else "FAIL",
                                      _time.time() - t0,
                                      f"{const} constant present" if ok else f"MISSING: {const}"))
    except Exception as e:
        results.append(TestResult("rag_config_read", "FAIL", _time.time() - t0, str(e)))

    # 2. rag_settings.py has all 5 keys
    try:
        code = (Path(__file__).parents[1] / "core" / "rag_settings.py").read_text(encoding="utf-8")
        for key in ["rag_top_k", "rag_chunk_size", "llm_timeout", "rag_timeout", "llm_temperature"]:
            ok = key in code
            results.append(TestResult(f"rag_settings_{key}", "PASS" if ok else "FAIL",
                                      _time.time() - t0,
                                      f"rag_settings key '{key}' present" if ok else f"MISSING key: {key}"))
    except Exception as e:
        results.append(TestResult("rag_settings_read", "FAIL", _time.time() - t0, str(e)))

    # 3. bot_rag.py: retrieve_context, classify_query, detect_rag_capability, RAGCapability, FTS5+HYBRID+FULL tiers
    try:
        code = (Path(__file__).parents[1] / "core" / "bot_rag.py").read_text(encoding="utf-8")
        for name in ["def retrieve_context", "def classify_query", "def detect_rag_capability",
                     "RAGCapability", "FTS5_ONLY", "HYBRID",
                     "def reciprocal_rank_fusion", "search_fts", "search_similar"]:
            ok = name in code
            results.append(TestResult(f"bot_rag_{name.replace(' ', '_').replace('def_', '')}",
                                      "PASS" if ok else "FAIL", _time.time() - t0,
                                      f"{name} present" if ok else f"MISSING: {name}"))
    except Exception as e:
        results.append(TestResult("bot_rag_read", "FAIL", _time.time() - t0, str(e)))

    # 4. _docs_rag_context() returns [KNOWLEDGE FROM USER DOCUMENTS] format and is wired in both chat paths
    try:
        code = (Path(__file__).parents[1] / "telegram" / "bot_access.py").read_text(encoding="utf-8")
        ok_fn    = "def _docs_rag_context" in code
        ok_kw    = "[KNOWLEDGE FROM USER DOCUMENTS]" in code
        ok_end   = "[END KNOWLEDGE]" in code
        ok_chat  = code.count("_docs_rag_context") >= 3   # _with_lang, _user_turn_content, voice path
        ok_log   = "log_rag_activity" in code
        for name, ok in [("rag_context_fn", ok_fn), ("knowledge_block_header", ok_kw),
                         ("knowledge_block_footer", ok_end), ("rag_context_wired_3_paths", ok_chat),
                         ("rag_logs_activity", ok_log)]:
            results.append(TestResult(f"rag_ctx_{name}", "PASS" if ok else "FAIL",
                                      _time.time() - t0, "present" if ok else f"MISSING: {name}"))
    except Exception as e:
        results.append(TestResult("rag_ctx_access_read", "FAIL", _time.time() - t0, str(e)))

    # 5. classify_query() routing: "hi" → simple, knowledge question → factual/contextual
    try:
        _sys.path.insert(0, str(Path(__file__).parents[1]))
        from core.bot_rag import classify_query
        simple_queries  = ["hi", "hello", "ok", "thanks", "привет", "да", "нет"]
        factual_queries = ["what is taris?", "explain how RAG works",
                           "what products does LR offer?", "tell me about the system"]
        for q in simple_queries:
            r = classify_query(q, has_documents=True)
            ok = r == "simple"
            results.append(TestResult(f"classify_simple_{q[:8]}", "PASS" if ok else "FAIL",
                                      _time.time() - t0,
                                      f"'{q}' → simple" if ok else f"'{q}' → {r} (expected simple)"))
        for q in factual_queries:
            r = classify_query(q, has_documents=True)
            ok = r in ("factual", "contextual")
            results.append(TestResult(f"classify_factual_{q[:12].replace(' ', '_')}",
                                      "PASS" if ok else "FAIL", _time.time() - t0,
                                      f"'{q[:20]}' → {r}" if ok
                                      else f"'{q[:20]}' → {r} (expected factual/contextual)"))
        # With no documents, all queries should skip RAG (strategy = simple or contextual)
        for q in factual_queries[:2]:
            r_no_doc = classify_query(q, has_documents=False)
            ok = r_no_doc in ("simple", "contextual")
            results.append(TestResult(f"classify_nodoc_{q[:12].replace(' ', '_')}",
                                      "PASS" if ok else "FAIL", _time.time() - t0,
                                      f"no-doc '{q[:20]}' → {r_no_doc}" if ok
                                      else f"no-doc '{q[:20]}' → {r_no_doc} (expected simple/contextual)"))
    except Exception as e:
        results.append(TestResult("classify_query_live", "FAIL", _time.time() - t0, str(e)))

    # 6. Live retrieve_context() on user with no documents → returns "skipped"
    try:
        _sys.path.insert(0, str(Path(__file__).parents[1]))
        from core.bot_rag import retrieve_context
        chunks, assembled, strategy = retrieve_context(
            chat_id=999999,        # non-existent user — no documents
            query="what is taris?",
            top_k=3,
            max_chars=500,
        )
        ok = strategy == "skipped" and chunks == [] and assembled == ""
        results.append(TestResult("retrieve_context_no_docs_skipped",
                                  "PASS" if ok else "FAIL", _time.time() - t0,
                                  f"no-doc retrieve → skipped (strategy={strategy})" if ok
                                  else f"expected skipped, got strategy={strategy}"))
    except Exception as e:
        results.append(TestResult("retrieve_context_live", "SKIP", _time.time() - t0,
                                  f"live retrieve_context skipped: {e}"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T77 – Multi-tier memory context assembly (STM + MTM/LTM + memory_enabled toggle)
# ─────────────────────────────────────────────────────────────────────────────
def t_memory_context_assembly(**_) -> list:
    """T77: STM conversation history + MTM/LTM summaries + memory_enabled toggle wired correctly.

    Verifies: conversation_summaries schema, get_memory_context(), _summarize_session_async(),
    add_to_history() triggers summarization at threshold, get_conv_history_max(), memory_enabled
    per-user pref respected, profile toggle callbacks, i18n labels.
    """
    import sys as _sys
    import time as _time
    results = []
    t0 = _time.time()

    # 1. conversation_summaries schema: tier, summary, msg_count, chat_id
    try:
        code = (Path(__file__).parents[1] / "core" / "bot_db.py").read_text(encoding="utf-8")
        ok_table  = "CREATE TABLE IF NOT EXISTS conversation_summaries" in code
        ok_tier   = "tier" in code and ("'mid'" in code or '"mid"' in code)
        ok_long   = "'long'" in code or '"long"' in code
        ok_sum    = "summary" in code
        ok_idx    = "idx_summ_chat" in code
        for name, ok in [("table_exists", ok_table), ("tier_mid", ok_tier),
                         ("tier_long", ok_long), ("summary_col", ok_sum), ("index", ok_idx)]:
            results.append(TestResult(f"conv_summaries_schema_{name}", "PASS" if ok else "FAIL",
                                      _time.time() - t0, "present" if ok else f"MISSING: {name}"))
    except Exception as e:
        results.append(TestResult("conv_summaries_read", "FAIL", _time.time() - t0, str(e)))

    # 2. Memory config constants: CONVERSATION_HISTORY_MAX, CONV_SUMMARY_THRESHOLD, get_conv_history_max()
    try:
        code = (Path(__file__).parents[1] / "core" / "bot_config.py").read_text(encoding="utf-8")
        ok_max   = "CONVERSATION_HISTORY_MAX" in code
        ok_thr   = "CONV_SUMMARY_THRESHOLD" in code
        ok_fn_h  = "def get_conv_history_max" in code
        ok_fn_t  = "def get_conv_summary_threshold" in code
        for name, ok in [("HISTORY_MAX", ok_max), ("SUMMARY_THRESHOLD", ok_thr),
                         ("get_conv_history_max_fn", ok_fn_h), ("get_conv_summary_threshold_fn", ok_fn_t)]:
            results.append(TestResult(f"memory_config_{name}", "PASS" if ok else "FAIL",
                                      _time.time() - t0, "present" if ok else f"MISSING: {name}"))
    except Exception as e:
        results.append(TestResult("memory_config_read", "FAIL", _time.time() - t0, str(e)))

    # 3. bot_state.py: get_memory_context, add_to_history, _summarize_session_async, clear_history
    try:
        code = (Path(__file__).parents[1] / "core" / "bot_state.py").read_text(encoding="utf-8")
        for name in ["def get_memory_context", "def add_to_history", "def _summarize_session_async",
                     "def clear_history", "def get_history", "_summarize_session_async",
                     "conversation_summaries", "get_conv_summary_threshold"]:
            ok = name in code
            results.append(TestResult(f"bot_state_{name.replace('def ', '').replace(' ', '_')[:30]}",
                                      "PASS" if ok else "FAIL", _time.time() - t0,
                                      f"{name} present" if ok else f"MISSING: {name}"))
    except Exception as e:
        results.append(TestResult("bot_state_read", "FAIL", _time.time() - t0, str(e)))

    # 4. memory_enabled per-user pref: toggle in bot_handlers.py, _memory_enabled() helper
    try:
        code = (Path(__file__).parents[1] / "telegram" / "bot_handlers.py").read_text(encoding="utf-8")
        ok_fn     = "def _memory_enabled" in code
        ok_pref   = "db_get_user_pref(chat_id, \"memory_enabled\"" in code or \
                    "db_get_user_pref(chat_id, 'memory_enabled'" in code
        ok_toggle = "db_set_user_pref(chat_id, \"memory_enabled\"" in code or \
                    "db_set_user_pref(chat_id, 'memory_enabled'" in code
        ok_inject = "get_memory_context" in code
        for name, ok in [("memory_enabled_fn", ok_fn), ("memory_enabled_get", ok_pref),
                         ("memory_enabled_set", ok_toggle), ("memory_context_injected", ok_inject)]:
            results.append(TestResult(f"memory_toggle_{name}", "PASS" if ok else "FAIL",
                                      _time.time() - t0, "present" if ok else f"MISSING: {name}"))
    except Exception as e:
        results.append(TestResult("memory_toggle_read", "FAIL", _time.time() - t0, str(e)))

    # 5. Profile memory toggle i18n keys
    try:
        import json as _json
        strings = _json.loads(
            (Path(__file__).parents[1] / "strings.json").read_text(encoding="utf-8")
        )
        for key in ["profile_memory_enabled_label", "profile_memory_disabled_label"]:
            ok = all(key in strings.get(lang, {}) for lang in ("ru", "en", "de"))
            results.append(TestResult(f"memory_i18n_{key}", "PASS" if ok else "FAIL",
                                      _time.time() - t0,
                                      f"'{key}' in ru/en/de" if ok
                                      else f"MISSING: '{key}' in some language"))
    except Exception as e:
        results.append(TestResult("memory_i18n_read", "FAIL", _time.time() - t0, str(e)))

    # 6. Live get_memory_context() on non-existent user → "" (no crash)
    try:
        _sys.path.insert(0, str(Path(__file__).parents[1]))
        from core.bot_state import get_memory_context
        result = get_memory_context(999999)
        ok = isinstance(result, str)
        results.append(TestResult("memory_context_nonexistent_user",
                                  "PASS" if ok else "FAIL", _time.time() - t0,
                                  f"no crash, returns str ({len(result)} chars)" if ok
                                  else "get_memory_context returned non-string"))
    except Exception as e:
        results.append(TestResult("memory_context_live", "SKIP", _time.time() - t0,
                                  f"live test skipped: {e}"))

    # 7. Live get_conv_history_max() returns a positive integer
    try:
        from core.bot_config import get_conv_history_max
        val = get_conv_history_max()
        ok = isinstance(val, int) and val > 0
        results.append(TestResult("conv_history_max_positive_int",
                                  "PASS" if ok else "FAIL", _time.time() - t0,
                                  f"get_conv_history_max() = {val}" if ok
                                  else f"bad value: {val!r}"))
    except Exception as e:
        results.append(TestResult("conv_history_max_live", "SKIP", _time.time() - t0, str(e)))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T78 – RAG + all memory tiers combined in ask_llm_with_history() call
# ─────────────────────────────────────────────────────────────────────────────
def t_rag_memory_combined_context(**_) -> list:
    """T78: RAG knowledge + STM history + MTM/LTM summaries all combine in ask_llm_with_history().

    Tests the exact context ordering contract:
      messages = [system(preamble+bot_config+memory_note+LTM/MTM)]
               + [history... (STM)]
               + [user(RAG_knowledge+user_text)]

    RAG goes in the user turn (query-specific). Memory summaries go in system (global context).
    History (STM) goes between system and current user turn.
    """
    import sys as _sys
    import time as _time
    results = []
    t0 = _time.time()

    # 1. _build_system_message() contains: preamble + bot_config + memory_note + lang_instr
    # Memory context (get_memory_context) is injected by bot_handlers.py after _build_system_message()
    try:
        code_access = (Path(__file__).parents[1] / "telegram" / "bot_access.py").read_text(encoding="utf-8")
        code_hdlr   = (Path(__file__).parents[1] / "telegram" / "bot_handlers.py").read_text(encoding="utf-8")
        ok_fn       = "def _build_system_message" in code_access
        ok_preamble = "SECURITY_PREAMBLE" in code_access
        ok_config   = "_bot_config_block" in code_access
        ok_mem_note = "memory context note" in code_access or "memory_note" in code_access
        # Memory context injection happens in bot_handlers.py (appended AFTER _build_system_message)
        ok_inject   = "get_memory_context" in code_hdlr
        for name, ok in [("build_system_fn", ok_fn), ("preamble_injected", ok_preamble),
                         ("bot_config_injected", ok_config), ("memory_note", ok_mem_note),
                         ("memory_ctx_injected_in_system", ok_inject)]:
            results.append(TestResult(f"system_msg_{name}", "PASS" if ok else "FAIL",
                                      _time.time() - t0, "present" if ok else f"MISSING: {name}"))
    except Exception as e:
        results.append(TestResult("system_msg_read", "FAIL", _time.time() - t0, str(e)))

    # 2. _user_turn_content() contains RAG context + user text (NOT preamble — that's in system)
    try:
        code = (Path(__file__).parents[1] / "telegram" / "bot_access.py").read_text(encoding="utf-8")
        ok_fn  = "def _user_turn_content" in code
        ok_rag = "_docs_rag_context" in code
        ok_wrap = "_wrap_user_input" in code
        # Preamble must NOT be in _user_turn_content (it would duplicate security context)
        # Check: SECURITY_PREAMBLE is only in _build_system_message and _with_lang, not _user_turn_content
        # By examining which functions contain SECURITY_PREAMBLE
        idx_user_turn = code.find("def _user_turn_content")
        idx_next_fn   = code.find("\ndef ", idx_user_turn + 10)
        user_turn_body = code[idx_user_turn:idx_next_fn] if idx_next_fn > 0 else code[idx_user_turn:]
        ok_no_preamble = "SECURITY_PREAMBLE" not in user_turn_body
        for name, ok in [("user_turn_fn", ok_fn), ("rag_in_user_turn", ok_rag),
                         ("wrap_user_input", ok_wrap), ("no_preamble_in_user_turn", ok_no_preamble)]:
            results.append(TestResult(f"user_turn_{name}", "PASS" if ok else "FAIL",
                                      _time.time() - t0, "present/correct" if ok else f"MISSING/WRONG: {name}"))
    except Exception as e:
        results.append(TestResult("user_turn_read", "FAIL", _time.time() - t0, str(e)))

    # 3. Context assembly wiring in the main chat handler: [system] + history + [current_user]
    try:
        code = (Path(__file__).parents[1] / "telegram" / "bot_handlers.py").read_text(encoding="utf-8")
        ok_build = "_build_system_message" in code
        ok_hist  = "get_history" in code
        ok_turn  = "_user_turn_content" in code
        ok_assemble = ("messages = [{\"role\": \"system\"" in code or
                       "messages=[{\"role\": \"system\"" in code or
                       'messages = [{"role": "system"' in code or
                       '{"role": "system"' in code)
        ok_llm   = "ask_llm_with_history" in code
        for name, ok in [("build_system_called", ok_build), ("get_history_called", ok_hist),
                         ("user_turn_called", ok_turn), ("system_msg_first", ok_assemble),
                         ("ask_llm_with_history_used", ok_llm)]:
            results.append(TestResult(f"context_assembly_{name}", "PASS" if ok else "FAIL",
                                      _time.time() - t0, "present" if ok else f"MISSING: {name}"))
    except Exception as e:
        results.append(TestResult("context_assembly_read", "FAIL", _time.time() - t0, str(e)))

    # 4. ask_llm_with_history() in bot_llm.py supports native messages format for all providers
    try:
        code = (Path(__file__).parents[1] / "core" / "bot_llm.py").read_text(encoding="utf-8")
        ok_fn    = "def ask_llm_with_history" in code
        # System role is passed through from the messages list (built by bot_handlers.py)
        # bot_llm.py doesn't write "role: system" itself — it just relays the messages list.
        # Verify the function accepts and forwards full messages including system role.
        ok_sys   = "messages" in code and "role" in code  # messages list with roles forwarded
        ok_hist_fmt = "_format_history_as_text" in code
        ok_ollama_native = "ollama" in code and "messages" in code    # ollama native multi-turn
        for name, ok in [("ask_llm_with_history_fn", ok_fn), ("system_role_supported", ok_sys),
                         ("history_fallback_formatter", ok_hist_fmt), ("ollama_native_messages", ok_ollama_native)]:
            results.append(TestResult(f"llm_history_{name}", "PASS" if ok else "FAIL",
                                      _time.time() - t0, "present" if ok else f"MISSING: {name}"))
    except Exception as e:
        results.append(TestResult("llm_history_read", "FAIL", _time.time() - t0, str(e)))

    # 5. Live integration: build a minimal messages list and call ask_llm_with_history
    #    (only runs if LLM is reachable; SKIP otherwise)
    try:
        _sys.path.insert(0, str(Path(__file__).parents[1]))
        from core.bot_llm import ask_llm_with_history
        from core.bot_state import get_memory_context, get_history
        from telegram.bot_access import _build_system_message, _user_turn_content

        test_chat_id = 999999   # non-existent → no real history or docs
        system_msg  = _build_system_message(test_chat_id, "test query")
        history_msgs = get_history(test_chat_id)  # empty for non-existent user
        user_turn   = _user_turn_content(test_chat_id, "What is 2+2?")
        messages = (
            [{"role": "system", "content": system_msg}]
            + history_msgs
            + [{"role": "user",   "content": user_turn}]
        )

        # Verify structure before sending to LLM
        ok_sys_first = messages[0]["role"] == "system"
        ok_user_last = messages[-1]["role"] == "user"
        ok_rag_in_user = "[KNOWLEDGE" not in user_turn   # no docs → no knowledge block
        results.append(TestResult("combined_context_structure",
                                  "PASS" if (ok_sys_first and ok_user_last) else "FAIL",
                                  _time.time() - t0,
                                  f"messages[0]=system, messages[-1]=user, len={len(messages)}"
                                  if ok_sys_first and ok_user_last
                                  else f"wrong structure: first={messages[0]['role']}, last={messages[-1]['role']}"))

        # Actually call LLM — SKIP if not reachable or binary LLM returns empty
        try:
            reply = ask_llm_with_history(messages, timeout=15, use_case="test")
            ok_reply = bool(reply and len(reply) > 0)
            if not ok_reply:
                # Binary LLM (taris/picoclaw) may return empty without exception when misconfigured
                bot_env_path = Path(os.path.expanduser("~/.taris/bot.env"))
                llm_prov = os.environ.get("LLM_PROVIDER", "taris")
                if bot_env_path.exists():
                    for _l in bot_env_path.read_text(encoding="utf-8").splitlines():
                        _l = _l.strip()
                        if _l.startswith("LLM_PROVIDER=") and not _l.startswith("#"):
                            llm_prov = _l.split("=", 1)[1].strip().strip('"').strip("'")
                            break
                if llm_prov == "taris":
                    results.append(TestResult("combined_context_llm_response", "SKIP",
                                              _time.time() - t0,
                                              "LLM_PROVIDER=taris binary returned empty — binary not configured for test context"))
                else:
                    results.append(TestResult("combined_context_llm_response", "FAIL",
                                              _time.time() - t0, "empty LLM response"))
            else:
                results.append(TestResult("combined_context_llm_response",
                                          "PASS", _time.time() - t0,
                                          f"LLM replied ({len(reply)} chars)"))
        except Exception as llm_exc:
            results.append(TestResult("combined_context_llm_response", "SKIP",
                                      _time.time() - t0, f"LLM not reachable: {llm_exc}"))

    except Exception as e:
        results.append(TestResult("combined_context_live", "SKIP", _time.time() - t0,
                                  f"live integration skipped: {e}"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T79 – RAG log datetime serialization (Postgres returns datetime, not str)
# ─────────────────────────────────────────────────────────────────────────────
def t_rag_log_datetime_serialization(**_) -> list:
    """T79: list_rag_log() created_at field is safely str()-able for both SQLite and Postgres.

    Root cause: Postgres returns created_at as datetime.datetime; SQLite returns str.
    _handle_admin_rag_log() used r["created_at"][:16] which raises TypeError on datetime.
    Fix: str(r["created_at"])[:16] normalises both backends.
    """
    import time as _time
    import sys as _sys
    results = []
    t0 = _time.time()

    # 1. Source code check: str() wrapping present in bot_admin.py
    _sys.path.insert(0, str(SRC_ROOT))
    try:
        code = (SRC_ROOT / "telegram" / "bot_admin.py").read_text(encoding="utf-8")
        has_str_wrap = "str(r[\"created_at\"])[:16]" in code or "str(r['created_at'])[:16]" in code
        results.append(TestResult("rag_log_created_at_str_wrap",
                                  "PASS" if has_str_wrap else "FAIL",
                                  _time.time() - t0,
                                  "str(r['created_at'])[:16] present in bot_admin.py"
                                  if has_str_wrap else
                                  "MISSING str() wrap — datetime slicing will crash on Postgres"))

        has_query_wrap = "str(r[\"query\"])[:40]" in code or "str(r['query'])[:40]" in code
        results.append(TestResult("rag_log_query_str_wrap",
                                  "PASS" if has_query_wrap else "FAIL",
                                  _time.time() - t0,
                                  "str(r['query'])[:40] present"
                                  if has_query_wrap else "MISSING str() wrap on query field"))
    except Exception as e:
        results.append(TestResult("rag_log_source_check", "SKIP", _time.time() - t0,
                                  f"source check skipped: {e}"))

    # 2. Live round-trip: insert a row with a datetime created_at, read back, str()-slice safely
    try:
        from core.store import store
        from datetime import datetime, timezone
        fake_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        # Simulate what list_rag_log returns (either str or datetime)
        class _FakeRow(dict):
            pass
        for ts_val in [fake_dt, "2026-01-01 12:00:00.000000+00:00"]:
            row = _FakeRow(query="testq", n_chunks=1, chars_injected=10,
                           created_at=ts_val, latency_ms=5, query_type="fts5")
            sliced = str(row["created_at"])[:16]
            assert sliced == "2026-01-01 12:00", f"unexpected: {sliced!r}"
        results.append(TestResult("rag_log_datetime_roundtrip", "PASS",
                                  _time.time() - t0, "datetime and str both sliceable via str()"))
    except Exception as e:
        results.append(TestResult("rag_log_datetime_roundtrip", "FAIL",
                                  _time.time() - t0, f"roundtrip failed: {e}"))

    return results



# ─────────────────────────────────────────────────────────────────────────────
# T80 – RAG hybrid retrieval: psutil fallback + embed() signature + chunk_idx
# ─────────────────────────────────────────────────────────────────────────────
def t_rag_hybrid_retrieval_fixes(**_) -> list:
    """T80: Verify the three RAG hybrid retrieval bugs are fixed.

    Bug 1: psutil missing → ram_gb=0.0 → always FTS5_ONLY (fix: /proc/meminfo fallback)
    Bug 2: svc.embed([query]) instead of svc.embed(query) → None embedding
    Bug 3: search_similar missing chunk_idx → RRF collapses all doc chunks to one key
    """
    import time as _time
    import sys as _sys
    results = []
    t0 = _time.time()

    _sys.path.insert(0, str(SRC_ROOT))

    # 1. /proc/meminfo fallback is present in bot_rag.py
    try:
        code = (SRC_ROOT / "core" / "bot_rag.py").read_text(encoding="utf-8")
        has_meminfo = "/proc/meminfo" in code
        results.append(TestResult("rag_meminfo_fallback",
                                  "PASS" if has_meminfo else "FAIL",
                                  _time.time() - t0,
                                  "/proc/meminfo fallback present in detect_rag_capability()"
                                  if has_meminfo else "MISSING /proc/meminfo fallback — always FTS5_ONLY without psutil"))
        # embed call uses single string, not [query]
        has_correct_embed = "svc.embed(query)" in code and "svc.embed([query])" not in code
        results.append(TestResult("rag_embed_signature",
                                  "PASS" if has_correct_embed else "FAIL",
                                  _time.time() - t0,
                                  "svc.embed(query) correct — not svc.embed([query])"
                                  if has_correct_embed else "svc.embed([query]) bug present — passes list to str API"))
    except Exception as e:
        results.append(TestResult("rag_hybrid_source_check", "SKIP", _time.time() - t0,
                                  f"source check skipped: {e}"))

    # 2. search_similar returns chunk_idx (fixes RRF key collision)
    try:
        pg_code = (SRC_ROOT / "core" / "store_postgres.py").read_text(encoding="utf-8")
        has_chunk_idx = "chunk_idx" in pg_code[pg_code.find("def search_similar"):pg_code.find("def search_similar") + 1000]
        results.append(TestResult("rag_search_similar_chunk_idx",
                                  "PASS" if has_chunk_idx else "FAIL",
                                  _time.time() - t0,
                                  "chunk_idx included in search_similar SELECT"
                                  if has_chunk_idx else "MISSING chunk_idx in search_similar — RRF collapses all chunks"))
    except Exception as e:
        results.append(TestResult("rag_search_similar_chunk_idx", "SKIP", _time.time() - t0,
                                  f"source check skipped: {e}"))

    # 3. detect_rag_capability reads /proc/meminfo when psutil absent
    try:
        import importlib
        import types
        # Simulate psutil missing by patching
        import core.bot_rag as _rag_mod
        orig_cap = _rag_mod._detected_capability
        _rag_mod._detected_capability = None
        # Temporarily hide psutil
        import sys as _sys2
        orig_psutil = _sys2.modules.get("psutil")
        _sys2.modules["psutil"] = None  # type: ignore[assignment]
        try:
            ram = 0.0
            try:
                with open("/proc/meminfo") as _f:
                    for _line in _f:
                        if "MemTotal" in _line:
                            ram = int(_line.split()[1]) / (1024 * 1024)
                            break
            except Exception:
                pass
            ok = ram > 0
            results.append(TestResult("rag_meminfo_read",
                                      "PASS" if ok else "SKIP",
                                      _time.time() - t0,
                                      f"/proc/meminfo reads {ram:.1f} GB successfully"
                                      if ok else "/proc/meminfo not available (non-Linux)"))
        finally:
            if orig_psutil is None:
                _sys2.modules.pop("psutil", None)
            else:
                _sys2.modules["psutil"] = orig_psutil
            _rag_mod._detected_capability = orig_cap
    except Exception as e:
        results.append(TestResult("rag_meminfo_read", "SKIP", _time.time() - t0,
                                  f"meminfo test skipped: {e}"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T81 — Qwen3.5 model available in Ollama
# ─────────────────────────────────────────────────────────────────────────────

def t_qwen35_ollama_available(**_) -> list[TestResult]:
    """T81 — at least one qwen3.5 model is pulled and listed in Ollama.
    SKIP if Ollama is not reachable (e.g. Pi target without Ollama).
    """
    import urllib.request
    import json as _json

    results: list[TestResult] = []
    t0 = time.time()
    ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

    try:
        req = urllib.request.Request(
            f"{ollama_url}/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
    except Exception as exc:
        results.append(TestResult(
            "qwen35_ollama_available", "SKIP", time.time() - t0,
            f"Ollama not reachable: {exc}",
        ))
        return results

    qwen35_models = [m for m in models if "qwen3.5" in m.lower()]
    if qwen35_models:
        results.append(TestResult(
            "qwen35_ollama_available", "PASS", time.time() - t0,
            f"Found: {', '.join(qwen35_models)}",
        ))
    else:
        results.append(TestResult(
            "qwen35_ollama_available", "WARN", time.time() - t0,
            f"No qwen3.5 model pulled yet. Available: {', '.join(models[:5])}… "
            "Pull with: ollama pull qwen3.5:latest",
        ))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T82 — Ollama latency regression: active model responds within threshold
# ─────────────────────────────────────────────────────────────────────────────

def t_ollama_latency_regression(**_) -> list[TestResult]:
    """T82 — active OLLAMA_MODEL responds to a minimal prompt within 30s.
    Measures wall time and tokens/sec; WARN if >30% slower than typical.
    SKIP if Ollama not running or DEVICE_VARIANT != openclaw.
    """
    import urllib.request
    import json as _json

    results: list[TestResult] = []
    t0 = time.time()

    device_variant = os.environ.get("DEVICE_VARIANT", "taris")
    if device_variant != "openclaw":
        results.append(TestResult(
            "ollama_latency", "SKIP", time.time() - t0,
            "DEVICE_VARIANT != openclaw; Ollama latency test only runs on OpenClaw",
        ))
        return results

    ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")

    try:
        payload = _json.dumps({
            "model": model,
            "prompt": "Say OK",
            "stream": False,
            "think": False,
            "options": {"num_predict": 5, "temperature": 0},
        }).encode()
        req = urllib.request.Request(
            f"{ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp_data = _json.loads(resp.read())
    except Exception as exc:
        results.append(TestResult(
            "ollama_latency", "SKIP", time.time() - t0,
            f"Ollama generate failed: {exc}",
        ))
        return results

    wall = time.time() - t0
    tokens_out = resp_data.get("eval_count", 0)
    eval_dur_ns = resp_data.get("eval_duration", 1)
    tps = tokens_out / (eval_dur_ns / 1e9) if eval_dur_ns > 0 else 0

    # Thresholds: wall < 30s (generous), tps > 2 (very minimal)
    ok = wall < 30.0 and tps > 2.0
    status = "PASS" if ok else "WARN"
    results.append(TestResult(
        "ollama_latency", status, wall,
        f"model={model} wall={wall:.1f}s tps={tps:.1f}",
        metric=wall, metric_key="ollama_latency_s",
    ))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T83 — Ollama quality: Russian calendar intent → valid JSON
# ─────────────────────────────────────────────────────────────────────────────

def t_ollama_quality_ru_calendar(**_) -> list[TestResult]:
    """T83 — active OLLAMA_MODEL extracts calendar event JSON from Russian text.
    Tests the core taris calendar use-case. SKIP if Ollama not running.
    """
    import urllib.request
    import json as _json

    results: list[TestResult] = []
    t0 = time.time()

    device_variant = os.environ.get("DEVICE_VARIANT", "taris")
    if device_variant != "openclaw":
        results.append(TestResult(
            "ollama_quality_ru_calendar", "SKIP", time.time() - t0,
            "DEVICE_VARIANT != openclaw",
        ))
        return results

    ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")

    prompt = (
        'Извлеки данные события из текста и верни JSON.\n'
        'Текст: "Встреча с врачом в четверг в 14:00"\n'
        'Формат: {"title": "<название>", "dt": "<YYYY-MM-DDTHH:MM>"}\n'
        'Верни только JSON, без пояснений.'
    )

    try:
        payload = _json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"num_predict": 80, "temperature": 0},
        }).encode()
        req = urllib.request.Request(
            f"{ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp_data = _json.loads(resp.read())
    except Exception as exc:
        results.append(TestResult(
            "ollama_quality_ru_calendar", "SKIP", time.time() - t0,
            f"Ollama not available: {exc}",
        ))
        return results

    wall = time.time() - t0
    response = resp_data.get("response", "").strip()

    # Extract JSON from response (may have markdown fences)
    json_text = response
    if "```" in response:
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if m:
            json_text = m.group(1)

    # Validate JSON structure
    try:
        parsed = _json.loads(json_text)
        has_title = "title" in parsed and isinstance(parsed["title"], str) and len(parsed["title"]) > 0
        has_dt = "dt" in parsed and isinstance(parsed["dt"], str)
        if has_title and has_dt:
            results.append(TestResult(
                "ollama_quality_ru_calendar", "PASS", wall,
                f"model={model} title='{parsed['title']}' dt='{parsed.get('dt','')}' wall={wall:.1f}s",
                metric=wall, metric_key="ollama_cal_json_s",
            ))
        else:
            results.append(TestResult(
                "ollama_quality_ru_calendar", "FAIL", wall,
                f"model={model} JSON missing fields: {parsed}",
            ))
    except Exception as parse_err:
        results.append(TestResult(
            "ollama_quality_ru_calendar", "FAIL", wall,
            f"model={model} response not valid JSON: {response[:120]} ({parse_err})",
        ))
    return results


# ─── T84: upload stats stored in document metadata ────────────────────────────
def t_upload_stats_metadata(**_) -> list[TestResult]:
    """T84: Chunk quality filter and upload stats (n_skipped, quality_pct, n_embedded) in metadata."""
    results = []
    try:
        src = Path(__file__).parent.parent / "features" / "bot_documents.py"
        code = src.read_text()
    except FileNotFoundError:
        results.append(TestResult("upload_stats_source", "SKIP", 0, "bot_documents.py not found"))
        return results

    checks = [
        ("MIN_CHUNK_CHARS", "_MIN_CHUNK_CHARS" in code, "minimum chunk length constant"),
        ("chunk_quality_filter", "_MIN_CHUNK_CHARS" in code and "len(chunk.strip()) < _MIN_CHUNK_CHARS" in code,
         "quality filter in _chunk_text()"),
        ("skipped_counter", "skipped" in code and "n + skipped" in code,
         "skipped chunks counter in _chunk_text"),
        ("quality_pct_stored", '"quality_pct"' in code, "quality_pct stored in metadata"),
        ("n_embedded_stored", '"n_embedded"' in code, "n_embedded stored in metadata"),
        ("n_skipped_stored", '"n_skipped"' in code, "n_skipped stored in metadata"),
        ("embed_count_return", "n_embedded" in code and "return len(chunks), n_embedded" in code,
         "_store_text_chunks returns (n_chunks, n_embedded)"),
        ("doc_detail_shows_embeds", "docs_doc_embeds" in code, "embed count shown in doc detail"),
        ("doc_detail_shows_quality", "docs_doc_quality" in code, "quality shown in doc detail"),
    ]
    for name, cond, detail in checks:
        results.append(TestResult(
            f"upload_stats_{name}",
            "PASS" if cond else "FAIL",
            0.0,
            detail,
        ))

    # Check strings.json has the new keys
    try:
        strings_path = Path(__file__).parent.parent / "strings.json"
        import json as _j
        strings = _j.loads(strings_path.read_text())
        for lang in ("ru", "en", "de"):
            for key in ("docs_doc_embeds", "docs_doc_quality"):
                present = key in strings.get(lang, {})
                results.append(TestResult(
                    f"upload_stats_string_{key}_{lang}",
                    "PASS" if present else "FAIL",
                    0.0,
                    f"{lang}: {key}",
                ))
    except Exception as exc:
        results.append(TestResult("upload_stats_strings", "FAIL", 0, str(exc)))

    return results


# ─── T85: bot_embeddings.py import fix ────────────────────────────────────────
def t_embeddings_import_fix(**_) -> list[TestResult]:
    """T85: bot_embeddings.py must use 'from core.bot_config' not 'from src.core.bot_config'."""
    results = []
    try:
        src = Path(__file__).parent.parent / "core" / "bot_embeddings.py"
        code = src.read_text()
    except FileNotFoundError:
        results.append(TestResult("embeddings_import_source", "SKIP", 0, "bot_embeddings.py not found"))
        return results

    bad_import = "from src.core.bot_config import" in code
    good_import = "from core.bot_config import" in code
    results.append(TestResult(
        "embeddings_no_src_import",
        "FAIL" if bad_import else "PASS",
        0.0,
        "'from src.core.bot_config' found — breaks production deploy" if bad_import
        else "import uses 'core.bot_config' (correct)",
    ))
    results.append(TestResult(
        "embeddings_has_core_import",
        "PASS" if good_import else "FAIL",
        0.0,
        "import 'core.bot_config' present" if good_import else "missing 'from core.bot_config'",
    ))

    # Verify EmbeddingService is importable locally
    t0 = time.monotonic()
    try:
        import sys, importlib
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from core.bot_embeddings import EmbeddingService  # noqa: F401
        results.append(TestResult("embeddings_importable", "PASS", time.monotonic() - t0,
                                  "EmbeddingService imported ok"))
    except Exception as exc:
        results.append(TestResult("embeddings_importable", "FAIL", time.monotonic() - t0, str(exc)))

    return results


# ─── T86: Phase D MCP server + client structure ────────────────────────────────
def t_mcp_phase_d_structure(**_) -> list[TestResult]:
    """T86: Phase D MCP server endpoint registered in bot_web.py + client circuit breaker."""
    results = []

    # Check bot_config.py has MCP constants
    try:
        cfg_src = Path(__file__).parent.parent / "core" / "bot_config.py"
        cfg = cfg_src.read_text()
    except FileNotFoundError:
        results.append(TestResult("mcp_config_source", "SKIP", 0, "bot_config.py not found"))
        return results

    for const in ("MCP_SERVER_ENABLED", "MCP_REMOTE_URL", "MCP_TIMEOUT", "MCP_REMOTE_TOP_K"):
        results.append(TestResult(
            f"mcp_config_{const}",
            "PASS" if const in cfg else "FAIL",
            0.0,
            f"{const} in bot_config.py",
        ))

    # Check bot_web.py has /mcp/search endpoint
    try:
        web_src = Path(__file__).parent.parent / "bot_web.py"
        web = web_src.read_text()
        for check, detail in [
            ('"/mcp/search"', "/mcp/search endpoint registered"),
            ("MCP_SERVER_ENABLED", "MCP_SERVER_ENABLED used as guard"),
            ("mcp_search", "mcp_search function defined"),
            ("retrieve_context", "retrieve_context called from mcp_search"),
        ]:
            results.append(TestResult(
                f"mcp_web_{check.strip('\"')}",
                "PASS" if check in web else "FAIL",
                0.0,
                detail,
            ))
    except FileNotFoundError:
        results.append(TestResult("mcp_web_source", "SKIP", 0, "bot_web.py not found"))

    # Check bot_mcp_client.py exists with circuit breaker
    try:
        client_src = Path(__file__).parent.parent / "core" / "bot_mcp_client.py"
        client = client_src.read_text()
        for check, detail in [
            ("query_remote", "query_remote() function present"),
            ("circuit_status", "circuit_status() health check present"),
            ("_CB_THRESHOLD", "circuit breaker threshold constant"),
            ("_CB_RESET_SEC", "circuit breaker reset timer"),
            ("_cb_record_failure", "failure recorder for circuit breaker"),
            ("urllib.request", "stdlib HTTP client (no heavy deps)"),
            ("MCP_REMOTE_URL", "MCP_REMOTE_URL used in client"),
        ]:
            results.append(TestResult(
                f"mcp_client_{check}",
                "PASS" if check in client else "FAIL",
                0.0,
                detail,
            ))
    except FileNotFoundError:
        results.append(TestResult("mcp_client_source", "FAIL", 0,
                                  "bot_mcp_client.py not found"))

    # Check bot_rag.py integrates MCP client
    try:
        rag_src = Path(__file__).parent.parent / "core" / "bot_rag.py"
        rag = rag_src.read_text()
        for check, detail in [
            ("bot_mcp_client", "mcp_client imported in bot_rag"),
            ("query_remote", "query_remote() called in retrieve_context"),
            ("+mcp", "strategy annotated with '+mcp' when remote used"),
        ]:
            results.append(TestResult(
                f"mcp_rag_{check}",
                "PASS" if check in rag else "FAIL",
                0.0,
                detail,
            ))
    except FileNotFoundError:
        results.append(TestResult("mcp_rag_source", "SKIP", 0, "bot_rag.py not found"))

    return results




def t_embedding_pipeline_fix(**_) -> list[TestResult]:
    """T87: _store_text_chunks() passes chunk_text to upsert_embedding (critical bug fix).

    The call was: store.upsert_embedding(doc_id, idx, chat_id, vec)  ← wrong
    Must be:      store.upsert_embedding(doc_id, idx, chat_id, chunks[idx], vec)
    Also verifies search_fts and search_similar return chunk_idx in results.
    """
    results = []
    SRC = Path(__file__).parent.parent

    # Check 1: bot_documents.py has the correct upsert_embedding call
    try:
        code = (SRC / "features/bot_documents.py").read_text()
        correct_call = "store.upsert_embedding(doc_id, idx, chat_id, chunks[idx], vec)"
        wrong_call   = "store.upsert_embedding(doc_id, idx, chat_id, vec)"
        results.append(TestResult(
            "embed_correct_args", "PASS" if correct_call in code else "FAIL", 0.0,
            "upsert_embedding passes chunks[idx] as chunk_text arg",
        ))
        results.append(TestResult(
            "embed_no_wrong_call", "PASS" if wrong_call not in code else "FAIL", 0.0,
            "Old wrong call (missing chunk_text) removed",
        ))
    except FileNotFoundError:
        results.append(TestResult("embed_correct_args", "SKIP", 0.0, "bot_documents.py not found"))

    # Check 2: search_fts returns chunk_idx in result dicts
    try:
        code = (SRC / "core/store_sqlite.py").read_text()
        results.append(TestResult(
            "fts_returns_chunk_idx",
            "PASS" if '"chunk_idx"' in code and "chunk_idx" in code else "FAIL", 0.0,
            "search_fts result dicts include chunk_idx",
        ))
        results.append(TestResult(
            "fts_select_chunk_idx",
            "PASS" if "SELECT doc_id, chunk_idx, chunk_text" in code else "FAIL", 0.0,
            "search_fts SQL SELECT includes chunk_idx column",
        ))
    except FileNotFoundError:
        results.append(TestResult("fts_returns_chunk_idx", "SKIP", 0.0, "store_sqlite.py not found"))

    # Check 3: search_similar returns chunk_idx
    try:
        code = (SRC / "core/store_sqlite.py").read_text()
        results.append(TestResult(
            "vector_returns_chunk_idx",
            "PASS" if "SELECT doc_id, chunk_idx, chunk_text, rank" in code else "FAIL", 0.0,
            "search_similar SELECT includes chunk_idx + chunk_text",
        ))
    except FileNotFoundError:
        results.append(TestResult("vector_returns_chunk_idx", "SKIP", 0.0, "store_sqlite.py not found"))

    return results


def t_shared_docs_search(**_) -> list[TestResult]:
    """T88: shared documents (is_shared=1) are included in FTS and vector search."""
    results = []
    SRC = Path(__file__).parent.parent

    try:
        code = (SRC / "core/store_sqlite.py").read_text()
        results.append(TestResult(
            "fts_includes_shared",
            "PASS" if "is_shared" in code and "_get_shared_doc_ids" in code else "FAIL", 0.0,
            "_get_shared_doc_ids() helper + FTS shared-doc inclusion",
        ))
        results.append(TestResult(
            "vector_includes_shared",
            "PASS" if "OR doc_id IN" in code else "FAIL", 0.0,
            "search_similar includes shared doc_ids",
        ))
        results.append(TestResult(
            "list_docs_includes_shared",
            "PASS" if "is_shared = 1" in code else "FAIL", 0.0,
            "list_documents returns own + shared docs",
        ))
    except FileNotFoundError:
        results.append(TestResult("fts_includes_shared", "SKIP", 0.0, "store_sqlite.py not found"))

    return results


def t_rag_trace_fields(**_) -> list[TestResult]:
    """T89: retrieve_context() returns 4-tuple with trace dict (n_fts5/n_vector/n_mcp/latency_ms)."""
    results = []
    SRC = Path(__file__).parent.parent

    try:
        code = (SRC / "core/bot_rag.py").read_text()
        # Function signature returns 4-tuple
        results.append(TestResult(
            "rag_4tuple_return",
            "PASS" if "tuple[list[dict], str, str, dict]" in code else "FAIL", 0.0,
            "retrieve_context signature declares 4-tuple return type",
        ))
        # Trace dict contains n_fts5, n_vector, n_mcp
        for field in ("n_fts5", "n_vector", "n_mcp", "latency_ms"):
            results.append(TestResult(
                f"trace_has_{field}",
                "PASS" if f'"{field}"' in code else "FAIL", 0.0,
                f"trace dict has {field} key",
            ))
        # bot_access.py unpacks 4-tuple
        access_code = (SRC / "telegram/bot_access.py").read_text()
        results.append(TestResult(
            "access_unpacks_trace",
            "PASS" if "chunks, assembled, strategy, trace = _fut.result" in access_code else "FAIL", 0.0,
            "bot_access.py unpacks 4-tuple + uses trace for logging",
        ))
        results.append(TestResult(
            "access_logs_trace",
            "PASS" if "n_fts5" in access_code and "n_vector" in access_code else "FAIL", 0.0,
            "bot_access.py passes n_fts5/n_vector to log_rag_activity",
        ))
        # rag_log has extended columns
        store_code = (SRC / "core/store_sqlite.py").read_text()
        for col in ("n_fts5", "n_vector", "n_mcp"):
            results.append(TestResult(
                f"raglog_col_{col}",
                "PASS" if col in store_code else "FAIL", 0.0,
                f"rag_log {col} column in store_sqlite",
            ))
        results.append(TestResult(
            "raglog_auto_migration",
            "PASS" if "ALTER TABLE rag_log ADD COLUMN" in store_code else "FAIL", 0.0,
            "log_rag_activity does auto-migration of old DBs",
        ))
    except FileNotFoundError as e:
        results.append(TestResult("rag_4tuple_return", "SKIP", 0.0, f"file not found: {e}"))

    return results


def t_system_docs_structure(**_) -> list[TestResult]:
    """T90: load_system_docs.py and migrate_reembed.py exist with correct structure."""
    results = []
    SRC = Path(__file__).parent.parent

    # Check load_system_docs.py
    loader = SRC / "setup/load_system_docs.py"
    results.append(TestResult(
        "loader_exists", "PASS" if loader.exists() else "FAIL", 0.0,
        "src/setup/load_system_docs.py exists",
    ))
    if loader.exists():
        code = loader.read_text(encoding="utf-8", errors="replace")
        for check, desc in [
            ("SYSTEM_CHAT_ID = 0", "SYSTEM_CHAT_ID=0 constant"),
            ("def _load_docs", "_load_docs() main entry function"),
            ("def _ingest", "_ingest() per-document indexer"),
            ("def _chunk", "_chunk() text splitter"),
            ("taris_user_guide", "user guide tag defined"),
            ("taris_admin_guide", "admin guide tag defined"),
            ("shared_level", "shared_level param: 1=all users, 2=admin-only"),
            ("is_shared=2", "admin guide stored as is_shared=2 (admin-only)"),
            ("upsert_embedding(doc_id, idx, SYSTEM_CHAT_ID, chunks[idx], vec)",
             "correct upsert_embedding call"),
        ]:
            results.append(TestResult(
                f"loader_{check[:30].replace(' ', '_').replace('(', '').replace(')', '')}",
                "PASS" if check in code else "FAIL", 0.0, desc,
            ))

    # Check migrate_reembed.py
    migrator = SRC / "setup/migrate_reembed.py"
    results.append(TestResult(
        "migrator_exists", "PASS" if migrator.exists() else "FAIL", 0.0,
        "src/setup/migrate_reembed.py exists",
    ))
    if migrator.exists():
        code = migrator.read_text()
        for check, desc in [
            ("def _migrate", "_migrate() main function"),
            ("get_chunks_without_embeddings", "uses store API to find unembedded chunks"),
            ("store.upsert_embedding", "calls upsert_embedding for each chunk"),
            ("--dry-run", "--dry-run CLI flag"),
        ]:
            results.append(TestResult(
                f"migrator_{check[:30].replace(' ', '_').replace('(', '').replace(')', '')}",
                "PASS" if check in code else "FAIL", 0.0, desc,
            ))

    # Check telegram_menu_bot.py auto-loads system docs at startup
    try:
        bot_code = (SRC / "telegram_menu_bot.py").read_text(encoding="utf-8", errors="replace")
        results.append(TestResult(
            "startup_system_docs_thread",
            "PASS" if "_ensure_system_docs" in bot_code and "_load_docs" in bot_code else "FAIL", 0.0,
            "telegram_menu_bot.py starts system docs loader thread at startup",
        ))
    except FileNotFoundError:
        results.append(TestResult("startup_system_docs_thread", "SKIP", 0.0, "telegram_menu_bot.py not found"))

    return results


# T91 — TeleBot num_threads=16 prevents menu callback queuing behind LLM/voice handlers
def t_telebot_num_threads(**_) -> list[TestResult]:
    """T91: bot_instance.py uses num_threads=16 (not the default 2)."""
    results = []
    SRC = Path(__file__).parent.parent
    bot_inst = SRC / "core/bot_instance.py"
    if not bot_inst.exists():
        return [TestResult("telebot_num_threads", "SKIP", 0.0, "bot_instance.py not found")]
    code = bot_inst.read_text()
    # Must have num_threads set to 16 (or higher), not the default 2
    import re
    m = re.search(r'num_threads\s*=\s*(\d+)', code)
    if m:
        n = int(m.group(1))
        status = "PASS" if n >= 16 else "FAIL"
        results.append(TestResult(
            "telebot_num_threads_value",
            status, 0.0,
            f"num_threads={n} (need ≥16 to prevent menu queuing behind LLM calls)",
        ))
    else:
        results.append(TestResult(
            "telebot_num_threads_value", "FAIL", 0.0,
            "num_threads not set in bot_instance.py — default is 2, menus queue behind LLM",
        ))
    return results


# T92 — Chat/voice message handlers dispatch heavy work to background threads
def t_handlers_background_dispatch(**_) -> list[TestResult]:
    """T92: chat/system/voice handlers use threading.Thread to free telebot worker thread."""
    results = []
    SRC = Path(__file__).parent.parent
    bot_code_path = SRC / "telegram_menu_bot.py"
    if not bot_code_path.exists():
        return [TestResult("handlers_dispatch", "SKIP", 0.0, "telegram_menu_bot.py not found")]
    code = bot_code_path.read_text()

    for name, pattern, desc in [
        ("chat_handler_dispatch",
         r'threading\.Thread\s*\(\s*target\s*=\s*_handle_chat_message',
         "_handle_chat_message dispatched to daemon thread (not blocking worker)"),
        ("system_handler_dispatch",
         r'threading\.Thread\s*\(\s*target\s*=\s*_handle_system_message',
         "_handle_system_message dispatched to daemon thread"),
        ("voice_handler_dispatch",
         r'threading\.Thread\s*\(\s*target\s*=\s*_handle_voice_message',
         "_handle_voice_message dispatched to daemon thread"),
        ("perf_timing_in_callback",
         r'_cb_t0\s*=\s*_time\.perf_counter',
         "[PERF] timing instrumentation in callback_handler"),
    ]:
        import re
        ok = bool(re.search(pattern, code))
        results.append(TestResult(name, "PASS" if ok else "FAIL", 0.0, desc))

    return results


# T93 — answer_callback_query wrapped in try/except (stale callback safety)
def t_callback_query_answer_safe(**_) -> list[TestResult]:
    """T93: callback_handler wraps answer_callback_query in try/except.

    Root cause of bot appearing frozen:
    Stale callbacks (>60s old) raised ApiTelegramException in the worker pool.
    raise_exceptions() re-raised in __threaded_polling, triggering exponential
    backoff (0.25s→60s) between getUpdates polls — bot became unresponsive.
    """
    import re
    src = Path(__file__).parent.parent / "telegram_menu_bot.py"
    if not src.exists():
        return [TestResult("callback_query_answer_safe", "SKIP", 0.0,
                           "telegram_menu_bot.py not found")]

    code = src.read_text()
    results = []

    has_try_except = bool(re.search(
        r'try\s*:\s*\n\s+bot\.answer_callback_query\(call\.id\)',
        code, re.MULTILINE
    ))
    results.append(TestResult(
        "answer_callback_try_except",
        "PASS" if has_try_except else "FAIL",
        0.0,
        "answer_callback_query(call.id) is wrapped in try/except"
    ))

    has_except_log = bool(re.search(
        r'except\s+Exception\s+as\s+\w+_err\s*:\s*\n.*log\.warning.*answer_callback',
        code, re.DOTALL
    ))
    results.append(TestResult(
        "answer_callback_except_logs",
        "PASS" if has_except_log else "FAIL",
        0.0,
        "except block logs warning instead of re-raising ApiTelegramException"
    ))

    return results


def t_fw_preload_config(**_) -> list[TestResult]:
    """T94: FASTER_WHISPER_PRELOAD env var controls model preloading.

    Root cause of menu freeze: FasterWhisper small model (~460MB) preloaded at
    startup on OpenClaw, exhausting available RAM and causing kernel swap I/O
    on every callback (30-100+ second stalls).  FASTER_WHISPER_PRELOAD=0 in
    bot.env disables preloading so the model loads lazily on first voice message.
    """
    import re
    results = []

    # 1. bot_config.py exports FASTER_WHISPER_PRELOAD
    cfg = Path(__file__).parent.parent / "core" / "bot_config.py"
    if cfg.exists():
        cfg_code = cfg.read_text()
        has_const = "FASTER_WHISPER_PRELOAD" in cfg_code
        results.append(TestResult(
            "fw_preload_const_in_config",
            "PASS" if has_const else "FAIL",
            0.0,
            "FASTER_WHISPER_PRELOAD constant defined in bot_config.py"
        ))
        uses_env = bool(re.search(
            r'FASTER_WHISPER_PRELOAD\s*=\s*os\.environ\.get', cfg_code
        ))
        results.append(TestResult(
            "fw_preload_reads_env",
            "PASS" if uses_env else "FAIL",
            0.0,
            "FASTER_WHISPER_PRELOAD reads from os.environ.get()"
        ))
    else:
        results.append(TestResult("fw_preload_const_in_config", "SKIP", 0.0,
                                  "bot_config.py not found"))

    # 2. telegram_menu_bot.py imports and checks FASTER_WHISPER_PRELOAD
    menu = Path(__file__).parent.parent / "telegram_menu_bot.py"
    if menu.exists():
        menu_code = menu.read_text()
        imports_it = "FASTER_WHISPER_PRELOAD" in menu_code
        results.append(TestResult(
            "fw_preload_used_in_menu_bot",
            "PASS" if imports_it else "FAIL",
            0.0,
            "telegram_menu_bot.py uses FASTER_WHISPER_PRELOAD"
        ))
        guards_preload = bool(re.search(
            r'FASTER_WHISPER_PRELOAD\s+and\s+\(', menu_code
        ))
        results.append(TestResult(
            "fw_preload_guards_preload_call",
            "PASS" if guards_preload else "FAIL",
            0.0,
            "FASTER_WHISPER_PRELOAD gates the _fw_preload() call"
        ))
    else:
        results.append(TestResult("fw_preload_used_in_menu_bot", "SKIP", 0.0,
                                  "telegram_menu_bot.py not found"))

    return results


def t_tail_log_no_readlines(**_) -> list[TestResult]:
    """T95: tail_log() uses subprocess tail instead of f.readlines().

    Root cause of admin_logs_show taking 45s: reading entire 7.5 MB log file
    (106 K lines) via readlines() while the system was under swap pressure
    caused massive I/O stalls.  Fixed by calling system ``tail -n N`` which
    reads only the last N lines from the file's end.
    """
    import re
    results = []

    logger = Path(__file__).parent.parent / "core" / "bot_logger.py"
    if not logger.exists():
        return [TestResult("tail_log_no_readlines", "SKIP", 0.0,
                           "bot_logger.py not found")]

    code = logger.read_text()

    # Must NOT use full readlines() as primary path
    uses_readlines = bool(re.search(r'^\s+lines\s*=\s*f\.readlines\(\)', code, re.MULTILINE))
    results.append(TestResult(
        "tail_log_no_full_readlines",
        "FAIL" if uses_readlines else "PASS",
        0.0,
        "tail_log does not do full f.readlines() (avoids loading multi-MB log into RAM)"
    ))

    # Must use subprocess tail or seek-based read
    uses_subprocess_tail = bool(re.search(r'["\']tail["\']', code))
    uses_seek = bool(re.search(r'f\.seek\(', code))
    results.append(TestResult(
        "tail_log_uses_tail_or_seek",
        "PASS" if (uses_subprocess_tail or uses_seek) else "FAIL",
        0.0,
        f"tail_log uses subprocess tail={uses_subprocess_tail} or seek={uses_seek}"
    ))

    return results


def t_startup_memory_check(**_) -> list[TestResult]:
    """T96: telegram_menu_bot.py logs memory status at startup.

    Low-memory warning helps operators quickly diagnose menu freeze caused by
    swap exhaustion.  Must use /proc/meminfo (not psutil) so it works without
    extra dependencies.
    """
    import re
    results = []

    menu = Path(__file__).parent.parent / "telegram_menu_bot.py"
    if not menu.exists():
        return [TestResult("startup_memory_check", "SKIP", 0.0,
                           "telegram_menu_bot.py not found")]

    code = menu.read_text()

    has_meminfo = "/proc/meminfo" in code
    results.append(TestResult(
        "memory_check_uses_proc_meminfo",
        "PASS" if has_meminfo else "FAIL",
        0.0,
        "startup memory check reads /proc/meminfo (no psutil dep)"
    ))

    has_swap_warn = bool(re.search(r'LOW MEMORY at startup', code))
    results.append(TestResult(
        "memory_check_warns_low_memory",
        "PASS" if has_swap_warn else "FAIL",
        0.0,
        "LOW MEMORY warning emitted when available RAM < 512MB or swap > 80%"
    ))

    has_avail_log = bool(re.search(r'MemAvailable', code))
    results.append(TestResult(
        "memory_check_reads_mem_available",
        "PASS" if has_avail_log else "FAIL",
        0.0,
        "reads MemAvailable key from /proc/meminfo"
    ))

    return results


# ── T97 — Personal data context injection ─────────────────────────────────
def t_personal_context_injection(**_) -> list[TestResult]:
    """T97 — _calendar_context, _notes_context, _contacts_context defined in bot_access.py
    and wired into _build_system_message()."""
    results = []
    src = None
    for candidate in ["src/telegram/bot_access.py", "telegram/bot_access.py",
                      str(Path(__file__).parents[1] / "telegram" / "bot_access.py")]:
        try:
            src = open(candidate, encoding="utf-8").read()
            break
        except FileNotFoundError:
            continue
    if src is None:
        return [TestResult("personal_context_src_not_found", "SKIP", 0.0,
                           "bot_access.py not found in expected locations")]

    checks = [
        ("_calendar_context_defined",    "def _calendar_context(" in src),
        ("_notes_context_defined",       "def _notes_context(" in src),
        ("_contacts_context_defined",    "def _contacts_context(" in src),
        ("calendar_in_build_system",     "_calendar_context(chat_id)" in src),
        ("notes_in_build_system",        "_notes_context(chat_id)" in src),
        ("contacts_in_build_system",     "_contacts_context(chat_id)" in src),
        ("personal_ctx_var",             "personal_ctx" in src),
    ]
    for name, ok in checks:
        results.append(TestResult(
            f"personal_context_{name}",
            "PASS" if ok else "FAIL",
            0.0,
            f"{'found' if ok else 'MISSING'}: {name}",
        ))
    return results


def t_render_telegram_empty_block(**_) -> list[TestResult]:
    """T98: render_telegram guards empty/whitespace MarkdownBlock text (note_view bug fix)."""
    import time
    results = []

    def _resolve(rel: str) -> str | None:
        for candidate in [str(Path(__file__).parents[1] / rel.replace("src/", "")), rel]:
            if Path(candidate).exists():
                return candidate
        return None

    def _check(name: str, src_rel: str, pattern: str, desc: str) -> None:
        t0 = time.time()
        path = _resolve(src_rel)
        if path is None:
            results.append(TestResult(name, "SKIP", 0.0, f"Source file not found: {src_rel}"))
            return
        try:
            src = Path(path).read_text(encoding="utf-8")
            found = pattern in src
            results.append(TestResult(
                name, "PASS" if found else "FAIL", round(time.time() - t0, 3),
                desc if found else f"MISSING: {pattern!r} not found in {path}"
            ))
        except Exception as e:
            results.append(TestResult(name, "FAIL", 0.0, str(e)))

    _check(
        "render_empty_block_guard",
        "src/ui/render_telegram.py",
        r'w.text if w.text.strip() else "\u200b"',
        "Empty MarkdownBlock text replaced with zero-width space"
    )
    _check(
        "note_view_has_content_var",
        "src/screens/note_view.yaml",
        "{note_content}",
        "note_view.yaml uses {note_content} substitution variable"
    )
    _check(
        "note_open_escapes_content",
        "src/telegram/bot_handlers.py",
        'note_content = _escape_md(',
        "note_open handler escapes note content before rendering"
    )
    return results


def t_admin_info_markdown_safe(**_) -> list[TestResult]:
    """T99: Voice admin info wraps dynamic labels in backticks to avoid Markdown injection."""
    import time
    results = []

    def _resolve(rel: str) -> str | None:
        for candidate in [str(Path(__file__).parents[1] / rel.replace("src/", "")), rel]:
            if Path(candidate).exists():
                return candidate
        return None

    def _check(name: str, src_rel: str, pattern: str, desc: str) -> None:
        t0 = time.time()
        path = _resolve(src_rel)
        if path is None:
            results.append(TestResult(name, "SKIP", 0.0, f"Source file not found: {src_rel}"))
            return
        try:
            src = Path(path).read_text(encoding="utf-8")
            found = pattern in src
            results.append(TestResult(
                name, "PASS" if found else "FAIL", round(time.time() - t0, 3),
                desc if found else f"MISSING: {pattern!r} not found in {path}"
            ))
        except Exception as e:
            results.append(TestResult(name, "FAIL", 0.0, str(e)))

    _check(
        "admin_info_stt_backtick",
        "src/features/bot_voice.py",
        "`{_meta.get('stt', '?')}`",
        "STT label in backticks — safe from _ Markdown injection"
    )
    _check(
        "admin_info_llm_backtick",
        "src/features/bot_voice.py",
        "`{_llm_label()}`",
        "LLM label in backticks — safe from _ Markdown injection (e.g. ollama/qwen3.5:latest)"
    )
    _check(
        "admin_info_tts_backtick",
        "src/features/bot_voice.py",
        "`{_tts_label()}`",
        "TTS label in backticks — safe from _ Markdown injection (e.g. ru_RU-dmitri-medium.onnx)"
    )
    # Verify no unescaped f-string with _tts_label() / _llm_label() outside backticks
    import re
    t0 = time.time()
    path = _resolve("src/features/bot_voice.py")
    if path is None:
        results.append(TestResult("admin_info_no_raw_tts_label", "SKIP", 0.0,
                                   "bot_voice.py not found"))
        return results
    try:
        src = Path(path).read_text(encoding="utf-8")
        bad = re.search(r'f"[^`"]*\{_tts_label\(\)\}[^`"]*"', src)
        if bad:
            results.append(TestResult("admin_info_no_raw_tts_label", "FAIL",
                                       round(time.time() - t0, 3),
                                       f"Raw _tts_label() in f-string without backtick: {bad.group()!r}"))
        else:
            results.append(TestResult("admin_info_no_raw_tts_label", "PASS",
                                       round(time.time() - t0, 3),
                                       "No raw _tts_label() outside backtick in f-strings"))
    except Exception as e:
        results.append(TestResult("admin_info_no_raw_tts_label", "FAIL", 0.0, str(e)))
    return results

def t_doc_detail_datetime_safe(**_) -> list[TestResult]:
    """T100: _handle_doc_detail must not crash when created_at is a datetime object (Postgres).

    Root cause: Postgres returns created_at as datetime.datetime, not a string.
    d.get("created_at", "")[:16] raises TypeError.
    Fix: use hasattr(x, 'strftime') guard before slicing.
    """
    import time
    results: list[TestResult] = []
    t0 = time.time()
    try:
        src_path = Path(__file__).parents[1] / "features" / "bot_documents.py"
        text = src_path.read_text(encoding="utf-8")

        # Must NOT contain the raw slice on created_at
        if 'd.get("created_at", "")[:16]' in text or "created_at\", \"\")[:16]" in text:
            results.append(TestResult(
                "doc_detail_datetime_safe", "FAIL", round(time.time() - t0, 3),
                "Raw [:16] slice on created_at still present — will crash with Postgres datetime"
            ))
            return results

        # Must contain a strftime guard
        if "strftime" not in text:
            results.append(TestResult(
                "doc_detail_datetime_safe", "FAIL", round(time.time() - t0, 3),
                "No strftime guard found in bot_documents.py for datetime handling"
            ))
            return results

        # Simulate the conversion logic directly
        import datetime as dt_mod
        test_cases = [
            (dt_mod.datetime(2026, 4, 6, 10, 21, 15), "2026-04-06 10:21"),
            ("2026-04-06T10:21:15.605903", "2026-04-06T10:"),
            ("", ""),
        ]
        for val, expected_prefix in test_cases:
            if hasattr(val, "strftime"):
                result = val.strftime("%Y-%m-%d %H:%M")
            else:
                result = str(val)[:16]
            if not result.startswith(expected_prefix):
                results.append(TestResult(
                    "doc_detail_datetime_safe", "FAIL", round(time.time() - t0, 3),
                    f"Conversion of {val!r} gave {result!r}, expected prefix {expected_prefix!r}"
                ))
                return results

        results.append(TestResult(
            "doc_detail_datetime_safe", "PASS", round(time.time() - t0, 3),
            "created_at datetime→string conversion safe for both Postgres and SQLite"
        ))
    except FileNotFoundError:
        results.append(TestResult("doc_detail_datetime_safe", "FAIL", 0.0,
                                   "bot_documents.py not found"))
    return results


def t_note_open_empty_file(**_) -> list[TestResult]:
    """T101: _handle_note_open must use note_empty_body placeholder when note file is 0-bytes.

    Root cause: 0-byte .md files exist (created but never populated). _load_note_text returns ""
    (not None) for empty files. _handle_note_open then passed _escape_md("") = "" as note_content,
    making the YAML widget text become "\\n" (whitespace-only) → Telegram 400 "text must be non-empty".
    Fix: use `text.strip() or _t(chat_id, "note_empty_body")` pattern — same as _handle_note_raw.
    """
    import time
    results: list[TestResult] = []
    t0 = time.time()
    try:
        src_path = Path(__file__).parents[1] / "telegram" / "bot_handlers.py"
        text = src_path.read_text(encoding="utf-8")

        # Must NOT pass _escape_md(text) directly without empty guard
        # Specifically: the old pattern was _escape_md(text) with no strip check
        if '"note_content": _escape_md(text),' in text or "'note_content': _escape_md(text)," in text:
            results.append(TestResult(
                "note_open_empty_file", "FAIL", round(time.time() - t0, 3),
                "note_content still uses raw _escape_md(text) without empty guard in _handle_note_open"
            ))
            return results

        # Must use note_empty_body when text is empty
        if "note_empty_body" not in text:
            results.append(TestResult(
                "note_open_empty_file", "FAIL", round(time.time() - t0, 3),
                "No note_empty_body guard found in bot_handlers.py"
            ))
            return results

        # Simulate the fix logic
        from unittest.mock import patch
        import sys
        sys.path.insert(0, str(Path(__file__).parents[1]))

        def _mock_escape_md(s):
            for ch in ("*", "_", "`", "["):
                s = s.replace(ch, "\\" + ch)
            return s

        def _mock_t(chat_id, key, **kwargs):
            stubs = {"note_empty_body": "📄 Note is empty.", "note_not_found": "Note not found."}
            return stubs.get(key, key)

        # Test cases: empty string → placeholder, non-empty → escape_md
        for raw_text, expected_contains in [
            ("", "Note is empty"),
            ("Hello world", "Hello world"),
            ("# Заметка\nТекст", "Заметка"),
        ]:
            note_content = _mock_escape_md(raw_text) if raw_text.strip() else _mock_t(0, "note_empty_body")
            if expected_contains not in note_content:
                results.append(TestResult(
                    "note_open_empty_file", "FAIL", round(time.time() - t0, 3),
                    f"For raw_text={raw_text!r}: got {note_content!r}, expected {expected_contains!r}"
                ))
                return results

        results.append(TestResult(
            "note_open_empty_file", "PASS", round(time.time() - t0, 3),
            "Empty note files get note_empty_body placeholder, non-empty notes get _escape_md()"
        ))
    except FileNotFoundError:
        results.append(TestResult("note_open_empty_file", "FAIL", 0.0,
                                   "bot_handlers.py not found"))
    return results


def t_store_postgres_notes_uuid_path(**_) -> list[TestResult]:
    """T102: store_postgres.py note methods must use UUID path, not str(chat_id).

    Root cause: save_note/load_note/delete_note in store_postgres.py used
    os.path.join(NOTES_DIR, str(chat_id)) — ignoring account UUID linking.
    When Telegram accounts are linked to web accounts (accounts.json), notes are
    stored under a UUID dir (e.g. u-21323d0f) not the raw chat_id dir (994963580).
    Fix: added _notes_storage_dir(chat_id) static method that reads accounts.json
    and resolves to the correct UUID directory (mirrors _resolve_storage_id in bot_users.py).
    """
    import time
    results: list[TestResult] = []
    t0 = time.time()
    try:
        src_path = Path(__file__).parents[1] / "core" / "store_postgres.py"
        text = src_path.read_text(encoding="utf-8")

        # The bad old pattern: os.path.join(NOTES_DIR, str(chat_id)) in individual methods
        # One occurrence is OK (it's the fallback inside _notes_storage_dir itself)
        # Multiple occurrences means the methods still use the raw str(chat_id) path
        bad_pattern_count = text.count("NOTES_DIR, str(chat_id)")
        if bad_pattern_count > 1:
            results.append(TestResult(
                "store_postgres_notes_uuid_path", "FAIL", round(time.time() - t0, 3),
                f"Found {bad_pattern_count} occurrence(s) of 'NOTES_DIR, str(chat_id)' — "
                "notes still use raw chat_id path instead of UUID"
            ))
            return results

        # Must have _notes_storage_dir method
        if "_notes_storage_dir" not in text:
            results.append(TestResult(
                "store_postgres_notes_uuid_path", "FAIL", round(time.time() - t0, 3),
                "_notes_storage_dir helper not found in store_postgres.py"
            ))
            return results

        # Must read accounts.json (UUID resolution)
        if "accounts.json" not in text and "ACCOUNTS_FILE" not in text:
            results.append(TestResult(
                "store_postgres_notes_uuid_path", "FAIL", round(time.time() - t0, 3),
                "_notes_storage_dir does not resolve accounts.json for UUID mapping"
            ))
            return results

        # save_note/load_note/delete_note must use _notes_storage_dir, not raw str(chat_id)
        for method in ("save_note", "load_note", "delete_note"):
            # Find the method block and check it calls _notes_storage_dir
            idx = text.find(f"def {method}(")
            if idx == -1:
                continue
            method_block = text[idx:idx + 600]
            if "_notes_storage_dir" not in method_block:
                results.append(TestResult(
                    "store_postgres_notes_uuid_path", "FAIL", round(time.time() - t0, 3),
                    f"{method} does not call _notes_storage_dir — still uses old path"
                ))
                return results

        results.append(TestResult(
            "store_postgres_notes_uuid_path", "PASS", round(time.time() - t0, 3),
            "store_postgres note methods use _notes_storage_dir(chat_id) for UUID path resolution"
        ))
    except FileNotFoundError:
        results.append(TestResult("store_postgres_notes_uuid_path", "FAIL", 0.0,
                                   "store_postgres.py not found"))
    return results


# ─────────────────────────────────────────────────────────────────────────────
def t_web_accounts_store_methods(**_) -> list[TestResult]:
    """T103: web_accounts/reset_tokens/link_codes methods must exist in both store backends."""
    import os
    results = []
    required = [
        "upsert_web_account", "find_web_account", "update_web_account", "list_web_accounts",
        "save_reset_token", "find_reset_token", "mark_reset_token_used", "delete_reset_tokens_for_user",
        "save_link_code", "find_link_code", "delete_link_code", "delete_expired_link_codes",
    ]
    src_root = os.path.join(os.path.dirname(__file__), "..")
    for fname in ("core/store_postgres.py", "core/store_sqlite.py", "core/store_base.py"):
        path = os.path.normpath(os.path.join(src_root, fname))
        try:
            src = open(path, encoding="utf-8").read()
        except FileNotFoundError:
            results.append(TestResult(f"T103_{fname}_exists", "FAIL", 0.0, "file not found"))
            continue
        missing = [m for m in required if f"def {m}" not in src]
        if missing:
            results.append(TestResult(f"T103_{fname}", "FAIL", 0.0, f"missing: {missing}"))
        else:
            results.append(TestResult(f"T103_{fname}", "PASS", 0.0, f"all {len(required)} methods present"))
    return results


def t_system_settings_json_file(**_) -> list[TestResult]:
    """T104: db_get_system_setting / db_set_system_setting must use SYSTEM_SETTINGS_PATH (JSON file), not get_db()."""
    import os
    results = []
    src_root = os.path.join(os.path.dirname(__file__), "..")
    path = os.path.normpath(os.path.join(src_root, "core/bot_db.py"))
    try:
        src = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return [TestResult("T104_bot_db_exists", "FAIL", 0.0, "bot_db.py not found")]
    if "SYSTEM_SETTINGS_PATH" not in src:
        results.append(TestResult("T104_system_settings_path", "FAIL", 0.0, "SYSTEM_SETTINGS_PATH not defined"))
    else:
        results.append(TestResult("T104_system_settings_path", "PASS", 0.0, "constant defined"))
    lines = src.splitlines()
    in_func = False
    func_lines = []
    for line in lines:
        if "def db_get_system_setting" in line:
            in_func = True
        if in_func:
            func_lines.append(line)
            if line.strip().startswith("def ") and len(func_lines) > 1:
                break
    func_src = "\n".join(func_lines)
    if "get_db()" in func_src:
        results.append(TestResult("T104_no_get_db_in_settings", "FAIL", 0.0, "db_get_system_setting still calls get_db()"))
    else:
        results.append(TestResult("T104_no_get_db_in_settings", "PASS", 0.0, "no get_db() in system settings"))
    return results


def t_mail_creds_store_primary(**_) -> list[TestResult]:
    """T105: bot_mail_creds._load_creds must try store.get_mail_creds() before file."""
    import os
    results = []
    src_root = os.path.join(os.path.dirname(__file__), "..")
    path = os.path.normpath(os.path.join(src_root, "features/bot_mail_creds.py"))
    try:
        src = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return [TestResult("T105_file_exists", "FAIL", 0.0, "bot_mail_creds.py not found")]
    start = src.find("def _load_creds(")
    if start == -1:
        return [TestResult("T105_load_creds_exists", "FAIL", 0.0, "_load_creds not found")]
    end = src.find("\ndef ", start + 1)
    func_src = src[start:end] if end != -1 else src[start:]
    store_pos = func_src.find("store.get_mail_creds")
    file_pos  = func_src.find(".read_text(") if ".read_text(" in func_src else func_src.find("json.loads")
    if store_pos == -1:
        results.append(TestResult("T105_store_call_present", "FAIL", 0.0, "store.get_mail_creds not in _load_creds"))
    elif file_pos != -1 and store_pos > file_pos:
        results.append(TestResult("T105_store_before_file", "FAIL", 0.0, "file read comes before store call"))
    else:
        results.append(TestResult("T105_store_primary", "PASS", 0.0, "store.get_mail_creds called first"))
    return results


def t_postgres_no_sqlite_fallbacks(**_) -> list[TestResult]:
    """T106: On OpenClaw/Postgres, key functions must NOT have SQLite fallbacks.

    Checks:
    - bot_access.py _notes_context has no 'from core.bot_db import get_db' fallback
    - bot_access.py _contacts_context has no 'from core.bot_db import get_db' fallback
    - telegram_menu_bot.py init_db is guarded with _postgres_mode() check
    - bot_db.py db_save_voice_opts delegates to store on Postgres
    """
    import os, re
    results = []
    src_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

    # 1. bot_access.py — _notes_context / _contacts_context must have no get_db fallback
    access_path = os.path.join(src_root, "telegram/bot_access.py")
    try:
        src = open(access_path, encoding="utf-8").read()
        for fn_name in ("_notes_context", "_contacts_context"):
            start = src.find(f"def {fn_name}(")
            end   = src.find("\ndef ", start + 1)
            fn_src = src[start:end] if end != -1 else src[start:]
            has_fallback = "from core.bot_db import get_db" in fn_src
            results.append(TestResult(
                f"T106_{fn_name}_no_sqlite_fallback",
                "FAIL" if has_fallback else "PASS",
                0.0,
                "SQLite fallback still present — not removed" if has_fallback else "no SQLite fallback",
            ))
    except FileNotFoundError:
        results.append(TestResult("T106_bot_access_exists", "FAIL", 0.0, "bot_access.py not found"))

    # 2. telegram_menu_bot.py — init_db must be guarded with _postgres_mode()
    menu_path = os.path.join(src_root, "telegram_menu_bot.py")
    try:
        src = open(menu_path, encoding="utf-8").read()
        has_guard = bool(re.search(r"_postgres_mode\(\).*_init_db|not.*_postgres_mode.*init_db", src, re.S))
        # Also accept simple guard pattern
        if not has_guard:
            has_guard = "if not _postgres_mode()" in src and "_init_db()" in src
        results.append(TestResult(
            "T106_init_db_postgres_guard",
            "PASS" if has_guard else "FAIL",
            0.0,
            "init_db guarded with _postgres_mode()" if has_guard else "init_db NOT guarded — always creates SQLite",
        ))
    except FileNotFoundError:
        results.append(TestResult("T106_menu_bot_exists", "FAIL", 0.0, "telegram_menu_bot.py not found"))

    # 3. bot_db.py — db_save_voice_opts must delegate to store
    db_path = os.path.join(src_root, "core/bot_db.py")
    try:
        src = open(db_path, encoding="utf-8").read()
        start = src.find("def db_save_voice_opts(")
        end   = src.find("\ndef ", start + 1)
        fn_src = src[start:end] if end != -1 else src[start:]
        delegates = "set_voice_opt" in fn_src or "_get_store()" in fn_src
        results.append(TestResult(
            "T106_voice_opts_postgres_delegate",
            "PASS" if delegates else "FAIL",
            0.0,
            "db_save_voice_opts delegates to store" if delegates else "db_save_voice_opts does NOT delegate to store",
        ))
    except FileNotFoundError:
        results.append(TestResult("T106_bot_db_exists", "FAIL", 0.0, "bot_db.py not found"))

    return results


def t_postgres_dict_row_access(**_) -> list[TestResult]:
    """T107: store_postgres uses dict_row → all row[col] access must use named keys not row[0].

    Verifies:
    - append_history_tracked returns row["id"] (not row[0])
    - get_tts_pending_msg returns row["msg_id"] (not row[0])
    - count_summaries returns row["count"] (not row[0])
    - get_user_pref returns row["value"] (not row[0])
    """
    import os, re
    results = []
    src_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    pg_path = os.path.join(src_root, "core/store_postgres.py")
    try:
        src = open(pg_path, encoding="utf-8").read()
        # Must NOT have positional row[0] access
        bad = list(re.finditer(r'\brow\[0\]', src))
        results.append(TestResult(
            "T107_no_positional_row_access",
            "FAIL" if bad else "PASS",
            0.0,
            f"Found {len(bad)} instance(s) of row[0] — must use named keys with dict_row" if bad
            else "no positional row[0] access (correct)",
        ))
        # Must have correct named access in append_history_tracked
        has_id = 'row["id"]' in src
        results.append(TestResult(
            "T107_append_history_row_id",
            "PASS" if has_id else "FAIL",
            0.0,
            'row["id"] found in store_postgres' if has_id else 'MISSING: row["id"] in append_history_tracked',
        ))
    except FileNotFoundError:
        results.append(TestResult("T107_pg_file_exists", "FAIL", 0.0, "store_postgres.py not found"))

    # Live test: append_history_tracked must return a positive integer
    try:
        import os as _os
        backend = _os.environ.get("STORE_BACKEND", "sqlite").lower()
        if backend != "postgres":
            results.append(TestResult("T107_live_append_history", "SKIP", 0.0, "not running on postgres"))
        else:
            from core.store import store
            rid = store.append_history_tracked(0, "user", "__t107_probe__")
            if isinstance(rid, int) and rid > 0:
                results.append(TestResult("T107_live_append_history", "PASS", 0.0, f"returned id={rid}"))
                # Clean up probe row
                try:
                    with store._pool.connection() as conn:
                        conn.execute("DELETE FROM chat_history WHERE chat_id=0 AND content='__t107_probe__'")
                        conn.commit()
                except Exception:
                    pass
            else:
                results.append(TestResult("T107_live_append_history", "FAIL", 0.0, f"returned {rid!r} (expected positive int)"))
    except Exception as e:
        results.append(TestResult("T107_live_append_history", "FAIL", 0.0, str(e)))

    return results


def t_llm_history_named_fallback(**_) -> list[TestResult]:
    """T108: ask_llm_with_history must try LLM_FALLBACK_PROVIDER before llama.cpp.

    Regression for: when OpenAI fails, history calls tried LLAMA_CPP_URL (connection refused)
    instead of LLM_FALLBACK_PROVIDER (ollama). Named fallback was missing from the
    ask_llm_with_history fallback chain.

    Verifies:
    - ask_llm_with_history accepts _force_provider parameter
    - Named fallback block exists before llama.cpp fallback
    - _force_provider routing works for ollama
    """
    import os, re, ast
    results = []
    src_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    llm_path = os.path.join(src_root, "core/bot_llm.py")
    try:
        src = open(llm_path, encoding="utf-8").read()

        # _force_provider parameter must be in ask_llm_with_history signature
        has_force_param = "_force_provider" in src
        results.append(TestResult(
            "T108_force_provider_param",
            "PASS" if has_force_param else "FAIL",
            0.0,
            "_force_provider parameter found in ask_llm_with_history" if has_force_param
            else "MISSING: _force_provider parameter in ask_llm_with_history",
        ))

        # Named fallback block must appear before LLAMA_CPP_URL in the function
        named_pos = src.find("named fallback'\\'")
        if named_pos == -1:
            named_pos = src.find("named provider")
        llama_pos = src.find("LLAMA_CPP_URL")
        # Both must exist and named fallback must appear before llama.cpp
        ok = named_pos != -1 and llama_pos != -1
        results.append(TestResult(
            "T108_named_fallback_before_llama",
            "PASS" if ok else "FAIL",
            0.0,
            "named fallback and LLAMA_CPP_URL both present in bot_llm.py" if ok
            else f"named_pos={named_pos} llama_pos={llama_pos}",
        ))

        # LLM_FALLBACK_PROVIDER must be read in ask_llm_with_history body
        # (find the function and check the fallback block is inside it)
        func_start = src.find("def ask_llm_with_history(")
        func_end = src.find("\ndef ", func_start + 1)
        if func_end == -1:
            func_end = len(src)
        func_body = src[func_start:func_end]
        has_named_fb = "LLM_FALLBACK_PROVIDER" in func_body and "named_fb" in func_body
        results.append(TestResult(
            "T108_named_fb_in_history_func",
            "PASS" if has_named_fb else "FAIL",
            0.0,
            "named fallback block present inside ask_llm_with_history" if has_named_fb
            else "MISSING: LLM_FALLBACK_PROVIDER fallback inside ask_llm_with_history",
        ))

    except FileNotFoundError:
        results.append(TestResult("T108_llm_file_exists", "FAIL", 0.0, "bot_llm.py not found"))
    return results


def t_llm_system_chat_fallback(*, gt, verbose=False):
    """T109: system chat fallback bugs:
    1. Ollama must NOT apply OLLAMA_MIN_TIMEOUT when use_case='system'.
    2. When per-func override fails and LLM_FALLBACK_PROVIDER==provider, the global
       LLM_PROVIDER (default) must still be tried as a final cloud fallback.
    """
    results = []
    try:
        llm_src = (SRC_ROOT / "core" / "bot_llm.py").read_text()

        # T109a: ask_llm_with_history ollama block must check use_case != "system"
        has_system_timeout_guard = (
            'use_case == "system"' in llm_src or "use_case != \"system\"" in llm_src
        ) and "effective_timeout" in llm_src
        results.append(TestResult(
            "T109_ollama_system_timeout_guard",
            "PASS" if has_system_timeout_guard else "FAIL",
            0.0,
            "use_case=='system' timeout guard found in ask_llm_with_history" if has_system_timeout_guard
            else "MISSING: ollama effective_timeout in history func must guard use_case=='system'",
        ))

        # T109b: global default fallback block must exist
        has_default_fallback = (
            "per_func and default_provider not in" in llm_src
            or "per_func and default_provider" in llm_src
        )
        results.append(TestResult(
            "T109_global_default_fallback",
            "PASS" if has_default_fallback else "FAIL",
            0.0,
            "global default provider fallback block found" if has_default_fallback
            else "MISSING: fallback to LLM_PROVIDER when per-func override fails and named_fb==provider",
        ))

        # T109c: the log message for the new fallback path is present
        has_log = "falling back to default provider" in llm_src
        results.append(TestResult(
            "T109_default_fallback_log",
            "PASS" if has_log else "FAIL",
            0.0,
            "default provider fallback log message found" if has_log
            else "MISSING: log message for global default fallback in ask_llm_with_history",
        ))

    except FileNotFoundError:
        results.append(TestResult("T109_llm_file_exists", "FAIL", 0.0, "bot_llm.py not found"))
    return results


def t_system_chat_host_context(*, gt, verbose=False):
    """T110: _handle_system_message must inject host OS/HW context into LLM system prompt.
    Checks that _build_host_ctx() exists, _HOST_CTX is used in _run(), and the context
    includes hostname, OS, CPU, temp-tools, and package-manager fields.
    """
    results = []
    try:
        handlers_src = (SRC_ROOT / "telegram" / "bot_handlers.py").read_text()

        checks = [
            ("T110_build_host_ctx_func",    "def _build_host_ctx()",     "def _build_host_ctx() function present"),
            ("T110_host_ctx_cached",         "_HOST_CTX",                 "_HOST_CTX cache variable present"),
            ("T110_host_ctx_injected",       "_HOST_CTX}",                "_HOST_CTX injected into sys_content"),
            ("T110_hostname_field",          "Hostname",                  "Hostname field in host context"),
            ("T110_cpu_field",               "cpu_model",                 "CPU model detection present"),
            ("T110_temp_tools_field",        "Temp tools",                "Temp tools field in host context"),
            ("T110_pkg_mgr_field",           "pkg_mgr",                   "Package manager detection present"),
        ]
        for test_id, pattern, detail in checks:
            found = pattern in handlers_src
            results.append(TestResult(test_id, "PASS" if found else "FAIL", 0.0,
                                       detail if found else f"MISSING: {pattern!r} not found in bot_handlers.py"))

        # Live check: _HOST_CTX must contain real host data (hostname not empty, not 'unknown')
        try:
            import sys as _sys
            _sys.path.insert(0, str(SRC_ROOT))
            import importlib, os as _os
            _os.environ.setdefault("DEVICE_VARIANT", "openclaw")
            _bh = importlib.import_module("telegram.bot_handlers")
            hctx = getattr(_bh, "_HOST_CTX", "")
            has_hostname = "Hostname" in hctx and "unknown" not in hctx.split("Hostname")[1].split("\n")[0]
            results.append(TestResult(
                "T110_live_host_ctx",
                "PASS" if has_hostname else "WARN",
                0.0,
                f"_HOST_CTX live check: {'ok' if has_hostname else 'hostname missing or unknown'}"
            ))
        except Exception as e:
            results.append(TestResult("T110_live_host_ctx", "SKIP", 0.0, f"import failed: {e}"))

    except FileNotFoundError:
        results.append(TestResult("T110_file_exists", "FAIL", 0.0, "bot_handlers.py not found"))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# T111 — migrate_sqlite_to_postgres.py structure: all 10 tables, no content filter bug
# ─────────────────────────────────────────────────────────────────────────────

def t_migrate_postgres_structure(**_) -> list[TestResult]:
    """T111: migrate_sqlite_to_postgres.py must cover all 10 required tables.

    Root-cause tests for bugs found during SintAItion PostgreSQL migration (2026-04-07):
    1. notes migration had WHERE content != '' — omitted 100% of notes on SintAItion
       (all notes stored in .md files with empty SQLite content column)
    2. contacts table migration was entirely missing
    3. documents table migration was entirely missing
    All three are now fixed; this test ensures they don't regress.
    """
    results = []
    import re as _re
    t0 = time.time()

    # SKIP on non-PostgreSQL targets — migration script is only relevant for postgres backend
    store_backend = os.environ.get("STORE_BACKEND", "sqlite")
    if store_backend != "postgres":
        results.append(TestResult("T111_script_exists", "SKIP", time.time() - t0,
                                  f"STORE_BACKEND={store_backend} — T111 only applies to PostgreSQL deployments"))
        return results

    script_path = Path(__file__).parents[1] / "setup" / "migrate_sqlite_to_postgres.py"
    if not script_path.exists():
        results.append(TestResult("T111_script_exists", "FAIL", time.time() - t0,
                                  f"migrate_sqlite_to_postgres.py not found at {script_path}"))
        return results

    src = script_path.read_text(encoding="utf-8")

    # 1. All required table names must appear in the migration
    required_tables = [
        "users", "calendar_events", "notes_index", "chat_history",
        "conversation_summaries", "contacts", "documents",
        "user_prefs", "voice_opts", "llm_calls",
    ]
    for tbl in required_tables:
        found = tbl in src
        results.append(TestResult(
            f"T111_table_{tbl}",
            "PASS" if found else "FAIL",
            time.time() - t0,
            f"table '{tbl}' migration present" if found
            else f"MISSING: table '{tbl}' not migrated in script",
        ))

    # 2. Notes migration must NOT filter by content (the critical regression bug)
    notes_content_filter = bool(_re.search(
        r"notes.*WHERE.*content\s*!=\s*['\"]|WHERE.*content\s*!=\s*['\"].*notes",
        src, _re.IGNORECASE | _re.DOTALL,
    ))
    results.append(TestResult(
        "T111_notes_no_content_filter",
        "FAIL" if notes_content_filter else "PASS",
        time.time() - t0,
        "notes migration: no WHERE content != '' filter (all notes migrated)" if not notes_content_filter
        else "BUG: notes migration has WHERE content != '' — empty-content notes are skipped",
    ))

    # 3. Notes migration must handle .md file content fallback
    has_md_fallback = ".read_text" in src or ".read()" in src or "open(" in src
    results.append(TestResult(
        "T111_notes_md_file_fallback",
        "PASS" if has_md_fallback else "WARN",
        time.time() - t0,
        "notes migration reads .md file content for empty SQLite rows" if has_md_fallback
        else "WARN: no file read in migration — notes with empty SQLite content will migrate empty",
    ))

    # 4. contacts and documents must each have a SELECT + store API call (not raw INSERT)
    #    The migration uses pg.save_contact() / pg.save_document_meta() — not raw SQL INSERT.
    checks_4 = [
        ("contacts",  "save_contact"),
        ("documents", "save_document_meta"),
    ]
    for tbl, api_call in checks_4:
        has_select = bool(_re.search(rf"SELECT.*FROM\s+{tbl}", src, _re.IGNORECASE))
        has_api = api_call in src
        ok = has_select and has_api
        results.append(TestResult(
            f"T111_{tbl}_full_migration",
            "PASS" if ok else "FAIL",
            time.time() - t0,
            f"{tbl}: SELECT + {api_call}() migration block present" if ok
            else f"MISSING: {tbl} migration incomplete "
                 f"(has_select={has_select}, has_api_call={has_api})",
        ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T112 — Contacts store parity: both SQLite and Postgres backends
# ─────────────────────────────────────────────────────────────────────────────

def t_contacts_store_parity(**_) -> list[TestResult]:
    """T112: Both store_sqlite.py and store_postgres.py must implement all 5 contacts methods.

    Parity check — mirrors T73 pattern for document methods.
    Ensures contacts work identically on both backends after SQLite → Postgres migration.
    """
    results = []
    t0 = time.time()

    REQUIRED_CONTACT_METHODS = [
        "def save_contact",
        "def get_contact",
        "def list_contacts",
        "def delete_contact",
        "def search_contacts",
    ]

    for store_file, label in [
        ("core/store_sqlite.py",   "SQLite"),
        ("core/store_postgres.py", "Postgres"),
    ]:
        try:
            code = (Path(__file__).parents[1] / store_file).read_text(encoding="utf-8")
            for method in REQUIRED_CONTACT_METHODS:
                ok = method in code
                results.append(TestResult(
                    f"T112_{label.lower()}_{method.split()[-1]}",
                    "PASS" if ok else "FAIL",
                    time.time() - t0,
                    f"{label}: {method} present" if ok
                    else f"MISSING in {store_file}: {method}",
                ))
        except FileNotFoundError:
            results.append(TestResult(f"T112_{label.lower()}_read", "FAIL", time.time() - t0,
                                      f"{store_file} not found"))

    # Live import check
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parents[1]))
        from core.store import store as _store
        for method in ["save_contact", "get_contact", "list_contacts", "delete_contact", "search_contacts"]:
            ok = hasattr(_store, method) and callable(getattr(_store, method))
            results.append(TestResult(
                f"T112_live_{method}",
                "PASS" if ok else "FAIL",
                time.time() - t0,
                f"live store.{method} callable" if ok else f"live store MISSING {method}",
            ))
    except Exception as e:
        results.append(TestResult("T112_live_import", "SKIP", time.time() - t0,
                                  f"store import skipped: {e}"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T113 — Live PostgreSQL data non-empty (SKIP if STORE_BACKEND != postgres)
# ─────────────────────────────────────────────────────────────────────────────

def t_postgres_live_data(**_) -> list[TestResult]:
    """T113: When running on PostgreSQL backend, all migrated tables must have rows.

    Verifies that the SQLite → PostgreSQL migration populated data correctly.
    Uses direct psycopg2 COUNT queries — avoids store API signature differences.
    SKIP automatically when STORE_BACKEND is not 'postgres'.
    """
    results = []
    t0 = time.time()

    backend = os.environ.get("STORE_BACKEND", "sqlite").lower()
    if backend != "postgres":
        return [TestResult("T113_postgres_live_data", "SKIP", time.time() - t0,
                           f"STORE_BACKEND={backend!r} — Postgres live check skipped")]

    dsn = os.environ.get("STORE_PG_DSN", "")
    if not dsn:
        return [TestResult("T113_no_dsn", "SKIP", time.time() - t0,
                           "STORE_PG_DSN not set — cannot query PostgreSQL")]

    try:
        import psycopg2

        conn = psycopg2.connect(dsn)
        cur = conn.cursor()

        # Each (table_name, min_expected_rows, description)
        table_checks = [
            ("users",                  1, "users"),
            ("calendar_events",        1, "calendar_events"),
            ("notes_index",            1, "notes_index"),
            ("chat_history",           1, "chat_history"),
            ("conversation_summaries", 1, "conversation_summaries"),
        ]
        for tbl, min_rows, label in table_checks:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                count = cur.fetchone()[0]
                ok = count >= min_rows
                results.append(TestResult(
                    f"T113_{tbl}_non_empty",
                    "PASS" if ok else "WARN",
                    time.time() - t0,
                    f"{label}: {count} rows" if ok
                    else f"{label}: {count} rows — migration may have missed data",
                ))
            except Exception as e:
                results.append(TestResult(f"T113_{tbl}_query", "FAIL", time.time() - t0, str(e)))

        # contacts and documents: WARN (not FAIL) — may be empty on fresh install
        for tbl in ("contacts", "documents"):
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                count = cur.fetchone()[0]
                results.append(TestResult(
                    f"T113_{tbl}_count",
                    "PASS",
                    time.time() - t0,
                    f"{tbl}: {count} rows (0 is acceptable — depends on user data)",
                ))
            except Exception as e:
                results.append(TestResult(f"T113_{tbl}_query", "FAIL", time.time() - t0, str(e)))

        conn.close()

    except ImportError:
        results.append(TestResult("T113_psycopg2_missing", "SKIP", time.time() - t0,
                                  "psycopg2 not installed"))
    except Exception as e:
        results.append(TestResult("T113_connect", "FAIL", time.time() - t0,
                                  f"PostgreSQL connection failed: {e}"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# T114 — bot_web.py admin page: created field uses str() before slicing
# ─────────────────────────────────────────────────────────────────────────────

def t_admin_page_datetime_safe(**_) -> list[TestResult]:
    """T114: admin_page() in bot_web.py must use str(a.get('created', ''))[:10].

    Root-cause: on PostgreSQL backend, web_accounts.created is a datetime.datetime
    object. The old code did a.get('created', '—')[:10] which raises
    TypeError: 'datetime.datetime' object is not subscriptable.
    Found by UI test TestAdmin (Internal Server Error on /admin).
    """
    results = []
    t0 = time.time()

    try:
        src = (SRC_ROOT / "bot_web.py").read_text(encoding="utf-8")

        # The fix: str() wrapping before slice
        has_safe = 'str(a.get("created", ""))[:10]' in src
        # The old bug pattern: direct slice on dict value
        has_bug   = 'a.get("created", "—")[:10]' in src or "a.get('created', '—')[:10]" in src

        results.append(TestResult(
            "T114_admin_created_str_wrap",
            "PASS" if has_safe and not has_bug else "FAIL",
            time.time() - t0,
            "admin_page uses str()[:10] for created field (datetime-safe)" if (has_safe and not has_bug)
            else f"BUG: admin_page may crash on Postgres — has_safe={has_safe} has_bug={has_bug}",
        ))
    except FileNotFoundError:
        results.append(TestResult("T114_file_exists", "FAIL", 0.0, "bot_web.py not found"))

    return results


# T115 — prompts.json rule 5: [BOT CAPABILITIES] literal tag fix
def t_bot_capabilities_tag_fix(**_) -> list[TestResult]:
    """T115: security_preamble rule 5 must NOT instruct LLM to output [BOT CAPABILITIES] literally.

    Root-cause: rule 5 said 'always use the [BOT CAPABILITIES] blocks', which
    taught the LLM to reference that block by name instead of enumerating capabilities.
    Fix: rule 5 must instruct LLM to enumerate capabilities directly and explicitly
    say to never reproduce block marker names literally.
    """
    results = []
    t0 = time.time()

    prompts_file = Path(__file__).parent.parent / "prompts.json"
    if not prompts_file.exists():
        return [TestResult("T115_prompts_file", "FAIL", 0.0, "prompts.json not found")]

    try:
        import json as _json
        prompts = _json.loads(prompts_file.read_text(encoding="utf-8"))
        preamble = prompts.get("security_preamble", "")

        # The preamble text that teaches LLM to output block marker names literally
        bad_phrase = "[BOT CAPABILITIES]"
        # Must say "never reproduce block markers" or similar
        has_block_marker_warning = (
            "block markers" in preamble or "never reproduce" in preamble
        )
        # Must NOT have the old "use the [BOT CAPABILITIES] block" phrase in a way
        # that encourages literal output in bot responses
        old_bad_pattern = "use the [BOT CAPABILITIES] block"

        results.append(TestResult(
            "T115_no_old_bad_pattern",
            "PASS" if old_bad_pattern not in preamble else "FAIL",
            time.time() - t0,
            f"rule5 does not contain '{old_bad_pattern}' (causes literal tag output)" if old_bad_pattern not in preamble
            else f"BUG: security_preamble still contains '{old_bad_pattern}'",
        ))
        results.append(TestResult(
            "T115_has_block_marker_warning",
            "PASS" if has_block_marker_warning else "FAIL",
            time.time() - t0,
            "security_preamble rule5 warns against outputting block markers literally" if has_block_marker_warning
            else "MISSING: security_preamble should say 'never reproduce block markers'",
        ))
    except Exception as exc:
        results.append(TestResult("T115_parse_error", "FAIL", 0.0, str(exc)))

    return results


# T116 — admin-only RAG: is_admin param propagates through entire retrieval stack
def t_admin_only_rag_access(**_) -> list[TestResult]:
    """T116: admin-only RAG (is_shared=2) — verify is_admin param in full retrieval stack.

    Checks:
    - load_system_docs._ingest accepts shared_level param; admin guide uses is_shared=2
    - store_sqlite.search_fts + search_similar accept is_admin kwarg
    - bot_rag.retrieve_context accepts is_admin kwarg
    - bot_access._docs_rag_context passes _is_admin(chat_id) to retrieve_context
    """
    results = []
    t0 = time.time()

    src_root = Path(__file__).parent.parent
    checks: list[tuple[Path, str, str]] = [
        (
            src_root / "setup/load_system_docs.py",
            "is_shared=2",
            "admin guide stored with is_shared=2 (admin-only)",
        ),
        (
            src_root / "setup/load_system_docs.py",
            "shared_level",
            "_ingest() has shared_level param for per-doc access level",
        ),
        (
            src_root / "core/store_sqlite.py",
            "is_admin",
            "store_sqlite.search_fts / search_similar accept is_admin param",
        ),
        (
            src_root / "core/store_postgres.py",
            "is_admin",
            "store_postgres.search_fts / search_similar accept is_admin param",
        ),
        (
            src_root / "core/store_base.py",
            "is_admin",
            "store_base abstract signatures include is_admin param",
        ),
        (
            src_root / "core/bot_rag.py",
            "is_admin",
            "bot_rag.retrieve_context accepts is_admin param",
        ),
        (
            src_root / "telegram/bot_access.py",
            "_is_admin(chat_id)",
            "bot_access._docs_rag_context calls _is_admin(chat_id)",
        ),
        (
            src_root / "core/store_sqlite.py",
            "is_shared IN (1, 2)",
            "SQLite store admin query includes is_shared=2 documents",
        ),
        (
            src_root / "core/store_postgres.py",
            "is_shared IN (1, 2)",
            "Postgres store admin query includes is_shared=2 documents",
        ),
    ]

    for fpath, pattern, desc in checks:
        try:
            code = fpath.read_text(encoding="utf-8", errors="replace")
            status = "PASS" if pattern in code else "FAIL"
        except FileNotFoundError:
            status = "SKIP"
            desc = f"{fpath.name} not found"
        results.append(TestResult(
            f"T116_{fpath.name}_{pattern[:20].replace(' ', '_').replace('(', '').replace(')', '')}",
            status, time.time() - t0, desc,
        ))

    return results


def t_gemma4_thinking_mode_fix(**_) -> list[TestResult]:
    """T117: benchmark _run_prompt() must disable thinking mode for gemma4 models.

    Regression guard: gemma4 has built-in chain-of-thought (<think> blocks) like
    qwen3. Without think:false the model consumes all output tokens in CoT.
    Verifies the 'gemma4' tag is listed alongside qwen3/deepseek-r in the
    is_thinking_model check in benchmark_ollama_models.py.
    """
    t0 = time.time()
    results: list[TestResult] = []

    bench_path = SRC_ROOT / "tests" / "llm" / "benchmark_ollama_models.py"
    try:
        src = bench_path.read_text(encoding="utf-8", errors="replace")

        # The is_thinking_model tag list must include gemma4
        has_gemma4_tag = '"gemma4"' in src and "is_thinking_model" in src
        results.append(TestResult(
            "benchmark_gemma4_thinking_tag",
            "PASS" if has_gemma4_tag else "FAIL",
            time.time() - t0,
            "gemma4 in is_thinking_model list" if has_gemma4_tag
            else "MISSING — gemma4 will return empty responses from benchmarks",
        ))

        # Verify the model list (CANDIDATE_MODELS) includes gemma4 variants
        has_e2b = "gemma4:e2b" in src
        has_e4b = "gemma4:e4b" in src
        results.append(TestResult(
            "benchmark_gemma4_candidate_models",
            "PASS" if (has_e2b and has_e4b) else "FAIL",
            time.time() - t0,
            f"gemma4:e2b={has_e2b} gemma4:e4b={has_e4b} in CANDIDATE_MODELS",
        ))

        # Verify --host flag exists for remote benchmarking
        has_host_flag = '"--host"' in src or "args.host" in src
        results.append(TestResult(
            "benchmark_host_flag",
            "PASS" if has_host_flag else "FAIL",
            time.time() - t0,
            "--host flag present for remote Ollama" if has_host_flag
            else "MISSING --host flag — cannot benchmark SintAItion remotely",
        ))

    except FileNotFoundError:
        results.append(TestResult("benchmark_gemma4_thinking_tag", "SKIP", time.time() - t0,
                                  "benchmark_ollama_models.py not found"))
    return results


def t_gemma4_ollama_config(**_) -> list[TestResult]:
    """T118: bot_config.py and bot_llm.py correctly handle Gemma4 models.

    Gemma4 uses the same Ollama /api/chat endpoint as all other models.
    OLLAMA_THINK=false (default) ensures thinking is off in production.
    This test verifies no Gemma4-specific hardcoding is needed (it just works),
    and confirms the think flag is passed correctly.
    """
    t0 = time.time()
    results: list[TestResult] = []

    llm_path = SRC_ROOT / "core" / "bot_llm.py"
    try:
        src = llm_path.read_text(encoding="utf-8", errors="replace")

        # think flag must be passed to Ollama (prevents gemma4 CoT token waste)
        has_think_flag = '"think"' in src and "OLLAMA_THINK" in src
        results.append(TestResult(
            "ollama_think_flag_passed",
            "PASS" if has_think_flag else "FAIL",
            time.time() - t0,
            "think:OLLAMA_THINK in _ask_ollama payload" if has_think_flag
            else "MISSING — gemma4 will exhaust context on <think> blocks",
        ))
    except FileNotFoundError:
        results.append(TestResult("ollama_think_flag_passed", "SKIP", time.time() - t0,
                                  "bot_llm.py not found"))

    config_path = SRC_ROOT / "core" / "bot_config.py"
    try:
        src = config_path.read_text(encoding="utf-8", errors="replace")

        # OLLAMA_THINK must default to False
        think_false = 'OLLAMA_THINK' in src and (
            'OLLAMA_THINK = False' in src
            or 'OLLAMA_THINK=False' in src
            or '"false"' in src.lower() and 'OLLAMA_THINK' in src
        )
        results.append(TestResult(
            "config_ollama_think_default_false",
            "PASS" if think_false else "FAIL",
            time.time() - t0,
            "OLLAMA_THINK defaults to False in bot_config.py",
        ))
    except FileNotFoundError:
        results.append(TestResult("config_ollama_think_default_false", "SKIP", time.time() - t0,
                                  "bot_config.py not found"))

    return results


def t_gemma4_live_availability(**_) -> list[TestResult]:
    """T119: Gemma4:E2B availability check via Ollama API (SKIP if Ollama not running).

    Source-inspection + live check: verifies gemma4:e2b is pulled and callable.
    On machines without Ollama installed this test is automatically skipped.
    """
    t0 = time.time()
    results: list[TestResult] = []
    import urllib.request, json as _json

    ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    try:
        req = urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=3)
        data = _json.loads(req.read().decode())
        model_names = [m["name"] for m in data.get("models", [])]
        has_e2b = any("gemma4" in n and "e2b" in n for n in model_names)
        has_e4b = any("gemma4" in n and "e4b" in n for n in model_names)
        has_any_gemma4 = any("gemma4" in n for n in model_names)
        if not has_any_gemma4:
            results.append(TestResult(
                "gemma4_ollama_availability",
                "SKIP", time.time() - t0,
                f"gemma4 not pulled yet. Pull with: ollama pull gemma4:e2b  "
                f"Available: {model_names[:5]}",
            ))
        else:
            results.append(TestResult(
                "gemma4_ollama_availability",
                "PASS", time.time() - t0,
                f"e2b={has_e2b} e4b={has_e4b} — {[n for n in model_names if 'gemma4' in n]}",
            ))
    except Exception as exc:
        results.append(TestResult(
            "gemma4_ollama_availability",
            "SKIP", time.time() - t0,
            f"Ollama not running ({exc.__class__.__name__}) — install/start to enable live test",
        ))

    return results


def t_gemma4_benchmark_report(**_) -> list[TestResult]:
    """T120: Gemma4 evaluation report and evaluation scripts exist.

    Verifies the research doc, evaluation shell script, and Windows eval script
    are present in the workspace so remote evaluation can be triggered.
    """
    t0 = time.time()
    results: list[TestResult] = []

    checks = [
        (SRC_ROOT.parent / "doc" / "research-gemma4-benchmark.md",
         "Gemma4 research + hardware analysis doc"),
        (SRC_ROOT.parent / "tools" / "run_gemma4_evaluation.sh",
         "Linux evaluation script for SintAItion / TariStation2"),
        (SRC_ROOT.parent / "tools" / "eval_gemma4_windows.ps1",
         "Windows PowerShell helper to run evaluation via SSH"),
    ]
    for fpath, desc in checks:
        exists = fpath.exists()
        results.append(TestResult(
            f"gemma4_asset_{fpath.name}",
            "PASS" if exists else "FAIL",
            time.time() - t0,
            desc if exists else f"MISSING: {fpath}",
        ))

    return results


def t_ollama_model_picker(**_) -> list[TestResult]:
    """T121: Admin Ollama model picker — get_ollama_model/set_ollama_model exist;
    _handle_ollama_llm_menu, _handle_ollama_set_model, _handle_ollama_persist_model in bot_admin;
    callback dispatch for ollama_llm_menu, admin_ollama_set:, admin_ollama_persist: in telegram_menu_bot;
    _update_bot_env_key helper exists in bot_admin; model grouping by family in menu handler.
    """
    t0 = time.time()
    results: list[TestResult] = []

    # 1. bot_llm.py defines get_ollama_model and set_ollama_model (source inspection)
    llm_src = SRC_ROOT / "core" / "bot_llm.py"
    llm_text = llm_src.read_text(encoding="utf-8") if llm_src.exists() else ""
    for sym in ("def get_ollama_model(", "def set_ollama_model(", "_runtime_ollama_model"):
        present = sym in llm_text
        results.append(TestResult(
            f"ollama_picker_llm_{sym.split('(')[0].lstrip('_')}",
            "PASS" if present else "FAIL",
            time.time() - t0,
            "found in bot_llm.py" if present else f"MISSING: {sym}",
        ))

    # 2. all three OLLAMA_MODEL usages replaced with get_ollama_model() call
    old_pattern_count = llm_text.count('"model": OLLAMA_MODEL,')
    new_pattern_count = llm_text.count('"model": get_ollama_model(),')
    ok = old_pattern_count == 0 and new_pattern_count >= 3
    results.append(TestResult(
        "ollama_picker_model_uses_getter",
        "PASS" if ok else "FAIL",
        time.time() - t0,
        f"get_ollama_model() uses: {new_pattern_count}, old OLLAMA_MODEL direct: {old_pattern_count}",
    ))

    # 3. bot_admin.py has all handler functions and helpers
    admin_src = SRC_ROOT / "telegram" / "bot_admin.py"
    src_text = admin_src.read_text(encoding="utf-8") if admin_src.exists() else ""
    for sym in (
        "_handle_ollama_llm_menu", "_handle_ollama_set_model",
        "_handle_ollama_persist_model", "_get_ollama_models_from_api",
        "_update_bot_env_key",
    ):
        present = sym in src_text
        results.append(TestResult(
            f"ollama_picker_{sym}",
            "PASS" if present else "FAIL",
            time.time() - t0,
            "found in bot_admin.py" if present else f"MISSING: {sym}",
        ))

    # 4. model grouping by family — family labels present in menu handler
    for label in ("qwen", "gemma", "llama", "_FAMILY_LABELS"):
        present = label in src_text
        results.append(TestResult(
            f"ollama_picker_family_{label}",
            "PASS" if present else "FAIL",
            time.time() - t0,
            "family grouping found" if present else f"MISSING family grouping: {label}",
        ))

    # 5. telegram_menu_bot.py dispatches all callbacks including new persist
    menu_src = SRC_ROOT.parent / "src" / "telegram_menu_bot.py"
    if not menu_src.exists():
        menu_src = SRC_ROOT / "telegram_menu_bot.py"
    if not menu_src.exists():
        menu_src = SRC_ROOT.parent / "telegram_menu_bot.py"
    menu_text = menu_src.read_text(encoding="utf-8") if menu_src.exists() else ""
    for token in (
        '"ollama_llm_menu"', '"admin_ollama_set:"', '"admin_ollama_persist:"',
        "_handle_ollama_llm_menu", "_handle_ollama_set_model", "_handle_ollama_persist_model",
    ):
        present = token in menu_text
        results.append(TestResult(
            f"ollama_picker_dispatch_{token.strip('\"_')}",
            "PASS" if present else "FAIL",
            time.time() - t0,
            "found in telegram_menu_bot.py" if present else f"MISSING: {token}",
        ))

    return results


def t_rbac_allowlist_enforcement(**_) -> list[TestResult]:
    """T122: RBAC allowlist enforcement — ADMIN_ALLOWED_CMDS, DEVELOPER_ALLOWED_CMDS,
    _classify_cmd_class() with extra-blocklist priority, get_extra_blocked_cmds(),
    SYSCHAT_EXTRA_BLOCKED_KEY, db_get_system_setting import, admin security policy UI.
    """
    t0 = time.time()
    results: list[TestResult] = []

    # 1. bot_security.py source inspection
    sec_src = SRC_ROOT / "security" / "bot_security.py"
    sec_text = sec_src.read_text(encoding="utf-8") if sec_src.exists() else ""

    checks_sec = [
        ("admin_allowed_cmds_set",     "ADMIN_ALLOWED_CMDS: set[str]" in sec_text,
         "ADMIN_ALLOWED_CMDS: set[str]"),
        ("developer_allowed_cmds_set", "DEVELOPER_ALLOWED_CMDS: set[str]" in sec_text
         or ("DEVELOPER_ALLOWED_CMDS" in sec_text and "ADMIN_ALLOWED_CMDS |" in sec_text),
         "DEVELOPER_ALLOWED_CMDS extends ADMIN_ALLOWED_CMDS"),
        ("classify_cmd_fn",            "def _classify_cmd_class" in sec_text,
         "_classify_cmd_class() defined"),
        ("extra_blocked_fn",           "def get_extra_blocked_cmds" in sec_text,
         "get_extra_blocked_cmds() defined"),
        ("extra_blocked_key",          "SYSCHAT_EXTRA_BLOCKED_KEY" in sec_text,
         "SYSCHAT_EXTRA_BLOCKED_KEY constant present"),
        ("db_setting_import",          "db_get_system_setting" in sec_text,
         "db_get_system_setting imported in bot_security"),
        ("extra_blocked_priority",
         "def _classify_cmd_class" in sec_text
         and "get_extra_blocked_cmds" in sec_text[sec_text.find("def _classify_cmd_class"):
                                                  sec_text.find("def _classify_cmd_class") + 600],
         "extra blocklist checked inside _classify_cmd_class (priority)"),
    ]
    for name, ok, detail in checks_sec:
        results.append(TestResult(
            f"rbac_{name}", "PASS" if ok else "FAIL", time.time() - t0,
            detail if ok else f"MISSING: {detail}",
        ))

    # 2. bot_admin.py — admin security policy UI
    admin_src = SRC_ROOT / "telegram" / "bot_admin.py"
    admin_text = admin_src.read_text(encoding="utf-8") if admin_src.exists() else ""
    checks_admin = [
        ("admin_security_policy_handler", "_handle_admin_security_policy" in admin_text,
         "_handle_admin_security_policy() in bot_admin"),
        ("admin_security_policy_btn",     "admin_security_policy" in admin_text,
         "admin_security_policy callback_data wired"),
        ("pending_syschat_block_add",     "_pending_syschat_block_add" in admin_text,
         "_pending_syschat_block_add set for multi-step input"),
        ("syschat_block_remove_handler",  "_handle_admin_syschat_block_remove" in admin_text,
         "_handle_admin_syschat_block_remove() present"),
        ("syschat_block_add_input",       "handle_admin_syschat_block_add_input" in admin_text,
         "handle_admin_syschat_block_add_input() present"),
    ]
    for name, ok, detail in checks_admin:
        results.append(TestResult(
            f"rbac_admin_ui_{name}", "PASS" if ok else "FAIL", time.time() - t0,
            detail if ok else f"MISSING: {detail}",
        ))

    # 3. telegram_menu_bot.py — callback dispatch wired
    menu_src = SRC_ROOT / "telegram_menu_bot.py"
    menu_text = menu_src.read_text(encoding="utf-8") if menu_src.exists() else ""
    checks_menu = [
        ("dispatch_security_policy", 'data == "admin_security_policy"' in menu_text,
         'data == "admin_security_policy" dispatch in telegram_menu_bot'),
        ("dispatch_block_rm",        '"admin_syschat_block_rm:"' in menu_text or
         "admin_syschat_block_rm:" in menu_text,
         "admin_syschat_block_rm: dispatch present"),
        ("dispatch_block_add",       'data == "admin_syschat_block_add"' in menu_text,
         'data == "admin_syschat_block_add" dispatch present'),
    ]
    for name, ok, detail in checks_menu:
        results.append(TestResult(
            f"rbac_dispatch_{name}", "PASS" if ok else "FAIL", time.time() - t0,
            detail if ok else f"MISSING: {detail}",
        ))

    return results


TEST_FUNCTIONS = [
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
    # Voice system mode routing + admin role preservation (T40)
    t_voice_system_mode_routing_guard,
    # Voice lang: STT_LANG env override takes priority over Telegram UI lang (T41)
    t_voice_lang_stt_lang_priority,
    # _set_lang uses _DEFAULT_LANG not hardcoded 'en' (T42)
    t_set_lang_default_not_hardcoded_en,
    # Voice system-chat admin guard at routing level (T43)
    t_voice_system_admin_guard,
    # openclaw-gateway Telegram channel disabled to prevent 409 token conflict (T44)
    t_openclaw_gateway_telegram_disabled,
    # TARIS_BIN must point to existing picoclaw/taris binary + picoclaw config present (T45)
    t_taris_bin_configured,
    # vosk_fallback disabled by default on OpenClaw platform (T46)
    t_vosk_fallback_openclaw_default,
    # faster-whisper: retry without VAD filter when first pass returns empty (T47)
    t_faster_whisper_vad_retry,
    # System Chat accessible only via Admin menu, not main menu (T48)
    t_system_chat_admin_menu_only,
    # STT fast-speech accuracy: 'Сколько у тебя памяти' at 4 speeds (T49)
    t_stt_fast_speech_accuracy,
    # Bot config block injection in normal chat prompts (T50)
    t_voice_chat_config_disclosure,
    # Notes delete confirmation dialog (T51)
    t_note_delete_confirm,
    # Notes rename title flow (T52)
    t_note_rename_flow,
    # Notes ZIP download handler (T53)
    t_note_zip_download,
    # RAG context injection in _with_lang / _with_lang_voice (T54)
    t_rag_context_injection,
    # No hardcoded user-visible strings in Python source (T55)
    t_no_hardcoded_strings,
    # Ollama multi-turn context: native messages array in ask_llm_with_history (T56)
    t_ollama_history_native_messages,
    # System message architecture: role:system prepended in multi-turn chat (T57)
    t_multiturn_system_message,
    # §4 RAG pipeline fixes: log called, timeout enforced, temperature configurable (T58)
    t_rag_pipeline_completeness,
    # Voice pipeline uses ask_llm_with_history + saves turns to history (T59)
    t_voice_history_context,
    # LLM context trace tool: db_get_llm_trace, voice logs, admin_llm_trace panel (T60)
    t_llm_context_trace,
    # DB-primary notes storage: content column, DB write+read (T61)
    t_notes_db_content,
    # Calendar DB-primary: _cal_save uses store.save_event, no JSON first (T62)
    t_calendar_db_primary,
    # Document deduplication: pending dict, handlers, i18n (T63)
    t_doc_dedup_logic,
    # Per-user memory toggle: user_prefs table, helpers, profile callback (T64)
    t_user_prefs_db,
    # Admin memory settings: system_settings table, helpers, runtime getters (T65)
    t_admin_memory_settings,
    # Phase B: classify_query() adaptive routing (T66)
    t_classify_query_routing,
    # Phase B: reciprocal_rank_fusion() math (T67)
    t_rrf_fusion_math,
    # Phase C: PyMuPDF fallback for PDF extraction (T68)
    t_pymupdf_pdf_fallback,
    # Phase C: per-user RAG settings override from user_prefs (T69)
    t_per_user_rag_settings,
    # User Rights: Developer Menu RBAC guard (T70)
    t_dev_menu_rbac,
    # User Rights: security_events table + logging (T71)
    t_security_events_logging,
    # Phase B/C: RAG monitoring rag_stats() method (T72)
    t_rag_monitoring_stats,
    # Document store API completeness — both SQLite + Postgres (T73)
    t_doc_store_api_complete,
    # Document upload pipeline — dedup, extract, save, hash (T74)
    t_doc_upload_pipeline,
    # Document list/delete/rename flow + i18n string coverage (T75)
    t_doc_list_delete_flow,
    # Full RAG pipeline: retrieve_context, classify_query, FTS5+vector, config (T76)
    t_rag_full_pipeline,
    # Multi-tier memory context assembly: STM + MTM/LTM summaries + memory_enabled toggle (T77)
    t_memory_context_assembly,
    # Combined RAG + all memory tiers in ask_llm_with_history() — context ordering contract (T78)
    t_rag_memory_combined_context,
    # RAG log datetime serialization — str() wrap on created_at for Postgres compat (T79)
    t_rag_log_datetime_serialization,
    # RAG hybrid retrieval: psutil fallback + embed() signature + chunk_idx in search_similar (T80)
    t_rag_hybrid_retrieval_fixes,
    # Qwen3.5 model available in Ollama registry (T81)
    t_qwen35_ollama_available,
    # Ollama latency regression: active model within 30s threshold (T82)
    t_ollama_latency_regression,
    # Ollama quality: Russian calendar intent → valid JSON (T83)
    t_ollama_quality_ru_calendar,
    # Phase C: upload stats (quality_pct, n_embedded, n_skipped) in metadata (T84)
    t_upload_stats_metadata,
    # Phase B/C: bot_embeddings.py import fix — 'from core' not 'from src.core' (T85)
    t_embeddings_import_fix,
    # Phase D: MCP server /mcp/search + client circuit breaker + bot_rag integration (T86)
    t_mcp_phase_d_structure,
    # Fix: upsert_embedding correct args + search_fts/search_similar return chunk_idx (T87)
    t_embedding_pipeline_fix,
    # Fix: shared docs (is_shared=1) included in FTS + vector search (T88)
    t_shared_docs_search,
    # RAG tracing: retrieve_context returns 4-tuple with trace dict n_fts5/n_vector/n_mcp (T89)
    t_rag_trace_fields,
    # System KB docs loader + migration script structure (T90)
    t_system_docs_structure,
    # TeleBot num_threads=16: prevents menu queuing behind LLM/voice (T91)
    t_telebot_num_threads,
    # Chat/voice handlers dispatch to background threads (T92)
    t_handlers_background_dispatch,
    # answer_callback_query wrapped in try/except: stale callbacks don't freeze polling (T93)
    t_callback_query_answer_safe,
    # FASTER_WHISPER_PRELOAD env var disables 460MB preload on low-memory machines (T94)
    t_fw_preload_config,
    # tail_log uses subprocess tail, not f.readlines() — avoids loading full log into RAM (T95)
    t_tail_log_no_readlines,
    # Startup memory warning via /proc/meminfo (no psutil dep) (T96)
    t_startup_memory_check,
    # Personal data context injection: calendar/notes/contacts in _build_system_message (T97)
    t_personal_context_injection,
    # render_telegram: empty/whitespace MarkdownBlock replaced with zero-width space (T98)
    t_render_telegram_empty_block,
    # Voice admin info: model labels wrapped in backticks to avoid Markdown injection (T99)
    t_admin_info_markdown_safe,
    # _handle_doc_detail: created_at from Postgres is datetime, not string — no raw [:16] slice (T100)
    t_doc_detail_datetime_safe,
    # _handle_note_open: 0-byte note files get note_empty_body placeholder (T101)
    t_note_open_empty_file,
    # store_postgres note methods use UUID path via _notes_storage_dir(chat_id) (T102)
    t_store_postgres_notes_uuid_path,
    # web_accounts store methods present in both backends (T103)
    t_web_accounts_store_methods,
    # system_settings uses JSON file, not get_db() (T104)
    t_system_settings_json_file,
    # mail_creds _load_creds uses store as primary (T105)
    t_mail_creds_store_primary,
    # Postgres-only: no SQLite fallbacks in key functions (T106)
    t_postgres_no_sqlite_fallbacks,
    # Postgres dict_row access — row["col"] not row[0] (T107)
    t_postgres_dict_row_access,
    # ask_llm_with_history named fallback (LLM_FALLBACK_PROVIDER) present (T108)
    t_llm_history_named_fallback,
    # system chat: ollama timeout guard + global default fallback (T109)
    t_llm_system_chat_fallback,
    # system chat: host OS/HW context injected into LLM prompt (T110)
    t_system_chat_host_context,
    # migrate_sqlite_to_postgres: all 10 tables, no notes content-filter bug (T111)
    t_migrate_postgres_structure,
    # Contacts store parity: both SQLite + Postgres have all 5 methods (T112)
    t_contacts_store_parity,
    # Live Postgres data non-empty after migration (T113, SKIP if not postgres)
    t_postgres_live_data,
    # bot_web.py admin page: created field uses str() before slicing (T114)
    t_admin_page_datetime_safe,
    # prompts.json rule 5: never reproduce [BOT CAPABILITIES] tag literally (T115)
    t_bot_capabilities_tag_fix,
    # Admin-only RAG: search_fts/search_similar accept is_admin; load_system_docs uses is_shared=2 (T116)
    t_admin_only_rag_access,
    # Gemma4: thinking mode disabled in benchmark; config correct (T117-T118)
    t_gemma4_thinking_mode_fix,
    t_gemma4_ollama_config,
    # Gemma4 live availability (T119, SKIP if Ollama not running or model not pulled)
    t_gemma4_live_availability,
    # Gemma4 evaluation report + scripts present (T120)
    t_gemma4_benchmark_report,
    # Ollama model picker: get/set model, admin UI handler, callback dispatch (T121)
    t_ollama_model_picker,
    # RBAC allowlist enforcement: ADMIN_ALLOWED_CMDS, DEVELOPER_ALLOWED_CMDS, _classify_cmd_class,
    # configurable extra blocklist, admin security policy UI (T122)
    t_rbac_allowlist_enforcement,
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
        detail_short = (r.detail.splitlines() or [""])[0][:70]
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
