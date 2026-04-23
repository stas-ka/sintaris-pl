"""device_variant.py — VariantConfig dataclass for DEVICE_VARIANT abstraction.

§30.3: Replace scattered ``if DEVICE_VARIANT == "openclaw"`` checks with a
single ``VariantConfig`` object built at startup.

Usage::

    from core.device_variant import VARIANT
    if VARIANT.has_openclaw: ...
    stt = VARIANT.default_stt    # "vosk" | "faster_whisper"

Adding a new variant = one entry in VARIANT_REGISTRY, no code changes elsewhere.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VariantConfig:
    """Static capability profile for a deployment variant.

    Evaluated once at startup; no env-var access after import.
    """
    name: str                    # "taris" | "openclaw"
    default_stt: str             # "vosk" | "faster_whisper"
    default_llm: str             # "taris" | "ollama"
    has_pgvector: bool           # PostgreSQL + pgvector (OpenClaw only)
    has_openclaw: bool           # OpenClaw AI gateway present
    has_vosk: bool               # Vosk STT installed / expected
    vosk_fallback_default: bool  # Fall back to Vosk when primary STT returns nothing


VARIANT_REGISTRY: dict[str, VariantConfig] = {
    "taris": VariantConfig(
        name="taris",
        default_stt="vosk",
        default_llm="taris",
        has_pgvector=False,
        has_openclaw=False,
        has_vosk=True,
        vosk_fallback_default=True,
    ),
    "openclaw": VariantConfig(
        name="openclaw",
        default_stt="faster_whisper",
        default_llm="ollama",
        has_pgvector=True,
        has_openclaw=True,
        has_vosk=False,
        vosk_fallback_default=False,
    ),
}


def get_variant(device_variant: str) -> VariantConfig:
    """Return VariantConfig for *device_variant*; falls back to 'taris' if unknown."""
    return VARIANT_REGISTRY.get(device_variant, VARIANT_REGISTRY["taris"])


# ── Module-level singleton — resolved from DEVICE_VARIANT at import time ──────
# Normalise picoclaw → taris (same alias logic as bot_config.py)
_dv_raw = os.environ.get("DEVICE_VARIANT", "taris").lower()
_dv = "taris" if _dv_raw == "picoclaw" else _dv_raw
VARIANT: VariantConfig = get_variant(_dv)
