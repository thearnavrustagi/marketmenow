from __future__ import annotations

import asyncio
import logging
import random

from rich.table import Table

from marketmenow.core.workflow import WorkflowContext
from marketmenow.outreach.outreach_comment_generator import OutreachComment

logger = logging.getLogger(__name__)


class PostOutreachCommentsStep:
    """Post outreach comments to Reddit with rate limiting and history tracking."""

    @property
    def name(self) -> str:
        return "post-outreach-comments"

    @property
    def description(self) -> str:
        return "Post outreach comments to Reddit"

    async def execute(self, ctx: WorkflowContext) -> None:
        from adapters.reddit.client import RedditClient
        from adapters.reddit.discovery import PostDiscoverer
        from marketmenow.outreach.history import OutreachHistory

        dry_run = ctx.artifacts.get("dry_run", False)
        if dry_run:
            ctx.console.print("[dim]Skipping posting (dry run).[/dim]")
            return

        comments: list[OutreachComment] = ctx.get_artifact("outreach_comments")  # type: ignore[assignment]
        if not comments:
            ctx.console.print("[yellow]No comments to post.[/yellow]")
            return

        client: RedditClient = ctx.get_artifact("reddit_client")  # type: ignore[assignment]
        history: OutreachHistory = ctx.get_artifact("outreach_history")  # type: ignore[assignment]
        discoverer: PostDiscoverer = ctx.get_artifact("post_discoverer")  # type: ignore[assignment]
        config: dict[str, object] = ctx.get_artifact("outreach_config")  # type: ignore[assignment]

        min_delay = int(config.get("min_delay_seconds", 180))  # type: ignore[arg-type]
        max_delay = int(config.get("max_delay_seconds", 420))  # type: ignore[arg-type]

        ctx.console.print(
            f"[bold cyan]Posting {len(comments)} outreach comments...[/bold cyan]"
        )

        results: list[dict[str, object]] = []
        for i, comment in enumerate(comments, start=1):
            ctx.console.print(
                f"  [dim]{i}/{len(comments)}:[/dim] Commenting on u/{comment.recipient_handle}'s post"
            )
            try:
                resp = await client.post_comment(
                    parent_fullname=comment.post_fullname,
                    text=comment.comment_text,
                )

                success = bool(resp)
                results.append({
                    "handle": comment.recipient_handle,
                    "post_id": comment.post_id,
                    "success": success,
                    "error": None,
                })

                history.record(
                    "reddit",
                    comment.post_id,
                    message_preview=comment.comment_text[:100],
                    score=comment.prospect_score,
                    success=success,
                )
                discoverer.mark_commented(comment.post_id)

                ctx.console.print("    [green]Posted successfully[/green]")

                if _looks_like_rate_limit(resp):
                    ctx.console.print(
                        "[red]Rate limit detected — halting outreach.[/red]"
                    )
                    break

            except Exception as exc:
                error_msg = str(exc)
                results.append({
                    "handle": comment.recipient_handle,
                    "post_id": comment.post_id,
                    "success": False,
                    "error": error_msg,
                })
                ctx.console.print(f"    [red]Failed: {error_msg}[/red]")

                if _looks_like_rate_limit(error_msg):
                    ctx.console.print(
                        "[red]Rate limit detected — halting outreach.[/red]"
                    )
                    break

            if i < len(comments):
                delay = random.randint(min_delay, max_delay)
                ctx.console.print(f"    [dim]Waiting {delay}s before next comment...[/dim]")
                await asyncio.sleep(delay)

        self._print_summary(ctx, results)
        ctx.set_artifact("outreach_results", results)

    @staticmethod
    def _print_summary(
        ctx: WorkflowContext,
        results: list[dict[str, object]],
    ) -> None:
        sent = sum(1 for r in results if r["success"])
        failed = sum(1 for r in results if not r["success"])

        table = Table(title="Outreach Results")
        table.add_column("Author", style="cyan")
        table.add_column("Status")
        table.add_column("Error", max_width=50)
        for r in results:
            status = "[green]Posted[/green]" if r["success"] else "[red]Failed[/red]"
            table.add_row(
                f"u/{r['handle']}",
                status,
                str(r.get("error") or ""),
            )
        ctx.console.print(table)
        ctx.console.print(f"[bold]Total: {sent} posted, {failed} failed[/bold]")


def _looks_like_rate_limit(response: object) -> bool:
    """Check if a response or error message indicates rate limiting."""
    text = str(response).lower()
    signals = ("rate limit", "ratelimit", "too many requests", "try again later")
    return any(s in text for s in signals)
