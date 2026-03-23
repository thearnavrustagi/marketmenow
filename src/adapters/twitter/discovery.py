from __future__ import annotations

import json
import logging
import random
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .browser import StealthBrowser

logger = logging.getLogger(__name__)


class DiscoveredPost(BaseModel, frozen=True):
    author_handle: str
    post_url: str
    post_text: str
    engagement_score: int = 0
    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    media_alt_texts: tuple[str, ...] = ()
    card_text: str = ""
    media_screenshot: bytes | None = Field(default=None, exclude=True, repr=False)


class PostDiscoverer:
    """Scrapes Twitter/X profiles and hashtag searches for recent posts."""

    def __init__(
        self,
        browser: StealthBrowser,
        reply_history_path: Path,
    ) -> None:
        self._browser = browser
        self._history_path = reply_history_path
        self._replied_urls: set[str] = set()
        self._load_history()

    def _load_history(self) -> None:
        if self._history_path.exists():
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            self._replied_urls = set(data.get("replied_urls", []))
            logger.info(
                "Loaded %d previously replied URLs",
                len(self._replied_urls),
            )

    def save_history(self) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        self._history_path.write_text(
            json.dumps({"replied_urls": sorted(self._replied_urls)}, indent=2),
            encoding="utf-8",
        )

    def mark_replied(self, url: str) -> None:
        self._replied_urls.add(url)
        self.save_history()

    def already_replied(self, url: str) -> bool:
        return url in self._replied_urls

    # ------------------------------------------------------------------
    # Profile scraping
    # ------------------------------------------------------------------

    async def discover_influencer_posts(
        self,
        handles: list[str],
        max_per_handle: int = 3,
    ) -> list[DiscoveredPost]:
        posts: list[DiscoveredPost] = []
        shuffled = list(handles)
        random.shuffle(shuffled)

        for handle in shuffled:
            handle_clean = handle.lstrip("@")
            profile_url = f"https://x.com/{handle_clean}"
            try:
                found = await self._scrape_profile(profile_url, handle_clean, max_per_handle)
                posts.extend(found)
            except Exception:
                logger.exception("Failed to scrape profile %s", handle_clean)
            await self._browser._random_delay(2.0, 5.0)

        return posts

    async def _scrape_profile(
        self,
        profile_url: str,
        handle: str,
        max_posts: int,
    ) -> list[DiscoveredPost]:
        await self._browser.navigate(profile_url)
        await self._browser.scroll_down(times=random.randint(1, 3))

        page = self._browser.page
        articles = page.locator('article[data-testid="tweet"]')
        count = await articles.count()

        results: list[DiscoveredPost] = []
        for i in range(min(count, max_posts + 5)):
            if len(results) >= max_posts:
                break
            try:
                article = articles.nth(i)
                post = await self._parse_tweet_article(article, handle)
                if post and not self.already_replied(post.post_url):
                    results.append(post)
            except Exception:
                continue

        logger.info("Found %d posts from @%s", len(results), handle)
        return results

    # ------------------------------------------------------------------
    # Hashtag search scraping
    # ------------------------------------------------------------------

    async def discover_hashtag_posts(
        self,
        hashtags: list[str],
        max_per_tag: int = 3,
    ) -> list[DiscoveredPost]:
        posts: list[DiscoveredPost] = []
        shuffled = list(hashtags)
        random.shuffle(shuffled)

        for tag in shuffled:
            tag_clean = tag.lstrip("#")
            search_url = f"https://x.com/search?q=%23{tag_clean}&src=typed_query&f=live"
            try:
                found = await self._scrape_search(search_url, tag_clean, max_per_tag)
                posts.extend(found)
            except Exception:
                logger.exception("Failed to scrape hashtag #%s", tag_clean)
            await self._browser._random_delay(2.0, 5.0)

        return posts

    async def _scrape_search(
        self,
        search_url: str,
        tag: str,
        max_posts: int,
    ) -> list[DiscoveredPost]:
        await self._browser.navigate(search_url)
        await self._browser.scroll_down(times=random.randint(1, 3))

        page = self._browser.page
        articles = page.locator('article[data-testid="tweet"]')
        count = await articles.count()

        results: list[DiscoveredPost] = []
        for i in range(min(count, max_posts + 5)):
            if len(results) >= max_posts:
                break
            try:
                article = articles.nth(i)
                post = await self._parse_tweet_article(article, f"#{tag}")
                if post and not self.already_replied(post.post_url):
                    results.append(post)
            except Exception:
                continue

        logger.info("Found %d posts for #%s", len(results), tag)
        return results

    # ------------------------------------------------------------------
    # Tweet article parser
    # ------------------------------------------------------------------

    async def _parse_tweet_article(
        self,
        article: object,
        source_label: str,
    ) -> DiscoveredPost | None:
        try:
            text_el = article.locator('div[data-testid="tweetText"]')  # type: ignore[attr-defined]
            post_text = await text_el.inner_text(timeout=3_000)
        except Exception:
            post_text = ""

        if not post_text.strip():
            return None

        try:
            time_el = article.locator("time").first  # type: ignore[attr-defined]
            link_el = time_el.locator("xpath=ancestor::a")
            href = await link_el.get_attribute("href", timeout=3_000)
            post_url = (
                f"https://x.com{href}" if href and not href.startswith("http") else (href or "")
            )
        except Exception:
            return None

        if not post_url:
            return None

        # Approximate engagement from visible metrics
        engagement = 0
        for testid in ("like", "retweet", "reply"):
            try:
                metric_el = article.locator(f'button[data-testid="{testid}"] span span')  # type: ignore[attr-defined]
                metric_text = await metric_el.inner_text(timeout=1_000)
                engagement += self._parse_metric(metric_text)
            except Exception:
                pass

        try:
            handle_el = article.locator(  # type: ignore[attr-defined]
                'div[data-testid="User-Name"] a[role="link"][tabindex="-1"]'
            )
            handle_href = await handle_el.get_attribute("href", timeout=2_000)
            author = handle_href.strip("/").split("/")[-1] if handle_href else source_label
        except Exception:
            author = source_label

        media_alt_texts = await self._extract_media_alt_texts(article)
        card_text = await self._extract_card_text(article)
        media_screenshot = await self._capture_media_screenshot(article)

        return DiscoveredPost(
            author_handle=author,
            post_url=post_url,
            post_text=post_text[:1000],
            engagement_score=engagement,
            media_alt_texts=media_alt_texts,
            card_text=card_text,
            media_screenshot=media_screenshot,
        )

    @staticmethod
    async def _extract_media_alt_texts(article: object) -> tuple[str, ...]:
        """Pull alt text from tweet images (excludes avatars)."""
        alt_texts: list[str] = []
        try:
            photos = article.locator('[data-testid="tweetPhoto"] img')  # type: ignore[attr-defined]
            count = await photos.count()
            for i in range(count):
                alt = await photos.nth(i).get_attribute("alt", timeout=2_000)
                if alt and alt.strip() and alt.strip().lower() != "image":
                    alt_texts.append(alt.strip())
        except Exception:
            pass
        return tuple(alt_texts)

    @staticmethod
    async def _extract_card_text(article: object) -> str:
        """Pull title + description from link preview cards."""
        parts: list[str] = []
        try:
            card = article.locator('[data-testid="card.wrapper"]')  # type: ignore[attr-defined]
            if await card.count() > 0:
                card_text = await card.first.inner_text(timeout=3_000)
                if card_text and card_text.strip():
                    parts.append(card_text.strip())
        except Exception:
            pass
        if not parts:
            try:
                quote = article.locator('[data-testid="quoteTweet"]')  # type: ignore[attr-defined]
                if await quote.count() > 0:
                    qt = await quote.first.inner_text(timeout=3_000)
                    if qt and qt.strip():
                        parts.append(f"[Quoted tweet] {qt.strip()}")
            except Exception:
                pass
        return "\n".join(parts)[:500]

    @staticmethod
    async def _capture_media_screenshot(article: object) -> bytes | None:
        """Screenshot the tweet article for multimodal LLM context."""
        try:
            screenshot = await article.screenshot(type="jpeg", quality=60, timeout=5_000)  # type: ignore[attr-defined]
            if screenshot and len(screenshot) > 0:
                return bytes(screenshot)
        except Exception:
            logger.debug("Could not screenshot tweet article", exc_info=True)
        return None

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
