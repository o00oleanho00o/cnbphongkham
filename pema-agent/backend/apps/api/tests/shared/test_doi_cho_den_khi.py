# ported from: src/shared/doi-cho-den-khi.test.ts
from __future__ import annotations

import asyncio
import time

import pytest

from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi, doi_cho_so_luong


async def test_already_true_condition_returns_at_once_without_a_beat() -> None:
    """điều kiện đã đúng sẵn thì trả về NGAY, không tốn một nhịp nào"""
    start = time.monotonic()
    await doi_cho_den_khi(lambda: True, WaitOptions(nhip_ms=200))
    # A 200 ms beat that cost under 150 ms means it tried BEFORE the first sleep.
    assert time.monotonic() - start < 0.15


async def test_waits_until_the_condition_holds() -> None:
    """chờ tới khi điều kiện đúng rồi mới về"""
    done = False

    async def finish() -> None:
        nonlocal done
        await asyncio.sleep(0.06)
        done = True

    task = asyncio.create_task(finish())
    await doi_cho_den_khi(lambda: done, WaitOptions(mo_ta="cờ xong"))
    assert done is True
    await task


async def test_returns_as_soon_as_true_not_after_the_whole_ceiling() -> None:
    """về NGAY khi điều kiện đúng chứ không ngủ trọn trần - đây là lý do nó nhanh hơn sleep cố định"""
    done = False

    async def finish() -> None:
        nonlocal done
        await asyncio.sleep(0.04)
        done = True

    task = asyncio.create_task(finish())
    start = time.monotonic()
    await doi_cho_den_khi(lambda: done, WaitOptions(tran_ms=5000))
    assert time.monotonic() - start < 0.5
    await task


async def test_ceiling_raises_with_the_description() -> None:
    """hết trần thì NÉM, kèm mô tả - code sai vẫn phải đỏ"""
    with pytest.raises(TimeoutError) as info:
        await doi_cho_den_khi(
            lambda: False, WaitOptions(tran_ms=60, nhip_ms=5, mo_ta="việc không bao giờ xong")
        )
    assert "Hết 60ms" in str(info.value)
    assert "việc không bao giờ xong" in str(info.value)


async def test_a_raising_condition_counts_as_not_yet_and_is_retried() -> None:
    """điều kiện NÉM thì coi như chưa đúng và thử lại, không vỡ ngay lần đầu"""
    tries = 0

    def condition() -> bool:
        nonlocal tries
        tries += 1
        if tries < 3:
            raise RuntimeError("dòng chưa tồn tại")
        return True

    await doi_cho_den_khi(condition, WaitOptions(nhip_ms=5))
    assert tries == 3, "must retry past two raises before succeeding"


async def test_a_condition_that_always_raises_reports_the_last_error() -> None:
    """điều kiện ném MÃI thì thông điệp hết trần mang theo lỗi của lần thử cuối"""

    def condition() -> bool:
        raise RuntimeError("bảng chưa dựng")

    with pytest.raises(TimeoutError) as info:
        await doi_cho_den_khi(condition, WaitOptions(tran_ms=40, nhip_ms=5))
    assert "lần thử cuối ném" in str(info.value)
    assert "bảng chưa dựng" in str(info.value)


async def test_accepts_an_async_condition() -> None:
    """nhận được cả điều kiện bất đồng bộ"""
    done = False

    async def finish() -> None:
        nonlocal done
        await asyncio.sleep(0.04)
        done = True

    async def condition() -> bool:
        await asyncio.sleep(0.001)
        return done

    task = asyncio.create_task(finish())
    await doi_cho_den_khi(condition)
    assert done is True
    await task


async def test_doi_cho_so_luong_waits_until_enough() -> None:
    """chờ tới khi đủ số lượng"""
    store: list[int] = []

    async def fill() -> None:
        for i in (1, 2, 3):
            await asyncio.sleep(0.02)
            store.append(i)

    task = asyncio.create_task(fill())
    await doi_cho_so_luong(lambda: len(store), 3, WaitOptions(mo_ta="số tin đã gửi"))
    assert len(store) == 3
    await task


async def test_doi_cho_so_luong_reports_the_real_number_at_the_ceiling() -> None:
    """hết trần thì báo SỐ THẬT lúc hết trần, không phải số lúc bắt đầu chờ"""
    store: list[int] = []

    async def fill() -> None:
        await asyncio.sleep(0.02)
        store.append(1)

    task = asyncio.create_task(fill())
    with pytest.raises(TimeoutError) as info:
        await doi_cho_so_luong(
            lambda: len(store), 5, WaitOptions(tran_ms=60, nhip_ms=5, mo_ta="số tin đã gửi")
        )
    # One element was added AFTER the wait began: a message built at call time would say "only 0".
    assert "số tin đã gửi chỉ đạt 1" in str(info.value)
    assert "mong >= 5" in str(info.value)
    await task
