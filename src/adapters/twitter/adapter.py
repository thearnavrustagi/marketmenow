from __future__ import annotations

import logging
from datetime import UTC, datetime

from marketmenow.models.content import ContentModality
from marketmenow.models.result import PublishResult, SendResult
from marketmenow.normaliser import NormalisedContent

from .browser import StealthBrowser

logger = logging.getLogger(__name__)


class TwitterAdapter:
    """Browser-based Twitter/X adapter satisfying ``PlatformAdapter`` protocol."""

    def __init__(self, browser: StealthBrowser) -> None:
        self._browser = browser

    @property
    def platform_name(self) -> str:
        return "twitter"

    def supported_modalities(self) -> frozenset[ContentModality]:
        return frozenset({ContentModality.REPLY, ContentModality.THREAD})

    async def authenticate(self, credentials: dict[str, str]) -> None:
        if not await self._browser.is_logged_in():
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            if username and password:
                await self._browser.login(username, password)
            else:
                raise RuntimeError(
                    "Not logged in and no credentials provided. "
                    "Run `mmn-x login` first to create a session."
                )

    async def publish(self, content: NormalisedContent) -> PublishResult:
        if content.modality == ContentModality.REPLY:
            return await self._publish_reply(content)
        if content.modality == ContentModality.THREAD:
            return await self._publish_thread(content)

        return PublishResult(
            platform="twitter",
            success=False,
            error_message=f"Unsupported modality: {content.modality}",
        )

    async def _publish_reply(self, content: NormalisedContent) -> PublishResult:
        post_url: str = content.extra.get("in_reply_to_url", "")  # type: ignore[assignment]
        reply_text = content.text_segments[0] if content.text_segments else ""

        if not post_url or not reply_text:
            return PublishResult(
                platform="twitter",
                success=False,
                error_message="Missing post URL or reply text",
            )

        try:
            success = await self._browser.post_reply(post_url, reply_text)
            return PublishResult(
                platform="twitter",
                success=success,
                remote_url=post_url,
                published_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception("Failed to post reply to %s", post_url)
            return PublishResult(
                platform="twitter",
                success=False,
                error_message=str(exc),
            )

    async def _publish_thread(self, content: NormalisedContent) -> PublishResult:
        tweets = list(content.text_segments)
        if not tweets:
            return PublishResult(
                platform="twitter",
                success=False,
                error_message="Thread has no tweets",
            )

        try:
            success = await self._browser.post_thread(tweets)
            return PublishResult(
                platform="twitter",
                success=success,
                published_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception("Failed to post thread")
            return PublishResult(
                platform="twitter",
                success=False,
                error_message=str(exc),
            )

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        return SendResult(
            platform="twitter",
            recipient_handle=(content.recipient_handles[0] if content.recipient_handles else ""),
            success=False,
            error_message="Twitter DMs are not supported in this adapter",
        )
