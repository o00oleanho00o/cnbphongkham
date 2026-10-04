"""The process loop of the knowledge-base ingest worker (``pema.workers.kb_ingest_worker``): new tests, the
original's timer (``batDauWorker`` + ``setInterval``) was never tested on its own."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pema.knowledge.kb_ingest_worker import CaiDatIngest, KbIngestWorker
from pema.knowledge.kb_source_store import tao_nguon
from pema.knowledge.kb_test_support import KbHarness
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema.workers.kb_ingest_worker import chay_mai_mai, chay_mot_luot

pytestmark = pytest.mark.db

CAI_DAT = CaiDatIngest(tran_lan_thu=2, co_doan_toi_da=1200, chong_lan=10, han_ms=60_000, tran_ram_mb=192)


def trang_thai(kb: KbHarness, id_: str) -> object:
    return kb.kb_database.scalar("SELECT status FROM agent.kb_document WHERE id = :id", {"id": id_})


async def test_the_loop_processes_sources_then_stops_on_the_event(kb: KbHarness, tmp_path: Path) -> None:
    """vòng lặp xử lý nguồn của phòng khám (bản cài đặt) rồi dừng khi có tín hiệu"""
    async with kb.session() as s:
        a = await tao_nguon(s, kb.clinic_id, ten="a", loai="text", noi_dung_goc="# A\n\nthân bài của phòng A")
    async with kb.session() as s:
        b = await tao_nguon(s, kb.clinic_id, ten="b", loai="text", noi_dung_goc="# B\n\nthân bài thứ hai")
    worker = KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=CAI_DAT)
    stop = asyncio.Event()
    chay = asyncio.create_task(chay_mai_mai(worker, kb.db, stop, tick_s=0.05))
    await doi_cho_den_khi(
        lambda: trang_thai(kb, a.id) == "san_sang" and trang_thai(kb, b.id) == "san_sang",
        WaitOptions(mo_ta="cả hai nguồn xử lý xong", tran_ms=60_000),
    )
    # A source added AFTER boot is picked up by a later tick, not only by the first pass.
    async with kb.session() as s:
        c = await tao_nguon(s, kb.clinic_id, ten="c", loai="text", noi_dung_goc="# C\n\nthân bài thêm sau")
    await doi_cho_den_khi(
        lambda: trang_thai(kb, c.id) == "san_sang", WaitOptions(mo_ta="nguồn thêm sau", tran_ms=60_000)
    )
    stop.set()
    await asyncio.wait_for(chay, timeout=30)


async def test_one_pass_processes_a_waiting_source_and_a_failing_pass_does_not_raise(
    kb: KbHarness, tmp_path: Path
) -> None:
    """một lượt xử lý nguồn đang chờ; lượt lỗi chỉ ghi log, không ném ra ngoài"""
    worker = KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=CAI_DAT)
    async with kb.session() as s:
        a = await tao_nguon(s, kb.clinic_id, ten="a", loai="text", noi_dung_goc="# A\n\nthân bài")
    await chay_mot_luot(worker)
    assert trang_thai(kb, a.id) == "san_sang"

    async def hong() -> None:
        raise RuntimeError("synthetic failure")

    worker.chay_mot_vong_an_toan = hong  # type: ignore[method-assign]
    await chay_mot_luot(worker)
