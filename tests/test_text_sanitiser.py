from __future__ import annotations

from conftest import make_text_post
from marketmenow.core.text_sanitiser import sanitise_text
from marketmenow.models.content import ContentModality, MediaAsset
from marketmenow.normaliser import NormalisedContent


def _make_normalised(**overrides: object) -> NormalisedContent:
    defaults: dict[str, object] = {
        "source": make_text_post(),
        "modality": ContentModality.TEXT_POST,
        "text_segments": [],
        "media_assets": [],
    }
    return NormalisedContent(**(defaults | overrides))


class TestSanitiseText:
    def test_em_dash_replaced_in_text_segments(self) -> None:
        nc = _make_normalised(text_segments=["Hello \u2014 world", "foo\u2014bar"])
        result = sanitise_text(nc)
        assert result.text_segments == ["Hello - world", "foo-bar"]

    def test_en_dash_replaced_in_text_segments(self) -> None:
        nc = _make_normalised(text_segments=["pages 1\u20135"])
        result = sanitise_text(nc)
        assert result.text_segments == ["pages 1-5"]

    def test_subject_sanitised(self) -> None:
        nc = _make_normalised(subject="Re: Update \u2014 Q1")
        result = sanitise_text(nc)
        assert result.subject == "Re: Update - Q1"

    def test_none_subject_unchanged(self) -> None:
        nc = _make_normalised(subject=None)
        result = sanitise_text(nc)
        assert result.subject is None

    def test_hashtags_sanitised(self) -> None:
        nc = _make_normalised(hashtags=["AI\u2014tools"])
        result = sanitise_text(nc)
        assert result.hashtags == ["AI-tools"]

    def test_extra_string_values_sanitised(self) -> None:
        nc = _make_normalised(extra={"poll_question": "Which \u2014 option?"})
        result = sanitise_text(nc)
        assert result.extra["poll_question"] == "Which - option?"

    def test_extra_list_of_strings_sanitised(self) -> None:
        nc = _make_normalised(extra={"poll_options": ["A \u2014 first", "B \u2014 second"]})
        result = sanitise_text(nc)
        assert result.extra["poll_options"] == ["A - first", "B - second"]

    def test_extra_non_string_values_preserved(self) -> None:
        nc = _make_normalised(extra={"count": 42, "flag": True})
        result = sanitise_text(nc)
        assert result.extra["count"] == 42
        assert result.extra["flag"] is True

    def test_clean_text_passes_through(self) -> None:
        nc = _make_normalised(
            text_segments=["No dashes here"],
            subject="Clean subject",
        )
        result = sanitise_text(nc)
        assert result.text_segments == ["No dashes here"]
        assert result.subject == "Clean subject"

    def test_media_assets_untouched(self) -> None:
        asset = MediaAsset(uri="file:///img.png", mime_type="image/png")
        nc = _make_normalised(media_assets=[asset])
        result = sanitise_text(nc)
        assert result.media_assets == [asset]
