from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from marketmenow.core.workflow import WorkflowContext

logger = logging.getLogger(__name__)


class FetchYouTubeFeedbackStep:
    """Fetch analytics from prior YouTube uploads and load guidelines.

    Uses a Neon DB cache when available — already-scored videos are
    skipped, making subsequent runs complete in seconds rather than
    minutes.  Falls back to file-based storage when no DB is configured.
    """

    @property
    def name(self) -> str:
        return "fetch-youtube-feedback"

    @property
    def description(self) -> str:
        return "Fetch YouTube analytics and generate content guidelines"

    async def execute(self, ctx: WorkflowContext) -> None:
        try:
            from adapters.youtube.analytics import YouTubeAnalyticsFetcher
            from adapters.youtube.settings import YouTubeSettings
        except ImportError:
            logger.info("YouTube adapter not available, skipping feedback step")
            return

        settings = YouTubeSettings()
        if not settings.youtube_refresh_token:
            ctx.console.print("[dim]No YouTube credentials, skipping feedback fetch[/dim]")
            return

        project_slug = str(ctx.get_param("project", "") or "")
        if not project_slug and ctx.project:
            project_slug = ctx.project.slug

        if not project_slug:
            ctx.console.print("[dim]No project set, skipping feedback fetch[/dim]")
            return

        project_root = Path.cwd()
        feedback_dir = project_root / "projects" / project_slug / "feedback" / "youtube"

        from marketmenow.core.feedback.models import ContentGuideline

        guidelines: list[ContentGuideline] = []

        # Try loading guidelines from DB cache first
        try:
            from marketmenow.core.feedback import db as fdb

            db_guidelines = await fdb.get_guidelines(project_slug)
            if db_guidelines:
                guidelines = db_guidelines
        except Exception:
            pass

        # Fall back to file-based guidelines
        if not guidelines and feedback_dir.exists():
            import yaml

            guidelines_path = feedback_dir / "guidelines.yaml"
            if guidelines_path.exists():
                try:
                    data = yaml.safe_load(guidelines_path.read_text(encoding="utf-8"))
                    if data and "guidelines" in data:
                        guidelines = [ContentGuideline(**g) for g in data["guidelines"]]
                except Exception:
                    logger.warning("Failed to load guidelines")

        days = int(ctx.get_param("feedback_days", 7) or 7)
        since = datetime.now(UTC) - timedelta(days=days)

        from adapters.instagram.settings import InstagramSettings
        from marketmenow.core.feedback.guideline_generator import GuidelineGenerator
        from marketmenow.core.feedback.orchestrator import FeedbackOrchestrator
        from marketmenow.core.feedback.sentiment import SentimentScorer
        from marketmenow.integrations.genai import configure_google_application_credentials

        ig_settings = InstagramSettings()
        configure_google_application_credentials(ig_settings.google_application_credentials)

        fetcher = YouTubeAnalyticsFetcher(
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            refresh_token=settings.youtube_refresh_token,
        )

        try:
            orch = FeedbackOrchestrator(
                fetcher=fetcher,
                sentiment_scorer=SentimentScorer(
                    vertex_project=ig_settings.vertex_ai_project,
                    vertex_location=ig_settings.vertex_ai_location,
                ),
                guideline_generator=GuidelineGenerator(
                    vertex_project=ig_settings.vertex_ai_project,
                    vertex_location=ig_settings.vertex_ai_location,
                ),
                project_slug=project_slug,
                project_root=project_root,
            )

            with ctx.console.status("[bold blue]Fetching YouTube feedback..."):
                report = await orch.run_feedback_cycle(since=since)

            if report.reels_analyzed > 0:
                ctx.console.print(
                    f"[green]Feedback:[/green] analyzed {report.reels_analyzed} reels, "
                    f"{report.new_guidelines_count} new guidelines, "
                    f"avg sentiment {report.avg_sentiment:.1f}/10"
                )

            # Reload guidelines after cycle
            guidelines_path = feedback_dir / "guidelines.yaml"
            if guidelines_path.exists():
                import yaml

                data = yaml.safe_load(guidelines_path.read_text(encoding="utf-8"))
                if data and "guidelines" in data:
                    guidelines = [ContentGuideline(**g) for g in data["guidelines"]]

        except Exception:
            logger.exception("Feedback cycle failed, continuing with existing guidelines")

        ctx.set_artifact("youtube_guidelines", guidelines)
