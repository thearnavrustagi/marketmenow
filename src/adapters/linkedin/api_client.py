from __future__ import annotations

import logging
from pathlib import Path

import httpx

from .settings import LinkedInSettings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.linkedin.com"


class LinkedInAPIClient:
    """Thin wrapper around LinkedIn's REST Posts API.

    Handles image uploads and post creation for text, single-image,
    multi-image (carousel), article-share, and poll content types.
    """

    def __init__(self, settings: LinkedInSettings) -> None:
        self._author = settings.author_urn
        self._version = settings.linkedin_api_version
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.linkedin_access_token}",
                "LinkedIn-Version": self._version,
                "X-Restli-Protocol-Version": "2.0.0",
            },
            timeout=60.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Image upload
    # ------------------------------------------------------------------

    async def upload_image(self, path: Path, alt_text: str = "") -> str:
        """Upload an image and return its ``urn:li:image:…`` URN."""
        init_resp = await self._client.post(
            "/rest/images?action=initializeUpload",
            json={"initializeUploadRequest": {"owner": self._author}},
        )
        if not init_resp.is_success:
            self._raise_with_hint(init_resp, "initialize image upload")
        data = init_resp.json()["value"]
        upload_url: str = data["uploadUrl"]
        image_urn: str = data["image"]

        image_bytes = path.read_bytes()
        put_resp = await self._client.put(
            upload_url,
            content=image_bytes,
            headers={
                "Content-Type": "application/octet-stream",
                "Authorization": self._client.headers["Authorization"],
            },
        )
        if not put_resp.is_success:
            self._raise_with_hint(put_resp, "upload image bytes")

        logger.info("Uploaded image %s -> %s", path.name, image_urn)
        return image_urn

    async def upload_images(
        self,
        paths: list[Path],
        alt_texts: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """Upload multiple images and return ``[{"id": urn, "altText": …}, …]``."""
        alts = alt_texts or [""] * len(paths)
        results: list[dict[str, str]] = []
        for path, alt in zip(paths, alts, strict=False):
            urn = await self.upload_image(path, alt)
            results.append({"id": urn, "altText": alt})
        return results

    # ------------------------------------------------------------------
    # Post creation
    # ------------------------------------------------------------------

    async def create_text_post(self, commentary: str) -> str:
        """Create a text-only post. Returns the post URN."""
        body = self._base_post_body(commentary)
        return await self._create_post(body)

    async def create_image_post(
        self,
        commentary: str,
        image_paths: list[Path],
    ) -> str:
        """Create a single-image or multi-image (carousel) post."""
        images = await self.upload_images(image_paths)

        body = self._base_post_body(commentary)
        if len(images) == 1:
            body["content"] = {"media": {"id": images[0]["id"], "altText": images[0]["altText"]}}
        else:
            body["content"] = {"multiImage": {"images": images}}

        return await self._create_post(body)

    async def create_article_post(
        self,
        commentary: str,
        article_url: str,
        title: str = "",
    ) -> str:
        """Share a link / article."""
        body = self._base_post_body(commentary)
        article: dict[str, str] = {"source": article_url}
        if title:
            article["title"] = title
        body["content"] = {"article": article}
        return await self._create_post(body)

    async def create_poll_post(
        self,
        commentary: str,
        question: str,
        options: list[str],
        duration: str = "THREE_DAYS",
    ) -> str:
        """Create a poll post. ``duration`` is ONE_DAY | THREE_DAYS | ONE_WEEK | TWO_WEEKS."""
        body = self._base_post_body(commentary)
        body["content"] = {
            "poll": {
                "question": question,
                "options": [{"text": opt} for opt in options[:4]],
                "settings": {"duration": duration},
            },
        }
        return await self._create_post(body)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _base_post_body(self, commentary: str) -> dict[str, object]:
        return {
            "author": self._author,
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
        }

    async def _create_post(self, body: dict[str, object]) -> str:
        logger.debug("POST /rest/posts author=%s", body.get("author"))
        resp = await self._client.post("/rest/posts", json=body)
        if resp.status_code >= 400:
            self._raise_with_hint(resp, "create post")
        post_id = resp.headers.get("x-restli-id", "")
        logger.info("Created LinkedIn post: %s", post_id)
        return post_id

    @staticmethod
    def _raise_with_hint(resp: httpx.Response, action: str) -> None:
        detail = resp.text[:500]
        status = resp.status_code
        hint = ""
        detail_lower = detail.lower()
        if status == 401 or "unauthorized" in detail_lower:
            hint = "LinkedIn access token is invalid or expired. Run `mmn auth linkedin --oauth` to generate a new one."
        elif status == 403 or "not enough permissions" in detail_lower:
            hint = "Your LinkedIn token lacks the required scope. Re-authenticate with `mmn auth linkedin --oauth` and approve w_member_social permission."
        elif "author" in detail_lower and "invalid" in detail_lower:
            hint = "LINKEDIN_PERSON_URN is wrong. Run `mmn auth linkedin --oauth` which auto-detects your URN, or set it manually in .env."
        elif status == 429:
            hint = "LinkedIn rate limit hit. Wait a few minutes before retrying."
        elif status >= 500:
            hint = "LinkedIn's servers are having issues. Try again in a few minutes."
        msg = f"LinkedIn API error {status} during {action}: {detail}"
        if hint:
            msg += f"\n  -> Fix: {hint}"
        logger.error(msg)
        raise httpx.HTTPStatusError(msg, request=resp.request, response=resp)
