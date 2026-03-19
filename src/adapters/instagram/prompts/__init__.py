from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_PROMPTS_DIR = _PROJECT_ROOT / "prompts" / "instagram"


@lru_cache(maxsize=32)
def load_prompt(name: str) -> dict[str, str]:
    """Load a prompt YAML file and return ``{"system": ..., "user": ...}``."""
    path = _PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return {
        "system": data.get("system", ""),
        "user": data.get("user", ""),
    }
