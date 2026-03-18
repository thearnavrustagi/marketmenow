from __future__ import annotations

import logging

from marketmenow.core.orchestrator import CampaignResult, Orchestrator
from marketmenow.models.campaign import Campaign, CampaignTarget
from marketmenow.models.content import BaseContent
from marketmenow.models.distribution import DistributionMap
from marketmenow.registry import AdapterRegistry

logger = logging.getLogger(__name__)


class ContentDistributor:
    """Resolves target platforms from a ``DistributionMap`` and fans out
    publishing via the existing ``Orchestrator`` / ``ContentPipeline`` stack.
    """

    def __init__(
        self,
        registry: AdapterRegistry,
        distribution_map: DistributionMap | None = None,
    ) -> None:
        self._registry = registry
        self._map = distribution_map or DistributionMap.defaults()
        self._orchestrator = Orchestrator(registry)

    async def distribute(
        self,
        content: BaseContent,
        *,
        platforms: frozenset[str] | None = None,
    ) -> CampaignResult:
        """Publish *content* to every applicable platform.

        If *platforms* is provided it overrides the distribution map; only
        those platforms will be targeted.  Otherwise the map is consulted to
        resolve the target set, intersected with whatever is actually
        registered in the adapter registry.
        """
        if platforms is not None:
            target_platforms = platforms
        else:
            target_platforms = self._map.platforms_for(content.modality)

        registered = frozenset(self._registry.list_platforms())
        resolved = target_platforms & registered

        if not resolved:
            logger.warning(
                "No registered platforms matched for modality %s (wanted %s, registered %s)",
                content.modality.value,
                sorted(target_platforms),
                sorted(registered),
            )
            return CampaignResult(campaign_id=content.id)

        targets = [CampaignTarget(platform=p, modality=content.modality) for p in sorted(resolved)]

        campaign = Campaign(
            name=f"distribute-{content.modality.value}",
            content=content,
            targets=targets,
        )

        logger.info(
            "Distributing %s to %s",
            content.modality.value,
            ", ".join(sorted(resolved)),
        )
        return await self._orchestrator.run_campaign(campaign)
