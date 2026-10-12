"""Keeping every chunk's vector up to date, and embedding a question for a search.

The job ``embed`` runs under ``agent serve`` (under ``agent chat`` there is no job: the vectors already stored
are used and new chunks are searched by keyword only). It takes the texts that have no vector in the current
space (``EmbeddingConfig.space``) a batch at a time, so a new source is searchable by keyword at once and by
meaning a little later. A failing service never stops anything else: the page shows the sentence and the job
tries again after a wait that grows.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

from .embedding import EMBED_BATCH, EmbeddingClient, EmbeddingConfig, EmbeddingError
from .store import KnowledgeStore

IDLE_S: Final = 5.0
NOT_READY_S: Final = 30.0
BACKOFF_S: Final = (5.0, 15.0, 60.0, 300.0)
STOP_S: Final = 300.0
"""A wrong key, address or setting does not mend itself: wait for a settings change (or this long)."""
CLEANUP_EVERY_S: Final = 3600.0
QUERY_CACHE: Final = 512
DOCUMENT_TIMEOUT_S: Final = 60.0

NOT_CONNECTED: Final = "Embedding chưa kết nối: đang tìm bằng từ khóa."
KEY_BROKEN: Final = "Khóa API đã lưu không giải mã được. Nhập lại khóa: đang tìm bằng từ khóa."

State = Literal["off", "working", "ok", "error"]


@dataclass(frozen=True, slots=True)
class EmbedStatus:
    state: State
    message: str | None
    """A sentence for the page; None when all is well."""
    missing: int
    """Chunks with no vector in the current space (0 while the service is not connected)."""
    model: str | None
    last_ok_at: datetime | None


class Embedder:
    def __init__(
        self,
        store: KnowledgeStore,
        client: EmbeddingClient,
        config: Callable[[], Awaitable[EmbeddingConfig]],
        *,
        logger: logging.Logger,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        idle_s: float = IDLE_S,
    ) -> None:
        self._store = store
        self._client = client
        self._config = config
        self._logger = logger
        self._clock = clock
        self._monotonic = monotonic
        self._idle_s = idle_s
        self._wake = asyncio.Event()
        self._error: str | None = None
        self._last_ok: datetime | None = None
        self._cache: OrderedDict[tuple[str, str, str], list[float]] = OrderedDict()

    def wake(self) -> None:
        """Something changed (a source was added, the settings were saved): look for work now."""
        self._wake.set()

    async def step(self) -> bool:
        """Embeds one batch of the texts still missing; True when it embedded something."""
        config = await self._config()
        if not config.ready:
            return False
        items = await self._store.missing_vectors(config.space, EMBED_BATCH)
        if not items:
            self._succeeded()
            return False
        texts = [config.document_prefix + text for _, text in items]
        started = self._monotonic()
        try:
            vectors = await self._client.embed(config, texts, timeout_s=DOCUMENT_TIMEOUT_S)
        except EmbeddingError as err:
            if not err.transient:
                raise
            vectors = await self._client.embed(config, texts, timeout_s=DOCUMENT_TIMEOUT_S)
        await self._store.save_vectors(
            config.space, [(item[0], vector) for item, vector in zip(items, vectors, strict=True)]
        )
        self._succeeded()
        self._logger.info("embedded %d texts in %.0f ms", len(items), (self._monotonic() - started) * 1000)
        return True

    async def run(self) -> None:
        """The job: batches while there is work, a wait when there is none, a longer one after a failure."""
        failures = 0
        space: str | None = None
        cleaned = self._monotonic()
        while True:
            try:
                config = await self._config()
                if config.space != space:
                    space, failures = config.space, 0
                worked = await self.step()
                failures = 0
                if config.ready and self._monotonic() - cleaned >= CLEANUP_EVERY_S:
                    cleaned = self._monotonic()
                    await self._store.drop_stale_vectors(config.space)
                if worked:
                    await asyncio.sleep(0)
                    continue
                await self._wait(self._idle_s if config.ready else NOT_READY_S)
            except EmbeddingError as err:
                self._error = err.message
                self._logger.warning("embedding failed (%s)", err.kind)
                wait = BACKOFF_S[min(failures, len(BACKOFF_S) - 1)] if err.transient else STOP_S
                failures += 1
                await self._wait(wait)
            except Exception:
                self._error = "Lỗi khi nhúng, xem log agent."
                self._logger.exception("embedding job failed")
                wait = BACKOFF_S[min(failures, len(BACKOFF_S) - 1)]
                failures += 1
                await self._wait(wait)

    async def query_vector(self, question: str, timeout_s: float) -> tuple[list[float], str]:
        """The vector of a question and the space it belongs to. Repeated questions come from a cache (kept
        in memory only: customers' questions are not stored). No retry: a search cannot wait."""
        config = await self._config()
        key = (config.space, config.query_prefix, question.strip())
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached, config.space
        (vector,) = await asyncio.wait_for(
            self._client.embed(config, [config.query_prefix + question.strip()], timeout_s=timeout_s),
            timeout_s,
        )
        self._cache[key] = vector
        while len(self._cache) > QUERY_CACHE:
            self._cache.popitem(last=False)
        return vector, config.space

    async def status(self) -> EmbedStatus:
        config = await self._config()
        if not config.ready:
            return EmbedStatus("off", KEY_BROKEN if config.key_broken else NOT_CONNECTED, 0, None, None)
        missing = await self._store.missing_count(config.space)
        if self._error is not None:
            return EmbedStatus("error", self._error, missing, config.model, self._last_ok)
        return EmbedStatus("working" if missing else "ok", None, missing, config.model, self._last_ok)

    def _succeeded(self) -> None:
        self._error = None
        self._last_ok = self._clock()

    async def _wait(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), seconds)
        self._wake.clear()
