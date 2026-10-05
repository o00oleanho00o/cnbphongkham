# ported from: src/knowledge/kb-source-queries.ts
"""SLIM reads / SQL-side filtering for ``agent.kb_document`` - split from ``kb_source_store`` so the main file
does not grow past 200 lines. The dashboard routes and the worker do not need the whole ``raw_text`` (a hand
typed source can be tens of thousands of characters) nor the whole table (the worker scans every 5 seconds,
and most sources are already ``san_sang``/``hong`` and irrelevant).

Forced deviation (SQLite -> Postgres, sync -> async): see ``kb_source_store``. The claim
(``gianh_nguon_cho_xu_ly``) is ONE ``UPDATE ... WHERE status = 'cho_xu_ly' AND attempts < :tran RETURNING``
statement, which Postgres makes atomic across processes (the original relied on one synchronous process);
under READ COMMITTED a concurrent claimer re-checks the predicate after the first one commits, so exactly
one wins.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.knowledge.kb_source_store import (
    COT_GON,
    KbSourceTomTat,
    TrangThaiNguon,
    bo_noi_dung_goc,
    map_row_gon,
)

__all__ = [
    "KbSourceTomTat",
    "bo_noi_dung_goc",
    "co_nguon_nao",
    "danh_sach_nguon_gon",
    "gianh_nguon_cho_xu_ly",
    "lay_nguon_theo_trang_thai",
    "loc_id_ton_tai",
]


async def danh_sach_nguon_gon(session: AsyncSession, clinic_id: UUID) -> list[KbSourceTomTat]:
    """List WITHOUT ``noi_dung_goc`` - for the dashboard route (``GET /admin/kb/sources``), where the screen
    shows only metadata. The page refreshes by itself every few seconds so pulling the full text along is
    pure wasted bandwidth."""
    rows = (
        (
            await session.execute(
                text(
                    f"SELECT {COT_GON} FROM agent.kb_document "  # noqa: S608 - constant column list
                    "WHERE clinic_id = :c ORDER BY created_at DESC, id"
                ),
                {"c": clinic_id},
            )
        )
        .mappings()
        .all()
    )
    return [map_row_gon(r) for r in rows]


async def lay_nguon_theo_trang_thai(
    session: AsyncSession, clinic_id: UUID, trang_thai: TrangThaiNguon
) -> list[KbSourceTomTat]:
    """List sources in EXACTLY one state - filtered IN SQL, never by pulling the whole table and filtering in
    Python. ``kb_ingest_worker`` calls it every 5s (``cho_xu_ly`` for the scan, ``dang_xu_ly`` to release
    stuck sources).

    WITHOUT ``noi_dung_goc`` (measured in the original: 8 sources x 5 million characters = +30 MB for one
    call if the snapshot pulled the full text of EVERY waiting source into RAM at once) - a ``kind='text'``
    source that needs its text re-read calls ``lay_nguon`` ONE source at a time, exactly when that source is
    really processed."""
    rows = (
        (
            await session.execute(
                text(
                    f"SELECT {COT_GON} FROM agent.kb_document "  # noqa: S608
                    "WHERE clinic_id = :c AND status = :s ORDER BY created_at DESC, id"
                ),
                {"c": clinic_id, "s": trang_thai},
            )
        )
        .mappings()
        .all()
    )
    return [map_row_gon(r) for r in rows]


async def loc_id_ton_tai(session: AsyncSession, clinic_id: UUID, ids: list[str]) -> set[str]:
    """The set of ids that REALLY exist among those passed in - the route that binds sources to an agent uses
    it to block junk ids without pulling the whole table (full text included) to compare in Python."""
    if not ids:
        return set()
    rows = (
        await session.execute(
            text("SELECT id FROM agent.kb_document WHERE clinic_id = :c AND id = ANY(:ids)"),
            {"c": clinic_id, "ids": ids},
        )
    ).scalars()
    return set(rows)


async def gianh_nguon_cho_xu_ly(session: AsyncSession, clinic_id: UUID, id_: str, tran_lan_thu: int) -> bool:
    """Claim a source for processing - succeeds ONLY when the source is in ``cho_xu_ly`` AND has not reached
    ``tran_lan_thu`` at the moment this UPDATE runs (compare-then-change ATOMIC in one statement, not read
    then write in two steps). Returns ``False`` if the source was already claimed/processed by another round,
    or has run out of attempts (the ceiling is normally lowered just before the source is moved to ``hong``
    - a precaution, ``go_nguon_ket_dau_tick`` is where a source that ran out of attempts is ACTIVELY moved to
    ``hong``).

    ``attempts`` is raised IN THIS UPDATE, not after processing: a source that makes the worker DIE/HANG
    halfway never reaches any "after failure" code - counting in the catch branch would be useless for
    exactly the case that most needs counting (a poison pill that hangs the process, not a neatly catchable
    error).

    The worker MUST use this function for the claim, not an unconditional update to ``dang_xu_ly``: two
    rounds can overlap in real time (one still awaiting a big file when the next tick fires, reaching THIS
    source from an old snapshot) - an unconditional UPDATE would claim it AGAIN although another round
    already claimed/processed it, causing double processing and a final state that depends on which round
    wrote LAST."""
    row = (
        await session.execute(
            text(
                "UPDATE agent.kb_document SET status = 'dang_xu_ly', attempts = attempts + 1 "
                "WHERE clinic_id = :c AND id = :id AND status = 'cho_xu_ly' AND attempts < :tran "
                "RETURNING id"
            ),
            {"c": clinic_id, "id": id_, "tran": tran_lan_thu},
        )
    ).first()
    return row is not None


async def co_nguon_nao(session: AsyncSession, clinic_id: UUID) -> bool:
    """Does the knowledge base have AT LEAST one source yet - used by the ``kb_search`` tool's availability
    check when no specific agent is known (the account-scope Tools page). ``SELECT 1 ... LIMIT 1`` instead of
    pulling the table (full text of EVERY source) just to compute a boolean, while the check runs every time
    the tool catalogue is built - i.e. EVERY AGENT TURN, twice per turn."""
    row = (
        await session.execute(
            text("SELECT 1 FROM agent.kb_document WHERE clinic_id = :c LIMIT 1"), {"c": clinic_id}
        )
    ).first()
    return row is not None
