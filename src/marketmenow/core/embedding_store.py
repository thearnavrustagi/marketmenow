from __future__ import annotations

import logging
import math

from marketmenow.integrations.llm import LLMProvider, create_llm_provider

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100


class EmbeddingStore:
    """Thin wrapper around LLM embedding API with cosine distance math."""

    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed *texts* via the configured LLM provider.

        Splits into chunks of ``_BATCH_SIZE`` to stay within API limits.
        Returns one embedding vector per input text.
        """
        all_embeddings: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            try:
                batch_embeddings = await self._provider.embed(texts=batch)
                all_embeddings.extend(batch_embeddings)
            except Exception:
                logger.warning(
                    "Embedding batch %d-%d failed, filling with empty vectors",
                    start,
                    start + len(batch),
                    exc_info=True,
                )
                all_embeddings.extend([] for _ in batch)
        return all_embeddings

    @staticmethod
    def cosine_distance(a: list[float], b: list[float]) -> float:
        """Return ``1 - cosine_similarity(a, b)``.

        Pure-stdlib math (no numpy). Returns 1.0 when either vector is empty.
        """
        if not a or not b or len(a) != len(b):
            return 1.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 1.0
        return 1.0 - (dot / (norm_a * norm_b))
