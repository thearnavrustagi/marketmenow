from __future__ import annotations

import asyncio
import random

from marketmenow.core.workflow import WorkflowContext, WorkflowError


class LinkedInPostStep:
    """Generate and publish a batch of AI-powered LinkedIn posts."""

    @property
    def name(self) -> str:
        return "linkedin-post"

    @property
    def description(self) -> str:
        return "Generate and post to LinkedIn"

    async def execute(self, ctx: WorkflowContext) -> None:
        from adapters.linkedin import create_linkedin_bundle
        from adapters.linkedin.content_generator import LinkedInContentGenerator
        from adapters.linkedin.settings import LinkedInSettings
        from marketmenow.normaliser import ContentNormaliser

        settings = LinkedInSettings()
        headless = bool(ctx.get_param("headless", False))
        if headless:
            settings = settings.model_copy(update={"headless": True})

        if not settings.vertex_ai_project:
            raise WorkflowError("VERTEX_AI_PROJECT not set in .env")

        count = int(ctx.get_param("count", 5) or 5)
        min_delay = int(ctx.get_param("min_delay", 300) or 300)
        max_delay = int(ctx.get_param("max_delay", 600) or 600)
        dry_run = bool(ctx.get_param("dry_run", False))

        generator = LinkedInContentGenerator(
            settings,
            top_examples_path=settings.top_examples_path,
            max_examples=settings.max_examples_in_prompt,
            epsilon=settings.epsilon,
        )

        with ctx.console.status("[bold blue]Generating LinkedIn content with Gemini..."):
            posts = await generator.generate_batch(count)

        ctx.console.print(f"[green]Generated {len(posts)} posts[/green]")

        if dry_run:
            ctx.console.print("[yellow]Dry run -- no posts published.[/yellow]")
            ctx.set_artifact("generated_posts", posts)
            return

        from adapters.linkedin.api_adapter import LinkedInAPIAdapter
        from adapters.linkedin.browser import LinkedInBrowser

        normaliser = ContentNormaliser()
        bundle = create_linkedin_bundle(settings)

        async def _open_and_post() -> int:
            successes = 0
            if settings.use_api:
                for i, post in enumerate(posts, 1):
                    try:
                        model = _to_content(post)
                        normalised = normaliser.normalise(model)
                        rendered = await bundle.renderer.render(normalised)
                        result = await bundle.adapter.publish(rendered)
                        if result.success:
                            successes += 1
                            ctx.console.print(f"  [green]Post {i}/{len(posts)} published[/green]")
                        else:
                            ctx.console.print(
                                f"  [red]Post {i} failed: {result.error_message}[/red]"
                            )
                    except Exception as exc:
                        ctx.console.print(f"  [red]Post {i} error: {exc}[/red]")
                    if i < len(posts):
                        delay = random.uniform(min_delay, max_delay)
                        await asyncio.sleep(delay)
                if isinstance(bundle.adapter, LinkedInAPIAdapter):
                    await bundle.adapter.close()
            else:
                browser: LinkedInBrowser = bundle.adapter._browser  # type: ignore[attr-defined]
                async with browser:
                    if not await browser.is_logged_in():
                        li_at = settings.linkedin_li_at
                        if li_at:
                            await browser.login_with_cookie(li_at)
                        else:
                            raise WorkflowError("LinkedIn not logged in")
                    for i, post in enumerate(posts, 1):
                        try:
                            model = _to_content(post)
                            normalised = normaliser.normalise(model)
                            rendered = await bundle.renderer.render(normalised)
                            result = await bundle.adapter.publish(rendered)
                            if result.success:
                                successes += 1
                                ctx.console.print(
                                    f"  [green]Post {i}/{len(posts)} published[/green]"
                                )
                            else:
                                ctx.console.print(
                                    f"  [red]Post {i} failed: {result.error_message}[/red]"
                                )
                        except Exception as exc:
                            ctx.console.print(f"  [red]Post {i} error: {exc}[/red]")
                        if i < len(posts):
                            delay = random.uniform(min_delay, max_delay)
                            await asyncio.sleep(delay)
            return successes

        successes = await _open_and_post()
        ctx.console.print(f"[green]{successes}/{len(posts)} posts published to LinkedIn[/green]")
        ctx.set_artifact("generated_posts", posts)


def _to_content(post: object) -> object:
    from marketmenow.models.content import Article, Poll, TextPost

    hashtags = [t.lstrip("#") for t in getattr(post, "hashtags", [])]
    post_type = getattr(post, "type", "text")

    if post_type == "poll":
        return Poll(
            question=getattr(post, "poll_question", ""),
            options=getattr(post, "poll_options", [])[:4],
            duration_days=3,
            commentary=getattr(post, "body", ""),
            hashtags=hashtags,
        )
    elif post_type == "article":
        return Article(
            url=getattr(post, "article_url", ""),
            commentary=getattr(post, "body", ""),
            hashtags=hashtags,
        )
    else:
        return TextPost(body=getattr(post, "body", ""), hashtags=hashtags)
