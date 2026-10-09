"""What happened in a turn, for operators: timings, tokens and outcomes of each model and tool call.

Only metadata is traced; the content lives in the session history. A turn is written once, when it ends (also
when it fails), so tracing adds no database round trip per step.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from agentcore.messages import Usage

TraceStop = Literal["completed", "max_steps", "error"]
EventKind = Literal["model_call", "tool_call", "compaction", "memory_flush"]


@dataclass(frozen=True, slots=True)
class TraceEvent:
    kind: EventKind
    step: int
    duration_s: float
    name: str = ""
    """The tool name for a tool call."""
    is_error: bool = False
    detail: Mapping[str, Any] = field(default_factory=dict[str, Any])
    """JSON-ready metadata: token counts, stop reason, error kind, result size, the guard that blocked."""


@dataclass(frozen=True, slots=True)
class TurnTrace:
    turn_id: str
    tenant_id: str
    session_id: str
    user_id: str | None
    channel: str | None
    started_at: datetime
    duration_s: float
    stop: TraceStop
    steps: int
    usage: Usage
    compactions: int
    error_kind: str | None
    events: tuple[TraceEvent, ...]


class Tracer(Protocol):
    async def record(self, trace: TurnTrace) -> None: ...


class InMemoryTracer:
    """Keeps the traces of this process, newest last; for tests and the CLI without a database."""

    def __init__(self) -> None:
        self.traces: list[TurnTrace] = []

    async def record(self, trace: TurnTrace) -> None:
        self.traces.append(trace)

    async def last(self, tenant_id: str, session_id: str) -> TurnTrace | None:
        return next(
            (t for t in reversed(self.traces) if (t.tenant_id, t.session_id) == (tenant_id, session_id)),
            None,
        )


def usage_detail(usage: Usage) -> dict[str, int]:
    return {name: value for name, value in usage.model_dump().items() if value}
