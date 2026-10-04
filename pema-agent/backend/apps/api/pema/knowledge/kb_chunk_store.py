# ported from: src/knowledge/kb-chunk-store.ts
"""Save/delete the chunks of a knowledge-base source, keeping the full-text column and the vector column in
step with the content. Schema: Alembic 0002 (``agent.kb_chunk``).

Forced deviations (SQLite -> Postgres, sync -> async):
* ``kb_chunks`` + the virtual table ``kb_chunks_fts`` are ONE table ``agent.kb_chunk``: the full-text index is
  the generated column ``tsv`` (``to_tsvector('simple', folded)``), so it cannot get out of step with the
  content. The original needed a rowid trick (``rowid`` of the FTS table assigned explicitly to
  ``kb_chunks.id``) and manual deletes of the FTS rows; none of that exists here;
* columns ``thu_tu, tieu_de, noi_dung, phang`` -> ``ord, title, content, folded``;
* the ``folded`` column holds the diacritics-folded text AS TOKENS joined by one space (every run of
  letters/digits is a token, anything else is a separator): this is the role the ``unicode61`` tokenizer
  played in the original, and it keeps the Postgres parser from reading "20.000" as one number token or
  "a-b" as a compound;
* new: ``embeddings`` - the bge-m3 vector of each chunk (``vector(1024)``) when an embedding client is
  configured. ``None`` stores no vector: the chunk is still found by the full-text side.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.knowledge.chunk_text import DoanMoi
from pema.knowledge.kb_fts_query import tach_tu_khoa

__all__ = [
    "DoanCuaNguon",
    "DoanMoi",
    "DoanTraNguoc",
    "dem_doan",
    "lay_doan_cua_nguon",
    "lay_doan_theo_id",
    "luu_doan",
    "van_ban_de_nhung",
    "vector_literal",
]


def van_ban_de_nhung(ten_nguon: str, d: DoanMoi) -> str:
    """The text a chunk is embedded from: source name + heading breadcrumb + body - the same three parts that
    enter the full-text column (but with their diacritics: bge-m3 reads Vietnamese properly)."""
    return " ".join(p for p in (ten_nguon, d.tieu_de, d.noi_dung) if p)


def vector_literal(vector: list[float]) -> str:
    """pgvector text form ``[0.1,0.2,...]``, passed as a parameter and cast with ``CAST(:v AS vector)``."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


async def luu_doan(
    session: AsyncSession,
    clinic_id: UUID,
    source_id: str,
    doan: list[DoanMoi],
    ten_nguon: str = "",
    embeddings: list[list[float]] | None = None,
) -> None:
    """REPLACE all the chunks of the source, never accumulate: each re-cut of a document counts as a new
    final copy, not a patch on the old one - delete the old chunks, insert again from the start, in the
    caller's transaction.

    ``ten_nguon`` defaults to "" (NOT required) - on purpose, so the dozens of call sites that only load
    fixtures need not be touched (they do not need the source name in the index). The REAL ingest path
    (``kb_ingest_worker``) MUST pass the real source name: without it, looking up the exact DOCUMENT NAME /
    SOURCE NAME comes back empty (I1) all over again."""
    if embeddings is not None and len(embeddings) != len(doan):
        raise ValueError("Số vector embedding phải bằng số đoạn")

    await session.execute(
        text("DELETE FROM agent.kb_chunk WHERE clinic_id = :c AND source_id = :s"),
        {"c": clinic_id, "s": source_id},
    )
    if not doan:
        return
    rows: list[dict[str, object]] = []
    for i, d in enumerate(doan):
        # Source name + heading (breadcrumb H1>H2>H3, see chunk_text) ALSO go into the folded column: a
        # customer who asks with the very DOCUMENT NAME or SOURCE NAME (e.g. "chính sách đổi trả", "bảng
        # giá quán") must find the chunk, not only match the body - exactly bug I1. ``filter`` drops empty
        # parts so no stray space is left when the name/heading is blank.
        phang = " ".join(tach_tu_khoa(" ".join(p for p in (ten_nguon, d.tieu_de, d.noi_dung) if p)))
        rows.append(
            {
                "c": clinic_id,
                "s": source_id,
                "ord": d.thu_tu,
                "title": d.tieu_de,
                "content": d.noi_dung,
                "folded": phang,
                "emb": vector_literal(embeddings[i]) if embeddings is not None else None,
            }
        )
    await session.execute(
        text(
            "INSERT INTO agent.kb_chunk (clinic_id, source_id, ord, title, content, folded, embedding) "
            "VALUES (:c, :s, :ord, :title, :content, :folded, CAST(:emb AS vector))"
        ),
        rows,
    )


async def dem_doan(session: AsyncSession, clinic_id: UUID, source_id: str) -> int:
    return int(
        (
            await session.execute(
                text("SELECT count(*) FROM agent.kb_chunk WHERE clinic_id = :c AND source_id = :s"),
                {"c": clinic_id, "s": source_id},
            )
        ).scalar_one()
    )


@dataclass(frozen=True, slots=True)
class DoanCuaNguon:
    thu_tu: int
    tieu_de: str
    noi_dung: str


async def lay_doan_cua_nguon(
    session: AsyncSession, clinic_id: UUID, source_id: str, offset: int, limit: int
) -> list[DoanCuaNguon]:
    """A page of the chunks of ONE source, PAGINATION is mandatory (I21 - dashboard) - a long source (a manual
    of hundreds of pages) can be cut into thousands of chunks, and pulling all of them at once is exactly the
    OOM that ``kb_route_guards`` already blocks on the upload path and must not be reopened on the READ path.
    ``tieu_de`` ALWAYS comes along (even when empty) - the only breadcrumb with which the operator can notice
    that the bot misread the structure of a document (H1>H2>H3, see chunk_text) without turning on
    AGENT_TRACE_ENABLED."""
    rows = (
        await session.execute(
            text(
                "SELECT ord, title, content FROM agent.kb_chunk WHERE clinic_id = :c AND source_id = :s "
                "ORDER BY ord ASC, id ASC LIMIT :limit OFFSET :offset"
            ),
            {"c": clinic_id, "s": source_id, "limit": limit, "offset": offset},
        )
    ).all()
    return [DoanCuaNguon(thu_tu=int(r[0]), tieu_de=r[1], noi_dung=r[2]) for r in rows]


@dataclass(frozen=True, slots=True)
class DoanTraNguoc:
    id: int
    source_id: str
    ten_nguon: str
    tieu_de: str
    noi_dung: str


async def lay_doan_theo_id(session: AsyncSession, clinic_id: UUID, ids: list[int]) -> list[DoanTraNguoc]:
    """Look chunks up from their ids, ALREADY joined to ``agent.kb_document`` for the source name. The search
    needs ``ten_nguon`` so the model can cite the source to the customer - the join is here and not left to
    the caller, so two places do not both know how to join the tables.

    Returns in EXACTLY the order of the ``ids`` passed in (the order decided by RRF), not the order SQL
    returns. An ``id`` that no longer exists (the chunk was just deleted between the search and this lookup)
    is silently skipped, no raise."""
    if not ids:
        return []
    rows = (
        await session.execute(
            text(
                "SELECT c.id, c.source_id, d.name, c.title, c.content FROM agent.kb_chunk c "
                "JOIN agent.kb_document d ON d.clinic_id = c.clinic_id AND d.id = c.source_id "
                "WHERE c.clinic_id = :c AND c.id = ANY(:ids)"
            ),
            {"c": clinic_id, "ids": ids},
        )
    ).all()
    theo_id = {
        int(r[0]): DoanTraNguoc(id=int(r[0]), source_id=r[1], ten_nguon=r[2], tieu_de=r[3], noi_dung=r[4])
        for r in rows
    }
    return [theo_id[i] for i in ids if i in theo_id]
