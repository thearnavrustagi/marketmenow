from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from marketmenow.core.workflow import WorkflowContext, WorkflowError


class YouTubeUploadStep:
    """Upload a local video as a YouTube Short.

    Reads the video from either the ``video`` param (explicit path) or
    the ``content`` artifact (from a prior GenerateReelStep).  YouTube
    metadata can come from explicit params or from artifacts set by
    PrepareYouTubeStep (``_yt_title``, ``_yt_description``, ``_yt_hashtags``).
    """

    @property
    def name(self) -> str:
        return "youtube-upload"

    @property
    def description(self) -> str:
        return "Upload video to YouTube Shorts"

    async def execute(self, ctx: WorkflowContext) -> None:
        from adapters.youtube import create_youtube_bundle
        from adapters.youtube.settings import YouTubeSettings
        from marketmenow.core.pipeline import ContentPipeline
        from marketmenow.models.content import MediaAsset, VideoPost
        from marketmenow.registry import AdapterRegistry

        settings = YouTubeSettings()
        if not settings.youtube_refresh_token:
            raise WorkflowError("YOUTUBE_REFRESH_TOKEN not set. Run `mmn auth youtube` first.")

        # Resolve video path: explicit param > content artifact
        video_param = ctx.get_param("video", "")
        video_path: Path | None = None
        if video_param:
            video_path = Path(str(video_param))
        else:
            content = ctx.artifacts.get("content")
            if content is not None and hasattr(content, "video"):
                video_path = Path(content.video.uri)

        if video_path is None or not video_path.exists():
            raise WorkflowError(f"Video file not found: {video_path}")

        # Resolve metadata: explicit params > artifacts from PrepareYouTubeStep
        title = str(ctx.get_param("title", "") or "") or str(
            ctx.artifacts.get("_yt_title", "") or ""
        )
        description = str(ctx.get_param("description", "") or "") or str(
            ctx.artifacts.get("_yt_description", "") or ""
        )
        hashtags_raw = str(ctx.get_param("hashtags", "") or "") or str(
            ctx.artifacts.get("_yt_hashtags", "") or ""
        )
        tags = [t.strip() for t in hashtags_raw.split(",") if t.strip()]
        privacy = str(ctx.get_param("privacy", "") or "")

        caption_parts = [p for p in [title, description] if p]
        caption = "\n\n".join(caption_parts) if caption_parts else ""
        meta: dict[str, str] = {}
        if title:
            meta["_yt_title"] = title

        # Inject reel ID from prior InjectReelIdStep or generate fresh
        reel_id_hex = ctx.artifacts.get("_reel_id_hex")
        tmpl_type_hex = ctx.artifacts.get("_template_type_hex")
        if reel_id_hex and tmpl_type_hex:
            meta["_reel_id_bytes"] = str(reel_id_hex)
            meta["_template_type_bytes"] = str(tmpl_type_hex)
        else:
            from marketmenow.core.reel_id import generate_reel_id, template_type_id_from_slug

            template_slug = str(ctx.get_param("template", "") or "")
            meta["_reel_id_bytes"] = generate_reel_id().hex()
            meta["_template_type_bytes"] = (
                template_type_id_from_slug(template_slug).hex()
                if template_slug
                else generate_reel_id().hex()
            )

        video_post = VideoPost(
            id=uuid4(),
            video=MediaAsset(uri=str(video_path.resolve()), mime_type="video/mp4"),
            caption=caption,
            hashtags=tags,
            metadata=meta,
        )

        bundle = create_youtube_bundle(settings)
        if privacy:
            bundle.adapter._default_privacy = privacy  # type: ignore[attr-defined]

        registry = AdapterRegistry()
        registry.register(bundle)
        pipeline = ContentPipeline(registry)

        with ctx.console.status("[bold blue]Uploading to YouTube Shorts..."):
            result = await pipeline.execute(video_post, "youtube")

        if hasattr(result, "success") and result.success:
            url = getattr(result, "remote_url", "") or ""
            post_id = getattr(result, "remote_post_id", "") or ""
            ctx.console.print(f"[green]Published to YouTube![/green] {url}")

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
                            platform="youtube",
                            remote_url=url,
                            remote_post_id=post_id,
                        ),
                    )
                except Exception:
                    pass  # Don't fail the upload over capsule bookkeeping
        else:
            err = getattr(result, "error_message", str(result))
            ctx.console.print(f"[red]YouTube upload failed:[/red] {err}")

        ctx.set_artifact("publish_result", result)
