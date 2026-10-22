"""Cases: a spec that could loop forever cannot be built; each hard limit blocks; a decision moves the record
as documented in ``agentcore.cases.rules``; the two steering tools hand the engine the right decision."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from agentcore import ToolContext
from agentcore.cases import (
    Budget,
    CaseRecord,
    CaseSpec,
    CodeNode,
    Decision,
    Edge,
    Graph,
    StopRules,
    Trigger,
    TurnNode,
    apply,
    blocked,
    make_case_tools,
    new_record,
    turn_text,
)

NOW = datetime(2026, 10, 22, 3, 0, tzinfo=UTC)


class Quiet(BaseModel):
    unanswered: int = 0
    verdict: str = ""


async def _judge(state: Quiet, now: datetime) -> Decision:
    return Decision()


def _goal(state: Quiet) -> str:
    return "the customer books or says no"


def _verify(state: Quiet) -> str:
    return "crm_my_appointments"


def _spec(**kw: object) -> CaseSpec:
    base: dict[str, object] = {
        "kind": "follow_up",
        "state_model": Quiet,
        "goal": _goal,
        "triggers": (Trigger("clock"), Trigger("customer_message")),
        "graph": Graph(
            start="judge",
            nodes=(
                CodeNode("judge", _judge),
                TurnNode("write", lambda s, now: "write one short message"),
            ),
            edges=(
                Edge("judge", "write", when=lambda s: s.verdict == "later"),
                Edge("write", "judge", counter="unanswered"),
            ),
        ),
        "verify": _verify,
        "stop": StopRules(max_turns=3, max_proactive=2, counters={"unanswered": 2}),
        "budget": Budget(per_person_per_day=2),
    }
    base.update(kw)
    return CaseSpec(**base)  # type: ignore[arg-type]


def _record(spec: CaseSpec, **kw: object) -> CaseRecord:
    record = new_record(
        spec,
        key="c1",
        channel="zalo-a",
        conversation_id="c1",
        user_id="u1",
        session_id="s1",
        state=Quiet(),
        now=NOW,
    )
    return replace(record, **kw)  # type: ignore[arg-type]


# --- the shape ---


def test_an_edge_back_without_a_counter_is_refused() -> None:
    graph = Graph("a", (CodeNode("a", _judge), CodeNode("b", _judge)), (Edge("a", "b"), Edge("b", "a")))
    with pytest.raises(ValueError, match="goes back"):
        _spec(graph=graph)


def test_an_edge_to_itself_counts_as_going_back() -> None:
    graph = Graph("a", (CodeNode("a", _judge),), (Edge("a", "a"),))
    with pytest.raises(ValueError, match="goes back"):
        _spec(graph=graph)


def test_a_counter_without_a_cap_is_refused() -> None:
    graph = Graph(
        "a",
        (CodeNode("a", _judge), CodeNode("b", _judge)),
        (Edge("a", "b"), Edge("b", "a", counter="verdict")),
    )
    with pytest.raises(ValueError, match="no cap"):
        _spec(graph=graph)


def test_a_capped_counter_must_be_a_field_of_the_state() -> None:
    with pytest.raises(ValueError, match="not in the state"):
        _spec(stop=StopRules(counters={"tries": 2}))


@pytest.mark.parametrize(
    "graph",
    [
        Graph("x", (CodeNode("a", _judge),)),
        Graph("a", (CodeNode("a", _judge),), (Edge("a", "zz"),)),
        Graph("a", (CodeNode("a", _judge), CodeNode("a", _judge))),
        Graph("A", (CodeNode("A", _judge),)),
    ],
)
def test_a_graph_naming_what_is_not_there_is_refused(graph: Graph) -> None:
    with pytest.raises(ValueError, match="case follow_up"):
        _spec(graph=graph)


def test_a_case_needs_a_trigger_and_a_plain_kind() -> None:
    with pytest.raises(ValueError, match="trigger"):
        _spec(triggers=())
    with pytest.raises(ValueError, match="kind"):
        _spec(kind="Follow-Up")
    with pytest.raises(ValueError, match="event"):
        Trigger("event")


def test_a_decision_cannot_both_end_and_wait() -> None:
    with pytest.raises(ValueError, match="not both"):
        Decision(done="x", stop="y")
    with pytest.raises(ValueError, match="neither waits"):
        Decision(done="x", wait_for="customer")
    with pytest.raises(ValueError, match="needs wake_at"):
        Decision(wait_for="clock")
    with pytest.raises(ValueError, match="time zone"):
        Decision(wait_for="clock", wake_at=datetime(2026, 10, 22, 10))  # naive on purpose


def test_a_new_case_opens_at_the_start_with_its_goal_and_deadline() -> None:
    spec = _spec()
    record = _record(spec)
    assert (record.status, record.node, record.goal) == ("open", "judge", "the customer books or says no")
    assert record.deadline == NOW + spec.stop.max_age
    assert record.state == {"unanswered": 0, "verdict": ""}


# --- what blocks ---


def test_nothing_blocks_a_fresh_case() -> None:
    assert blocked(_spec(), _record(_spec()), NOW) is None


@pytest.mark.parametrize(
    ("changes", "kwargs", "reason"),
    [
        ({}, {"enabled": False}, "disabled"),
        ({"status": "done"}, {}, "closed"),
        ({"deadline": NOW}, {}, "expired"),
        ({"node": "gone"}, {}, "no node gone"),
        ({"state": {"unanswered": 2, "verdict": ""}}, {}, "unanswered reached 2"),
        ({"node": "write", "turns": 3}, {}, "max_turns"),
        ({"node": "write", "proactive_sent": 2}, {}, "max_proactive"),
    ],
)
def test_each_hard_limit_stops_the_case(
    changes: dict[str, object], kwargs: dict[str, object], reason: str
) -> None:
    spec = _spec()
    found = blocked(spec, _record(spec, **changes), NOW, **kwargs)  # type: ignore[arg-type]
    assert found is not None
    assert (found.reason, found.retry_at) == (reason, None)


def test_turn_limits_do_not_block_a_code_node() -> None:
    spec = _spec()
    assert blocked(spec, _record(spec, turns=3, proactive_sent=2), NOW, sent_to_person_today=9) is None


def test_the_daily_cap_of_a_person_defers_to_the_next_day() -> None:
    spec = _spec()
    tomorrow = NOW + timedelta(hours=17)
    found = blocked(spec, _record(spec, node="write"), NOW, sent_to_person_today=2, next_day=tomorrow)
    assert found is not None
    assert (found.reason, found.retry_at) == ("person_daily_cap", tomorrow)


def test_the_setting_lowers_the_daily_cap_but_never_raises_it() -> None:
    spec = _spec()
    record = _record(spec, node="write")
    assert blocked(spec, record, NOW, sent_to_person_today=1, per_person_per_day=1) is not None
    assert blocked(spec, record, NOW, sent_to_person_today=2, per_person_per_day=5) is not None


# --- what a decision does ---


def test_done_and_stop_close_the_case() -> None:
    spec = _spec()
    done = apply(spec, _record(spec), Decision(done="booked for Friday"), NOW)
    assert (done.status, done.end_reason, done.closed_at) == ("done", "booked for Friday", NOW)
    stopped = apply(spec, _record(spec), Decision(stop="asked not to be written to"), NOW)
    assert (stopped.status, stopped.end_reason) == ("stopped", "asked not to be written to")


def test_the_patch_is_read_before_the_edges() -> None:
    spec = _spec()
    moved = apply(spec, _record(spec), Decision(patch={"verdict": "later"}), NOW)
    assert (moved.node, moved.status, moved.state["verdict"]) == ("write", "open", "later")


def test_no_edge_that_holds_ends_the_case_as_done() -> None:
    spec = _spec()
    ended = apply(spec, _record(spec), Decision(patch={"verdict": "done"}), NOW)
    assert (ended.status, ended.end_reason) == ("done", "end of the graph")


def test_waiting_for_the_clock_keeps_the_pointer_moved() -> None:
    spec = _spec()
    at = NOW + timedelta(hours=20)
    waiting = apply(
        spec, _record(spec), Decision(wait_for="clock", wake_at=at, patch={"verdict": "later"}), NOW
    )
    assert (waiting.status, waiting.wait_for, waiting.wake_at, waiting.node) == (
        "waiting",
        "clock",
        at,
        "write",
    )


def test_a_wake_up_after_the_deadline_is_brought_to_the_deadline() -> None:
    spec = _spec()
    record = _record(spec)
    late = record.deadline + timedelta(days=3)
    waiting = apply(spec, record, Decision(wait_for="clock", wake_at=late, patch={"verdict": "later"}), NOW)
    assert waiting.wake_at == record.deadline


def test_a_turn_that_wrote_and_decided_nothing_waits_for_the_customer() -> None:
    spec = _spec()
    after = apply(spec, _record(spec, node="write"), Decision(), NOW)
    assert (after.status, after.wait_for, after.node, after.state["unanswered"]) == (
        "waiting",
        "customer",
        "judge",
        1,
    )


def test_the_edge_back_that_reaches_its_cap_stops_the_case() -> None:
    spec = _spec()
    record = _record(spec, node="write", state={"unanswered": 1, "verdict": "later"})
    after = apply(spec, record, Decision(), NOW)
    assert (after.status, after.end_reason, after.state["unanswered"]) == (
        "stopped",
        "unanswered reached 2",
        2,
    )


def test_next_must_be_an_edge_and_still_counts() -> None:
    spec = _spec()
    with pytest.raises(ValueError, match="no edge"):
        apply(spec, _record(spec), Decision(next="judge"), NOW)
    after = apply(spec, _record(spec, node="write"), Decision(next="judge"), NOW)
    assert after.state["unanswered"] == 1


def test_a_patch_the_state_refuses_raises() -> None:
    spec = _spec()
    with pytest.raises(ValueError, match="unanswered"):
        apply(spec, _record(spec), Decision(patch={"unanswered": "many"}), NOW)


def test_the_text_of_a_turn_carries_goal_check_step_and_how_to_steer() -> None:
    spec = _spec()
    record = _record(spec, node="write")
    node = spec.graph.node("write")
    assert isinstance(node, TurnNode)
    text = turn_text(spec, record, node, NOW)
    assert text.startswith("[Case · follow_up] Goal: the customer books or says no")
    assert "How to check it: crm_my_appointments" in text
    assert "This step: write one short message" in text
    assert "case_done" in text
    assert "case_wait_until" in text


# --- the steering tools ---


class Sink:
    def __init__(self, refuse: str | None = None) -> None:
        self.refuse = refuse
        self.taken: list[Decision] = []

    async def take(self, ctx: ToolContext, decision: Decision) -> str | None:
        self.taken.append(decision)
        return self.refuse


CTX = ToolContext(session_id="s1", channel="zalo-a", conversation_id="c1", now=NOW)


async def test_case_done_hands_the_reason_to_the_engine() -> None:
    sink = Sink()
    done, _ = make_case_tools(sink)
    out = await done.handler(done.args_model(reason="crm says confirmed"), CTX)
    assert not out.is_error
    assert sink.taken == [Decision(done="crm says confirmed", note="crm says confirmed")]


async def test_case_wait_until_hands_a_wait_to_the_engine() -> None:
    sink = Sink()
    _, wait = make_case_tools(sink)
    at = NOW + timedelta(days=1)
    out = await wait.handler(wait.args_model(wait_for="clock", until=at, why="call back tomorrow"), CTX)
    assert not out.is_error
    assert sink.taken == [Decision(wait_for="clock", wake_at=at, note="call back tomorrow")]
    await wait.handler(wait.args_model(wait_for="customer"), CTX)
    assert sink.taken[-1] == Decision(wait_for="customer")


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"wait_for": "clock"}, "needs until"),
        ({"wait_for": "clock", "until": NOW - timedelta(minutes=1)}, "future"),
        ({"wait_for": "customer", "until": datetime(2026, 10, 23, 9)}, "offset"),  # naive on purpose
    ],
)
async def test_a_wait_the_engine_cannot_keep_is_refused_before_it(
    args: dict[str, object], error: str
) -> None:
    sink = Sink()
    _, wait = make_case_tools(sink)
    out = await wait.handler(wait.args_model.model_validate(args), CTX)
    assert out.is_error
    assert error in out.text
    assert sink.taken == []


async def test_outside_a_case_the_tools_say_so() -> None:
    done, _ = make_case_tools(Sink(refuse="There is no case running in this chat."))
    out = await done.handler(done.args_model(reason="x"), CTX)
    assert out.is_error
    assert out.text == "There is no case running in this chat."
