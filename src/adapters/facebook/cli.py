from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from marketmenow.models.content import (
    ImagePost,
    MediaAsset,
    TextPost,
    VideoPost,
)
from marketmenow.normaliser import ContentNormaliser

from . import create_facebook_bundle
from .browser import FacebookBrowser
from .settings import FacebookSettings

app = typer.Typer(
    name="mmn-facebook",
    help="MarketMeNow Facebook posting CLI",
    no_args_is_help=True,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
console = Console()


def _settings() -> FacebookSettings:
    return FacebookSettings()


def _mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _make_browser(settings: FacebookSettings) -> FacebookBrowser:
    return FacebookBrowser(
        session_path=settings.facebook_session_path,
        user_data_dir=settings.facebook_user_data_dir,
        headless=settings.headless,
        slow_mo_ms=settings.slow_mo_ms,
        proxy_url=settings.proxy_url,
        viewport_width=settings.viewport_width,
        viewport_height=settings.viewport_height,
    )


def _split_targets(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _normalise_group_url(group: str) -> str:
    value = group.strip()
    if value.startswith(("http://", "https://")):
        return value
    return f"https://www.facebook.com/groups/{value}"


def _normalise_page_url(page: str) -> str:
    value = page.strip().lstrip("/")
    if value.startswith(("http://", "https://")):
        return value
    if value.isdigit():
        return f"https://www.facebook.com/profile.php?id={value}"
    return f"https://www.facebook.com/{value}"


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
        help="Log in by injecting c_user and xs cookies",
    ),
) -> None:
    """Create a Facebook session for future commands.

    Two methods:

      mmn facebook login --cookies    Inject c_user + xs from your browser
                                      (set FACEBOOK_C_USER / FACEBOOK_XS in .env,
                                       or you'll be prompted).

      mmn facebook login              Opens Chrome to facebook.com --
                                      log in manually.
    """
    settings = _settings()

    async def _run() -> None:
        browser = _make_browser(settings)
        async with browser:
            if not force and not cookies:
                typer.echo("Checking existing session...")
                if await browser.is_logged_in():
                    typer.echo("Already logged in! Session is valid.")
                    return

            if cookies:
                c_user = settings.facebook_c_user
                xs = settings.facebook_xs

                if not c_user:
                    c_user = typer.prompt("c_user cookie value")
                if not xs:
                    xs = typer.prompt("xs cookie value")

                await browser.login_with_cookies(c_user, xs)
                typer.echo("Cookie login successful. Session saved.")
            else:
                typer.echo(
                    "\nA browser window will open to facebook.com.\n"
                    "Please log in manually (you have 5 minutes).\n"
                    "The session will be saved once you reach the feed.\n"
                )
                await browser.login_manual()
                typer.echo("Login successful. Session saved.")

    asyncio.run(_run())


@app.command()
def status() -> None:
    """Check Facebook login status."""
    settings = _settings()

    table = Table(title="Facebook Status", show_header=False, border_style="bold")
    table.add_column("key", style="bold")
    table.add_column("value")

    table.add_row("Session file", str(settings.facebook_session_path))
    table.add_row(
        "Session exists",
        "[green]yes[/green]" if settings.facebook_session_path.exists() else "[red]no[/red]",
    )
    table.add_row(
        "c_user in .env",
        "[green]set[/green]" if settings.facebook_c_user else "[dim]not set[/dim]",
    )
    table.add_row(
        "xs in .env",
        "[green]set[/green]" if settings.facebook_xs else "[dim]not set[/dim]",
    )
    table.add_row(
        "Group IDs",
        settings.facebook_group_ids if settings.facebook_group_ids else "[dim]none[/dim]",
    )
    table.add_row(
        "Page IDs",
        settings.facebook_page_ids if settings.facebook_page_ids else "[dim]none[/dim]",
    )

    console.print()
    console.print(table)
    console.print()


@app.command()
def post(
    text: str | None = typer.Option(
        None,
        "--text",
        "-t",
        help="Post body text",
    ),
    image: list[Path] | None = typer.Option(
        None,
        "--image",
        "-i",
        help="Image file(s) to attach",
        exists=True,
        readable=True,
    ),
    video: Path | None = typer.Option(
        None,
        "--video",
        "-v",
        help="Video file to attach",
        exists=True,
        readable=True,
    ),
    hashtags: str | None = typer.Option(
        None,
        "--hashtags",
        help="Comma-separated hashtags",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode",
    ),
) -> None:
    """Publish a post to your personal Facebook feed via the browser.

    Exactly one content type should be specified. If only --text is given,
    a text-only post is created. Combine --text with --image or --video
    for rich content.
    """
    settings = _settings()
    if headless:
        settings = settings.model_copy(update={"headless": True})
    tag_list = [t.strip() for t in (hashtags or "").split(",") if t.strip()]

    content_flags = sum([bool(image), bool(video)])
    if content_flags > 1:
        console.print("[red]Specify only one of --image or --video.[/red]")
        raise typer.Exit(1)

    if not text and not image and not video:
        console.print("[red]Provide at least --text or a media option.[/red]")
        raise typer.Exit(1)

    normaliser = ContentNormaliser()

    if image:
        assets = [MediaAsset(uri=str(p.resolve()), mime_type=_mime(p)) for p in image]
        model = ImagePost(images=assets, caption=text or "", hashtags=tag_list)
    elif video:
        asset = MediaAsset(uri=str(video.resolve()), mime_type=_mime(video))
        model = VideoPost(video=asset, caption=text or "", hashtags=tag_list)
    else:
        model = TextPost(body=text or "", hashtags=tag_list)

    normalised = normaliser.normalise(model)

    async def _run() -> None:
        bundle = create_facebook_bundle(settings)
        browser: FacebookBrowser = bundle.adapter._browser  # type: ignore[attr-defined]

        async with browser:
            if not await browser.is_logged_in():
                c_user = settings.facebook_c_user
                xs = settings.facebook_xs
                if c_user and xs:
                    await browser.login_with_cookies(c_user, xs)
                else:
                    console.print(
                        "[red]Not logged in. Run `mmn facebook login` first,[/red]\n"
                        "[red]or set FACEBOOK_C_USER and FACEBOOK_XS in .env.[/red]"
                    )
                    raise typer.Exit(1)

            rendered = await bundle.renderer.render(normalised)
            result = await bundle.adapter.publish(rendered)

            if result.success:
                console.print()
                console.print(
                    Panel(
                        "[bold green]Published![/bold green]",
                        title="Facebook",
                        border_style="green",
                    )
                )
            else:
                console.print()
                console.print(
                    Panel(
                        f"[bold red]Publish failed[/bold red]\n\nError: {result.error_message}",
                        title="Facebook",
                        border_style="red",
                    )
                )
                raise typer.Exit(1)

    asyncio.run(_run())


@app.command("group-post")
def group_post(
    group: str = typer.Option(
        ...,
        "--group",
        "-g",
        help="Facebook Group URL or ID",
    ),
    text: str = typer.Option(
        ...,
        "--text",
        "-t",
        help="Post body text",
    ),
    image: list[Path] | None = typer.Option(
        None,
        "--image",
        "-i",
        help="Image file(s) to attach",
        exists=True,
        readable=True,
    ),
    hashtags: str | None = typer.Option(
        None,
        "--hashtags",
        help="Comma-separated hashtags",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode",
    ),
) -> None:
    """Post to a Facebook Group.

    Provide the group URL (e.g. https://www.facebook.com/groups/123456)
    or just the numeric group ID.
    """
    settings = _settings()
    if headless:
        settings = settings.model_copy(update={"headless": True})

    group_url = _normalise_group_url(group)
    tag_list = [t.strip() for t in (hashtags or "").split(",") if t.strip()]

    full_text = text
    if tag_list:
        tag_line = " ".join(f"#{t.lstrip('#')}" for t in tag_list)
        full_text = f"{text}\n\n{tag_line}"

    async def _run() -> None:
        browser = _make_browser(settings)
        async with browser:
            if not await browser.is_logged_in():
                c_user = settings.facebook_c_user
                xs = settings.facebook_xs
                if c_user and xs:
                    await browser.login_with_cookies(c_user, xs)
                else:
                    console.print(
                        "[red]Not logged in. Run `mmn facebook login` first,[/red]\n"
                        "[red]or set FACEBOOK_C_USER and FACEBOOK_XS in .env.[/red]"
                    )
                    raise typer.Exit(1)

            image_paths = [p.resolve() for p in image] if image else None
            success = await browser.create_group_post(group_url, full_text, image_paths=image_paths)

            if success:
                console.print()
                console.print(
                    Panel(
                        "[bold green]Posted to group![/bold green]",
                        title="Facebook Group",
                        border_style="green",
                    )
                )
            else:
                console.print()
                console.print(
                    Panel(
                        "[bold red]Group post failed[/bold red]",
                        title="Facebook Group",
                        border_style="red",
                    )
                )
                raise typer.Exit(1)

    asyncio.run(_run())


@app.command("page-post")
def page_post(
    page: str | None = typer.Option(
        None,
        "--page",
        "-p",
        help="Facebook Page URL, slug, or numeric ID",
    ),
    text: str = typer.Option(
        ...,
        "--text",
        "-t",
        help="Post body text",
    ),
    image: list[Path] | None = typer.Option(
        None,
        "--image",
        "-i",
        help="Image file(s) to attach",
        exists=True,
        readable=True,
    ),
    hashtags: str | None = typer.Option(
        None,
        "--hashtags",
        help="Comma-separated hashtags",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode",
    ),
) -> None:
    """Post to a Facebook Page.

    Provide a page URL, slug (e.g. ``mybrand``), or numeric page ID.
    If omitted, the first entry in ``FACEBOOK_PAGE_IDS`` is used.
    """
    settings = _settings()
    if headless:
        settings = settings.model_copy(update={"headless": True})

    page_value = (page or "").strip()
    if not page_value:
        configured_pages = _split_targets(settings.facebook_page_ids)
        if configured_pages:
            page_value = configured_pages[0]

    if not page_value:
        console.print(
            "[red]Missing page target. Use --page or set FACEBOOK_PAGE_IDS in .env.[/red]"
        )
        raise typer.Exit(1)

    page_url = _normalise_page_url(page_value)
    tag_list = [t.strip() for t in (hashtags or "").split(",") if t.strip()]

    full_text = text
    if tag_list:
        tag_line = " ".join(f"#{t.lstrip('#')}" for t in tag_list)
        full_text = f"{text}\n\n{tag_line}"

    async def _run() -> None:
        browser = _make_browser(settings)
        async with browser:
            if not await browser.is_logged_in():
                c_user = settings.facebook_c_user
                xs = settings.facebook_xs
                if c_user and xs:
                    await browser.login_with_cookies(c_user, xs)
                else:
                    console.print(
                        "[red]Not logged in. Run `mmn facebook login` first,[/red]\n"
                        "[red]or set FACEBOOK_C_USER and FACEBOOK_XS in .env.[/red]"
                    )
                    raise typer.Exit(1)

            image_paths = [p.resolve() for p in image] if image else None
            success = await browser.create_page_post(page_url, full_text, image_paths=image_paths)

            if success:
                console.print()
                console.print(
                    Panel(
                        "[bold green]Posted to page![/bold green]",
                        title="Facebook Page",
                        border_style="green",
                    )
                )
            else:
                console.print()
                console.print(
                    Panel(
                        "[bold red]Page post failed[/bold red]",
                        title="Facebook Page",
                        border_style="red",
                    )
                )
                raise typer.Exit(1)

    asyncio.run(_run())


@app.command("group-comment")
def group_comment(
    post_url: str = typer.Option(
        ...,
        "--post-url",
        "-u",
        help="URL of the Facebook group post to comment on",
    ),
    text: str = typer.Option(
        ...,
        "--text",
        "-t",
        help="Comment text",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode",
    ),
) -> None:
    """Comment on a Facebook Group post."""
    settings = _settings()
    if headless:
        settings = settings.model_copy(update={"headless": True})

    async def _run() -> None:
        browser = _make_browser(settings)
        async with browser:
            if not await browser.is_logged_in():
                c_user = settings.facebook_c_user
                xs = settings.facebook_xs
                if c_user and xs:
                    await browser.login_with_cookies(c_user, xs)
                else:
                    console.print(
                        "[red]Not logged in. Run `mmn facebook login` first,[/red]\n"
                        "[red]or set FACEBOOK_C_USER and FACEBOOK_XS in .env.[/red]"
                    )
                    raise typer.Exit(1)

            success = await browser.comment_on_group_post(post_url, text)

            if success:
                console.print()
                console.print(
                    Panel(
                        "[bold green]Comment posted![/bold green]",
                        title="Facebook Comment",
                        border_style="green",
                    )
                )
            else:
                console.print()
                console.print(
                    Panel(
                        "[bold red]Comment failed[/bold red]",
                        title="Facebook Comment",
                        border_style="red",
                    )
                )
                raise typer.Exit(1)

    asyncio.run(_run())


@app.command()
def engage(
    max_comments: int = typer.Option(
        0,
        "--max-comments",
        "-n",
        help="Override max comments per day (0 = use settings default)",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--no-headless",
        help="Run browser in headless mode",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Generate comments but do not post them",
    ),
) -> None:
    """Discover posts in teacher Facebook groups and engage with AI comments.

    This command scrapes target groups, generates teacher-persona comments
    via Gemini, and optionally posts them with human-like delays.
    """
    from .orchestrator import EngagementOrchestrator

    settings = _settings()
    if headless:
        settings = settings.model_copy(update={"headless": True})
    if max_comments > 0:
        settings = settings.model_copy(update={"max_comments_per_day": max_comments})

    async def _run() -> None:
        browser = _make_browser(settings)
        async with browser:
            if not await browser.is_logged_in():
                c_user = settings.facebook_c_user
                xs = settings.facebook_xs
                if c_user and xs:
                    await browser.login_with_cookies(c_user, xs)
                else:
                    console.print(
                        "[red]Not logged in. Run `mmn facebook login` first,[/red]\n"
                        "[red]or set FACEBOOK_C_USER and FACEBOOK_XS in .env.[/red]"
                    )
                    raise typer.Exit(1)

            orchestrator = EngagementOrchestrator(settings, browser)

            console.print("[bold cyan]Discovering posts in Facebook groups...[/bold cyan]")
            comments = await orchestrator.generate_only()

            if not comments:
                console.print(
                    "[yellow]No comments generated. Check your targets file and group access.[/yellow]"
                )
                raise typer.Exit(0)

            console.print(f"[green]Generated {len(comments)} comments[/green]")
            console.print()

            for i, c in enumerate(comments, start=1):
                console.print(
                    Panel(
                        f"[bold]{c.group_name}[/bold]\n"
                        f"[dim]Post by {c.post_author}:[/dim] {c.post_text[:120]}...\n\n"
                        f"[green]Comment:[/green] {c.comment_text}",
                        title=f"Comment {i}/{len(comments)}",
                        border_style="cyan",
                    )
                )

            if dry_run:
                console.print("\n[yellow]Dry run — comments were NOT posted.[/yellow]")
                return

            console.print("\n[bold cyan]Posting comments...[/bold cyan]")
            stats = await orchestrator.comment_from_list(comments)

            console.print()
            console.print(
                Panel(
                    f"[bold green]Engagement complete[/bold green]\n\n"
                    f"Succeeded: {stats.total_succeeded}\n"
                    f"Failed: {stats.total_failed}",
                    title="Facebook Engagement",
                    border_style="green",
                )
            )

    asyncio.run(_run())


if __name__ == "__main__":
    app()
