from __future__ import annotations

import logging
from pathlib import Path

import yaml

from marketmenow.models.project import (
    BrandConfig,
    GenerationConfig,
    PersonaConfig,
    ProjectConfig,
    TargetCustomer,
)

logger = logging.getLogger(__name__)

_ACTIVE_PROJECT_FILE = ".mmn_active_project"

_SCAFFOLD_DIRS = (
    "personas",
    "prompts/twitter",
    "prompts/reddit",
    "prompts/instagram",
    "targets",
    "templates/reels",
    "templates/email",
    "campaigns",
    "capsules",
    "vault",
    "output",
)


class ProjectManager:
    """CRUD operations for per-product project directories.

    All filesystem operations are relative to *projects_root* so callers
    (and tests) can point at any directory.
    """

    def __init__(self, projects_root: Path | None = None) -> None:
        self._root = projects_root or Path("projects")

    # ── helpers ────────────────────────────────────────────────────────

    def project_dir(self, slug: str) -> Path:
        return self._root / slug

    def _active_file(self) -> Path:
        return (
            self._root.parent / _ACTIVE_PROJECT_FILE
            if self._root.name == "projects"
            else self._root / _ACTIVE_PROJECT_FILE
        )

    # ── create ────────────────────────────────────────────────────────

    def create_project(
        self,
        slug: str,
        brand: BrandConfig,
        *,
        target_customer: TargetCustomer | None = None,
        default_persona: str = "default",
        env_overrides: dict[str, str] | None = None,
    ) -> ProjectConfig:
        proj_dir = self.project_dir(slug)
        if proj_dir.exists():
            raise FileExistsError(f"Project '{slug}' already exists at {proj_dir}")

        for sub in _SCAFFOLD_DIRS:
            (proj_dir / sub).mkdir(parents=True, exist_ok=True)

        config = ProjectConfig(
            slug=slug,
            brand=brand,
            target_customer=target_customer,
            default_persona=default_persona,
            env_overrides=env_overrides or {},
        )

        (proj_dir / "project.yaml").write_text(
            yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        default = PersonaConfig(name=default_persona, description="Default persona")
        self.save_persona(slug, default)

        return config

    # ── load ──────────────────────────────────────────────────────────

    def load_project(self, slug: str) -> ProjectConfig:
        path = self.project_dir(slug) / "project.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Project '{slug}' not found at {path}")

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return ProjectConfig(**raw)

    def load_generation_config(self, slug: str) -> GenerationConfig:
        path = self.project_dir(slug) / "generation_config.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Generation config not found at {path}")

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return GenerationConfig(**raw)

    def list_projects(self) -> list[ProjectConfig]:
        if not self._root.is_dir():
            return []
        projects: list[ProjectConfig] = []
        for child in sorted(self._root.iterdir()):
            cfg = child / "project.yaml"
            if cfg.is_file():
                try:
                    projects.append(
                        ProjectConfig(**yaml.safe_load(cfg.read_text(encoding="utf-8")))
                    )
                except Exception:
                    logger.warning("Skipping invalid project at %s", child)
        return projects

    # ── personas ──────────────────────────────────────────────────────

    def save_persona(self, slug: str, persona: PersonaConfig) -> Path:
        path = self.project_dir(slug) / "personas" / f"{persona.name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.dump(persona.model_dump(), default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        return path

    def load_persona(self, slug: str, persona_name: str) -> PersonaConfig:
        path = self.project_dir(slug) / "personas" / f"{persona_name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Persona '{persona_name}' not found at {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return PersonaConfig(**raw)

    def list_personas(self, slug: str) -> list[str]:
        personas_dir = self.project_dir(slug) / "personas"
        if not personas_dir.is_dir():
            return []
        return sorted(p.stem for p in personas_dir.glob("*.yaml") if p.is_file())

    # ── active project ────────────────────────────────────────────────

    def get_active_project(self) -> str | None:
        f = self._active_file()
        if not f.exists():
            return None
        text = f.read_text(encoding="utf-8").strip()
        return text or None

    def set_active_project(self, slug: str) -> None:
        if not self.project_dir(slug).is_dir():
            raise FileNotFoundError(f"Project '{slug}' does not exist")
        self._active_file().write_text(slug + "\n", encoding="utf-8")

    # ── path resolution ───────────────────────────────────────────────

    def resolve_path(
        self,
        slug: str,
        category: str,
        *parts: str,
        fallback: Path | None = None,
    ) -> Path:
        """Resolve a file path within a project, falling back to a global path.

        Checks ``projects/{slug}/{category}/{parts}`` first.  If not found
        and *fallback* is provided, checks ``fallback / parts``.  Raises
        ``FileNotFoundError`` when neither location contains the file.
        """
        project_path = self.project_dir(slug) / category / Path(*parts)
        if project_path.exists():
            return project_path

        if fallback is not None:
            global_path = fallback / Path(*parts)
            if global_path.exists():
                return global_path

        raise FileNotFoundError(
            f"'{'/'.join(parts)}' not found in project '{slug}' ({category}/) "
            f"or fallback {fallback}"
        )

    # ── reel template helpers ─────────────────────────────────────────

    def save_reel_template(self, slug: str, template_id: str, yaml_content: str) -> Path:
        path = self.project_dir(slug) / "templates" / "reels" / f"{template_id}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml_content, encoding="utf-8")
        return path

    def save_file(self, slug: str, *parts: str, content: str) -> Path:
        """Write arbitrary content to a file under the project directory."""
        path = self.project_dir(slug) / Path(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
