"""The care turn a delegation belongs to (the data ``delegate`` and the specialist tools read).

New module (not a port). The wiring package that builds the ``ToolContext`` of a care turn puts ONE
``CareTurnScope`` in ``ToolContext.extras[CARE_TURN_EXTRA]``. Its presence is what makes a turn a care turn:
without it the ``delegate`` tool answers a marked failure, so ``delegate`` works for care agents only.

``contexts`` maps an opaque ``context_ref`` (the argument of ``delegate``) to a small STRUCTURED, PII-masked
dictionary the care loop prepared (the claimed depth, the action type, the template id and body, the sources
cited so far). The model passes a reference, never the data, so a prompt injection cannot make it hand a
specialist (or read back) a different patient's context.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from pema.care.budget import TurnBudget
from pema.care.ports import CareAgentSnapshot
from pema_contracts.common import JsonObject

CARE_TURN_EXTRA = "care_turn"


@dataclass
class CareTurnScope:
    care_agent: CareAgentSnapshot
    patient_ref: str
    """The pseudonym patient code (``P025``): never a name or a phone number."""
    budget: TurnBudget
    turn_key: str
    """Stable id of the turn (idempotency key of anything a specialist writes)."""
    contexts: Mapping[str, JsonObject] = field(default_factory=dict[str, JsonObject])
    slot_picked_by_patient: bool = False
    root_task_id: UUID | None = None
    """The ``agent.tasks`` row of the turn itself; created by the first delegation."""
