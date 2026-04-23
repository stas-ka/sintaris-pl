"""stt_providers/vosk_stt.py — Vosk offline STT provider (§30.2)."""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Optional

from core.bot_config import VOSK_MODEL_DE_PATH, VOSK_MODEL_PATH, log_voice as log

# Conf threshold below which words are marked uncertain
_STT_CONF_THRESHOLD = 0.65


class VoskSTT:
    """Vosk offline speech-to-text provider.

    Model is loaded lazily on first call and cached per language.
    Requires: vosk package + model directory (see VOSK_MODEL_PATH).
    """

    def transcribe(self, raw_pcm: bytes, sample_rate: int, lang: str = "ru") -> Optional[str]:
        """Transcribe raw S16LE PCM using Vosk KaldiRecognizer.

        Returns transcript text with low-confidence words wrapped in [?word],
        or None if nothing recognised.
        """
        try:
            import vosk as _vosk_lib
            _vosk_lib.SetLogLevel(-1)
            model = self._get_model(lang)
        except ImportError:
            log.debug("[Vosk] vosk not installed — pip install vosk")
            return None
        except Exception as exc:
            log.warning(f"[Vosk] model load error: {exc}")
            return None

        try:
            rec = _vosk_lib.KaldiRecognizer(model, sample_rate)
            rec.SetWords(True)
            chunk = 4000 * 2 * sample_rate // 16000
            for i in range(0, len(raw_pcm), chunk):
                rec.AcceptWaveform(raw_pcm[i:i + chunk])
            final = _json.loads(rec.FinalResult())
            words = final.get("result", [])
            if words:
                parts = []
                low_conf = 0
                for w in words:
                    conf = w.get("conf", 1.0)
                    word = w.get("word", "")
                    if conf < _STT_CONF_THRESHOLD:
                        parts.append(f"[?{word}]")
                        low_conf += 1
                    else:
                        parts.append(word)
                text = " ".join(parts).strip()
                if low_conf:
                    log.debug(f"[Vosk] {low_conf}/{len(words)} words below conf={_STT_CONF_THRESHOLD}")
                return text or None
            return final.get("text", "").strip() or None
        except Exception as exc:
            log.warning(f"[Vosk] transcription error: {exc}")
            return None

    # ── Model cache (per language, process lifetime) ──────────────────────────
    _model_cache: dict = {}

    def _get_model(self, lang: str):
        if lang not in self._model_cache:
            import vosk as _vosk_lib
            model_path = VOSK_MODEL_DE_PATH if lang == "de" else VOSK_MODEL_PATH
            if not Path(model_path).is_dir():
                log.warning(f"[Vosk] model not found for lang={lang}: {model_path}, falling back to ru")
                model_path = VOSK_MODEL_PATH
            self._model_cache[lang] = _vosk_lib.Model(model_path)
        return self._model_cache[lang]
