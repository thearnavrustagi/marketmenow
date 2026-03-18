from __future__ import annotations

from dataclasses import dataclass

from marketmenow.exceptions import AdapterNotFoundError
from marketmenow.models.content import ContentModality
from marketmenow.ports.analytics import AnalyticsCollector
from marketmenow.ports.content_renderer import ContentRenderer
from marketmenow.ports.platform_adapter import PlatformAdapter
from marketmenow.ports.uploader import Uploader


@dataclass
class PlatformBundle:
    """Groups all adapter components for a single platform."""

    adapter: PlatformAdapter
    renderer: ContentRenderer
    uploader: Uploader
    analytics: AnalyticsCollector | None = None


class AdapterRegistry:
    def __init__(self) -> None:
        self._platforms: dict[str, PlatformBundle] = {}

    def register(self, bundle: PlatformBundle) -> None:
        name = bundle.adapter.platform_name
        if not isinstance(bundle.adapter, PlatformAdapter):
            raise TypeError(
                f"adapter does not satisfy PlatformAdapter protocol: {type(bundle.adapter)}"
            )
        if not isinstance(bundle.renderer, ContentRenderer):
            raise TypeError(
                f"renderer does not satisfy ContentRenderer protocol: {type(bundle.renderer)}"
            )
        if not isinstance(bundle.uploader, Uploader):
            raise TypeError(f"uploader does not satisfy Uploader protocol: {type(bundle.uploader)}")
        self._platforms[name] = bundle

    def get(self, platform: str) -> PlatformBundle:
        if platform not in self._platforms:
            raise AdapterNotFoundError(platform)
        return self._platforms[platform]

    def list_platforms(self) -> list[str]:
        return list(self._platforms.keys())

    def supports(self, platform: str, modality: ContentModality) -> bool:
        bundle = self.get(platform)
        return modality in bundle.adapter.supported_modalities()
