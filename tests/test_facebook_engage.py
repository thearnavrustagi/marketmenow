from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from adapters.facebook.discovery import DiscoveredGroupPost, GroupPostDiscoverer
from adapters.facebook.orchestrator import EngagementOrchestrator, GeneratedComment
from adapters.facebook.settings import FacebookSettings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_discovered_post(
    group_url: str = "https://www.facebook.com/groups/teachers",
    group_name: str = "Teachers",
    post_url: str = "https://www.facebook.com/groups/teachers/posts/123",
    post_text: str = "I'm so tired of grading essays, any tips for speeding things up?",
    post_author: str = "Jane Teacher",
    reactions_count: int = 15,
    comments_count: int = 3,
) -> DiscoveredGroupPost:
    return DiscoveredGroupPost(
        group_url=group_url,
        group_name=group_name,
        post_url=post_url,
        post_text=post_text,
        post_author=post_author,
        reactions_count=reactions_count,
        comments_count=comments_count,
    )


def _make_generated_comment(
    post_url: str = "https://www.facebook.com/groups/teachers/posts/123",
    comment_text: str = "Have you tried batch grading in 25-minute sprints?",
) -> GeneratedComment:
    return GeneratedComment(
        group_url="https://www.facebook.com/groups/teachers",
        group_name="Teachers",
        post_url=post_url,
        post_text="I'm so tired of grading essays...",
        post_author="Jane Teacher",
        reactions_count=15,
        comments_count=3,
        comment_text=comment_text,
    )


@pytest.fixture
def fb_settings(tmp_path: Path) -> FacebookSettings:
    targets_yaml = tmp_path / "targets.yaml"
    targets_yaml.write_text(
        "groups:\n"
        '  - url: "https://www.facebook.com/groups/teachers"\n'
        '    name: "Teachers"\n'
        '  - url: "https://www.facebook.com/groups/edtech"\n'
        '    name: "EdTech"\n',
        encoding="utf-8",
    )
    return FacebookSettings(
        targets_path=targets_yaml,
        comment_history_path=tmp_path / "comment_history.json",
        audit_log_path=tmp_path / "audit.jsonl",
        max_comments_per_day=3,
        mention_rate=10,
        min_delay_seconds=0,
        max_delay_seconds=0,
    )


# ---------------------------------------------------------------------------
# discovery.py
# ---------------------------------------------------------------------------


class TestGroupPostDiscoverer:
    def test_already_commented_initially_empty(self, tmp_path: Path) -> None:
        browser = MagicMock()
        discoverer = GroupPostDiscoverer(
            browser,
            comment_history_path=tmp_path / "history.json",
        )
        assert not discoverer.already_commented("https://fb.com/post/1")

    def test_mark_commented_persists(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.json"
        browser = MagicMock()
        discoverer = GroupPostDiscoverer(browser, comment_history_path=history_path)
        discoverer.mark_commented("https://fb.com/post/1")

        discoverer2 = GroupPostDiscoverer(browser, comment_history_path=history_path)
        assert discoverer2.already_commented("https://fb.com/post/1")

    def test_is_eligible_skips_short_text(self, tmp_path: Path) -> None:
        browser = MagicMock()
        discoverer = GroupPostDiscoverer(
            browser,
            comment_history_path=tmp_path / "history.json",
        )
        short_post = _make_discovered_post(post_text="short")
        assert not discoverer._is_eligible(short_post)

    def test_is_eligible_skips_already_commented(self, tmp_path: Path) -> None:
        browser = MagicMock()
        discoverer = GroupPostDiscoverer(
            browser,
            comment_history_path=tmp_path / "history.json",
        )
        post = _make_discovered_post()
        discoverer.mark_commented(post.post_url)
        assert not discoverer._is_eligible(post)

    def test_is_eligible_accepts_valid_post(self, tmp_path: Path) -> None:
        browser = MagicMock()
        discoverer = GroupPostDiscoverer(
            browser,
            comment_history_path=tmp_path / "history.json",
        )
        post = _make_discovered_post()
        assert discoverer._is_eligible(post)

    def test_dedupe_removes_duplicates(self, tmp_path: Path) -> None:
        posts = [
            _make_discovered_post(post_url="https://fb.com/post/1"),
            _make_discovered_post(post_url="https://fb.com/post/1"),
            _make_discovered_post(post_url="https://fb.com/post/2"),
        ]
        unique = GroupPostDiscoverer._dedupe(posts)
        assert len(unique) == 2

    async def test_discover_group_posts_calls_browser(self, tmp_path: Path) -> None:
        browser = AsyncMock()
        browser.scrape_group_feed = AsyncMock(
            return_value=[
                {
                    "post_url": "https://fb.com/post/1",
                    "post_text": "How do you handle late work grading? I'm drowning in papers.",
                    "post_author": "Jane",
                    "reactions": "10",
                    "comments": "5",
                },
                {
                    "post_url": "https://fb.com/post/2",
                    "post_text": "Looking for a better rubric system for my AP English class.",
                    "post_author": "Bob",
                    "reactions": "20",
                    "comments": "8",
                },
            ]
        )
        discoverer = GroupPostDiscoverer(
            browser,
            comment_history_path=tmp_path / "history.json",
        )
        posts = await discoverer.discover_group_posts(
            "https://fb.com/groups/teachers",
            "Teachers",
            max_posts=5,
        )
        assert len(posts) == 2
        assert posts[0].post_author == "Jane"
        browser.scrape_group_feed.assert_called_once()


# ---------------------------------------------------------------------------
# orchestrator.py — GeneratedComment model
# ---------------------------------------------------------------------------


class TestGeneratedComment:
    def test_frozen_model(self) -> None:
        comment = _make_generated_comment()
        assert comment.group_name == "Teachers"
        assert comment.comment_text == "Have you tried batch grading in 25-minute sprints?"
        with pytest.raises(ValidationError, match="frozen"):
            comment.comment_text = "new text"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# orchestrator.py — EngagementOrchestrator
# ---------------------------------------------------------------------------


class TestEngagementOrchestrator:
    async def test_generate_only_returns_comments(self, fb_settings: FacebookSettings) -> None:
        mock_browser = AsyncMock()
        mock_browser.scrape_group_feed = AsyncMock(
            return_value=[
                {
                    "post_url": "https://fb.com/post/1",
                    "post_text": "I spend 3 hours every night grading papers and I'm burning out.",
                    "post_author": "Jane",
                    "reactions": "10",
                    "comments": "5",
                },
            ]
        )

        orchestrator = EngagementOrchestrator(fb_settings, mock_browser)

        with patch(
            "adapters.facebook.comment_generator.CommentGenerator.generate_comment",
            new_callable=AsyncMock,
            return_value="I totally feel this. When I was teaching 5 classes...",
        ):
            results = await orchestrator.generate_only()

        assert len(results) >= 1
        assert results[0].comment_text == "I totally feel this. When I was teaching 5 classes..."

    async def test_comment_from_list_posts_and_tracks(self, fb_settings: FacebookSettings) -> None:
        mock_browser = AsyncMock()
        mock_browser.comment_on_group_post = AsyncMock(return_value=True)

        orchestrator = EngagementOrchestrator(fb_settings, mock_browser)

        comments = [
            _make_generated_comment(
                post_url="https://fb.com/post/1",
                comment_text="Great question!",
            ),
            _make_generated_comment(
                post_url="https://fb.com/post/2",
                comment_text="Have you tried rubric templates?",
            ),
        ]

        stats = await orchestrator.comment_from_list(comments)

        assert stats.total_succeeded == 2
        assert stats.total_failed == 0
        assert mock_browser.comment_on_group_post.call_count == 2

        assert fb_settings.audit_log_path.exists()

    async def test_comment_from_list_handles_failure(self, fb_settings: FacebookSettings) -> None:
        mock_browser = AsyncMock()
        mock_browser.comment_on_group_post = AsyncMock(return_value=False)

        orchestrator = EngagementOrchestrator(fb_settings, mock_browser)
        comments = [_make_generated_comment()]

        stats = await orchestrator.comment_from_list(comments)

        assert stats.total_succeeded == 0
        assert stats.total_failed == 1

    async def test_generate_only_empty_targets(self, tmp_path: Path) -> None:
        empty_targets = tmp_path / "empty.yaml"
        empty_targets.write_text("groups: []\n", encoding="utf-8")
        settings = FacebookSettings(
            targets_path=empty_targets,
            comment_history_path=tmp_path / "h.json",
            audit_log_path=tmp_path / "a.jsonl",
        )
        mock_browser = AsyncMock()
        orchestrator = EngagementOrchestrator(settings, mock_browser)

        results = await orchestrator.generate_only()
        assert results == []


# ---------------------------------------------------------------------------
# settings.py
# ---------------------------------------------------------------------------


class TestFacebookSettings:
    def test_defaults(self) -> None:
        settings = FacebookSettings()
        assert settings.max_comments_per_day == 5
        assert settings.mention_rate == 10
        assert settings.min_delay_seconds == 120
        assert settings.max_delay_seconds == 300
        assert settings.cooldown_hours == 12
        assert settings.gemini_model == "gemini-2.5-flash"

    def test_engagement_paths_default(self) -> None:
        settings = FacebookSettings()
        assert "facebook" in str(settings.audit_log_path)
        assert "facebook" in str(settings.comment_history_path)


# ---------------------------------------------------------------------------
# workflow definition
# ---------------------------------------------------------------------------


class TestFacebookEngageWorkflow:
    def test_workflow_definition(self) -> None:
        from marketmenow.workflows.facebook_engage import workflow

        assert workflow.name == "facebook-engage"
        assert len(workflow.steps) == 2
        assert workflow.steps[0].name == "discover-facebook"
        assert workflow.steps[1].name == "post-replies"

    def test_workflow_params(self) -> None:
        from marketmenow.workflows.facebook_engage import workflow

        param_names = {p.name for p in workflow.params}
        assert "max_comments" in param_names
        assert "headless" in param_names


# ---------------------------------------------------------------------------
# workflow registry
# ---------------------------------------------------------------------------


class TestFacebookEngageRegistered:
    def test_facebook_engage_in_registry(self) -> None:
        from marketmenow.core.workflow_registry import build_workflow_registry

        registry = build_workflow_registry()
        names = [w.name for w in registry.list_all()]
        assert "facebook-engage" in names


# ---------------------------------------------------------------------------
# discover_posts step accepts facebook
# ---------------------------------------------------------------------------


class TestDiscoverPostsStepFacebook:
    def test_accepts_facebook_platform(self) -> None:
        from marketmenow.steps.discover_posts import DiscoverPostsStep

        step = DiscoverPostsStep(platform="facebook")
        assert step.name == "discover-facebook"
        assert "facebook" in step.description.lower()

    def test_rejects_unknown_platform(self) -> None:
        from marketmenow.steps.discover_posts import DiscoverPostsStep

        with pytest.raises(ValueError, match="Unsupported"):
            DiscoverPostsStep(platform="myspace")
