from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel, Field

from marketmenow.core.icl import select_icl_examples
from marketmenow.core.prompt_builder import PromptBuilder
from marketmenow.integrations.llm import LLMProvider, create_llm_provider

if TYPE_CHECKING:
    from marketmenow.models.project import BrandConfig, PersonaConfig

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _sanitise_json(raw: str) -> str:
    """Strip markdown fences and trailing commas that the LLM sometimes emits."""
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
    """Generates viral Twitter/X threads."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        top_examples_path: Path | None = None,
        max_examples: int = 5,
        epsilon: float = 0.3,
        persona: PersonaConfig | None = None,
        brand: BrandConfig | None = None,
        project_slug: str | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider()
        self._model = model
        self._top_examples_path = top_examples_path
        self._max_examples = max_examples
        self._epsilon = epsilon
        self._persona = persona
        self._brand = brand
        self._project_slug = project_slug
        self._prompt_builder = PromptBuilder()

    async def generate_thread(
        self,
        topic_hint: str = "",
    ) -> GeneratedThread:
        if not topic_hint:
            hints = _load_topic_hints(self._project_slug, "twitter")
            if hints:
                topic_hint = random.choice(hints)

        icl_examples: list[dict[str, object]] | None = None
        if self._top_examples_path is not None:
            icl_examples, exploring = select_icl_examples(
                self._top_examples_path,
                self._max_examples,
                self._epsilon,
            )
            if exploring:
                logger.info("ICL explore mode — no examples for this thread")

        template_vars: dict[str, object] = {
            "topic_hint": topic_hint,
        }

        if self._persona and self._brand:
            prompt = self._prompt_builder.build(
                platform="twitter",
                function="thread",
                persona=self._persona,
                brand=self._brand,
                icl_examples=icl_examples,
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

        response = await self._provider.generate_json(
            model=self._model,
            system=system_prompt,
            contents=user_prompt,
            temperature=1.0,
        )
        raw_json = _sanitise_json(response.text)
        data = json.loads(raw_json)

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
