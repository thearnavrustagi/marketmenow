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
from adapters.tiktok.cli import app as tiktok_app
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
app.add_typer(
    tiktok_app,
    name="tiktok",
    help="TikTok video publishing.",
    rich_help_panel="Platforms",
)

project_app = typer.Typer(name="project", help="Manage marketing projects.")
app.add_typer(project_app, name="project", rich_help_panel="Projects")

persona_app = typer.Typer(name="persona", help="Manage project personas.")
project_app.add_typer(persona_app, name="persona")


@project_app.command("add")
def project_add(
    slug: str = typer.Argument(help="Project slug (e.g. 'cookbot')"),
) -> None:
    """Create a new project with an interactive onboarding wizard."""
    from marketmenow.core.onboarding import run_onboarding
    from marketmenow.core.project_manager import ProjectManager

    pm = ProjectManager()
    result = run_onboarding(pm=pm, console=console, slug_override=slug)
    if not result:
        raise typer.Exit(1)


@project_app.command("list")
def project_list() -> None:
    """List all marketing projects."""
    from marketmenow.core.project_manager import ProjectManager

    pm = ProjectManager()
    projects = pm.list_projects()
    active = pm.get_active_project()

    if not projects:
        console.print(
            "[dim]No projects found. Run [bold]mmn project add <slug>[/bold] to create one.[/dim]"
        )
        return

    table = Table(title="Projects", show_header=True, border_style="dim")
    table.add_column("", width=2)
    table.add_column("Slug", style="bold cyan")
    table.add_column("Brand", style="white")
    table.add_column("URL", style="dim")

    for p in projects:
        marker = "►" if p.slug == active else ""
        table.add_row(marker, p.slug, p.brand.name, p.brand.url)

    console.print(table)


@project_app.command("use")
def project_use(
    slug: str = typer.Argument(help="Project slug to activate"),
) -> None:
    """Set the active project."""
    from marketmenow.core.project_manager import ProjectManager

    pm = ProjectManager()
    try:
        pm.set_active_project(slug)
    except FileNotFoundError as exc:
        console.print(f"[red]Project '{slug}' not found.[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] Active project set to: [bold]{slug}[/bold]")


@project_app.command("info")
def project_info(
    slug: str = typer.Argument("", help="Project slug (default: active project)"),
) -> None:
    """Show project details."""
    from marketmenow.core.project_manager import ProjectManager

    pm = ProjectManager()
    slug = slug or pm.get_active_project() or ""
    if not slug:
        console.print(
            "[red]No active project. Run [bold]mmn project use <slug>[/bold] first.[/red]"
        )
        raise typer.Exit(1)

    try:
        cfg = pm.load_project(slug)
    except FileNotFoundError as exc:
        console.print(f"[red]Project '{slug}' not found.[/red]")
        raise typer.Exit(1) from exc

    b = cfg.brand
    console.print(
        Panel(
            f"[bold]{b.name}[/bold]{b.logo_suffix}  •  {b.url}\n"
            f"{b.tagline}\n"
            f"Color: {b.color}  •  Logo: {b.logo_letter}{b.logo_suffix}\n\n"
            + (f"Target: {cfg.target_customer.description}\n" if cfg.target_customer else "")
            + f"Default persona: {cfg.default_persona}",
            title=f"Project: {slug}",
            border_style="cyan",
        )
    )

    personas = pm.list_personas(slug)
    if personas:
        console.print(f"\n[bold]Personas:[/bold] {', '.join(personas)}")

    proj_dir = pm.project_dir(slug)
    for sub in ("prompts", "targets", "templates/reels", "campaigns"):
        sub_path = proj_dir / sub
        if sub_path.is_dir():
            files = [f.name for f in sub_path.rglob("*.yaml") if f.is_file()]
            files.extend(f.name for f in sub_path.rglob("*.html") if f.is_file())
            if files:
                console.print(f"  [dim]{sub}/[/dim] {', '.join(sorted(files))}")


@persona_app.command("add")
def persona_add(
    name: str = typer.Argument(help="Persona name"),
) -> None:
    """Add a new persona to the active project."""
    from marketmenow.core.project_manager import ProjectManager
    from marketmenow.models.project import PersonaConfig

    pm = ProjectManager()
    slug = pm.get_active_project()
    if not slug:
        console.print(
            "[red]No active project. Run [bold]mmn project use <slug>[/bold] first.[/red]"
        )
        raise typer.Exit(1)

    description = typer.prompt("Description")
    voice = typer.prompt("Voice style")
    tone = typer.prompt("Tone")

    persona = PersonaConfig(name=name, description=description, voice=voice, tone=tone)
    path = pm.save_persona(slug, persona)
    console.print(f"[green]✓[/green] Persona saved to {path}")


@persona_app.command("list")
def persona_list() -> None:
    """List personas for the active project."""
    from marketmenow.core.project_manager import ProjectManager

    pm = ProjectManager()
    slug = pm.get_active_project()
    if not slug:
        console.print("[red]No active project.[/red]")
        raise typer.Exit(1)

    names = pm.list_personas(slug)
    if not names:
        console.print("[dim]No personas found.[/dim]")
        return

    table = Table(title=f"Personas — {slug}", show_header=True, border_style="dim")
    table.add_column("Name", style="bold cyan")
    for n in names:
        table.add_row(n)
    console.print(table)


# ── Campaigns ─────────────────────────────────────────────────────────

from marketmenow.core.campaign_cli import campaign_app  # noqa: E402

app.add_typer(campaign_app, name="campaign", rich_help_panel="Campaigns")

# ── Capsules ──────────────────────────────────────────────────────────

capsule_app = typer.Typer(name="capsule", help="Manage content capsules.")
app.add_typer(capsule_app, name="capsule", rich_help_panel="Content")


@capsule_app.command("list")
def capsule_list(
    slug: str = typer.Argument("", help="Project slug (default: active project)"),
) -> None:
    """List all content capsules for a project."""
    from marketmenow.core.capsule import CapsuleManager
    from marketmenow.core.project_manager import ProjectManager

    pm = ProjectManager()
    slug = slug or pm.get_active_project() or ""
    if not slug:
        console.print(
            "[red]No active project. Run [bold]mmn project use <slug>[/bold] first.[/red]"
        )
        raise typer.Exit(1)

    mgr = CapsuleManager()
    capsules = mgr.list_capsules(slug)

    if not capsules:
        console.print("[dim]No capsules found.[/dim]")
        return

    table = Table(title=f"Content Capsules — {slug}", show_header=True, border_style="dim")
    table.add_column("ID", style="bold cyan", min_width=24)
    table.add_column("Modality", style="white", width=10)
    table.add_column("Caption", style="dim", max_width=40)
    table.add_column("Published", style="green", width=10)

    for c in capsules:
        caption_preview = c.caption[:37] + "..." if len(c.caption) > 40 else c.caption
        pub_count = str(len(c.publications)) if c.publications else "-"
        table.add_row(c.capsule_id, c.modality, caption_preview, pub_count)

    console.print(table)


@capsule_app.command("info")
def capsule_info(
    capsule_id: str = typer.Argument(help="Capsule ID"),
    slug: str = typer.Option("", help="Project slug (default: active project)"),
) -> None:
    """Show details for a specific content capsule."""
    from marketmenow.core.capsule import CapsuleManager
    from marketmenow.core.project_manager import ProjectManager

    pm = ProjectManager()
    slug = slug or pm.get_active_project() or ""
    if not slug:
        console.print(
            "[red]No active project. Run [bold]mmn project use <slug>[/bold] first.[/red]"
        )
        raise typer.Exit(1)

    mgr = CapsuleManager()
    try:
        capsule = mgr.load(slug, capsule_id)
    except FileNotFoundError as exc:
        console.print(f"[red]Capsule '{capsule_id}' not found in project '{slug}'.[/red]")
        raise typer.Exit(1) from exc

    lines = [
        f"[bold]Capsule:[/bold] {capsule.capsule_id}",
        f"[bold]Modality:[/bold] {capsule.modality}",
        f"[bold]Created:[/bold] {capsule.created_at}",
    ]
    if capsule.template_id:
        lines.append(f"[bold]Template:[/bold] {capsule.template_id}")
    if capsule.caption:
        lines.append(f"[bold]Caption:[/bold] {capsule.caption[:100]}")
    if capsule.title:
        lines.append(f"[bold]Title:[/bold] {capsule.title}")
    if capsule.hashtags:
        lines.append(f"[bold]Hashtags:[/bold] {', '.join(capsule.hashtags)}")

    if capsule.media:
        lines.append("")
        lines.append("[bold]Media:[/bold]")
        for m in capsule.media:
            lines.append(f"  {m.role}: {m.path} ({m.mime_type})")

    if capsule.publications:
        lines.append("")
        lines.append("[bold]Publications:[/bold]")
        for pub in capsule.publications:
            lines.append(f"  {pub.platform}: {pub.remote_url} ({pub.published_at})")

    console.print(Panel("\n".join(lines), title="Capsule Details", border_style="cyan"))


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
    name: str = typer.Argument("", help="Workflow name (see [bold]mmn workflows[/bold])"),
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
    list_workflows: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List all available workflows",
    ),
    project: str = typer.Option(
        "", "--project", "-p", help="Project slug (default: active project)"
    ),
    persona: str = typer.Option("", "--persona", help="Persona name (default: project default)"),
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

    if list_workflows or not name:
        _show_workflows(registry)
        raise typer.Exit(0)

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

    proj_config = None
    persona_config = None
    try:
        from marketmenow.core.project_manager import ProjectManager

        pm = ProjectManager()
        proj_slug = project or pm.get_active_project()
        if proj_slug:
            proj_config = pm.load_project(proj_slug)
            persona_name = persona or proj_config.default_persona
            persona_config = pm.load_persona(proj_slug, persona_name)
            params["project"] = proj_slug
            params["persona"] = persona_name
    except Exception:
        pass

    console.print()
    console.print(
        Panel(
            f"[bold]{wf.name}[/bold] -- {wf.description}",
            border_style="bright_blue",
        )
    )

    result = asyncio.run(
        wf.run(params, console=console, project=proj_config, persona=persona_config)
    )

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


def _show_workflows(registry: object) -> None:
    """Print the workflow table from a WorkflowRegistry."""
    from marketmenow.core.workflow_registry import WorkflowRegistry

    reg: WorkflowRegistry = registry  # type: ignore[assignment]
    all_workflows = reg.list_all()

    if not all_workflows:
        console.print("[yellow]No workflows registered.[/yellow]")
        return

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

    for wf in all_workflows:
        steps_str = " -> ".join(s.name for s in wf.steps)
        table.add_row(wf.name, steps_str, wf.description)

    console.print(table)
    console.print()
    console.print("[dim]Run a workflow:[/dim]  mmn run [bold]<name>[/bold] [--key value ...]")
    console.print("[dim]Workflow help:[/dim]   mmn run [bold]<name>[/bold] --info")
    console.print()


@app.command("workflows", rich_help_panel="Workflows")
def list_workflows_cmd() -> None:
    """List all available marketing workflows."""
    from marketmenow.core.workflow_registry import build_workflow_registry

    registry = build_workflow_registry()
    _show_workflows(registry)


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


@auth_app.command("tiktok")
def auth_tiktok() -> None:
    """Run the TikTok OAuth 2.0 flow for access and refresh tokens.

    Requires TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env.
    Opens a browser for consent, then prints the tokens.
    """
    from adapters.tiktok.cli import tiktok_auth

    tiktok_auth()


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


# ── mmn heal ──────────────────────────────────────────────────────────


@app.command(rich_help_panel="Utilities")
def heal(
    fix: bool = typer.Option(True, "--fix/--no-fix", help="Prompt to auto-fix via Cursor agent"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full output"),
) -> None:
    """Run lint, format, and tests — then auto-fix failures with the Cursor agent."""
    import re
    import shutil
    import subprocess

    project_root = Path(__file__).resolve().parents[2]
    problems: list[str] = []

    # ── 1. Lint ──────────────────────────────────────────────────────
    console.print()
    console.print("[bold]Running ruff check...[/bold]")

    lint_result = subprocess.run(
        ["uv", "run", "ruff", "check", "src/", "tests/"],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    lint_output = lint_result.stdout + lint_result.stderr

    if lint_result.returncode == 0:
        console.print("[green]  Lint: all checks passed.[/green]")
    else:
        console.print("[red]  Lint: issues found.[/red]")
        if verbose:
            console.print(lint_output)

        console.print("  [dim]Auto-fixing safe issues...[/dim]")
        subprocess.run(
            ["uv", "run", "ruff", "check", "--fix", "src/", "tests/"],
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        recheck = subprocess.run(
            ["uv", "run", "ruff", "check", "src/", "tests/"],
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        if recheck.returncode == 0:
            console.print("  [green]All lint issues auto-fixed.[/green]")
        else:
            remaining = recheck.stdout + recheck.stderr
            problems.append(f"Ruff lint errors:\n{remaining}")
            console.print(f"  [red]{remaining.strip().splitlines()[-1]}[/red]")

    # ── 2. Format ────────────────────────────────────────────────────
    console.print()
    console.print("[bold]Running ruff format...[/bold]")

    fmt_check = subprocess.run(
        ["uv", "run", "ruff", "format", "--check", "src/", "tests/"],
        capture_output=True,
        text=True,
        cwd=project_root,
    )

    if fmt_check.returncode == 0:
        console.print("[green]  Format: all files formatted.[/green]")
    else:
        fmt_result = subprocess.run(
            ["uv", "run", "ruff", "format", "src/", "tests/"],
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        formatted = fmt_result.stdout + fmt_result.stderr
        count = sum(1 for line in formatted.splitlines() if "file" in line.lower())
        console.print(f"  [green]Reformatted {count or 'all'} files.[/green]")

    # ── 3. Tests ─────────────────────────────────────────────────────
    console.print()
    console.print("[bold]Running test suite...[/bold]\n")

    test_result = subprocess.run(
        ["uv", "run", "--extra", "dev", "pytest", "--tb=short", "-q"],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    test_output = test_result.stdout + test_result.stderr

    if test_result.returncode == 0:
        console.print(Panel("[bold green]All tests passed.[/bold green]", border_style="green"))
    else:
        if verbose:
            console.print(test_output)
            console.print()

        failures: list[dict[str, str]] = []
        current: dict[str, str] | None = None
        for line in test_output.splitlines():
            m = re.match(r"^FAILED\s+(\S+)", line)
            if m:
                failures.append({"test": m.group(1), "detail": ""})
                continue

            m2 = re.match(r"^(tests/\S+::\S+)", line)
            if m2 and not line.startswith("PASSED"):
                current = {"test": m2.group(1), "detail": ""}
                continue

            if current is not None:
                if line.strip() and not line.startswith("="):
                    current["detail"] += line + "\n"
                if line.startswith(("FAILED", "=")):
                    failures.append(current)
                    current = None

        if not failures:
            for line in test_output.splitlines():
                m = re.match(r"^(E\s+.+|FAILED .+|.*Error.*|.*assert.*)", line)
                if m:
                    failures.append({"test": "unknown", "detail": m.group(0)})

        table = Table(title="Test Failures", show_lines=True, border_style="red")
        table.add_column("#", style="bold", width=4)
        table.add_column("Test", style="bold cyan", min_width=30)
        table.add_column("Error", min_width=40)

        for i, f in enumerate(failures, 1):
            detail = f["detail"].strip()
            if len(detail) > 200:
                detail = detail[:200] + "..."
            table.add_row(str(i), f["test"], detail or "(see full output with --verbose)")

        console.print(table)
        console.print()

        summary_line = ""
        for line in reversed(test_output.splitlines()):
            if "failed" in line or "error" in line.lower():
                summary_line = line.strip()
                break
        if summary_line:
            console.print(f"[bold red]{summary_line}[/bold red]")
        console.print()

        test_names = " ".join(f["test"] for f in failures if f["test"] != "unknown")
        problems.append(
            f"{len(failures)} test failure(s): {test_names}\n\n"
            f"Pytest output:\n{test_output[-3000:]}"
        )

    # ── 4. Summary ───────────────────────────────────────────────────
    if not problems:
        console.print(
            Panel(
                "[bold green]Everything clean — lint, format, and tests all pass.[/bold green]",
                border_style="green",
            )
        )
        raise typer.Exit(0)

    if not fix:
        raise typer.Exit(1)

    if not shutil.which("agent"):
        console.print("[yellow]Cursor agent CLI not found on PATH.[/yellow]")
        console.print("[dim]Install it: curl https://cursor.com/install -fsS | bash[/dim]")
        raise typer.Exit(1)

    if not typer.confirm("Fix remaining issues with Cursor agent?"):
        raise typer.Exit(1)

    prompt = _build_heal_prompt(problems, project_root)

    console.print()
    console.print("[bold]Handing off to Cursor agent...[/bold]\n")

    subprocess.run(["agent", prompt], cwd=project_root)


def _build_heal_prompt(problems: list[str], project_root: Path) -> str:
    """Construct the prompt sent to the Cursor agent for auto-healing."""
    problem_block = "\n---\n".join(problems)

    return (
        "You are fixing failing pre-push checks for the MarketMeNow project.\n\n"
        "## Context\n"
        f"Project root: {project_root}\n"
        "Read CLAUDE.md and AGENTS.md for architecture rules before making changes.\n"
        "Key invariants: ports-and-adapters architecture, frozen Pydantic models, "
        "structural subtyping (typing.Protocol), async-first adapters.\n\n"
        "## Problems found\n\n"
        f"{problem_block}\n\n"
        "## Instructions\n\n"
        "1. Diagnose each failure — determine whether the bug is in source code, "
        "tests, or both. Fixing tests is fine when the test expectation is wrong "
        "(e.g. a new workflow was added but the expected-set was not updated). "
        "Do NOT weaken assertions or delete tests to hide real bugs.\n"
        "2. Fix all issues.\n"
        "3. Run `uv run --extra dev pytest --tb=short -q` to verify the fix.\n"
        "4. If tests still fail, diagnose the new failures and repeat from step 1. "
        "Keep iterating until the full test suite passes.\n"
        "5. Run `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/` "
        "to confirm lint and formatting are clean. Fix any issues.\n"
        "6. Once everything is green, stop.\n"
    )


# ── mmn feedback ─────────────────────────────────────────────────────


@app.command(rich_help_panel="Feedback")
def feedback(
    project: str = typer.Option("", "--project", "-p", help="Project slug (default: active)"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to look back"),
) -> None:
    """Analyze prior video performance and generate content guidelines from audience feedback."""
    asyncio.run(_feedback_async(project, days))


async def _feedback_async(project: str, days: int) -> None:
    from datetime import UTC, datetime, timedelta

    from adapters.instagram.settings import InstagramSettings
    from adapters.youtube.analytics import YouTubeAnalyticsFetcher
    from adapters.youtube.settings import YouTubeSettings
    from marketmenow.core.feedback.guideline_generator import GuidelineGenerator
    from marketmenow.core.feedback.orchestrator import FeedbackOrchestrator
    from marketmenow.core.feedback.sentiment import SentimentScorer
    from marketmenow.core.project_manager import ProjectManager
    from marketmenow.integrations.genai import configure_google_application_credentials

    settings = YouTubeSettings()
    if not settings.youtube_refresh_token:
        console.print("[red]YOUTUBE_REFRESH_TOKEN not set. Run `mmn auth youtube` first.[/red]")
        raise typer.Exit(code=1)

    ig_settings = InstagramSettings()
    configure_google_application_credentials(ig_settings.google_application_credentials)

    pm = ProjectManager()
    slug = project or pm.active_slug()
    if not slug:
        console.print("[red]No project specified and no active project set.[/red]")
        raise typer.Exit(code=1)

    fetcher = YouTubeAnalyticsFetcher(
        client_id=settings.youtube_client_id,
        client_secret=settings.youtube_client_secret,
        refresh_token=settings.youtube_refresh_token,
    )
    orch = FeedbackOrchestrator(
        fetcher=fetcher,
        sentiment_scorer=SentimentScorer(
            vertex_project=ig_settings.vertex_ai_project,
            vertex_location=ig_settings.vertex_ai_location,
        ),
        guideline_generator=GuidelineGenerator(
            vertex_project=ig_settings.vertex_ai_project,
            vertex_location=ig_settings.vertex_ai_location,
        ),
        project_slug=slug,
        project_root=Path.cwd(),
    )

    since = datetime.now(UTC) - timedelta(days=days)
    with console.status("[bold blue]Running feedback cycle..."):
        report = await orch.run_feedback_cycle(since=since)

    table = Table(title=f"Feedback Report ({slug})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Reels analyzed", str(report.reels_analyzed))
    table.add_row("New guidelines", str(report.new_guidelines_count))
    table.add_row("Avg sentiment", f"{report.avg_sentiment:.1f}/10")
    table.add_row("Flagged reels", str(len(report.flagged_reels)))
    console.print(table)

    if report.flagged_reels:
        console.print(f"\n[yellow]Flagged video IDs:[/yellow] {', '.join(report.flagged_reels)}")


# ── mmn index ────────────────────────────────────────────────────────


@app.command(rich_help_panel="Feedback")
def index(
    project: str = typer.Option("", "--project", "-p", help="Project slug (default: active)"),
    limit: int = typer.Option(200, "--limit", "-l", help="Max videos to index"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without saving"),
) -> None:
    """Retroactively index all prior videos, classify by template, and generate guidelines."""
    asyncio.run(_index_async(project, limit, dry_run))


async def _index_async(project: str, limit: int, dry_run: bool) -> None:
    import yaml

    from adapters.youtube.analytics import YouTubeAnalyticsFetcher
    from adapters.youtube.settings import YouTubeSettings
    from marketmenow.core.embedding_store import EmbeddingStore
    from marketmenow.core.feedback.classifier import TemplateCandidate, TemplateClassifier
    from marketmenow.core.feedback.guideline_generator import GuidelineGenerator
    from marketmenow.core.feedback.orchestrator import FeedbackOrchestrator
    from marketmenow.core.feedback.sentiment import SentimentScorer
    from marketmenow.core.project_manager import ProjectManager
    from marketmenow.core.reel_id import decode_reel_id

    settings = YouTubeSettings()
    if not settings.youtube_refresh_token:
        console.print("[red]YOUTUBE_REFRESH_TOKEN not set. Run `mmn auth youtube` first.[/red]")
        raise typer.Exit(code=1)

    pm = ProjectManager()
    slug = project or pm.active_slug()
    if not slug:
        console.print("[red]No project specified and no active project set.[/red]")
        raise typer.Exit(code=1)

    # Load templates for classification
    templates_dir = pm.project_dir(slug) / "templates" / "reels"
    template_candidates: list[TemplateCandidate] = []
    if templates_dir.is_dir():
        for tmpl_path in sorted(templates_dir.glob("*.yaml")):
            data = yaml.safe_load(tmpl_path.read_text(encoding="utf-8"))
            template_candidates.append(
                TemplateCandidate(
                    template_id=data.get("id", tmpl_path.stem),
                    name=data.get("name", tmpl_path.stem),
                    text=data.get("caption_template", ""),
                    hashtags=data.get("hashtags", []),
                )
            )

    # Set up classifier
    classifier: TemplateClassifier | None = None
    if template_candidates:
        try:
            store = EmbeddingStore()
            classifier = TemplateClassifier(store)
            with console.status("[bold blue]Embedding templates..."):
                await classifier.precompute_template_embeddings(template_candidates)
        except Exception as exc:
            console.print(f"[yellow]Template classifier unavailable: {exc}[/yellow]")
            classifier = None

    fetcher = YouTubeAnalyticsFetcher(
        client_id=settings.youtube_client_id,
        client_secret=settings.youtube_client_secret,
        refresh_token=settings.youtube_refresh_token,
    )

    # Fetch all videos
    with console.status(f"[bold blue]Fetching up to {limit} videos..."):
        videos = await fetcher.fetch_channel_videos(max_results=limit)

    if not videos:
        console.print("[yellow]No videos found on channel.[/yellow]")
        return

    console.print(f"Found {len(videos)} videos.")

    # Classify and display
    table = Table(title=f"Reel Index ({slug})")
    table.add_column("#", style="dim")
    table.add_column("Title")
    table.add_column("Template", style="cyan")
    table.add_column("Confidence", style="blue")
    table.add_column("Has ID", style="green")

    classified_count = 0
    for i, video in enumerate(videos, 1):
        title = video.get("title", "")[:50]
        desc = video.get("description", "")

        # Try decode first
        identifier = decode_reel_id(desc)
        if identifier:
            table.add_row(str(i), title, f"(ID: {identifier.template_type_id[:8]})", "-", "Y")
            classified_count += 1
        elif classifier:
            result = await classifier.classify(video.get("title", ""), desc)
            tmpl_display = result.template_id if result.is_confident else f"({result.template_id}?)"
            conf_display = f"{result.confidence:.0%}"
            table.add_row(str(i), title, tmpl_display, conf_display, "N")
            if result.is_confident:
                classified_count += 1
        else:
            table.add_row(str(i), title, "?", "-", "N")

    console.print(table)
    console.print(f"\nClassified: {classified_count}/{len(videos)}")

    if dry_run:
        console.print("[yellow]Dry run — no data saved.[/yellow]")
        return

    # Run full feedback cycle to persist index and generate guidelines
    orch = FeedbackOrchestrator(
        fetcher=fetcher,
        sentiment_scorer=SentimentScorer(),
        guideline_generator=GuidelineGenerator(),
        project_slug=slug,
        project_root=Path.cwd(),
    )

    with console.status("[bold blue]Indexing and analyzing..."):
        report = await orch.run_feedback_cycle(max_videos=limit)

    console.print(
        f"[green]Done![/green] Analyzed {report.reels_analyzed} reels, "
        f"generated {report.new_guidelines_count} guidelines."
    )


# ── Hidden adapter CLI groups (used by web frontend subprocess calls) ──

app.add_typer(instagram_app, name="instagram", hidden=True)
app.add_typer(twitter_app, name="twitter", hidden=True)
app.add_typer(twitter_app, name="x", hidden=True)
app.add_typer(linkedin_app, name="linkedin", hidden=True)
app.add_typer(reddit_app, name="reddit", hidden=True)
app.add_typer(email_app, name="email", hidden=True)
app.add_typer(youtube_app, name="youtube", hidden=True)
app.add_typer(tiktok_app, name="tiktok", hidden=True)
app.add_typer(reel_app, name="reel", hidden=True)
app.add_typer(carousel_app, name="carousel", hidden=True)


if __name__ == "__main__":
    app()
