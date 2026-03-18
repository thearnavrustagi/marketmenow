from __future__ import annotations

from marketmenow.registry import PlatformBundle

from .adapter import FacebookAdapter
from .browser import FacebookBrowser
from .renderer import FacebookRenderer
from .settings import FacebookSettings
from .uploader import FacebookUploader


def create_facebook_bundle(
    settings: FacebookSettings | None = None,
) -> PlatformBundle:
    """Construct a fully-wired Facebook ``PlatformBundle``."""
    if settings is None:
        settings = FacebookSettings()

    browser = FacebookBrowser(
        session_path=settings.facebook_session_path,
        user_data_dir=settings.facebook_user_data_dir,
        headless=settings.headless,
        slow_mo_ms=settings.slow_mo_ms,
        proxy_url=settings.proxy_url,
        viewport_width=settings.viewport_width,
        viewport_height=settings.viewport_height,
    )

    return PlatformBundle(
        adapter=FacebookAdapter(browser),
        renderer=FacebookRenderer(),
        uploader=FacebookUploader(),
    )


__all__ = [
    "FacebookAdapter",
    "FacebookBrowser",
    "FacebookRenderer",
    "FacebookSettings",
    "FacebookUploader",
    "create_facebook_bundle",
]
