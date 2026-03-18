from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from conftest import make_text_post
from marketmenow.models.campaign import (
    Audience,
    Campaign,
    CampaignTarget,
    ScheduleRule,
)
from marketmenow.models.content import ContentModality

# ---------------------------------------------------------------------------
# ScheduleRule
# ---------------------------------------------------------------------------


class TestScheduleRule:
    def test_defaults(self) -> None:
        rule = ScheduleRule()
        assert rule.publish_at is None
        assert rule.timezone == "UTC"
        assert rule.repeat_cron is None

    def test_custom_values(self) -> None:
        dt = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
        rule = ScheduleRule(publish_at=dt, timezone="US/Eastern", repeat_cron="0 9 * * 1")
        assert rule.publish_at == dt
        assert rule.timezone == "US/Eastern"


# ---------------------------------------------------------------------------
# CampaignTarget
# ---------------------------------------------------------------------------


class TestCampaignTarget:
    def test_default_schedule(self) -> None:
        target = CampaignTarget(platform="twitter", modality=ContentModality.TEXT_POST)
        assert target.schedule.publish_at is None

    def test_frozen(self) -> None:
        target = CampaignTarget(platform="twitter", modality=ContentModality.TEXT_POST)
        with pytest.raises(ValidationError):
            target.platform = "linkedin"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Audience
# ---------------------------------------------------------------------------


class TestAudience:
    def test_empty_handles(self) -> None:
        a = Audience(name="devs")
        assert a.platform_handles == {}

    def test_with_handles(self) -> None:
        a = Audience(
            name="devs",
            platform_handles={"twitter": ["@alice", "@bob"]},
        )
        assert len(a.platform_handles["twitter"]) == 2


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------


class TestCampaign:
    def _target(self) -> CampaignTarget:
        return CampaignTarget(platform="mock", modality=ContentModality.TEXT_POST)

    def test_min_one_target(self) -> None:
        with pytest.raises(ValidationError, match="targets"):
            Campaign(name="empty", content=make_text_post(), targets=[])

    def test_status_default(self) -> None:
        c = Campaign(name="c", content=make_text_post(), targets=[self._target()])
        assert c.status == "draft"

    def test_auto_id(self) -> None:
        c = Campaign(name="c", content=make_text_post(), targets=[self._target()])
        assert isinstance(c.id, UUID)

    def test_auto_created_at(self) -> None:
        before = datetime.now(UTC)
        c = Campaign(name="c", content=make_text_post(), targets=[self._target()])
        after = datetime.now(UTC)
        assert before <= c.created_at <= after

    def test_audience_optional(self) -> None:
        c = Campaign(name="c", content=make_text_post(), targets=[self._target()])
        assert c.audience is None
