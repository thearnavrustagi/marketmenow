from __future__ import annotations

import pytest

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
from marketmenow.exceptions import UnsupportedModalityError
from marketmenow.models.content import (
    BaseContent,
    ContentModality,
    MediaAsset,
)
from marketmenow.normaliser import ContentNormaliser

normaliser = ContentNormaliser()


# ---------------------------------------------------------------------------
# VideoPost
# ---------------------------------------------------------------------------


class TestNormaliseVideo:
    def test_basic(self) -> None:
        v = make_video()
        n = normaliser.normalise(v)
        assert n.modality == ContentModality.VIDEO
        assert len(n.media_assets) == 1
        assert n.media_assets[0].mime_type == "video/mp4"
        assert n.text_segments == ["Check this out"]
        assert n.hashtags == ["ai", "tech"]

    def test_with_thumbnail(self) -> None:
        thumb = MediaAsset(uri="thumb.jpg", mime_type="image/jpeg")
        v = make_video(thumbnail=thumb)
        n = normaliser.normalise(v)
        assert len(n.media_assets) == 2
        assert n.media_assets[1] == thumb

    def test_empty_caption(self) -> None:
        v = make_video(caption="")
        n = normaliser.normalise(v)
        assert n.text_segments == []

    def test_source_preserved(self) -> None:
        v = make_video()
        n = normaliser.normalise(v)
        assert n.source is v


# ---------------------------------------------------------------------------
# ImagePost
# ---------------------------------------------------------------------------


class TestNormaliseImage:
    def test_basic(self) -> None:
        img = make_image()
        n = normaliser.normalise(img)
        assert n.modality == ContentModality.IMAGE
        assert len(n.media_assets) == 1
        assert n.text_segments == ["Beautiful shot"]

    def test_empty_caption(self) -> None:
        img = make_image(caption="")
        n = normaliser.normalise(img)
        assert n.text_segments == []

    def test_multiple_images(self) -> None:
        imgs = [MediaAsset(uri=f"img{i}.png", mime_type="image/png") for i in range(3)]
        post = make_image(images=imgs)
        n = normaliser.normalise(post)
        assert len(n.media_assets) == 3


# ---------------------------------------------------------------------------
# Thread
# ---------------------------------------------------------------------------


class TestNormaliseThread:
    def test_text_from_all_entries(self) -> None:
        t = make_thread()
        n = normaliser.normalise(t)
        assert n.modality == ContentModality.THREAD
        assert n.text_segments == ["First tweet", "Second tweet"]

    def test_media_flattened(self) -> None:
        t = make_thread()
        n = normaliser.normalise(t)
        assert len(n.media_assets) == 1


# ---------------------------------------------------------------------------
# DirectMessage
# ---------------------------------------------------------------------------


class TestNormaliseDM:
    def test_basic(self) -> None:
        dm = make_dm()
        n = normaliser.normalise(dm)
        assert n.modality == ContentModality.DIRECT_MESSAGE
        assert n.text_segments == ["Hello!"]
        assert n.recipient_handles == ["@user"]
        assert n.subject == "Greeting"

    def test_attachments(self) -> None:
        attach = MediaAsset(uri="file.pdf", mime_type="application/pdf")
        dm = make_dm(attachments=[attach])
        n = normaliser.normalise(dm)
        assert len(n.media_assets) == 1


# ---------------------------------------------------------------------------
# Reply
# ---------------------------------------------------------------------------


class TestNormaliseReply:
    def test_basic(self) -> None:
        r = make_reply()
        n = normaliser.normalise(r)
        assert n.modality == ContentModality.REPLY
        assert n.text_segments == ["Great point!"]
        assert n.extra["in_reply_to_url"] == "https://twitter.com/user/status/123"
        assert n.extra["in_reply_to_platform_id"] == ""

    def test_with_platform_id(self) -> None:
        r = make_reply(in_reply_to_platform_id="12345")
        n = normaliser.normalise(r)
        assert n.extra["in_reply_to_platform_id"] == "12345"

    def test_media(self) -> None:
        m = MediaAsset(uri="reply.png", mime_type="image/png")
        r = make_reply(media=[m])
        n = normaliser.normalise(r)
        assert len(n.media_assets) == 1


# ---------------------------------------------------------------------------
# TextPost
# ---------------------------------------------------------------------------


class TestNormaliseTextPost:
    def test_basic(self) -> None:
        t = make_text_post()
        n = normaliser.normalise(t)
        assert n.modality == ContentModality.TEXT_POST
        assert n.text_segments == ["Just sharing a thought"]
        assert n.hashtags == ["thoughts"]
        assert n.media_assets == []

    def test_empty_body(self) -> None:
        t = make_text_post(body="")
        n = normaliser.normalise(t)
        assert n.text_segments == []


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


class TestNormaliseDocument:
    def test_basic(self) -> None:
        d = make_document()
        n = normaliser.normalise(d)
        assert n.modality == ContentModality.DOCUMENT
        assert len(n.media_assets) == 1
        assert n.extra["document_title"] == "Whitepaper"
        assert n.text_segments == ["Read our latest whitepaper"]

    def test_empty_caption(self) -> None:
        d = make_document(caption="")
        n = normaliser.normalise(d)
        assert n.text_segments == []


# ---------------------------------------------------------------------------
# Article
# ---------------------------------------------------------------------------


class TestNormaliseArticle:
    def test_basic(self) -> None:
        a = make_article()
        n = normaliser.normalise(a)
        assert n.modality == ContentModality.ARTICLE
        assert n.extra["article_url"] == "https://blog.example.com/post"
        assert n.text_segments == ["Interesting read"]
        assert n.media_assets == []

    def test_empty_commentary(self) -> None:
        a = make_article(commentary="")
        n = normaliser.normalise(a)
        assert n.text_segments == []


# ---------------------------------------------------------------------------
# Poll
# ---------------------------------------------------------------------------


class TestNormalisePoll:
    def test_basic(self) -> None:
        p = make_poll()
        n = normaliser.normalise(p)
        assert n.modality == ContentModality.POLL
        assert n.extra["poll_question"] == "Which is better?"
        assert n.extra["poll_options"] == ["A", "B", "C"]
        assert n.extra["poll_duration_days"] == 3
        assert n.media_assets == []

    def test_commentary(self) -> None:
        p = make_poll(commentary="Vote now!")
        n = normaliser.normalise(p)
        assert n.text_segments == ["Vote now!"]

    def test_empty_commentary(self) -> None:
        p = make_poll(commentary="")
        n = normaliser.normalise(p)
        assert n.text_segments == []


# ---------------------------------------------------------------------------
# Unknown modality
# ---------------------------------------------------------------------------


class TestNormaliseUnknown:
    def test_raises(self) -> None:
        bogus = BaseContent(modality=ContentModality.VIDEO)
        with pytest.raises(UnsupportedModalityError):
            normaliser.normalise(bogus)
