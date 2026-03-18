from __future__ import annotations

from marketmenow.models.content import MediaAsset
from marketmenow.models.result import MediaRef


class FacebookUploader:
    """Minimal uploader for Facebook -- browser handles actual file uploads."""

    @property
    def platform_name(self) -> str:
        return "facebook"

    async def upload(self, asset: MediaAsset) -> MediaRef:
        return MediaRef(
            platform="facebook",
            remote_id="",
            remote_url=asset.uri,
        )

    async def upload_batch(self, assets: list[MediaAsset]) -> list[MediaRef]:
        return [await self.upload(a) for a in assets]
