from __future__ import annotations

from pathlib import Path

from marketmenow.core.workflow import WorkflowContext, WorkflowError


def _is_adapter_default_targets(current_path: Path, settings_module_file: str) -> bool:
    """True when *current_path* still points to the adapter-bundled template."""
    adapter_dir = Path(settings_module_file).resolve().parent
    default_targets = adapter_dir / "targets.yaml"
    try:
        return current_path.resolve() == default_targets.resolve()
    except OSError:
        return False


def _reject_default_targets(
    targets_path: Path,
    settings_module_file: str,
    platform: str,
    project_slug: str | None,
) -> None:
    """Raise ``WorkflowError`` if *targets_path* is the adapter-bundled template.

    This prevents silent engagement runs against placeholder hashtags like
    ``#yourindustry`` that ship with the adapter source code.
    """
    if not _is_adapter_default_targets(targets_path, settings_module_file):
        return

    slug_display = project_slug or "<project>"
    raise WorkflowError(
        f"Using default placeholder targets for {platform} "
        f"({targets_path}). Create a custom targets file:\n"
        f"  projects/{slug_display}/targets/{platform}.yaml\n"
        f"Or set {platform.upper()}_TARGETS_PATH in .env.\n"
        f"See src/adapters/{platform}/targets.yaml for the format reference."
    )


class DiscoverPostsStep:
    """Discover relevant posts on a social platform for engagement.

    Supports ``twitter``, ``reddit``, and ``facebook``.
    """

    def __init__(self, platform: str) -> None:
        if platform not in ("twitter", "reddit", "facebook"):
            raise ValueError(f"Unsupported discovery platform: {platform}")
        self._platform = platform

    @property
    def name(self) -> str:
        return f"discover-{self._platform}"

    @property
    def description(self) -> str:
        return f"Discover posts on {self._platform}"

    async def execute(self, ctx: WorkflowContext) -> None:
        if self._platform == "twitter":
            await self._discover_twitter(ctx)
        elif self._platform == "facebook":
            await self._discover_facebook(ctx)
        else:
            await self._discover_reddit(ctx)

    async def _discover_twitter(self, ctx: WorkflowContext) -> None:
        from adapters.twitter import settings as _tw_settings_mod
        from adapters.twitter.orchestrator import EngagementOrchestrator
        from adapters.twitter.settings import TwitterSettings

        settings = TwitterSettings()
        headless = ctx.get_param("headless", True)
        if headless:
            settings = settings.model_copy(update={"headless": True})

        max_replies = int(ctx.get_param("max_replies", 0) or 0)
        if max_replies > 0:
            settings = settings.model_copy(update={"max_replies_per_day": max_replies})

        project_slug = ctx.project.slug if ctx.project else None
        if project_slug:
            project_targets = Path(f"projects/{project_slug}/targets/twitter.yaml")
            if project_targets.exists():
                settings = settings.model_copy(update={"targets_path": project_targets})

        _reject_default_targets(
            settings.targets_path,
            _tw_settings_mod.__file__,
            "twitter",
            project_slug,
        )

        persona = ctx.persona
        brand = ctx.project.brand if ctx.project else None
        orchestrator = EngagementOrchestrator(
            settings,
            persona=persona,
            brand=brand,
            project_slug=project_slug,
        )

        with ctx.console.status("[bold cyan]Discovering Twitter posts..."):
            posts = await orchestrator.discover_only()

        if not posts:
            raise WorkflowError("No posts discovered on Twitter. Are you logged in?")

        ctx.console.print(f"[green]Discovered {len(posts)} posts on Twitter[/green]")
        ctx.set_artifact("discovered_posts", posts)
        ctx.set_artifact("engagement_orchestrator", orchestrator)
        ctx.set_artifact("engagement_platform", "twitter")

    async def _discover_reddit(self, ctx: WorkflowContext) -> None:
        from adapters.reddit.orchestrator import EngagementOrchestrator
        from adapters.reddit.settings import RedditSettings

        settings = RedditSettings()
        max_comments = int(ctx.get_param("max_comments", 0) or 0)
        if max_comments > 0:
            settings = RedditSettings(
                **{**settings.model_dump(), "max_comments_per_day": max_comments},
            )

        orchestrator = EngagementOrchestrator(settings)

        with ctx.console.status("[bold cyan]Discovering Reddit posts..."):
            comments = await orchestrator.generate_only()

        if not comments:
            raise WorkflowError("No comments generated for Reddit.")

        ctx.console.print(f"[green]Generated {len(comments)} comments for Reddit[/green]")
        ctx.set_artifact("generated_replies", comments)
        ctx.set_artifact("engagement_orchestrator", orchestrator)
        ctx.set_artifact("engagement_platform", "reddit")

    async def _discover_facebook(self, ctx: WorkflowContext) -> None:
        from adapters.facebook import settings as _fb_settings_mod
        from adapters.facebook.browser import FacebookBrowser
        from adapters.facebook.orchestrator import EngagementOrchestrator
        from adapters.facebook.settings import FacebookSettings

        settings = FacebookSettings()
        headless = ctx.get_param("headless", True)
        if headless:
            settings = settings.model_copy(update={"headless": True})

        max_comments = int(ctx.get_param("max_comments", 0) or 0)
        if max_comments > 0:
            settings = settings.model_copy(update={"max_comments_per_day": max_comments})

        project_slug = ctx.project.slug if ctx.project else None
        if project_slug:
            project_targets = Path(f"projects/{project_slug}/targets/facebook.yaml")
            if project_targets.exists():
                settings = settings.model_copy(update={"targets_path": project_targets})

        _reject_default_targets(
            settings.targets_path,
            _fb_settings_mod.__file__,
            "facebook",
            project_slug,
        )

        browser = FacebookBrowser(
            session_path=settings.facebook_session_path,
            user_data_dir=settings.facebook_user_data_dir,
            headless=settings.headless,
            slow_mo_ms=settings.slow_mo_ms,
            proxy_url=settings.proxy_url,
            viewport_width=settings.viewport_width,
            viewport_height=settings.viewport_height,
        )

        async with browser:
            if not await browser.is_logged_in():
                c_user = settings.facebook_c_user
                xs = settings.facebook_xs
                if c_user and xs:
                    await browser.login_with_cookies(c_user, xs)
                else:
                    raise WorkflowError(
                        "Not logged into Facebook. "
                        "Run `mmn facebook login` first, or set FACEBOOK_C_USER and FACEBOOK_XS in .env."
                    )

            orchestrator = EngagementOrchestrator(
                settings,
                browser,
                project_slug=project_slug,
            )

            with ctx.console.status("[bold cyan]Discovering Facebook group posts..."):
                comments = await orchestrator.generate_only()

        if not comments:
            raise WorkflowError("No comments generated for Facebook groups.")

        ctx.console.print(f"[green]Generated {len(comments)} comments for Facebook groups[/green]")
        ctx.set_artifact("generated_replies", comments)
        ctx.set_artifact("engagement_orchestrator", orchestrator)
        ctx.set_artifact("engagement_platform", "facebook")
        ctx.set_artifact("_facebook_settings", settings)
