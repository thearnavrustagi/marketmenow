from __future__ import annotations

import logging
from datetime import UTC, datetime

from marketmenow.models.content import ContentModality
from marketmenow.models.result import PublishResult, SendResult
from marketmenow.normaliser import NormalisedContent

from .client import RedditClient

logger = logging.getLogger(__name__)


class RedditAdapter:
    """Cookie-based Reddit adapter satisfying ``PlatformAdapter`` protocol."""

    def __init__(self, client: RedditClient) -> None:
        self._client = client

    @property
    def platform_name(self) -> str:
        return "reddit"

    def supported_modalities(self) -> frozenset[ContentModality]:
        return frozenset({ContentModality.REPLY, ContentModality.TEXT_POST})

    async def authenticate(self, credentials: dict[str, str]) -> None:
        if not await self._client.is_logged_in():
            raise RuntimeError(
                "Reddit session cookie is invalid or expired. "
                "Update REDDIT_SESSION in your .env with a fresh cookie "
                "from DevTools > Application > Cookies > reddit.com."
            )

    async def publish(self, content: NormalisedContent) -> PublishResult:
        if content.modality == ContentModality.REPLY:
            return await self._publish_comment(content)
        if content.modality == ContentModality.TEXT_POST:
            return await self._publish_post(content)

        return PublishResult(
            platform="reddit",
            success=False,
            error_message=f"Unsupported modality: {content.modality}",
        )

    async def _publish_comment(self, content: NormalisedContent) -> PublishResult:
        parent_fullname: str = content.extra.get("in_reply_to_platform_id", "")  # type: ignore[assignment]
        comment_text = content.text_segments[0] if content.text_segments else ""

        if not parent_fullname or not comment_text:
            return PublishResult(
                platform="reddit",
                success=False,
                error_message="Missing parent fullname or comment text",
            )

        try:
            resp = await self._client.post_comment(parent_fullname, comment_text)
            json_data = resp.get("json", {})
            errors = json_data.get("errors", []) if isinstance(json_data, dict) else []  # type: ignore[union-attr]

            if errors:
                error_str = str(errors)
                logger.error("Reddit API errors: %s", error_str)
                return PublishResult(
                    platform="reddit",
                    success=False,
                    error_message=error_str,
                )

            things = (
                json_data.get("data", {}).get("things", [])  # type: ignore[union-attr]
                if isinstance(json_data, dict)
                else []
            )
            remote_id = ""
            if things and isinstance(things[0], dict):
                remote_id = str(things[0].get("data", {}).get("id", ""))

            return PublishResult(
                platform="reddit",
                success=True,
                remote_post_id=remote_id,
                published_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception("Failed to post comment to %s", parent_fullname)
            return PublishResult(
                platform="reddit",
                success=False,
                error_message=str(exc),
            )

    async def _publish_post(self, content: NormalisedContent) -> PublishResult:
        return PublishResult(
            platform="reddit",
            success=False,
            error_message="Text post publishing not yet implemented — comment-only for now",
        )

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        return SendResult(
            platform="reddit",
            recipient_handle=(content.recipient_handles[0] if content.recipient_handles else ""),
            success=False,
            error_message="Reddit DMs are not supported in this adapter",
        )
