from __future__ import annotations

import logging
import random

from marketmenow.outreach.models import OutreachSendResult

from ..browser import StealthBrowser

logger = logging.getLogger(__name__)

_MESSAGES_URL = "https://x.com/messages"


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

    async def _send_dm(self, handle: str, message: str) -> OutreachSendResult:
        page = self._browser.page

        await self._browser.navigate(_MESSAGES_URL)
        await self._browser._random_delay(2.0, 4.0)

        # Click new message compose button
        compose_btn = page.locator('a[data-testid="NewDM_Button"], a[href="/messages/compose"]')
        try:
            await compose_btn.first.wait_for(state="visible", timeout=10_000)
            await compose_btn.first.click()
        except Exception:
            return OutreachSendResult(
                recipient_handle=handle,
                success=False,
                error_message="Could not find new-message button",
            )
        await self._browser._random_delay(1.5, 3.0)

        # Type the handle in the search field
        search_input = page.locator('input[data-testid="searchPeople"], input[name="searchPeople"]')
        try:
            await search_input.first.wait_for(state="visible", timeout=8_000)
            await search_input.first.click()
            await self._browser._random_delay(0.3, 0.8)
            for char in handle:
                await page.keyboard.type(char, delay=random.randint(50, 150))
            await self._browser._random_delay(1.5, 2.5)
        except Exception:
            return OutreachSendResult(
                recipient_handle=handle,
                success=False,
                error_message="Could not type in recipient search field",
            )

        # Select the user from autocomplete
        user_result = page.locator('div[data-testid="TypeaheadUser"]')
        try:
            await user_result.first.wait_for(state="visible", timeout=5_000)
            await user_result.first.click()
            await self._browser._random_delay(0.5, 1.0)
        except Exception:
            return OutreachSendResult(
                recipient_handle=handle,
                success=False,
                error_message="User not found in autocomplete -- may not accept DMs",
            )

        # Click Next to enter conversation
        next_btn = page.locator(
            'button[data-testid="nextButton"], div[role="button"][data-testid="nextButton"]'
        )
        try:
            await next_btn.first.wait_for(state="visible", timeout=5_000)
            await next_btn.first.click()
            await self._browser._random_delay(1.5, 3.0)
        except Exception:
            return OutreachSendResult(
                recipient_handle=handle,
                success=False,
                error_message="Could not proceed to conversation view",
            )

        # Type the message
        msg_input = page.locator(
            'div[data-testid="dmComposerTextInput"], '
            'div[data-testid="dmComposerTextInput"] div[role="textbox"]'
        )
        try:
            await msg_input.first.wait_for(state="visible", timeout=8_000)
            await msg_input.first.click()
            await self._browser._random_delay(0.3, 0.8)

            for char in message:
                await page.keyboard.type(char, delay=random.randint(30, 150))
                if random.random() < 0.03:
                    await self._browser._random_delay(0.3, 1.0)

            await self._browser._random_delay(0.8, 2.0)
        except Exception:
            return OutreachSendResult(
                recipient_handle=handle,
                success=False,
                error_message="Could not type message -- user may not accept DMs",
            )

        # Send
        send_btn = page.locator('button[data-testid="dmComposerSendButton"]')
        try:
            await send_btn.first.wait_for(state="visible", timeout=5_000)
            await send_btn.first.click()
            await self._browser._random_delay(2.0, 4.0)
        except Exception:
            return OutreachSendResult(
                recipient_handle=handle,
                success=False,
                error_message="Could not click send button",
            )

        logger.info("DM sent to @%s", handle)
        return OutreachSendResult(recipient_handle=handle, success=True)
