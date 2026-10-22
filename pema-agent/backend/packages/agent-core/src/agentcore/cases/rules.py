"""The rules of a case, pure: what blocks the next node, and what a decision makes of the record.

``node`` of a record is the node to run next. After a node ran, ``apply`` moves it: to ``decision.next``
(which must be the end of an edge from the node that ran), else along the first edge whose ``when`` holds.
An edge with a counter adds one to that field of the state; reaching its cap ends the case. No edge left
ends the case as done. A ``TurnNode`` that sent and decided nothing waits for the customer, its pointer
already moved; so does one that answered with the skip word. A case still ``open`` after ``apply`` runs its
next node at once (the engine bounds how many).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final

from pydantic import BaseModel

from agentcore.cases.spec import LIVE, CaseSpec, CaseStatus, Decision, Edge, TurnNode, WaitFor

CASE_MARK: Final = "[Case"
"""Starts the text the engine gives the agent for a case's turn: the harness's words, not the customer's."""
MAX_REASON_CHARS: Final = 300


@dataclass(frozen=True, slots=True)
class CaseRecord:
    """One case as stored. ``state`` is the JSON of the spec's ``state_model``."""

    id: int
    kind: str
    key: str
    channel: str
    conversation_id: str
    user_id: str
    session_id: str
    goal: str
    status: CaseStatus
    node: str
    state: Mapping[str, Any]
    deadline: datetime
    created_at: datetime
    updated_at: datetime
    wait_for: WaitFor | None = None
    wake_at: datetime | None = None
    turns: int = 0
    proactive_sent: int = 0
    end_reason: str | None = None
    closed_at: datetime | None = None
    version: int = 0

    @property
    def live(self) -> bool:
        return self.status in LIVE


@dataclass(frozen=True, slots=True)
class Block:
    """Why the next node may not run. With ``retry_at`` the case waits until then; without, it stops."""

    reason: str
    retry_at: datetime | None = None


def state_of(spec: CaseSpec, record: CaseRecord) -> BaseModel:
    return spec.state_model.model_validate(dict(record.state))


def new_record(
    spec: CaseSpec,
    *,
    key: str,
    channel: str,
    conversation_id: str,
    user_id: str,
    session_id: str,
    state: BaseModel,
    now: datetime,
) -> CaseRecord:
    """A case about to open, at the start node (the store gives it its id)."""
    if not isinstance(state, spec.state_model):
        raise TypeError(f"case {spec.kind}: state must be a {spec.state_model.__name__}")
    return CaseRecord(
        id=0,
        kind=spec.kind,
        key=key,
        channel=channel,
        conversation_id=conversation_id,
        user_id=user_id,
        session_id=session_id,
        goal=spec.goal(state),
        status="open",
        node=spec.graph.start,
        state=state.model_dump(mode="json"),
        deadline=now + spec.stop.max_age,
        created_at=now,
        updated_at=now,
    )


def blocked(
    spec: CaseSpec,
    record: CaseRecord,
    now: datetime,
    *,
    enabled: bool = True,
    sent_to_person_today: int = 0,
    per_person_per_day: int | None = None,
    next_day: datetime | None = None,
) -> Block | None:
    """Whether the record's next node may run now. ``per_person_per_day`` (the agent's setting) never raises
    the spec's own budget; ``next_day`` is when the person's day starts again (the case waits till then)."""
    if not enabled:
        return Block("disabled")
    if not record.live:
        return Block("closed")
    if now >= record.deadline:
        return Block("expired")
    node = spec.graph.node(record.node)
    if node is None:
        return Block(f"no node {record.node}")
    for name, cap in spec.stop.counters.items():
        if int(record.state.get(name, 0)) >= cap:
            return Block(f"{name} reached {cap}")
    if not isinstance(node, TurnNode):
        return None
    if record.turns >= spec.stop.max_turns:
        return Block("max_turns")
    if record.proactive_sent >= spec.stop.max_proactive:
        return Block("max_proactive")
    cap = spec.budget.per_person_per_day
    if per_person_per_day is not None:
        cap = min(cap, per_person_per_day)
    if sent_to_person_today >= cap:
        return Block("person_daily_cap", next_day)
    return None


def _edge(spec: CaseSpec, ran: str, state: BaseModel, chosen: str | None) -> Edge | None:
    edges = spec.graph.edges_from(ran)
    if chosen is not None:
        found = next((e for e in edges if e.dst == chosen), None)
        if found is None:
            raise ValueError(f"case {spec.kind}: no edge {ran} -> {chosen}")
        return found
    return next((e for e in edges if e.when is None or e.when(state)), None)


def _end(record: CaseRecord, status: CaseStatus, reason: str, now: datetime, **changes: Any) -> CaseRecord:
    return replace(
        record,
        status=status,
        end_reason=reason.strip()[:MAX_REASON_CHARS] or status,
        wait_for=None,
        wake_at=None,
        closed_at=now,
        updated_at=now,
        **changes,
    )


def apply(spec: CaseSpec, record: CaseRecord, decision: Decision, now: datetime) -> CaseRecord:
    """The record after the node at ``record.node`` ran and decided ``decision``. Raises ``ValueError`` on a
    ``next`` that is not an edge, or a patch the state model refuses."""
    ran = spec.graph.node(record.node)
    merged = {**record.state, **decision.patch}
    state = spec.state_model.model_validate(merged)
    changes: dict[str, Any] = {"state": state.model_dump(mode="json"), "goal": spec.goal(state)}
    if decision.stop is not None:
        return _end(record, "stopped", decision.stop, now, **changes)
    if decision.done is not None:
        return _end(record, "done", decision.done, now, **changes)
    edge = _edge(spec, record.node, state, decision.next)
    if edge is None:
        return _end(record, "done", "end of the graph", now, **changes)
    if edge.counter is not None:
        count = int(changes["state"].get(edge.counter, 0)) + 1
        changes["state"] = {**changes["state"], edge.counter: count}
        cap = spec.stop.counters[edge.counter]
        if count >= cap:
            return _end(record, "stopped", f"{edge.counter} reached {cap}", now, **changes)
    wait_for = decision.wait_for
    wake_at = decision.wake_at
    if wait_for is None and isinstance(ran, TurnNode):
        wait_for = "customer"  # it wrote (or chose to say nothing): the next move is the customer's
    if wake_at is not None:
        wake_at = min(wake_at, record.deadline)
    status: CaseStatus = "open" if wait_for is None else "waiting"
    return replace(
        record, node=edge.dst, status=status, wait_for=wait_for, wake_at=wake_at, updated_at=now, **changes
    )


def turn_text(spec: CaseSpec, record: CaseRecord, node: TurnNode, now: datetime) -> str:
    """What the agent is told at a case's turn: the goal, how to check it, this step, and how to steer the
    case. Goes into the chat as a message marked as the harness's (``CASE_MARK``), never as the customer's."""
    state = state_of(spec, record)
    return (
        f"{CASE_MARK} · {spec.kind}] Goal: {record.goal}\n"
        f"How to check it: {spec.verify(state)}\n"
        f"This step: {node.instruction(state, now)}\n"
        "When the goal is reached, call case_done and say how you know. To come back to this later, call "
        "case_wait_until (when the customer answers, or at a time). Otherwise the case waits for the "
        "customer."
    )
