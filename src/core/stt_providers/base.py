"""stt_providers/base.py — STTProvider Protocol definition (§30.2)."""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class STTProvider(Protocol):
    """Interface every STT provider must implement.

    ``transcribe(raw_pcm, sample_rate, lang) -> Optional[str]``
    Returns transcript text or None when no speech detected.
    """

    def transcribe(self, raw_pcm: bytes, sample_rate: int, lang: str = "ru") -> Optional[str]:
        """Transcribe raw S16LE PCM audio to text.

        Args:
            raw_pcm:     Raw 16-bit LE PCM audio bytes.
            sample_rate: Audio sample rate in Hz (typically 16000).
            lang:        Language hint: ``'ru'`` | ``'en'`` | ``'de'`` | ``'sl'``.

        Returns:
            Transcript string or ``None`` if no speech detected.
        """
        ...
