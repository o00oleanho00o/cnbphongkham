# ported from: src/knowledge/don-doan-mo-coi.ts
"""Clean up ORPHAN chunks (``source_id`` no longer exists in ``agent.kb_document``) - patches exactly the race
window I4: the worker is awaiting extraction of a source when the DELETE route removes that source in
between; ``xoa_nguon`` ran BEFORE the worker could ``luu_doan`` so it had nothing to remove, while the worker
checks "the source still exists" before writing (see ``kb_ingest_worker``) so the window does not normally
produce a NEW orphan any more - this function is the safety net for the OLDER paths that had no such check,
and for cases not foreseen.

Forced deviation (SQLite -> Postgres): ``agent.kb_chunk`` has a real foreign key to ``agent.kb_document`` with
``ON DELETE CASCADE`` and holds the full-text index in a generated column, so the race cannot create an
orphan any more and there is no separate FTS row to clean (``so_hang_fts`` always equals ``so_doan``, like
the original where the FTS rows matched the chunks 1-1). It is kept because the safety net is cheap and
useful after a restore from a backup or a manual repair done with constraints off.

Called ONCE at boot (``kb_ingest_worker.bat_dau_worker``) (one clinic per installation), not periodically.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class KetQuaDon:
    so_doan: int
    so_hang_fts: int


async def don_doan_mo_coi(session: AsyncSession, clinic_id: UUID) -> KetQuaDon:
    deleted = (
        await session.execute(
            text(
                "DELETE FROM agent.kb_chunk c WHERE c.clinic_id = :c AND NOT EXISTS ("
                "SELECT 1 FROM agent.kb_document d WHERE d.clinic_id = c.clinic_id AND d.id = c.source_id) "
                "RETURNING c.id"
            ),
            {"c": clinic_id},
        )
    ).all()
    so_doan = len(deleted)
    return KetQuaDon(so_doan=so_doan, so_hang_fts=so_doan)
