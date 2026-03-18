from __future__ import annotations

from marketmenow.normaliser import NormalisedContent

_YT_MAX_DESCRIPTION = 5000
_SHORTS_TAG = "shorts"


class YouTubeRenderer:
    """Satisfies ``ContentRenderer`` protocol -- YouTube Shorts transforms."""

    @property
    def platform_name(self) -> str:
        return "youtube"

    async def render(self, content: NormalisedContent) -> NormalisedContent:
        hashtags = [tag.lstrip("#") for tag in content.hashtags]
        if _SHORTS_TAG not in (t.lower() for t in hashtags):
            hashtags.insert(0, _SHORTS_TAG)

        text_segments = list(content.text_segments)
        if text_segments:
            hashtag_str = " ".join(f"#{t}" for t in hashtags)
            total_len = sum(len(s) for s in text_segments) + len(hashtag_str) + 2
            if total_len > _YT_MAX_DESCRIPTION:
                overflow = total_len - _YT_MAX_DESCRIPTION
                last = text_segments[-1]
                text_segments[-1] = last[: max(0, len(last) - overflow)]

        return content.model_copy(
            update={
                "text_segments": text_segments,
                "hashtags": hashtags,
            }
        )
