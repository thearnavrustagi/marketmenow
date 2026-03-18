from __future__ import annotations

from marketmenow.exceptions import (
    AdapterNotFoundError,
    AuthenticationError,
    MarketMeNowError,
    PublishError,
    RenderError,
    UnsupportedModalityError,
    UploadError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self) -> None:
        for exc_cls in (
            AdapterNotFoundError,
            UnsupportedModalityError,
            AuthenticationError,
            PublishError,
            RenderError,
            UploadError,
        ):
            assert issubclass(exc_cls, MarketMeNowError)


class TestAdapterNotFoundError:
    def test_platform_attribute(self) -> None:
        exc = AdapterNotFoundError("twitter")
        assert exc.platform == "twitter"
        assert "twitter" in str(exc)


class TestUnsupportedModalityError:
    def test_attributes(self) -> None:
        exc = UnsupportedModalityError("twitter", "poll")
        assert exc.platform == "twitter"
        assert exc.modality == "poll"
        assert "twitter" in str(exc)
        assert "poll" in str(exc)


class TestAuthenticationError:
    def test_platform_attribute(self) -> None:
        exc = AuthenticationError("linkedin", "bad token")
        assert exc.platform == "linkedin"
        assert "bad token" in str(exc)


class TestPublishError:
    def test_platform_attribute(self) -> None:
        exc = PublishError("instagram", "rate limited")
        assert exc.platform == "instagram"


class TestRenderError:
    def test_platform_attribute(self) -> None:
        exc = RenderError("reddit", "too long")
        assert exc.platform == "reddit"


class TestUploadError:
    def test_platform_attribute(self) -> None:
        exc = UploadError("twitter", "file too large")
        assert exc.platform == "twitter"
