from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web import db
from web.cli_runner import run_cli_streaming
from web.config import settings
from web.credentials import get_env_overrides, load_credential_sets
from web.deps import templates
from web.events import ProgressEvent, hub

router = APIRouter(prefix="/outreach", tags=["outreach"])
logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[None]] = set()

_HISTORY_PATH = Path(".outreach_history.json")
_CAMPAIGNS_DIR = Path("campaigns")


def _load_history() -> dict[str, dict[str, object]]:
    if not _HISTORY_PATH.exists():
        return {}
    try:
        raw = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
        return raw.get("contacted", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def _load_campaign_profiles() -> list[dict[str, object]]:
    profiles: list[dict[str, object]] = []
    if not _CAMPAIGNS_DIR.exists():
        return profiles
    for p in sorted(_CAMPAIGNS_DIR.glob("*.yaml")):
        if p.name.endswith(".example.yaml"):
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("platform"):
                profiles.append({
                    "filename": p.name,
                    "path": str(p),
                    "platform": data.get("platform", ""),
                    "product_name": data.get("product", {}).get("name", "Untitled"),
                    "product_tagline": data.get("product", {}).get("tagline", ""),
                    "min_score": data.get("ideal_customer", {}).get("min_score", 0),
                    "max_messages": data.get("messaging", {}).get("max_messages", 10),
                    "vectors": len(data.get("discovery", [])),
                })
        except (yaml.YAMLError, AttributeError):
            continue
    return profiles


def _get_outreach_workflows() -> list[dict[str, object]]:
    from marketmenow.core.workflow_registry import build_workflow_registry

    registry = build_workflow_registry()
    outreach_names = {"twitter-outreach", "email-outreach"}
    result = []
    for wf in registry.list_all():
        if wf.name in outreach_names:
            result.append({
                "name": wf.name,
                "description": wf.description,
                "steps": [{"name": s.name, "description": s.description} for s in wf.steps],
                "params": [
                    {
                        "name": p.name,
                        "type": p.type.value,
                        "required": p.required,
                        "default": p.default,
                        "help": p.help,
                        "short": p.short,
                    }
                    for p in wf.params
                ],
            })
    return result


def _history_stats(contacted: dict[str, dict[str, object]]) -> dict[str, object]:
    total = len(contacted)
    success = sum(1 for v in contacted.values() if v.get("success", True))
    by_platform: dict[str, int] = {}
    for key in contacted:
        plat = key.split(":", 1)[0] if ":" in key else "unknown"
        by_platform[plat] = by_platform.get(plat, 0) + 1

    avg_score = 0.0
    scores = [v.get("score", 0) for v in contacted.values() if isinstance(v.get("score"), int | float)]
    if scores:
        avg_score = sum(scores) / len(scores)

    return {
        "total": total,
        "success": success,
        "fail": total - success,
        "success_rate": round(success / total * 100, 1) if total else 0,
        "avg_score": round(avg_score, 1),
        "by_platform": by_platform,
    }


def _history_entries(contacted: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    entries = []
    for key, val in contacted.items():
        platform, handle = key.split(":", 1) if ":" in key else ("unknown", key)
        entries.append({
            "platform": platform,
            "handle": handle,
            "sent_at": val.get("sent_at", ""),
            "message_preview": val.get("message_preview", ""),
            "score": val.get("score", 0),
            "success": val.get("success", True),
        })
    entries.sort(key=lambda e: e.get("sent_at", ""), reverse=True)
    return entries


@router.get("", response_class=HTMLResponse)
async def outreach_page(request: Request) -> HTMLResponse:
    contacted = _load_history()
    stats = _history_stats(contacted)
    entries = _history_entries(contacted)
    campaigns = _load_campaign_profiles()
    workflows = _get_outreach_workflows()

    cred_sets = load_credential_sets()
    cred_sets_by_platform: dict[str, list[str]] = {}
    for name, cs in cred_sets.items():
        cred_sets_by_platform.setdefault(cs.platform, []).append(name)

    return templates.TemplateResponse(
        "outreach.html",
        {
            "request": request,
            "stats": stats,
            "entries": entries,
            "campaigns": campaigns,
            "workflows": workflows,
            "cred_sets_by_platform": cred_sets_by_platform,
        },
    )


@router.post("/run", response_class=HTMLResponse)
async def run_outreach(request: Request) -> HTMLResponse:
    form_data = await request.form()
    workflow_name = str(form_data.get("workflow_name", ""))

    if not workflow_name:
        return templates.TemplateResponse(
            "partials/toast.html",
            {"request": request, "message": "No workflow selected", "level": "error"},
        )

    cmd = ["mmn", "run", workflow_name]
    for key, val in form_data.items():
        if key in ("workflow_name", "credential_set") or not val:
            continue
        cli_key = f"--{key.replace('_', '-')}"
        if val == "true":
            cmd.append(cli_key)
        elif val != "false":
            cmd.extend([cli_key, str(val)])

    cred_set_name = str(form_data.get("credential_set", ""))
    env_overrides = get_env_overrides(cred_set_name) if cred_set_name else None

    run_id = uuid.uuid4().hex[:8]
    output_dir = str(settings.output_dir.resolve() / "outreach" / run_id)
    os.makedirs(output_dir, exist_ok=True)

    item_id = await db.insert_content_item(
        platform="outreach",
        modality="outreach",
        title=f"{workflow_name} ({run_id})",
        generate_command=cmd,
        publish_command=cmd,
    )

    task = asyncio.create_task(_run_outreach(item_id, cmd, output_dir, env_overrides))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    item = await db.get_content_item(item_id)
    return templates.TemplateResponse(
        "partials/content_card.html",
        {"request": request, "item": item},
    )


async def _run_outreach(
    item_id: uuid.UUID,
    cmd: list[str],
    output_dir: str,
    env_overrides: dict[str, str] | None,
) -> None:
    try:
        hub.publish(
            item_id,
            ProgressEvent(event_type="phase", message="Outreach started", phase="generation"),
        )
        result = await run_cli_streaming(
            cmd,
            item_id=item_id,
            output_dir=output_dir,
            env_overrides=env_overrides,
        )

        if result.exit_code == 0:
            preview: dict[str, object] = {"stdout": result.stdout[:3000], "files": result.output_files}
            primary = result.output_files[0] if result.output_files else None
            await db.update_content_status(
                item_id,
                "posted",
                preview_data=preview,
                output_path=primary,
            )
            hub.publish(item_id, ProgressEvent(event_type="done", message="Outreach completed"))
        else:
            await db.update_content_status(
                item_id,
                "failed",
                error_message=result.stderr[:1000] or f"Exit code {result.exit_code}",
                preview_data={"stdout": result.stdout[:3000], "stderr": result.stderr[:3000]},
            )
            hub.publish(item_id, ProgressEvent(event_type="error", message="Outreach failed"))
    except Exception as exc:
        await db.update_content_status(item_id, "failed", error_message=str(exc)[:1000])
        hub.publish(item_id, ProgressEvent(event_type="error", message=str(exc)[:200]))
