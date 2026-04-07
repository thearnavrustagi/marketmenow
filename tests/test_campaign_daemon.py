from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from marketmenow.core.campaign_daemon import CampaignDaemon
from marketmenow.core.workflow import StepOutcome, Workflow, WorkflowResult
from marketmenow.core.workflow_registry import WorkflowRegistry
from marketmenow.models.campaign_plan import (
    CampaignGoal,
    CampaignPlan,
    ContentCalendarItem,
)


def _make_item(
    item_id: str = "item-1",
    item_date: date = date(2026, 4, 6),
    status: str = "pending",
    workflow: str = "twitter-thread",
) -> ContentCalendarItem:
    return ContentCalendarItem(
        id=item_id,
        date=item_date,
        platform="twitter",
        workflow=workflow,
        content_type="thread",
        topic="Test topic",
        brief="Test brief",
        status=status,
    )


def _make_plan(items: list[ContentCalendarItem] | None = None) -> CampaignPlan:
    return CampaignPlan(
        name="test-campaign",
        project_slug="testproj",
        goal=CampaignGoal(objective="Test", kpi="1k", duration_days=7),
        audience_summary="Devs",
        tone="casual",
        platforms=["twitter"],
        calendar=items or [_make_item()],
    )


class TestCampaignDaemon:
    def test_find_due_items(self) -> None:
        """_find_due_items returns only items dated today or earlier with pending status."""
        today = date.today()
        items = [
            _make_item(item_id="past", item_date=date(2020, 1, 1), status="pending"),
            _make_item(item_id="today", item_date=today, status="pending"),
            _make_item(item_id="future", item_date=date(2030, 12, 31), status="pending"),
            _make_item(item_id="done", item_date=today, status="published"),
        ]
        plan = _make_plan(items)

        registry = WorkflowRegistry()
        mgr_mock = MagicMock()
        pm_mock = MagicMock()

        daemon = CampaignDaemon(
            plan=plan,
            workflow_registry=registry,
            campaign_manager=mgr_mock,
            project_manager=pm_mock,
        )

        due = daemon._find_due_items()
        due_ids = {item.id for item in due}

        assert "past" in due_ids
        assert "today" in due_ids
        assert "future" not in due_ids
        assert "done" not in due_ids

    async def test_execute_item_success(self) -> None:
        """Successful workflow execution sets item status to 'published'."""
        plan = _make_plan()
        item = plan.calendar[0]

        mock_workflow = MagicMock(spec=Workflow)
        mock_workflow.run = AsyncMock(
            return_value=WorkflowResult(
                workflow_name="twitter-thread",
                outcomes=[StepOutcome(step_name="generate", success=True)],
            )
        )

        registry = WorkflowRegistry()
        registry._workflows["twitter-thread"] = mock_workflow

        mgr_mock = MagicMock()
        pm_mock = MagicMock()
        pm_mock.load_project.return_value = MagicMock(default_persona=None)

        daemon = CampaignDaemon(
            plan=plan,
            workflow_registry=registry,
            campaign_manager=mgr_mock,
            project_manager=pm_mock,
        )

        await daemon._execute_item(item)

        mgr_mock.update_item_status.assert_called_once_with(
            "testproj",
            "test-campaign",
            "item-1",
            "published",
            capsule_id="",
        )

    async def test_execute_item_workflow_not_found(self) -> None:
        """Non-existent workflow results in 'failed' status.

        We mock the registry's get() to return None (matching the daemon's
        None-check branch) since the real get() raises WorkflowError.
        """
        items = [_make_item(workflow="nonexistent-workflow")]
        plan = _make_plan(items)
        item = plan.calendar[0]

        registry_mock = MagicMock(spec=WorkflowRegistry)
        registry_mock.get.return_value = None

        mgr_mock = MagicMock()
        pm_mock = MagicMock()

        daemon = CampaignDaemon(
            plan=plan,
            workflow_registry=registry_mock,
            campaign_manager=mgr_mock,
            project_manager=pm_mock,
        )

        await daemon._execute_item(item)

        mgr_mock.update_item_status.assert_called_once_with(
            "testproj",
            "test-campaign",
            "item-1",
            "failed",
        )

    async def test_stop_event(self) -> None:
        """Setting _stop_event causes the daemon loop to exit."""
        plan = _make_plan()

        registry = WorkflowRegistry()
        mgr_mock = MagicMock()
        mgr_mock.load_plan.return_value = plan
        pm_mock = MagicMock()

        daemon = CampaignDaemon(
            plan=plan,
            workflow_registry=registry,
            campaign_manager=mgr_mock,
            project_manager=pm_mock,
            poll_interval=0.01,
        )

        # Pre-set the stop event so the loop exits immediately
        daemon._stop_event.set()

        # Patch _write_daemon_state to avoid filesystem access
        with patch.object(daemon, "_write_daemon_state"):
            await daemon.run()

        # If we reach here, the loop exited correctly

    def test_status_report(self) -> None:
        """generate_status_report includes counts for each status."""
        items = [
            _make_item(item_id="a", status="published"),
            _make_item(item_id="b", status="published"),
            _make_item(item_id="c", status="failed"),
            _make_item(item_id="d", status="pending"),
        ]
        plan = _make_plan(items)

        registry = WorkflowRegistry()
        mgr_mock = MagicMock()
        pm_mock = MagicMock()

        daemon = CampaignDaemon(
            plan=plan,
            workflow_registry=registry,
            campaign_manager=mgr_mock,
            project_manager=pm_mock,
        )

        report = daemon.generate_status_report()

        assert "test-campaign" in report
        assert "2/4 published" in report
        assert "1 failed" in report
        assert "1 pending" in report
