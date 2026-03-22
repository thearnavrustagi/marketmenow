from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from marketmenow.models.content import BaseContent, ContentModality


class Audience(BaseModel, frozen=True):
    name: str
    platform_handles: dict[str, list[str]] = Field(default_factory=dict)


class ScheduleRule(BaseModel, frozen=True):
    publish_at: datetime | None = None
    timezone: str = "UTC"
    repeat_cron: str | None = None


class CampaignTarget(BaseModel, frozen=True):
    platform: str
    modality: ContentModality
    schedule: ScheduleRule = Field(default_factory=ScheduleRule)


class Campaign(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    content: BaseContent
    targets: list[CampaignTarget] = Field(..., min_length=1)
    audience: Audience | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "draft"
