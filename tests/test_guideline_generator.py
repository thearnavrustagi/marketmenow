from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from marketmenow.core.feedback.guideline_generator import (
    GuidelineGenerator,
    should_generate_guidelines,
)
from marketmenow.core.feedback.models import (
    CommentData,
    ReelIndexEntry,
    VideoMetrics,
)


def _make_entry(
    *,
    view_count: int = 500,
    like_count: int = 50,
    avg_sentiment: float = 6.0,
) -> ReelIndexEntry:
    return ReelIndexEntry(
        reel_id="aabb",
        video_id="vid1",
        template_id="test_template",
        title="Test Reel",
        metrics=VideoMetrics(video_id="vid1", view_count=view_count, like_count=like_count),
        avg_sentiment=avg_sentiment,
    )


def test_should_generate_avoid_low_views() -> None:
    entry = _make_entry(view_count=100, like_count=10)
    assert should_generate_guidelines(entry) == "avoid"


def test_should_generate_avoid_low_like_ratio() -> None:
    entry = _make_entry(view_count=1000, like_count=5)  # 0.5% ratio
    assert should_generate_guidelines(entry) == "avoid"


def test_should_generate_avoid_low_sentiment() -> None:
    entry = _make_entry(avg_sentiment=2.0)
    assert should_generate_guidelines(entry) == "avoid"


def test_should_generate_replicate_high_like_ratio() -> None:
    entry = _make_entry(view_count=1000, like_count=100)  # 10% ratio
    assert should_generate_guidelines(entry) == "replicate"


def test_should_generate_replicate_high_sentiment() -> None:
    entry = _make_entry(avg_sentiment=8.0)
    assert should_generate_guidelines(entry) == "replicate"


def test_should_generate_none_for_average() -> None:
    entry = _make_entry(view_count=500, like_count=25, avg_sentiment=5.5)  # 5% ratio
    assert should_generate_guidelines(entry) is None


def test_should_generate_none_without_metrics() -> None:
    entry = ReelIndexEntry(reel_id="aabb", video_id="vid1")
    assert should_generate_guidelines(entry) is None


def _mock_provider(json_data: dict[str, object]) -> MagicMock:
    from marketmenow.integrations.llm import LLMResponse

    provider = MagicMock()
    provider.generate_json = AsyncMock(
        return_value=LLMResponse(text=json.dumps(json_data), raw=None)
    )
    return provider


async def test_analyze_reel_generates_guidelines() -> None:
    provider = _mock_provider(
        {
            "guidelines": [
                {
                    "guideline_type": "avoid",
                    "rule": "Don't use unclear timelines in stories",
                    "evidence": "Comments pointed out date inconsistencies",
                }
            ]
        }
    )

    generator = GuidelineGenerator(provider=provider)
    entry = _make_entry(view_count=100)
    entry = entry.model_copy(
        update={
            "comments": [
                CommentData(
                    comment_id="c1",
                    author="User",
                    text="Timeline makes no sense",
                    sentiment_score=2.0,
                    sentiment_label="negative",
                )
            ]
        }
    )

    guidelines = await generator.analyze_reel(entry, [])
    assert len(guidelines) == 1
    assert guidelines[0].guideline_type == "avoid"
    assert "timeline" in guidelines[0].rule.lower()
    assert guidelines[0].source_video_id == "vid1"


async def test_analyze_reel_no_metrics() -> None:
    provider = _mock_provider({})
    generator = GuidelineGenerator(provider=provider)
    entry = ReelIndexEntry(reel_id="aabb", video_id="vid1")
    guidelines = await generator.analyze_reel(entry, [])
    assert guidelines == []
