# ported from: src/zalo-bot/zalo-bot-listener.ts
"""Long polling loop for ONE bot account.

The three behaviours below all come from MEASUREMENTS on the real API, not from caution:

1. An EMPTY poll is not an error. When the wait expires with no message Zalo answers ``error_code: 408`` and
  ``client.get_updates`` already turns that into ``None``. This loop polls again at once, WITHOUT retreating:
  silence is the permanent state of a bot.

2. Hammering polls gets an nginx **429** with an HTML body. So every error must retreat; it must never poll
  again straight away.

3. ``get_updates`` returns ONE update per call. With a message, poll again AT ONCE (no pause) so the loop does
  not fall behind when people write several lines in a row.

Forced deviations: the loop is an ``asyncio.Task``; ``dung()`` only sets the flag (as the original: a call in
flight is not aborted) and ``task`` is exposed so a shutdown can await or cancel it; ``on_update`` may be sync
or async and is awaited when it returns an awaitable. ``timeout_giay`` is a FUNCTION: reading it once and
freezing it would make an edit on the Settings page ineffective until the account restarts.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from pema.channels.zalo_bot.zalo_bot_api_types import ZaloBotUpdate
from pema.shared.logger import create_logger

_log = create_logger("zalo-bot-listener")


class _PollingClient(Protocol):
    async def get_updates(self, timeout_giay: int = 30) -> ZaloBotUpdate | None: ...


OnUpdate = Callable[[str, ZaloBotUpdate], "Awaitable[None] | None"]
"""May be sync or async; the loop AWAITS an awaitable. A sync-only signature would let an async function be
passed and its promise abandoned: the ``try/except`` around the call sees nothing, the error becomes an
unhandled rejection, and the loop spins because it waits for nobody."""


@dataclass
class PollHandle:
    task: asyncio.Task[None]
    stopped: bool = False
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    def dung(self) -> None:
        self.stopped = True
        self._stop_event.set()

    async def ngu_that(self, ms: float) -> None:
        """The default backoff sleep: it ends early on ``dung()``, so a stopped account does not leave a task
        asleep for up to a minute. (A poll call in flight is still not aborted, as in the original.)"""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), ms / 1000)


def bat_dau_vong_poll(
    *,
    account_id: str,
    client: _PollingClient,
    on_update: OnUpdate,
    timeout_giay: Callable[[], int] | None = None,
    lui_ban_dau_ms: float = 2_000,
    lui_toi_da_ms: float = 60_000,
    ngu_ms: Callable[[float], Awaitable[None]] | None = None,
) -> PollHandle:
    """Start the loop. ``lui_ban_dau_ms``: retreat after the FIRST error, doubling per consecutive error up to
    ``lui_toi_da_ms``. ``ngu_ms`` is injected so tests do not wait for real."""
    lay_timeout_giay = timeout_giay or (lambda: 30)
    handle_box: list[PollHandle] = []

    async def vong() -> None:
        handle = handle_box[0]
        ngu = ngu_ms or handle.ngu_that
        lui_hien_tai = lui_ban_dau_ms
        while not handle.stopped:
            try:
                u = await client.get_updates(lay_timeout_giay())
                # A successful poll (even an empty one) RESETS the retreat. Without it a passing network blip
                # would leave the bot retreating 60 seconds forever after.
                lui_hien_tai = lui_ban_dau_ms
                # ``dung()`` was called while this call was still in flight: DROP the message, do not process
                # it. The ``except`` branch below has this guard; the SUCCESS branch did not, and that window
                # is as wide as ``timeout_giay`` (30 seconds by default) from when the operator switches the
                # account off.
                #
                # It must LOG: ``get_updates`` has no ``offset`` so Zalo already took this message off its
                # queue; dropping it silently is gone for good and nobody knows. It happens on every account
                # switch-off and every shutdown.
                if handle.stopped:
                    if u is not None and u.message is not None:
                        _log.warning(
                            "Đã dừng vòng poll giữa lúc một tin đang về - tin này MẤT "
                            "(getUpdates không có offset để lấy lại)",
                            account_id=account_id,
                            message_id=u.message.message_id,
                        )
                    break
                if u is None:
                    continue

                # ``on_update`` is supplied by the caller and may raise (DB locked, disk full...). Letting it
                # reach the ``except`` below would count it as a NETWORK error: the bot would retreat 60
                # seconds for a completely different cause. Swallow it here and log, as the personal channel
                # router does.
                try:
                    result = on_update(account_id, u)
                    if inspect.isawaitable(result):
                        await result
                except Exception as err:
                    _log.error(
                        "Xử lý tin đến thất bại - vòng poll vẫn chạy tiếp", err=err, account_id=account_id
                    )
            except asyncio.CancelledError:
                raise
            except Exception as err:
                if handle.stopped:
                    break
                _log.warning(
                    "Poll Zalo Bot thất bại - lùi rồi thử lại",
                    err=err,
                    account_id=account_id,
                    retreat_ms=lui_hien_tai,
                )
                await ngu(lui_hien_tai)
                lui_hien_tai = min(lui_hien_tai * 2, lui_toi_da_ms)
        _log.info("Đã dừng vòng poll Zalo Bot", account_id=account_id)

    task = asyncio.get_running_loop().create_task(vong())
    handle = PollHandle(task=task)
    handle_box.append(handle)
    return handle
