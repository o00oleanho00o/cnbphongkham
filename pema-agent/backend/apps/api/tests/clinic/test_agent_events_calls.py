"""Nothing changes a visit or the messaging consent without telling the agent (docs/PLAN-crm-plugin.md 3.4).

Read from the code, no database: the places that create or move a visit are exactly the four known ones and the
places that add a consent row are the two known ones; each calls the writer of its event. A new place that
changes a visit without that call turns this red.
"""

from __future__ import annotations

import ast
from pathlib import Path

ACTIONS = Path(__file__).resolve().parents[2] / "pema" / "clinic" / "actions"
SKIPPED = {"seed_demo.py", "agent_events.py"}  # the demo seed has no chat links: no one to tell
VISIT_FIELDS = {
    "starts_at",
    "duration_min",
}  # the time of a visit; doctor and room move with it in one action


def _functions() -> list[tuple[str, ast.AST]]:
    found: list[tuple[str, ast.AST]] = []
    for path in sorted(ACTIONS.glob("*.py")):
        if path.name in SKIPPED:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                found.append((f"{path.stem}.{node.name}", node))
    return found


def _calls(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) == name or getattr(n.func, "attr", None) == name)
        for n in ast.walk(node)
    )


def _sets_visit_field(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Attribute) and t.attr in VISIT_FIELDS for t in n.targets)
        for n in ast.walk(node)
    )


def test_every_place_that_creates_or_moves_a_visit_tells_the_agent() -> None:
    touching = {name for name, node in _functions() if _calls(node, "Appointment") or _sets_visit_field(node)}
    assert touching == {
        "appointments.book_in_session",
        "appointments.update_appointment",
        "agent_gateway.reschedule",
    }
    told = {name for name, node in _functions() if _calls(node, "record_appointment_changed")}
    assert told == touching | {"appointments.transition"}


def test_every_place_that_adds_a_consent_row_tells_the_agent() -> None:
    adding = {name for name, node in _functions() if _calls(node, "Consent")}
    assert adding == {"consents.record_consent", "agent_gateway.save_contact"}
    told = {name for name, node in _functions() if _calls(node, "record_person_changed")}
    assert told == adding
