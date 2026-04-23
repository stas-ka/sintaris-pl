"""llm_providers/__init__.py — LLM provider registry (§30.1).

Exports the ``LLMProvider`` Protocol and a ``REGISTRY`` dict mapping provider
names to callable objects.  ``bot_llm.py`` uses this registry to build
``_DISPATCH`` without containing the provider implementations.

Usage::

    from core.llm_providers import REGISTRY
    fn = REGISTRY.get("ollama")
    text = fn(prompt, timeout)
"""
from __future__ import annotations

from core.llm_providers.base import LLMProvider  # noqa: F401 (re-exported)

# Import provider ask() functions
from core.llm_providers import (
    anthropic,
    copilot,
    gemini,
    local,
    ollama,
    openclaw,
    openai_p,
    taris_p,
    yandexgpt,
)

# Public registry — maps provider name → callable(prompt, timeout) -> str
REGISTRY: dict[str, LLMProvider] = {
    "taris":     taris_p.ask,
    "openclaw":  openclaw.ask,
    "copilot":   copilot.ask,
    "openai":    openai_p.ask,
    "yandexgpt": yandexgpt.ask,
    "gemini":    gemini.ask,
    "anthropic": anthropic.ask,
    "local":     local.ask,
    "ollama":    ollama.ask,  # type: ignore[assignment]  (has extra chat_id kwarg)
}

__all__ = ["LLMProvider", "REGISTRY"]
