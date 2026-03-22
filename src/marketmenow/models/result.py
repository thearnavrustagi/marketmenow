from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MediaRef(BaseModel, frozen=True):
    """Opaque reference to an uploaded media asset on a specific platform."""

    platform: str
    remote_id: str
    remote_url: str | None = None


class PublishResult(BaseModel, frozen=True):
    id: UUID = Field(default_factory=uuid4)
    platform: str
    success: bool
    remote_post_id: str | None = None
    remote_url: str | None = None
    published_at: datetime | None = None
    error_message: str | None = None


class SendResult(BaseModel, frozen=True):
    id: UUID = Field(default_factory=uuid4)
    platform: str
    recipient_handle: str
    success: bool
    remote_message_id: str | None = None
    error_message: str | None = None


class AnalyticsSnapshot(BaseModel, frozen=True):
    publish_result_id: UUID
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    impressions: int = 0
    engagements: int = 0
    clicks: int = 0
    shares: int = 0
    raw_data: dict[str, object] = Field(default_factory=dict)
