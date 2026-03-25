from __future__ import annotations

import asyncio
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Annotated
from uuid import uuid4

import httpx
import typer
from rich.console import Console

from .settings import TikTokSettings

app = typer.Typer(
    name="tiktok",
    help="TikTok video publishing.",
    no_args_is_help=True,
)

console = Console()

_TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
_TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_REDIRECT_PORT = 8091
_REDIRECT_URI = f"http://localhost:{_REDIRECT_PORT}/callback"


def _get_settings() -> TikTokSettings:
    return TikTokSettings()


@app.command("login")
def tiktok_login(
    cookies: bool = typer.Option(False, "--cookies", help="Inject sessionid cookie from .env"),
    force: bool = typer.Option(False, "--force", help="Skip session check and log in fresh"),
) -> None:
    """Log in to TikTok via browser for cookie-based posting.

    \b
    Two methods:
      mmn tiktok login --cookies   Inject sessionid from TIKTOK_SESSION_ID in .env
      mmn tiktok login             Opens Chrome to tiktok.com -- log in manually
    """
    asyncio.run(_tiktok_login_async(cookies, force))


async def _tiktok_login_async(cookies: bool, force: bool) -> None:
    from .browser import TikTokBrowser

    settings = _get_settings()

    browser = TikTokBrowser(
        session_path=settings.tiktok_session_path,
        user_data_dir=settings.tiktok_user_data_dir,
        headless=False,
        slow_mo_ms=settings.slow_mo_ms,
        proxy_url=settings.proxy_url,
        viewport_width=settings.viewport_width,
        viewport_height=settings.viewport_height,
    )

    async with browser:
        if not force and await browser.is_logged_in():
            console.print("[green]Already logged in to TikTok.[/green]")
            return

        if cookies:
            session_id = settings.tiktok_session_id
            if not session_id:
                console.print(
                    "[red]TIKTOK_SESSION_ID not set in .env. "
                    "Grab the sessionid cookie from DevTools > Application > Cookies > tiktok.com.[/red]"
                )
                raise typer.Exit(code=1)
            console.print("[bold blue]Injecting TikTok session cookie...[/bold blue]")
            await browser.login_with_cookies(session_id)
        else:
            console.print(
                "[bold blue]Opening TikTok -- please log in manually in the browser window.[/bold blue]"
            )
            await browser.login_manual()

    console.print("[green]TikTok login successful, session saved.[/green]")


@app.command("auth")
def tiktok_auth() -> None:
    """Run the TikTok OAuth 2.0 flow to obtain access and refresh tokens.

    Requires TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env.
    Opens a browser for consent, then prints the tokens.
    """
    settings = _get_settings()
    if not settings.tiktok_client_key or not settings.tiktok_client_secret:
        console.print("[red]Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env first.[/red]")
        raise typer.Exit(code=1)

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)

    auth_params = urllib.parse.urlencode(
        {
            "client_key": settings.tiktok_client_key,
            "response_type": "code",
            "scope": "video.publish,video.upload",
            "redirect_uri": _REDIRECT_URI,
            "state": state,
            "code_verifier": code_verifier,
        }
    )
    auth_url = f"{_TIKTOK_AUTH_URL}?{auth_params}"

    captured: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            captured["code"] = params.get("code", [""])[0]
            captured["state"] = params.get("state", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization complete. You can close this tab.</h2></body></html>"
            )

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("localhost", _REDIRECT_PORT), CallbackHandler)
    thread = Thread(target=server.handle_request, daemon=True)
    thread.start()

    console.print("[bold blue]Opening browser for TikTok OAuth2 consent...[/bold blue]")
    webbrowser.open(auth_url)

    thread.join(timeout=120)
    server.server_close()

    code = captured.get("code", "")
    received_state = captured.get("state", "")

    if not code:
        console.print("[red]No authorization code received. Try again.[/red]")
        raise typer.Exit(code=1)

    if received_state != state:
        console.print("[red]State mismatch — possible CSRF. Try again.[/red]")
        raise typer.Exit(code=1)

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            _TIKTOK_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": _REDIRECT_URI,
                "code_verifier": code_verifier,
            },
        )

    if not resp.is_success:
        console.print(f"[red]Token exchange failed: {resp.text}[/red]")
        raise typer.Exit(code=1)

    body = resp.json()
    access_token = body.get("access_token", "")
    refresh_token = body.get("refresh_token", "")

    if not access_token:
        console.print(f"[red]No access token in response: {body}[/red]")
        raise typer.Exit(code=1)

    console.print()
    console.print("[green]Authentication successful![/green]")
    console.print()
    console.print("[bold]Add these to your .env file:[/bold]")
    console.print(f"TIKTOK_ACCESS_TOKEN={access_token}")
    if refresh_token:
        console.print(f"TIKTOK_REFRESH_TOKEN={refresh_token}")


@app.command("upload")
def tiktok_upload(
    video: Annotated[Path, typer.Argument(help="Path to the video file (MP4)")],
    title: Annotated[str, typer.Option(help="Video caption/title")] = "",
    hashtags: Annotated[str | None, typer.Option(help="Comma-separated hashtags")] = None,
    privacy: Annotated[
        str,
        typer.Option(
            help="Privacy: PUBLIC_TO_EVERYONE, FOLLOWER_OF_CREATOR, MUTUAL_FOLLOW_FRIENDS, or SELF_ONLY"
        ),
    ] = "",
) -> None:
    """Upload a local video to TikTok."""
    asyncio.run(_tiktok_upload_async(video, title, hashtags, privacy))


async def _tiktok_upload_async(
    video: Path,
    title: str,
    hashtags: str | None,
    privacy: str,
) -> None:
    from marketmenow.core.pipeline import ContentPipeline
    from marketmenow.models.content import MediaAsset, VideoPost
    from marketmenow.registry import AdapterRegistry

    from . import create_tiktok_bundle

    settings = _get_settings()
    if not settings.tiktok_access_token and not settings.tiktok_session_id:
        console.print(
            "[red]Neither TIKTOK_ACCESS_TOKEN nor TIKTOK_SESSION_ID is set. "
            "Run `mmn tiktok auth` or `mmn tiktok login --cookies` first.[/red]"
        )
        raise typer.Exit(code=1)

    if not video.exists():
        console.print(f"[red]Video file not found: {video}[/red]")
        raise typer.Exit(code=1)

    tags = [t.strip() for t in hashtags.split(",")] if hashtags else []
    caption = title or ""

    video_post = VideoPost(
        id=uuid4(),
        video=MediaAsset(uri=str(video.resolve()), mime_type="video/mp4"),
        caption=caption,
        hashtags=tags,
    )

    bundle = create_tiktok_bundle(settings)
    if privacy:
        bundle.adapter._default_privacy = privacy  # type: ignore[attr-defined]

    registry = AdapterRegistry()
    registry.register(bundle)

    pipeline = ContentPipeline(registry)
    with console.status("[bold blue]Uploading to TikTok..."):
        result = await pipeline.execute(video_post, "tiktok")

    if result.success:  # type: ignore[union-attr]
        console.print(f"[green]Published to TikTok![/green] publish_id={result.remote_post_id}")  # type: ignore[union-attr]
    else:
        console.print(f"[red]Upload failed:[/red] {result.error_message}")  # type: ignore[union-attr]
