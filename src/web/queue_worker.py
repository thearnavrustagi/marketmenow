from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from web import db
from web.cli_runner import CliResult, run_cli_streaming
from web.config import settings
from web.events import ProgressEvent, hub

logger = logging.getLogger(__name__)


async def _can_post(platform: str, limits: dict) -> bool:
    """Check whether a post to *platform* is allowed under its rate limits."""
    max_hour = limits.get("max_per_hour", 2)
    max_day = limits.get("max_per_day", 10)
    min_interval = limits.get("min_interval_seconds", 300)

    posts_last_hour = await db.count_recent_posts(platform, within_seconds=3600)
    if posts_last_hour >= max_hour:
        return False

    posts_last_day = await db.count_recent_posts(platform, within_seconds=86400)
    if posts_last_day >= max_day:
        return False

    last = await db.last_post_time(platform)
    if last is not None:
        elapsed = (datetime.now(UTC) - last).total_seconds()
        if elapsed < min_interval:
            return False

    return True


async def _process_job(job: dict, limits: dict) -> None:
    platform = job["platform"]
    queue_id: UUID = job["id"]
    content_id: UUID = job["content_item_id"]
    publish_command: list[str] | None = job.get("publish_command")

    if not publish_command:
        logger.warning("Queue job %s has no publish_command, marking failed", queue_id)
        await db.update_queue_status(
            queue_id, "failed", error_message="No publish command configured"
        )
        await db.update_content_status(content_id, "failed", error_message="No publish command")
        hub.publish(
            content_id, ProgressEvent(event_type="error", message="No publish command configured")
        )
        return

    await db.update_queue_status(queue_id, "posting")
    await db.update_content_status(content_id, "posting")
    hub.publish(
        content_id,
        ProgressEvent(event_type="phase", message=f"Publishing to {platform}...", phase="posting"),
    )

    result: CliResult = await run_cli_streaming(
        publish_command,
        item_id=content_id,
        output_dir=job.get("output_path"),
    )

    if result.exit_code == 0:
        await db.update_queue_status(queue_id, "posted")
        await db.update_content_status(content_id, "posted")
        await db.log_post(platform, content_id, success=True)
        hub.publish(
            content_id,
            ProgressEvent(event_type="done", message=f"Posted to {platform} successfully"),
        )
        logger.info("Posted content %s to %s", content_id, platform)
    else:
        error = result.stderr[:500] or f"Exit code {result.exit_code}"
        await db.update_queue_status(queue_id, "failed", error_message=error)
        await db.update_content_status(content_id, "failed", error_message=error)
        await db.log_post(platform, content_id, success=False)
        hub.publish(
            content_id, ProgressEvent(event_type="error", message=f"Post failed: {error[:200]}")
        )
        logger.error("Failed posting %s to %s: %s", content_id, platform, error)


async def run_queue_loop() -> None:
    """Main loop: drain each platform queue respecting rate limits."""
    logger.info("Queue worker started (poll every %ds)", settings.queue_poll_seconds)

    while True:
        try:
            rate_limit_rows = await db.get_rate_limits()
            limits_map = {r["platform"]: dict(r) for r in rate_limit_rows}

            for platform, limits in limits_map.items():
                if not await _can_post(platform, limits):
                    continue

                job = await db.get_next_queue_job(platform)
                if job is None:
                    continue

                await _process_job(dict(job), limits)

        except Exception:
            logger.exception("Queue worker cycle error")

        await asyncio.sleep(settings.queue_poll_seconds)
