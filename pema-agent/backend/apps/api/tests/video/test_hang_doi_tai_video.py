# ported from: src/video/hang-doi-tai-video.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass

import pytest
import pytest_asyncio

from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema.video.hang_doi_tai_video import (
    TrangThaiHangDoi,
    reset_hang_doi_tai_video,
    trang_thai_hang_doi,
    xep_hang_tai_video,
)


@pytest_asyncio.fixture(autouse=True)
async def _reset() -> AsyncIterator[None]:
    yield
    reset_hang_doi_tai_video()


@dataclass
class _ViecTreo:
    p: asyncio.Future[None]

    def xong(self) -> None:
        self.p.set_result(None)

    def hong(self, e: BaseException) -> None:
        self.p.set_exception(e)


def _viec_treo() -> _ViecTreo:
    """A job that hangs until the test calls ``xong()``: holds a slot without needing a clock."""
    return _ViecTreo(p=asyncio.get_running_loop().create_future())


# ------------------------------------------------------------------ hàng đợi tải video


async def test_hang_doi_tai_video_tran_2_viec_thu_3_phai_cho_toi_khi_co_suat_trong() -> None:
    """trần 2: việc thứ 3 phải CHỜ tới khi có suất trống"""
    a = _viec_treo()
    b = _viec_treo()
    c = _viec_treo()
    c_da_chay = False

    def viec_c() -> Awaitable[None]:
        nonlocal c_da_chay
        c_da_chay = True
        return c.p

    t1 = asyncio.ensure_future(xep_hang_tai_video(lambda: a.p, 2))
    t2 = asyncio.ensure_future(xep_hang_tai_video(lambda: b.p, 2))
    t3 = asyncio.ensure_future(xep_hang_tai_video(viec_c, 2))

    await doi_cho_den_khi(lambda: trang_thai_hang_doi().dang_chay == 2, WaitOptions(mo_ta="2 việc chạy"))
    assert c_da_chay is False, "việc thứ 3 KHÔNG được chạy khi đã có 2 việc đang chạy"
    assert trang_thai_hang_doi().dang_cho == 1

    a.xong()
    await doi_cho_den_khi(lambda: c_da_chay, WaitOptions(mo_ta="việc thứ 3 chạy sau khi có suất trống"))

    b.xong()
    c.xong()
    await asyncio.gather(t1, t2, t3)


async def test_hang_doi_tai_video_viec_hong_van_nha_suat_khong_thi_hang_doi_tac_vinh_vien() -> None:
    """việc HỎNG vẫn nhả suất - không thì hàng đợi tắc vĩnh viễn"""
    a = _viec_treo()
    b_da_chay = False

    pa = asyncio.ensure_future(xep_hang_tai_video(lambda: a.p, 1))

    async def viec_b() -> None:
        nonlocal b_da_chay
        b_da_chay = True

    pb = asyncio.ensure_future(xep_hang_tai_video(viec_b, 1))

    await doi_cho_den_khi(lambda: trang_thai_hang_doi().dang_chay == 1, WaitOptions(mo_ta="việc đầu chạy"))
    assert b_da_chay is False

    a.hong(RuntimeError("hỏng"))
    with pytest.raises(RuntimeError, match="hỏng"):
        await pa
    await doi_cho_den_khi(lambda: b_da_chay, WaitOptions(mo_ta="việc sau vẫn chạy sau khi việc trước hỏng"))
    await pb


async def test_hang_doi_tai_video_viec_nem_dong_bo_van_nha_suat_khong_thi_hang_doi_ket_vinh_vien() -> None:
    """việc ném ĐỒNG BỘ vẫn nhả suất - không thì hàng đợi kẹt vĩnh viễn"""

    # This case differs from "a FAILED job" above: that is a rejected promise, this is a NON-async function
    # that raises straight away. The counter goes up before the job is called, so without wrapping the
    # cleanup is never reached and the slot leaks forever. Measured on the unpatched version: 2 synchronous
    # raises jam the queue for good.
    def nem() -> Awaitable[None]:
        raise RuntimeError("ném đồng bộ")

    with pytest.raises(RuntimeError, match="ném đồng bộ"):
        await xep_hang_tai_video(nem, 1)
    with pytest.raises(RuntimeError, match="ném đồng bộ"):
        await xep_hang_tai_video(nem, 1)

    assert trang_thai_hang_doi() == TrangThaiHangDoi(dang_chay=0, dang_cho=0), (
        "suất bị rò sau khi việc ném đồng bộ"
    )

    # The real lock: the queue is STILL USABLE afterwards.
    async def van_chay() -> str:
        return "van chay duoc"

    assert await xep_hang_tai_video(van_chay, 1) == "van chay duoc"


async def test_hang_doi_tai_video_loi_duoc_nem_nguyen_ven_ra_ngoai_hang_doi_khong_nuot() -> None:
    """lỗi được ném NGUYÊN VẸN ra ngoài, hàng đợi không nuốt"""
    # Swallowing the error means the tool does not know why it failed, and the user gets a generic sentence.
    rieng = RuntimeError("lý do rất riêng")

    async def viec() -> None:
        raise rieng

    with pytest.raises(RuntimeError) as thay:
        await xep_hang_tai_video(viec, 2)
    assert thay.value is rieng


async def test_hang_doi_tai_video_tra_ve_dung_gia_tri_cua_viec() -> None:
    """trả về ĐÚNG giá trị của việc"""

    async def viec() -> int:
        return 42

    assert await xep_hang_tai_video(viec, 2) == 42


async def test_hang_doi_tai_video_tran_lay_tu_loi_goi_moi_nhat_doi_tren_dashboard_la_an_ngay() -> None:
    """trần lấy từ lời gọi MỚI NHẤT - đổi trên dashboard là ăn ngay"""
    # The ceiling is passed on EVERY enqueue rather than set by a global setter called at startup. The first
    # version of this file used a setter and FORGOT to wire it: the queue ran with the default number, the
    # user adjusted the dashboard and saw nothing change, and nothing said so.
    a = _viec_treo()
    b = _viec_treo()
    b_da_chay = False

    def viec_b() -> Awaitable[None]:
        nonlocal b_da_chay
        b_da_chay = True
        return b.p

    t1 = asyncio.ensure_future(xep_hang_tai_video(lambda: a.p, 1))
    t2 = asyncio.ensure_future(xep_hang_tai_video(viec_b, 1))

    await doi_cho_den_khi(
        lambda: trang_thai_hang_doi().dang_chay == 1, WaitOptions(mo_ta="1 việc chạy với trần 1")
    )
    assert b_da_chay is False, "trần 1 thì việc thứ hai phải chờ"

    # Enqueue a new job with ceiling 2: simulates the user just raising the configuration
    async def viec_moi() -> None:
        return None

    t3 = asyncio.ensure_future(xep_hang_tai_video(viec_moi, 2))
    await doi_cho_den_khi(lambda: b_da_chay, WaitOptions(mo_ta="việc đang chờ chạy sau khi nâng trần"))

    a.xong()
    b.xong()
    await asyncio.gather(t1, t2, t3)


async def test_hang_doi_tai_video_tran_0_van_chay_duoc_1_cau_hinh_loi_khong_lam_treo_ca_tinh_nang() -> None:
    """trần 0 vẫn chạy được 1 - cấu hình lỗi không được làm treo cả tính năng"""

    async def viec() -> str:
        return "chay duoc"

    assert await xep_hang_tai_video(viec, 0) == "chay duoc"


async def test_hang_doi_tai_video_nhieu_viec_xep_hang_thi_chay_het_khong_bo_sot() -> None:
    """nhiều việc xếp hàng thì chạy HẾT, không bỏ sót"""
    xong: list[int] = []

    def tao(i: int) -> Awaitable[None]:
        async def viec() -> None:
            xong.append(i)

        return xep_hang_tai_video(viec, 2)

    await asyncio.gather(*(tao(i) for i in range(7)))
    assert len(xong) == 7
    assert sorted(xong) == [0, 1, 2, 3, 4, 5, 6]
    assert trang_thai_hang_doi() == TrangThaiHangDoi(dang_chay=0, dang_cho=0)
