from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from marketmenow.core.prompt_builder import BuiltPrompt, PromptBuilder
from marketmenow.models.project import BrandConfig, PersonaConfig


@pytest.fixture
def brand() -> BrandConfig:
    return BrandConfig(
        name="TestBrand",
        url="testbrand.com",
        tagline="AI-powered widget maker",
        value_prop="Saves 10 hours/week",
        features=["Fast widgets", "Free to try"],
    )


@pytest.fixture
def persona() -> PersonaConfig:
    return PersonaConfig(
        name="default",
        description="Witty and helpful",
        voice="Confident and friendly",
        tone="Casual but never sloppy",
        example_phrases=["let's go", "ngl", "this slaps"],
        platform_overrides={
            "reddit": {"tone": "Helpful and direct"},
        },
    )


@pytest.fixture
def builder() -> PromptBuilder:
    return PromptBuilder()


def test_prompt_builder_build_decomposed(
    tmp_path: Path, brand: BrandConfig, persona: PersonaConfig
) -> None:
    """When persona.yaml + functions/reply.yaml exist, build assembles them."""
    project_dir = tmp_path / "projects" / "test" / "prompts" / "twitter"
    project_dir.mkdir(parents=True)

    persona_yaml = {
        "system": "You ARE {{ brand.name }}. {{ persona.voice }}.",
    }
    (project_dir / "persona.yaml").write_text(
        yaml.dump(persona_yaml),
        encoding="utf-8",
    )

    func_dir = tmp_path / "prompts" / "twitter" / "functions"
    func_dir.mkdir(parents=True)
    func_yaml = {
        "system": "RULES: Keep it short.",
        "user": "{{ icl_block }}POST by @{{ author_handle }}: {{ post_text }}",
    }
    (func_dir / "reply.yaml").write_text(
        yaml.dump(func_yaml),
        encoding="utf-8",
    )

    import marketmenow.core.prompt_builder as pb

    orig_projects = pb._PROJECTS_DIR
    orig_prompts = pb._PROMPTS_DIR
    pb._PROJECTS_DIR = tmp_path / "projects"
    pb._PROMPTS_DIR = tmp_path / "prompts"

    try:
        builder = PromptBuilder()
        result = builder.build(
            platform="twitter",
            function="reply",
            persona=persona,
            brand=brand,
            template_vars={"author_handle": "alice", "post_text": "hello"},
            project_slug="test",
        )
        assert isinstance(result, BuiltPrompt)
        assert "TestBrand" in result.system
        assert "Confident and friendly" in result.system
        assert "RULES: Keep it short" in result.system
        assert "@alice" in result.user
    finally:
        pb._PROJECTS_DIR = orig_projects
        pb._PROMPTS_DIR = orig_prompts


def test_prompt_builder_build_legacy_fallback(
    tmp_path: Path, brand: BrandConfig, persona: PersonaConfig
) -> None:
    """When only a monolithic reply_generation.yaml exists, falls back to it."""
    prompts_dir = tmp_path / "prompts" / "twitter"
    prompts_dir.mkdir(parents=True)

    legacy = {
        "system": "You are {{ brand.name }}. mention_rate={{ mention_rate }}",
        "user": "{% if winning_examples %}EXAMPLES{% endif %}POST: {{ post_text }}",
    }
    (prompts_dir / "reply_generation.yaml").write_text(
        yaml.dump(legacy),
        encoding="utf-8",
    )

    import marketmenow.core.prompt_builder as pb

    orig_projects = pb._PROJECTS_DIR
    orig_prompts = pb._PROMPTS_DIR
    pb._PROJECTS_DIR = tmp_path / "projects"
    pb._PROMPTS_DIR = tmp_path / "prompts"

    try:
        builder = PromptBuilder()
        result = builder.build(
            platform="twitter",
            function="reply",
            persona=persona,
            brand=brand,
            template_vars={"mention_rate": 25, "post_text": "test"},
            project_slug=None,
        )
        assert "TestBrand" in result.system
        assert "mention_rate=25" in result.system
        assert "POST: test" in result.user
    finally:
        pb._PROJECTS_DIR = orig_projects
        pb._PROMPTS_DIR = orig_prompts


def test_prompt_builder_icl_block_rendered(
    tmp_path: Path, brand: BrandConfig, persona: PersonaConfig
) -> None:
    """ICL examples are rendered into the user prompt."""
    project_dir = tmp_path / "projects" / "test" / "prompts" / "twitter"
    project_dir.mkdir(parents=True)
    (project_dir / "persona.yaml").write_text(
        yaml.dump({"system": "Persona here."}),
        encoding="utf-8",
    )

    func_dir = tmp_path / "prompts" / "twitter" / "functions"
    func_dir.mkdir(parents=True)
    (func_dir / "reply.yaml").write_text(
        yaml.dump({"system": "Rules.", "user": "{{ icl_block }}TASK"}),
        encoding="utf-8",
    )

    import marketmenow.core.prompt_builder as pb

    orig_projects = pb._PROJECTS_DIR
    orig_prompts = pb._PROMPTS_DIR
    pb._PROJECTS_DIR = tmp_path / "projects"
    pb._PROMPTS_DIR = tmp_path / "prompts"

    try:
        builder = PromptBuilder()
        result = builder.build(
            platform="twitter",
            function="reply",
            persona=persona,
            brand=brand,
            icl_examples=[
                {
                    "parent_author": "bob",
                    "parent_text": "hey",
                    "our_reply": "yo",
                    "likes": 5,
                    "retweets": 1,
                },
            ],
            template_vars={},
            project_slug="test",
        )
        assert "bob" in result.user
        assert "yo" in result.user
        assert "5 likes" in result.user
    finally:
        pb._PROJECTS_DIR = orig_projects
        pb._PROMPTS_DIR = orig_prompts


def test_prompt_builder_no_icl_on_explore(
    tmp_path: Path, brand: BrandConfig, persona: PersonaConfig
) -> None:
    """When icl_examples is None (explore mode), no examples block appears."""
    project_dir = tmp_path / "projects" / "test" / "prompts" / "twitter"
    project_dir.mkdir(parents=True)
    (project_dir / "persona.yaml").write_text(
        yaml.dump({"system": "P."}),
        encoding="utf-8",
    )

    func_dir = tmp_path / "prompts" / "twitter" / "functions"
    func_dir.mkdir(parents=True)
    (func_dir / "reply.yaml").write_text(
        yaml.dump({"system": "R.", "user": "{{ icl_block }}TASK: {{ post_text }}"}),
        encoding="utf-8",
    )

    import marketmenow.core.prompt_builder as pb

    orig_projects = pb._PROJECTS_DIR
    orig_prompts = pb._PROMPTS_DIR
    pb._PROJECTS_DIR = tmp_path / "projects"
    pb._PROMPTS_DIR = tmp_path / "prompts"

    try:
        builder = PromptBuilder()
        result = builder.build(
            platform="twitter",
            function="reply",
            persona=persona,
            brand=brand,
            icl_examples=None,
            template_vars={"post_text": "hello world"},
            project_slug="test",
        )
        assert "WINNING EXAMPLES" not in result.user
        assert "TASK: hello world" in result.user
    finally:
        pb._PROJECTS_DIR = orig_projects
        pb._PROMPTS_DIR = orig_prompts


def test_prompt_builder_platform_override(
    tmp_path: Path, brand: BrandConfig, persona: PersonaConfig
) -> None:
    """Platform overrides from PersonaConfig are applied."""
    project_dir = tmp_path / "projects" / "test" / "prompts" / "reddit"
    project_dir.mkdir(parents=True)
    (project_dir / "persona.yaml").write_text(
        yaml.dump({"system": "Tone: {{ persona.tone }}"}),
        encoding="utf-8",
    )

    func_dir = tmp_path / "prompts" / "reddit" / "functions"
    func_dir.mkdir(parents=True)
    (func_dir / "comment.yaml").write_text(
        yaml.dump({"system": "Rules.", "user": "TASK"}),
        encoding="utf-8",
    )

    import marketmenow.core.prompt_builder as pb

    orig_projects = pb._PROJECTS_DIR
    orig_prompts = pb._PROMPTS_DIR
    pb._PROJECTS_DIR = tmp_path / "projects"
    pb._PROMPTS_DIR = tmp_path / "prompts"

    try:
        builder = PromptBuilder()
        result = builder.build(
            platform="reddit",
            function="comment",
            persona=persona,
            brand=brand,
            template_vars={},
            project_slug="test",
        )
        assert "Helpful and direct" in result.system
    finally:
        pb._PROJECTS_DIR = orig_projects
        pb._PROMPTS_DIR = orig_prompts
