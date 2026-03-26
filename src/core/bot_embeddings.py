"""
Embedding Service — lazy-loaded text-to-vector encoder.

Priority:
  1. fastembed  (ONNX Runtime based — ARM-safe, no PyTorch required)
  2. sentence-transformers (PyTorch — works on x86_64, heavy on Pi)
  3. None       — embedding generation silently disabled; FTS5-only mode.

Controlled by bot_config constants:
  EMBED_MODEL          — HuggingFace model name (empty → disable)
  EMBED_KEEP_RESIDENT  — keep model in RAM between calls (default True)
  EMBED_DIMENSION      — expected output dimension (default 384)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.core.bot_config import EMBED_DIMENSION, EMBED_KEEP_RESIDENT, EMBED_MODEL

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


class EmbeddingService:
    """
    Wraps fastembed or sentence-transformers behind a single interface.

    Usage:
        svc = EmbeddingService.get()
        if svc:
            vec = svc.embed("some text")
    """

    _instance: "EmbeddingService | None" = None

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None          # loaded on first use
        self._backend: str = "none"
        self._keep_resident = EMBED_KEEP_RESIDENT
        self._try_load()

    # ─── public API ─────────────────────────────────────────────────────────

    def embed(self, text: str) -> list[float] | None:
        """Return a 384-dim embedding for *text*, or None on failure."""
        vecs = self.embed_batch([text])
        return vecs[0] if vecs else None

    def embed_batch(self, texts: list[str]) -> list[list[float]] | None:
        """Return embeddings for a list of texts, or None on failure."""
        if not texts:
            return []
        model = self._get_model()
        if model is None:
            return None
        try:
            if self._backend == "fastembed":
                vecs = list(model.embed(texts))
                result = [v.tolist() for v in vecs]
            else:  # sentence-transformers
                result = model.encode(texts, show_progress_bar=False).tolist()
            if not self._keep_resident:
                self._model = None
            return result
        except Exception as exc:
            log.warning("[Embeddings] inference error: %s", exc)
            return None

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def dimension(self) -> int:
        return EMBED_DIMENSION

    # ─── singleton ──────────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "EmbeddingService | None":
        """Return the module-level singleton, or None if model is unavailable."""
        if cls._instance is not None:
            return cls._instance
        if not EMBED_MODEL:
            log.debug("[Embeddings] EMBED_MODEL is empty — disabled")
            return None
        svc = cls(EMBED_MODEL)
        if svc.backend == "none":
            return None
        cls._instance = svc
        return svc

    @classmethod
    def reset(cls) -> None:
        """Release singleton (used in tests)."""
        cls._instance = None

    # ─── internals ──────────────────────────────────────────────────────────

    def _try_load(self) -> None:
        """Attempt to import and initialise the embedding library."""
        # Try fastembed first — ONNX Runtime based, no PyTorch, ARM-safe.
        try:
            from fastembed import TextEmbedding  # type: ignore[import]
            self._model = TextEmbedding(model_name=self._model_name)
            self._backend = "fastembed"
            log.info("[Embeddings] fastembed loaded: %s", self._model_name)
            return
        except ImportError:
            log.debug("[Embeddings] fastembed not installed, trying sentence-transformers")
        except Exception as exc:
            log.warning("[Embeddings] fastembed init error (%s): %s", self._model_name, exc)

        # Fall back to sentence-transformers (PyTorch, heavier but ubiquitous on x86_64).
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
            self._model = SentenceTransformer(self._model_name)
            self._backend = "sentence-transformers"
            log.info("[Embeddings] sentence-transformers loaded: %s", self._model_name)
            return
        except ImportError:
            log.debug("[Embeddings] sentence-transformers not installed — embeddings disabled")
        except Exception as exc:
            log.warning("[Embeddings] sentence-transformers init error (%s): %s",
                        self._model_name, exc)

        log.warning(
            "[Embeddings] no embedding backend available for '%s' — "
            "install fastembed or sentence-transformers to enable semantic search.",
            self._model_name,
        )
        self._backend = "none"

    def _get_model(self):
        """Return the loaded model, triggering a reload if keep_resident is False."""
        if self._model is None and self._backend != "none":
            self._try_load()
        return self._model
