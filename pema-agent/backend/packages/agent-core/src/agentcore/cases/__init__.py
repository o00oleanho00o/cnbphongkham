"""Cases: goals the agent works on across many wake-ups (the loop outside a turn). Shape and rules only; the
engine that runs them lives in the application, the cases themselves in plugins."""

from __future__ import annotations

from agentcore.cases.rules import (
    CASE_MARK,
    TURN_PREFIX,
    Block,
    CaseRecord,
    apply,
    blocked,
    decision_from_json,
    decision_to_json,
    new_record,
    parse_turn_message_id,
    state_of,
    turn_message_id,
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
    "TURN_PREFIX",
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
    "decision_from_json",
    "decision_to_json",
    "make_case_tools",
    "new_record",
    "parse_turn_message_id",
    "state_of",
    "turn_message_id",
    "turn_text",
]
