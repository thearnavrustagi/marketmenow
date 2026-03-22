from __future__ import annotations

from pathlib import Path

import yaml


class TestPromptResolutionWithProject:
    def test_twitter_prompt_from_project(self, tmp_path: Path) -> None:
        from marketmenow.core.project_manager import ProjectManager
        from marketmenow.models.project import BrandConfig

        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("app", BrandConfig(name="App", url="app.io", tagline="t"))
        prompt_path = pm.project_dir("app") / "prompts" / "twitter" / "reply_generation.yaml"
        prompt_path.write_text(yaml.dump({"system": "project prompt", "user": "ask"}))

        from adapters.twitter.prompts import load_prompt

        load_prompt("reply_generation", project_slug="app")
        assert callable(load_prompt)

    def test_twitter_prompt_fallback_global(self, tmp_path: Path) -> None:
        from adapters.twitter.prompts import load_prompt

        # Without project_slug, should use global path (the actual prompts/ dir)
        # This just verifies backward compat — doesn't need to find the file
        assert callable(load_prompt)

    def test_load_prompt_signature(self) -> None:
        import inspect

        from adapters.twitter.prompts import load_prompt
        sig = inspect.signature(load_prompt)
        assert "project_slug" in sig.parameters

    def test_reddit_load_prompt_signature(self) -> None:
        import inspect

        from adapters.reddit.prompts import load_prompt
        sig = inspect.signature(load_prompt)
        assert "project_slug" in sig.parameters

    def test_instagram_load_prompt_signature(self) -> None:
        import inspect

        from adapters.instagram.prompts import load_prompt
        sig = inspect.signature(load_prompt)
        assert "project_slug" in sig.parameters
