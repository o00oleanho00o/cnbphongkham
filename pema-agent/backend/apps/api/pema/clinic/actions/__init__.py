"""The action layer: authorise, filter by clinic, audit every mutation, idempotency. REST routes,
scheduler and agent tools all call these. ``agent_facing`` implements
``pema_contracts.clinic_actions.AgentFacingClinicActions``. Owner: B1.

Conventions: every public action is ``async def name(db, ctx, ...)``; ``db`` is a
``pema.core.db.ClinicDatabase`` and ``ctx`` an ``ActionContext``. Each action checks the permission FIRST
(``pema.clinic.rbac``), opens ``db.session()`` (one installation is one clinic: no RLS), and writes
its audit row in the same transaction (``pema.clinic.audit``; a structural guard rejects a commit that
changed clinic data without one).
"""

from pema.clinic.actions import (
    appointments,
    assignees,
    audit_logs,
    catalog,
    consents,
    consult_notes,
    conversations,
    crm_tasks,
    dashboard,
    finance,
    finance_cash,
    media,
    orders,
    patient_360,
    patients,
    plans,
    protocols,
    resources,
    review_items,
    services,
    sessions,
    studio,
    templates,
)
from pema.clinic.actions.agent_facing import ClinicAgentFacingActions
from pema.clinic.actions.outbound import FakeOutboundDelivery, OutboundDelivery, OutboundRequest
from pema_contracts.clinic_actions import AppointmentProposalRequest, EscalationRequest

__all__ = [
    "AppointmentProposalRequest",
    "ClinicAgentFacingActions",
    "EscalationRequest",
    "FakeOutboundDelivery",
    "OutboundDelivery",
    "OutboundRequest",
    "appointments",
    "assignees",
    "audit_logs",
    "catalog",
    "consents",
    "consult_notes",
    "conversations",
    "crm_tasks",
    "dashboard",
    "finance",
    "finance_cash",
    "media",
    "orders",
    "patient_360",
    "patients",
    "plans",
    "protocols",
    "resources",
    "review_items",
    "services",
    "sessions",
    "studio",
    "templates",
]
