from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from web.deps import templates

router = APIRouter(prefix="/project", tags=["project"])


def _get_pm():
    from marketmenow.core.project_manager import ProjectManager

    return ProjectManager()


@router.get("", response_class=HTMLResponse)
async def project_page(request: Request) -> HTMLResponse:
    pm = _get_pm()
    projects = pm.list_projects()
    active = pm.get_active_project()
    return templates.TemplateResponse(
        request,
        "project.html",
        {"projects": projects, "active": active},
    )


@router.post("/select", response_class=HTMLResponse)
async def select_project(request: Request, slug: str = Form(...)) -> Response:
    pm = _get_pm()
    import contextlib

    with contextlib.suppress(FileNotFoundError):
        pm.set_active_project(slug)
    response = Response(status_code=200, headers={"HX-Refresh": "true"})
    response.set_cookie("mmn_project", slug, max_age=86400 * 365)
    return response
