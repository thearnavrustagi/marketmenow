from __future__ import annotations

import logging
import random

from marketmenow.outreach.models import DiscoveredProspectPost, UserProfile

from ..browser import StealthBrowser

logger = logging.getLogger(__name__)


class TwitterProfileScraper:
    """Visits a Twitter profile and extracts structured data. Implements ProfileEnricher."""

    def __init__(self, browser: StealthBrowser) -> None:
        self._browser = browser

    async def enrich(
        self,
        handle: str,
        triggering_posts: list[DiscoveredProspectPost],
    ) -> UserProfile | None:
        handle_clean = handle.lstrip("@")
        url = f"https://x.com/{handle_clean}"

        try:
            await self._browser.navigate(url)
            await self._browser._random_delay(1.5, 3.0)
        except Exception:
            logger.warning("Could not navigate to profile @%s", handle_clean)
            return None

        page = self._browser.page

        current_url = page.url
        if "/suspended" in current_url or "account/access" in current_url:
            logger.info("Profile @%s is suspended/restricted, skipping", handle_clean)
            return None

        display_name = await self._safe_text(
            page, 'div[data-testid="UserName"] span', default=handle_clean
        )
        bio = await self._safe_text(page, 'div[data-testid="UserDescription"]')
        location = await self._safe_text(page, 'span[data-testid="UserLocation"]')
        join_date = await self._safe_text(page, 'span[data-testid="UserJoinDate"]')

        follower_count = await self._parse_follow_stat(page, "followers", handle_clean)
        following_count = await self._parse_follow_stat(page, "following", handle_clean)

        dm_possible = await self._check_dm_button(page)

        recent_posts = await self._scrape_recent_posts(page)

        trig_texts = [p.post_text for p in triggering_posts]
        trig_urls = [p.post_url for p in triggering_posts]

        return UserProfile(
            platform="twitter",
            handle=handle_clean,
            display_name=display_name,
            bio=bio,
            location=location,
            follower_count=follower_count,
            following_count=following_count,
            join_date=join_date,
            dm_possible=dm_possible,
            recent_posts=recent_posts,
            triggering_posts=trig_texts,
            triggering_post_urls=trig_urls,
            discovery_count=len({p.source_vector for p in triggering_posts}),
        )

    async def _safe_text(
        self,
        page: object,
        selector: str,
        default: str = "",
        timeout: int = 3_000,
    ) -> str:
        try:
            el = page.locator(selector).first  # type: ignore[attr-defined]
            return (await el.inner_text(timeout=timeout)).strip()
        except Exception:
            return default

    async def _parse_follow_stat(
        self,
        page: object,
        stat: str,
        handle: str,
    ) -> int:
        selectors = [
            f'a[href="/{handle}/{stat}"] span',
            f'a[href="/{handle}/verified_{stat}"] span',
        ]
        for selector in selectors:
            try:
                el = page.locator(selector).first  # type: ignore[attr-defined]
                text = await el.inner_text(timeout=3_000)
                return self._parse_count(text)
            except Exception:
                continue
        return 0

    @staticmethod
    def _parse_count(text: str) -> int:
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

    async def _check_dm_button(self, page: object) -> bool:
        try:
            btn = page.locator('button[data-testid="sendDMFromProfile"]')  # type: ignore[attr-defined]
            return await btn.is_visible(timeout=3_000)
        except Exception:
            return False

    async def _scrape_recent_posts(self, page: object, max_posts: int = 8) -> list[str]:
        import contextlib

        with contextlib.suppress(Exception):
            await self._browser.scroll_down(times=random.randint(1, 2))

        posts: list[str] = []
        try:
            articles = page.locator('article[data-testid="tweet"]')  # type: ignore[attr-defined]
            count = await articles.count()
            for i in range(min(count, max_posts + 3)):
                if len(posts) >= max_posts:
                    break
                try:
                    text_el = articles.nth(i).locator('div[data-testid="tweetText"]')
                    text = await text_el.inner_text(timeout=2_000)
                    if text.strip():
                        posts.append(text.strip()[:500])
                except Exception:
                    continue
        except Exception:
            pass

        return posts
