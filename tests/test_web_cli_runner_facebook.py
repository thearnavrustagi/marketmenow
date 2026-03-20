from __future__ import annotations

from web.cli_runner import get_builders, get_meta


class TestFacebookMeta:
    def test_facebook_post_meta_exists(self) -> None:
        meta = get_meta("facebook", "post")
        assert meta is not None
        assert meta["label"] == "Facebook Post"
        assert meta["modality"] == "text_post"

    def test_facebook_page_post_meta_exists(self) -> None:
        meta = get_meta("facebook", "page_post")
        assert meta is not None
        assert meta["label"] == "Facebook Page Post"
        assert meta["modality"] == "text_post"


class TestFacebookBuilders:
    def test_facebook_generate_uses_status_command(self) -> None:
        builders = get_builders("facebook", "post")
        assert builders is not None

        build_generate, _build_publish = builders
        command = build_generate({}, "/tmp/out")

        assert command == ["mmn", "facebook", "status"]

    def test_facebook_publish_builds_flags(self) -> None:
        builders = get_builders("facebook", "post")
        assert builders is not None

        _build_generate, build_publish = builders
        command = build_publish(
            {
                "text": "Hello Facebook",
                "hashtags": "marketing,automation",
                "image": "one.png, two.png",
            },
            "/tmp/out",
        )

        assert command == [
            "mmn",
            "facebook",
            "post",
            "--text",
            "Hello Facebook",
            "--image",
            "one.png",
            "--image",
            "two.png",
            "--hashtags",
            "marketing,automation",
        ]

    def test_facebook_publish_has_default_text(self) -> None:
        builders = get_builders("facebook", "post")
        assert builders is not None

        _build_generate, build_publish = builders
        command = build_publish({}, "/tmp/out")

        assert command == [
            "mmn",
            "facebook",
            "post",
            "--text",
            "Automated Facebook post from MarketMeNow.",
        ]

    def test_facebook_page_post_generate_uses_status_command(self) -> None:
        builders = get_builders("facebook", "page_post")
        assert builders is not None

        build_generate, _build_publish = builders
        command = build_generate({}, "/tmp/out")

        assert command == ["mmn", "facebook", "status"]

    def test_facebook_page_post_publish_builds_flags(self) -> None:
        builders = get_builders("facebook", "page_post")
        assert builders is not None

        _build_generate, build_publish = builders
        command = build_publish(
            {
                "page": "gradeasy",
                "text": "Hello Page",
                "hashtags": "marketing,automation",
                "image": "one.png, two.png",
            },
            "/tmp/out",
        )

        assert command == [
            "mmn",
            "facebook",
            "page-post",
            "--page",
            "gradeasy",
            "--text",
            "Hello Page",
            "--image",
            "one.png",
            "--image",
            "two.png",
            "--hashtags",
            "marketing,automation",
        ]

    def test_facebook_page_post_publish_has_default_text(self) -> None:
        builders = get_builders("facebook", "page_post")
        assert builders is not None

        _build_generate, build_publish = builders
        command = build_publish({}, "/tmp/out")

        assert command == [
            "mmn",
            "facebook",
            "page-post",
            "--text",
            "Automated Facebook page post from MarketMeNow.",
        ]
