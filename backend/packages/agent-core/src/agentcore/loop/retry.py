"""When a failed model call is tried again, and after how long."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from agentcore.harness.model.errors import ModelError, ModelErrorKind

RETRYABLE: Final[frozenset[ModelErrorKind]] = frozenset({"rate_limit", "transient", "empty_response"})


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Rate limits, dropped or stalled connections and empty completions are tried again after a pause that
    doubles each time (``Retry-After`` wins when the provider sends one); anything else fails at once."""

    max_retries: int = 4
    base_s: float = 0.5
    max_s: float = 10.0
    jitter: float = 0.2
    """Up to this share is added at random, so clients that failed together do not retry together."""

    def __post_init__(self) -> None:
        if self.max_retries < 0 or self.base_s < 0 or self.max_s < self.base_s or not 0 <= self.jitter <= 1:
            raise ValueError("invalid retry policy")

    def retries(self, err: ModelError) -> bool:
        return err.kind in RETRYABLE

    def delay(self, retry: int, err: ModelError, rand: Callable[[], float] = random.random) -> float:
        """The pause before retry number ``retry`` (1 for the first)."""
        if err.retry_after_s is not None:
            return err.retry_after_s
        pause = min(self.max_s, self.base_s * 2 ** (retry - 1))
        return pause * (1 + self.jitter * rand())
