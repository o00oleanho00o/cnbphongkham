"""Services one plugin gives to the others (``ctx.provide`` / ``ctx.use``), and the contracts they follow. The
harness only carries them by name; which plugin provides one is that plugin's business.

A service is an object a plugin hands the host under a name; another plugin asks for it by name and the type
it expects, and gets ``None`` while no enabled plugin provides it (the plugin that needs it then does
without). The asking plugin looks it up when it needs it, never at registration, because plugins register in
no fixed order and the provider can be enabled or disabled while the agent runs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol, runtime_checkable

EMBEDDINGS: Final = "embeddings"
"""The name of the embedding service (``EmbeddingService``)."""
JUDGE: Final = "judge"
"""The name of the judging service (``JudgeService``)."""


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


class JudgeUnavailableError(Exception):
    """The judging service cannot be used right now (no key, a wrong key, out of credit, a limit, an
    outage, the day's allowance used, an answer it could not read); ``message`` is a sentence a person can
    read. Callers go on without the judgement."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@runtime_checkable
class JudgeService(Protocol):
    """Puts typed questions to a small classifying model and gets probabilities back. The service knows
    nothing of what the caller judges: the caller writes the questions and the criteria, and decides with
    the answers.

    A question is a mapping as TypeSafe's ``/v1/systemone`` takes it (``type`` ``noul``, ``choice`` or
    ``score``, ``instructions`` and ``criteria``); an answer is the mapping it gives back for that question
    (``noul``: a probability; ``choice``: the option, ``probabilities``, ``confidence``; ``score``: the
    score, ``legend``, ``probabilities``, ``confidence``)."""

    async def ready(self) -> bool:
        """Whether a call can be made now: a key is stored and the day's allowance is not used up."""
        ...

    async def ask(
        self,
        states: Sequence[Any],
        questions: Mapping[str, Mapping[str, Any]],
        *,
        timeout_s: float,
    ) -> list[dict[str, Any]]:
        """For each state, in order, the answers to all the questions (each state is one request; they run
        together). Raises ``JudgeUnavailableError`` when any of them cannot be answered in ``timeout_s``."""
        ...
