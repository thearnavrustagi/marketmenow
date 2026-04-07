from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from marketmenow.core.feedback.sentiment import SentimentScorer
from marketmenow.integrations.llm import LLMResponse


def _mock_provider(json_data: list[dict[str, object]]) -> MagicMock:
    provider = MagicMock()
    provider.generate_json = AsyncMock(
        return_value=LLMResponse(text=json.dumps(json_data), raw=None)
    )
    return provider


async def test_score_comments_basic() -> None:
    provider = _mock_provider(
        [
            {
                "comment_id": "c1",
                "score": 8.5,
                "label": "positive",
                "reasoning": "Strong praise.",
            },
            {
                "comment_id": "c2",
                "score": 2.0,
                "label": "negative",
                "reasoning": "Disappointed.",
            },
        ]
    )

    scorer = SentimentScorer(provider=provider)
    comments = [
        {
            "comment_id": "c1",
            "author": "User1",
            "text": "Great!",
            "like_count": "5",
            "published_at": "",
        },
        {
            "comment_id": "c2",
            "author": "User2",
            "text": "Bad",
            "like_count": "0",
            "published_at": "",
        },
    ]
    results = await scorer.score_comments(comments, "Test Video")

    assert len(results) == 2
    assert results[0].sentiment_score == 8.5
    assert results[0].sentiment_label == "positive"
    assert results[0].author == "User1"
    assert results[1].sentiment_score == 2.0
    assert results[1].sentiment_label == "negative"


async def test_score_comments_empty() -> None:
    provider = _mock_provider([])
    scorer = SentimentScorer(provider=provider)
    results = await scorer.score_comments([], "Test")
    assert results == []


async def test_score_clamps_to_range() -> None:
    provider = _mock_provider(
        [
            {"comment_id": "c1", "score": 15.0, "label": "positive", "reasoning": ""},
            {"comment_id": "c2", "score": -3.0, "label": "negative", "reasoning": ""},
        ]
    )

    scorer = SentimentScorer(provider=provider)
    comments = [
        {"comment_id": "c1", "author": "", "text": "", "like_count": "0", "published_at": ""},
        {"comment_id": "c2", "author": "", "text": "", "like_count": "0", "published_at": ""},
    ]
    results = await scorer.score_comments(comments, "Test")

    assert results[0].sentiment_score == 10.0
    assert results[1].sentiment_score == 0.0


async def test_score_fixes_invalid_label() -> None:
    provider = _mock_provider(
        [{"comment_id": "c1", "score": 1.0, "label": "bad_label", "reasoning": ""}]
    )

    scorer = SentimentScorer(provider=provider)
    comments = [
        {"comment_id": "c1", "author": "", "text": "", "like_count": "0", "published_at": ""}
    ]
    results = await scorer.score_comments(comments, "Test")
    assert results[0].sentiment_label == "negative"  # score 1.0 < 3.5
