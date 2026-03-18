from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from web.config import settings

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

_output_prefix = str(settings.output_dir.resolve())

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _to_output_url(abs_path: str) -> str:
    """Convert an absolute file path to a /output/... URL."""
    if abs_path.startswith(_output_prefix):
        return "/output" + abs_path[len(_output_prefix) :]
    return abs_path


templates.env.filters["output_url"] = _to_output_url
