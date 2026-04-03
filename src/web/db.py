from __future__ import annotations

import asyncio
import json
import logging
import ssl
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from web.config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS content_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL,
    modality TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    generate_command JSONB NOT NULL,
    publish_command JSONB,
    status TEXT NOT NULL DEFAULT 'generating',
    preview_data JSONB,
    output_path TEXT,
    error_message TEXT,
    progress_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE content_items ADD COLUMN IF NOT EXISTS progress_data JSONB;

ALTER TABLE content_items ADD COLUMN IF NOT EXISTS project_slug TEXT;
CREATE INDEX IF NOT EXISTS idx_content_items_project ON content_items(project_slug);

CREATE TABLE IF NOT EXISTS platform_queues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_item_id UUID NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    priority INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'waiting',
    posted_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rate_limits (
    platform TEXT PRIMARY KEY,
    max_per_hour INT NOT NULL DEFAULT 2,
    max_per_day INT NOT NULL DEFAULT 10,
    min_interval_seconds INT NOT NULL DEFAULT 300
);

CREATE TABLE IF NOT EXISTS post_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL,
    content_item_id UUID REFERENCES content_items(id) ON DELETE SET NULL,
    posted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    remote_url TEXT,
    success BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_content_items_status ON content_items(status);
CREATE INDEX IF NOT EXISTS idx_content_items_platform ON content_items(platform);
CREATE INDEX IF NOT EXISTS idx_platform_queues_status ON platform_queues(status, platform);
CREATE INDEX IF NOT EXISTS idx_post_log_platform_time ON post_log(platform, posted_at DESC);

INSERT INTO rate_limits (platform, max_per_hour, max_per_day, min_interval_seconds)
VALUES
    ('instagram', 2, 10, 600),
    ('twitter', 3, 15, 300),
    ('linkedin', 2, 8, 900),
    ('reddit', 2, 10, 600),
    ('facebook', 2, 8, 600),
    ('email', 10, 50, 60)
ON CONFLICT (platform) DO NOTHING;

-- Feedback cache tables (shared with CLI feedback system)
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


async def init_pool(*, retries: int = 5, delay: float = 2.0) -> asyncpg.Pool:
    global _pool
    dsn = settings.database_url

    ssl_ctx: ssl.SSLContext | str = "require"
    if "sslmode=" in dsn:
        dsn_base = dsn.split("?")[0]
        params = [p for p in dsn.split("?", 1)[1].split("&") if not p.startswith("sslmode=")]
        dsn = dsn_base + ("?" + "&".join(params) if params else "")

    for attempt in range(1, retries + 1):
        try:
            _pool = await asyncpg.create_pool(
                dsn,
                min_size=2,
                max_size=10,
                init=_set_json_codec,
                ssl=ssl_ctx,
            )
            async with _pool.acquire() as conn:
                await conn.execute(SCHEMA_SQL)
            return _pool
        except (ConnectionResetError, OSError, asyncpg.PostgresError) as exc:
            if attempt == retries:
                raise
            logger.warning(
                "DB connection attempt %d/%d failed: %s — retrying in %.1fs",
                attempt,
                retries,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            delay *= 2
    raise RuntimeError("Failed to connect to database")


async def _set_json_codec(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    assert _pool is not None, "DB pool not initialised — call init_pool() first"
    return _pool


# ── Helpers ──────────────────────────────────────────────────────────


async def insert_content_item(
    *,
    platform: str,
    modality: str,
    title: str,
    generate_command: list[str],
    publish_command: list[str] | None = None,
    project_slug: str | None = None,
) -> UUID:
    row = await pool().fetchrow(
        """
        INSERT INTO content_items (platform, modality, title, generate_command, publish_command, project_slug)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, project_slug
        """,
        platform,
        modality,
        title,
        generate_command,
        publish_command,
        project_slug,
    )
    return row["id"]


async def update_content_status(
    item_id: UUID,
    status: str,
    *,
    preview_data: dict[str, Any] | None = None,
    output_path: str | None = None,
    error_message: str | None = None,
    publish_command: list[str] | None = None,
) -> None:
    sets = ["status = $2", "updated_at = now()"]
    params: list[Any] = [item_id, status]
    idx = 3
    if preview_data is not None:
        sets.append(f"preview_data = ${idx}")
        params.append(preview_data)
        idx += 1
    if output_path is not None:
        sets.append(f"output_path = ${idx}")
        params.append(output_path)
        idx += 1
    if error_message is not None:
        sets.append(f"error_message = ${idx}")
        params.append(error_message)
        idx += 1
    if publish_command is not None:
        sets.append(f"publish_command = ${idx}")
        params.append(publish_command)
        idx += 1
    await pool().execute(
        f"UPDATE content_items SET {', '.join(sets)} WHERE id = $1",
        *params,
    )


async def update_progress_data(item_id: UUID, progress_data: dict[str, Any]) -> None:
    await pool().execute(
        "UPDATE content_items SET progress_data = $2, updated_at = now() WHERE id = $1",
        item_id,
        progress_data,
    )


async def get_content_item(item_id: UUID) -> asyncpg.Record | None:
    return await pool().fetchrow("SELECT * FROM content_items WHERE id = $1", item_id)


async def list_content_items(
    status: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    project_slug: str | None = None,
) -> list[asyncpg.Record]:
    clauses: list[str] = []
    params: list[Any] = []
    idx = 1
    if status:
        clauses.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if platform:
        clauses.append(f"platform = ${idx}")
        params.append(platform)
        idx += 1
    if project_slug:
        clauses.append(f"project_slug = ${idx}")
        params.append(project_slug)
        idx += 1
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    return await pool().fetch(
        f"SELECT * FROM content_items {where} ORDER BY created_at DESC LIMIT ${idx}",
        *params,
    )


async def enqueue_content(content_item_id: UUID, platform: str, priority: int = 0) -> UUID:
    row = await pool().fetchrow(
        """
        INSERT INTO platform_queues (content_item_id, platform, priority)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        content_item_id,
        platform,
        priority,
    )
    return row["id"]


async def get_next_queue_job(platform: str) -> asyncpg.Record | None:
    return await pool().fetchrow(
        """
        SELECT pq.*, ci.publish_command, ci.output_path, ci.preview_data
        FROM platform_queues pq
        JOIN content_items ci ON ci.id = pq.content_item_id
        WHERE pq.platform = $1 AND pq.status = 'waiting'
        ORDER BY pq.priority DESC, pq.created_at ASC
        LIMIT 1
        """,
        platform,
    )


async def update_queue_status(
    queue_id: UUID, status: str, *, error_message: str | None = None
) -> None:
    if status == "posted":
        await pool().execute(
            "UPDATE platform_queues SET status = $2, posted_at = now() WHERE id = $1",
            queue_id,
            status,
        )
    elif error_message:
        await pool().execute(
            "UPDATE platform_queues SET status = $2, error_message = $3 WHERE id = $1",
            queue_id,
            status,
            error_message,
        )
    else:
        await pool().execute(
            "UPDATE platform_queues SET status = $2 WHERE id = $1",
            queue_id,
            status,
        )


async def cancel_queue_job_for_content(content_item_id: UUID) -> None:
    """Remove any waiting queue jobs for the given content item."""
    await pool().execute(
        "DELETE FROM platform_queues WHERE content_item_id = $1 AND status = 'waiting'",
        content_item_id,
    )


async def log_post(
    platform: str,
    content_item_id: UUID,
    *,
    success: bool = True,
    remote_url: str | None = None,
) -> None:
    await pool().execute(
        """
        INSERT INTO post_log (platform, content_item_id, success, remote_url)
        VALUES ($1, $2, $3, $4)
        """,
        platform,
        content_item_id,
        success,
        remote_url,
    )


async def get_rate_limits() -> list[asyncpg.Record]:
    return await pool().fetch("SELECT * FROM rate_limits ORDER BY platform")


async def update_rate_limit(
    platform: str, max_per_hour: int, max_per_day: int, min_interval_seconds: int
) -> None:
    await pool().execute(
        """
        INSERT INTO rate_limits (platform, max_per_hour, max_per_day, min_interval_seconds)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (platform) DO UPDATE SET
            max_per_hour = EXCLUDED.max_per_hour,
            max_per_day = EXCLUDED.max_per_day,
            min_interval_seconds = EXCLUDED.min_interval_seconds
        """,
        platform,
        max_per_hour,
        max_per_day,
        min_interval_seconds,
    )


async def count_recent_posts(platform: str, *, within_seconds: int) -> int:
    row = await pool().fetchrow(
        """
        SELECT count(*) AS cnt FROM post_log
        WHERE platform = $1 AND success = true
          AND posted_at > now() - make_interval(secs => $2::double precision)
        """,
        platform,
        float(within_seconds),
    )
    return row["cnt"]


async def last_post_time(platform: str) -> datetime | None:
    row = await pool().fetchrow(
        """
        SELECT max(posted_at) AS last_at FROM post_log
        WHERE platform = $1 AND success = true
        """,
        platform,
    )
    return row["last_at"] if row else None


async def get_platform_activity_stats() -> list[asyncpg.Record]:
    """Per-platform activity summary: posts today, last post, rate limits."""
    return await pool().fetch("""
        SELECT
            rl.platform,
            rl.max_per_hour,
            rl.max_per_day,
            rl.min_interval_seconds,
            coalesce(today.cnt, 0)  AS posts_today,
            coalesce(hour.cnt, 0)   AS posts_this_hour,
            latest.last_at
        FROM rate_limits rl
        LEFT JOIN LATERAL (
            SELECT count(*) AS cnt FROM post_log
            WHERE platform = rl.platform AND success = true
              AND posted_at > date_trunc('day', now())
        ) today ON true
        LEFT JOIN LATERAL (
            SELECT count(*) AS cnt FROM post_log
            WHERE platform = rl.platform AND success = true
              AND posted_at > now() - interval '1 hour'
        ) hour ON true
        LEFT JOIN LATERAL (
            SELECT max(posted_at) AS last_at FROM post_log
            WHERE platform = rl.platform AND success = true
        ) latest ON true
        ORDER BY rl.platform
        """)


async def list_queue_items(platform: str | None = None) -> list[asyncpg.Record]:
    if platform:
        return await pool().fetch(
            """
            SELECT pq.*, ci.title, ci.modality, ci.platform AS ci_platform
            FROM platform_queues pq
            JOIN content_items ci ON ci.id = pq.content_item_id
            WHERE pq.platform = $1
            ORDER BY pq.status ASC, pq.priority DESC, pq.created_at ASC
            """,
            platform,
        )
    return await pool().fetch("""
        SELECT pq.*, ci.title, ci.modality, ci.platform AS ci_platform
        FROM platform_queues pq
        JOIN content_items ci ON ci.id = pq.content_item_id
        ORDER BY pq.platform, pq.status ASC, pq.priority DESC, pq.created_at ASC
        """)


async def get_post_log(limit: int = 50) -> list[asyncpg.Record]:
    return await pool().fetch(
        """
        SELECT pl.*, ci.title, ci.platform AS ci_platform, ci.modality
        FROM post_log pl
        LEFT JOIN content_items ci ON ci.id = pl.content_item_id
        ORDER BY pl.posted_at DESC
        LIMIT $1
        """,
        limit,
    )


async def clear_all_content() -> int:
    """Delete all content items (cascades to platform_queues). Returns count deleted."""
    row = await pool().fetchrow("SELECT count(*) AS cnt FROM content_items")
    count = row["cnt"]
    await pool().execute("DELETE FROM content_items")
    return count


async def list_history_items(platform: str | None = None, limit: int = 100) -> list[asyncpg.Record]:
    """Return completed content items (posted or failed) ordered by most recent."""
    clauses = ["status IN ('posted', 'failed')"]
    params: list[Any] = []
    idx = 1
    if platform:
        clauses.append(f"platform = ${idx}")
        params.append(platform)
        idx += 1
    where = "WHERE " + " AND ".join(clauses)
    params.append(limit)
    return await pool().fetch(
        f"SELECT * FROM content_items {where} ORDER BY updated_at DESC LIMIT ${idx}",
        *params,
    )
