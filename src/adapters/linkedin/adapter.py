from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from marketmenow.models.content import ContentModality
from marketmenow.models.result import PublishResult, SendResult
from marketmenow.normaliser import NormalisedContent

from .browser import LinkedInBrowser

logger = logging.getLogger(__name__)


class LinkedInAdapter:
    """Browser-based LinkedIn adapter satisfying ``PlatformAdapter`` protocol."""

    def __init__(self, browser: LinkedInBrowser) -> None:
        self._browser = browser

    @property
    def platform_name(self) -> str:
        return "linkedin"

    def supported_modalities(self) -> frozenset[ContentModality]:
        return frozenset(
            {
                ContentModality.TEXT_POST,
                ContentModality.IMAGE,
                ContentModality.VIDEO,
                ContentModality.DOCUMENT,
                ContentModality.ARTICLE,
                ContentModality.POLL,
            }
        )

    async def authenticate(self, credentials: dict[str, str]) -> None:
        if not await self._browser.is_logged_in():
            li_at = credentials.get("li_at", "")
            if li_at:
                await self._browser.login_with_cookie(li_at)
            else:
                raise RuntimeError(
                    "Not logged in and no li_at cookie provided. "
                    "Run `mmn linkedin login` first to create a session."
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
                            platform="linkedin",
                            success=False,
                            error_message="No video asset provided.",
                        )
                    video_path = Path(content.media_assets[0].uri)
                    success = await self._browser.create_video_post(commentary, video_path)
                case ContentModality.DOCUMENT:
                    if not content.media_assets:
                        return PublishResult(
                            platform="linkedin",
                            success=False,
                            error_message="No document asset provided.",
                        )
                    doc_path = Path(content.media_assets[0].uri)
                    doc_title = str(content.extra.get("document_title", ""))
                    success = await self._browser.create_document_post(
                        commentary,
                        doc_path,
                        title=doc_title,
                    )
                case ContentModality.ARTICLE:
                    article_url = str(content.extra.get("article_url", ""))
                    if not article_url:
                        return PublishResult(
                            platform="linkedin",
                            success=False,
                            error_message="No article URL provided.",
                        )
                    full_text = f"{commentary}\n\n{article_url}" if commentary else article_url
                    success = await self._browser.create_text_post(full_text)
                case ContentModality.POLL:
                    question = str(content.extra.get("poll_question", ""))
                    options: list[str] = content.extra.get("poll_options", [])  # type: ignore[assignment]
                    if not question or len(options) < 2:
                        return PublishResult(
                            platform="linkedin",
                            success=False,
                            error_message="Poll requires a question and at least 2 options.",
                        )
                    success = await self._browser.create_poll_post(
                        commentary,
                        question,
                        options,
                    )
                case _:
                    return PublishResult(
                        platform="linkedin",
                        success=False,
                        error_message=f"Unsupported modality: {content.modality}",
                    )

            return PublishResult(
                platform="linkedin",
                success=success,
                published_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception("LinkedIn publish failed for modality %s", content.modality)
            return PublishResult(
                platform="linkedin",
                success=False,
                error_message=str(exc),
            )

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        return SendResult(
            platform="linkedin",
            recipient_handle=(content.recipient_handles[0] if content.recipient_handles else ""),
            success=False,
            error_message="LinkedIn DMs are not supported in this adapter.",
        )

    def _build_commentary(self, content: NormalisedContent) -> str:
        parts: list[str] = list(content.text_segments)
        if content.hashtags:
            tag_line = " ".join(f"#{tag.lstrip('#')}" for tag in content.hashtags)
            parts.append(tag_line)
        return "\n\n".join(parts)
