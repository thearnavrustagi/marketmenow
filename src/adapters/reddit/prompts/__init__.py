from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=32)
def load_prompt(name: str) -> dict[str, str]:
    """Load a YAML prompt file and return ``{"system": ..., "user": ...}``."""
    path = Path(__file__).parent / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, str] = yaml.safe_load(f)
    return data
