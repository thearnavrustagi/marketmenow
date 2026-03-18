from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://www.reddit.com"
_OAUTH_BASE = "https://oauth.reddit.com"


@dataclass
class RedditClient:
    """Async HTTP client for Reddit's JSON API using a ``reddit_session`` cookie."""

    session_cookie: str
    username: str = ""
    user_agent: str = "marketmenow:v0.1"
    _http: httpx.AsyncClient = field(init=False, repr=False)
    _modhash: str = field(init=False, default="", repr=False)

    def __post_init__(self) -> None:
        self._http = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            cookies={"reddit_session": self.session_cookie},
            follow_redirects=True,
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> RedditClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Auth verification
    # ------------------------------------------------------------------

    async def get_me(self) -> dict[str, object]:
        """Verify the session cookie is valid and return user info."""
        resp = await self._get(f"{_BASE}/api/me.json")
        data: dict[str, object] = resp.get("data", {})  # type: ignore[assignment]
        self._modhash = str(data.get("modhash", ""))
        return data

    async def is_logged_in(self) -> bool:
        try:
            me = await self.get_me()
            return bool(me.get("name"))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_subreddit_posts(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 25,
    ) -> list[dict[str, object]]:
        url = f"{_BASE}/r/{subreddit}/{sort}.json"
        resp = await self._get(url, params={"limit": limit, "raw_json": 1})
        return self._extract_posts(resp)

    async def search_subreddit(
        self,
        subreddit: str,
        query: str,
        sort: str = "relevance",
        time_filter: str = "week",
        limit: int = 10,
    ) -> list[dict[str, object]]:
        url = f"{_BASE}/r/{subreddit}/search.json"
        params = {
            "q": query,
            "restrict_sr": "on",
            "sort": sort,
            "t": time_filter,
            "limit": limit,
            "raw_json": 1,
        }
        resp = await self._get(url, params=params)
        return self._extract_posts(resp)

    async def get_post_detail(self, permalink: str) -> dict[str, object]:
        url = f"{_BASE}{permalink}.json"
        resp = await self._get(url, params={"raw_json": 1})
        if isinstance(resp, list) and resp:
            listing = resp[0]
            children = listing.get("data", {}).get("children", [])  # type: ignore[union-attr]
            if children:
                return children[0].get("data", {})  # type: ignore[union-attr]
        return {}

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def post_comment(self, parent_fullname: str, text: str) -> dict[str, object]:
        """Post a comment on a submission or reply to a comment.

        ``parent_fullname`` is a Reddit fullname like ``t3_abc123`` (submission)
        or ``t1_xyz789`` (comment).
        """
        if not self._modhash:
            await self.get_me()

        url = f"{_BASE}/api/comment"
        payload = {
            "thing_id": parent_fullname,
            "text": text,
            "api_type": "json",
            "uh": self._modhash,
        }
        resp = await self._post(url, data=payload)
        return resp  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _get(
        self,
        url: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, object] | list[object]:
        resp = await self._http.get(url, params=params)  # type: ignore[arg-type]
        self._check_rate_limit(resp)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def _post(
        self,
        url: str,
        data: dict[str, object] | None = None,
    ) -> dict[str, object] | list[object]:
        resp = await self._http.post(url, data=data)  # type: ignore[arg-type]
        self._check_rate_limit(resp)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def _check_rate_limit(self, resp: httpx.Response) -> None:
        remaining = resp.headers.get("x-ratelimit-remaining")
        reset = resp.headers.get("x-ratelimit-reset")
        if remaining is not None:
            logger.debug("Reddit rate-limit remaining: %s, reset in %ss", remaining, reset)
            if float(remaining) < 2:
                logger.warning(
                    "Reddit rate-limit nearly exhausted (%s left, resets in %ss)",
                    remaining,
                    reset,
                )

    @staticmethod
    def _extract_posts(resp: dict[str, object] | list[object]) -> list[dict[str, object]]:
        if isinstance(resp, list):
            resp = resp[0] if resp else {}  # type: ignore[assignment]
        data = resp.get("data", {}) if isinstance(resp, dict) else {}  # type: ignore[union-attr]
        children: list[dict[str, object]] = data.get("children", [])  # type: ignore[union-attr, assignment]
        return [c.get("data", {}) for c in children if isinstance(c, dict)]  # type: ignore[misc]
