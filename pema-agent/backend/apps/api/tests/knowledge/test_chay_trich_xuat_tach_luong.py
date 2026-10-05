# ported from: src/knowledge/chay-trich-xuat-tach-luong.test.ts
"""Pure module (the worker and the extractors touch no environment or database) - imported directly.

Forced deviation: ``worker_threads`` -> a child process (see ``chay_trich_xuat_tach_luong``). The "small
buffer sharing a pool with other buffers" test of the original has no counterpart: the bytes are copied
through a pipe, there is no pool to detach.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from collections.abc import Callable

import pytest

from pema.knowledge import chay_trich_xuat_tach_luong as modul
from pema.knowledge.chay_trich_xuat_tach_luong import LoiTrichXuatBiNgatGiuaChung, trich_xuat_tach_luong
from pema.knowledge.chunk_text import ThamSoCat
from pema.knowledge.kb_slow_docx_test_fixture import bom_quay_cpu_docx
from pema.knowledge.ooxml_zip_test_helper import docx_chi_co_anh, docx_nhieu_chu

MAC_DINH = ThamSoCat(co_doan_toi_da=1600, chong_lan=10)

HAN_ROI_RAI = 60_000
"""A GENEROUS deadline for the cases that do NOT measure the deadline (successful extraction, content
error). A short deadline is only for the case that measures the deadline: a child process needs a moment to
start and a loaded machine can take seconds, which would drop a test that measures something else into the
"over time" branch."""


class _TheoDoiNhip:
    """Tells whether the MAIN loop stayed alive while the worker ran, independent of the OS scheduler.

    The check is that the loop responds at least once in the FIRST HALF of the interval the worker runs. If
    the extraction ran on the SAME thread (the regression to block), a synchronous loop would hold the event
    loop tight, so no beat could fire: every timer would pile up and run only AFTER it released. The budget
    is HALF the interval for ONE response of a 10 ms ticker - far wider than "count N beats", which would
    measure the speed of the machine, yet a blocked loop still misses it whatever the speed."""

    def __init__(self) -> None:
        self.nhip: list[float] = []
        self._tac_vu: asyncio.Task[None] | None = None

    def bat_dau(self) -> None:
        async def dem() -> None:
            while True:
                self.nhip.append(time.monotonic())
                await asyncio.sleep(0.01)

        self._tac_vu = asyncio.get_running_loop().create_task(dem())

    async def dung(self) -> None:
        if self._tac_vu is not None:
            self._tac_vu.cancel()
            await asyncio.gather(self._tac_vu, return_exceptions=True)

    def khang_dinh_khong_bi_khoa(self, bat_dau: float, ket_thuc: float) -> None:
        giua = bat_dau + (ket_thuc - bat_dau) / 2
        nua_dau = [t for t in self.nhip if bat_dau < t <= giua]
        assert len(nua_dau) >= 1, (
            f"luồng chính KHÔNG đáp ứng lần nào trong {round((giua - bat_dau) * 1000)}ms đầu của quãng "
            f"{round((ket_thuc - bat_dau) * 1000)}ms worker làm việc - bị khoá"
        )


async def test_trich_xuat_tach_luong_txt_succeeds_and_returns_the_right_text_and_chunks_through_the_worker() -> (
    None
):
    """trích xuất .txt thành công, trả đúng chữ và đoạn đã cắt qua worker"""
    buf = "# Bảo hành\n\n12 tháng kể từ ngày mua".encode()
    ket = await trich_xuat_tach_luong(buf=buf, dinh_dang="txt", tham_so_cat=MAC_DINH, han_ms=HAN_ROI_RAI)
    assert "12 tháng kể từ ngày mua" in ket.chu
    assert len(ket.doan) > 0, "phải cắt ra ít nhất 1 đoạn"
    assert ket.doan[0].tieu_de == "Bảo hành"


async def test_trich_xuat_tach_luong_ordinary_extraction_error_rejects_with_the_right_message_not_the_timeout_branch() -> (
    None
):
    """lỗi trích xuất THƯỜNG (docx chỉ có ảnh, không chữ) reject với đúng thông điệp, KHÔNG đi nhánh quá hạn"""
    # Measure by ERROR TYPE, not by the clock: the two branches raise TWO DIFFERENT error types - the
    # timeout branch gives ``LoiTrichXuatBiNgatGiuaChung``, the content branch an ordinary ``ValueError``.
    with pytest.raises(ValueError, match=r"(?i)không đọc được chữ nào") as excinfo:
        await trich_xuat_tach_luong(
            buf=docx_chi_co_anh(), dinh_dang="docx", tham_so_cat=MAC_DINH, han_ms=HAN_ROI_RAI
        )
    assert not isinstance(excinfo.value, LoiTrichXuatBiNgatGiuaChung), (
        "lỗi NỘI DUNG bị gán nhầm thành lỗi bị ngắt giữa chừng - kb-ingest-worker sẽ thử lại thay vì đánh hong"
    )


async def test_trich_xuat_tach_luong_worker_over_the_ram_ceiling_rejects_with_the_right_error_type_and_the_test_process_stays_alive() -> (
    None
):
    """worker vượt trần RAM thì REJECT đúng loại lỗi, và TIẾN TRÌNH TEST VẪN SỐNG"""
    # The SECOND breaker (next to ``han_ms``): a document that bloats memory dies before the time ceiling
    # arrives. This test does NOT claim the breaker ALWAYS gives a catchable error - see "TWO LIMITS" at
    # ``TRAN_RAM_WORKER_MB``; it only claims the path is wired right for this allocation shape.
    #
    # Lower the ceiling to 8 MB of growth instead of building a "RAM bomb": every ceiling of
    # ``ooxml_limits`` is set precisely so that no valid document can eat hundreds of MB, so there is no
    # valid bomb to build. The 6 MB text below is entirely VALID - it just exceeds the ceiling this test
    # lowers on purpose. Build the fixture BEFORE starting the beat watcher: building it is heavy
    # SYNCHRONOUS work on the main thread and would block the loop and fail the "not blocked" check for
    # nothing. The watched interval must cover exactly the time the WORKER runs.
    buf = docx_nhieu_chu(6)
    nhip = _TheoDoiNhip()
    nhip.bat_dau()
    bat_dau = time.monotonic()
    try:
        with pytest.raises(LoiTrichXuatBiNgatGiuaChung, match=r"(?i)dừng bất thường") as excinfo:
            await trich_xuat_tach_luong(
                buf=buf,
                dinh_dang="docx",
                tham_so_cat=MAC_DINH,
                han_ms=HAN_ROI_RAI,  # must fall into the RAM branch, not the timeout branch
                tran_ram_mb=8,
            )
        assert "out of memory" in str(excinfo.value).lower(), (
            f"phải giữ nguyên mã lỗi gốc để chẩn đoán được: {excinfo.value}"
        )
        # The expensive part of this case: the test process is still alive to run on to here (the worker's
        # out-of-memory does not take the parent down), and the main loop was not blocked meanwhile.
        nhip.khang_dinh_khong_bi_khoa(bat_dau, time.monotonic())
    finally:
        await nhip.dung()


async def test_trich_xuat_tach_luong_a_valid_document_under_the_ram_ceiling_still_extracts() -> None:
    """(thêm) tài liệu hợp lệ dưới trần RAM vẫn trích được - trần RAM không chặn oan"""
    ket = await trich_xuat_tach_luong(
        buf=docx_nhieu_chu(1), dinh_dang="docx", tham_so_cat=MAC_DINH, han_ms=HAN_ROI_RAI, tran_ram_mb=192
    )
    assert len(ket.doan) > 0


async def test_trich_xuat_tach_luong_over_time_kills_the_worker_and_raises_and_the_main_loop_does_not_hang(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trích xuất quá hạn thì worker bị terminate và ném lỗi, luồng chính KHÔNG treo"""
    # Build the fixture BEFORE starting the beat watcher - same reason as the RAM case: building the bomb is
    # synchronous work on the main thread.
    bom = bom_quay_cpu_docx()
    nhip = _TheoDoiNhip()
    nhip.bat_dau()
    bat_dau = time.monotonic()

    # Observe that the worker process is REALLY killed - independent of the beat count below. Calling
    # ``kill`` does not prove the process died, only that it was called: record the process started and
    # check ``poll()`` afterwards. The wrapper keeps the real behaviour (it delegates), it only ADDS two
    # observation points: ``kill`` was CALLED (counted) and the process is REALLY dead.
    tien_trinh_da_chay: list[subprocess.Popen[bytes]] = []
    so_lan_kill: list[int] = []
    khoi_dong_goc: Callable[[], subprocess.Popen[bytes]] = modul.khoi_dong_tien_trinh

    def khoi_dong_co_theo_doi() -> subprocess.Popen[bytes]:
        tien_trinh = khoi_dong_goc()
        kill_goc = tien_trinh.kill

        def kill_dem() -> None:
            so_lan_kill.append(1)
            kill_goc()

        monkeypatch.setattr(tien_trinh, "kill", kill_dem)
        tien_trinh_da_chay.append(tien_trinh)
        return tien_trinh

    monkeypatch.setattr(modul, "khoi_dong_tien_trinh", khoi_dong_co_theo_doi)

    try:
        with pytest.raises(LoiTrichXuatBiNgatGiuaChung, match=r"(?i)quá thời gian"):
            await trich_xuat_tach_luong(buf=bom, dinh_dang="docx", tham_so_cat=MAC_DINH, han_ms=300)

        assert len(so_lan_kill) == 1, "worker phải bị kill ĐÚNG 1 lần khi quá hạn"
        nhip.khang_dinh_khong_bi_khoa(bat_dau, time.monotonic())

        # The MOST IMPORTANT claim of this test: the worker REALLY died, not only that ``kill`` was called.
        # Ceiling 3000 ms (not 300): it only tells "kill was called" from "never exits" - the mutation that
        # drops the kill never exits, so widening ten times still tells them apart and removes flicker.
        assert len(tien_trinh_da_chay) == 1
        tien_trinh_da_chay[0].wait(timeout=3)
        assert tien_trinh_da_chay[0].poll() is not None, "worker không tự thoát trong 3000ms sau khi bị kill"
    finally:
        await nhip.dung()
