"""Per-turn budget of the delegations of one care turn (PLAN-AI01-M sections 9 and 11, recipe M4 step 6).

New module (not a port). One ``TurnBudget`` lives for ONE care turn and is shared by every ``delegate`` call
of that turn:

* at most ``MAX_SPECIALISTS`` (3) delegations per turn;
* at most ``MAX_TOOL_STEPS`` (8) model steps for each specialist;
* a token ceiling for the whole turn (``DEFAULT_TOKEN_CEILING``, TEMPORARY: sized for a local 8B model with a
  context of a few thousand tokens, to be tuned with the real numbers of M6);
* a deadline: 3 minutes for an interactive turn (a patient waits), 20 minutes for background work (the 06:00
  tick, a scheduled job).

Running out of any of them is not an error: the delegation answers ``TaskResult(needs_human=True)`` and the
turn goes to a person. ``reserve`` is the single entry point (check, then count), so two concurrent
delegations of one turn cannot both take the last slot. The clock is injected so tests never sleep.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

MAX_SPECIALISTS = 3
MAX_TOOL_STEPS = 8
DEFAULT_TOKEN_CEILING = 24_000
"""TEMPORARY (awaiting M6 measurements): total tokens of all specialists of one turn."""
INTERACTIVE_DEADLINE = timedelta(minutes=3)
BACKGROUND_DEADLINE = timedelta(minutes=20)

type Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TurnMode(StrEnum):
    INTERACTIVE = "interactive"
    BACKGROUND = "background"


class BudgetReason(StrEnum):
    """Why a delegation was refused or cut short (the ``<why>`` of ``budget_exhausted:<why>``)."""

    SPECIALISTS = "max_specialists"
    TOOL_STEPS = "max_tool_steps"
    TOKENS = "token_ceiling"
    DEADLINE = "deadline"


@dataclass
class TurnBudget:
    mode: TurnMode = TurnMode.INTERACTIVE
    clock: Clock = _utc_now
    max_specialists: int = MAX_SPECIALISTS
    max_tool_steps: int = MAX_TOOL_STEPS
    token_ceiling: int = DEFAULT_TOKEN_CEILING
    deadline: timedelta | None = None
    """``None``: the default of the mode (3 or 20 minutes)."""
    started_at: datetime = field(init=False)
    limit: timedelta = field(init=False)
    specialists_started: int = field(default=0, init=False)
    tokens_used: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.started_at = self.clock()
        default = INTERACTIVE_DEADLINE if self.mode is TurnMode.INTERACTIVE else BACKGROUND_DEADLINE
        self.limit = self.deadline if self.deadline is not None else default

    # ------------------------------------------------------------------------------------ reading
    @property
    def deadline_at(self) -> datetime:
        return self.started_at + self.limit

    def seconds_left(self) -> float:
        return max(0.0, (self.deadline_at - self.clock()).total_seconds())

    def tokens_left(self) -> int:
        return max(0, self.token_ceiling - self.tokens_used)

    def exhausted(self) -> BudgetReason | None:
        """The first limit that is already hit (the count of specialists is NOT here: it only stops a NEW "
        "one)."""
        if self.seconds_left() <= 0:
            return BudgetReason.DEADLINE
        if self.tokens_used >= self.token_ceiling:
            return BudgetReason.TOKENS
        return None

    # ----------------------------------------------------------------------------------- writing
    def reserve(self) -> BudgetReason | None:
        """Take one specialist slot. ``None`` = granted; otherwise the reason it was refused (nothing "
        "counted)."""
        reason = self.exhausted()
        if reason is not None:
            return reason
        if self.specialists_started >= self.max_specialists:
            return BudgetReason.SPECIALISTS
        self.specialists_started += 1
        return None

    def charge_tokens(self, tokens: int) -> None:
        self.tokens_used += max(0, tokens)
