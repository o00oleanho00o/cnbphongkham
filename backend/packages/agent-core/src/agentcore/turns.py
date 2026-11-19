"""The shape of a turn that runs along a graph (docs/PLAN-rag-graph.md, section 4).

A plugin may declare one graph for the customer's turns (``ctx.register_turn_graph``): nodes where code
decides (``CodeStep``), where the model works (``ModelStep``: the usual loop of model calls and tools, with an
instruction of the plugin in the turn's context block) and where the turn ends (``SendStep``). Edges are the
ones of the case graphs (``agentcore.cases.Edge``): the first edge from a node whose ``when`` holds is taken;
an edge with a counter is taken only while its counter, a field of the state, is below its cap (``counters``),
and taking it adds one. An edge that goes back must carry a counter, and every node must lead to a
``SendStep``, so a turn's graph always ends (rule H3).

Nothing here runs anything: ``agentcore.loop.run_turn`` walks the graph, plugins declare it. This module knows
no plugin, database or model.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from agentcore.cases.spec import Edge
from agentcore.graph_rules import NAME, check_graph
from agentcore.messages import Message

DEFAULT_MAX_NODES = 12


@dataclass(frozen=True, slots=True)
class TurnView:
    """What a ``CodeStep`` may read of the turn."""

    user_text: str
    """What the person wrote for this turn (messages collected together are joined)."""
    history: tuple[Message, ...]
    """The chat as the model sees it now, this turn's messages included."""
    draft: str
    """The text of the latest answer a kept ``ModelStep`` wrote in this turn; empty before the first."""
    tool_texts: tuple[str, ...]
    """The results of every tool call of this turn, in order."""
    now: datetime
    channel: str | None
    is_group: bool


@dataclass(frozen=True, slots=True)
class Step:
    """What a ``CodeStep`` decided: changes to the state, applied before the edges are read, and why (for the
    trace, and for the model when the walk sends it back to write again)."""

    patch: Mapping[str, Any] = field(default_factory=dict[str, Any])
    note: str = ""


@dataclass(frozen=True, slots=True)
class ModelOutcome:
    text: str
    tool_texts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CodeStep:
    id: str
    run: Callable[[Any, TurnView], Awaitable[Step]]
    """``(state, view) -> Step``; ``state`` is an instance of the spec's ``state_model``."""


@dataclass(frozen=True, slots=True)
class ModelStep:
    """The model works: calls tools and answers, as in a turn without a graph. ``keep``: its messages enter
    the chat's history and its answer is the turn's draft. Not kept: one call without tools whose text only
    ``after`` reads (a model that rewrites a question, judges, sorts); the customer never sees it."""

    id: str
    instruction: Callable[[Any], str]
    """``(state) -> text`` put in the context block of each of its calls; never stored."""
    tools: tuple[str, ...] | None = None
    """The tools it may call; None for every tool of the agent, ``()`` for none."""
    max_steps: int = 3
    """Model calls of this node that may use tools; one more without tools answers when they run out."""
    keep: bool = True
    after: Callable[[Any, ModelOutcome], Mapping[str, Any]] | None = None
    """``(state, outcome) -> patch`` of the state."""


@dataclass(frozen=True, slots=True)
class SendStep:
    """The turn ends: its reply is the draft, or ``text(state)`` written by code."""

    id: str
    text: Callable[[Any], str] | None = None


TurnStep = CodeStep | ModelStep | SendStep


@dataclass(frozen=True, slots=True)
class TurnGraph:
    start: str
    nodes: tuple[TurnStep, ...]
    edges: tuple[Edge, ...] = ()

    def node(self, node_id: str) -> TurnStep | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def edges_from(self, node_id: str) -> tuple[Edge, ...]:
        return tuple(e for e in self.edges if e.src == node_id)


@dataclass(frozen=True, slots=True)
class TurnGraphSpec:
    """A turn's graph, declared by a plugin. Checked when built: one that could loop forever, names a node
    that is not there, or has a node that cannot reach a ``SendStep``, cannot exist."""

    name: str
    state_model: type[BaseModel]
    graph: TurnGraph
    counters: Mapping[str, int] = field(default_factory=dict[str, int])
    """Cap of each counter: how many times its edges may be taken in one turn."""
    max_nodes: int = DEFAULT_MAX_NODES
    """Nodes one turn may run in all; the walk stops after them."""
    active: Callable[[], Awaitable[bool]] | None = None
    """Asked when a turn starts; False runs that turn as if there were no graph (a setting switched off)."""

    def __post_init__(self) -> None:
        _check(self)


def _check(spec: TurnGraphSpec) -> None:
    where = f"turn graph {spec.name}"
    if not NAME.fullmatch(spec.name):
        raise ValueError(f"{where}: use a-z, 0-9 and _, starting with a letter")
    if spec.max_nodes < 1 or any(cap < 1 for cap in spec.counters.values()):
        raise ValueError(f"{where}: max_nodes and counter caps must be at least 1")
    graph = spec.graph
    order = [n.id for n in graph.nodes]
    check_graph(where, order, graph.start, graph.edges, spec.counters, spec.state_model.model_fields)
    for node in graph.nodes:
        if isinstance(node, SendStep) and graph.edges_from(node.id):
            raise ValueError(f"{where}: send step {node.id} ends the turn, it has no edges")
        if isinstance(node, ModelStep) and node.max_steps < 1:
            raise ValueError(f"{where}: model step {node.id} needs max_steps of at least 1")
    ends = {n.id for n in graph.nodes if isinstance(n, SendStep)}
    reaches = set(ends)
    grew = True
    while grew:
        grew = False
        for edge in graph.edges:
            if edge.dst in reaches and edge.src not in reaches:
                reaches.add(edge.src)
                grew = True
    stuck = [i for i in order if i not in reaches]
    if stuck:
        raise ValueError(f"{where}: node(s) {', '.join(stuck)} cannot reach a send step")
