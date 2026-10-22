"""The shape of a case: a goal the agent keeps working on across many wake-ups (docs/DESIGN-case-loop.md).

A case is data in five parts: ``goal`` (one sentence the data can confirm), ``triggers`` (what wakes it),
``state`` (a typed record every run reads and writes), ``stop`` (hard limits code checks before each node) and
``verify`` (where to look to know the goal is reached). Its work is a graph: nodes where code decides
(``CodeNode``) or where the model takes one turn of the customer's chat (``TurnNode``), and edges between
them, conditional or not. An edge that goes back must carry a counter with a cap, so a loop always ends.

Nothing here runs anything: the engine (``agent_app.cases``) wakes cases, runs nodes and stores records;
plugins declare the cases. This module knows no plugin, database or model.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final, Literal

from pydantic import BaseModel

CaseStatus = Literal["open", "waiting", "needs_human", "done", "stopped"]
LIVE: Final[frozenset[str]] = frozenset({"open", "waiting", "needs_human"})
"""A case in these states blocks a second one of the same kind and key."""
WaitFor = Literal["customer", "clock", "event"]
NAME: Final = re.compile(r"[a-z][a-z0-9_]{0,63}")


@dataclass(frozen=True, slots=True)
class Trigger:
    """What wakes a case: the clock (``wake_at`` came), a message of the customer, or an event a plugin
    reports (``ctx.cases.wake``)."""

    kind: Literal["clock", "customer_message", "event"]
    event: str | None = None

    def __post_init__(self) -> None:
        if (self.kind == "event") != bool(self.event):
            raise ValueError("an event trigger names its event, and only an event trigger does")


@dataclass(frozen=True, slots=True)
class StopRules:
    """Hard limits, checked by code before every node; nothing the model says moves them."""

    max_turns: int = 6
    """Turns of the model the case may take in all."""
    max_proactive: int = 2
    """Messages the case may send the customer in all."""
    max_age: timedelta = timedelta(days=14)
    """The case ends this long after it opened, whatever its state."""
    counters: Mapping[str, int] = field(default_factory=dict[str, int])
    """Cap of each counter of the state; an edge back that brings a counter to its cap ends the case."""

    def __post_init__(self) -> None:
        if self.max_turns < 1 or self.max_proactive < 0 or self.max_age <= timedelta(0):
            raise ValueError("max_turns must be at least 1, max_proactive not negative, max_age positive")
        bad = [name for name, cap in self.counters.items() if cap < 1]
        if bad:
            raise ValueError(f"counter caps must be at least 1: {', '.join(bad)}")


@dataclass(frozen=True, slots=True)
class Budget:
    per_person_per_day: int = 2
    """Messages one person may get from all cases together in one local day (the agent's settings may lower
    it). Over it, a case waits for the next day instead of writing."""

    def __post_init__(self) -> None:
        if self.per_person_per_day < 1:
            raise ValueError("per_person_per_day must be at least 1")


@dataclass(frozen=True, slots=True)
class Decision:
    """What a node decided. Empty: follow the edges. A ``TurnNode`` that sent a message and decided nothing
    waits for the customer."""

    next: str | None = None
    """The node to go to; it must be the end of an edge from this node (its counter still counts)."""
    wait_for: WaitFor | None = None
    wake_at: datetime | None = None
    """Required to wait for the clock; with ``customer``, the latest moment to look again anyway."""
    done: str | None = None
    """The goal is reached; why."""
    stop: str | None = None
    """The case ends without its goal; why."""
    patch: Mapping[str, Any] = field(default_factory=dict[str, Any])
    """Changes to the state, applied before the edges are read."""
    note: str = ""
    """Why, for the case's log (what the model said, what code saw)."""

    def __post_init__(self) -> None:
        if self.done is not None and self.stop is not None:
            raise ValueError("a decision is done or stopped, not both")
        ends = self.done is not None or self.stop is not None
        if ends and (self.wait_for is not None or self.next is not None):
            raise ValueError("a decision that ends the case neither waits nor moves on")
        if self.wait_for == "clock" and self.wake_at is None:
            raise ValueError("waiting for the clock needs wake_at")
        if self.wake_at is not None and self.wake_at.tzinfo is None:
            raise ValueError("wake_at must carry a time zone")
        if self.wake_at is not None and self.wait_for is None:
            raise ValueError("wake_at needs wait_for")


@dataclass(frozen=True, slots=True)
class CodeNode:
    """Code decides from the state: no model call unless the plugin makes one itself."""

    id: str
    run: Callable[[Any, datetime], Awaitable[Decision]]
    """``(state, now) -> Decision``; ``state`` is an instance of the case's ``state_model``."""


@dataclass(frozen=True, slots=True)
class TurnNode:
    """The model takes one turn of the customer's chat with the case's goal in front of it, and may call
    ``case_done`` or ``case_wait_until``. Its answer goes to the customer, unless it is the channel's skip
    word. (A step where the model only judges is a ``CodeNode`` that calls the model itself: an answer the
    customer never got must not enter the chat's history.)"""

    id: str
    instruction: Callable[[Any, datetime], str]
    """``(state, now) -> text``: what to do at this step, in the plugin's words."""
    look_again: timedelta | None = None
    """When the turn decided nothing and the case waits for the customer: run the next node this long later
    anyway, heard or not (a follow-up looks again after a silence). None waits for the customer only."""


Node = CodeNode | TurnNode


@dataclass(frozen=True, slots=True)
class Edge:
    src: str
    dst: str
    when: Callable[[Any], bool] | None = None
    """``(state) -> bool``; None always holds. The first edge from a node that holds is taken."""
    counter: str | None = None
    """A field of the state this edge adds one to; required on an edge that goes back."""
    on: Literal["ok", "error"] = "ok"
    """``error``: taken only when its node raised (the engine tries again from ``dst``, after a pause), never
    when the node ran; one per node, without ``when``."""


@dataclass(frozen=True, slots=True)
class Graph:
    start: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...] = ()

    def node(self, node_id: str) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def edges_from(self, node_id: str) -> tuple[Edge, ...]:
        return tuple(e for e in self.edges if e.src == node_id)


@dataclass(frozen=True, slots=True)
class CaseSpec:
    """One kind of case, declared by a plugin (``ctx.register_case``). Checked when built: a spec that could
    loop forever, or names a node that is not there, cannot exist."""

    kind: str
    state_model: type[BaseModel]
    goal: Callable[[Any], str]
    """``(state) -> one sentence``: what the case is for, checkable from data."""
    triggers: tuple[Trigger, ...]
    graph: Graph
    verify: Callable[[Any], str]
    """``(state) -> text``: where to look to know the goal is reached (a tool, a field)."""
    stop: StopRules = field(default_factory=StopRules)
    budget: Budget = field(default_factory=Budget)
    stop_if: Callable[[Any, str], str | None] | None = None
    """``(state, customer's text) -> why`` to end the case at once when the customer writes (a "stop
    writing to me"); None to keep it."""

    def __post_init__(self) -> None:
        _check(self)

    def wakes_on(self, kind: str) -> bool:
        return any(t.kind == kind for t in self.triggers)


def _check(spec: CaseSpec) -> None:
    if not NAME.fullmatch(spec.kind):
        raise ValueError(f"case kind {spec.kind!r}: use a-z, 0-9 and _, starting with a letter")
    if not spec.triggers:
        raise ValueError(f"case {spec.kind}: needs at least one trigger")
    order = [n.id for n in spec.graph.nodes]
    if not order or len(set(order)) != len(order):
        raise ValueError(f"case {spec.kind}: node ids must be present and unique")
    bad_ids = [i for i in order if not NAME.fullmatch(i)]
    if bad_ids:
        raise ValueError(f"case {spec.kind}: invalid node id(s) {', '.join(bad_ids)}")
    if spec.graph.start not in order:
        raise ValueError(f"case {spec.kind}: start node {spec.graph.start} is not a node")
    fields = spec.state_model.model_fields
    unknown = [name for name in spec.stop.counters if name not in fields]
    if unknown:
        raise ValueError(f"case {spec.kind}: counter(s) not in the state: {', '.join(unknown)}")
    failing = [e.src for e in spec.graph.edges if e.on == "error"]
    if len(set(failing)) != len(failing):
        raise ValueError(f"case {spec.kind}: one error edge per node at most")
    for edge in spec.graph.edges:
        where = f"case {spec.kind}, edge {edge.src} -> {edge.dst}"
        if edge.on == "error" and edge.when is not None:
            raise ValueError(f"{where}: an error edge has no condition")
        if edge.src not in order or edge.dst not in order:
            raise ValueError(f"{where}: names a node that is not there")
        if edge.counter is not None and edge.counter not in spec.stop.counters:
            raise ValueError(f"{where}: counter {edge.counter} has no cap in stop.counters")
        if order.index(edge.dst) <= order.index(edge.src) and edge.counter is None:
            raise ValueError(f"{where}: goes back, so it needs a counter with a cap")
