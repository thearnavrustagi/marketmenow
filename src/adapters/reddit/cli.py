from __future__ import annotations

import asyncio
import csv
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .discovery import DiscoveredPost
from .orchestrator import (
    EngagementOrchestrator,
    EngagementStats,
    GeneratedComment,
)
from .settings import RedditSettings

app = typer.Typer(
    name="mmn-reddit",
    help="MarketMeNow Reddit engagement CLI",
    no_args_is_help=True,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

console = Console()

_NOISY_LOGGERS = (
    "adapters.reddit",
    "httpx",
    "httpcore",
    "google_genai",
    "google.auth",
    "google.auth.transport",
    "urllib3",
)


def _quiet_loggers() -> dict[str, int]:
    prev: dict[str, int] = {}
    for name in _NOISY_LOGGERS:
        lg = logging.getLogger(name)
        prev[name] = lg.level
        lg.setLevel(logging.WARNING)
    return prev


def _restore_loggers(prev: dict[str, int]) -> None:
    for name, level in prev.items():
        logging.getLogger(name).setLevel(level)


# -- Rich progress UI -------------------------------------------------


class _CommentEntry:
    __slots__ = ("comment_text", "idx", "status", "subreddit", "total")

    def __init__(self, idx: int, total: int, subreddit: str) -> None:
        self.idx = idx
        self.total = total
        self.subreddit = subreddit
        self.status: str = "generating"
        self.comment_text: str = ""


class _RichProgress:
    """Live-updating terminal UI for the Reddit engagement loop."""

    def __init__(self, live: Live) -> None:
        self._live = live
        self._total_subs = 0
        self._total_queries = 0
        self._subs_done: list[tuple[str, int]] = []
        self._total_posts = 0
        self._candidates = 0
        self._comments: list[_CommentEntry] = []
        self._phase = "discovery"
        self._status_text = ""
        self._start = monotonic()

    def _elapsed(self) -> str:
        secs = int(monotonic() - self._start)
        m, s = divmod(secs, 60)
        return f"{m}:{s:02d}"

    def _render(self) -> Table:
        grid = Table.grid(padding=(0, 1))
        grid.add_column()

        if self._phase == "discovery":
            grid.add_row(self._render_discovery())
        else:
            grid.add_row(self._render_discovery_summary())
            grid.add_row(Text())
            grid.add_row(self._render_comments())

        if self._status_text:
            grid.add_row(Text())
            grid.add_row(Text(f"  {self._status_text}", style="dim"))

        return grid

    def _render_discovery(self) -> Panel:
        tbl = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
        tbl.add_column("icon", width=3)
        tbl.add_column("source", min_width=20)
        tbl.add_column("count", justify="right", width=12)

        for sub, count in self._subs_done:
            style = "green" if count > 0 else "dim"
            tbl.add_row("  ", f"r/{sub}", f"[{style}]{count} posts[/{style}]")

        remaining = self._total_subs - len(self._subs_done)
        if remaining > 0:
            tbl.add_row(
                "[bold cyan]>[/bold cyan]",
                f"[dim]{remaining} more sub{'s' if remaining != 1 else ''}...[/dim]",
                "",
            )

        total_found = sum(c for _, c in self._subs_done)
        progress_str = f"Subreddits {len(self._subs_done)}/{self._total_subs}  Posts {total_found}"

        return Panel(
            tbl,
            title=f"[bold]Discovering[/bold]  [dim]{self._elapsed()}[/dim]",
            subtitle=f"[dim]{progress_str}[/dim]",
            border_style="cyan",
        )

    def _render_discovery_summary(self) -> Panel:
        total_found = sum(c for _, c in self._subs_done)
        txt = Text()
        txt.append(f"  {total_found}", style="bold green")
        txt.append(" posts from ")
        txt.append(f"{len(self._subs_done)}", style="bold")
        txt.append(" subreddits")
        if self._candidates > 0 and self._candidates != total_found:
            txt.append(
                f"  (generating {self._candidates} comments)",
                style="dim",
            )
        return Panel(txt, title="[bold]Discovery[/bold]", border_style="green")

    def _render_comments(self) -> Panel:
        tbl = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
        tbl.add_column("status", width=3)
        tbl.add_column("info", ratio=1)

        for entry in self._comments:
            counter = f"[dim]{entry.idx}/{entry.total}[/dim]"
            if entry.status == "generating":
                tbl.add_row(
                    "[bold yellow]~[/bold yellow]",
                    f"{counter}  r/{entry.subreddit}  [yellow]generating...[/yellow]",
                )
            elif entry.status == "generated":
                preview = entry.comment_text[:120].replace("\n", " ")
                tbl.add_row(
                    "[bold green]✓[/bold green]",
                    Text.from_markup(
                        f"{counter}  r/{entry.subreddit}\n       [dim]{preview}[/dim]"
                    ),
                )
            elif entry.status == "posted":
                preview = entry.comment_text[:120].replace("\n", " ")
                tbl.add_row(
                    "[bold green]✓[/bold green]",
                    Text.from_markup(
                        f"{counter}  r/{entry.subreddit}  [green]posted[/green]\n"
                        f"       [dim]{preview}[/dim]"
                    ),
                )
            elif entry.status == "post_failed":
                tbl.add_row(
                    "[bold red]✗[/bold red]",
                    f"{counter}  r/{entry.subreddit}  [red]post failed[/red]",
                )
            elif entry.status == "failed":
                tbl.add_row(
                    "[bold red]✗[/bold red]",
                    f"{counter}  r/{entry.subreddit}  [red]generate failed[/red]",
                )

        title_label = "Generating" if self._phase in ("generating", "commenting") else "Done"
        border = "yellow" if self._phase in ("generating", "commenting") else "green"

        return Panel(
            tbl,
            title=f"[bold]{title_label}[/bold]  [dim]{self._elapsed()}[/dim]",
            border_style=border,
        )

    def _refresh(self) -> None:
        self._live.update(self._render())

    def _find_entry(self, current: int, subreddit: str) -> _CommentEntry | None:
        for e in reversed(self._comments):
            if e.idx == current and e.subreddit == subreddit:
                return e
        return None

    # -- ProgressCallback interface --

    def on_discovery_start(self, total_subs: int, total_queries: int) -> None:
        self._total_subs = total_subs
        self._total_queries = total_queries
        self._phase = "discovery"
        self._refresh()

    def on_sub_done(self, subreddit: str, posts_found: int) -> None:
        self._subs_done.append((subreddit, posts_found))
        self._refresh()

    def on_discovery_end(self, total_posts: int, candidates: int) -> None:
        self._total_posts = total_posts
        self._candidates = candidates
        self._phase = "generating" if candidates > 0 else "done"
        self._status_text = ""
        self._refresh()

    def on_generating(self, current: int, total: int, subreddit: str) -> None:
        self._comments.append(_CommentEntry(current, total, subreddit))
        self._status_text = ""
        self._refresh()

    def on_generated(
        self,
        current: int,
        total: int,
        subreddit: str,
        comment_text: str,
    ) -> None:
        entry = self._find_entry(current, subreddit)
        if entry:
            entry.status = "generated"
            entry.comment_text = comment_text
        self._refresh()

    def on_generate_failed(
        self,
        current: int,
        total: int,
        subreddit: str,
    ) -> None:
        entry = self._find_entry(current, subreddit)
        if entry:
            entry.status = "failed"
        self._refresh()

    def on_comment_posted(
        self,
        current: int,
        total: int,
        subreddit: str,
        success: bool,
    ) -> None:
        entry = self._find_entry(current, subreddit)
        if entry:
            entry.status = "posted" if success else "post_failed"
        self._refresh()

    def on_comment_wait(self, seconds: int) -> None:
        self._status_text = f"Waiting {seconds}s before next comment..."
        self._refresh()

    def on_complete(self, stats: EngagementStats) -> None:
        self._phase = "done"
        self._status_text = ""
        self._refresh()


# -- Helpers -----------------------------------------------------------


def _settings() -> RedditSettings:
    return RedditSettings()


def _ensure_vertex_credentials(settings: RedditSettings) -> None:
    creds = settings.google_application_credentials
    if creds and creds.exists():
        os.environ.setdefault(
            "GOOGLE_APPLICATION_CREDENTIALS",
            str(creds.resolve()),
        )


def _print_summary(stats: EngagementStats) -> None:
    console.print()
    tbl = Table(title="Summary", show_header=False, border_style="bold")
    tbl.add_column("metric", style="bold")
    tbl.add_column("value", justify="right")
    tbl.add_row("Discovered", str(stats.total_discovered))
    tbl.add_row("Attempted", str(stats.total_attempted))
    tbl.add_row(
        "Succeeded",
        f"[green]{stats.total_succeeded}[/green]" if stats.total_succeeded else "0",
    )
    tbl.add_row(
        "Failed",
        f"[red]{stats.total_failed}[/red]" if stats.total_failed else "0",
    )
    for source, count in stats.posts_by_source.items():
        tbl.add_row(f"  {source}", str(count))
    console.print(tbl)


def _write_csv(comments: list[GeneratedComment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "subreddit",
                "post_url",
                "post_id",
                "post_fullname",
                "post_title",
                "post_text",
                "author",
                "score",
                "comment_text",
            ]
        )
        for c in comments:
            writer.writerow(
                [
                    c.subreddit,
                    c.post_url,
                    c.post_id,
                    c.post_fullname,
                    c.post_title,
                    c.post_text,
                    c.author,
                    c.score,
                    c.comment_text,
                ]
            )


def _read_csv(path: Path) -> list[GeneratedComment]:
    rows: list[GeneratedComment] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                GeneratedComment(
                    subreddit=row["subreddit"],
                    post_url=row["post_url"],
                    post_id=row["post_id"],
                    post_fullname=row["post_fullname"],
                    post_title=row.get("post_title", ""),
                    post_text=row.get("post_text", ""),
                    author=row.get("author", ""),
                    score=int(row.get("score", 0)),
                    comment_text=row["comment_text"],
                )
            )
    return rows


# -- Commands ----------------------------------------------------------


@app.command()
def engage(
    output: Path = typer.Option(
        None,
        "-o",
        "--output",
        help="CSV output path (default: reddit_comments_<timestamp>.csv)",
    ),
    max_comments: int = typer.Option(
        0,
        "--max-comments",
        help="Override max comments per day (0 = use settings default)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show raw log output instead of rich UI",
    ),
) -> None:
    """Discover posts and generate comments, saving them to a CSV.

    Does NOT post anything. Review the CSV, edit comments if you want,
    then run `mmn reddit reply -f <csv>` to post them.
    """
    settings = _settings()

    if not settings.reddit_session:
        console.print(
            "[red]REDDIT_SESSION is not set in .env. Cannot authenticate with Reddit.[/red]"
        )
        raise typer.Exit(1)
    if not settings.vertex_ai_project:
        console.print(
            "[red]VERTEX_AI_PROJECT is not set in .env. Gemini is required for comment generation.[/red]"
        )
        raise typer.Exit(1)

    if max_comments > 0:
        settings = RedditSettings(
            **{**settings.model_dump(), "max_comments_per_day": max_comments},
        )
    orchestrator = EngagementOrchestrator(settings)

    csv_path = output or Path(f"reddit_comments_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv")

    async def _run() -> None:
        if verbose:
            comments = await orchestrator.generate_only()
        else:
            prev = _quiet_loggers()
            try:
                with Live(
                    console=console,
                    refresh_per_second=8,
                    transient=False,
                ) as live:
                    progress = _RichProgress(live)
                    comments = await orchestrator.generate_only(progress=progress)
            finally:
                _restore_loggers(prev)

        if not comments:
            console.print("[yellow]No comments generated.[/yellow]")
            return

        _write_csv(comments, csv_path)
        console.print()
        console.print(f"[bold green]Saved {len(comments)} comments to {csv_path}[/bold green]")
        console.print("[dim]Review/edit the CSV, then run:[/dim]")
        console.print(f"  mmn reddit reply -f {csv_path}")

    asyncio.run(_run())


@app.command("reply")
def reply_cmd(
    csv_file: Path = typer.Option(
        ...,
        "-f",
        "--file",
        help="CSV file with generated comments",
        exists=True,
        readable=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show raw log output instead of rich UI",
    ),
) -> None:
    """Post comments from a CSV file generated by `mmn reddit engage`.

    The CSV must have columns: subreddit, post_url, post_id, post_fullname,
    comment_text. You can edit comment_text in the CSV before running this.
    """
    settings = _settings()
    orchestrator = EngagementOrchestrator(settings)

    comments = _read_csv(csv_file)
    if not comments:
        console.print("[yellow]CSV is empty, nothing to post.[/yellow]")
        raise typer.Exit()

    console.print(f"Loaded [bold]{len(comments)}[/bold] comments from {csv_file}")

    async def _run() -> EngagementStats:
        if verbose:
            return await orchestrator.comment_from_list(comments)
        else:
            prev = _quiet_loggers()
            try:
                with Live(
                    console=console,
                    refresh_per_second=8,
                    transient=False,
                ) as live:
                    progress = _RichProgress(live)
                    return await orchestrator.comment_from_list(
                        comments,
                        progress=progress,
                    )
            finally:
                _restore_loggers(prev)

    stats = asyncio.run(_run())
    _print_summary(stats)


@app.command()
def discover(
    max_per_sub: int = typer.Option(
        5,
        "--max-per-sub",
        help="Max posts to fetch per subreddit",
    ),
) -> None:
    """Discover posts without commenting. Useful for testing discovery logic."""
    settings = _settings()

    async def _run() -> None:
        from .client import RedditClient
        from .discovery import PostDiscoverer

        client = RedditClient(
            session_cookie=settings.reddit_session,
            username=settings.reddit_username,
            user_agent=settings.reddit_user_agent,
        )

        async with client:
            if not await client.is_logged_in():
                console.print(
                    "[red]Reddit session cookie is invalid or expired. "
                    "Update REDDIT_SESSION in .env.[/red]"
                )
                return

            discoverer = PostDiscoverer(
                client,
                settings.comment_history_path,
                own_username=settings.reddit_username,
            )

            import yaml

            targets_path = settings.targets_path
            if not targets_path.exists():
                console.print(f"[red]Targets file not found: {targets_path}[/red]")
                return

            with targets_path.open("r", encoding="utf-8") as f:
                targets = yaml.safe_load(f) or {}

            subreddits = targets.get("subreddits", [])
            queries = targets.get("search_queries", [])

            with console.status("[bold cyan]Discovering posts...[/bold cyan]"):
                search_posts = await discoverer.discover_search_posts(
                    subreddits[:6],
                    queries[:4],
                    max_per_query=2,
                )
                hot_posts = await discoverer.discover_hot_posts(
                    subreddits[:6],
                    max_per_sub=max_per_sub,
                )

            all_posts = discoverer._dedupe(search_posts + hot_posts)
            all_posts.sort(key=lambda p: p.score, reverse=True)

            if not all_posts:
                console.print("[yellow]No posts discovered. Is your session cookie valid?[/yellow]")
                return

            console.print(f"\nDiscovered [bold]{len(all_posts)}[/bold] posts:\n")
            for i, post in enumerate(all_posts, start=1):
                console.print(
                    f"  {i}. [cyan]r/{post.subreddit}[/cyan]  "
                    f"[dim]score: {post.score}  "
                    f"comments: {post.num_comments}[/dim]"
                )
                console.print(f"     {post.post_url}")
                console.print(f"     {post.post_title[:120]}")
                if post.post_text:
                    console.print(f"     [dim]{post.post_text[:150]}...[/dim]")
                console.print()

    asyncio.run(_run())


@app.command("test-comment")
def test_comment(
    post_url: str = typer.Argument(
        help="URL of a Reddit post to generate a comment for",
    ),
) -> None:
    """Generate a comment for a specific Reddit post URL without posting it."""
    settings = _settings()
    _ensure_vertex_credentials(settings)

    async def _run() -> None:
        from .client import RedditClient
        from .comment_generator import CommentGenerator

        client = RedditClient(
            session_cookie=settings.reddit_session,
            username=settings.reddit_username,
            user_agent=settings.reddit_user_agent,
        )

        async with client:
            if not await client.is_logged_in():
                console.print("[red]Reddit session cookie is invalid or expired.[/red]")
                return

            permalink = post_url.split("reddit.com")[-1] if "reddit.com" in post_url else post_url
            if permalink.endswith("/"):
                permalink = permalink[:-1]

            with console.status("[bold cyan]Fetching post...[/bold cyan]"):
                data = await client.get_post_detail(permalink)

            if not data:
                console.print("[red]Could not fetch post details.[/red]")
                return

            post = DiscoveredPost(
                subreddit=str(data.get("subreddit", "")),
                post_id=str(data.get("id", "")),
                post_fullname=str(data.get("name", "")),
                post_url=post_url,
                post_title=str(data.get("title", "")),
                post_text=str(data.get("selftext", ""))[:2000],
                author=str(data.get("author", "[deleted]")),
                score=int(data.get("score", 0)),  # type: ignore[arg-type]
                num_comments=int(data.get("num_comments", 0)),  # type: ignore[arg-type]
            )

            console.print(
                f"\n[bold]r/{post.subreddit}[/bold]  "
                f"by u/{post.author}  "
                f"[dim](score: {post.score})[/dim]"
            )
            console.print(f"  {post.post_title}")
            if post.post_text:
                console.print(f"  [dim]{post.post_text[:300]}[/dim]")

            generator = CommentGenerator(
                gemini_model=settings.gemini_model,
                mention_rate=settings.mention_rate,
                vertex_project=settings.vertex_ai_project,
                vertex_location=settings.vertex_ai_location,
            )

            with console.status("[bold cyan]Generating comment...[/bold cyan]"):
                comment = await generator.generate_comment(post, comment_number=1)

            console.print(f"\n[bold green]Generated comment[/bold green] ({len(comment)} chars):\n")
            console.print(Panel(comment, border_style="green"))

    asyncio.run(_run())


if __name__ == "__main__":
    app()
