from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

from marketmenow.core.pipeline import ContentPipeline
from marketmenow.exceptions import UnsupportedModalityError
from marketmenow.models.campaign import Campaign, CampaignTarget
from marketmenow.models.result import PublishResult, SendResult
from marketmenow.registry import AdapterRegistry


@dataclass
class CampaignResult:
    campaign_id: UUID
    results: list[PublishResult | SendResult] = field(default_factory=list)
    errors: list[tuple[CampaignTarget, Exception]] = field(default_factory=list)


class Orchestrator:
    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry
        self._pipeline = ContentPipeline(registry)

    async def run_campaign(self, campaign: Campaign) -> CampaignResult:
        result = CampaignResult(campaign_id=campaign.id)

        executable_targets: list[CampaignTarget] = []
        for target in campaign.targets:
            if not self._registry.supports(target.platform, target.modality):
                result.errors.append(
                    (
                        target,
                        UnsupportedModalityError(target.platform, target.modality.value),
                    )
                )
            else:
                executable_targets.append(target)

        if not executable_targets:
            return result

        outcomes = await asyncio.gather(
            *(self._execute_target(campaign, target) for target in executable_targets),
            return_exceptions=True,
        )

        for target, outcome in zip(executable_targets, outcomes):
            if isinstance(outcome, BaseException):
                result.errors.append((target, outcome))  # type: ignore[arg-type]
            else:
                result.results.append(outcome)

        return result

    async def _execute_target(
        self, campaign: Campaign, target: CampaignTarget
    ) -> PublishResult | SendResult:
        return await self._pipeline.execute(campaign.content, target.platform)
