from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from conftest import MockLLMProvider
from marketmenow.core.campaign_planner import CampaignPlanner
from marketmenow.core.workflow_registry import WorkflowRegistry
from marketmenow.models.project import BrandConfig, ProjectConfig, TargetCustomer


def _make_project() -> ProjectConfig:
    return ProjectConfig(
        slug="testproj",
        brand=BrandConfig(
            name="TestBrand",
            url="https://testbrand.com",
            tagline="The best test brand",
        ),
        target_customer=TargetCustomer(
            description="Indie developers who ship fast",
        ),
    )


_PLAN_JSON = json.dumps(
    {
        "name": "spring-launch",
        "goal": {"objective": "Grow awareness", "kpi": "5k impressions", "duration_days": 7},
        "audience_summary": "Indie devs 25-35",
        "tone": "casual",
        "platforms": ["twitter"],
        "calendar": [
            {
                "id": "d1-thread",
                "date": str(date(2026, 4, 10)),
                "platform": "twitter",
                "workflow": "twitter-thread",
                "content_type": "thread",
                "topic": "Launch announcement",
                "brief": "Announce the product launch",
                "cta": "Try it free",
            },
        ],
        "repurpose_chains": [],
    }
)


class TestCampaignPlanner:
    @patch("marketmenow.core.campaign_planner.build_workflow_registry")
    async def test_planner_loads_project_context(
        self,
        mock_build_registry: MagicMock,
    ) -> None:
        """Planner calls LLM with system prompt containing the brand name."""
        mock_build_registry.return_value = WorkflowRegistry()

        provider = MockLLMProvider(text_response="Here is my proposed campaign plan...")

        pm_mock = MagicMock()
        pm_mock.load_project.return_value = _make_project()

        console_mock = MagicMock()
        # First input returns "done", which triggers finalization.
        # But finalization calls generate_text again and tries to parse JSON.
        # So we just test the first call: set up console to raise KeyboardInterrupt
        # after the first LLM call to exit the loop.
        console_mock.input.side_effect = KeyboardInterrupt

        planner = CampaignPlanner(provider=provider, project_manager=pm_mock)

        with pytest.raises(KeyboardInterrupt):
            await planner.plan("testproj", console=console_mock)

        # Verify the LLM was called with system prompt containing the brand name
        assert len(provider.calls) >= 1
        system_prompt = provider.calls[0]["system"]
        assert "TestBrand" in system_prompt
        assert "The best test brand" in system_prompt

    @patch("marketmenow.core.campaign_planner.build_workflow_registry")
    async def test_planner_parses_json_plan(
        self,
        mock_build_registry: MagicMock,
    ) -> None:
        """When user types 'done', planner parses LLM JSON into a CampaignPlan."""
        mock_build_registry.return_value = WorkflowRegistry()

        # First call: initial proposal. Second call: final JSON when user says "done".
        provider = MockLLMProvider(text_response=_PLAN_JSON)

        pm_mock = MagicMock()
        pm_mock.load_project.return_value = _make_project()
        pm_mock.project_dir.return_value = MagicMock()

        console_mock = MagicMock()
        console_mock.input.return_value = "done"

        planner = CampaignPlanner(provider=provider, project_manager=pm_mock)

        plan = await planner.plan("testproj", console=console_mock)

        assert plan.name == "spring-launch"
        assert plan.project_slug == "testproj"
        assert plan.goal.objective == "Grow awareness"
        assert len(plan.calendar) == 1
        assert plan.calendar[0].id == "d1-thread"
        assert plan.platforms == ["twitter"]
