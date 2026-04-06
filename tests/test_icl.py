from __future__ import annotations

from pathlib import Path

import pytest

from marketmenow.core.icl import (
    ExampleCache,
    WinningExample,
    cache_is_fresh,
    load_example_cache,
    select_icl_examples,
)


def _make_example(
    text: str, score: float = 1.0, embedding: list[float] | None = None
) -> WinningExample:
    return WinningExample(
        text=text,
        score=score,
        platform="test",
        embedding=embedding or [],
    )


class TestWinningExample:
    def test_frozen(self) -> None:
        from pydantic import ValidationError

        ex = _make_example("hello")
        with pytest.raises(ValidationError, match="frozen"):
            ex.text = "mutated"  # type: ignore[misc]

    def test_defaults(self) -> None:
        ex = WinningExample(text="hi")
        assert ex.context == ""
        assert ex.context_author == ""
        assert ex.score == 0.0
        assert ex.url == ""
        assert ex.platform == ""
        assert ex.embedding == []


class TestExampleCache:
    def test_empty(self) -> None:
        cache = ExampleCache()
        assert cache.last_collected == ""
        assert cache.examples == []


class TestLoadExampleCache:
    def test_missing_file(self, tmp_path: Path) -> None:
        cache = load_example_cache(tmp_path / "does_not_exist.json")
        assert cache.examples == []
        assert cache.last_collected == ""

    def test_valid_file(self, tmp_path: Path) -> None:
        data = ExampleCache(
            last_collected="2026-04-01T00:00:00+00:00",
            examples=[_make_example("test content", score=5.0)],
        )
        path = tmp_path / "cache.json"
        path.write_text(data.model_dump_json(), encoding="utf-8")

        loaded = load_example_cache(path)
        assert loaded.last_collected == "2026-04-01T00:00:00+00:00"
        assert len(loaded.examples) == 1
        assert loaded.examples[0].text == "test content"
        assert loaded.examples[0].score == 5.0

    def test_corrupt_file(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        cache = load_example_cache(path)
        assert cache.examples == []


class TestCacheIsFresh:
    def test_empty_timestamp(self) -> None:
        cache = ExampleCache()
        assert cache_is_fresh(cache, max_age_hours=168) is False

    def test_fresh_cache(self) -> None:
        from datetime import UTC, datetime

        cache = ExampleCache(last_collected=datetime.now(UTC).isoformat())
        assert cache_is_fresh(cache, max_age_hours=168) is True

    def test_stale_cache(self) -> None:
        cache = ExampleCache(last_collected="2020-01-01T00:00:00+00:00")
        assert cache_is_fresh(cache, max_age_hours=168) is False

    def test_invalid_timestamp(self) -> None:
        cache = ExampleCache(last_collected="not-a-date")
        assert cache_is_fresh(cache, max_age_hours=168) is False


class TestSelectIclExamples:
    def test_no_cache_file_returns_explore(self, tmp_path: Path) -> None:
        examples, exploring = select_icl_examples(
            tmp_path / "missing.json", max_examples=5, epsilon=0.0
        )
        # epsilon=0.0 means never explore by coin flip, but empty cache forces explore
        assert examples is None
        assert exploring is True

    def test_epsilon_one_always_explores(self, tmp_path: Path) -> None:
        cache = ExampleCache(
            last_collected="2026-04-01T00:00:00+00:00",
            examples=[_make_example("text", score=10.0)],
        )
        path = tmp_path / "cache.json"
        path.write_text(cache.model_dump_json(), encoding="utf-8")

        examples, exploring = select_icl_examples(path, max_examples=5, epsilon=1.0)
        assert examples is None
        assert exploring is True

    def test_epsilon_zero_exploits(self, tmp_path: Path) -> None:
        cache = ExampleCache(
            last_collected="2026-04-01T00:00:00+00:00",
            examples=[
                _make_example("best", score=10.0),
                _make_example("good", score=5.0),
                _make_example("ok", score=1.0),
            ],
        )
        path = tmp_path / "cache.json"
        path.write_text(cache.model_dump_json(), encoding="utf-8")

        examples, exploring = select_icl_examples(path, max_examples=2, epsilon=0.0)
        assert exploring is False
        assert examples is not None
        assert len(examples) == 2
        # Highest score example should be in the results
        texts = [e["text"] for e in examples]
        assert "best" in texts

    def test_max_examples_respected(self, tmp_path: Path) -> None:
        cache = ExampleCache(
            last_collected="2026-04-01T00:00:00+00:00",
            examples=[_make_example(f"ex{i}", score=float(10 - i)) for i in range(10)],
        )
        path = tmp_path / "cache.json"
        path.write_text(cache.model_dump_json(), encoding="utf-8")

        examples, exploring = select_icl_examples(path, max_examples=3, epsilon=0.0)
        assert exploring is False
        assert examples is not None
        assert len(examples) == 3
