from __future__ import annotations

import pytest

from conftest import MockAdapter, MockRenderer, MockUploader
from marketmenow.exceptions import AdapterNotFoundError
from marketmenow.models.content import ContentModality
from marketmenow.registry import AdapterRegistry, PlatformBundle


class TestRegister:
    def test_valid_bundle(self) -> None:
        reg = AdapterRegistry()
        bundle = PlatformBundle(
            adapter=MockAdapter("test"),
            renderer=MockRenderer("test"),
            uploader=MockUploader("test"),
        )
        reg.register(bundle)
        assert "test" in reg.list_platforms()

    def test_invalid_adapter_raises(self) -> None:
        reg = AdapterRegistry()
        bundle = PlatformBundle(
            adapter="not an adapter",  # type: ignore[arg-type]
            renderer=MockRenderer("test"),
            uploader=MockUploader("test"),
        )
        with pytest.raises((TypeError, AttributeError)):
            reg.register(bundle)

    def test_invalid_renderer_raises_type_error(self) -> None:
        reg = AdapterRegistry()
        bundle = PlatformBundle(
            adapter=MockAdapter("test"),
            renderer="not a renderer",  # type: ignore[arg-type]
            uploader=MockUploader("test"),
        )
        with pytest.raises(TypeError, match="ContentRenderer"):
            reg.register(bundle)

    def test_invalid_uploader_raises_type_error(self) -> None:
        reg = AdapterRegistry()
        bundle = PlatformBundle(
            adapter=MockAdapter("test"),
            renderer=MockRenderer("test"),
            uploader="not an uploader",  # type: ignore[arg-type]
        )
        with pytest.raises(TypeError, match="Uploader"):
            reg.register(bundle)

    def test_analytics_optional(self) -> None:
        reg = AdapterRegistry()
        bundle = PlatformBundle(
            adapter=MockAdapter("test"),
            renderer=MockRenderer("test"),
            uploader=MockUploader("test"),
            analytics=None,
        )
        reg.register(bundle)
        assert reg.get("test").analytics is None


class TestGet:
    def test_returns_bundle(self, registry: AdapterRegistry) -> None:
        bundle = registry.get("mock")
        assert bundle.adapter.platform_name == "mock"

    def test_missing_raises(self) -> None:
        reg = AdapterRegistry()
        with pytest.raises(AdapterNotFoundError) as exc_info:
            reg.get("nonexistent")
        assert exc_info.value.platform == "nonexistent"


class TestListPlatforms:
    def test_empty(self) -> None:
        reg = AdapterRegistry()
        assert reg.list_platforms() == []

    def test_multiple(self) -> None:
        reg = AdapterRegistry()
        for name in ("alpha", "beta", "gamma"):
            reg.register(
                PlatformBundle(
                    adapter=MockAdapter(name),
                    renderer=MockRenderer(name),
                    uploader=MockUploader(name),
                )
            )
        platforms = reg.list_platforms()
        assert set(platforms) == {"alpha", "beta", "gamma"}


class TestSupports:
    def test_supported_modality(self, registry: AdapterRegistry) -> None:
        assert registry.supports("mock", ContentModality.TEXT_POST) is True

    def test_unsupported_modality(self) -> None:
        reg = AdapterRegistry()
        adapter = MockAdapter("limited", modalities=frozenset({ContentModality.VIDEO}))
        reg.register(
            PlatformBundle(
                adapter=adapter,
                renderer=MockRenderer("limited"),
                uploader=MockUploader("limited"),
            )
        )
        assert reg.supports("limited", ContentModality.VIDEO) is True
        assert reg.supports("limited", ContentModality.POLL) is False

    def test_missing_platform_raises(self) -> None:
        reg = AdapterRegistry()
        with pytest.raises(AdapterNotFoundError):
            reg.supports("ghost", ContentModality.VIDEO)
