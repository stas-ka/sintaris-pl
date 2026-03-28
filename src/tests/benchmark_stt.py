#!/usr/bin/env python3
"""
benchmark_stt.py — STT benchmark: Vosk vs faster-whisper
=========================================================
Measures WER, RTF (Real-Time Factor), and latency for both STT engines
on the local machine. Designed for OpenClaw (laptop/PC) variant.

Usage:
    python3 src/tests/benchmark_stt.py [--audio <path.ogg>] [--text "ground truth"]
    python3 src/tests/benchmark_stt.py --all               # run all fixture files
    python3 src/tests/benchmark_stt.py --model small        # test fw model size

Environment:
    VOSK_MODEL_PATH       — path to Vosk model dir
    FASTER_WHISPER_MODEL  — faster-whisper model size (tiny/base/small)
    FASTER_WHISPER_DEVICE — cpu / cuda
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TARIS_HOME     = os.environ.get("TARIS_HOME", os.path.expanduser("~/.taris"))
VOSK_MODEL     = os.environ.get("VOSK_MODEL_PATH", f"{TARIS_HOME}/vosk-model-small-ru")
FW_MODEL       = os.environ.get("FASTER_WHISPER_MODEL", "base")
FW_DEVICE      = os.environ.get("FASTER_WHISPER_DEVICE", "cpu")
FW_COMPUTE     = os.environ.get("FASTER_WHISPER_COMPUTE", "int8")
VOICE_TEST_DIR = Path(__file__).parent / "voice"
GROUND_TRUTH   = VOICE_TEST_DIR / "ground_truth.json"

SAMPLE_RATE = 16000


def _ogg_to_pcm(ogg_path: str) -> tuple[bytes, float]:
    """Convert OGG/Opus to 16-bit LE PCM at 16kHz.  Returns (pcm_bytes, duration_s)."""
    cmd = [
        "ffmpeg", "-y", "-i", ogg_path,
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "s16le",
        "-loglevel", "error", "-",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:200]}")
    pcm = result.stdout
    duration = len(pcm) / (SAMPLE_RATE * 2)
    return pcm, duration


def _wer(ref: str, hyp: str) -> float:
    """Word Error Rate: (S+D+I) / len(ref_words).  Returns 0.0–1.0."""
    ref_w = ref.lower().split()
    hyp_w = hyp.lower().split()
    if not ref_w:
        return 0.0 if not hyp_w else 1.0
    # Simple DP WER
    n, m = len(ref_w), len(hyp_w)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1): dp[i][0] = i
    for j in range(m + 1): dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = dp[i-1][j-1] if ref_w[i-1] == hyp_w[j-1] else \
                       1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    return dp[n][m] / n


def benchmark_vosk(pcm: bytes, duration: float, lang: str = "ru") -> dict:
    """Run Vosk STT on PCM, return result dict with transcript, latency, RTF."""
    try:
        import vosk
        import json as _json
        vosk.SetLogLevel(-1)

        t0 = time.time()
        model = vosk.Model(VOSK_MODEL)
        model_load_t = time.time() - t0

        t1 = time.time()
        rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)
        rec.SetWords(True)
        chunk = 4000 * 2
        for i in range(0, len(pcm), chunk):
            rec.AcceptWaveform(pcm[i:i + chunk])
        result = _json.loads(rec.FinalResult())
        transcribe_t = time.time() - t1
        text = " ".join(w["word"] for w in result.get("result", []) if w.get("conf", 1.0) >= 0.5)

        return {
            "engine": f"vosk ({Path(VOSK_MODEL).name})",
            "text": text,
            "latency_s": round(transcribe_t, 3),
            "model_load_s": round(model_load_t, 3),
            "rtf": round(transcribe_t / duration, 3) if duration > 0 else 0,
            "ok": True,
        }
    except ImportError:
        return {"engine": "vosk", "ok": False, "error": "vosk not installed"}
    except Exception as e:
        return {"engine": "vosk", "ok": False, "error": str(e)}


def benchmark_faster_whisper(pcm: bytes, duration: float, model_size: str = FW_MODEL, lang: str = "ru") -> dict:
    """Run faster-whisper on PCM, return result dict."""
    try:
        import numpy as np
        from faster_whisper import WhisperModel

        audio_np = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        t0 = time.time()
        model = WhisperModel(model_size, device=FW_DEVICE, compute_type=FW_COMPUTE)
        model_load_t = time.time() - t0

        t1 = time.time()
        segments, info = model.transcribe(
            audio_np, language=lang, beam_size=5,
            vad_filter=True, condition_on_previous_text=False,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        transcribe_t = time.time() - t1

        return {
            "engine": f"faster-whisper {model_size} ({FW_DEVICE}/{FW_COMPUTE})",
            "text": text,
            "latency_s": round(transcribe_t, 3),
            "model_load_s": round(model_load_t, 3),
            "rtf": round(transcribe_t / duration, 3) if duration > 0 else 0,
            "detected_lang": info.language,
            "lang_prob": round(info.language_probability, 3),
            "ok": True,
        }
    except ImportError:
        return {"engine": f"faster-whisper {model_size}", "ok": False,
                "error": "faster-whisper not installed (pip install faster-whisper)"}
    except Exception as e:
        return {"engine": f"faster-whisper {model_size}", "ok": False, "error": str(e)}


def run_benchmark(audio_file: str, ref_text: str = "", fw_models: list = None) -> None:
    if fw_models is None:
        fw_models = [FW_MODEL]

    print(f"\n{'='*65}")
    print(f"Audio: {os.path.basename(audio_file)}")
    print(f"Ref:   {ref_text or '(no reference)'}")
    print(f"{'='*65}")

    pcm, duration = _ogg_to_pcm(audio_file)
    print(f"Duration: {duration:.2f}s  |  PCM: {len(pcm)//1024} KB")

    results = []

    # Vosk
    r = benchmark_vosk(pcm, duration)
    results.append(r)

    # faster-whisper (one or more model sizes)
    for model_size in fw_models:
        r = benchmark_faster_whisper(pcm, duration, model_size)
        results.append(r)

    # Print table
    print(f"\n{'Engine':<45} {'Text (truncated)':<30} {'Latency':>8} {'RTF':>6} {'WER':>6}")
    print("-" * 100)
    for r in results:
        if not r["ok"]:
            print(f"  {r['engine']:<43} ERROR: {r.get('error','')[:50]}")
            continue
        text_show = r["text"][:28] + ".." if len(r["text"]) > 30 else r["text"]
        wer = _wer(ref_text, r["text"]) if ref_text else "-"
        wer_str = f"{wer:.1%}" if isinstance(wer, float) else wer
        print(f"  {r['engine']:<43} {text_show:<30} {r['latency_s']:>7.3f}s {r['rtf']:>6.3f} {wer_str:>6}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="STT benchmark: Vosk vs faster-whisper")
    parser.add_argument("--audio", help="Path to OGG audio file")
    parser.add_argument("--text",  help="Reference text (ground truth) for WER")
    parser.add_argument("--all",   action="store_true", help="Run all voice fixtures")
    parser.add_argument("--model", nargs="+", default=[FW_MODEL],
                        help="faster-whisper model sizes to benchmark (e.g. tiny base small)")
    args = parser.parse_args()

    print("\n🎙  STT Benchmark — Vosk vs faster-whisper")
    print(f"   Vosk:          {Path(VOSK_MODEL).name}")
    print(f"   faster-whisper: {', '.join(args.model)} ({FW_DEVICE}/{FW_COMPUTE})")

    if args.all and GROUND_TRUTH.exists():
        gt = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
        audio_dir = VOICE_TEST_DIR
        files_run = 0
        for fname, ref_text in gt.items():
            ogg = audio_dir / fname
            if ogg.exists():
                run_benchmark(str(ogg), ref_text, fw_models=args.model)
                files_run += 1
        if files_run == 0:
            print(f"[WARN] No OGG fixture files found in {audio_dir}")
    elif args.audio:
        run_benchmark(args.audio, args.text or "", fw_models=args.model)
    else:
        # Synthetic test: create a short silent WAV for smoke test
        print("\n[INFO] No audio file specified — running latency-only test (silent audio)")
        import numpy as np
        pcm = (np.zeros(SAMPLE_RATE * 2, dtype=np.int16)).tobytes()  # 2s silence
        print(f"\n{'Engine':<45} {'Text':<30} {'Latency':>8} {'RTF':>6}")
        print("-" * 95)
        for r in [benchmark_vosk(pcm, 2.0), *[benchmark_faster_whisper(pcm, 2.0, m) for m in args.model]]:
            if r["ok"]:
                print(f"  {r['engine']:<43} {r['text'][:28]:<30} {r['latency_s']:>7.3f}s {r['rtf']:>6.3f}")
            else:
                print(f"  {r['engine']:<43} ERROR: {r.get('error','')[:50]}")
        print("\n[TIP] Run with real audio: python3 src/tests/benchmark_stt.py --audio test.ogg --text 'привет пико'")


if __name__ == "__main__":
    main()
