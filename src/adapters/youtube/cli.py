from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from rich.console import Console

from .settings import YouTubeSettings

app = typer.Typer(
    name="youtube",
    help="YouTube Shorts generation and publishing.",
    no_args_is_help=True,
)

console = Console()


def _get_settings() -> YouTubeSettings:
    return YouTubeSettings()


@app.command("auth")
def youtube_auth() -> None:
    """Run the OAuth2 flow to obtain a YouTube refresh token.

    Requires YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env.
    Opens a browser for consent, then prints the refresh token.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = _get_settings()
    if not settings.youtube_client_id or not settings.youtube_client_secret:
        console.print("[red]Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env first.[/red]")
        raise typer.Exit(code=1)

    client_config = {
        "installed": {
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(
        client_config,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )

    console.print("[bold blue]Opening browser for YouTube OAuth2 consent...[/bold blue]")
    creds = flow.run_local_server(port=8090, prompt="consent")

    console.print()
    console.print("[green]Authentication successful![/green]")
    console.print()
    console.print("[bold]Add this to your .env file:[/bold]")
    console.print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")


@app.command("upload")
def youtube_upload(
    video: Annotated[Path, typer.Argument(help="Path to the video file (MP4)")],
    title: Annotated[str, typer.Option(help="Video title")] = "",
    description: Annotated[str, typer.Option(help="Video description")] = "",
    hashtags: Annotated[str | None, typer.Option(help="Comma-separated hashtags")] = None,
    privacy: Annotated[
        str,
        typer.Option(help="Privacy status: public, unlisted, or private"),
    ] = "",
    category: Annotated[str, typer.Option(help="YouTube category ID")] = "",
) -> None:
    """Upload a local video as a YouTube Short."""
    asyncio.run(_youtube_upload_async(video, title, description, hashtags, privacy, category))


async def _youtube_upload_async(
    video: Path,
    title: str,
    description: str,
    hashtags: str | None,
    privacy: str,
    category: str,
) -> None:
    from marketmenow.models.content import MediaAsset, VideoPost

    settings = _get_settings()
    if not settings.youtube_refresh_token:
        console.print("[red]YOUTUBE_REFRESH_TOKEN not set. Run `mmn youtube auth` first.[/red]")
        raise typer.Exit(code=1)

    if not video.exists():
        console.print(f"[red]Video file not found: {video}[/red]")
        raise typer.Exit(code=1)

    tags = [t.strip() for t in hashtags.split(",")] if hashtags else []

    caption_parts = [p for p in [title, description] if p]
    caption = "\n\n".join(caption_parts) if caption_parts else ""

    meta: dict[str, str] = {}
    if title:
        meta["_yt_title"] = title

    video_post = VideoPost(
        id=uuid4(),
        video=MediaAsset(uri=str(video.resolve()), mime_type="video/mp4"),
        caption=caption,
        hashtags=tags,
        metadata=meta,
    )

    from marketmenow.core.pipeline import ContentPipeline
    from marketmenow.registry import AdapterRegistry

    from . import create_youtube_bundle

    bundle = create_youtube_bundle(settings)
    if privacy:
        bundle.adapter._default_privacy = privacy  # type: ignore[attr-defined]
    if category:
        bundle.adapter._default_category_id = category  # type: ignore[attr-defined]

    registry = AdapterRegistry()
    registry.register(bundle)

    pipeline = ContentPipeline(registry)
    with console.status("[bold blue]Uploading to YouTube Shorts..."):
        result = await pipeline.execute(video_post, "youtube")

    if result.success:  # type: ignore[union-attr]
        console.print(f"[green]Published![/green] {result.remote_url}")  # type: ignore[union-attr]
    else:
        console.print(f"[red]Upload failed:[/red] {result.error_message}")  # type: ignore[union-attr]
