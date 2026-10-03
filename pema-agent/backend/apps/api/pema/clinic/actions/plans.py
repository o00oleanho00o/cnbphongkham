# ported from: prototype/shared/clinic.js (``plan``, ``modalHtml('plan-edit')``, ``save-plan``)
"""Treatment plans of the Kế hoạch tab: list, create, edit (actions behind ``routers/patient_care.py``).

Forced deviation: the prototype kept one plan per patient in ``localStorage`` (``p.plan``, ``p.total``,
``p.completed``) and edited its name and total in a modal. Here a plan is a ``clinic.treatment_plan`` row
(a patient may have several); the counter ``completed_sessions`` is moved only by
``sessions.complete_session``.

Rules: ``session.write`` (doctor, owner) to create or edit, narrowed to the doctor's own patients; reading the
plans is part of the Patient 360 read model (``patient.read_360``). The old edit form refused a total
below the sessions already done (``min`` of ``plan-total``); the BE enforces it. Audit details carry ids and
the NAMES of changed fields, never the title or the goal.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from pema.clinic import audit
from pema.clinic.actions._care_mappers import plan_out
from pema.clinic.actions._clinical_scope import CLINICIAN_ROLES
from pema.clinic.actions._common import check_version, lost_race_is_conflict, not_found
from pema.clinic.actions._scope import require_patient_access
from pema.clinic.actions.patients import load_patient
from pema.clinic.models import Episode, TreatmentPlan
from pema.clinic.rbac import is_role, require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.patient_care import PlanCreate, PlanStatus, PlanUpdate
from pema_contracts.patients import TreatmentPlanOut
from pema_contracts.roles import Permission

TOTAL_BELOW_DONE_MESSAGE = "Tổng số buổi không được thấp hơn số buổi đã hoàn tất."


async def list_plans(db: ClinicDatabase, ctx: ActionContext, patient_id: UUID) -> list[TreatmentPlanOut]:
    require(ctx, Permission.PATIENT_READ_360)
    async with db.session() as session:
        await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        rows = (
            await session.scalars(
                select(TreatmentPlan)
                .where(TreatmentPlan.clinic_id == ctx.clinic_id, TreatmentPlan.patient_id == patient_id)
                .order_by(TreatmentPlan.created_at.desc(), TreatmentPlan.id)
            )
        ).all()
        return [plan_out(row) for row in rows]


async def create_plan(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, payload: PlanCreate
) -> TreatmentPlanOut:
    require(ctx, Permission.SESSION_WRITE)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        if payload.episode_id is not None:
            episode = await session.scalar(
                select(Episode.id).where(
                    Episode.clinic_id == ctx.clinic_id,
                    Episode.id == payload.episode_id,
                    Episode.patient_id == patient_id,
                )
            )
            if episode is None:
                raise DomainError(ErrorCode.VALIDATION_FAILED, "Đợt điều trị không thuộc người bệnh này.")
        clinician = is_role(ctx, *CLINICIAN_ROLES)
        row = TreatmentPlan(
            clinic_id=ctx.clinic_id,
            patient_id=patient_id,
            episode_id=payload.episode_id,
            doctor_id=ctx.actor_user_id if clinician else patient.doctor_id,
            service_code=payload.service_code,
            title=payload.title,
            goal=payload.goal,
            total_sessions=payload.total_sessions,
            completed_sessions=0,
            status=PlanStatus.ACTIVE.value,
        )
        session.add(row)
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "plan.create",
            "treatment_plan",
            row.id,
            {
                "patient_id": str(patient_id),
                "service_code": row.service_code,
                "total_sessions": row.total_sessions,
            },
        )
        return plan_out(row)


async def update_plan(
    db: ClinicDatabase, ctx: ActionContext, plan_id: UUID, payload: PlanUpdate
) -> TreatmentPlanOut:
    require(ctx, Permission.SESSION_WRITE)
    async with db.session() as session:
        row = await session.scalar(
            select(TreatmentPlan).where(TreatmentPlan.clinic_id == ctx.clinic_id, TreatmentPlan.id == plan_id)
        )
        if row is None:
            raise not_found("kế hoạch")
        await require_patient_access(session, ctx, row.patient_id)
        check_version(row.version, payload.version)
        sent = payload.model_fields_set
        changed: list[str] = []
        if "title" in sent and payload.title is not None:
            row.title = payload.title
            changed.append("title")
        if "goal" in sent:
            row.goal = payload.goal
            changed.append("goal")
        if "total_sessions" in sent and payload.total_sessions is not None:
            if payload.total_sessions < row.completed_sessions:
                raise DomainError(ErrorCode.VALIDATION_FAILED, TOTAL_BELOW_DONE_MESSAGE)
            row.total_sessions = payload.total_sessions
            changed.append("total_sessions")
        if "status" in sent and payload.status is not None:
            row.status = payload.status.value
            changed.append("status")
        elif "total_sessions" in changed:
            # the plan follows its counter: all sessions done closes it, raising the total opens it again
            if row.completed_sessions >= row.total_sessions and row.status in ("planned", "active"):
                row.status = PlanStatus.COMPLETED.value
                changed.append("status")
            elif row.completed_sessions < row.total_sessions and row.status == PlanStatus.COMPLETED.value:
                row.status = PlanStatus.ACTIVE.value
                changed.append("status")
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "plan.update",
            "treatment_plan",
            row.id,
            {"patient_id": str(row.patient_id), "changed_fields": changed},
        )
        return plan_out(row)
