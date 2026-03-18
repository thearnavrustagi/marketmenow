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
        init_resp.raise_for_status()
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
        put_resp.raise_for_status()

        logger.info("Uploaded image %s -> %s", path.name, image_urn)
        return image_urn

    async def upload_images(
        self, paths: list[Path], alt_texts: list[str] | None = None,
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
        self, commentary: str, image_paths: list[Path],
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
        self, commentary: str, article_url: str, title: str = "",
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
            detail = resp.text
            logger.error(
                "LinkedIn API %d: %s", resp.status_code, detail,
            )
            resp.raise_for_status()
        post_id = resp.headers.get("x-restli-id", "")
        logger.info("Created LinkedIn post: %s", post_id)
        return post_id
