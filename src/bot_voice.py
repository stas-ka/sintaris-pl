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
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import bot_state as _st
from bot_config import (
    PIPER_BIN, PIPER_MODEL, PIPER_MODEL_TMPFS, PIPER_MODEL_LOW,
    VOSK_MODEL_PATH, VOICE_SAMPLE_RATE, VOICE_CHUNK_SIZE,
    TTS_MAX_CHARS, VOICE_TIMING_DEBUG,
    WHISPER_BIN, WHISPER_MODEL,
    _PENDING_TTS_FILE, log,
)
from bot_instance import bot
from bot_access import (
    _t, _safe_edit, _back_keyboard, _voice_back_keyboard,
    _escape_tts, _escape_md, _truncate, _with_lang_voice, _ask_picoclaw,
    _is_guest,
)
from bot_users import (
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

def _get_vosk_model():
    """Lazy-load the Vosk Russian model (singleton)."""
    if _st._vosk_model_cache is None:
        import vosk as _vosk_lib
        _vosk_lib.SetLogLevel(-1)
        _st._vosk_model_cache = _vosk_lib.Model(VOSK_MODEL_PATH)
    return _st._vosk_model_cache


# ─────────────────────────────────────────────────────────────────────────────
# Piper — model selection and warmup
# ─────────────────────────────────────────────────────────────────────────────

def _piper_model_path() -> str:
    """
    Return the effective Piper ONNX model path.
    Priority: tmpfs (RAM disk) → low model → medium (default).
    """
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
            size_mb = os.path.getsize(PIPER_MODEL_TMPFS) / 1024 / 1024
            log.info(f"[VoiceOpt] tmpfs_model: done ({size_mb:.0f} MB in RAM, ~10× faster reads)")
        except Exception as e:
            log.warning(f"[VoiceOpt] tmpfs_model: copy failed: {e}")
            _st._voice_opts["tmpfs_model"] = False
            from bot_state import _save_voice_opts
            _save_voice_opts()
    else:
        try:
            if os.path.exists(PIPER_MODEL_TMPFS):
                os.unlink(PIPER_MODEL_TMPFS)
                log.info(f"[VoiceOpt] tmpfs_model: removed {PIPER_MODEL_TMPFS}")
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

        result = subprocess.run(
            [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", tmp_path,
             "-l", "ru", "--no-timestamps", "-otxt"],
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
        return text if text else None

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
# TTS — Piper → raw PCM → ffmpeg → OGG Opus
# ─────────────────────────────────────────────────────────────────────────────

def _tts_to_ogg(text: str) -> Optional[bytes]:
    """
    Synthesise text with Piper TTS, encode with ffmpeg as OGG Opus.
    Returns bytes for bot.send_voice(), or None on failure.

    Two sequential subprocess.run() calls (not Popen pipe) to avoid
    the deadlock where parent holds piper.stdout open → ffmpeg blocks on stdin EOF.
    """
    tts_text = _escape_tts(text)

    # Trim to whole sentences, then hard-cap at TTS_MAX_CHARS
    if len(tts_text) > TTS_MAX_CHARS:
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
            [PIPER_BIN, "--model", _piper_model_path(), "--output-raw"],
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
        → [notes cmd] or [picoclaw LLM] → text + Piper TTS OGG.

    Runs in a background thread so the Telegram handler returns immediately.
    """
    msg = bot.send_message(chat_id, _t(chat_id, "recognizing"), parse_mode="Markdown")

    def _run():
        _timing: dict[str, float] = {}

        def _fmt_timing() -> str:
            if not VOICE_TIMING_DEBUG or not _timing:
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

        # ── STT: whisper.cpp (§5.3) or Vosk (default / fallback) ─────────────
        _ts = time.time()
        text = ""
        if opts.get("whisper_stt"):
            text = _stt_whisper(raw_pcm, _srate) or ""
            if text:
                log.debug(f"[WhisperSTT] transcript: {text[:80]}")
            else:
                log.warning("[WhisperSTT] no result — falling back to Vosk")

        if not text:
            STT_CONF_THRESHOLD = 0.65
            try:
                import vosk as _vosk_lib
                import json as _json
                model = _get_vosk_model()
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
                ogg = _tts_to_ogg(reply)
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
                ogg3 = _tts_to_ogg(note_plain)
                if ogg3:
                    bot.send_voice(chat_id, io.BytesIO(ogg3),
                                   caption=_t(chat_id, "audio_caption"))
                    bot.delete_message(chat_id, tts3.message_id)
                else:
                    _safe_edit(chat_id, tts3.message_id,
                               _t(chat_id, "audio_na"), parse_mode="Markdown")
            return

        # ── Show transcript, call picoclaw ─────────────────────────────────────
        _safe_edit(chat_id, msg.message_id,
                   _t(chat_id, "you_said", text=text),
                   parse_mode="Markdown")

        _ts = time.time()
        response = _ask_picoclaw(_with_lang_voice(chat_id, text), timeout=90)
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
                _tts_result[0] = _tts_to_ogg(response)
            _tts_thread = threading.Thread(target=_bg_tts, daemon=True)
            _tts_thread.start()

        try:
            bot.send_message(
                chat_id,
                f"🤖 *Picoclaw:*\n{_escape_md(_truncate(response))}{_fmt_timing()}",
                parse_mode="Markdown",
                reply_markup=_voice_back_keyboard(chat_id),
            )
        except Exception:
            bot.send_message(
                chat_id,
                f"Picoclaw:\n{_truncate(response)}{_fmt_timing()}",
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
                    ogg = _tts_to_ogg(response)
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
