from __future__ import annotations

from pathlib import Path

import yaml

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.outreach.history import OutreachHistory
from marketmenow.outreach.models import CustomerProfile


class DiscoverProspectsStep:
    """Load a customer profile and discover prospect posts via platform-specific vectors."""

    def __init__(self, platform: str = "twitter") -> None:
        self._platform = platform

    @property
    def name(self) -> str:
        return "discover-prospects"

    @property
    def description(self) -> str:
        return f"Discover prospects on {self._platform} via configured vectors"

    async def execute(self, ctx: WorkflowContext) -> None:
        profile_path = Path(str(ctx.require_param("profile")))
        if not profile_path.exists():
            raise WorkflowError(f"Customer profile not found: {profile_path}")

        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))

        raw_discovery = raw.pop("discovery", [])
        discovery_vectors = []
        for vec in raw_discovery:
            discovery_vectors.append(
                {
                    "vector_type": vec["type"],
                    "entries": vec.get("entries", []),
                    "max_per_entry": vec.get("max_per_entry", 5),
                }
            )
        raw["discovery_vectors"] = discovery_vectors

        customer_profile = CustomerProfile(**raw)
        ctx.set_artifact("customer_profile", customer_profile)

        history = OutreachHistory()
        ctx.set_artifact("outreach_history", history)

        if self._platform == "twitter":
            await self._discover_twitter(ctx, customer_profile, history)
        else:
            raise WorkflowError(f"Outreach discovery not implemented for {self._platform}")

    async def _discover_twitter(
        self,
        ctx: WorkflowContext,
        profile: CustomerProfile,
        history: OutreachHistory,
    ) -> None:
        from adapters.twitter.outreach.orchestrator import TwitterOutreachOrchestrator
        from adapters.twitter.settings import TwitterSettings

        settings = TwitterSettings()
        headless_raw = ctx.get_param("headless", True)
        headless = headless_raw if isinstance(headless_raw, bool) else str(headless_raw).lower() in ("true", "1", "yes")
        settings = settings.model_copy(update={"headless": headless})

        orchestrator = TwitterOutreachOrchestrator(settings, profile, history)
        ctx.set_artifact("outreach_orchestrator", orchestrator)

        await orchestrator.launch()
        if not await orchestrator.ensure_logged_in():
            raise WorkflowError("Not logged in to Twitter. Run `mmn twitter login` first.")

        with ctx.console.status("[bold cyan]Running discovery vectors..."):
            prospects = await orchestrator.discover()

        if not prospects:
            raise WorkflowError("No prospects discovered. Check your search queries.")

        ctx.console.print(
            f"[green]Discovered {sum(len(v) for v in prospects.values())} posts "
            f"from {len(prospects)} unique handles[/green]"
        )
        ctx.set_artifact("discovered_prospects", prospects)
