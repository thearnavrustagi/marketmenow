from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from google.genai import types as genai_types

from marketmenow.core.icl import select_icl_examples
from marketmenow.integrations.genai import create_genai_client
from marketmenow.models.content import ImagePost, MediaAsset

from ..prompts import load_prompt
from ..settings import InstagramSettings
from .renderer import SlideRenderer

if TYPE_CHECKING:
    from marketmenow.models.project import BrandConfig, PersonaConfig

_MAX_IMAGE_RETRIES = 3
_INITIAL_BACKOFF_S = 2.0


def _ensure_vertex_credentials(settings: InstagramSettings) -> None:
    creds = settings.google_application_credentials
    if creds and creds.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(creds.resolve()))


class CarouselOrchestrator:
    """End-to-end pipeline: Gemini topic -> Imagen images -> Pillow slides -> ImagePost."""

    GEMINI_MODEL = "gemini-2.5-flash"
    IMAGEN_MODEL = "imagen-3.0-generate-002"

    def __init__(
        self,
        settings: InstagramSettings,
        *,
        persona: PersonaConfig | None = None,
        brand: BrandConfig | None = None,
        project_slug: str | None = None,
        top_examples_path: Path | None = None,
        max_examples: int = 5,
        epsilon: float = 0.3,
    ) -> None:
        self._settings = settings
        self._output_dir = settings.output_dir / "carousel"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._persona = persona
        self._brand = brand
        self._project_slug = project_slug
        self._top_examples_path = top_examples_path
        self._max_examples = max_examples
        self._epsilon = epsilon

        _ensure_vertex_credentials(settings)

        self._client = create_genai_client(
            vertex_project=settings.vertex_ai_project,
            vertex_location=settings.vertex_ai_location,
        )
        from .renderer import _hex_to_rgb

        self._renderer = SlideRenderer(
            self._output_dir,
            brand_letter=brand.logo_letter if brand and brand.logo_letter else "G",
            brand_suffix=brand.logo_suffix if brand and brand.logo_suffix else ".",
            accent_color=(
                _hex_to_rgb(brand.color) if brand and brand.color != "#000000" else (68, 136, 255)
            ),
        )

    async def create_carousel(self) -> ImagePost:
        run_id = uuid4().hex[:8]

        content = await self._generate_content()

        cover_image_bytes, item_images = await self._generate_all_images(content)

        images: list[MediaAsset] = []

        cover_path = self._renderer.render_cover(
            heading=content["cover_heading"],
            subtitle=content.get("cover_subtitle", ""),
            image_bytes=cover_image_bytes,
            run_id=run_id,
        )
        images.append(
            MediaAsset(uri=str(cover_path.resolve()), mime_type="image/png"),
        )

        for item, img_bytes in zip(content["items"], item_images, strict=True):
            item_path = self._renderer.render_item(
                number=item["number"],
                heading=item["heading"],
                sub_heading=item["sub_heading"],
                image_bytes=img_bytes,
                run_id=run_id,
            )
            images.append(
                MediaAsset(uri=str(item_path.resolve()), mime_type="image/png"),
            )

        return ImagePost(
            images=images,
            caption=content.get("caption", ""),
            hashtags=content.get("hashtags", []),
        )

    async def _generate_content(self) -> dict[str, object]:
        system_prompt, user_prompt = self._build_prompt()

        response = await self._client.aio.models.generate_content(
            model=self.GEMINI_MODEL,
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(text=user_prompt)],
                ),
            ],
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=1.0,
            ),
        )

        data = json.loads(response.text)
        if isinstance(data, list):
            data = data[0]

        assert "cover_heading" in data, f"Missing cover_heading in LLM response: {data}"
        assert "items" in data and len(data["items"]) == 5, (
            f"Expected 5 items, got: {data.get('items')}"
        )
        return data

    def _build_prompt(self) -> tuple[str, str]:
        """Build the carousel prompt, rendering Jinja2 variables with project context."""
        icl_examples: list[dict[str, object]] | None = None
        if self._top_examples_path is not None:
            icl_examples, _exploring = select_icl_examples(
                self._top_examples_path,
                self._max_examples,
                self._epsilon,
            )

        if self._persona and self._brand:
            from marketmenow.core.prompt_builder import PromptBuilder

            built = PromptBuilder().build(
                platform="instagram",
                function="carousel_top5",
                persona=self._persona,
                brand=self._brand,
                icl_examples=icl_examples,
                template_vars={},
                project_slug=self._project_slug,
            )
            return built.system, built.user

        raw = load_prompt("carousel_top5", project_slug=self._project_slug)
        from jinja2 import Template

        variables: dict[str, object] = {}
        if self._brand:
            variables["brand"] = self._brand.model_dump()
        if self._persona:
            overrides = self._persona.platform_overrides.get("instagram", {})
            persona_dict = self._persona.model_dump()
            if overrides:
                persona_dict.update(overrides)
            variables["persona"] = persona_dict

        system = Template(raw["system"]).render(**variables)
        user = Template(raw["user"]).render(**variables)
        return system, user

    async def _generate_all_images(self, content: dict[str, object]) -> tuple[bytes, list[bytes]]:
        cover_task = self._generate_image(content["cover_image_prompt"])
        item_tasks = [self._generate_image(item["image_prompt"]) for item in content["items"]]

        results = await asyncio.gather(cover_task, *item_tasks)
        return results[0], list(results[1:])

    async def _generate_image(self, prompt: str) -> bytes:
        """Generate an image with retry + exponential backoff on API errors."""
        prompts = [prompt, self._simplify_prompt(prompt), self._fallback_prompt()]
        last_error: Exception | None = None

        for attempt, current_prompt in enumerate(prompts):
            for retry in range(_MAX_IMAGE_RETRIES):
                try:
                    response = await self._client.aio.models.generate_images(
                        model=self.IMAGEN_MODEL,
                        prompt=current_prompt,
                        config=genai_types.GenerateImagesConfig(
                            number_of_images=1,
                            aspect_ratio="3:4",
                            person_generation=genai_types.PersonGeneration.ALLOW_ADULT,
                            safety_filter_level=genai_types.SafetyFilterLevel.BLOCK_ONLY_HIGH,
                        ),
                    )
                    if response.generated_images:
                        return response.generated_images[0].image.image_bytes
                    break
                except Exception as exc:
                    last_error = exc
                    wait = _INITIAL_BACKOFF_S * (2**retry)
                    logging.getLogger(__name__).warning(
                        "Imagen attempt %d/%d failed (prompt variant %d): %s — retrying in %.0fs",
                        retry + 1,
                        _MAX_IMAGE_RETRIES,
                        attempt + 1,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)

        raise RuntimeError(
            f"Imagen failed after all retries for: {prompt[:80]}... Last error: {last_error}"
        )

    @staticmethod
    def _simplify_prompt(prompt: str) -> str:
        """Strip a prompt down to a safe, generic version for retry."""
        from jinja2 import Template

        data = _load_image_fallback_prompts()
        words = " ".join(prompt.split()[:12])
        return Template(data["simplify_template"]).render(words=words).strip()

    @staticmethod
    def _fallback_prompt() -> str:
        """Last-resort generic prompt that should never be rejected."""
        data = _load_image_fallback_prompts()
        return data["fallback"].strip()


def _load_image_fallback_prompts() -> dict[str, str]:
    """Load carousel image fallback prompts from YAML (cached)."""
    cached = getattr(_load_image_fallback_prompts, "_cache", None)
    if cached is not None:
        return cached

    from pathlib import Path

    import yaml

    prompts_path = (
        Path(__file__).resolve().parents[4]
        / "prompts"
        / "instagram"
        / "carousel_image_fallback.yaml"
    )
    with prompts_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    _load_image_fallback_prompts._cache = data  # type: ignore[attr-defined]
    return data
