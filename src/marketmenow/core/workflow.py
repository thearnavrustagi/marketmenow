from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from rich.console import Console

if TYPE_CHECKING:
    from marketmenow.models.project import PersonaConfig, ProjectConfig

logger = logging.getLogger(__name__)


class ParamType(str, enum.Enum):
    STRING = "string"
    PATH = "path"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"


@dataclass(frozen=True)
class ParamDef:
    """Declares a workflow parameter that maps to a CLI option."""

    name: str
    type: ParamType = ParamType.STRING
    required: bool = False
    default: str | int | float | bool | None = None
    help: str = ""
    short: str = ""


class WorkflowContext:
    """Mutable state bag passed between workflow steps.

    ``params`` holds user-provided CLI arguments.
    ``artifacts`` holds data produced by earlier steps (e.g. generated content).
    ``console`` is the shared Rich console for output.
    """

    def __init__(
        self,
        params: dict[str, str | int | float | bool],
        *,
        console: Console | None = None,
        project: ProjectConfig | None = None,
        persona: PersonaConfig | None = None,
    ) -> None:
        self.params: dict[str, str | int | float | bool] = dict(params)
        self.artifacts: dict[str, object] = {}
        self.console: Console = console or Console()
        self.project: ProjectConfig | None = project
        self.persona: PersonaConfig | None = persona

    def get_param(
        self, key: str, default: str | int | float | bool | None = None
    ) -> str | int | float | bool | None:
        return self.params.get(key, default)

    def require_param(self, key: str) -> str | int | float | bool:
        if key not in self.params:
            raise WorkflowError(f"Required parameter missing: {key}")
        return self.params[key]

    def set_artifact(self, key: str, value: object) -> None:
        self.artifacts[key] = value

    def get_artifact(self, key: str) -> object:
        if key not in self.artifacts:
            raise WorkflowError(f"Expected artifact missing: {key}")
        return self.artifacts[key]

    def resolve_project_path(
        self, category: str, *parts: str, fallback: Path | None = None
    ) -> Path:
        """Resolve a path within the active project, with optional global fallback."""
        if self.project is None:
            if fallback is not None:
                candidate = fallback / Path(*parts)
                if candidate.exists():
                    return candidate
            raise WorkflowError("No active project and no fallback path")
        from marketmenow.core.project_manager import ProjectManager

        pm = ProjectManager()
        return pm.resolve_path(self.project.slug, category, *parts, fallback=fallback)


@runtime_checkable
class WorkflowStep(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    async def execute(self, ctx: WorkflowContext) -> None: ...


class WorkflowError(Exception):
    """Raised when a workflow or step encounters an unrecoverable error."""


@dataclass
class StepOutcome:
    step_name: str
    success: bool
    error: str = ""


@dataclass
class WorkflowResult:
    workflow_name: str
    outcomes: list[StepOutcome] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return all(o.success for o in self.outcomes)


@dataclass(frozen=True)
class Workflow:
    """A named, composable marketing workflow.

    A workflow is a sequence of steps executed in order, with a shared
    ``WorkflowContext`` carrying state between them.
    """

    name: str
    description: str
    steps: tuple[WorkflowStep, ...]
    params: tuple[ParamDef, ...] = ()

    async def run(
        self,
        raw_params: dict[str, str | int | float | bool],
        *,
        console: Console | None = None,
        project: ProjectConfig | None = None,
        persona: PersonaConfig | None = None,
    ) -> WorkflowResult:
        ctx = WorkflowContext(raw_params, console=console, project=project, persona=persona)
        result = WorkflowResult(workflow_name=self.name)

        for step in self.steps:
            ctx.console.print(f"  [bold cyan]>[/bold cyan] {step.name}: {step.description}")
            try:
                await step.execute(ctx)
                result.outcomes.append(StepOutcome(step_name=step.name, success=True))
            except Exception as exc:
                logger.exception("Step '%s' failed", step.name)
                result.outcomes.append(
                    StepOutcome(step_name=step.name, success=False, error=str(exc))
                )
                ctx.console.print(f"  [red]Step '{step.name}' failed: {exc}[/red]")
                break

        return result
