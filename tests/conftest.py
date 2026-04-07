from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marketmenow.integrations.llm import LLMResponse
from marketmenow.models.content import (
    Article,
    ContentModality,
    DirectMessage,
    Document,
    ImagePost,
    MediaAsset,
    Poll,
    Recipient,
    Reply,
    TextPost,
    Thread,
    ThreadEntry,
    VideoPost,
)
from marketmenow.models.result import (
    AnalyticsSnapshot,
    MediaRef,
    PublishResult,
    SendResult,
)
from marketmenow.normaliser import NormalisedContent
from marketmenow.registry import AdapterRegistry, PlatformBundle

# ---------------------------------------------------------------------------
# Mock implementations satisfying the Protocol interfaces
# ---------------------------------------------------------------------------


class MockAdapter:
    def __init__(
        self,
        name: str = "mock",
        modalities: frozenset[ContentModality] | None = None,
    ) -> None:
        self._name = name
        self._modalities = modalities or frozenset(ContentModality)
        self.publish_calls: list[NormalisedContent] = []
        self.dm_calls: list[NormalisedContent] = []

    @property
    def platform_name(self) -> str:
        return self._name

    def supported_modalities(self) -> frozenset[ContentModality]:
        return self._modalities

    async def authenticate(self, credentials: dict[str, str]) -> None:
        pass

    async def publish(self, content: NormalisedContent) -> PublishResult:
        self.publish_calls.append(content)
        return PublishResult(
            platform=self._name,
            success=True,
            remote_post_id="post_123",
            remote_url=f"https://{self._name}.example.com/post_123",
            published_at=datetime.now(UTC),
        )

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        self.dm_calls.append(content)
        handle = content.recipient_handles[0] if content.recipient_handles else "unknown"
        return SendResult(
            platform=self._name,
            recipient_handle=handle,
            success=True,
            remote_message_id="dm_456",
        )


class MockRenderer:
    def __init__(self, name: str = "mock") -> None:
        self._name = name

    @property
    def platform_name(self) -> str:
        return self._name

    async def render(self, content: NormalisedContent) -> NormalisedContent:
        return content


class MockUploader:
    def __init__(self, name: str = "mock") -> None:
        self._name = name

    @property
    def platform_name(self) -> str:
        return self._name

    async def upload(self, asset: MediaAsset) -> MediaRef:
        return MediaRef(
            platform=self._name,
            remote_id=f"upload_{asset.uri}",
            remote_url=f"https://cdn.{self._name}.example.com/{asset.uri}",
        )

    async def upload_batch(self, assets: list[MediaAsset]) -> list[MediaRef]:
        return [await self.upload(a) for a in assets]


class MockAnalytics:
    def __init__(self, name: str = "mock") -> None:
        self._name = name

    @property
    def platform_name(self) -> str:
        return self._name

    async def collect(self, result: PublishResult) -> AnalyticsSnapshot:
        return AnalyticsSnapshot(
            publish_result_id=result.id,
            impressions=100,
            engagements=10,
        )


class FailingAdapter(MockAdapter):
    """Adapter whose publish always raises."""

    async def publish(self, content: NormalisedContent) -> PublishResult:
        raise RuntimeError(f"publish failed on {self._name}")

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        raise RuntimeError(f"send_dm failed on {self._name}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _media(uri: str = "file:///img.png", mime: str = "image/png") -> MediaAsset:
    return MediaAsset(uri=uri, mime_type=mime)


@pytest.fixture
def media_asset() -> MediaAsset:
    return _media()


@pytest.fixture
def mock_bundle() -> PlatformBundle:
    return PlatformBundle(
        adapter=MockAdapter("mock"),
        renderer=MockRenderer("mock"),
        uploader=MockUploader("mock"),
        analytics=MockAnalytics("mock"),
    )


@pytest.fixture
def registry(mock_bundle: PlatformBundle) -> AdapterRegistry:
    reg = AdapterRegistry()
    reg.register(mock_bundle)
    return reg


# ---------------------------------------------------------------------------
# Content factories
# ---------------------------------------------------------------------------


def make_video(**overrides: object) -> VideoPost:
    defaults: dict[str, object] = {
        "video": _media("file:///vid.mp4", "video/mp4"),
        "caption": "Check this out",
        "hashtags": ["ai", "tech"],
    }
    return VideoPost(**(defaults | overrides))


def make_image(**overrides: object) -> ImagePost:
    defaults: dict[str, object] = {
        "images": [_media()],
        "caption": "Beautiful shot",
        "hashtags": ["photo"],
    }
    return ImagePost(**(defaults | overrides))


def make_thread(**overrides: object) -> Thread:
    defaults: dict[str, object] = {
        "entries": [
            ThreadEntry(text="First tweet"),
            ThreadEntry(text="Second tweet", media=[_media()]),
        ],
    }
    return Thread(**(defaults | overrides))


def make_dm(**overrides: object) -> DirectMessage:
    defaults: dict[str, object] = {
        "recipients": [Recipient(handle="@user")],
        "body": "Hello!",
        "subject": "Greeting",
    }
    return DirectMessage(**(defaults | overrides))


def make_reply(**overrides: object) -> Reply:
    defaults: dict[str, object] = {
        "in_reply_to_url": "https://twitter.com/user/status/123",
        "body": "Great point!",
    }
    return Reply(**(defaults | overrides))


def make_text_post(**overrides: object) -> TextPost:
    defaults: dict[str, object] = {
        "body": "Just sharing a thought",
        "hashtags": ["thoughts"],
    }
    return TextPost(**(defaults | overrides))


def make_document(**overrides: object) -> Document:
    defaults: dict[str, object] = {
        "file": _media("file:///doc.pdf", "application/pdf"),
        "title": "Whitepaper",
        "caption": "Read our latest whitepaper",
    }
    return Document(**(defaults | overrides))


def make_article(**overrides: object) -> Article:
    defaults: dict[str, object] = {
        "url": "https://blog.example.com/post",
        "commentary": "Interesting read",
        "hashtags": ["blog"],
    }
    return Article(**(defaults | overrides))


def make_poll(**overrides: object) -> Poll:
    defaults: dict[str, object] = {
        "question": "Which is better?",
        "options": ["A", "B", "C"],
        "duration_days": 3,
    }
    return Poll(**(defaults | overrides))


# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------


class MockLLMProvider:
    def __init__(self, text_response: str = "", json_response: str = "{}"):
        self.text_response = text_response
        self.json_response = json_response
        self.calls: list[dict[str, object]] = []

    async def generate_text(
        self,
        *,
        model: str,
        system: str,
        contents: str | list[object],
        temperature: float = 1.0,
        max_retries: int = 3,
        initial_backoff: float = 5.0,
    ) -> LLMResponse:
        self.calls.append(
            {"method": "generate_text", "model": model, "system": system, "contents": contents}
        )
        return LLMResponse(text=self.text_response, raw=None)

    async def generate_json(
        self,
        *,
        model: str,
        system: str,
        contents: str | list[object],
        temperature: float = 0.3,
        max_retries: int = 3,
        initial_backoff: float = 5.0,
    ) -> LLMResponse:
        self.calls.append(
            {"method": "generate_json", "model": model, "system": system, "contents": contents}
        )
        return LLMResponse(text=self.json_response, raw=None)

    async def embed(self, *, texts: list[str], model: str = "") -> list[list[float]]:
        self.calls.append({"method": "embed", "texts": texts})
        return [[0.1] * 768 for _ in texts]


@pytest.fixture
def mock_provider() -> MockLLMProvider:
    return MockLLMProvider()
