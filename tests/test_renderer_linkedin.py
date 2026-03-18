from __future__ import annotations

from adapters.linkedin.renderer import LinkedInRenderer
from conftest import make_text_post
from marketmenow.models.content import ContentModality, MediaAsset
from marketmenow.normaliser import NormalisedContent

renderer = LinkedInRenderer()


def _normalised(
    text_segments: list[str],
    hashtags: list[str] | None = None,
    modality: ContentModality = ContentModality.TEXT_POST,
    media_assets: list[MediaAsset] | None = None,
) -> NormalisedContent:
    return NormalisedContent(
        source=make_text_post(),
        modality=modality,
        text_segments=text_segments,
        media_assets=media_assets or [],
        hashtags=hashtags or [],
    )


class TestLinkedInRenderer:
    async def test_within_limit_unchanged(self) -> None:
        content = _normalised(["Short post"], hashtags=["ai"])
        result = await renderer.render(content)
        assert result.text_segments == ["Short post"]
        assert result.hashtags == ["ai"]

    async def test_hashtag_hash_stripped(self) -> None:
        content = _normalised(["Post"], hashtags=["#ai", "#ml", "tech"])
        result = await renderer.render(content)
        assert result.hashtags == ["ai", "ml", "tech"]

    async def test_over_3000_truncates_text(self) -> None:
        long_text = "a" * 2990
        content = _normalised([long_text], hashtags=["longhashtag"])
        result = await renderer.render(content)
        total = sum(len(s) for s in result.text_segments)
        hashtag_str = " ".join(f"#{t}" for t in result.hashtags)
        assert total + 2 + len(hashtag_str) <= 3000

    async def test_truncated_segment_has_ellipsis(self) -> None:
        long_text = "b" * 3000
        content = _normalised([long_text], hashtags=["tag"])
        result = await renderer.render(content)
        assert result.text_segments[0].endswith("...")

    async def test_extremely_long_hashtags_trimmed_to_5(self) -> None:
        tags = [f"{'x' * 50}_{i}" for i in range(50)]
        content = _normalised(["tiny"], hashtags=tags)
        result = await renderer.render(content)
        assert len(result.hashtags) <= 50  # trimmed if over budget

    async def test_image_media_capped_at_20(self) -> None:
        assets = [MediaAsset(uri=f"img{i}.png", mime_type="image/png") for i in range(25)]
        content = _normalised(["carousel"], modality=ContentModality.IMAGE, media_assets=assets)
        result = await renderer.render(content)
        assert len(result.media_assets) == 20

    async def test_non_image_media_not_capped(self) -> None:
        assets = [MediaAsset(uri=f"vid{i}.mp4", mime_type="video/mp4") for i in range(25)]
        content = _normalised(
            ["videos"],
            modality=ContentModality.VIDEO,
            media_assets=assets,
        )
        result = await renderer.render(content)
        assert len(result.media_assets) == 25

    async def test_empty_text(self) -> None:
        content = _normalised([], hashtags=["ai"])
        result = await renderer.render(content)
        assert result.text_segments == []

    async def test_platform_name(self) -> None:
        assert renderer.platform_name == "linkedin"
