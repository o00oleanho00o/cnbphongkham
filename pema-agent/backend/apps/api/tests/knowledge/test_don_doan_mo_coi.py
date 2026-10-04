# ported from: src/knowledge/don-doan-mo-coi.test.ts
"""Forced deviation (SQLite -> Postgres): with the foreign key ``ON DELETE CASCADE`` an orphan chunk cannot be
made by an ordinary delete, so these tests create one the way a restore or a manual repair would: deleting the
document with ``session_replication_role = replica`` (constraint triggers off, superuser only)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from pema.knowledge.chunk_text import DoanMoi
from pema.knowledge.don_doan_mo_coi import don_doan_mo_coi
from pema.knowledge.kb_chunk_store import dem_doan, luu_doan
from pema.knowledge.kb_ingest_worker import KbIngestWorker
from pema.knowledge.kb_source_store import tao_nguon
from pema.knowledge.kb_test_support import KbHarness

pytestmark = pytest.mark.db


def _xoa_khong_cascade(kb: KbHarness, source_id: str) -> None:
    with kb.kb_database.admin_engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM agent.kb_document WHERE id = :id"), {"id": source_id})


async def test_don_doan_mo_coi_chunks_of_a_deleted_source_are_cleaned(kb: KbHarness) -> None:
    """đoạn của nguồn đã bị xóa được dọn, kể cả hàng FTS không có đường dọn nào khác"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="abc")
        await luu_doan(s, kb.clinic_id, n.id, [DoanMoi(0, "", "nội dung")])
    _xoa_khong_cascade(kb, n.id)
    assert kb.kb_database.scalar("SELECT count(*) FROM agent.kb_chunk") == 1, "tiền đề: có đoạn mồ côi"

    async with kb.session() as s:
        ket = await don_doan_mo_coi(s, kb.clinic_id)

    assert ket.so_doan == 1
    assert kb.kb_database.scalar("SELECT count(*) FROM agent.kb_chunk") == 0


async def test_don_doan_mo_coi_does_not_touch_chunks_of_a_source_that_still_exists(kb: KbHarness) -> None:
    """KHÔNG đụng đoạn của nguồn còn tồn tại"""
    async with kb.session() as s:
        con = await tao_nguon(s, kb.clinic_id, ten="còn", loai="text", noi_dung_goc="abc")
        await luu_doan(s, kb.clinic_id, con.id, [DoanMoi(0, "", "còn nguyên")])
    async with kb.session() as s:
        ket = await don_doan_mo_coi(s, kb.clinic_id)
        assert ket.so_doan == 0
        assert await dem_doan(s, kb.clinic_id, con.id) == 1


async def test_don_doan_mo_coi_nothing_orphan_returns_0_without_error(kb: KbHarness) -> None:
    """không có gì mồ côi thì trả về 0, không lỗi"""
    async with kb.session() as s:
        ket = await don_doan_mo_coi(s, kb.clinic_id)
    assert (ket.so_doan, ket.so_hang_fts) == (0, 0)


async def test_don_doan_mo_coi_is_wired_into_the_boot_of_bat_dau_worker(kb: KbHarness) -> None:
    """gọi batDauWorker() dọn luôn đoạn mồ côi có sẵn từ trước, không cần gọi donDoanMoCoi() tay"""
    # Different from the unit test above: it calls what the operator really runs at start-up
    # (``bat_dau_worker``), not ``don_doan_mo_coi`` directly - otherwise removing the sweep from the boot
    # would turn no test red.
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="mồ côi trước khi boot", loai="text", noi_dung_goc="abc")
        await luu_doan(s, kb.clinic_id, n.id, [DoanMoi(0, "", "sẽ mồ côi")])
    _xoa_khong_cascade(kb, n.id)

    await KbIngestWorker(kb.db).bat_dau_worker([kb.clinic_id])

    assert kb.kb_database.scalar("SELECT count(*) FROM agent.kb_chunk") == 0
