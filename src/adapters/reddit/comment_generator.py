from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Template

from marketmenow.core.icl import select_icl_examples
from marketmenow.integrations.llm import LLMProvider, create_llm_provider

from .discovery import DiscoveredPost
from .prompts import load_prompt

if TYPE_CHECKING:
    from marketmenow.models.project import BrandConfig, PersonaConfig

logger = logging.getLogger(__name__)


class CommentGenerator:
    """Generates helpful, persona-driven Reddit comments."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        mention_rate: int = 10,
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
        self._mention_rate = mention_rate
        self._persona = persona
        self._brand = brand
        self._project_slug = project_slug
        self._top_examples_path = top_examples_path
        self._max_examples = max_examples
        self._epsilon = epsilon

    async def generate_comment(
        self,
        post: DiscoveredPost,
        comment_number: int = 1,
    ) -> str:
        should_mention = random.randint(1, 100) <= self._mention_rate
        directive = (
            f"mention {self._brand.name} naturally — ALWAYS disclose your affiliation, "
            "never be salesy, lead with genuine help first"
            if should_mention and self._brand
            else "DO NOT mention any product. Just be genuinely helpful."
        )

        icl_examples: list[dict[str, object]] | None = None
        exploring = False
        if self._top_examples_path is not None:
            icl_examples, exploring = select_icl_examples(
                self._top_examples_path,
                self._max_examples,
                self._epsilon,
            )

        if self._persona and self._brand:
            from marketmenow.core.prompt_builder import PromptBuilder

            built = PromptBuilder().build(
                platform="reddit",
                function="comment",
                persona=self._persona,
                brand=self._brand,
                icl_examples=icl_examples,
                template_vars={
                    "subreddit": post.subreddit,
                    "post_title": post.post_title,
                    "post_text": post.post_text[:1500],
                    "comment_number": comment_number,
                    "should_mention": should_mention,
                    "mention_rate": self._mention_rate,
                    "directive": directive,
                    "author_handle": getattr(post, "author", "anonymous"),
                },
                project_slug=self._project_slug,
            )
            system_prompt = built.system
            user_prompt = built.user
        else:
            prompt_data = load_prompt("comment_generation")

            system_template = Template(prompt_data["system"])
            system_prompt = system_template.render(mention_rate=self._mention_rate)

            user_template = Template(prompt_data["user"])
            user_prompt = user_template.render(
                subreddit=post.subreddit,
                post_title=post.post_title,
                post_text=post.post_text[:1500],
                comment_number=comment_number,
                should_mention=should_mention,
            )

        response = await self._provider.generate_text(
            model=self._model,
            system=system_prompt,
            contents=user_prompt,
            temperature=0.9,
        )
        comment_text = response.text.strip().strip('"').strip("'")

        mode = "explore" if exploring else "exploit"
        n_examples = 0 if icl_examples is None else len(icl_examples)
        logger.info(
            "Generated comment for r/%s post %s (mention=%s, mode=%s, examples=%d): %s",
            post.subreddit,
            post.post_id,
            should_mention,
            mode,
            n_examples,
            comment_text[:80],
        )
        return comment_text
