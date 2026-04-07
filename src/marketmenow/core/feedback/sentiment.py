from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from jinja2 import Template

from marketmenow.core.feedback.models import CommentData
from marketmenow.integrations.llm import LLMProvider, create_llm_provider

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20
_PROMPTS_DIR = Path(__file__).resolve().parents[4] / "prompts" / "feedback"


@lru_cache(maxsize=4)
def _load_prompt(name: str) -> dict[str, str]:
    path = _PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    import yaml

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {"system": data.get("system", ""), "user": data.get("user", "")}


class SentimentScorer:
    """Scores YouTube comments on a 0-10 sentiment scale."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider()
        self._model = model

    async def score_comments(
        self,
        comments: list[dict[str, str]],
        video_title: str,
    ) -> list[CommentData]:
        """Score a list of comments and return CommentData objects."""
        if not comments:
            return []

        prompt_data = _load_prompt("score_sentiment")
        system_prompt = prompt_data["system"]
        user_template = Template(prompt_data["user"])

        results: list[CommentData] = []
        for i in range(0, len(comments), _BATCH_SIZE):
            batch = comments[i : i + _BATCH_SIZE]
            user_prompt = user_template.render(
                video_title=video_title,
                comments=batch,
            )
            scored = await self._call_llm(system_prompt, user_prompt)
            for item in scored:
                score = max(0.0, min(10.0, float(item.get("score", 5.0))))
                label = str(item.get("label", "neutral"))
                if label not in ("negative", "neutral", "positive"):
                    if score < 3.5:
                        label = "negative"
                    elif score > 6.5:
                        label = "positive"
                    else:
                        label = "neutral"

                # Find matching comment to preserve original fields
                comment_id = str(item.get("comment_id", ""))
                original = next((c for c in batch if c.get("comment_id") == comment_id), None)

                results.append(
                    CommentData(
                        comment_id=comment_id,
                        author=original.get("author", "") if original else "",
                        text=original.get("text", "") if original else "",
                        like_count=int(original.get("like_count", 0)) if original else 0,
                        published_at=original.get("published_at", "") if original else "",
                        sentiment_score=score,
                        sentiment_label=label,
                    )
                )

        return results

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> list[dict[str, object]]:
        response = await self._provider.generate_json(
            model=self._model,
            system=system_prompt,
            contents=user_prompt,
            temperature=0.3,
        )
        parsed = json.loads(response.text)
        if isinstance(parsed, list):
            return parsed  # type: ignore[no-any-return]
        return []
