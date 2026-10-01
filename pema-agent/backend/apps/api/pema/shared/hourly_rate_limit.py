# ported from: src/shared/hourly-rate-limit.ts
"""Sliding 1-hour quota counter, counted per key (usually ``account_id:thread_id``).

The bot reads messages from strangers, so every expensive tool needs a ceiling: building a file costs CPU,
drawing an image costs real money. It is shared because the hard part is not counting but CLEANING UP:
keeping an entry for every thread that ever wrote makes memory grow without bound on a long run (the Map
leak regression of V2.4). Copying this logic to a second place copies the trap too.

No forced deviation: the original was a closure over a ``Map``; this is a small class with the same method
names in snake_case (``check``, ``hoan_suat``, ``reset``, ``so_key_dang_giu``). It is synchronous and keeps
its state in the process (a per-process limit, as in the original). ``now`` is epoch MILLISECONDS like
``Date.now()`` so the original test numbers carry over unchanged.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

WINDOW_MS = 60 * 60 * 1000
"""Quota window: an anti-spam policy, there is no 'right number'."""


@dataclass(frozen=True)
class RateCheck:
    """``RateCheck``: ``ok`` is True, or False with the user-facing ``reason``."""

    ok: bool
    reason: str = ""


@dataclass(frozen=True)
class RateReasonInfo:
    used: int
    limit: int
    wait_minutes: int


def _now_ms() -> float:
    return time.time() * 1000


class HourlyRateLimit:
    """``createHourlyRateLimit``. ``limit`` is a FUNCTION, not a number: the ceiling is read when CALLED, so
    changing the tuning applies at once."""

    def __init__(self, *, limit: Callable[[], int], build_reason: Callable[[RateReasonInfo], str]) -> None:
        self._limit = limit
        self._build_reason = build_reason
        self._recent_by_key: dict[str, list[float]] = {}
        """key -> timestamps of the uses still inside the window."""

    def _prune_stale(self, cutoff: float) -> None:
        for key, times in list(self._recent_by_key.items()):
            alive = [at for at in times if at > cutoff]
            if not alive:
                del self._recent_by_key[key]
            elif len(alive) != len(times):
                self._recent_by_key[key] = alive

    def check(self, key: str, now: float | None = None) -> RateCheck:
        """If a slot is left, RECORD this use and return ok."""
        now_ms = _now_ms() if now is None else now
        cutoff = now_ms - WINDOW_MS
        max_uses = self._limit()
        recent = [at for at in self._recent_by_key.get(key, []) if at > cutoff]

        if len(recent) >= max_uses:
            # Clean the other cold keys on the way, so the map does not grow
            self._prune_stale(cutoff)
            self._recent_by_key[key] = recent
            wait_minutes = max(1, -(-int(recent[0] + WINDOW_MS - now_ms) // 60_000))
            reason = self._build_reason(
                RateReasonInfo(used=len(recent), limit=max_uses, wait_minutes=wait_minutes)
            )
            return RateCheck(ok=False, reason=reason)

        recent.append(now_ms)
        self._recent_by_key[key] = recent
        self._prune_stale(cutoff)
        return RateCheck(ok=True)

    def hoan_suat(self, key: str, now: float | None = None) -> None:
        """Give back ONE slot just recorded for ``key``.

        Use it when the work FAILED: ``check`` records at call time, so without a refund a failed attempt
        also eats a slot. Real case seen on the video download tool: the source is down, the user tries 15
        links that all fail, the quota is gone, and attempt 16 says "15 videos downloaded in the last hour",
        which is untrue because nothing was sent, and they would wait an hour for 15 failures.

        The ceiling exists to stop mass SENDING (the risk of the account being locked), and a message that
        was not sent creates no such risk: counting it counts the wrong thing.

        With no slot to refund it is silently ignored: a superfluous call must never make the count negative.
        """
        now_ms = _now_ms() if now is None else now
        cutoff = now_ms - WINDOW_MS
        recent = [at for at in self._recent_by_key.get(key, []) if at > cutoff]
        # Drop the NEWEST stamp. The stamps are only timestamps and the only thing read is the COUNT, so
        # dropping any is equivalent; the newest lets two parallel runs of one thread refund their own part.
        if recent:
            recent.pop()
        if not recent:
            self._recent_by_key.pop(key, None)
        else:
            self._recent_by_key[key] = recent

    def reset(self) -> None:
        """Tests only: clear the whole counting state."""
        self._recent_by_key.clear()

    def so_key_dang_giu(self) -> int:
        """Number of keys held in memory. TESTS ONLY.

        It exists because otherwise the CLEAN-UP of this module is not observable from outside, and what is
        not observable cannot be tested: dropping the ``cutoff`` filter in ``hoan_suat`` kept the whole suite
        green. A resident bot meets thousands of threads, so growing the map is a real regression.
        """
        return len(self._recent_by_key)


def create_hourly_rate_limit(
    *, limit: Callable[[], int], build_reason: Callable[[RateReasonInfo], str]
) -> HourlyRateLimit:
    return HourlyRateLimit(limit=limit, build_reason=build_reason)
