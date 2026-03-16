from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from .settings import InstagramSettings

app = typer.Typer(
    name="mmn",
    help="MarketMeNow -- Instagram content generation CLI",
    no_args_is_help=True,
)
carousel_app = typer.Typer(help="Figma-to-carousel commands")
reel_app = typer.Typer(help="Reel generation and preview commands")
app.add_typer(carousel_app, name="carousel")
app.add_typer(reel_app, name="reel")

console = Console()


def _get_settings() -> InstagramSettings:
    return InstagramSettings()


# ---------------------------------------------------------------------------
# Carousel commands
# ---------------------------------------------------------------------------


@carousel_app.command("export")
def carousel_export(
    file_key: Annotated[str, typer.Option("--file-key", help="Figma file key")],
    frame_ids: Annotated[
        Optional[str],
        typer.Option("--frame-ids", help="Comma-separated Figma node IDs"),
    ] = None,
    caption: Annotated[str, typer.Option(help="Carousel caption")] = "",
    hashtags: Annotated[
        Optional[str],
        typer.Option(help="Comma-separated hashtags"),
    ] = None,
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", help="Output directory"),
    ] = None,
    publish: Annotated[
        bool, typer.Option("--publish", help="Publish to Instagram after export")
    ] = False,
) -> None:
    """Export Figma frames as an Instagram carousel."""
    asyncio.run(
        _carousel_export_async(
            file_key, frame_ids, caption, hashtags, output_dir, publish
        )
    )


async def _carousel_export_async(
    file_key: str,
    frame_ids: str | None,
    caption: str,
    hashtags: str | None,
    output_dir: Path | None,
    publish: bool,
) -> None:
    settings = _get_settings()
    out = output_dir or settings.output_dir

    from .figma.client import FigmaClient
    from .figma.exporter import CarouselExporter

    client = FigmaClient(api_token=settings.figma_api_token)
    exporter = CarouselExporter(figma_client=client, output_dir=out)

    ids = [fid.strip() for fid in frame_ids.split(",")] if frame_ids else None
    tags = [t.strip() for t in hashtags.split(",")] if hashtags else []

    with console.status("[bold green]Exporting carousel from Figma..."):
        carousel = await exporter.export(
            file_key=file_key,
            frame_ids=ids,
            caption=caption,
            hashtags=tags,
        )
    await client.close()

    console.print(
        f"[green]Carousel created with {len(carousel.slides)} slides[/green]"
    )
    for i, slide in enumerate(carousel.slides):
        console.print(f"  Slide {i + 1}: {slide.media.uri}")

    if publish:
        from . import create_instagram_bundle
        from marketmenow.core.pipeline import ContentPipeline
        from marketmenow.registry import AdapterRegistry

        registry = AdapterRegistry()
        bundle = create_instagram_bundle(settings)
        registry.register(bundle)

        pipeline = ContentPipeline(registry)
        with console.status("[bold blue]Publishing to Instagram..."):
            result = await pipeline.execute(carousel, "instagram")
        console.print(f"[green]Published![/green] Result: {result}")


@carousel_app.command("generate")
def carousel_generate(
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", help="Output directory"),
    ] = None,
    publish: Annotated[
        bool, typer.Option("--publish", help="Publish to Instagram after generation")
    ] = False,
) -> None:
    """Generate a fresh Top-5 carousel using AI (Gemini + Imagen)."""
    asyncio.run(_carousel_generate_async(output_dir, publish))


async def _carousel_generate_async(
    output_dir: Path | None,
    publish: bool,
) -> None:
    settings = _get_settings()
    if output_dir:
        settings = settings.model_copy(update={"output_dir": output_dir})

    from .carousel.orchestrator import CarouselOrchestrator

    orch = CarouselOrchestrator(settings)

    with console.status("[bold green]Generating carousel (Gemini + Imagen)..."):
        carousel = await orch.create_carousel()

    console.print(
        f"[green]Carousel created with {len(carousel.slides)} slides[/green]"
    )
    for i, slide in enumerate(carousel.slides):
        console.print(f"  Slide {i + 1}: {slide.media.uri}")
    console.print(f"\n[bold]Caption:[/bold] {carousel.caption}")

    if publish:
        from . import create_instagram_bundle
        from marketmenow.core.pipeline import ContentPipeline
        from marketmenow.registry import AdapterRegistry

        registry = AdapterRegistry()
        bundle = create_instagram_bundle(settings)
        registry.register(bundle)

        pipeline = ContentPipeline(registry)
        with console.status("[bold blue]Publishing to Instagram..."):
            result = await pipeline.execute(carousel, "instagram")
        console.print(f"[green]Published![/green] Result: {result}")


# ---------------------------------------------------------------------------
# Reel commands
# ---------------------------------------------------------------------------


@reel_app.command("create")
def reel_create(
    assignment: Annotated[
        Path, typer.Option("--assignment", help="Path to assignment image")
    ],
    template: Annotated[
        str, typer.Option("--template", help="Template ID")
    ] = "can_ai_grade_this",
    rubric: Annotated[
        Optional[Path],
        typer.Option("--rubric", help="Path to rubric JSON/YAML file"),
    ] = None,
    caption: Annotated[str, typer.Option(help="Reel caption")] = "",
    hashtags: Annotated[
        Optional[str], typer.Option(help="Comma-separated hashtags")
    ] = None,
    output_dir: Annotated[
        Optional[Path], typer.Option("--output-dir", help="Output directory")
    ] = None,
    tts: Annotated[
        str,
        typer.Option("--tts", help="TTS provider: elevenlabs, openai, local, or kokoro"),
    ] = "",
    reaction_image: Annotated[
        Optional[Path],
        typer.Option("--reaction-image", help="Path to reaction image (e.g. funny dog)"),
    ] = None,
    comment_username: Annotated[
        str,
        typer.Option("--comment-username", help="Username for the TikTok-style comment hook"),
    ] = "",
    comment_avatar: Annotated[
        Optional[Path],
        typer.Option("--comment-avatar", help="Path to commenter's avatar image"),
    ] = None,
    comment_text: Annotated[
        str,
        typer.Option("--comment-text", help="Comment text for the TikTok hook"),
    ] = "",
    student_name: Annotated[
        str,
        typer.Option("--student-name", help="Student name shown on the grading card"),
    ] = "",
    publish: Annotated[
        bool, typer.Option("--publish", help="Publish to Instagram after render")
    ] = False,
) -> None:
    """Generate a reel from a YAML template and assignment image."""
    asyncio.run(
        _reel_create_async(
            assignment, template, rubric, caption, hashtags, output_dir, tts,
            reaction_image, comment_username, comment_avatar, comment_text,
            student_name, publish,
        )
    )


async def _reel_create_async(
    assignment: Path,
    template: str,
    rubric: Path | None,
    caption: str,
    hashtags: str | None,
    output_dir: Path | None,
    tts: str,
    reaction_image: Path | None,
    comment_username: str,
    comment_avatar: Path | None,
    comment_text: str,
    student_name: str,
    publish: bool,
) -> None:
    settings = _get_settings()
    updates: dict[str, object] = {}
    if output_dir:
        updates["output_dir"] = output_dir
    if tts:
        updates["tts_provider"] = tts
    if updates:
        settings = settings.model_copy(update=updates)

    rubric_items = None
    if rubric and rubric.exists():
        import yaml

        raw = yaml.safe_load(rubric.read_text())
        from .grading.models import RubricItem

        if isinstance(raw, list):
            rubric_items = [RubricItem(**item) for item in raw]
        elif isinstance(raw, dict) and "rubric_items" in raw:
            rubric_items = [RubricItem(**item) for item in raw["rubric_items"]]

    tags = [t.strip() for t in hashtags.split(",")] if hashtags else None

    from .reels.orchestrator import ReelOrchestrator

    orch = ReelOrchestrator(settings)

    with console.status(
        f"[bold green]Generating reel (template={template})..."
    ):
        reel = await orch.create_reel(
            assignment_image=assignment,
            template_id=template,
            rubric_items=rubric_items,
            caption=caption,
            hashtags=tags,
            reaction_image=reaction_image,
            comment_username=comment_username,
            comment_avatar=comment_avatar,
            comment_text=comment_text,
            student_name=student_name,
        )

    console.print(f"[green]Reel rendered:[/green] {reel.video.uri}")

    hashtag_str = " ".join(f"#{t}" for t in reel.hashtags)
    full_caption = f"{reel.caption}\n\n{hashtag_str}"

    console.print()
    console.print("[bold]Caption:[/bold]")
    console.print(full_caption)
    console.print()

    caption_path = Path(reel.video.uri).with_suffix(".caption.txt")
    caption_path.write_text(full_caption)
    console.print(f"[dim]Caption saved to {caption_path}[/dim]")

    if publish:
        from . import create_instagram_bundle
        from marketmenow.core.pipeline import ContentPipeline
        from marketmenow.registry import AdapterRegistry

        registry = AdapterRegistry()
        bundle = create_instagram_bundle(settings)
        registry.register(bundle)

        pipeline = ContentPipeline(registry)
        with console.status("[bold blue]Publishing to Instagram..."):
            result = await pipeline.execute(reel, "instagram")
        console.print(f"[green]Published![/green] Result: {result}")


@reel_app.command("preview")
def reel_preview(
    template: Annotated[
        str, typer.Option("--template", help="Template ID")
    ] = "can_ai_grade_this",
    props_file: Annotated[
        Optional[Path],
        typer.Option("--props-file", help="Pre-generated props JSON file"),
    ] = None,
) -> None:
    """Open Remotion Studio for live preview of a reel composition."""
    import subprocess

    settings = _get_settings()
    remotion_dir = settings.remotion_project_dir

    cmd = ["npx", "remotion", "studio", "src/index.ts"]
    if props_file:
        cmd.extend(["--props", str(props_file.resolve())])

    console.print(
        f"[bold blue]Opening Remotion Studio[/bold blue] (template={template})"
    )
    console.print(f"  Working dir: {remotion_dir}")
    subprocess.run(cmd, cwd=str(remotion_dir), check=True)


@reel_app.command("list-templates")
def reel_list_templates() -> None:
    """List all available YAML reel templates."""
    from .reels.template_loader import ReelTemplateLoader

    loader = ReelTemplateLoader()
    templates = loader.list_templates()

    table = Table(title="Available Reel Templates")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Beats", justify="right")
    table.add_column("FPS", justify="right")

    for tid in templates:
        try:
            tmpl = loader.load(tid)
            table.add_row(tmpl.id, tmpl.name, str(len(tmpl.beats)), str(tmpl.fps))
        except Exception as e:
            table.add_row(tid, f"[red]Error: {e}[/red]", "-", "-")

    console.print(table)


@reel_app.command("validate")
def reel_validate(
    template: Annotated[str, typer.Argument(help="Template ID to validate")],
) -> None:
    """Validate a YAML reel template without running the pipeline."""
    from .reels.template_loader import ReelTemplateLoader

    loader = ReelTemplateLoader()
    issues = loader.validate(template)

    if not issues:
        console.print(f"[green]Template '{template}' is valid.[/green]")
    else:
        console.print(f"[red]Template '{template}' has issues:[/red]")
        for issue in issues:
            console.print(f"  [yellow]- {issue}[/yellow]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
