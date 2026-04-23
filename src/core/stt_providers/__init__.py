"""stt_providers/__init__.py — STT provider registry (§30.2).

Exports the ``STTProvider`` Protocol and ``stt_factory()`` function.

Usage::

    from core.stt_providers import stt_factory
    stt = stt_factory(STT_PROVIDER)
    text = stt.transcribe(raw_pcm, sample_rate, lang="ru")
"""
from __future__ import annotations

from core.stt_providers.base import STTProvider  # noqa: F401 (re-exported)
from core.stt_providers.faster_whisper_stt import FasterWhisperSTT
from core.stt_providers.vosk_stt import VoskSTT


def stt_factory(provider: str) -> STTProvider:
    """Return the STT provider instance for *provider* name.

    ``provider`` values: ``"faster_whisper"`` | ``"vosk"`` | any other string
    defaults to VoskSTT for backward compatibility.
    """
    if provider == "faster_whisper":
        return FasterWhisperSTT()
    return VoskSTT()


__all__ = ["STTProvider", "stt_factory", "FasterWhisperSTT", "VoskSTT"]
