from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import webbrowser
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from marketmenow.integrations.genai import has_genai_credentials

from .models import SendResult
from .paraphraser import EmailParaphraser
from .sender import send_batch, send_single
from .settings import EmailSettings

app = typer.Typer(
    name="mmn-email",
    help="MarketMeNow email outreach CLI",
    no_args_is_help=True,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

console = Console()

_RANGE_RE = re.compile(r"^(\d+)-(\d+)$")


def _preview_in_browser(results: list[SendResult]) -> None:
    """Write rendered emails to temp HTML files and open the first in the browser."""
    previewed = [r for r in results if r.rendered_html]
    if not previewed:
        return
    result = previewed[0]
    subject_bar = (
        f'<div style="background:#f0f0f0;padding:12px 20px;font-family:Arial,sans-serif;'
        f'font-size:14px;color:#555;border-bottom:1px solid #ddd;">'
        f"<strong>Subject:</strong> {result.rendered_subject} &nbsp;&nbsp;|&nbsp;&nbsp;"
        f"<strong>To:</strong> {result.email}</div>"
    )
    html = result.rendered_html.replace(
        "<body", f"<body>\n{subject_bar}\n<!-- original body -->", 1
    )
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp_path = f.name
    webbrowser.open(f"file://{tmp_path}")
    console.print(f"[cyan]Preview opened in browser:[/cyan] {tmp_path}")


def _ensure_vertex_credentials(settings: EmailSettings) -> None:
    """Export GOOGLE_APPLICATION_CREDENTIALS so the genai SDK picks it up."""
    creds = settings.google_application_credentials
    if creds and creds.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(creds.resolve()))


def _parse_range(value: str) -> tuple[int, int]:
    m = _RANGE_RE.match(value.strip())
    if not m:
        raise typer.BadParameter(f"Range must be START-END (e.g. 100-200), got: {value}")
    start, end = int(m.group(1)), int(m.group(2))
    if start >= end:
        raise typer.BadParameter(f"Start ({start}) must be less than end ({end})")
    return start, end


class _EmailProgress:
    """Live-updating terminal UI for the email send loop."""

    def __init__(self, live: Live, total: int, start: int) -> None:
        self._live = live
        self._total = total
        self._start = start
        self._entries: list[tuple[str, bool, str]] = []

    @property
    def succeeded(self) -> int:
        return sum(1 for _, ok, _ in self._entries if ok)

    @property
    def failed(self) -> int:
        return sum(1 for _, ok, _ in self._entries if not ok)

    def _render(self) -> Panel:
        tbl = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
        tbl.add_column("status", width=3)
        tbl.add_column("info", ratio=1)

        visible = self._entries[-20:]
        for email, ok, err in visible:
            if ok:
                tbl.add_row("[bold green]✓[/bold green]", f"[green]{email}[/green]")
            else:
                tbl.add_row("[bold red]✗[/bold red]", f"[red]{email}[/red]  {err}")

        done = len(self._entries)
        progress = f"{done}/{self._total}  [green]{self.succeeded} sent[/green]"
        if self.failed:
            progress += f"  [red]{self.failed} failed[/red]"

        return Panel(
            tbl,
            title=f"[bold]Sending emails[/bold]  [dim]{progress}[/dim]",
            border_style="cyan" if done < self._total else "green",
        )

    def on_progress(
        self,
        current: int,
        total: int,
        email: str,
        success: bool,
        error: str,
    ) -> None:
        self._entries.append((email, success, error))
        self._live.update(self._render())


def _print_summary(results: list[SendResult], dry_run: bool) -> None:
    console.print()
    tbl = Table(title="Summary", show_header=False, border_style="bold")
    tbl.add_column("metric", style="bold")
    tbl.add_column("value", justify="right")

    succeeded = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    tbl.add_row("Mode", "[yellow]DRY RUN[/yellow]" if dry_run else "Live")
    tbl.add_row("Total", str(len(results)))
    tbl.add_row(
        "Sent",
        f"[green]{succeeded}[/green]" if succeeded else "0",
    )
    tbl.add_row(
        "Failed",
        f"[red]{failed}[/red]" if failed else "0",
    )
    console.print(tbl)

    if failed:
        console.print()
        err_tbl = Table(title="Failures", border_style="red")
        err_tbl.add_column("Row", style="dim", width=6)
        err_tbl.add_column("Email")
        err_tbl.add_column("Error", style="red")
        for r in results:
            if not r.success:
                err_tbl.add_row(str(r.row_index), r.email, r.error)
        console.print(err_tbl)


@app.command("send")
def send(
    template: Path = typer.Option(
        ...,
        "-t",
        "--template",
        help="HTML Jinja2 template file",
        exists=True,
        readable=True,
    ),
    to: str | None = typer.Option(
        None,
        "--to",
        help="Send a single test email to this address (skips CSV/range).",
    ),
    var: list[str] | None = typer.Option(
        None,
        "--var",
        help="Template variable as key=value (repeatable). Used with --to.",
    ),
    csv_file: Path | None = typer.Option(
        None,
        "-f",
        "--file",
        help="CSV file with contacts (must have an 'email' column)",
        exists=True,
        readable=True,
    ),
    subject: str | None = typer.Option(
        None,
        "-s",
        "--subject",
        help="Email subject (supports Jinja2 placeholders). If omitted, read from template front-matter.",
    ),
    row_range: str | None = typer.Option(
        None,
        "-r",
        "--range",
        help="Row range as START-END (inclusive start, exclusive end, 0-indexed data rows)",
    ),
    paraphrase: bool = typer.Option(
        False,
        "--paraphrase",
        help="Use Gemini to slightly rewrite each email so no two are identical.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Render emails and log them without actually sending",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show raw log output instead of rich UI",
    ),
) -> None:
    """Send templated emails to a CSV contact list or a single recipient.

    Use --to for a quick single-recipient test.  Use -f/-r for batch
    sends from a CSV (must have an 'email' column; other columns become
    Jinja2 template variables).

    The subject can be set in the template's YAML front-matter or
    via -s on the command line (CLI flag wins if both exist).

    Every sent email is BCC'd to the sender address.

    Examples:

        mmn email send -t invite.html --to you@example.com --var first_name=Arnav

        mmn email send -f contacts.csv -t invite.html -r 0-50

        mmn email send -f contacts.csv -t invite.html -r 100-200 --dry-run
    """
    settings = EmailSettings()

    if not settings.smtp_username and not dry_run:
        console.print("[red]SMTP_USERNAME is not set in .env[/red]")
        raise typer.Exit(code=1)

    if paraphrase and not has_genai_credentials(settings.vertex_ai_project):
        console.print(
            "[red]Gemini credentials are not configured for --paraphrase. "
            "Set VERTEX_AI_PROJECT or GEMINI_API_KEY/GOOGLE_API_KEY.[/red]"
        )
        raise typer.Exit(code=1)

    rewriter: EmailParaphraser | None = None
    if paraphrase:
        _ensure_vertex_credentials(settings)
        rewriter = EmailParaphraser(
            vertex_project=settings.vertex_ai_project,
            vertex_location=settings.vertex_ai_location,
        )
        console.print("[cyan]Paraphrase mode ON — each email will be uniquely rewritten[/cyan]")

    if dry_run:
        console.print("[yellow]DRY RUN — no emails will be sent[/yellow]")

    if to:
        template_vars: dict[str, str] = {}
        for item in var or []:
            if "=" not in item:
                console.print(f"[red]--var must be key=value, got: {item}[/red]")
                raise typer.Exit(code=1)
            k, v = item.split("=", 1)
            template_vars[k.strip()] = v.strip()

        console.print(f"Sending to [bold]{to}[/bold]  template [bold]{template.name}[/bold]")

        async def _run_single() -> list[SendResult]:
            result = await send_single(
                settings,
                template,
                subject,
                to,
                template_vars=template_vars,
                paraphraser=rewriter,
                dry_run=dry_run,
            )
            return [result]

        results = asyncio.run(_run_single())
        _print_summary(results, dry_run)
        if dry_run:
            _preview_in_browser(results)
        return

    if not csv_file:
        console.print("[red]Provide --to for a single email or -f/-r for batch sends.[/red]")
        raise typer.Exit(code=1)
    if not row_range:
        console.print("[red]-r/--range is required for batch sends.[/red]")
        raise typer.Exit(code=1)

    start, end = _parse_range(row_range)

    console.print(
        f"CSV [bold]{csv_file}[/bold]  rows [bold]{start}[/bold]–[bold]{end}[/bold]  "
        f"template [bold]{template.name}[/bold]"
    )

    async def _run() -> list[SendResult]:
        if verbose or dry_run:
            return await send_batch(
                settings,
                csv_file,
                template,
                subject,
                start,
                end,
                paraphraser=rewriter,
                dry_run=dry_run,
            )

        from .sender import read_contacts

        total = len(read_contacts(csv_file, start, end))
        with Live(console=console, refresh_per_second=8, transient=False) as live:
            progress = _EmailProgress(live, total, start)
            return await send_batch(
                settings,
                csv_file,
                template,
                subject,
                start,
                end,
                paraphraser=rewriter,
                dry_run=dry_run,
                on_progress=progress.on_progress,
            )

    results = asyncio.run(_run())
    _print_summary(results, dry_run)
    if dry_run:
        _preview_in_browser(results)
