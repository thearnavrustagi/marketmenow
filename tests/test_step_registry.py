from __future__ import annotations

from unittest.mock import MagicMock, patch

from marketmenow.steps.registry import get_step_class, list_steps


def _patch_llm_provider():
    """Patch create_llm_provider in step modules that call it at construction time."""
    mock_provider = MagicMock()
    return [
        patch(
            "marketmenow.steps.repurpose_content.create_llm_provider", return_value=mock_provider
        ),
        patch("marketmenow.steps.prepare_youtube.create_llm_provider", return_value=mock_provider),
    ]


class TestGetStepClass:
    def test_known_step(self) -> None:
        cls = get_step_class("generate-reel")
        assert cls is not None
        assert cls.__name__ == "GenerateReelStep"

    def test_all_registered_steps(self) -> None:
        expected = {
            "generate-reel",
            "generate-carousel",
            "generate-thread",
            "generate-reddit-posts",
            "generate-replies",
            "post-to-platform",
            "post-to-subreddits",
            "post-replies",
            "discover-posts",
            "linkedin-post",
            "send-emails",
            "youtube-upload",
        }
        for name in expected:
            cls = get_step_class(name)
            assert cls is not None, f"Step '{name}' not found"

    def test_unknown_raises(self) -> None:
        import pytest

        with pytest.raises(KeyError, match="Unknown step"):
            get_step_class("nonexistent-step")


class TestListSteps:
    def test_returns_list(self) -> None:
        for p in _patch_llm_provider():
            p.start()
        try:
            steps = list_steps()
        finally:
            for p in _patch_llm_provider():
                p.stop()
            patch.stopall()
        assert isinstance(steps, list)
        assert len(steps) >= 10

    def test_step_info_fields(self) -> None:
        for p in _patch_llm_provider():
            p.start()
        try:
            steps = list_steps()
        finally:
            patch.stopall()
        for info in steps:
            assert info.name
            assert info.description
            assert info.cls is not None

    def test_names_are_unique(self) -> None:
        for p in _patch_llm_provider():
            p.start()
        try:
            steps = list_steps()
        finally:
            patch.stopall()
        names = [s.name for s in steps]
        assert len(names) == len(set(names))
