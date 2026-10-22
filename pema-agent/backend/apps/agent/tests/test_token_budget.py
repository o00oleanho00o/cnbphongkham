"""The daily token budget, checked before a turn: a conversation (or the whole agent) that spent its budget
gets no more turns that day, while the turn that crossed the line still ended and other conversations go on."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_app.dispatcher import Dispatcher, DispatchSettings, TokenBudget
from agent_app.profile import load_profile
from agent_app.runtime import Runtime, build_runtime
from agentcore import InMemoryTracer, TurnTrace, Usage
from agentcore.channels import InboundMessage
from agentcore.harness.model.scripted import ScriptedModel, reply


def _runtime(tmp_path: Path, *answers: int) -> tuple[Runtime, Dispatcher]:
    """Each answer used that many prompt tokens."""
    path = tmp_path / "agent.toml"
    path.write_text('[agent]\nname = "t"\ntools = ["get_datetime"]\n', encoding="utf-8")
    runtime = build_runtime(load_profile(path), fake=True, env={}, db=None)
    runtime.live.use_model(ScriptedModel([reply(f"answer {n}", input_tokens=n) for n in answers]))
    return runtime, runtime.dispatcher(DispatchSettings(poll_s=0.01))


async def _ask(dispatcher: Dispatcher, message_id: str, user: str = "u1") -> tuple[str, str | None]:
    record, _ = await dispatcher.accept(InboundMessage("http", user, user, message_id, "hi"))
    done = await dispatcher.wait(record.id, 5.0)
    return done.status, done.error_kind


def test_a_budget_says_which_one_is_spent() -> None:
    budget = TokenBudget(per_session_per_day=10, per_day=100)

    assert budget.spent(9, 99) is None
    assert budget.spent(10, 10) == "this conversation's daily token budget is spent"
    assert budget.spent(0, 100) == "the agent's daily token budget is spent"


async def test_a_conversation_that_spent_its_budget_gets_no_more_turns_today(tmp_path: Path) -> None:
    runtime, dispatcher = _runtime(tmp_path, 12_000, 50)
    await runtime.agent_settings.update({"tokens_per_session_per_day": 10_000})

    first = await _ask(dispatcher, "m1")  # starts under the budget, ends over it
    refused = await _ask(dispatcher, "m2")
    other = await _ask(dispatcher, "m3", user="u2")

    assert (first, refused, other) == (("done", None), ("failed", "token_budget"), ("done", None))
    await dispatcher.close()


async def test_the_whole_agent_stops_once_its_daily_budget_is_spent(tmp_path: Path) -> None:
    runtime, dispatcher = _runtime(tmp_path, 100_000)
    await runtime.agent_settings.update({"tokens_per_day": 100_000})

    assert await _ask(dispatcher, "m1") == ("done", None)
    assert await _ask(dispatcher, "m2", user="u2") == ("failed", "token_budget")
    await dispatcher.close()


async def test_only_turns_of_today_count() -> None:
    tracer = InMemoryTracer()
    now = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    for session, started, tokens in (("s1", now, 5), ("s2", now, 7), ("s1", now - timedelta(days=1), 100)):
        trace = TurnTrace(
            turn_id=f"{session}{tokens}",
            tenant_id="t",
            session_id=session,
            user_id=None,
            channel=None,
            started_at=started,
            duration_s=0.0,
            stop="completed",
            steps=1,
            usage=Usage(input_tokens=tokens - 1, output_tokens=1),
            compactions=0,
            error_kind=None,
            events=(),
        )
        await tracer.record(trace)

    assert await tracer.used_since("t", "s1", now - timedelta(hours=1)) == (5, 12)
    assert await tracer.used_since("other", "s1", now - timedelta(hours=1)) == (0, 0)
