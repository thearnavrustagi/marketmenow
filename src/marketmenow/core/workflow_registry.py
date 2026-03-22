from __future__ import annotations

import logging

from marketmenow.core.workflow import Workflow, WorkflowError

logger = logging.getLogger(__name__)


class WorkflowRegistry:
    """Holds registered workflows keyed by name."""

    def __init__(self) -> None:
        self._workflows: dict[str, Workflow] = {}

    def register(self, workflow: Workflow) -> None:
        if workflow.name in self._workflows:
            raise WorkflowError(f"Workflow already registered: {workflow.name}")
        self._workflows[workflow.name] = workflow
        logger.debug("Registered workflow: %s", workflow.name)

    def get(self, name: str) -> Workflow:
        if name not in self._workflows:
            raise WorkflowError(f"Unknown workflow: {name}")
        return self._workflows[name]

    def list_all(self) -> list[Workflow]:
        return list(self._workflows.values())


def build_workflow_registry() -> WorkflowRegistry:
    """Auto-register all built-in workflows.

    Each workflow is attempted independently; import or config errors
    cause that workflow to be silently skipped.
    """
    registry = WorkflowRegistry()

    _try_register(registry, "marketmenow.workflows.instagram_reel", "workflow")
    _try_register(registry, "marketmenow.workflows.instagram_carousel", "workflow")
    _try_register(registry, "marketmenow.workflows.twitter_thread", "workflow")
    _try_register(registry, "marketmenow.workflows.twitter_engage", "workflow")
    _try_register(registry, "marketmenow.workflows.reddit_engage", "workflow")
    _try_register(registry, "marketmenow.workflows.linkedin_post", "workflow")
    _try_register(registry, "marketmenow.workflows.email_outreach", "workflow")
    _try_register(registry, "marketmenow.workflows.youtube_short", "workflow")
    _try_register(registry, "marketmenow.workflows.reddit_launch", "workflow")
    _try_register(registry, "marketmenow.workflows.twitter_outreach", "workflow")

    _load_custom_workflows(registry)

    return registry


def _load_custom_workflows(registry: WorkflowRegistry) -> None:
    """Scan ``workflows/custom/*.yaml`` and register each as a Workflow."""
    from pathlib import Path

    import yaml

    from marketmenow.core.workflow import ParamDef, ParamType, Workflow
    from marketmenow.steps.registry import get_step_class

    custom_dir = Path(__file__).resolve().parent.parent / "workflows" / "custom"
    if not custom_dir.is_dir():
        return

    for yaml_path in sorted(custom_dir.glob("*.yaml")):
        try:
            with yaml_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            name = data.get("name", yaml_path.stem)
            description = data.get("description", "")
            step_names: list[str] = data.get("steps", [])
            param_defs_raw: list[dict[str, object]] = data.get("params", [])

            steps = []
            for sname in step_names:
                cls = get_step_class(sname)
                steps.append(cls())

            params = []
            for pdef in param_defs_raw:
                params.append(
                    ParamDef(
                        name=str(pdef.get("name", "")),
                        type=ParamType(str(pdef.get("type", "string"))),
                        required=bool(pdef.get("required", False)),
                        default=pdef.get("default"),
                        help=str(pdef.get("help", "")),
                        short=str(pdef.get("short", "")),
                    )
                )

            wf = Workflow(
                name=name,
                description=description,
                steps=tuple(steps),
                params=tuple(params),
            )
            registry.register(wf)
            logger.debug("Registered custom workflow: %s (from %s)", name, yaml_path.name)
        except Exception as exc:
            logger.debug("Skipping custom workflow %s: %s", yaml_path.name, exc)


def _try_register(
    registry: WorkflowRegistry,
    module_path: str,
    attr_name: str,
) -> None:
    """Import *module_path*, grab the ``attr_name`` attribute, and register it."""
    import importlib

    try:
        mod = importlib.import_module(module_path)
        workflow = getattr(mod, attr_name)
        registry.register(workflow)
    except Exception as exc:
        logger.debug("Skipping workflow from %s: %s", module_path, exc)
