from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from marketmenow.core.feedback.guideline_generator import (
    GuidelineGenerator,
    should_generate_guidelines,
)
from marketmenow.core.feedback.models import (
    CommentData,
    ContentGuideline,
    FeedbackReport,
    GuidelinesFile,
    ReelIndexEntry,
    VideoMetrics,
)
from marketmenow.core.feedback.ports import VideoAnalyticsFetcher
from marketmenow.core.feedback.sentiment import SentimentScorer
from marketmenow.core.reel_id import decode_reel_id

logger = logging.getLogger(__name__)


class FeedbackOrchestrator:
    """Central coordinator for the YouTube reel feedback cycle."""

    def __init__(
        self,
        fetcher: VideoAnalyticsFetcher,
        sentiment_scorer: SentimentScorer,
        guideline_generator: GuidelineGenerator,
        project_slug: str,
        project_root: Path,
    ) -> None:
        self._fetcher = fetcher
        self._scorer = sentiment_scorer
        self._generator = guideline_generator
        self._project_slug = project_slug
        self._feedback_dir = project_root / "projects" / project_slug / "feedback" / "youtube"

    @property
    def feedback_dir(self) -> Path:
        return self._feedback_dir

    async def run_feedback_cycle(
        self,
        *,
        since: datetime | None = None,
        view_threshold: int = 250,
        max_videos: int = 50,
    ) -> FeedbackReport:
        """Run a full feedback cycle: fetch -> score -> analyze -> persist.

        Uses DB cache when available — only scores comments for videos not
        already in the cache.  Falls back to file-based storage if the DB
        is unavailable.
        """
        from marketmenow.core.feedback import db as fdb

        self._feedback_dir.mkdir(parents=True, exist_ok=True)
        comments_dir = self._feedback_dir / "comments"
        comments_dir.mkdir(exist_ok=True)

        # Try to initialise DB cache
        db_available = await fdb.ensure_schema()

        # Load existing state
        index = self._load_index()
        existing_guidelines = self._load_guidelines()

        # If DB is available, also load guidelines from DB
        if db_available:
            db_guidelines = await fdb.get_guidelines(self._project_slug)
            if db_guidelines:
                existing_guidelines = db_guidelines

        # Fetch channel videos from YouTube API
        videos = await self._fetcher.fetch_channel_videos(
            max_results=max_videos,
            published_after=since,
        )
        if not videos:
            return FeedbackReport(reels_analyzed=0)

        # Fetch stats (always refresh — views/likes change)
        video_ids = [v["video_id"] for v in videos]
        stats_list = await self._fetcher.fetch_video_stats(video_ids)
        stats_map: dict[str, VideoMetrics] = {s.video_id: s for s in stats_list}

        # Determine which videos need comment scoring
        already_scored: set[str] = set()
        if db_available:
            already_scored = await fdb.get_scored_video_ids(self._project_slug)

        # Process each video
        new_entries: list[ReelIndexEntry] = []
        flagged: list[str] = []
        all_sentiments: list[float] = []
        new_guidelines: list[ContentGuideline] = []

        for video in videos:
            vid = video["video_id"]
            metrics = stats_map.get(vid)

            identifier = decode_reel_id(video.get("description", ""))
            reel_id = identifier.reel_id if identifier else vid
            template_type_id = identifier.template_type_id if identifier else ""

            existing = next((e for e in index if e.video_id == vid), None)

            needs_scoring = vid not in already_scored

            # Upsert video row first (needed as FK parent for comments)
            if db_available:
                await fdb.upsert_video(
                    vid,
                    self._project_slug,
                    reel_id=reel_id,
                    template_id=existing.template_id if existing else "",
                    template_type_id=template_type_id,
                    title=video.get("title", ""),
                    description=video.get("description", ""),
                    published_at=video.get("published_at", ""),
                    metrics=metrics,
                    avg_sentiment=5.0,
                    comments_scored=False,
                )

            if needs_scoring:
                # Fetch and score comments (expensive — only for new videos)
                raw_comments = await self._fetcher.fetch_comments(vid, max_results=100)
                scored_comments: list[CommentData] = []
                if raw_comments:
                    scored_comments = await self._scorer.score_comments(
                        raw_comments, video.get("title", "")
                    )
                    # Persist comments to file
                    comments_path = comments_dir / f"{vid}.json"
                    comments_path.write_text(
                        json.dumps(
                            [c.model_dump() for c in scored_comments],
                            indent=2,
                            default=str,
                        ),
                        encoding="utf-8",
                    )
                    # Cache comments in DB
                    if db_available:
                        await fdb.upsert_comments(vid, scored_comments)

                avg_sentiment = (
                    sum(c.sentiment_score for c in scored_comments) / len(scored_comments)
                    if scored_comments
                    else 5.0
                )
            else:
                # Load cached comments + sentiment from DB
                scored_comments = await fdb.get_cached_comments(vid) if db_available else []
                avg_sentiment = (
                    sum(c.sentiment_score for c in scored_comments) / len(scored_comments)
                    if scored_comments
                    else 5.0
                )

            all_sentiments.append(avg_sentiment)

            entry = ReelIndexEntry(
                reel_id=reel_id,
                video_id=vid,
                template_id=existing.template_id if existing else "",
                template_type_id=template_type_id,
                title=video.get("title", ""),
                description=video.get("description", ""),
                script=existing.script if existing else "",
                published_at=video.get("published_at", ""),
                metrics=metrics,
                comments=scored_comments,
                avg_sentiment=avg_sentiment,
            )
            new_entries.append(entry)

            # Update video with final sentiment + metrics + scored flag
            if db_available:
                await fdb.upsert_video(
                    vid,
                    self._project_slug,
                    reel_id=reel_id,
                    template_id=existing.template_id if existing else "",
                    template_type_id=template_type_id,
                    title=video.get("title", ""),
                    description=video.get("description", ""),
                    published_at=video.get("published_at", ""),
                    metrics=metrics,
                    avg_sentiment=avg_sentiment,
                    comments_scored=needs_scoring,
                )

            # Generate guidelines only for newly scored videos
            if needs_scoring:
                guideline_type = should_generate_guidelines(entry)
                if guideline_type:
                    flagged.append(vid)
                    try:
                        generated = await self._generator.analyze_reel(
                            entry, existing_guidelines + new_guidelines
                        )
                        new_guidelines.extend(generated)
                    except Exception:
                        logger.exception("Failed to generate guidelines for video %s", vid)

        # Update file-based index
        index_map = {e.video_id: e for e in index}
        for entry in new_entries:
            index_map[entry.video_id] = entry
        self._save_index(list(index_map.values()))

        # Merge and save guidelines
        if new_guidelines:
            all_guidelines = existing_guidelines + new_guidelines
            self._save_guidelines(all_guidelines)
            if db_available:
                await fdb.upsert_guidelines(self._project_slug, new_guidelines)

        overall_sentiment = sum(all_sentiments) / len(all_sentiments) if all_sentiments else 5.0

        scored_count = sum(1 for v in videos if v["video_id"] not in already_scored)
        skipped_count = len(videos) - scored_count
        if skipped_count > 0:
            logger.info(
                "Feedback cache: scored %d new videos, skipped %d cached",
                scored_count,
                skipped_count,
            )

        return FeedbackReport(
            reels_analyzed=len(new_entries),
            new_guidelines_count=len(new_guidelines),
            avg_sentiment=overall_sentiment,
            flagged_reels=flagged,
        )

    def _load_index(self) -> list[ReelIndexEntry]:
        path = self._feedback_dir / "reel_index.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [ReelIndexEntry(**item) for item in data]
        except Exception:
            logger.warning("Failed to load reel index, starting fresh")
            return []

    def _save_index(self, entries: list[ReelIndexEntry]) -> None:
        path = self._feedback_dir / "reel_index.json"
        path.write_text(
            json.dumps(
                [e.model_dump() for e in entries],
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    def _load_guidelines(self) -> list[ContentGuideline]:
        path = self._feedback_dir / "guidelines.yaml"
        if not path.exists():
            return []
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not data or "guidelines" not in data:
                return []
            return [ContentGuideline(**g) for g in data["guidelines"]]
        except Exception:
            logger.warning("Failed to load guidelines, starting fresh")
            return []

    def _save_guidelines(self, guidelines: list[ContentGuideline]) -> None:
        path = self._feedback_dir / "guidelines.yaml"
        data = GuidelinesFile(
            guidelines=guidelines,
            last_updated=datetime.now(UTC).isoformat(),
        )
        path.write_text(
            yaml.dump(
                data.model_dump(),
                default_flow_style=False,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
