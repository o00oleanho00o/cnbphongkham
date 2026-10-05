# ported from: src/server/routes/schedule-routes.ts
"""Scheduled jobs: CRUD, trial run, run history (package S). Port of schedule-routes.ts.

The ``patient_channel`` profile may downgrade or deny a job (``PolicyHooks.check_job``); the response then
carries the policy error code (``policy_denied``). Every rule lives in ``pema.scheduler.admin_service``; the
bodies here only resolve the caller and call it.

WIRING (open item for package G, see the report): the clinic id and the actor of the request come from package
B1's authentication, which does not exist in this worktree. ``get_schedule_context`` is the ONE function to
replace (``app.dependency_overrides`` or an edit): by default it reads ``request.state.clinic_id`` /
``request.state.actor`` and ``request.app.state.schedule_admin``, which the composition root sets. It is not
part of the OpenAPI document (it takes the raw ``Request``), so the contract of the skeleton is unchanged."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, status

from pema.api.deps import admin_router, not_implemented
from pema.scheduler.admin_service import ScheduleAdminService
from pema_contracts.admin_agent import ScheduleCreate, ScheduleUpdate
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.scheduler import JobRunRecord, ScheduledJob

router = admin_router("schedules", "admin-schedules")


@dataclass(frozen=True)
class ScheduleContext:
    clinic_id: UUID
    actor: str
    """Who is calling (written to ``jobs.created_by``): the staff member id, never a name."""
    service: ScheduleAdminService


def get_schedule_context(request: Request) -> ScheduleContext:
    service = getattr(request.app.state, "schedule_admin", None)
    if not isinstance(service, ScheduleAdminService):
        # The composition root has not wired the scheduler yet: the route exists, the service does not, which
        # is exactly what the skeleton answered before (501), so the skeleton tests keep their meaning until
        # G wires.
        not_implemented()
    clinic_id = getattr(request.state, "clinic_id", None)
    if not isinstance(clinic_id, UUID):
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Chưa đăng nhập.")
    actor = getattr(request.state, "actor", "dashboard")
    return ScheduleContext(clinic_id=clinic_id, actor=str(actor), service=service)


Ctx = Annotated[ScheduleContext, Depends(get_schedule_context)]


@router.get("", response_model=list[ScheduledJob], summary="Jobs of the clinic (optionally one account)")
async def list_schedules(ctx: Ctx, account_id: str | None = None) -> list[ScheduledJob]:
    return await ctx.service.list_jobs(ctx.clinic_id, account_id)


@router.post("", response_model=ScheduledJob, status_code=status.HTTP_201_CREATED, summary="Create a job")
async def create_schedule(ctx: Ctx, body: ScheduleCreate) -> ScheduledJob:
    return await ctx.service.create(ctx.clinic_id, body, ctx.actor)


@router.patch("/{job_id}", response_model=ScheduledJob, summary="Update, enable or disable a job")
async def update_schedule(ctx: Ctx, job_id: str, body: ScheduleUpdate) -> ScheduledJob:
    return await ctx.service.update(ctx.clinic_id, job_id, body)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a job")
async def delete_schedule(ctx: Ctx, job_id: str) -> None:
    await ctx.service.delete(ctx.clinic_id, job_id)


@router.post(
    "/{job_id}/run",
    response_model=JobRunRecord,
    summary="Run now: same pipeline as the tick, schedule unchanged",
)
async def run_schedule_trial(ctx: Ctx, job_id: str) -> JobRunRecord:
    return await ctx.service.run_trial(ctx.clinic_id, job_id)


@router.get("/{job_id}/runs", response_model=list[JobRunRecord], summary="Run history, newest first")
async def list_schedule_runs(ctx: Ctx, job_id: str) -> list[JobRunRecord]:
    return await ctx.service.list_runs(ctx.clinic_id, job_id)
