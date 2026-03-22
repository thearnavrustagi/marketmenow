from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from marketmenow.models.content import ContentModality
from marketmenow.models.result import PublishResult, SendResult
from marketmenow.normaliser import NormalisedContent

from .api_client import LinkedInAPIClient

logger = logging.getLogger(__name__)

_POLL_DURATION_MAP: dict[int, str] = {
    1: "ONE_DAY",
    3: "THREE_DAYS",
    7: "ONE_WEEK",
    14: "TWO_WEEKS",
}


def _duration_for_days(days: int) -> str:
    if days <= 1:
        return "ONE_DAY"
    if days <= 3:
        return "THREE_DAYS"
    if days <= 7:
        return "ONE_WEEK"
    return "TWO_WEEKS"


class LinkedInAPIAdapter:
    """LinkedIn adapter that uses the official REST API (no browser)."""

    def __init__(self, client: LinkedInAPIClient) -> None:
        self._client = client

    @property
    def platform_name(self) -> str:
        return "linkedin"

    def supported_modalities(self) -> frozenset[ContentModality]:
        return frozenset(
            {
                ContentModality.TEXT_POST,
                ContentModality.IMAGE,
                ContentModality.ARTICLE,
                ContentModality.POLL,
            }
        )

    async def authenticate(self, credentials: dict[str, str]) -> None:
        pass

    async def publish(self, content: NormalisedContent) -> PublishResult:
        try:
            commentary = self._build_commentary(content)

            match content.modality:
                case ContentModality.TEXT_POST:
                    post_id = await self._client.create_text_post(commentary)

                case ContentModality.IMAGE:
                    image_paths = [Path(a.uri) for a in content.media_assets]
                    if not image_paths:
                        return self._fail("No image assets provided.")
                    post_id = await self._client.create_image_post(
                        commentary,
                        image_paths,
                    )

                case ContentModality.ARTICLE:
                    article_url = str(content.extra.get("article_url", ""))
                    if not article_url:
                        return self._fail("No article URL provided.")
                    post_id = await self._client.create_article_post(
                        commentary,
                        article_url,
                    )

                case ContentModality.POLL:
                    question = str(content.extra.get("poll_question", ""))
                    options: list[str] = content.extra.get("poll_options", [])  # type: ignore[assignment]
                    days: int = content.extra.get("poll_duration_days", 3)  # type: ignore[assignment]
                    if not question or len(options) < 2:
                        return self._fail(
                            "Poll requires a question and at least 2 options.",
                        )
                    post_id = await self._client.create_poll_post(
                        commentary,
                        question,
                        options,
                        duration=_duration_for_days(days),
                    )

                case _:
                    return self._fail(
                        f"Unsupported modality for API adapter: {content.modality}",
                    )

            return PublishResult(
                platform="linkedin",
                success=True,
                remote_post_id=post_id,
                published_at=datetime.now(UTC),
            )

        except Exception as exc:
            logger.exception("LinkedIn API publish failed for %s", content.modality)
            return self._fail(str(exc))

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        return SendResult(
            platform="linkedin",
            recipient_handle=(content.recipient_handles[0] if content.recipient_handles else ""),
            success=False,
            error_message="LinkedIn DMs are not supported via the API adapter.",
        )

    async def close(self) -> None:
        await self._client.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_commentary(self, content: NormalisedContent) -> str:
        parts: list[str] = list(content.text_segments)
        if content.hashtags:
            tag_line = " ".join(f"#{tag.lstrip('#')}" for tag in content.hashtags)
            parts.append(tag_line)
        return "\n\n".join(parts)

    @staticmethod
    def _fail(msg: str) -> PublishResult:
        return PublishResult(platform="linkedin", success=False, error_message=msg)
