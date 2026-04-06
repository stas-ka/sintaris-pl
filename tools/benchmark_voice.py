#!/usr/bin/env python3
"""
benchmark_voice.py — Comprehensive voice pipeline benchmark
===========================================================
Measures STT (Vosk / faster-whisper multiple sizes), TTS (Piper),
and LLM (Ollama) latency and quality on any taris-openclaw target.

Usage:
    # Run locally (TariStation2):
    python3 tools/benchmark_voice.py

    # Run with specific options:
    python3 tools/benchmark_voice.py --target ts2 --stt-models tiny base small
    python3 tools/benchmark_voice.py --target sintaition --ollama-models qwen2:0.5b qwen3:14b
    python3 tools/benchmark_voice.py --output results/ts2.json

    # Compare results from multiple targets:
    python3 tools/benchmark_voice.py --compare results/ts2.json results/sintaition.json

Output: JSON + human-readable table to stdout. Results appended to --output file.

Environment (auto-detected from ~/.taris/bot.env if present):
    TARIS_DIR              — ~/.taris
    PIPER_BIN              — path to piper binary
    PIPER_MODEL            — path to .onnx model
    FASTER_WHISPER_DEVICE  — cpu / cuda
    FASTER_WHISPER_COMPUTE — int8 / float16
    OLLAMA_URL             — http://127.0.0.1:11434
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Auto-load bot.env if present
# ─────────────────────────────────────────────────────────────────────────────
_taris_dir = Path(os.environ.get("TARIS_DIR", Path.home() / ".taris"))
_bot_env = _taris_dir / "bot.env"
if _bot_env.exists():
    for _line in _bot_env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

TARIS_DIR    = _taris_dir
PIPER_BIN    = os.environ.get("PIPER_BIN", str(TARIS_DIR / "piper/piper"))
PIPER_MODEL  = os.environ.get("PIPER_MODEL", str(TARIS_DIR / "ru_RU-irina-medium.onnx"))
FW_DEVICE    = os.environ.get("FASTER_WHISPER_DEVICE", "cpu")
FW_COMPUTE   = os.environ.get("FASTER_WHISPER_COMPUTE", "int8")
OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
SAMPLE_RATE  = 16000

# ─────────────────────────────────────────────────────────────────────────────
# Test corpus
# ─────────────────────────────────────────────────────────────────────────────
TTS_TEXTS = {
    "short_ru":  "Привет! Как дела? Что нового?",
    "medium_ru": (
        "Напомни мне завтра в девять утра о встрече с врачом. "
        "Также добавь в список покупок молоко, хлеб и яблоки."
    ),
    "long_ru": (
        "Расскажи мне о погоде на следующей неделе. Я планирую поездку за город "
        "и хочу знать, стоит ли брать зонт или тёплую куртку. "
        "Также узнай, какие достопримечательности есть поблизости и как до них добраться."
    ),
    "short_de":  "Hallo! Wie geht es dir?",
    "short_en":  "Hello! What is the weather like today?",
}

LLM_PROMPTS = {
    "factual_short": "Сколько планет в солнечной системе? Ответь одним словом.",
    "factual_medium": "Объясни кратко (2-3 предложения) как работает нейронная сеть.",
    "creative": (
        "Напиши короткое (3-4 предложения) стихотворение о весне на русском языке."
    ),
    "command_like": "Добавь напоминание: позвонить маме в 18:00.",
}

STT_REF_TEXTS = {
    "short_ru": "привет как дела что нового",
    "medium_ru": (
        "напомни мне завтра в девять утра о встрече с врачом "
        "также добавь в список покупок молоко хлеб и яблоки"
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────
def _wer(ref: str, hyp: str) -> float:
    """Word Error Rate (0.0–1.0)."""
    ref_w = ref.lower().split()
    hyp_w = hyp.lower().split()
    if not ref_w:
        return 0.0 if not hyp_w else 1.0
    n, m = len(ref_w), len(hyp_w)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = (dp[i - 1][j - 1] if ref_w[i - 1] == hyp_w[j - 1]
                        else 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]))
    return dp[n][m] / n


def _sys_info() -> dict:
    cpu = ""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    cpu = line.split(":", 1)[1].strip()
                    break
    except Exception:
        cpu = platform.processor()
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    mem_kb = int(line.split()[1])
                    mem_gb = round(mem_kb / 1024 / 1024, 1)
                    break
    except Exception:
        mem_gb = 0
    return {
        "hostname": platform.node(),
        "cpu": cpu,
        "ram_gb": mem_gb,
        "python": platform.python_version(),
        "arch": platform.machine(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TTS Benchmark
# ─────────────────────────────────────────────────────────────────────────────
def _pcm_to_ogg(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Encode raw PCM to OGG/Opus via ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
        "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1",
        "-loglevel", "error",
    ]
    r = subprocess.run(cmd, input=pcm_bytes, capture_output=True, timeout=30)
    return r.stdout if r.returncode == 0 else b""


def _ogg_to_pcm(ogg_bytes: bytes) -> tuple[bytes, float]:
    """Decode OGG/Opus to 16-bit LE PCM at 16kHz. Returns (pcm, duration_s)."""
    cmd = [
        "ffmpeg", "-y", "-i", "pipe:0",
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "s16le", "pipe:1",
        "-loglevel", "error",
    ]
    r = subprocess.run(cmd, input=ogg_bytes, capture_output=True, timeout=30)
    pcm = r.stdout
    duration = len(pcm) / (SAMPLE_RATE * 2) if pcm else 0.0
    return pcm, duration


def benchmark_tts(texts: dict = None) -> list[dict]:
    """Benchmark Piper TTS for multiple text lengths."""
    if texts is None:
        texts = TTS_TEXTS
    results = []

    piper_ok = Path(PIPER_BIN).exists()
    if not piper_ok:
        return [{"suite": "tts", "ok": False, "error": f"piper binary not found: {PIPER_BIN}"}]

    model_ok = Path(PIPER_MODEL).exists()
    model_json = PIPER_MODEL + ".json"
    if not model_ok:
        return [{"suite": "tts", "ok": False, "error": f"piper model not found: {PIPER_MODEL}"}]

    for label, text in texts.items():
        lang = label.split("_")[-1] if "_" in label else "ru"
        model = PIPER_MODEL
        if lang == "de":
            de_model = str(TARIS_DIR / "de_DE-thorsten-medium.onnx")
            if Path(de_model).exists():
                model = de_model
        if lang == "en":
            en_model = str(TARIS_DIR / "en_US-ljspeech-medium.onnx")
            if Path(en_model).exists():
                model = en_model

        cmd = [PIPER_BIN, "--model", model, "--output_raw", "--quiet"]
        t0 = time.time()
        try:
            r = subprocess.run(cmd, input=text.encode("utf-8"),
                               capture_output=True, timeout=120)
            latency = time.time() - t0
            pcm = r.stdout
            if not pcm or r.returncode != 0:
                results.append({"suite": "tts", "label": label, "ok": False,
                                "error": r.stderr.decode(errors="ignore")[:120]})
                continue
            chars = len(text)
            words = len(text.split())
            duration = len(pcm) / (SAMPLE_RATE * 2)
            results.append({
                "suite": "tts",
                "label": label,
                "ok": True,
                "chars": chars,
                "words": words,
                "latency_s": round(latency, 3),
                "audio_duration_s": round(duration, 3),
                "rtf": round(latency / duration, 3) if duration > 0 else 0,
                "ms_per_char": round(latency * 1000 / chars, 1) if chars > 0 else 0,
                "model": Path(model).name,
            })
        except subprocess.TimeoutExpired:
            results.append({"suite": "tts", "label": label, "ok": False,
                            "error": "piper timeout 120s"})
        except Exception as e:
            results.append({"suite": "tts", "label": label, "ok": False, "error": str(e)})

    return results


# ─────────────────────────────────────────────────────────────────────────────
# STT Benchmark
# ─────────────────────────────────────────────────────────────────────────────
def _tts_to_pcm(text: str) -> Optional[bytes]:
    """Generate PCM audio from text using Piper (for STT fixture)."""
    if not Path(PIPER_BIN).exists() or not Path(PIPER_MODEL).exists():
        return None
    cmd = [PIPER_BIN, "--model", PIPER_MODEL, "--output_raw", "--quiet"]
    try:
        r = subprocess.run(cmd, input=text.encode("utf-8"),
                           capture_output=True, timeout=60)
        return r.stdout if r.returncode == 0 and r.stdout else None
    except Exception:
        return None


def benchmark_stt_fw(model_size: str, pcm: bytes, duration: float,
                     ref_text: str = "", lang: str = "ru") -> dict:
    """Benchmark faster-whisper with given model size."""
    try:
        import numpy as np
        from faster_whisper import WhisperModel

        audio_np = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        t_load = time.time()
        model = WhisperModel(model_size, device=FW_DEVICE, compute_type=FW_COMPUTE)
        load_t = time.time() - t_load

        t1 = time.time()
        segs, info = model.transcribe(
            audio_np, language=lang, beam_size=5,
            vad_filter=True, condition_on_previous_text=False,
        )
        text = " ".join(seg.text.strip() for seg in segs).strip()
        transcribe_t = time.time() - t1

        wer = _wer(ref_text, text) if ref_text else None
        return {
            "suite": "stt",
            "engine": "faster-whisper",
            "model": model_size,
            "device": FW_DEVICE,
            "compute": FW_COMPUTE,
            "text": text,
            "ref_text": ref_text,
            "wer": round(wer, 3) if wer is not None else None,
            "latency_s": round(transcribe_t, 3),
            "model_load_s": round(load_t, 3),
            "audio_duration_s": round(duration, 3),
            "rtf": round(transcribe_t / duration, 3) if duration > 0 else 0,
            "detected_lang": info.language,
            "lang_prob": round(info.language_probability, 3),
            "ok": True,
        }
    except ImportError:
        return {"suite": "stt", "engine": "faster-whisper", "model": model_size,
                "ok": False, "error": "faster-whisper not installed (pip install faster-whisper)"}
    except Exception as e:
        return {"suite": "stt", "engine": "faster-whisper", "model": model_size,
                "ok": False, "error": str(e)[:200]}


def benchmark_stt_vosk(pcm: bytes, duration: float,
                       ref_text: str = "", lang: str = "ru") -> dict:
    """Benchmark Vosk STT."""
    vosk_model_path = os.environ.get("VOSK_MODEL_PATH",
                                     str(TARIS_DIR / "vosk-model-small-ru"))
    try:
        import vosk
        import json as _json
        vosk.SetLogLevel(-1)

        if not Path(vosk_model_path).exists():
            return {"suite": "stt", "engine": "vosk", "ok": False,
                    "error": f"model not found: {vosk_model_path}"}

        t0 = time.time()
        model = vosk.Model(vosk_model_path)
        load_t = time.time() - t0

        rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)
        rec.SetWords(True)
        t1 = time.time()
        chunk = 4000
        for i in range(0, len(pcm), chunk):
            rec.AcceptWaveform(pcm[i:i + chunk])
        final = _json.loads(rec.FinalResult())
        text = final.get("text", "").strip()
        transcribe_t = time.time() - t1

        wer = _wer(ref_text, text) if ref_text else None
        return {
            "suite": "stt",
            "engine": "vosk",
            "model": Path(vosk_model_path).name,
            "text": text,
            "ref_text": ref_text,
            "wer": round(wer, 3) if wer is not None else None,
            "latency_s": round(transcribe_t, 3),
            "model_load_s": round(load_t, 3),
            "audio_duration_s": round(duration, 3),
            "rtf": round(transcribe_t / duration, 3) if duration > 0 else 0,
            "ok": True,
        }
    except ImportError:
        return {"suite": "stt", "engine": "vosk", "ok": False,
                "error": "vosk not installed"}
    except Exception as e:
        return {"suite": "stt", "engine": "vosk", "ok": False, "error": str(e)[:200]}


def benchmark_stt(fw_models: list = None) -> list[dict]:
    """Generate TTS audio fixtures and benchmark all STT engines."""
    if fw_models is None:
        fw_models = ["tiny", "base", "small"]

    results = []
    test_cases = [
        ("short_ru", TTS_TEXTS["short_ru"], STT_REF_TEXTS["short_ru"], "ru"),
        ("medium_ru", TTS_TEXTS["medium_ru"], STT_REF_TEXTS["medium_ru"], "ru"),
    ]

    for label, tts_text, ref_text, lang in test_cases:
        print(f"  Generating TTS fixture: {label}...", end=" ", flush=True)
        pcm = _tts_to_pcm(tts_text)
        if pcm is None:
            print("SKIP (piper unavailable)")
            results.append({"suite": "stt", "label": label, "ok": False,
                            "error": "TTS fixture unavailable (piper missing)"})
            continue
        duration = len(pcm) / (SAMPLE_RATE * 2)
        print(f"{duration:.1f}s audio generated")

        # Test Vosk
        print(f"    Vosk...", end=" ", flush=True)
        r = benchmark_stt_vosk(pcm, duration, ref_text, lang)
        r["label"] = label
        results.append(r)
        if r["ok"]:
            wer_str = f"WER={r['wer']:.0%}" if r.get("wer") is not None else ""
            print(f"{r['latency_s']:.2f}s RTF={r['rtf']:.2f} {wer_str}")
        else:
            print(f"SKIP: {r['error'][:60]}")

        # Test faster-whisper models
        for model_size in fw_models:
            print(f"    fw/{model_size}...", end=" ", flush=True)
            r = benchmark_stt_fw(model_size, pcm, duration, ref_text, lang)
            r["label"] = label
            results.append(r)
            if r["ok"]:
                wer_str = f"WER={r['wer']:.0%}" if r.get("wer") is not None else ""
                print(f"{r['latency_s']:.2f}s RTF={r['rtf']:.2f} {wer_str} (load={r['model_load_s']:.1f}s)")
            else:
                print(f"SKIP: {r['error'][:60]}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# STT Speed-Sensitivity Benchmark
# ─────────────────────────────────────────────────────────────────────────────
_SPEED_PHRASES = [
    ("memory_query_ru", "Сколько у тебя памяти",   "сколько у тебя памяти",   "ru"),
    ("greeting_ru",     "Привет, как дела",          "привет как дела",         "ru"),
    ("command_ru",      "Добавь напоминание на завтра", "добавь напоминание на завтра", "ru"),
]

_SPEEDS = [
    (0.60, "slow_0.6x"),
    (0.80, "slow_0.8x"),
    (1.00, "normal_1.0x"),
    (1.40, "fast_1.4x"),
    (1.80, "fast_1.8x"),
]


def _apply_speed_to_pcm(pcm_22k: bytes, speed: float) -> tuple[bytes, float]:
    """Apply atempo speed change and resample to 16kHz PCM. Returns (pcm16k, duration_s)."""
    if speed <= 0.5:
        atempo = f"atempo=0.5,atempo={speed / 0.5:.3f}"
    elif speed >= 2.0:
        atempo = f"atempo=2.0,atempo={speed / 2.0:.3f}"
    else:
        atempo = f"atempo={speed:.3f}"

    cmd = [
        "ffmpeg", "-y",
        "-f", "s16le", "-ar", "22050", "-ac", "1", "-i", "pipe:0",
        "-af", atempo,
        "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1",
        "-loglevel", "error",
    ]
    r = subprocess.run(cmd, input=pcm_22k, capture_output=True, timeout=30)
    pcm = r.stdout
    return pcm, len(pcm) / (SAMPLE_RATE * 2) if pcm else (b"", 0.0)


def benchmark_stt_speed_sensitivity(fw_models: list = None) -> list[dict]:
    """Benchmark STT accuracy across speech speeds for known-problematic phrases.

    Tests the regression identified 2026-03-29: faster-whisper 'base' model
    fails on fast Russian speech (<1.5s audio). Measures WER per model/speed combo.

    Test phrase: 'Сколько у тебя памяти' — the exact phrase that triggered the bug.
    """
    if fw_models is None:
        fw_models = ["base", "small"]

    results = []
    piper_ok = Path(PIPER_BIN).exists() and Path(PIPER_MODEL).exists()
    if not piper_ok:
        print("  SKIP: Piper not available — cannot generate audio fixtures")
        return [{"suite": "stt_speed", "ok": False,
                 "error": f"Piper not found ({PIPER_BIN})"}]

    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError:
        print("  SKIP: faster-whisper not installed")
        return [{"suite": "stt_speed", "ok": False,
                 "error": "faster-whisper not installed (pip install faster-whisper)"}]

    # Pre-load models (avoid reload per phrase)
    loaded_models: dict = {}
    fw_threads = int(os.environ.get("FASTER_WHISPER_THREADS", "0")) or min(4, os.cpu_count() or 4)
    for ms in fw_models:
        try:
            print(f"  Loading fw/{ms}...", end=" ", flush=True)
            loaded_models[ms] = WhisperModel(ms, device=FW_DEVICE, compute_type=FW_COMPUTE,
                                             cpu_threads=fw_threads)
            print("OK")
        except Exception as e:
            print(f"FAIL ({e})")

    for phrase_label, phrase_text, ref_text, lang in _SPEED_PHRASES:
        # Generate base TTS audio at natural speed (22050 Hz raw PCM)
        print(f"\n  Phrase: '{phrase_text}'")
        piper_cmd = [PIPER_BIN, "--model", PIPER_MODEL, "--output-raw"]
        r = subprocess.run(piper_cmd, input=phrase_text.encode("utf-8"),
                           capture_output=True, timeout=30)
        if r.returncode != 0 or not r.stdout:
            print(f"  SKIP: Piper failed for '{phrase_text}'")
            continue
        pcm_22k = r.stdout
        natural_dur = len(pcm_22k) / (22050 * 2)
        print(f"  TTS generated: {natural_dur:.2f}s at natural speed")

        print(f"  {'Speed':<14} {'Dur':>6} {'RTF':>6} {'WER':>6}  {'Transcript':<40}")
        print(f"  {'-'*14} {'-'*6} {'-'*6} {'-'*6}  {'-'*40}")

        for speed, speed_label in _SPEEDS:
            pcm16k, dur = _apply_speed_to_pcm(pcm_22k, speed)
            if not pcm16k:
                print(f"  {speed_label:<14}  ffmpeg error")
                continue

            audio_np = np.frombuffer(pcm16k, dtype=np.int16).astype(np.float32) / 32768.0

            for ms, fw_model in loaded_models.items():
                try:
                    t1 = time.time()
                    segs, info = fw_model.transcribe(
                        audio_np, language=lang, beam_size=5,
                        vad_filter=True, condition_on_previous_text=False,
                    )
                    transcript = " ".join(seg.text.strip() for seg in segs).strip()
                    inf_t = time.time() - t1

                    # Retry without VAD for short clips
                    if not transcript:
                        segs2, _ = fw_model.transcribe(
                            audio_np, language=lang, beam_size=5,
                            vad_filter=False, condition_on_previous_text=False,
                        )
                        transcript = " ".join(seg.text.strip() for seg in segs2).strip()

                    wer = _wer(ref_text, transcript.lower()) if transcript else 1.0
                    rtf = inf_t / dur if dur > 0 else 0
                    ok = wer <= 0.35

                    row_label = f"{speed_label}/{ms}"
                    trunc = transcript[:38] + ".." if len(transcript) > 38 else transcript
                    flag = "✓" if ok else "✗"
                    print(f"  {row_label:<14} {dur:>6.2f}s {rtf:>5.2f}x {wer:>5.0%}  "
                          f"{flag} '{trunc}'")

                    results.append({
                        "suite": "stt_speed",
                        "phrase": phrase_label,
                        "speed": speed,
                        "speed_label": speed_label,
                        "model": ms,
                        "transcript": transcript,
                        "ref_text": ref_text,
                        "wer": round(wer, 3),
                        "latency_s": round(inf_t, 3),
                        "audio_duration_s": round(dur, 3),
                        "rtf": round(rtf, 3),
                        "ok": ok,
                    })
                except Exception as e:
                    print(f"  {speed_label}/{ms}: ERROR {e}")
                    results.append({"suite": "stt_speed", "phrase": phrase_label,
                                    "speed": speed, "model": ms, "ok": False, "error": str(e)})

    return results



def benchmark_llm(ollama_models: list = None, n_repeats: int = 2) -> list[dict]:
    """Benchmark Ollama LLM with different models and prompts."""
    if ollama_models is None:
        ollama_models = [os.environ.get("OLLAMA_MODEL", "qwen2:0.5b")]

    results = []

    for model in ollama_models:
        for prompt_label, prompt in LLM_PROMPTS.items():
            timings = []
            chars_list = []
            last_response = ""

            for _ in range(n_repeats):
                t0 = time.time()
                try:
                    import urllib.request, json as _json
                    payload = json.dumps({
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": 200, "temperature": 0.3},
                    }).encode()
                    req = urllib.request.Request(
                        f"{OLLAMA_URL}/api/generate",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        data = _json.loads(resp.read())
                    latency = time.time() - t0
                    last_response = data.get("response", "").strip()
                    timings.append(latency)
                    chars_list.append(len(last_response))
                except Exception as e:
                    results.append({
                        "suite": "llm", "model": model, "prompt": prompt_label,
                        "ok": False, "error": str(e)[:200],
                    })
                    break
            else:
                avg_latency = sum(timings) / len(timings)
                avg_chars = sum(chars_list) / len(chars_list)
                results.append({
                    "suite": "llm",
                    "model": model,
                    "prompt": prompt_label,
                    "prompt_text": prompt[:80],
                    "response_preview": last_response[:100],
                    "latency_s": round(avg_latency, 3),
                    "response_chars": round(avg_chars),
                    "chars_per_sec": round(avg_chars / avg_latency, 1) if avg_latency > 0 else 0,
                    "n_repeats": n_repeats,
                    "ok": True,
                })
                print(f"    [{model}] {prompt_label}: {avg_latency:.2f}s "
                      f"({round(avg_chars)} chars, {round(avg_chars/avg_latency,0):.0f} c/s)")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Benchmark (end-to-end)
# ─────────────────────────────────────────────────────────────────────────────
def benchmark_pipeline(fw_model: str = "small", ollama_model: str = None) -> dict:
    """Measure end-to-end: TTS→PCM→STT→LLM→TTS latency."""
    if ollama_model is None:
        ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2:0.5b")

    query_text = TTS_TEXTS["short_ru"]
    ref_text = STT_REF_TEXTS["short_ru"]
    result = {"suite": "pipeline", "fw_model": fw_model, "llm_model": ollama_model}

    t_pipe_start = time.time()

    # Step 1: generate PCM (simulate user speaking)
    t0 = time.time()
    pcm = _tts_to_pcm(query_text)
    if pcm is None:
        result["ok"] = False
        result["error"] = "TTS fixture unavailable"
        return result
    duration = len(pcm) / (SAMPLE_RATE * 2)
    result["fixture_s"] = round(time.time() - t0, 3)

    # Step 2: STT
    t0 = time.time()
    stt_r = benchmark_stt_fw(fw_model, pcm, duration, ref_text)
    result["stt_s"] = round(time.time() - t0, 3)
    result["stt_ok"] = stt_r["ok"]
    result["stt_text"] = stt_r.get("text", "")

    if not stt_r["ok"]:
        result["ok"] = False
        result["error"] = f"STT failed: {stt_r.get('error')}"
        return result

    # Step 3: LLM
    t0 = time.time()
    llm_r = benchmark_llm([ollama_model], n_repeats=1)
    result["llm_s"] = round(time.time() - t0, 3)
    result["llm_ok"] = bool(llm_r and llm_r[0].get("ok"))

    # Step 4: TTS response
    t0 = time.time()
    resp_text = "Хорошо, понял. Есть восемь планет в солнечной системе."
    tts_r = benchmark_tts({"response": resp_text})
    result["tts_reply_s"] = round(time.time() - t0, 3)
    result["tts_ok"] = bool(tts_r and tts_r[0].get("ok"))

    result["total_s"] = round(time.time() - t_pipe_start, 3)
    result["ok"] = True
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────
def _print_table(headers: list, rows: list, widths: list = None) -> None:
    if widths is None:
        widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
                  for i, h in enumerate(headers)]
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*[str(v) for v in row]))


def print_report(run_result: dict) -> None:
    sysinfo = run_result.get("sysinfo", {})
    print(f"\n{'='*70}")
    print(f"🖥  {sysinfo.get('hostname','?')}  |  {sysinfo.get('cpu','?')[:50]}")
    print(f"   RAM: {sysinfo.get('ram_gb','?')} GB  |  Python {sysinfo.get('python','?')}")
    print(f"   Timestamp: {run_result.get('timestamp','?')}")
    print(f"{'='*70}")

    # TTS
    tts_rows = [r for r in run_result.get("results", []) if r.get("suite") == "tts" and r.get("ok")]
    if tts_rows:
        print(f"\n🔊 TTS (Piper)")
        _print_table(
            ["Label", "Chars", "Latency", "RTF", "ms/char", "Model"],
            [[r["label"], r["chars"], f"{r['latency_s']:.3f}s",
              f"{r['rtf']:.3f}", f"{r['ms_per_char']:.1f}", r["model"]] for r in tts_rows],
            [14, 5, 9, 7, 8, 30],
        )

    # STT
    stt_rows = [r for r in run_result.get("results", []) if r.get("suite") == "stt" and r.get("ok")]
    if stt_rows:
        print(f"\n🎤 STT")
        _print_table(
            ["Engine/Model", "Label", "Latency", "RTF", "WER", "Detected"],
            [[f"{r['engine']}/{r['model']}", r.get('label',''), f"{r['latency_s']:.3f}s",
              f"{r['rtf']:.3f}",
              f"{r['wer']:.0%}" if r.get('wer') is not None else "-",
              r.get('detected_lang', '-')] for r in stt_rows],
            [28, 12, 9, 7, 7, 8],
        )

    # LLM
    llm_rows = [r for r in run_result.get("results", []) if r.get("suite") == "llm" and r.get("ok")]
    if llm_rows:
        print(f"\n🧠 LLM (Ollama)")
        _print_table(
            ["Model", "Prompt", "Latency", "Chars", "c/sec"],
            [[r["model"], r["prompt"], f"{r['latency_s']:.2f}s",
              r["response_chars"], f"{r['chars_per_sec']:.0f}"] for r in llm_rows],
            [20, 20, 9, 7, 7],
        )

    # Pipeline
    pipe = next((r for r in run_result.get("results", []) if r.get("suite") == "pipeline"), None)
    if pipe and pipe.get("ok"):
        print(f"\n⚡ End-to-end pipeline (fw/{pipe['fw_model']} + {pipe['llm_model']})")
        print(f"   STT: {pipe.get('stt_s','?')}s  |  LLM: {pipe.get('llm_s','?')}s  |  "
              f"TTS: {pipe.get('tts_reply_s','?')}s  |  Total: {pipe.get('total_s','?')}s")

    # STT failures (informative)
    stt_fail = [r for r in run_result.get("results", []) if r.get("suite") == "stt" and not r.get("ok")]
    if stt_fail:
        print(f"\n⚠️  STT skipped:")
        for r in stt_fail:
            print(f"   {r.get('engine','?')}/{r.get('model','?')}: {r.get('error','?')[:80]}")


def compare_report(result_files: list[str]) -> None:
    runs = []
    for f in result_files:
        try:
            data = json.loads(Path(f).read_text())
            if isinstance(data, list):
                runs.extend(data)
            else:
                runs.append(data)
        except Exception as e:
            print(f"[WARN] Could not load {f}: {e}")

    if not runs:
        print("No results to compare.")
        return

    print(f"\n{'='*80}")
    print("📊 Cross-target voice pipeline comparison")
    print(f"{'='*80}")

    # TTS comparison: short_ru
    print("\n🔊 TTS latency — short_ru (Piper)")
    rows = []
    for run in runs:
        host = run.get("sysinfo", {}).get("hostname", "?")
        for r in run.get("results", []):
            if r.get("suite") == "tts" and r.get("label") == "short_ru" and r.get("ok"):
                rows.append([host, f"{r['latency_s']:.3f}s", f"{r['rtf']:.3f}", f"{r['ms_per_char']:.1f}"])
    if rows:
        _print_table(["Host", "Latency", "RTF", "ms/char"], rows, [20, 9, 7, 8])

    # STT comparison
    print("\n🎤 STT latency — faster-whisper/small (short_ru)")
    rows = []
    for run in runs:
        host = run.get("sysinfo", {}).get("hostname", "?")
        for r in run.get("results", []):
            if (r.get("suite") == "stt" and r.get("ok") and
                    "small" in str(r.get("model", "")) and r.get("label") == "short_ru"):
                wer_str = f"{r['wer']:.0%}" if r.get("wer") is not None else "-"
                rows.append([host, f"{r['latency_s']:.3f}s", f"{r['rtf']:.3f}", wer_str])
    if rows:
        _print_table(["Host", "Latency", "RTF", "WER"], rows, [20, 9, 7, 7])

    # LLM comparison
    print("\n🧠 LLM latency — qwen2:0.5b / factual_short")
    rows = []
    for run in runs:
        host = run.get("sysinfo", {}).get("hostname", "?")
        for r in run.get("results", []):
            if (r.get("suite") == "llm" and r.get("ok") and
                    "qwen2" in r.get("model", "") and r.get("prompt") == "factual_short"):
                rows.append([host, r["model"], f"{r['latency_s']:.2f}s",
                             f"{r['chars_per_sec']:.0f} c/s"])
    if rows:
        _print_table(["Host", "Model", "Latency", "Speed"], rows, [20, 16, 9, 10])


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Voice pipeline benchmark")
    parser.add_argument("--target", default="local",
                        help="Target label (ts2/sintaition/pi2/local)")
    parser.add_argument("--stt-models", nargs="+", default=["tiny", "base", "small"],
                        dest="stt_models", help="faster-whisper model sizes to test")
    parser.add_argument("--ollama-models", nargs="+", default=None,
                        dest="ollama_models",
                        help="Ollama model tags to benchmark (default: from bot.env)")
    parser.add_argument("--skip-stt", action="store_true", help="Skip STT benchmark")
    parser.add_argument("--skip-tts", action="store_true", help="Skip TTS benchmark")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM benchmark")
    parser.add_argument("--skip-pipeline", action="store_true", help="Skip pipeline benchmark")
    parser.add_argument("--speed-test", action="store_true",
                        help="Run STT speed-sensitivity benchmark (Piper+FW required)")
    parser.add_argument("--output", default=None, help="JSON output file (append)")
    parser.add_argument("--compare", nargs="+", metavar="FILE",
                        help="Compare result JSON files and print table")
    args = parser.parse_args()

    if args.compare:
        compare_report(args.compare)
        return

    print(f"\n🚀 Voice pipeline benchmark — target: {args.target}")
    sysinfo = _sys_info()
    print(f"   {sysinfo['hostname']}  |  {sysinfo['cpu'][:55]}")
    print(f"   RAM: {sysinfo['ram_gb']} GB  |  Python {sysinfo['python']}")

    ollama_models = args.ollama_models or [os.environ.get("OLLAMA_MODEL", "qwen2:0.5b")]

    all_results = []
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    # TTS
    if not args.skip_tts:
        print(f"\n🔊 TTS benchmark (Piper: {Path(PIPER_MODEL).name})")
        r = benchmark_tts()
        all_results.extend(r)

    # STT
    if not args.skip_stt:
        print(f"\n🎤 STT benchmark — models: {', '.join(args.stt_models)}")
        r = benchmark_stt(args.stt_models)
        all_results.extend(r)

    # STT speed-sensitivity
    if args.speed_test:
        print(f"\n🏃 STT speed-sensitivity benchmark — models: {', '.join(args.stt_models)}")
        r = benchmark_stt_speed_sensitivity(args.stt_models)
        all_results.extend(r)

    # LLM
    if not args.skip_llm:
        print(f"\n🧠 LLM benchmark — models: {', '.join(ollama_models)}")
        r = benchmark_llm(ollama_models)
        all_results.extend(r)

    # Pipeline
    if not args.skip_pipeline:
        print(f"\n⚡ End-to-end pipeline benchmark")
        fw_m = "small" if "small" in args.stt_models else args.stt_models[0]
        r = benchmark_pipeline(fw_m, ollama_models[0])
        all_results.append(r)

    run_result = {
        "target": args.target,
        "timestamp": timestamp,
        "sysinfo": sysinfo,
        "config": {
            "piper_model": Path(PIPER_MODEL).name,
            "piper_bin": PIPER_BIN,
            "fw_device": FW_DEVICE,
            "fw_compute": FW_COMPUTE,
            "ollama_url": OLLAMA_URL,
            "ollama_models": ollama_models,
        },
        "results": all_results,
    }

    print_report(run_result)

    # Save output
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if out_path.exists():
            try:
                existing = json.loads(out_path.read_text())
                if not isinstance(existing, list):
                    existing = [existing]
            except Exception:
                existing = []
        existing.append(run_result)
        out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
        print(f"\n✅ Results saved to {args.output}")

    # Also always save to tools/benchmark_voice_results.json
    default_out = Path(__file__).parent / "benchmark_voice_results.json"
    existing_default = []
    if default_out.exists():
        try:
            existing_default = json.loads(default_out.read_text())
            if not isinstance(existing_default, list):
                existing_default = [existing_default]
        except Exception:
            existing_default = []
    existing_default.append(run_result)
    default_out.write_text(json.dumps(existing_default, ensure_ascii=False, indent=2))
    if not args.output:
        print(f"\n✅ Results saved to {default_out}")


if __name__ == "__main__":
    main()
