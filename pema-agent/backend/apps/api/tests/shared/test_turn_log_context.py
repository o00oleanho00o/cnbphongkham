# ported from: src/shared/turn-log-context.test.ts
"""The thing that matters: the context SURVIVES ``await``. That is why ``contextvars`` replaces a module
variable: a log line produced several awaits deep would lose it, or worse, pick up another turn's."""

from __future__ import annotations

import asyncio

import pytest

from pema.shared.turn_log_context import TurnLogContext, current_turn_log_context, run_in_turn_log_context

CTX = TurnLogContext(account_id="acc-1", thread_id="t-1", turn_id=42)


def test_outside_a_turn_there_is_no_context() -> None:
    """ngoài lượt thì không có ngữ cảnh - mixin không ghép gì vào log hệ thống"""
    assert current_turn_log_context() is None


async def test_context_survives_nested_awaits_and_is_clean_after_the_turn() -> None:
    """giữ được ngữ cảnh qua nhiều tầng await"""

    async def inner() -> None:
        await asyncio.sleep(0)
        assert current_turn_log_context() == CTX, "nested function also sees it: the case of a tool"

    async def turn() -> None:
        assert current_turn_log_context() == CTX
        await asyncio.sleep(0.005)
        assert current_turn_log_context() == CTX, "still there after a sleep"
        await inner()

    await run_in_turn_log_context(CTX, turn)
    assert current_turn_log_context() is None, "leaving the turn must leave nothing behind"


async def test_two_interleaved_turns_do_not_mix_contexts() -> None:
    """hai lượt chạy xen kẽ KHÔNG lẫn ngữ cảnh của nhau"""
    seen: list[int] = []

    async def one_turn(turn_id: int, wait: float) -> None:
        async def work() -> None:
            await asyncio.sleep(wait)
            context = current_turn_log_context()
            assert context is not None
            seen.append(context.turn_id)

        await run_in_turn_log_context(TurnLogContext("acc-1", "t-1", turn_id), work)

    # Turn 1 waits longer so it ends AFTER turn 2: with a module variable turn 1 would read turn 2's id.
    await asyncio.gather(one_turn(1, 0.02), one_turn(2, 0.005))
    assert seen == [2, 1]


async def test_an_error_does_not_leave_the_context_behind() -> None:
    """lỗi ném ra không để ngữ cảnh sót lại"""

    async def failing_turn() -> None:
        raise RuntimeError("lượt hỏng")

    with pytest.raises(RuntimeError, match="lượt hỏng"):
        await run_in_turn_log_context(CTX, failing_turn)
    assert current_turn_log_context() is None
