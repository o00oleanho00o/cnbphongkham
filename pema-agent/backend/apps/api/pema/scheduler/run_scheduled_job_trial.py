# ported from: src/scheduler/run-scheduled-job-trial.ts
""" "Run now" (dashboard) - run 1 turn of a job through EXACTLY the ``run_scheduled_job`` pipeline (guard /
send / trace the same as a real turn triggered by the tick loop), but it must NOT shift the REAL SCHEDULE of
the job.

Merely avoiding ``next_run_at`` is not enough: ``mark_run()`` (``scheduled_job_store``) increments
``run_count`` THEN compares with ``max_runs`` - a 'once' job always has ``max_runs = 1`` (the invariant of
``create_job``), so ONE TRIAL run uses up the ONLY slot of the schedule and switches the job off
(``enabled = false``, ``next_run_at = NULL``) BEFORE the real schedule gets to run - exactly what the brief
forbids ("a trial must not shift the real schedule"), only heavier than the literal wording (not just
next_run_at changes, the job is also turned off). For the same reason ``delivery_attempts`` (the count of
consecutive failed sends) is also touched by the trial - mixing with the chain of REAL failed sends would make
the job reach ``MAX_DELIVERY_ATTEMPTS`` earlier than it should.

The FIRST version only snapshotted/restored WITHOUT claiming the job first - there is a real race (review
round 2): a ``kind='agent'`` job calling an LLM easily runs longer than ``SCHEDULER_TICK_MS`` (default 30 s).
If the job is OVERDUE when "Run now" is pressed, ``next_run_at`` in the DB stays at the overdue instant the
whole time the trial runs (the trial does not clear-before-dispatch like the tick) - a REAL tick in between
still sees the job "due" and dispatches for REAL once more. When the trial ends, the restore overwrote
UNCONDITIONALLY with the old snapshot, wiping the NEW next_run_at the real tick just computed - the next tick
picks up the old instant (already overdue) and SENDS A DUPLICATE real message to the end user.

The fix: CLAIM the job before dispatch, the same clear-before-dispatch as ``scheduler_loop`` - set
``next_run_at = NULL`` right before calling ``run_scheduled_job``. ``list_due_jobs`` filters
``next_run_at IS NOT NULL`` so the claim closes the collision window with FUTURE ticks.

BUT the claim does NOT close the window with a run ALREADY dispatched BEFORE pressing the trial (found at the
whole-branch review, after the paragraph above wrongly said "closes completely"): the admin route refuses with
409 as soon as ``job_runs`` still has a ``running`` row of the job (``has_running_run``).

Forced deviation (several workers): the claim is a compare-and-swap on ``next_run_at`` (the value of the
snapshot), in the SAME transaction that opens the run, so a tick of another worker that took the occurrence
between the snapshot and the claim makes the trial refuse (``INVALID_STATE``) instead of restoring a stale
snapshot over it. The restore is unconditional like the original (the narrow window left, an edit of the
schedule made in another tab exactly while the trial runs, is the one the original also documented).

Not put in ``scheduled_job_store`` so the store keeps its API; the SQL to snapshot/claim/restore is written
here - no store function lets you overwrite ``run_count``, the ``last_*`` columns or ``delivery_attempts``
with an arbitrary value.

NOTE (contract): the trial really goes through the pipeline - under a ``staff_assistant`` profile it SENDS
(counts against the cap, leaves a real run log), exactly like the original. Under ``patient_channel`` it can
only end in a review draft, never a send.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.run_scheduled_job import RunScheduledJobOptions, run_scheduled_job
from pema.shared.zone_time import to_iso_z
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.scheduler import JobRunRecord, ScheduledJob


@dataclass(frozen=True)
class _Bookkeeping:
    run_count: int
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    delivery_attempts: int


async def run_scheduled_job_trial(deps: SchedulerDeps, job: ScheduledJob) -> JobRunRecord | None:
    """Run a job NOW - really sends, counts against the daily cap, leaves a real run log, but changes NO "real
    schedule" column of ``agent.jobs``. Returns the history row just written (if any) so the route can answer
    the web."""
    clinic_id = job.clinic_id
    now = datetime.now(UTC)
    scheduled_for = job.next_run_at or to_iso_z(now)

    async with deps.db.session(clinic_id) as s:
        row = (
            await s.execute(
                text(
                    "SELECT run_count, enabled, next_run_at, last_run_at, last_status, last_error, "
                    "delivery_attempts FROM agent.jobs WHERE clinic_id = :clinic_id AND id = :id FOR UPDATE"
                ),
                {"clinic_id": clinic_id, "id": job.id},
            )
        ).first()
        if row is None:
            before = None
            run_id = None
        else:
            if row[2] is None and job.next_run_at is not None:
                # The caller's copy says "scheduled" but the row says NULL: another worker took the occurrence
                # between the caller's read and our lock. Refuse (the transaction rolls back, nothing changed)
                # instead of racing it and restoring a stale snapshot over its progress.
                raise DomainError(
                    ErrorCode.INVALID_STATE, "Lịch hẹn đang được chạy ở nơi khác, thử lại sau ít phút."
                )
            before = _Bookkeeping(
                run_count=int(row[0]),
                enabled=bool(row[1]),
                next_run_at=row[2],
                last_run_at=row[3],
                last_status=row[4],
                last_error=row[5],
                delivery_attempts=int(row[6]),
            )
            # CLAIM the job BEFORE dispatch - the trial's own clear-before-dispatch, in the same transaction
            # that opens the run (the row is locked by the FOR UPDATE above, so the compare is exact).
            await s.execute(
                text("UPDATE agent.jobs SET next_run_at = NULL WHERE clinic_id = :clinic_id AND id = :id"),
                {"clinic_id": clinic_id, "id": job.id},
            )
            run_id = await deps.runs.open_run(clinic_id, job.id, worker_id=deps.worker_id, session=s)

    if before is None:
        # The job was deleted right before the snapshot (extremely rare) - nothing to claim or restore, run
        # straight through ``run_scheduled_job`` (which opens its own run and settles safely when the job is
        # no longer in the DB) and return an empty run log.
        await run_scheduled_job(
            deps, job, RunScheduledJobOptions(late=False, scheduled_for=scheduled_for, now=now, trial=True)
        )
        runs = await deps.runs.list_runs(clinic_id, job.id, 1)
        return runs[0] if runs else None

    if run_id is None:
        raise RuntimeError("trial run was not opened")
    try:
        await run_scheduled_job(
            deps,
            job,
            RunScheduledJobOptions(
                late=False, scheduled_for=scheduled_for, now=now, run_id=run_id, trial=True
            ),
        )
    finally:
        # ``finally``, not after the await: ``run_scheduled_job`` promises never to raise (it catches
        # internally), but if there is a surprise the job must still be GIVEN BACK, not stuck forever at
        # next_run_at=NULL.
        async with deps.db.session(clinic_id) as s:
            await s.execute(
                text(
                    """
                    UPDATE agent.jobs
                       SET run_count = :run_count, enabled = :enabled,
                           next_run_at = :next_run_at,
                           last_run_at = :last_run_at, last_status = :last_status, last_error = :last_error,
                           delivery_attempts = :delivery_attempts
                     WHERE clinic_id = :clinic_id AND id = :id"""
                ),
                {
                    "clinic_id": clinic_id,
                    "id": job.id,
                    "run_count": before.run_count,
                    "enabled": before.enabled,
                    "next_run_at": before.next_run_at,
                    "last_run_at": before.last_run_at,
                    "last_status": before.last_status,
                    "last_error": before.last_error,
                    "delivery_attempts": before.delivery_attempts,
                },
            )

    runs = await deps.runs.list_runs(clinic_id, job.id, 1)
    return runs[0] if runs else None
