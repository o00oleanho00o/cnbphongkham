# ported from: src/shared/doi-cho-den-khi.ts
"""Wait until a condition holds, instead of ``await sleep(N)`` followed by an assertion.

WHY: ``sleep(N)`` does not measure what the test cares about, it measures the WALL CLOCK. On an idle machine
N is enough; on a busy one the work is not finished, the counter is short and the test goes red although
the code is right. Measured in zalo-agent: the whole suite under 6 CPU-burning processes, on a clean HEAD,
went red 4 times out of 5; on an idle machine 2136/2136 green.

The danger is not the false red but that it TEACHES PEOPLE TO IGNORE RED: rerun, see green, and the reflex
"probably flaky" forms; one day it is red for a real bug and gets rerun past.

Not "widen the margin". Raising ``sleep(20)`` to ``sleep(200)`` only moves the red threshold and slows the
suite on EVERY machine. Changing the measurement gives three things: a busy machine stays green (wide
ceiling, spent only when really needed), wrong code stays red (raises at the ceiling with a description of
what was awaited), and an idle machine is FASTER than a fixed sleep (returns as soon as the condition holds).

LIMIT, read before use: only for POSITIVE assertions ("it must eventually happen"). For a NEGATIVE one
("exactly once, no second time") it proves nothing, since the condition holds on the first try. Anchor
those on a definite event (wait for the thing that WOULD produce the second run to finish) or inject a fake
clock.

Used by the tests of the channels, the scheduler, the video queue and the typing indicator.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class WaitOptions:
    """``TuyChonDoiCho``."""

    tran_ms: int = 5000
    """Ceiling. 5 s is wide ON PURPOSE: it is only spent fully when the code is really wrong; the green path
    leaves as soon as the condition holds, so a large ceiling does not slow the suite."""
    nhip_ms: int = 5
    """Gap between two tries; fine enough without spinning the CPU."""
    mo_ta: str = "điều kiện"
    """What is awaited. Goes straight into the error message when the ceiling is hit."""


async def doi_cho_den_khi(
    dieu_kien: Callable[[], bool | Awaitable[bool]],
    tuy_chon: WaitOptions | None = None,
) -> None:
    """Try ``dieu_kien()`` until it returns ``True``, or raise at ``tran_ms``.

    ``dieu_kien`` is called ONCE right away before the first sleep: work already done costs no beat.

    A condition that raises counts as NOT YET true and is retried: exactly while waiting, the thing to read
    often does not exist yet (the DB row is missing, the list is empty). The error of the LAST attempt is
    attached to the message so the real cause is not swallowed.
    """
    options = tuy_chon or WaitOptions()
    deadline = time.monotonic() + options.tran_ms / 1000
    last_error: BaseException | None = None
    while True:
        try:
            result = dieu_kien()
            if isinstance(result, Awaitable):
                result = await result
            if result:
                return
            last_error = None
        except Exception as err:
            last_error = err
        if time.monotonic() >= deadline:
            suffix = "" if last_error is None else f" - lần thử cuối ném: {last_error}"
            raise TimeoutError(f"Hết {options.tran_ms}ms mà chưa thấy: {options.mo_ta}{suffix}")
        await asyncio.sleep(options.nhip_ms / 1000)


async def doi_cho_so_luong(
    dem: Callable[[], int],
    toi_thieu: int,
    tuy_chon: WaitOptions | None = None,
) -> None:
    """The most common form: wait until a counter reaches a threshold.

    Separate because the error message can state the REAL number at the ceiling ("expected >= 3, stopped at
    2"), which a bare boolean function cannot, and that is exactly what you need reading a CI log.
    """
    options = tuy_chon or WaitOptions(mo_ta="số lượng")
    try:
        await doi_cho_den_khi(lambda: dem() >= toi_thieu, options)
    except TimeoutError:
        # ``dem()`` is read AGAIN here, not built when called: the number to print is the one at the
        # ceiling, not the one when the wait began.
        raise TimeoutError(
            f"Hết {options.tran_ms}ms mà {options.mo_ta} chỉ đạt {dem()}, mong >= {toi_thieu}"
        ) from None
