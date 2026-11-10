"""LLM providers.  Each returns the raw JSON text of a feedback object."""

from __future__ import annotations

import os
from typing import Protocol


class ProviderError(RuntimeError):
    """The provider could not produce a usable response (network, refusal, bad JSON...)."""


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, system: str, user: str, schema: dict) -> str: ...


def create_provider() -> LLMProvider | None:
    """Pick a provider from environment variables (``LLM_PROVIDER``).

    * ``anthropic`` - Claude via the official SDK (credentials: ANTHROPIC_API_KEY,
      ANTHROPIC_AUTH_TOKEN or an ``ant auth login`` profile).
    * ``ollama`` - a local open-source model served by Ollama (``OLLAMA_HOST``).
    * ``rule_based`` / ``none`` - no LLM; deterministic templates.
    * ``auto`` (default) - anthropic if an API key/token is set, else ollama if
      OLLAMA_HOST is set, else rule-based.
    """
    choice = os.environ.get("LLM_PROVIDER", "auto").lower()
    if choice in {"rule_based", "none", "off"}:
        return None
    if choice == "auto":
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            choice = "anthropic"
        elif os.environ.get("OLLAMA_HOST"):
            choice = "ollama"
        else:
            return None
    if choice == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if choice == "ollama":
        from .ollama_provider import OllamaProvider

        return OllamaProvider()
    raise ValueError(f"unknown LLM_PROVIDER {choice!r}")
