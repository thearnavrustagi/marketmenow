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

from .adapter import TwitterAdapter
from .browser import StealthBrowser
from .discovery import DiscoveredPost, PostDiscoverer
from .performance_tracker import (
    PerformanceTracker,
    cache_is_fresh,
    load_examples_cache,
)
from .renderer import TwitterRenderer
from .reply_generator import ReplyGenerator
from .settings import TwitterSettings
from .thread_generator import GeneratedThread, ThreadGenerator


def _ensure_vertex_credentials(settings: TwitterSettings) -> None:
    """Export GOOGLE_APPLICATION_CREDENTIALS so the genai SDK picks it up."""
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
    post_url: str
    author_handle: str
    reply_text: str
    success: bool
    error: str = ""
    icl_mode: str = ""
    epsilon: float = 0.0
    num_examples: int = 0


class EngagementStats(BaseModel):
    total_discovered: int = 0
    total_attempted: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    posts_by_source: dict[str, int] = Field(default_factory=dict)


class GeneratedReply(BaseModel, frozen=True):
    """A single discover+generate result, ready to be reviewed or posted."""

    post_url: str
    author_handle: str
    post_text: str
    engagement_score: int = 0
    reply_text: str


@runtime_checkable
class ProgressCallback(Protocol):
    """UI-agnostic progress reporting for the engagement loop."""

    def on_discovery_start(self, total_handles: int, total_hashtags: int) -> None: ...
    def on_handle_done(self, handle: str, posts_found: int) -> None: ...
    def on_hashtag_done(self, hashtag: str, posts_found: int) -> None: ...
    def on_discovery_end(self, total_posts: int, candidates: int) -> None: ...
    def on_generating(self, current: int, total: int, handle: str) -> None: ...
    def on_generated(self, current: int, total: int, handle: str, reply_text: str) -> None: ...
    def on_generate_failed(self, current: int, total: int, handle: str) -> None: ...
    def on_reply_posted(self, current: int, total: int, handle: str, success: bool) -> None: ...
    def on_reply_wait(self, seconds: int) -> None: ...
    def on_complete(self, stats: EngagementStats) -> None: ...


class _NullProgress:
    """No-op fallback when no progress callback is provided."""

    def on_discovery_start(self, total_handles: int, total_hashtags: int) -> None:
        pass

    def on_handle_done(self, handle: str, posts_found: int) -> None:
        pass

    def on_hashtag_done(self, hashtag: str, posts_found: int) -> None:
        pass

    def on_discovery_end(self, total_posts: int, candidates: int) -> None:
        pass

    def on_generating(self, current: int, total: int, handle: str) -> None:
        pass

    def on_generated(self, current: int, total: int, handle: str, reply_text: str) -> None:
        pass

    def on_generate_failed(self, current: int, total: int, handle: str) -> None:
        pass

    def on_reply_posted(self, current: int, total: int, handle: str, success: bool) -> None:
        pass

    def on_reply_wait(self, seconds: int) -> None:
        pass

    def on_complete(self, stats: EngagementStats) -> None:
        pass


class EngagementOrchestrator:
    """Runs the full discover-generate-reply engagement loop."""

    def __init__(
        self,
        settings: TwitterSettings,
        persona: object | None = None,
        brand: object | None = None,
        project_slug: str | None = None,
    ) -> None:
        self._settings = settings
        self._normaliser = ContentNormaliser()
        self._persona = persona
        self._brand = brand
        self._project_slug = project_slug

    async def run(
        self,
        dry_run: bool = False,
        approval_callback: ApprovalCallback | None = None,
        progress: ProgressCallback | None = None,
    ) -> EngagementStats:
        _ensure_vertex_credentials(self._settings)

        stats = EngagementStats()
        prog: ProgressCallback = progress or _NullProgress()

        browser = StealthBrowser(
            session_path=self._settings.twitter_session_path,
            user_data_dir=self._settings.twitter_user_data_dir,
            headless=self._settings.headless,
            slow_mo_ms=self._settings.slow_mo_ms,
            proxy_url=self._settings.proxy_url,
            viewport_width=self._settings.viewport_width,
            viewport_height=self._settings.viewport_height,
        )

        async with browser:
            if not await browser.is_logged_in():
                logger.error("Not logged in. Run `mmn-x login` first to create a session.")
                return stats

            await self._maybe_collect_examples(browser)

            adapter = TwitterAdapter(browser)
            renderer = TwitterRenderer()
            discoverer = PostDiscoverer(
                browser,
                self._settings.reply_history_path,
            )
            generator = ReplyGenerator(
                model=self._settings.gemini_model,
                top_examples_path=self._settings.top_examples_path,
                max_examples=self._settings.max_examples_in_prompt,
                epsilon=self._settings.epsilon,
                persona=self._persona,
                brand=self._brand,
                project_slug=self._project_slug,
            )

            targets = self._load_targets()
            influencers = targets.get("influencers", [])
            hashtags = targets.get("hashtags", [])
            companies = targets.get("company_accounts", [])

            all_handles = influencers + companies
            random.shuffle(all_handles)
            random.shuffle(hashtags)

            handle_subset = all_handles[: random.randint(8, 15)]
            hashtag_subset = hashtags[: random.randint(5, 10)]

            prog.on_discovery_start(len(handle_subset), len(hashtag_subset))

            influencer_posts = await self._discover_handles(
                discoverer,
                handle_subset,
                prog,
            )
            hashtag_posts = await self._discover_hashtags(
                discoverer,
                hashtag_subset,
                prog,
            )

            all_posts = influencer_posts + hashtag_posts
            stats.total_discovered = len(all_posts)
            stats.posts_by_source = {
                "influencers": len(influencer_posts),
                "hashtags": len(hashtag_posts),
            }

            all_posts.sort(
                key=lambda p: (p.engagement_score, p.discovered_at),
                reverse=True,
            )

            candidates = all_posts[: self._settings.max_replies_per_day]
            random.shuffle(candidates)

            prog.on_discovery_end(len(all_posts), len(candidates))

            for i, post in enumerate(candidates, start=1):
                stats.total_attempted += 1
                prog.on_generating(i, len(candidates), post.author_handle)

                try:
                    reply_text, _exploring = await generator.generate_reply(post, reply_number=i)
                except Exception:
                    logger.exception("Failed to generate reply for %s", post.post_url)
                    stats.total_failed += 1
                    prog.on_generate_failed(i, len(candidates), post.author_handle)
                    continue

                prog.on_generated(i, len(candidates), post.author_handle, reply_text)

                if approval_callback is not None:
                    approval = await approval_callback(
                        post,
                        reply_text,
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
                        reply_text = approval.edited_text

                if dry_run:
                    self._log_audit(
                        AuditEntry(
                            timestamp=datetime.now(UTC).isoformat(),
                            post_url=post.post_url,
                            author_handle=post.author_handle,
                            reply_text=reply_text,
                            success=True,
                            error="dry_run",
                        )
                    )
                    stats.total_succeeded += 1
                    prog.on_reply_posted(i, len(candidates), post.author_handle, success=True)
                    continue

                reply_content = Reply(
                    in_reply_to_url=post.post_url,
                    body=reply_text,
                )
                normalised = self._normaliser.normalise(reply_content)
                rendered = await renderer.render(normalised)
                result = await adapter.publish(rendered)

                entry = AuditEntry(
                    timestamp=datetime.now(UTC).isoformat(),
                    post_url=post.post_url,
                    author_handle=post.author_handle,
                    reply_text=reply_text,
                    success=result.success,
                    error=result.error_message or "",
                )
                self._log_audit(entry)

                if result.success:
                    stats.total_succeeded += 1
                    discoverer.mark_replied(post.post_url)
                    prog.on_reply_posted(i, len(candidates), post.author_handle, success=True)
                else:
                    stats.total_failed += 1
                    prog.on_reply_posted(i, len(candidates), post.author_handle, success=False)

                    if self._looks_like_captcha(result.error_message or ""):
                        logger.error(
                            "CAPTCHA or unusual activity detected -- halting for %d hours",
                            self._settings.cooldown_hours,
                        )
                        break

                if i < len(candidates):
                    delay = random.randint(
                        self._settings.min_delay_seconds,
                        self._settings.max_delay_seconds,
                    )
                    prog.on_reply_wait(delay)
                    await browser._random_delay(delay, delay + 30)

        prog.on_complete(stats)
        return stats

    async def generate_only(
        self,
        progress: ProgressCallback | None = None,
    ) -> list[GeneratedReply]:
        """Discover posts and generate replies without posting. Returns the list."""
        _ensure_vertex_credentials(self._settings)
        prog: ProgressCallback = progress or _NullProgress()

        browser = StealthBrowser(
            session_path=self._settings.twitter_session_path,
            user_data_dir=self._settings.twitter_user_data_dir,
            headless=self._settings.headless,
            slow_mo_ms=self._settings.slow_mo_ms,
            proxy_url=self._settings.proxy_url,
            viewport_width=self._settings.viewport_width,
            viewport_height=self._settings.viewport_height,
        )

        results: list[GeneratedReply] = []

        async with browser:
            if not await browser.is_logged_in():
                logger.error("Not logged in. Run `mmn twitter login` first.")
                return results

            await self._maybe_collect_examples(browser)

            discoverer = PostDiscoverer(
                browser,
                self._settings.reply_history_path,
            )
            generator = ReplyGenerator(
                model=self._settings.gemini_model,
                top_examples_path=self._settings.top_examples_path,
                max_examples=self._settings.max_examples_in_prompt,
                epsilon=self._settings.epsilon,
                persona=self._persona,
                brand=self._brand,
                project_slug=self._project_slug,
            )

            targets = self._load_targets()
            influencers = targets.get("influencers", [])
            hashtags = targets.get("hashtags", [])
            companies = targets.get("company_accounts", [])

            all_handles = influencers + companies
            random.shuffle(all_handles)
            random.shuffle(hashtags)

            handle_subset = all_handles[: random.randint(8, 15)]
            hashtag_subset = hashtags[: random.randint(5, 10)]

            prog.on_discovery_start(len(handle_subset), len(hashtag_subset))

            influencer_posts = await self._discover_handles(
                discoverer,
                handle_subset,
                prog,
            )
            hashtag_posts = await self._discover_hashtags(
                discoverer,
                hashtag_subset,
                prog,
            )

            all_posts = influencer_posts + hashtag_posts
            all_posts.sort(
                key=lambda p: (p.engagement_score, p.discovered_at),
                reverse=True,
            )
            candidates = all_posts[: self._settings.max_replies_per_day]
            random.shuffle(candidates)

            prog.on_discovery_end(len(all_posts), len(candidates))

            for i, post in enumerate(candidates, start=1):
                prog.on_generating(i, len(candidates), post.author_handle)

                try:
                    reply_text, _exploring = await generator.generate_reply(post, reply_number=i)
                except Exception:
                    logger.exception("Failed to generate reply for %s", post.post_url)
                    prog.on_generate_failed(i, len(candidates), post.author_handle)
                    continue

                prog.on_generated(i, len(candidates), post.author_handle, reply_text)
                results.append(
                    GeneratedReply(
                        post_url=post.post_url,
                        author_handle=post.author_handle,
                        post_text=post.post_text,
                        engagement_score=post.engagement_score,
                        reply_text=reply_text,
                    )
                )

        stats = EngagementStats(
            total_discovered=len(all_posts),
            total_attempted=len(candidates),
            total_succeeded=len(results),
            total_failed=len(candidates) - len(results),
            posts_by_source={
                "influencers": len(influencer_posts),
                "hashtags": len(hashtag_posts),
            },
        )
        prog.on_complete(stats)
        return results

    async def reply_from_list(
        self,
        replies: list[GeneratedReply],
        progress: ProgressCallback | None = None,
    ) -> EngagementStats:
        """Post replies from a pre-generated list (e.g. loaded from CSV)."""
        stats = EngagementStats(total_discovered=len(replies))
        prog: ProgressCallback = progress or _NullProgress()

        browser = StealthBrowser(
            session_path=self._settings.twitter_session_path,
            user_data_dir=self._settings.twitter_user_data_dir,
            headless=self._settings.headless,
            slow_mo_ms=self._settings.slow_mo_ms,
            proxy_url=self._settings.proxy_url,
            viewport_width=self._settings.viewport_width,
            viewport_height=self._settings.viewport_height,
        )

        async with browser:
            if not await browser.is_logged_in():
                logger.error("Not logged in. Run `mmn twitter login` first.")
                return stats

            adapter = TwitterAdapter(browser)
            renderer = TwitterRenderer()
            discoverer = PostDiscoverer(
                browser,
                self._settings.reply_history_path,
            )

            prog.on_discovery_end(len(replies), len(replies))

            for i, row in enumerate(replies, start=1):
                stats.total_attempted += 1
                prog.on_generating(i, len(replies), row.author_handle)
                prog.on_generated(i, len(replies), row.author_handle, row.reply_text)

                reply_content = Reply(
                    in_reply_to_url=row.post_url,
                    body=row.reply_text,
                )
                normalised = self._normaliser.normalise(reply_content)
                rendered = await renderer.render(normalised)
                result = await adapter.publish(rendered)

                self._log_audit(
                    AuditEntry(
                        timestamp=datetime.now(UTC).isoformat(),
                        post_url=row.post_url,
                        author_handle=row.author_handle,
                        reply_text=row.reply_text,
                        success=result.success,
                        error=result.error_message or "",
                    )
                )

                if result.success:
                    stats.total_succeeded += 1
                    discoverer.mark_replied(row.post_url)
                    prog.on_reply_posted(i, len(replies), row.author_handle, success=True)
                else:
                    stats.total_failed += 1
                    prog.on_reply_posted(i, len(replies), row.author_handle, success=False)

                    if self._looks_like_captcha(result.error_message or ""):
                        logger.error(
                            "CAPTCHA or unusual activity detected -- halting for %d hours",
                            self._settings.cooldown_hours,
                        )
                        break

                if i < len(replies):
                    delay = random.randint(
                        self._settings.min_delay_seconds,
                        self._settings.max_delay_seconds,
                    )
                    prog.on_reply_wait(delay)
                    await browser._random_delay(delay, delay + 30)

        prog.on_complete(stats)
        return stats

    # ------------------------------------------------------------------
    # Thread generation + posting
    # ------------------------------------------------------------------

    async def generate_and_post_thread(self) -> GeneratedThread | None:
        """Generate a Top-5 thread via Gemini and post it to X.

        Returns the generated thread on success, or None on failure.
        """
        _ensure_vertex_credentials(self._settings)

        browser = StealthBrowser(
            session_path=self._settings.twitter_session_path,
            user_data_dir=self._settings.twitter_user_data_dir,
            headless=self._settings.headless,
            slow_mo_ms=self._settings.slow_mo_ms,
            proxy_url=self._settings.proxy_url,
            viewport_width=self._settings.viewport_width,
            viewport_height=self._settings.viewport_height,
        )

        async with browser:
            if not await browser.is_logged_in():
                logger.error("Not logged in. Run `mmn twitter login` first.")
                return None

            await self._maybe_collect_examples(browser)

            generator = ThreadGenerator(
                model=self._settings.gemini_model,
                top_examples_path=self._settings.top_examples_path,
                max_examples=self._settings.max_examples_in_prompt,
                persona=self._persona,
                brand=self._brand,
                project_slug=self._project_slug,
            )

            try:
                thread = await generator.generate_thread()
            except Exception:
                logger.exception("Failed to generate thread")
                return None

            tweet_texts = [t.text for t in thread.tweets]

            try:
                success = await browser.post_thread(tweet_texts)
            except Exception:
                logger.exception("Failed to post thread")
                return None

            if not success:
                logger.error("post_thread returned False")
                return None

            logger.info("Thread posted: %s (%d tweets)", thread.topic, len(thread.tweets))
            return thread

    async def _discover_handles(
        self,
        discoverer: PostDiscoverer,
        handles: list[str],
        prog: ProgressCallback,
    ) -> list[DiscoveredPost]:
        posts: list[DiscoveredPost] = []
        for handle in handles:
            handle_clean = handle.lstrip("@")
            profile_url = f"https://x.com/{handle_clean}"
            try:
                found = await discoverer._scrape_profile(profile_url, handle_clean, 2)
                posts.extend(found)
                prog.on_handle_done(handle_clean, len(found))
            except Exception:
                logger.exception("Failed to scrape profile %s", handle_clean)
                prog.on_handle_done(handle_clean, 0)
            await discoverer._browser._random_delay(2.0, 5.0)
        return posts

    async def _discover_hashtags(
        self,
        discoverer: PostDiscoverer,
        hashtags: list[str],
        prog: ProgressCallback,
    ) -> list[DiscoveredPost]:
        posts: list[DiscoveredPost] = []
        for tag in hashtags:
            tag_clean = tag.lstrip("#")
            search_url = f"https://x.com/search?q=%23{tag_clean}&src=typed_query&f=live"
            try:
                found = await discoverer._scrape_search(search_url, tag_clean, 2)
                posts.extend(found)
                prog.on_hashtag_done(tag_clean, len(found))
            except Exception:
                logger.exception("Failed to scrape hashtag #%s", tag_clean)
                prog.on_hashtag_done(tag_clean, 0)
            await discoverer._browser._random_delay(2.0, 5.0)
        return posts

    # ------------------------------------------------------------------
    # Discovery-only (no posting)
    # ------------------------------------------------------------------

    async def discover_only(self) -> list[DiscoveredPost]:
        browser = StealthBrowser(
            session_path=self._settings.twitter_session_path,
            user_data_dir=self._settings.twitter_user_data_dir,
            headless=self._settings.headless,
            slow_mo_ms=self._settings.slow_mo_ms,
            proxy_url=self._settings.proxy_url,
        )

        async with browser:
            if not await browser.is_logged_in():
                logger.error("Not logged in.")
                return []

            discoverer = PostDiscoverer(browser, self._settings.reply_history_path)
            targets = self._load_targets()

            handles = targets.get("influencers", []) + targets.get("company_accounts", [])
            random.shuffle(handles)
            hashtags = list(targets.get("hashtags", []))
            random.shuffle(hashtags)

            posts = await discoverer.discover_influencer_posts(
                handles[:10],
                max_per_handle=2,
            )
            posts += await discoverer.discover_hashtag_posts(
                hashtags[:5],
                max_per_tag=2,
            )
            return posts

    # ------------------------------------------------------------------
    # In-context learning: collect top-performing examples
    # ------------------------------------------------------------------

    async def _maybe_collect_examples(self, browser: StealthBrowser) -> None:
        """Refresh the top-examples cache if stale or missing."""
        username = self._settings.twitter_username
        if not username:
            logger.debug("twitter_username not set, skipping example collection")
            return

        cache = load_examples_cache(self._settings.top_examples_path)
        if cache_is_fresh(cache, self._settings.examples_max_age_hours):
            logger.info(
                "Examples cache is fresh (%d replies, %d posts), skipping collection",
                len(cache.replies),
                len(cache.posts),
            )
            return

        logger.info("Examples cache is stale or missing, collecting from @%s", username)
        tracker = PerformanceTracker(
            browser,
            username,
            self._settings.top_examples_path,
        )
        try:
            await tracker.collect()
        except Exception:
            logger.exception("Failed to collect top-performing examples, continuing anyway")

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
    def _looks_like_captcha(error_msg: str) -> bool:
        triggers = ["captcha", "unusual activity", "suspicious", "verify", "challenge"]
        lower = error_msg.lower()
        return any(t in lower for t in triggers)
