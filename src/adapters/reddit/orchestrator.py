from __future__ import annotations

import logging
import os
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, Field

from marketmenow.models.content import Reply
from marketmenow.normaliser import ContentNormaliser

from .adapter import RedditAdapter
from .client import RedditClient
from .comment_generator import CommentGenerator
from .discovery import DiscoveredPost, PostDiscoverer
from .renderer import RedditRenderer
from .settings import RedditSettings


def _ensure_vertex_credentials(settings: RedditSettings) -> None:
    creds = settings.google_application_credentials
    if creds and creds.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(creds.resolve()))


logger = logging.getLogger(__name__)


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    SKIP = "skip"
    EDIT = "edit"
    STOP = "stop"


class ApprovalResult(BaseModel):
    decision: ApprovalDecision
    edited_text: str = ""


ApprovalCallback = Callable[
    [DiscoveredPost, str, int, int],
    Awaitable[ApprovalResult],
]


class AuditEntry(BaseModel):
    timestamp: str
    subreddit: str
    post_url: str
    post_id: str
    author: str
    comment_text: str
    success: bool
    error: str = ""


class EngagementStats(BaseModel):
    total_discovered: int = 0
    total_attempted: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    posts_by_source: dict[str, int] = Field(default_factory=dict)


class GeneratedComment(BaseModel, frozen=True):
    """A single discover+generate result, ready to be reviewed or posted."""

    subreddit: str
    post_url: str
    post_id: str
    post_fullname: str
    post_title: str
    post_text: str
    author: str
    score: int = 0
    comment_text: str


@runtime_checkable
class ProgressCallback(Protocol):
    def on_discovery_start(self, total_subs: int, total_queries: int) -> None: ...
    def on_sub_done(self, subreddit: str, posts_found: int) -> None: ...
    def on_discovery_end(self, total_posts: int, candidates: int) -> None: ...
    def on_generating(self, current: int, total: int, subreddit: str) -> None: ...
    def on_generated(self, current: int, total: int, subreddit: str, comment_text: str) -> None: ...
    def on_generate_failed(self, current: int, total: int, subreddit: str) -> None: ...
    def on_comment_posted(
        self, current: int, total: int, subreddit: str, success: bool
    ) -> None: ...
    def on_comment_wait(self, seconds: int) -> None: ...
    def on_complete(self, stats: EngagementStats) -> None: ...


class _NullProgress:
    def on_discovery_start(self, total_subs: int, total_queries: int) -> None: ...
    def on_sub_done(self, subreddit: str, posts_found: int) -> None: ...
    def on_discovery_end(self, total_posts: int, candidates: int) -> None: ...
    def on_generating(self, current: int, total: int, subreddit: str) -> None: ...
    def on_generated(self, current: int, total: int, subreddit: str, comment_text: str) -> None: ...
    def on_generate_failed(self, current: int, total: int, subreddit: str) -> None: ...
    def on_comment_posted(
        self, current: int, total: int, subreddit: str, success: bool
    ) -> None: ...
    def on_comment_wait(self, seconds: int) -> None: ...
    def on_complete(self, stats: EngagementStats) -> None: ...


class EngagementOrchestrator:
    """Runs the full discover-generate-comment engagement loop for Reddit."""

    def __init__(self, settings: RedditSettings) -> None:
        self._settings = settings
        self._normaliser = ContentNormaliser()

    async def run(
        self,
        dry_run: bool = False,
        approval_callback: ApprovalCallback | None = None,
        progress: ProgressCallback | None = None,
    ) -> EngagementStats:
        _ensure_vertex_credentials(self._settings)

        stats = EngagementStats()
        prog: ProgressCallback = progress or _NullProgress()  # type: ignore[assignment]

        client = RedditClient(
            session_cookie=self._settings.reddit_session,
            username=self._settings.reddit_username,
            user_agent=self._settings.reddit_user_agent,
        )

        async with client:
            if not await client.is_logged_in():
                logger.error(
                    "Reddit session cookie is invalid or expired. Update REDDIT_SESSION in .env."
                )
                return stats

            adapter = RedditAdapter(client)
            renderer = RedditRenderer()
            discoverer = PostDiscoverer(
                client,
                self._settings.comment_history_path,
                own_username=self._settings.reddit_username,
            )
            generator = CommentGenerator(
                model=self._settings.gemini_model,
                mention_rate=self._settings.mention_rate,
                top_examples_path=self._settings.top_examples_path,
                max_examples=self._settings.max_examples_in_prompt,
                epsilon=self._settings.epsilon,
            )

            targets = self._load_targets()
            subreddits = targets.get("subreddits", [])
            queries = targets.get("search_queries", [])

            random.shuffle(subreddits)
            sub_subset = subreddits[: random.randint(4, 8)]

            prog.on_discovery_start(len(sub_subset), len(queries))

            search_posts = await discoverer.discover_search_posts(
                sub_subset,
                queries,
                max_per_query=2,
            )
            hot_posts = await discoverer.discover_hot_posts(sub_subset, max_per_sub=3)

            all_posts = discoverer._dedupe(search_posts + hot_posts)
            stats.total_discovered = len(all_posts)
            stats.posts_by_source = {
                "search": len(search_posts),
                "hot": len(hot_posts),
            }

            all_posts.sort(
                key=lambda p: (p.score, p.num_comments, p.discovered_at),
                reverse=True,
            )

            candidates = all_posts[: self._settings.max_comments_per_day]
            random.shuffle(candidates)

            prog.on_discovery_end(len(all_posts), len(candidates))

            for i, post in enumerate(candidates, start=1):
                stats.total_attempted += 1
                prog.on_generating(i, len(candidates), post.subreddit)

                try:
                    comment_text = await generator.generate_comment(
                        post,
                        comment_number=i,
                    )
                except Exception:
                    logger.exception(
                        "Failed to generate comment for r/%s post %s",
                        post.subreddit,
                        post.post_id,
                    )
                    stats.total_failed += 1
                    prog.on_generate_failed(i, len(candidates), post.subreddit)
                    continue

                prog.on_generated(i, len(candidates), post.subreddit, comment_text)

                if approval_callback is not None:
                    approval = await approval_callback(
                        post,
                        comment_text,
                        i,
                        len(candidates),
                    )
                    if approval.decision == ApprovalDecision.STOP:
                        logger.info("User stopped the engagement loop.")
                        break
                    if approval.decision == ApprovalDecision.SKIP:
                        stats.total_attempted -= 1
                        continue
                    if approval.decision == ApprovalDecision.EDIT:
                        comment_text = approval.edited_text

                if dry_run:
                    self._log_audit(
                        AuditEntry(
                            timestamp=datetime.now(UTC).isoformat(),
                            subreddit=post.subreddit,
                            post_url=post.post_url,
                            post_id=post.post_id,
                            author=post.author,
                            comment_text=comment_text,
                            success=True,
                            error="dry_run",
                        )
                    )
                    stats.total_succeeded += 1
                    prog.on_comment_posted(
                        i,
                        len(candidates),
                        post.subreddit,
                        success=True,
                    )
                    continue

                reply_content = Reply(
                    in_reply_to_url=post.post_url,
                    in_reply_to_platform_id=post.post_fullname,
                    body=comment_text,
                )
                normalised = self._normaliser.normalise(reply_content)
                rendered = await renderer.render(normalised)
                result = await adapter.publish(rendered)

                entry = AuditEntry(
                    timestamp=datetime.now(UTC).isoformat(),
                    subreddit=post.subreddit,
                    post_url=post.post_url,
                    post_id=post.post_id,
                    author=post.author,
                    comment_text=comment_text,
                    success=result.success,
                    error=result.error_message or "",
                )
                self._log_audit(entry)

                if result.success:
                    stats.total_succeeded += 1
                    discoverer.mark_commented(post.post_id)
                    prog.on_comment_posted(
                        i,
                        len(candidates),
                        post.subreddit,
                        success=True,
                    )
                else:
                    stats.total_failed += 1
                    prog.on_comment_posted(
                        i,
                        len(candidates),
                        post.subreddit,
                        success=False,
                    )

                    if self._looks_like_rate_limit(result.error_message or ""):
                        logger.error(
                            "Rate-limited or blocked — halting for %d hours",
                            self._settings.cooldown_hours,
                        )
                        break

                if i < len(candidates):
                    delay = random.randint(
                        self._settings.min_delay_seconds,
                        self._settings.max_delay_seconds,
                    )
                    prog.on_comment_wait(delay)
                    import asyncio

                    await asyncio.sleep(delay)

        prog.on_complete(stats)
        return stats

    async def generate_only(
        self,
        progress: ProgressCallback | None = None,
    ) -> list[GeneratedComment]:
        _ensure_vertex_credentials(self._settings)
        prog: ProgressCallback = progress or _NullProgress()  # type: ignore[assignment]

        client = RedditClient(
            session_cookie=self._settings.reddit_session,
            username=self._settings.reddit_username,
            user_agent=self._settings.reddit_user_agent,
        )

        results: list[GeneratedComment] = []

        async with client:
            if not await client.is_logged_in():
                logger.error("Reddit session cookie is invalid or expired.")
                return results

            discoverer = PostDiscoverer(
                client,
                self._settings.comment_history_path,
                own_username=self._settings.reddit_username,
            )
            generator = CommentGenerator(
                model=self._settings.gemini_model,
                mention_rate=self._settings.mention_rate,
                top_examples_path=self._settings.top_examples_path,
                max_examples=self._settings.max_examples_in_prompt,
                epsilon=self._settings.epsilon,
            )

            targets = self._load_targets()
            subreddits = targets.get("subreddits", [])
            queries = targets.get("search_queries", [])

            random.shuffle(subreddits)
            sub_subset = subreddits[: random.randint(4, 8)]

            prog.on_discovery_start(len(sub_subset), len(queries))

            search_posts = await discoverer.discover_search_posts(
                sub_subset,
                queries,
                max_per_query=2,
            )
            hot_posts = await discoverer.discover_hot_posts(sub_subset, max_per_sub=3)

            all_posts = discoverer._dedupe(search_posts + hot_posts)
            all_posts.sort(
                key=lambda p: (p.score, p.num_comments, p.discovered_at),
                reverse=True,
            )
            candidates = all_posts[: self._settings.max_comments_per_day]
            random.shuffle(candidates)

            prog.on_discovery_end(len(all_posts), len(candidates))

            for i, post in enumerate(candidates, start=1):
                prog.on_generating(i, len(candidates), post.subreddit)

                try:
                    comment_text = await generator.generate_comment(
                        post,
                        comment_number=i,
                    )
                except Exception:
                    logger.exception(
                        "Failed to generate comment for r/%s post %s",
                        post.subreddit,
                        post.post_id,
                    )
                    prog.on_generate_failed(i, len(candidates), post.subreddit)
                    continue

                prog.on_generated(i, len(candidates), post.subreddit, comment_text)
                results.append(
                    GeneratedComment(
                        subreddit=post.subreddit,
                        post_url=post.post_url,
                        post_id=post.post_id,
                        post_fullname=post.post_fullname,
                        post_title=post.post_title,
                        post_text=post.post_text,
                        author=post.author,
                        score=post.score,
                        comment_text=comment_text,
                    )
                )

        stats = EngagementStats(
            total_discovered=len(all_posts),
            total_attempted=len(candidates),
            total_succeeded=len(results),
            total_failed=len(candidates) - len(results),
            posts_by_source={
                "search": len(search_posts),
                "hot": len(hot_posts),
            },
        )
        prog.on_complete(stats)
        return results

    async def comment_from_list(
        self,
        comments: list[GeneratedComment],
        progress: ProgressCallback | None = None,
    ) -> EngagementStats:
        """Post comments from a pre-generated list (e.g. loaded from CSV)."""
        stats = EngagementStats(total_discovered=len(comments))
        prog: ProgressCallback = progress or _NullProgress()  # type: ignore[assignment]

        client = RedditClient(
            session_cookie=self._settings.reddit_session,
            username=self._settings.reddit_username,
            user_agent=self._settings.reddit_user_agent,
        )

        async with client:
            if not await client.is_logged_in():
                logger.error("Reddit session cookie is invalid or expired.")
                return stats

            adapter = RedditAdapter(client)
            renderer = RedditRenderer()
            discoverer = PostDiscoverer(
                client,
                self._settings.comment_history_path,
                own_username=self._settings.reddit_username,
            )

            prog.on_discovery_end(len(comments), len(comments))

            for i, row in enumerate(comments, start=1):
                stats.total_attempted += 1
                prog.on_generating(i, len(comments), row.subreddit)
                prog.on_generated(i, len(comments), row.subreddit, row.comment_text)

                reply_content = Reply(
                    in_reply_to_url=row.post_url,
                    in_reply_to_platform_id=row.post_fullname,
                    body=row.comment_text,
                )
                normalised = self._normaliser.normalise(reply_content)
                rendered = await renderer.render(normalised)
                result = await adapter.publish(rendered)

                self._log_audit(
                    AuditEntry(
                        timestamp=datetime.now(UTC).isoformat(),
                        subreddit=row.subreddit,
                        post_url=row.post_url,
                        post_id=row.post_id,
                        author=row.author,
                        comment_text=row.comment_text,
                        success=result.success,
                        error=result.error_message or "",
                    )
                )

                if result.success:
                    stats.total_succeeded += 1
                    discoverer.mark_commented(row.post_id)
                    prog.on_comment_posted(
                        i,
                        len(comments),
                        row.subreddit,
                        success=True,
                    )
                else:
                    stats.total_failed += 1
                    prog.on_comment_posted(
                        i,
                        len(comments),
                        row.subreddit,
                        success=False,
                    )

                    if self._looks_like_rate_limit(result.error_message or ""):
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
                    import asyncio

                    await asyncio.sleep(delay)

        prog.on_complete(stats)
        return stats

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_targets(self) -> dict[str, list[str]]:
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
        ]
        lower = error_msg.lower()
        return any(t in lower for t in triggers)
