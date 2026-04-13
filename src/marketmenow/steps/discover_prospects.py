from __future__ import annotations

from pathlib import Path

import yaml

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.outreach.history import OutreachHistory
from marketmenow.outreach.models import (
    CustomerProfile,
    DiscoveryVectorConfig,
    ICPConfig,
    MessagingConfig,
    ProductInfo,
    RubricCriterion,
)


class DiscoverProspectsStep:
    """Load outreach config from project and discover prospect posts via platform-specific vectors."""

    def __init__(self, platform: str = "twitter") -> None:
        self._platform = platform

    @property
    def name(self) -> str:
        return "discover-prospects"

    @property
    def description(self) -> str:
        return f"Discover prospects on {self._platform} via project targets"

    async def execute(self, ctx: WorkflowContext) -> None:
        if not ctx.project:
            raise WorkflowError(
                "No project set. Use --project <slug> or `mmn project use <slug>` first."
            )

        customer_profile = self._build_customer_profile(ctx)
        ctx.set_artifact("customer_profile", customer_profile)

        ctx.console.print(f"[dim]Project: {ctx.project.slug}[/dim]")
        ctx.console.print(
            f"[dim]Product: {customer_profile.product.name} — {customer_profile.product.tagline}[/dim]"
        )
        ctx.console.print(
            f"[dim]Vectors: {len(customer_profile.discovery_vectors)} configured[/dim]"
        )

        history_path = None
        from marketmenow.core.project_manager import ProjectManager

        pm = ProjectManager()
        project_dir = pm.project_dir(ctx.project.slug)
        history_path = project_dir / ".outreach_history.json"

        history = OutreachHistory(path=history_path)
        ctx.set_artifact("outreach_history", history)

        contacted = history.contacted_handles(self._platform)
        if contacted:
            ctx.console.print(f"[dim]Already contacted: {len(contacted)} handles (will skip)[/dim]")

        if self._platform == "twitter":
            await self._discover_twitter(ctx, customer_profile, history)
        else:
            raise WorkflowError(f"Outreach discovery not implemented for {self._platform}")

    def _build_customer_profile(self, ctx: WorkflowContext) -> CustomerProfile:
        """Build CustomerProfile from project config + targets file."""
        brand = ctx.project.brand  # type: ignore[union-attr]
        target = ctx.project.target_customer  # type: ignore[union-attr]

        product = ProductInfo(
            name=brand.name,
            url=brand.url,
            tagline=brand.tagline,
            value_prop=brand.value_prop,
        )

        targets_path = ctx.resolve_project_path("targets", f"{self._platform}.yaml")
        targets_data = yaml.safe_load(Path(targets_path).read_text(encoding="utf-8"))

        discovery_vectors = self._build_discovery_vectors(targets_data)

        bio_blocklist: list[str] = targets_data.get("bio_blocklist", [])
        bio_require_any: list[str] = targets_data.get("bio_require_any", [])

        icp = ICPConfig(
            description=target.description if target else "",
            rubric=[
                RubricCriterion(
                    name="relevance",
                    description="General relevance to the product's target customer",
                    max_points=10,
                ),
            ],
            min_score=7,
            max_prospects_to_enrich=50,
            bio_blocklist=bio_blocklist,
            bio_require_any=bio_require_any,
        )

        messaging_overrides = targets_data.get("messaging", {})
        messaging = MessagingConfig(
            max_messages=int(messaging_overrides.get("max_messages", 10)),
            min_delay_seconds=int(messaging_overrides.get("min_delay_seconds", 120)),
            max_delay_seconds=int(messaging_overrides.get("max_delay_seconds", 300)),
            tone=str(messaging_overrides.get("tone", "")),
            reference_post=bool(messaging_overrides.get("reference_post", True)),
            pause_every_n=int(messaging_overrides.get("pause_every_n", 5)),
            long_pause_seconds=int(messaging_overrides.get("long_pause_seconds", 600)),
            max_message_length=int(messaging_overrides.get("max_message_length", 280)),
        )

        return CustomerProfile(
            product=product,
            platform=self._platform,
            ideal_customer=icp,
            discovery_vectors=discovery_vectors,
            messaging=messaging,
        )

    def _build_discovery_vectors(
        self, targets_data: dict[str, object]
    ) -> list[DiscoveryVectorConfig]:
        """Derive discovery vectors from the targets file structure."""
        vectors: list[DiscoveryVectorConfig] = []

        search_queries: list[str] = targets_data.get("search_queries", [])  # type: ignore[assignment]
        if search_queries:
            vectors.append(
                DiscoveryVectorConfig(
                    vector_type="pain_search",
                    entries=search_queries,
                    max_per_entry=5,
                )
            )

        influencers: list[str] = targets_data.get("influencers", [])  # type: ignore[assignment]
        if influencers:
            vectors.append(
                DiscoveryVectorConfig(
                    vector_type="conversation_mining",
                    entries=influencers[:10],
                    max_per_entry=5,
                )
            )

        hashtags: list[str] = targets_data.get("hashtags", [])  # type: ignore[assignment]
        if hashtags:
            vectors.append(
                DiscoveryVectorConfig(
                    vector_type="hashtag_scan",
                    entries=hashtags,
                    max_per_entry=5,
                )
            )

        return vectors

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
        headless = (
            headless_raw
            if isinstance(headless_raw, bool)
            else str(headless_raw).lower() in ("true", "1", "yes")
        )
        settings = settings.model_copy(update={"headless": headless})

        orchestrator = TwitterOutreachOrchestrator(settings, profile, history)
        ctx.set_artifact("outreach_orchestrator", orchestrator)

        await orchestrator.launch()
        ctx.console.print("[dim]Browser launched, checking login...[/dim]")
        if not await orchestrator.ensure_logged_in():
            raise WorkflowError("Not logged in to Twitter. Run `mmn twitter login` first.")
        ctx.console.print("[green]Logged in to Twitter.[/green]")

        ctx.console.print("[bold cyan]Running discovery vectors...[/bold cyan]")
        prospects = await orchestrator.discover()

        if not prospects:
            raise WorkflowError("No prospects discovered. Check your search queries.")

        total_posts = sum(len(v) for v in prospects.values())
        ctx.console.print(
            f"[green]Discovery complete: {total_posts} posts from {len(prospects)} unique handles[/green]"
        )
        ctx.set_artifact("discovered_prospects", prospects)
