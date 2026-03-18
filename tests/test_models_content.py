from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from conftest import (
    make_article,
    make_dm,
    make_document,
    make_image,
    make_poll,
    make_reply,
    make_text_post,
    make_thread,
    make_video,
)
from marketmenow.models.content import (
    Article,
    ContentModality,
    DirectMessage,
    Document,
    ImagePost,
    MediaAsset,
    Poll,
    Recipient,
    TextPost,
    Thread,
    ThreadEntry,
)

# ---------------------------------------------------------------------------
# MediaAsset
# ---------------------------------------------------------------------------


class TestMediaAsset:
    def test_construction(self) -> None:
        asset = MediaAsset(uri="file:///a.png", mime_type="image/png")
        assert asset.uri == "file:///a.png"
        assert asset.mime_type == "image/png"
        assert asset.alt_text == ""
        assert asset.duration_seconds is None
        assert asset.width is None
        assert asset.height is None

    def test_full_fields(self) -> None:
        asset = MediaAsset(
            uri="https://cdn.example.com/v.mp4",
            mime_type="video/mp4",
            alt_text="A demo video",
            duration_seconds=42.5,
            width=1920,
            height=1080,
        )
        assert asset.duration_seconds == 42.5
        assert asset.width == 1920

    def test_frozen(self) -> None:
        asset = MediaAsset(uri="x", mime_type="y")
        with pytest.raises(ValidationError):
            asset.uri = "z"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BaseContent defaults
# ---------------------------------------------------------------------------


class TestBaseContentDefaults:
    def test_auto_id(self) -> None:
        post = make_text_post()
        assert isinstance(post.id, UUID)

    def test_auto_created_at(self) -> None:
        before = datetime.now(UTC)
        post = make_text_post()
        after = datetime.now(UTC)
        assert before <= post.created_at <= after

    def test_metadata_default(self) -> None:
        post = make_text_post()
        assert post.metadata == {}


# ---------------------------------------------------------------------------
# VideoPost
# ---------------------------------------------------------------------------


class TestVideoPost:
    def test_modality(self) -> None:
        v = make_video()
        assert v.modality == ContentModality.VIDEO

    def test_thumbnail_optional(self) -> None:
        v = make_video()
        assert v.thumbnail is None

    def test_with_thumbnail(self) -> None:
        thumb = MediaAsset(uri="thumb.jpg", mime_type="image/jpeg")
        v = make_video(thumbnail=thumb)
        assert v.thumbnail == thumb

    def test_frozen(self) -> None:
        v = make_video()
        with pytest.raises(ValidationError):
            v.caption = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ImagePost
# ---------------------------------------------------------------------------


class TestImagePost:
    def test_modality(self) -> None:
        assert make_image().modality == ContentModality.IMAGE

    def test_min_one_image(self) -> None:
        with pytest.raises(ValidationError, match="images"):
            ImagePost(images=[])

    def test_multiple_images(self) -> None:
        imgs = [MediaAsset(uri=f"img{i}.png", mime_type="image/png") for i in range(5)]
        post = make_image(images=imgs)
        assert len(post.images) == 5


# ---------------------------------------------------------------------------
# Thread
# ---------------------------------------------------------------------------


class TestThread:
    def test_modality(self) -> None:
        assert make_thread().modality == ContentModality.THREAD

    def test_min_one_entry(self) -> None:
        with pytest.raises(ValidationError, match="entries"):
            Thread(entries=[])

    def test_entries_preserved(self) -> None:
        t = make_thread()
        assert len(t.entries) == 2
        assert t.entries[0].text == "First tweet"


class TestThreadEntry:
    def test_no_media(self) -> None:
        entry = ThreadEntry(text="hello")
        assert entry.media == []

    def test_with_media(self) -> None:
        m = MediaAsset(uri="a.png", mime_type="image/png")
        entry = ThreadEntry(text="hello", media=[m])
        assert len(entry.media) == 1


# ---------------------------------------------------------------------------
# DirectMessage
# ---------------------------------------------------------------------------


class TestDirectMessage:
    def test_modality(self) -> None:
        assert make_dm().modality == ContentModality.DIRECT_MESSAGE

    def test_min_one_recipient(self) -> None:
        with pytest.raises(ValidationError, match="recipients"):
            DirectMessage(recipients=[], body="hi")

    def test_subject_optional(self) -> None:
        dm = DirectMessage(
            recipients=[Recipient(handle="@a")],
            body="hello",
        )
        assert dm.subject is None

    def test_attachments_default(self) -> None:
        assert make_dm().attachments == []


# ---------------------------------------------------------------------------
# Reply
# ---------------------------------------------------------------------------


class TestReply:
    def test_modality(self) -> None:
        assert make_reply().modality == ContentModality.REPLY

    def test_platform_id_optional(self) -> None:
        r = make_reply()
        assert r.in_reply_to_platform_id is None

    def test_media_default(self) -> None:
        assert make_reply().media == []


# ---------------------------------------------------------------------------
# TextPost
# ---------------------------------------------------------------------------


class TestTextPost:
    def test_modality(self) -> None:
        assert make_text_post().modality == ContentModality.TEXT_POST

    def test_hashtags_default(self) -> None:
        post = TextPost(body="plain")
        assert post.hashtags == []


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


class TestDocument:
    def test_modality(self) -> None:
        assert make_document().modality == ContentModality.DOCUMENT

    def test_title_default(self) -> None:
        asset = MediaAsset(uri="d.pdf", mime_type="application/pdf")
        doc = Document(file=asset)
        assert doc.title == ""
        assert doc.caption == ""


# ---------------------------------------------------------------------------
# Article
# ---------------------------------------------------------------------------


class TestArticle:
    def test_modality(self) -> None:
        assert make_article().modality == ContentModality.ARTICLE

    def test_commentary_default(self) -> None:
        a = Article(url="https://example.com")
        assert a.commentary == ""


# ---------------------------------------------------------------------------
# Poll
# ---------------------------------------------------------------------------


class TestPoll:
    def test_modality(self) -> None:
        assert make_poll().modality == ContentModality.POLL

    def test_min_two_options(self) -> None:
        with pytest.raises(ValidationError, match="options"):
            Poll(question="Q?", options=["only_one"])

    def test_max_four_options(self) -> None:
        with pytest.raises(ValidationError, match="options"):
            Poll(question="Q?", options=["a", "b", "c", "d", "e"])

    def test_duration_too_low(self) -> None:
        with pytest.raises(ValidationError, match="duration_days"):
            Poll(question="Q?", options=["a", "b"], duration_days=0)

    def test_duration_too_high(self) -> None:
        with pytest.raises(ValidationError, match="duration_days"):
            Poll(question="Q?", options=["a", "b"], duration_days=15)

    def test_duration_default(self) -> None:
        assert make_poll().duration_days == 3

    def test_boundary_two_options(self) -> None:
        p = Poll(question="Q?", options=["a", "b"])
        assert len(p.options) == 2

    def test_boundary_four_options(self) -> None:
        p = Poll(question="Q?", options=["a", "b", "c", "d"])
        assert len(p.options) == 4

    def test_boundary_duration_1(self) -> None:
        p = Poll(question="Q?", options=["a", "b"], duration_days=1)
        assert p.duration_days == 1

    def test_boundary_duration_14(self) -> None:
        p = Poll(question="Q?", options=["a", "b"], duration_days=14)
        assert p.duration_days == 14


# ---------------------------------------------------------------------------
# ContentModality enum
# ---------------------------------------------------------------------------


class TestContentModality:
    def test_all_nine_values(self) -> None:
        assert len(ContentModality) == 9

    def test_string_values(self) -> None:
        assert ContentModality.VIDEO.value == "video"
        assert ContentModality.POLL.value == "poll"
        assert ContentModality.DIRECT_MESSAGE.value == "direct_message"
