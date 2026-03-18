from __future__ import annotations

from pathlib import Path

import httpx
from pydantic import BaseModel

_FIGMA_API_BASE = "https://api.figma.com/v1"


class FrameInfo(BaseModel, frozen=True):
    """Metadata for a single Figma frame node."""

    node_id: str
    name: str
    width: float
    height: float


class ExportedImage(BaseModel, frozen=True):
    """Result of exporting a single Figma frame to an image."""

    node_id: str
    image_url: str
    local_path: Path | None = None


class FigmaClient:
    """Async wrapper around the Figma REST API for frame discovery and image export."""

    def __init__(self, api_token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=_FIGMA_API_BASE,
            headers={"X-FIGMA-TOKEN": api_token},
            timeout=60.0,
        )

    async def get_file_frames(self, file_key: str) -> list[FrameInfo]:
        """Return all top-level FRAME nodes from the first page of a Figma file."""
        resp = await self._client.get(f"/files/{file_key}", params={"depth": 2})
        resp.raise_for_status()
        data = resp.json()

        frames: list[FrameInfo] = []
        for page in data.get("document", {}).get("children", []):
            for child in page.get("children", []):
                if child.get("type") == "FRAME":
                    bbox = child.get("absoluteBoundingBox", {})
                    frames.append(
                        FrameInfo(
                            node_id=child["id"],
                            name=child.get("name", ""),
                            width=bbox.get("width", 0),
                            height=bbox.get("height", 0),
                        )
                    )
        return frames

    async def export_frames(
        self,
        file_key: str,
        node_ids: list[str],
        fmt: str = "png",
        scale: float = 2.0,
    ) -> list[ExportedImage]:
        """Request Figma render URLs for a list of node IDs."""
        ids_param = ",".join(node_ids)
        resp = await self._client.get(
            f"/images/{file_key}",
            params={"ids": ids_param, "format": fmt, "scale": scale},
        )
        resp.raise_for_status()
        images_map: dict[str, str | None] = resp.json().get("images", {})

        return [ExportedImage(node_id=nid, image_url=url or "") for nid, url in images_map.items()]

    async def download_image(self, url: str, dest: Path) -> Path:
        """Download an image from a URL to a local path."""
        async with httpx.AsyncClient(timeout=120.0) as dl:
            resp = await dl.get(url)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
        return dest

    async def close(self) -> None:
        await self._client.aclose()
