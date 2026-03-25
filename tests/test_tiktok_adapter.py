from __future__ import annotations

from adapters.tiktok import create_tiktok_bundle
from adapters.tiktok.adapter import TikTokAdapter, TikTokAPIError
from adapters.tiktok.renderer import TikTokRenderer
from adapters.tiktok.settings import TikTokSettings
from adapters.tiktok.uploader import TikTokUploader
from marketmenow.models.content import ContentModality, MediaAsset, VideoPost
from marketmenow.models.result import MediaRef
from marketmenow.normaliser import NormalisedContent
from marketmenow.registry import AdapterRegistry

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestTikTokSettings:
    def test_defaults(self, monkeypatch: object) -> None:
        import pytest

        mp = pytest.MonkeyPatch()  # type: ignore[attr-defined]
        mp.delenv("TIKTOK_SESSION_ID", raising=False)
        mp.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
        mp.delenv("TIKTOK_REFRESH_TOKEN", raising=False)
        settings = TikTokSettings(
            _env_file=None,  # type: ignore[call-arg]
            tiktok_client_key="ck",
            tiktok_client_secret="cs",
        )
        assert settings.tiktok_default_privacy == "SELF_ONLY"
        assert settings.tiktok_access_token == ""
        assert settings.tiktok_refresh_token == ""
        assert settings.tiktok_session_id == ""
        mp.undo()

    def test_cookie_settings(self) -> None:
        settings = TikTokSettings(
            _env_file=None,  # type: ignore[call-arg]
            tiktok_session_id="abc123",
        )
        assert settings.tiktok_session_id == "abc123"
        assert settings.tiktok_access_token == ""


# ---------------------------------------------------------------------------
# Uploader (passthrough)
# ---------------------------------------------------------------------------


class TestTikTokUploader:
    async def test_platform_name(self) -> None:
        uploader = TikTokUploader()
        assert uploader.platform_name == "tiktok"

    async def test_upload_returns_local_path(self) -> None:
        uploader = TikTokUploader()
        asset = MediaAsset(uri="/tmp/test.mp4", mime_type="video/mp4")
        ref = await uploader.upload(asset)
        assert ref.platform == "tiktok"
        assert ref.remote_url == "/tmp/test.mp4"

    async def test_upload_batch(self) -> None:
        uploader = TikTokUploader()
        assets = [
            MediaAsset(uri="/tmp/a.mp4", mime_type="video/mp4"),
            MediaAsset(uri="/tmp/b.mp4", mime_type="video/mp4"),
        ]
        refs = await uploader.upload_batch(assets)
        assert len(refs) == 2
        assert refs[0].remote_url == "/tmp/a.mp4"
        assert refs[1].remote_url == "/tmp/b.mp4"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class TestTikTokRenderer:
    async def test_platform_name(self) -> None:
        renderer = TikTokRenderer()
        assert renderer.platform_name == "tiktok"

    async def test_strips_hash_prefix(self) -> None:
        renderer = TikTokRenderer()
        video = VideoPost(
            video=MediaAsset(uri="/tmp/test.mp4", mime_type="video/mp4"),
            caption="hello",
            hashtags=["#fyp", "viral"],
        )
        normalised = NormalisedContent(
            source=video,
            modality=ContentModality.VIDEO,
            text_segments=["hello"],
            media_assets=[video.video],
            hashtags=["#fyp", "viral"],
        )
        result = await renderer.render(normalised)
        assert result.hashtags == ["fyp", "viral"]

    async def test_truncates_long_caption(self) -> None:
        renderer = TikTokRenderer()
        video = VideoPost(
            video=MediaAsset(uri="/tmp/test.mp4", mime_type="video/mp4"),
            caption="x" * 2300,
        )
        normalised = NormalisedContent(
            source=video,
            modality=ContentModality.VIDEO,
            text_segments=["x" * 2300],
            media_assets=[video.video],
            hashtags=["longtag"],
        )
        result = await renderer.render(normalised)
        total_len = (
            sum(len(s) for s in result.text_segments)
            + len(" ".join(f"#{t}" for t in result.hashtags))
            + 2
        )
        assert total_len <= 2200


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class TestTikTokAdapter:
    def test_platform_name(self) -> None:
        adapter = TikTokAdapter(
            client_key="ck",
            client_secret="cs",
            access_token="at",
            refresh_token="rt",
        )
        assert adapter.platform_name == "tiktok"

    def test_supported_modalities(self) -> None:
        adapter = TikTokAdapter(
            client_key="ck",
            client_secret="cs",
            access_token="at",
            refresh_token="rt",
        )
        assert adapter.supported_modalities() == frozenset({ContentModality.VIDEO})

    async def test_send_dm_unsupported(self) -> None:
        adapter = TikTokAdapter(
            client_key="ck",
            client_secret="cs",
            access_token="at",
            refresh_token="rt",
        )
        video = VideoPost(
            video=MediaAsset(uri="/tmp/test.mp4", mime_type="video/mp4"),
        )
        content = NormalisedContent(
            source=video,
            modality=ContentModality.VIDEO,
            text_segments=[],
            media_assets=[],
        )
        result = await adapter.send_dm(content)
        assert result.success is False
        assert "not support" in result.error_message.lower()

    async def test_publish_unsupported_modality(self) -> None:
        adapter = TikTokAdapter(
            client_key="ck",
            client_secret="cs",
            access_token="at",
            refresh_token="rt",
        )
        from marketmenow.models.content import TextPost

        text = TextPost(body="test")
        content = NormalisedContent(
            source=text,
            modality=ContentModality.TEXT_POST,
            text_segments=["test"],
            media_assets=[],
        )
        result = await adapter.publish(content)
        assert result.success is False
        assert "Unsupported modality" in (result.error_message or "")

    async def test_publish_missing_file(self) -> None:
        adapter = TikTokAdapter(
            client_key="ck",
            client_secret="cs",
            access_token="at",
            refresh_token="rt",
        )
        video = VideoPost(
            video=MediaAsset(uri="/nonexistent/video.mp4", mime_type="video/mp4"),
        )
        content = NormalisedContent(
            source=video,
            modality=ContentModality.VIDEO,
            text_segments=["caption"],
            media_assets=[video.video],
            extra={
                "_media_refs": [
                    MediaRef(platform="tiktok", remote_id="", remote_url="/nonexistent/video.mp4")
                ]
            },
        )
        result = await adapter.publish(content)
        assert result.success is False
        assert "not found" in (result.error_message or "").lower()

    def test_compute_chunks_small_file(self) -> None:
        chunk_size, total = TikTokAdapter._compute_chunks(3 * 1024 * 1024)
        assert total == 1
        assert chunk_size == 3 * 1024 * 1024

    def test_compute_chunks_medium_file(self) -> None:
        video_size = 50 * 1024 * 1024  # 50 MB
        chunk_size, total = TikTokAdapter._compute_chunks(video_size)
        assert chunk_size == 10 * 1024 * 1024
        assert total == 5

    def test_compute_chunks_large_file(self) -> None:
        video_size = 2 * 1024 * 1024 * 1024  # 2 GB
        chunk_size, total = TikTokAdapter._compute_chunks(video_size)
        assert total <= 1000
        assert chunk_size >= 5 * 1024 * 1024

    def test_use_browser_when_session_id_only(self) -> None:
        adapter = TikTokAdapter(session_id="sid123")
        assert adapter._use_browser is True

    def test_use_api_when_access_token_set(self) -> None:
        adapter = TikTokAdapter(access_token="at", session_id="sid123")
        assert adapter._use_browser is False

    def test_use_api_when_no_session_id(self) -> None:
        adapter = TikTokAdapter(
            client_key="ck",
            client_secret="cs",
            access_token="at",
            refresh_token="rt",
        )
        assert adapter._use_browser is False

    def test_neither_mode_set(self) -> None:
        adapter = TikTokAdapter()
        assert adapter._use_browser is False

    def test_build_caption(self) -> None:
        video = VideoPost(
            video=MediaAsset(uri="/tmp/test.mp4", mime_type="video/mp4"),
            caption="check this out",
            hashtags=["fyp", "viral"],
        )
        content = NormalisedContent(
            source=video,
            modality=ContentModality.VIDEO,
            text_segments=["check this out"],
            media_assets=[video.video],
            hashtags=["fyp", "viral"],
        )
        caption = TikTokAdapter._build_caption(content)
        assert "check this out" in caption
        assert "#fyp" in caption
        assert "#viral" in caption
        assert len(caption) <= 2200


# ---------------------------------------------------------------------------
# Bundle factory
# ---------------------------------------------------------------------------


class TestCreateTikTokBundle:
    def test_creates_valid_bundle(self) -> None:
        settings = TikTokSettings(
            tiktok_client_key="ck",
            tiktok_client_secret="cs",
            tiktok_access_token="at",
            tiktok_refresh_token="rt",
        )
        bundle = create_tiktok_bundle(settings)
        assert bundle.adapter.platform_name == "tiktok"
        assert bundle.renderer.platform_name == "tiktok"
        assert bundle.uploader.platform_name == "tiktok"

    def test_registers_in_adapter_registry(self) -> None:
        settings = TikTokSettings(
            tiktok_client_key="ck",
            tiktok_client_secret="cs",
            tiktok_access_token="at",
            tiktok_refresh_token="rt",
        )
        bundle = create_tiktok_bundle(settings)
        registry = AdapterRegistry()
        registry.register(bundle)
        assert "tiktok" in registry.list_platforms()
        assert registry.supports("tiktok", ContentModality.VIDEO)


# ---------------------------------------------------------------------------
# TikTokAPIError
# ---------------------------------------------------------------------------


class TestTikTokAPIError:
    def test_with_known_hint(self) -> None:
        err = TikTokAPIError(401, "access_token_invalid", "token expired")
        assert "access_token_invalid" in str(err)
        assert "Fix:" in str(err)

    def test_with_unknown_code(self) -> None:
        err = TikTokAPIError(500, "unknown_code", "server error")
        assert "unknown_code" in str(err)
        assert "server error" in str(err)
