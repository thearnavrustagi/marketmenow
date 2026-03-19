from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import yaml
from google import genai
from google.genai.types import GenerateContentConfig

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 5.0

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PROMPT_PATH = _PROJECT_ROOT / "prompts" / "email" / "paraphrase.yaml"


def _load_system_prompt() -> str:
    with _PROMPT_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("system", "")


_SYSTEM_PROMPT = _load_system_prompt()


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
    ) -> None:
        self._client = genai.Client(
            vertexai=True,
            project=vertex_project,
            location=vertex_location,
        )
        self._model = model

    async def paraphrase(self, html: str) -> str:
        """Return a paraphrased version of *html* (single call with retries)."""
        last_exc: BaseException | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=html,
                    config=GenerateContentConfig(
                        system_instruction=_SYSTEM_PROMPT,
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
