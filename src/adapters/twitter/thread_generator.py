from __future__ import annotations

import asyncio
import json
import logging
import random
from pathlib import Path

from google import genai
from google.genai.types import GenerateContentConfig
from jinja2 import Template
from pydantic import BaseModel, Field

from .performance_tracker import WinningPost, load_examples_cache
from .prompts import load_prompt

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 5.0

_TOPIC_HINTS = [
    "grading mistakes teachers don't realise they're making",
    "AI grading myths that need to die",
    "time-saving grading hacks for burnt-out teachers",
    "why rubric-based grading changes everything",
    "feedback techniques that actually improve student outcomes",
    "signs your grading process is broken",
    "things teachers waste time on that AI can handle",
    "assessment strategies backed by research",
    "how to give better feedback in less time",
    "grading habits that are stealing your weekends",
    "what students actually want from feedback",
    "common rubric mistakes and how to fix them",
    "AI tools every teacher should know about in 2025",
    "classroom management tips that save grading time",
    "ways to make grading less soul-crushing",
]


class GeneratedThread(BaseModel, frozen=True):
    """The full generated thread ready for posting."""

    topic: str
    tweets: list[TweetEntry] = Field(..., min_length=7, max_length=7)


class TweetEntry(BaseModel, frozen=True):
    position: int
    text: str
    is_hook: bool = False
    is_cta: bool = False


GeneratedThread.model_rebuild()


class ThreadGenerator:
    """Generates viral Twitter/X threads using Gemini."""

    def __init__(
        self,
        gemini_model: str = "gemini-2.5-flash",
        vertex_project: str = "",
        vertex_location: str = "us-central1",
        top_examples_path: Path | None = None,
        max_examples: int = 5,
    ) -> None:
        self._client = genai.Client(
            vertexai=True,
            project=vertex_project,
            location=vertex_location,
        )
        self._model = gemini_model
        self._top_examples_path = top_examples_path
        self._max_examples = max_examples

    def _load_winning_posts(self) -> list[WinningPost]:
        if self._top_examples_path is None:
            return []
        cache = load_examples_cache(self._top_examples_path)
        if not cache.posts:
            return []
        ranked = sorted(
            cache.posts,
            key=lambda p: p.likes + p.retweets,
            reverse=True,
        )
        return ranked[: self._max_examples]

    async def generate_thread(
        self,
        topic_hint: str = "",
    ) -> GeneratedThread:
        if not topic_hint:
            topic_hint = random.choice(_TOPIC_HINTS)

        winning_posts = self._load_winning_posts()

        prompt_data = load_prompt("thread_generation")

        system_prompt = prompt_data["system"]

        user_template = Template(prompt_data["user"])
        user_prompt = user_template.render(
            topic_hint=topic_hint,
            winning_posts=[p.model_dump() for p in winning_posts],
        )

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
                f"All {_MAX_RETRIES} Gemini attempts failed for thread generation"
            ) from last_exc

        data = json.loads(raw_json)
        thread = GeneratedThread(
            topic=data["topic"],
            tweets=[TweetEntry(**t) for t in data["tweets"]],
        )

        for tweet in thread.tweets:
            if len(tweet.text) > 280:
                logger.warning(
                    "Tweet %d exceeds 280 chars (%d), truncating",
                    tweet.position,
                    len(tweet.text),
                )

        logger.info("Generated thread: %s (%d tweets)", thread.topic, len(thread.tweets))
        return thread
