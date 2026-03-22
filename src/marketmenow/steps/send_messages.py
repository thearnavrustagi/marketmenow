from __future__ import annotations

from rich.table import Table

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.outreach.models import OutreachMessage, OutreachSendResult


class SendMessagesStep:
    """Send the generated outreach messages via the platform. Platform-specific."""

    def __init__(self, platform: str = "twitter") -> None:
        self._platform = platform

    @property
    def name(self) -> str:
        return "send-messages"

    @property
    def description(self) -> str:
        return f"Send outreach messages on {self._platform}"

    async def execute(self, ctx: WorkflowContext) -> None:
        dry_run = ctx.artifacts.get("dry_run", False)
        if dry_run:
            ctx.console.print("[dim]Skipping send (dry run).[/dim]")
            return

        messages: list[OutreachMessage] = ctx.get_artifact("outreach_messages")  # type: ignore[assignment]
        if not messages:
            ctx.console.print("[yellow]No messages to send.[/yellow]")
            return

        if self._platform == "twitter":
            await self._send_twitter(ctx, messages)
        else:
            raise WorkflowError(f"Outreach sending not implemented for {self._platform}")

    async def _send_twitter(
        self,
        ctx: WorkflowContext,
        messages: list[OutreachMessage],
    ) -> None:
        from adapters.twitter.outreach.orchestrator import TwitterOutreachOrchestrator

        orchestrator: TwitterOutreachOrchestrator = ctx.get_artifact(  # type: ignore[assignment]
            "outreach_orchestrator"
        )

        ctx.console.print(f"[bold]Sending {len(messages)} DMs on Twitter...[/bold]")
        results = await orchestrator.send_batch(messages)

        self._print_summary(ctx, results)
        ctx.set_artifact("send_results", results)

    @staticmethod
    def _print_summary(
        ctx: WorkflowContext,
        results: list[OutreachSendResult],
    ) -> None:
        sent = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)

        table = Table(title="Send Results")
        table.add_column("Handle", style="cyan")
        table.add_column("Status")
        table.add_column("Error", max_width=50)
        for r in results:
            status = "[green]Sent[/green]" if r.success else "[red]Failed[/red]"
            table.add_row(
                f"@{r.recipient_handle}",
                status,
                r.error_message or "",
            )
        ctx.console.print(table)
        ctx.console.print(f"[bold]Total: {sent} sent, {failed} failed[/bold]")
