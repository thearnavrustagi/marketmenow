from __future__ import annotations

from marketmenow.models.content import ContentModality, MediaAsset
from marketmenow.models.result import MediaRef, PublishResult
from marketmenow.models.result import SendResult as CoreSendResult
from marketmenow.normaliser import NormalisedContent
from marketmenow.registry import PlatformBundle

from .settings import EmailSettings


class EmailAdapter:
    """Minimal ``PlatformAdapter`` shim for the email platform."""

    @property
    def platform_name(self) -> str:
        return "email"

    def supported_modalities(self) -> frozenset[ContentModality]:
        return frozenset({ContentModality.DIRECT_MESSAGE})

    async def authenticate(self, credentials: dict[str, str]) -> None:
        pass

    async def publish(self, content: NormalisedContent) -> PublishResult:
        return PublishResult(
            platform="email",
            success=False,
            error_message="Use `mmn email send` for email outreach",
        )

    async def send_dm(self, content: NormalisedContent) -> CoreSendResult:
        return CoreSendResult(
            platform="email",
            recipient_handle=content.recipient_handles[0] if content.recipient_handles else "",
            success=False,
            error_message="Use `mmn email send` for email outreach",
        )


class EmailRenderer:
    @property
    def platform_name(self) -> str:
        return "email"

    async def render(self, content: NormalisedContent) -> NormalisedContent:
        return content


class EmailUploader:
    @property
    def platform_name(self) -> str:
        return "email"

    async def upload(self, asset: MediaAsset) -> MediaRef:
        return MediaRef(platform="email", remote_id="", remote_url=asset.uri)

    async def upload_batch(self, assets: list[MediaAsset]) -> list[MediaRef]:
        return [await self.upload(a) for a in assets]


def create_email_bundle(
    settings: EmailSettings | None = None,
) -> PlatformBundle:
    """Construct a fully-wired Email ``PlatformBundle``."""
    if settings is None:
        settings = EmailSettings()

    return PlatformBundle(
        adapter=EmailAdapter(),
        renderer=EmailRenderer(),
        uploader=EmailUploader(),
    )


__all__ = [
    "EmailAdapter",
    "EmailRenderer",
    "EmailSettings",
    "EmailUploader",
    "create_email_bundle",
]
