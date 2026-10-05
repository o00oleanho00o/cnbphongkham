# ported from: src/middleware/rate-limiter.test.ts
from __future__ import annotations

import asyncio

import pytest

from pema.middleware import rate_limiter as limiter


async def test_gui_tuan_tu_trong_cung_thread_khong_chong_lan() -> None:
    """gửi tuần tự trong cùng thread, không chồng lấn"""
    events: list[str] = []

    def task(name: str):
        async def run() -> str:
            events.append(f"start:{name}")
            await asyncio.sleep(0.02)
            events.append(f"end:{name}")
            return name

        return run

    first = limiter.enqueue_send("t-1", task("A"))
    second = limiter.enqueue_send("t-1", task("B"))
    assert await asyncio.gather(first, second) == ["A", "B"]
    assert events == ["start:A", "end:A", "start:B", "end:B"]


async def test_task_loi_van_nem_ve_caller_nhung_khong_lam_chet_queue_cua_thread() -> None:
    """task lỗi vẫn ném về caller nhưng không làm chết queue của thread"""

    async def fails() -> str:
        raise RuntimeError("gửi thất bại")

    with pytest.raises(RuntimeError):
        await limiter.enqueue_send("t-loi", fails)

    async def after_failure() -> str:
        return "sau-loi"

    assert await limiter.enqueue_send("t-loi", after_failure) == "sau-loi"


async def test_thread_gui_xong_thi_bo_khoi_map_khong_ro_ri_theo_so_thread_tung_gap() -> None:
    """thread gửi xong thì bỏ khỏi Map - không rò rỉ theo số thread từng gặp"""

    def make(i: int):
        async def run() -> int:
            return i

        return run

    await asyncio.gather(*(limiter.enqueue_send(f"t-ro-ri-{i}", make(i)) for i in range(20)))
    assert limiter.pending_send_thread_count() == 0


async def test_dang_gui_tren_dung_ngay_sau_khi_xep_hang() -> None:
    """thread được đánh dấu bận ĐỒNG BỘ ngay khi xếp hàng (như `queues.set` của bản gốc)"""
    release = asyncio.Event()

    async def blocked() -> None:
        await release.wait()

    task = limiter.enqueue_send("t-dong-bo", blocked)
    assert limiter.dang_gui_tren("t-dong-bo") is True
    release.set()
    await task
    assert limiter.dang_gui_tren("t-dong-bo") is False
