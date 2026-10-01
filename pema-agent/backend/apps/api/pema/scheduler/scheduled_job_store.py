# ported from: src/scheduler/scheduled-job-store.ts
"""CRUD of table ``agent.jobs``: the CURRENT state of every scheduled job. The run history is in
``job_run_log_store`` (a separate table, see the reason there). The data shape (type + row conversion) is in
``scheduled_job_record``.

Forced deviations:

* ``node:sqlite`` (sync, one process) becomes SQLAlchemy async over Postgres; every method takes the clinic id
  (RLS context) as its first argument and optionally joins an open session (``session_scope``);
* the one-process invariants become atomic SQL: ``mark_run`` is a single ``UPDATE`` that increments
  ``run_count`` and decides the ``max_runs`` shut-off from the row itself (no read-then-write, so two
  concurrent finishes cannot lose an increment), and ``claim_due_job`` is a compare-and-swap on
  ``next_run_at`` (the "clear-before-dispatch" of the tick, which now has to hold across workers);
* ``create_job`` honours ``dedupe_key`` (CRM rule + patient + source event): a second create with the same key
  in the same clinic returns the first job instead of a duplicate.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.core.db import ClinicDatabase
from pema.scheduler.next_run import compute_next_run
from pema.scheduler.scheduled_job_record import (
    JOB_COLUMNS,
    row_to_job,
    schedule_columns,
    schedule_of,
)
from pema.scheduler.session_scope import parse_utc, use_session
from pema_contracts.scheduler import (
    CreateScheduledJobInput,
    JobRunStatus,
    ParsedSchedule,
    ScheduledJob,
    ScheduleKind,
)

__all__ = [
    "ScheduledJobStore",
    "UpdateScheduledJobInput",
    "schedule_of",
]


@dataclass(frozen=True)
class UpdateScheduledJobInput:
    name: str | None = None
    payload: str | None = None
    schedule: ParsedSchedule | None = None
    timezone: str | None = None
    max_runs: int | None = None
    max_runs_set: bool = False
    """``max_runs=None`` alone means "not given"; set this to True to write an explicit NULL (unlimited)."""
    now: datetime | None = None
    """"Now" to recompute next_run_at when the schedule changes; defaults to the system clock."""


class ScheduledJobStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def create_job(
        self, job_input: CreateScheduledJobInput, *, session: AsyncSession | None = None
    ) -> ScheduledJob:
        job_id = secrets.token_hex(6)
        cols = schedule_columns(job_input.schedule)
        now = job_input.now.astimezone(UTC) if job_input.now is not None else datetime.now(UTC)
        next_run_at = compute_next_run(job_input.schedule, now)
        # Invariant: 'once' ALWAYS runs exactly once - the kind is checked FIRST and any ``max_runs`` the
        # caller passes is ignored (even an explicit value > 1). The hole that was measured: ``max_runs=5``
        # slipping through on a once job, ``compute_next_run('once')`` still returns the whole ``run_at_utc``
        # whatever ``now`` is, so after the first run (not yet at the cap of 5) next_run_at stays at the past
        # instant -> the next tick picks it up AT ONCE -> it fires again every tick until 5 runs.
        max_runs = 1 if job_input.schedule.kind is ScheduleKind.ONCE else job_input.max_runs

        async with use_session(self._db, job_input.clinic_id, session) as s:
            inserted = (
                (
                    await s.execute(
                        text(
                            f"""
                            INSERT INTO agent.jobs
                              (clinic_id, id, account_id, thread_id, thread_type, name, kind, payload,
                               schedule_kind, run_at, every_minutes, cron_expr, timezone, next_run_at,
                               max_runs, created_by, dedupe_key, patient_id, origin)
                            VALUES
                              (:clinic_id, :id, :account_id, :thread_id, :thread_type, :name, :kind, :payload,
                               :schedule_kind, :run_at, :every_minutes, :cron_expr, :timezone, :next_run_at,
                               :max_runs, :created_by, :dedupe_key, :patient_id, :origin)
                            ON CONFLICT (clinic_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
                            RETURNING {JOB_COLUMNS}"""  # noqa: S608 - constant column list
                        ),
                        {
                            "clinic_id": job_input.clinic_id,
                            "id": job_id,
                            "account_id": job_input.account_id,
                            "thread_id": job_input.thread_id,
                            "thread_type": job_input.thread_type,
                            "name": job_input.name,
                            "kind": job_input.kind.value,
                            "payload": job_input.payload,
                            "schedule_kind": job_input.schedule.kind.value,
                            "run_at": parse_utc(cols.run_at),
                            "every_minutes": cols.every_minutes,
                            "cron_expr": cols.cron_expr,
                            "timezone": job_input.timezone,
                            "next_run_at": parse_utc(next_run_at),
                            "max_runs": max_runs,
                            "created_by": job_input.created_by,
                            "dedupe_key": job_input.dedupe_key,
                            "patient_id": job_input.patient_id,
                            "origin": job_input.origin.value,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if inserted is not None:
                return row_to_job(inserted)
            # The only way to get no row is the dedupe conflict: hand back the job that already holds the key.
            existing = (
                (
                    await s.execute(
                        text(
                            f"SELECT {JOB_COLUMNS} FROM agent.jobs "  # noqa: S608 - constant column list
                            "WHERE clinic_id = :clinic_id AND dedupe_key = :dedupe_key"
                        ),
                        {"clinic_id": job_input.clinic_id, "dedupe_key": job_input.dedupe_key},
                    )
                )
                .mappings()
                .one()
            )
            return row_to_job(existing)

    async def get_job_unscoped(
        self, clinic_id: UUID, job_id: str, *, session: AsyncSession | None = None
    ) -> ScheduledJob | None:
        """Read a job WITHOUT the (account, thread) scope - ONLY for internal use by the tick
        (``list_due_jobs``
        scans every account and then needs to look up by id a job it just found) and by ``mark_run`` /
        ``create_job``, which are sure of where the id came from. NEVER call it with an id given by a user or
        the LLM: that is an IDOR path (the id is only 12 hex characters, guessable or probeable)."""
        async with use_session(self._db, clinic_id, session) as s:
            row = (
                (
                    await s.execute(
                        text(
                            f"SELECT {JOB_COLUMNS} FROM agent.jobs "  # noqa: S608 - constant column list
                            "WHERE clinic_id = :clinic_id AND id = :id"
                        ),
                        {"clinic_id": clinic_id, "id": job_id},
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else row_to_job(row)

    async def get_job(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        job_id: str,
        *,
        session: AsyncSession | None = None,
    ) -> ScheduledJob | None:
        """Read a job WITH the scope check - the path for the tool / admin API. The check lives here (the
        store layer), not only in the tool: every later caller automatically gets the same rule and nobody can
        forget it."""
        async with use_session(self._db, clinic_id, session) as s:
            row = (
                (
                    await s.execute(
                        text(
                            f"SELECT {JOB_COLUMNS} FROM agent.jobs "  # noqa: S608 - constant column list
                            "WHERE clinic_id = :clinic_id AND id = :id AND account_id = :account_id "
                            "AND thread_id = :thread_id"
                        ),
                        {
                            "clinic_id": clinic_id,
                            "id": job_id,
                            "account_id": account_id,
                            "thread_id": thread_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else row_to_job(row)

    async def list_jobs_for_thread(
        self, clinic_id: UUID, account_id: str, thread_id: str, *, session: AsyncSession | None = None
    ) -> list[ScheduledJob]:
        async with use_session(self._db, clinic_id, session) as s:
            rows = (
                (
                    await s.execute(
                        text(
                            f"SELECT {JOB_COLUMNS} FROM agent.jobs "  # noqa: S608 - constant column list
                            "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id "  # noqa: E501
                            "ORDER BY created_at DESC, id"
                        ),
                        {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id},
                    )
                )
                .mappings()
                .all()
            )
        return [row_to_job(r) for r in rows]

    async def update_job(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        job_id: str,
        patch: UpdateScheduledJobInput,
    ) -> bool:
        """Partial update; a field not passed keeps its old value. ``next_run_at`` is recomputed only when
        ``schedule`` REALLY changes - recomputing the schedule just because the name/payload changed is absurd
        and can jump the slot unintentionally.

        ``(account_id, thread_id)`` are mandatory and go straight into the WHERE: a job of another thread is
        treated as nonexistent (returns ``False``), not even revealing that it exists. The read-modify-write
        runs under ``SELECT ... FOR UPDATE`` so two edits cannot overwrite each other.
        """
        async with self._db.session(clinic_id) as s:
            row = (
                (
                    await s.execute(
                        text(
                            f"SELECT {JOB_COLUMNS} FROM agent.jobs "  # noqa: S608 - constant column list
                            "WHERE clinic_id = :clinic_id AND id = :id AND account_id = :account_id "
                            "AND thread_id = :thread_id FOR UPDATE"
                        ),
                        {
                            "clinic_id": clinic_id,
                            "id": job_id,
                            "account_id": account_id,
                            "thread_id": thread_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return False
            job = row_to_job(row)

            if patch.schedule is not None:
                cols = schedule_columns(patch.schedule)
                run_at, every_minutes, cron_expr = cols.run_at, cols.every_minutes, cols.cron_expr
                now = patch.now.astimezone(UTC) if patch.now is not None else datetime.now(UTC)
                next_run_at = compute_next_run(patch.schedule, now)
            else:
                run_at, every_minutes, cron_expr = job.run_at, job.every_minutes, job.cron_expr
                next_run_at = job.next_run_at
            effective_kind = patch.schedule.kind if patch.schedule is not None else job.schedule_kind
            # The kind REALLY changes - not merely "there is a patch.schedule". A wider trigger (recompute on
            # any patch.schedule) once lost an explicit max_runs=5 set at creation when only the frequency
            # changed every 30m -> every 45m (kind still "every"): the cap "remind 5 times then stop" vanished
            # and the job became unlimited - exactly the kind of risk this phase exists to block, only in the
            # other direction from the case below.
            kind_changed = patch.schedule is not None and patch.schedule.kind is not job.schedule_kind

            max_runs: int | None
            if effective_kind is ScheduleKind.ONCE:
                # Invariant: 'once' ALWAYS runs exactly once, even when the patch passes another max_runs
                # (see ``create_job``: a max_runs > 1 freezes next_run_at at a past instant).
                max_runs = 1
            elif patch.max_runs is not None or patch.max_runs_set:
                max_runs = patch.max_runs
            elif kind_changed:
                # Switched to another kind (every<->cron) without saying max_runs -> default unlimited, mirror
                # the ternary of ``create_job`` for the new kind.
                max_runs = None
            else:
                # Kind unchanged (even when the schedule is not touched at all) -> keep the old value.
                max_runs = job.max_runs

            await s.execute(
                text(
                    """
                    UPDATE agent.jobs
                       SET name = :name, payload = :payload, schedule_kind = :schedule_kind, run_at = :run_at,
                           every_minutes = :every_minutes, cron_expr = :cron_expr, timezone = :timezone,
                           next_run_at = :next_run_at, max_runs = :max_runs
                     WHERE clinic_id = :clinic_id AND id = :id"""
                ),
                {
                    "clinic_id": clinic_id,
                    "id": job_id,
                    "name": patch.name if patch.name is not None else job.name,
                    "payload": patch.payload if patch.payload is not None else job.payload,
                    "schedule_kind": effective_kind.value,
                    "run_at": parse_utc(run_at),
                    "every_minutes": every_minutes,
                    "cron_expr": cron_expr,
                    "timezone": patch.timezone if patch.timezone is not None else job.timezone,
                    "next_run_at": parse_utc(next_run_at),
                    "max_runs": max_runs,
                },
            )
        return True

    async def set_enabled(
        self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str, enabled: bool
    ) -> bool:
        async with self._db.session(clinic_id) as s:
            result = await s.execute(
                text(
                    "UPDATE agent.jobs SET enabled = :enabled WHERE clinic_id = :clinic_id AND id = :id "
                    "AND account_id = :account_id AND thread_id = :thread_id"
                ),
                {
                    "clinic_id": clinic_id,
                    "id": job_id,
                    "account_id": account_id,
                    "thread_id": thread_id,
                    "enabled": enabled,
                },
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    async def get_job_by_dedupe_key(
        self, clinic_id: UUID, dedupe_key: str, *, session: AsyncSession | None = None
    ) -> ScheduledJob | None:
        """The job that holds ``dedupe_key`` in this clinic (the unique index allows at most one)."""
        async with use_session(self._db, clinic_id, session) as s:
            row = (
                (
                    await s.execute(
                        text(
                            f"SELECT {JOB_COLUMNS} FROM agent.jobs "  # noqa: S608 - constant column list
                            "WHERE clinic_id = :clinic_id AND dedupe_key = :dedupe_key"
                        ),
                        {"clinic_id": clinic_id, "dedupe_key": dedupe_key},
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else row_to_job(row)

    async def set_enabled_by_dedupe_key(self, clinic_id: UUID, dedupe_key: str, enabled: bool) -> bool:
        """Switch a job on/off by the idempotency key of the CRM rule that created it (the scope is the key
        itself: it is unique per clinic, so no IDOR path through a guessable id)."""
        async with self._db.session(clinic_id) as s:
            result = await s.execute(
                text(
                    "UPDATE agent.jobs SET enabled = :enabled "
                    "WHERE clinic_id = :clinic_id AND dedupe_key = :dedupe_key"
                ),
                {"clinic_id": clinic_id, "dedupe_key": dedupe_key, "enabled": enabled},
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    async def delete_job(self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str) -> bool:
        # The run history is removed by the ``ON DELETE CASCADE`` of ``agent.job_runs`` (0002), where the
        # original needed a second DELETE because ``scheduled_job_runs.job_id`` was a plain TEXT. A job that
        # is deleted never opens a run again, so without cascading its history would be orphaned FOREVER; the
        # dashboard tells the user "the run history of this schedule is deleted with it" - that sentence has
        # to be TRUE.
        async with self._db.session(clinic_id) as s:
            result = await s.execute(
                text(
                    "DELETE FROM agent.jobs WHERE clinic_id = :clinic_id AND id = :id "
                    "AND account_id = :account_id AND thread_id = :thread_id"
                ),
                {"clinic_id": clinic_id, "id": job_id, "account_id": account_id, "thread_id": thread_id},
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    async def list_due_jobs(
        self, clinic_id: UUID, now_utc: datetime, *, session: AsyncSession | None = None
    ) -> list[ScheduledJob]:
        """Jobs due up to ``now_utc`` - the source for the tick loop. DELIBERATELY takes no ``(account_id,
        thread_id)``: the tick scans EVERY account of the clinic, it has no "calling thread" to limit by."""
        async with use_session(self._db, clinic_id, session) as s:
            rows = (
                (
                    await s.execute(
                        text(
                            f"SELECT {JOB_COLUMNS} FROM agent.jobs "  # noqa: S608 - constant column list
                            "WHERE clinic_id = :clinic_id AND enabled AND next_run_at IS NOT NULL "
                            "AND next_run_at <= :now ORDER BY next_run_at ASC, id"
                        ),
                        {"clinic_id": clinic_id, "now": now_utc},
                    )
                )
                .mappings()
                .all()
            )
        return [row_to_job(r) for r in rows]

    async def set_next_run(
        self,
        clinic_id: UUID,
        job_id: str,
        next_run_at_utc: str | None,
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """Write the next run instant. No scope check: the id always comes from ``list_due_jobs`` or from the
        run itself (the loop found it, it is not an id supplied by a user)."""
        async with use_session(self._db, clinic_id, session) as s:
            await s.execute(
                text("UPDATE agent.jobs SET next_run_at = :next WHERE clinic_id = :clinic_id AND id = :id"),
                {"clinic_id": clinic_id, "id": job_id, "next": parse_utc(next_run_at_utc)},
            )

    async def claim_due_job(
        self,
        clinic_id: UUID,
        job_id: str,
        expected_next_run_at: datetime,
        new_next_run_at: str | None,
        *,
        session: AsyncSession | None = None,
    ) -> bool:
        """The "clear-before-dispatch" as an ATOMIC claim: write the NEW ``next_run_at`` only if the row still
        holds the instant the tick read. Of N workers (or the tick and a trial run) that read the same due
        row, exactly one UPDATE matches; the others get ``False`` and must not run the job. ``True`` means
        this caller owns the occurrence."""
        async with use_session(self._db, clinic_id, session) as s:
            result = await s.execute(
                text(
                    "UPDATE agent.jobs SET next_run_at = :new WHERE clinic_id = :clinic_id AND id = :id "
                    "AND enabled AND next_run_at = :expected"
                ),
                {
                    "clinic_id": clinic_id,
                    "id": job_id,
                    "new": parse_utc(new_next_run_at),
                    "expected": expected_next_run_at,
                },
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    async def mark_blocked(
        self, clinic_id: UUID, job_id: str, reason: str, *, session: AsyncSession | None = None
    ) -> None:
        """Write the PRE-FLIGHT block reason on the job row (``last_status='blocked'``): before, a job blocked
        there left no trace at all, an account that dropped its session for 3 days looked exactly like a
        healthy job on the dashboard. Reuses ``last_status``/``last_error``; it heals when the job really runs
        next."""
        async with use_session(self._db, clinic_id, session) as s:
            await s.execute(
                text(
                    "UPDATE agent.jobs SET last_status = 'blocked', last_error = :reason "
                    "WHERE clinic_id = :clinic_id AND id = :id"
                ),
                {"clinic_id": clinic_id, "id": job_id, "reason": reason},
            )

    async def mark_run(
        self,
        clinic_id: UUID,
        job_id: str,
        status: JobRunStatus,
        error: str | None = None,
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """Record that a job ran to the end (increment ``run_count`` + update the summary). Reaching
        ``max_runs`` sets ``enabled = false`` and ``next_run_at = NULL`` but KEEPS the row - deleting it (as
        Hermes/goclaw do) makes an appointed reminder vanish without a trace.

        ONE atomic statement: the increment and the cap decision read the same old row, so two concurrent
        finishes can never both see ``run_count = 0``. No scope check, same reason as ``set_next_run``."""
        async with use_session(self._db, clinic_id, session) as s:
            await s.execute(
                text(
                    """
                    UPDATE agent.jobs
                       SET run_count = run_count + 1,
                           last_run_at = now(),
                           last_status = :status,
                           last_error = :error,
                           enabled = CASE WHEN max_runs IS NOT NULL AND run_count + 1 >= max_runs
                                          THEN false ELSE enabled END,
                           next_run_at = CASE WHEN max_runs IS NOT NULL AND run_count + 1 >= max_runs
                                              THEN NULL ELSE next_run_at END
                     WHERE clinic_id = :clinic_id AND id = :id"""
                ),
                {"clinic_id": clinic_id, "id": job_id, "status": status.value, "error": error},
            )

    async def revive_claimed_once(self, clinic_id: UUID, *, session: AsyncSession | None = None) -> int:
        """Restore a 'once' reminder that was CLAIMED (``next_run_at = NULL`` by clear-before-dispatch, see
        ``claim_due_job``) but whose worker died BEFORE ``mark_run`` - a normal deploy/restart, not a rare
        incident. Without this the row stays ``enabled = true, next_run_at = NULL, run_count = 0``, and
        ``list_due_jobs`` filters ``next_run_at IS NOT NULL`` so NO tick ever sees the job again - the
        reminder vanishes FOREVER, breaking the decided invariant "a reminder that never managed to be sent is
        never counted as run".

        ``enabled`` + ``run_count < max_runs`` (or ``max_runs IS NULL``) tells "in progress" from "ran and
        switched itself off" - a finished 'once' job was disabled by ``mark_run`` so it does not match the
        first condition either, but the ``run_count < max_runs`` condition is kept for clarity: without it a
        change of the ``enabled`` invariant elsewhere would resurrect a COMPLETED job.

        With several workers a live worker may be in the middle of a long run of that very job, so the job is
        revived only when NO ``running`` row of it remains (call ``interrupt_stale_runs`` first: what is still
        ``running`` after it has a worker that proved it is alive).

        The deliberate, accepted flip side stays: "the message really left but the worker died BEFORE
        ``mark_run``" also matches and is revived, so the next recovery sends a second copy. That window is a
        few milliseconds (the statements between the send and ``mark_run`` are one transaction), in exchange
        for removing the window of LOSING the reminder that used to cover the whole dispatch (an agent turn
        can run for minutes) - the direction of the decided invariant."""
        async with use_session(self._db, clinic_id, session) as s:
            result = await s.execute(
                text(
                    """
                    UPDATE agent.jobs j SET next_run_at = j.run_at
                     WHERE j.clinic_id = :clinic_id AND j.enabled AND j.next_run_at IS NULL
                       AND j.schedule_kind = 'once' AND j.run_at IS NOT NULL
                       AND (j.max_runs IS NULL OR j.run_count < j.max_runs)
                       AND NOT EXISTS (SELECT 1 FROM agent.job_runs r
                                        WHERE r.clinic_id = j.clinic_id AND r.job_id = j.id
                                          AND r.status = 'running')"""
                ),
                {"clinic_id": clinic_id},
            )
            return int(result.rowcount)  # type: ignore[attr-defined]
