from __future__ import annotations

import asyncio
import json
import logging
from functools import lru_cache
from pathlib import Path

from google import genai
from google.genai.types import GenerateContentConfig
from jinja2 import Template

from marketmenow.outreach.models import (
    CustomerProfile,
    RubricEvaluation,
    ScoredProspect,
    UserProfile,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 5.0
_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts" / "outreach"


@lru_cache(maxsize=8)
def _load_prompt(name: str) -> dict[str, str]:
    path = _PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    import yaml

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {"system": data.get("system", ""), "user": data.get("user", "")}


class ProspectScorer:
    """Evaluates a user profile against a rubric using Gemini. Platform-agnostic."""

    def __init__(
        self,
        gemini_model: str = "gemini-2.5-flash",
        vertex_project: str = "",
        vertex_location: str = "us-central1",
    ) -> None:
        self._client = genai.Client(
            vertexai=True,
            project=vertex_project,
            location=vertex_location,
        )
        self._model = gemini_model

    async def score(
        self,
        profile: UserProfile,
        customer_profile: CustomerProfile,
    ) -> ScoredProspect:
        prompt_data = _load_prompt("score_prospect")

        system_template = Template(prompt_data["system"])
        system_prompt = system_template.render(
            product=customer_profile.product,
            ideal_customer=customer_profile.ideal_customer,
        )

        rubric = customer_profile.ideal_customer.rubric
        max_score = sum(c.max_points for c in rubric)

        user_template = Template(prompt_data["user"])
        user_prompt = user_template.render(
            product=customer_profile.product,
            icp_description=customer_profile.ideal_customer.description,
            handle=profile.handle,
            display_name=profile.display_name,
            bio=profile.bio,
            location=profile.location,
            follower_count=profile.follower_count,
            following_count=profile.following_count,
            join_date=profile.join_date,
            recent_posts=profile.recent_posts,
            triggering_posts=profile.triggering_posts,
            rubric=rubric,
        )

        raw_json = await self._call_gemini(system_prompt, user_prompt, profile.handle)
        return self._parse_response(raw_json, profile, max_score)

    async def _call_gemini(
        self,
        system_prompt: str,
        user_prompt: str,
        handle: str,
    ) -> dict[str, object]:
        last_exc: BaseException | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=user_prompt,
                    config=GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        temperature=0.3,
                    ),
                )
                text = (response.text or "").strip()
                return json.loads(text)  # type: ignore[no-any-return]
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    backoff = _INITIAL_BACKOFF_S * (2 ** (attempt - 1))
                    logger.warning(
                        "Scorer attempt %d/%d failed for @%s, retrying in %.0fs: %s",
                        attempt,
                        _MAX_RETRIES,
                        handle,
                        backoff,
                        exc,
                    )
                    await asyncio.sleep(backoff)

        raise RuntimeError(
            f"All {_MAX_RETRIES} Gemini scoring attempts failed for @{handle}"
        ) from last_exc

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
