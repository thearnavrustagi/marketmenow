from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import BaseModel, Field


class CampaignGoal(BaseModel, frozen=True):
    """High-level campaign objective."""

    objective: str
    kpi: str
    duration_days: int


class ContentCalendarItem(BaseModel, frozen=True):
    """A single scheduled content piece in the campaign calendar."""

    id: str
    date: date
    platform: str
    workflow: str
    content_type: str
    topic: str
    brief: str
    cta: str = ""
    status: str = "pending"
    capsule_id: str = ""


class RepurposeChain(BaseModel, frozen=True):
    """Defines content repurposed across platforms from a source item."""

    source_item_id: str
    target_items: list[str] = Field(default_factory=list)


class CampaignPlan(BaseModel, frozen=True):
    """Full campaign plan as persisted to YAML."""

    name: str
    project_slug: str
    goal: CampaignGoal
    audience_summary: str
    tone: str
    platforms: list[str]
    calendar: list[ContentCalendarItem]
    repurpose_chains: list[RepurposeChain] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
