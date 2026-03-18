from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from marketmenow.core.distributor import ContentDistributor
from marketmenow.core.orchestrator import CampaignResult
from marketmenow.core.registry_builder import build_registry
from marketmenow.models.content import BaseContent
from marketmenow.models.distribution import DistributionMap


async def distribute_content(
    content: BaseContent,
    console: Console,
    *,
    only: str | None = None,
) -> CampaignResult:
    """Shared async helper used by all CLI ``--distribute`` flags.

    Builds the full adapter registry, resolves the distribution map, publishes
    to all applicable platforms, and prints a summary table.
    """
    registry = build_registry()
    dist_map = DistributionMap.defaults()
    distributor = ContentDistributor(registry, dist_map)

    platforms: frozenset[str] | None = None
    if only:
        platforms = frozenset(p.strip() for p in only.split(",") if p.strip())

    target_label = ", ".join(sorted(platforms)) if platforms else "all mapped platforms"

    with console.status(
        f"[bold blue]Distributing {content.modality.value} to {target_label}...[/bold blue]"
    ):
        result = await distributor.distribute(content, platforms=platforms)

    _print_distribution_result(console, result)
    return result


def _print_distribution_result(console: Console, result: CampaignResult) -> None:
    table = Table(title="Distribution Results", show_header=True, border_style="bold")
    table.add_column("Platform", style="bold cyan")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    for pub in result.results:
        status = "[green]Published[/green]" if pub.success else "[red]Failed[/red]"
        detail = pub.remote_url or pub.error_message or ""
        table.add_row(pub.platform, status, str(detail))

    for target, exc in result.errors:
        table.add_row(target.platform, "[red]Error[/red]", str(exc))

    console.print()
    console.print(table)

    successes = sum(1 for r in result.results if r.success)
    failures = len(result.results) - successes + len(result.errors)
    console.print()
    if failures == 0 and successes > 0:
        console.print(
            Panel(
                f"[bold green]Distributed to {successes} platform(s)[/bold green]",
                border_style="green",
            )
        )
    elif successes > 0:
        console.print(f"[yellow]{successes} succeeded, {failures} failed[/yellow]")
    else:
        console.print("[red]Distribution failed on all platforms.[/red]")
