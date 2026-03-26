from __future__ import annotations

import asyncio
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

router = APIRouter(prefix="/flows", tags=["flows"])
logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()

_CUSTOM_DIR = Path(__file__).resolve().parent.parent.parent / "marketmenow" / "workflows" / "custom"


def _get_registry():  # type: ignore[no-untyped-def]
    from marketmenow.core.workflow_registry import build_workflow_registry

    return build_workflow_registry()


def _get_steps():  # type: ignore[no-untyped-def]
    from marketmenow.steps.registry import list_steps

    return list_steps()


def _workflows_as_dicts() -> list[dict]:
    registry = _get_registry()
    result = []
    for wf in registry.list_all():
        result.append(
            {
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
            }
        )
    return result


# ── Pages ─────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def flows_page(request: Request) -> HTMLResponse:
    workflows = _workflows_as_dicts()
    cred_sets = load_credential_sets()
    cred_sets_by_platform: dict[str, list[str]] = {}
    for name, cs in cred_sets.items():
        cred_sets_by_platform.setdefault(cs.platform, []).append(name)

    return templates.TemplateResponse(
        request,
        "flows.html",
        {
            "workflows": workflows,
            "cred_sets_by_platform": cred_sets_by_platform,
        },
    )


@router.post("/run", response_class=HTMLResponse)
async def run_flow(request: Request) -> HTMLResponse:
    form_data = await request.form()
    workflow_name = str(form_data.get("workflow_name", ""))

    if not workflow_name:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "No workflow selected", "level": "error"},
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
    output_dir = str(settings.output_dir.resolve() / "flows" / run_id)
    os.makedirs(output_dir, exist_ok=True)

    item_id = await db.insert_content_item(
        platform="workflow",
        modality="workflow",
        title=f"{workflow_name} ({run_id})",
        generate_command=cmd,
        publish_command=cmd,
    )

    task = asyncio.create_task(_run_workflow(item_id, cmd, output_dir, env_overrides))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    item = await db.get_content_item(item_id)
    return templates.TemplateResponse(
        request,
        "partials/content_card.html",
        {"item": item},
    )


async def _run_workflow(
    item_id: uuid.UUID,
    cmd: list[str],
    output_dir: str,
    env_overrides: dict[str, str] | None,
) -> None:
    try:
        hub.publish(
            item_id,
            ProgressEvent(event_type="phase", message="Workflow started", phase="generation"),
        )
        result = await run_cli_streaming(
            cmd,
            item_id=item_id,
            output_dir=output_dir,
            env_overrides=env_overrides,
        )

        if result.exit_code == 0:
            preview: dict = {"stdout": result.stdout[:3000], "files": result.output_files}
            primary = result.output_files[0] if result.output_files else None
            await db.update_content_status(
                item_id,
                "posted",
                preview_data=preview,
                output_path=primary,
            )
            hub.publish(item_id, ProgressEvent(event_type="done", message="Workflow completed"))
        else:
            await db.update_content_status(
                item_id,
                "failed",
                error_message=result.stderr[:1000] or f"Exit code {result.exit_code}",
                preview_data={"stdout": result.stdout[:3000], "stderr": result.stderr[:3000]},
            )
            hub.publish(item_id, ProgressEvent(event_type="error", message="Workflow failed"))
    except Exception as exc:
        await db.update_content_status(item_id, "failed", error_message=str(exc)[:1000])
        hub.publish(item_id, ProgressEvent(event_type="error", message=str(exc)[:200]))


# ── Flow Editor ───────────────────────────────────────────────────────


@router.get("/editor", response_class=HTMLResponse)
async def editor_page(request: Request, name: str = "") -> HTMLResponse:
    steps = [{"name": s.name, "description": s.description} for s in _get_steps()]

    existing_yaml = ""
    if name:
        yaml_path = _CUSTOM_DIR / f"{name}.yaml"
        if yaml_path.exists():
            existing_yaml = yaml_path.read_text(encoding="utf-8")

    return templates.TemplateResponse(
        request,
        "flow_editor.html",
        {
            "steps": steps,
            "existing_name": name,
            "existing_yaml": existing_yaml,
        },
    )


@router.post("/save", response_class=HTMLResponse)
async def save_flow(request: Request) -> HTMLResponse:
    form_data = await request.form()
    yaml_content = str(form_data.get("yaml_content", ""))

    if not yaml_content.strip():
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "YAML content is empty", "level": "error"},
        )

    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": f"Invalid YAML: {exc}", "level": "error"},
        )

    if not isinstance(data, dict) or "name" not in data:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "YAML must have a 'name' field", "level": "error"},
        )

    if not data.get("steps"):
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {
                "message": "Workflow must have at least one step",
                "level": "error",
            },
        )

    name = str(data["name"])
    safe_name = name.replace(" ", "-").lower()

    _CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    yaml_path = _CUSTOM_DIR / f"{safe_name}.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")

    return templates.TemplateResponse(
        request,
        "partials/toast.html",
        {"message": f"Workflow '{name}' saved", "level": "success"},
    )


@router.delete("/{name}", response_class=HTMLResponse)
async def delete_flow(request: Request, name: str) -> HTMLResponse:
    yaml_path = _CUSTOM_DIR / f"{name}.yaml"
    if yaml_path.exists():
        yaml_path.unlink()
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": f"Workflow '{name}' deleted", "level": "success"},
        )
    return templates.TemplateResponse(
        request,
        "partials/toast.html",
        {"message": f"Workflow '{name}' not found", "level": "error"},
    )
