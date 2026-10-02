"""Per-user rate limit for cheap read routes that every signed-in member calls (package ST-S). New module.

It follows the shape of the login limiter in ``dashboard_auth`` (fixed window per key, buckets pruned once
the map is large, in-process, reset on restart) but with a budget meant for a screen that loads a list
when a sheet opens, not for a password: ``STAFF_LIST_MAX_PER_MINUTE`` per user. A limit that is hit answers
429 with the repo's ``rate_limited`` code; the picker then falls back to "Tôi" and "Giữ nguyên".

The clock is ``time.monotonic`` (not the action clock that tests freeze), so a frozen demo day never keeps
a window open for ever. Each API process counts on its own; the budget is a guard against a runaway
client, not a quota.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

STAFF_LIST_MAX_PER_MINUTE = 60
WINDOW_MS = 60_000
PRUNE_THRESHOLD = 500
"""Only sweep past this many buckets: sweeping on every call is O(n) for nothing."""


@dataclass
class FixedWindowLimiter:
    max_hits: int
    window_ms: int = WINDOW_MS
    prune_threshold: int = PRUNE_THRESHOLD

    def __post_init__(self) -> None:
        self._buckets: dict[str, tuple[int, float]] = {}

    def allow(self, key: str, now_ms: float | None = None) -> bool:
        """``True`` = within budget; ``False`` = more than ``max_hits`` calls in this window for ``key``."""
        at = time.monotonic() * 1000 if now_ms is None else now_ms
        if len(self._buckets) > self.prune_threshold:
            self._prune(at)
        entry = self._buckets.get(key)
        if entry is None or at >= entry[1]:
            self._buckets[key] = (1, at + self.window_ms)
            return True
        count = entry[0] + 1
        self._buckets[key] = (count, entry[1])
        return count <= self.max_hits

    def _prune(self, at: float) -> None:
        for key in [k for k, (_, reset_at) in self._buckets.items() if at >= reset_at]:
            del self._buckets[key]

    def bucket_count(self) -> int:
        return len(self._buckets)

    def reset(self) -> None:
        self._buckets.clear()


staff_list_limiter = FixedWindowLimiter(max_hits=STAFF_LIST_MAX_PER_MINUTE)
"""Shared by the read routes of the staff pickers; keyed by the signed-in user id."""
