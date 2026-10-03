# ported from: prototype/shared/crm-ui.js (dashboard, doctorHome) and crm-automation.js (metrics)
"""Dashboard KPIs: the numbers of the old "Tong quan" that the database can really answer.

Forced deviations from the JS prototype (which computed everything from ``localStorage`` in the browser):

* one read model per call, aggregated in SQL (a count per status, a distinct count of patients), not a
  per-row loop in the page;
* a ``range`` (today, this week, this month) instead of the fixed demo day;
* NOT ported because the data is not stored: money (``revenue`` "Phat sinh hom nay" needs invoices, package
  U6) and the derived CRM profile counts (``atRisk``, ``abandoned``, ``stages``: the rule engine computes
  them per run, they are not rows). The page shows what is here and nothing else, never a made-up number.

Authorization: ``appointment.read`` fills ``appointments`` and ``patients``; ``crm.task.read`` fills ``care``;
a caller with neither is refused. A doctor sees their own appointments only and, for care, the D+7 tasks and
the contacts of their own patients (the same narrowing as ``crm_tasks``), like ``doctorHome`` of the JS.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic.actions._common import now
from pema.clinic.actions._scope import patient_scope
from pema.clinic.actions.crm_tasks import OPEN_STATUSES, doctor_task_condition
from pema.clinic.models import Appointment, CrmActivity, CrmTask, Patient
from pema.clinic.rbac import has_permission, is_doctor_scoped, require_any
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.appointments import AppointmentStatus
from pema_contracts.common import VN_TZ
from pema_contracts.crm import CrmChannel, CrmOutcome, TaskStatus
from pema_contracts.dashboard import (
    AppointmentKpis,
    CareKpis,
    DashboardKpisOut,
    DashboardRange,
    DashboardScope,
    PatientKpis,
)
from pema_contracts.roles import Permission

_VISIT_STATUSES = (
    AppointmentStatus.ARRIVED.value,
    AppointmentStatus.IN_PROGRESS.value,
    AppointmentStatus.COMPLETED.value,
)
_NOT_REACHED = (CrmOutcome.UNANSWERED.value, CrmOutcome.INVALID.value)
_DUE_STATUSES = (*OPEN_STATUSES, TaskStatus.RESOLVED.value)


def range_days(range_: DashboardRange, today: date) -> tuple[date, date]:
    """First and last day (inclusive, clinic time). The week runs Monday to Sunday."""
    if range_ is DashboardRange.TODAY:
        return today, today
    if range_ is DashboardRange.WEEK:
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=6)
    first = today.replace(day=1)
    following = (first + timedelta(days=32)).replace(day=1)
    return first, following - timedelta(days=1)


def percent(part: int, whole: int) -> int | None:
    """Whole percent, half rounded up (JS ``Math.round``); ``None`` when there is nothing to divide by."""
    if whole <= 0:
        return None
    return (part * 200 + whole) // (2 * whole)


def _start_of(day: date) -> datetime:
    return datetime.combine(day, time(0, 0), tzinfo=VN_TZ)


async def _appointment_kpis(
    session: AsyncSession, ctx: ActionContext, first: date, last: date
) -> tuple[AppointmentKpis, PatientKpis]:
    conditions = [
        Appointment.clinic_id == ctx.clinic_id,
        Appointment.starts_at >= _start_of(first),
        Appointment.starts_at < _start_of(last + timedelta(days=1)),
    ]
    if is_doctor_scoped(ctx):
        conditions.append(Appointment.doctor_id == ctx.actor_user_id)
    rows = await session.execute(
        select(Appointment.status, func.count()).where(*conditions).group_by(Appointment.status)
    )
    by_status = dict(rows.all())

    def count(*statuses: AppointmentStatus) -> int:
        return sum(by_status.get(s.value, 0) for s in statuses)

    appointments = AppointmentKpis(
        total=sum(by_status.values()),
        upcoming=count(AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED),
        waiting=count(AppointmentStatus.ARRIVED),
        in_progress=count(AppointmentStatus.IN_PROGRESS),
        completed=count(AppointmentStatus.COMPLETED),
        missed=count(AppointmentStatus.MISSED),
        cancelled=count(AppointmentStatus.CANCELLED),
        visits=count(AppointmentStatus.ARRIVED, AppointmentStatus.IN_PROGRESS, AppointmentStatus.COMPLETED),
    )
    is_new = Patient.first_contact_at.between(first, last)
    seen, new = (
        await session.execute(
            select(
                func.count(distinct(Appointment.patient_id)),
                func.count(distinct(case((is_new, Appointment.patient_id)))),
            )
            .join(
                Patient, (Patient.id == Appointment.patient_id) & (Patient.clinic_id == Appointment.clinic_id)
            )
            .where(*conditions, Appointment.status.in_(_VISIT_STATUSES))
        )
    ).one()
    return appointments, PatientKpis(seen=seen, new=new, returning=seen - new)


async def _care_kpis(
    session: AsyncSession, ctx: ActionContext, first: date, last: date, today: date
) -> CareKpis:
    starts, ends = _start_of(first), _start_of(last + timedelta(days=1))
    task_scope = [CrmTask.clinic_id == ctx.clinic_id, *doctor_task_condition(ctx)]
    due_total, due_resolved = (
        await session.execute(
            select(
                func.count(),
                func.count(case((CrmTask.status == TaskStatus.RESOLVED.value, 1))),
            ).where(
                *task_scope,
                CrmTask.status.in_(_DUE_STATUSES),
                CrmTask.due_at >= starts,
                CrmTask.due_at < ends,
            )
        )
    ).one()
    overdue_tasks, overdue_patients = (
        await session.execute(
            select(func.count(), func.count(distinct(CrmTask.patient_id))).where(
                *task_scope, CrmTask.status.in_(OPEN_STATUSES), CrmTask.due_at < _start_of(today)
            )
        )
    ).one()
    activity_scope = [
        CrmActivity.clinic_id == ctx.clinic_id,
        CrmActivity.occurred_at >= starts,
        CrmActivity.occurred_at < ends,
        CrmActivity.channel != CrmChannel.INTERNAL_NOTE.value,
    ]
    scope = patient_scope(ctx)
    if scope is not None:
        activity_scope.append(
            CrmActivity.patient_id.in_(select(Patient.id).where(Patient.clinic_id == ctx.clinic_id, scope))
        )
    reached = case((CrmActivity.outcome.is_(None) | CrmActivity.outcome.notin_(_NOT_REACHED), 1))
    attempts, contacted, booked = (
        await session.execute(
            select(
                func.count(),
                func.count(reached),
                func.count(case((CrmActivity.related_appointment_id.is_not(None), 1))),
            ).where(*activity_scope)
        )
    ).one()
    return CareKpis(
        tasks_due=due_total,
        tasks_resolved=due_resolved,
        followup_completion_pct=percent(due_resolved, due_total),
        overdue_tasks=overdue_tasks,
        overdue_patients=overdue_patients,
        contact_attempts=attempts,
        contacts_reached=contacted,
        contact_rate_pct=percent(contacted, attempts),
        booked_after_care=booked,
    )


async def kpis(db: ClinicDatabase, ctx: ActionContext, *, range_: DashboardRange) -> DashboardKpisOut:
    require_any(ctx, (Permission.APPOINTMENT_READ, Permission.CRM_TASK_READ))
    today = now().astimezone(VN_TZ).date()
    first, last = range_days(range_, today)
    appointments: AppointmentKpis | None = None
    patients: PatientKpis | None = None
    care: CareKpis | None = None
    async with db.session() as session:
        if has_permission(ctx, Permission.APPOINTMENT_READ):
            appointments, patients = await _appointment_kpis(session, ctx, first, last)
        if has_permission(ctx, Permission.CRM_TASK_READ):
            care = await _care_kpis(session, ctx, first, last, today)
    return DashboardKpisOut(
        range=range_,
        scope=DashboardScope.DOCTOR if is_doctor_scoped(ctx) else DashboardScope.CLINIC,
        starts_on=first,
        ends_on=last,
        appointments=appointments,
        patients=patients,
        care=care,
    )


__all__ = ["kpis", "percent", "range_days"]
