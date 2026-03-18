from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from conftest import make_text_post
from marketmenow.core.orchestrator import Orchestrator
from marketmenow.core.scheduler import Scheduler
from marketmenow.models.campaign import Campaign, CampaignTarget, ScheduleRule
from marketmenow.models.content import ContentModality
from marketmenow.registry import AdapterRegistry


def _scheduled_campaign(publish_at: datetime | None = None) -> Campaign:
    return Campaign(
        name="scheduled",
        content=make_text_post(),
        targets=[
            CampaignTarget(
                platform="mock",
                modality=ContentModality.TEXT_POST,
                schedule=ScheduleRule(publish_at=publish_at),
            ),
        ],
    )


class TestSchedule:
    async def test_enqueue(self, registry: AdapterRegistry) -> None:
        orch = Orchestrator(registry)
        scheduler = Scheduler(orch)
        future = datetime.now(UTC) + timedelta(hours=1)
        campaign = _scheduled_campaign(future)
        await scheduler.schedule(campaign)
        assert not scheduler._queue.empty()

    async def test_no_publish_at_uses_now(self, registry: AdapterRegistry) -> None:
        orch = Orchestrator(registry)
        scheduler = Scheduler(orch)
        campaign = _scheduled_campaign(publish_at=None)
        await scheduler.schedule(campaign)
        assert not scheduler._queue.empty()


class TestRunLoop:
    async def test_executes_campaign(self, registry: AdapterRegistry) -> None:
        orch = Orchestrator(registry)
        scheduler = Scheduler(orch)

        past = datetime.now(UTC) - timedelta(seconds=1)
        campaign = _scheduled_campaign(past)
        await scheduler.schedule(campaign)

        with patch.object(orch, "run_campaign", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = AsyncMock()

            async def _run_once() -> None:
                await scheduler.run_loop()

            task = asyncio.create_task(_run_once())
            await asyncio.sleep(0.1)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

            mock_run.assert_called_once()
            assert mock_run.call_args[0][0].id == campaign.id
