"""The embedding service of this plugin as other plugins use it (``ctx.provide("embeddings", ...)``): its
settings, its key and its question cache, behind the ``EmbeddingService`` contract. Whoever uses it never sees
the key or the address."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import batched

from agent_app.plugins import EmbeddingUnavailableError

from .embedding import EMBED_BATCH, EmbeddingError
from .plugin import KnowledgePlugin


class SharedEmbeddings:
    def __init__(self, plugin: KnowledgePlugin) -> None:
        self._plugin = plugin

    async def space(self) -> str | None:
        config = await self._plugin.embedding_config()
        return config.space if config.ready else None

    async def embed_documents(
        self, texts: Sequence[str], *, timeout_s: float
    ) -> tuple[list[list[float]], str]:
        config = await self._plugin.embedding_config()
        if not config.ready:
            raise EmbeddingUnavailableError("Embedding chưa kết nối.")
        vectors: list[list[float]] = []
        try:
            for batch in batched(texts, EMBED_BATCH):
                prefixed = [config.document_prefix + text for text in batch]
                vectors.extend(await self._plugin.client.embed(config, prefixed, timeout_s=timeout_s))
        except EmbeddingError as err:
            raise EmbeddingUnavailableError(err.message) from err
        return vectors, config.space

    async def embed_query(self, text: str, *, timeout_s: float) -> tuple[list[float], str]:
        try:
            return await self._plugin.embedder.query_vector(text, timeout_s)
        except EmbeddingError as err:
            raise EmbeddingUnavailableError(err.message) from err
        except TimeoutError as err:
            raise EmbeddingUnavailableError("Embedding trả lời quá chậm.") from err
