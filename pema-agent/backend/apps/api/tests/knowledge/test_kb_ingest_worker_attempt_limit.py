# ported from: src/knowledge/kb-ingest-worker-attempt-limit.test.ts
"""The case "a source that makes the worker stick over and over" goes through its own tuning
(``KB_MAX_INGEST_ATTEMPTS``) and simulates "stuck in ``dang_xu_ly``" with the SAME technique as the neighbour
test: claim with the real UPDATE, then call ``go_nguon_ket_dau_tick()`` - it does NOT wait for an extraction to
really run out of time (the real branch has its own test, ``test_kb_ingest_worker_real_timeout_branch``).

Why not build the test with a file that really overruns through ``xu_ly_mot_vong()``: measured in the
original - content inside the valid limits of ``ooxml_limits`` is processed far faster than the floor of
``KB_EXTRACT_TIMEOUT_MS`` (5000 ms) and ``get_tuning`` rejects any value below the floor. That is itself
proof the ceilings work, not a hole of the test.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from pathlib import Path

import pytest

from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.knowledge.kb_ingest_worker import CaiDatIngest, KbIngestWorker
from pema.knowledge.kb_source_queries import gianh_nguon_cho_xu_ly
from pema.knowledge.kb_source_store import KbSource, lay_nguon, tao_nguon
from pema.knowledge.kb_test_support import KbHarness

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _tuning_sach() -> Generator[None]:
    reset_tuning_provider()
    yield
    reset_tuning_provider()


async def lay(kb: KbHarness, id_: str) -> KbSource:
    async with kb.session() as s:
        n = await lay_nguon(s, kb.clinic_id, id_)
    assert n is not None
    return n


async def gianh(kb: KbHarness, id_: str) -> bool:
    async with kb.session() as s:
        return await gianh_nguon_cho_xu_ly(s, kb.clinic_id, id_, CaiDatIngest.tu_tuning().tran_lan_thu)


async def test_nguon_ket_lap_lai_marked_hong_after_exactly_the_max_attempts_not_retried_for_ever(
    kb: KbHarness, tmp_path: Path
) -> None:
    """bị đánh hong sau đúng KB_MAX_INGEST_ATTEMPTS lần, không thử vô hạn qua các lần khởi động lại"""
    install_tuning_provider(StaticTuningProvider({"KB_MAX_INGEST_ATTEMPTS": 2}))
    worker = KbIngestWorker(kb.db, data_dir=tmp_path)
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="kẹt lặp lại", loai="text", noi_dung_goc="abc")

    # Attempt 1: claim (attempts 0 -> 1) - the REAL claim UPDATE, not a hand simulation. The source stands in
    # dang_xu_ly exactly like after ``LoiTrichXuatBiNgatGiuaChung`` (the catch calls nothing else).
    assert await gianh(kb, n.id) is True
    assert (await lay(kb, n.id)).trang_thai == "dang_xu_ly"

    # "Restart": attempts(1) < ceiling(2) -> back to cho_xu_ly to retry
    await worker.go_nguon_ket_dau_tick(kb.clinic_id)
    assert (await lay(kb, n.id)).trang_thai == "cho_xu_ly"

    # Attempt 2 (the LAST allowed): claim again (1 -> 2)
    assert await gianh(kb, n.id) is True
    assert (await lay(kb, n.id)).trang_thai == "dang_xu_ly"

    # "Restart" 2: attempts(2) >= ceiling(2) -> give up, mark hong
    await worker.go_nguon_ket_dau_tick(kb.clinic_id)
    sau = await lay(kb, n.id)
    assert sau.trang_thai == "hong"
    assert sau.so_lan_thu == 2
    assert re.search(r"(?i)đã thử 2 lần", sau.loi)

    # Attempt 3: no longer cho_xu_ly - the claim fails, the count does not grow, no endless retry.
    assert await gianh(kb, n.id) is False, "lần 3 KHÔNG được giành nữa"
    assert (await lay(kb, n.id)).so_lan_thu == 2, "đếm không được tăng thêm"


async def test_nguon_ket_lap_lai_a_different_ceiling_needs_that_many_attempts_not_a_hard_coded_2(
    kb: KbHarness, tmp_path: Path
) -> None:
    """trần khác nhau (KB_MAX_INGEST_ATTEMPTS=4) thì phải đủ 4 lần mới bỏ hẳn, không chốt cứng số 2"""
    # The invariant "exactly the configured ceiling", not "exactly 2" - if the code hard-coded 2 somewhere
    # instead of reading the tuning, THIS test flips.
    install_tuning_provider(StaticTuningProvider({"KB_MAX_INGEST_ATTEMPTS": 4}))
    worker = KbIngestWorker(kb.db, data_dir=tmp_path)
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="trần 4", loai="text", noi_dung_goc="abc")

    for lan in range(1, 4):
        assert await gianh(kb, n.id) is True, f"lần {lan} phải giành được"
        await worker.go_nguon_ket_dau_tick(kb.clinic_id)
        assert (await lay(kb, n.id)).trang_thai == "cho_xu_ly", f"sau lần {lan}/4 phải còn cho_xu_ly"

    assert await gianh(kb, n.id) is True, "lần 4 phải giành được"
    await worker.go_nguon_ket_dau_tick(kb.clinic_id)
    sau = await lay(kb, n.id)
    assert sau.trang_thai == "hong"
    assert sau.so_lan_thu == 4


async def test_go_nguon_ket_dau_tick_runs_every_tick_through_chay_mot_vong_an_toan_not_only_at_boot(
    kb: KbHarness, tmp_path: Path
) -> None:
    """nguồn kẹt dang_xu_ly XUẤT HIỆN SAU tick đầu vẫn được gỡ ở tick kế tiếp, không cần restart"""
    # BEFORE the fix ``go_nguon_ket_dau_tick`` was called only at boot, and a source stuck AFTER boot had no
    # way to release itself. Two ticks in a row prove the SECOND one - not only the first - releases too.
    worker = KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=CaiDatIngest.tu_tuning())
    await worker.chay_mot_vong_an_toan(kb.clinic_id)  # tick 1: nothing stuck

    # The stick happens BETWEEN two ticks - the real case: a worker killed by its deadline, the catch leaves
    # dang_xu_ly and waits for the next tick to judge.
    async with kb.session() as s:
        n = await tao_nguon(
            s, kb.clinic_id, ten="kẹt giữa hai tick", loai="text", noi_dung_goc="# Giờ mở cửa\n\n8h - 21h"
        )
    assert await gianh(kb, n.id) is True
    assert (await lay(kb, n.id)).trang_thai == "dang_xu_ly", (
        "tiền đề: nguồn phải đang kẹt dang_xu_ly trước tick 2"
    )

    await worker.chay_mot_vong_an_toan(kb.clinic_id)  # tick 2 (periodic, not boot)

    sau = await lay(kb, n.id)
    assert sau.trang_thai != "dang_xu_ly", "goNguonKetDauTick() phải chạy lại ở MỖI tick"
    # Valid and fast content: the same tick 2 runs it to san_sang, not just "out of dang_xu_ly".
    assert sau.trang_thai == "san_sang"
    assert sau.so_doan > 0


async def test_chay_mot_vong_an_toan_a_second_process_holding_the_clinic_lock_makes_this_pass_skip(
    kb: KbHarness, tmp_path: Path
) -> None:
    """(thêm) khóa advisory theo phòng khám: tiến trình khác đang chạy vòng thì vòng này bỏ qua, không đụng nguồn"""
    from sqlalchemy import text

    from pema.knowledge.kb_ingest_worker import khoa_advisory

    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="# A\n\nthân bài")
        await s.execute(text("SELECT 1"))
    with kb.kb_database.admin_engine.connect() as giu:
        giu.execute(text("SELECT pg_advisory_lock(:k)"), {"k": khoa_advisory(kb.clinic_id)})
        try:
            await KbIngestWorker(
                kb.db, data_dir=tmp_path, cai_dat=CaiDatIngest.tu_tuning()
            ).chay_mot_vong_an_toan(kb.clinic_id)
            assert (await lay(kb, n.id)).trang_thai == "cho_xu_ly", "vòng bị khóa thì không được đụng nguồn"
        finally:
            giu.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": khoa_advisory(kb.clinic_id)})
    await KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=CaiDatIngest.tu_tuning()).chay_mot_vong_an_toan(
        kb.clinic_id
    )
    assert (await lay(kb, n.id)).trang_thai == "san_sang"
