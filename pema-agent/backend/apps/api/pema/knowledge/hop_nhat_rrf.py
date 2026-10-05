# ported from: src/knowledge/hop-nhat-rrf.ts
"""Reciprocal Rank Fusion (RRF): merge N RANKED lists into one, by RANK and not by the original score of each
list.

Why by rank and not by score: different rankers use scales that cannot be compared (bm25 gives a NEGATIVE
number with no ceiling, cosine similarity of a vector gives 0-1) - adding the scores is adding two different
units. In the original phase there was a SINGLE list (bm25) so this function was the identity; the Python
port has TWO (Postgres full-text rank and pgvector cosine distance) and that is the only extension over the
original: adding the vector list was just adding an element to ``ds``, no change of formula.

Formula: ``diem(item) = sum over the lists of 1 / (k + rank)``, rank counted from 1. A small ``k`` gives
the top of each list more weight.

PURE module: knows nothing about Postgres or any data source. ``khoa_cua`` lets the merge run on any item
type, as long as a key can be derived to recognise "the same item" across lists.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MucHopNhat[T]:
    item: T
    diem: float


def hop_nhat_rrf[T](
    ds: Sequence[Sequence[T]],
    khoa_cua: Callable[[T], str],
    k: float,
) -> list[MucHopNhat[T]]:
    diem_theo_khoa: dict[str, float] = {}
    item_theo_khoa: dict[str, T] = {}

    for danh_sach in ds:
        for chi_so, item in enumerate(danh_sach):
            khoa = khoa_cua(item)
            hang = chi_so + 1  # count from 1, not from 0
            diem_theo_khoa[khoa] = diem_theo_khoa.get(khoa, 0.0) + 1 / (k + hang)
            if khoa not in item_theo_khoa:
                item_theo_khoa[khoa] = item

    ket_qua = [MucHopNhat(item=item_theo_khoa[khoa], diem=diem) for khoa, diem in diem_theo_khoa.items()]
    # sorted() is stable, like Array.prototype.sort: equal scores keep first-seen order.
    return sorted(ket_qua, key=lambda m: m.diem, reverse=True)
