from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from marketmenow.core.icl import select_icl_examples
from marketmenow.integrations.llm import LLMProvider, create_llm_provider

logger = logging.getLogger(__name__)


_EM_DASH_RE = re.compile(r"\u2014|\u2013|&mdash;|&ndash;")


def _sanitize(html: str) -> str:
    """Replace em-dashes / en-dashes (unicode and HTML entities) with plain hyphens."""
    return _EM_DASH_RE.sub("-", html)


class EmailParaphraser:
    """Rewrites email HTML body text while preserving structure."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        top_examples_path: Path | None = None,
        max_examples: int = 5,
        epsilon: float = 0.3,
        provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider()
        self._model = model
        self._top_examples_path = top_examples_path
        self._max_examples = max_examples
        self._epsilon = epsilon

        from marketmenow.core.prompt_builder import PromptBuilder

        icl_examples: list[dict[str, object]] | None = None
        if self._top_examples_path is not None:
            icl_examples, exploring = select_icl_examples(
                self._top_examples_path,
                self._max_examples,
                self._epsilon,
            )
            if exploring:
                logger.info("ICL explore mode — no examples for email paraphrase")

        built = PromptBuilder().build(
            platform="email",
            function="paraphrase",
            icl_examples=icl_examples,
        )
        self._system_prompt = built.system

    async def paraphrase(self, html: str) -> str:
        """Return a paraphrased version of *html*."""
        response = await self._provider.generate_text(
            model=self._model,
            system=self._system_prompt,
            contents=html,
            temperature=1.0,
        )
        result = response.text
        if result.startswith("```"):
            result = result.split("\n", 1)[1]
        if result.endswith("```"):
            result = result.rsplit("```", 1)[0]
        result = _sanitize(result.strip())
        logger.debug("Paraphrased email (%d chars)", len(result))
        return result

    async def paraphrase_many(
        self,
        html: str,
        count: int,
        *,
        batch_size: int = 10,
    ) -> list[str]:
        """Generate *count* unique paraphrased versions, *batch_size* at a time."""
        results: list[str] = []
        remaining = count
        while remaining > 0:
            chunk = min(remaining, batch_size)
            logger.info(
                "Paraphrasing batch of %d (%d/%d done)",
                chunk,
                len(results),
                count,
            )
            batch = await asyncio.gather(
                *(self.paraphrase(html) for _ in range(chunk)),
            )
            results.extend(batch)
            remaining -= chunk
        return results
