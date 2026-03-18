from __future__ import annotations

from marketmenow.normaliser import NormalisedContent

_MAX_COMMENT_LENGTH = 10_000


class RedditRenderer:
    """Content renderer for Reddit — strips hashtags, enforces char limit."""

    @property
    def platform_name(self) -> str:
        return "reddit"

    async def render(self, content: NormalisedContent) -> NormalisedContent:
        cleaned: list[str] = []
        for seg in content.text_segments:
            text = seg[:_MAX_COMMENT_LENGTH]
            cleaned.append(text)

        return content.model_copy(
            update={"text_segments": cleaned, "hashtags": []},
        )
