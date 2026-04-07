from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine

logger = logging.getLogger(__name__)


async def with_retry[T](
    fn: Callable[..., Coroutine[object, object, T]],
    *args: object,
    max_retries: int = 3,
    initial_backoff: float = 5.0,
    retry_logger: logging.Logger | None = None,
    context: str = "",
    **kwargs: object,
) -> T:
    """Call *fn* with exponential backoff on failure.

    Backoff doubles each attempt: ``initial_backoff * 2^(attempt-1)``.
    Raises the last exception after *max_retries* exhausted.
    """
    log = retry_logger or logger
    last_exc: BaseException | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt == max_retries:
                log.error(
                    "%sAttempt %d/%d failed, giving up: %s",
                    f"[{context}] " if context else "",
                    attempt,
                    max_retries,
                    exc,
                )
                raise
            backoff = initial_backoff * (2 ** (attempt - 1))
            log.warning(
                "%sAttempt %d/%d failed (%s), retrying in %.1fs",
                f"[{context}] " if context else "",
                attempt,
                max_retries,
                exc,
                backoff,
            )
            await asyncio.sleep(backoff)

    # Unreachable, but satisfies type checker
    raise last_exc  # type: ignore[misc]
