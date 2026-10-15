"""Small to big: the section around a chunk the search found (``plugins/knowledge/section.py``), and the searcher
reading it when asked."""

from __future__ import annotations

from datetime import UTC, date, datetime

from plugins.knowledge.ingest import make_chunks
from plugins.knowledge.models import Chunk, Hit, Source
from plugins.knowledge.search import Searcher
from plugins.knowledge.section import in_section, parent_of, widen
from plugins.knowledge.store import InMemoryKnowledgeStore
from plugins.knowledge.text import chunk, content_hash

TITLE = "Đổi và hủy lịch"


def _chunk(number: int, heading: str, body: str, parent: str = TITLE) -> Chunk:
    return Chunk(id=f"c{number}", source_id="s1", ordinal=number, path=f"{parent} > {heading}", body=body)


def _hit(item: Chunk) -> Hit:
    return Hit(item, TITLE, "D13", 1.0)


def test_a_chunk_with_a_heading_under_the_title_sits_in_a_section_but_one_with_only_a_title_does_not() -> (
    None
):
    assert parent_of(f"{TITLE} > Phí") == TITLE
    assert parent_of(f"{TITLE} > Mục > Phí") == f"{TITLE} > Mục"
    assert parent_of(TITLE) == ""


def test_a_path_is_in_a_section_when_it_is_the_parent_or_below_it_but_not_a_longer_name() -> None:
    assert in_section(TITLE, TITLE)
    assert in_section(f"{TITLE} > Phí", TITLE)
    assert not in_section(f"{TITLE} hôm nay > Phí", TITLE)


def test_a_hit_becomes_its_section_with_each_chunk_under_its_own_heading() -> None:
    members = [
        _chunk(1, "Báo trước", "24 giờ."),
        _chunk(2, "Phí", "200.000 đồng."),
        _chunk(3, "Đổi lịch", "2 lần."),
    ]

    widened, taken = widen(_hit(members[1]), members)

    assert widened.chunk.path == TITLE
    assert widened.chunk.body == "Báo trước\n24 giờ.\n\nPhí\n200.000 đồng.\n\nĐổi lịch\n2 lần."
    assert widened.chunk.id == "c2"
    assert taken == {"c1", "c2", "c3"}


def test_a_long_section_is_cut_to_the_chunks_nearest_the_hit() -> None:
    members = [_chunk(n, f"Mục {n}", "x" * 40) for n in range(1, 8)]

    widened, taken = widen(_hit(members[3]), members, limit=130)

    assert taken == {"c3", "c4", "c5"}
    assert widened.chunk.body.count("Mục") == 3


def test_a_chunk_that_fills_the_limit_by_itself_or_has_no_neighbour_is_left_as_it_is() -> None:
    members = [_chunk(1, "Dài", "y" * 200), _chunk(2, "Ngắn", "z")]
    only = _chunk(9, "Một mình", "w")

    long_one, taken = widen(_hit(members[0]), members, limit=100)
    alone, alone_taken = widen(_hit(only), [only])

    assert (long_one.chunk, taken) == (members[0], {"c1"})
    assert (alone.chunk, alone_taken) == (only, {"c9"})


async def _store() -> InMemoryKnowledgeStore:
    body = (
        f"# {TITLE}\n\n### Báo trước tối thiểu\n\nKhách báo trước ít nhất 24 giờ thì lịch được đổi hoặc hủy mà không mất phí.\n\n"
        "### Phí báo muộn\n\nKhách báo dưới 24 giờ hoặc không đến buổi hẹn thì phải trả phí 200.000 đồng cho buổi đó.\n\n"
        "### Số lần đổi\n\nMỗi gói liệu trình được đổi lịch miễn phí 2 lần, từ lần thứ ba tính phí đổi lịch."
    )
    now = datetime(2026, 10, 1, tzinfo=UTC)
    source = Source(
        id="s1",
        title=TITLE,
        doc_code="D13",
        kind="file",
        format="md",
        size=len(body),
        audience="patient",
        lifecycle="active",
        content_hash=content_hash(body),
        created_by="test",
        markdown=body,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        created_at=now,
        updated_at=now,
    )
    store = InMemoryKnowledgeStore()
    await store.add_source(source, make_chunks("s1", TITLE, chunk(body, TITLE), []))
    return store


async def test_the_search_reads_the_section_only_when_asked_and_never_the_same_chunk_twice() -> None:
    store = await _store()
    plain = Searcher(store)
    wide = Searcher(store, expand_chars=1200)

    alone = await plain.search("phí báo muộn", date(2026, 10, 12), results=6, char_budget=6000, services=[])
    around = await wide.search("phí báo muộn", date(2026, 10, 12), results=6, char_budget=6000, services=[])

    assert "đổi lịch miễn phí 2 lần" not in alone.final[0].chunk.body
    assert around.final[0].chunk.path == TITLE
    assert "đổi lịch miễn phí 2 lần" in around.final[0].chunk.body
    assert "200.000 đồng" in around.final[0].chunk.body
    assert len(around.final) == 1
