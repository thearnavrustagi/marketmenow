from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from marketmenow.models.content import ContentModality
from marketmenow.models.result import MediaRef, PublishResult, SendResult
from marketmenow.normaliser import NormalisedContent

_FB_GRAPH_BASE = "https://graph.facebook.com/v21.0"
_IG_GRAPH_BASE = "https://graph.instagram.com/v21.0"

logger = logging.getLogger(__name__)


def _base_url_for_token(token: str) -> str:
    """IGAA tokens (Instagram Business Login) use graph.instagram.com;
    EAA tokens (Facebook Login) use graph.facebook.com."""
    if token.startswith("IGAA"):
        return _IG_GRAPH_BASE
    return _FB_GRAPH_BASE


def _raise_for_status(resp: httpx.Response) -> None:
    """Raise with Meta's error message included for debuggability."""
    if resp.is_success:
        return
    try:
        body = resp.json()
        meta_err = body.get("error", {})
        msg = meta_err.get("message", resp.text)
        code = meta_err.get("code", "")
        subcode = meta_err.get("error_subcode", "")
        logger.error("Instagram API %s (code=%s, subcode=%s): %s", resp.status_code, code, subcode, msg)
    except Exception:
        msg = resp.text
    resp.raise_for_status()


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

        if content.modality == ContentModality.IMAGE:
            return await self._publish_carousel(content, media_refs)
        if content.modality == ContentModality.VIDEO:
            return await self._publish_reel(content, media_refs)

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
            resp = await self._client.post(
                f"/{self._account_id}/media",
                params=self._params(),
                data={"image_url": url, "is_carousel_item": "true"},
            )
            _raise_for_status(resp)
            child_ids.append(resp.json()["id"])

        caption = self._build_caption(content)
        resp = await self._client.post(
            f"/{self._account_id}/media",
            params=self._params(),
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

        resp = await self._client.post(
            f"/{self._account_id}/media",
            params=self._params(),
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
            },
        )
        _raise_for_status(resp)
        container_id = resp.json()["id"]

        return await self._await_and_publish(container_id)

    async def _await_and_publish(self, container_id: str) -> PublishResult:
        import asyncio

        for _ in range(30):
            status_resp = await self._client.get(
                f"/{container_id}",
                params=self._params({"fields": "status_code"}),
            )
            _raise_for_status(status_resp)
            status = status_resp.json().get("status_code")
            if status == "FINISHED":
                break
            if status == "ERROR":
                return PublishResult(
                    platform="instagram",
                    success=False,
                    error_message=f"Container {container_id} failed processing",
                )
            await asyncio.sleep(2)

        resp = await self._client.post(
            f"/{self._account_id}/media_publish",
            params=self._params(),
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
