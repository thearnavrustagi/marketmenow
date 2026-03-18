from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from marketmenow.models.result import (
    AnalyticsSnapshot,
    MediaRef,
    PublishResult,
    SendResult,
)


class TestMediaRef:
    def test_construction(self) -> None:
        ref = MediaRef(platform="ig", remote_id="abc")
        assert ref.platform == "ig"
        assert ref.remote_url is None

    def test_frozen(self) -> None:
        ref = MediaRef(platform="ig", remote_id="abc")
        with pytest.raises(ValidationError):
            ref.platform = "tw"  # type: ignore[misc]


class TestPublishResult:
    def test_auto_id(self) -> None:
        r = PublishResult(platform="twitter", success=True)
        assert isinstance(r.id, UUID)

    def test_success_fields(self) -> None:
        r = PublishResult(
            platform="twitter",
            success=True,
            remote_post_id="123",
            remote_url="https://twitter.com/post/123",
            published_at=datetime.now(UTC),
        )
        assert r.success is True
        assert r.error_message is None

    def test_failure_fields(self) -> None:
        r = PublishResult(platform="twitter", success=False, error_message="timeout")
        assert r.success is False
        assert r.error_message == "timeout"

    def test_frozen(self) -> None:
        r = PublishResult(platform="twitter", success=True)
        with pytest.raises(ValidationError):
            r.success = False  # type: ignore[misc]


class TestSendResult:
    def test_auto_id(self) -> None:
        r = SendResult(platform="mock", recipient_handle="@user", success=True)
        assert isinstance(r.id, UUID)

    def test_fields(self) -> None:
        r = SendResult(
            platform="mock",
            recipient_handle="@user",
            success=False,
            error_message="blocked",
        )
        assert r.recipient_handle == "@user"
        assert r.error_message == "blocked"


class TestAnalyticsSnapshot:
    def test_auto_collected_at(self) -> None:
        before = datetime.now(UTC)
        snap = AnalyticsSnapshot(publish_result_id=uuid4())
        after = datetime.now(UTC)
        assert before <= snap.collected_at <= after

    def test_defaults_zero(self) -> None:
        snap = AnalyticsSnapshot(publish_result_id=uuid4())
        assert snap.impressions == 0
        assert snap.engagements == 0
        assert snap.clicks == 0
        assert snap.shares == 0
        assert snap.raw_data == {}

    def test_custom_values(self) -> None:
        snap = AnalyticsSnapshot(
            publish_result_id=uuid4(),
            impressions=500,
            engagements=50,
            clicks=20,
            shares=5,
            raw_data={"viral": True},
        )
        assert snap.impressions == 500
        assert snap.raw_data["viral"] is True
