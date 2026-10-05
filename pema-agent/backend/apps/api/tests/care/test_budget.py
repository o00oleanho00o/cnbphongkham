"""Per-turn delegation budget (package M, step M4). New tests; the clock is fake, nothing sleeps."""

from __future__ import annotations

from datetime import timedelta

from pema.care.budget import (
    BACKGROUND_DEADLINE,
    INTERACTIVE_DEADLINE,
    MAX_SPECIALISTS,
    MAX_TOOL_STEPS,
    BudgetReason,
    TurnBudget,
    TurnMode,
)
from pema.care.testing import FakeClock, vn


def _budget(
    *, mode: TurnMode = TurnMode.INTERACTIVE, token_ceiling: int = 24_000, deadline: timedelta | None = None
) -> tuple[TurnBudget, FakeClock]:
    clock = FakeClock(vn(2026, 10, 3, 10, 0))
    return TurnBudget(mode=mode, clock=clock, token_ceiling=token_ceiling, deadline=deadline), clock


def test_the_limits_are_those_of_the_plan() -> None:
    assert (MAX_SPECIALISTS, MAX_TOOL_STEPS) == (3, 8)
    assert (timedelta(minutes=3), timedelta(minutes=20)) == (INTERACTIVE_DEADLINE, BACKGROUND_DEADLINE)


def test_the_deadline_depends_on_the_mode() -> None:
    interactive, _ = _budget(mode=TurnMode.INTERACTIVE)
    background, _ = _budget(mode=TurnMode.BACKGROUND)
    assert interactive.seconds_left() == 180
    assert background.seconds_left() == 1200


def test_a_fourth_specialist_is_refused_and_not_counted() -> None:
    budget, _ = _budget()
    assert [budget.reserve() for _ in range(3)] == [None, None, None]
    assert budget.reserve() is BudgetReason.SPECIALISTS
    assert budget.specialists_started == 3


def test_an_expired_deadline_refuses_a_new_specialist() -> None:
    budget, clock = _budget()
    clock.advance(timedelta(minutes=3, seconds=1))
    assert budget.seconds_left() == 0
    assert budget.reserve() is BudgetReason.DEADLINE
    assert budget.specialists_started == 0


def test_the_token_ceiling_stops_new_work_but_not_a_result_already_charged() -> None:
    budget, _ = _budget(token_ceiling=1000)
    assert budget.reserve() is None
    budget.charge_tokens(1200)
    assert (budget.tokens_left(), budget.exhausted()) == (0, BudgetReason.TOKENS)
    assert budget.reserve() is BudgetReason.TOKENS


def test_a_negative_charge_is_ignored() -> None:
    budget, _ = _budget(token_ceiling=1000)
    budget.charge_tokens(-50)
    assert budget.tokens_used == 0


def test_the_deadline_can_be_set_for_one_turn() -> None:
    budget, clock = _budget(deadline=timedelta(seconds=30))
    clock.advance(timedelta(seconds=10))
    assert budget.seconds_left() == 20
