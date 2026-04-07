from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Template
from pydantic import BaseModel, Field

from marketmenow.core.icl import select_icl_examples
from marketmenow.integrations.llm import LLMProvider, create_llm_provider
from marketmenow.models.project import BrandConfig, PersonaConfig

from .prompts import load_prompt
from .settings import LinkedInSettings

logger = logging.getLogger(__name__)


class GeneratedPost(BaseModel, frozen=True):
    """A single AI-generated LinkedIn post."""

    type: str
    body: str = ""
    hashtags: list[str] = Field(default_factory=list)
    poll_question: str = ""
    poll_options: list[str] = Field(default_factory=list)
    article_url: str = ""


class LinkedInContentGenerator:
    """Generates a batch of varied LinkedIn posts."""

    def __init__(
        self,
        settings: LinkedInSettings,
        model: str = "gemini-2.5-flash",
        persona: PersonaConfig | None = None,
        brand: BrandConfig | None = None,
        project_slug: str | None = None,
        top_examples_path: Path | None = None,
        max_examples: int = 5,
        epsilon: float = 0.3,
        provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider()
        self._model = model
        self._persona = persona
        self._brand = brand
        self._project_slug = project_slug
        self._top_examples_path = top_examples_path
        self._max_examples = max_examples
        self._epsilon = epsilon

    async def generate_batch(
        self,
        count: int = 5,
        brand: BrandConfig | None = None,
        persona: PersonaConfig | None = None,
    ) -> list[GeneratedPost]:
        effective_persona = persona or self._persona
        effective_brand = brand or self._brand

        icl_examples: list[dict[str, object]] | None = None
        if self._top_examples_path is not None:
            icl_examples, _exploring = select_icl_examples(
                self._top_examples_path,
                self._max_examples,
                self._epsilon,
            )

        if effective_persona and effective_brand:
            from marketmenow.core.prompt_builder import PromptBuilder

            built = PromptBuilder().build(
                platform="linkedin",
                function="batch",
                persona=effective_persona,
                brand=effective_brand,
                icl_examples=icl_examples,
                template_vars={"count": count},
                project_slug=self._project_slug,
            )
            system_prompt = built.system
            user_prompt = built.user
        else:
            prompt_data = load_prompt("batch_generation")

            template_vars: dict[str, object] = {"count": count}
            if effective_brand is not None:
                template_vars["brand"] = effective_brand
            if effective_persona is not None:
                template_vars["persona"] = effective_persona

            system_prompt = Template(prompt_data["system"]).render(**template_vars)
            user_prompt = Template(prompt_data["user"]).render(**template_vars)

        response = await self._provider.generate_json(
            model=self._model,
            system=system_prompt,
            contents=user_prompt,
            temperature=1.0,
        )
        raw_json = response.text

        data = json.loads(raw_json)
        if isinstance(data, dict) and "posts" in data:
            data = data["posts"]
        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array from LLM, got: {type(data).__name__}")

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
