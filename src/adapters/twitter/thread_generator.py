from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from google.genai.types import GenerateContentConfig
from pydantic import BaseModel, Field

from marketmenow.core.prompt_builder import PromptBuilder
from marketmenow.integrations.genai import create_genai_client

from .performance_tracker import WinningPost, load_examples_cache

if TYPE_CHECKING:
    from marketmenow.models.project import BrandConfig, PersonaConfig

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 5.0

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _sanitise_json(raw: str) -> str:
    """Strip markdown fences and trailing commas that Gemini sometimes emits."""
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw)
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return raw.strip()


def _load_topic_hints(project_slug: str | None, platform: str = "twitter") -> list[str]:
    """Load topic hints from the project directory, or return empty list."""
    if not project_slug:
        return []
    topics_path = _PROJECT_ROOT / "projects" / project_slug / "topics.yaml"
    if not topics_path.exists():
        return []
    try:
        with topics_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        hints = data.get(platform, data.get("topics", []))
        return list(hints) if isinstance(hints, list) else []
    except Exception:
        logger.warning("Failed to load topics from %s", topics_path)
        return []


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
        persona: PersonaConfig | None = None,
        brand: BrandConfig | None = None,
        project_slug: str | None = None,
    ) -> None:
        self._client = create_genai_client(
            vertex_project=vertex_project,
            vertex_location=vertex_location,
        )
        self._model = gemini_model
        self._top_examples_path = top_examples_path
        self._max_examples = max_examples
        self._persona = persona
        self._brand = brand
        self._project_slug = project_slug
        self._prompt_builder = PromptBuilder()

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
            hints = _load_topic_hints(self._project_slug, "twitter")
            if hints:
                topic_hint = random.choice(hints)

        winning_posts = self._load_winning_posts()

        template_vars: dict[str, object] = {
            "topic_hint": topic_hint,
            "winning_posts": [p.model_dump() for p in winning_posts],
        }

        if self._persona and self._brand:
            prompt = self._prompt_builder.build(
                platform="twitter",
                function="thread",
                persona=self._persona,
                brand=self._brand,
                icl_examples=None,
                template_vars=template_vars,
                project_slug=self._project_slug,
            )
            system_prompt = prompt.system
            user_prompt = prompt.user
        else:
            from .prompts import load_prompt

            prompt_data = load_prompt(
                "thread_generation",
                project_slug=self._project_slug,
            )
            from jinja2 import Template

            system_prompt = prompt_data["system"]
            user_prompt = Template(prompt_data["user"]).render(**template_vars)

        data: dict[str, object] | None = None
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
                raw_json = _sanitise_json(raw_json)
                data = json.loads(raw_json)
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

        if data is None:
            raise RuntimeError(
                f"All {_MAX_RETRIES} Gemini attempts failed for thread generation"
            ) from last_exc
        cleaned_tweets: list[dict[str, object]] = []
        for t in data["tweets"]:
            t = dict(t)
            if isinstance(t.get("text"), str):
                t["text"] = t["text"].replace("\u2014", "-").replace("\u2013", "-")
            cleaned_tweets.append(t)

        thread = GeneratedThread(
            topic=data["topic"],
            tweets=[TweetEntry(**t) for t in cleaned_tweets],
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
