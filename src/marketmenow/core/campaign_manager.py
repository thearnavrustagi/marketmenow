from __future__ import annotations

import logging
from pathlib import Path

import yaml

from marketmenow.core.project_manager import ProjectManager
from marketmenow.models.campaign_plan import CampaignPlan, ContentCalendarItem

logger = logging.getLogger(__name__)


class CampaignManager:
    """CRUD for campaign plans stored as YAML under project directories."""

    def __init__(self, project_manager: ProjectManager | None = None) -> None:
        self._pm = project_manager or ProjectManager()

    def _campaigns_dir(self, project_slug: str) -> Path:
        return self._pm.project_dir(project_slug) / "campaigns"

    def _campaign_dir(self, project_slug: str, name: str) -> Path:
        return self._campaigns_dir(project_slug) / name

    def _plan_path(self, project_slug: str, name: str) -> Path:
        return self._campaign_dir(project_slug, name) / "campaign.yaml"

    def save_plan(self, plan: CampaignPlan) -> Path:
        """Persist a CampaignPlan to projects/{slug}/campaigns/{name}/campaign.yaml."""
        campaign_dir = self._campaign_dir(plan.project_slug, plan.name)
        campaign_dir.mkdir(parents=True, exist_ok=True)

        path = campaign_dir / "campaign.yaml"
        data = plan.model_dump(mode="json")
        # Convert date objects to ISO strings for YAML
        for item in data.get("calendar", []):
            if isinstance(item.get("date"), str):
                pass  # already a string from mode="json"

        with path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        logger.info("Saved campaign plan to %s", path)
        return path

    def load_plan(self, project_slug: str, name: str) -> CampaignPlan:
        """Load a campaign plan from YAML."""
        path = self._plan_path(project_slug, name)
        if not path.exists():
            raise FileNotFoundError(f"Campaign plan not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return CampaignPlan(**data)

    def list_campaigns(self, project_slug: str) -> list[CampaignPlan]:
        """List all campaigns for a project."""
        campaigns_dir = self._campaigns_dir(project_slug)
        if not campaigns_dir.exists():
            return []

        plans: list[CampaignPlan] = []
        for child in sorted(campaigns_dir.iterdir()):
            plan_file = child / "campaign.yaml"
            if child.is_dir() and plan_file.exists():
                try:
                    plans.append(self.load_plan(project_slug, child.name))
                except Exception:
                    logger.warning("Failed to load campaign %s", child.name, exc_info=True)
        return plans

    def update_item_status(
        self,
        project_slug: str,
        campaign_name: str,
        item_id: str,
        status: str,
        capsule_id: str = "",
    ) -> None:
        """Update a single calendar item's status (and optionally capsule_id).

        Reloads, mutates via model_copy, and re-saves the plan.
        """
        plan = self.load_plan(project_slug, campaign_name)

        updated_calendar: list[ContentCalendarItem] = []
        found = False
        for item in plan.calendar:
            if item.id == item_id:
                updates: dict[str, str] = {"status": status}
                if capsule_id:
                    updates["capsule_id"] = capsule_id
                updated_calendar.append(item.model_copy(update=updates))
                found = True
            else:
                updated_calendar.append(item)

        if not found:
            raise ValueError(f"Calendar item '{item_id}' not found in campaign '{campaign_name}'")

        updated_plan = plan.model_copy(update={"calendar": updated_calendar})
        self.save_plan(updated_plan)
