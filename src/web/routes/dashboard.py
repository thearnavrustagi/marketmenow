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


@router.delete("/clear", response_class=HTMLResponse)
async def clear_all(request: Request) -> HTMLResponse:
    await db.clear_all_content()
    return HTMLResponse(
        '<div class="col-span-full text-center py-16 text-zinc-500">'
        "<p>All content cleared.</p>"
        '</div>'
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


@router.get("/content/{item_id}/status", response_class=HTMLResponse)
async def content_status(request: Request, item_id: UUID) -> HTMLResponse:
    item = await db.get_content_item(item_id)
    if item is None:
        return HTMLResponse("<div>Not found</div>", status_code=404)
    return templates.TemplateResponse(
        "partials/content_card.html",
        {"request": request, "item": item},
    )
