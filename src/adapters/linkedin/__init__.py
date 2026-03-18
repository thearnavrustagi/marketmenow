from __future__ import annotations

import logging

from marketmenow.registry import PlatformBundle

from .adapter import LinkedInAdapter
from .api_adapter import LinkedInAPIAdapter
from .api_client import LinkedInAPIClient
from .browser import LinkedInBrowser
from .renderer import LinkedInRenderer
from .settings import LinkedInSettings
from .uploader import LinkedInUploader

logger = logging.getLogger(__name__)


def create_linkedin_bundle(
    settings: LinkedInSettings | None = None,
) -> PlatformBundle:
    """Construct a fully-wired LinkedIn ``PlatformBundle``.

    When ``LINKEDIN_ACCESS_TOKEN`` is set, the bundle uses the REST API
    adapter (no browser, no session expiry).  Otherwise it falls back to
    the Playwright browser adapter.
    """
    if settings is None:
        settings = LinkedInSettings()

    if settings.use_api:
        logger.info("LinkedIn: using REST API adapter")
        client = LinkedInAPIClient(settings)
        adapter: LinkedInAdapter | LinkedInAPIAdapter = LinkedInAPIAdapter(client)
    else:
        logger.info("LinkedIn: using browser adapter (set LINKEDIN_ACCESS_TOKEN for API mode)")
        browser = LinkedInBrowser(
            session_path=settings.linkedin_session_path,
            user_data_dir=settings.linkedin_user_data_dir,
            headless=settings.headless,
            slow_mo_ms=settings.slow_mo_ms,
            proxy_url=settings.proxy_url,
            viewport_width=settings.viewport_width,
            viewport_height=settings.viewport_height,
            organization_id=settings.linkedin_organization_id,
        )
        adapter = LinkedInAdapter(browser)

    return PlatformBundle(
        adapter=adapter,
        renderer=LinkedInRenderer(),
        uploader=LinkedInUploader(),
    )


__all__ = [
    "LinkedInAPIAdapter",
    "LinkedInAPIClient",
    "LinkedInAdapter",
    "LinkedInBrowser",
    "LinkedInRenderer",
    "LinkedInSettings",
    "LinkedInUploader",
    "create_linkedin_bundle",
]
