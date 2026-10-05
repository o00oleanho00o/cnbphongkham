# ported from: src/shared/daily-task-schedule.ts
"""Run a cleanup task now and then every 24 hours.

Forced deviation (``setInterval`` + ``unref`` -> an ``asyncio`` task): the callback is ``async`` because the
cleanups it drives (media files, image descriptions, traces) talk to the database. The original called the
task synchronously inside ``startDailyTask`` and required a SYNC callback (an async one would have escaped
its ``try/catch`` as an unhandled rejection); awaiting the callback inside the loop keeps the same
guarantee: an error is swallowed and logged, a failing cleanup must not kill the bot process. The returned
task is the handle to cancel at shutdown (``unref`` had the same purpose: do not keep the process alive for
it).

``interval_seconds`` is a parameter only so a test does not wait a day; production uses the default.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pema.shared.logger import create_logger

_log = create_logger("daily-task")

ONE_DAY_SECONDS = 24 * 60 * 60.0


def start_daily_task(
    label: str,
    task: Callable[[], Awaitable[None]],
    *,
    interval_seconds: float = ONE_DAY_SECONDS,
) -> asyncio.Task[None]:
    """Chạy 1 tác vụ dọn dẹp ngay lúc gọi rồi lặp lại mỗi 24h. Lỗi bị nuốt và log - tác vụ dọn dẹp hỏng không
    được làm chết process bot."""

    async def run_once() -> None:
        try:
            await task()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _log.error("Tác vụ định kỳ lỗi - bỏ qua lượt này", label=label, err=err)

    async def loop() -> None:
        await run_once()
        while True:
            await asyncio.sleep(interval_seconds)
            await run_once()

    return asyncio.create_task(loop(), name=f"daily-task:{label}")
