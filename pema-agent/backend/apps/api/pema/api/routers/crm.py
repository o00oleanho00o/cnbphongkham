"""CRM tasks and activities (B1 routes; B2 rules/scheduler create the tasks)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, IdempotencyKey, Limit, Offset, cookie_scheme
from pema.clinic.actions import crm_overview, crm_tasks
from pema_contracts.common import Page
from pema_contracts.crm import (
    CrmActivityCreate,
    CrmActivityOut,
    CrmRuleOut,
    CrmSegmentKey,
    CrmSegmentPatientOut,
    CrmSegmentsOut,
    CrmTaskOut,
    CrmTaskResolve,
    RuleKey,
    TaskStatus,
)

router = APIRouter(
    tags=["crm"],
    responses=ERROR_RESPONSES,
    dependencies=[Security(cookie_scheme)],
)


@router.get(
    "/crm/tasks",
    response_model=Page[CrmTaskOut],
    summary="Task queue ('Viec hom nay' = due_by today, status open)",
)
async def list_tasks(
    db: Database,
    ctx: Ctx,
    task_status: TaskStatus | None = None,
    rule_key: RuleKey | None = None,
    owner_user_id: UUID | None = None,
    patient_id: UUID | None = None,
    due_by: date | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[CrmTaskOut]:
    return await crm_tasks.list_tasks(
        db,
        ctx,
        status=task_status,
        rule_key=rule_key,
        owner_user_id=owner_user_id,
        patient_id=patient_id,
        due_by=due_by,
        limit=limit,
        offset=offset,
    )


@router.get("/crm/tasks/{task_id}", response_model=CrmTaskOut, summary="One task")
async def get_task(task_id: UUID, db: Database, ctx: Ctx) -> CrmTaskOut:
    return await crm_tasks.get_task(db, ctx, task_id)


@router.post(
    "/crm/tasks/{task_id}/resolve",
    response_model=CrmTaskOut,
    summary="Log a contact attempt and close or reschedule the task",
)
async def resolve_task(
    task_id: UUID,
    body: CrmTaskResolve,
    db: Database,
    ctx: Ctx,
    idempotency_key: IdempotencyKey = None,
) -> CrmTaskOut:
    # ``ctx`` already carries the Idempotency-Key header; the parameter stays so OpenAPI documents it.
    return await crm_tasks.resolve_task(db, ctx, task_id, body)


@router.get("/crm/activities", response_model=Page[CrmActivityOut], summary="Contact log")
async def list_activities(
    db: Database,
    ctx: Ctx,
    patient_id: UUID | None = None,
    task_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[CrmActivityOut]:
    return await crm_tasks.list_activities(
        db, ctx, patient_id=patient_id, task_id=task_id, limit=limit, offset=offset
    )


@router.post(
    "/crm/activities",
    response_model=CrmActivityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an internal note or contact log",
)
async def create_activity(body: CrmActivityCreate, db: Database, ctx: Ctx) -> CrmActivityOut:
    return await crm_tasks.create_activity(db, ctx, body)


@router.get(
    "/crm/segments",
    response_model=CrmSegmentsOut,
    summary="Customer groups: lifecycle stages and at-risk, with counts",
)
async def get_segments(db: Database, ctx: Ctx) -> CrmSegmentsOut:
    return await crm_overview.segments(db, ctx)


@router.get(
    "/crm/segments/{segment}/patients",
    response_model=Page[CrmSegmentPatientOut],
    summary="Patients of one group, most overdue first",
)
async def list_segment_patients(
    segment: CrmSegmentKey, db: Database, ctx: Ctx, limit: Limit = 50, offset: Offset = 0
) -> Page[CrmSegmentPatientOut]:
    return await crm_overview.segment_patients(db, ctx, segment, limit=limit, offset=offset)


@router.get(
    "/crm/rules",
    response_model=list[CrmRuleOut],
    summary="The automation rules, read only (tuning is /admin/rules)",
)
async def list_crm_rules(db: Database, ctx: Ctx) -> list[CrmRuleOut]:
    return await crm_overview.list_rules(db, ctx)
