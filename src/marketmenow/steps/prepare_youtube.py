from __future__ import annotations

import json
import logging

from marketmenow.core.workflow import WorkflowContext
from marketmenow.integrations.llm import LLMProvider, create_llm_provider

logger = logging.getLogger(__name__)


class PrepareYouTubeStep:
    """Generate YouTube-optimized title, description, and hashtags from reel content."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider or create_llm_provider()

    @property
    def name(self) -> str:
        return "prepare-youtube"

    @property
    def description(self) -> str:
        return "Generate YouTube title and description from reel content"

    async def execute(self, ctx: WorkflowContext) -> None:
        content = ctx.artifacts.get("content")
        if content is None:
            logger.warning("No content artifact found, skipping YouTube metadata generation")
            return

        # Extract script text from the content
        script = getattr(content, "caption", "") or ""
        if not script:
            text_segments = getattr(content, "text_segments", [])
            if text_segments:
                script = "\n".join(text_segments)

        brand = ctx.project.brand if ctx.project else None
        brand_name = brand.name if brand else "YourBrand"
        brand_url = brand.url if brand else "yourbrand.com"
        template_type = str(ctx.get_param("template", "unknown"))

        from marketmenow.core.prompt_builder import PromptBuilder

        built = PromptBuilder().build(
            platform="youtube",
            function="generate_metadata",
            brand=brand,
            template_vars={
                "script": script,
                "template_type": template_type,
                "brand": {"name": brand_name, "url": brand_url},
            },
            project_slug=ctx.project.slug if ctx.project else None,
        )

        response = await self._provider.generate_json(
            model="",
            system=built.system,
            contents=built.user,
            temperature=0.8,
        )

        try:
            data = json.loads(response.text or "{}")
            yt_title = str(data.get("title", ""))[:100]
            raw_description = str(data.get("description", ""))
            yt_description = f"Check out {brand_name} at {brand_url}\n\n{raw_description}"
            yt_hashtags = str(data.get("hashtags", ""))

            ctx.set_artifact("_yt_title", yt_title)
            ctx.set_artifact("_yt_description", yt_description)
            ctx.set_artifact("_yt_hashtags", yt_hashtags)

            ctx.console.print(f"[cyan]YouTube title:[/cyan] {yt_title}")
        except (json.JSONDecodeError, Exception):
            logger.exception("Failed to parse YouTube metadata from LLM response")
            ctx.set_artifact("_yt_title", "")
            ctx.set_artifact("_yt_description", "")
            ctx.set_artifact("_yt_hashtags", "")
