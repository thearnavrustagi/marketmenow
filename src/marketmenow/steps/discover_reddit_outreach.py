from __future__ import annotations

from pathlib import Path

import yaml

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.outreach.history import OutreachHistory
from marketmenow.outreach.models import ProductInfo


class DiscoverRedditOutreachStep:
    """Discover new Reddit posts for cold outreach using project config."""

    @property
    def name(self) -> str:
        return "discover-reddit-outreach"

    @property
    def description(self) -> str:
        return "Discover Reddit posts for cold outreach"

    async def execute(self, ctx: WorkflowContext) -> None:
        from adapters.reddit.client import RedditClient
        from adapters.reddit.discovery import PostDiscoverer
        from adapters.reddit.settings import RedditSettings

        if not ctx.project:
            raise WorkflowError(
                "No project set. Use --project <slug> or `mmn project use <slug>` first."
            )

        brand = ctx.project.brand
        target = ctx.project.target_customer

        product = ProductInfo(
            name=brand.name,
            url=brand.url,
            tagline=brand.tagline,
            value_prop=brand.value_prop,
        )
        features = list(brand.features)
        target_description = target.description if target else ""
        pain_points = list(target.pain_points) if target else []

        targets_path = ctx.resolve_project_path("targets", "reddit.yaml")
        targets_data = yaml.safe_load(Path(targets_path).read_text(encoding="utf-8"))
        subreddits: list[str] = targets_data.get("subreddits", [])
        search_queries: list[str] = targets_data.get("search_queries", [])

        if not subreddits:
            raise WorkflowError(
                f"No subreddits found in {targets_path}. Add subreddits to targets/reddit.yaml."
            )

        max_per_subreddit = int(ctx.get_param("max-per-sub", 5) or 5)
        max_per_query = int(ctx.get_param("max-per-query", 3) or 3)

        config = {
            "product": product,
            "features": features,
            "target_customer_description": target_description,
            "pain_points": pain_points,
            "messaging_tone": "",
            "max_comment_length": 1500,
            "min_delay_seconds": 180,
            "max_delay_seconds": 420,
        }
        ctx.set_artifact("outreach_config", config)

        ctx.console.print(f"[dim]Project: {ctx.project.slug}[/dim]")
        ctx.console.print(f"[dim]Product: {brand.name} — {brand.tagline}[/dim]")
        ctx.console.print(
            f"[dim]Subreddits: {len(subreddits)} | Queries: {len(search_queries)}[/dim]"
        )
        ctx.console.print(f"[dim]Features: {len(features)} loaded[/dim]")

        history_path = None
        from marketmenow.core.project_manager import ProjectManager

        pm = ProjectManager()
        project_dir = pm.project_dir(ctx.project.slug)
        history_path = project_dir / ".outreach_history.json"

        history = OutreachHistory(path=history_path)
        ctx.set_artifact("outreach_history", history)

        contacted = history.contacted_handles("reddit")
        if contacted:
            ctx.console.print(f"[dim]Already contacted: {len(contacted)} posts (will skip)[/dim]")

        settings = RedditSettings()
        client = RedditClient(
            session_cookie=settings.reddit_session,
            username=settings.reddit_username,
            user_agent=settings.reddit_user_agent,
        )
        ctx.set_artifact("reddit_client", client)

        if not await client.is_logged_in():
            raise WorkflowError("Not logged in to Reddit. Check REDDIT_SESSION cookie in .env.")
        ctx.console.print("[green]Reddit session active.[/green]")

        discoverer = PostDiscoverer(
            client=client,
            comment_history_path=Path(settings.comment_history_path),
            own_username=settings.reddit_username,
        )
        ctx.set_artifact("post_discoverer", discoverer)

        ctx.console.print("[bold cyan]Discovering new posts...[/bold cyan]")

        new_posts = await discoverer.discover_new_posts(
            subreddits=subreddits,
            max_per_sub=max_per_subreddit,
        )

        search_posts = []
        if search_queries:
            search_posts = await discoverer.discover_search_posts(
                subreddits=subreddits,
                queries=search_queries,
                max_per_query=max_per_query,
                sort="new",
                min_score=0,
            )

        all_posts = discoverer._dedupe(new_posts + search_posts)

        filtered = [p for p in all_posts if not history.is_contacted("reddit", p.post_id)]

        if not filtered:
            raise WorkflowError("No new posts discovered. Try different subreddits or queries.")

        ctx.console.print(
            f"[green]Discovered {len(filtered)} posts "
            f"({len(new_posts)} from new, {len(search_posts)} from search)[/green]"
        )
        ctx.set_artifact("discovered_posts", filtered)
