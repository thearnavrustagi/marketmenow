from __future__ import annotations

from marketmenow.models.content import MediaAsset
from marketmenow.models.result import MediaRef


class RedditUploader:
    """Stub uploader for Reddit — comments are text-only in this phase."""

    @property
    def platform_name(self) -> str:
        return "reddit"

    async def upload(self, asset: MediaAsset) -> MediaRef:
        return MediaRef(
            platform="reddit",
            remote_id="",
            remote_url=asset.uri,
        )

    async def upload_batch(self, assets: list[MediaAsset]) -> list[MediaRef]:
        return [await self.upload(a) for a in assets]
