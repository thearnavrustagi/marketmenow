from __future__ import annotations

import base64
import logging
import os

from marketmenow.integrations.llm import LLMResponse, MultimodalPart
from marketmenow.integrations.retry import with_retry

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o"
_DEFAULT_EMBED_MODEL = "text-embedding-3-small"


class OpenAIProvider:
    """LLMProvider backed by the OpenAI API."""

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        *,
        api_key: str = "",
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("OpenAI SDK not installed. Run: uv sync --extra openai") from exc

        resolved_key = (
            api_key or os.getenv("OPENAI_LLM_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
        )
        if not resolved_key:
            raise ValueError("Missing OpenAI API key. Set OPENAI_LLM_API_KEY or OPENAI_API_KEY.")

        self._client = AsyncOpenAI(api_key=resolved_key)
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
        messages = _build_messages(system, contents)

        async def _call() -> LLMResponse:
            response = await self._client.chat.completions.create(
                model=resolved_model,
                messages=messages,
                temperature=temperature,
            )
            text = response.choices[0].message.content or ""
            return LLMResponse(text=text.strip(), raw=response)

        return await with_retry(
            _call,
            max_retries=max_retries,
            initial_backoff=initial_backoff,
            retry_logger=logger,
            context=f"openai/{resolved_model}",
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
        messages = _build_messages(system, contents)

        async def _call() -> LLMResponse:
            response = await self._client.chat.completions.create(
                model=resolved_model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or ""
            return LLMResponse(text=text.strip(), raw=response)

        return await with_retry(
            _call,
            max_retries=max_retries,
            initial_backoff=initial_backoff,
            retry_logger=logger,
            context=f"openai-json/{resolved_model}",
        )

    async def embed(
        self,
        *,
        texts: list[str],
        model: str = "",
    ) -> list[list[float]]:
        resolved_model = model or _DEFAULT_EMBED_MODEL
        response = await self._client.embeddings.create(
            model=resolved_model,
            input=texts,
        )
        return [item.embedding for item in response.data]


def _build_messages(
    system: str,
    contents: str | list[MultimodalPart],
) -> list[dict[str, object]]:
    """Convert our content types into OpenAI message format."""
    messages: list[dict[str, object]] = []

    if system:
        messages.append({"role": "system", "content": system})

    if isinstance(contents, str):
        messages.append({"role": "user", "content": contents})
    else:
        parts: list[dict[str, object]] = []
        for part in contents:
            if part.image_bytes is not None:
                b64 = base64.b64encode(part.image_bytes).decode("ascii")
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{part.mime_type};base64,{b64}"},
                    }
                )
            if part.text is not None:
                parts.append({"type": "text", "text": part.text})
        messages.append({"role": "user", "content": parts})

    return messages
