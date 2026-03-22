from __future__ import annotations

import asyncio
import json
import logging

from google.genai.types import GenerateContentConfig
from jinja2 import Template
from pydantic import BaseModel, Field

from marketmenow.integrations.genai import (
    configure_google_application_credentials,
    create_genai_client,
)

from .prompts import load_prompt
from .settings import LinkedInSettings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 5.0


class GeneratedPost(BaseModel, frozen=True):
    """A single AI-generated LinkedIn post."""

    type: str
    body: str = ""
    hashtags: list[str] = Field(default_factory=list)
    poll_question: str = ""
    poll_options: list[str] = Field(default_factory=list)
    article_url: str = ""


def _ensure_vertex_credentials(settings: LinkedInSettings) -> None:
    configure_google_application_credentials(settings.google_application_credentials)


class LinkedInContentGenerator:
    """Generates a batch of varied LinkedIn posts using Gemini."""

    def __init__(
        self,
        settings: LinkedInSettings,
        gemini_model: str = "gemini-2.5-flash",
    ) -> None:
        _ensure_vertex_credentials(settings)
        self._client = create_genai_client(
            vertex_project=settings.vertex_ai_project,
            vertex_location=settings.vertex_ai_location,
        )
        self._model = gemini_model

    async def generate_batch(self, count: int = 5) -> list[GeneratedPost]:
        prompt_data = load_prompt("batch_generation")

        system_prompt = prompt_data["system"]
        user_template = Template(prompt_data["user"])
        user_prompt = user_template.render(count=count)

        raw_json: str | None = None
        last_exc: BaseException | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=user_prompt,
                    config=GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=1.0,
                        response_mime_type="application/json",
                    ),
                )
                raw_json = (response.text or "").strip()
                break
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    backoff = _INITIAL_BACKOFF_S * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini attempt %d/%d failed, retrying in %.0fs: %s",
                        attempt,
                        _MAX_RETRIES,
                        backoff,
                        exc,
                    )
                    await asyncio.sleep(backoff)

        if raw_json is None:
            raise RuntimeError(
                f"All {_MAX_RETRIES} Gemini attempts failed for batch generation"
            ) from last_exc

        data = json.loads(raw_json)
        if isinstance(data, dict) and "posts" in data:
            data = data["posts"]
        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array from Gemini, got: {type(data).__name__}")

        posts = [GeneratedPost(**item) for item in data]

        for i, post in enumerate(posts):
            logger.info(
                "Generated post %d/%d: type=%s, hashtags=%s, body_len=%d",
                i + 1,
                len(posts),
                post.type,
                post.hashtags,
                len(post.body),
            )

        return posts
