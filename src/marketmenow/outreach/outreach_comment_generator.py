from __future__ import annotations

import logging

from pydantic import BaseModel

from marketmenow.integrations.llm import LLMProvider, create_llm_provider
from marketmenow.outreach.models import ProductInfo
from marketmenow.outreach.post_scorer import ScoredPost

logger = logging.getLogger(__name__)


class OutreachComment(BaseModel, frozen=True):
    """A generated outreach comment ready to post on Reddit."""

    post_id: str
    post_fullname: str
    post_url: str
    recipient_handle: str
    comment_text: str
    outreach_angle: str = ""
    prospect_score: int = 0


class OutreachCommentGenerator:
    """Generates personalised outreach comments for Reddit posts. Platform-agnostic."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider()
        self._model = model

    async def generate(
        self,
        scored_post: ScoredPost,
        product: ProductInfo,
        features: list[str],
        *,
        messaging_tone: str = "",
        max_length: int = 1500,
    ) -> OutreachComment:
        from marketmenow.core.prompt_builder import PromptBuilder

        built = PromptBuilder().build(
            platform="outreach",
            function="generate_outreach_comment",
            template_vars={
                "product": product,
                "features": features,
                "post_title": scored_post.post_title,
                "post_text": scored_post.post_text,
                "subreddit": scored_post.subreddit,
                "author": scored_post.author,
                "outreach_angle": scored_post.outreach_angle,
                "tone": messaging_tone,
                "max_length": max_length,
                "url": product.url,
            },
        )

        response = await self._provider.generate_text(
            model=self._model,
            system=built.system,
            contents=built.user,
            temperature=0.9,
        )
        comment_text = response.text.strip().strip('"').strip("'")

        if not comment_text:
            raise ValueError(
                f"LLM returned empty response for post by u/{scored_post.author}"
            )

        return OutreachComment(
            post_id=scored_post.post_id,
            post_fullname=scored_post.post_fullname,
            post_url=scored_post.post_url,
            recipient_handle=scored_post.author,
            comment_text=comment_text,
            outreach_angle=scored_post.outreach_angle,
            prospect_score=scored_post.relevance_score,
        )
