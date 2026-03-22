from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from web import db
from web.cli_runner import cancel_cli_process
from web.deps import templates
from web.events import ProgressEvent, hub

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    status: str | None = Query(None),
    platform: str | None = Query(None),
) -> HTMLResponse:
    items = await db.list_content_items(status=status, platform=platform)
    activity_stats = await db.get_platform_activity_stats()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "items": items,
            "current_status": status,
            "current_platform": platform,
            "activity_stats": activity_stats,
            "now_utc": datetime.now(UTC),
        },
    )


@router.delete("/clear", response_class=HTMLResponse)
async def clear_all(request: Request) -> HTMLResponse:
    await db.clear_all_content()
    return HTMLResponse(
        '<div class="col-span-full text-center py-16 text-zinc-500">'
        "<p>All content cleared.</p>"
        "</div>"
    )


@router.get("/history", response_class=HTMLResponse)
async def history(
    request: Request,
    platform: str | None = Query(None),
) -> HTMLResponse:
    items = await db.list_history_items(platform=platform)
    platforms = sorted({r["platform"] for r in items}) if items else []
    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "items": items,
            "current_platform": platform,
            "platforms": platforms,
        },
    )


@router.post("/content/{item_id}/cancel", response_class=HTMLResponse)
async def cancel_content(request: Request, item_id: UUID) -> HTMLResponse:
    item = await db.get_content_item(item_id)
    if not item:
        return HTMLResponse("<div>Not found</div>", status_code=404)

    cancelled = await cancel_cli_process(item_id)

    # If it wasn't running, it might be in the queue waiting
    if not cancelled and item["status"] == "queued":
        await db.cancel_queue_job_for_content(item_id)
        cancelled = True

    if cancelled:
        await db.update_content_status(
            item_id, "failed", error_message="Process was cancelled by user"
        )
        hub.publish(
            item_id, ProgressEvent(event_type="error", message="Process was cancelled by user")
        )

    item = await db.get_content_item(item_id)
    return templates.TemplateResponse(
        "partials/content_card.html",
        {"request": request, "item": item},
    )


@router.get("/content/{item_id}/status", response_class=HTMLResponse)
async def content_status(request: Request, item_id: UUID) -> HTMLResponse:
    item = await db.get_content_item(item_id)
    if item is None:
        return HTMLResponse("<div>Not found</div>", status_code=404)
    return templates.TemplateResponse(
        "partials/content_card.html",
        {"request": request, "item": item},
    )
