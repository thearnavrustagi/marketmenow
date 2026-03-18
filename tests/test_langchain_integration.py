from __future__ import annotations

import pytest

import marketmenow.integrations.langchain as lc_module
from conftest import MockAdapter, MockRenderer, MockUploader
from marketmenow.integrations.langchain import (
    _build_content,
    _get_registry,
    get_tools,
    init,
)
from marketmenow.models.content import (
    Article,
    ContentModality,
    DirectMessage,
    Document,
    ImagePost,
    Poll,
    Reply,
    TextPost,
    Thread,
    VideoPost,
)
from marketmenow.registry import AdapterRegistry, PlatformBundle

# ---------------------------------------------------------------------------
# _build_content
# ---------------------------------------------------------------------------


class TestBuildContent:
    def test_video(self) -> None:
        content = _build_content(
            "video",
            {
                "video": {"uri": "v.mp4", "mime_type": "video/mp4"},
            },
        )
        assert isinstance(content, VideoPost)
        assert content.modality == ContentModality.VIDEO

    def test_image(self) -> None:
        content = _build_content(
            "image",
            {
                "images": [{"uri": "i.png", "mime_type": "image/png"}],
            },
        )
        assert isinstance(content, ImagePost)

    def test_thread(self) -> None:
        content = _build_content(
            "thread",
            {
                "entries": [{"text": "tweet 1"}],
            },
        )
        assert isinstance(content, Thread)

    def test_direct_message(self) -> None:
        content = _build_content(
            "direct_message",
            {
                "recipients": [{"handle": "@user"}],
                "body": "hi",
            },
        )
        assert isinstance(content, DirectMessage)

    def test_reply(self) -> None:
        content = _build_content(
            "reply",
            {
                "in_reply_to_url": "https://example.com/post",
                "body": "nice",
            },
        )
        assert isinstance(content, Reply)

    def test_text_post(self) -> None:
        content = _build_content("text_post", {"body": "hello"})
        assert isinstance(content, TextPost)

    def test_document(self) -> None:
        content = _build_content(
            "document",
            {
                "file": {"uri": "d.pdf", "mime_type": "application/pdf"},
            },
        )
        assert isinstance(content, Document)

    def test_article(self) -> None:
        content = _build_content(
            "article",
            {
                "url": "https://example.com",
            },
        )
        assert isinstance(content, Article)

    def test_poll(self) -> None:
        content = _build_content(
            "poll",
            {
                "question": "Q?",
                "options": ["A", "B"],
            },
        )
        assert isinstance(content, Poll)

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown modality"):
            _build_content("unknown_type", {})


# ---------------------------------------------------------------------------
# init / _get_registry
# ---------------------------------------------------------------------------


class TestRegistryLifecycle:
    def test_get_registry_before_init_raises(self) -> None:
        original = lc_module._registry
        try:
            lc_module._registry = None
            with pytest.raises(RuntimeError, match="not initialised"):
                _get_registry()
        finally:
            lc_module._registry = original

    def test_init_sets_registry(self) -> None:
        reg = AdapterRegistry()
        original = lc_module._registry
        try:
            init(reg)
            assert _get_registry() is reg
        finally:
            lc_module._registry = original


# ---------------------------------------------------------------------------
# get_tools
# ---------------------------------------------------------------------------


class TestGetTools:
    def test_returns_three_tools(self) -> None:
        reg = AdapterRegistry()
        reg.register(
            PlatformBundle(
                adapter=MockAdapter("test"),
                renderer=MockRenderer("test"),
                uploader=MockUploader("test"),
            )
        )
        original = lc_module._registry
        try:
            tools = get_tools(reg)
            assert len(tools) == 3
        finally:
            lc_module._registry = original

    def test_tool_names(self) -> None:
        reg = AdapterRegistry()
        reg.register(
            PlatformBundle(
                adapter=MockAdapter("test"),
                renderer=MockRenderer("test"),
                uploader=MockUploader("test"),
            )
        )
        original = lc_module._registry
        try:
            tools = get_tools(reg)
            names = {t.name for t in tools}
            assert "mmn_list_platforms" in names
            assert "mmn_publish" in names
            assert "mmn_run_campaign" in names
        finally:
            lc_module._registry = original
