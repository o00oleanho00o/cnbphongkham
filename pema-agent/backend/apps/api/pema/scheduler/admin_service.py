# ported from: src/server/routes/schedule-routes.ts
"""The logic behind ``/admin/schedules`` (the "Schedules" page of the dashboard): view / create / edit /
delete / trial-run a scheduled job without going through chat. The routes
(``pema.api.routers.admin_schedules``) stay thin and call this service.

The writes go through EXACTLY the store the ``schedule_task`` tool uses, so they carry the SAME constraints
(cap of jobs per thread, schedule density threshold) - there is no separate rule for "a job created from the
web".

Forced deviation from the original IDOR rule: the original addressed an existing job by ``(accountId,
threadId, id)`` taken from the request, because its only admin was ONE shared dashboard password. Here the
OpenAPI contract addresses a job by ``job_id`` alone and the caller is a signed-in staff member of ONE clinic:
the clinic is the isolation boundary (RLS on ``clinic_id`` plus the explicit ``clinic_id`` predicate of every
query), so a job of ANOTHER clinic is simply not found. Inside a clinic every staff member with the schedules
permission may see every thread's jobs (the list already shows them all); the permission itself is checked by
package B1's dependency in the router.

Validation errors keep the original wording; the HTTP statuses follow ``ErrorCode``: 422 for a rejected input
(``VALIDATION_FAILED`` / ``INVALID_SCHEDULE``), 404 for a missing job, 409 for a run already in progress."""

from __future__ import annotations

from uuid import UUID

from pema.config.runtime_tuning_settings import bot_time_zone, get_tuning_int
from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.schedule_parser import ParseScheduleError, ParseScheduleParams, parse_schedule
from pema.scheduler.scheduled_job_store import UpdateScheduledJobInput
from pema.scheduler.scheduled_job_thread_cap import check_thread_job_cap
from pema.scheduler.store import PgSchedulerStore
from pema.shared.logger import create_logger
from pema_contracts.admin_agent import ScheduleCreate, ScheduleUpdate
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.scheduler import (
    CreateScheduledJobInput,
    JobOrigin,
    JobRunRecord,
    ParsedSchedule,
    ScheduledJob,
    ScheduleInput,
)

log = create_logger("schedule-routes")

DEFAULT_RUNS_LIMIT = 50
MAX_RUNS_LIMIT = 200


class ScheduleAdminService:
    def __init__(self, deps: SchedulerDeps, store: PgSchedulerStore | None = None) -> None:
        self._deps = deps
        self._store = store if store is not None else PgSchedulerStore(deps)

    def _parse(self, schedule_input: ScheduleInput, time_zone: str) -> ParsedSchedule:
        """``parse_schedule`` parameters shared by create/update - the same configuration the tool uses."""
        result = parse_schedule(
            schedule_input,
            ParseScheduleParams(
                time_zone=time_zone or bot_time_zone(),
                min_interval_minutes=get_tuning_int("SCHEDULER_MIN_INTERVAL_MINUTES"),
            ),
        )
        if isinstance(result, ParseScheduleError):
            raise DomainError(ErrorCode.INVALID_SCHEDULE, result.error)
        return result.schedule

    async def _require_job(self, clinic_id: UUID, job_id: str) -> ScheduledJob:
        job = await self._deps.jobs.get_job_unscoped(clinic_id, job_id)
        if job is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy lịch hẹn")
        return job

    async def list_jobs(self, clinic_id: UUID, account_id: str | None) -> list[ScheduledJob]:
        return await self._store.list_jobs(clinic_id, account_id or None)

    async def create(self, clinic_id: UUID, body: ScheduleCreate, actor: str) -> ScheduledJob:
        deps = self._deps
        account = await deps.accounts.get_account(clinic_id, body.account_id)
        if account is None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Account không tồn tại")
        # There is NO branch blocking the bot channel here: the scheduler builds its send path from the
        # CHANNEL (``scheduled_job_reply_target``) so both kinds of account share one path.
        if await deps.threads.find_thread_status(clinic_id, body.account_id, body.thread_id) is None:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                "Cuộc trò chuyện chưa từng ghi nhận trong hệ thống - không tạo lịch được.",
            )

        cap = await check_thread_job_cap(deps.jobs, clinic_id, body.account_id, body.thread_id)
        if not cap.ok:
            raise DomainError(ErrorCode.VALIDATION_FAILED, cap.reason)

        schedule = self._parse(body.schedule, body.timezone)
        job = await self._store.create_job(
            CreateScheduledJobInput(
                clinic_id=clinic_id,
                account_id=body.account_id,
                thread_id=body.thread_id,
                thread_type=body.thread_type,
                name=body.name,
                kind=body.kind,
                payload=body.payload,
                schedule=schedule,
                timezone=body.timezone,
                max_runs=body.max_runs,
                created_by=actor,
                origin=JobOrigin.STAFF,
            )
        )
        log.info("Tạo lịch hẹn từ dashboard", job_id=job.id, account_id=job.account_id)
        return job

    async def update(self, clinic_id: UUID, job_id: str, body: ScheduleUpdate) -> ScheduledJob:
        deps = self._deps
        job = await self._require_job(clinic_id, job_id)

        # Re-enabling a job that is off must pass through the SAME cap as creating a new one - without this
        # step: create 20 jobs, switch off 10, create 10 more, switch them all back on = 30 enabled jobs,
        # above the cap (the create route checked, the enable/disable route used not to).
        if body.enabled is True and not job.enabled:
            cap = await check_thread_job_cap(deps.jobs, clinic_id, job.account_id, job.thread_id)
            if not cap.ok:
                raise DomainError(ErrorCode.VALIDATION_FAILED, cap.reason)

        schedule: ParsedSchedule | None = None
        if body.schedule is not None:
            schedule = self._parse(
                body.schedule, body.timezone if body.timezone is not None else job.timezone
            )

        if (
            body.name is not None
            or body.payload is not None
            or schedule is not None
            or body.timezone is not None
            or body.max_runs is not None
        ):
            await deps.jobs.update_job(
                clinic_id,
                job.account_id,
                job.thread_id,
                job.id,
                UpdateScheduledJobInput(
                    name=body.name,
                    payload=body.payload,
                    schedule=schedule,
                    timezone=body.timezone,
                    max_runs=body.max_runs,
                ),
            )
        if body.enabled is not None:
            await deps.jobs.set_enabled(clinic_id, job.account_id, job.thread_id, job.id, body.enabled)

        return await self._require_job(clinic_id, job_id)

    async def delete(self, clinic_id: UUID, job_id: str) -> None:
        job = await self._require_job(clinic_id, job_id)
        if not await self._store.delete_job(clinic_id, job.account_id, job.thread_id, job.id):
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy lịch hẹn")

    async def run_trial(self, clinic_id: UUID, job_id: str) -> JobRunRecord:
        """ "Run now" - really sends, through EXACTLY the guard/daily cap, but does not move the real schedule
        (``next_run_at``, ``run_count``, ``enabled``...) - see ``run_scheduled_job_trial``."""
        job = await self._require_job(clinic_id, job_id)
        # Block BEFORE the trial gets to snapshot/claim the job: if this job still has a 'running' run (a REAL
        # tick still dispatching, or another "Run now" in progress), the trial's claim cannot close the window
        # with a run that started earlier - see the header of ``run_scheduled_job_trial``.
        if await self._deps.runs.has_running_run(clinic_id, job.id):
            raise DomainError(ErrorCode.INVALID_STATE, "Lịch hẹn đang chạy, thử lại sau ít phút.")
        record = await self._store.run_trial(clinic_id, job.id)
        log.info("Chạy thử lịch hẹn từ dashboard", job_id=job.id, status=record.status.value)
        return record

    async def list_runs(self, clinic_id: UUID, job_id: str, limit: int | None = None) -> list[JobRunRecord]:
        job = await self._require_job(clinic_id, job_id)
        # ``|| DEFAULT`` of the original (trace-routes pattern): a broken/empty value falls to the default.
        effective = min(MAX_RUNS_LIMIT, max(1, limit or DEFAULT_RUNS_LIMIT))
        return await self._deps.runs.list_runs(clinic_id, job.id, effective)
