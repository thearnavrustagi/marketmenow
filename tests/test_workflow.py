from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from marketmenow.core.workflow import (
    ParamDef,
    ParamType,
    Workflow,
    WorkflowContext,
    WorkflowError,
    WorkflowStep,
)

# ---------------------------------------------------------------------------
# Mock steps for testing
# ---------------------------------------------------------------------------


class SuccessStep:
    """Step that writes an artifact to context."""

    def __init__(self, artifact_key: str = "out", artifact_value: str = "done") -> None:
        self._key = artifact_key
        self._value = artifact_value

    @property
    def name(self) -> str:
        return "success-step"

    @property
    def description(self) -> str:
        return "Always succeeds"

    async def execute(self, ctx: WorkflowContext) -> None:
        ctx.set_artifact(self._key, self._value)


class ParamEchoStep:
    """Step that reads a param and writes it as an artifact."""

    def __init__(self, param_name: str) -> None:
        self._param = param_name

    @property
    def name(self) -> str:
        return "echo-step"

    @property
    def description(self) -> str:
        return "Echoes a param"

    async def execute(self, ctx: WorkflowContext) -> None:
        val = ctx.require_param(self._param)
        ctx.set_artifact("echoed", val)


class FailingStep:
    """Step that always raises."""

    @property
    def name(self) -> str:
        return "fail-step"

    @property
    def description(self) -> str:
        return "Always fails"

    async def execute(self, ctx: WorkflowContext) -> None:
        raise WorkflowError("intentional failure")


class ArtifactReaderStep:
    """Step that reads an artifact produced by a previous step."""

    def __init__(self, read_key: str, write_key: str) -> None:
        self._read = read_key
        self._write = write_key

    @property
    def name(self) -> str:
        return "reader-step"

    @property
    def description(self) -> str:
        return "Reads an artifact"

    async def execute(self, ctx: WorkflowContext) -> None:
        val = ctx.get_artifact(self._read)
        ctx.set_artifact(self._write, f"read:{val}")


# ---------------------------------------------------------------------------
# WorkflowContext
# ---------------------------------------------------------------------------


class TestWorkflowContext:
    def test_params_stored(self) -> None:
        ctx = WorkflowContext({"key": "val"})
        assert ctx.get_param("key") == "val"

    def test_get_param_default(self) -> None:
        ctx = WorkflowContext({})
        assert ctx.get_param("missing", "fallback") == "fallback"

    def test_require_param_present(self) -> None:
        ctx = WorkflowContext({"x": 42})
        assert ctx.require_param("x") == 42

    def test_require_param_missing_raises(self) -> None:
        ctx = WorkflowContext({})
        with pytest.raises(WorkflowError, match="Required parameter missing"):
            ctx.require_param("nope")

    def test_set_and_get_artifact(self) -> None:
        ctx = WorkflowContext({})
        ctx.set_artifact("content", {"type": "video"})
        assert ctx.get_artifact("content") == {"type": "video"}

    def test_get_artifact_missing_raises(self) -> None:
        ctx = WorkflowContext({})
        with pytest.raises(WorkflowError, match="Expected artifact missing"):
            ctx.get_artifact("nonexistent")

    def test_artifact_overwrite(self) -> None:
        ctx = WorkflowContext({})
        ctx.set_artifact("key", "first")
        ctx.set_artifact("key", "second")
        assert ctx.get_artifact("key") == "second"

    def test_console_default(self) -> None:
        ctx = WorkflowContext({})
        assert isinstance(ctx.console, Console)

    def test_console_injected(self) -> None:
        con = Console(quiet=True)
        ctx = WorkflowContext({}, console=con)
        assert ctx.console is con


# ---------------------------------------------------------------------------
# WorkflowStep protocol
# ---------------------------------------------------------------------------


class TestWorkflowStepProtocol:
    def test_success_step_satisfies_protocol(self) -> None:
        step = SuccessStep()
        assert isinstance(step, WorkflowStep)

    def test_failing_step_satisfies_protocol(self) -> None:
        step = FailingStep()
        assert isinstance(step, WorkflowStep)


# ---------------------------------------------------------------------------
# Workflow.run
# ---------------------------------------------------------------------------


class TestWorkflowRun:
    async def test_single_step_success(self) -> None:
        wf = Workflow(
            name="test",
            description="test workflow",
            steps=(SuccessStep(),),
        )
        result = await wf.run({}, console=Console(quiet=True))
        assert result.success is True
        assert result.workflow_name == "test"
        assert len(result.outcomes) == 1
        assert result.outcomes[0].step_name == "success-step"
        assert result.outcomes[0].success is True

    async def test_multi_step_pipeline(self) -> None:
        wf = Workflow(
            name="pipe",
            description="multi-step",
            steps=(
                SuccessStep(artifact_key="stage1", artifact_value="data"),
                ArtifactReaderStep(read_key="stage1", write_key="stage2"),
            ),
        )
        result = await wf.run({}, console=Console(quiet=True))
        assert result.success is True
        assert len(result.outcomes) == 2

    async def test_step_failure_stops_pipeline(self) -> None:
        wf = Workflow(
            name="fail-pipe",
            description="fails mid-way",
            steps=(
                SuccessStep(),
                FailingStep(),
                SuccessStep(artifact_key="should_not_run"),
            ),
        )
        result = await wf.run({}, console=Console(quiet=True))
        assert result.success is False
        assert len(result.outcomes) == 2
        assert result.outcomes[0].success is True
        assert result.outcomes[1].success is False
        assert "intentional failure" in result.outcomes[1].error

    async def test_params_passed_to_steps(self) -> None:
        wf = Workflow(
            name="echo",
            description="echoes param",
            steps=(ParamEchoStep("topic"),),
        )
        result = await wf.run({"topic": "AI marketing"}, console=Console(quiet=True))
        assert result.success is True

    async def test_missing_required_param_in_step_fails(self) -> None:
        wf = Workflow(
            name="missing",
            description="missing param",
            steps=(ParamEchoStep("does_not_exist"),),
        )
        result = await wf.run({}, console=Console(quiet=True))
        assert result.success is False
        assert "Required parameter missing" in result.outcomes[0].error

    async def test_empty_workflow_succeeds(self) -> None:
        wf = Workflow(name="empty", description="no steps", steps=())
        result = await wf.run({}, console=Console(quiet=True))
        assert result.success is True
        assert len(result.outcomes) == 0


# ---------------------------------------------------------------------------
# ParamDef
# ---------------------------------------------------------------------------


class TestParamDef:
    def test_defaults(self) -> None:
        p = ParamDef(name="topic")
        assert p.type == ParamType.STRING
        assert p.required is False
        assert p.default is None
        assert p.help == ""
        assert p.short == ""

    def test_full_definition(self) -> None:
        p = ParamDef(
            name="count",
            type=ParamType.INT,
            required=True,
            default=5,
            help="Number of posts",
            short="-n",
        )
        assert p.name == "count"
        assert p.type == ParamType.INT
        assert p.required is True
        assert p.default == 5
        assert p.short == "-n"

    def test_all_param_types_exist(self) -> None:
        expected = {"string", "path", "int", "float", "bool"}
        actual = {t.value for t in ParamType}
        assert actual == expected


# ---------------------------------------------------------------------------
# Workflow frozen dataclass
# ---------------------------------------------------------------------------


class TestWorkflowDataclass:
    def test_workflow_is_frozen(self) -> None:
        wf = Workflow(name="x", description="y", steps=())
        with pytest.raises(AttributeError):
            wf.name = "changed"  # type: ignore[misc]

    def test_workflow_params_schema(self) -> None:
        wf = Workflow(
            name="x",
            description="y",
            steps=(),
            params=(
                ParamDef(name="a", type=ParamType.STRING),
                ParamDef(name="b", type=ParamType.INT, required=True),
            ),
        )
        assert len(wf.params) == 2
        assert wf.params[0].name == "a"
        assert wf.params[1].required is True


# ---------------------------------------------------------------------------
# Project integration
# ---------------------------------------------------------------------------


class TestWorkflowContextProject:
    def test_context_with_project(self) -> None:
        from marketmenow.models.project import BrandConfig, PersonaConfig, ProjectConfig

        proj = ProjectConfig(
            slug="test",
            brand=BrandConfig(name="T", url="t.io", tagline="t"),
        )
        persona = PersonaConfig(name="default")
        ctx = WorkflowContext({"key": "val"}, project=proj, persona=persona)
        assert ctx.project is not None
        assert ctx.project.slug == "test"
        assert ctx.persona is not None

    def test_context_without_project(self) -> None:
        ctx = WorkflowContext({"key": "val"})
        assert ctx.project is None
        assert ctx.persona is None

    def test_resolve_project_path_with_fallback_no_project(self, tmp_path: Path) -> None:
        fallback = tmp_path / "global"
        fallback.mkdir()
        (fallback / "file.txt").write_text("global")
        ctx = WorkflowContext({})
        resolved = ctx.resolve_project_path("prompts", "file.txt", fallback=fallback)
        assert resolved == fallback / "file.txt"

    def test_resolve_project_path_no_project_no_fallback_raises(self) -> None:
        ctx = WorkflowContext({})
        with pytest.raises(WorkflowError):
            ctx.resolve_project_path("prompts", "file.txt")


class TestWorkflowRunWithProject:
    async def test_run_passes_project_to_context(self) -> None:
        from marketmenow.models.project import BrandConfig, PersonaConfig, ProjectConfig

        proj = ProjectConfig(
            slug="test",
            brand=BrandConfig(name="T", url="t.io", tagline="t"),
        )
        persona = PersonaConfig(name="default")

        captured: list[WorkflowContext] = []

        class CaptureStep:
            @property
            def name(self) -> str:
                return "capture"

            @property
            def description(self) -> str:
                return "capture ctx"

            async def execute(self, ctx: WorkflowContext) -> None:
                captured.append(ctx)

        wf = Workflow(name="test", description="test", steps=(CaptureStep(),))
        await wf.run({}, project=proj, persona=persona)
        assert len(captured) == 1
        assert captured[0].project is not None
        assert captured[0].project.slug == "test"
        assert captured[0].persona is not None

    async def test_run_without_project(self) -> None:
        class NoopStep:
            @property
            def name(self) -> str:
                return "noop"

            @property
            def description(self) -> str:
                return "noop"

            async def execute(self, ctx: WorkflowContext) -> None:
                pass

        wf = Workflow(name="test", description="test", steps=(NoopStep(),))
        result = await wf.run({})
        assert result.success
