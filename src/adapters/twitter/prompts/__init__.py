from __future__ import annotations

from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_PROMPTS_DIR = _PROJECT_ROOT / "prompts" / "twitter"


def load_prompt(name: str, project_slug: str | None = None) -> dict[str, str]:
    """Load a prompt YAML file and return ``{"system": ..., "user": ...}``."""
    if project_slug:
        from marketmenow.core.project_manager import ProjectManager

        pm = ProjectManager()
        try:
            path = pm.resolve_path(
                project_slug,
                "prompts",
                "twitter",
                f"{name}.yaml",
                fallback=_PROMPTS_DIR.parent,
            )
        except FileNotFoundError:
            path = _PROMPTS_DIR / f"{name}.yaml"
    else:
        path = _PROMPTS_DIR / f"{name}.yaml"

    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return {
        "system": data.get("system", ""),
        "user": data.get("user", ""),
    }
