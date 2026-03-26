from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.credentials import (
    PLATFORM_CREDENTIAL_KEYS,
    delete_credential_set,
    get_all_platforms,
    get_keys_for_platform,
    load_credential_sets,
    save_credential_set,
)
from web.deps import templates

router = APIRouter(prefix="/credentials", tags=["credentials"])
logger = logging.getLogger(__name__)


@router.get("", response_class=HTMLResponse)
async def credentials_page(request: Request) -> HTMLResponse:
    cred_sets = load_credential_sets()
    platforms = get_all_platforms()
    platform_keys = PLATFORM_CREDENTIAL_KEYS

    grouped: dict[str, list[dict]] = {}
    for name, cs in cred_sets.items():
        entry = {
            "name": name,
            "platform": cs.platform,
            "keys_filled": list(cs.env.keys()),
            "env": cs.env,
        }
        grouped.setdefault(cs.platform, []).append(entry)

    return templates.TemplateResponse(
        request,
        "credentials.html",
        {
            "grouped_sets": grouped,
            "platforms": platforms,
            "platform_keys": platform_keys,
        },
    )


@router.post("/save", response_class=HTMLResponse)
async def save_cred(request: Request) -> HTMLResponse:
    form_data = await request.form()
    set_name = str(form_data.get("set_name", "")).strip()
    platform = str(form_data.get("platform", "")).strip()

    if not set_name or not platform:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "Name and platform are required", "level": "error"},
        )

    keys_info = get_keys_for_platform(platform)
    all_keys = keys_info["required"] + keys_info["optional"]

    env_vars: dict[str, str] = {}
    for key in all_keys:
        val = str(form_data.get(key, "")).strip()
        if val:
            env_vars[key] = val

    save_credential_set(set_name, platform, env_vars)

    return templates.TemplateResponse(
        request,
        "partials/toast.html",
        {"message": f"Credential set '{set_name}' saved", "level": "success"},
    )


@router.delete("/{set_name}", response_class=HTMLResponse)
async def delete_cred(request: Request, set_name: str) -> HTMLResponse:
    if delete_credential_set(set_name):
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": f"'{set_name}' deleted", "level": "success"},
        )
    return templates.TemplateResponse(
        request,
        "partials/toast.html",
        {"message": f"'{set_name}' not found", "level": "error"},
    )


@router.get("/keys/{platform}", response_class=HTMLResponse)
async def platform_keys(request: Request, platform: str) -> HTMLResponse:
    """Return form fields for a platform's credential keys (HTMX partial)."""
    keys_info = get_keys_for_platform(platform)
    html_parts: list[str] = []

    for key in keys_info["required"]:
        html_parts.append(_field_html(key, required=True))
    for key in keys_info["optional"]:
        html_parts.append(_field_html(key, required=False))

    return HTMLResponse("\n".join(html_parts))


def _field_html(key: str, *, required: bool) -> str:
    label = key
    req = ' <span class="text-red-400">*</span>' if required else ""
    return (
        f'<div class="flex flex-col gap-1.5">'
        f'<label class="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">'
        f"{label}{req}</label>"
        f'<input type="text" name="{key}" placeholder="{key}"'
        f' class="w-full bg-black border border-zinc-800 rounded-lg px-3 py-2 text-sm'
        f" text-zinc-100 focus:border-white focus:ring-1 focus:ring-white/20"
        f' transition-colors outline-none font-mono"'
        f"{' required' if required else ''}>"
        f"</div>"
    )
