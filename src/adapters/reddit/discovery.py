from __future__ import annotations

import json
import logging
import random
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .client import RedditClient

logger = logging.getLogger(__name__)


class DiscoveredPost(BaseModel, frozen=True):
    subreddit: str
    post_id: str
    post_fullname: str
    post_url: str
    post_title: str
    post_text: str
    author: str
    score: int = 0
    num_comments: int = 0
    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )


class PostDiscoverer:
    """Finds grading/teaching pain-point posts across target subreddits."""

    def __init__(
        self,
        client: RedditClient,
        comment_history_path: Path,
        own_username: str = "",
    ) -> None:
        self._client = client
        self._history_path = comment_history_path
        self._own_username = own_username.lower()
        self._commented_ids: set[str] = set()
        self._load_history()

    # ------------------------------------------------------------------
    # History persistence
    # ------------------------------------------------------------------

    def _load_history(self) -> None:
        if self._history_path.exists():
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            self._commented_ids = set(data.get("commented_ids", []))
            logger.info(
                "Loaded %d previously commented post IDs",
                len(self._commented_ids),
            )

    def save_history(self) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        self._history_path.write_text(
            json.dumps({"commented_ids": sorted(self._commented_ids)}, indent=2),
            encoding="utf-8",
        )

    def mark_commented(self, post_id: str) -> None:
        self._commented_ids.add(post_id)
        self.save_history()

    def already_commented(self, post_id: str) -> bool:
        return post_id in self._commented_ids

    # ------------------------------------------------------------------
    # Discovery: search
    # ------------------------------------------------------------------

    async def discover_search_posts(
        self,
        subreddits: list[str],
        queries: list[str],
        max_per_query: int = 3,
        sort: str = "relevance",
        min_score: int = 2,
    ) -> list[DiscoveredPost]:
        posts: list[DiscoveredPost] = []
        pairs = [(s, q) for s in subreddits for q in queries]
        random.shuffle(pairs)

        for sub, query in pairs:
            try:
                raw = await self._client.search_subreddit(
                    subreddit=sub,
                    query=query,
                    sort=sort,
                    time_filter="week",
                    limit=max_per_query,
                )
                for item in raw:
                    post = self._parse_post(item)
                    if post and self._is_eligible(post, min_score=min_score):
                        posts.append(post)
            except Exception:
                logger.exception("Failed to search r/%s for '%s'", sub, query)

        return self._dedupe(posts)

    # ------------------------------------------------------------------
    # Discovery: hot / new
    # ------------------------------------------------------------------

    async def discover_hot_posts(
        self,
        subreddits: list[str],
        max_per_sub: int = 5,
    ) -> list[DiscoveredPost]:
        posts: list[DiscoveredPost] = []
        shuffled = list(subreddits)
        random.shuffle(shuffled)

        for sub in shuffled:
            try:
                raw = await self._client.get_subreddit_posts(
                    subreddit=sub,
                    sort="hot",
                    limit=max_per_sub,
                )
                for item in raw:
                    post = self._parse_post(item)
                    if post and self._is_eligible(post):
                        posts.append(post)
            except Exception:
                logger.exception("Failed to fetch hot posts from r/%s", sub)

        return self._dedupe(posts)

    # ------------------------------------------------------------------
    # Discovery: new
    # ------------------------------------------------------------------

    async def discover_new_posts(
        self,
        subreddits: list[str],
        max_per_sub: int = 5,
    ) -> list[DiscoveredPost]:
        """Discover the newest posts across subreddits (sort by new)."""
        posts: list[DiscoveredPost] = []
        shuffled = list(subreddits)
        random.shuffle(shuffled)

        for sub in shuffled:
            try:
                raw = await self._client.get_subreddit_posts(
                    subreddit=sub,
                    sort="new",
                    limit=max_per_sub,
                )
                for item in raw:
                    post = self._parse_post(item)
                    if post and self._is_eligible(post, min_score=0):
                        posts.append(post)
            except Exception:
                logger.exception("Failed to fetch new posts from r/%s", sub)

        return self._dedupe(posts)

    # ------------------------------------------------------------------
    # Parsing & filtering
    # ------------------------------------------------------------------

    def _parse_post(self, data: dict[str, object]) -> DiscoveredPost | None:
        post_id = str(data.get("id", ""))
        if not post_id:
            return None

        title = str(data.get("title", ""))
        selftext = str(data.get("selftext", ""))
        if not title:
            return None

        subreddit = str(data.get("subreddit", ""))
        author = str(data.get("author", "[deleted]"))
        permalink = str(data.get("permalink", ""))
        fullname = str(data.get("name", f"t3_{post_id}"))

        return DiscoveredPost(
            subreddit=subreddit,
            post_id=post_id,
            post_fullname=fullname,
            post_url=f"https://www.reddit.com{permalink}" if permalink else "",
            post_title=title[:500],
            post_text=selftext[:2000],
            author=author,
            score=int(data.get("score", 0)),  # type: ignore[arg-type]
            num_comments=int(data.get("num_comments", 0)),  # type: ignore[arg-type]
        )

    def _is_eligible(self, post: DiscoveredPost, min_score: int = 2) -> bool:
        if self.already_commented(post.post_id):
            return False
        if post.author.lower() == self._own_username:
            return False
        if post.author in ("[deleted]", "AutoModerator"):
            return False
        if post.score < min_score:
            return False
        return True

    @staticmethod
    def _dedupe(posts: list[DiscoveredPost]) -> list[DiscoveredPost]:
        seen: set[str] = set()
        unique: list[DiscoveredPost] = []
        for p in posts:
            if p.post_id not in seen:
                seen.add(p.post_id)
                unique.append(p)
        return unique
