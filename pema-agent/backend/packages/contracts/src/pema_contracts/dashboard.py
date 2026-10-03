"""Dashboard (KPI) DTOs. New module: the numbers of the old Clinic Web "Tong quan" (``crm-ui.js``
``dashboard()``) that can be computed from rows the database really holds.

What is NOT here on purpose: revenue and any money figure (no finance data until package U6), the
"customers at risk" and lifecycle-stage counts (derived profiles of the CRM engine, not stored). A KPI the
backend cannot compute from rows is left out; the page never invents one.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field

from pema_contracts.common import ApiModel


class DashboardRange(StrEnum):
    TODAY = "today"
    WEEK = "week"
    """Monday to Sunday of the current week (clinic time)."""
    MONTH = "month"
    """First to last day of the current month (clinic time)."""


class DashboardScope(StrEnum):
    CLINIC = "clinic"
    DOCTOR = "doctor"
    """A doctor sees only their own appointments and the care tasks of their own patients."""


class AppointmentKpis(ApiModel):
    """Appointments whose start falls in the range, counted by their status now."""

    total: int = Field(ge=0)
    upcoming: int = Field(ge=0, description="booked + confirmed: not arrived yet.")
    waiting: int = Field(ge=0, description="arrived: in the waiting room.")
    in_progress: int = Field(ge=0)
    completed: int = Field(ge=0)
    missed: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    visits: int = Field(ge=0, description="Came to the clinic: arrived + in_progress + completed.")


class PatientKpis(ApiModel):
    """``seen`` = distinct patients with a visit in the range; ``new`` of them had their first contact in the
    range (``patient.first_contact_at``), ``returning`` is the rest."""

    seen: int = Field(ge=0)
    new: int = Field(ge=0)
    returning: int = Field(ge=0)


class CareKpis(ApiModel):
    """CSKH numbers (need ``crm.task.read``). Rates are whole percents, ``None`` when there is nothing to
    divide by (never a made-up 0%)."""

    tasks_due: int = Field(ge=0, description="Tasks whose due day is in the range.")
    tasks_resolved: int = Field(ge=0, description="Of those, resolved.")
    followup_completion_pct: int | None = None
    overdue_tasks: int = Field(ge=0, description="Open or rescheduled, due before today.")
    overdue_patients: int = Field(ge=0, description="Distinct patients of those tasks.")
    contact_attempts: int = Field(ge=0, description="Logged contacts in the range, internal notes excluded.")
    contacts_reached: int = Field(ge=0, description="Of those, not unanswered or invalid.")
    contact_rate_pct: int | None = None
    booked_after_care: int = Field(ge=0, description="Contacts in the range that ended in an appointment.")


class DashboardKpisOut(ApiModel):
    range: DashboardRange
    scope: DashboardScope
    starts_on: date
    ends_on: date = Field(description="Inclusive.")
    appointments: AppointmentKpis | None = Field(
        default=None, description="Null when the caller lacks ``appointment.read``."
    )
    patients: PatientKpis | None = Field(default=None, description="Null with ``appointments``.")
    care: CareKpis | None = Field(default=None, description="Null when the caller lacks ``crm.task.read``.")
