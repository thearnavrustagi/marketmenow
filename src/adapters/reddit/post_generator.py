from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from google import genai
from google.genai.types import GenerateContentConfig
from jinja2 import Template

from marketmenow.core.icl import select_icl_examples

from .prompts import load_prompt

if TYPE_CHECKING:
    from marketmenow.models.project import BrandConfig, PersonaConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeneratedRedditPost:
    subreddit: str
    title: str
    body: str


class RedditPostGenerator:
    """Generates Reddit text posts (update / milestone / launch) via Gemini."""

    def __init__(
        self,
        gemini_model: str = "gemini-2.5-flash",
        vertex_project: str = "",
        vertex_location: str = "us-central1",
        persona: PersonaConfig | None = None,
        brand: BrandConfig | None = None,
        project_slug: str | None = None,
        top_examples_path: Path | None = None,
        max_examples: int = 5,
        epsilon: float = 0.3,
    ) -> None:
        self._client = genai.Client(
            vertexai=True,
            project=vertex_project,
            location=vertex_location,
        )
        self._model = gemini_model
        self._persona = persona
        self._brand = brand
        self._project_slug = project_slug
        self._top_examples_path = top_examples_path
        self._max_examples = max_examples
        self._epsilon = epsilon

    async def generate_post(
        self,
        subreddit: str,
        product_name: str,
        product_url: str,
        product_description: str,
        post_type: str = "update",
        context: str = "",
    ) -> GeneratedRedditPost:
        icl_examples: list[dict[str, object]] | None = None
        if self._top_examples_path is not None:
            icl_examples, exploring = select_icl_examples(
                self._top_examples_path,
                self._max_examples,
                self._epsilon,
            )
            if exploring:
                logger.info("ICL explore mode — no examples for this Reddit post")

        if self._persona and self._brand:
            from marketmenow.core.prompt_builder import PromptBuilder

            built = PromptBuilder().build(
                platform="reddit",
                function="post",
                persona=self._persona,
                brand=self._brand,
                icl_examples=icl_examples,
                template_vars={
                    "subreddit": subreddit,
                    "product_name": product_name or self._brand.name,
                    "product_url": product_url or self._brand.url,
                    "product_description": product_description or self._brand.tagline,
                    "post_type": post_type,
                    "context": context,
                },
                project_slug=self._project_slug,
            )
            system_prompt = built.system
            user_prompt = built.user
        else:
            prompt_data = load_prompt("post_generation")

            system_prompt = prompt_data["system"]
            user_template = Template(prompt_data["user"])
            user_prompt = user_template.render(
                subreddit=subreddit,
                product_name=product_name,
                product_url=product_url,
                product_description=product_description,
                post_type=post_type,
                context=context,
            )

        config = GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.9,
            max_output_tokens=1024,
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=config,
        )

        raw = response.text or ""
        title, body = _parse_post(raw)

        return GeneratedRedditPost(
            subreddit=subreddit,
            title=title,
            body=body,
        )


def _parse_post(raw: str) -> tuple[str, str]:
    """Extract TITLE and BODY from the LLM response."""
    title = ""
    body = ""

    lines = raw.strip().splitlines()
    in_body = False

    for line in lines:
        if line.strip().upper().startswith("TITLE:") and not title:
            title = line.split(":", 1)[1].strip()
        elif line.strip().upper().startswith("BODY:"):
            in_body = True
        elif in_body:
            body += line + "\n"

    body = body.strip()

    if not title and not body:
        title = lines[0] if lines else "Update"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw.strip()

    return title, body
