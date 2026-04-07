from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResponse:
    """Unified response from any LLM provider."""

    text: str
    raw: object = field(default=None, repr=False)


@dataclass(frozen=True)
class MultimodalPart:
    """A single part of a multimodal prompt (text or image bytes)."""

    text: str | None = None
    image_bytes: bytes | None = field(default=None, repr=False)
    mime_type: str = "image/jpeg"


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-agnostic LLM interface.

    Implementations exist for Gemini, OpenAI, and Anthropic.
    """

    async def generate_text(
        self,
        *,
        model: str,
        system: str,
        contents: str | list[MultimodalPart],
        temperature: float = 1.0,
        max_retries: int = 3,
        initial_backoff: float = 5.0,
    ) -> LLMResponse: ...

    async def generate_json(
        self,
        *,
        model: str,
        system: str,
        contents: str | list[MultimodalPart],
        temperature: float = 0.3,
        max_retries: int = 3,
        initial_backoff: float = 5.0,
    ) -> LLMResponse: ...

    async def embed(
        self,
        *,
        texts: list[str],
        model: str = "",
    ) -> list[list[float]]: ...


def create_llm_provider(
    *,
    provider_name: str = "",
    model: str = "",
) -> LLMProvider:
    """Create an LLM provider from env vars or explicit overrides.

    Reads ``LLM_PROVIDER`` (gemini|openai|anthropic) and ``LLM_MODEL``.
    Defaults to ``gemini`` / ``gemini-2.5-flash`` for backward compatibility.
    """
    name = (provider_name or os.getenv("LLM_PROVIDER", "gemini")).lower().strip()
    resolved_model = model or os.getenv("LLM_MODEL", "")

    match name:
        case "gemini":
            from marketmenow.integrations.providers.gemini import GeminiProvider

            return GeminiProvider(model=resolved_model or "gemini-2.5-flash")
        case "openai":
            from marketmenow.integrations.providers.openai import OpenAIProvider

            return OpenAIProvider(model=resolved_model or "gpt-4o")
        case "anthropic":
            from marketmenow.integrations.providers.anthropic import AnthropicProvider

            return AnthropicProvider(model=resolved_model or "claude-sonnet-4-20250514")
        case _:
            raise ValueError(
                f"Unknown LLM_PROVIDER={name!r}. Supported: gemini, openai, anthropic."
            )
