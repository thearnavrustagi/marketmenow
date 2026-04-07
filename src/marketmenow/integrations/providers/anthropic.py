from __future__ import annotations

import base64
import logging
import os

from marketmenow.integrations.llm import LLMResponse, MultimodalPart
from marketmenow.integrations.retry import with_retry

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider:
    """LLMProvider backed by the Anthropic API."""

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        *,
        api_key: str = "",
    ) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ImportError(
                "Anthropic SDK not installed. Run: uv sync --extra anthropic"
            ) from exc

        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not resolved_key:
            raise ValueError("Missing Anthropic API key. Set ANTHROPIC_API_KEY.")

        self._client = AsyncAnthropic(api_key=resolved_key)
        self._default_model = model

    async def generate_text(
        self,
        *,
        model: str,
        system: str,
        contents: str | list[MultimodalPart],
        temperature: float = 1.0,
        max_retries: int = 3,
        initial_backoff: float = 5.0,
    ) -> LLMResponse:
        resolved_model = model or self._default_model
        messages = _build_messages(contents)

        async def _call() -> LLMResponse:
            response = await self._client.messages.create(
                model=resolved_model,
                system=system,
                messages=messages,
                temperature=temperature,
                max_tokens=4096,
            )
            text = response.content[0].text if response.content else ""
            return LLMResponse(text=text.strip(), raw=response)

        return await with_retry(
            _call,
            max_retries=max_retries,
            initial_backoff=initial_backoff,
            retry_logger=logger,
            context=f"anthropic/{resolved_model}",
        )

    async def generate_json(
        self,
        *,
        model: str,
        system: str,
        contents: str | list[MultimodalPart],
        temperature: float = 0.3,
        max_retries: int = 3,
        initial_backoff: float = 5.0,
    ) -> LLMResponse:
        resolved_model = model or self._default_model

        json_system = (
            f"{system}\n\n"
            "IMPORTANT: You must respond with ONLY valid JSON. "
            "No markdown fences, no explanation, no text before or after the JSON."
        )

        # Use prefill to encourage JSON output
        user_messages = _build_messages(contents)
        user_messages.append({"role": "assistant", "content": "{"})

        async def _call() -> LLMResponse:
            response = await self._client.messages.create(
                model=resolved_model,
                system=json_system,
                messages=user_messages,
                temperature=temperature,
                max_tokens=4096,
            )
            text = response.content[0].text if response.content else ""
            # Prepend the prefill "{" that we used
            full_json = "{" + text.strip()
            return LLMResponse(text=full_json, raw=response)

        return await with_retry(
            _call,
            max_retries=max_retries,
            initial_backoff=initial_backoff,
            retry_logger=logger,
            context=f"anthropic-json/{resolved_model}",
        )

    async def embed(
        self,
        *,
        texts: list[str],
        model: str = "",
    ) -> list[list[float]]:
        raise NotImplementedError(
            "Anthropic does not provide an embedding API. "
            "Use LLM_PROVIDER=gemini or LLM_PROVIDER=openai for embeddings."
        )


def _build_messages(
    contents: str | list[MultimodalPart],
) -> list[dict[str, object]]:
    """Convert our content types into Anthropic message format."""
    if isinstance(contents, str):
        return [{"role": "user", "content": contents}]

    parts: list[dict[str, object]] = []
    for part in contents:
        if part.image_bytes is not None:
            b64 = base64.b64encode(part.image_bytes).decode("ascii")
            parts.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": part.mime_type,
                        "data": b64,
                    },
                }
            )
        if part.text is not None:
            parts.append({"type": "text", "text": part.text})

    return [{"role": "user", "content": parts}]
