# ported from: src/knowledge/kb-source-store.ts
"""CRUD of knowledge-base sources + their processing state. Schema: Alembic 0002 (``agent.kb_document``).

Forced deviations (SQLite -> Postgres, sync -> async):
* every function is ``async`` and takes the open ``AsyncSession`` of ``ClinicDatabase.session(clinic_id)``
  plus the ``clinic_id`` (every row carries it; row level security enforces it). A function never opens its
  own transaction, so the caller composes several steps into one unit of work;
* table ``kb_sources`` -> ``agent.kb_document``; columns ``ten, loai, dinh_dang, duong_dan, noi_dung_goc,
  trang_thai, loi, so_doan, so_byte, so_lan_thu`` -> ``name, kind, format, storage_key, raw_text, status,
  error, chunk_count, byte_size, attempts``; the Python field names keep the ORIGINAL (Vietnamese) names;
* the original had NO foreign keys (SQLite ran without ``PRAGMA foreign_keys``) so every delete had to clean
  FOUR places by hand in one transaction. In Postgres chunks and agent bindings are removed by
  ``ON DELETE CASCADE`` of the same transaction, which makes the "orphan chunk" state impossible to create;
  ``xoa_nguon`` keeps its contract (it still reports the number of chunks deleted);
* ``so_lan_thu`` (the claim counter) is ``attempts``; ``da_duyet`` is the new doctor sign-off flag
  (``approved_by_clinical_owner``), the only column the original does not have.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

type TrangThaiNguon = Literal["cho_xu_ly", "dang_xu_ly", "san_sang", "hong"]
type LoaiNguon = Literal["file", "text"]

COT_GON: Final = (
    "id, name, kind, format, storage_key, status, error, chunk_count, byte_size, attempts, "
    "approved_by_clinical_owner, created_at, updated_at"
)
"""Every column EXCEPT ``raw_text`` - see ``kb_source_queries``."""
COT_DAY_DU: Final = COT_GON + ", raw_text"


@dataclass(frozen=True, slots=True)
class KbSourceTomTat:
    """A source WITHOUT its raw text: what the dashboard, the worker's scan and the API responses need."""

    id: str
    ten: str
    loai: LoaiNguon
    dinh_dang: str
    duong_dan: str
    trang_thai: TrangThaiNguon
    loi: str
    so_doan: int
    so_byte: int
    so_lan_thu: int
    """Times already CLAIMED for processing (raised as the claim happens, see ``gianh_nguon_cho_xu_ly``) -
    the ceiling that stops a source that makes the worker hang/die over and over."""
    da_duyet: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KbSource(KbSourceTomTat):
    noi_dung_goc: str = ""


def map_row_gon(row: Any) -> KbSourceTomTat:
    return KbSourceTomTat(
        id=row["id"],
        ten=row["name"],
        loai=row["kind"],
        dinh_dang=row["format"],
        duong_dan=row["storage_key"],
        trang_thai=row["status"],
        loi=row["error"],
        so_doan=row["chunk_count"],
        so_byte=row["byte_size"],
        so_lan_thu=row["attempts"],
        da_duyet=row["approved_by_clinical_owner"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _truong_gon(s: KbSourceTomTat) -> dict[str, Any]:
    return {f.name: getattr(s, f.name) for f in fields(KbSourceTomTat)}


def map_row(row: Any) -> KbSource:
    return KbSource(**_truong_gon(map_row_gon(row)), noi_dung_goc=row["raw_text"])


def bo_noi_dung_goc(s: KbSource) -> KbSourceTomTat:
    """A full ``KbSource`` -> the SLIM version without ``noi_dung_goc``, for API responses. ``POST
    /sources/text`` and ``POST /sources/:id/reindex`` once dumped the whole text just typed/stored back to
    the client - the same family of bug as "GET /sources leaks the full text" fixed in an earlier review
    round, left behind in those two routes because they read through the full read path."""
    return KbSourceTomTat(**_truong_gon(s))


async def tao_nguon(
    session: AsyncSession,
    clinic_id: UUID,
    *,
    ten: str,
    loai: LoaiNguon,
    dinh_dang: str = "",
    duong_dan: str = "",
    noi_dung_goc: str = "",
    so_byte: int = 0,
) -> KbSource:
    id_ = secrets.token_hex(8)
    row = (
        (
            await session.execute(
                text(
                    "INSERT INTO agent.kb_document (clinic_id, id, name, kind, format, storage_key, "  # noqa: S608 - constant column list
                    "raw_text, byte_size) VALUES (:c, :id, :ten, :loai, :dinh_dang, :duong_dan, "
                    ":noi_dung_goc, :so_byte) RETURNING " + COT_DAY_DU
                ),
                {
                    "c": clinic_id,
                    "id": id_,
                    "ten": ten,
                    "loai": loai,
                    "dinh_dang": dinh_dang,
                    "duong_dan": duong_dan,
                    "noi_dung_goc": noi_dung_goc,
                    "so_byte": so_byte,
                },
            )
        )
        .mappings()
        .one()
    )
    return map_row(row)


async def lay_nguon(session: AsyncSession, clinic_id: UUID, id_: str) -> KbSource | None:
    row = (
        (
            await session.execute(
                text(f"SELECT {COT_DAY_DU} FROM agent.kb_document WHERE clinic_id = :c AND id = :id"),  # noqa: S608
                {"c": clinic_id, "id": id_},
            )
        )
        .mappings()
        .first()
    )
    return map_row(row) if row is not None else None


async def danh_sach_nguon(session: AsyncSession, clinic_id: UUID) -> list[KbSource]:
    rows = (
        (
            await session.execute(
                text(
                    f"SELECT {COT_DAY_DU} FROM agent.kb_document WHERE clinic_id = :c "  # noqa: S608
                    "ORDER BY created_at DESC, id"
                ),
                {"c": clinic_id},
            )
        )
        .mappings()
        .all()
    )
    return [map_row(r) for r in rows]


async def dat_trang_thai(
    session: AsyncSession,
    clinic_id: UUID,
    id_: str,
    trang_thai: TrangThaiNguon,
    *,
    loi: str | None = None,
    so_doan: int | None = None,
    so_lan_thu: int | None = None,
) -> None:
    """``loi`` / ``so_doan`` / ``so_lan_thu`` left out KEEP the old value (re-read and written back in the
    original; here ``COALESCE`` does it in the same statement, so no extra round trip and no lost update) -
    changing the state from 'dang_xu_ly' to 'san_sang' without a new ``so_doan`` has no reason to reset the
    chunk count to 0.

    ``so_lan_thu`` does NOT reset by itself with ``trang_thai`` - the caller must pass it EXPLICITLY when it
    wants to grant a fresh budget (the source was just processed, or the operator pressed "Xử lý lại" on
    the dashboard). Resetting it automatically on the target state would make ``go_nguon_ket_dau_tick``
    (which moves ``dang_xu_ly`` -> ``cho_xu_ly`` to RETRY) wipe the very counter it needs to read to decide
    whether to retry or give up."""
    await session.execute(
        text(
            "UPDATE agent.kb_document SET status = :trang_thai, "
            "error = COALESCE(CAST(:loi AS text), error), "
            "chunk_count = COALESCE(CAST(:so_doan AS integer), chunk_count), "
            "attempts = COALESCE(CAST(:so_lan_thu AS integer), attempts) "
            "WHERE clinic_id = :c AND id = :id"
        ),
        {
            "c": clinic_id,
            "id": id_,
            "trang_thai": trang_thai,
            "loi": loi,
            "so_doan": so_doan,
            "so_lan_thu": so_lan_thu,
        },
    )


async def xoa_nguon(session: AsyncSession, clinic_id: UUID, id_: str) -> int:
    """Delete a source and return the number of chunks deleted (``so_doan_da_xoa``).

    The most important invariant of the knowledge base: nothing of the source may stay behind. The original
    cleaned FOUR places by hand in one transaction; here ``agent.kb_chunk`` and ``agent.agent_kb_document``
    go with the document through ``ON DELETE CASCADE`` in the same statement, so a half-deleted source cannot
    exist. The count is read FIRST, in the same transaction, because the cascade removes the rows."""
    so_doan_da_xoa = (
        await session.execute(
            text("SELECT count(*) FROM agent.kb_chunk WHERE clinic_id = :c AND source_id = :id"),
            {"c": clinic_id, "id": id_},
        )
    ).scalar_one()
    await session.execute(
        text("DELETE FROM agent.kb_document WHERE clinic_id = :c AND id = :id"), {"c": clinic_id, "id": id_}
    )
    return int(so_doan_da_xoa)
