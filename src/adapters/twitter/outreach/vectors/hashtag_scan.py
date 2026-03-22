"""Hashtag community scan vector (MEDIUM signal).

Finds people posting in relevant hashtags who self-identify with the community.
"""

from __future__ import annotations

import logging
import random

from marketmenow.outreach.models import DiscoveredProspectPost

from ...browser import StealthBrowser
from ._parsing import parse_tweet_article

logger = logging.getLogger(__name__)


class HashtagScan:
    """Discovers prospects by scanning hashtag search results on X."""

    def __init__(
        self,
        browser: StealthBrowser,
        hashtags: list[str],
        max_per_tag: int = 5,
    ) -> None:
        self._browser = browser
        self._hashtags = hashtags
        self._max_per_tag = max_per_tag

    @property
    def name(self) -> str:
        return "hashtag_scan"

    async def discover(self) -> list[DiscoveredProspectPost]:
        posts: list[DiscoveredProspectPost] = []
        shuffled = list(self._hashtags)
        random.shuffle(shuffled)

        for tag in shuffled:
            tag_clean = tag.lstrip("#")
            try:
                found = await self._scan_hashtag(tag_clean)
                posts.extend(found)
                logger.info("Hashtag #%s: found %d posts", tag_clean, len(found))
            except Exception:
                logger.exception("Failed to scan hashtag #%s", tag_clean)
            await self._browser._random_delay(3.0, 6.0)

        return posts

    async def _scan_hashtag(self, tag: str) -> list[DiscoveredProspectPost]:
        url = f"https://x.com/search?q=%23{tag}&src=typed_query&f=live"
        await self._browser.navigate(url)
        await self._browser.scroll_down(times=random.randint(2, 4))

        page = self._browser.page
        articles = page.locator('article[data-testid="tweet"]')
        count = await articles.count()

        results: list[DiscoveredProspectPost] = []
        for i in range(min(count, self._max_per_tag + 5)):
            if len(results) >= self._max_per_tag:
                break
            try:
                article = articles.nth(i)
                post = await parse_tweet_article(article, self.name)
                if post:
                    results.append(post)
            except Exception:
                continue

        return results
