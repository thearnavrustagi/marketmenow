from __future__ import annotations

from pathlib import Path

import yaml

from .models import AudioSpec, AudioType, BeatDefinition, ReelTemplate

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class ReelTemplateLoader:
    """Discovers, loads, and validates YAML reel templates."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        self._dir = templates_dir or _TEMPLATES_DIR

    def list_templates(self) -> list[str]:
        """Return IDs of all available templates (filename without extension)."""
        return sorted(
            p.stem for p in self._dir.glob("*.yaml") if p.is_file()
        )

    def load(self, template_id: str) -> ReelTemplate:
        """Load and validate a template by its ID."""
        path = self._dir / f"{template_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(
                f"Template '{template_id}' not found at {path}"
            )

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
            )
            for b in raw.get("beats", [])
        ]

        return ReelTemplate(
            id=raw["id"],
            name=raw["name"],
            aspect_ratio=raw.get("aspect_ratio", "9:16"),
            fps=raw.get("fps", 30),
            variables=raw.get("variables", []),
            beats=beats,
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

        return issues
