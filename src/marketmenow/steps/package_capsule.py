from __future__ import annotations

import logging
from pathlib import Path

from marketmenow.core.workflow import WorkflowContext

logger = logging.getLogger(__name__)


class PackageCapsuleStep:
    """Package generated content into a self-contained Content Capsule.

    Reads the ``content`` artifact (VideoPost, ImagePost, or Thread) from
    context, creates a capsule directory with media files and generation
    metadata, then sets ``capsule_id`` and ``capsule`` artifacts for
    downstream steps.
    """

    @property
    def name(self) -> str:
        return "package-capsule"

    @property
    def description(self) -> str:
        return "Package content into a reusable capsule"

    async def execute(self, ctx: WorkflowContext) -> None:
        from marketmenow.core.capsule import (
            CapsuleGenerationParams,
            CapsuleManager,
        )
        from marketmenow.models.content import ImagePost, Thread, VideoPost

        content = ctx.artifacts.get("content")
        if content is None:
            logger.warning("No content artifact found, skipping capsule packaging")
            return

        project_slug = str(ctx.get_param("project", "") or "")
        if not project_slug and ctx.project:
            project_slug = ctx.project.slug
        if not project_slug:
            logger.warning("No project slug available, skipping capsule packaging")
            return

        mgr = CapsuleManager()

        # Determine modality and extract metadata
        caption = ""
        title = ""
        hashtags: list[str] = []
        template_id = str(ctx.get_param("template", "") or "")
        thread_entries: list[str] = []

        if isinstance(content, VideoPost):
            modality = "video"
            caption = content.caption
            hashtags = list(content.hashtags)
        elif isinstance(content, ImagePost):
            modality = "image"
            caption = content.caption
            hashtags = list(content.hashtags)
        elif isinstance(content, Thread):
            modality = "thread"
            thread_entries = [entry.text for entry in content.entries]
        else:
            logger.warning("Unsupported content type for capsule: %s", type(content).__name__)
            return

        # Build generation params from CLI params
        gen_params: dict[str, str] = {}
        for key in ("assignment", "rubric", "comment_username", "comment_text", "student_name"):
            val = ctx.get_param(key, "")
            if val:
                gen_params[key] = str(val)

        tts_provider = str(ctx.get_param("tts", "") or "")
        generation = CapsuleGenerationParams(
            tts_provider=tts_provider,
            template_id=template_id,
            params=gen_params,
        )

        # Reel tracking IDs
        reel_id_hex = str(ctx.artifacts.get("_reel_id_hex", "") or "")
        template_type_hex = str(ctx.artifacts.get("_template_type_hex", "") or "")

        # YouTube metadata if available
        title = str(ctx.artifacts.get("_yt_title", "") or "")
        description = str(ctx.artifacts.get("_yt_description", "") or "")

        capsule = mgr.create(
            project_slug,
            modality,
            caption=caption,
            title=title,
            description=description,
            hashtags=hashtags,
            template_id=template_id,
            generation=generation,
            reel_id_hex=reel_id_hex,
            template_type_hex=template_type_hex,
            thread_entries=thread_entries,
        )

        # Copy media files into capsule
        if isinstance(content, VideoPost):
            video_path = Path(content.video.uri)
            if video_path.exists():
                mgr.add_media(
                    project_slug,
                    capsule.capsule_id,
                    video_path,
                    mime_type=content.video.mime_type,
                    role="primary",
                )
            if content.thumbnail:
                thumb_path = Path(content.thumbnail.uri)
                if thumb_path.exists():
                    mgr.add_media(
                        project_slug,
                        capsule.capsule_id,
                        thumb_path,
                        mime_type=content.thumbnail.mime_type,
                        role="thumbnail",
                    )
        elif isinstance(content, ImagePost):
            for i, img in enumerate(content.images):
                img_path = Path(img.uri)
                if img_path.exists():
                    role = "primary" if i == 0 else "slide"
                    mgr.add_media(
                        project_slug,
                        capsule.capsule_id,
                        img_path,
                        mime_type=img.mime_type,
                        role=role,
                    )

        # Save script artifacts for regeneration
        reel_script = ctx.artifacts.get("_reel_script")
        if reel_script is not None and hasattr(reel_script, "model_dump"):
            mgr.save_script_artifact(
                project_slug,
                capsule.capsule_id,
                "reel_script",
                reel_script.model_dump(),
            )

        generated_thread = ctx.artifacts.get("generated_thread")
        if generated_thread is not None and hasattr(generated_thread, "model_dump"):
            mgr.save_script_artifact(
                project_slug,
                capsule.capsule_id,
                "thread",
                generated_thread.model_dump(),
            )

        carousel_meta = ctx.artifacts.get("_carousel_meta")
        if carousel_meta is not None and isinstance(carousel_meta, dict):
            mgr.save_script_artifact(
                project_slug,
                capsule.capsule_id,
                "carousel",
                carousel_meta,
            )

        # Reload to get updated media list after add_media calls
        capsule = mgr.load(project_slug, capsule.capsule_id)

        ctx.set_artifact("capsule_id", capsule.capsule_id)
        ctx.set_artifact("capsule", capsule)

        ctx.console.print(
            f"[cyan]Capsule packaged:[/cyan] {capsule.capsule_id} "
            f"({len(capsule.media)} media files)"
        )
