from __future__ import annotations

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from web import db
from web.deps import templates

router = APIRouter(prefix="/queues", tags=["queues"])


@router.get("", response_class=HTMLResponse)
async def queues_page(request: Request, platform: str | None = Query(None)) -> HTMLResponse:
    rate_limits = await db.get_rate_limits()
    queue_items = await db.list_queue_items(platform=platform)
    post_log = await db.get_post_log(limit=30)

    queue_counts: dict[str, int] = {}
    for rl in rate_limits:
        p = rl["platform"]
        queue_counts[p] = sum(
            1 for q in queue_items if q["platform"] == p and q["status"] == "waiting"
        )

    return templates.TemplateResponse(
        "queues.html",
        {
            "request": request,
            "rate_limits": rate_limits,
            "queue_items": queue_items,
            "queue_counts": queue_counts,
            "post_log": post_log,
            "current_platform": platform,
        },
    )


@router.put("/rate-limit", response_class=HTMLResponse)
async def update_rate_limit(
    request: Request,
    platform: str = Form(...),
    max_per_hour: int = Form(...),
    max_per_day: int = Form(...),
    min_interval_seconds: int = Form(...),
) -> HTMLResponse:
    await db.update_rate_limit(platform, max_per_hour, max_per_day, min_interval_seconds)
    rate_limits = await db.get_rate_limits()
    queue_items = await db.list_queue_items()

    queue_counts: dict[str, int] = {}
    for rl in rate_limits:
        p = rl["platform"]
        queue_counts[p] = sum(
            1 for q in queue_items if q["platform"] == p and q["status"] == "waiting"
        )

    return templates.TemplateResponse(
        "partials/rate_limits_table.html",
        {"request": request, "rate_limits": rate_limits, "queue_counts": queue_counts},
    )
