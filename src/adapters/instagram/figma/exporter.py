from __future__ import annotations

from pathlib import Path

from marketmenow.models.content import ImagePost, MediaAsset

from .client import FigmaClient


class CarouselExporter:
    """Exports Figma frames as images and assembles an ``ImagePost`` content model."""

    def __init__(self, figma_client: FigmaClient, output_dir: Path) -> None:
        self._figma = figma_client
        self._output_dir = output_dir / "carousel"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def export(
        self,
        file_key: str,
        frame_ids: list[str] | None = None,
        caption: str = "",
        hashtags: list[str] | None = None,
        fmt: str = "png",
        scale: float = 2.0,
    ) -> ImagePost:
        """Export frames from a Figma file and return an ``ImagePost``.

        If *frame_ids* is ``None``, all top-level frames from the first
        page are exported.
        """
        if frame_ids is None:
            frames = await self._figma.get_file_frames(file_key)
            frame_ids = [f.node_id for f in frames]

        if len(frame_ids) < 2:
            raise ValueError("A carousel requires at least 2 frames")

        exports = await self._figma.export_frames(file_key, frame_ids, fmt=fmt, scale=scale)

        images: list[MediaAsset] = []
        for idx, export in enumerate(exports):
            if not export.image_url:
                continue
            dest = self._output_dir / f"{file_key}_{idx}.{fmt}"
            await self._figma.download_image(export.image_url, dest)

            mime = "image/png" if fmt == "png" else "image/jpeg"
            images.append(
                MediaAsset(uri=str(dest.resolve()), mime_type=mime),
            )

        if len(images) < 2:
            raise ValueError(f"Only {len(images)} images exported successfully; need at least 2")

        return ImagePost(
            images=images,
            caption=caption,
            hashtags=hashtags or [],
        )
