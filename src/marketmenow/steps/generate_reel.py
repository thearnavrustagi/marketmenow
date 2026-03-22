from __future__ import annotations

from pathlib import Path

from marketmenow.core.workflow import WorkflowContext


class GenerateReelStep:
    """Generate an Instagram reel from a YAML template via ReelOrchestrator."""

    @property
    def name(self) -> str:
        return "generate-reel"

    @property
    def description(self) -> str:
        return "Generate reel video from template"

    async def execute(self, ctx: WorkflowContext) -> None:
        from adapters.instagram.reels.orchestrator import ReelOrchestrator
        from adapters.instagram.settings import InstagramSettings

        settings = InstagramSettings()

        tts = str(ctx.get_param("tts", "") or "")
        output_dir = ctx.get_param("output_dir")
        updates: dict[str, object] = {}
        if tts:
            updates["tts_provider"] = tts
        if output_dir:
            updates["output_dir"] = Path(str(output_dir))
        if updates:
            settings = settings.model_copy(update=updates)

        template_dir: Path | None = None
        project_slug = ctx.get_param("project")
        if project_slug:
            from marketmenow.core.project_manager import ProjectManager

            pm = ProjectManager()
            project_templates = pm.project_dir(str(project_slug)) / "templates" / "reels"
            if project_templates.is_dir():
                template_dir = project_templates

        template_id = str(ctx.get_param("template", "can_ai_grade_this"))

        rubric_items = None
        rubric_path = ctx.get_param("rubric")
        if rubric_path:
            import yaml

            from adapters.instagram.grading.models import RubricItem

            raw = yaml.safe_load(Path(str(rubric_path)).read_text())
            if isinstance(raw, list):
                rubric_items = [RubricItem(**item) for item in raw]
            elif isinstance(raw, dict) and "rubric_items" in raw:
                rubric_items = [RubricItem(**item) for item in raw["rubric_items"]]

        assignment = ctx.get_param("assignment")
        assignment_path = Path(str(assignment)) if assignment else None

        caption = str(ctx.get_param("caption", "") or "")
        hashtags_raw = str(ctx.get_param("hashtags", "") or "")
        hashtags = [t.strip() for t in hashtags_raw.split(",") if t.strip()] or None

        orch = ReelOrchestrator(settings, templates_dir=template_dir)

        with ctx.console.status(f"[bold green]Generating reel (template={template_id})..."):
            reel = await orch.create_reel(
                assignment_image=assignment_path,
                template_id=template_id,
                rubric_items=rubric_items,
                caption=caption,
                hashtags=hashtags,
                reaction_image=None,
                comment_username=str(ctx.get_param("comment_username", "") or ""),
                comment_avatar=None,
                comment_text=str(ctx.get_param("comment_text", "") or ""),
                student_name=str(ctx.get_param("student_name", "") or ""),
            )

        ctx.console.print(f"[green]Reel rendered:[/green] {reel.video.uri}")
        ctx.set_artifact("content", reel)
        ctx.set_artifact("platform", "instagram")
