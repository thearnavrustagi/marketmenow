from __future__ import annotations

from rich.table import Table

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.outreach.outreach_comment_generator import OutreachComment
from marketmenow.outreach.post_scorer import ScoredPost


class GenerateOutreachCommentsStep:
    """Generate personalised outreach comments for scored Reddit posts."""

    @property
    def name(self) -> str:
        return "generate-outreach-comments"

    @property
    def description(self) -> str:
        return "Generate outreach comments with product features"

    async def execute(self, ctx: WorkflowContext) -> None:
        from marketmenow.outreach.outreach_comment_generator import (
            OutreachCommentGenerator,
        )

        scored: list[ScoredPost] = ctx.get_artifact("scored_posts")  # type: ignore[assignment]
        config: dict[str, object] = ctx.get_artifact("outreach_config")  # type: ignore[assignment]

        if not scored:
            raise WorkflowError("No scored posts to generate comments for.")

        product = config["product"]  # type: ignore[index]
        features: list[str] = config.get("features", [])  # type: ignore[assignment]
        tone = str(config.get("messaging_tone", ""))
        max_length = int(config.get("max_comment_length", 1500))  # type: ignore[arg-type]

        generator = OutreachCommentGenerator()

        comments: list[OutreachComment] = []
        for i, post in enumerate(scored, start=1):
            ctx.console.print(
                f"  Generating comment {i}/{len(scored)}: u/{post.author} in r/{post.subreddit}"
            )
            try:
                comment = await generator.generate(
                    scored_post=post,
                    product=product,  # type: ignore[arg-type]
                    features=features,
                    messaging_tone=tone,
                    max_length=max_length,
                )
                comments.append(comment)
            except Exception as exc:
                ctx.console.print(
                    f"  [yellow]Failed for u/{post.author}: {exc}[/yellow]"
                )

        self._print_drafts(ctx, comments)

        dry_run = ctx.get_param("dry-run", False)
        if dry_run:
            ctx.console.print("[yellow]Dry run — comments not posted.[/yellow]")
            ctx.set_artifact("dry_run", True)

        ctx.set_artifact("outreach_comments", comments)

    @staticmethod
    def _print_drafts(ctx: WorkflowContext, comments: list[OutreachComment]) -> None:
        table = Table(title="Generated Outreach Comments")
        table.add_column("Author", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Comment Preview", max_width=80)
        for c in comments:
            table.add_row(
                f"u/{c.recipient_handle}",
                str(c.prospect_score),
                c.comment_text[:80],
            )
        ctx.console.print(table)
