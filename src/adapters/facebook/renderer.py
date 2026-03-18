from __future__ import annotations

from marketmenow.models.content import ContentModality
from marketmenow.normaliser import NormalisedContent

_FB_MAX_POST_LENGTH = 63_206
_FB_MAX_IMAGES = 10


class FacebookRenderer:
    """Satisfies ``ContentRenderer`` protocol -- Facebook-specific transforms."""

    @property
    def platform_name(self) -> str:
        return "facebook"

    async def render(self, content: NormalisedContent) -> NormalisedContent:
        hashtags = [tag.lstrip("#") for tag in content.hashtags]
        text_segments = list(content.text_segments)

        hashtag_str = " ".join(f"#{t}" for t in hashtags) if hashtags else ""
        total_text_len = sum(len(s) for s in text_segments)
        separator_len = 2 if hashtag_str else 0

        if total_text_len + separator_len + len(hashtag_str) > _FB_MAX_POST_LENGTH:
            budget = _FB_MAX_POST_LENGTH - separator_len - len(hashtag_str)
            if budget < 0:
                hashtags = hashtags[:10]
                hashtag_str = " ".join(f"#{t}" for t in hashtags)
                budget = _FB_MAX_POST_LENGTH - 2 - len(hashtag_str)
            truncated: list[str] = []
            remaining = budget
            for seg in text_segments:
                if remaining <= 0:
                    break
                if len(seg) <= remaining:
                    truncated.append(seg)
                    remaining -= len(seg)
                else:
                    truncated.append(seg[: remaining - 3] + "...")
                    remaining = 0
            text_segments = truncated

        media_assets = content.media_assets
        if content.modality == ContentModality.IMAGE:
            media_assets = media_assets[:_FB_MAX_IMAGES]

        return content.model_copy(
            update={
                "text_segments": text_segments,
                "hashtags": hashtags,
                "media_assets": media_assets,
            }
        )
