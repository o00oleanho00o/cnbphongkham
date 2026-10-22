"""Cases: goals the agent works on across many wake-ups (the loop outside a turn). Shape and rules only; the
engine that runs them lives in the application, the cases themselves in plugins."""

from __future__ import annotations

from agentcore.cases.rules import (
    CASE_MARK,
    Block,
    CaseRecord,
    apply,
    blocked,
    new_record,
    state_of,
    turn_text,
)
from agentcore.cases.spec import (
    LIVE,
    Budget,
    CaseSpec,
    CaseStatus,
    CodeNode,
    Decision,
    Edge,
    Graph,
    Node,
    StopRules,
    Trigger,
    TurnNode,
    WaitFor,
)
from agentcore.cases.tools import DecisionSink, make_case_tools

__all__ = [
    "CASE_MARK",
    "LIVE",
    "Block",
    "Budget",
    "CaseRecord",
    "CaseSpec",
    "CaseStatus",
    "CodeNode",
    "Decision",
    "DecisionSink",
    "Edge",
    "Graph",
    "Node",
    "StopRules",
    "Trigger",
    "TurnNode",
    "WaitFor",
    "apply",
    "blocked",
    "make_case_tools",
    "new_record",
    "state_of",
    "turn_text",
]
