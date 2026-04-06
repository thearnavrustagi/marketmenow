from __future__ import annotations

import json
import logging
import random
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from marketmenow.core.diversity_selector import select_diverse_examples

logger = logging.getLogger(__name__)


class WinningExample(BaseModel, frozen=True):
    """A single high-performing content example for ICL.

    Platform-agnostic: adapters map their native metrics into ``score``
    and their content into ``text`` / ``context``.
    """

    text: str
    context: str = ""
    context_author: str = ""
    score: float = 0.0
    url: str = ""
    platform: str = ""
    embedding: list[float] = Field(default_factory=list)


class ExampleCache(BaseModel):
    """Generic cache of winning examples for any platform."""

    last_collected: str = ""
    examples: list[WinningExample] = Field(default_factory=list)


def load_example_cache(path: Path) -> ExampleCache:
    """Load an :class:`ExampleCache` from *path*, returning empty on failure."""
    if not path.exists():
        return ExampleCache()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ExampleCache(**data)
    except Exception:
        logger.warning("Failed to load ICL example cache from %s, starting fresh", path)
        return ExampleCache()


def cache_is_fresh(cache: ExampleCache, max_age_hours: int) -> bool:
    """Return ``True`` if *cache* was collected less than *max_age_hours* ago."""
    if not cache.last_collected:
        return False
    try:
        collected_at = datetime.fromisoformat(cache.last_collected)
        age_hours = (datetime.now(UTC) - collected_at).total_seconds() / 3600
        return age_hours < max_age_hours
    except Exception:
        return False


def select_icl_examples(
    cache_path: Path,
    max_examples: int,
    epsilon: float,
) -> tuple[list[dict[str, object]] | None, bool]:
    """Epsilon-greedy ICL example selection.

    Returns ``(icl_examples, is_exploring)``.  When exploring,
    ``icl_examples`` is ``None`` (the LLM sees no examples).
    When exploiting, returns up to *max_examples* diverse,
    high-scoring examples via farthest-point sampling.
    """
    exploring = random.random() < epsilon

    if exploring:
        return None, True

    cache = load_example_cache(cache_path)
    if not cache.examples:
        return None, True  # no data to exploit — forced explore

    ranked = sorted(cache.examples, key=lambda e: e.score, reverse=True)
    candidate_pool = ranked[: max_examples * 4]

    selected = select_diverse_examples(
        candidate_pool,
        [e.embedding for e in candidate_pool],
        n=max_examples,
    )

    icl_examples = [e.model_dump() for e in selected]
    return icl_examples, False
