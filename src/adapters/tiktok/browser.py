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

_TIKTOK_HOME = "https://www.tiktok.com/"
_TIKTOK_UPLOAD = "https://www.tiktok.com/creator#/upload?scene=creator_center"


class TikTokBrowser:
    """Playwright wrapper with anti-detection for TikTok cookie-based posting."""

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
            logger.info("Restoring TikTok session from %s", self._session_path)

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
        logger.info("TikTok session saved to %s", self._session_path)

    # ------------------------------------------------------------------
    # Login flows
    # ------------------------------------------------------------------

    async def login_manual(self) -> None:
        """Open tiktok.com and let the user log in manually."""
        page = self.page
        logger.info("Opening tiktok.com -- please log in manually.")
        await page.goto(_TIKTOK_HOME, wait_until="load", timeout=60_000)
        await self._random_delay(2.0, 3.0)

        logger.info("Waiting for login (up to 5 minutes)...")
        try:
            await page.wait_for_selector(
                'a[data-e2e="upload-icon"], button[id="header-more-menu-icon"]',
                timeout=300_000,
            )
        except Exception as exc:
            url = page.url
            if "/login" in url:
                raise RuntimeError("Login was not completed within the timeout.") from exc
            logger.warning("Could not detect logged-in indicator, checking URL.")

        await self.save_session()
        logger.info("TikTok login successful, session saved.")

    async def login_with_cookies(self, session_id: str) -> None:
        """Inject the sessionid cookie and verify login."""
        if self._context is None:
            raise RuntimeError("Browser not launched")

        cookies = [
            {
                "name": "sessionid",
                "value": session_id,
                "domain": ".tiktok.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            },
            {
                "name": "sessionid_ss",
                "value": session_id,
                "domain": ".tiktok.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            },
        ]
        await self._context.add_cookies(cookies)  # type: ignore[arg-type]
        logger.info("TikTok cookies injected, verifying login...")

        page = self.page
        await page.goto(_TIKTOK_HOME, wait_until="load", timeout=60_000)
        await self._random_delay(3.0, 5.0)

        url = page.url
        if "/login" in url:
            raise RuntimeError(
                "Cookie login failed -- TikTok redirected to login page. "
                "The sessionid cookie may be expired. Grab a fresh one from "
                "DevTools > Application > Cookies > tiktok.com."
            )

        await self.save_session()
        logger.info("TikTok cookie login successful, session saved.")

    async def is_logged_in(self) -> bool:
        page = self.page
        try:
            await page.goto(_TIKTOK_HOME, wait_until="domcontentloaded", timeout=30_000)
            await self._random_delay(3.0, 5.0)
            url = page.url
            if "/login" in url:
                return False
            upload_icon = page.locator('a[data-e2e="upload-icon"]').first
            try:
                await upload_icon.wait_for(state="visible", timeout=10_000)
                return True
            except Exception:
                return "tiktok.com" in url and "/login" not in url
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Video upload via browser UI
    # ------------------------------------------------------------------

    async def upload_video(self, video_path: Path, caption: str) -> bool:
        """Upload a video via TikTok's web creator center.

        Returns True on success.
        """
        page = self.page
        await self.navigate(_TIKTOK_UPLOAD)
        await self._random_delay(2.0, 4.0)

        iframe_locator = page.frame_locator('iframe[src*="creator"]')

        file_input = page.locator('input[type="file"][accept*="video"]').first
        try:
            await file_input.wait_for(state="attached", timeout=10_000)
        except Exception:
            logger.debug("File input not in main page, trying iframe")
            file_input = iframe_locator.locator('input[type="file"][accept*="video"]').first
            await file_input.wait_for(state="attached", timeout=15_000)

        await file_input.set_input_files(str(video_path.resolve()))
        logger.info("Video file selected: %s", video_path.name)
        await self._random_delay(5.0, 8.0)

        await self._dismiss_modals(page)
        await self._wait_for_upload_complete(page)
        await self._dismiss_modals(page)

        await self._type_caption(page, caption)

        await self._click_post(page)

        logger.info("Video published to TikTok via browser")
        return True

    async def _dismiss_modals(self, page: Page) -> None:
        """Close any TikTok modal overlays that block interaction."""
        for _ in range(5):
            overlay = page.locator("div.TUXModal-overlay").first
            try:
                if await overlay.is_visible(timeout=1_000):  # type: ignore[call-arg]
                    logger.debug("Modal overlay detected, attempting to dismiss")
                    # Try clicking close/X buttons inside the modal
                    for close_sel in [
                        'div.TUXModal-overlay button[aria-label="Close"]',
                        "div.TUXModal-overlay button:has(svg)",
                        'div.TUXModal-overlay [data-e2e*="close"]',
                        'button[aria-label="Close"]',
                    ]:
                        close_btn = page.locator(close_sel).first
                        try:
                            if await close_btn.is_visible(timeout=1_000):  # type: ignore[call-arg]
                                await close_btn.click(force=True)
                                await self._random_delay(0.5, 1.0)
                                logger.debug("Closed modal via %s", close_sel)
                                break
                        except Exception:
                            continue
                    else:
                        # No close button found — press Escape
                        await page.keyboard.press("Escape")
                        await self._random_delay(0.5, 1.0)
                        logger.debug("Dismissed modal via Escape")
                else:
                    return
            except Exception:
                return
        logger.debug("Modal dismiss loop exhausted")

    async def _wait_for_upload_complete(self, page: Page) -> None:
        """Wait until the video upload finishes processing."""
        for i in range(90):
            await asyncio.sleep(2.0)
            try:
                # TikTok shows a progress percentage or "Uploaded" text
                for text in ["Uploaded", "uploaded", "100%", "Repost"]:
                    indicator = page.locator(f'text="{text}"').first
                    if await indicator.is_visible(timeout=500):  # type: ignore[call-arg]
                        logger.debug("Upload complete: found '%s'", text)
                        return
            except Exception:
                pass
            # Check if Post button exists and is not disabled
            try:
                post_btn = page.locator('button:has-text("Post"):not([disabled])').first
                if await post_btn.is_visible(timeout=500):  # type: ignore[call-arg]
                    logger.debug("Post button visible and enabled")
                    return
            except Exception:
                pass
            if i > 0 and i % 10 == 0:
                logger.debug("Still waiting for upload... (%ds)", i * 2)
        logger.warning("Upload wait timed out after 180s, proceeding anyway")

    async def _type_caption(self, page: Page, caption: str) -> None:
        """Clear and type caption into the editor, dismissing overlays as needed."""
        editor = page.locator(
            'div.public-DraftEditor-content[contenteditable="true"], '
            'div[contenteditable="true"][role="combobox"], '
            'div[contenteditable="true"][role="textbox"], '
            'div[contenteditable="true"][data-text="true"]'
        ).first

        try:
            await editor.wait_for(state="visible", timeout=10_000)
        except Exception:
            logger.warning("Caption editor not found, skipping caption")
            return

        # Try normal click first; if intercepted by overlay, dismiss and force-click
        for attempt in range(3):
            try:
                await editor.click(timeout=5_000)
                break
            except Exception:
                logger.debug("Caption click blocked (attempt %d), dismissing modals", attempt + 1)
                await self._dismiss_modals(page)
                await self._random_delay(0.5, 1.0)
                try:
                    await editor.click(force=True, timeout=5_000)
                    break
                except Exception:
                    # Last resort: JS click
                    try:
                        await editor.evaluate("el => el.click()")
                        break
                    except Exception:
                        await self._random_delay(1.0, 2.0)

        await self._random_delay(0.3, 0.8)
        await page.keyboard.press("Meta+a")
        await self._random_delay(0.1, 0.3)
        await self._human_type(caption)
        await self._random_delay(0.5, 1.0)

    async def _click_post(self, page: Page) -> None:
        """Click the Post/Publish button."""
        await self._dismiss_modals(page)

        post_btn = page.locator('button:has-text("Post"), button:has-text("Publish")').first

        try:
            await post_btn.wait_for(state="visible", timeout=15_000)
        except Exception as exc:
            raise RuntimeError("Post button not found on TikTok upload page") from exc

        for attempt in range(3):
            try:
                await post_btn.click(timeout=5_000)
                break
            except Exception:
                logger.debug("Post click blocked (attempt %d), dismissing modals", attempt + 1)
                await self._dismiss_modals(page)
                try:
                    await post_btn.click(force=True, timeout=5_000)
                    break
                except Exception:
                    await post_btn.evaluate("el => el.click()")
                    break

        await self._random_delay(3.0, 6.0)

        # Wait for success or navigation away from upload page
        for _ in range(30):
            await asyncio.sleep(2.0)
            url = page.url
            if "upload" not in url.lower():
                logger.debug("Navigated away from upload page -- post likely succeeded")
                return
            for text in ["uploaded", "processing", "Your video", "Manage your posts"]:
                try:
                    el = page.locator(f'text="{text}"').first
                    if await el.is_visible(timeout=500):  # type: ignore[call-arg]
                        logger.debug("Post success indicator: '%s'", text)
                        return
                except Exception:
                    pass
        logger.warning("Post success indicator not found, but button was clicked")

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

    async def __aenter__(self) -> TikTokBrowser:
        await self.launch()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
