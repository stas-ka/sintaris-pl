#!/usr/bin/env python3
"""
Taris Russian Voice Assistant
=================================
Local Russian voice interface for taris gateway on Raspberry Pi.

Pipeline:
  Microphone (webcam or USB mic via PipeWire)
    → [pw-record subprocess]                → raw PCM audio
    → [Vosk STT - vosk-model-small-ru]      (offline, Russian)
    → hotword detection ("пико")
    → record voice command → recognize text
    → taris agent -m "..."               (OpenRouter LLM via gateway)
    → [Piper TTS - ru_RU-irina-medium]      (offline, Russian, fast)
    → speaker (Pi 3.5mm jack or USB speaker)

Audio backend: pw-record (PipeWire native) with parec fallback.
PipeWire manages audio on this Pi OS (Bookworm+). sounddevice/PortAudio
cannot see PipeWire devices directly, so we use pw-record subprocess.

Based on KIM-ASSISTANT architecture analysis (KIM_FULL_ANALYSIS_REPORT.md):
  - STT: Vosk with small Russian model (48MB), real-time on Pi 3
  - TTS: Piper (no PyTorch required, replaces heavy Silero for Pi 3)
  - Hotword: Vosk fuzzy-match on "пико/пика/пике/пик"

Supported microphones (set AUDIO_TARGET):
  - auto     = system default (first available in PipeWire)
  - webcam   = alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback
               (requires webcam USB mic to be working — known Pi 3 HW issue!)
  - <name>   = custom PipeWire source node name (from: pactl list sources short)

Config via environment variables:
  VOSK_MODEL_PATH, PIPER_BIN, PIPER_MODEL, TARIS_BIN, AUDIO_TARGET
"""

import json
import logging
import os
import subprocess
import sys
import time
import threading
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, IO

import vosk

# STT provider — set via STT_PROVIDER env var
# vosk          → Vosk offline (default for Pi/taris)
# faster_whisper → faster-whisper CTranslate2 (default for openclaw/laptop)
# §30.3: Use VARIANT.default_stt instead of raw DEVICE_VARIANT check
from core.device_variant import VARIANT as _VARIANT
STT_PROVIDER = os.getenv("STT_PROVIDER", _VARIANT.default_stt).lower()
FASTER_WHISPER_MODEL   = os.getenv("FASTER_WHISPER_MODEL",   "base")
FASTER_WHISPER_DEVICE  = os.getenv("FASTER_WHISPER_DEVICE",  "cpu")
FASTER_WHISPER_COMPUTE = os.getenv("FASTER_WHISPER_COMPUTE", "int8")

# faster-whisper model cache (loaded on first use)
_fw_model_cache: dict = {}


# ---------------------------------------------------------------------------

CONFIG = {
    # Paths
    "vosk_model_path": os.getenv("VOSK_MODEL_PATH", "/home/stas/.taris/vosk-model-small-ru"),
    "piper_bin":       os.getenv("PIPER_BIN",       "/usr/local/bin/piper"),
    "piper_model":     os.getenv("PIPER_MODEL",     "/home/stas/.taris/ru_RU-irina-medium.onnx"),
    "taris_bin":    os.getenv("TARIS_BIN",    "/usr/bin/picoclaw"),

    # PipeWire runtime
    "pipewire_runtime_dir": "/run/user/1000",

    # Audio targets (PipeWire source node names):
    #   "auto"   = system default (recommended, let PipeWire decide)
    #   "webcam" = Philips SPC 520 (USB mic — currently broken on Pi 3, see notes)
    #   ""       = system default
    "audio_target":    os.getenv("AUDIO_TARGET", "auto"),

    # Audio format
    "sample_rate":     16000,
    "chunk_size":      4000,       # frames per chunk (250ms at 16kHz)

    # Hotword detection
    "hotwords":        ["пико", "пика", "пике", "пик", "привет пико"],
    "hotword_threshold": 0.75,

    # Recording
    "silence_timeout": 2.0,        # seconds of silence to end phrase
    "max_phrase_duration": 15.0,   # max recording time in seconds
    "min_phrase_chars": 3,

    # Known audio targets
    "webcam_mic_target": "alsa_input.usb-0471_USB_Video_Camera-02.mono-fallback",

    # TTS
    "confirm_sound":   True,
    "timeout_reply":   "Не слышу вас. Повторите, пожалуйста.",
    "error_reply":     "Произошла ошибка. Попробуйте ещё раз.",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/stas/.taris/voice.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("taris-voice")

# ---------------------------------------------------------------------------
# PipeWire audio capture (replaces sounddevice — PipeWire owns audio on Pi)
# ---------------------------------------------------------------------------

def _pipewire_env() -> dict:
    """Build environment with required PipeWire runtime vars."""
    env = os.environ.copy()
    runtime_dir = CONFIG["pipewire_runtime_dir"]
    env["XDG_RUNTIME_DIR"] = runtime_dir
    env["PIPEWIRE_RUNTIME_DIR"] = runtime_dir
    env["PULSE_SERVER"] = f"unix:{runtime_dir}/pulse/native"
    return env


def _get_audio_target() -> Optional[str]:
    """
    Resolve the audio target node name.
    Returns None for system default, or a specific node name.
    """
    target = CONFIG.get("audio_target", "auto").strip().lower()
    if target in ("auto", "default", ""):
        return None
    if target == "webcam":
        return CONFIG["webcam_mic_target"]
    return target  # user-specified node name


def _check_pipewire_sources() -> list:
    """List available PipeWire audio sources (non-monitor)."""
    try:
        result = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True, text=True, timeout=5,
            env=_pipewire_env(),
        )
        sources = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[1]
                if "monitor" not in name.lower():
                    sources.append(name)
        return sources
    except Exception:
        return []


def start_audio_capture(target: Optional[str] = None) -> subprocess.Popen:
    """
    Start pw-record subprocess and return the process.
    Audio is available at proc.stdout as raw S16_LE mono at sample_rate.

    Falls back to parec if pw-record fails.
    """
    env = _pipewire_env()
    sample_rate = CONFIG["sample_rate"]

    # Build pw-record command
    cmd = [
        "pw-record",
        f"--rate={sample_rate}",
        "--channels=1",
        "--format=s16",
        "-",  # stdout
    ]
    if target:
        cmd.extend(["--target", target])

    log.info(f"[AUDIO] Starting pw-record: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            bufsize=0,
        )
        # Brief check: give it 0.5s to fail fast or succeed
        time.sleep(0.5)
        if proc.poll() is not None:
            # Process exited early
            stderr = proc.stderr.read(500).decode("utf-8", errors="replace")
            raise RuntimeError(f"pw-record exited immediately: {stderr}")
        log.info("[AUDIO] pw-record started successfully.")
        return proc
    except FileNotFoundError:
        log.warning("[AUDIO] pw-record not found, trying parec...")
        return _start_parec(target, env, sample_rate)
    except Exception as e:
        log.warning(f"[AUDIO] pw-record failed: {e}, trying parec...")
        return _start_parec(target, env, sample_rate)


def _start_parec(target: Optional[str], env: dict, sample_rate: int) -> subprocess.Popen:
    """Fallback: use parec (PulseAudio compat via PipeWire)."""
    cmd = [
        "parec",
        f"--rate={sample_rate}",
        "--channels=1",
        "--format=s16le",
    ]
    if target:
        cmd.extend(["--device", target])

    log.info(f"[AUDIO] Starting parec: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        bufsize=0,
    )
    time.sleep(0.5)
    if proc.poll() is not None:
        err = proc.stderr.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"parec also failed: {err}\n"
                           "No working audio capture found. "
                           "Ensure a microphone is connected and visible via:\n"
                           "  pactl list sources short")
    log.info("[AUDIO] parec started successfully.")
    return proc


def read_audio_chunk(proc: subprocess.Popen, chunk_frames: int) -> Optional[bytes]:
    """
    Read exactly chunk_frames PCM frames from the process stdout.
    Returns None if the process has died.
    """
    chunk_bytes = chunk_frames * 2  # 2 bytes per frame for S16_LE mono
    try:
        data = proc.stdout.read(chunk_bytes)
        if not data:
            return None
        # Pad to exact size if short read
        while len(data) < chunk_bytes:
            more = proc.stdout.read(chunk_bytes - len(data))
            if not more:
                break
            data += more
        return data
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Hotword detection (adapted from KIM kim_hotword.py fuzzy-match approach)
# ---------------------------------------------------------------------------

def _similar(a: str, b: str) -> float:
    """SequenceMatcher similarity — same approach as KIM hotword engine."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _contains_hotword(text: str, hotwords: list, threshold: float) -> bool:
    """
    Check if recognized text contains a hotword.
    Checks both exact substring and fuzzy similarity (KIM pattern).
    """
    text_lower = text.lower().strip()
    words = text_lower.split()

    for hw in hotwords:
        hw_lower = hw.lower()
        hw_words = hw_lower.split()

        if hw_lower in text_lower:
            return True

        if len(hw_words) == 1:
            for w in words:
                if _similar(w, hw_lower) >= threshold:
                    return True
        elif len(hw_words) == 2 and len(words) >= 2:
            for i in range(len(words) - 1):
                bigram = words[i] + " " + words[i + 1]
                if _similar(bigram, hw_lower) >= threshold:
                    return True

    return False

# ---------------------------------------------------------------------------
# Text-to-Speech via Piper (replaces Silero/PyTorch — too heavy for Pi 3)
# ---------------------------------------------------------------------------

def speak(text: str) -> None:
    """
    Synthesize and play text using Piper TTS → aplay.
    Uses PIPEWIRE/XDG_RUNTIME_DIR env for aplay to work via PipeWire.
    """
    if not text.strip():
        return

    piper_bin = CONFIG["piper_bin"]
    piper_model = CONFIG["piper_model"]
    env = _pipewire_env()

    try:
        piper_cmd = [piper_bin, "--model", piper_model, "--output-raw"]
        aplay_cmd = ["aplay", "--rate=22050", "--format=S16_LE", "--channels=1", "-"]

        piper_proc = subprocess.Popen(
            piper_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        aplay_proc = subprocess.Popen(
            aplay_cmd,
            stdin=piper_proc.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )

        piper_proc.stdin.write(text.encode("utf-8"))
        piper_proc.stdin.close()
        piper_proc.stdout.close()
        aplay_proc.wait(timeout=60)

        log.info(f"[TTS] Spoke: {text[:80]}")

    except FileNotFoundError:
        log.error(f"Piper not found at {piper_bin}. Run setup_voice.sh first.")
    except subprocess.TimeoutExpired:
        log.warning("[TTS] Piper timeout, killing processes")
        try:
            piper_proc.kill()
            aplay_proc.kill()
        except Exception:
            pass
    except Exception as e:
        log.error(f"[TTS] Error: {e}")


def play_beep() -> None:
    """Play a short confirmation beep."""
    try:
        env = _pipewire_env()
        subprocess.run(
            ["aplay", "-q", "/usr/share/sounds/alsa/Front_Left.wav"],
            timeout=2, capture_output=True, env=env,
        )
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Ask taris (subprocess CLI)
# ---------------------------------------------------------------------------

def ask_taris(text: str, timeout: int = 60) -> Optional[str]:
    """Send recognized text to taris agent and return its response."""
    taris_bin = CONFIG["taris_bin"]
    log.info(f"[ASK] → taris: {text}")
    try:
        result = subprocess.run(
            [taris_bin, "agent", "-m", text],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        response = result.stdout.strip()
        if result.returncode != 0 and not response:
            log.error(f"taris error: {result.stderr.strip()}")
            return None
        log.info(f"[RESPONSE] ← {response[:120]}")
        return response or None
    except subprocess.TimeoutExpired:
        log.warning(f"taris timed out after {timeout}s")
        return None
    except FileNotFoundError:
        log.error(f"taris binary not found at {taris_bin}")
        return None
    except Exception as e:
        log.error(f"taris call error: {e}")
        return None

# ---------------------------------------------------------------------------
# Voice recording (using pw-record subprocess instead of sounddevice)
# ---------------------------------------------------------------------------

def record_phrase(
    recognizer: vosk.KaldiRecognizer,
    audio_target: Optional[str],
) -> Optional[str]:
    """
    Record audio and return recognized Russian text.
    Stops on silence or max duration.
    """
    sample_rate = CONFIG["sample_rate"]
    chunk_size = CONFIG["chunk_size"]
    silence_timeout = CONFIG["silence_timeout"]
    max_duration = CONFIG["max_phrase_duration"]
    min_chars = CONFIG["min_phrase_chars"]

    chunks_per_second = sample_rate // chunk_size
    max_chunks = int(max_duration * chunks_per_second)
    silence_chunks = int(silence_timeout * chunks_per_second)
    silent_count = 0
    recognized_text = ""

    log.debug("[STT] Recording phrase...")

    try:
        proc = start_audio_capture(target=audio_target)
    except RuntimeError as e:
        log.error(f"[STT] Failed to start audio: {e}")
        return None

    try:
        for _ in range(max_chunks):
            data = read_audio_chunk(proc, chunk_size)
            if data is None:
                log.warning("[STT] Audio stream ended unexpectedly")
                break

            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                partial_text = result.get("text", "").strip()
                if partial_text:
                    recognized_text += " " + partial_text
                    silent_count = 0
                else:
                    silent_count += 1
            else:
                partial = json.loads(recognizer.PartialResult())
                if not partial.get("partial", "").strip():
                    silent_count += 1
                else:
                    silent_count = 0

            if silent_count >= silence_chunks and recognized_text.strip():
                break

        # Get remaining text
        final = json.loads(recognizer.FinalResult())
        final_text = final.get("text", "").strip()
        if final_text:
            recognized_text += " " + final_text

    finally:
        proc.kill()
        proc.wait()

    recognized_text = recognized_text.strip()
    log.info(f"[STT] Recognized: '{recognized_text}'")

    if len(recognized_text) < min_chars:
        return None
    return recognized_text

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def record_and_recognize_faster_whisper(audio_target: Optional[str]) -> Optional[str]:
    """Record a voice phrase and transcribe it with faster-whisper.

    Unlike record_phrase() which runs STT incrementally, this function:
      1. Records audio into a buffer until silence is detected
      2. Transcribes the full buffer with faster-whisper in one shot

    Returns recognized text or None.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore[import]
        import numpy as _np
    except ImportError:
        log.error("[FasterWhisper] faster-whisper not installed. Run: pip install faster-whisper")
        return None

    sample_rate = CONFIG["sample_rate"]
    chunk_size = CONFIG["chunk_size"]
    silence_timeout = CONFIG["silence_timeout"]
    max_duration = CONFIG["max_phrase_duration"]
    min_chars = CONFIG["min_phrase_chars"]

    chunks_per_second = sample_rate // chunk_size
    max_chunks = int(max_duration * chunks_per_second)
    silence_chunks = int(silence_timeout * chunks_per_second)

    # Load model (cached)
    cache_key = (FASTER_WHISPER_MODEL, FASTER_WHISPER_DEVICE, FASTER_WHISPER_COMPUTE)
    if cache_key not in _fw_model_cache:
        log.info(f"[FasterWhisper] Loading model={FASTER_WHISPER_MODEL} device={FASTER_WHISPER_DEVICE}")
        _fw_model_cache[cache_key] = WhisperModel(
            FASTER_WHISPER_MODEL,
            device=FASTER_WHISPER_DEVICE,
            compute_type=FASTER_WHISPER_COMPUTE,
        )
    fw_model = _fw_model_cache[cache_key]

    # Simple energy-based silence detection using Vosk for VAD
    vosk_model = vosk.Model(CONFIG["vosk_model_path"])
    vosk_vad = vosk.KaldiRecognizer(vosk_model, sample_rate)
    vosk.SetLogLevel(-1)

    log.debug("[FasterWhisper] Recording phrase...")
    all_chunks: list[bytes] = []
    silent_count = 0

    try:
        proc = start_audio_capture(target=audio_target)
    except RuntimeError as e:
        log.error(f"[FasterWhisper] Failed to start audio: {e}")
        return None

    try:
        for _ in range(max_chunks):
            data = read_audio_chunk(proc, chunk_size)
            if data is None:
                break
            all_chunks.append(data)

            # Use Vosk PartialResult just for silence detection
            if vosk_vad.AcceptWaveform(data):
                silent_count = 0
            else:
                partial = json.loads(vosk_vad.PartialResult())
                if not partial.get("partial", "").strip():
                    silent_count += 1
                else:
                    silent_count = 0

            if silent_count >= silence_chunks and len(all_chunks) > chunks_per_second:
                break
    finally:
        proc.kill()
        proc.wait()

    if not all_chunks:
        return None

    raw_pcm = b"".join(all_chunks)
    audio_np = _np.frombuffer(raw_pcm, dtype=_np.int16).astype(_np.float32) / 32768.0

    lang = CONFIG.get("language", "ru")
    lang_map = {"ru": "ru", "en": "en", "de": "de"}
    fw_lang = lang_map.get(lang, "ru")

    segments, info = fw_model.transcribe(
        audio_np,
        language=fw_lang,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        condition_on_previous_text=False,
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    log.info(f"[FasterWhisper] Recognized: '{text}' (lang={info.language}, p={info.language_probability:.2f})")

    if len(text) < min_chars:
        return None
    return text




def main() -> None:
    """
    Main voice assistant loop.
    States: LISTENING → (hotword) → RECORDING → taris → SPEAKING → LISTENING

    STT routing (controlled by STT_PROVIDER env var):
      - 'vosk'           → Vosk offline (default for taris / Raspberry Pi)
      - 'faster_whisper' → faster-whisper CTranslate2 (default for openclaw / laptop)
    """
    log.info("=" * 60)
    log.info("Taris Russian Voice Assistant starting...")
    log.info(f"  STT provider: {STT_PROVIDER}")
    if STT_PROVIDER == "faster_whisper":
        log.info(f"  faster-whisper model : {FASTER_WHISPER_MODEL} ({FASTER_WHISPER_DEVICE}/{FASTER_WHISPER_COMPUTE})")
    else:
        log.info(f"  Vosk model : {CONFIG['vosk_model_path']}")
    log.info(f"  Piper TTS  : {CONFIG['piper_model']}")
    log.info(f"  Hotwords   : {CONFIG['hotwords']}")
    log.info(f"  Audio      : {CONFIG['audio_target'] or 'system default (PipeWire)'}")
    log.info("=" * 60)

    # Validate piper model always
    if not Path(CONFIG["piper_model"]).exists():
        log.error(f"Piper model not found: {CONFIG['piper_model']}")
        log.error("Run: bash src/setup/setup_voice_openclaw.sh")
        sys.exit(1)

    # Validate Vosk model only when Vosk is the STT provider
    if STT_PROVIDER != "faster_whisper":
        if not Path(CONFIG["vosk_model_path"]).exists():
            log.error(f"Vosk model not found: {CONFIG['vosk_model_path']}")
            log.error("Run: bash src/setup/setup_voice_openclaw.sh")
            sys.exit(1)

    # List available sources for diagnostics
    sources = _check_pipewire_sources()
    if sources:
        log.info(f"[AUDIO] Available sources: {', '.join(sources)}")
    else:
        log.warning("[AUDIO] No PipeWire sources found. Check: pactl list sources short")

    # Load Vosk model — always needed for hotword detection (even with faster-whisper)
    # Hotword loop uses Vosk because it is streaming/real-time; faster-whisper is batch.
    log.info("[STT] Loading Vosk model for hotword detection...")
    vosk.SetLogLevel(-1)
    model = vosk.Model(CONFIG["vosk_model_path"])
    recognizer = vosk.KaldiRecognizer(model, CONFIG["sample_rate"])
    recognizer.SetWords(True)
    log.info(f"[STT] Vosk loaded. Command STT: {STT_PROVIDER.replace('_', '-')}")

    # Resolve audio target
    audio_target = _get_audio_target()
    if audio_target:
        log.info(f"[AUDIO] Using target: {audio_target}")
    else:
        log.info("[AUDIO] Using system default microphone")

    # Startup announcement
    tts_model  = Path(CONFIG["piper_model"]).stem
    stt_label  = f"faster-whisper {FASTER_WHISPER_MODEL}" if STT_PROVIDER == "faster_whisper" else f"vosk {Path(CONFIG['vosk_model_path']).name}"
    log.info(f"[READY] STT: {stt_label}  |  TTS: {tts_model}")
    speak(
        f"Голосовой ассистент Пико запущен. "
        f"Поддерживаемые языки: русский. "
        f"Скажите «Пико» для активации."
    )

    log.info("[READY] Listening for hotword...")

    # Establish audio capture process for hotword loop
    try:
        audio_proc = start_audio_capture(target=audio_target)
    except RuntimeError as e:
        log.error(f"Cannot start audio capture: {e}")
        sys.exit(1)

    try:
        while True:
            data = read_audio_chunk(audio_proc, CONFIG["chunk_size"])

            if data is None:
                # Stream died - try to restart
                log.warning("[AUDIO] Stream died, restarting in 2s...")
                time.sleep(2)
                try:
                    audio_proc = start_audio_capture(target=audio_target)
                    recognizer.Reset()
                except RuntimeError as e:
                    log.error(f"Failed to restart audio: {e}")
                    time.sleep(5)
                continue

            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()

                if not text:
                    continue

                log.debug(f"[HOTWORD-LOOP] heard: '{text}'")

                if _contains_hotword(text, CONFIG["hotwords"], CONFIG["hotword_threshold"]):
                    log.info(f"[HOTWORD] Activated! heard: '{text}'")

                    # Stop hotword stream before recording
                    audio_proc.kill()
                    audio_proc.wait()

                    if CONFIG["confirm_sound"]:
                        play_beep()

                    log.info("[RECORDING] Listening for command...")

                    # Route to STT provider for command recognition
                    if STT_PROVIDER == "faster_whisper":
                        command = record_and_recognize_faster_whisper(audio_target)
                    else:
                        cmd_recognizer = vosk.KaldiRecognizer(model, CONFIG["sample_rate"])
                        cmd_recognizer.SetWords(True)
                        command = record_phrase(cmd_recognizer, audio_target)

                    if not command:
                        log.warning("[RECORDING] Nothing recognized")
                        speak(CONFIG["timeout_reply"])
                    else:
                        response = ask_taris(command)
                        if response:
                            speak(response)
                        else:
                            speak(CONFIG["error_reply"])

                    # Restart hotword stream
                    log.info("[READY] Listening for hotword...")
                    try:
                        audio_proc = start_audio_capture(target=audio_target)
                        recognizer.Reset()
                    except RuntimeError as e:
                        log.error(f"Failed to restart audio after command: {e}")
                        sys.exit(1)

    except KeyboardInterrupt:
        log.info("Stopped by user.")
        speak("До свидания!")
    except Exception as e:
        log.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        try:
            audio_proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    main()

