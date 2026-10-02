"""Small numeric helpers of the care eval. New module (not a port)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


def percentile(values: Sequence[float], q: float) -> float:
    """The ``q`` percentile (0..100) by linear interpolation between the closest ranks; 0.0 for no data."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * q / 100.0
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


@dataclass(frozen=True)
class Latency:
    """Milliseconds over ``n`` timed runs."""

    n: int
    p50: float
    p95: float
    max: float

    @classmethod
    def from_ns(cls, samples_ns: Sequence[int]) -> Latency:
        ms = [value / 1_000_000 for value in samples_ns]
        return cls(len(ms), percentile(ms, 50), percentile(ms, 95), max(ms) if ms else 0.0)


def ratio(numerator: int, denominator: int) -> float | None:
    """``None`` when there is nothing to divide by: a rate over zero cases is not 100 % and not 0 %."""
    return None if denominator == 0 else numerator / denominator


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


@dataclass(frozen=True)
class Confusion:
    """Counts of a binary decision; ``positive`` is the class whose misses matter."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float | None:
        return ratio(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        return ratio(self.tp, self.tp + self.fn)

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    def add(self, *, expected: bool, actual: bool) -> Confusion:
        return Confusion(
            tp=self.tp + (1 if expected and actual else 0),
            fp=self.fp + (1 if not expected and actual else 0),
            fn=self.fn + (1 if expected and not actual else 0),
            tn=self.tn + (1 if not expected and not actual else 0),
        )
