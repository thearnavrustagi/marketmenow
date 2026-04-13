from __future__ import annotations

import json
import logging

from marketmenow.integrations.llm import LLMProvider, create_llm_provider
from marketmenow.outreach.models import (
    CustomerProfile,
    ScoredProspect,
    UserProfile,
)

logger = logging.getLogger(__name__)


class ProspectScorer:
    """Evaluates a user profile for product relevance. Platform-agnostic."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider()
        self._model = model

    async def score(
        self,
        profile: UserProfile,
        customer_profile: CustomerProfile,
    ) -> ScoredProspect:
        from marketmenow.core.prompt_builder import PromptBuilder

        target = customer_profile.ideal_customer

        built = PromptBuilder().build(
            platform="outreach",
            function="score_prospect",
            template_vars={
                "product": customer_profile.product,
                "target_customer_description": target.description,
                "pain_points": [],
                "handle": profile.handle,
                "display_name": profile.display_name,
                "bio": profile.bio,
                "location": profile.location,
                "follower_count": profile.follower_count,
                "following_count": profile.following_count,
                "join_date": profile.join_date,
                "recent_posts": profile.recent_posts,
                "triggering_posts": profile.triggering_posts,
            },
        )

        raw_json = await self._call_llm(built.system, built.user, profile.handle)
        return self._parse_response(raw_json, profile)

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        handle: str,
    ) -> dict[str, object]:
        response = await self._provider.generate_json(
            model=self._model,
            system=system_prompt,
            contents=user_prompt,
            temperature=0.3,
        )
        return json.loads(response.text)  # type: ignore[no-any-return]

    @staticmethod
    def _parse_response(
        data: dict[str, object],
        profile: UserProfile,
    ) -> ScoredProspect:
        relevance_score = int(data.get("relevance_score", 0))
        dm_angle = str(data.get("dm_angle", ""))
        disqualify = data.get("disqualify_reason")
        disqualify_reason = str(disqualify) if disqualify else None

        return ScoredProspect(
            user_profile=profile,
            evaluations=[],
            total_score=relevance_score,
            max_score=10,
            dm_angle=dm_angle,
            disqualify_reason=disqualify_reason,
        )
