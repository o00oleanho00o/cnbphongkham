"""``SchedulerPort`` over Postgres (new module, no zalo-agent source).

The seam B2 (CRM rules), D4 (``schedule_task``) and the admin API push jobs through, without editing any code
of package S. It composes the ported stores; every method sets the clinic context itself from ``clinic_id``
(the stores open ``db.session(clinic_id)``), so callers never manage RLS.

``create_job`` is where ``PolicyHooks.check_job`` is called at creation (CONTRACTS section 3): a ``deny`` is
raised as ``DomainError(POLICY_DENIED)``; a ``downgrade_to_draft`` is accepted (the job is stored and is
re-decided at every run, so the policy of the moment of the run is the one that counts). The ``once`` /
``max_runs`` invariant and ``dedupe_key`` idempotency live in ``ScheduledJobStore.create_job``.

``run_trial`` goes through the real pipeline: see the note of ``run_scheduled_job_trial``. It really runs the
job but never moves the real schedule, which under ``patient_channel`` can only end in a review draft (the
contract docstring and the route summary say so)."""

from __future__ import annotations

from uuid import UUID

from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.run_context import decide_job, resolve_policy_context
from pema.scheduler.run_scheduled_job_trial import run_scheduled_job_trial
from pema.scheduler.scheduled_job_store import UpdateScheduledJobInput
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.policy import JobAction
from pema_contracts.scheduler import CreateScheduledJobInput, JobRunRecord, ParsedSchedule, ScheduledJob


class PgSchedulerStore:
    def __init__(self, deps: SchedulerDeps) -> None:
        self._deps = deps

    async def create_job(self, job: CreateScheduledJobInput) -> ScheduledJob:
        deps = self._deps
        account = await deps.accounts.get_account(job.clinic_id, job.account_id)
        if account is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy tài khoản của lịch hẹn.")
        ctx = await resolve_policy_context(deps, _preview(job), account, isolated=False)
        decision = await decide_job(deps, ctx, job)
        if decision.action is JobAction.DENY:
            raise DomainError(
                ErrorCode.POLICY_DENIED, decision.reason or "Chính sách không cho phép tạo lịch hẹn này."
            )
        return await deps.jobs.create_job(job)

    async def get_job(
        self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str
    ) -> ScheduledJob | None:
        return await self._deps.jobs.get_job(clinic_id, account_id, thread_id, job_id)

    async def update_job(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        job_id: str,
        *,
        name: str | None = None,
        payload: str | None = None,
        schedule: ParsedSchedule | None = None,
    ) -> ScheduledJob | None:
        """``JobUpdater``: the partial update of the ``schedule_task`` tool. The policy of the moment is
        applied at every RUN (``run_scheduled_job`` decides again), so an edit cannot widen what a job
        may do."""
        patch = UpdateScheduledJobInput(name=name, payload=payload, schedule=schedule)
        if not await self._deps.jobs.update_job(clinic_id, account_id, thread_id, job_id, patch):
            return None
        return await self._deps.jobs.get_job(clinic_id, account_id, thread_id, job_id)

    async def get_job_unscoped(self, clinic_id: UUID, job_id: str) -> ScheduledJob | None:
        return await self._deps.jobs.get_job_unscoped(clinic_id, job_id)

    async def list_jobs_for_thread(
        self, clinic_id: UUID, account_id: str, thread_id: str
    ) -> list[ScheduledJob]:
        return await self._deps.jobs.list_jobs_for_thread(clinic_id, account_id, thread_id)

    async def list_jobs(self, clinic_id: UUID, account_id: str | None = None) -> list[ScheduledJob]:
        return await self._deps.job_list.list_jobs_for_account(clinic_id, account_id)

    async def get_job_by_dedupe_key(self, clinic_id: UUID, dedupe_key: str) -> ScheduledJob | None:
        return await self._deps.jobs.get_job_by_dedupe_key(clinic_id, dedupe_key)

    async def set_enabled_by_dedupe_key(self, clinic_id: UUID, dedupe_key: str, enabled: bool) -> bool:
        return await self._deps.jobs.set_enabled_by_dedupe_key(clinic_id, dedupe_key, enabled)

    async def set_enabled(
        self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str, enabled: bool
    ) -> bool:
        return await self._deps.jobs.set_enabled(clinic_id, account_id, thread_id, job_id, enabled)

    async def delete_job(self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str) -> bool:
        return await self._deps.jobs.delete_job(clinic_id, account_id, thread_id, job_id)

    async def list_runs(self, clinic_id: UUID, job_id: str, limit: int = 20) -> list[JobRunRecord]:
        return await self._deps.runs.list_runs(clinic_id, job_id, limit)

    async def run_trial(self, clinic_id: UUID, job_id: str) -> JobRunRecord:
        job = await self._deps.jobs.get_job_unscoped(clinic_id, job_id)
        if job is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy lịch hẹn.")
        record = await run_scheduled_job_trial(self._deps, job)
        if record is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy lịch hẹn.")
        return record


def _preview(job: CreateScheduledJobInput) -> ScheduledJob:
    """A not-yet-stored ``ScheduledJob`` carrying the fields the policy context reads (ids and patient)."""
    return ScheduledJob(
        id="",
        clinic_id=job.clinic_id,
        account_id=job.account_id,
        thread_id=job.thread_id,
        thread_type=job.thread_type,
        name=job.name,
        kind=job.kind,
        payload=job.payload,
        schedule_kind=job.schedule.kind,
        created_by=job.created_by,
        patient_id=job.patient_id,
        origin=job.origin,
    )
