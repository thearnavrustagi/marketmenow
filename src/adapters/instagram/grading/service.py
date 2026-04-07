from __future__ import annotations

import json
from pathlib import Path

from marketmenow.integrations.llm import LLMProvider, MultimodalPart, create_llm_provider

from ..prompts import load_prompt
from .models import GradingResult, RubricEvaluation, RubricItem


class SimpleGradingService:
    """Simplified grading service using vision-based grading."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        model: str = "gemini-2.5-flash",
    ) -> None:
        self._provider = provider or create_llm_provider()
        self._model = model

    async def grade(
        self,
        assignment_image: Path,
        rubric_items: list[RubricItem],
    ) -> GradingResult:
        """Grade an assignment image against a rubric using vision."""
        image_bytes = assignment_image.read_bytes()
        mime = "image/png" if assignment_image.suffix == ".png" else "image/jpeg"

        prompt = load_prompt("autograde")
        rubric_text = "\n".join(
            f"- {item.name} ({item.max_points} pts): {item.description}" for item in rubric_items
        )
        user_prompt = prompt["user"].format(rubric_text=rubric_text)

        contents = [
            MultimodalPart(image_bytes=image_bytes, mime_type=mime),
            MultimodalPart(text=user_prompt),
        ]

        response = await self._provider.generate_json(
            model=self._model,
            system=prompt["system"],
            contents=contents,
            temperature=0.2,
        )

        raw = json.loads(response.text)
        evaluations = [
            RubricEvaluation(
                rubric_item_name=ev["rubric_item_name"],
                points_awarded=ev["points_awarded"],
                max_points=ev["max_points"],
                feedback=ev["feedback"],
            )
            for ev in raw.get("rubric_evaluations", [])
        ]

        total_awarded = sum(ev.points_awarded for ev in evaluations)
        total_max = sum(ev.max_points for ev in evaluations)

        return GradingResult(
            points_awarded=total_awarded,
            max_points=total_max,
            feedback=raw.get("overall_feedback", ""),
            rubric_evaluations=evaluations,
        )

    async def generate_rubric(self, assignment_image: Path) -> list[RubricItem]:
        """Use vision to auto-generate a rubric from the assignment image."""
        image_bytes = assignment_image.read_bytes()
        mime = "image/png" if assignment_image.suffix == ".png" else "image/jpeg"

        prompt = load_prompt("generate_rubric")

        contents = [
            MultimodalPart(image_bytes=image_bytes, mime_type=mime),
            MultimodalPart(text=prompt["user"]),
        ]

        response = await self._provider.generate_json(
            model=self._model,
            system=prompt["system"] or "",
            contents=contents,
            temperature=0.3,
        )

        raw = json.loads(response.text)
        return [
            RubricItem(
                name=item["name"],
                description=item["description"],
                max_points=item["max_points"],
            )
            for item in raw.get("rubric_items", [])
        ]
