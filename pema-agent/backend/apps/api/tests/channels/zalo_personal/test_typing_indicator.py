# ported from: src/zalo/typing-indicator.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import asyncio

from pema.channels.zalo_personal.typing_indicator import start_typing_indicator
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_so_luong
from pema_contracts.channel import ThreadKind


class Recorder:
    """Ghi lại mọi lần bắn typing; ``should_fail`` cho phép mô phỏng lỗi mạng."""

    def __init__(self, *, should_fail: bool = False) -> None:
        self.calls: list[tuple[str, ThreadKind]] = []
        self.should_fail = should_fail

    async def send(self, thread_id: str, thread_type: ThreadKind) -> object:
        self.calls.append((thread_id, thread_type))
        if self.should_fail:
            raise RuntimeError("mạng rớt")
        return {"status": 0}


async def _yield() -> None:
    # lets the first fire() task run; no sleep of N ms, just scheduler turns
    for _ in range(3):
        await asyncio.sleep(0)


async def test_typing_indicator_ban_ngay_lap_tuc_khong_doi_het_chu_ky_dau() -> None:
    """bắn ngay lập tức, không đợi hết chu kỳ đầu"""
    rec = Recorder()
    stop = start_typing_indicator(rec.send, "t-1", ThreadKind.USER, interval_ms=1000)
    await _yield()

    assert len(rec.calls) == 1, "phải bắn ngay khi bắt đầu"
    assert rec.calls[0] == ("t-1", ThreadKind.USER)
    stop()


async def test_typing_indicator_lap_lai_theo_chu_ky_vi_zalo_khong_co_api_tat_chi_bao() -> None:
    """lặp lại theo chu kỳ vì Zalo không có API tắt chỉ báo"""
    rec = Recorder()
    stop = start_typing_indicator(rec.send, "t-lap", ThreadKind.GROUP, interval_ms=25)

    # Chờ tới khi đủ 3 lần thì không còn biên nào để trượt, mà máy rảnh lại về sớm hơn một sleep cố định.
    await doi_cho_so_luong(lambda: len(rec.calls), 3, WaitOptions(mo_ta="số lần bắn chỉ báo"))
    stop()
    assert len(rec.calls) >= 3, f"phải lặp nhiều lần, thực tế {len(rec.calls)}"
    assert all(kind is ThreadKind.GROUP for _, kind in rec.calls)


async def test_typing_indicator_stop_dung_han_khong_ban_them_lan_nao() -> None:
    """stop dừng hẳn, không bắn thêm lần nào"""
    rec = Recorder()
    stop = start_typing_indicator(rec.send, "t-stop", ThreadKind.USER, interval_ms=20)

    # Chờ nó bắn được ít nhất 2 lần rồi mới dừng: khẳng định "sau stop không bắn thêm" chỉ có nghĩa khi TRƯỚC
    # stop nó thật sự đang lặp.
    await doi_cho_so_luong(lambda: len(rec.calls), 2, WaitOptions(mo_ta="số lần bắn trước khi dừng"))
    stop()
    await _yield()
    after_stop = len(rec.calls)

    await asyncio.sleep(0.08)
    assert len(rec.calls) == after_stop, "sau stop không được bắn thêm"


async def test_typing_indicator_goi_stop_nhieu_lan_khong_loi() -> None:
    """gọi stop nhiều lần không lỗi"""
    rec = Recorder()
    stop = start_typing_indicator(rec.send, "t-stop-2", ThreadKind.USER, interval_ms=20)
    await _yield()
    stop()
    stop()
    stop()
    await asyncio.sleep(0.05)
    assert len(rec.calls) == 1


async def test_typing_indicator_loi_khi_ban_bi_nuot_va_van_lap_tiep() -> None:
    """lỗi khi bắn bị nuốt và vẫn lặp tiếp - chỉ báo hỏng không được chết lượt trả lời"""
    rec = Recorder(should_fail=True)  # mọi lần bắn đều raise
    loop = asyncio.get_running_loop()
    unhandled: list[object] = []
    previous = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
    try:
        stop = start_typing_indicator(rec.send, "t-loi", ThreadKind.USER, interval_ms=20)
        await doi_cho_so_luong(
            lambda: len(rec.calls), 2, WaitOptions(mo_ta="số lần bắn (mỗi lần đều ném lỗi)")
        )
        stop()
        await _yield()
    finally:
        loop.set_exception_handler(previous)

    assert unhandled == [], "không được để task lỗi lọt ra ngoài"
    assert len(rec.calls) >= 2, "lỗi rồi vẫn phải thử lại lượt sau"


async def test_typing_indicator_chot_chan_max_duration_tu_tat_khi_caller_quen_goi_stop() -> None:
    """chốt chặn maxDuration tự tắt khi caller quên gọi stop"""
    rec = Recorder()
    start_typing_indicator(rec.send, "t-treo", ThreadKind.USER, interval_ms=20, max_duration_ms=45)

    await asyncio.sleep(0.07)
    at_guard = len(rec.calls)
    await asyncio.sleep(0.08)
    assert len(rec.calls) == at_guard, "quá maxDuration phải tự dừng"


async def test_typing_indicator_mac_dinh_lay_chu_ky_tu_typing_refresh_ms() -> None:
    """chu kỳ mặc định đọc từ cấu hình TYPING_REFRESH_MS (3000 ms): trong 50 ms chỉ có lần bắn đầu"""
    rec = Recorder()
    stop = start_typing_indicator(rec.send, "t-mac-dinh", ThreadKind.USER)
    await asyncio.sleep(0.05)
    stop()
    assert len(rec.calls) == 1
