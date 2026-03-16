from __future__ import annotations

import json
from pathlib import Path

from google import genai
from google.genai import types as genai_types
from jinja2 import Environment

from ..grading.models import GradingResult, RubricItem
from ..grading.service import SimpleGradingService
from ..prompts import load_prompt
from .models import AudioType, BeatDefinition, ReelTemplate

_JINJA_ENV = Environment()


class ReelScriptGenerator:
    """Hydrates a YAML reel template with LLM-generated content and grading data."""

    def __init__(
        self,
        grading_service: SimpleGradingService,
        vertex_project: str,
        vertex_location: str = "us-central1",
    ) -> None:
        self._grader = grading_service
        self._client = genai.Client(
            vertexai=True,
            project=vertex_project,
            location=vertex_location,
        )
        self._model = "gemini-2.5-flash"

    async def generate(
        self,
        template: ReelTemplate,
        assignment_image: Path,
        rubric_items: list[RubricItem] | None = None,
    ) -> tuple[dict[str, object], list[BeatDefinition]]:
        """Fill template variables and resolve Jinja placeholders in beats.

        Returns (variables_dict, resolved_beats) where resolved_beats
        have all ``{{ ... }}`` placeholders replaced with concrete values.
        Audio durations are NOT yet computed -- that happens in the orchestrator
        after TTS synthesis.
        """
        if rubric_items is None:
            rubric_items = await self._grader.generate_rubric(assignment_image)

        grading_result = await self._grader.grade(assignment_image, rubric_items)

        script_vars = await self._generate_script_text(template, grading_result)

        variables: dict[str, object] = {
            "assignment_image": str(assignment_image.resolve()),
            "reaction_text": script_vars["reaction_text"],
            "roast_text": script_vars.get("roast_text", script_vars["reaction_text"]),
            "gradeasy_response": script_vars.get("gradeasy_response", "I gotchu bro, let me cook"),
            "reaction_image": "",
            "comment_username": "student",
            "comment_avatar": "",
            "comment_text": "yo can you grade my assignment",
            "rubric_items": [item.model_dump() for item in rubric_items],
            "grading_result": grading_result.model_dump(),
            "rubric_narration": script_vars["rubric_narration"],
            "grading_narration": script_vars["grading_narration"],
            "result_comment": script_vars["result_comment"],
        }

        resolved_beats = self._resolve_beats(template.beats, variables)
        return variables, resolved_beats

    async def _generate_script_text(
        self,
        template: ReelTemplate,
        grading_result: GradingResult,
    ) -> dict[str, str]:
        prompt = load_prompt("script_generation")
        rubric_eval_text = "\n".join(
            f"  - {ev.rubric_item_name}: {ev.points_awarded}/{ev.max_points} -- {ev.feedback}"
            for ev in grading_result.rubric_evaluations
        )

        user_text = prompt["user"].format(
            template_name=template.name,
            points_awarded=grading_result.points_awarded,
            max_points=grading_result.max_points,
            feedback=grading_result.feedback,
            rubric_eval_text=rubric_eval_text,
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(text=user_text)],
                ),
            ],
            config=genai_types.GenerateContentConfig(
                system_instruction=prompt["system"],
                response_mime_type="application/json",
                temperature=0.8,
            ),
        )

        data = json.loads(response.text)
        if isinstance(data, list):
            data = data[0]
        return data

    @staticmethod
    def _resolve_beats(
        beats: list[BeatDefinition],
        variables: dict[str, object],
    ) -> list[BeatDefinition]:
        """Replace ``{{ var }}`` placeholders in beat audio text, voice, and visual props."""
        resolved: list[BeatDefinition] = []
        for beat in beats:
            audio_text = beat.audio.text
            if audio_text:
                audio_text = _render_template_str(audio_text, variables)

            audio_voice = beat.audio.voice
            if audio_voice:
                audio_voice = _render_template_str(audio_voice, variables)

            visual = _resolve_dict(beat.visual, variables)

            resolved.append(
                beat.model_copy(
                    update={
                        "audio": beat.audio.model_copy(
                            update={"text": audio_text, "voice": audio_voice}
                        ),
                        "visual": visual,
                    }
                )
            )
        return resolved


def _render_template_str(text: str, variables: dict[str, object]) -> str:
    """Resolve Jinja2 placeholders in a string, falling back to the original on error.

    If the template resolves to a complex object (dict/list), serialize it
    as proper JSON so that the Remotion side can safely ``JSON.parse()`` it.
    """
    if "{{" not in text:
        return text
    try:
        tmpl = _JINJA_ENV.from_string(text)
        result = tmpl.render(**variables)
        return result
    except Exception:
        return text


def _render_template_value(text: str, variables: dict[str, object]) -> object:
    """Like _render_template_str but returns the raw Python object when the
    template is a single ``{{ var }}`` reference to a dict/list, preserving
    type so it can be serialised as proper JSON later."""
    stripped = text.strip()
    if stripped.startswith("{{") and stripped.endswith("}}"):
        var_name = stripped[2:-2].strip()
        parts = var_name.split(".")
        obj: object = variables
        try:
            for part in parts:
                if isinstance(obj, dict):
                    obj = obj[part]
                else:
                    return _render_template_str(text, variables)
            if isinstance(obj, (dict, list)):
                return obj
        except (KeyError, TypeError):
            pass
    return _render_template_str(text, variables)


def _resolve_dict(
    d: dict[str, object], variables: dict[str, object]
) -> dict[str, object]:
    """Recursively resolve Jinja2 strings inside a dict."""
    out: dict[str, object] = {}
    for k, v in d.items():
        if isinstance(v, str):
            out[k] = _render_template_value(v, variables)
        elif isinstance(v, dict):
            out[k] = _resolve_dict(v, variables)  # type: ignore[arg-type]
        else:
            out[k] = v
    return out
