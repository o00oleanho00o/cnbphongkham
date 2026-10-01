"""Review item rules: who may decide what, and the state machine of a review item.

New module. Rules of PLAN-AI01 section 5 and ``pema_contracts.review``:

* in ``patient_channel`` every text for a patient lands in the queue first; a human decides, only then does
  the system send;
* red-flag items (``requires_doctor``) are decided by a clinician (owner or doctor) and are never
  auto-resolved; a CS member can neither approve nor reject them (``CSKH does not do medical review``);
* a decision is final: approved, rejected and expired items cannot be decided again. Escalated items can
  still be approved or rejected by a clinician.
"""

from __future__ import annotations

from typing import Any

from pema_contracts.review import ReviewKind, ReviewOrigin, ReviewStatus

DECIDABLE_FROM: frozenset[ReviewStatus] = frozenset({ReviewStatus.PENDING, ReviewStatus.ESCALATED})
ESCALATABLE_FROM: frozenset[ReviewStatus] = frozenset({ReviewStatus.PENDING})

APPOINTMENT_PROPOSAL = "appointment"
"""``payload['proposal']`` of a review item that proposes an appointment (see ``agent_facing``)."""


def needs_clinician(*, requires_doctor: bool, kind: ReviewKind) -> bool:
    """Items that only a clinician decides: red flags and triage alerts."""
    return requires_doctor or kind is ReviewKind.TRIAGE_ALERT


def is_proactive(origin: ReviewOrigin) -> bool:
    """A message that no recent inbound message triggered goes out as ``proactive`` (the cap, window and
    kill switch of the channel apply). A reply to a patient message (agent turn) and policy items do not."""
    return origin in {ReviewOrigin.SCHEDULED_AGENT, ReviewOrigin.CRM_RULE}


def appointment_proposal(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """The appointment proposal carried by a review item, or ``None``."""
    if payload and payload.get("proposal") == APPOINTMENT_PROPOSAL:
        return payload
    return None
