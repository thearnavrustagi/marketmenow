from __future__ import annotations

import pytest

from marketmenow.core.workflow import Workflow, WorkflowError
from marketmenow.core.workflow_registry import WorkflowRegistry, build_workflow_registry


def _make_workflow(name: str) -> Workflow:
    return Workflow(name=name, description=f"test {name}", steps=())


# ---------------------------------------------------------------------------
# WorkflowRegistry
# ---------------------------------------------------------------------------


class TestWorkflowRegistry:
    def test_register_and_get(self) -> None:
        reg = WorkflowRegistry()
        wf = _make_workflow("alpha")
        reg.register(wf)
        assert reg.get("alpha") is wf

    def test_get_unknown_raises(self) -> None:
        reg = WorkflowRegistry()
        with pytest.raises(WorkflowError, match="Unknown workflow"):
            reg.get("nonexistent")

    def test_duplicate_register_raises(self) -> None:
        reg = WorkflowRegistry()
        reg.register(_make_workflow("dup"))
        with pytest.raises(WorkflowError, match="already registered"):
            reg.register(_make_workflow("dup"))

    def test_list_all_empty(self) -> None:
        reg = WorkflowRegistry()
        assert reg.list_all() == []

    def test_list_all_returns_all(self) -> None:
        reg = WorkflowRegistry()
        for name in ("a", "b", "c"):
            reg.register(_make_workflow(name))
        names = {w.name for w in reg.list_all()}
        assert names == {"a", "b", "c"}

    def test_list_all_preserves_order(self) -> None:
        reg = WorkflowRegistry()
        for name in ("first", "second", "third"):
            reg.register(_make_workflow(name))
        names = [w.name for w in reg.list_all()]
        assert names == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# build_workflow_registry
# ---------------------------------------------------------------------------


class TestBuildWorkflowRegistry:
    def test_returns_registry(self) -> None:
        reg = build_workflow_registry()
        assert isinstance(reg, WorkflowRegistry)

    def test_built_in_workflows_registered(self) -> None:
        reg = build_workflow_registry()
        workflows = reg.list_all()
        names = {w.name for w in workflows}
        expected = {
            "instagram-reel",
            "instagram-carousel",
            "twitter-thread",
            "twitter-engage",
            "twitter-outreach",
            "reddit-engage",
            "reddit-launch",
            "linkedin-post",
            "email-outreach",
            "youtube-short",
        }
        assert expected == names

    def test_each_workflow_has_steps(self) -> None:
        reg = build_workflow_registry()
        for wf in reg.list_all():
            assert len(wf.steps) >= 1, f"{wf.name} has no steps"

    def test_each_workflow_has_description(self) -> None:
        reg = build_workflow_registry()
        for wf in reg.list_all():
            assert wf.description, f"{wf.name} has no description"

    def test_workflow_names_are_kebab_case(self) -> None:
        reg = build_workflow_registry()
        for wf in reg.list_all():
            assert "_" not in wf.name, f"{wf.name} should use kebab-case"
            assert wf.name == wf.name.lower(), f"{wf.name} should be lowercase"

    def test_instagram_reel_has_template_param(self) -> None:
        reg = build_workflow_registry()
        wf = reg.get("instagram-reel")
        param_names = {p.name for p in wf.params}
        assert "template" in param_names

    def test_twitter_thread_has_topic_param(self) -> None:
        reg = build_workflow_registry()
        wf = reg.get("twitter-thread")
        param_names = {p.name for p in wf.params}
        assert "topic" in param_names

    def test_email_outreach_template_is_required(self) -> None:
        reg = build_workflow_registry()
        wf = reg.get("email-outreach")
        template_params = [p for p in wf.params if p.name == "template"]
        assert len(template_params) == 1
        assert template_params[0].required is True

    def test_reddit_launch_has_config_and_brief_params(self) -> None:
        reg = build_workflow_registry()
        wf = reg.get("reddit-launch")
        param_names = {p.name for p in wf.params}
        assert "config" in param_names
        assert "brief" in param_names
        assert "product_name" in param_names

    def test_reddit_launch_has_two_steps(self) -> None:
        reg = build_workflow_registry()
        wf = reg.get("reddit-launch")
        assert len(wf.steps) == 2
        assert wf.steps[0].name == "generate-reddit-posts"
        assert wf.steps[1].name == "post-to-subreddits"
