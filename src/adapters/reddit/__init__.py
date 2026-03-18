from __future__ import annotations

from marketmenow.registry import PlatformBundle

from .adapter import RedditAdapter
from .client import RedditClient
from .renderer import RedditRenderer
from .settings import RedditSettings
from .uploader import RedditUploader


def create_reddit_bundle(
    settings: RedditSettings | None = None,
) -> PlatformBundle:
    """Construct a fully-wired Reddit ``PlatformBundle``."""
    if settings is None:
        settings = RedditSettings()

    client = RedditClient(
        session_cookie=settings.reddit_session,
        username=settings.reddit_username,
        user_agent=settings.reddit_user_agent,
    )

    return PlatformBundle(
        adapter=RedditAdapter(client),
        renderer=RedditRenderer(),
        uploader=RedditUploader(),
    )


__all__ = [
    "RedditAdapter",
    "RedditClient",
    "RedditRenderer",
    "RedditSettings",
    "RedditUploader",
    "create_reddit_bundle",
]
