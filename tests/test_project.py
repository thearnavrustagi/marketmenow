from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from marketmenow.core.project_manager import ProjectManager
from marketmenow.models.project import (
    BrandConfig,
    PersonaConfig,
    ProjectConfig,
    TargetCustomer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _brand(**overrides: object) -> BrandConfig:
    defaults: dict[str, object] = {
        "name": "TestBrand",
        "url": "testbrand.io",
        "tagline": "A test product",
    }
    return BrandConfig(**(defaults | overrides))


def _persona(**overrides: object) -> PersonaConfig:
    defaults: dict[str, object] = {"name": "default", "description": "Test persona"}
    return PersonaConfig(**(defaults | overrides))


def _target_customer(**overrides: object) -> TargetCustomer:
    defaults: dict[str, object] = {
        "description": "People who need tests",
        "pain_points": ["slow feedback"],
        "keywords": ["testing"],
        "platforms": ["twitter"],
    }
    return TargetCustomer(**(defaults | overrides))


def _create_project(pm: ProjectManager, slug: str = "myapp", **kw: object) -> ProjectConfig:
    return pm.create_project(slug, _brand(), **kw)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestBrandConfig:
    def test_frozen(self) -> None:
        b = _brand()
        with pytest.raises(ValidationError):
            b.name = "changed"  # type: ignore[misc]

    def test_defaults(self) -> None:
        b = _brand()
        assert b.color == "#000000"
        assert b.logo_letter == ""
        assert b.features == []

    def test_full(self) -> None:
        b = _brand(
            color="#FF0000",
            logo_letter="T",
            logo_suffix=".io",
            value_prop="Best tests",
            features=["fast", "reliable"],
        )
        assert b.color == "#FF0000"
        assert b.features == ["fast", "reliable"]


class TestPersonaConfig:
    def test_frozen(self) -> None:
        p = _persona()
        with pytest.raises(ValidationError):
            p.name = "changed"  # type: ignore[misc]

    def test_platform_overrides(self) -> None:
        p = _persona(platform_overrides={"twitter": {"tone": "edgy"}})
        assert p.platform_overrides["twitter"]["tone"] == "edgy"

    def test_example_phrases(self) -> None:
        p = _persona(example_phrases=["ngl", "lowkey"])
        assert len(p.example_phrases) == 2


class TestTargetCustomer:
    def test_frozen(self) -> None:
        t = _target_customer()
        with pytest.raises(ValidationError):
            t.description = "changed"  # type: ignore[misc]

    def test_defaults(self) -> None:
        t = TargetCustomer(description="someone")
        assert t.pain_points == []
        assert t.keywords == []
        assert t.platforms == []


class TestProjectConfig:
    def test_requires_slug_and_brand(self) -> None:
        with pytest.raises(ValidationError):
            ProjectConfig()  # type: ignore[call-arg]

    def test_defaults(self) -> None:
        cfg = ProjectConfig(slug="x", brand=_brand())
        assert cfg.default_persona == "default"
        assert cfg.env_overrides == {}
        assert cfg.target_customer is None

    def test_env_overrides(self) -> None:
        cfg = ProjectConfig(
            slug="x", brand=_brand(), env_overrides={"TWITTER_USERNAME": "bot"}
        )
        assert cfg.env_overrides["TWITTER_USERNAME"] == "bot"

    def test_yaml_roundtrip(self, tmp_path: Path) -> None:
        cfg = ProjectConfig(
            slug="rt",
            brand=_brand(),
            target_customer=_target_customer(),
            env_overrides={"K": "V"},
        )
        path = tmp_path / "project.yaml"
        path.write_text(yaml.dump(cfg.model_dump(), sort_keys=False), encoding="utf-8")
        loaded = ProjectConfig(**yaml.safe_load(path.read_text(encoding="utf-8")))
        assert loaded.slug == cfg.slug
        assert loaded.brand.name == cfg.brand.name
        assert loaded.target_customer is not None
        assert loaded.target_customer.description == cfg.target_customer.description  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# ProjectManager — create
# ---------------------------------------------------------------------------


class TestProjectManagerCreate:
    def test_scaffolds_all_directories(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        proj = tmp_path / "projects" / "myapp"
        for sub in (
            "personas",
            "prompts/twitter",
            "prompts/reddit",
            "prompts/instagram",
            "targets",
            "templates/reels",
            "templates/email",
            "campaigns",
            "vault",
            "output",
        ):
            assert (proj / sub).is_dir(), f"Missing directory: {sub}"

    def test_writes_valid_project_yaml(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        cfg_path = tmp_path / "projects" / "myapp" / "project.yaml"
        assert cfg_path.exists()
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        assert data["slug"] == "myapp"
        assert data["brand"]["name"] == "TestBrand"

    def test_writes_default_persona(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        persona_path = tmp_path / "projects" / "myapp" / "personas" / "default.yaml"
        assert persona_path.exists()
        data = yaml.safe_load(persona_path.read_text(encoding="utf-8"))
        assert data["name"] == "default"

    def test_duplicate_slug_raises(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        with pytest.raises(FileExistsError):
            _create_project(pm)


# ---------------------------------------------------------------------------
# ProjectManager — load
# ---------------------------------------------------------------------------


class TestProjectManagerLoad:
    def test_load_valid_project(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        loaded = pm.load_project("myapp")
        assert loaded.slug == "myapp"
        assert loaded.brand.name == "TestBrand"

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        with pytest.raises(FileNotFoundError):
            pm.load_project("nonexistent")

    def test_load_invalid_yaml_raises(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        proj_dir = tmp_path / "projects" / "bad"
        proj_dir.mkdir(parents=True)
        (proj_dir / "project.yaml").write_text("slug: bad\n", encoding="utf-8")
        with pytest.raises(ValidationError):
            pm.load_project("bad")


# ---------------------------------------------------------------------------
# ProjectManager — list
# ---------------------------------------------------------------------------


class TestProjectManagerList:
    def test_list_empty(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        assert pm.list_projects() == []

    def test_list_multiple_sorted(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        for slug in ("charlie", "alpha", "bravo"):
            pm.create_project(slug, _brand(name=slug))
        names = [p.slug for p in pm.list_projects()]
        assert names == ["alpha", "bravo", "charlie"]


# ---------------------------------------------------------------------------
# ProjectManager — personas
# ---------------------------------------------------------------------------


class TestProjectManagerPersona:
    def test_load_persona_default(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        p = pm.load_persona("myapp", "default")
        assert p.name == "default"

    def test_load_persona_custom(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        pm.save_persona("myapp", _persona(name="edgy", voice="sarcastic"))
        p = pm.load_persona("myapp", "edgy")
        assert p.voice == "sarcastic"

    def test_load_persona_missing_raises(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        with pytest.raises(FileNotFoundError):
            pm.load_persona("myapp", "nonexistent")

    def test_list_personas(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        pm.save_persona("myapp", _persona(name="alt"))
        names = pm.list_personas("myapp")
        assert "default" in names
        assert "alt" in names

    def test_save_persona(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        path = pm.save_persona("myapp", _persona(name="new", tone="calm"))
        assert path.exists()
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["tone"] == "calm"


# ---------------------------------------------------------------------------
# ProjectManager — active project
# ---------------------------------------------------------------------------


class TestProjectManagerActiveProject:
    def test_get_active_none(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        assert pm.get_active_project() is None

    def test_set_and_get_active(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm, slug="alpha")
        pm.set_active_project("alpha")
        assert pm.get_active_project() == "alpha"

    def test_set_active_invalid_slug_raises(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        with pytest.raises(FileNotFoundError):
            pm.set_active_project("nope")


# ---------------------------------------------------------------------------
# ProjectManager — path resolution
# ---------------------------------------------------------------------------


class TestProjectManagerResolvePath:
    def test_resolve_project_override(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        prompt = pm.project_dir("myapp") / "prompts" / "twitter" / "reply.yaml"
        prompt.write_text("system: hi\n", encoding="utf-8")
        resolved = pm.resolve_path("myapp", "prompts", "twitter", "reply.yaml")
        assert resolved == prompt

    def test_resolve_global_fallback(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        fallback_dir = tmp_path / "global_prompts"
        fallback_dir.mkdir()
        (fallback_dir / "reply.yaml").write_text("system: global\n", encoding="utf-8")
        resolved = pm.resolve_path("myapp", "prompts", "reply.yaml", fallback=fallback_dir)
        assert resolved == fallback_dir / "reply.yaml"

    def test_resolve_no_fallback_raises(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        with pytest.raises(FileNotFoundError):
            pm.resolve_path("myapp", "prompts", "missing.yaml")

    def test_resolve_project_precedence(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        proj_file = pm.project_dir("myapp") / "prompts" / "twitter" / "reply.yaml"
        proj_file.write_text("system: project\n", encoding="utf-8")
        fallback_dir = tmp_path / "global_prompts" / "twitter"
        fallback_dir.mkdir(parents=True)
        (fallback_dir / "reply.yaml").write_text("system: global\n", encoding="utf-8")
        resolved = pm.resolve_path(
            "myapp", "prompts", "twitter", "reply.yaml", fallback=tmp_path / "global_prompts"
        )
        assert resolved == proj_file


# ---------------------------------------------------------------------------
# ProjectManager — reel template
# ---------------------------------------------------------------------------


class TestProjectManagerReelTemplate:
    def test_save_reel_template(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        _create_project(pm)
        path = pm.save_reel_template("myapp", "my_template", "id: my_template\n")
        assert path.exists()
        assert "my_template" in path.read_text(encoding="utf-8")

    def test_save_reel_template_creates_dir(self, tmp_path: Path) -> None:
        pm = ProjectManager(tmp_path / "projects")
        (tmp_path / "projects" / "bare").mkdir(parents=True)
        (tmp_path / "projects" / "bare" / "project.yaml").write_text(
            yaml.dump(ProjectConfig(slug="bare", brand=_brand()).model_dump()),
            encoding="utf-8",
        )
        path = pm.save_reel_template("bare", "t", "id: t\n")
        assert path.exists()
