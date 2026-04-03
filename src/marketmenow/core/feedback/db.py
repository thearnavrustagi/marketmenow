from __future__ import annotations

import logging
import os
import ssl

import asyncpg

from marketmenow.core.feedback.models import CommentData, ContentGuideline, VideoMetrics

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

FEEDBACK_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS feedback_videos (
    video_id TEXT PRIMARY KEY,
    project_slug TEXT NOT NULL,
    reel_id TEXT,
    template_id TEXT,
    template_type_id TEXT,
    title TEXT,
    description TEXT,
    published_at TEXT,
    view_count INT DEFAULT 0,
    like_count INT DEFAULT 0,
    comment_count INT DEFAULT 0,
    avg_sentiment FLOAT DEFAULT 5.0,
    metrics_collected_at TIMESTAMPTZ,
    comments_scored_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_videos_project ON feedback_videos(project_slug);

CREATE TABLE IF NOT EXISTS feedback_comments (
    id SERIAL PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES feedback_videos(video_id) ON DELETE CASCADE,
    comment_id TEXT NOT NULL,
    author TEXT,
    text TEXT,
    like_count INT DEFAULT 0,
    published_at TEXT,
    sentiment_score FLOAT DEFAULT 5.0,
    sentiment_label TEXT DEFAULT 'neutral',
    UNIQUE(video_id, comment_id)
);

CREATE TABLE IF NOT EXISTS feedback_guidelines (
    id TEXT PRIMARY KEY,
    project_slug TEXT NOT NULL,
    source_video_id TEXT,
    source_template_id TEXT,
    guideline_type TEXT NOT NULL,
    rule TEXT NOT NULL,
    evidence TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_guidelines_project ON feedback_guidelines(project_slug);
"""


async def get_pool() -> asyncpg.Pool | None:
    """Return (and lazily create) the feedback cache connection pool.

    Returns ``None`` if ``MMN_WEB_DATABASE_URL`` is not set — callers
    should fall back to file-based storage.
    """
    global _pool
    if _pool is not None:
        return _pool

    dsn = os.environ.get("MMN_WEB_DATABASE_URL", "")
    if not dsn:
        dsn = _read_dsn_from_dotenv()
    if not dsn:
        return None

    ssl_ctx: ssl.SSLContext | str = "require"
    if "sslmode=" in dsn:
        dsn_base = dsn.split("?")[0]
        params = [p for p in dsn.split("?", 1)[1].split("&") if not p.startswith("sslmode=")]
        dsn = dsn_base + ("?" + "&".join(params) if params else "")

    try:
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3, ssl=ssl_ctx)
        return _pool
    except Exception:
        logger.warning("Failed to connect to feedback cache DB, falling back to files")
        return None


async def ensure_schema() -> bool:
    """Create feedback tables if they don't exist. Returns True on success."""
    pool = await get_pool()
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            await conn.execute(FEEDBACK_SCHEMA_SQL)
        return True
    except Exception:
        logger.warning("Failed to create feedback schema")
        return False


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── Video cache ───────────────────────────────────────────────────────


async def get_scored_video_ids(project_slug: str) -> set[str]:
    """Return video_ids that already have comments scored."""
    pool = await get_pool()
    if pool is None:
        return set()
    rows = await pool.fetch(
        "SELECT video_id FROM feedback_videos WHERE project_slug = $1 AND comments_scored_at IS NOT NULL",
        project_slug,
    )
    return {r["video_id"] for r in rows}


async def upsert_video(
    video_id: str,
    project_slug: str,
    *,
    reel_id: str = "",
    template_id: str = "",
    template_type_id: str = "",
    title: str = "",
    description: str = "",
    published_at: str = "",
    metrics: VideoMetrics | None = None,
    avg_sentiment: float = 5.0,
    comments_scored: bool = False,
) -> None:
    pool = await get_pool()
    if pool is None:
        return

    from datetime import UTC, datetime

    scored_at = datetime.now(UTC) if comments_scored else None

    await pool.execute(
        """
        INSERT INTO feedback_videos (
            video_id, project_slug, reel_id, template_id, template_type_id,
            title, description, published_at,
            view_count, like_count, comment_count,
            avg_sentiment, metrics_collected_at,
            comments_scored_at, updated_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,now(),$13,now())
        ON CONFLICT (video_id) DO UPDATE SET
            view_count = EXCLUDED.view_count,
            like_count = EXCLUDED.like_count,
            comment_count = EXCLUDED.comment_count,
            avg_sentiment = CASE WHEN EXCLUDED.comments_scored_at IS NOT NULL
                THEN EXCLUDED.avg_sentiment ELSE feedback_videos.avg_sentiment END,
            metrics_collected_at = now(),
            comments_scored_at = COALESCE(EXCLUDED.comments_scored_at, feedback_videos.comments_scored_at),
            updated_at = now()
        """,
        video_id,
        project_slug,
        reel_id,
        template_id,
        template_type_id,
        title,
        description,
        published_at,
        metrics.view_count if metrics else 0,
        metrics.like_count if metrics else 0,
        metrics.comment_count if metrics else 0,
        avg_sentiment,
        scored_at,
    )


# ── Comments cache ────────────────────────────────────────────────────


async def get_cached_comments(video_id: str) -> list[CommentData]:
    pool = await get_pool()
    if pool is None:
        return []
    rows = await pool.fetch(
        "SELECT * FROM feedback_comments WHERE video_id = $1",
        video_id,
    )
    return [
        CommentData(
            comment_id=r["comment_id"],
            author=r["author"] or "",
            text=r["text"] or "",
            like_count=r["like_count"] or 0,
            published_at=r["published_at"] or "",
            sentiment_score=r["sentiment_score"] or 5.0,
            sentiment_label=r["sentiment_label"] or "neutral",
        )
        for r in rows
    ]


async def upsert_comments(video_id: str, comments: list[CommentData]) -> None:
    pool = await get_pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        for c in comments:
            await conn.execute(
                """
                INSERT INTO feedback_comments
                    (video_id, comment_id, author, text, like_count, published_at, sentiment_score, sentiment_label)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (video_id, comment_id) DO UPDATE SET
                    sentiment_score = EXCLUDED.sentiment_score,
                    sentiment_label = EXCLUDED.sentiment_label
                """,
                video_id,
                c.comment_id,
                c.author,
                c.text,
                c.like_count,
                c.published_at,
                c.sentiment_score,
                c.sentiment_label,
            )


# ── Guidelines cache ──────────────────────────────────────────────────


async def get_guidelines(project_slug: str) -> list[ContentGuideline]:
    pool = await get_pool()
    if pool is None:
        return []
    rows = await pool.fetch(
        "SELECT * FROM feedback_guidelines WHERE project_slug = $1 ORDER BY created_at",
        project_slug,
    )
    return [
        ContentGuideline(
            id=r["id"],
            created_at=str(r["created_at"]),
            source_video_id=r["source_video_id"] or "",
            source_template_id=r["source_template_id"] or "",
            guideline_type=r["guideline_type"],
            rule=r["rule"],
            evidence=r["evidence"] or "",
        )
        for r in rows
    ]


async def upsert_guidelines(
    project_slug: str, guidelines: list[ContentGuideline]
) -> None:
    pool = await get_pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        for g in guidelines:
            await conn.execute(
                """
                INSERT INTO feedback_guidelines
                    (id, project_slug, source_video_id, source_template_id, guideline_type, rule, evidence)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (id) DO NOTHING
                """,
                g.id,
                project_slug,
                g.source_video_id,
                g.source_template_id,
                g.guideline_type,
                g.rule,
                g.evidence,
            )


def _read_dsn_from_dotenv() -> str:
    """Read MMN_WEB_DATABASE_URL from .env file (CLI doesn't auto-load dotenv)."""
    from pathlib import Path

    for candidate in (Path.cwd() / ".env", Path.cwd().parent / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MMN_WEB_DATABASE_URL=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip("'\"")
    return ""
