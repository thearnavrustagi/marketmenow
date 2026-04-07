from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING

from marketmenow.core.diversity_selector import select_diverse_examples
from marketmenow.core.prompt_builder import PromptBuilder
from marketmenow.integrations.llm import LLMProvider, MultimodalPart, create_llm_provider

from .discovery import DiscoveredPost
from .performance_tracker import WinningReply, load_examples_cache

if TYPE_CHECKING:
    from marketmenow.models.project import BrandConfig, PersonaConfig

logger = logging.getLogger(__name__)


class ReplyGenerator:
    """Generates persona-driven replies with epsilon-greedy ICL."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        mention_rate: int = 25,
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
        self._mention_rate = mention_rate
        self._top_examples_path = top_examples_path
        self._max_examples = max_examples
        self._epsilon = epsilon
        self._persona = persona
        self._brand = brand
        self._project_slug = project_slug
        self._prompt_builder = PromptBuilder()

    def _load_winning_replies(self) -> list[WinningReply]:
        if self._top_examples_path is None:
            return []
        cache = load_examples_cache(self._top_examples_path)
        if not cache.replies:
            return []
        ranked = sorted(
            cache.replies,
            key=lambda r: r.likes + r.retweets,
            reverse=True,
        )
        return ranked[: self._max_examples * 4]

    async def generate_reply(
        self,
        post: DiscoveredPost,
        reply_number: int = 1,
    ) -> tuple[str, bool]:
        """Generate a reply. Returns ``(reply_text, is_exploring)``."""
        should_mention = random.randint(1, 100) <= self._mention_rate

        exploring = random.random() < self._epsilon

        icl_examples: list[dict[str, object]] | None = None
        if not exploring:
            candidates = self._load_winning_replies()
            if candidates:
                selected = select_diverse_examples(
                    candidates,
                    [c.embedding for c in candidates],
                    n=self._max_examples,
                )
                icl_examples = [e.model_dump() for e in selected]

        if should_mention:
            brand_name = self._brand.name if self._brand else "the product"
            directive = (
                f"weave in a {brand_name} mention — be creative, never salesy, "
                "never the same trick twice"
            )
        else:
            directive = (
                "DO NOT mention any product. Just be funny, insightful, or "
                "genuinely supportive. Build the character, not the brand."
            )

        media_context = self._build_media_context(post)

        template_vars: dict[str, object] = {
            "author_handle": post.author_handle,
            "post_text": post.post_text[:500],
            "reply_number": reply_number,
            "should_mention": should_mention,
            "mention_rate": self._mention_rate,
            "directive": directive,
            "media_context": media_context,
        }

        if self._persona and self._brand:
            prompt = self._prompt_builder.build(
                platform="twitter",
                function="reply",
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
                "reply_generation",
                project_slug=self._project_slug,
            )
            from jinja2 import Template

            system_prompt = Template(prompt_data["system"]).render(
                mention_rate=self._mention_rate,
            )
            user_prompt = Template(prompt_data["user"]).render(
                **template_vars,
                winning_examples=icl_examples or [],
            )

        contents = self._build_contents(user_prompt, post.media_screenshot)

        response = await self._provider.generate_text(
            model=self._model,
            system=system_prompt,
            contents=contents,
            temperature=1.0,
        )
        reply_text = response.text.strip().strip('"').strip("'")

        mode = "explore" if exploring else "exploit"
        n_examples = 0 if icl_examples is None else len(icl_examples)
        logger.info(
            "Generated reply for @%s (mention=%s, mode=%s, examples=%d): %s",
            post.author_handle,
            should_mention,
            mode,
            n_examples,
            reply_text[:80],
        )
        return reply_text, exploring

    @staticmethod
    def _build_media_context(post: DiscoveredPost) -> str:
        """Assemble a textual summary of the tweet's visual/media content."""
        parts: list[str] = []
        if post.media_alt_texts:
            for i, alt in enumerate(post.media_alt_texts, 1):
                parts.append(f"[Image {i} alt text]: {alt}")
        if post.card_text:
            parts.append(f"[Link preview / card]: {post.card_text}")
        if not parts and post.media_screenshot:
            parts.append("[A screenshot of the tweet (including any images/media) is attached]")
        return "\n".join(parts)

    @staticmethod
    def _build_contents(
        user_prompt: str,
        screenshot: bytes | None,
    ) -> str | list[MultimodalPart]:
        """Build text-only or multimodal contents."""
        if not screenshot:
            return user_prompt
        return [
            MultimodalPart(image_bytes=screenshot, mime_type="image/jpeg"),
            MultimodalPart(text=user_prompt),
        ]
