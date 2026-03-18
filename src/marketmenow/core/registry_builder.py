from __future__ import annotations

import logging

from marketmenow.registry import AdapterRegistry

logger = logging.getLogger(__name__)


def build_registry() -> AdapterRegistry:
    """Auto-register all available platform bundles.

    Each adapter is attempted independently; if credentials are missing or the
    adapter's settings fail validation the platform is silently skipped so that
    the remaining platforms still work.
    """
    registry = AdapterRegistry()

    _try_instagram(registry)
    _try_twitter(registry)
    _try_linkedin(registry)
    _try_reddit(registry)
    _try_facebook(registry)
    _try_youtube(registry)

    return registry


def _try_instagram(registry: AdapterRegistry) -> None:
    try:
        from adapters.instagram import create_instagram_bundle
        from adapters.instagram.settings import InstagramSettings

        settings = InstagramSettings()
        bundle = create_instagram_bundle(settings)
        registry.register(bundle)
        logger.debug("Registered instagram adapter")
    except Exception as exc:
        logger.debug("Skipping instagram adapter: %s", exc)


def _try_twitter(registry: AdapterRegistry) -> None:
    try:
        from adapters.twitter import create_twitter_bundle
        from adapters.twitter.settings import TwitterSettings

        settings = TwitterSettings()
        bundle = create_twitter_bundle(settings)
        registry.register(bundle)
        logger.debug("Registered twitter adapter")
    except Exception as exc:
        logger.debug("Skipping twitter adapter: %s", exc)


def _try_linkedin(registry: AdapterRegistry) -> None:
    try:
        from adapters.linkedin import create_linkedin_bundle
        from adapters.linkedin.settings import LinkedInSettings

        settings = LinkedInSettings()
        bundle = create_linkedin_bundle(settings)
        registry.register(bundle)
        logger.debug("Registered linkedin adapter")
    except Exception as exc:
        logger.debug("Skipping linkedin adapter: %s", exc)


def _try_reddit(registry: AdapterRegistry) -> None:
    try:
        from adapters.reddit import create_reddit_bundle
        from adapters.reddit.settings import RedditSettings

        settings = RedditSettings()
        bundle = create_reddit_bundle(settings)
        registry.register(bundle)
        logger.debug("Registered reddit adapter")
    except Exception as exc:
        logger.debug("Skipping reddit adapter: %s", exc)


def _try_facebook(registry: AdapterRegistry) -> None:
    try:
        from adapters.facebook import create_facebook_bundle
        from adapters.facebook.settings import FacebookSettings

        settings = FacebookSettings()
        bundle = create_facebook_bundle(settings)
        registry.register(bundle)
        logger.debug("Registered facebook adapter")
    except Exception as exc:
        logger.debug("Skipping facebook adapter: %s", exc)


def _try_youtube(registry: AdapterRegistry) -> None:
    try:
        from adapters.youtube import create_youtube_bundle
        from adapters.youtube.settings import YouTubeSettings

        settings = YouTubeSettings()
        bundle = create_youtube_bundle(settings)
        registry.register(bundle)
        logger.debug("Registered youtube adapter")
    except Exception as exc:
        logger.debug("Skipping youtube adapter: %s", exc)
