from __future__ import annotations

from marketmenow.models.content import MediaAsset
from marketmenow.models.result import MediaRef


class YouTubeUploader:
    """Passthrough uploader -- the YouTube Data API handles file uploads directly."""

    @property
    def platform_name(self) -> str:
        return "youtube"

    async def upload(self, asset: MediaAsset) -> MediaRef:
        return MediaRef(
            platform="youtube",
            remote_id="",
            remote_url=asset.uri,
        )

    async def upload_batch(self, assets: list[MediaAsset]) -> list[MediaRef]:
        return [await self.upload(a) for a in assets]
