from __future__ import annotations

from pathlib import Path

from marketmenow.core.workflow import WorkflowContext


class GenerateCarouselStep:
    """Generate an AI carousel (Gemini + Imagen) via CarouselOrchestrator."""

    @property
    def name(self) -> str:
        return "generate-carousel"

    @property
    def description(self) -> str:
        return "Generate AI carousel images"

    async def execute(self, ctx: WorkflowContext) -> None:
        from adapters.instagram.carousel.orchestrator import CarouselOrchestrator
        from adapters.instagram.settings import InstagramSettings

        settings = InstagramSettings()

        output_dir = ctx.get_param("output_dir")
        if output_dir:
            settings = settings.model_copy(update={"output_dir": Path(str(output_dir))})

        orch = CarouselOrchestrator(
            settings,
            persona=ctx.persona,
            brand=ctx.project.brand if ctx.project else None,
            project_slug=ctx.project.slug if ctx.project else None,
        )

        with ctx.console.status("[bold green]Generating carousel (Gemini + Imagen)..."):
            carousel = await orch.create_carousel()

        ctx.console.print(f"[green]Carousel created with {len(carousel.images)} slides[/green]")
        ctx.set_artifact("content", carousel)
        ctx.set_artifact(
            "_carousel_meta",
            {
                "num_slides": len(carousel.images),
                "caption": carousel.caption,
                "hashtags": list(carousel.hashtags),
            },
        )
        ctx.set_artifact("platform", "instagram")
