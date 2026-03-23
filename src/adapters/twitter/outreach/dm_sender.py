from __future__ import annotations

import logging
import random
from pathlib import Path

from marketmenow.outreach.models import OutreachSendResult

from ..browser import StealthBrowser

logger = logging.getLogger(__name__)

_SCREENSHOT_DIR = Path(".outreach_debug")


class TwitterDMSender:
    """Sends DMs via the Twitter web UI using Playwright. Implements MessageSender."""

    def __init__(self, browser: StealthBrowser) -> None:
        self._browser = browser

    async def send(self, handle: str, message: str) -> OutreachSendResult:
        handle_clean = handle.lstrip("@")
        try:
            return await self._send_dm(handle_clean, message)
        except Exception as exc:
            logger.exception("DM send failed for @%s", handle_clean)
            return OutreachSendResult(
                recipient_handle=handle_clean,
                success=False,
                error_message=str(exc),
            )

    async def _save_debug_screenshot(self, handle: str, stage: str) -> None:
        try:
            _SCREENSHOT_DIR.mkdir(exist_ok=True)
            path = _SCREENSHOT_DIR / f"{handle}_{stage}.png"
            await self._browser.page.screenshot(path=str(path))
            logger.info("Debug screenshot saved: %s", path)
        except Exception:
            logger.debug("Could not save debug screenshot", exc_info=True)

    async def _send_dm(self, handle: str, message: str) -> OutreachSendResult:
        page = self._browser.page

        profile_url = f"https://x.com/{handle}"
        logger.info("Navigating to profile @%s to open DM", handle)
        await self._browser.navigate(profile_url)
        await self._browser._random_delay(2.0, 4.0)

        dm_btn = page.locator(
            'button[data-testid="sendDMFromProfile"], '
            '[aria-label="Message"], '
            'a[href*="/messages/"][data-testid]'
        )
        try:
            await dm_btn.first.wait_for(state="visible", timeout=8_000)
            await dm_btn.first.click()
            logger.info("Clicked DM button on @%s profile", handle)
            await self._browser._random_delay(2.0, 4.0)
        except Exception:
            await self._save_debug_screenshot(handle, "no_dm_button")
            return OutreachSendResult(
                recipient_handle=handle,
                success=False,
                error_message="Could not find DM button on profile — may not accept DMs",
            )

        msg_input = page.locator(
            'div[data-testid="dmComposerTextInput"], '
            'div[data-testid="dmComposerTextInput"] div[role="textbox"], '
            'div[data-testid="DmScrollerContainer"] div[role="textbox"], '
            'div[contenteditable="true"][data-testid="dmComposerTextInput"]'
        )
        try:
            await msg_input.first.wait_for(state="visible", timeout=10_000)
            await msg_input.first.click()
            logger.info("Message input found, typing message to @%s", handle)
            await self._browser._random_delay(0.3, 0.8)

            for char in message:
                await page.keyboard.type(char, delay=random.randint(30, 150))
                if random.random() < 0.03:
                    await self._browser._random_delay(0.3, 1.0)

            await self._browser._random_delay(0.8, 2.0)
        except Exception:
            await self._save_debug_screenshot(handle, "no_msg_input")
            return OutreachSendResult(
                recipient_handle=handle,
                success=False,
                error_message="Could not type message — conversation view may not have loaded",
            )

        send_btn = page.locator(
            'button[data-testid="dmComposerSendButton"], '
            'div[data-testid="dmComposerSendButton"], '
            'button[aria-label="Send"]'
        )
        try:
            await send_btn.first.wait_for(state="visible", timeout=5_000)
            await send_btn.first.click()
            await self._browser._random_delay(2.0, 4.0)
        except Exception:
            await self._save_debug_screenshot(handle, "no_send_button")
            return OutreachSendResult(
                recipient_handle=handle,
                success=False,
                error_message="Could not click send button",
            )

        logger.info("DM sent to @%s", handle)
        return OutreachSendResult(recipient_handle=handle, success=True)
