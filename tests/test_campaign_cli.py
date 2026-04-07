from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from marketmenow.cli import app

runner = CliRunner()


class TestCampaignCLI:
    def test_campaign_list_no_project(self) -> None:
        """'mmn campaign list' with no active project should print error and exit 1."""
        with patch("marketmenow.core.campaign_cli.ProjectManager") as MockPM:
            instance = MockPM.return_value
            instance.get_active_project.return_value = None

            result = runner.invoke(app, ["campaign", "list"])

        assert result.exit_code != 0

    def test_campaign_help(self) -> None:
        """'mmn campaign --help' should succeed."""
        result = runner.invoke(app, ["campaign", "--help"])
        assert result.exit_code == 0
        assert "campaign" in result.output.lower()

    def test_campaign_info_not_found(self) -> None:
        """'mmn campaign info nonexistent' with no matching campaign should exit with error."""
        with patch("marketmenow.core.campaign_cli.ProjectManager") as MockPM:
            pm_instance = MockPM.return_value
            pm_instance.get_active_project.return_value = "testproj"

            with patch("marketmenow.core.campaign_cli.CampaignManager") as MockCM:
                cm_instance = MockCM.return_value
                cm_instance.load_plan.side_effect = FileNotFoundError("not found")

                result = runner.invoke(app, ["campaign", "info", "nonexistent"])

        assert result.exit_code != 0
