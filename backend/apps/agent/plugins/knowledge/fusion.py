"""Merging the vector list and the keyword list of a search: the vector list leads. Pure, no I/O.

Measured on the Pema demo corpus (docs/PLAN-knowledge-embedding.md §10, §12): the right document is in the top
three for 30/30 questions by vector alone and 27/30 when both lists are merged by rank, because the keyword
list on Postgres puts unrelated documents first for short questions. So the keyword list only follows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Final

from .models import Hit

KEYWORD_SHARE: Final = 0.5
RRF_K: Final = 60
"""The constant of reciprocal rank fusion: the larger, the flatter the difference between places."""
"""A keyword-only chunk scores at most this share of the weakest vector chunk: it always ranks after them."""


def vector_first(vector: Sequence[Hit], keyword: Sequence[Hit]) -> list[Hit]:
    """The vector chunks in their order, then the keyword chunks they do not already contain, in theirs.

    Vector chunks keep their similarity as score. A keyword-only chunk gets a score below the weakest vector
    chunk (``KEYWORD_SHARE`` of it, falling with its place in the keyword list), so that sorting the result by
    score, as the search does after boosting chunks of a named service, keeps this order.
    """
    seen = {hit.chunk.id for hit in vector}
    ceiling = min((hit.score for hit in vector), default=1.0) * KEYWORD_SHARE
    after = [
        replace(hit, score=ceiling / (rank + 1))
        for rank, hit in enumerate(h for h in keyword if h.chunk.id not in seen)
    ]
    return [*vector, *after]


def rank_fusion(lists: Sequence[Sequence[Hit]]) -> list[Hit]:
    """Several ranked lists of one search (the question and its variants) as one. A chunk scores the sum of
    ``1 / (RRF_K + place)`` over the lists that hold it, so a chunk that several of them find leads; it keeps
    the data of the first hit that held it, and equal scores keep the order they were first seen in."""
    scores: dict[str, float] = {}
    first: dict[str, Hit] = {}
    for hits in lists:
        for place, hit in enumerate(hits, start=1):
            scores[hit.chunk.id] = scores.get(hit.chunk.id, 0.0) + 1.0 / (RRF_K + place)
            first.setdefault(hit.chunk.id, hit)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [replace(first[chunk_id], score=score) for chunk_id, score in ordered]
