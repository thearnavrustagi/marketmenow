from __future__ import annotations

import logging
import os

from google import genai
from google.genai import types as genai_types
from google.genai.types import GenerateContentConfig

from marketmenow.integrations.llm import LLMResponse, MultimodalPart
from marketmenow.integrations.retry import with_retry

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash"
_DEFAULT_EMBED_MODEL = "text-embedding-004"


class GeminiProvider:
    """LLMProvider backed by Google GenAI (AI Studio / Vertex AI)."""

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        *,
        api_key: str = "",
        vertex_project: str = "",
        vertex_location: str = "us-central1",
    ) -> None:
        self._default_model = model
        resolved_key = _resolve_api_key(api_key)
        if resolved_key:
            self._client = genai.Client(api_key=resolved_key)
        elif vertex_project.strip():
            self._client = genai.Client(
                vertexai=True,
                project=vertex_project,
                location=vertex_location,
            )
        else:
            vp = os.getenv("VERTEX_AI_PROJECT", "").strip()
            vl = os.getenv("VERTEX_AI_LOCATION", "us-central1").strip()
            if vp:
                self._client = genai.Client(
                    vertexai=True,
                    project=vp,
                    location=vl,
                )
            else:
                raise ValueError(
                    "Missing Gemini credentials. Set GEMINI_API_KEY (AI Studio) "
                    "or VERTEX_AI_PROJECT (Vertex AI)."
                )

    @property
    def client(self) -> genai.Client:
        """Escape hatch for Gemini-only features (Imagen, image editing)."""
        return self._client

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
        genai_contents = _to_genai_contents(contents)
        config = GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
        )

        async def _call() -> LLMResponse:
            response = await self._client.aio.models.generate_content(
                model=resolved_model,
                contents=genai_contents,
                config=config,
            )
            return LLMResponse(text=(response.text or "").strip(), raw=response)

        return await with_retry(
            _call,
            max_retries=max_retries,
            initial_backoff=initial_backoff,
            retry_logger=logger,
            context=f"gemini/{resolved_model}",
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
        genai_contents = _to_genai_contents(contents)
        config = GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
        )

        async def _call() -> LLMResponse:
            response = await self._client.aio.models.generate_content(
                model=resolved_model,
                contents=genai_contents,
                config=config,
            )
            return LLMResponse(text=(response.text or "").strip(), raw=response)

        return await with_retry(
            _call,
            max_retries=max_retries,
            initial_backoff=initial_backoff,
            retry_logger=logger,
            context=f"gemini-json/{resolved_model}",
        )

    async def embed(
        self,
        *,
        texts: list[str],
        model: str = "",
    ) -> list[list[float]]:
        resolved_model = model or _DEFAULT_EMBED_MODEL
        response = await self._client.aio.models.embed_content(
            model=resolved_model,
            contents=texts,
        )
        return [list(e.values) for e in response.embeddings]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_api_key(explicit: str = "") -> str:
    candidates = (
        explicit,
        os.getenv("GEMINI_API_KEY", ""),
        os.getenv("GOOGLE_API_KEY", ""),
    )
    for val in candidates:
        if val and val.strip():
            return val.strip()
    return ""


def _to_genai_contents(
    contents: str | list[MultimodalPart],
) -> str | list[genai_types.Content]:
    """Convert our MultimodalPart list into genai-native types."""
    if isinstance(contents, str):
        return contents

    parts: list[genai_types.Part] = []
    for part in contents:
        if part.image_bytes is not None:
            parts.append(
                genai_types.Part.from_bytes(
                    data=part.image_bytes,
                    mime_type=part.mime_type,
                )
            )
        if part.text is not None:
            parts.append(genai_types.Part.from_text(text=part.text))

    return [genai_types.Content(role="user", parts=parts)]
