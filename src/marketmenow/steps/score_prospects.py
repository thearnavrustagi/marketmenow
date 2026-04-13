from __future__ import annotations

from rich.table import Table

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.outreach.models import CustomerProfile, ScoredProspect, UserProfile


class ScoreProspectsStep:
    """Score each enriched user profile for product relevance. Platform-agnostic."""

    @property
    def name(self) -> str:
        return "score-prospects"

    @property
    def description(self) -> str:
        return "Evaluate prospects for product relevance"

    async def execute(self, ctx: WorkflowContext) -> None:
        from marketmenow.outreach.scorer import ProspectScorer

        profiles: list[UserProfile] = ctx.get_artifact("user_profiles")  # type: ignore[assignment]
        customer_profile: CustomerProfile = ctx.get_artifact("customer_profile")  # type: ignore[assignment]

        if not profiles:
            raise WorkflowError("No enriched profiles to score.")

        min_score = customer_profile.ideal_customer.min_score

        ctx.console.print(
            f"[bold cyan]Scoring {len(profiles)} profiles for relevance "
            f"(min_score={min_score})...[/bold cyan]"
        )

        scorer = ProspectScorer()

        scored: list[ScoredProspect] = []
        for i, profile in enumerate(profiles, start=1):
            ctx.console.print(f"  [dim]Scoring {i}/{len(profiles)}:[/dim] @{profile.handle}")
            try:
                result = await scorer.score(profile, customer_profile)
                scored.append(result)
                if result.disqualify_reason:
                    ctx.console.print(f"    [red]Disqualified: {result.disqualify_reason}[/red]")
                else:
                    ctx.console.print(
                        f"    [green]Score: {result.total_score}/{result.max_score}[/green] — {result.dm_angle[:70]}"
                    )
            except Exception as exc:
                ctx.console.print(f"    [yellow]Error: {exc}[/yellow]")

        qualified = [
            s for s in scored if s.disqualify_reason is None and s.total_score >= min_score
        ]

        min_score_override = int(ctx.get_param("min-score", 0) or 0)
        if min_score_override > 0:
            qualified = [s for s in qualified if s.total_score >= min_score_override]

        qualified.sort(
            key=lambda s: (s.total_score, s.user_profile.discovery_count),
            reverse=True,
        )

        max_messages = int(ctx.get_param("max-messages", 10) or 10)
        qualified = qualified[:max_messages]

        disqualified = len(scored) - len(qualified)
        ctx.console.print(
            f"\n[bold]Scoring summary: {len(qualified)} qualified, {disqualified} dropped[/bold]"
        )

        self._print_table(ctx, qualified)
        ctx.set_artifact("scored_prospects", qualified)

    @staticmethod
    def _print_table(ctx: WorkflowContext, prospects: list[ScoredProspect]) -> None:
        table = Table(title="Qualified Prospects")
        table.add_column("Handle", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("DM Angle", max_width=60)
        for p in prospects:
            table.add_row(
                f"@{p.user_profile.handle}",
                f"{p.total_score}/{p.max_score}",
                p.dm_angle[:60],
            )
        ctx.console.print(table)
