# ported from: src/zalo/typing-indicator.ts
"""Giữ chỉ báo "đang nhập" trong suốt lượt xử lý.

Zalo KHÔNG có API tắt chỉ báo (đã rà hết zca-js/src/apis) - nó tự hết sau vài giây, nên phải bắn lặp lại. Trả
về hàm stop, caller BẮT BUỘC gọi trong finally. Lỗi khi bắn bị nuốt: chỉ báo hỏng không được làm chết lượt trả
lời.

Forced deviation (``setInterval``/``setTimeout`` -> asyncio): one background task loops ``send`` every
``interval_ms``; the first send happens immediately; a second task is the ``max_duration_ms`` guard.
``stop()``
is synchronous and idempotent (cancels both tasks). Needs a running event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.logger import create_logger
from pema_contracts.channel import ThreadKind

log = create_logger("typing-indicator")

# Hàm bắn 1 event "đang nhập" - tách ra để test không cần bridge thật
type TypingSender = Callable[[str, ThreadKind], Awaitable[object]]

# Chốt chặn khi caller quên gọi stop. Phải phủ được lượt agent DÀI NHẤT hợp lệ, mà giờ đó là lượt vẽ ảnh:
# đo thật
# một prompt phức tạp mất 135 giây, còn trần là 10 phút. Để 2 phút như trước thì chỉ báo tắt giữa chừng và bot
# trông như đã chết trong khi vẫn đang vẽ.
DEFAULT_MAX_DURATION_MS = 10 * 60_000


def start_typing_indicator(
    send: TypingSender,
    thread_id: str,
    thread_type: ThreadKind,
    interval_ms: int | None = None,
    max_duration_ms: int = DEFAULT_MAX_DURATION_MS,
) -> Callable[[], None]:
    interval = interval_ms if interval_ms is not None else get_tuning_int("TYPING_REFRESH_MS")
    stopped = False
    tasks: set[asyncio.Task[None]] = set()
    loop = asyncio.get_running_loop()

    async def fire() -> None:
        try:
            await send(thread_id, thread_type)
        except Exception as err:
            log.debug("Bắn typing thất bại - bỏ qua", thread_id=thread_id, err=err)

    def tick() -> None:
        if stopped:
            return
        task = loop.create_task(fire())
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    async def run() -> None:
        # bắn ngay, không đợi hết chu kỳ đầu
        tick()
        while True:
            await asyncio.sleep(interval / 1000)
            tick()

    async def guard() -> None:
        await asyncio.sleep(max_duration_ms / 1000)
        log.warning("Typing chạy quá lâu - tự tắt", thread_id=thread_id)
        stop()

    runner = loop.create_task(run())
    guard_task = loop.create_task(guard())

    def stop() -> None:
        nonlocal stopped
        if stopped:
            return
        stopped = True
        runner.cancel()
        # The guard may be the caller of stop(): cancelling the current task from inside is harmless (it
        # ends).
        guard_task.cancel()

    return stop
