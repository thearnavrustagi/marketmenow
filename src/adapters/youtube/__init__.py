from __future__ import annotations

from marketmenow.registry import PlatformBundle

from .adapter import YouTubeAdapter
from .renderer import YouTubeRenderer
from .settings import YouTubeSettings
from .uploader import YouTubeUploader


def create_youtube_bundle(
    settings: YouTubeSettings | None = None,
) -> PlatformBundle:
    """Construct a fully-wired YouTube ``PlatformBundle``."""
    if settings is None:
        settings = YouTubeSettings()

    return PlatformBundle(
        adapter=YouTubeAdapter(
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            refresh_token=settings.youtube_refresh_token,
            default_privacy=settings.youtube_default_privacy,
            default_category_id=settings.youtube_default_category_id,
        ),
        renderer=YouTubeRenderer(),
        uploader=YouTubeUploader(),
    )


__all__ = [
    "YouTubeAdapter",
    "YouTubeRenderer",
    "YouTubeSettings",
    "YouTubeUploader",
    "create_youtube_bundle",
]
