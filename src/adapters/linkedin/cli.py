from __future__ import annotations

import asyncio
import contextlib
import logging
import mimetypes
import random
import time
from collections.abc import AsyncIterator
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from marketmenow.models.content import (
    Article,
    Document,
    ImagePost,
    MediaAsset,
    Poll,
    TextPost,
    VideoPost,
)
from marketmenow.normaliser import ContentNormaliser
from marketmenow.registry import PlatformBundle

from . import create_linkedin_bundle
from .api_adapter import LinkedInAPIAdapter
from .browser import LinkedInBrowser
from .content_generator import GeneratedPost, LinkedInContentGenerator
from .settings import LinkedInSettings

app = typer.Typer(
    name="mmn-linkedin",
    help="MarketMeNow LinkedIn posting CLI",
    no_args_is_help=True,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
console = Console()


def _settings() -> LinkedInSettings:
    return LinkedInSettings()


def _mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _make_browser(settings: LinkedInSettings) -> LinkedInBrowser:
    return LinkedInBrowser(
        session_path=settings.linkedin_session_path,
        user_data_dir=settings.linkedin_user_data_dir,
        headless=settings.headless,
        slow_mo_ms=settings.slow_mo_ms,
        proxy_url=settings.proxy_url,
        viewport_width=settings.viewport_width,
        viewport_height=settings.viewport_height,
        organization_id=settings.linkedin_organization_id,
    )


@contextlib.asynccontextmanager
async def _open_bundle(settings: LinkedInSettings) -> AsyncIterator[PlatformBundle]:
    """Create a bundle and handle lifecycle for both API and browser modes."""
    bundle = create_linkedin_bundle(settings)

    if settings.use_api:
        try:
            yield bundle
        finally:
            adapter = bundle.adapter
            if isinstance(adapter, LinkedInAPIAdapter):
                await adapter.close()
    else:
        browser: LinkedInBrowser = bundle.adapter._browser  # type: ignore[attr-defined]
        async with browser:
            if not await browser.is_logged_in():
                li_at = settings.linkedin_li_at
                if li_at:
                    await browser.login_with_cookie(li_at)
                else:
                    console.print(
                        "[red]Not logged in. Run `mmn linkedin login` first,[/red]\n"
                        "[red]or set LINKEDIN_LI_AT / LINKEDIN_ACCESS_TOKEN in .env.[/red]"
                    )
                    raise typer.Exit(1)
            yield bundle


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
        help="Log in by injecting li_at cookie",
    ),
) -> None:
    """Create a LinkedIn session for future commands.

    Two methods:

      mmn linkedin login --cookies    Inject li_at from your browser
                                      (set LINKEDIN_LI_AT in .env,
                                       or you'll be prompted).

      mmn linkedin login              Opens Chrome to linkedin.com --
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


@app.command()
def auth(
    port: int = typer.Option(
        8337,
        "--port",
        help="Local port for the OAuth callback server",
    ),
) -> None:
    """Authenticate with the LinkedIn REST API via OAuth 2.0.

    Opens your browser to LinkedIn's authorization page. After you
    approve, LinkedIn redirects to a local server that exchanges the
    authorization code for an access token and writes it to .env.

    Requires LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env.
    """
    import re
    import secrets
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    import httpx

    settings = _settings()
    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        console.print(
            "[red]Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env first.\n"
            "Get them from https://linkedin.com/developers/apps[/red]"
        )
        raise typer.Exit(1)

    redirect_uri = f"http://localhost:{port}/callback"
    state = secrets.token_urlsafe(16)

    scopes = "profile w_member_social"

    auth_url = (
        "https://www.linkedin.com/oauth/v2/authorization"
        f"?response_type=code"
        f"&client_id={settings.linkedin_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
        f"&scope={scopes}"
    )

    captured: dict[str, str] = {}

    class _Handler(BaseHTTPRequestHandler):
        def _send_html(self, code: int, body: str) -> None:
            payload = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            qs = parse_qs(urlparse(self.path).query)
            if qs.get("state", [None])[0] != state:
                self._send_html(400, "<h2>State mismatch</h2>")
                return

            if "error" in qs:
                msg = qs.get("error_description", qs["error"])[0]
                captured["error"] = msg
                self._send_html(400, f"<h2>LinkedIn error</h2><p>{msg}</p>")
                return

            captured["code"] = qs["code"][0]
            self._send_html(
                200,
                "<html><body style='font-family:system-ui;text-align:center;"
                "padding:60px'><h2>Done! You can close this tab.</h2>"
                "<p>Go back to your terminal.</p></body></html>",
            )

        def log_message(self, *_args: object) -> None:
            pass

    console.print()
    console.print("[bold blue]Opening LinkedIn authorization page...[/bold blue]")
    console.print(f"[dim]Redirect URI: {redirect_uri}[/dim]")
    console.print(f"[dim]Scopes: {scopes}[/dim]")
    console.print()
    console.print(
        "[yellow]Make sure your LinkedIn app's Authorized redirect URLs "
        f"includes:[/yellow]\n  [bold]{redirect_uri}[/bold]"
    )
    console.print()

    webbrowser.open(auth_url)
    console.print("[dim]Waiting for callback...[/dim]")

    server = HTTPServer(("127.0.0.1", port), _Handler)
    server.handle_request()
    server.server_close()

    if "error" in captured:
        console.print(f"[red]Authorization failed: {captured['error']}[/red]")
        raise typer.Exit(1)

    if "code" not in captured:
        console.print("[red]No authorization code received.[/red]")
        raise typer.Exit(1)

    console.print("[dim]Exchanging code for access token...[/dim]")

    token_resp = httpx.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": captured["code"],
            "redirect_uri": redirect_uri,
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
        },
    )
    token_resp.raise_for_status()
    token_data = token_resp.json()
    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", "?")

    console.print(f"[green]Got access token[/green] (expires in {expires_in}s)")

    # Fetch person URN — try multiple endpoints since permissions vary.
    person_urn = ""
    auth_headers = {"Authorization": f"Bearer {access_token}"}
    versioned_headers = {
        **auth_headers,
        "LinkedIn-Version": settings.linkedin_api_version,
        "X-Restli-Protocol-Version": "2.0.0",
    }
    _me_endpoints = [
        ("https://api.linkedin.com/v2/userinfo", auth_headers, "sub"),
        ("https://api.linkedin.com/v2/me", auth_headers, "id"),
        ("https://api.linkedin.com/v2/me", versioned_headers, "id"),
    ]
    for url, hdrs, key in _me_endpoints:
        try:
            me_resp = httpx.get(url, headers=hdrs)
            if me_resp.status_code != 200:
                continue
            member_id = me_resp.json().get(key, "")
            if member_id:
                person_urn = f"urn:li:person:{member_id}"
                console.print(f"[green]Person URN:[/green] {person_urn}")
                break
        except Exception:
            continue

    if not person_urn and settings.linkedin_li_at:
        # Fallback: use the li_at cookie to hit LinkedIn's internal API.
        try:
            voyager_resp = httpx.get(
                "https://www.linkedin.com/voyager/api/me",
                headers={
                    "csrf-token": "ajax:0",
                    "cookie": f"li_at={settings.linkedin_li_at}; JSESSIONID=ajax:0",
                },
            )
            if voyager_resp.status_code == 200:
                plain_id = voyager_resp.json().get("plainId")
                if plain_id:
                    person_urn = f"urn:li:person:{plain_id}"
                    console.print(f"[green]Person URN (via cookie):[/green] {person_urn}")
        except Exception:
            pass

    if not person_urn:
        console.print(
            "[yellow]Could not auto-detect person URN.[/yellow]\n"
            "Set LINKEDIN_PERSON_URN=urn:li:person:<your_id> in .env manually.\n"
            "Find your ID: open linkedin.com/in/yourname, view page source, search 'publicIdentifier'."
        )

    # Write token + URN to .env.
    env_path = Path(".env")
    env_text = env_path.read_text() if env_path.exists() else ""

    def _set_env(text: str, key: str, value: str) -> str:
        pattern = rf"^{re.escape(key)}=.*$"
        if re.search(pattern, text, re.MULTILINE):
            return re.sub(pattern, f"{key}={value}", text, flags=re.MULTILINE)
        return text + f"\n{key}={value}\n"

    env_text = _set_env(env_text, "LINKEDIN_ACCESS_TOKEN", access_token)
    if person_urn:
        env_text = _set_env(env_text, "LINKEDIN_PERSON_URN", person_urn)
    env_path.write_text(env_text)

    console.print()
    console.print(
        Panel(
            f"[bold green]LinkedIn API authenticated![/bold green]\n\n"
            f"Token written to .env — all commands now use the REST API.\n"
            f"Token expires in ~{int(expires_in) // 86400} days.",
            title="LinkedIn OAuth",
            border_style="green",
        )
    )


@app.command()
def status() -> None:
    """Check LinkedIn connection status."""
    settings = _settings()

    table = Table(title="LinkedIn Status", show_header=False, border_style="bold")
    table.add_column("key", style="bold")
    table.add_column("value")

    table.add_row(
        "Mode",
        "[green]REST API[/green]" if settings.use_api else "[yellow]Browser[/yellow]",
    )
    table.add_row(
        "Access token",
        "[green]set[/green]" if settings.linkedin_access_token else "[dim]not set[/dim]",
    )
    table.add_row(
        "Author URN",
        settings.author_urn or "[dim]not set[/dim]",
    )
    table.add_row(
        "li_at cookie",
        "[green]set[/green]" if settings.linkedin_li_at else "[dim]not set[/dim]",
    )
    table.add_row("Session file", str(settings.linkedin_session_path))
    table.add_row(
        "Session exists",
        "[green]yes[/green]" if settings.linkedin_session_path.exists() else "[red]no[/red]",
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
        help="Video file to attach (browser mode only)",
        exists=True,
        readable=True,
    ),
    document: Path | None = typer.Option(
        None,
        "--document",
        "-d",
        help="Document file (PDF/PPT/DOCX) to attach (browser mode only)",
        exists=True,
        readable=True,
    ),
    doc_title: str | None = typer.Option(
        None,
        "--doc-title",
        help="Title for the document",
    ),
    article_url: str | None = typer.Option(
        None,
        "--article",
        "-a",
        help="Article / link URL to share",
    ),
    poll_question: str | None = typer.Option(
        None,
        "--poll",
        "-p",
        help="Poll question",
    ),
    poll_options: str | None = typer.Option(
        None,
        "--poll-options",
        help="Comma-separated poll answers, 2-4 options",
    ),
    poll_days: int = typer.Option(
        3,
        "--poll-days",
        help="Poll duration in days (1-14)",
        min=1,
        max=14,
    ),
    hashtags: str | None = typer.Option(
        None,
        "--hashtags",
        help="Comma-separated hashtags",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode (ignored in API mode)",
    ),
) -> None:
    """Publish a post to LinkedIn.

    Uses the REST API when LINKEDIN_ACCESS_TOKEN is set, otherwise falls
    back to the Playwright browser.

    Exactly one content type should be specified. If only --text is given,
    a text-only post is created. Combine --text with --image, --video,
    --document, --article, or --poll for rich content.
    """
    settings = _settings()
    if headless:
        settings = settings.model_copy(update={"headless": True})
    tag_list = [t.strip() for t in (hashtags or "").split(",") if t.strip()]

    content_flags = sum(
        [
            bool(image),
            bool(video),
            bool(document),
            bool(article_url),
            bool(poll_question),
        ]
    )
    if content_flags > 1:
        console.print(
            "[red]Specify only one of --image, --video, --document, --article, or --poll.[/red]"
        )
        raise typer.Exit(1)

    if (
        not text
        and not image
        and not video
        and not document
        and not article_url
        and not poll_question
    ):
        console.print("[red]Provide at least --text or a media/article/poll option.[/red]")
        raise typer.Exit(1)

    if poll_question and not poll_options:
        console.print("[red]--poll requires --poll-options (comma-separated, 2-4 choices).[/red]")
        raise typer.Exit(1)

    normaliser = ContentNormaliser()

    if image:
        assets = [MediaAsset(uri=str(p.resolve()), mime_type=_mime(p)) for p in image]
        model = ImagePost(images=assets, caption=text or "", hashtags=tag_list)
    elif video:
        asset = MediaAsset(uri=str(video.resolve()), mime_type=_mime(video))
        model = VideoPost(video=asset, caption=text or "", hashtags=tag_list)
    elif document:
        asset = MediaAsset(uri=str(document.resolve()), mime_type=_mime(document))
        model = Document(
            file=asset,
            title=doc_title or document.stem,
            caption=text or "",
            hashtags=tag_list,
        )
    elif article_url:
        model = Article(url=article_url, commentary=text or "", hashtags=tag_list)
    elif poll_question:
        choices = [o.strip() for o in (poll_options or "").split(",") if o.strip()]
        if len(choices) < 2 or len(choices) > 4:
            console.print("[red]Poll requires 2-4 options.[/red]")
            raise typer.Exit(1)
        model = Poll(
            question=poll_question,
            options=choices,
            duration_days=poll_days,
            commentary=text or "",
            hashtags=tag_list,
        )
    else:
        model = TextPost(body=text or "", hashtags=tag_list)

    normalised = normaliser.normalise(model)

    async def _run() -> None:
        async with _open_bundle(settings) as bundle:
            mode = "API" if settings.use_api else "browser"
            console.print(f"[dim]Mode: {mode}[/dim]")

            rendered = await bundle.renderer.render(normalised)
            result = await bundle.adapter.publish(rendered)

            if result.success:
                console.print()
                console.print(
                    Panel(
                        "[bold green]Published![/bold green]",
                        title="LinkedIn",
                        border_style="green",
                    )
                )
            else:
                console.print()
                console.print(
                    Panel(
                        f"[bold red]Publish failed[/bold red]\n\nError: {result.error_message}",
                        title="LinkedIn",
                        border_style="red",
                    )
                )
                raise typer.Exit(1)

    asyncio.run(_run())


# ── Batch AI command ──────────────────────────────────────────────────


def _build_plan_table(posts: list[GeneratedPost]) -> Table:
    table = Table(title="Generated Post Batch", show_header=True, border_style="bold")
    table.add_column("#", style="bold", width=3)
    table.add_column("Type", style="cyan", min_width=10)
    table.add_column("Preview", min_width=40, max_width=70)
    table.add_column("Hashtags", style="dim", min_width=20)

    for i, p in enumerate(posts, 1):
        if p.type == "poll":
            preview = f"[bold]{p.poll_question}[/bold]\n" + "\n".join(
                f"  - {o}" for o in p.poll_options
            )
            if p.body:
                preview += (
                    f"\n[dim]{p.body[:80]}...[/dim]"
                    if len(p.body) > 80
                    else f"\n[dim]{p.body}[/dim]"
                )
        elif p.type == "article":
            preview = f"[link]{p.article_url}[/link]\n{p.body[:100]}" if p.body else p.article_url
        else:
            preview = p.body[:120] + "..." if len(p.body) > 120 else p.body

        tags = " ".join(f"#{t}" for t in p.hashtags)
        table.add_row(str(i), p.type, preview, tags)

    return table


def _build_results_table(
    results: list[tuple[int, GeneratedPost, bool, str]],
) -> Table:
    table = Table(title="Posting Results", show_header=True, border_style="bold")
    table.add_column("#", style="bold", width=3)
    table.add_column("Type", style="cyan", min_width=10)
    table.add_column("Status", min_width=12)
    table.add_column("Details", style="dim", min_width=30)

    for idx, post, success, detail in results:
        status = "[green]Published[/green]" if success else "[red]Failed[/red]"
        table.add_row(str(idx), post.type, status, detail)

    return table


def _post_to_content_model(
    post: GeneratedPost,
) -> TextPost | Poll | Article:
    """Convert a GeneratedPost into the appropriate content model."""
    hashtags = [t.lstrip("#") for t in post.hashtags]

    if post.type == "poll":
        return Poll(
            question=post.poll_question,
            options=post.poll_options[:4],
            duration_days=3,
            commentary=post.body,
            hashtags=hashtags,
        )
    elif post.type == "article":
        return Article(
            url=post.article_url,
            commentary=post.body,
            hashtags=hashtags,
        )
    else:
        return TextPost(body=post.body, hashtags=hashtags)


@app.command(name="all")
def batch_post(
    count: int = typer.Option(
        5,
        "--count",
        "-n",
        help="Number of posts to generate",
        min=1,
        max=20,
    ),
    min_delay: int = typer.Option(
        300,
        "--min-delay",
        help="Minimum delay between posts in seconds",
    ),
    max_delay: int = typer.Option(
        600,
        "--max-delay",
        help="Maximum delay between posts in seconds",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run the browser in headless mode (ignored in API mode)",
    ),
    carousel: bool = typer.Option(
        False,
        "--carousel",
        help="Also generate and publish an AI carousel (Gemini + Imagen)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Generate and preview posts without publishing",
    ),
) -> None:
    """Generate a batch of AI-powered posts and publish them with human-like delays.

    Uses Gemini to create a mix of text posts, polls, and article shares,
    then posts them sequentially with 5-10 minute gaps to look natural.
    Add --carousel to also generate and post an AI image carousel.

    Set LINKEDIN_ACCESS_TOKEN in .env to use the REST API (recommended).
    Falls back to the Playwright browser if no token is set.
    """
    settings = _settings()
    if headless:
        settings = settings.model_copy(update={"headless": True})

    if not settings.vertex_ai_project:
        console.print(
            "[red]VERTEX_AI_PROJECT is not set in .env. "
            "Gemini is required for content generation.[/red]"
        )
        raise typer.Exit(1)

    async def _run() -> None:
        mode = "API" if settings.use_api else "browser"
        console.print()
        console.print(f"[bold blue]Generating content with Gemini...[/bold blue] [dim](mode: {mode})[/dim]")
        console.print()

        generator = LinkedInContentGenerator(settings)
        posts = await generator.generate_batch(count)

        console.print(_build_plan_table(posts))
        console.print()

        carousel_post: ImagePost | None = None
        if carousel:
            from adapters.instagram.carousel.orchestrator import CarouselOrchestrator
            from adapters.instagram.settings import InstagramSettings

            console.print("[bold blue]Generating carousel (Gemini + Imagen)...[/bold blue]")
            orch = CarouselOrchestrator(InstagramSettings())
            carousel_post = await orch.create_carousel()
            console.print(
                f"[green]Carousel ready:[/green] {len(carousel_post.images)} slides — "
                f"{carousel_post.caption[:80] + '...' if len(carousel_post.caption) > 80 else carousel_post.caption}"
            )
            console.print()

        if dry_run:
            dry_msg = "[bold yellow]Dry run — no posts published.[/bold yellow]"
            if carousel_post:
                dry_msg += (
                    f"\n[dim]Carousel would post {len(carousel_post.images)} slides.[/dim]"
                )
            console.print(Panel(dry_msg, border_style="yellow"))
            return

        normaliser = ContentNormaliser()
        results: list[tuple[int, GeneratedPost, bool, str]] = []

        async with _open_bundle(settings) as bundle:
            for i, post in enumerate(posts, 1):
                console.print(
                    f"\n[bold cyan]Publishing post {i}/{len(posts)}[/bold cyan] ({post.type})"
                )

                try:
                    model = _post_to_content_model(post)
                    normalised = normaliser.normalise(model)
                    rendered = await bundle.renderer.render(normalised)
                    result = await bundle.adapter.publish(rendered)

                    if result.success:
                        console.print(f"  [green]Post {i} published.[/green]")
                        results.append((i, post, True, "Published"))
                    else:
                        console.print(f"  [red]Post {i} failed: {result.error_message}[/red]")
                        results.append((i, post, False, result.error_message or "Unknown error"))
                except Exception as exc:
                    logger.exception("Post %d failed", i)
                    console.print(f"  [red]Post {i} error: {exc}[/red]")
                    results.append((i, post, False, str(exc)))

                if i < len(posts) or carousel_post:
                    delay = random.uniform(min_delay, max_delay)
                    _countdown(delay, i, len(posts))

            if carousel_post:
                console.print(
                    f"\n[bold cyan]Publishing carousel[/bold cyan] "
                    f"({len(carousel_post.images)} slides)"
                )
                try:
                    normalised = normaliser.normalise(carousel_post)
                    rendered = await bundle.renderer.render(normalised)
                    result = await bundle.adapter.publish(rendered)

                    if result.success:
                        console.print("  [green]Carousel published.[/green]")
                    else:
                        console.print(
                            f"  [red]Carousel failed: {result.error_message}[/red]"
                        )
                except Exception as exc:
                    logger.exception("Carousel publish failed")
                    console.print(f"  [red]Carousel error: {exc}[/red]")

        console.print()
        console.print(_build_results_table(results))

        successes = sum(1 for *_, ok, _ in results if ok)
        failures = len(results) - successes
        console.print()
        if failures == 0:
            console.print(
                Panel(
                    f"[bold green]All {successes} posts published.[/bold green]",
                    border_style="green",
                )
            )
        elif successes > 0:
            console.print(f"[yellow]{successes} published, {failures} failed.[/yellow]")
        else:
            console.print("[red]All posts failed.[/red]")

    asyncio.run(_run())


def _countdown(seconds: float, current: int, total: int) -> None:
    """Display a live countdown between posts."""
    end = time.monotonic() + seconds
    with Live(console=console, refresh_per_second=1) as live:
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            mins, secs = divmod(int(remaining), 60)
            text = Text()
            text.append(f"  Next post ({current + 1}/{total}) in ", style="dim")
            text.append(f"{mins:02d}:{secs:02d}", style="bold yellow")
            live.update(text)
            time.sleep(1)
