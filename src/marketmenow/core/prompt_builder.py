from __future__ import annotations

import logging
from pathlib import Path

import yaml
from jinja2 import Template
from pydantic import BaseModel

from marketmenow.models.project import BrandConfig, PersonaConfig

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PROMPTS_DIR = _PROJECT_ROOT / "prompts"
_PROJECTS_DIR = _PROJECT_ROOT / "projects"


class BuiltPrompt(BaseModel, frozen=True):
    """Assembled prompt ready for LLM submission."""

    system: str
    user: str


class PromptBuilder:
    """Composes prompts from persona + function + ICL building blocks.

    Resolution order for each sub-prompt file:
      1. projects/{slug}/prompts/{platform}/{file}
      2. projects/{slug}/prompts/{file}
      3. prompts/{platform}/{file}

    Falls back to legacy monolithic prompt if decomposed files are absent.
    """

    def _resolve_file(
        self,
        filename: str,
        platform: str,
        project_slug: str | None,
    ) -> Path | None:
        """Walk the resolution chain and return the first path that exists."""
        if project_slug:
            project_platform = _PROJECTS_DIR / project_slug / "prompts" / platform / filename
            if project_platform.exists():
                return project_platform

            project_generic = _PROJECTS_DIR / project_slug / "prompts" / filename
            if project_generic.exists():
                return project_generic

        global_platform = _PROMPTS_DIR / platform / filename
        if global_platform.exists():
            return global_platform

        return None

    def _load_yaml(self, path: Path) -> dict[str, str]:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data

    def _render_template(self, raw: str, variables: dict[str, object]) -> str:
        return Template(raw).render(**variables)

    def _make_brand_dict(self, brand: BrandConfig) -> dict[str, object]:
        return brand.model_dump()

    def _make_persona_dict(self, persona: PersonaConfig, platform: str) -> dict[str, object]:
        base = persona.model_dump()
        overrides = persona.platform_overrides.get(platform, {})
        if overrides:
            base.update(overrides)
        return base

    def build(
        self,
        platform: str,
        function: str,
        persona: PersonaConfig,
        brand: BrandConfig,
        *,
        icl_examples: list[dict[str, object]] | None = None,
        template_vars: dict[str, object],
        project_slug: str | None = None,
    ) -> BuiltPrompt:
        """Assemble a prompt from persona + function + optional ICL block.

        If decomposed files (``persona.yaml``, ``functions/{function}.yaml``)
        are not found, falls back to the legacy monolithic prompt at
        ``{platform}/{function}_generation.yaml``.
        """
        shared_vars: dict[str, object] = {
            "brand": self._make_brand_dict(brand),
            "persona": self._make_persona_dict(persona, platform),
            **template_vars,
        }

        persona_path = self._resolve_file("persona.yaml", platform, project_slug)
        function_path = self._resolve_file(f"functions/{function}.yaml", platform, project_slug)

        if persona_path and function_path:
            return self._build_decomposed(
                persona_path,
                function_path,
                platform,
                project_slug,
                icl_examples,
                shared_vars,
            )

        return self._build_legacy(
            platform,
            function,
            icl_examples,
            shared_vars,
            project_slug,
        )

    def _build_decomposed(
        self,
        persona_path: Path,
        function_path: Path,
        platform: str,
        project_slug: str | None,
        icl_examples: list[dict[str, object]] | None,
        variables: dict[str, object],
    ) -> BuiltPrompt:
        persona_data = self._load_yaml(persona_path)
        function_data = self._load_yaml(function_path)

        persona_system = self._render_template(
            persona_data.get("system", ""),
            variables,
        )

        function_system = self._render_template(
            function_data.get("system", ""),
            variables,
        )

        icl_text = self._render_icl_block(platform, icl_examples, project_slug, variables)

        user_vars = {**variables, "icl_block": icl_text}
        function_user = self._render_template(
            function_data.get("user", ""),
            user_vars,
        )

        system = persona_system.rstrip() + "\n\n" + function_system.lstrip()

        return BuiltPrompt(system=system.strip(), user=function_user.strip())

    def _build_legacy(
        self,
        platform: str,
        function: str,
        icl_examples: list[dict[str, object]] | None,
        variables: dict[str, object],
        project_slug: str | None,
    ) -> BuiltPrompt:
        """Fallback: load a single monolithic prompt YAML."""
        legacy_names = [
            f"{function}_generation.yaml",
            f"{function}.yaml",
        ]
        for name in legacy_names:
            path = self._resolve_file(name, platform, project_slug)
            if path:
                break
        else:
            raise FileNotFoundError(
                f"No prompt found for platform={platform!r}, function={function!r} "
                f"(tried decomposed + legacy)"
            )

        data = self._load_yaml(path)

        icl_text = ""
        if icl_examples:
            icl_text = self._render_icl_block(
                platform,
                icl_examples,
                project_slug,
                variables,
            )
        variables_with_icl = {
            **variables,
            "icl_block": icl_text,
            "winning_examples": [e for e in (icl_examples or [])],
            "winning_posts": [e for e in (icl_examples or [])],
        }

        system = self._render_template(data.get("system", ""), variables_with_icl)
        user = self._render_template(data.get("user", ""), variables_with_icl)
        return BuiltPrompt(system=system.strip(), user=user.strip())

    def _render_icl_block(
        self,
        platform: str,
        icl_examples: list[dict[str, object]] | None,
        project_slug: str | None,
        variables: dict[str, object],
    ) -> str:
        if not icl_examples:
            return ""

        icl_path = self._resolve_file("icl_block.yaml", platform, project_slug)
        if icl_path:
            data = self._load_yaml(icl_path)
            template_str = data.get("block", "")
            return self._render_template(
                template_str,
                {**variables, "examples": icl_examples},
            )

        default_icl_path = _PROMPTS_DIR / "icl_block_default.yaml"
        if default_icl_path.exists():
            data = self._load_yaml(default_icl_path)
            template_str = data.get("block", "")
            return self._render_template(
                template_str,
                {**variables, "examples": icl_examples},
            )

        raise FileNotFoundError(
            "No ICL block template found. Expected icl_block.yaml in "
            f"prompts/{platform}/ or prompts/icl_block_default.yaml"
        )
