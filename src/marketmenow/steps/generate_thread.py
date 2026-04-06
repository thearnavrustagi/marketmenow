from __future__ import annotations

from marketmenow.core.workflow import WorkflowContext


class GenerateThreadStep:
    """Generate a Twitter/X thread via Gemini."""

    @property
    def name(self) -> str:
        return "generate-thread"

    @property
    def description(self) -> str:
        return "Generate Twitter/X thread via AI"

    async def execute(self, ctx: WorkflowContext) -> None:
        import os

        from adapters.twitter.settings import TwitterSettings
        from adapters.twitter.thread_generator import ThreadGenerator

        settings = TwitterSettings()

        creds = settings.google_application_credentials
        if creds and creds.exists():
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(creds.resolve()))

        generator = ThreadGenerator(
            gemini_model=settings.gemini_model,
            vertex_project=settings.vertex_ai_project,
            vertex_location=settings.vertex_ai_location,
            top_examples_path=settings.top_examples_path,
            max_examples=settings.max_examples_in_prompt,
            epsilon=settings.epsilon,
            persona=ctx.persona,
            brand=ctx.project.brand if ctx.project else None,
            project_slug=ctx.project.slug if ctx.project else None,
        )

        topic = str(ctx.get_param("topic", "") or "")

        with ctx.console.status("[bold cyan]Generating thread..."):
            generated = await generator.generate_thread(topic_hint=topic)

        from rich.panel import Panel

        ctx.console.print(
            Panel(
                f"[bold]{generated.topic}[/bold]",
                title="Thread Topic",
                border_style="cyan",
            )
        )
        for tweet in generated.tweets:
            label = ""
            if tweet.is_hook:
                label = " [bold yellow](HOOK)[/bold yellow]"
            elif tweet.is_cta:
                label = " [bold green](CTA)[/bold green]"
            char_count = len(tweet.text)
            char_style = "green" if char_count <= 280 else "red"
            ctx.console.print(
                Panel(
                    tweet.text,
                    title=f"Tweet {tweet.position}{label}",
                    subtitle=f"[{char_style}]{char_count}/280[/{char_style}]",
                    border_style="blue" if not tweet.is_cta else "green",
                )
            )

        from marketmenow.models.content import Thread, ThreadEntry

        thread_content = Thread(
            entries=[ThreadEntry(text=t.text) for t in generated.tweets],
        )
        ctx.set_artifact("content", thread_content)
        ctx.set_artifact("generated_thread", generated)
        ctx.set_artifact("platform", "twitter")
