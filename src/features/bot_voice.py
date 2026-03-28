"""
bot_voice.py — Full voice pipeline.

Responsibilities:
  - Piper TTS (model selection, tmpfs copy, warmup, persistent process)
  - Vosk STT (lazy model load, confidence filtering)
  - Optional whisper.cpp STT (§5.3)
  - Optional WebRTC VAD pre-filter (§5.3)
  - OGG download → PCM decode (ffmpeg) → STT → LLM → TTS → send reply
  - Orphaned TTS message cleanup across restarts
"""

import io
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import core.bot_state as _st
from core.bot_config import (
    PIPER_BIN, PIPER_MODEL, PIPER_MODEL_TMPFS, PIPER_MODEL_LOW,
    PIPER_MODEL_DE, PIPER_MODEL_DE_TMPFS,
    VOSK_MODEL_PATH, VOSK_MODEL_DE_PATH, VOICE_SAMPLE_RATE, VOICE_CHUNK_SIZE,
    TTS_MAX_CHARS, TTS_CHUNK_CHARS, VOICE_TIMING_DEBUG,
    WHISPER_BIN, WHISPER_MODEL, VOICE_BACKEND,
    STT_PROVIDER, FASTER_WHISPER_MODEL, FASTER_WHISPER_DEVICE, FASTER_WHISPER_COMPUTE,
    STT_LANG,
    TARIS_DIR, _PENDING_TTS_FILE, log,
)
from core.bot_instance import bot
from telegram.bot_access import (
    _t, _lang, _safe_edit, _back_keyboard, _voice_back_keyboard,
    _escape_tts, _escape_md, _truncate, _with_lang_voice,
    _is_guest, _is_admin,
)
from core.bot_llm import ask_llm
from telegram.bot_users import (
    _slug, _list_notes_for, _load_note_text, _save_note_file,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — shorthand for state access
# ─────────────────────────────────────────────────────────────────────────────

def _voice_opts() -> dict:
    """Return the live voice opts dict (single source of truth in bot_state)."""
    return _st._voice_opts


# ─────────────────────────────────────────────────────────────────────────────
# Orphaned TTS message tracker
# ─────────────────────────────────────────────────────────────────────────────

def _save_pending_tts(chat_id: int, msg_id: int) -> None:
    """Record a pending TTS message so it can be cleaned up on restart."""
    try:
        try:
            data: dict = json.loads(Path(_PENDING_TTS_FILE).read_text(encoding="utf-8"))
        except Exception:
            data = {}
        data[str(chat_id)] = msg_id
        Path(_PENDING_TTS_FILE).write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        log.debug(f"[TTS] _save_pending_tts: {e}")


def _clear_pending_tts(chat_id: int) -> None:
    """Remove a chat's TTS entry once the message has been handled."""
    try:
        data: dict = json.loads(Path(_PENDING_TTS_FILE).read_text(encoding="utf-8"))
        data.pop(str(chat_id), None)
        Path(_PENDING_TTS_FILE).write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _voice_lang(chat_id: int) -> str:
    """Return the language to use for TTS/voice output.

    Prioritises STT_LANG (configured voice language) over the Telegram UI language.
    This ensures TTS speaks the same language the user *speaks*, not their Telegram
    client language (e.g. user has Telegram set to 'en' but speaks Russian).
    """
    return STT_LANG if STT_LANG else _lang(chat_id)


def _cleanup_orphaned_tts() -> None:
    """On startup, edit 'Generating audio…' messages left by a previous restart."""
    try:
        data: dict = json.loads(Path(_PENDING_TTS_FILE).read_text(encoding="utf-8"))
    except Exception:
        return
    if not data:
        return
    cleaned = 0
    for chat_id_str, msg_id in list(data.items()):
        try:
            bot.edit_message_text(
                "⚠️ Генерация аудио прервана (бот перезапущен)\n"
                "⚠️ Audio generation interrupted (bot restarted)",
                int(chat_id_str), msg_id,
            )
            cleaned += 1
        except Exception:
            pass
    try:
        Path(_PENDING_TTS_FILE).unlink(missing_ok=True)
    except Exception:
        pass
    if cleaned:
        log.info(f"[TTS] cleaned {cleaned} orphaned 'Generating audio…' message(s)")


# ─────────────────────────────────────────────────────────────────────────────
# Vosk — lazy singleton
# ─────────────────────────────────────────────────────────────────────────────

def _get_vosk_model(lang: str = "ru"):
    """Lazy-load the Vosk STT model for the given language (cached per language)."""
    if not hasattr(_st, "_vosk_model_cache_map"):
        _st._vosk_model_cache_map = {}
    if lang not in _st._vosk_model_cache_map:
        import vosk as _vosk_lib
        _vosk_lib.SetLogLevel(-1)
        model_path = VOSK_MODEL_DE_PATH if lang == "de" else VOSK_MODEL_PATH
        if not os.path.isdir(model_path):
            log.warning(f"[STT] Vosk model not found for lang={lang}: {model_path}, falling back to ru")
            model_path = VOSK_MODEL_PATH
        _st._vosk_model_cache_map[lang] = _vosk_lib.Model(model_path)
        # Keep legacy singleton in sync for first loaded model
        if _st._vosk_model_cache is None:
            _st._vosk_model_cache = _st._vosk_model_cache_map[lang]
    return _st._vosk_model_cache_map[lang]


# ─────────────────────────────────────────────────────────────────────────────
# Piper — model selection and warmup
# ─────────────────────────────────────────────────────────────────────────────

def _piper_model_path(lang: str = "ru") -> str:
    """
    Return the effective Piper ONNX model path for the given language.
    Priority: tmpfs (RAM disk) → low model → medium (default).
    German users always get the German model (no low/tmpfs variants yet).
    """
    if lang == "de":
        if _st._voice_opts.get("tmpfs_model") and os.path.exists(PIPER_MODEL_DE_TMPFS):
            return PIPER_MODEL_DE_TMPFS
        if os.path.exists(PIPER_MODEL_DE):
            return PIPER_MODEL_DE
        log.warning("[TTS] German Piper model not found, falling back to Russian model")
    opts = _st._voice_opts
    if opts.get("tmpfs_model") and os.path.exists(PIPER_MODEL_TMPFS):
        return PIPER_MODEL_TMPFS
    if opts.get("piper_low_model") and os.path.exists(PIPER_MODEL_LOW):
        return PIPER_MODEL_LOW
    return PIPER_MODEL


def _setup_tmpfs_model(enable: bool) -> None:
    """Copy or remove the Piper ONNX model to/from /dev/shm (tmpfs RAM disk).
    enable=True  → mkdir -p /dev/shm/piper + cp  (~30s on Pi 3)
    enable=False → remove from /dev/shm (fast)
    """
    import shutil
    if enable:
        try:
            os.makedirs("/dev/shm/piper", exist_ok=True)
            log.info(f"[VoiceOpt] tmpfs_model: copying {PIPER_MODEL} → {PIPER_MODEL_TMPFS}…")
            shutil.copy2(PIPER_MODEL, PIPER_MODEL_TMPFS)
            # Piper also requires the .onnx.json config file in the same directory
            _json_src = PIPER_MODEL + ".json"
            _json_dst = PIPER_MODEL_TMPFS + ".json"
            if os.path.exists(_json_src):
                shutil.copy2(_json_src, _json_dst)
                log.info(f"[VoiceOpt] tmpfs_model: also copied {_json_src}")
            else:
                log.warning(f"[VoiceOpt] tmpfs_model: model config not found: {_json_src}")
            size_mb = os.path.getsize(PIPER_MODEL_TMPFS) / 1024 / 1024
            log.info(f"[VoiceOpt] tmpfs_model: done ({size_mb:.0f} MB in RAM, ~10× faster reads)")
        except Exception as e:
            log.warning(f"[VoiceOpt] tmpfs_model: copy failed: {e}")
            _st._voice_opts["tmpfs_model"] = False
            from core.bot_state import _save_voice_opts
            _save_voice_opts()
    else:
        try:
            if os.path.exists(PIPER_MODEL_TMPFS):
                os.unlink(PIPER_MODEL_TMPFS)
                log.info(f"[VoiceOpt] tmpfs_model: removed {PIPER_MODEL_TMPFS}")
            _json_dst = PIPER_MODEL_TMPFS + ".json"
            if os.path.exists(_json_dst):
                os.unlink(_json_dst)
        except Exception as e:
            log.warning(f"[VoiceOpt] tmpfs_model: remove failed: {e}")


def _warm_piper_cache() -> None:
    """Pre-warm Piper ONNX model into OS page cache (background thread).
    Eliminates the 10–15s cold load on the first TTS call after startup.
    Only called when warm_piper opt is enabled.
    """
    try:
        log.info("[VoiceOpt] Warming Piper ONNX cache…")
        result = subprocess.run(
            [PIPER_BIN, "--model", _piper_model_path(), "--output-raw"],
            input=b".",
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0:
            log.info("[VoiceOpt] Piper cache warm complete.")
        else:
            log.warning(f"[VoiceOpt] Piper warmup rc={result.returncode}: "
                        f"{result.stderr[:100]}")
    except Exception as e:
        log.warning(f"[VoiceOpt] Piper warmup failed: {e}")


def _start_persistent_piper() -> None:
    """Launch a long-running Piper process to keep ONNX in the kernel page cache.
    The subprocess holds stdin open without receiving input.  Actual TTS synthesis
    still uses fresh subprocess.run() calls for safety (§5.3 persistent_piper).
    """
    _stop_persistent_piper()
    try:
        _st._persistent_piper_proc = subprocess.Popen(
            [PIPER_BIN, "--model", _piper_model_path(), "--output-raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info(f"[PersistentPiper] started PID={_st._persistent_piper_proc.pid}")
    except Exception as e:
        log.warning(f"[PersistentPiper] failed to start: {e}")


def _stop_persistent_piper() -> None:
    """Terminate the persistent Piper keepalive subprocess."""
    if _st._persistent_piper_proc is not None:
        try:
            if _st._persistent_piper_proc.poll() is None:
                _st._persistent_piper_proc.terminate()
                _st._persistent_piper_proc.wait(timeout=5)
            log.info(f"[PersistentPiper] stopped PID={_st._persistent_piper_proc.pid}")
        except Exception as e:
            log.debug(f"[PersistentPiper] stop error: {e}")
        _st._persistent_piper_proc = None


# ─────────────────────────────────────────────────────────────────────────────
# §5.3 — VAD pre-filter
# ─────────────────────────────────────────────────────────────────────────────

def _vad_filter_pcm(raw_pcm: bytes, sample_rate: int) -> bytes:
    """Apply WebRTC VAD to strip non-speech frames from raw S16LE PCM.
    Returns filtered PCM.  Falls back silently if webrtcvad is not installed.
    Requires: pip3 install webrtcvad
    """
    try:
        import webrtcvad as _vad_lib
        vad = _vad_lib.Vad(2)          # aggressiveness 0–3 (2 = balanced)
        frame_ms = 30                   # 10/20/30 ms frames supported by WebRTC VAD
        frame_bytes = int(sample_rate * (frame_ms / 1000.0)) * 2
        out_frames = []
        for i in range(0, len(raw_pcm) - frame_bytes + 1, frame_bytes):
            frame = raw_pcm[i:i + frame_bytes]
            try:
                if vad.is_speech(frame, sample_rate):
                    out_frames.append(frame)
            except Exception:
                out_frames.append(frame)           # keep on per-frame error
        filtered = b"".join(out_frames)
        removed_pct = 100 * (1 - len(filtered) / max(len(raw_pcm), 1))
        log.debug(f"[VAD] removed {removed_pct:.0f}% non-speech frames")
        return filtered if filtered else raw_pcm   # never return empty
    except ImportError:
        log.debug("[VAD] webrtcvad not installed — skipping filter")
        return raw_pcm
    except Exception as e:
        log.debug(f"[VAD] filter error: {e} — skipping")
        return raw_pcm


# ─────────────────────────────────────────────────────────────────────────────
# §5.3 — whisper.cpp STT
# ─────────────────────────────────────────────────────────────────────────────

def _stt_whisper(raw_pcm: bytes, sample_rate: int) -> Optional[str]:
    """Run whisper.cpp on raw S16LE PCM.  Returns transcript or None.
    Writes PCM to a temp WAV file, invokes WHISPER_BIN, parses stdout.
    Falls back to None on any error (caller uses Vosk as fallback).
    Requires: whisper-cpp binary at WHISPER_BIN + ggml-tiny.bin model.
    """
    try:
        import re as _re_w
        import tempfile
        import wave as _wave_mod

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        with _wave_mod.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(raw_pcm)

        _whisper_cmd = [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", tmp_path,
                        "-l", "ru", "--no-timestamps", "-otxt",
                        "--threads", "4",            # use all Pi 3 cores
                        "--suppress-blank",          # don't output blank/silence segments
                        "--entropy-thold", "1.8",    # reject hallucinated output
                        "--no-speech-thold", "0.6"]  # reject silence/noise segments
        if VOICE_BACKEND == "cuda":
            _whisper_cmd += ["--device", "cuda"]

        result = subprocess.run(
            _whisper_cmd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=60,
        )
        os.unlink(tmp_path)

        if result.returncode != 0:
            log.warning(f"[WhisperSTT] rc={result.returncode}: {result.stderr[:200]}")
            return None

        txt_path = tmp_path + ".txt"
        if os.path.exists(txt_path):
            text = open(txt_path, encoding="utf-8").read().strip()
            os.unlink(txt_path)
        else:
            text = result.stdout.strip()

        # Strip whisper.cpp timestamp markers: [00:00:00.000 --> 00:00:05.000]
        text = _re_w.sub(r"\[[\d:.]+ --> [\d:.]+\]\s*", "", text).strip()
        if not text:
            return None

        # Sanity check: Whisper hallucinates short garbled phrases on unclear
        # audio.  Expected Russian speech rate ~3 words/s; if output is way
        # below that for audio longer than 2 s, discard and let Vosk handle it.
        duration_s = len(raw_pcm) / (sample_rate * 2)
        if duration_s > 2.0:
            min_expected = max(2, int(duration_s * 2.0))
            actual_words = len(text.split())
            if actual_words < min_expected:
                log.warning(
                    f"[WhisperSTT] output too sparse ({actual_words} words for "
                    f"{duration_s:.1f}s audio, expected >={min_expected}) — discarding"
                )
                return None

        return text

    except FileNotFoundError:
        log.debug(f"[WhisperSTT] binary not found: {WHISPER_BIN}")
        return None
    except subprocess.TimeoutExpired:
        log.warning("[WhisperSTT] timed out after 60 s")
        return None
    except Exception as e:
        log.warning(f"[WhisperSTT] error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# §OpenClaw — faster-whisper STT (Python, CTranslate2)
# Recommended STT for OpenClaw (laptop/PC) variant.
# Much better WER than Vosk small model; runs on CPU without GPU.
# Install: pip install faster-whisper
# Model auto-downloaded on first run to ~/.cache/huggingface/hub/
# ─────────────────────────────────────────────────────────────────────────────

_fw_model_cache: dict = {}   # {(model_size, device, compute): WhisperModel}


def _stt_faster_whisper(raw_pcm: bytes, sample_rate: int, lang: str = "ru") -> Optional[str]:
    """Run faster-whisper on raw S16LE PCM.  Returns transcript or None.

    Uses CTranslate2 backend — much faster than original Whisper on CPU.
    Model is loaded once and cached for the process lifetime.

    Args:
        raw_pcm:     Raw 16-bit LE PCM audio bytes.
        sample_rate: Audio sample rate in Hz.
        lang:        Language code: 'ru', 'en', 'de'.

    Config (bot.env):
        FASTER_WHISPER_MODEL   — model size: tiny/base/small/medium (default: base)
        FASTER_WHISPER_DEVICE  — cpu / cuda (default: cpu)
        FASTER_WHISPER_COMPUTE — int8 / float16 / float32 (default: int8)
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore[import]
    except ImportError:
        log.debug("[FasterWhisper] faster-whisper not installed — install with: pip install faster-whisper")
        return None

    try:
        import tempfile
        import wave as _wave_mod
        import numpy as _np

        cache_key = (FASTER_WHISPER_MODEL, FASTER_WHISPER_DEVICE, FASTER_WHISPER_COMPUTE)
        if cache_key not in _fw_model_cache:
            log.info(
                f"[FasterWhisper] Loading model={FASTER_WHISPER_MODEL} "
                f"device={FASTER_WHISPER_DEVICE} compute={FASTER_WHISPER_COMPUTE}"
            )
            # Prefer local HuggingFace cache path to avoid any network/auth requests.
            # faster-whisper caches as models--Systran--faster-whisper-<size>
            model_arg = FASTER_WHISPER_MODEL
            _hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
            _model_dir = _hf_cache / f"models--Systran--faster-whisper-{FASTER_WHISPER_MODEL}"
            _snapshots = _model_dir / "snapshots"
            if _snapshots.is_dir():
                _snaps = sorted(_snapshots.iterdir())
                if _snaps:
                    model_arg = str(_snaps[-1])   # latest snapshot
                    log.info(f"[FasterWhisper] using local cache: {model_arg}")
            _fw_model_cache[cache_key] = WhisperModel(
                model_arg,
                device=FASTER_WHISPER_DEVICE,
                compute_type=FASTER_WHISPER_COMPUTE,
            )
        model = _fw_model_cache[cache_key]

        # Convert S16LE PCM bytes → float32 numpy array in [-1, 1]
        audio_np = _np.frombuffer(raw_pcm, dtype=_np.int16).astype(_np.float32) / 32768.0

        # Resample to 16kHz if needed (faster-whisper expects 16kHz)
        if sample_rate != 16000:
            from scipy.signal import resample as _resample  # type: ignore[import]
            target_len = int(len(audio_np) * 16000 / sample_rate)
            audio_np = _resample(audio_np, target_len).astype(_np.float32)

        # Map language codes — faster-whisper uses ISO 639-1
        lang_map = {"ru": "ru", "en": "en", "de": "de"}
        fw_lang = lang_map.get(lang, "ru")

        segments, info = model.transcribe(
            audio_np,
            language=fw_lang,
            beam_size=5,
            vad_filter=True,          # built-in VAD — suppresses silence/noise
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False,
        )

        text = " ".join(seg.text.strip() for seg in segments).strip()
        if not text:
            log.debug("[FasterWhisper] no speech detected")
            return None

        # Hallucination guard: reject known false-positive phrases Whisper emits on short/noisy audio
        _HALLUCINATIONS = {
            "and that's the whole thing", "thank you", "thanks for watching",
            "thanks for watching!", "you", ".", "..", "...",
        }
        if text.lower().rstrip(".!? ") in _HALLUCINATIONS or len(text) < 3:
            log.warning(f"[FasterWhisper] hallucination rejected: {text!r}")
            return None

        log.info(f"[FasterWhisper] transcript lang={info.language} prob={info.language_probability:.2f}: {text[:120]}")
        return text

    except Exception as exc:
        log.warning(f"[FasterWhisper] error: {exc}")
        return None




def _split_for_tts(text: str, max_chars: int) -> list[str]:
    """
    Split *text* into chunks ≤ *max_chars* each, breaking preferentially at
    sentence / paragraph boundaries so each chunk is a natural speech unit.
    Returns a list of non-empty stripped strings.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # Sentence / clause separators ordered by preference
    SENT_ENDS = [". ", "! ", "? ", ".\n", "!\n", "?\n", "…\n", ";\n", "; "]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        window = remaining[:max_chars]
        best = -1
        for sep in SENT_ENDS:
            idx = window.rfind(sep)
            # Require the break to be at least 20 % into the window
            if idx > max_chars // 5 and idx + len(sep) - 1 > best:
                best = idx + len(sep) - 1
        if best > 0:
            chunk     = remaining[:best + 1].strip()
            remaining = remaining[best + 1:].strip()
        else:
            # Fall back to last whitespace boundary
            idx = window.rfind(" ")
            if idx > max_chars // 5:
                chunk     = remaining[:idx].strip()
                remaining = remaining[idx + 1:].strip()
            else:
                # Hard cut — no suitable boundary found
                chunk     = remaining[:max_chars].strip()
                remaining = remaining[max_chars:].strip()
        if chunk:
            chunks.append(chunk)
    if remaining:
        chunks.append(remaining)
    return chunks


def _tts_to_ogg(text: str, _trim: bool = True, lang: str = "ru") -> Optional[bytes]:
    """
    Synthesise text with Piper TTS, encode with ffmpeg as OGG Opus.
    Returns bytes for bot.send_voice(), or None on failure.

    Two sequential subprocess.run() calls (not Popen pipe) to avoid
    the deadlock where parent holds piper.stdout open → ffmpeg blocks on stdin EOF.

    _trim=True  — cap at TTS_MAX_CHARS (real-time voice chat responses).
    _trim=False — no length cap; caller is responsible for pre-chunking.
    """
    tts_text = _escape_tts(text)

    # Trim to whole sentences, then hard-cap at TTS_MAX_CHARS (real-time path only)
    if _trim and len(tts_text) > TTS_MAX_CHARS:
        cut = tts_text[:TTS_MAX_CHARS]
        for sep in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
            idx = cut.rfind(sep)
            if idx > TTS_MAX_CHARS // 2:
                cut = cut[:idx + 1]
                break
        tts_text = cut.strip()

    if not tts_text:
        return None

    try:
        # Step 1: Piper TTS → raw S16LE PCM at 22050 Hz
        piper_result = subprocess.run(
            [PIPER_BIN, "--model", _piper_model_path(lang), "--output-raw"],
            input=tts_text.encode("utf-8"),
            capture_output=True,
            timeout=120,
        )
        raw_pcm = piper_result.stdout
        if not raw_pcm:
            log.warning(f"[TTS] piper no output rc={piper_result.returncode}: "
                        f"{piper_result.stderr[:200]}")
            return None

        # Step 2: ffmpeg PCM → OGG Opus
        ff_result = subprocess.run(
            ["ffmpeg", "-y",
             "-f", "s16le", "-ar", "22050", "-ac", "1", "-i", "pipe:0",
             "-c:a", "libopus", "-b:a", "24k", "-f", "ogg", "pipe:1"],
            input=raw_pcm,
            capture_output=True,
            timeout=30,
        )
        ogg_bytes = ff_result.stdout
        if not ogg_bytes:
            log.warning(f"[TTS] ffmpeg no output rc={ff_result.returncode}: "
                        f"{ff_result.stderr[:200]}")
            return None
        return ogg_bytes

    except subprocess.TimeoutExpired as e:
        log.warning(f"[TTS] timeout: {e}")
        return None
    except Exception as e:
        log.warning(f"[TTS] failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Notes TTS — “Read aloud” button handler
# ─────────────────────────────────────────────────────────────────────────────

def _handle_note_read_aloud(chat_id: int, slug: str) -> None:
    """
    Read a note aloud via Piper TTS.
    Long notes are split into chunks (~55 s each) and delivered as consecutive
    voice messages so the full text is always heard.
    Runs in a background thread to avoid blocking the callback handler.
    """
    from telegram.bot_handlers import _notes_menu_keyboard  # deferred — avoids circular import at module level

    note_text = _load_note_text(chat_id, slug)
    if note_text is None:
        bot.send_message(chat_id, _t(chat_id, "note_not_found"),
                         reply_markup=_notes_menu_keyboard(chat_id))
        return

    msg = bot.send_message(chat_id, _t(chat_id, "gen_audio"), parse_mode="Markdown")
    _save_pending_tts(chat_id, msg.message_id)

    def _run():
        import io as _io
        try:
            # Strip title header and Markdown/emoji before TTS
            lines      = note_text.splitlines()
            body       = "\n".join(lines[2:] if len(lines) > 2 else lines).strip() or note_text
            plain      = _escape_tts(body)
            if not plain.strip():
                plain  = _escape_tts(note_text)
            if not plain.strip():
                _safe_edit(chat_id, msg.message_id,
                           _t(chat_id, "audio_na"), parse_mode="Markdown")
                return

            note_title = lines[0].lstrip("# ").strip()
            chunks     = _split_for_tts(plain, TTS_CHUNK_CHARS)
            total      = len(chunks)
            sent       = 0

            for i, chunk in enumerate(chunks):
                ogg = _tts_to_ogg(chunk, _trim=False, lang=_voice_lang(chat_id))
                if not ogg:
                    log.warning(f"[NotesTTS] chunk {i + 1}/{total} TTS synthesis failed — skipping")
                    continue
                sent += 1
                label = (f"🔊 {note_title} ({sent}/{total})"
                         if total > 1 else f"🔊 {note_title}")
                try:
                    bot.send_voice(chat_id, _io.BytesIO(ogg), caption=label)
                except Exception as _send_err:
                    log.warning(f"[NotesTTS] send_voice chunk {i + 1}/{total} failed: {_send_err}")
                    sent -= 1  # was not actually delivered

            if sent:
                bot.delete_message(chat_id, msg.message_id)
            else:
                _safe_edit(chat_id, msg.message_id,
                           _t(chat_id, "audio_na"), parse_mode="Markdown")
        except Exception as e:
            log.warning(f"[NotesTTS] error: {e}")
            try:
                _safe_edit(chat_id, msg.message_id,
                           _t(chat_id, "audio_error", e=str(e)), parse_mode="Markdown")
            except Exception:
                pass
        finally:
            _clear_pending_tts(chat_id)

    threading.Thread(target=_run, daemon=True).start()


def _handle_digest_tts(chat_id: int) -> None:
    """
    Read the last mail digest aloud via Piper TTS.
    Long digests are split into ~55 s chunks and delivered as consecutive
    voice messages so the complete digest is always read in full.
    Runs in a background thread to avoid blocking the callback handler.
    """
    from features.bot_mail_creds import _last_digest_file  # deferred — avoids circular import

    fp = _last_digest_file(chat_id)
    if not fp.exists() or fp.stat().st_size == 0:
        bot.send_message(chat_id, _t(chat_id, "digest_not_ready"), parse_mode="Markdown")
        return

    digest_text = fp.read_text(encoding="utf-8", errors="replace").strip()

    msg = bot.send_message(chat_id, _t(chat_id, "gen_audio"), parse_mode="Markdown")
    _save_pending_tts(chat_id, msg.message_id)

    def _run():
        import io as _io
        try:
            plain = _escape_tts(digest_text)
            if not plain.strip():
                _safe_edit(chat_id, msg.message_id,
                           _t(chat_id, "audio_na"), parse_mode="Markdown")
                return

            caption = "🔊 " + _t(chat_id, "mail_digest_audio_caption")
            chunks  = _split_for_tts(plain, TTS_CHUNK_CHARS)
            total   = len(chunks)
            sent    = 0

            for i, chunk in enumerate(chunks):
                ogg = _tts_to_ogg(chunk, _trim=False, lang=_voice_lang(chat_id))
                if not ogg:
                    log.warning(f"[DigestTTS] chunk {i + 1}/{total} TTS synthesis failed — skipping")
                    continue
                sent += 1
                label = (f"{caption} ({sent}/{total})"
                         if total > 1 else caption)
                try:
                    bot.send_voice(chat_id, _io.BytesIO(ogg), caption=label)
                except Exception as _send_err:
                    log.warning(f"[DigestTTS] send_voice chunk {i + 1}/{total} failed: {_send_err}")
                    sent -= 1  # was not actually delivered

            if sent:
                bot.delete_message(chat_id, msg.message_id)
            else:
                _safe_edit(chat_id, msg.message_id,
                           _t(chat_id, "audio_na"), parse_mode="Markdown")
        except Exception as e:
            log.warning(f"[DigestTTS] error: {e}")
            try:
                _safe_edit(chat_id, msg.message_id,
                           _t(chat_id, "audio_error", e=str(e)), parse_mode="Markdown")
            except Exception:
                pass
        finally:
            _clear_pending_tts(chat_id)

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Voice session entry point
# ─────────────────────────────────────────────────────────────────────────────

def _start_voice_session(chat_id: int) -> None:
    """Enter voice mode — user sends a Telegram voice note to interact."""
    _st._user_mode[chat_id] = "voice"
    bot.send_message(
        chat_id,
        _t(chat_id, "voice_enter"),
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Voice message handler — full pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _handle_voice_message(chat_id: int, voice_obj) -> None:
    """
    Process a Telegram voice note:
      OGG → ffmpeg decode (16 kHz PCM) → [VAD] → [Whisper|Vosk] STT
        → [notes cmd] or [taris LLM] → text + Piper TTS OGG.

    Runs in a background thread so the Telegram handler returns immediately.
    """
    msg = bot.send_message(chat_id, _t(chat_id, "recognizing"), parse_mode="Markdown")

    def _run():
        _timing: dict[str, float] = {}

        def _fmt_timing() -> str:
            if not (VOICE_TIMING_DEBUG or opts.get("voice_timing_debug")) or not _timing:
                return ""
            return "\n\n⏱ " + " · ".join(f"{k} {v:.0f}s" for k, v in _timing.items())

        opts = _st._voice_opts

        # ── Download OGG ─────────────────────────────────────────────────────
        _ts = time.time()
        try:
            file_info = bot.get_file(voice_obj.file_id)
            ogg_bytes  = bot.download_file(file_info.file_path)
        except Exception as e:
            _safe_edit(chat_id, msg.message_id,
                       _t(chat_id, "dl_error", e=e),
                       reply_markup=_back_keyboard())
            return
        _timing["Download"] = time.time() - _ts

        # ── OGG → 16 kHz mono S16LE PCM ──────────────────────────────────────
        _srate = 8000 if opts.get("low_sample_rate") else VOICE_SAMPLE_RATE
        _af_filters = []
        if opts.get("silence_strip"):
            _af_filters.append(
                "silenceremove=start_periods=1:start_silence=0.3"
                ":start_threshold=-40dB"
                ":stop_periods=1:stop_silence=0.5:stop_threshold=-40dB"
            )
        _af_filters += ["highpass=f=80", "dynaudnorm=p=0.9"]
        _ff_cmd = (
            ["ffmpeg", "-i", "pipe:0", "-af", ",".join(_af_filters)]
            + ["-ar", str(_srate), "-ac", "1", "-f", "s16le", "pipe:1"]
        )
        _ts = time.time()
        try:
            ff = subprocess.Popen(
                _ff_cmd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            raw_pcm, _ = ff.communicate(input=ogg_bytes, timeout=30)
        except Exception as e:
            _safe_edit(chat_id, msg.message_id,
                       _t(chat_id, "decode_error", e=e),
                       reply_markup=_back_keyboard())
            return
        _timing["Convert"] = time.time() - _ts

        if not raw_pcm:
            _safe_edit(chat_id, msg.message_id,
                       _t(chat_id, "ffmpeg_no_data"),
                       reply_markup=_back_keyboard())
            return

        # ── VAD pre-filter (§5.3) ─────────────────────────────────────────────
        if opts.get("vad_prefilter"):
            _ts = time.time()
            raw_pcm = _vad_filter_pcm(raw_pcm, _srate)
            _timing["VAD"] = time.time() - _ts

        # ── STT: faster-whisper (OpenClaw default) or whisper.cpp or Vosk ───────
        _ts = time.time()
        text = ""
        fw_used = opts.get("faster_whisper_stt")
        whisper_used = opts.get("whisper_stt")
        # STT language: explicit STT_LANG config beats UI language (Telegram client lang ≠ speech lang)
        _stt_lang = STT_LANG if STT_LANG else _lang(chat_id)
        log.info(f"[STT] provider={'fw' if fw_used else 'whisper' if whisper_used else 'vosk'} "
                 f"lang={_stt_lang} (STT_LANG={STT_LANG!r} _lang={_lang(chat_id)!r})")

        if fw_used:
            text = _stt_faster_whisper(raw_pcm, _srate, _stt_lang) or ""
            if text:
                log.info(f"[FasterWhisper] transcript: {text[:120]}")
            else:
                log.warning("[FasterWhisper] no result — falling back to Vosk")
        elif whisper_used:
            text = _stt_whisper(raw_pcm, _srate) or ""
            if text:
                log.debug(f"[WhisperSTT] transcript: {text[:80]}")
            else:
                log.warning("[WhisperSTT] no result — falling back to Vosk")

        # Vosk fallback — skip only when primary STT succeeded or vosk_fallback=False
        primary_stt_used = fw_used or whisper_used
        vosk_fallback_enabled = not primary_stt_used or opts.get("vosk_fallback", True)
        if not text and vosk_fallback_enabled:
            STT_CONF_THRESHOLD = 0.65
            try:
                import vosk as _vosk_lib
                import json as _json
                model = _get_vosk_model(_stt_lang)
                rec = _vosk_lib.KaldiRecognizer(model, _srate)
                rec.SetWords(True)
                chunk = VOICE_CHUNK_SIZE * 2 * _srate // VOICE_SAMPLE_RATE
                for i in range(0, len(raw_pcm), chunk):
                    rec.AcceptWaveform(raw_pcm[i:i + chunk])
                final = _json.loads(rec.FinalResult())
                words = final.get("result", [])
                if words:
                    parts = []
                    low_conf_count = 0
                    for w in words:
                        conf = w.get("conf", 1.0)
                        word = w.get("word", "")
                        if conf < STT_CONF_THRESHOLD:
                            parts.append(f"[?{word}]")
                            low_conf_count += 1
                        else:
                            parts.append(word)
                    text = " ".join(parts).strip()
                    if low_conf_count:
                        log.debug(f"[STT] {low_conf_count}/{len(words)} words "
                                  f"below conf={STT_CONF_THRESHOLD}: {text[:120]}")
                else:
                    text = final.get("text", "").strip()
            except Exception as e:
                _safe_edit(chat_id, msg.message_id,
                           _t(chat_id, "vosk_error", e=e),
                           reply_markup=_back_keyboard())
                return
        _timing["STT"] = time.time() - _ts

        if not text:
            _safe_edit(chat_id, msg.message_id,
                       _t(chat_id, "not_recognized"),
                       parse_mode="Markdown",
                       reply_markup=_back_keyboard())
            return

        # ── Voice input during note multi-step flow ────────────────────────────
        # If the user is waiting for a note title/content/edit via the keyboard
        # flow, treat this voice message as the text input for that step.
        _cur_mode = _st._user_mode.get(chat_id)
        if _cur_mode in ("note_add_title", "note_add_content", "note_edit_content") \
                and not _is_guest(chat_id):
            _clean_text = re.sub(r'\[\?([^\]]*)\]', r'\1', text).strip()
            _safe_edit(chat_id, msg.message_id,
                       f"🎤 _{_escape_md(_clean_text)}_",
                       parse_mode="Markdown")

            if _cur_mode == "note_add_title":
                note_slug = _slug(_clean_text)
                _st._pending_note[chat_id] = {"step": "content", "slug": note_slug, "title": _clean_text}
                _st._user_mode[chat_id]    = "note_add_content"
                bot.send_message(chat_id,
                                 _t(chat_id, "note_create_prompt_content",
                                    title=_escape_md(_clean_text)),
                                 parse_mode="Markdown")

            elif _cur_mode == "note_add_content":
                info  = _st._pending_note.pop(chat_id, {})
                _st._user_mode.pop(chat_id, None)
                slug  = info.get("slug", _slug(_clean_text[:30]))
                title = info.get("title", slug)
                _save_note_file(chat_id, slug, f"# {title}\n\n{_clean_text}")
                from telegram.bot_handlers import _notes_menu_keyboard  # safe — deferred import, no circular issue at runtime
                bot.send_message(chat_id,
                                 _t(chat_id, "note_saved", title=_escape_md(title)),
                                 parse_mode="Markdown",
                                 reply_markup=_notes_menu_keyboard(chat_id))

            elif _cur_mode == "note_edit_content":
                info = _st._pending_note.pop(chat_id, {})
                _st._user_mode.pop(chat_id, None)
                slug = info.get("slug")
                if not slug:
                    from telegram.bot_access import _send_menu
                    _send_menu(chat_id, greeting=False)
                    return
                existing   = _load_note_text(chat_id, slug)
                title_line = existing.splitlines()[0] if existing else f"# {slug}"
                _save_note_file(chat_id, slug, f"{title_line}\n\n{_clean_text}")
                edit_title = title_line.lstrip("# ").strip()
                from telegram.bot_handlers import _notes_menu_keyboard  # deferred — safe
                bot.send_message(chat_id,
                                 _t(chat_id, "note_updated", title=_escape_md(edit_title)),
                                 parse_mode="Markdown",
                                 reply_markup=_notes_menu_keyboard(chat_id))
            return

        # ── Voice input during calendar-add flow ──────────────────────────────
        if _cur_mode == "calendar" and not _is_guest(chat_id):
            _clean_text = re.sub(r'\[\?([^\]]*)\]', r'\1', text).strip()
            _safe_edit(chat_id, msg.message_id,
                       f"🎤 _{_escape_md(_clean_text)}_",
                       parse_mode="Markdown")
            from features.bot_calendar import _finish_cal_add  # noqa: PLC0415  deferred — no circular at runtime
            _finish_cal_add(chat_id, _clean_text)
            return

        # ── Voice input during calendar console ───────────────────────────────
        if _cur_mode == "cal_console" and not _is_guest(chat_id):
            _clean_text = re.sub(r'\[\?([^\]]*)\]', r'\1', text).strip()
            _safe_edit(chat_id, msg.message_id,
                       f"🎤 _{_escape_md(_clean_text)}_",
                       parse_mode="Markdown")
            from features.bot_calendar import _handle_cal_console  # noqa: PLC0415
            _handle_cal_console(chat_id, _clean_text)
            return

        # ── Voice input during calendar field-edit flows ──────────────────────
        if _cur_mode in ("cal_edit_title", "cal_edit_dt", "cal_edit_remind") \
                and not _is_guest(chat_id):
            _field = _cur_mode[len("cal_edit_"):]   # "title" / "dt" / "remind"
            _clean_text = re.sub(r'\[\?([^\]]*)\]', r'\1', text).strip()
            _safe_edit(chat_id, msg.message_id,
                       f"🎤 _{_escape_md(_clean_text)}_",
                       parse_mode="Markdown")
            from features.bot_calendar import _cal_handle_edit_input  # noqa: PLC0415
            _cal_handle_edit_input(chat_id, _clean_text, _field)
            return

        # ── Voice input during contact-book flows ─────────────────────────────
        if _cur_mode == "contact_add" and not _is_guest(chat_id):
            _clean_text = re.sub(r'\[\?([^\]]*)\]', r'\1', text).strip()
            _safe_edit(chat_id, msg.message_id,
                       f"🎤 _{_escape_md(_clean_text)}_",
                       parse_mode="Markdown")
            from features.bot_contacts import _finish_contact_add  # noqa: PLC0415
            _finish_contact_add(chat_id, _clean_text)
            return

        if _cur_mode == "contact_edit" and not _is_guest(chat_id):
            _clean_text = re.sub(r'\[\?([^\]]*)\]', r'\1', text).strip()
            _safe_edit(chat_id, msg.message_id,
                       f"🎤 _{_escape_md(_clean_text)}_",
                       parse_mode="Markdown")
            from features.bot_contacts import _finish_contact_edit  # noqa: PLC0415
            _finish_contact_edit(chat_id, _clean_text)
            return

        if _cur_mode == "contact_search" and not _is_guest(chat_id):
            _clean_text = re.sub(r'\[\?([^\]]*)\]', r'\1', text).strip()
            _safe_edit(chat_id, msg.message_id,
                       f"🎤 _{_escape_md(_clean_text)}_",
                       parse_mode="Markdown")
            from features.bot_contacts import _finish_contact_search  # noqa: PLC0415
            _finish_contact_search(chat_id, _clean_text)
            return

        # ── Voice note commands (intercept before LLM) ────────────────────────
        _text_lower = text.lower()
        _note_create_ru = ("запиши заметку", "создай заметку", "запишите заметку", "сохрани заметку")
        _note_create_en = ("create note", "save note", "new note")
        _note_read_ru   = ("прочитай заметку", "читай заметку", "открой заметку")
        _note_read_en   = ("read note", "open note", "show note")

        def _starts_with_any(s: str, prefixes) -> Optional[str]:
            for p in prefixes:
                if s.startswith(p):
                    return s[len(p):].strip()
            return None

        _create_rem = (_starts_with_any(_text_lower, _note_create_ru)
                       or _starts_with_any(_text_lower, _note_create_en))
        _read_rem   = (_starts_with_any(_text_lower, _note_read_ru)
                       or _starts_with_any(_text_lower, _note_read_en))

        if _create_rem is not None and not _is_guest(chat_id):
            note_title   = _create_rem.strip() or _t(chat_id, "note_voice_default_title")
            note_slug    = _slug(note_title)
            note_content = f"# {note_title}\n\n(голосовая заметка / voice note)\n{text}"
            _save_note_file(chat_id, note_slug, note_content)
            reply = _t(chat_id, "note_voice_saved", title=note_title)
            _safe_edit(chat_id, msg.message_id,
                       f"📝 *Заметка / Note:* _{_escape_md(text)}_\n\n{_escape_md(reply)}",
                       parse_mode="Markdown",
                       reply_markup=_voice_back_keyboard(chat_id))
            audio_on = (not opts.get("user_audio_toggle")
                        or _st._user_audio.get(chat_id, True))
            if audio_on:
                ogg = _tts_to_ogg(reply, lang=_voice_lang(chat_id))
                if ogg:
                    bot.send_voice(chat_id, io.BytesIO(ogg))
            return

        if _read_rem is not None and not _is_guest(chat_id):
            notes = _list_notes_for(chat_id)
            match = None
            if _read_rem:
                for n in notes:
                    if _read_rem in n["title"].lower() or _read_rem in n["slug"]:
                        match = n
                        break
            if not match and notes:
                match = notes[0]
            if not match:
                reply2 = _t(chat_id, "note_voice_read_notfound")
                _safe_edit(chat_id, msg.message_id, _escape_md(reply2),
                           parse_mode="Markdown",
                           reply_markup=_voice_back_keyboard(chat_id))
                return
            note_body  = _load_note_text(chat_id, match["slug"]) or ""
            note_plain = _escape_tts(note_body)
            _safe_edit(chat_id, msg.message_id,
                       f"📄 *{_escape_md(match['title'])}*\n\n{_escape_md(note_body)}",
                       parse_mode="Markdown",
                       reply_markup=_voice_back_keyboard(chat_id))
            audio_on3 = (not opts.get("user_audio_toggle")
                         or _st._user_audio.get(chat_id, True))
            if audio_on3:
                tts3 = bot.send_message(chat_id, _t(chat_id, "gen_audio"),
                                        parse_mode="Markdown")
                ogg3 = _tts_to_ogg(note_plain, lang=_voice_lang(chat_id))
                if ogg3:
                    bot.send_voice(chat_id, io.BytesIO(ogg3),
                                   caption=_t(chat_id, "audio_caption"))
                    bot.delete_message(chat_id, tts3.message_id)
                else:
                    _safe_edit(chat_id, tts3.message_id,
                               _t(chat_id, "audio_na"), parse_mode="Markdown")
            return

        # ── Show transcript, call taris ─────────────────────────────────────
        # Strip [?word] markers for display — clean text shown to user,
        # but full text with markers is sent to LLM so it can fill gaps.
        _clean_text = re.sub(r'\[\?([^\]]*)\]', r'\1', text).strip()
        _safe_edit(chat_id, msg.message_id,
                   _t(chat_id, "you_said", text=_clean_text),
                   parse_mode="Markdown")

        # ── Save last transcript for web UI display ────────────────────────────
        try:
            _last_t_path = Path(TARIS_DIR) / "last_transcript.txt"
            _last_t_path.write_text(
                f"[telegram] {time.strftime('%Y-%m-%d %H:%M')}  {_clean_text}",
                encoding="utf-8",
            )
        except Exception:
            pass

        # ── System chat mode: route to system handler (admin-only, role-aware) ──
        # Guard at routing level (mirrors text-mode handling in telegram_menu_bot.py)
        if _cur_mode == "system":
            if not _is_admin(chat_id):
                _st._user_mode.pop(chat_id, None)
                _safe_edit(chat_id, msg.message_id,
                            _t(chat_id, "security_admin_only"),
                            reply_markup=_back_keyboard())
                log.warning(f"[Security] non-admin voice system-chat attempt chat_id={chat_id}")
                return
            from telegram.bot_handlers import _handle_system_message
            _handle_system_message(chat_id, _clean_text)
            return

        # Security L1: reject injection attempts before sending to LLM
        from security.bot_security import _check_injection
        _is_inj, _inj_reason = _check_injection(text)
        if _is_inj:
            log.warning(f"[Security] voice injection blocked chat_id={chat_id}")
            _safe_edit(chat_id, msg.message_id,
                       _t(chat_id, "security_blocked"),
                       parse_mode="Markdown",
                       reply_markup=_back_keyboard())
            return

        _ts = time.time()
        response = ask_llm(_with_lang_voice(chat_id, text), timeout=90)
        _timing["LLM"] = time.time() - _ts

        if not response:
            response = _t(chat_id, "no_answer")

        # ── Text answer ───────────────────────────────────────────────────────
        audio_on = (not opts.get("user_audio_toggle")
                    or _st._user_audio.get(chat_id, True))
        _tts_result: list = [None]
        _tts_thread = None
        if audio_on and opts.get("parallel_tts"):
            def _bg_tts():
                _tts_result[0] = _tts_to_ogg(response, lang=_voice_lang(chat_id))
            _tts_thread = threading.Thread(target=_bg_tts, daemon=True)
            _tts_thread.start()

        try:
            bot.send_message(
                chat_id,
                f"🤖 *Taris:*\n{_escape_md(_truncate(response))}{_fmt_timing()}",
                parse_mode="Markdown",
                reply_markup=_voice_back_keyboard(chat_id),
            )
        except Exception:
            bot.send_message(
                chat_id,
                f"Taris:\n{_truncate(response)}{_fmt_timing()}",
                parse_mode=None,
                reply_markup=_voice_back_keyboard(chat_id),
            )

        if audio_on:
            tts_msg = None
            try:
                tts_msg = bot.send_message(chat_id, _t(chat_id, "gen_audio"),
                                           parse_mode="Markdown")
                _save_pending_tts(chat_id, tts_msg.message_id)
                _ts = time.time()
                if _tts_thread is not None:
                    _tts_thread.join(timeout=160)   # piper 120s + ffmpeg 30s + slack
                    ogg = _tts_result[0]
                else:
                    ogg = _tts_to_ogg(response, lang=_voice_lang(chat_id))
                _timing["TTS"] = time.time() - _ts

                if ogg:
                    caption = _t(chat_id, "audio_caption") + _fmt_timing()
                    bot.send_voice(chat_id, io.BytesIO(ogg), caption=caption)
                    bot.delete_message(chat_id, tts_msg.message_id)
                    tts_msg = None
                else:
                    _safe_edit(chat_id, tts_msg.message_id,
                               _t(chat_id, "audio_na"), parse_mode="Markdown")
                    tts_msg = None
            except Exception as e:
                log.warning(f"[TTS] block error: {e}")
            finally:
                _clear_pending_tts(chat_id)
                if tts_msg is not None:
                    try:
                        _safe_edit(chat_id, tts_msg.message_id,
                                   _t(chat_id, "audio_error", e="generation failed"),
                                   parse_mode="Markdown")
                    except Exception:
                        pass

    threading.Thread(target=_run, daemon=True).start()
