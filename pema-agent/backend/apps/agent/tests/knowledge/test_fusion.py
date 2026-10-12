"""Merging the vector list and the keyword list: the vector list leads and the keyword list follows."""

from __future__ import annotations

from plugins.knowledge.fusion import vector_first
from plugins.knowledge.models import Chunk, Hit


def _hit(name: str, score: float) -> Hit:
    return Hit(Chunk(id=name, source_id="s", ordinal=1, path="p", body=name), "T", None, score)


def _ids(hits: list[Hit]) -> list[str]:
    return [hit.chunk.id for hit in hits]


def test_vector_chunks_come_first_in_their_order_then_the_keyword_chunks_they_lack() -> None:
    vector = [_hit("v1", 0.9), _hit("v2", 0.6)]
    keyword = [_hit("k1", 12.0), _hit("v2", 8.0), _hit("k2", 5.0)]

    merged = vector_first(vector, keyword)

    assert _ids(merged) == ["v1", "v2", "k1", "k2"]


def test_vector_chunks_keep_their_similarity_as_score() -> None:
    merged = vector_first([_hit("v1", 0.9), _hit("v2", 0.6)], [_hit("k1", 12.0)])

    assert [hit.score for hit in merged[:2]] == [0.9, 0.6]


def test_keyword_chunks_score_below_the_weakest_vector_chunk_so_sorting_keeps_the_order() -> None:
    vector = [_hit("v1", 0.9), _hit("v2", 0.36)]
    keyword = [_hit("k1", 99.0), _hit("k2", 98.0), _hit("k3", 97.0)]

    merged = vector_first(vector, keyword)

    assert all(hit.score < 0.36 for hit in merged[2:])
    assert _ids(sorted(merged, key=lambda hit: hit.score, reverse=True)) == _ids(merged)


def test_without_vector_chunks_the_keyword_chunks_are_kept_in_order_below_one() -> None:
    merged = vector_first([], [_hit("k1", 12.0), _hit("k2", 5.0)])

    assert _ids(merged) == ["k1", "k2"]
    assert all(hit.score < 1 for hit in merged)


def test_nothing_in_nothing_out() -> None:
    assert vector_first([], []) == []
