from __future__ import annotations

import json
from pathlib import Path

from google.genai import types as genai_types
from marketmenow.integrations.genai import create_genai_client

from ..prompts import load_prompt
from .models import GradingResult, RubricEvaluation, RubricItem


class SimpleGradingService:
    """Simplified grading service using Vertex AI Gemini for vision-based grading."""

    def __init__(
        self,
        project: str | None,
        location: str = "us-central1",
    ) -> None:
        self._client = create_genai_client(
            vertex_project=project,
            vertex_location=location,
        )
        self._model = "gemini-2.5-flash"

    async def grade(
        self,
        assignment_image: Path,
        rubric_items: list[RubricItem],
    ) -> GradingResult:
        """Grade an assignment image against a rubric using Gemini vision."""
        image_bytes = assignment_image.read_bytes()
        mime = "image/png" if assignment_image.suffix == ".png" else "image/jpeg"

        prompt = load_prompt("autograde")
        rubric_text = "\n".join(
            f"- {item.name} ({item.max_points} pts): {item.description}" for item in rubric_items
        )
        user_prompt = prompt["user"].format(rubric_text=rubric_text)

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[
                        genai_types.Part.from_bytes(data=image_bytes, mime_type=mime),
                        genai_types.Part.from_text(text=user_prompt),
                    ],
                ),
            ],
            config=genai_types.GenerateContentConfig(
                system_instruction=prompt["system"],
                response_mime_type="application/json",
                temperature=0.2,
            ),
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
        """Use Gemini to auto-generate a rubric from the assignment image."""
        image_bytes = assignment_image.read_bytes()
        mime = "image/png" if assignment_image.suffix == ".png" else "image/jpeg"

        prompt = load_prompt("generate_rubric")
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[
                        genai_types.Part.from_bytes(data=image_bytes, mime_type=mime),
                        genai_types.Part.from_text(text=prompt["user"]),
                    ],
                ),
            ],
            config=genai_types.GenerateContentConfig(
                system_instruction=prompt["system"] or None,
                response_mime_type="application/json",
                temperature=0.3,
            ),
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
