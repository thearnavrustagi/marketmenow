from __future__ import annotations

import asyncio
import csv
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .browser import StealthBrowser
from .orchestrator import (
    EngagementOrchestrator,
    EngagementStats,
    GeneratedReply,
)
from .reply_generator import ReplyGenerator
from .settings import TwitterSettings
from .thread_generator import GeneratedThread, ThreadGenerator

app = typer.Typer(
    name="mmn-x",
    help="MarketMeNow Twitter/X engagement CLI",
    no_args_is_help=True,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

console = Console()

_NOISY_LOGGERS = (
    "adapters.twitter",
    "httpx",
    "httpcore",
    "google_genai",
    "google.auth",
    "google.auth.transport",
    "urllib3",
)


def _quiet_loggers() -> dict[str, int]:
    """Silence noisy third-party loggers, return previous levels."""
    prev: dict[str, int] = {}
    for name in _NOISY_LOGGERS:
        lg = logging.getLogger(name)
        prev[name] = lg.level
        lg.setLevel(logging.WARNING)
    return prev


def _restore_loggers(prev: dict[str, int]) -> None:
    for name, level in prev.items():
        logging.getLogger(name).setLevel(level)


# ── Rich progress UI ────────────────────────────────────────────────


class _ReplyEntry:
    __slots__ = ("handle", "idx", "reply_text", "status", "total")

    def __init__(self, idx: int, total: int, handle: str) -> None:
        self.idx = idx
        self.total = total
        self.handle = handle
        self.status: str = "generating"
        self.reply_text: str = ""


class _RichProgress:
    """Live-updating terminal UI for the engagement loop."""

    def __init__(self, live: Live) -> None:
        self._live = live
        self._total_handles = 0
        self._total_hashtags = 0
        self._handles_done: list[tuple[str, int]] = []
        self._hashtags_done: list[tuple[str, int]] = []
        self._total_posts = 0
        self._candidates = 0
        self._replies: list[_ReplyEntry] = []
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
            grid.add_row(self._render_replies())

        if self._status_text:
            grid.add_row(Text())
            grid.add_row(Text(f"  {self._status_text}", style="dim"))

        return grid

    def _render_discovery(self) -> Panel:
        tbl = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
        tbl.add_column("icon", width=3)
        tbl.add_column("source", min_width=20)
        tbl.add_column("count", justify="right", width=8)

        h_done = len(self._handles_done)
        ht_done = len(self._hashtags_done)

        for handle, count in self._handles_done:
            style = "green" if count > 0 else "dim"
            tbl.add_row("  ", f"@{handle}", f"[{style}]{count} posts[/{style}]")

        remaining_handles = self._total_handles - h_done
        if remaining_handles > 0:
            tbl.add_row(
                "[bold cyan]>[/bold cyan]",
                f"[dim]{remaining_handles} more handle{'s' if remaining_handles != 1 else ''}...[/dim]",
                "",
            )

        for tag, count in self._hashtags_done:
            style = "green" if count > 0 else "dim"
            tbl.add_row("  ", f"#{tag}", f"[{style}]{count} posts[/{style}]")

        remaining_tags = self._total_hashtags - ht_done
        if remaining_tags > 0:
            tbl.add_row(
                "[bold cyan]>[/bold cyan]",
                f"[dim]{remaining_tags} more hashtag{'s' if remaining_tags != 1 else ''}...[/dim]",
                "",
            )

        total_found = sum(c for _, c in self._handles_done) + sum(c for _, c in self._hashtags_done)
        progress_str = (
            f"Handles {h_done}/{self._total_handles}  "
            f"Hashtags {ht_done}/{self._total_hashtags}  "
            f"Posts {total_found}"
        )

        return Panel(
            tbl,
            title=f"[bold]Discovering[/bold]  [dim]{self._elapsed()}[/dim]",
            subtitle=f"[dim]{progress_str}[/dim]",
            border_style="cyan",
        )

    def _render_discovery_summary(self) -> Panel:
        total_found = sum(c for _, c in self._handles_done) + sum(c for _, c in self._hashtags_done)
        txt = Text()
        txt.append(f"  {total_found}", style="bold green")
        txt.append(" posts from ")
        txt.append(f"{len(self._handles_done)}", style="bold")
        txt.append(" handles + ")
        txt.append(f"{len(self._hashtags_done)}", style="bold")
        txt.append(" hashtags")
        if self._candidates > 0 and self._candidates != total_found:
            txt.append(f"  (generating {self._candidates} replies)", style="dim")
        return Panel(txt, title="[bold]Discovery[/bold]", border_style="green")

    def _render_replies(self) -> Panel:
        tbl = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
        tbl.add_column("status", width=3)
        tbl.add_column("info", ratio=1)

        for entry in self._replies:
            counter = f"[dim]{entry.idx}/{entry.total}[/dim]"
            if entry.status == "generating":
                tbl.add_row(
                    "[bold yellow]~[/bold yellow]",
                    f"{counter}  @{entry.handle}  [yellow]generating...[/yellow]",
                )
            elif entry.status == "generated":
                tbl.add_row(
                    "[bold green]✓[/bold green]",
                    Text.from_markup(
                        f"{counter}  @{entry.handle}\n       [dim]{entry.reply_text}[/dim]"
                    ),
                )
            elif entry.status == "posted":
                tbl.add_row(
                    "[bold green]✓[/bold green]",
                    Text.from_markup(
                        f"{counter}  @{entry.handle}  [green]posted[/green]\n       [dim]{entry.reply_text}[/dim]"
                    ),
                )
            elif entry.status == "post_failed":
                tbl.add_row(
                    "[bold red]✗[/bold red]",
                    f"{counter}  @{entry.handle}  [red]post failed[/red]",
                )
            elif entry.status == "failed":
                tbl.add_row(
                    "[bold red]✗[/bold red]",
                    f"{counter}  @{entry.handle}  [red]generate failed[/red]",
                )

        title_label = "Generating" if self._phase in ("generating", "replying") else "Done"
        border = "yellow" if self._phase in ("generating", "replying") else "green"

        return Panel(
            tbl,
            title=f"[bold]{title_label}[/bold]  [dim]{self._elapsed()}[/dim]",
            border_style=border,
        )

    def _refresh(self) -> None:
        self._live.update(self._render())

    def _find_entry(self, current: int, handle: str) -> _ReplyEntry | None:
        for e in reversed(self._replies):
            if e.idx == current and e.handle == handle:
                return e
        return None

    # -- ProgressCallback interface --

    def on_discovery_start(self, total_handles: int, total_hashtags: int) -> None:
        self._total_handles = total_handles
        self._total_hashtags = total_hashtags
        self._phase = "discovery"
        self._refresh()

    def on_handle_done(self, handle: str, posts_found: int) -> None:
        self._handles_done.append((handle, posts_found))
        self._refresh()

    def on_hashtag_done(self, hashtag: str, posts_found: int) -> None:
        self._hashtags_done.append((hashtag, posts_found))
        self._refresh()

    def on_discovery_end(self, total_posts: int, candidates: int) -> None:
        self._total_posts = total_posts
        self._candidates = candidates
        self._phase = "generating" if candidates > 0 else "done"
        self._status_text = ""
        self._refresh()

    def on_generating(self, current: int, total: int, handle: str) -> None:
        self._replies.append(_ReplyEntry(current, total, handle))
        self._status_text = ""
        self._refresh()

    def on_generated(self, current: int, total: int, handle: str, reply_text: str) -> None:
        entry = self._find_entry(current, handle)
        if entry:
            entry.status = "generated"
            entry.reply_text = reply_text
        self._refresh()

    def on_generate_failed(self, current: int, total: int, handle: str) -> None:
        entry = self._find_entry(current, handle)
        if entry:
            entry.status = "failed"
        self._refresh()

    def on_reply_posted(self, current: int, total: int, handle: str, success: bool) -> None:
        entry = self._find_entry(current, handle)
        if entry:
            entry.status = "posted" if success else "post_failed"
        self._refresh()

    def on_reply_wait(self, seconds: int) -> None:
        self._status_text = f"Waiting {seconds}s before next reply..."
        self._refresh()

    def on_complete(self, stats: EngagementStats) -> None:
        self._phase = "done"
        self._status_text = ""
        self._refresh()


# ── Helpers ──────────────────────────────────────────────────────────


def _settings() -> TwitterSettings:
    return TwitterSettings()


def _apply_overrides(
    settings: TwitterSettings,
    headless: bool = False,
    max_replies: int = 0,
) -> TwitterSettings:
    overrides: dict[str, object] = {}
    if max_replies > 0:
        overrides["max_replies_per_day"] = max_replies
    if headless:
        overrides["headless"] = True
    if overrides:
        return TwitterSettings(**{**settings.model_dump(), **overrides})
    return settings


def _print_summary(
    stats: EngagementStats,
    thread: GeneratedThread | None = None,
) -> None:
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
    if thread is not None:
        tbl.add_row(
            "Thread",
            f"[green]Posted ({len(thread.tweets)} tweets)[/green]",
        )
    console.print(tbl)


def _print_thread(generated: GeneratedThread) -> None:
    """Display a generated thread with Rich panels."""
    console.print()
    console.print(
        Panel(
            f"[bold]{generated.topic}[/bold]",
            title="Thread Topic",
            border_style="cyan",
        )
    )
    console.print()

    for tweet in generated.tweets:
        label = ""
        if tweet.is_hook:
            label = " [bold yellow](HOOK)[/bold yellow]"
        elif tweet.is_cta:
            label = " [bold green](CTA)[/bold green]"

        char_count = len(tweet.text)
        char_style = "green" if char_count <= 280 else "red"

        console.print(
            Panel(
                tweet.text,
                title=f"Tweet {tweet.position}{label}",
                subtitle=f"[{char_style}]{char_count}/280[/{char_style}]",
                border_style="blue" if not tweet.is_cta else "green",
            )
        )


def _write_csv(replies: list[GeneratedReply], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["post_url", "author_handle", "post_text", "reply_text", "engagement_score"]
        )
        for r in replies:
            writer.writerow(
                [
                    r.post_url,
                    r.author_handle,
                    r.post_text,
                    r.reply_text,
                    r.engagement_score,
                ]
            )


def _read_csv(path: Path) -> list[GeneratedReply]:
    rows: list[GeneratedReply] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                GeneratedReply(
                    post_url=row["post_url"],
                    author_handle=row["author_handle"],
                    post_text=row.get("post_text", ""),
                    reply_text=row["reply_text"],
                    engagement_score=int(row.get("engagement_score", 0)),
                )
            )
    return rows


# ── Commands ─────────────────────────────────────────────────────────


@app.command()
def login(
    force: bool = typer.Option(
        False,
        "--force",
        help="Skip session check and log in fresh",
    ),
    cookies: bool = typer.Option(
        False,
        "--cookies",
        help="Log in by injecting auth_token and ct0 cookies",
    ),
) -> None:
    """Create a Twitter/X session for future commands.

    Two methods:

      mmn twitter login --cookies    Inject auth_token + ct0 from your browser
                                     (set TWITTER_AUTH_TOKEN / TWITTER_CT0 in .env,
                                      or you'll be prompted).

      mmn twitter login              Opens Chrome to x.com -- log in manually.
    """
    settings = _settings()

    async def _run() -> None:
        browser = StealthBrowser(
            session_path=settings.twitter_session_path,
            user_data_dir=settings.twitter_user_data_dir,
            headless=False,
            slow_mo_ms=settings.slow_mo_ms,
            proxy_url=settings.proxy_url,
        )
        async with browser:
            if not force and not cookies:
                typer.echo("Checking existing session...")
                if await browser.is_logged_in():
                    typer.echo("Already logged in! Session is valid.")
                    return

            if cookies:
                auth_token = settings.twitter_auth_token
                ct0 = settings.twitter_ct0

                if not auth_token:
                    auth_token = typer.prompt("auth_token cookie value")
                if not ct0:
                    ct0 = typer.prompt("ct0 cookie value")

                await browser.login_with_cookies(auth_token, ct0)
                typer.echo("Cookie login successful. Session saved.")
            else:
                typer.echo(
                    "\nA browser window will open to x.com.\n"
                    "Please log in manually (you have 5 minutes).\n"
                    "The session will be saved once you reach the home feed.\n"
                )
                await browser.login_manual()
                typer.echo("Login successful. Session saved.")

    asyncio.run(_run())


@app.command()
def engage(
    output: Path = typer.Option(
        None,
        "-o",
        "--output",
        help="CSV output path (default: replies_<timestamp>.csv)",
    ),
    max_replies: int = typer.Option(
        0,
        "--max-replies",
        help="Override max replies (0 = use settings default)",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show raw log output instead of rich UI",
    ),
) -> None:
    """Discover posts and generate replies, saving them to a CSV.

    Does NOT post anything. Review the CSV, edit replies if you want,
    then run `mmn twitter reply -f <csv>` to post them.
    """
    settings = _apply_overrides(_settings(), headless=headless, max_replies=max_replies)
    orchestrator = EngagementOrchestrator(settings)

    csv_path = output or Path(f"replies_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv")

    async def _run() -> None:
        if verbose:
            replies = await orchestrator.generate_only()
        else:
            prev = _quiet_loggers()
            try:
                with Live(console=console, refresh_per_second=8, transient=False) as live:
                    progress = _RichProgress(live)
                    replies = await orchestrator.generate_only(progress=progress)
            finally:
                _restore_loggers(prev)

        if not replies:
            console.print("[yellow]No replies generated.[/yellow]")
            return

        _write_csv(replies, csv_path)
        console.print()
        console.print(f"[bold green]Saved {len(replies)} replies to {csv_path}[/bold green]")
        console.print("[dim]Review/edit the CSV, then run:[/dim]")
        console.print(f"  mmn twitter reply -f {csv_path}" + (" --headless" if headless else ""))

    asyncio.run(_run())


@app.command("reply")
def reply_cmd(
    csv_file: Path = typer.Option(
        ...,
        "-f",
        "--file",
        help="CSV file with generated replies",
        exists=True,
        readable=True,
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show raw log output instead of rich UI",
    ),
) -> None:
    """Post replies from a CSV file generated by `mmn twitter engage`.

    The CSV must have columns: post_url, author_handle, reply_text.
    You can edit reply_text in the CSV before running this.
    """
    settings = _apply_overrides(_settings(), headless=headless)
    orchestrator = EngagementOrchestrator(settings)

    replies = _read_csv(csv_file)
    if not replies:
        console.print("[yellow]CSV is empty, nothing to reply.[/yellow]")
        raise typer.Exit()

    console.print(f"Loaded [bold]{len(replies)}[/bold] replies from {csv_file}")

    async def _run() -> EngagementStats:
        if verbose:
            return await orchestrator.reply_from_list(replies)
        else:
            prev = _quiet_loggers()
            try:
                with Live(console=console, refresh_per_second=8, transient=False) as live:
                    progress = _RichProgress(live)
                    return await orchestrator.reply_from_list(replies, progress=progress)
            finally:
                _restore_loggers(prev)

    stats = asyncio.run(_run())
    _print_summary(stats)


@app.command()
def discover(
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode",
    ),
) -> None:
    """Discover posts without replying. Useful for testing discovery logic."""
    settings = _apply_overrides(_settings(), headless=headless)
    orchestrator = EngagementOrchestrator(settings)

    async def _run() -> None:
        posts = await orchestrator.discover_only()
        if not posts:
            typer.echo("No posts discovered. Are you logged in?")
            return
        typer.echo(f"\nDiscovered {len(posts)} posts:\n")
        for i, post in enumerate(posts, start=1):
            typer.echo(f"  {i}. @{post.author_handle} (engagement: {post.engagement_score})")
            typer.echo(f"     {post.post_url}")
            typer.echo(f"     {post.post_text[:120]}...")
            typer.echo()

    asyncio.run(_run())


@app.command()
def collect(
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode",
    ),
) -> None:
    """Scrape your own profile for top-performing posts/replies.

    Saves winning examples (>0 likes or retweets) to a JSON cache file.
    These are automatically injected as few-shot examples when generating
    new replies and threads.

    The cache is also auto-refreshed during `engage` and `all` when stale.
    """
    from .performance_tracker import PerformanceTracker

    settings = _apply_overrides(_settings(), headless=headless)
    username = settings.twitter_username

    if not username:
        console.print(
            "[red]twitter_username not set in .env -- "
            "cannot collect examples without knowing your handle.[/red]"
        )
        raise typer.Exit(1)

    async def _run() -> None:
        browser = StealthBrowser(
            session_path=settings.twitter_session_path,
            user_data_dir=settings.twitter_user_data_dir,
            headless=settings.headless,
            slow_mo_ms=settings.slow_mo_ms,
            proxy_url=settings.proxy_url,
            viewport_width=settings.viewport_width,
            viewport_height=settings.viewport_height,
        )

        async with browser:
            if not await browser.is_logged_in():
                console.print("[red]Not logged in. Run `mmn twitter login` first.[/red]")
                return

            tracker = PerformanceTracker(
                browser,
                username,
                settings.top_examples_path,
            )

            with console.status("[bold cyan]Collecting top-performing examples...[/bold cyan]"):
                cache = await tracker.collect()

            console.print()
            console.print(
                Panel(
                    f"[bold green]{len(cache.posts)}[/bold green] winning posts  |  "
                    f"[bold green]{len(cache.replies)}[/bold green] winning replies",
                    title="Collection Complete",
                    border_style="green",
                )
            )

            if cache.replies:
                tbl = Table(title="Top Replies", show_lines=True)
                tbl.add_column("Likes", justify="right", width=6)
                tbl.add_column("RTs", justify="right", width=6)
                tbl.add_column("Parent", max_width=40)
                tbl.add_column("Our Reply", max_width=50)
                for r in sorted(cache.replies, key=lambda x: x.likes + x.retweets, reverse=True)[
                    :10
                ]:
                    tbl.add_row(
                        str(r.likes),
                        str(r.retweets),
                        r.parent_text[:80] + ("..." if len(r.parent_text) > 80 else ""),
                        r.our_reply[:80] + ("..." if len(r.our_reply) > 80 else ""),
                    )
                console.print(tbl)

            if cache.posts:
                tbl = Table(title="Top Posts", show_lines=True)
                tbl.add_column("Likes", justify="right", width=6)
                tbl.add_column("RTs", justify="right", width=6)
                tbl.add_column("Text", max_width=60)
                for p in sorted(cache.posts, key=lambda x: x.likes + x.retweets, reverse=True)[:10]:
                    tbl.add_row(
                        str(p.likes),
                        str(p.retweets),
                        p.text[:100] + ("..." if len(p.text) > 100 else ""),
                    )
                console.print(tbl)

            console.print(f"\n[dim]Cache saved to {settings.top_examples_path}[/dim]")

    asyncio.run(_run())


@app.command("test-reply")
def test_reply(
    post_url: str = typer.Argument(help="URL of the tweet to generate a reply for"),
) -> None:
    """Generate a reply for a specific post URL without posting it."""
    settings = _settings()

    async def _run() -> None:
        browser = StealthBrowser(
            session_path=settings.twitter_session_path,
            user_data_dir=settings.twitter_user_data_dir,
            headless=settings.headless,
            slow_mo_ms=settings.slow_mo_ms,
            proxy_url=settings.proxy_url,
        )

        async with browser:
            if not await browser.is_logged_in():
                typer.echo("Not logged in. Run `mmn twitter login` first.", err=True)
                sys.exit(1)

            await browser.navigate(post_url)

            page = browser.page
            try:
                text_el = page.locator('div[data-testid="tweetText"]').first
                post_text = await text_el.inner_text(timeout=10_000)
            except Exception:
                post_text = "(could not extract tweet text)"

            try:
                handle_el = page.locator(
                    'div[data-testid="User-Name"] a[role="link"][tabindex="-1"]'
                )
                href = await handle_el.get_attribute("href", timeout=5_000)
                author = href.strip("/").split("/")[-1] if href else "unknown"
            except Exception:
                author = "unknown"

            from .discovery import DiscoveredPost

            post = DiscoveredPost(
                author_handle=author,
                post_url=post_url,
                post_text=post_text,
            )

            generator = ReplyGenerator(
                model=settings.gemini_model,
                top_examples_path=settings.top_examples_path,
                max_examples=settings.max_examples_in_prompt,
            )
            reply = await generator.generate_reply(post, reply_number=1)

            typer.echo(f"\nOriginal by @{author}:")
            typer.echo(f"  {post_text[:200]}")
            typer.echo(f"\nGenerated reply ({len(reply)} chars):")
            typer.echo(f"  {reply}")

    asyncio.run(_run())


@app.command()
def thread(
    topic: str = typer.Option(
        "",
        "--topic",
        "-t",
        help="Topic hint for the thread (leave empty for random)",
    ),
    post: bool = typer.Option(
        False,
        "--post",
        help="Actually post the thread (default: generate only)",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode",
    ),
    distribute: bool = typer.Option(
        False,
        "--distribute",
        help="Distribute to all mapped platforms",
    ),
    only: str = typer.Option(
        "",
        "--only",
        help="Comma-separated platform filter for --distribute",
    ),
) -> None:
    """Generate (and optionally post) a viral Twitter/X thread.

    By default, generates the thread and prints it for review.
    Add --post to publish it to X.
    """
    settings = _apply_overrides(_settings(), headless=headless)

    async def _run() -> None:

        _ensure_vertex_credentials(settings)

        generator = ThreadGenerator(
            model=settings.gemini_model,
            top_examples_path=settings.top_examples_path,
            max_examples=settings.max_examples_in_prompt,
        )

        with console.status("[bold cyan]Generating thread...[/bold cyan]"):
            generated = await generator.generate_thread(topic_hint=topic)

        _print_thread(generated)

        if distribute:
            from marketmenow.core.distribute_cli import distribute_content
            from marketmenow.models.content import Thread, ThreadEntry

            thread_content = Thread(
                entries=[ThreadEntry(text=t.text) for t in generated.tweets],
            )
            await distribute_content(thread_content, console, only=only or None)
            return

        if not post:
            console.print()
            console.print(
                "[dim]Thread generated (dry run). "
                "Add --post to publish it to X or --distribute for all platforms.[/dim]"
            )
            return

        browser = StealthBrowser(
            session_path=settings.twitter_session_path,
            user_data_dir=settings.twitter_user_data_dir,
            headless=settings.headless,
            slow_mo_ms=settings.slow_mo_ms,
            proxy_url=settings.proxy_url,
            viewport_width=settings.viewport_width,
            viewport_height=settings.viewport_height,
        )

        async with browser:
            if not await browser.is_logged_in():
                console.print("[red]Not logged in. Run `mmn-x login` first.[/red]")
                return

            tweet_texts = [t.text for t in generated.tweets]

            console.print()
            with console.status("[bold cyan]Posting thread...[/bold cyan]"):
                success = await browser.post_thread(tweet_texts)

            if success:
                console.print("[bold green]Thread posted successfully![/bold green]")
            else:
                console.print("[bold red]Failed to post thread.[/bold red]")

    asyncio.run(_run())


@app.command("all")
def all_cmd(
    max_replies: int = typer.Option(
        0,
        "--max-replies",
        help="Override max replies (0 = use settings default)",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--no-headless",
        help="Run the browser in headless mode (default: on)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show raw log output instead of rich UI",
    ),
    min_delay: int = typer.Option(
        0,
        "--min-delay",
        help="Minimum seconds between replies (0 = use settings default)",
    ),
    max_delay: int = typer.Option(
        0,
        "--max-delay",
        help="Maximum seconds between replies (0 = use settings default)",
    ),
) -> None:
    """Discover, generate, and post replies + a Top-5 thread.

    Runs the full pipeline:

    \b
      1. Discover relevant posts from configured handles/hashtags
      2. Generate AI replies for each candidate
      3. Post them with randomised 5-10 minute gaps between each
      4. Generate and post a Top-5 listicle thread

    Headless mode is ON by default to reduce detection risk.
    Override intervals with --min-delay / --max-delay (seconds).
    """
    settings = _apply_overrides(_settings(), headless=headless, max_replies=max_replies)

    overrides: dict[str, object] = {}
    if min_delay > 0:
        overrides["min_delay_seconds"] = min_delay
    if max_delay > 0:
        overrides["max_delay_seconds"] = max_delay
    if overrides:
        settings = TwitterSettings(**{**settings.model_dump(), **overrides})

    orchestrator = EngagementOrchestrator(settings)

    async def _run() -> tuple[EngagementStats, GeneratedThread | None]:
        stats: EngagementStats

        if verbose:
            replies = await orchestrator.generate_only()
            if not replies:
                console.print("[yellow]No replies generated.[/yellow]")
                stats = EngagementStats()
            else:
                console.print(f"[bold]Posting {len(replies)} replies...[/bold]")
                stats = await orchestrator.reply_from_list(replies)
        else:
            prev = _quiet_loggers()
            try:
                with Live(console=console, refresh_per_second=8, transient=False) as live:
                    progress = _RichProgress(live)
                    replies = await orchestrator.generate_only(progress=progress)
                if not replies:
                    console.print("[yellow]No replies generated.[/yellow]")
                    stats = EngagementStats()
                else:
                    with Live(console=console, refresh_per_second=8, transient=False) as live:
                        progress = _RichProgress(live)
                        stats = await orchestrator.reply_from_list(replies, progress=progress)
            finally:
                _restore_loggers(prev)

        console.print()
        with console.status("[bold cyan]Generating Top-5 thread...[/bold cyan]"):
            thread_result = await orchestrator.generate_and_post_thread()

        if thread_result:
            _print_thread(thread_result)
            console.print("[bold green]Thread posted successfully![/bold green]")
        else:
            console.print("[bold red]Thread generation or posting failed.[/bold red]")

        return stats, thread_result

    stats, thread_result = asyncio.run(_run())
    _print_summary(stats, thread=thread_result)


def _ensure_vertex_credentials(settings: TwitterSettings) -> None:
    """Export GOOGLE_APPLICATION_CREDENTIALS so the genai SDK picks it up."""
    import os

    creds = settings.google_application_credentials
    if creds and creds.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(creds.resolve()))


if __name__ == "__main__":
    app()
