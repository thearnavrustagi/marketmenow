from __future__ import annotations

import asyncio
import logging
import random

from google import genai
from google.genai.types import GenerateContentConfig
from jinja2 import Template
from pydantic import BaseModel

from .discovery import DiscoveredPost
from .prompts import load_prompt

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 5.0


class GradeasyContext(BaseModel, frozen=True):
    name: str = "Gradeasy"
    url: str = "gradeasy.ai"
    tagline: str = "AI-powered grading assistant for K-12 teachers"
    features: list[str] = [
        "Grades assignments against rubrics in seconds",
        "Supports images, PDFs, and handwritten work",
        "Saves teachers 8-15 hours per week",
        "Teachers keep full control over final grades",
        "Free to try",
    ]


class ReplyGenerator:
    """Generates witty, persona-driven replies using Gemini."""

    def __init__(
        self,
        gemini_model: str = "gemini-2.5-flash",
        mention_rate: int = 45,
        vertex_project: str = "",
        vertex_location: str = "us-central1",
    ) -> None:
        self._client = genai.Client(
            vertexai=True,
            project=vertex_project,
            location=vertex_location,
        )
        self._model = gemini_model
        self._mention_rate = mention_rate
        self._context = GradeasyContext()

    async def generate_reply(
        self,
        post: DiscoveredPost,
        reply_number: int = 1,
    ) -> str:
        should_mention = random.randint(1, 100) <= self._mention_rate

        prompt_data = load_prompt("reply_generation")

        system_template = Template(prompt_data["system"])
        system_prompt = system_template.render(mention_rate=self._mention_rate)

        user_template = Template(prompt_data["user"])
        user_prompt = user_template.render(
            author_handle=post.author_handle,
            post_text=post.post_text[:500],
            reply_number=reply_number,
            should_mention=should_mention,
        )

        reply_text: str | None = None
        last_exc: BaseException | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=user_prompt,
                    config=GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.9,
                    ),
                )
                reply_text = (response.text or "").strip().strip('"').strip("'")
                break
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    backoff = _INITIAL_BACKOFF_S * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini attempt %d/%d failed for @%s, retrying in %.0fs: %s",
                        attempt,
                        _MAX_RETRIES,
                        post.author_handle,
                        backoff,
                        exc,
                    )
                    await asyncio.sleep(backoff)

        if reply_text is None:
            raise RuntimeError(
                f"All {_MAX_RETRIES} Gemini attempts failed for @{post.author_handle}"
            ) from last_exc

        logger.info(
            "Generated reply for @%s (mention=%s): %s",
            post.author_handle,
            should_mention,
            reply_text[:80],
        )
        return reply_text
