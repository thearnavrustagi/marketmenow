from __future__ import annotations

from adapters.twitter.renderer import TwitterRenderer
from conftest import make_text_post
from marketmenow.models.content import ContentModality
from marketmenow.normaliser import ContentNormaliser, NormalisedContent

renderer = TwitterRenderer()
normaliser = ContentNormaliser()


def _normalised(text_segments: list[str]) -> NormalisedContent:
    post = make_text_post()
    return NormalisedContent(
        source=post,
        modality=ContentModality.TEXT_POST,
        text_segments=text_segments,
        media_assets=[],
    )


class TestTwitterRenderer:
    async def test_short_segment_unchanged(self) -> None:
        content = _normalised(["Hello world"])
        result = await renderer.render(content)
        assert result.text_segments == ["Hello world"]

    async def test_exactly_280_unchanged(self) -> None:
        text = "x" * 280
        content = _normalised([text])
        result = await renderer.render(content)
        assert result.text_segments == [text]

    async def test_over_280_truncated(self) -> None:
        text = "y" * 300
        content = _normalised([text])
        result = await renderer.render(content)
        assert len(result.text_segments[0]) == 280
        assert result.text_segments[0].endswith("...")

    async def test_truncation_at_277_plus_ellipsis(self) -> None:
        text = "a" * 500
        content = _normalised([text])
        result = await renderer.render(content)
        truncated = result.text_segments[0]
        assert truncated == "a" * 277 + "..."

    async def test_multiple_segments(self) -> None:
        content = _normalised(["short", "z" * 300])
        result = await renderer.render(content)
        assert result.text_segments[0] == "short"
        assert len(result.text_segments[1]) == 280

    async def test_empty_segments(self) -> None:
        content = _normalised([])
        result = await renderer.render(content)
        assert result.text_segments == []

    async def test_platform_name(self) -> None:
        assert renderer.platform_name == "twitter"
