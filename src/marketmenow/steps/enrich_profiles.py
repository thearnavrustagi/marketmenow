from __future__ import annotations

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.outreach.models import CustomerProfile, DiscoveredProspectPost


class EnrichProfilesStep:
    """Visit each discovered prospect's profile and extract structured data."""

    def __init__(self, platform: str = "twitter") -> None:
        self._platform = platform

    @property
    def name(self) -> str:
        return "enrich-profiles"

    @property
    def description(self) -> str:
        return f"Scrape profile details for discovered prospects on {self._platform}"

    async def execute(self, ctx: WorkflowContext) -> None:
        prospects: dict[str, list[DiscoveredProspectPost]] = ctx.get_artifact(  # type: ignore[assignment]
            "discovered_prospects"
        )
        customer_profile: CustomerProfile = ctx.get_artifact("customer_profile")  # type: ignore[assignment]

        if self._platform == "twitter":
            await self._enrich_twitter(ctx, prospects, customer_profile)
        else:
            raise WorkflowError(f"Profile enrichment not implemented for {self._platform}")

    async def _enrich_twitter(
        self,
        ctx: WorkflowContext,
        prospects: dict[str, list[DiscoveredProspectPost]],
        customer_profile: CustomerProfile,
    ) -> None:
        from adapters.twitter.outreach.orchestrator import TwitterOutreachOrchestrator

        orchestrator: TwitterOutreachOrchestrator = ctx.get_artifact(  # type: ignore[assignment]
            "outreach_orchestrator"
        )

        total = min(
            len(prospects),
            customer_profile.ideal_customer.max_prospects_to_enrich,
        )
        ctx.console.print(f"[bold cyan]Enriching up to {total} profiles...[/bold cyan]")

        profiles = await orchestrator.enrich(prospects)

        dm_open = [p for p in profiles if p.dm_possible]
        dm_closed = [p for p in profiles if not p.dm_possible]

        ctx.console.print(
            f"[green]Enrichment done: {len(profiles)} profiles passed bio filter[/green]"
        )
        ctx.console.print(
            f"  [green]{len(dm_open)} accept DMs[/green]  |  "
            f"[yellow]{len(dm_closed)} DMs closed (dropped)[/yellow]"
        )

        if dm_open:
            ctx.console.print("[dim]Proceeding with DM-open profiles:[/dim]")
            for p in dm_open:
                ctx.console.print(f"  [cyan]@{p.handle}[/cyan] — {p.bio[:80]}")

        ctx.set_artifact("user_profiles", dm_open)
