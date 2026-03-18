from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from web import db
from web.deps import templates

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    status: str | None = Query(None),
    platform: str | None = Query(None),
) -> HTMLResponse:
    items = await db.list_content_items(status=status, platform=platform)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "items": items,
            "current_status": status,
            "current_platform": platform,
        },
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
