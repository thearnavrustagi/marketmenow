from __future__ import annotations

import logging

from marketmenow.registry import PlatformBundle

from .adapter import InstagramAdapter
from .renderer import InstagramRenderer
from .settings import InstagramSettings
from .token_manager import TokenManager
from .uploader import InstagramUploader

logger = logging.getLogger(__name__)


async def ensure_token(settings: InstagramSettings) -> str:
    """Return a long-lived access token, exchanging/refreshing if needed."""
    token = settings.instagram_access_token
    if not (settings.instagram_app_id and settings.instagram_app_secret):
        logger.debug("No app_id/app_secret -- skipping token lifecycle management")
        return token

    mgr = TokenManager(settings.instagram_app_id, settings.instagram_app_secret)
    return await mgr.ensure_long_lived(token)


def create_instagram_bundle(settings: InstagramSettings | None = None) -> PlatformBundle:
    """Construct a fully-wired Instagram ``PlatformBundle``."""
    if settings is None:
        settings = InstagramSettings()

    return PlatformBundle(
        adapter=InstagramAdapter(
            access_token=settings.instagram_access_token,
            business_account_id=settings.instagram_business_account_id,
        ),
        renderer=InstagramRenderer(),
        uploader=InstagramUploader(
            bucket=settings.aws_s3_bucket,
            region=settings.aws_s3_region,
            prefix=settings.aws_s3_prefix,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        ),
    )


__all__ = [
    "InstagramAdapter",
    "InstagramRenderer",
    "InstagramSettings",
    "InstagramUploader",
    "TokenManager",
    "create_instagram_bundle",
    "ensure_token",
]
