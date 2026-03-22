from __future__ import annotations

import logging
import os
import random
from collections import defaultdict
from collections.abc import Callable

from marketmenow.outreach.history import OutreachHistory
from marketmenow.outreach.models import (
    CustomerProfile,
    DiscoveredProspectPost,
    DiscoveryVectorConfig,
    OutreachMessage,
    OutreachSendResult,
    UserProfile,
)
from marketmenow.outreach.ports import DiscoveryVector

from ..browser import StealthBrowser
from ..settings import TwitterSettings
from .dm_sender import TwitterDMSender
from .profile_scraper import TwitterProfileScraper
from .vectors.conversation_mining import ConversationMining
from .vectors.hashtag_scan import HashtagScan
from .vectors.pain_search import PainSignalSearch

logger = logging.getLogger(__name__)

VectorFactory = Callable[[StealthBrowser, DiscoveryVectorConfig], DiscoveryVector]

_VECTOR_FACTORIES: dict[str, VectorFactory] = {
    "pain_search": lambda browser, cfg: PainSignalSearch(browser, cfg.entries, cfg.max_per_entry),
    "conversation_mining": lambda browser, cfg: ConversationMining(
        browser, cfg.entries, cfg.max_per_entry
    ),
    "hashtag_scan": lambda browser, cfg: HashtagScan(browser, cfg.entries, cfg.max_per_entry),
}


def _ensure_vertex_credentials(settings: TwitterSettings) -> None:
    creds = settings.google_application_credentials
    if creds and creds.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(creds.resolve()))


class TwitterOutreachOrchestrator:
    """Wires Twitter-specific discovery, enrichment, and sending to the core engine."""

    def __init__(
        self,
        settings: TwitterSettings,
        profile: CustomerProfile,
        history: OutreachHistory,
    ) -> None:
        self._settings = settings
        self._profile = profile
        self._history = history
        self._browser: StealthBrowser | None = None

    def _make_browser(self) -> StealthBrowser:
        return StealthBrowser(
            session_path=self._settings.twitter_session_path,
            user_data_dir=self._settings.twitter_user_data_dir,
            headless=self._settings.headless,
            slow_mo_ms=self._settings.slow_mo_ms,
            proxy_url=self._settings.proxy_url,
            viewport_width=self._settings.viewport_width,
            viewport_height=self._settings.viewport_height,
        )

    @property
    def browser(self) -> StealthBrowser:
        if self._browser is None:
            self._browser = self._make_browser()
        return self._browser

    async def ensure_logged_in(self) -> bool:
        if not await self.browser.is_logged_in():
            logger.error("Not logged in to Twitter. Run `mmn twitter login` first.")
            return False
        return True

    async def launch(self) -> None:
        await self.browser.launch()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None

    def ensure_vertex(self) -> None:
        _ensure_vertex_credentials(self._settings)

    async def discover(self) -> dict[str, list[DiscoveredProspectPost]]:
        """Run all enabled vectors, dedup by handle, return grouped posts."""
        all_posts: list[DiscoveredProspectPost] = []

        for vec_config in self._profile.discovery_vectors:
            factory = _VECTOR_FACTORIES.get(vec_config.vector_type)
            if factory is None:
                logger.warning(
                    "Unknown discovery vector type '%s', skipping",
                    vec_config.vector_type,
                )
                continue

            vector = factory(self.browser, vec_config)
            try:
                posts = await vector.discover()
                all_posts.extend(posts)
                logger.info("Vector '%s' found %d posts", vector.name, len(posts))
            except Exception:
                logger.exception("Vector '%s' failed", vector.name)

        already_contacted = self._history.contacted_handles("twitter")
        own_handle = self._settings.twitter_username.lower().lstrip("@")

        grouped: dict[str, list[DiscoveredProspectPost]] = defaultdict(list)
        for post in all_posts:
            h = post.author_handle.lower()
            if h == own_handle:
                continue
            if h in already_contacted:
                continue
            grouped[h].append(post)

        logger.info(
            "Discovery complete: %d total posts -> %d unique handles",
            len(all_posts),
            len(grouped),
        )
        return dict(grouped)

    async def enrich(
        self,
        prospects: dict[str, list[DiscoveredProspectPost]],
    ) -> list[UserProfile]:
        """Visit each handle's profile and return enriched profiles."""
        scraper = TwitterProfileScraper(self.browser)
        max_enrich = self._profile.ideal_customer.max_prospects_to_enrich

        handles = list(prospects.keys())
        random.shuffle(handles)
        handles = handles[:max_enrich]

        profiles: list[UserProfile] = []
        for handle in handles:
            try:
                profile = await scraper.enrich(handle, prospects[handle])
                if profile is not None:
                    profiles.append(profile)
            except Exception:
                logger.exception("Failed to enrich profile @%s", handle)
            await self.browser._random_delay(2.0, 5.0)

        logger.info(
            "Enrichment complete: %d handles -> %d profiles",
            len(handles),
            len(profiles),
        )
        return profiles

    async def send_batch(
        self,
        messages: list[OutreachMessage],
    ) -> list[OutreachSendResult]:
        """Send messages via DM with rate limiting."""
        sender = TwitterDMSender(self.browser)
        messaging = self._profile.messaging
        results: list[OutreachSendResult] = []

        for i, msg in enumerate(messages):
            result = await sender.send(msg.recipient_handle, msg.message_text)
            results.append(result)

            self._history.record(
                platform="twitter",
                handle=msg.recipient_handle,
                message_preview=msg.message_text,
                score=msg.prospect_score,
                success=result.success,
            )

            if not result.success and self._looks_like_captcha(result.error_message or ""):
                logger.error("CAPTCHA/unusual activity detected, halting sends")
                break

            if i < len(messages) - 1:
                if (i + 1) % messaging.pause_every_n == 0:
                    logger.info("Long pause after %d DMs", i + 1)
                    await self.browser._random_delay(
                        messaging.long_pause_seconds,
                        messaging.long_pause_seconds + 60,
                    )
                else:
                    delay = random.randint(
                        messaging.min_delay_seconds,
                        messaging.max_delay_seconds,
                    )
                    await self.browser._random_delay(delay, delay + 30)

        sent = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        logger.info("Send batch complete: %d sent, %d failed", sent, failed)
        return results

    @staticmethod
    def _looks_like_captcha(error_msg: str) -> bool:
        triggers = ["captcha", "unusual activity", "suspicious", "verify", "challenge"]
        lower = error_msg.lower()
        return any(t in lower for t in triggers)
