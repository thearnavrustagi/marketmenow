from __future__ import annotations

import asyncio
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

_LINKEDIN_HOME = "https://www.linkedin.com/feed/"
_LINKEDIN_BASE = "https://www.linkedin.com"

# Consistent UA used across Stealth, context, and client-hint headers.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
# Client Hints that must match the UA above.
_CLIENT_HINT_HEADERS = {
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}


class LinkedInBrowser:
    """Playwright wrapper with anti-detection for LinkedIn."""

    def __init__(
        self,
        session_path: Path,
        user_data_dir: Path,
        headless: bool = False,
        slow_mo_ms: int = 50,
        proxy_url: str = "",
        viewport_width: int = 1280,
        viewport_height: int = 900,
        organization_id: str = "",
    ) -> None:
        self._session_path = session_path
        self._user_data_dir = user_data_dir
        self._headless = headless
        self._slow_mo_ms = slow_mo_ms
        self._proxy_url = proxy_url
        self._viewport_width = viewport_width
        self._viewport_height = viewport_height
        self._organization_id = organization_id

        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def _feed_url(self) -> str:
        """Personal feed or company page depending on organization_id."""
        if self._organization_id:
            return f"{_LINKEDIN_BASE}/company/{self._organization_id}/"
        return _LINKEDIN_HOME

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not launched -- call launch() first")
        return self._page

    async def launch(self) -> Page:
        self._stealth = Stealth(
            navigator_platform_override="MacIntel",
            # Provide an explicit UA so stealth patches stay in sync with
            # what we set on the context below.
            navigator_user_agent_override=_USER_AGENT,
            # Real Chrome always exposes window.chrome.runtime; enabling it
            # here prevents LinkedIn's bot-detection from flagging the absence.
            chrome_runtime=True,
        )
        self._stealth_cm = self._stealth.use_async(async_playwright())
        self._pw = await self._stealth_cm.__aenter__()

        headless_args: list[str] = (
            [
                "--disable-gpu",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                f"--window-size={self._viewport_width},{self._viewport_height}",
            ]
            if self._headless
            else []
        )
        launch_kwargs: dict[str, object] = {
            "headless": self._headless,
            "slow_mo": self._slow_mo_ms,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                *headless_args,
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
            "user_agent": _USER_AGENT,
            "locale": "en-US",
            "timezone_id": "America/New_York",
            # Client-Hint headers must match the UA; headless Chromium omits
            # them by default, which is a reliable bot signal.
            "extra_http_headers": _CLIENT_HINT_HEADERS,
        }

        if self._session_path.exists():
            context_kwargs["storage_state"] = str(self._session_path)
            logger.info("Restoring session from %s", self._session_path)

        self._context = await self._browser.new_context(**context_kwargs)  # type: ignore[arg-type]
        # Belt-and-suspenders: apply stealth scripts to the context directly
        # in addition to the hook already applied via use_async().
        await self._stealth.apply_stealth_async(self._context)
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
        """Open linkedin.com and let the user log in manually."""
        page = self.page
        logger.info("Opening linkedin.com -- please log in manually.")
        await page.goto(_LINKEDIN_BASE, wait_until="load", timeout=60_000)
        await self._random_delay(2.0, 3.0)

        logger.info("Waiting for login (up to 5 minutes)...")
        await page.wait_for_url("**/feed/**", timeout=300_000)

        await self.save_session()
        logger.info("Login successful, session saved.")

    async def login_with_cookie(self, li_at: str) -> None:
        """Inject the li_at session cookie and verify login."""
        if self._context is None:
            raise RuntimeError("Browser not launched")

        cookies = [
            {
                "name": "li_at",
                "value": li_at,
                "domain": ".www.linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            },
        ]
        await self._context.add_cookies(cookies)  # type: ignore[arg-type]
        logger.info("li_at cookie injected, verifying login...")

        page = self.page
        await page.goto(_LINKEDIN_HOME, wait_until="load", timeout=60_000)
        await self._random_delay(3.0, 5.0)

        url = page.url
        if "/login" in url or "/checkpoint" in url or "/authwall" in url:
            raise RuntimeError(
                "Cookie login failed -- LinkedIn redirected to login. "
                "The li_at cookie may be expired. Grab a fresh one from your browser."
            )

        await self.save_session()
        logger.info("Cookie login successful, session saved.")

    async def is_logged_in(self) -> bool:
        page = self.page
        try:
            await page.goto(_LINKEDIN_HOME, wait_until="domcontentloaded", timeout=30_000)
            await self._random_delay(3.0, 5.0)
            url = page.url
            if "/login" in url or "/authwall" in url or "/checkpoint" in url:
                return False
            feed = page.locator("div.feed-shared-update-v2").first
            try:
                await feed.wait_for(state="visible", timeout=10_000)
                return True
            except Exception:
                return "/feed" in url
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
    # Post creation via the LinkedIn web UI
    # ------------------------------------------------------------------

    async def create_text_post(self, text: str) -> bool:
        """Create a text-only post via the LinkedIn web UI."""
        page = self.page
        await self.navigate(self._feed_url)
        await self._random_delay(1.0, 2.0)
        await self.scroll_down(times=random.randint(0, 1))

        start_post = page.locator("button.share-box-feed-entry__trigger")
        await start_post.wait_for(state="visible", timeout=15_000)
        await self._smart_click(start_post)
        await self._random_delay(1.0, 2.0)

        editor = page.locator("div.ql-editor[contenteditable='true']")
        await editor.wait_for(state="visible", timeout=10_000)
        await editor.click()
        await self._random_delay(0.3, 0.8)

        await self._human_type(text)
        await self._random_delay(0.8, 1.5)

        post_btn = page.locator("button.share-actions__primary-action")
        await post_btn.wait_for(state="visible", timeout=10_000)
        await self._smart_click(post_btn)
        await self._random_delay(3.0, 5.0)

        logger.info("Text post created on LinkedIn")
        return True

    async def create_image_post(self, text: str, image_paths: list[Path]) -> bool:
        """Create a post with images via the LinkedIn web UI."""
        page = self.page
        await self.navigate(self._feed_url)
        await self._random_delay(1.0, 2.0)
        await self.scroll_down(times=random.randint(0, 1))

        start_post = page.locator("button.share-box-feed-entry__trigger")
        await start_post.wait_for(state="visible", timeout=15_000)
        await self._smart_click(start_post)
        await self._random_delay(1.0, 2.0)

        media_btn = page.locator(
            'button[aria-label="Add media"],'
            'button[aria-label="Add a photo"],'
            "button.image-sharing-detour-button"
        ).first
        await media_btn.wait_for(state="visible", timeout=10_000)
        await self._smart_click(media_btn)
        await self._random_delay(1.0, 2.0)

        file_input = page.locator('input[type="file"][accept*="image"]').first
        await file_input.set_input_files([str(p.resolve()) for p in image_paths])
        await self._random_delay(2.0, 4.0)

        done_btn = page.locator(
            'button[aria-label="Done"],button:has-text("Done"),button:has-text("Next")'
        ).first
        try:
            await done_btn.wait_for(state="visible", timeout=5_000)
            await self._smart_click(done_btn)
            await self._random_delay(1.0, 2.0)
        except Exception:
            pass

        if text:
            editor = page.locator("div.ql-editor[contenteditable='true']")
            await editor.wait_for(state="visible", timeout=10_000)
            await editor.click()
            await self._random_delay(0.3, 0.8)
            await self._human_type(text)
            await self._random_delay(0.8, 1.5)

        post_btn = page.locator("button.share-actions__primary-action")
        await post_btn.wait_for(state="visible", timeout=10_000)
        await self._smart_click(post_btn)
        await self._random_delay(3.0, 5.0)

        logger.info("Image post created on LinkedIn (%d images)", len(image_paths))
        return True

    async def create_video_post(self, text: str, video_path: Path) -> bool:
        """Create a post with a video via the LinkedIn web UI."""
        page = self.page
        await self.navigate(self._feed_url)
        await self._random_delay(1.0, 2.0)
        await self.scroll_down(times=random.randint(0, 1))

        start_post = page.locator("button.share-box-feed-entry__trigger")
        await start_post.wait_for(state="visible", timeout=15_000)
        await self._smart_click(start_post)
        await self._random_delay(1.0, 2.0)

        media_btn = page.locator(
            'button[aria-label="Add media"],'
            'button[aria-label="Add a video"],'
            "button.image-sharing-detour-button"
        ).first
        await media_btn.wait_for(state="visible", timeout=10_000)
        await self._smart_click(media_btn)
        await self._random_delay(1.0, 2.0)

        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(str(video_path.resolve()))
        await self._random_delay(3.0, 6.0)

        done_btn = page.locator(
            'button[aria-label="Done"],button:has-text("Done"),button:has-text("Next")'
        ).first
        try:
            await done_btn.wait_for(state="visible", timeout=10_000)
            await self._smart_click(done_btn)
            await self._random_delay(1.0, 2.0)
        except Exception:
            pass

        if text:
            editor = page.locator("div.ql-editor[contenteditable='true']")
            await editor.wait_for(state="visible", timeout=10_000)
            await editor.click()
            await self._random_delay(0.3, 0.8)
            await self._human_type(text)
            await self._random_delay(0.8, 1.5)

        post_btn = page.locator("button.share-actions__primary-action")
        await post_btn.wait_for(state="visible", timeout=10_000)
        await self._smart_click(post_btn)
        await self._random_delay(3.0, 5.0)

        logger.info("Video post created on LinkedIn")
        return True

    async def create_document_post(self, text: str, doc_path: Path, title: str = "") -> bool:
        """Create a post with a document (PDF/PPT) via the LinkedIn web UI."""
        page = self.page
        await self.navigate(self._feed_url)
        await self._random_delay(1.0, 2.0)
        await self.scroll_down(times=random.randint(0, 1))

        start_post = page.locator("button.share-box-feed-entry__trigger")
        await start_post.wait_for(state="visible", timeout=15_000)
        await self._smart_click(start_post)
        await self._random_delay(1.0, 2.0)

        more_btn = page.locator('button[aria-label="More"],button:has-text("More")').first
        try:
            await more_btn.wait_for(state="visible", timeout=5_000)
            await self._smart_click(more_btn)
            await self._random_delay(0.5, 1.0)
        except Exception:
            pass

        doc_btn = page.locator(
            'button[aria-label="Add a document"],'
            'button:has-text("Add a document"),'
            'li-icon[type="document"]'
        ).first
        await doc_btn.wait_for(state="visible", timeout=10_000)
        await self._smart_click(doc_btn)
        await self._random_delay(1.0, 2.0)

        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(str(doc_path.resolve()))
        await self._random_delay(2.0, 4.0)

        if title:
            title_input = page.locator(
                'input[placeholder*="title"],input[aria-label*="title"],input[name*="title"]'
            ).first
            try:
                await title_input.wait_for(state="visible", timeout=5_000)
                await title_input.click()
                await self._random_delay(0.2, 0.5)
                await self._human_type(title)
                await self._random_delay(0.5, 1.0)
            except Exception:
                logger.debug("Could not find document title input")

        done_btn = page.locator(
            'button[aria-label="Done"],button:has-text("Done"),button:has-text("Next")'
        ).first
        try:
            await done_btn.wait_for(state="visible", timeout=10_000)
            await self._smart_click(done_btn)
            await self._random_delay(1.0, 2.0)
        except Exception:
            pass

        if text:
            editor = page.locator("div.ql-editor[contenteditable='true']")
            await editor.wait_for(state="visible", timeout=10_000)
            await editor.click()
            await self._random_delay(0.3, 0.8)
            await self._human_type(text)
            await self._random_delay(0.8, 1.5)

        post_btn = page.locator("button.share-actions__primary-action")
        await post_btn.wait_for(state="visible", timeout=10_000)
        await self._smart_click(post_btn)
        await self._random_delay(3.0, 5.0)

        logger.info("Document post created on LinkedIn")
        return True

    async def create_poll_post(
        self,
        text: str,
        question: str,
        options: list[str],
        duration_weeks: int = 1,
    ) -> bool:
        """Create a poll post via the LinkedIn web UI."""
        page = self.page
        await self.navigate(self._feed_url)
        await self._random_delay(1.0, 2.0)
        await self.scroll_down(times=random.randint(0, 1))

        start_post = page.locator("button.share-box-feed-entry__trigger")
        await start_post.wait_for(state="visible", timeout=15_000)
        await self._smart_click(start_post)
        await self._random_delay(1.0, 2.0)

        more_btn = page.locator('button[aria-label="More"],button:has-text("More")').first
        try:
            await more_btn.wait_for(state="visible", timeout=5_000)
            await self._smart_click(more_btn)
            await self._random_delay(0.5, 1.0)
        except Exception:
            pass

        poll_btn = page.locator(
            'button[aria-label="Create a poll"],'
            'button:has-text("Create a poll"),'
            'li-icon[type="poll"]'
        ).first
        await poll_btn.wait_for(state="visible", timeout=10_000)
        await self._smart_click(poll_btn)
        await self._random_delay(1.0, 2.0)

        q_input = page.locator(
            'textarea[placeholder*="question"],'
            'input[placeholder*="question"],'
            'textarea[aria-label*="question"]'
        ).first
        await q_input.wait_for(state="visible", timeout=10_000)
        await q_input.click()
        await self._random_delay(0.2, 0.5)
        await self._human_type(question)
        await self._random_delay(0.5, 1.0)

        option_inputs = page.locator('input[placeholder*="Option"],input[aria-label*="Option"]')
        for idx, opt_text in enumerate(options):
            if idx >= await option_inputs.count():
                add_option_btn = page.locator(
                    'button:has-text("Add option"),button[aria-label="Add option"]'
                ).first
                try:
                    await self._smart_click(add_option_btn)
                    await self._random_delay(0.3, 0.6)
                except Exception:
                    break

            option_input = option_inputs.nth(idx)
            await option_input.click()
            await self._random_delay(0.1, 0.3)
            await self._human_type(opt_text)
            await self._random_delay(0.3, 0.6)

        done_btn = page.locator('button:has-text("Done"),button[aria-label="Done"]').first
        await done_btn.wait_for(state="visible", timeout=5_000)
        await self._smart_click(done_btn)
        await self._random_delay(1.0, 2.0)

        if text:
            editor = page.locator("div.ql-editor[contenteditable='true']")
            await editor.wait_for(state="visible", timeout=10_000)
            await editor.click()
            await self._random_delay(0.3, 0.8)
            await self._human_type(text)
            await self._random_delay(0.8, 1.5)

        post_btn = page.locator("button.share-actions__primary-action")
        await post_btn.wait_for(state="visible", timeout=10_000)
        await self._smart_click(post_btn)
        await self._random_delay(3.0, 5.0)

        logger.info("Poll post created on LinkedIn")
        return True

    async def screenshot(self, path: str | Path) -> None:
        await self.page.screenshot(path=str(path), full_page=False)

    # ------------------------------------------------------------------
    # Human-like behaviour
    # ------------------------------------------------------------------

    async def _smart_click(self, locator: object) -> None:
        """Click at a random position within the element's bounding box."""
        box = await locator.bounding_box()  # type: ignore[union-attr]
        if box:
            x = box["x"] + random.uniform(2, box["width"] - 2)
            y = box["y"] + random.uniform(2, box["height"] - 2)
            await self.page.mouse.click(x, y)
        else:
            await locator.click()  # type: ignore[union-attr]
        await self._random_delay(0.3, 1.0)

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

    async def __aenter__(self) -> LinkedInBrowser:
        await self.launch()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
