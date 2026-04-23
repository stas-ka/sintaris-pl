"""stt_providers/faster_whisper_stt.py — Faster-Whisper CTranslate2 STT provider (§30.2)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.bot_config import (
    FASTER_WHISPER_COMPUTE, FASTER_WHISPER_DEVICE, FASTER_WHISPER_MODEL,
    FASTER_WHISPER_SPEECH_PAD_MS, FASTER_WHISPER_THREADS,
    log_voice as log,
)

_HALLUCINATIONS = {
    "and that's the whole thing", "thank you", "thanks for watching",
    "thanks for watching!", "you", ".", "..", "...",
}

# Module-level model cache shared across all FasterWhisperSTT instances
_fw_model_cache: dict = {}


def preload() -> None:
    """Preload the faster-whisper model into memory at startup.

    Called in a background thread to eliminate ~0.3-1s cold-start on first voice message.
    """
    try:
        import numpy as _np
        silence_pcm = _np.zeros(8000, dtype=_np.int16).tobytes()
        FasterWhisperSTT().transcribe(silence_pcm, 16000, "ru")
        log.info("[FasterWhisper] model preloaded at startup — first voice call will be fast")
    except Exception as exc:
        log.debug(f"[FasterWhisper] startup preload skipped: {exc}")


class FasterWhisperSTT:
    """Faster-Whisper CTranslate2 speech-to-text provider.

    Model loaded once and cached for process lifetime.
    Config: FASTER_WHISPER_MODEL, FASTER_WHISPER_DEVICE, FASTER_WHISPER_COMPUTE.
    """

    def transcribe(self, raw_pcm: bytes, sample_rate: int, lang: str = "ru") -> Optional[str]:
        """Transcribe raw S16LE PCM using faster-whisper.

        Returns transcript or None on no speech / error.
        """
        try:
            from faster_whisper import WhisperModel  # type: ignore[import]
        except ImportError:
            log.debug("[FasterWhisper] not installed — pip install faster-whisper")
            return None

        try:
            import numpy as _np
            import os as _os

            cache_key = (FASTER_WHISPER_MODEL, FASTER_WHISPER_DEVICE,
                         FASTER_WHISPER_COMPUTE, FASTER_WHISPER_THREADS)
            if cache_key not in _fw_model_cache:
                _cpu_threads = FASTER_WHISPER_THREADS or _os.cpu_count() or 4
                if not FASTER_WHISPER_THREADS:
                    _cpu_threads = min(_cpu_threads, 8)
                log.info(
                    f"[FasterWhisper] Loading model={FASTER_WHISPER_MODEL} "
                    f"device={FASTER_WHISPER_DEVICE} compute={FASTER_WHISPER_COMPUTE} "
                    f"threads={_cpu_threads}"
                )
                _FW_ALIASES: dict = {"turbo": "large-v3-turbo", "large": "large-v3"}
                model_arg = FASTER_WHISPER_MODEL
                _hf = Path.home() / ".cache" / "huggingface" / "hub"
                if "/" in FASTER_WHISPER_MODEL:
                    _org, _repo = FASTER_WHISPER_MODEL.split("/", 1)
                    _model_dir = _hf / f"models--{_org}--{_repo}"
                else:
                    _resolved = _FW_ALIASES.get(FASTER_WHISPER_MODEL, FASTER_WHISPER_MODEL)
                    _model_dir = _hf / f"models--Systran--faster-whisper-{_resolved}"
                    if not (_model_dir / "snapshots").is_dir() and "turbo" in _resolved:
                        _model_dir = _hf / f"models--mobiuslabsgmbh--faster-whisper-{_resolved}"
                _snaps = _model_dir / "snapshots"
                if _snaps.is_dir():
                    _snap_list = sorted(_snaps.iterdir())
                    if _snap_list:
                        model_arg = str(_snap_list[-1])
                        log.info(f"[FasterWhisper] using local cache: {model_arg}")
                if model_arg != FASTER_WHISPER_MODEL:
                    _os.environ.setdefault("HF_HUB_OFFLINE", "1")
                _fw_model_cache[cache_key] = WhisperModel(
                    model_arg,
                    device=FASTER_WHISPER_DEVICE,
                    compute_type=FASTER_WHISPER_COMPUTE,
                    cpu_threads=_cpu_threads,
                )
            model = _fw_model_cache[cache_key]

            audio_np = _np.frombuffer(raw_pcm, dtype=_np.int16).astype(_np.float32) / 32768.0
            if sample_rate != 16000:
                from scipy.signal import resample as _resample  # type: ignore[import]
                target_len = int(len(audio_np) * 16000 / sample_rate)
                audio_np = _resample(audio_np, target_len).astype(_np.float32)

            lang_map = {"ru": "ru", "en": "en", "de": "de", "sl": "sl"}
            fw_lang = lang_map.get(lang) if lang else None

            segments, info = model.transcribe(
                audio_np, language=fw_lang, beam_size=5, vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500,
                                    speech_pad_ms=FASTER_WHISPER_SPEECH_PAD_MS),
                condition_on_previous_text=False, without_timestamps=True,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()

            if not text:
                log.debug("[FasterWhisper] VAD pass empty — retrying without VAD")
                segments, info = model.transcribe(
                    audio_np, language=fw_lang, beam_size=5, vad_filter=False,
                    condition_on_previous_text=False, without_timestamps=True,
                )
                text = " ".join(seg.text.strip() for seg in segments).strip()

            if not text:
                log.debug("[FasterWhisper] no speech detected")
                return None

            if text.lower().rstrip(".!? ") in _HALLUCINATIONS or len(text) < 3:
                log.warning(f"[FasterWhisper] hallucination rejected: {text!r}")
                return None

            log.info(f"[FasterWhisper] transcript lang={info.language} "
                     f"prob={info.language_probability:.2f}: {text[:120]}")
            return text

        except Exception as exc:
            log.warning(f"[FasterWhisper] error: {exc}")
            return None
