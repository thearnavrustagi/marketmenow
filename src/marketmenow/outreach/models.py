from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ProductInfo(BaseModel, frozen=True):
    name: str
    url: str
    tagline: str
    value_prop: str


class RubricCriterion(BaseModel, frozen=True):
    name: str
    description: str
    max_points: int


class DiscoveryVectorConfig(BaseModel, frozen=True):
    """Config for a single discovery vector, loaded from YAML."""

    vector_type: str
    entries: list[str]
    max_per_entry: int = 5


class MessagingConfig(BaseModel, frozen=True):
    max_messages: int = 10
    min_delay_seconds: int = 120
    max_delay_seconds: int = 300
    tone: str = ""
    reference_post: bool = True
    pause_every_n: int = 5
    long_pause_seconds: int = 600
    max_message_length: int = 280


class ICPConfig(BaseModel, frozen=True):
    description: str
    rubric: list[RubricCriterion]
    min_score: int
    max_prospects_to_enrich: int = 50
    bio_blocklist: list[str] = Field(default_factory=list)
    bio_require_any: list[str] = Field(default_factory=list)


class CustomerProfile(BaseModel, frozen=True):
    """Complete outreach config loaded from YAML. Drives the entire pipeline."""

    product: ProductInfo
    platform: str
    ideal_customer: ICPConfig
    discovery_vectors: list[DiscoveryVectorConfig]
    messaging: MessagingConfig = MessagingConfig()


class DiscoveredProspectPost(BaseModel, frozen=True):
    """A single post found during discovery. Multiple may map to one person."""

    author_handle: str
    post_url: str
    post_text: str
    engagement_score: int = 0
    source_vector: str = ""
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserProfile(BaseModel, frozen=True):
    """Platform-agnostic user profile enriched from a social media account."""

    platform: str
    handle: str
    display_name: str
    bio: str
    location: str = ""
    follower_count: int = 0
    following_count: int = 0
    join_date: str = ""
    dm_possible: bool = True
    recent_posts: list[str] = Field(default_factory=list)
    triggering_posts: list[str] = Field(default_factory=list)
    triggering_post_urls: list[str] = Field(default_factory=list)
    discovery_count: int = 1
    extra: dict[str, str] = Field(default_factory=dict)


class RubricEvaluation(BaseModel, frozen=True):
    criterion_name: str
    points_awarded: int
    max_points: int
    reasoning: str


class ScoredProspect(BaseModel, frozen=True):
    user_profile: UserProfile
    evaluations: list[RubricEvaluation]
    total_score: int
    max_score: int
    dm_angle: str
    disqualify_reason: str | None = None


class OutreachMessage(BaseModel, frozen=True):
    id: UUID = Field(default_factory=uuid4)
    recipient_handle: str
    message_text: str
    referenced_post_url: str = ""
    referenced_post_text: str = ""
    prospect_score: int = 0
    dm_angle: str = ""


class OutreachSendResult(BaseModel, frozen=True):
    recipient_handle: str
    success: bool
    error_message: str | None = None
