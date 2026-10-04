# ported from: src/video/hang-doi-tai-video.ts
"""A queue that limits how many jobs run AT THE SAME TIME.

WHY IT IS NEEDED: measured on a real Python process:

    yt-dlp metadata only : 72.8 MB peak RAM
    yt-dlp downloading 5MB: 75.6 MB peak RAM

RAM barely changes between the two cases, i.e. ~73 MB is Python + yt-dlp itself, and that cost is FIXED per
process, not by video size. So the bottleneck is not bandwidth as first thought but RAM: 4 in parallel is
~300 MB, 6 in parallel is ~450 MB: too much for a VPS that also runs other apps.

The user settled it: **2 run at once, the rest queue up**.

WHY NOT ``enqueueSend``: that one queues PER THREAD so one conversation's messages go out in order. This is a
completely different problem: limiting the TOTAL number of heavy processes on the whole machine, regardless
of thread. Two people in different threads still queue with each other.

Forced deviations: Node ``Promise`` chains become asyncio ``Task`` + ``Future``. The state is module-level
and process-local exactly as in the original (it is a per-process RAM guard). Running jobs are kept in a set
so the event loop does not garbage-collect a running task. The module state is bound to the event loop that
runs the jobs: ``reset_hang_doi_tai_video`` between tests.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

_ViecCho = tuple[Callable[[], Awaitable[Any]], "asyncio.Future[Any]"]

_dang_chay = 0
_dang_cho: deque[_ViecCho] = deque()
_tac_vu: set[asyncio.Task[None]] = set()

_tran_hien_tai = 2
"""Parallel ceiling, passed by the CALLER on every enqueue.

WHY NOT READ THE CONFIG DIRECTLY HERE: ``get_tuning`` pulls in the database, and that module opens it at
load time: the queue's test would open the real DB by mistake. (In this port the tuning provider is
in-memory, but the caller-passes-it rule is kept, since the rest of the reasoning still holds.)

WHY NOT A GLOBAL SETTER (``datTranSongSong`` at startup): forgetting to call it fails SILENTLY: the queue
runs with the default number, the user adjusts the dashboard and sees nothing change, and nothing says so.
The first version of this file forgot to wire it, exactly that. Passing it on every call lets the compiler
watch."""


async def _chay_viec(chay: Callable[[], Awaitable[Any]], ket: asyncio.Future[Any]) -> None:
    global _dang_chay
    try:
        # Awaited INSIDE the ``try``: ``_dang_chay`` was already incremented, so if ``chay()`` raises
        # SYNCHRONOUSLY the cleanup must still run, or the slot leaks FOREVER. Measured: 2 synchronous raises
        # and the queue jams for good, every later download hangs, dragging the agent turn and the thread
        # lock with it.
        #
        # Today callers pass an ``async`` function (which cannot raise synchronously) so it is not reachable
        # yet, but it is exactly one refactor ("drop the async for brevity") away.
        result = await chay()
    except BaseException as err:
        if not ket.cancelled():
            ket.set_exception(err)
    else:
        if not ket.cancelled():
            ket.set_result(result)
    finally:
        _dang_chay -= 1
        # Call again here rather than relying on the next call: the last job finishing without anyone
        # waking the queue would hang every waiting job forever.
        _chay_tiep()


def _chay_tiep() -> None:
    global _dang_chay
    if _dang_chay >= max(1, _tran_hien_tai):
        return
    if not _dang_cho:
        return
    chay, ket = _dang_cho.popleft()

    _dang_chay += 1
    task = asyncio.get_running_loop().create_task(_chay_viec(chay, ket))
    _tac_vu.add(task)
    task.add_done_callback(_tac_vu.discard)


async def xep_hang_tai_video[T](viec: Callable[[], Awaitable[T]], tran_song_song: int) -> T:
    """Queue one job, wait for its turn, then run it.

    The job's error is raised INTACT: the queue does not swallow errors, since the caller needs to know why
    it failed to tell the user.
    """
    global _tran_hien_tai
    # Updated on every enqueue: a change on the dashboard takes effect on the very next call, no bot restart.
    _tran_hien_tai = tran_song_song
    ket: asyncio.Future[T] = asyncio.get_running_loop().create_future()
    _dang_cho.append((viec, ket))
    _chay_tiep()
    return await ket


@dataclass(frozen=True)
class TrangThaiHangDoi:
    dang_chay: int
    dang_cho: int


def trang_thai_hang_doi() -> TrangThaiHangDoi:
    """Number running and waiting: so the tool can say "busy, you are number N"."""
    return TrangThaiHangDoi(dang_chay=_dang_chay, dang_cho=len(_dang_cho))


def reset_hang_doi_tai_video() -> None:
    """Tests only: wipe the state between cases."""
    global _dang_chay, _tran_hien_tai
    _dang_chay = 0
    _dang_cho.clear()
    _tran_hien_tai = 2
    _tac_vu.clear()
