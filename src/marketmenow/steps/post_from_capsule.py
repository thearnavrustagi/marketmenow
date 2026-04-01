from __future__ import annotations

from marketmenow.core.workflow import WorkflowContext, WorkflowError


class PostFromCapsuleStep:
    """Post content to any platform using only a capsule ID.

    Loads the capsule, converts it to the appropriate ``BaseContent``
    subclass, runs it through ``ContentPipeline``, and records the
    publication back to the capsule's ``meta.yaml``.
    """

    def __init__(self, platform: str | None = None) -> None:
        self._platform = platform

    @property
    def name(self) -> str:
        label = self._platform or "platform"
        return f"post-capsule-to-{label}"

    @property
    def description(self) -> str:
        label = self._platform or "target platform"
        return f"Post capsule content to {label}"

    async def execute(self, ctx: WorkflowContext) -> None:
        from marketmenow.core.capsule import CapsuleManager, CapsulePublication
        from marketmenow.core.pipeline import ContentPipeline
        from marketmenow.core.registry_builder import build_registry

        if ctx.get_param("dry_run", False):
            ctx.console.print("[yellow]Dry run -- skipping publish.[/yellow]")
            return

        capsule_id = str(ctx.get_param("capsule", "") or "")
        if not capsule_id:
            capsule_id = str(ctx.artifacts.get("capsule_id", "") or "")
        if not capsule_id:
            raise WorkflowError("No capsule ID provided (--capsule param or capsule_id artifact)")

        project_slug = str(ctx.get_param("project", "") or "")
        if not project_slug and ctx.project:
            project_slug = ctx.project.slug
        if not project_slug:
            raise WorkflowError("No project slug available")

        platform = self._platform or str(ctx.get_param("platform", "") or "")
        if not platform:
            raise WorkflowError("No target platform specified (--platform param)")

        mgr = CapsuleManager()
        capsule = mgr.load(project_slug, capsule_id)
        content = mgr.to_content(capsule, project_slug)

        registry = build_registry()
        pipeline = ContentPipeline(registry)

        with ctx.console.status(f"[bold blue]Publishing capsule to {platform}..."):
            result = await pipeline.execute(content, platform)

        if hasattr(result, "success") and result.success:
            url = getattr(result, "remote_url", "") or ""
            post_id = getattr(result, "remote_post_id", "") or ""
            ctx.console.print(f"[green]Published to {platform}![/green] {url}")

            mgr.record_publication(
                project_slug,
                capsule_id,
                CapsulePublication(
                    platform=platform,
                    remote_url=url,
                    remote_post_id=post_id,
                ),
            )
        else:
            err = getattr(result, "error_message", str(result))
            raise WorkflowError(f"Publish capsule to {platform} failed: {err}")

        ctx.set_artifact("publish_result", result)
