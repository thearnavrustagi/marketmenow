from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from marketmenow.integrations.llm import LLMProvider, create_llm_provider
from marketmenow.outreach.models import ProductInfo

logger = logging.getLogger(__name__)


class ScoredPost(BaseModel, frozen=True):
    """A Reddit post scored for relevance to a product."""

    post_title: str
    post_text: str
    post_url: str
    post_id: str
    post_fullname: str
    author: str
    subreddit: str
    relevance_score: int = 0
    outreach_angle: str = ""
    disqualify_reason: str | None = None


class PostRelevanceScorer:
    """Scores a post for product relevance using a general prompt. Platform-agnostic."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider()
        self._model = model

    async def score(
        self,
        *,
        post_title: str,
        post_text: str,
        post_url: str,
        post_id: str,
        post_fullname: str,
        author: str,
        subreddit: str,
        product: ProductInfo,
        target_customer_description: str = "",
        pain_points: list[str] | None = None,
    ) -> ScoredPost:
        from marketmenow.core.prompt_builder import PromptBuilder

        built = PromptBuilder().build(
            platform="outreach",
            function="score_post",
            template_vars={
                "product": product,
                "post_title": post_title,
                "post_text": post_text,
                "subreddit": subreddit,
                "author": author,
                "target_customer_description": target_customer_description,
                "pain_points": pain_points or [],
            },
        )

        response = await self._provider.generate_json(
            model=self._model,
            system=built.system,
            contents=built.user,
            temperature=0.3,
        )
        data: dict[str, object] = json.loads(response.text)

        relevance_score = int(data.get("relevance_score", 0))
        outreach_angle = str(data.get("outreach_angle", ""))
        disqualify = data.get("disqualify_reason")
        disqualify_reason = str(disqualify) if disqualify else None

        return ScoredPost(
            post_title=post_title,
            post_text=post_text,
            post_url=post_url,
            post_id=post_id,
            post_fullname=post_fullname,
            author=author,
            subreddit=subreddit,
            relevance_score=relevance_score,
            outreach_angle=outreach_angle,
            disqualify_reason=disqualify_reason,
        )
