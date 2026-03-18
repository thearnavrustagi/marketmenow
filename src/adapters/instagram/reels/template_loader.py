from __future__ import annotations

from pathlib import Path

import yaml

from .models import (
    AudioSpec,
    AudioType,
    BeatDefinition,
    PipelineConfig,
    PipelineStepDef,
    QuestionTypeDef,
    ReelTemplate,
    TransitionSpec,
    WorksheetConfig,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _parse_transition(raw: dict[str, object] | None) -> TransitionSpec:
    if not raw:
        return TransitionSpec()
    return TransitionSpec(
        type=str(raw.get("type", "none")),
        duration_frames=int(raw.get("duration_frames", 0)),
        direction=str(raw.get("direction", "")),
        easing=str(raw.get("easing", "")),
    )


def _parse_worksheet(raw: dict[str, object] | None) -> WorksheetConfig | None:
    if not raw:
        return None
    question_types = [
        QuestionTypeDef(
            type=qt["type"],
            description=qt.get("description", ""),
            needs_image_prompt=qt.get("needs_image_prompt", False),
        )
        for qt in raw.get("question_types", [])
    ]
    num_range = raw.get("num_questions", [1, 3])
    if isinstance(num_range, list) and len(num_range) == 2:
        num_min, num_max = int(num_range[0]), int(num_range[1])
    else:
        num_min, num_max = 1, 3
    return WorksheetConfig(
        question_types=question_types,
        subjects=raw.get("subjects", []),
        num_questions_min=num_min,
        num_questions_max=num_max,
        fill_prompt=raw.get("fill_prompt", WorksheetConfig().fill_prompt),
    )


def _parse_pipeline(raw: dict[str, object] | None) -> PipelineConfig:
    if not raw:
        return PipelineConfig()
    steps: list[PipelineStepDef] = []
    for s in raw.get("steps", []):  # type: ignore[union-attr]
        inputs = s.get("inputs", {})
        steps.append(
            PipelineStepDef(
                id=s["id"],
                type=s["type"],
                inputs=inputs if isinstance(inputs, dict) else {},
                output_var=s.get("output_var", ""),
                output_fields=s.get("output_fields", []),
            )
        )
    return PipelineConfig(steps=steps)


class ReelTemplateLoader:
    """Discovers, loads, and validates YAML reel templates."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        self._dir = templates_dir or _TEMPLATES_DIR

    def list_templates(self) -> list[str]:
        """Return IDs of all available templates (filename without extension)."""
        return sorted(p.stem for p in self._dir.glob("*.yaml") if p.is_file())

    def load(self, template_id: str) -> ReelTemplate:
        """Load and validate a template by its ID."""
        path = self._dir / f"{template_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Template '{template_id}' not found at {path}")

        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        beats = [
            BeatDefinition(
                id=b["id"],
                scene=b["scene"],
                audio=AudioSpec(
                    type=AudioType(b["audio"]["type"]),
                    text=b["audio"].get("text", ""),
                    file=b["audio"].get("file", ""),
                    voice=b["audio"].get("voice", ""),
                ),
                duration=b.get("duration", "from_audio"),
                fixed_seconds=b.get("fixed_seconds", 0.0),
                pad_seconds=b.get("pad_seconds", 0.0),
                visual=b.get("visual", {}),
                entry_transition=_parse_transition(b.get("entry_transition")),
                exit_transition=_parse_transition(b.get("exit_transition")),
            )
            for b in raw.get("beats", [])
        ]

        return ReelTemplate(
            id=raw["id"],
            name=raw["name"],
            aspect_ratio=raw.get("aspect_ratio", "9:16"),
            fps=raw.get("fps", 30),
            composition_id=raw.get("composition_id", "ReelFromTemplate"),
            variables=raw.get("variables", []),
            beats=beats,
            pipeline=_parse_pipeline(raw.get("pipeline")),
            default_visual=raw.get("default_visual", {}),
            caption_template=raw.get("caption_template", ""),
            hashtags=raw.get("hashtags", []),
            hook_lines=raw.get("hook_lines", []),
            worksheet=_parse_worksheet(raw.get("worksheet")),
        )

    def validate(self, template_id: str) -> list[str]:
        """Validate a template and return a list of issues (empty = valid)."""
        issues: list[str] = []
        try:
            tmpl = self.load(template_id)
        except Exception as exc:
            return [f"Failed to load: {exc}"]

        if not tmpl.beats:
            issues.append("Template has no beats")

        seen_ids: set[str] = set()
        for beat in tmpl.beats:
            if beat.id in seen_ids:
                issues.append(f"Duplicate beat ID: {beat.id}")
            seen_ids.add(beat.id)

            if beat.audio.type == AudioType.TTS and not beat.audio.text:
                issues.append(f"Beat '{beat.id}': TTS audio has no text")
            if (
                beat.audio.type == AudioType.SFX
                and not beat.audio.file
                and beat.duration != "fixed"
            ):
                issues.append(f"Beat '{beat.id}': SFX audio has no file path")

            for label, t in [("entry", beat.entry_transition), ("exit", beat.exit_transition)]:
                valid_types = {"none", "fade", "slide", "scale", "wipe", "spring"}
                if t.type not in valid_types:
                    issues.append(
                        f"Beat '{beat.id}': {label}_transition type '{t.type}' not in {valid_types}"
                    )

        for step in tmpl.pipeline.steps:
            if not step.id:
                issues.append("Pipeline step missing 'id'")
            if not step.type:
                issues.append(f"Pipeline step '{step.id}' missing 'type'")

        return issues
