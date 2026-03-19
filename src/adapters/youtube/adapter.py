from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from marketmenow.models.content import ContentModality
from marketmenow.models.result import MediaRef, PublishResult, SendResult
from marketmenow.normaliser import NormalisedContent

_YOUTUBE_API_SERVICE = "youtube"
_YOUTUBE_API_VERSION = "v3"
_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"

_MAX_TITLE = 100
_MAX_RETRIES = 3

logger = logging.getLogger(__name__)


class YouTubeAdapter:
    """YouTube Data API v3 adapter satisfying ``PlatformAdapter`` protocol."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        default_privacy: str = "private",
        default_category_id: str = "27",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._default_privacy = default_privacy
        self._default_category_id = default_category_id

    @property
    def platform_name(self) -> str:
        return "youtube"

    def supported_modalities(self) -> frozenset[ContentModality]:
        return frozenset({ContentModality.VIDEO})

    async def authenticate(self, credentials: dict[str, str]) -> None:
        creds = self._build_credentials()
        service = build(_YOUTUBE_API_SERVICE, _YOUTUBE_API_VERSION, credentials=creds)
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None, partial(service.channels().list(part="id", mine=True).execute)
        )
        if not resp.get("items"):
            raise RuntimeError("YouTube authentication failed: no channel found")
        service.close()

    async def publish(self, content: NormalisedContent) -> PublishResult:
        if content.modality != ContentModality.VIDEO:
            return PublishResult(
                platform="youtube",
                success=False,
                error_message=f"Unsupported modality: {content.modality}",
            )

        media_refs: list[MediaRef] = content.extra.get("_media_refs", [])  # type: ignore[assignment]
        video_path = (media_refs[0].remote_url or "") if media_refs else ""

        if not video_path or not Path(video_path).exists():
            return PublishResult(
                platform="youtube",
                success=False,
                error_message=f"Video file not found: {video_path}",
            )

        title = self._build_title(content)
        description = self._build_description(content)

        try:
            video_id = await self._upload_video(
                video_path=video_path,
                title=title,
                description=description,
                category_id=self._default_category_id,
                privacy_status=self._default_privacy,
            )
            return PublishResult(
                platform="youtube",
                success=True,
                remote_post_id=video_id,
                remote_url=f"https://youtube.com/shorts/{video_id}",
                published_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception("YouTube upload failed")
            return PublishResult(
                platform="youtube",
                success=False,
                error_message=str(exc),
            )

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        return SendResult(
            platform="youtube",
            recipient_handle=content.recipient_handles[0] if content.recipient_handles else "",
            success=False,
            error_message="YouTube does not support direct messages",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_credentials(self) -> Credentials:
        return Credentials(
            token=None,
            refresh_token=self._refresh_token,
            token_uri=_TOKEN_URI,
            client_id=self._client_id,
            client_secret=self._client_secret,
            scopes=_SCOPES,
        )

    async def _upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        category_id: str,
        privacy_status: str,
    ) -> str:
        """Upload a video via the YouTube Data API v3 resumable upload."""
        creds = self._build_credentials()
        service = build(_YOUTUBE_API_SERVICE, _YOUTUBE_API_VERSION, credentials=creds)

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": category_id,
                "tags": ["Shorts"],
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,
        )

        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        loop = asyncio.get_running_loop()
        video_id = await loop.run_in_executor(None, partial(self._execute_upload, request))
        service.close()
        return video_id

    @staticmethod
    def _execute_upload(request: object) -> str:
        """Execute a resumable upload synchronously (run in executor)."""
        response = None
        for attempt in range(_MAX_RETRIES):
            try:
                _, response = request.next_chunk()  # type: ignore[union-attr]
                if response is not None:
                    video_id: str = response["id"]
                    logger.info("YouTube upload complete: video_id=%s", video_id)
                    return video_id
            except Exception:
                if attempt == _MAX_RETRIES - 1:
                    raise
                logger.warning("Upload chunk failed (attempt %d), retrying...", attempt + 1)
        raise RuntimeError("YouTube upload failed: no response after retries")

    @staticmethod
    def _build_title(content: NormalisedContent) -> str:
        explicit = content.source.metadata.get("_yt_title", "")
        if explicit:
            base = explicit
        elif content.text_segments:
            base = content.text_segments[0].split("\n")[0].strip()
        else:
            base = "Short"
        if len(base) > _MAX_TITLE - 9:
            base = base[: _MAX_TITLE - 9].rstrip()
        if "#shorts" not in base.lower():
            base = f"{base} #Shorts"
        return base[:_MAX_TITLE]

    @staticmethod
    def _build_description(content: NormalisedContent) -> str:
        parts: list[str] = list(content.text_segments)
        if content.hashtags:
            tag_line = " ".join(f"#{tag.lstrip('#')}" for tag in content.hashtags)
            parts.append(tag_line)
        return "\n\n".join(parts)[:5000]
