from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from marketmenow.integrations.retry import with_retry


class TestWithRetry:
    async def test_succeeds_first_try(self) -> None:
        """Function that succeeds immediately returns its result."""
        fn = AsyncMock(return_value=42)

        result = await with_retry(fn, max_retries=3, initial_backoff=0.01)

        assert result == 42
        assert fn.await_count == 1

    async def test_succeeds_after_retries(self) -> None:
        """Function that fails twice then succeeds on third attempt."""
        fn = AsyncMock(side_effect=[ValueError("fail1"), ValueError("fail2"), "ok"])

        with patch(
            "marketmenow.integrations.retry.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await with_retry(fn, max_retries=3, initial_backoff=1.0)

        assert result == "ok"
        assert fn.await_count == 3
        assert mock_sleep.await_count == 2

    async def test_raises_after_max_retries(self) -> None:
        """Function that always fails raises after max_retries exhausted."""
        fn = AsyncMock(side_effect=ValueError("always fail"))

        with (
            patch("marketmenow.integrations.retry.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(ValueError, match="always fail"),
        ):
            await with_retry(fn, max_retries=2, initial_backoff=0.01)

        assert fn.await_count == 2

    async def test_exponential_backoff_timing(self) -> None:
        """Sleep durations should follow initial * 2^(attempt-1)."""
        fn = AsyncMock(side_effect=[ValueError("e1"), ValueError("e2"), ValueError("e3"), "ok"])

        with patch(
            "marketmenow.integrations.retry.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await with_retry(fn, max_retries=4, initial_backoff=5.0)

        assert result == "ok"
        sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
        # attempt 1 fails: sleep = 5.0 * 2^0 = 5.0
        # attempt 2 fails: sleep = 5.0 * 2^1 = 10.0
        # attempt 3 fails: sleep = 5.0 * 2^2 = 20.0
        assert sleep_args == [5.0, 10.0, 20.0]
