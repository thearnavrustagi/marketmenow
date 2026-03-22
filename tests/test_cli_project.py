from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from marketmenow.cli import app
from marketmenow.core.project_manager import ProjectManager
from marketmenow.models.project import BrandConfig

runner = CliRunner()

_BRAND = BrandConfig(name="TestApp", url="testapp.io", tagline="A test app")


def _seed_project(tmp_path, slug: str = "testapp") -> ProjectManager:
    """Create a ProjectManager rooted at tmp_path/projects with one project."""
    pm = ProjectManager(tmp_path / "projects")
    pm.create_project(slug, _BRAND)
    return pm


class TestProjectAdd:
    @patch("marketmenow.core.onboarding.run_onboarding")
    def test_add_calls_onboarding(self, mock_onboarding, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_onboarding.return_value = MagicMock()
        runner.invoke(app, ["project", "add", "myslug"])
        mock_onboarding.assert_called_once()
        _, kwargs = mock_onboarding.call_args
        assert kwargs["slug_override"] == "myslug"

    def test_add_help(self):
        result = runner.invoke(app, ["project", "add", "--help"])
        assert result.exit_code == 0
        assert "slug" in result.output.lower()


class TestProjectList:
    def test_list_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["project", "list"])
        assert result.exit_code == 0
        assert "No projects" in result.output

    def test_list_shows_projects(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _seed_project(tmp_path)
        result = runner.invoke(app, ["project", "list"])
        assert result.exit_code == 0
        assert "testapp" in result.output

    def test_list_shows_active_marker(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pm = _seed_project(tmp_path)
        pm.set_active_project("testapp")
        result = runner.invoke(app, ["project", "list"])
        assert result.exit_code == 0
        assert "►" in result.output


class TestProjectUse:
    def test_use_sets_active(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _seed_project(tmp_path)
        result = runner.invoke(app, ["project", "use", "testapp"])
        assert result.exit_code == 0
        assert "testapp" in result.output
        pm = ProjectManager(tmp_path / "projects")
        assert pm.get_active_project() == "testapp"

    def test_use_invalid_slug(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["project", "use", "nope"])
        assert result.exit_code == 1


class TestProjectInfo:
    def test_info_shows_brand(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pm = _seed_project(tmp_path)
        pm.set_active_project("testapp")
        result = runner.invoke(app, ["project", "info"])
        assert result.exit_code == 0
        assert "TestApp" in result.output

    def test_info_specific_slug(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _seed_project(tmp_path)
        result = runner.invoke(app, ["project", "info", "testapp"])
        assert result.exit_code == 0
        assert "TestApp" in result.output

    def test_info_no_active_errors(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["project", "info"])
        assert result.exit_code == 1


class TestProjectPersona:
    def test_persona_add(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pm = _seed_project(tmp_path)
        pm.set_active_project("testapp")
        result = runner.invoke(
            app,
            ["project", "persona", "add", "edgy"],
            input="Sarcastic bot\nEdgy voice\nCasual tone\n",
        )
        assert result.exit_code == 0
        assert "edgy" in ProjectManager(tmp_path / "projects").list_personas("testapp")

    def test_persona_add_no_active_errors(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["project", "persona", "add", "edgy"],
            input="desc\nvoice\ntone\n",
        )
        assert result.exit_code == 1

    def test_persona_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pm = _seed_project(tmp_path)
        pm.set_active_project("testapp")
        result = runner.invoke(app, ["project", "persona", "list"])
        assert result.exit_code == 0
        assert "default" in result.output

    def test_persona_list_no_active_errors(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["project", "persona", "list"])
        assert result.exit_code == 1


class TestProjectHelp:
    def test_project_help(self):
        result = runner.invoke(app, ["project", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "list" in result.output
        assert "use" in result.output
        assert "info" in result.output
        assert "persona" in result.output
