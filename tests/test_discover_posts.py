from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.models.project import BrandConfig, ProjectConfig
from marketmenow.steps.discover_posts import (
    DiscoverPostsStep,
    _is_adapter_default_targets,
    _reject_default_targets,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(slug: str = "testproj") -> ProjectConfig:
    return ProjectConfig(
        slug=slug,
        brand=BrandConfig(name="Test", url="https://test.com", tagline="Testing"),
    )


# ---------------------------------------------------------------------------
# _is_adapter_default_targets
# ---------------------------------------------------------------------------


class TestIsAdapterDefaultTargets:
    def test_matches_adapter_template(self, tmp_path: Path) -> None:
        adapter_dir = tmp_path / "adapters" / "twitter"
        adapter_dir.mkdir(parents=True)
        settings_file = adapter_dir / "settings.py"
        settings_file.touch()
        targets_file = adapter_dir / "targets.yaml"
        targets_file.write_text("hashtags: ['#placeholder']")

        assert _is_adapter_default_targets(targets_file, str(settings_file)) is True

    def test_rejects_custom_path(self, tmp_path: Path) -> None:
        adapter_dir = tmp_path / "adapters" / "twitter"
        adapter_dir.mkdir(parents=True)
        settings_file = adapter_dir / "settings.py"
        settings_file.touch()

        custom = tmp_path / "projects" / "myproj" / "targets" / "twitter.yaml"
        custom.parent.mkdir(parents=True)
        custom.write_text("hashtags: ['#edtech']")

        assert _is_adapter_default_targets(custom, str(settings_file)) is False

    def test_different_directory_same_filename(self, tmp_path: Path) -> None:
        adapter_dir = tmp_path / "adapters" / "twitter"
        adapter_dir.mkdir(parents=True)
        settings_file = adapter_dir / "settings.py"
        settings_file.touch()

        other_dir = tmp_path / "other"
        other_dir.mkdir()
        other_targets = other_dir / "targets.yaml"
        other_targets.write_text("hashtags: []")

        assert _is_adapter_default_targets(other_targets, str(settings_file)) is False


# ---------------------------------------------------------------------------
# _reject_default_targets
# ---------------------------------------------------------------------------


class TestRejectDefaultTargets:
    def test_raises_on_adapter_template(self, tmp_path: Path) -> None:
        adapter_dir = tmp_path / "adapters" / "twitter"
        adapter_dir.mkdir(parents=True)
        settings_file = adapter_dir / "settings.py"
        settings_file.touch()
        targets_file = adapter_dir / "targets.yaml"
        targets_file.write_text("hashtags: ['#placeholder']")

        with pytest.raises(WorkflowError, match="default placeholder targets"):
            _reject_default_targets(targets_file, str(settings_file), "twitter", None)

    def test_error_message_includes_platform(self, tmp_path: Path) -> None:
        adapter_dir = tmp_path / "adapters" / "facebook"
        adapter_dir.mkdir(parents=True)
        settings_file = adapter_dir / "settings.py"
        settings_file.touch()
        targets_file = adapter_dir / "targets.yaml"
        targets_file.write_text("groups: []")

        with pytest.raises(WorkflowError, match="facebook"):
            _reject_default_targets(targets_file, str(settings_file), "facebook", "myproj")

    def test_error_message_includes_project_slug(self, tmp_path: Path) -> None:
        adapter_dir = tmp_path / "adapters" / "twitter"
        adapter_dir.mkdir(parents=True)
        settings_file = adapter_dir / "settings.py"
        settings_file.touch()
        targets_file = adapter_dir / "targets.yaml"
        targets_file.write_text("hashtags: []")

        with pytest.raises(WorkflowError, match=r"projects/gradeasy/targets/twitter\.yaml"):
            _reject_default_targets(targets_file, str(settings_file), "twitter", "gradeasy")

    def test_no_error_on_custom_path(self, tmp_path: Path) -> None:
        adapter_dir = tmp_path / "adapters" / "twitter"
        adapter_dir.mkdir(parents=True)
        settings_file = adapter_dir / "settings.py"
        settings_file.touch()

        custom = tmp_path / "projects" / "myproj" / "targets" / "twitter.yaml"
        custom.parent.mkdir(parents=True)
        custom.write_text("hashtags: ['#edtech']")

        _reject_default_targets(custom, str(settings_file), "twitter", "myproj")


# ---------------------------------------------------------------------------
# DiscoverPostsStep — Twitter default targets rejection
# ---------------------------------------------------------------------------


class TestDiscoverTwitterDefaultTargets:
    async def test_raises_when_no_project_and_default_targets(self) -> None:
        """No project set → settings use adapter template → WorkflowError."""
        step = DiscoverPostsStep(platform="twitter")
        ctx = WorkflowContext(params={})

        with pytest.raises(WorkflowError, match="default placeholder targets"):
            await step.execute(ctx)

    async def test_raises_when_project_has_no_targets_file(self, tmp_path: Path) -> None:
        """Project set but no targets/twitter.yaml in project dir → WorkflowError."""
        step = DiscoverPostsStep(platform="twitter")
        project = _make_project("noproj")
        ctx = WorkflowContext(params={}, project=project)

        with pytest.raises(WorkflowError, match="default placeholder targets"):
            await step.execute(ctx)

    async def test_passes_with_project_targets(self, tmp_path: Path) -> None:
        """Project has a targets file → should NOT raise the default-targets error.

        We still mock the orchestrator to avoid browser/network calls.
        """
        step = DiscoverPostsStep(platform="twitter")

        project_dir = Path("projects/_test_discover_targets")
        targets_file = project_dir / "targets" / "twitter.yaml"
        targets_file.parent.mkdir(parents=True, exist_ok=True)
        targets_file.write_text("influencers:\n  - '@edtech_guru'\nhashtags:\n  - '#edtech'\n")

        project = _make_project("_test_discover_targets")
        ctx = WorkflowContext(params={}, project=project)

        try:
            mock_orch = AsyncMock()
            mock_orch.discover_only = AsyncMock(return_value=[])

            with (
                patch(
                    "adapters.twitter.orchestrator.EngagementOrchestrator",
                    return_value=mock_orch,
                ),
                pytest.raises(WorkflowError, match="No posts discovered"),
            ):
                await step.execute(ctx)
        finally:
            targets_file.unlink(missing_ok=True)
            targets_file.parent.rmdir()
            project_dir.rmdir()


# ---------------------------------------------------------------------------
# DiscoverPostsStep — Facebook default targets rejection
# ---------------------------------------------------------------------------


class TestDiscoverFacebookDefaultTargets:
    async def test_raises_when_no_project_and_default_targets(self) -> None:
        """No project set → settings use adapter template → WorkflowError."""
        step = DiscoverPostsStep(platform="facebook")
        ctx = WorkflowContext(params={})

        with pytest.raises(WorkflowError, match="default placeholder targets"):
            await step.execute(ctx)

    async def test_raises_when_project_has_no_targets_file(self) -> None:
        """Project set but no targets/facebook.yaml → WorkflowError."""
        step = DiscoverPostsStep(platform="facebook")
        project = _make_project("noproj_fb")
        ctx = WorkflowContext(params={}, project=project)

        with pytest.raises(WorkflowError, match="default placeholder targets"):
            await step.execute(ctx)


# ---------------------------------------------------------------------------
# DiscoverPostsStep — basic construction
# ---------------------------------------------------------------------------


class TestDiscoverPostsStepConstruction:
    def test_accepts_twitter(self) -> None:
        step = DiscoverPostsStep(platform="twitter")
        assert step.name == "discover-twitter"

    def test_accepts_reddit(self) -> None:
        step = DiscoverPostsStep(platform="reddit")
        assert step.name == "discover-reddit"

    def test_accepts_facebook(self) -> None:
        step = DiscoverPostsStep(platform="facebook")
        assert step.name == "discover-facebook"

    def test_rejects_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            DiscoverPostsStep(platform="myspace")
