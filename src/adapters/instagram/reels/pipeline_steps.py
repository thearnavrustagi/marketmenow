from __future__ import annotations

import json
import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment

from ..prompts import load_prompt


def _render_prompt_text(template_str: str, variables: dict[str, object]) -> str:
    """Render a prompt template string with the given variables.

    Tries Jinja2 first (``{{ var }}`` syntax). If the template itself fails
    to parse (e.g. because it uses ``{{`` / ``}}`` as literal JSON braces in
    Python ``.format()`` style), falls back to ``str.format_map()``.
    """
    from jinja2 import Template

    try:
        tmpl = Template(template_str)
        # Escape Jinja2 delimiters in variable *values* (LLM-generated text)
        safe = {
            k: v.replace("{{", "{ {").replace("}}", "} }") if isinstance(v, str) else v
            for k, v in variables.items()
        }
        return tmpl.render(**safe)
    except Exception:
        # Template uses .format() style {var} / {{ for literal braces
        str_vars = {k: str(v) for k, v in variables.items()}
        try:
            return template_str.format_map(str_vars)
        except (KeyError, ValueError):
            return template_str


_MD_PATTERNS = re.compile(
    r"\*\*\*(.+?)\*\*\*"  # ***bold italic***
    r"|\*\*(.+?)\*\*"  # **bold**
    r"|\*(.+?)\*"  # *italic*
    r"|__(.+?)__"  # __bold__
    r"|_(.+?)_"  # _italic_
    r"|~~(.+?)~~"  # ~~strikethrough~~
    r"|`(.+?)`"  # `code`
    r"|^#{1,6}\s+",  # headings
    re.MULTILINE,
)


def _strip_markdown(text: str) -> str:
    """Remove common markdown formatting from a string."""

    def _replace(m: re.Match[str]) -> str:
        for g in m.groups():
            if g is not None:
                return g
        return ""

    return _MD_PATTERNS.sub(_replace, text).strip()


def _sanitise_dashes(text: str) -> str:
    """Replace em-dashes and en-dashes with hyphens (AI-detection avoidance + TTS clarity)."""
    return text.replace("\u2014", " - ").replace("\u2013", " - ")


def _clean_llm_text(text: str) -> str:
    """Strip markdown and sanitise dashes from LLM-generated text."""
    return _sanitise_dashes(_strip_markdown(text))


_JINJA_ENV = Environment()

StepFunc = Callable[["PipelineContext", dict[str, object]], Coroutine[None, None, object]]


@dataclass
class PipelineContext:
    """Accumulated state passed through every pipeline step."""

    variables: dict[str, object] = field(default_factory=dict)
    settings: object = None
    services: dict[str, object] = field(default_factory=dict)


def _resolve_inputs(
    raw_inputs: dict[str, object],
    variables: dict[str, object],
) -> dict[str, object]:
    """Resolve ``{{ var }}`` references in step input values."""
    resolved: dict[str, object] = {}
    for key, val in raw_inputs.items():
        if isinstance(val, str) and "{{" in val:
            stripped = val.strip()
            if stripped.startswith("{{") and stripped.endswith("}}"):
                var_path = stripped[2:-2].strip()
                parts = var_path.split(".")
                obj: object = variables
                try:
                    for part in parts:
                        if isinstance(obj, dict):
                            obj = obj[part]
                        else:
                            obj = val
                            break
                    resolved[key] = obj
                except (KeyError, TypeError):
                    resolved[key] = val
            else:
                tmpl = _JINJA_ENV.from_string(val)
                resolved[key] = tmpl.render(**variables)
        elif isinstance(val, dict):
            resolved[key] = _resolve_inputs(val, variables)  # type: ignore[arg-type]
        else:
            resolved[key] = val
    return resolved


class StepRegistry:
    """Maps step type names to async callables."""

    def __init__(self) -> None:
        self._steps: dict[str, StepFunc] = {}

    def register(self, type_name: str, func: StepFunc) -> None:
        self._steps[type_name] = func

    def get(self, type_name: str) -> StepFunc:
        if type_name not in self._steps:
            raise KeyError(f"Unknown pipeline step type: {type_name!r}")
        return self._steps[type_name]

    def has(self, type_name: str) -> bool:
        return type_name in self._steps


# ---------------------------------------------------------------------------
# Built-in step implementations
# ---------------------------------------------------------------------------


async def _rubric_step(ctx: PipelineContext, inputs: dict[str, object]) -> object:
    """Generate a rubric from an assignment image using the grading service."""
    grader = ctx.services["grader"]
    image_path = Path(str(inputs["assignment_image"]))
    rubric_items = await grader.generate_rubric(image_path)  # type: ignore[union-attr]
    return [item.model_dump() for item in rubric_items]


async def _grading_step(ctx: PipelineContext, inputs: dict[str, object]) -> object:
    """Grade an assignment image against rubric items."""
    from ..grading.models import RubricItem

    grader = ctx.services["grader"]
    image_path = Path(str(inputs["assignment_image"]))
    raw_items = inputs.get("rubric_items", [])
    if isinstance(raw_items, list):
        rubric_items = [
            RubricItem(**item) if isinstance(item, dict) else item for item in raw_items
        ]
    else:
        rubric_items = []
    result = await grader.grade(image_path, rubric_items)  # type: ignore[union-attr]
    return result.model_dump()


async def _pick_horror_step(ctx: PipelineContext, inputs: dict[str, object]) -> object:
    """Pick a random horror movie/game title from the corpus."""
    from .horror_corpus import pick_random_horror

    title = pick_random_horror()
    return {"horror_source": title}


async def _pick_aita_step(ctx: PipelineContext, inputs: dict[str, object]) -> object:
    """Pick a random AITA teaching scenario from the corpus."""
    from .aita_corpus import pick_random_aita

    scenario = pick_random_aita()
    return {"aita_scenario": scenario}


async def _load_product_step(ctx: PipelineContext, inputs: dict[str, object]) -> object:
    """Read product.md and discover background video from the active project."""
    from marketmenow.core.project_manager import ProjectManager

    project_slug = ctx.services.get("project_slug", "")
    if not project_slug:
        raise ValueError("load_product step requires 'project_slug' in pipeline services")

    pm = ProjectManager()
    project_dir = pm.project_dir(str(project_slug))

    product_path = project_dir / "product.md"
    if not product_path.exists():
        raise FileNotFoundError(
            f"product.md not found in project '{project_slug}' (expected at {product_path})"
        )

    result: dict[str, str] = {
        "product_info": product_path.read_text(encoding="utf-8"),
    }

    import random

    bg_dir = project_dir / "assets" / "backgrounds"
    if bg_dir.is_dir():
        videos = [f for f in bg_dir.iterdir() if f.suffix.lower() in {".mp4", ".webm", ".mov"}]
        if videos:
            result["background_video"] = str(random.choice(videos).resolve())

    music_dir = project_dir / "assets" / "music"
    if music_dir.is_dir():
        tracks = [
            f for f in music_dir.iterdir() if f.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}
        ]
        if tracks:
            result["background_music"] = str(random.choice(tracks).resolve())

    return result


async def _llm_step(ctx: PipelineContext, inputs: dict[str, object]) -> object:
    """Run an LLM call using a named prompt file and return parsed JSON fields."""
    from marketmenow.integrations.llm import LLMProvider, create_llm_provider

    provider: LLMProvider | None = ctx.services.get("llm_provider")  # type: ignore[assignment]
    if provider is None:
        provider = create_llm_provider()

    prompt_name = str(inputs.get("prompt", ""))
    model = str(inputs.get("model", "gemini-2.5-flash"))
    temperature = float(inputs.get("temperature", 0.8))
    context_vars = inputs.get("context", {})
    output_fields = inputs.get("output_fields", [])

    if not prompt_name:
        raise ValueError("LLM step requires a 'prompt' input (prompt file name)")

    project_slug = str(ctx.services.get("project_slug", "")) or None

    # Resolve context variables for template rendering
    template_vars: dict[str, object] = {}
    if isinstance(context_vars, dict):
        for k, v in context_vars.items():
            if isinstance(v, str):
                template_vars[k] = v
            elif isinstance(v, list):
                template_vars[k] = (
                    "\n".join(
                        f"  - {ev.get('rubric_item_name', ev.get('name', ''))}: "
                        f"{ev.get('points_awarded', ev.get('max_points', ''))}/{ev.get('max_points', '')} "
                        f"-- {ev.get('feedback', ev.get('description', ''))}"
                        for ev in v
                        if isinstance(ev, dict)
                    )
                    if v and isinstance(v[0], dict)
                    else str(v)
                )
            else:
                template_vars[k] = str(v)

    # Add brand/persona from pipeline context if available
    brand_dict = ctx.variables.get("brand")
    persona_dict = ctx.variables.get("persona")
    if brand_dict and isinstance(brand_dict, dict):
        template_vars["brand"] = brand_dict
    if persona_dict and isinstance(persona_dict, dict):
        template_vars["persona"] = persona_dict

    # Epsilon-greedy ICL if settings are available in the pipeline context.
    icl_examples: list[dict[str, object]] | None = None
    top_examples_path = ctx.services.get("top_examples_path")
    if top_examples_path is not None:
        from marketmenow.core.icl import select_icl_examples

        icl_examples, _exploring = select_icl_examples(
            top_examples_path,  # type: ignore[arg-type]
            int(ctx.services.get("max_examples", 5)),  # type: ignore[arg-type]
            float(ctx.services.get("epsilon", 0.3)),  # type: ignore[arg-type]
        )

    # Use PromptBuilder when a decomposed functions/ YAML exists, otherwise
    # fall back to legacy load_prompt + .format() for older pipeline prompts.
    from marketmenow.core.prompt_builder import PromptBuilder

    builder = PromptBuilder()
    function_path = builder._resolve_file(
        f"functions/{prompt_name}.yaml", "instagram", project_slug
    )

    if function_path:
        built = builder.build(
            platform="instagram",
            function=prompt_name,
            icl_examples=icl_examples,
            template_vars=template_vars,
            project_slug=project_slug,
        )
        system_text = built.system or None
        user_text = built.user
    else:
        prompt = load_prompt(prompt_name, project_slug=project_slug)
        user_text = _render_prompt_text(prompt["user"], template_vars)
        system_text = (
            _render_prompt_text(prompt["system"], template_vars) if prompt["system"] else None
        )

    response = await provider.generate_json(
        model=model,
        system=system_text or "",
        contents=user_text,
        temperature=temperature,
    )

    data = json.loads(response.text)
    if isinstance(data, list):
        data = data[0]

    if isinstance(data, dict):
        data = {k: _clean_llm_text(v) if isinstance(v, str) else v for k, v in data.items()}

    if isinstance(output_fields, list) and output_fields:
        return {k: data.get(k, "") for k in output_fields}
    return data


# ---------------------------------------------------------------------------
# Default registry with built-in steps
# ---------------------------------------------------------------------------


def create_default_registry() -> StepRegistry:
    from .worksheet import _fill_worksheet_step, _worksheet_step

    registry = StepRegistry()
    registry.register("rubric", _rubric_step)
    registry.register("grading", _grading_step)
    registry.register("llm", _llm_step)
    registry.register("worksheet", _worksheet_step)
    registry.register("fill_worksheet", _fill_worksheet_step)
    registry.register("pick_horror", _pick_horror_step)
    registry.register("pick_aita", _pick_aita_step)
    registry.register("load_product", _load_product_step)
    return registry


default_registry = create_default_registry()
