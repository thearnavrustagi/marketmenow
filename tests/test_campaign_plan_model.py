from __future__ import annotations

from datetime import date

import pytest
import yaml
from pydantic import ValidationError

from marketmenow.models.campaign_plan import (
    CampaignGoal,
    CampaignPlan,
    ContentCalendarItem,
)


def _make_goal(**overrides: object) -> CampaignGoal:
    defaults: dict[str, object] = {
        "objective": "Launch product awareness",
        "kpi": "10k impressions",
        "duration_days": 14,
    }
    return CampaignGoal(**(defaults | overrides))


def _make_item(**overrides: object) -> ContentCalendarItem:
    defaults: dict[str, object] = {
        "id": "day1-reel",
        "date": date(2026, 4, 10),
        "platform": "instagram",
        "workflow": "instagram-reel",
        "content_type": "reel",
        "topic": "Product intro",
        "brief": "Introduce the product with a hook",
    }
    return ContentCalendarItem(**(defaults | overrides))


def _make_plan(**overrides: object) -> CampaignPlan:
    defaults: dict[str, object] = {
        "name": "spring-launch",
        "project_slug": "testproject",
        "goal": _make_goal(),
        "audience_summary": "Indie hackers aged 25-35",
        "tone": "casual, witty",
        "platforms": ["instagram", "twitter"],
        "calendar": [_make_item()],
    }
    return CampaignPlan(**(defaults | overrides))


class TestCampaignPlanModel:
    def test_round_trip_yaml(self) -> None:
        """CampaignPlan can be dumped to YAML and loaded back identically."""
        plan = _make_plan()
        dumped = yaml.dump(plan.model_dump(mode="json"), default_flow_style=False)
        loaded = CampaignPlan(**yaml.safe_load(dumped))

        assert loaded.name == plan.name
        assert loaded.project_slug == plan.project_slug
        assert loaded.goal.objective == plan.goal.objective
        assert loaded.goal.kpi == plan.goal.kpi
        assert loaded.goal.duration_days == plan.goal.duration_days
        assert loaded.audience_summary == plan.audience_summary
        assert loaded.tone == plan.tone
        assert loaded.platforms == plan.platforms
        assert len(loaded.calendar) == len(plan.calendar)
        assert loaded.calendar[0].id == plan.calendar[0].id
        assert loaded.calendar[0].topic == plan.calendar[0].topic

    def test_frozen_model(self) -> None:
        """CampaignPlan is frozen; direct attribute assignment raises ValidationError."""
        plan = _make_plan()
        with pytest.raises(ValidationError):
            plan.name = "new-name"  # type: ignore[misc]

    def test_calendar_item_defaults(self) -> None:
        """ContentCalendarItem defaults: status='pending', capsule_id=''."""
        item = _make_item()
        assert item.status == "pending"
        assert item.capsule_id == ""

    def test_minimum_fields(self) -> None:
        """CampaignPlan can be created with only required fields."""
        plan = CampaignPlan(
            name="minimal",
            project_slug="proj",
            goal=_make_goal(),
            audience_summary="everyone",
            tone="neutral",
            platforms=["twitter"],
            calendar=[],
        )
        assert plan.name == "minimal"
        assert plan.repurpose_chains == []
        assert plan.created_at  # auto-populated
