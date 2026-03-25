from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from marketmenow.core.project_manager import ProjectManager
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


def _email_offset_file() -> Path:
    pm = ProjectManager()
    slug = pm.get_active_project()
    if slug:
        return pm.project_dir(slug) / "vault" / ".email_offset"
    return Path("projects/gradeasy/vault/.email_offset")


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
    {"platform": "facebook", "command_type": "post", "title": "Facebook Post", "key": "facebook"},
    {
        "platform": "twitter",
        "command_type": "all",
        "title": "Twitter All (Replies + Thread)",
        "key": "twitter",
    },
    {"platform": "reddit", "command_type": "engage", "title": "Reddit Comments", "key": "reddit"},
    {"platform": "youtube", "command_type": "short", "title": "YouTube Short", "key": "youtube"},
    {"platform": "tiktok", "command_type": "upload", "title": "TikTok Video", "key": "tiktok"},
    {"platform": "email", "command_type": "send", "title": "Email Outreach", "key": "email"},
]


@dataclass
class _BatchEntry:
    key: str
    item_id: uuid.UUID
    platform: str
    command_type: str
    modality: str
    output_dir: str
    generate_cmd: list[str]
    publish_cmd: list[str]


def _read_email_offset() -> int:
    try:
        return int(_email_offset_file().read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def _write_email_offset(offset: int) -> None:
    f = _email_offset_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(str(offset))


def _get_batch_items() -> list[dict[str, object]]:
    pm = ProjectManager()
    slug = pm.get_active_project()
    if slug:
        try:
            config = pm.load_generation_config(slug)
            items = []
            for item in config.items:
                for i in range(item.count):
                    key = f"{item.command_type}_{i}" if item.count > 1 else item.command_type
                    title_suffix = f" {i + 1}" if item.count > 1 else ""
                    meta = get_meta(item.platform, item.command_type)
                    title = meta["label"] if meta else f"{item.platform} {item.command_type}"

                    params = dict(item.params)
                    for k, v in params.items():
                        if isinstance(v, str) and (v.endswith((".yaml", ".yml")) or "/" in v):
                            path = pm.project_dir(slug) / v
                            if path.exists():
                                params[k] = str(path)

                    items.append(
                        {
                            "platform": item.platform,
                            "command_type": item.command_type,
                            "title": f"{title}{title_suffix}",
                            "key": key,
                            "params": params,
                        }
                    )
            return items
        except FileNotFoundError:
            pass

    return BATCH_ITEMS


@router.post("/all", response_class=HTMLResponse)
async def generate_all(request: Request) -> HTMLResponse:
    """Create all platform content items and kick off the batch pipeline."""
    batch_id = uuid.uuid4().hex[:8]
    entries: list[_BatchEntry] = []

    items_to_run = _get_batch_items()

    for spec in items_to_run:
        platform = str(spec["platform"])
        command_type = str(spec["command_type"])
        key = str(spec["key"])

        meta = get_meta(platform, command_type)
        builders = get_builders(platform, command_type)
        if not meta or not builders:
            logger.warning("Skipping %s/%s — no meta or builders", platform, command_type)
            continue

        build_generate, build_publish = builders
        run_id = f"batch_{batch_id}_{key}"
        output_dir = str(settings.output_dir.resolve() / platform / run_id)
        os.makedirs(output_dir, exist_ok=True)

        params: dict[str, str] = dict(spec.get("params", {}))  # type: ignore
        if command_type == "send" and platform == "email" and not params.get("template"):
            pm = ProjectManager()
            slug = pm.get_active_project()
            csv_path = str(settings.batch_email_csv.resolve())
            template_path = str(settings.batch_email_template.resolve())
            if slug:
                proj_csv = pm.project_dir(slug) / "vault" / "teachers.csv"
                if proj_csv.exists():
                    csv_path = str(proj_csv)
                for tmpl in pm.project_dir(slug).glob("templates/email/*.html"):
                    template_path = str(tmpl)
                    break
            params["template"] = template_path
            if not params.get("file"):
                params["file"] = csv_path

        generate_cmd = build_generate(params, output_dir)
        publish_cmd = build_publish(params, output_dir)

        if command_type == "send" and platform == "email":
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
                command_type=command_type,
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


def _get_index(key: str) -> int:
    parts = key.split("_")
    if parts[-1].isdigit():
        return int(parts[-1])
    return 0


async def _run_batch(entries: list[_BatchEntry]) -> None:
    """Run all batch items in parallel, coordinating dependencies."""
    reel_outputs: dict[int, str] = {}
    reel_dones: dict[int, asyncio.Event] = {}

    for e in entries:
        if e.command_type == "reel":
            idx = _get_index(e.key)
            reel_dones[idx] = asyncio.Event()

    async def _run_one(entry: _BatchEntry) -> None:
        idx = _get_index(entry.key)

        try:
            _reel_dependent = (entry.command_type == "short" and entry.platform == "youtube") or (
                entry.command_type == "upload" and entry.platform == "tiktok"
            )
            if _reel_dependent:
                platform_label = "YouTube" if entry.platform == "youtube" else "TikTok"
                hub.publish(
                    entry.item_id,
                    ProgressEvent(
                        event_type="phase",
                        message="Waiting for Instagram Reel to finish...",
                        phase="waiting",
                    ),
                )
                if not reel_dones:
                    await db.update_content_status(
                        entry.item_id,
                        "failed",
                        error_message=f"No reels in batch for {platform_label} upload",
                    )
                    hub.publish(
                        entry.item_id,
                        ProgressEvent(event_type="error", message="No reels in batch"),
                    )
                    return

                target_idx = idx if idx in reel_dones else max(reel_dones.keys())
                await reel_dones[target_idx].wait()

                reel_output_path = reel_outputs.get(target_idx)
                if reel_output_path:
                    entry.publish_cmd = _patch_video_cmd(entry.publish_cmd, reel_output_path)
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
                        error_message=f"No reel MP4 available for {platform_label} upload",
                    )
                    hub.publish(
                        entry.item_id,
                        ProgressEvent(event_type="error", message="No reel MP4 available"),
                    )
                    return

            if entry.command_type == "engage" and entry.platform == "reddit":
                await _run_reddit_two_step(entry)
                return

            result = await _run_single_command(entry)

            if entry.command_type == "reel":
                for f in result.output_files:
                    if f.endswith(".mp4"):
                        reel_outputs[idx] = f
                        break
                reel_dones[idx].set()

            if entry.command_type == "send" and entry.platform == "email":
                email_offset = _read_email_offset()
                _write_email_offset(email_offset + settings.batch_email_size)

        except Exception as exc:
            logger.exception("Batch item %s failed", entry.key)
            await db.update_content_status(entry.item_id, "failed", error_message=str(exc)[:1000])
            hub.publish(entry.item_id, ProgressEvent(event_type="error", message=str(exc)[:200]))
            if entry.command_type == "reel":
                reel_dones[idx].set()

    await asyncio.gather(*[_run_one(e) for e in entries], return_exceptions=True)


_ERROR_MARKERS = re.compile(
    r"(Traceback \(most recent call last\)|Error:|Exception:|FAILED|raise \w+)",
    re.IGNORECASE,
)


def _extract_error(stderr: str, stdout: str, exit_code: int) -> str:
    """Pull the most useful error snippet from CLI subprocess output."""
    for source in (stderr, stdout):
        lines = source.strip().splitlines()
        for line in reversed(lines):
            stripped = line.strip()
            if stripped and _ERROR_MARKERS.search(stripped):
                return stripped[:1000]
        if lines:
            last = lines[-1].strip()
            if last:
                return last[:1000]
    return f"Process exited with code {exit_code}"


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
        error = _extract_error(result.stderr, result.stdout, result.exit_code)
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
        error = _extract_error(gen_result.stderr, gen_result.stdout, gen_result.exit_code)
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
        error = _extract_error(pub_result.stderr, pub_result.stdout, pub_result.exit_code)
        await db.update_content_status(
            entry.item_id,
            "failed",
            error_message=error,
            preview_data={"stdout": pub_result.stdout[:3000], "stderr": pub_result.stderr[:3000]},
        )
        hub.publish(
            entry.item_id,
            ProgressEvent(event_type="error", message=f"Posting failed: {error[:200]}"),
        )


def _patch_video_cmd(cmd: list[str], mp4_path: str) -> list[str]:
    """Replace the placeholder MP4 path in a video upload command (YouTube/TikTok)."""
    patched: list[str] = []
    for arg in cmd:
        if arg.endswith(("*.mp4", "latest.mp4")):
            patched.append(mp4_path)
        else:
            patched.append(arg)
    return patched
