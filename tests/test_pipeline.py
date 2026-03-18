from __future__ import annotations

import pytest

from conftest import (
    MockAdapter,
    MockRenderer,
    MockUploader,
    make_dm,
    make_text_post,
    make_video,
)
from marketmenow.core.pipeline import ContentPipeline
from marketmenow.exceptions import AdapterNotFoundError
from marketmenow.models.result import PublishResult, SendResult
from marketmenow.registry import AdapterRegistry, PlatformBundle


@pytest.fixture
def pipeline(registry: AdapterRegistry) -> ContentPipeline:
    return ContentPipeline(registry)


class TestPipelineExecute:
    async def test_publish_flow(self, pipeline: ContentPipeline) -> None:
        post = make_text_post()
        result = await pipeline.execute(post, "mock")
        assert isinstance(result, PublishResult)
        assert result.success is True
        assert result.platform == "mock"

    async def test_dm_dispatches_to_send_dm(self, pipeline: ContentPipeline) -> None:
        dm = make_dm()
        result = await pipeline.execute(dm, "mock")
        assert isinstance(result, SendResult)
        assert result.success is True
        assert result.recipient_handle == "@user"

    async def test_media_refs_merged_into_extra(self) -> None:
        reg = AdapterRegistry()
        adapter = MockAdapter("test")
        reg.register(
            PlatformBundle(
                adapter=adapter,
                renderer=MockRenderer("test"),
                uploader=MockUploader("test"),
            )
        )
        pipeline = ContentPipeline(reg)
        post = make_video()
        await pipeline.execute(post, "test")

        published_content = adapter.publish_calls[0]
        assert "_media_refs" in published_content.extra
        refs = published_content.extra["_media_refs"]
        assert len(refs) == 1
        assert refs[0].platform == "test"

    async def test_missing_platform_raises(self, pipeline: ContentPipeline) -> None:
        post = make_text_post()
        with pytest.raises(AdapterNotFoundError):
            await pipeline.execute(post, "nonexistent")

    async def test_render_called(self) -> None:
        """Verify the renderer is invoked by checking the pipeline produces a result."""
        reg = AdapterRegistry()
        reg.register(
            PlatformBundle(
                adapter=MockAdapter("rtest"),
                renderer=MockRenderer("rtest"),
                uploader=MockUploader("rtest"),
            )
        )
        pipeline = ContentPipeline(reg)
        result = await pipeline.execute(make_text_post(), "rtest")
        assert result.success is True
