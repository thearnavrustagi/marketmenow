from __future__ import annotations

import importlib.metadata
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from adapters.email.cli import app as email_app
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

app.add_typer(
    reel_app,
    name="reel",
    help="Reel generation (shortcut for instagram reel).",
    rich_help_panel="Shortcuts",
)
app.add_typer(
    carousel_app,
    name="carousel",
    help="Carousel generation (shortcut for instagram carousel).",
    rich_help_panel="Shortcuts",
)


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
def main(
    ctx: typer.Context,
) -> None:
    """Open-source agentic marketing framework.

    Automate content creation, publishing, and engagement across
    Instagram, Twitter/X, LinkedIn, and more.
    """
    if ctx.invoked_subcommand is None:
        console.print(_banner())
        console.print()
        console.print("  Run [bold cyan]mmn --help[/] to see available commands.\n")


@app.command(rich_help_panel="Distribution")
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
    import asyncio
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
        modality = raw.get("modality", "")
        return str(modality)

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


@app.command(rich_help_panel="Info")
def version() -> None:
    """Show the MarketMeNow version."""
    console.print(f"[bold]marketmenow[/bold] [cyan]{VERSION}[/cyan]")


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
    table.add_column("Entry Point", style="dim", min_width=18)

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
    table.add_row("Facebook", "[yellow]Planned[/]", "Reels, Carousels, DMs", "")
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
    table.add_row("WhatsApp Business", "[yellow]Planned[/]", "Direct Messages", "")

    console.print()
    console.print(table)
    console.print()


if __name__ == "__main__":
    app()
