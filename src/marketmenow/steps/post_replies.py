from __future__ import annotations

from marketmenow.core.workflow import WorkflowContext, WorkflowError


class PostRepliesStep:
    """Post generated replies/comments via the engagement orchestrator.

    Reads ``generated_replies`` and ``engagement_orchestrator`` from context.
    """

    @property
    def name(self) -> str:
        return "post-replies"

    @property
    def description(self) -> str:
        return "Post generated replies/comments"

    async def execute(self, ctx: WorkflowContext) -> None:
        platform = str(ctx.artifacts.get("engagement_platform", ""))
        orchestrator = ctx.get_artifact("engagement_orchestrator")
        replies = ctx.get_artifact("generated_replies")

        if not replies:
            ctx.console.print("[yellow]No replies to post.[/yellow]")
            return

        if platform == "twitter":
            with ctx.console.status("[bold cyan]Posting Twitter replies..."):
                stats = await orchestrator.reply_from_list(replies)  # type: ignore[union-attr]
        elif platform == "reddit":
            with ctx.console.status("[bold cyan]Posting Reddit comments..."):
                stats = await orchestrator.comment_from_list(replies)  # type: ignore[union-attr]
        elif platform == "facebook":
            stats = await self._post_facebook(ctx, replies)
        else:
            raise WorkflowError(f"Unsupported engagement platform: {platform}")

        ctx.console.print(
            f"[green]Engagement complete:[/green] "
            f"{stats.total_succeeded} succeeded, {stats.total_failed} failed"
        )
        ctx.set_artifact("engagement_stats", stats)

    async def _post_facebook(
        self,
        ctx: WorkflowContext,
        replies: list[object],
    ) -> object:
        from adapters.facebook.browser import FacebookBrowser
        from adapters.facebook.orchestrator import EngagementOrchestrator
        from adapters.facebook.settings import FacebookSettings

        settings: FacebookSettings = ctx.get_artifact("_facebook_settings")  # type: ignore[assignment]
        if settings is None:
            settings = FacebookSettings()
            headless = ctx.get_param("headless", True)
            if headless:
                settings = settings.model_copy(update={"headless": True})

        browser = FacebookBrowser(
            session_path=settings.facebook_session_path,
            user_data_dir=settings.facebook_user_data_dir,
            headless=settings.headless,
            slow_mo_ms=settings.slow_mo_ms,
            proxy_url=settings.proxy_url,
            viewport_width=settings.viewport_width,
            viewport_height=settings.viewport_height,
        )

        project_slug = ctx.project.slug if ctx.project else None

        async with browser:
            if not await browser.is_logged_in():
                c_user = settings.facebook_c_user
                xs = settings.facebook_xs
                if c_user and xs:
                    await browser.login_with_cookies(c_user, xs)
                else:
                    raise WorkflowError("Not logged into Facebook. Run `mmn facebook login` first.")

            orchestrator = EngagementOrchestrator(
                settings,
                browser,
                project_slug=project_slug,
            )

            with ctx.console.status("[bold cyan]Posting Facebook group comments..."):
                stats = await orchestrator.comment_from_list(replies)  # type: ignore[arg-type]

        return stats
