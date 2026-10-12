"""The embed job, the cache of question vectors, the status the page shows, and what a search does when the
vector branch is off, failing or slow (it must give exactly the keyword result)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import date

import httpx
import pytest

from plugins.knowledge.embedder import Embedder
from plugins.knowledge.embedding import EmbeddingClient, EmbeddingConfig, EmbeddingError
from plugins.knowledge.ingest import make_chunks
from plugins.knowledge.models import Source
from plugins.knowledge.search import Searcher, VectorPlan
from plugins.knowledge.store import InMemoryKnowledgeStore
from plugins.knowledge.text import Piece, content_hash
from tests.knowledge.fake_embedding import (
    BASE_URL,
    DIMENSIONS,
    KEY,
    embeddings_transport,
    slow_transport,
    status_transport,
)

ASKED = date(2026, 10, 12)


def _config(**changes: object) -> EmbeddingConfig:
    values: dict[str, object] = {
        "base_url": BASE_URL,
        "model": "fake",
        "dimensions": DIMENSIONS,
        "query_prefix": "",
        "document_prefix": "",
        "api_key": KEY,
    }
    return EmbeddingConfig(**{**values, **changes})  # type: ignore[arg-type]  # test values of the config's fields


def _embedder(
    store: InMemoryKnowledgeStore, transport: httpx.MockTransport, config: EmbeddingConfig | None = None
) -> Embedder:
    current = config or _config()

    async def read() -> EmbeddingConfig:
        return current

    return Embedder(store, EmbeddingClient(transport=transport), read, logger=logging.getLogger("test"))


async def _fill(store: InMemoryKnowledgeStore, title: str, *bodies: str) -> None:
    source = Source(
        id=f"src-{title.lower()}",
        title=title,
        doc_code=title,
        kind="file",
        format="md",
        size=1,
        audience="patient",
        lifecycle="active",
        content_hash=content_hash(title),
        created_by="test",
    )
    pieces = [Piece(f"Mục {i}", body) for i, body in enumerate(bodies)]
    await store.add_source(source, make_chunks(source.id, title, pieces, []))


@contextlib.asynccontextmanager
async def _running(embedder: Embedder):
    task = asyncio.create_task(embedder.run())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_the_job_embeds_every_text_in_batches_of_sixteen() -> None:
    store = InMemoryKnowledgeStore()
    await _fill(store, "D", *[f"đoạn số {i} nói về giá" for i in range(20)])
    calls: list[list[str]] = []
    embedder = _embedder(store, embeddings_transport(calls))

    assert await embedder.step() is True
    assert await embedder.step() is True
    assert await embedder.step() is False

    assert [len(batch) for batch in calls] == [16, 4]
    assert await store.missing_count(_config().space) == 0


async def test_texts_are_sent_with_the_document_prefix() -> None:
    store = InMemoryKnowledgeStore()
    await _fill(store, "D", "một đoạn")
    calls: list[list[str]] = []

    await _embedder(store, embeddings_transport(calls), _config(document_prefix="Passage: ")).step()

    assert calls[0][0].startswith("Passage: D\nMục 0\n\nmột đoạn")


async def test_nothing_is_sent_while_the_service_is_not_connected() -> None:
    store = InMemoryKnowledgeStore()
    await _fill(store, "D", "một đoạn")
    calls: list[list[str]] = []

    assert await _embedder(store, embeddings_transport(calls), _config(api_key="")).step() is False
    assert calls == []


async def test_a_transient_error_is_tried_once_more_at_once() -> None:
    store = InMemoryKnowledgeStore()
    await _fill(store, "D", "một đoạn")
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        if len(seen) == 1:
            return httpx.Response(500, text="blip")
        return embeddings_transport([]).handler(request)  # type: ignore[attr-defined,no-any-return]

    embedder = _embedder(store, httpx.MockTransport(handler))

    assert await embedder.step() is True
    assert len(seen) == 2


async def test_a_wrong_key_is_not_retried() -> None:
    store = InMemoryKnowledgeStore()
    await _fill(store, "D", "một đoạn")
    calls: list[list[str]] = []

    with pytest.raises(EmbeddingError) as raised:
        await _embedder(store, status_transport(401, calls)).step()

    assert raised.value.kind == "auth"
    assert len(calls) == 1


async def test_the_query_vector_is_cached() -> None:
    store = InMemoryKnowledgeStore()
    calls: list[list[str]] = []
    embedder = _embedder(store, embeddings_transport(calls))

    first, space = await embedder.query_vector("  giá nám  ", 5)
    again, same = await embedder.query_vector("giá nám", 5)
    await embedder.query_vector("hủy lịch", 5)

    assert first == again
    assert space == same == _config().space
    assert [len(batch) for batch in calls] == [1, 1]


async def test_the_query_prefix_goes_in_front_of_the_question_but_not_into_the_space() -> None:
    store = InMemoryKnowledgeStore()
    calls: list[list[str]] = []
    config = _config(query_prefix="Query: ")

    await _embedder(store, embeddings_transport(calls), config).query_vector("giá nám", 5)

    assert calls == [["Query: giá nám"]]
    assert config.space == _config().space


async def test_the_status_says_off_working_ok_and_error() -> None:
    store = InMemoryKnowledgeStore()
    await _fill(store, "D", "một đoạn")

    off = await _embedder(store, embeddings_transport([]), _config(api_key="")).status()
    broken = await _embedder(store, embeddings_transport([]), _config(api_key="", key_broken=True)).status()
    working = await _embedder(store, embeddings_transport([])).status()
    embedder = _embedder(store, embeddings_transport([]))
    await embedder.step()
    done = await embedder.status()

    assert (off.state, off.missing, off.model) == ("off", 0, None)
    assert off.message is not None
    assert "chưa kết nối" in off.message
    assert broken.message is not None
    assert "không giải mã được" in broken.message
    assert (working.state, working.missing, working.model) == ("working", 1, "fake")
    assert (done.state, done.missing, done.message) == ("ok", 0, None)
    assert done.last_ok_at is not None


async def test_the_status_turns_to_error_when_the_service_fails_and_back_when_it_does_not() -> None:
    store = InMemoryKnowledgeStore()
    await _fill(store, "D", "một đoạn")
    failing = {"on": True}
    good = embeddings_transport([])

    async def handler(request: httpx.Request) -> httpx.Response:
        if failing["on"]:
            return httpx.Response(429, text="slow down")
        return await good.handle_async_request(request)

    embedder = _embedder(store, httpx.MockTransport(handler))
    async with _running(embedder):
        async with asyncio.timeout(5):
            while (await embedder.status()).state != "error":  # noqa: ASYNC110 - the job moves this state on its own
                await asyncio.sleep(0.01)
        shown = await embedder.status()
        failing["on"] = False
        embedder.wake()
        async with asyncio.timeout(5):
            while (await embedder.status()).state != "ok":  # noqa: ASYNC110 - the job moves this state on its own
                await asyncio.sleep(0.01)

    assert shown.message is not None
    assert "giới hạn" in shown.message


async def test_stale_vectors_go_when_the_model_changes() -> None:
    store = InMemoryKnowledgeStore()
    await _fill(store, "D", "một đoạn")
    await _embedder(store, embeddings_transport([]), _config(model="old")).step()
    new = _config(model="new")

    assert await store.missing_count(new.space) == 1
    assert await store.drop_stale_vectors(new.space) == 1
    assert await store.missing_count(_config(model="old").space) == 1


# -- what a search does with the vector branch ---------------------------------------------------------------


async def _searcher(store: InMemoryKnowledgeStore) -> Searcher:
    await _fill(
        store, "BG", "Điều trị nám: một buổi có giá 4.000.000 đồng.", "Hủy lịch trước 24 giờ không mất phí."
    )
    return Searcher(store)


async def _plan(embedder: Embedder, **changes: float) -> VectorPlan:
    return VectorPlan(
        changes.get("min_similarity", 0.5), changes.get("timeout_s", 5.0), embedder.query_vector
    )


async def _keyword_only(searcher: Searcher, question: str) -> list[tuple[str, float]]:
    result = await searcher.search(question, ASKED, results=6, char_budget=6000, services=[])
    return [(hit.chunk.id, hit.score) for hit in result.final]


async def test_without_vectors_the_results_are_the_keyword_results() -> None:
    store = InMemoryKnowledgeStore()
    searcher = await _searcher(store)
    question = "nám một buổi giá bao nhiêu"
    baseline = await _keyword_only(searcher, question)

    result = await searcher.search(question, ASKED, results=6, char_budget=6000, services=[], vector=None)

    assert baseline
    assert [(hit.chunk.id, hit.score) for hit in result.final] == baseline
    assert not result.vector_used
    assert result.vector_skip == "off"
    assert not result.fusion


async def test_a_failing_service_gives_the_keyword_results_unchanged() -> None:
    store = InMemoryKnowledgeStore()
    searcher = await _searcher(store)
    question = "nám một buổi giá bao nhiêu"
    baseline = await _keyword_only(searcher, question)
    embedder = _embedder(store, status_transport(500))

    result = await searcher.search(
        question, ASKED, results=6, char_budget=6000, services=[], vector=await _plan(embedder)
    )

    assert [(hit.chunk.id, hit.score) for hit in result.final] == baseline
    assert result.vector_skip == "error"
    assert result.vector_note is not None
    assert "HTTP 500" in result.vector_note


async def test_a_slow_service_falls_back_to_keywords_after_the_wait() -> None:
    store = InMemoryKnowledgeStore()
    searcher = await _searcher(store)
    question = "nám một buổi giá bao nhiêu"
    baseline = await _keyword_only(searcher, question)
    embedder = _embedder(store, slow_transport(2))

    result = await searcher.search(
        question,
        ASKED,
        results=6,
        char_budget=6000,
        services=[],
        vector=await _plan(embedder, timeout_s=0.05),
    )

    assert [(hit.chunk.id, hit.score) for hit in result.final] == baseline
    assert result.vector_skip == "timeout"
    assert result.vector_note is not None
    assert "quá" in result.vector_note
    assert result.total_ms < 1500


async def test_a_paraphrase_is_found_by_meaning_and_its_chunks_come_first() -> None:
    store = InMemoryKnowledgeStore()
    searcher = await _searcher(store)
    embedder = _embedder(store, embeddings_transport([]))
    while await embedder.step():
        pass
    question = "da bị sạm nâu từng mảng"

    plain = await searcher.search(question, ASKED, results=6, char_budget=6000, services=[])
    hybrid = await searcher.search(
        question, ASKED, results=6, char_budget=6000, services=[], vector=await _plan(embedder)
    )

    assert plain.final == ()
    assert hybrid.vector_used
    assert hybrid.fusion
    assert hybrid.final
    assert "nám" in hybrid.final[0].chunk.body
    assert hybrid.vector[0].score > 0.5
    assert [hit.chunk.id for hit in hybrid.final[: len(hybrid.vector)]] == [
        hit.chunk.id for hit in hybrid.vector
    ][: len(hybrid.final)]
