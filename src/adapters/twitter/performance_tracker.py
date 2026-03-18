from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .browser import StealthBrowser

logger = logging.getLogger(__name__)

_MAX_ARTICLES_PER_TAB = 30


class WinningReply(BaseModel, frozen=True):
    parent_author: str
    parent_text: str
    our_reply: str
    likes: int = 0
    retweets: int = 0
    url: str = ""


class WinningPost(BaseModel, frozen=True):
    text: str
    likes: int = 0
    retweets: int = 0
    url: str = ""


class TopExamplesCache(BaseModel):
    last_collected: str = ""
    replies: list[WinningReply] = Field(default_factory=list)
    posts: list[WinningPost] = Field(default_factory=list)


def load_examples_cache(path: Path) -> TopExamplesCache:
    if not path.exists():
        return TopExamplesCache()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return TopExamplesCache(**data)
    except Exception:
        logger.warning("Failed to load examples cache from %s, starting fresh", path)
        return TopExamplesCache()


def cache_is_fresh(cache: TopExamplesCache, max_age_hours: int) -> bool:
    if not cache.last_collected:
        return False
    try:
        collected_at = datetime.fromisoformat(cache.last_collected)
        age_hours = (datetime.now(UTC) - collected_at).total_seconds() / 3600
        return age_hours < max_age_hours
    except Exception:
        return False


class PerformanceTracker:
    """Scrapes our own Twitter profile to find posts/replies with positive engagement."""

    def __init__(
        self,
        browser: StealthBrowser,
        username: str,
        output_path: Path,
    ) -> None:
        self._browser = browser
        self._username = username.lstrip("@")
        self._output_path = output_path

    async def collect(self) -> TopExamplesCache:
        """Scrape own profile for top-performing posts and replies, save to JSON."""
        logger.info("Collecting top-performing examples for @%s", self._username)

        posts = await self._collect_posts()
        replies = await self._collect_replies()

        cache = TopExamplesCache(
            last_collected=datetime.now(UTC).isoformat(),
            replies=replies,
            posts=posts,
        )
        self._save(cache)

        logger.info(
            "Collected %d winning posts + %d winning replies",
            len(posts),
            len(replies),
        )
        return cache

    # ------------------------------------------------------------------
    # Posts tab
    # ------------------------------------------------------------------

    async def _collect_posts(self) -> list[WinningPost]:
        profile_url = f"https://x.com/{self._username}"
        await self._browser.navigate(profile_url)
        await self._browser.scroll_down(times=3)

        page = self._browser.page
        articles = page.locator('article[data-testid="tweet"]')
        count = await articles.count()

        winners: list[WinningPost] = []
        for i in range(min(count, _MAX_ARTICLES_PER_TAB)):
            try:
                article = articles.nth(i)
                author = await self._get_author(article)

                if author.lower() != self._username.lower():
                    continue

                text = await self._get_text(article)
                if not text:
                    continue

                likes, retweets = await self._get_metrics(article)
                if likes <= 0 and retweets <= 0:
                    continue

                url = await self._get_url(article)
                winners.append(
                    WinningPost(
                        text=text[:1000],
                        likes=likes,
                        retweets=retweets,
                        url=url,
                    )
                )
            except Exception:
                continue

        logger.info("Found %d winning posts on main tab", len(winners))
        return winners

    # ------------------------------------------------------------------
    # Replies tab — pairs parent tweet with our reply
    # ------------------------------------------------------------------

    async def _collect_replies(self) -> list[WinningReply]:
        replies_url = f"https://x.com/{self._username}/with_replies"
        await self._browser.navigate(replies_url)
        await self._browser.scroll_down(times=3)

        page = self._browser.page
        articles = page.locator('article[data-testid="tweet"]')
        count = await articles.count()

        winners: list[WinningReply] = []
        pending_parent: tuple[str, str] | None = None  # (author, text)

        for i in range(min(count, _MAX_ARTICLES_PER_TAB)):
            try:
                article = articles.nth(i)
                author = await self._get_author(article)
                text = await self._get_text(article)

                if not text:
                    pending_parent = None
                    continue

                is_ours = author.lower() == self._username.lower()

                if not is_ours:
                    pending_parent = (author, text)
                    continue

                likes, retweets = await self._get_metrics(article)

                if likes <= 0 and retweets <= 0:
                    pending_parent = None
                    continue

                url = await self._get_url(article)

                if pending_parent is not None:
                    winners.append(
                        WinningReply(
                            parent_author=pending_parent[0],
                            parent_text=pending_parent[1][:500],
                            our_reply=text[:500],
                            likes=likes,
                            retweets=retweets,
                            url=url,
                        )
                    )
                else:
                    winners.append(
                        WinningReply(
                            parent_author="",
                            parent_text="",
                            our_reply=text[:500],
                            likes=likes,
                            retweets=retweets,
                            url=url,
                        )
                    )

                pending_parent = None
            except Exception:
                pending_parent = None
                continue

        logger.info("Found %d winning replies on replies tab", len(winners))
        return winners

    # ------------------------------------------------------------------
    # DOM helpers (reuse patterns from PostDiscoverer)
    # ------------------------------------------------------------------

    async def _get_text(self, article: object) -> str:
        try:
            text_el = article.locator('div[data-testid="tweetText"]')  # type: ignore[attr-defined]
            return (await text_el.inner_text(timeout=3_000)).strip()
        except Exception:
            return ""

    async def _get_author(self, article: object) -> str:
        try:
            handle_el = article.locator(  # type: ignore[attr-defined]
                'div[data-testid="User-Name"] a[role="link"][tabindex="-1"]'
            )
            href = await handle_el.get_attribute("href", timeout=2_000)
            return href.strip("/").split("/")[-1] if href else ""
        except Exception:
            return ""

    async def _get_url(self, article: object) -> str:
        try:
            time_el = article.locator("time").first  # type: ignore[attr-defined]
            link_el = time_el.locator("xpath=ancestor::a")
            href = await link_el.get_attribute("href", timeout=3_000)
            if href and not href.startswith("http"):
                return f"https://x.com{href}"
            return href or ""
        except Exception:
            return ""

    async def _get_metrics(self, article: object) -> tuple[int, int]:
        """Return (likes, retweets) for a tweet article."""
        likes = 0
        retweets = 0
        for testid, label in (("like", "likes"), ("retweet", "retweets")):
            try:
                el = article.locator(f'button[data-testid="{testid}"] span span')  # type: ignore[attr-defined]
                text = await el.inner_text(timeout=1_000)
                val = self._parse_metric(text)
                if label == "likes":
                    likes = val
                else:
                    retweets = val
            except Exception:
                pass
        return likes, retweets

    @staticmethod
    def _parse_metric(text: str) -> int:
        text = text.strip().replace(",", "")
        if not text:
            return 0
        multiplier = 1
        if text.endswith("K"):
            multiplier = 1_000
            text = text[:-1]
        elif text.endswith("M"):
            multiplier = 1_000_000
            text = text[:-1]
        try:
            return int(float(text) * multiplier)
        except ValueError:
            return 0

    def _save(self, cache: TopExamplesCache) -> None:
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._output_path.write_text(
            cache.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info("Saved examples cache to %s", self._output_path)
