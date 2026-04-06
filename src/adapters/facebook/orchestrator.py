from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, Field

from .browser import FacebookBrowser
from .comment_generator import CommentGenerator
from .discovery import GroupPostDiscoverer
from .settings import FacebookSettings

logger = logging.getLogger(__name__)


def _ensure_vertex_credentials(settings: FacebookSettings) -> None:
    creds = settings.google_application_credentials
    if creds and creds.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(creds.resolve()))


class GeneratedComment(BaseModel, frozen=True):
    """A single discover+generate result, ready to be reviewed or posted."""

    group_url: str
    group_name: str
    post_url: str
    post_text: str
    post_author: str
    reactions_count: int = 0
    comments_count: int = 0
    comment_text: str


class AuditEntry(BaseModel):
    timestamp: str
    group_name: str
    post_url: str
    post_author: str
    comment_text: str
    success: bool
    error: str = ""


class EngagementStats(BaseModel):
    total_discovered: int = 0
    total_attempted: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    posts_by_group: dict[str, int] = Field(default_factory=dict)


@runtime_checkable
class ProgressCallback(Protocol):
    def on_discovery_start(self, total_groups: int) -> None: ...
    def on_group_done(self, group_name: str, posts_found: int) -> None: ...
    def on_discovery_end(self, total_posts: int, candidates: int) -> None: ...
    def on_generating(self, current: int, total: int, group_name: str) -> None: ...
    def on_generated(
        self, current: int, total: int, group_name: str, comment_text: str
    ) -> None: ...
    def on_generate_failed(self, current: int, total: int, group_name: str) -> None: ...
    def on_comment_posted(
        self, current: int, total: int, group_name: str, success: bool
    ) -> None: ...
    def on_comment_wait(self, seconds: int) -> None: ...
    def on_complete(self, stats: EngagementStats) -> None: ...


class _NullProgress:
    def on_discovery_start(self, total_groups: int) -> None: ...
    def on_group_done(self, group_name: str, posts_found: int) -> None: ...
    def on_discovery_end(self, total_posts: int, candidates: int) -> None: ...
    def on_generating(self, current: int, total: int, group_name: str) -> None: ...
    def on_generated(
        self, current: int, total: int, group_name: str, comment_text: str
    ) -> None: ...
    def on_generate_failed(self, current: int, total: int, group_name: str) -> None: ...
    def on_comment_posted(
        self, current: int, total: int, group_name: str, success: bool
    ) -> None: ...
    def on_comment_wait(self, seconds: int) -> None: ...
    def on_complete(self, stats: EngagementStats) -> None: ...


class EngagementOrchestrator:
    """Runs the full discover-generate-comment engagement loop for Facebook groups."""

    def __init__(
        self,
        settings: FacebookSettings,
        browser: FacebookBrowser,
        project_slug: str | None = None,
    ) -> None:
        self._settings = settings
        self._browser = browser
        self._project_slug = project_slug

    async def generate_only(
        self,
        progress: ProgressCallback | None = None,
    ) -> list[GeneratedComment]:
        """Discover posts in groups and generate comments without posting."""
        _ensure_vertex_credentials(self._settings)
        prog: ProgressCallback = progress or _NullProgress()  # type: ignore[assignment]

        discoverer = GroupPostDiscoverer(
            self._browser,
            self._settings.comment_history_path,
        )
        generator = CommentGenerator(
            gemini_model=self._settings.gemini_model,
            mention_rate=self._settings.mention_rate,
            vertex_project=self._settings.vertex_ai_project,
            vertex_location=self._settings.vertex_ai_location,
            project_slug=self._project_slug,
            top_examples_path=self._settings.top_examples_path,
            max_examples=self._settings.max_examples_in_prompt,
            epsilon=self._settings.epsilon,
        )

        targets = self._load_targets()
        groups: list[dict[str, str]] = targets.get("groups", [])

        if not groups:
            logger.warning("No groups configured in targets file: %s", self._settings.targets_path)
            return []

        random.shuffle(groups)
        group_subset = groups[: random.randint(2, min(5, len(groups)))]

        prog.on_discovery_start(len(group_subset))

        all_posts = await discoverer.discover_all_groups(
            group_subset,
            max_per_group=3,
        )

        posts_by_group: dict[str, int] = {}
        for p in all_posts:
            posts_by_group[p.group_name] = posts_by_group.get(p.group_name, 0) + 1
        for gname, gcount in posts_by_group.items():
            prog.on_group_done(gname, gcount)

        all_posts.sort(
            key=lambda p: (p.reactions_count + p.comments_count, p.discovered_at),
            reverse=True,
        )
        candidates = all_posts[: self._settings.max_comments_per_day]
        random.shuffle(candidates)

        prog.on_discovery_end(len(all_posts), len(candidates))

        results: list[GeneratedComment] = []
        for i, post in enumerate(candidates, start=1):
            prog.on_generating(i, len(candidates), post.group_name)

            try:
                comment_text = await generator.generate_comment(
                    post,
                    comment_number=i,
                )
            except Exception:
                logger.exception(
                    "Failed to generate comment for %s post %s",
                    post.group_name,
                    post.post_url,
                )
                prog.on_generate_failed(i, len(candidates), post.group_name)
                continue

            prog.on_generated(i, len(candidates), post.group_name, comment_text)
            results.append(
                GeneratedComment(
                    group_url=post.group_url,
                    group_name=post.group_name,
                    post_url=post.post_url,
                    post_text=post.post_text,
                    post_author=post.post_author,
                    reactions_count=post.reactions_count,
                    comments_count=post.comments_count,
                    comment_text=comment_text,
                )
            )

        stats = EngagementStats(
            total_discovered=len(all_posts),
            total_attempted=len(candidates),
            total_succeeded=len(results),
            total_failed=len(candidates) - len(results),
            posts_by_group=posts_by_group,
        )
        prog.on_complete(stats)
        return results

    async def comment_from_list(
        self,
        comments: list[GeneratedComment],
        progress: ProgressCallback | None = None,
    ) -> EngagementStats:
        """Post comments from a pre-generated list."""
        stats = EngagementStats(total_discovered=len(comments))
        prog: ProgressCallback = progress or _NullProgress()  # type: ignore[assignment]

        discoverer = GroupPostDiscoverer(
            self._browser,
            self._settings.comment_history_path,
        )

        prog.on_discovery_end(len(comments), len(comments))

        for i, row in enumerate(comments, start=1):
            stats.total_attempted += 1
            prog.on_generating(i, len(comments), row.group_name)
            prog.on_generated(i, len(comments), row.group_name, row.comment_text)

            try:
                success = await self._browser.comment_on_group_post(
                    row.post_url,
                    row.comment_text,
                )
            except Exception as exc:
                logger.exception("Failed to post comment on %s", row.post_url)
                success = False
                error_msg = str(exc)
            else:
                error_msg = "" if success else "Comment posting returned False"

            self._log_audit(
                AuditEntry(
                    timestamp=datetime.now(UTC).isoformat(),
                    group_name=row.group_name,
                    post_url=row.post_url,
                    post_author=row.post_author,
                    comment_text=row.comment_text,
                    success=success,
                    error=error_msg,
                )
            )

            if success:
                stats.total_succeeded += 1
                discoverer.mark_commented(row.post_url)
                prog.on_comment_posted(i, len(comments), row.group_name, success=True)
            else:
                stats.total_failed += 1
                prog.on_comment_posted(i, len(comments), row.group_name, success=False)

                if self._looks_like_rate_limit(error_msg):
                    logger.error(
                        "Rate-limited or blocked — halting for %d hours",
                        self._settings.cooldown_hours,
                    )
                    break

            if i < len(comments):
                delay = random.randint(
                    self._settings.min_delay_seconds,
                    self._settings.max_delay_seconds,
                )
                prog.on_comment_wait(delay)
                await asyncio.sleep(delay)

        prog.on_complete(stats)
        return stats

    def _load_targets(self) -> dict[str, list[dict[str, str]]]:
        path = self._settings.targets_path
        if not path.exists():
            logger.warning("Targets file not found: %s", path)
            return {}
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _log_audit(self, entry: AuditEntry) -> None:
        path = self._settings.audit_log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    @staticmethod
    def _looks_like_rate_limit(error_msg: str) -> bool:
        triggers = [
            "rate limit",
            "ratelimit",
            "429",
            "too many requests",
            "blocked",
            "suspended",
            "banned",
            "checkpoint",
            "temporarily",
        ]
        lower = error_msg.lower()
        return any(t in lower for t in triggers)
