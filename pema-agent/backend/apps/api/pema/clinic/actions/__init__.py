"""The action layer: authorise, filter by clinic, audit every mutation, idempotency. REST routes call
these. Owner: B1.

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
    crm_tasks,
    dashboard,
    finance,
    finance_cash,
    media,
    orders,
    patient_360,
    patient_app,
    patient_profile,
    patients,
    plans,
    protocols,
    resources,
    services,
    sessions,
    studio,
)

__all__ = [
    "appointments",
    "assignees",
    "audit_logs",
    "catalog",
    "consents",
    "consult_notes",
    "crm_tasks",
    "dashboard",
    "finance",
    "finance_cash",
    "media",
    "orders",
    "patient_360",
    "patient_app",
    "patient_profile",
    "patients",
    "plans",
    "protocols",
    "resources",
    "services",
    "sessions",
    "studio",
]
