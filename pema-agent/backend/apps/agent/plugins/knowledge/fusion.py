"""Merging the keyword list and the vector list of a search: reciprocal rank fusion. Pure, no I/O."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Final

from .models import Hit

RRF_K: Final = 60
"""The usual constant: it keeps one list's first place from outweighing a chunk both lists rank well."""


def fuse(ranked: Sequence[Sequence[Hit]], k: int = RRF_K) -> list[Hit]:
    """Each chunk scores the sum of ``1 / (k + rank)`` over the lists it is in (rank from 1).

    The Hit kept for a chunk is its first appearance (keyword list first) with its score replaced by the RRF
    score. Ties keep the order of first appearance.
    """
    scores: dict[str, float] = {}
    first: dict[str, Hit] = {}
    for hits in ranked:
        for rank, hit in enumerate(hits, start=1):
            scores[hit.chunk.id] = scores.get(hit.chunk.id, 0.0) + 1.0 / (k + rank)
            first.setdefault(hit.chunk.id, hit)
    # sorted() is stable: equal scores keep the order the chunks were first seen in
    order = sorted(first, key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [replace(first[chunk_id], score=scores[chunk_id]) for chunk_id in order]
