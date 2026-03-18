from __future__ import annotations

from adapters.instagram.renderer import InstagramRenderer
from conftest import make_image
from marketmenow.models.content import ContentModality, MediaAsset
from marketmenow.normaliser import NormalisedContent

renderer = InstagramRenderer()


def _normalised(
    text_segments: list[str],
    hashtags: list[str] | None = None,
    modality: ContentModality = ContentModality.IMAGE,
    media_assets: list[MediaAsset] | None = None,
) -> NormalisedContent:
    return NormalisedContent(
        source=make_image(),
        modality=modality,
        text_segments=text_segments,
        media_assets=media_assets or [],
        hashtags=hashtags or [],
    )


class TestInstagramRenderer:
    async def test_within_caption_limit(self) -> None:
        content = _normalised(["Short caption"], hashtags=["photo"])
        result = await renderer.render(content)
        assert result.text_segments == ["Short caption"]

    async def test_hashtag_stripped(self) -> None:
        content = _normalised(["Post"], hashtags=["#ai", "ml"])
        result = await renderer.render(content)
        assert result.hashtags == ["ai", "ml"]

    async def test_overflow_trims_last_segment(self) -> None:
        long_text = "c" * 2200
        content = _normalised([long_text], hashtags=["tag"])
        result = await renderer.render(content)
        total_len = sum(len(s) for s in result.text_segments)
        hashtag_str = " ".join(f"#{t}" for t in result.hashtags)
        assert total_len + len(hashtag_str) + 2 <= 2200

    async def test_image_media_capped_at_10(self) -> None:
        assets = [MediaAsset(uri=f"img{i}.png", mime_type="image/png") for i in range(15)]
        content = _normalised(
            ["carousel"],
            modality=ContentModality.IMAGE,
            media_assets=assets,
        )
        result = await renderer.render(content)
        assert len(result.media_assets) == 10

    async def test_video_not_capped(self) -> None:
        assets = [MediaAsset(uri=f"vid{i}.mp4", mime_type="video/mp4") for i in range(15)]
        content = _normalised(
            ["multi"],
            modality=ContentModality.VIDEO,
            media_assets=assets,
        )
        result = await renderer.render(content)
        assert len(result.media_assets) == 15

    async def test_video_aspect_ratio_in_extra(self) -> None:
        content = _normalised(["reel"], modality=ContentModality.VIDEO)
        result = await renderer.render(content)
        assert "ig_aspect" in result.extra
        assert result.extra["ig_aspect"]["width"] == 1080
        assert result.extra["ig_aspect"]["height"] == 1920

    async def test_image_aspect_ratio_in_extra(self) -> None:
        content = _normalised(["post"], modality=ContentModality.IMAGE)
        result = await renderer.render(content)
        assert result.extra["ig_aspect"]["width"] == 1080
        assert result.extra["ig_aspect"]["height"] == 1080

    async def test_text_post_no_aspect(self) -> None:
        content = _normalised(["text"], modality=ContentModality.TEXT_POST)
        result = await renderer.render(content)
        assert "ig_aspect" not in result.extra

    async def test_empty_segments(self) -> None:
        content = _normalised([])
        result = await renderer.render(content)
        assert result.text_segments == []

    async def test_platform_name(self) -> None:
        assert renderer.platform_name == "instagram"
