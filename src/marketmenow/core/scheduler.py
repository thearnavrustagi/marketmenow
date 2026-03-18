from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from marketmenow.core.orchestrator import Orchestrator
from marketmenow.models.campaign import Campaign


class Scheduler:
    """Minimal in-process scheduler. Replace with Celery/APScheduler in production."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator
        self._queue: asyncio.PriorityQueue[tuple[datetime, Campaign]] = asyncio.PriorityQueue()

    async def schedule(self, campaign: Campaign) -> None:
        publish_times = [
            t.schedule.publish_at for t in campaign.targets if t.schedule.publish_at is not None
        ]
        first_time = min(publish_times) if publish_times else datetime.now(UTC)
        await self._queue.put((first_time, campaign))

    async def run_loop(self) -> None:
        """Block forever, executing campaigns as their scheduled time arrives."""
        while True:
            publish_at, campaign = await self._queue.get()
            delay = (publish_at - datetime.now(UTC)).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            await self._orchestrator.run_campaign(campaign)
            self._queue.task_done()
