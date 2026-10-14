"""Services one plugin gives to the others (``ctx.provide`` / ``ctx.use``), and the contracts they follow.

A service is an object a plugin hands the host under a name; another plugin asks for it by name and the type
it expects, and gets ``None`` while no enabled plugin provides it (the plugin that needs it then does
without). The asking plugin looks it up when it needs it, never at registration, because plugins register in
no fixed order and the provider can be enabled or disabled while the agent runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, Protocol, runtime_checkable

EMBEDDINGS: Final = "embeddings"
"""The name of the embedding service (``EmbeddingService``), provided by ``knowledge``."""


class EmbeddingUnavailableError(Exception):
    """The embedding service cannot be used right now (not connected, a wrong key, a limit, an outage);
    ``message`` is a sentence a person can read. Callers fall back to searching by keyword."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@runtime_checkable
class EmbeddingService(Protocol):
    """Turns text into normalised vectors. A vector belongs to a ``space`` (the model, its dimensions and its
    document prefix); vectors of different spaces are never compared, and a change of model changes the
    space, so the caller finds its stored vectors missing and makes them again."""

    async def space(self) -> str | None:
        """The space new vectors are made in; None while the service is not connected."""
        ...

    async def embed_documents(
        self, texts: Sequence[str], *, timeout_s: float
    ) -> tuple[list[list[float]], str]:
        """One vector per text (at most a few dozen per call), in order, and their space. Raises
        ``EmbeddingUnavailableError``."""
        ...

    async def embed_query(self, text: str, *, timeout_s: float) -> tuple[list[float], str]:
        """The vector of a question and its space (the same question twice may come from a cache). Raises
        ``EmbeddingUnavailableError``; never retries, a search cannot wait."""
        ...
