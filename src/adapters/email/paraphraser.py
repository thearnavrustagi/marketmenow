from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from google.genai.types import GenerateContentConfig

from marketmenow.core.icl import select_icl_examples
from marketmenow.integrations.genai import create_genai_client

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 5.0


_EM_DASH_RE = re.compile(r"\u2014|\u2013|&mdash;|&ndash;")


def _sanitize(html: str) -> str:
    """Replace em-dashes / en-dashes (unicode and HTML entities) with plain hyphens."""
    return _EM_DASH_RE.sub("-", html)


class EmailParaphraser:
    """Rewrites email HTML body text using Gemini while preserving structure."""

    def __init__(
        self,
        vertex_project: str,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.5-flash",
        top_examples_path: Path | None = None,
        max_examples: int = 5,
        epsilon: float = 0.3,
    ) -> None:
        self._client = create_genai_client(
            vertex_project=vertex_project,
            vertex_location=vertex_location,
        )
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
        """Return a paraphrased version of *html* (single call with retries)."""
        last_exc: BaseException | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=html,
                    config=GenerateContentConfig(
                        system_instruction=self._system_prompt,
                        temperature=1.0,
                    ),
                )
                result = (response.text or "").strip()
                if result.startswith("```"):
                    result = result.split("\n", 1)[1]
                if result.endswith("```"):
                    result = result.rsplit("```", 1)[0]
                result = _sanitize(result.strip())
                logger.debug("Paraphrased email (%d chars)", len(result))
                return result
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    backoff = _INITIAL_BACKOFF_S * (2 ** (attempt - 1))
                    logger.warning(
                        "Paraphrase attempt %d/%d failed, retrying in %.0fs: %s",
                        attempt,
                        _MAX_RETRIES,
                        backoff,
                        exc,
                    )
                    await asyncio.sleep(backoff)

        raise RuntimeError(f"All {_MAX_RETRIES} paraphrase attempts failed") from last_exc

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
