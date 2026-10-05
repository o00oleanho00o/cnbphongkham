# ported from: src/shared/daily-task-schedule.ts
"""``daily-task-schedule.ts`` has no test file in the original; these pin its three promises: run now, repeat, and
never let a failing task kill the process. ``interval_seconds`` is tiny so nothing waits a day (the waiting helper
is ``doi_cho_den_khi``, never ``sleep(N)`` then assert)."""

from __future__ import annotations

import asyncio
import contextlib

from pema.shared.daily_task_schedule import ONE_DAY_SECONDS, start_daily_task
from pema.shared.doi_cho_den_khi import doi_cho_den_khi


async def _stop(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_start_daily_task_runs_immediately_and_again_on_each_interval() -> None:
    """chạy ngay lúc gọi rồi lặp lại"""
    runs: list[int] = []

    async def task() -> None:
        runs.append(len(runs) + 1)

    handle = start_daily_task("test-repeat", task, interval_seconds=0.01)
    try:
        await doi_cho_den_khi(lambda: len(runs) >= 3)
    finally:
        await _stop(handle)
    assert runs[:3] == [1, 2, 3]


async def test_start_daily_task_a_failing_run_is_swallowed_and_the_next_run_still_happens() -> None:
    """lỗi bị nuốt và log - tác vụ dọn dẹp hỏng không được làm chết process bot"""
    calls: list[int] = []

    async def task() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("dọn dẹp lỗi")

    handle = start_daily_task("test-fail", task, interval_seconds=0.01)
    try:
        await doi_cho_den_khi(lambda: len(calls) >= 2)
        assert not handle.done(), "lỗi của một lượt không được kết thúc vòng lặp"
    finally:
        await _stop(handle)


async def test_start_daily_task_cancelling_the_handle_stops_the_loop() -> None:
    """(thêm) huỷ handle lúc shutdown thì vòng lặp dừng (tương đương unref)"""
    runs: list[int] = []

    async def task() -> None:
        runs.append(1)

    handle = start_daily_task("test-cancel", task)  # default interval: one day
    await doi_cho_den_khi(lambda: len(runs) >= 1)
    await _stop(handle)
    assert handle.cancelled()
    assert ONE_DAY_SECONDS == 86400
