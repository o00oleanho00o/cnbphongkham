"""Vectors in the in-memory store: which texts still need one, cosine search in force on the day asked, what a
chunk reports, and what is thrown away. (The Postgres store has the same tests in test_knowledge_db.py.)"""

from __future__ import annotations

from datetime import UTC, date, datetime

from plugins.knowledge.ingest import make_chunks
from plugins.knowledge.models import Chunk, Source
from plugins.knowledge.store import InMemoryKnowledgeStore
from plugins.knowledge.text import Piece, content_hash, embed_text_of, text_hash

SPACE = "0123456789abcdef"
OTHER = "fedcba9876543210"
NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _source(source_id: str, title: str, *, lifecycle: str = "active", start: date | None = None) -> Source:
    return Source(
        id=source_id,
        title=title,
        doc_code=title,
        kind="file",
        format="md",
        size=1,
        audience="patient",
        lifecycle=lifecycle,  # type: ignore[arg-type]  # a test value of the Lifecycle literal
        content_hash=content_hash(title),
        created_by="test",
        effective_from=start,
        created_at=NOW,
        updated_at=NOW,
    )


async def _add(store: InMemoryKnowledgeStore, source: Source, *bodies: str) -> list[Chunk]:
    chunks = make_chunks(
        source.id, source.title, [Piece(f"Mục {i}", body) for i, body in enumerate(bodies)], []
    )
    await store.add_source(source, chunks)
    return chunks


def _unit(*values: float) -> list[float]:
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values]


async def test_missing_vectors_lists_each_text_once_and_saving_is_idempotent() -> None:
    store = InMemoryKnowledgeStore()
    first, second = await _add(store, _source("src-a", "A"), "một", "hai")
    (third,) = await _add(
        store, _source("src-b", "B"), "một"
    )  # the same body under another title: another text

    wanting = await store.missing_vectors(SPACE, 10)

    assert len(wanting) == 3
    assert {hash_ for hash_, _ in wanting} == {c.embed_hash for c in (first, second, third)}
    assert await store.missing_count(SPACE) == 3

    await store.save_vectors(SPACE, [(first.embed_hash, _unit(1, 0))])
    await store.save_vectors(SPACE, [(first.embed_hash, _unit(0, 1))])  # a second save changes nothing

    assert await store.missing_count(SPACE) == 2
    assert len(await store.missing_vectors(SPACE, 10)) == 2
    assert len(await store.missing_vectors(SPACE, 1)) == 1


async def test_chunks_with_the_same_text_share_one_vector_and_count_separately() -> None:
    store = InMemoryKnowledgeStore()
    source = _source("src-a", "A")
    twins = make_chunks(source.id, source.title, [Piece("Mục", "giống"), Piece("Mục", "giống")], [])
    await store.add_source(source, twins)
    assert twins[0].embed_hash == twins[1].embed_hash != ""

    assert len(await store.missing_vectors(SPACE, 10)) == 1
    assert await store.missing_count(SPACE) == 2


async def test_a_draft_or_old_source_is_not_embedded_but_a_future_one_is() -> None:
    store = InMemoryKnowledgeStore()
    await _add(store, _source("src-d", "D", lifecycle="draft"), "nháp")
    await _add(store, _source("src-o", "O", lifecycle="superseded"), "cũ")
    await _add(store, _source("src-f", "F", start=date(2099, 1, 1)), "tương lai")

    wanting = await store.missing_vectors(SPACE, 10)

    assert [text for _, text in wanting] == [embed_text_of("F", "Mục 0", "tương lai")]


async def test_vectors_are_found_by_cosine_in_force_on_the_day_asked() -> None:
    store = InMemoryKnowledgeStore()
    new = _source("src-new", "NEW", start=date(2026, 10, 1))
    old = _source("src-old", "OLD", start=date(2026, 1, 1))
    old.effective_to = date(2026, 9, 30)
    (new_chunk,) = await _add(store, new, "giá mới")
    (old_chunk,) = await _add(store, old, "giá cũ")
    await store.save_vectors(
        SPACE, [(new_chunk.embed_hash, _unit(1, 0)), (old_chunk.embed_hash, _unit(1, 1))]
    )

    today = await store.vector_search(SPACE, _unit(1, 0), date(2026, 10, 12), 5, 0.0)
    before = await store.vector_search(SPACE, _unit(1, 0), date(2026, 9, 15), 5, 0.0)

    assert [hit.doc_code for hit in today] == ["NEW"]
    assert today[0].score == 1.0
    assert today[0].chunk.embedded
    assert [hit.doc_code for hit in before] == ["OLD"]
    assert before[0].score == 2**-0.5 or abs(before[0].score - 2**-0.5) < 1e-9


async def test_the_similarity_floor_and_the_limit_apply_best_first() -> None:
    store = InMemoryKnowledgeStore()
    chunks = await _add(store, _source("src-a", "A"), "x", "y", "z")
    await store.save_vectors(
        SPACE,
        [
            (chunks[0].embed_hash, _unit(1, 0)),
            (chunks[1].embed_hash, _unit(3, 1)),
            (chunks[2].embed_hash, _unit(0, 1)),
        ],
    )

    close = await store.vector_search(SPACE, _unit(1, 0), date(2026, 10, 12), 5, 0.5)
    limited = await store.vector_search(SPACE, _unit(1, 0), date(2026, 10, 12), 1, 0.0)

    assert [hit.chunk.id for hit in close] == [chunks[0].id, chunks[1].id]
    assert [hit.chunk.id for hit in limited] == [chunks[0].id]


async def test_another_space_finds_nothing() -> None:
    store = InMemoryKnowledgeStore()
    (chunk,) = await _add(store, _source("src-a", "A"), "x")
    await store.save_vectors(SPACE, [(chunk.embed_hash, _unit(1, 0))])

    assert await store.vector_search(OTHER, _unit(1, 0), date(2026, 10, 12), 5, 0.0) == []


async def test_chunks_report_whether_they_have_a_vector() -> None:
    store = InMemoryKnowledgeStore()
    first, _ = await _add(store, _source("src-a", "A"), "x", "y")
    await store.save_vectors(SPACE, [(first.embed_hash, _unit(1, 0))])

    with_vectors, _ = await store.chunks("src-a", "", 1, 10, SPACE)
    without_space, _ = await store.chunks("src-a", "", 1, 10, None)
    other_space, _ = await store.chunks("src-a", "", 1, 10, OTHER)

    assert [c.embedded for c in with_vectors] == [True, False]
    assert not any(c.embedded for c in without_space)
    assert not any(c.embedded for c in other_space)
    assert await store.vector_counts(SPACE) == {"src-a": 1}
    assert await store.vector_counts(OTHER) == {}


async def test_clearing_a_space_removes_only_its_vectors() -> None:
    store = InMemoryKnowledgeStore()
    (chunk,) = await _add(store, _source("src-a", "A"), "x")
    await store.save_vectors(SPACE, [(chunk.embed_hash, _unit(1, 0))])
    await store.save_vectors(OTHER, [(chunk.embed_hash, _unit(0, 1))])

    assert await store.clear_vectors(SPACE) == 1

    assert await store.missing_count(SPACE) == 1
    assert await store.missing_count(OTHER) == 0


async def test_stale_vectors_are_other_spaces_and_texts_no_chunk_has_any_more() -> None:
    store = InMemoryKnowledgeStore()
    (chunk,) = await _add(store, _source("src-a", "A"), "x")
    await store.save_vectors(SPACE, [(chunk.embed_hash, _unit(1, 0)), (text_hash("gone"), _unit(0, 1))])
    await store.save_vectors(OTHER, [(chunk.embed_hash, _unit(1, 0))])

    assert await store.drop_stale_vectors(SPACE) == 2

    assert await store.missing_count(SPACE) == 0
    assert await store.missing_count(OTHER) == 1
    assert await store.drop_stale_vectors(SPACE) == 0


async def test_re_cutting_a_source_with_the_same_text_keeps_its_vectors() -> None:
    store = InMemoryKnowledgeStore()
    source = _source("src-a", "A")
    (chunk,) = await _add(store, source, "x")
    await store.save_vectors(SPACE, [(chunk.embed_hash, _unit(1, 0))])

    again = make_chunks("src-a", "A", [Piece("Mục 0", "x")], [])
    await store.replace_chunks("src-a", again)

    assert again[0].embed_hash == chunk.embed_hash
    assert await store.missing_count(SPACE) == 0
