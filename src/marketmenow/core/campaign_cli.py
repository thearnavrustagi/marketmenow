from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from marketmenow.core.campaign_manager import CampaignManager
from marketmenow.core.project_manager import ProjectManager

campaign_app = typer.Typer(
    name="campaign",
    help="Plan and manage marketing campaigns.",
    no_args_is_help=True,
)

console = Console()


def _resolve_project(project: str) -> str:
    """Resolve the project slug from the explicit arg or active project."""
    if project:
        return project
    pm = ProjectManager()
    active = pm.get_active_project()
    if not active:
        console.print("[red]No active project. Use --project or `mmn project use <slug>`.[/red]")
        raise typer.Exit(1)
    return active


@campaign_app.command("create")
def campaign_create(
    project: str = typer.Option("", "--project", "-p", help="Project slug (default: active)"),
) -> None:
    """Start an interactive campaign planning conversation."""
    from marketmenow.core.campaign_planner import CampaignPlanner

    slug = _resolve_project(project)

    planner = CampaignPlanner()
    try:
        asyncio.run(planner.plan(slug, console=console))
    except KeyboardInterrupt:
        raise typer.Exit(0) from None


@campaign_app.command("list")
def campaign_list(
    project: str = typer.Option("", "--project", "-p", help="Project slug (default: active)"),
) -> None:
    """List all campaigns for the active project."""
    slug = _resolve_project(project)
    mgr = CampaignManager()
    plans = mgr.list_campaigns(slug)

    if not plans:
        console.print(f"[yellow]No campaigns found for project '{slug}'.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"Campaigns for {slug}")
    table.add_column("Name", style="cyan")
    table.add_column("Objective", style="green")
    table.add_column("Duration", justify="right")
    table.add_column("Platforms")
    table.add_column("Items", justify="right")
    table.add_column("Status")

    for plan in plans:
        done = sum(1 for i in plan.calendar if i.status == "published")
        total = len(plan.calendar)
        status = f"{done}/{total}"
        table.add_row(
            plan.name,
            plan.goal.objective,
            f"{plan.goal.duration_days}d",
            ", ".join(plan.platforms),
            str(total),
            status,
        )

    console.print(table)


@campaign_app.command("info")
def campaign_info(
    name: str = typer.Argument(help="Campaign name"),
    project: str = typer.Option("", "--project", "-p", help="Project slug (default: active)"),
) -> None:
    """Show campaign details and content calendar."""
    slug = _resolve_project(project)
    mgr = CampaignManager()

    try:
        plan = mgr.load_plan(slug, name)
    except FileNotFoundError:
        console.print(f"[red]Campaign '{name}' not found for project '{slug}'.[/red]")
        raise typer.Exit(1) from None

    console.print(f"\n[bold cyan]{plan.name}[/bold cyan] — {plan.goal.objective}")
    console.print(f"KPI: {plan.goal.kpi}")
    console.print(f"Duration: {plan.goal.duration_days} days")
    console.print(f"Audience: {plan.audience_summary}")
    console.print(f"Tone: {plan.tone}")
    console.print(f"Platforms: {', '.join(plan.platforms)}")
    console.print()

    table = Table(title="Content Calendar")
    table.add_column("ID", style="dim")
    table.add_column("Date")
    table.add_column("Platform", style="cyan")
    table.add_column("Type")
    table.add_column("Topic", max_width=40)
    table.add_column("Status", style="green")

    for item in plan.calendar:
        status_style = {
            "pending": "dim",
            "generated": "yellow",
            "published": "green",
            "failed": "red",
        }.get(item.status, "")

        table.add_row(
            item.id,
            str(item.date),
            item.platform,
            item.content_type,
            item.topic,
            f"[{status_style}]{item.status}[/{status_style}]" if status_style else item.status,
        )

    console.print(table)

    if plan.repurpose_chains:
        console.print("\n[bold]Repurpose Chains:[/bold]")
        for chain in plan.repurpose_chains:
            console.print(f"  {chain.source_item_id} -> {', '.join(chain.target_items)}")


@campaign_app.command("start")
def campaign_start(
    name: str = typer.Argument(help="Campaign name"),
    project: str = typer.Option("", "--project", "-p", help="Project slug (default: active)"),
) -> None:
    """Start the campaign daemon (runs in foreground)."""
    from marketmenow.core.campaign_daemon import CampaignDaemon

    slug = _resolve_project(project)
    mgr = CampaignManager()

    try:
        plan = mgr.load_plan(slug, name)
    except FileNotFoundError:
        console.print(f"[red]Campaign '{name}' not found for project '{slug}'.[/red]")
        raise typer.Exit(1) from None

    daemon = CampaignDaemon(plan)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        daemon.stop()
        console.print("\n[yellow]Daemon stopped.[/yellow]")


@campaign_app.command("status")
def campaign_status(
    name: str = typer.Argument(help="Campaign name"),
    project: str = typer.Option("", "--project", "-p", help="Project slug (default: active)"),
) -> None:
    """Show campaign execution progress."""
    import json as _json

    slug = _resolve_project(project)
    mgr = CampaignManager()

    try:
        plan = mgr.load_plan(slug, name)
    except FileNotFoundError:
        console.print(f"[red]Campaign '{name}' not found.[/red]")
        raise typer.Exit(1) from None

    # Show daemon state if available
    state_file = mgr._campaign_dir(slug, name) / ".daemon.json"
    if state_file.exists():
        state = _json.loads(state_file.read_text(encoding="utf-8"))
        console.print(
            f"Daemon: [bold]{state.get('status', 'unknown')}[/bold] (PID {state.get('pid', '?')})"
        )
    else:
        console.print("Daemon: [dim]not running[/dim]")

    from marketmenow.core.campaign_daemon import CampaignDaemon

    daemon = CampaignDaemon(plan)
    console.print(daemon.generate_status_report())


@campaign_app.command("stop")
def campaign_stop(
    name: str = typer.Argument(help="Campaign name"),
    project: str = typer.Option("", "--project", "-p", help="Project slug (default: active)"),
) -> None:
    """Stop the campaign daemon by sending SIGTERM."""
    import json as _json
    import os
    import signal

    slug = _resolve_project(project)
    mgr = CampaignManager()
    state_file = mgr._campaign_dir(slug, name) / ".daemon.json"

    if not state_file.exists():
        console.print("[yellow]No daemon state found. Is the daemon running?[/yellow]")
        raise typer.Exit(1)

    state = _json.loads(state_file.read_text(encoding="utf-8"))
    pid = state.get("pid")
    if not pid:
        console.print("[red]No PID found in daemon state.[/red]")
        raise typer.Exit(1)

    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Sent SIGTERM to daemon (PID {pid}).[/green]")
    except ProcessLookupError:
        console.print(f"[yellow]Process {pid} not found. Daemon may have already stopped.[/yellow]")
        # Clean up state file
        state_file.unlink(missing_ok=True)
