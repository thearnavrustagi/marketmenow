"""Conversation mining vector (HIGH signal).

Finds people who reply to influencer/competitor posts -- the repliers
are prospects, not the original poster.
"""

from __future__ import annotations

import logging
import random

from marketmenow.outreach.models import DiscoveredProspectPost

from ...browser import StealthBrowser
from ._parsing import parse_tweet_article

logger = logging.getLogger(__name__)


class ConversationMining:
    """Discovers prospects by mining reply threads of target handles."""

    def __init__(
        self,
        browser: StealthBrowser,
        handles: list[str],
        max_per_handle: int = 5,
    ) -> None:
        self._browser = browser
        self._handles = handles
        self._max_per_handle = max_per_handle

    @property
    def name(self) -> str:
        return "conversation_mining"

    async def discover(self) -> list[DiscoveredProspectPost]:
        posts: list[DiscoveredProspectPost] = []
        shuffled = list(self._handles)
        random.shuffle(shuffled)

        for handle in shuffled:
            handle_clean = handle.lstrip("@")
            try:
                found = await self._mine_handle(handle_clean)
                posts.extend(found)
                logger.info(
                    "Conversation mining @%s: found %d repliers",
                    handle_clean,
                    len(found),
                )
            except Exception:
                logger.exception("Failed to mine conversations for @%s", handle_clean)
            await self._browser._random_delay(2.0, 5.0)

        return posts

    async def _mine_handle(self, handle: str) -> list[DiscoveredProspectPost]:
        profile_url = f"https://x.com/{handle}"
        await self._browser.navigate(profile_url)
        await self._browser.scroll_down(times=random.randint(1, 2))

        page = self._browser.page
        articles = page.locator('article[data-testid="tweet"]')
        count = await articles.count()

        post_urls: list[str] = []
        for i in range(min(count, 5)):
            try:
                article = articles.nth(i)
                time_el = article.locator("time").first
                link_el = time_el.locator("xpath=ancestor::a")
                href = await link_el.get_attribute("href", timeout=3_000)
                if href:
                    url = f"https://x.com{href}" if not href.startswith("http") else href
                    if f"/{handle}/" in url.lower() or f"/{handle.lower()}/" in url.lower():
                        post_urls.append(url)
            except Exception:
                continue

        post_urls = post_urls[:3]

        repliers: list[DiscoveredProspectPost] = []
        for post_url in post_urls:
            if len(repliers) >= self._max_per_handle:
                break
            try:
                found = await self._scrape_replies(post_url, handle)
                repliers.extend(found)
            except Exception:
                logger.exception("Failed to scrape replies for %s", post_url)
            await self._browser._random_delay(2.0, 4.0)

        return repliers[: self._max_per_handle]

    async def _scrape_replies(
        self, post_url: str, original_author: str
    ) -> list[DiscoveredProspectPost]:
        await self._browser.navigate(post_url)
        await self._browser._random_delay(1.5, 3.0)
        await self._browser.scroll_down(times=random.randint(1, 3))

        page = self._browser.page
        articles = page.locator('article[data-testid="tweet"]')
        count = await articles.count()

        results: list[DiscoveredProspectPost] = []
        for i in range(1, min(count, 15)):
            try:
                article = articles.nth(i)
                post = await parse_tweet_article(article, self.name)
                if post and post.author_handle.lower() != original_author.lower():
                    results.append(post)
            except Exception:
                continue

        return results
