from __future__ import annotations

from rich.table import Table

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.outreach.models import CustomerProfile, OutreachMessage, ScoredProspect


class GenerateMessagesStep:
    """Generate personalised outreach messages for scored prospects. Platform-agnostic."""

    @property
    def name(self) -> str:
        return "generate-messages"

    @property
    def description(self) -> str:
        return "Generate personalised outreach messages"

    async def execute(self, ctx: WorkflowContext) -> None:
        from marketmenow.outreach.message_generator import OutreachMessageGenerator

        prospects: list[ScoredProspect] = ctx.get_artifact("scored_prospects")  # type: ignore[assignment]
        customer_profile: CustomerProfile = ctx.get_artifact("customer_profile")  # type: ignore[assignment]

        if not prospects:
            raise WorkflowError("No scored prospects to generate messages for.")

        generator = OutreachMessageGenerator(
            vertex_project=self._get_vertex_project(),
            vertex_location=self._get_vertex_location(),
        )

        messages: list[OutreachMessage] = []
        for i, prospect in enumerate(prospects, start=1):
            handle = prospect.user_profile.handle
            ctx.console.print(f"  Generating message {i}/{len(prospects)}: @{handle}")
            try:
                msg = await generator.generate(prospect, customer_profile)
                messages.append(msg)
            except Exception as exc:
                ctx.console.print(
                    f"  [yellow]Failed to generate message for @{handle}: {exc}[/yellow]"
                )

        self._print_drafts(ctx, messages)

        dry_run = ctx.get_param("dry-run", False)
        if dry_run:
            ctx.console.print("[yellow]Dry run — messages not sent.[/yellow]")
            ctx.set_artifact("dry_run", True)

        ctx.set_artifact("outreach_messages", messages)

    @staticmethod
    def _print_drafts(ctx: WorkflowContext, messages: list[OutreachMessage]) -> None:
        table = Table(title="Generated Messages")
        table.add_column("Handle", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Message", max_width=80)
        for m in messages:
            table.add_row(
                f"@{m.recipient_handle}",
                str(m.prospect_score),
                m.message_text[:80],
            )
        ctx.console.print(table)

    @staticmethod
    def _get_vertex_project() -> str:
        import os

        return os.environ.get("VERTEX_AI_PROJECT", "")

    @staticmethod
    def _get_vertex_location() -> str:
        import os

        return os.environ.get("VERTEX_AI_LOCATION", "us-central1")
