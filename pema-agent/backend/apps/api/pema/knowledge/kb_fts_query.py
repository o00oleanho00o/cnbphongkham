# ported from: src/knowledge/kb-fts-query.ts
"""Build a SAFE full-text query for ``agent.kb_chunk.tsv`` and run the keyword ranking on it.

The customer's question goes straight in here - it may contain ``-``, ``*``, ``"``, ``(``, ``:``, ``^``,
``'``, ``&``, ``|``, ``!`` which are tsquery/FTS syntax; unquoted, the query raises a syntax error and
the tool dies midway. See ``kb_chunk_store`` (why the ``folded`` column is already diacritics-free).

Forced deviation (SQLite FTS5 ``MATCH`` + ``bm25()`` -> Postgres ``to_tsquery`` + BM25 computed here):
* the query is built from the same tokens (``[letters digits]+`` of the folded question) each wrapped in
  single quotes, which makes it a literal lexeme for ``to_tsquery`` whatever the character, joined by
  ``|`` (OR, not the AND of ``plainto_tsquery``) for the same reason as the original: AND demands every word
  match, and a natural question with an extra word that is not in the document (e.g. "ship" in "phí ship nội
  thành") would match nothing at all;
* Postgres has no ``bm25()`` (``ts_rank``/``ts_rank_cd`` have no IDF part, so a repeated common word beats
  several distinct rare ones - measured on the fixtures of the original: "mấy giờ đóng cửa" ranked the wrong
  chunk). The index finds the CANDIDATES (``tsv @@ query``, filtered by source in the WHERE) and the ranking
  is the same Okapi BM25 as FTS5 (``k1 = 1.2``, ``b = 0.75``, IDF ``ln((N - n + 0.5) / (n + 0.5))`` floored at
  ``1e-6``), computed over the tokens of the folded column, with N, n and the average length taken from the
  sources the agent may read (one aggregate query, no query per term);
* the text config is ``simple`` (no stemming, no stop words, no language): Vietnamese has no stemmer in
  Postgres and the folded text is already ASCII;
* two guards the original did not need (SQLite had none of these limits): a token longer than
  ``TU_DAI_TOI_DA`` is not a word and is dropped (``to_tsquery`` rejects a lexeme over 2046 bytes), and at
  most ``SO_TU_TOI_DA`` tokens are used; at most ``SO_UNG_VIEN_TOI_DA`` candidates are ranked (the best by the
  cheap ``ts_rank_cd`` when more match).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.shared.bo_dau_tieng_viet import bo_dau_tieng_viet

TU_KHOA_RE: Final = re.compile(r"[^\W_]+")
"""A token: letters and digits (``\\p{L}\\p{N}`` of the original; ``\\w`` minus the underscore)."""
TU_DAI_TOI_DA: Final = 100
SO_TU_TOI_DA: Final = 64
SO_UNG_VIEN_TOI_DA: Final = 2000
BM25_K1: Final = 1.2
BM25_B: Final = 0.75
BM25_IDF_SAN: Final = 1e-6


def tach_tu_khoa(cau_hoi: str) -> list[str]:
    """Tokens of the folded text - used for BOTH the stored ``folded`` column and the query, so the two sides
    tokenise identically (the role the ``unicode61`` tokenizer played in the original)."""
    return TU_KHOA_RE.findall(bo_dau_tieng_viet(cau_hoi))


def dung_truy_van_fts(cau_hoi: str) -> str:
    """``""`` when the question has no usable WORD left (only punctuation/emoji) - the caller must check for
    the empty string before running the query, because an empty tsquery matches nothing and Postgres only
    emits a NOTICE."""
    tu_khoa = [t for t in tach_tu_khoa(cau_hoi) if len(t) <= TU_DAI_TOI_DA][:SO_TU_TOI_DA]
    if not tu_khoa:
        return ""
    return " | ".join(f"'{tu}'" for tu in tu_khoa)


@dataclass(frozen=True, slots=True)
class KetQuaFts:
    chunk_id: int


def idf_bm25(tong_doan: int, so_doan_chua_tu: int) -> float:
    """IDF of FTS5's ``bm25()``: ``ln((N - n + 0.5) / (n + 0.5))``, never below ``BM25_IDF_SAN`` (a word in
    most chunks counts for almost nothing instead of negatively)."""
    return max(BM25_IDF_SAN, math.log((tong_doan - so_doan_chua_tu + 0.5) / (so_doan_chua_tu + 0.5)))


def diem_bm25(
    tu_khoa: Sequence[str],
    tokens_doan: Sequence[str],
    idf_theo_tu: dict[str, float],
    do_dai_trung_binh: float,
) -> float:
    """Okapi BM25 of one chunk (its folded tokens) against the query words."""
    if not tokens_doan:
        return 0.0
    tan_suat = Counter(tokens_doan)
    dl = len(tokens_doan)
    diem = 0.0
    for tu in tu_khoa:
        tf = tan_suat.get(tu, 0)
        if tf == 0:
            continue
        mau = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / max(do_dai_trung_binh, 1e-9))
        diem += idf_theo_tu[tu] * tf * (BM25_K1 + 1) / mau
    return diem


async def tim_theo_tu_khoa(
    session: AsyncSession,
    clinic_id: UUID,
    cau_hoi: str,
    source_ids: list[str],
    so_luong: int,
) -> list[KetQuaFts]:
    """Search by keyword, only in the ``source_ids`` passed in - filtered RIGHT IN THE WHERE, not take the top
    and filter afterwards: take the top 50 then filter down to a few sources and the right result, sitting
    beyond rank 50, is lost.

    ``so_luong`` HERE is the number of rows returned - NOT the final number of chunks given to the model. The
    caller (``kb_search``) deliberately passes a number LARGER than the chunks it needs to leave room for
    dedup AFTER: deduplicating after a LIMIT of exactly the needed count comes up short (two duplicate chunks
    take 2 of the few slots and after the dedup one slot is lost instead of being refilled with another
    chunk) - this function does not know that, it returns exactly the count it is given."""
    if not source_ids:
        return []

    match_query = dung_truy_van_fts(cau_hoi)
    if not match_query:
        return []
    tu_khoa = list(dict.fromkeys(t.lower() for t in tach_tu_khoa(cau_hoi) if len(t) <= TU_DAI_TOI_DA))[
        :SO_TU_TOI_DA
    ]

    # ONE aggregate query for the corpus statistics BM25 needs: N, the average length (in tokens) and, per
    # query word, the number of chunks that contain it.
    cot_df = ", ".join(
        f"count(*) FILTER (WHERE tsv @@ to_tsquery('simple', :t{i})) AS df{i}" for i in range(len(tu_khoa))
    )
    tham_so_tu = {f"t{i}": f"'{tu}'" for i, tu in enumerate(tu_khoa)}
    thong_ke = (
        (
            await session.execute(
                text(
                    "SELECT count(*) AS n, "  # noqa: S608 - the aliases are built from integers only
                    "COALESCE(avg(cardinality(string_to_array(folded, ' '))), 1) AS avgdl, "
                    + cot_df
                    + " FROM agent.kb_chunk WHERE clinic_id = :c AND source_id = ANY(:ids)"
                ),
                {"c": clinic_id, "ids": source_ids, **tham_so_tu},
            )
        )
        .mappings()
        .one()
    )
    tong_doan = int(thong_ke["n"])
    do_dai_trung_binh = float(thong_ke["avgdl"])
    idf_theo_tu = {tu: idf_bm25(tong_doan, int(thong_ke[f"df{i}"])) for i, tu in enumerate(tu_khoa)}

    ung_vien = (
        await session.execute(
            text(
                "SELECT c.id, c.folded FROM agent.kb_chunk c "
                "WHERE c.clinic_id = :c AND c.source_id = ANY(:ids) "
                "AND c.tsv @@ to_tsquery('simple', :q) "
                "ORDER BY ts_rank_cd(c.tsv, to_tsquery('simple', :q), 1) DESC, c.id "
                "LIMIT :cap"
            ),
            {"c": clinic_id, "ids": source_ids, "q": match_query, "cap": SO_UNG_VIEN_TOI_DA},
        )
    ).all()
    xep_hang = sorted(
        (
            (int(r[0]), diem_bm25(tu_khoa, r[1].lower().split(), idf_theo_tu, do_dai_trung_binh))
            for r in ung_vien
        ),
        key=lambda x: (-x[1], x[0]),
    )
    return [KetQuaFts(chunk_id=chunk_id) for chunk_id, _ in xep_hang[:so_luong]]
