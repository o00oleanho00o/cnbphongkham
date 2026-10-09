"""When to compact, and how much recent history to keep word for word."""

from __future__ import annotations

from dataclasses import dataclass

from agentcore.context.tokens import DEFAULT_CHARS_PER_TOKEN


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    window_tokens: int
    """The model's context window."""
    compact_at: float = 0.75
    """Compact when a request would use more than this share of the window left after the reply."""
    keep_recent_ratio: float = 0.20
    """Share of the threshold kept word for word at the end; the current turn is kept whatever its size."""
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN

    def __post_init__(self) -> None:
        if self.window_tokens < 1:
            raise ValueError("window_tokens must be at least 1")
        if not 0 < self.compact_at <= 1:
            raise ValueError("compact_at must be in (0, 1]")
        if not 0 <= self.keep_recent_ratio < 1:
            raise ValueError("keep_recent_ratio must be in [0, 1)")
        if self.chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")

    def threshold(self, max_output_tokens: int) -> int:
        return int(max(self.window_tokens - max_output_tokens, 0) * self.compact_at)

    def keep_budget(self, max_output_tokens: int) -> int:
        return int(self.threshold(max_output_tokens) * self.keep_recent_ratio)
