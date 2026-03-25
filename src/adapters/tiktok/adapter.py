from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime
from pathlib import Path

import httpx

from marketmenow.models.content import ContentModality
from marketmenow.models.result import MediaRef, PublishResult, SendResult
from marketmenow.normaliser import NormalisedContent

_TIKTOK_API_BASE = "https://open.tiktokapis.com"
_TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB
_MIN_CHUNK_SIZE = 5 * 1024 * 1024  # 5 MB per TikTok docs
_MAX_CHUNK_SIZE = 64 * 1024 * 1024  # 64 MB per TikTok docs
_MAX_CAPTION = 2200

_MAX_RETRIES = 3
_STATUS_POLL_INTERVAL_S = 5.0
_STATUS_POLL_MAX_ATTEMPTS = 120

logger = logging.getLogger(__name__)


class TikTokAPIError(Exception):
    """Wraps a TikTok API error with code and message."""

    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        self.status_code = status_code
        self.error_code = error_code
        detail = f"TikTok API error ({error_code}): {message}"
        hint = _error_hint(error_code)
        if hint:
            detail += f"\n  -> Fix: {hint}"
        super().__init__(detail)


_ERROR_HINTS: dict[str, str] = {
    "access_token_invalid": (
        "Access token is invalid or expired. Run `mmn tiktok auth` to get a new one, "
        "or check TIKTOK_REFRESH_TOKEN in .env."
    ),
    "scope_not_authorized": (
        "Token lacks video.publish scope. Re-run `mmn tiktok auth` and grant the "
        "required permissions."
    ),
    "spam_risk_too_many_posts": "Daily post cap reached. Wait until tomorrow.",
    "rate_limit_exceeded": "Rate limited. Wait a few minutes and retry.",
    "privacy_level_option_mismatch": (
        "Privacy level not allowed for this account. Query creator info first "
        "or change TIKTOK_DEFAULT_PRIVACY in .env."
    ),
    "unaudited_client_can_only_post_to_private_accounts": (
        "Unaudited app — posts are restricted to private. Complete the TikTok "
        "developer audit to post publicly."
    ),
    "url_ownership_unverified": (
        "PULL_FROM_URL requires domain ownership verification on the TikTok developer portal."
    ),
}


def _error_hint(error_code: str) -> str:
    return _ERROR_HINTS.get(error_code, "")


def _raise_for_tiktok(resp: httpx.Response) -> None:
    """Raise TikTokAPIError if the response indicates failure."""
    if resp.is_success:
        try:
            body = resp.json()
            err = body.get("error", {})
            code = err.get("code", "ok")
            if code != "ok":
                raise TikTokAPIError(resp.status_code, code, err.get("message", ""))
        except (ValueError, KeyError):
            pass
        return
    error_code = ""
    message = resp.text
    try:
        body = resp.json()
        err = body.get("error", {})
        error_code = err.get("code", "")
        message = err.get("message", resp.text)
    except Exception:
        pass
    raise TikTokAPIError(resp.status_code, error_code, message)


class TikTokAdapter:
    """TikTok adapter satisfying ``PlatformAdapter`` protocol.

    Supports two publishing modes:
    - **API mode**: Uses the Content Posting API (Direct Post) when
      ``access_token`` is provided.  Requires a TikTok developer app.
    - **Browser mode**: Uses Playwright + ``sessionid`` cookie when
      ``session_id`` is provided.  No developer app needed.

    If both are set, API mode takes precedence.
    """

    def __init__(
        self,
        client_key: str = "",
        client_secret: str = "",
        access_token: str = "",
        refresh_token: str = "",
        default_privacy: str = "SELF_ONLY",
        session_id: str = "",
        session_path: str = ".tiktok_session.json",
        user_data_dir: str = ".tiktok_browser_profile",
        headless: bool = True,
        slow_mo_ms: int = 50,
        proxy_url: str = "",
        viewport_width: int = 1280,
        viewport_height: int = 900,
    ) -> None:
        self._client_key = client_key
        self._client_secret = client_secret
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._default_privacy = default_privacy
        self._client = httpx.AsyncClient(timeout=120.0)

        # Browser mode settings
        self._session_id = session_id
        self._session_path = Path(session_path)
        self._user_data_dir = Path(user_data_dir)
        self._headless = headless
        self._slow_mo_ms = slow_mo_ms
        self._proxy_url = proxy_url
        self._viewport_width = viewport_width
        self._viewport_height = viewport_height

    @property
    def _use_browser(self) -> bool:
        """True when browser mode should be used (no API token, but cookie set)."""
        return bool(self._session_id) and not bool(self._access_token)

    @property
    def platform_name(self) -> str:
        return "tiktok"

    def supported_modalities(self) -> frozenset[ContentModality]:
        return frozenset({ContentModality.VIDEO})

    async def authenticate(self, credentials: dict[str, str]) -> None:
        """Validate the token by querying creator info."""
        resp = await self._client.post(
            f"{_TIKTOK_API_BASE}/v2/post/publish/creator_info/query/",
            headers=self._auth_headers(),
            content=b"",
        )
        _raise_for_tiktok(resp)

    async def publish(self, content: NormalisedContent) -> PublishResult:
        if content.modality != ContentModality.VIDEO:
            return PublishResult(
                platform="tiktok",
                success=False,
                error_message=f"Unsupported modality: {content.modality}",
            )

        media_refs: list[MediaRef] = content.extra.get("_media_refs", [])  # type: ignore[assignment]
        video_path = (media_refs[0].remote_url or "") if media_refs else ""

        if not video_path or not Path(video_path).exists():
            return PublishResult(
                platform="tiktok",
                success=False,
                error_message=f"Video file not found: {video_path}",
            )

        title = self._build_caption(content)

        if self._use_browser:
            return await self._publish_via_browser(video_path, title)
        return await self._publish_via_api(video_path, title)

    async def _publish_via_api(self, video_path: str, title: str) -> PublishResult:
        """Publish using the TikTok Content Posting API (Direct Post)."""
        try:
            await self._try_refresh_token()
            publish_id = await self._direct_post(video_path, title)
            await self._poll_status(publish_id)
            return PublishResult(
                platform="tiktok",
                success=True,
                remote_post_id=publish_id,
                published_at=datetime.now(UTC),
            )
        except TikTokAPIError as exc:
            logger.exception("TikTok API publish failed")
            return PublishResult(
                platform="tiktok",
                success=False,
                error_message=str(exc),
            )
        except Exception as exc:
            logger.exception("TikTok API publish failed")
            return PublishResult(
                platform="tiktok",
                success=False,
                error_message=str(exc),
            )

    async def _publish_via_browser(self, video_path: str, caption: str) -> PublishResult:
        """Publish using Playwright browser automation with session cookie."""
        try:
            from .browser import TikTokBrowser

            browser = TikTokBrowser(
                session_path=self._session_path,
                user_data_dir=self._user_data_dir,
                headless=self._headless,
                slow_mo_ms=self._slow_mo_ms,
                proxy_url=self._proxy_url,
                viewport_width=self._viewport_width,
                viewport_height=self._viewport_height,
            )
            async with browser:
                if not self._session_path.exists():
                    await browser.login_with_cookies(self._session_id)

                if not await browser.is_logged_in():
                    await browser.login_with_cookies(self._session_id)

                ok = await browser.upload_video(Path(video_path), caption)
                if ok:
                    return PublishResult(
                        platform="tiktok",
                        success=True,
                        published_at=datetime.now(UTC),
                    )
                return PublishResult(
                    platform="tiktok",
                    success=False,
                    error_message="Browser upload returned failure",
                )
        except Exception as exc:
            logger.exception("TikTok browser publish failed")
            return PublishResult(
                platform="tiktok",
                success=False,
                error_message=str(exc),
            )

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        return SendResult(
            platform="tiktok",
            recipient_handle=content.recipient_handles[0] if content.recipient_handles else "",
            success=False,
            error_message="TikTok does not support direct messages via API",
        )

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _try_refresh_token(self) -> None:
        """Attempt to refresh the access token using the refresh token."""
        if not self._refresh_token or not self._client_key or not self._client_secret:
            return
        try:
            resp = await self._client.post(
                _TIKTOK_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_key": self._client_key,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
            )
            if resp.is_success:
                body = resp.json()
                new_token = body.get("access_token", "")
                new_refresh = body.get("refresh_token", "")
                if new_token:
                    self._access_token = new_token
                    logger.debug("TikTok access token refreshed")
                if new_refresh:
                    self._refresh_token = new_refresh
        except Exception as exc:
            logger.debug("Token refresh failed (will use existing token): %s", exc)

    # ------------------------------------------------------------------
    # Direct Post flow
    # ------------------------------------------------------------------

    async def _direct_post(self, video_path: str, title: str) -> str:
        """Initialize a Direct Post, upload chunks, return publish_id."""
        file_path = Path(video_path)
        video_size = file_path.stat().st_size

        chunk_size, total_chunks = self._compute_chunks(video_size)

        init_resp = await self._init_post(
            video_size=video_size,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            title=title,
        )
        data = init_resp.json().get("data", {})
        publish_id: str = data.get("publish_id", "")
        upload_url: str = data.get("upload_url", "")

        if not upload_url:
            raise TikTokAPIError(200, "missing_upload_url", "No upload_url in init response")

        await self._upload_chunks(file_path, upload_url, video_size, chunk_size, total_chunks)
        return publish_id

    async def _init_post(
        self,
        video_size: int,
        chunk_size: int,
        total_chunks: int,
        title: str,
    ) -> httpx.Response:
        """POST /v2/post/publish/video/init/ to initialize the upload."""
        body: dict[str, object] = {
            "post_info": {
                "title": title[:_MAX_CAPTION],
                "privacy_level": self._default_privacy,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        }
        resp = await self._client.post(
            f"{_TIKTOK_API_BASE}/v2/post/publish/video/init/",
            headers=self._auth_headers(),
            json=body,
        )
        _raise_for_tiktok(resp)
        return resp

    async def _upload_chunks(
        self,
        file_path: Path,
        upload_url: str,
        video_size: int,
        chunk_size: int,
        total_chunks: int,
    ) -> None:
        """Upload the video file in sequential chunks via PUT."""
        with file_path.open("rb") as f:
            for i in range(total_chunks):
                first_byte = i * chunk_size
                if i == total_chunks - 1:
                    chunk_data = f.read()
                else:
                    chunk_data = f.read(chunk_size)

                last_byte = first_byte + len(chunk_data) - 1
                content_range = f"bytes {first_byte}-{last_byte}/{video_size}"

                for attempt in range(_MAX_RETRIES):
                    try:
                        resp = await self._client.put(
                            upload_url,
                            headers={
                                "Content-Type": "video/mp4",
                                "Content-Length": str(len(chunk_data)),
                                "Content-Range": content_range,
                            },
                            content=chunk_data,
                        )
                        if resp.status_code in (201, 206):
                            break
                        if resp.status_code >= 500 and attempt < _MAX_RETRIES - 1:
                            logger.warning(
                                "Chunk %d upload got %s, retrying (%d/%d)",
                                i,
                                resp.status_code,
                                attempt + 1,
                                _MAX_RETRIES,
                            )
                            await asyncio.sleep(2.0 * (2**attempt))
                            continue
                        resp.raise_for_status()
                    except httpx.HTTPError:
                        if attempt == _MAX_RETRIES - 1:
                            raise
                        logger.warning(
                            "Chunk %d upload failed, retrying (%d/%d)",
                            i,
                            attempt + 1,
                            _MAX_RETRIES,
                        )
                        await asyncio.sleep(2.0 * (2**attempt))

                logger.debug(
                    "Uploaded chunk %d/%d (%s)",
                    i + 1,
                    total_chunks,
                    content_range,
                )

    async def _poll_status(self, publish_id: str) -> None:
        """Poll /v2/post/publish/status/fetch/ until the post is published."""
        for attempt in range(_STATUS_POLL_MAX_ATTEMPTS):
            try:
                resp = await self._client.post(
                    f"{_TIKTOK_API_BASE}/v2/post/publish/status/fetch/",
                    headers=self._auth_headers(),
                    json={"publish_id": publish_id},
                )
                if resp.is_success:
                    body = resp.json()
                    status = body.get("data", {}).get("status", "")
                    if status == "PUBLISH_COMPLETE":
                        logger.info("TikTok publish complete: %s", publish_id)
                        return
                    if status in ("FAILED", "PUBLISH_FAILED"):
                        fail_reason = body.get("data", {}).get("fail_reason", "unknown")
                        raise TikTokAPIError(
                            200,
                            "publish_failed",
                            f"Publish failed: {fail_reason}",
                        )
            except TikTokAPIError:
                raise
            except Exception as exc:
                logger.debug("Status poll attempt %d error: %s", attempt + 1, exc)

            await asyncio.sleep(_STATUS_POLL_INTERVAL_S)

        raise TikTokAPIError(
            200,
            "publish_timeout",
            f"Publish status not resolved after {_STATUS_POLL_MAX_ATTEMPTS} polls",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    @staticmethod
    def _compute_chunks(video_size: int) -> tuple[int, int]:
        """Return (chunk_size, total_chunks) respecting TikTok constraints."""
        if video_size <= _MIN_CHUNK_SIZE:
            return video_size, 1

        chunk_size = _CHUNK_SIZE
        total_chunks = math.floor(video_size / chunk_size)
        if total_chunks == 0:
            total_chunks = 1
            chunk_size = video_size

        if total_chunks > 1000:
            chunk_size = math.ceil(video_size / 1000)
            chunk_size = max(chunk_size, _MIN_CHUNK_SIZE)
            total_chunks = math.floor(video_size / chunk_size)

        return chunk_size, total_chunks

    @staticmethod
    def _build_caption(content: NormalisedContent) -> str:
        parts: list[str] = list(content.text_segments)
        if content.hashtags:
            tag_line = " ".join(f"#{tag.lstrip('#')}" for tag in content.hashtags)
            parts.append(tag_line)
        caption = "\n\n".join(parts)
        return caption[:_MAX_CAPTION]
