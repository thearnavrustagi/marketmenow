from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from web import db
from web.cli_runner import (
    PLATFORM_META,
    CliResult,
    get_builders,
    get_meta,
    run_cli_streaming,
)
from web.config import settings
from web.deps import templates
from web.events import ProgressEvent, hub

router = APIRouter(prefix="/generate", tags=["generate"])
logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()

_EMAIL_OFFSET_FILE = Path("vault/.email_offset")


@router.get("", response_class=HTMLResponse)
async def generate_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "generate.html",
        {"request": request, "platforms": PLATFORM_META},
    )


@router.post("", response_class=HTMLResponse)
async def generate_content(
    request: Request,
    platform: str = Form(...),
    command_type: str = Form(...),
) -> HTMLResponse:
    form_data = await request.form()
    params = {k: v for k, v in form_data.items() if k not in ("platform", "command_type") and v}

    meta = get_meta(platform, command_type)
    builders = get_builders(platform, command_type)
    if not meta or not builders:
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "message": f"Unknown command: {platform}/{command_type}",
                "level": "error",
            },
        )

    build_generate, build_publish = builders

    run_id = uuid.uuid4().hex[:8]
    output_dir = str(settings.output_dir.resolve() / platform / run_id)
    os.makedirs(output_dir, exist_ok=True)

    generate_cmd = build_generate(params, output_dir)
    publish_cmd = build_publish(params, output_dir)
    title = (
        params.get("topic")
        or params.get("caption")
        or params.get("subject")
        or f"{meta['label']} ({run_id})"
    )

    item_id = await db.insert_content_item(
        platform=platform,
        modality=meta["modality"],
        title=str(title)[:120],
        generate_command=generate_cmd,
        publish_command=publish_cmd,
    )

    task = asyncio.create_task(_run_generation(item_id, generate_cmd, publish_cmd, output_dir))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    item = await db.get_content_item(item_id)
    return templates.TemplateResponse(
        "partials/content_card.html",
        {"request": request, "item": item},
    )


async def _run_generation(
    item_id: uuid.UUID,
    generate_cmd: list[str],
    publish_cmd: list[str],
    output_dir: str,
) -> None:
    try:
        hub.publish(
            item_id,
            ProgressEvent(event_type="phase", message="Generation started", phase="generation"),
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
                publish_command=publish_cmd,
            )
            hub.publish(
                item_id,
                ProgressEvent(event_type="done", message="Generation complete — ready for review"),
            )
        else:
            await db.update_content_status(
                item_id,
                "failed",
                error_message=result.stderr[:1000] or f"Exit code {result.exit_code}",
                preview_data={"stdout": result.stdout[:3000], "stderr": result.stderr[:3000]},
            )
            hub.publish(item_id, ProgressEvent(event_type="error", message="Generation failed"))
    except Exception as exc:
        await db.update_content_status(item_id, "failed", error_message=str(exc)[:1000])
        hub.publish(item_id, ProgressEvent(event_type="error", message=str(exc)[:200]))


# ── Batch: Generate & Publish All ────────────────────────────────────

BATCH_ITEMS: list[dict[str, str]] = [
    {"platform": "instagram", "command_type": "reel", "title": "Instagram Reel", "key": "reel"},
    {
        "platform": "instagram",
        "command_type": "carousel",
        "title": "Instagram Carousel",
        "key": "carousel",
    },
    {"platform": "linkedin", "command_type": "post", "title": "LinkedIn Post", "key": "linkedin"},
    {
        "platform": "twitter",
        "command_type": "all",
        "title": "Twitter All (Replies + Thread)",
        "key": "twitter",
    },
    {"platform": "reddit", "command_type": "engage", "title": "Reddit Comments", "key": "reddit"},
    {"platform": "youtube", "command_type": "short", "title": "YouTube Short", "key": "youtube"},
    {"platform": "email", "command_type": "send", "title": "Email Outreach", "key": "email"},
]


@dataclass
class _BatchEntry:
    key: str
    item_id: uuid.UUID
    platform: str
    modality: str
    output_dir: str
    generate_cmd: list[str]
    publish_cmd: list[str]


def _read_email_offset() -> int:
    try:
        return int(_EMAIL_OFFSET_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def _write_email_offset(offset: int) -> None:
    _EMAIL_OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _EMAIL_OFFSET_FILE.write_text(str(offset))


@router.post("/all", response_class=HTMLResponse)
async def generate_all(request: Request) -> HTMLResponse:
    """Create all platform content items and kick off the batch pipeline."""
    batch_id = uuid.uuid4().hex[:8]
    entries: list[_BatchEntry] = []

    for spec in BATCH_ITEMS:
        platform = spec["platform"]
        command_type = spec["command_type"]
        key = spec["key"]

        meta = get_meta(platform, command_type)
        builders = get_builders(platform, command_type)
        if not meta or not builders:
            logger.warning("Skipping %s/%s — no meta or builders", platform, command_type)
            continue

        build_generate, build_publish = builders
        run_id = f"batch_{batch_id}_{key}"
        output_dir = str(settings.output_dir.resolve() / platform / run_id)
        os.makedirs(output_dir, exist_ok=True)

        params: dict[str, str] = {}
        if key == "email":
            email_offset = _read_email_offset()
            batch_size = settings.batch_email_size
            csv_path = str(settings.batch_email_csv.resolve())
            template_path = str(settings.batch_email_template.resolve())
            params = {"template": template_path, "file": csv_path}

        generate_cmd = build_generate(params, output_dir)
        publish_cmd = build_publish(params, output_dir)

        if key == "email":
            email_offset = _read_email_offset()
            batch_size = settings.batch_email_size
            end_row = email_offset + batch_size
            range_flag = f"{email_offset}-{end_row}"
            generate_cmd.extend(["-r", range_flag])
            publish_cmd.extend(["-r", range_flag])

        item_id = await db.insert_content_item(
            platform=platform,
            modality=meta["modality"],
            title=f"{spec['title']} (batch {batch_id})",
            generate_command=generate_cmd,
            publish_command=publish_cmd,
        )

        entries.append(
            _BatchEntry(
                key=key,
                item_id=item_id,
                platform=platform,
                modality=meta["modality"],
                output_dir=output_dir,
                generate_cmd=generate_cmd,
                publish_cmd=publish_cmd,
            )
        )

    task = asyncio.create_task(_run_batch(entries))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    items = [await db.get_content_item(e.item_id) for e in entries]
    cards_html = ""
    for item in items:
        if item is not None:
            resp = templates.TemplateResponse(
                "partials/content_card.html",
                {"request": request, "item": item},
            )
            cards_html += resp.body.decode()

    return HTMLResponse(cards_html)


async def _run_batch(entries: list[_BatchEntry]) -> None:
    """Run all batch items in parallel, coordinating dependencies."""
    reel_output_path: str | None = None
    reel_done = asyncio.Event()

    async def _run_one(entry: _BatchEntry) -> None:
        nonlocal reel_output_path

        try:
            if entry.key == "youtube":
                hub.publish(
                    entry.item_id,
                    ProgressEvent(
                        event_type="phase",
                        message="Waiting for Instagram Reel to finish...",
                        phase="waiting",
                    ),
                )
                await reel_done.wait()
                if reel_output_path:
                    entry.publish_cmd = _patch_youtube_cmd(entry.publish_cmd, reel_output_path)
                    hub.publish(
                        entry.item_id,
                        ProgressEvent(
                            event_type="log",
                            message=f"Using reel video: {reel_output_path}",
                        ),
                    )
                else:
                    await db.update_content_status(
                        entry.item_id,
                        "failed",
                        error_message="No reel MP4 available for YouTube upload",
                    )
                    hub.publish(
                        entry.item_id,
                        ProgressEvent(event_type="error", message="No reel MP4 available"),
                    )
                    return

            if entry.key == "reddit":
                await _run_reddit_two_step(entry)
                return

            result = await _run_single_command(entry)

            if entry.key == "reel":
                for f in result.output_files:
                    if f.endswith(".mp4"):
                        reel_output_path = f
                        break
                reel_done.set()

            if entry.key == "email":
                email_offset = _read_email_offset()
                _write_email_offset(email_offset + settings.batch_email_size)

        except Exception as exc:
            logger.exception("Batch item %s failed", entry.key)
            await db.update_content_status(entry.item_id, "failed", error_message=str(exc)[:1000])
            hub.publish(entry.item_id, ProgressEvent(event_type="error", message=str(exc)[:200]))
            if entry.key == "reel":
                reel_done.set()

    await asyncio.gather(*[_run_one(e) for e in entries], return_exceptions=True)


async def _run_single_command(entry: _BatchEntry) -> CliResult:
    """Run a single publish command that does generate+publish in one shot."""
    await db.update_content_status(entry.item_id, "posting")
    hub.publish(
        entry.item_id,
        ProgressEvent(
            event_type="phase",
            message=f"Running {entry.platform} pipeline...",
            phase="posting",
        ),
    )

    result = await run_cli_streaming(
        entry.publish_cmd,
        item_id=entry.item_id,
        output_dir=entry.output_dir,
    )

    if result.exit_code == 0:
        preview = {"stdout": result.stdout[:3000], "files": result.output_files}
        primary = result.output_files[0] if result.output_files else None
        await db.update_content_status(
            entry.item_id,
            "posted",
            preview_data=preview,
            output_path=primary,
        )
        hub.publish(
            entry.item_id,
            ProgressEvent(event_type="done", message=f"{entry.platform} posted successfully"),
        )
    else:
        error = result.stderr.strip()[:500]
        if not error:
            tail = "\n".join(result.stdout.strip().splitlines()[-10:])
            error = tail[:500] if tail else f"Exit code {result.exit_code}"
        await db.update_content_status(
            entry.item_id,
            "failed",
            error_message=error,
            preview_data={"stdout": result.stdout[:3000], "stderr": result.stderr[:3000]},
        )
        hub.publish(
            entry.item_id, ProgressEvent(event_type="error", message=f"Failed: {error[:200]}")
        )

    return result


async def _run_reddit_two_step(entry: _BatchEntry) -> None:
    """Reddit needs generate (discover+generate CSV) then publish (post from CSV)."""
    await db.update_content_status(entry.item_id, "generating")
    hub.publish(
        entry.item_id,
        ProgressEvent(
            event_type="phase", message="Discovering and generating comments...", phase="discovery"
        ),
    )

    gen_result = await run_cli_streaming(
        entry.generate_cmd,
        item_id=entry.item_id,
        output_dir=entry.output_dir,
    )

    if gen_result.exit_code != 0:
        error = gen_result.stderr.strip()[:500]
        if not error:
            tail = "\n".join(gen_result.stdout.strip().splitlines()[-10:])
            error = tail[:500] if tail else f"Exit code {gen_result.exit_code}"
        await db.update_content_status(
            entry.item_id,
            "failed",
            error_message=error,
            preview_data={"stdout": gen_result.stdout[:3000], "stderr": gen_result.stderr[:3000]},
        )
        hub.publish(
            entry.item_id,
            ProgressEvent(event_type="error", message=f"Discovery failed: {error[:200]}"),
        )
        return

    csv_path = os.path.join(entry.output_dir, "comments.csv")
    if not os.path.isfile(csv_path):
        error = f"Generate step completed but {csv_path} was not created"
        await db.update_content_status(
            entry.item_id,
            "failed",
            error_message=error,
            preview_data={"stdout": gen_result.stdout[:3000], "files": gen_result.output_files},
        )
        hub.publish(entry.item_id, ProgressEvent(event_type="error", message=error[:200]))
        return

    await db.update_content_status(entry.item_id, "posting")
    hub.publish(
        entry.item_id,
        ProgressEvent(event_type="phase", message="Posting comments...", phase="posting"),
    )

    pub_result = await run_cli_streaming(
        entry.publish_cmd,
        item_id=entry.item_id,
        output_dir=entry.output_dir,
    )

    if pub_result.exit_code == 0:
        preview = {
            "stdout": (gen_result.stdout + "\n---\n" + pub_result.stdout)[:3000],
            "files": gen_result.output_files + pub_result.output_files,
        }
        await db.update_content_status(entry.item_id, "posted", preview_data=preview)
        hub.publish(
            entry.item_id, ProgressEvent(event_type="done", message="Reddit comments posted")
        )
    else:
        error = pub_result.stderr.strip()[:500]
        if not error:
            tail = "\n".join(pub_result.stdout.strip().splitlines()[-10:])
            error = tail[:500] if tail else f"Exit code {pub_result.exit_code}"
        await db.update_content_status(entry.item_id, "failed", error_message=error)
        hub.publish(
            entry.item_id,
            ProgressEvent(event_type="error", message=f"Posting failed: {error[:200]}"),
        )


def _patch_youtube_cmd(cmd: list[str], mp4_path: str) -> list[str]:
    """Replace the placeholder MP4 path in the YouTube upload command."""
    patched: list[str] = []
    for arg in cmd:
        if arg.endswith(("*.mp4", "latest.mp4")):
            patched.append(mp4_path)
        else:
            patched.append(arg)
    return patched
