from __future__ import annotations

from adapters.reddit.renderer import RedditRenderer
from conftest import make_text_post
from marketmenow.models.content import ContentModality
from marketmenow.normaliser import NormalisedContent

renderer = RedditRenderer()


def _normalised(
    text_segments: list[str],
    hashtags: list[str] | None = None,
) -> NormalisedContent:
    return NormalisedContent(
        source=make_text_post(),
        modality=ContentModality.TEXT_POST,
        text_segments=text_segments,
        media_assets=[],
        hashtags=hashtags or ["tag1", "tag2"],
    )


class TestRedditRenderer:
    async def test_short_segment_unchanged(self) -> None:
        content = _normalised(["Hello Reddit"])
        result = await renderer.render(content)
        assert result.text_segments == ["Hello Reddit"]

    async def test_exactly_10000_unchanged(self) -> None:
        text = "x" * 10_000
        content = _normalised([text])
        result = await renderer.render(content)
        assert len(result.text_segments[0]) == 10_000

    async def test_over_10000_truncated(self) -> None:
        text = "y" * 15_000
        content = _normalised([text])
        result = await renderer.render(content)
        assert len(result.text_segments[0]) == 10_000

    async def test_hashtags_stripped(self) -> None:
        content = _normalised(["Post"], hashtags=["python", "dev"])
        result = await renderer.render(content)
        assert result.hashtags == []

    async def test_empty_segments(self) -> None:
        content = _normalised([])
        result = await renderer.render(content)
        assert result.text_segments == []

    async def test_platform_name(self) -> None:
        assert renderer.platform_name == "reddit"
