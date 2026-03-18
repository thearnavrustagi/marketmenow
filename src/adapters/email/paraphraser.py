from __future__ import annotations

import asyncio
import logging
import re

from google import genai
from google.genai.types import GenerateContentConfig

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 5.0

_SYSTEM_PROMPT = """\
You are an email copywriter. You will receive raw HTML source code of an email.

Your task: paraphrase ONLY the human-readable text so each version reads
slightly differently while preserving the exact same meaning, tone, and intent.

CRITICAL OUTPUT RULES:
- Your output MUST be raw HTML source code. NEVER use markdown syntax.
- NEVER convert <strong> to **bold** or <em> to *italic*. Keep the HTML tags.
- NEVER add markdown code fences, backticks, or any non-HTML formatting.
- Keep EVERY HTML tag, inline style, attribute, href, and structure byte-for-byte.
- Keep Jinja2 placeholders ({{ first_name }} etc.) exactly as-is.
- Only change the visible text between HTML tags.
- Keep the same casual-professional tone as the original.
- Do NOT add or remove sections, links, CTAs, or steps.
- Do NOT change names (Gradeasy, Arnav), URLs, or video links.
- NEVER use em-dashes, en-dashes, or &mdash; / &ndash; entities. Use a plain
  hyphen (-) surrounded by spaces instead.
- Output starts with <!DOCTYPE html> and ends with </html>.
"""


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
