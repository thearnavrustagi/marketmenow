from __future__ import annotations

import asyncio
import importlib.metadata
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from adapters.email.cli import app as email_app
from adapters.facebook.cli import app as facebook_app
from adapters.instagram.cli import app as instagram_app
from adapters.instagram.cli import carousel_app, reel_app
from adapters.linkedin.cli import app as linkedin_app
from adapters.reddit.cli import app as reddit_app
from adapters.twitter.cli import app as twitter_app
from adapters.youtube.cli import app as youtube_app

VERSION = importlib.metadata.version("marketmenow")

console = Console()

app = typer.Typer(
    name="mmn",
    invoke_without_command=True,
    no_args_is_help=False,
    rich_markup_mode="rich",
    help="Open-source agentic marketing framework.",
)

app.add_typer(
    instagram_app,
    name="instagram",
    help="Instagram content generation and publishing.",
    rich_help_panel="Platforms",
)
app.add_typer(
    twitter_app,
    name="twitter",
    help="Twitter/X engagement and reply automation.",
    rich_help_panel="Platforms",
)
app.add_typer(
    twitter_app,
    name="x",
    help="Twitter/X engagement and reply automation (alias for `twitter`).",
    rich_help_panel="Platforms",
)
app.add_typer(
    linkedin_app,
    name="linkedin",
    help="LinkedIn organization page posting.",
    rich_help_panel="Platforms",
)
app.add_typer(
    facebook_app,
    name="facebook",
    help="Facebook posting and group engagement.",
    rich_help_panel="Platforms",
)
app.add_typer(
    reddit_app,
    name="reddit",
    help="Reddit engagement and comment automation.",
    rich_help_panel="Platforms",
)
app.add_typer(
    email_app,
    name="email",
    help="Email outreach via SMTP with CSV + Jinja2 templates.",
    rich_help_panel="Platforms",
)
app.add_typer(
    youtube_app,
    name="youtube",
    help="YouTube Shorts uploading and publishing.",
    rich_help_panel="Platforms",
)

# ── Banner ────────────────────────────────────────────────────────────


def _banner() -> Panel:
    logo = Text()
    logo.append("  __  __ ", style="bold cyan")
    logo.append("            _        _   ", style="bold cyan")
    logo.append("\n")
    logo.append(" |  \\/  |", style="bold cyan")
    logo.append(" __ _ _ __| | _____| |_ ", style="bold cyan")
    logo.append("\n")
    logo.append(" | |\\/| |", style="bold cyan")
    logo.append("/ _` | '__| |/ / _ \\ __|", style="bold cyan")
    logo.append("\n")
    logo.append(" | |  | |", style="bold magenta")
    logo.append(" (_| | |  |   <  __/ |_ ", style="bold magenta")
    logo.append("\n")
    logo.append(" |_|  |_|", style="bold magenta")
    logo.append("\\__,_|_|  |_|\\_\\___|\\__|", style="bold magenta")
    logo.append("\n")
    logo.append("  __  __      _   _                   ", style="bold magenta")
    logo.append("\n")
    logo.append(" |  \\/  | ___| \\ | | _____      __", style="bold yellow")
    logo.append("\n")
    logo.append(" | |\\/| |/ _ \\  \\| |/ _ \\ \\ /\\ / /", style="bold yellow")
    logo.append("\n")
    logo.append(" | |  | |  __/ |\\  | (_) \\ V  V / ", style="bold yellow")
    logo.append("\n")
    logo.append(" |_|  |_|\\___|_| \\_|\\___/ \\_/\\_/  ", style="bold yellow")
    logo.append("\n\n", style="default")
    logo.append(f"  v{VERSION}", style="dim")
    logo.append("  |  ", style="dim")
    logo.append("Agentic Marketing Framework", style="italic")
    logo.append("  |  ", style="dim")
    logo.append("MIT License", style="dim green")

    return Panel(
        logo,
        border_style="bright_blue",
        padding=(1, 2),
    )


@app.callback()
def main(ctx: typer.Context) -> None:
    """Open-source agentic marketing framework.

    Automate content creation, publishing, and engagement across
    Instagram, Twitter/X, LinkedIn, Reddit, YouTube, and Email.

    \b
    Quick start:
      mmn workflows          List available workflows
      mmn run <workflow>     Run a marketing workflow
      mmn auth <platform>   Authenticate with a platform
    """
    if ctx.invoked_subcommand is None:
        console.print(_banner())
        console.print()
        console.print("  Run [bold cyan]mmn --help[/] to see available commands.")
        console.print("  Run [bold cyan]mmn workflows[/] to list marketing workflows.\n")


# ── mmn run ───────────────────────────────────────────────────────────


def _parse_extra_args(args: list[str]) -> dict[str, str | bool]:
    """Parse ``--key value`` and ``--flag`` pairs from extra CLI args."""
    params: dict[str, str | bool] = {}
    i = 0
    while i < len(args):
        token = args[i]
        if token.startswith("--"):
            key = token.lstrip("-").replace("-", "_")
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                params[key] = args[i + 1]
                i += 2
            else:
                params[key] = True
                i += 1
        elif token.startswith("-") and len(token) == 2:
            key = token.lstrip("-")
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                params[key] = args[i + 1]
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    return params


def _print_workflow_help(workflow: object) -> None:
    """Print detailed help for a single workflow."""
    from marketmenow.core.workflow import ParamType, Workflow

    wf: Workflow = workflow  # type: ignore[assignment]
    console.print()
    console.print(Panel(f"[bold]{wf.name}[/bold]\n\n{wf.description}", border_style="cyan"))

    if wf.steps:
        console.print()
        console.print("[bold]Pipeline steps:[/bold]")
        for i, step in enumerate(wf.steps, 1):
            console.print(f"  [cyan]{i}.[/cyan] {step.name} -- {step.description}")

    if wf.params:
        console.print()
        table = Table(title="Parameters", show_header=True, border_style="dim")
        table.add_column("Option", style="bold cyan", min_width=20)
        table.add_column("Type", style="dim", width=8)
        table.add_column("Default", width=12)
        table.add_column("Description", min_width=30)

        for p in wf.params:
            flag = f"--{p.name.replace('_', '-')}"
            if p.short:
                flag = f"{p.short}, {flag}"
            if p.required:
                flag += " [red]*[/red]"
            type_str = p.type.value
            if p.type == ParamType.BOOL:
                type_str = "flag"
            default_str = str(p.default) if p.default is not None else ""
            table.add_row(flag, type_str, default_str, p.help)

        console.print(table)

    console.print()
    console.print("[dim]Run with:[/dim]")
    console.print(f"  mmn run {wf.name} [bold]--key value[/bold] ...")
    console.print()


@app.command(
    "run",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": True,
        "ignore_unknown_options": True,
    },
    rich_help_panel="Workflows",
)
def run_workflow(
    ctx: typer.Context,
    name: str = typer.Argument(help="Workflow name (see [bold]mmn workflows[/bold])"),
    set_param: list[str] | None = typer.Option(
        None,
        "--set",
        "-s",
        help="Pass a parameter as key=value (repeatable)",
    ),
    info: bool = typer.Option(
        False,
        "--info",
        help="Show detailed help for this workflow",
    ),
) -> None:
    """Run a marketing workflow by name.

    \b
    Parameters can be passed two ways:
      mmn run instagram-reel --template can_ai_grade_this
      mmn run instagram-reel --set template=can_ai_grade_this

    \b
    Examples:
      mmn run instagram-reel --template can_ai_grade_this --tts kokoro
      mmn run twitter-thread --topic "AI in marketing"
      mmn run twitter-engage --headless --max-replies 10
      mmn run email-outreach --template invite.html --to you@example.com
      mmn run linkedin-post --count 3 --dry-run
    """
    from marketmenow.core.workflow import ParamType
    from marketmenow.core.workflow_registry import build_workflow_registry

    registry = build_workflow_registry()

    try:
        wf = registry.get(name)
    except Exception as exc:
        console.print(f"[red]Unknown workflow:[/red] {name}")
        console.print("[dim]Run `mmn workflows` to see available workflows.[/dim]")
        raise typer.Exit(1) from exc

    if info:
        _print_workflow_help(wf)
        raise typer.Exit(0)

    params: dict[str, str | int | float | bool] = {}

    for item in set_param or []:
        key, _, val = item.partition("=")
        params[key.strip().replace("-", "_")] = val.strip()

    extra = _parse_extra_args(ctx.args)
    for key, val in extra.items():
        params[key.replace("-", "_")] = val

    for p in wf.params:
        if p.name in params:
            raw = params[p.name]
            if p.type == ParamType.INT:
                params[p.name] = int(raw)
            elif p.type == ParamType.FLOAT:
                params[p.name] = float(raw)
            elif p.type == ParamType.BOOL and isinstance(raw, str):
                params[p.name] = raw.lower() in ("true", "1", "yes")
        elif p.default is not None:
            params[p.name] = p.default
        elif p.required:
            console.print(f"[red]Missing required parameter:[/red] --{p.name.replace('_', '-')}")
            console.print(f"[dim]Run `mmn run {name} --info` for details.[/dim]")
            raise typer.Exit(1)

    console.print()
    console.print(
        Panel(
            f"[bold]{wf.name}[/bold] -- {wf.description}",
            border_style="bright_blue",
        )
    )

    result = asyncio.run(wf.run(params, console=console))

    console.print()
    if result.success:
        console.print(
            Panel(
                f"[bold green]Workflow '{wf.name}' completed successfully.[/bold green]",
                border_style="green",
            )
        )
    else:
        failed = [o for o in result.outcomes if not o.success]
        msg = "\n".join(f"  {o.step_name}: {o.error}" for o in failed)
        console.print(
            Panel(
                f"[bold red]Workflow '{wf.name}' failed.[/bold red]\n\n{msg}",
                border_style="red",
            )
        )
        raise typer.Exit(1)


# ── mmn workflows ─────────────────────────────────────────────────────


@app.command("workflows", rich_help_panel="Workflows")
def list_workflows() -> None:
    """List all available marketing workflows."""
    from marketmenow.core.workflow_registry import build_workflow_registry

    registry = build_workflow_registry()
    workflows = registry.list_all()

    if not workflows:
        console.print("[yellow]No workflows registered.[/yellow]")
        raise typer.Exit(0)

    console.print()
    table = Table(
        title="Available Workflows",
        title_style="bold",
        show_lines=True,
        padding=(0, 2),
    )
    table.add_column("Name", style="bold cyan", min_width=20)
    table.add_column("Steps", min_width=30)
    table.add_column("Description", min_width=35)

    for wf in workflows:
        steps_str = " -> ".join(s.name for s in wf.steps)
        table.add_row(wf.name, steps_str, wf.description)

    console.print(table)
    console.print()
    console.print("[dim]Run a workflow:[/dim]  mmn run [bold]<name>[/bold] [--key value ...]")
    console.print("[dim]Workflow help:[/dim]   mmn run [bold]<name>[/bold] --info")
    console.print()


# ── mmn auth ──────────────────────────────────────────────────────────

auth_app = typer.Typer(
    name="auth",
    help="Authenticate with a platform.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(auth_app, name="auth", rich_help_panel="Setup")


@auth_app.command("twitter")
def auth_twitter(
    force: bool = typer.Option(False, "--force", help="Skip session check and log in fresh"),
    cookies: bool = typer.Option(
        False, "--cookies", help="Log in by injecting auth_token and ct0 cookies"
    ),
) -> None:
    """Create a Twitter/X browser session.

    \b
    Two methods:
      mmn auth twitter --cookies   Inject auth_token + ct0 from your browser
      mmn auth twitter             Opens Chrome to x.com -- log in manually
    """
    from adapters.twitter.browser import StealthBrowser
    from adapters.twitter.settings import TwitterSettings

    settings = TwitterSettings()

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


@auth_app.command("linkedin")
def auth_linkedin(
    force: bool = typer.Option(False, "--force", help="Skip session check"),
    cookies: bool = typer.Option(False, "--cookies", help="Log in by injecting li_at cookie"),
    oauth: bool = typer.Option(False, "--oauth", help="Run OAuth 2.0 flow for REST API token"),
    port: int = typer.Option(8337, "--port", help="Local port for OAuth callback"),
) -> None:
    """Authenticate with LinkedIn.

    \b
    Three methods:
      mmn auth linkedin --oauth     OAuth 2.0 for REST API (recommended)
      mmn auth linkedin --cookies   Inject li_at cookie
      mmn auth linkedin             Opens Chrome -- log in manually
    """
    if oauth:
        from adapters.linkedin.cli import auth as linkedin_oauth

        linkedin_oauth(port=port)
        return

    from adapters.linkedin.browser import LinkedInBrowser
    from adapters.linkedin.settings import LinkedInSettings

    settings = LinkedInSettings()

    async def _run() -> None:
        browser = LinkedInBrowser(
            session_path=settings.linkedin_session_path,
            user_data_dir=settings.linkedin_user_data_dir,
            headless=False,
            slow_mo_ms=settings.slow_mo_ms,
            proxy_url=settings.proxy_url,
            viewport_width=settings.viewport_width,
            viewport_height=settings.viewport_height,
            organization_id=settings.linkedin_organization_id,
        )
        async with browser:
            if not force and not cookies:
                typer.echo("Checking existing session...")
                if await browser.is_logged_in():
                    typer.echo("Already logged in! Session is valid.")
                    return

            if cookies:
                li_at = settings.linkedin_li_at
                if not li_at:
                    li_at = typer.prompt("li_at cookie value")
                await browser.login_with_cookie(li_at)
                typer.echo("Cookie login successful. Session saved.")
            else:
                typer.echo(
                    "\nA browser window will open to linkedin.com.\n"
                    "Please log in manually (you have 5 minutes).\n"
                    "The session will be saved once you reach the feed.\n"
                )
                await browser.login_manual()
                typer.echo("Login successful. Session saved.")

    asyncio.run(_run())


@auth_app.command("youtube")
def auth_youtube() -> None:
    """Run the OAuth2 flow for a YouTube refresh token.

    Requires YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env.
    Opens a browser for consent, then prints the refresh token.
    """
    from adapters.youtube.cli import youtube_auth

    youtube_auth()


# ── mmn distribute ────────────────────────────────────────────────────


@app.command(rich_help_panel="Utilities")
def distribute(
    content_json: Path = typer.Option(
        ...,
        "--content-json",
        "-c",
        help="Path to a JSON file containing serialised BaseContent",
        exists=True,
        readable=True,
    ),
    only: str = typer.Option(
        "",
        "--only",
        help="Comma-separated platform filter (overrides default routing)",
    ),
) -> None:
    """Distribute pre-created content to all mapped platforms.

    The JSON file must contain a serialised BaseContent subclass
    (VideoPost, ImagePost, Thread, etc.) with a valid ``modality`` field.
    """
    import json
    from typing import Annotated

    from pydantic import Discriminator, Tag, TypeAdapter

    from marketmenow.models.content import (
        Article,
        ContentModality,
        DirectMessage,
        Document,
        ImagePost,
        Reply,
        TextPost,
        Thread,
        VideoPost,
    )

    def _discriminator(raw: dict[str, object]) -> str:
        return str(raw.get("modality", ""))

    AnyContent = Annotated[
        Annotated[VideoPost, Tag(ContentModality.VIDEO.value)]
        | Annotated[ImagePost, Tag(ContentModality.IMAGE.value)]
        | Annotated[Thread, Tag(ContentModality.THREAD.value)]
        | Annotated[DirectMessage, Tag(ContentModality.DIRECT_MESSAGE.value)]
        | Annotated[Reply, Tag(ContentModality.REPLY.value)]
        | Annotated[TextPost, Tag(ContentModality.TEXT_POST.value)]
        | Annotated[Document, Tag(ContentModality.DOCUMENT.value)]
        | Annotated[Article, Tag(ContentModality.ARTICLE.value)],
        Discriminator(_discriminator),
    ]

    adapter = TypeAdapter(AnyContent)
    raw = json.loads(content_json.read_text())
    content = adapter.validate_python(raw)

    console.print(f"[bold]Loaded:[/bold] {content.modality.value} (id={content.id})")

    from marketmenow.core.distribute_cli import distribute_content

    asyncio.run(distribute_content(content, console, only=only or None))


# ── mmn platforms ─────────────────────────────────────────────────────


@app.command(rich_help_panel="Info")
def platforms() -> None:
    """List all supported platforms and their content modalities."""
    table = Table(
        title="Platform Support",
        title_style="bold",
        show_lines=True,
        padding=(0, 2),
    )
    table.add_column("Platform", style="bold cyan", min_width=16)
    table.add_column("Status", min_width=14)
    table.add_column("Modalities", min_width=30)

    table.add_row("Instagram", "[green]Active[/]", "Videos, Images")
    table.add_row("X / Twitter", "[green]Active[/]", "Replies, Threads")
    table.add_row(
        "Instagram",
        "[green]Implemented[/]",
        "Videos, Images",
        "mmn instagram",
    )
    table.add_row(
        "X / Twitter",
        "[green]Implemented[/]",
        "Replies, Threads",
        "mmn twitter",
    )
    table.add_row(
        "LinkedIn",
        "[green]Implemented[/]",
        "Text, Images, Videos, Documents, Articles, Polls",
        "mmn linkedin",
    )
    table.add_row(
        "Facebook",
        "[green]Implemented[/]",
        "Text, Images, Videos, Group Posts",
        "mmn facebook",
    )
    table.add_row("TikTok", "[yellow]Planned[/]", "Reels", "")
    table.add_row(
        "YouTube Shorts",
        "[green]Implemented[/]",
        "Shorts (Videos)",
        "mmn youtube",
    )
    table.add_row(
        "Email / SMTP",
        "[green]Implemented[/]",
        "Bulk outreach (CSV + templates)",
        "mmn email",
    )
    table.add_row("Threads (Meta)", "[yellow]Planned[/]", "Threads", "")
    table.add_row("Pinterest", "[yellow]Planned[/]", "Carousels", "")
    table.add_row("Bluesky", "[yellow]Planned[/]", "Threads", "")
    table.add_row(
        "Reddit",
        "[green]Implemented[/]",
        "Comments, Replies",
        "mmn reddit",
    )
    table.add_row("Reddit", "[green]Active[/]", "Comments, Replies")
    table.add_row("YouTube Shorts", "[green]Active[/]", "Shorts (Videos)")
    table.add_row("Email / SMTP", "[green]Active[/]", "Bulk outreach (CSV + templates)")
    table.add_row("Facebook", "[yellow]Planned[/]", "Reels, Carousels, DMs")
    table.add_row("TikTok", "[yellow]Planned[/]", "Reels")
    table.add_row("Threads (Meta)", "[yellow]Planned[/]", "Threads")
    table.add_row("Pinterest", "[yellow]Planned[/]", "Carousels")
    table.add_row("Bluesky", "[yellow]Planned[/]", "Threads")
    table.add_row("WhatsApp Business", "[yellow]Planned[/]", "Direct Messages")

    console.print()
    console.print(table)
    console.print()


# ── mmn version ───────────────────────────────────────────────────────


@app.command(rich_help_panel="Info")
def version() -> None:
    """Show the MarketMeNow version."""
    console.print(f"[bold]marketmenow[/bold] [cyan]{VERSION}[/cyan]")


# ── Hidden adapter CLI groups (used by web frontend subprocess calls) ──

app.add_typer(instagram_app, name="instagram", hidden=True)
app.add_typer(twitter_app, name="twitter", hidden=True)
app.add_typer(twitter_app, name="x", hidden=True)
app.add_typer(linkedin_app, name="linkedin", hidden=True)
app.add_typer(reddit_app, name="reddit", hidden=True)
app.add_typer(email_app, name="email", hidden=True)
app.add_typer(youtube_app, name="youtube", hidden=True)
app.add_typer(reel_app, name="reel", hidden=True)
app.add_typer(carousel_app, name="carousel", hidden=True)


if __name__ == "__main__":
    app()
