from __future__ import annotations

from rich.table import Table

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.outreach.post_scorer import ScoredPost


class ScorePostRelevanceStep:
    """Score discovered posts for product relevance using a general LLM prompt."""

    @property
    def name(self) -> str:
        return "score-post-relevance"

    @property
    def description(self) -> str:
        return "Score posts for product relevance"

    async def execute(self, ctx: WorkflowContext) -> None:
        from adapters.reddit.discovery import DiscoveredPost
        from marketmenow.outreach.post_scorer import PostRelevanceScorer

        posts: list[DiscoveredPost] = ctx.get_artifact("discovered_posts")  # type: ignore[assignment]
        config: dict[str, object] = ctx.get_artifact("outreach_config")  # type: ignore[assignment]

        if not posts:
            raise WorkflowError("No discovered posts to score.")

        product = config["product"]  # type: ignore[index]
        target_description = str(config.get("target_customer_description", ""))
        pain_points: list[str] = config.get("pain_points", [])  # type: ignore[assignment]

        min_score = int(ctx.get_param("min-score", 0) or 0) or 7

        scorer = PostRelevanceScorer()

        ctx.console.print(
            f"[bold cyan]Scoring {len(posts)} posts for relevance (min_score={min_score})...[/bold cyan]"
        )

        scored: list[ScoredPost] = []
        for i, post in enumerate(posts, start=1):
            ctx.console.print(
                f"  [dim]Scoring {i}/{len(posts)}:[/dim] r/{post.subreddit} — {post.post_title[:50]}"
            )
            try:
                result = await scorer.score(
                    post_title=post.post_title,
                    post_text=post.post_text,
                    post_url=post.post_url,
                    post_id=post.post_id,
                    post_fullname=post.post_fullname,
                    author=post.author,
                    subreddit=post.subreddit,
                    product=product,  # type: ignore[arg-type]
                    target_customer_description=target_description,
                    pain_points=pain_points,
                )
                scored.append(result)
                if result.disqualify_reason:
                    ctx.console.print(f"    [red]Disqualified: {result.disqualify_reason}[/red]")
                else:
                    ctx.console.print(
                        f"    [green]Score: {result.relevance_score}/10[/green]"
                        f" — {result.outreach_angle[:60]}"
                    )
            except Exception as exc:
                ctx.console.print(f"    [yellow]Error: {exc}[/yellow]")

        qualified = [
            s for s in scored
            if s.disqualify_reason is None and s.relevance_score >= min_score
        ]

        qualified.sort(key=lambda s: s.relevance_score, reverse=True)

        max_comments = int(ctx.get_param("max-comments", 10) or 10)
        qualified = qualified[:max_comments]

        dropped = len(scored) - len(qualified)
        ctx.console.print(
            f"\n[bold]Scoring summary: {len(qualified)} qualified, {dropped} dropped[/bold]"
        )

        self._print_table(ctx, qualified)
        ctx.set_artifact("scored_posts", qualified)

    @staticmethod
    def _print_table(ctx: WorkflowContext, posts: list[ScoredPost]) -> None:
        table = Table(title="Qualified Posts")
        table.add_column("Subreddit", style="cyan")
        table.add_column("Author", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Title", max_width=40)
        table.add_column("Outreach Angle", max_width=40)
        for p in posts:
            table.add_row(
                f"r/{p.subreddit}",
                f"u/{p.author}",
                f"{p.relevance_score}/10",
                p.post_title[:40],
                p.outreach_angle[:40],
            )
        ctx.console.print(table)
