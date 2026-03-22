"""Pain-signal free-text search vector (HIGHEST signal).

Finds people who tweet about the exact problem the product solves.
"""

from __future__ import annotations

import logging
import random
from urllib.parse import quote

from marketmenow.outreach.models import DiscoveredProspectPost

from ...browser import StealthBrowser
from ._parsing import parse_tweet_article

logger = logging.getLogger(__name__)


class PainSignalSearch:
    """Discovers prospects by searching for pain-signal queries on X."""

    def __init__(
        self,
        browser: StealthBrowser,
        queries: list[str],
        max_per_query: int = 5,
    ) -> None:
        self._browser = browser
        self._queries = queries
        self._max_per_query = max_per_query

    @property
    def name(self) -> str:
        return "pain_search"

    async def discover(self) -> list[DiscoveredProspectPost]:
        posts: list[DiscoveredProspectPost] = []
        shuffled = list(self._queries)
        random.shuffle(shuffled)

        for query in shuffled:
            try:
                found = await self._search_query(query)
                posts.extend(found)
                logger.info("Pain search '%s': found %d posts", query[:50], len(found))
            except Exception:
                logger.exception("Failed to search query: %s", query[:50])
            await self._browser._random_delay(3.0, 6.0)

        return posts

    async def _search_query(self, query: str) -> list[DiscoveredProspectPost]:
        encoded = quote(query)
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
        await self._browser.navigate(url)
        await self._browser.scroll_down(times=random.randint(2, 4))

        page = self._browser.page
        articles = page.locator('article[data-testid="tweet"]')
        count = await articles.count()

        results: list[DiscoveredProspectPost] = []
        for i in range(min(count, self._max_per_query + 5)):
            if len(results) >= self._max_per_query:
                break
            try:
                article = articles.nth(i)
                post = await parse_tweet_article(article, self.name)
                if post:
                    results.append(post)
            except Exception:
                continue

        return results
