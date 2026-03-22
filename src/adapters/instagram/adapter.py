from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import httpx

from marketmenow.models.content import ContentModality
from marketmenow.models.result import MediaRef, PublishResult, SendResult
from marketmenow.normaliser import NormalisedContent

_FB_GRAPH_BASE = "https://graph.facebook.com/v21.0"
_IG_GRAPH_BASE = "https://graph.instagram.com/v21.0"

_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 3.0

logger = logging.getLogger(__name__)


def _base_url_for_token(token: str) -> str:
    """IGAA tokens (Instagram Business Login) use graph.instagram.com;
    EAA tokens (Facebook Login) use graph.facebook.com."""
    if token.startswith("IGAA"):
        return _IG_GRAPH_BASE
    return _FB_GRAPH_BASE


class InstagramAPIError(Exception):
    """Wraps a Meta Graph API error with an actionable message."""

    def __init__(
        self, status_code: int, meta_message: str, meta_code: str = "", subcode: str = ""
    ) -> None:
        self.status_code = status_code
        self.meta_message = meta_message
        self.meta_code = meta_code
        self.subcode = subcode

        hint = _error_hint(status_code, meta_code, subcode, meta_message)
        detail = f"Instagram API error: {meta_message}"
        if hint:
            detail += f"\n  -> Fix: {hint}"
        super().__init__(detail)


_ERROR_HINTS: list[tuple[str, str]] = [
    (
        "API access blocked",
        "Your Instagram access token has been revoked or the app is in restricted mode. Generate a new token at https://developers.facebook.com and update INSTAGRAM_ACCESS_TOKEN in .env.",
    ),
    (
        "Invalid OAuth",
        "The access token is malformed or expired. Generate a fresh token and update INSTAGRAM_ACCESS_TOKEN in .env.",
    ),
    (
        "expired",
        "Your access token has expired (they last ~60 days). Generate a new long-lived token and update INSTAGRAM_ACCESS_TOKEN in .env.",
    ),
    (
        "does not exist",
        "The Instagram Business Account ID is wrong. Check INSTAGRAM_BUSINESS_ACCOUNT_ID in .env matches your account.",
    ),
    (
        "not authorized",
        "Your token doesn't have the required permissions. Re-authenticate with instagram_basic + instagram_content_publish scopes.",
    ),
    (
        "media_type",
        "Instagram rejected the media format. Reels must be MP4, 9:16 aspect ratio, 3-90 seconds. Carousels need JPEG/PNG under 8MB.",
    ),
    (
        "transcode",
        "Instagram couldn't process the video. Try a different codec (H.264) or reduce resolution to 1080x1920.",
    ),
    (
        "URL is not reachable",
        "Instagram can't fetch the media from S3. The presigned URL may have expired. Check your AWS_S3_BUCKET and AWS credentials in .env.",
    ),
    ("rate limit", "You've hit Instagram's rate limit. Wait 5-10 minutes before retrying."),
]


def _error_hint(status_code: int, meta_code: str, subcode: str, message: str) -> str:
    """Return an actionable hint based on the Meta error details."""
    msg_lower = message.lower()
    for pattern, hint in _ERROR_HINTS:
        if pattern.lower() in msg_lower:
            return hint
    if meta_code == "190":
        return "Access token is invalid or expired. Generate a new one at https://developers.facebook.com and update INSTAGRAM_ACCESS_TOKEN in .env."
    if meta_code == "10" or meta_code == "200":
        return "Permission denied. Make sure your app has instagram_content_publish permission and the token has the right scopes."
    if status_code == 429:
        return "Rate limited by Instagram. Wait a few minutes and try again."
    if status_code >= 500:
        return "Instagram's servers are having issues. Try again in a few minutes."
    return ""


def _raise_for_status(resp: httpx.Response) -> None:
    """Raise with Meta's error message and an actionable hint."""
    if resp.is_success:
        return
    meta_message = resp.text
    meta_code = ""
    subcode = ""
    try:
        body = resp.json()
        meta_err = body.get("error", {})
        meta_message = meta_err.get("message", resp.text)
        meta_code = str(meta_err.get("code", ""))
        subcode = str(meta_err.get("error_subcode", ""))
    except Exception:
        pass
    logger.error(
        "Instagram API %s (code=%s, subcode=%s): %s",
        resp.status_code,
        meta_code,
        subcode,
        meta_message,
    )
    raise InstagramAPIError(resp.status_code, meta_message, meta_code, subcode)


class InstagramAdapter:
    """Instagram Graph API adapter satisfying ``PlatformAdapter`` protocol."""

    def __init__(self, access_token: str, business_account_id: str) -> None:
        self._token = access_token
        self._account_id = business_account_id
        self._client = httpx.AsyncClient(
            base_url=_base_url_for_token(access_token),
            timeout=60.0,
        )

    def set_access_token(self, token: str) -> None:
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=_base_url_for_token(token),
            timeout=60.0,
        )

    def _params(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        params = {"access_token": self._token}
        if extra:
            params.update(extra)
        return params

    @property
    def platform_name(self) -> str:
        return "instagram"

    def supported_modalities(self) -> frozenset[ContentModality]:
        return frozenset({ContentModality.VIDEO, ContentModality.IMAGE})

    async def authenticate(self, credentials: dict[str, str]) -> None:
        resp = await self._client.get(
            f"/{self._account_id}",
            params=self._params({"fields": "id,username"}),
        )
        _raise_for_status(resp)

    async def resolve_user_id(self) -> None:
        """For IGAA tokens, resolve the app-scoped user ID from ``/me``."""
        if not self._token.startswith("IGAA"):
            return
        resp = await self._client.get("/me", params=self._params({"fields": "id,username,user_id"}))
        _raise_for_status(resp)
        data = resp.json()
        app_scoped_id = data["id"]
        logger.info(
            "Resolved Instagram app-scoped ID: %s (username=%s)",
            app_scoped_id,
            data.get("username", ""),
        )
        self._account_id = app_scoped_id

    async def publish(self, content: NormalisedContent) -> PublishResult:
        media_refs: list[MediaRef] = content.extra.get("_media_refs", [])  # type: ignore[assignment]

        try:
            if content.modality == ContentModality.IMAGE:
                return await self._publish_carousel(content, media_refs)
            if content.modality == ContentModality.VIDEO:
                return await self._publish_reel(content, media_refs)
        except InstagramAPIError as exc:
            logger.exception("Instagram publish failed")
            return PublishResult(
                platform="instagram",
                success=False,
                error_message=str(exc),
            )
        except httpx.HTTPStatusError as exc:
            logger.exception("Instagram publish HTTP error")
            return PublishResult(
                platform="instagram",
                success=False,
                error_message=f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
            )

        return PublishResult(
            platform="instagram",
            success=False,
            error_message=f"Unsupported modality: {content.modality}",
        )

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        return SendResult(
            platform="instagram",
            recipient_handle=content.recipient_handles[0] if content.recipient_handles else "",
            success=False,
            error_message="Instagram DMs via Graph API are not supported in this adapter",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _publish_carousel(
        self, content: NormalisedContent, media_refs: list[MediaRef]
    ) -> PublishResult:
        await self.resolve_user_id()

        child_ids: list[str] = []
        for ref in media_refs:
            url = ref.remote_url or ""
            resp = await self._post_with_retry(
                f"/{self._account_id}/media",
                data={"image_url": url, "is_carousel_item": "true"},
            )
            _raise_for_status(resp)
            child_ids.append(resp.json()["id"])

        caption = self._build_caption(content)
        resp = await self._post_with_retry(
            f"/{self._account_id}/media",
            data={
                "media_type": "CAROUSEL",
                "caption": caption,
                "children": ",".join(child_ids),
            },
        )
        _raise_for_status(resp)
        container_id = resp.json()["id"]

        return await self._await_and_publish(container_id)

    async def _publish_reel(
        self, content: NormalisedContent, media_refs: list[MediaRef]
    ) -> PublishResult:
        await self.resolve_user_id()

        video_url = (media_refs[0].remote_url or "") if media_refs else ""
        caption = self._build_caption(content)

        resp = await self._post_with_retry(
            f"/{self._account_id}/media",
            data={"media_type": "REELS", "video_url": video_url, "caption": caption},
        )
        _raise_for_status(resp)
        container_id = resp.json()["id"]

        return await self._await_and_publish(container_id)

    async def _post_with_retry(
        self,
        path: str,
        *,
        data: dict[str, str],
    ) -> httpx.Response:
        """POST to the Graph API with retry + backoff on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.post(
                    path,
                    params=self._params(),
                    data=data,
                )
                if resp.is_success or resp.status_code in (400, 403):
                    return resp
                logger.warning(
                    "Instagram API %s on attempt %d/%d for %s — retrying",
                    resp.status_code,
                    attempt + 1,
                    _MAX_RETRIES,
                    path,
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning(
                    "Instagram request failed on attempt %d/%d: %s — retrying",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                )
            await asyncio.sleep(_INITIAL_BACKOFF_S * (2**attempt))

        if last_exc:
            raise last_exc
        return await self._client.post(path, params=self._params(), data=data)

    async def _await_and_publish(self, container_id: str) -> PublishResult:
        for _ in range(60):
            try:
                status_resp = await self._client.get(
                    f"/{container_id}",
                    params=self._params({"fields": "status_code,status"}),
                )
                if not status_resp.is_success:
                    await asyncio.sleep(3)
                    continue
                data = status_resp.json()
                status = data.get("status_code")
                if status == "FINISHED":
                    break
                if status == "ERROR":
                    detail = data.get("status", "unknown")
                    return PublishResult(
                        platform="instagram",
                        success=False,
                        error_message=f"Container {container_id} failed: {detail}",
                    )
            except httpx.HTTPError:
                pass
            await asyncio.sleep(3)

        resp = await self._post_with_retry(
            f"/{self._account_id}/media_publish",
            data={"creation_id": container_id},
        )
        _raise_for_status(resp)
        post_id = resp.json().get("id", "")

        return PublishResult(
            platform="instagram",
            success=True,
            remote_post_id=post_id,
            remote_url=f"https://www.instagram.com/p/{post_id}/",
            published_at=datetime.now(UTC),
        )

    @staticmethod
    def _build_caption(content: NormalisedContent) -> str:
        parts: list[str] = list(content.text_segments)
        if content.hashtags:
            tag_line = " ".join(f"#{tag.lstrip('#')}" for tag in content.hashtags)
            parts.append(tag_line)
        caption = "\n\n".join(parts)
        return caption[:2200]
