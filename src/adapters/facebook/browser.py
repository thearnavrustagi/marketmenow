from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from pathlib import Path

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright_stealth import Stealth

logger = logging.getLogger(__name__)

_FACEBOOK_HOME = "https://www.facebook.com/"
_FACEBOOK_BASE = "https://www.facebook.com"


class FacebookBrowser:
    """Playwright wrapper with anti-detection for Facebook."""

    def __init__(
        self,
        session_path: Path,
        user_data_dir: Path,
        headless: bool = False,
        slow_mo_ms: int = 50,
        proxy_url: str = "",
        viewport_width: int = 1280,
        viewport_height: int = 900,
    ) -> None:
        self._session_path = session_path
        self._user_data_dir = user_data_dir
        self._headless = headless
        self._slow_mo_ms = slow_mo_ms
        self._proxy_url = proxy_url
        self._viewport_width = viewport_width
        self._viewport_height = viewport_height

        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not launched -- call launch() first")
        return self._page

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def launch(self) -> Page:
        self._stealth = Stealth(navigator_platform_override="MacIntel")
        self._stealth_cm = self._stealth.use_async(async_playwright())
        self._pw = await self._stealth_cm.__aenter__()

        launch_kwargs: dict[str, object] = {
            "headless": self._headless,
            "slow_mo": self._slow_mo_ms,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        }
        if self._proxy_url:
            launch_kwargs["proxy"] = {"server": self._proxy_url}

        self._browser = await self._pw.chromium.launch(**launch_kwargs)  # type: ignore[arg-type]

        context_kwargs: dict[str, object] = {
            "viewport": {
                "width": self._viewport_width,
                "height": self._viewport_height,
            },
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }

        if self._session_path.exists():
            context_kwargs["storage_state"] = str(self._session_path)
            logger.info("Restoring session from %s", self._session_path)

        self._context = await self._browser.new_context(**context_kwargs)  # type: ignore[arg-type]
        self._page = await self._context.new_page()
        return self._page

    async def close(self) -> None:
        if self._context is not None:
            await self.save_session()
            try:
                await self._context.close()
            except Exception:
                logger.debug("Context already closed", exc_info=True)
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                logger.debug("Browser already closed", exc_info=True)
        if hasattr(self, "_stealth_cm") and self._stealth_cm is not None:
            try:
                await self._stealth_cm.__aexit__(None, None, None)
            except Exception:
                logger.debug("Stealth cleanup failed", exc_info=True)
            self._stealth_cm = None
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None

    async def save_session(self) -> None:
        if self._context is None:
            return
        try:
            state = await self._context.storage_state()
        except Exception:
            logger.warning("Could not save session (browser context already closed)")
            return
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        logger.info("Session saved to %s", self._session_path)

    # ------------------------------------------------------------------
    # Login flows
    # ------------------------------------------------------------------

    async def login_manual(self) -> None:
        """Open facebook.com and let the user log in manually."""
        page = self.page
        logger.info("Opening facebook.com -- please log in manually.")
        await page.goto(_FACEBOOK_BASE, wait_until="load", timeout=60_000)
        await self._random_delay(2.0, 3.0)

        logger.info("Waiting for login (up to 5 minutes)...")
        with contextlib.suppress(Exception):
            await page.wait_for_url(
                lambda url: "/login" not in url and "facebook.com" in url,
                timeout=300_000,
            )

        # Wait for the feed or a logged-in indicator
        try:
            await page.wait_for_selector(
                'div[role="feed"], div[role="main"], a[aria-label="Home"]',
                timeout=300_000,
            )
        except Exception:
            logger.warning("Could not detect feed element; checking URL.")

        url = page.url
        if "/login" in url or "/checkpoint" in url:
            raise RuntimeError("Login was not completed within the timeout.")

        await self.save_session()
        logger.info("Login successful, session saved.")

    async def login_with_cookies(self, c_user: str, xs: str) -> None:
        """Inject the c_user and xs session cookies and verify login."""
        if self._context is None:
            raise RuntimeError("Browser not launched")

        cookies = [
            {
                "name": "c_user",
                "value": c_user,
                "domain": ".facebook.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "None",
            },
            {
                "name": "xs",
                "value": xs,
                "domain": ".facebook.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            },
        ]
        await self._context.add_cookies(cookies)  # type: ignore[arg-type]
        logger.info("Facebook cookies injected, verifying login...")

        page = self.page
        await page.goto(_FACEBOOK_HOME, wait_until="load", timeout=60_000)
        await self._random_delay(3.0, 5.0)

        url = page.url
        if "/login" in url or "/checkpoint" in url:
            raise RuntimeError(
                "Cookie login failed -- Facebook redirected to login. "
                "The cookies may be expired. Grab fresh c_user and xs from your browser."
            )

        await self.save_session()
        logger.info("Cookie login successful, session saved.")

    async def is_logged_in(self) -> bool:
        page = self.page
        try:
            await page.goto(_FACEBOOK_HOME, wait_until="domcontentloaded", timeout=30_000)
            await self._random_delay(3.0, 5.0)
            url = page.url
            if "/login" in url or "/checkpoint" in url:
                return False
            # Look for logged-in indicators
            home_link = page.locator('a[aria-label="Home"], a[aria-label="Facebook"]').first
            try:
                await home_link.wait_for(state="visible", timeout=10_000)
                return True
            except Exception:
                return "facebook.com" in url and "/login" not in url
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> None:
        await self._random_delay(0.5, 2.0)
        await self.page.goto(url, wait_until=wait_until)  # type: ignore[arg-type]
        await self._random_delay(1.5, 3.5)
        await self._mouse_jitter()

    async def scroll_down(self, times: int = 1) -> None:
        for _ in range(times):
            delta = random.randint(300, 700)
            await self.page.mouse.wheel(0, delta)
            await self._random_delay(0.8, 2.5)
            await self._mouse_jitter()

    # ------------------------------------------------------------------
    # Feed post creation
    # ------------------------------------------------------------------

    async def _open_feed_composer(self) -> None:
        """Click the 'What's on your mind?' box to open the post composer."""
        page = self.page
        await self.navigate(_FACEBOOK_HOME)
        await self._random_delay(1.0, 2.0)

        composer_trigger = page.locator(
            'div[role="button"]:has-text("What\'s on your mind"),'
            'span:has-text("What\'s on your mind")'
        ).first
        await composer_trigger.wait_for(state="visible", timeout=15_000)
        await composer_trigger.click()
        await self._random_delay(1.5, 2.5)

    async def _type_in_composer(self, text: str) -> None:
        """Type text into the active composer dialog."""
        page = self.page
        editor = page.locator(
            'div[contenteditable="true"][role="textbox"],'
            'div[contenteditable="true"][aria-label*="on your mind"],'
            'div[contenteditable="true"][data-lexical-editor="true"]'
        ).first
        await editor.wait_for(state="visible", timeout=10_000)
        await editor.click()
        await self._random_delay(0.3, 0.8)
        await self._human_type(text)
        await self._random_delay(0.8, 1.5)

    async def _click_post_button(self) -> None:
        """Click the Post button in the composer dialog."""
        page = self.page
        post_btn = page.locator(
            'div[aria-label="Post"][role="button"],span:has-text("Post"):not(:has-text("Posting"))'
        ).first
        await post_btn.wait_for(state="visible", timeout=10_000)
        await post_btn.click()
        await self._random_delay(3.0, 5.0)

    async def create_text_post(self, text: str) -> bool:
        """Create a text-only post on the personal feed."""
        await self._open_feed_composer()
        await self._type_in_composer(text)
        await self._click_post_button()
        logger.info("Text post created on Facebook")
        return True

    async def create_image_post(self, text: str, image_paths: list[Path]) -> bool:
        """Create a post with images on the personal feed."""
        page = self.page
        await self._open_feed_composer()
        await self._random_delay(0.5, 1.0)

        # Click the Photo/Video button in the composer
        photo_btn = page.locator(
            'div[aria-label="Photo/video"][role="button"],'
            'div[role="button"]:has-text("Photo/video"),'
            'i[data-visualcompletion="css-img"][style*="photo"]'
        ).first
        try:
            await photo_btn.wait_for(state="visible", timeout=8_000)
            await photo_btn.click()
            await self._random_delay(1.0, 2.0)
        except Exception:
            logger.debug("Photo button not found in composer, trying toolbar")
            toolbar_photo = page.locator(
                'div[aria-label="Photo/Video"],span:has-text("Photo/Video")'
            ).first
            await toolbar_photo.click()
            await self._random_delay(1.0, 2.0)

        # Upload images via file input
        file_input = page.locator('input[type="file"][accept*="image"]').first
        await file_input.set_input_files([str(p.resolve()) for p in image_paths])
        await self._random_delay(2.0, 4.0)

        if text:
            await self._type_in_composer(text)

        await self._click_post_button()
        logger.info("Image post created on Facebook (%d images)", len(image_paths))
        return True

    async def create_video_post(self, text: str, video_path: Path) -> bool:
        """Create a post with a video on the personal feed."""
        page = self.page
        await self._open_feed_composer()
        await self._random_delay(0.5, 1.0)

        photo_btn = page.locator(
            'div[aria-label="Photo/video"][role="button"],'
            'div[role="button"]:has-text("Photo/video")'
        ).first
        try:
            await photo_btn.wait_for(state="visible", timeout=8_000)
            await photo_btn.click()
            await self._random_delay(1.0, 2.0)
        except Exception:
            toolbar_photo = page.locator(
                'div[aria-label="Photo/Video"],span:has-text("Photo/Video")'
            ).first
            await toolbar_photo.click()
            await self._random_delay(1.0, 2.0)

        file_input = page.locator('input[type="file"][accept*="video"]').first
        try:
            await file_input.set_input_files(str(video_path.resolve()))
        except Exception:
            # Fallback: some FB UIs use a single file input for both images/videos
            file_input = page.locator('input[type="file"]').first
            await file_input.set_input_files(str(video_path.resolve()))
        await self._random_delay(3.0, 6.0)

        if text:
            await self._type_in_composer(text)

        await self._click_post_button()
        logger.info("Video post created on Facebook")
        return True

    # ------------------------------------------------------------------
    # Page posting
    # ------------------------------------------------------------------

    async def _open_page_composer(self, page_url: str) -> None:
        """Navigate to a page and open its post composer."""
        page = self.page
        await self.navigate(page_url)
        await self._random_delay(1.5, 2.5)

        composer_trigger = page.locator(
            'div[role="button"]:has-text("Write something"),'
            'div[role="button"]:has-text("Create post"),'
            'div[role="button"]:has-text("What\'s on your mind"),'
            'span:has-text("Write something")'
        ).first
        await composer_trigger.wait_for(state="visible", timeout=15_000)
        await composer_trigger.click()
        await self._random_delay(1.5, 2.5)

    async def create_page_post(
        self, page_url: str, text: str, image_paths: list[Path] | None = None
    ) -> bool:
        """Create a post on a Facebook Page, optionally with images."""
        page = self.page
        await self._open_page_composer(page_url)

        if image_paths:
            photo_btn = page.locator(
                'div[aria-label="Photo/video"][role="button"],'
                'div[role="button"]:has-text("Photo/video"),'
                'div[aria-label="Photo/Video"]'
            ).first
            try:
                await photo_btn.wait_for(state="visible", timeout=8_000)
                await photo_btn.click()
                await self._random_delay(1.0, 2.0)
            except Exception:
                logger.debug("Photo button not found in page composer")

            file_input = page.locator('input[type="file"]').first
            await file_input.set_input_files([str(p.resolve()) for p in image_paths])
            await self._random_delay(2.0, 4.0)

        await self._type_in_composer(text)
        await self._click_post_button()

        logger.info("Page post created in %s", page_url)
        return True

    # ------------------------------------------------------------------
    # Group posting
    # ------------------------------------------------------------------

    async def _open_group_composer(self, group_url: str) -> None:
        """Navigate to a group and open its post composer."""
        page = self.page
        await self.navigate(group_url)
        await self._random_delay(1.5, 2.5)

        composer_trigger = page.locator(
            'div[role="button"]:has-text("Write something"),'
            'div[role="button"]:has-text("What\'s on your mind"),'
            'span:has-text("Write something")'
        ).first
        await composer_trigger.wait_for(state="visible", timeout=15_000)
        await composer_trigger.click()
        await self._random_delay(1.5, 2.5)

    async def create_group_post(
        self, group_url: str, text: str, image_paths: list[Path] | None = None
    ) -> bool:
        """Create a post inside a Facebook Group, optionally with images."""
        page = self.page
        await self._open_group_composer(group_url)

        if image_paths:
            photo_btn = page.locator(
                'div[aria-label="Photo/video"][role="button"],'
                'div[role="button"]:has-text("Photo/video"),'
                'div[aria-label="Photo/Video"]'
            ).first
            try:
                await photo_btn.wait_for(state="visible", timeout=8_000)
                await photo_btn.click()
                await self._random_delay(1.0, 2.0)
            except Exception:
                logger.debug("Photo button not found in group composer")

            file_input = page.locator('input[type="file"]').first
            await file_input.set_input_files([str(p.resolve()) for p in image_paths])
            await self._random_delay(2.0, 4.0)

        await self._type_in_composer(text)
        await self._click_post_button()

        logger.info("Group post created in %s", group_url)
        return True

    async def comment_on_group_post(self, post_url: str, comment_text: str) -> bool:
        """Navigate to a group post and leave a comment."""
        page = self.page
        await self.navigate(post_url)
        await self._random_delay(1.5, 3.0)
        await self.scroll_down(times=random.randint(0, 1))

        # Look for the comment input box
        comment_box = page.locator(
            'div[aria-label="Write a comment"][contenteditable="true"],'
            'div[aria-label="Write a comment..."][contenteditable="true"],'
            'div[contenteditable="true"][role="textbox"][aria-label*="comment"]'
        ).first

        try:
            await comment_box.wait_for(state="visible", timeout=10_000)
        except Exception:
            # Try clicking "Write a comment" placeholder to activate the input
            placeholder = page.locator(
                'div[aria-label="Write a comment"],span:has-text("Write a comment")'
            ).first
            await placeholder.click()
            await self._random_delay(0.5, 1.0)
            comment_box = page.locator('div[contenteditable="true"][role="textbox"]').first
            await comment_box.wait_for(state="visible", timeout=10_000)

        await comment_box.click()
        await self._random_delay(0.5, 1.2)

        await self._human_type(comment_text)
        await self._random_delay(0.8, 1.5)

        # Press Enter to submit the comment
        await page.keyboard.press("Enter")
        await self._random_delay(2.0, 4.0)

        logger.info("Comment posted on %s", post_url)
        return True

    # ------------------------------------------------------------------
    # Group feed scraping
    # ------------------------------------------------------------------

    async def scrape_group_feed(
        self,
        group_url: str,
        max_posts: int = 5,
    ) -> list[dict[str, str]]:
        """Scrape recent posts from a Facebook group feed.

        Returns a list of dicts with keys: ``post_url``, ``post_text``,
        ``post_author``, ``reactions``, ``comments``.
        """
        page = self.page
        await self.navigate(group_url)
        await self._random_delay(2.0, 4.0)

        scroll_rounds = max(2, max_posts // 2)
        await self.scroll_down(times=scroll_rounds)
        await self._random_delay(1.0, 2.0)

        post_elements = page.locator(
            'div[role="feed"] div[role="article"],div[role="main"] div[role="article"]'
        )
        count = await post_elements.count()
        logger.info("Found %d article elements in group %s", count, group_url)

        results: list[dict[str, str]] = []
        for i in range(min(count, max_posts * 2)):
            if len(results) >= max_posts:
                break
            try:
                el = post_elements.nth(i)
                parsed = await self._parse_group_article(el, group_url)
                if parsed:
                    results.append(parsed)
            except Exception:
                logger.debug("Failed to parse article %d in %s", i, group_url, exc_info=True)
                continue

        logger.info("Scraped %d posts from %s", len(results), group_url)
        return results

    async def _parse_group_article(
        self,
        el: object,
        group_url: str,
    ) -> dict[str, str] | None:
        """Extract structured data from a single group feed article element."""
        from playwright.async_api import Locator

        article: Locator = el  # type: ignore[assignment]

        text_parts: list[str] = []
        text_container = article.locator(
            'div[data-ad-preview="message"],div[data-ad-comet-preview="message"],div[dir="auto"]'
        )
        text_count = await text_container.count()
        for j in range(min(text_count, 5)):
            part = (await text_container.nth(j).inner_text()).strip()
            if part and len(part) > 10:
                text_parts.append(part)
        post_text = "\n".join(dict.fromkeys(text_parts))

        if not post_text or len(post_text) < 20:
            return None

        post_url = ""
        time_links = article.locator(
            'a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid"]'
        )
        link_count = await time_links.count()
        for j in range(link_count):
            href = await time_links.nth(j).get_attribute("href")
            if href:
                if href.startswith("/"):
                    href = f"https://www.facebook.com{href}"
                post_url = href.split("?")[0] if "?" in href else href
                break

        if not post_url:
            return None

        author = ""
        heading = article.locator("h2, h3, h4").first
        try:
            author_el = heading.locator("a, span strong a, span a").first
            author = (await author_el.inner_text()).strip()
        except Exception:
            pass

        reactions = "0"
        reactions_el = article.locator(
            'span[aria-label*="reaction"], span[aria-label*="like"]'
        ).first
        try:
            label = await reactions_el.get_attribute("aria-label")
            if label:
                nums = "".join(c for c in label if c.isdigit())
                if nums:
                    reactions = nums
        except Exception:
            pass

        comments_count = "0"
        comment_link = article.locator('span:has-text("comment"), span:has-text("Comment")').first
        try:
            c_text = (await comment_link.inner_text()).strip()
            nums = "".join(c for c in c_text if c.isdigit())
            if nums:
                comments_count = nums
        except Exception:
            pass

        return {
            "post_url": post_url,
            "post_text": post_text[:3000],
            "post_author": author,
            "reactions": reactions,
            "comments": comments_count,
        }

    # ------------------------------------------------------------------
    # Screenshot for debugging
    # ------------------------------------------------------------------

    async def screenshot(self, path: str | Path) -> None:
        await self.page.screenshot(path=str(path), full_page=False)

    # ------------------------------------------------------------------
    # Human-like behaviour
    # ------------------------------------------------------------------

    async def _human_type(self, text: str) -> None:
        for char in text:
            delay_ms = random.randint(40, 180)
            await self.page.keyboard.type(char, delay=delay_ms)
            if random.random() < 0.02:
                await self._random_delay(0.2, 0.6)

    async def _random_delay(self, min_s: float, max_s: float) -> None:
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def _mouse_jitter(self) -> None:
        for _ in range(random.randint(1, 3)):
            x = random.randint(100, self._viewport_width - 100)
            y = random.randint(100, self._viewport_height - 100)
            await self.page.mouse.move(x, y, steps=random.randint(5, 15))
            await self._random_delay(0.1, 0.4)

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> FacebookBrowser:
        await self.launch()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
