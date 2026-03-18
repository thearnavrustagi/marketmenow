from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from marketmenow.models.content import ContentModality
from marketmenow.models.result import PublishResult, SendResult
from marketmenow.normaliser import NormalisedContent

from .browser import FacebookBrowser

logger = logging.getLogger(__name__)


class FacebookAdapter:
    """Browser-based Facebook adapter satisfying ``PlatformAdapter`` protocol."""

    def __init__(self, browser: FacebookBrowser) -> None:
        self._browser = browser

    @property
    def platform_name(self) -> str:
        return "facebook"

    def supported_modalities(self) -> frozenset[ContentModality]:
        return frozenset(
            {
                ContentModality.TEXT_POST,
                ContentModality.IMAGE,
                ContentModality.VIDEO,
                ContentModality.DIRECT_MESSAGE,
            }
        )

    async def authenticate(self, credentials: dict[str, str]) -> None:
        if not await self._browser.is_logged_in():
            c_user = credentials.get("c_user", "")
            xs = credentials.get("xs", "")
            if c_user and xs:
                await self._browser.login_with_cookies(c_user, xs)
            else:
                raise RuntimeError(
                    "Not logged in and no cookies provided. "
                    "Run `mmn facebook login` first to create a session."
                )

    async def publish(self, content: NormalisedContent) -> PublishResult:
        try:
            commentary = self._build_commentary(content)
            match content.modality:
                case ContentModality.TEXT_POST:
                    success = await self._browser.create_text_post(commentary)
                case ContentModality.IMAGE:
                    image_paths = [Path(a.uri) for a in content.media_assets]
                    success = await self._browser.create_image_post(commentary, image_paths)
                case ContentModality.VIDEO:
                    if not content.media_assets:
                        return PublishResult(
                            platform="facebook",
                            success=False,
                            error_message="No video asset provided.",
                        )
                    video_path = Path(content.media_assets[0].uri)
                    success = await self._browser.create_video_post(commentary, video_path)
                case _:
                    return PublishResult(
                        platform="facebook",
                        success=False,
                        error_message=f"Unsupported modality: {content.modality}",
                    )

            return PublishResult(
                platform="facebook",
                success=success,
                published_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception("Facebook publish failed for modality %s", content.modality)
            return PublishResult(
                platform="facebook",
                success=False,
                error_message=str(exc),
            )

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        """Post to a Facebook Group (mapped via DIRECT_MESSAGE modality).

        The group URL is taken from ``extra["group_url"]`` or from the first
        entry in ``recipient_handles``.
        """
        group_url = str(content.extra.get("group_url", ""))
        if not group_url and content.recipient_handles:
            group_url = content.recipient_handles[0]

        if not group_url:
            return SendResult(
                platform="facebook",
                recipient_handle="",
                success=False,
                error_message="No group URL provided. Set extra['group_url'] or recipient_handles.",
            )

        try:
            text = "\n\n".join(content.text_segments) if content.text_segments else ""
            image_paths: list[Path] | None = None
            if content.media_assets:
                image_paths = [Path(a.uri) for a in content.media_assets]

            success = await self._browser.create_group_post(
                group_url, text, image_paths=image_paths
            )
            return SendResult(
                platform="facebook",
                recipient_handle=group_url,
                success=success,
            )
        except Exception as exc:
            logger.exception("Facebook group post failed for %s", group_url)
            return SendResult(
                platform="facebook",
                recipient_handle=group_url,
                success=False,
                error_message=str(exc),
            )

    def _build_commentary(self, content: NormalisedContent) -> str:
        parts: list[str] = list(content.text_segments)
        if content.hashtags:
            tag_line = " ".join(f"#{tag.lstrip('#')}" for tag in content.hashtags)
            parts.append(tag_line)
        return "\n\n".join(parts)
