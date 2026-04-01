from __future__ import annotations

from marketmenow.core.workflow import WorkflowContext, WorkflowError


class PostToPlatformStep:
    """Publish content to a platform via ContentPipeline.

    Reads ``content`` and ``platform`` from context artifacts.
    If constructed with a fixed *platform*, that overrides the context value.
    """

    def __init__(self, platform: str | None = None) -> None:
        self._platform = platform

    @property
    def name(self) -> str:
        label = self._platform or "platform"
        return f"post-to-{label}"

    @property
    def description(self) -> str:
        label = self._platform or "target platform"
        return f"Publish content to {label}"

    async def execute(self, ctx: WorkflowContext) -> None:
        from marketmenow.core.pipeline import ContentPipeline
        from marketmenow.core.registry_builder import build_registry
        from marketmenow.models.content import BaseContent

        if ctx.get_param("dry_run", False):
            ctx.console.print("[yellow]Dry run — skipping publish.[/yellow]")
            return

        content = ctx.get_artifact("content")
        if not isinstance(content, BaseContent):
            raise WorkflowError("Artifact 'content' is not a BaseContent instance")

        platform = self._platform or str(ctx.artifacts.get("platform", ""))
        if not platform:
            raise WorkflowError("No target platform specified")

        registry = build_registry()
        pipeline = ContentPipeline(registry)

        with ctx.console.status(f"[bold blue]Publishing to {platform}..."):
            result = await pipeline.execute(content, platform)

        ctx.set_artifact("publish_result", result)

        if hasattr(result, "success") and result.success:
            url = getattr(result, "remote_url", None) or ""
            post_id = getattr(result, "remote_post_id", None) or ""
            ctx.console.print(f"[green]Published to {platform}![/green] {url}")

            # Record publication to capsule if one exists
            capsule_id = str(ctx.artifacts.get("capsule_id", "") or "")
            project_slug = str(ctx.params.get("project", "") or "")
            if not project_slug and ctx.project:
                project_slug = ctx.project.slug
            if capsule_id and project_slug:
                try:
                    from marketmenow.core.capsule import CapsuleManager, CapsulePublication

                    mgr = CapsuleManager()
                    mgr.record_publication(
                        project_slug,
                        capsule_id,
                        CapsulePublication(
                            platform=platform,
                            remote_url=url,
                            remote_post_id=post_id,
                        ),
                    )
                except Exception:
                    pass  # Don't fail the publish over capsule bookkeeping
        else:
            err = getattr(result, "error_message", str(result))
            raise WorkflowError(f"Publish to {platform} failed: {err}")
