"""Reciprocal rank fusion of the keyword list and the vector list."""

from __future__ import annotations

import pytest

from plugins.knowledge.fusion import fuse
from plugins.knowledge.models import Chunk, Hit


def _hit(name: str, score: float = 0.0) -> Hit:
    return Hit(Chunk(id=name, source_id="s", ordinal=1, path="p", body=name), "T", None, score)


def _ids(hits: list[Hit]) -> list[str]:
    return [hit.chunk.id for hit in hits]


def test_a_chunk_in_both_lists_comes_first_and_scores_the_formula() -> None:
    keyword = [_hit("a", 9.0), _hit("b", 5.0)]
    vector = [_hit("b", 0.8), _hit("c", 0.5)]

    fused = fuse([keyword, vector])

    assert _ids(fused) == ["b", "a", "c"]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1].score == pytest.approx(1 / 61)
    assert fused[2].score == pytest.approx(1 / 62)


def test_first_place_in_both_lists_scores_two_over_sixty_one() -> None:
    (only,) = fuse([[_hit("a")], [_hit("a")]])

    assert only.score == pytest.approx(2 / 61)


def test_the_hit_kept_is_its_first_appearance_with_the_new_score() -> None:
    fused = fuse([[_hit("a", 9.0)], [_hit("a", 0.8)]])

    assert fused[0].chunk.id == "a"
    assert fused[0].score != 9.0


def test_one_empty_list_leaves_the_other_in_order() -> None:
    assert _ids(fuse([[_hit("a"), _hit("b"), _hit("c")], []])) == ["a", "b", "c"]
    assert _ids(fuse([[], [_hit("x"), _hit("y")]])) == ["x", "y"]


def test_ties_keep_the_order_of_first_appearance() -> None:
    assert _ids(fuse([[_hit("a")], [_hit("b")]])) == ["a", "b"]


def test_nothing_in_nothing_out() -> None:
    assert fuse([]) == []
    assert fuse([[], []]) == []
