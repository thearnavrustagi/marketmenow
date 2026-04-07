from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from marketmenow.core.campaign_manager import CampaignManager
from marketmenow.core.project_manager import ProjectManager
from marketmenow.models.campaign_plan import (
    CampaignGoal,
    CampaignPlan,
    ContentCalendarItem,
)


def _make_plan(name: str = "test-campaign", slug: str = "testproj") -> CampaignPlan:
    return CampaignPlan(
        name=name,
        project_slug=slug,
        goal=CampaignGoal(objective="Launch", kpi="1k views", duration_days=7),
        audience_summary="Developers",
        tone="technical",
        platforms=["twitter"],
        calendar=[
            ContentCalendarItem(
                id="item-1",
                date=date(2026, 4, 10),
                platform="twitter",
                workflow="twitter-thread",
                content_type="thread",
                topic="Intro thread",
                brief="Introduce the product",
            ),
            ContentCalendarItem(
                id="item-2",
                date=date(2026, 4, 12),
                platform="twitter",
                workflow="twitter-thread",
                content_type="thread",
                topic="Deep dive",
                brief="Technical deep dive",
            ),
        ],
    )


class TestCampaignManager:
    def test_save_and_load_plan(self, tmp_path: Path) -> None:
        """save_plan persists to YAML; load_plan reads it back correctly."""
        pm = ProjectManager(projects_root=tmp_path)
        mgr = CampaignManager(project_manager=pm)

        plan = _make_plan(slug="myproj")
        # Ensure the project directory exists
        (tmp_path / "myproj").mkdir(parents=True, exist_ok=True)

        mgr.save_plan(plan)
        loaded = mgr.load_plan("myproj", "test-campaign")

        assert loaded.name == plan.name
        assert loaded.project_slug == plan.project_slug
        assert loaded.goal.objective == plan.goal.objective
        assert len(loaded.calendar) == 2
        assert loaded.calendar[0].id == "item-1"
        assert loaded.calendar[1].topic == "Deep dive"

    def test_list_campaigns(self, tmp_path: Path) -> None:
        """list_campaigns returns all saved campaigns for a project."""
        pm = ProjectManager(projects_root=tmp_path)
        mgr = CampaignManager(project_manager=pm)

        (tmp_path / "proj").mkdir(parents=True, exist_ok=True)

        plan_a = _make_plan(name="alpha", slug="proj")
        plan_b = _make_plan(name="beta", slug="proj")
        mgr.save_plan(plan_a)
        mgr.save_plan(plan_b)

        campaigns = mgr.list_campaigns("proj")
        names = {c.name for c in campaigns}
        assert names == {"alpha", "beta"}

    def test_list_campaigns_empty(self, tmp_path: Path) -> None:
        """Empty project directory returns empty list."""
        pm = ProjectManager(projects_root=tmp_path)
        mgr = CampaignManager(project_manager=pm)

        result = mgr.list_campaigns("nonexistent")
        assert result == []

    def test_update_item_status(self, tmp_path: Path) -> None:
        """update_item_status changes a calendar item's status and persists it."""
        pm = ProjectManager(projects_root=tmp_path)
        mgr = CampaignManager(project_manager=pm)

        (tmp_path / "proj").mkdir(parents=True, exist_ok=True)

        plan = _make_plan(slug="proj")
        mgr.save_plan(plan)

        mgr.update_item_status("proj", "test-campaign", "item-1", "published")

        reloaded = mgr.load_plan("proj", "test-campaign")
        item1 = next(i for i in reloaded.calendar if i.id == "item-1")
        item2 = next(i for i in reloaded.calendar if i.id == "item-2")

        assert item1.status == "published"
        assert item2.status == "pending"  # unchanged

    def test_update_item_not_found(self, tmp_path: Path) -> None:
        """Updating a non-existent item raises ValueError."""
        pm = ProjectManager(projects_root=tmp_path)
        mgr = CampaignManager(project_manager=pm)

        (tmp_path / "proj").mkdir(parents=True, exist_ok=True)

        plan = _make_plan(slug="proj")
        mgr.save_plan(plan)

        with pytest.raises(ValueError, match="not found"):
            mgr.update_item_status("proj", "test-campaign", "nonexistent-item", "published")
