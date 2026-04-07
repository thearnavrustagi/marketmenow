from __future__ import annotations

import json
import logging

from marketmenow.integrations.llm import LLMProvider, create_llm_provider
from marketmenow.outreach.models import (
    CustomerProfile,
    RubricEvaluation,
    ScoredProspect,
    UserProfile,
)

logger = logging.getLogger(__name__)


class ProspectScorer:
    """Evaluates a user profile against a rubric. Platform-agnostic."""

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

        rubric = customer_profile.ideal_customer.rubric
        max_score = sum(c.max_points for c in rubric)

        built = PromptBuilder().build(
            platform="outreach",
            function="score_prospect",
            template_vars={
                "product": customer_profile.product,
                "ideal_customer": customer_profile.ideal_customer,
                "icp_description": customer_profile.ideal_customer.description,
                "handle": profile.handle,
                "display_name": profile.display_name,
                "bio": profile.bio,
                "location": profile.location,
                "follower_count": profile.follower_count,
                "following_count": profile.following_count,
                "join_date": profile.join_date,
                "recent_posts": profile.recent_posts,
                "triggering_posts": profile.triggering_posts,
                "rubric": rubric,
            },
        )

        raw_json = await self._call_llm(built.system, built.user, profile.handle)
        return self._parse_response(raw_json, profile, max_score)

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
        max_score: int,
    ) -> ScoredProspect:
        evaluations: list[RubricEvaluation] = []
        for ev in data.get("evaluations", []):  # type: ignore[union-attr]
            evaluations.append(
                RubricEvaluation(
                    criterion_name=str(ev.get("criterion_name", "")),  # type: ignore[union-attr]
                    points_awarded=int(ev.get("points_awarded", 0)),  # type: ignore[union-attr]
                    max_points=int(ev.get("max_points", 0)),  # type: ignore[union-attr]
                    reasoning=str(ev.get("reasoning", "")),  # type: ignore[union-attr]
                )
            )

        total_score = int(data.get("total_score", sum(e.points_awarded for e in evaluations)))
        dm_angle = str(data.get("dm_angle", ""))
        disqualify = data.get("disqualify_reason")
        disqualify_reason = str(disqualify) if disqualify else None

        return ScoredProspect(
            user_profile=profile,
            evaluations=evaluations,
            total_score=total_score,
            max_score=max_score,
            dm_angle=dm_angle,
            disqualify_reason=disqualify_reason,
        )
