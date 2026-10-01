# ported from: src/scheduler/scheduled-job-conclude.ts
"""The COMMON conclusion of one run of a job: the invariant "never sent means never counted as run" (Finding
1) and the mechanism of retrying at most ``MAX_DELIVERY_ATTEMPTS`` times when sending fails. The part "really
send + guard before sending" is in ``scheduled_job_send`` (big enough to split, to keep this file small) - the
2 files operate on the same ``job_runs`` / ``jobs`` rows, they differ only in WHERE they are called (before
anything was really sent, or after an attempt to send).

Forced deviation: each conclusion is ONE transaction (``finish_run`` + ``mark_run`` +
``reset_delivery_attempts``
were three separate statements in the original, interruptible between two of them; a crash between them left a
closed run on a job that was never marked, or the reverse).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.job_run_log_store import FinishRunParams
from pema_contracts.scheduler import MAX_DELIVERY_ATTEMPTS, JobRunStatus, ScheduledJob, ScheduleKind


async def conclude_blocked_not_run(
    deps: SchedulerDeps,
    job: ScheduledJob,
    run_id: int,
    reason: str,
    scheduled_for: str,
    turn_id: int | None = None,
) -> None:
    """The job was NOT sent for a reason OUTSIDE its own will (account dropped its session, thread switched
    off) - the job NEVER REALLY RAN so it must NOT be ``mark_run``. A ``once`` job also needs ``next_run_at``
    restored to EXACTLY the old ``scheduled_for`` (retry at the very next tick - unlike the DAILY CAP reason,
    see ``scheduled_job_cap_guard``). Resets ``delivery_attempts``: this run did NOT end because of a failed
    send."""
    async with deps.db.session(job.clinic_id) as s:
        if job.schedule_kind is ScheduleKind.ONCE:
            await deps.jobs.set_next_run(job.clinic_id, job.id, scheduled_for, session=s)
        await deps.runs.finish_run(
            job.clinic_id,
            run_id,
            FinishRunParams(status=JobRunStatus.SKIPPED, detail=reason, turn_id=turn_id),
            session=s,
        )
        await deps.attempts.reset_delivery_attempts(job.clinic_id, job.id, session=s)


async def conclude_in(
    deps: SchedulerDeps, session: AsyncSession, job: ScheduledJob, run_id: int, params: FinishRunParams
) -> None:
    """``conclude`` inside an already open transaction."""
    await deps.runs.finish_run(job.clinic_id, run_id, params, session=session)
    await deps.jobs.mark_run(
        job.clinic_id,
        job.id,
        params.status,
        (params.detail or "Lỗi không rõ nguyên nhân.") if params.status is JobRunStatus.ERROR else None,
        session=session,
    )
    await deps.attempts.reset_delivery_attempts(job.clinic_id, job.id, session=session)


async def conclude(deps: SchedulerDeps, job: ScheduledJob, run_id: int, params: FinishRunParams) -> None:
    """Close BOTH places: the run ledger (``job_runs``) and the summary on the job. Resets
    ``delivery_attempts``: this run REALLY ended, it cuts the chain of consecutive failed sends - it does not
    accumulate across the successful/silent runs in between (Item 4, round 3)."""
    async with deps.db.session(job.clinic_id) as s:
        await conclude_in(deps, s, job, run_id, params)


async def conclude_delivery_failed(
    deps: SchedulerDeps,
    job: ScheduledJob,
    run_id: int,
    scheduled_for: str,
    message: str,
    turn_id: int | None = None,
) -> None:
    """Could NOT send ANYTHING (network down, the agent turn threw halfway, or an unexpected error at the
    outermost layer of ``run_scheduled_job``) - the invariant "never sent means never counted as run" (Finding
    1). Counted into ``delivery_attempts`` instead of ``mark_run`` at once: one dropped connection must not
    kill the job, but it must not be retried FOREVER either. Only reaching ``MAX_DELIVERY_ATTEMPTS`` really
    spends the run slot."""
    async with deps.db.session(job.clinic_id) as s:
        attempts = await deps.attempts.increment_delivery_attempts(job.clinic_id, job.id, session=s)

        if attempts < MAX_DELIVERY_ATTEMPTS:
            # 'once' has no natural next slot - restore to ``scheduled_for`` so the next tick retries AT ONCE.
            # every/cron already have the next slot on their own rhythm - do not touch it.
            if job.schedule_kind is ScheduleKind.ONCE:
                await deps.jobs.set_next_run(job.clinic_id, job.id, scheduled_for, session=s)
            await deps.runs.finish_run(
                job.clinic_id,
                run_id,
                FinishRunParams(
                    status=JobRunStatus.ERROR,
                    detail=f"{message} (thử lại lần {attempts}/{MAX_DELIVERY_ATTEMPTS})",
                    turn_id=turn_id,
                ),
                session=s,
            )
            return

        await conclude_in(
            deps,
            s,
            job,
            run_id,
            FinishRunParams(
                status=JobRunStatus.ERROR,
                turn_id=turn_id,
                detail=f"{message} (đã thử {MAX_DELIVERY_ATTEMPTS} lần liên tiếp, dừng)",
            ),
        )
