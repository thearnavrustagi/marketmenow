from __future__ import annotations

import asyncio
import os
import uuid
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web import db
from web.cli_runner import run_cli_streaming
from web.config import settings
from web.deps import templates
from web.events import ProgressEvent, hub

router = APIRouter(prefix="/content", tags=["review"])

_background_tasks: set[asyncio.Task] = set()


@router.post("/{item_id}/approve", response_class=HTMLResponse)
async def approve_content(request: Request, item_id: UUID) -> HTMLResponse:
    item = await db.get_content_item(item_id)
    if item is None:
        return HTMLResponse("<div>Not found</div>", status_code=404)

    await db.update_content_status(item_id, "approved")
    await db.enqueue_content(item_id, item["platform"])
    await db.update_content_status(item_id, "queued")

    item = await db.get_content_item(item_id)
    return templates.TemplateResponse(
        "partials/content_card.html",
        {"request": request, "item": item},
    )


@router.post("/{item_id}/reject", response_class=HTMLResponse)
async def reject_content(request: Request, item_id: UUID) -> HTMLResponse:
    await db.update_content_status(item_id, "failed", error_message="Rejected by user")
    item = await db.get_content_item(item_id)
    return templates.TemplateResponse(
        "partials/content_card.html",
        {"request": request, "item": item},
    )


@router.post("/{item_id}/regenerate", response_class=HTMLResponse)
async def regenerate_content(request: Request, item_id: UUID) -> HTMLResponse:
    item = await db.get_content_item(item_id)
    if item is None:
        return HTMLResponse("<div>Not found</div>", status_code=404)

    generate_cmd: list[str] = item["generate_command"]
    publish_cmd: list[str] | None = item["publish_command"]

    output_dir = _extract_output_dir(generate_cmd)
    if not output_dir:
        run_id = uuid.uuid4().hex[:8]
        output_dir = str(settings.output_dir.resolve() / item["platform"] / run_id)
    os.makedirs(output_dir, exist_ok=True)

    await db.update_content_status(item_id, "generating", error_message="")

    task = asyncio.create_task(_run_regeneration(item_id, generate_cmd, publish_cmd, output_dir))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    item = await db.get_content_item(item_id)
    return templates.TemplateResponse(
        "partials/content_card.html",
        {"request": request, "item": item},
    )


def _extract_output_dir(cmd: list[str]) -> str | None:
    """Extract --output-dir value from a stored CLI command."""
    for i, arg in enumerate(cmd):
        if arg == "--output-dir" and i + 1 < len(cmd):
            return cmd[i + 1]
    return None


async def _run_regeneration(
    item_id: UUID,
    generate_cmd: list[str],
    publish_cmd: list[str] | None,
    output_dir: str,
) -> None:
    try:
        hub.publish(
            item_id,
            ProgressEvent(event_type="phase", message="Regeneration started", phase="generation"),
        )
        result = await run_cli_streaming(generate_cmd, item_id=item_id, output_dir=output_dir)

        if result.exit_code == 0:
            preview: dict = {
                "stdout": result.stdout[:3000],
                "files": result.output_files,
            }
            primary_output = result.output_files[0] if result.output_files else None
            await db.update_content_status(
                item_id,
                "pending_review",
                preview_data=preview,
                output_path=primary_output,
            )
            hub.publish(
                item_id,
                ProgressEvent(
                    event_type="done", message="Regeneration complete — ready for review"
                ),
            )
        else:
            await db.update_content_status(
                item_id,
                "failed",
                error_message=result.stderr[:1000] or f"Exit code {result.exit_code}",
                preview_data={"stdout": result.stdout[:3000], "stderr": result.stderr[:3000]},
            )
            hub.publish(item_id, ProgressEvent(event_type="error", message="Regeneration failed"))
    except Exception as exc:
        await db.update_content_status(item_id, "failed", error_message=str(exc)[:1000])
        hub.publish(item_id, ProgressEvent(event_type="error", message=str(exc)[:200]))
