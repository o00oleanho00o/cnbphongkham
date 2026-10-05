# ported from: src/scheduler/scheduled-job-record.ts
"""Shape of a scheduled job and the conversion DB row (snake_case) <-> object.

Split from ``scheduled_job_store`` so the CRUD file stays small: this is purely "the shape of the data", with
no SQL statement. The job type itself is ``pema_contracts.scheduler.ScheduledJob`` (snake_case already, with
the three clinic fields ``clinic_id``, ``dedupe_key``, ``patient_id``, ``origin``); ``JobKind`` too.

Forced deviation: SQLite rows carried ISO strings and ``enabled`` as 0/1; Postgres returns ``timestamptz`` and
``boolean``. ``row_to_job`` turns the instants back into the UTC ISO strings (``...Z``) the DTO documents for
``run_at`` / ``next_run_at`` / ``last_run_at``.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.engine import RowMapping

from pema.scheduler.session_scope import iso_or_none
from pema_contracts.scheduler import (
    CronSchedule,
    EverySchedule,
    JobKind,
    JobOrigin,
    OnceSchedule,
    ParsedSchedule,
    ScheduledJob,
    ScheduleKind,
)

JOB_COLUMNS = (
    "clinic_id, id, account_id, thread_id, thread_type, name, kind, payload, schedule_kind, run_at, "
    "every_minutes, cron_expr, timezone, enabled, next_run_at, last_run_at, last_status, last_error, "
    "run_count, max_runs, delivery_attempts, created_by, dedupe_key, patient_id, origin, created_at, updated_at"  # noqa: E501
)
"""Every column of ``agent.jobs`` in the order ``row_to_job`` reads them (no ``SELECT *``)."""


def row_to_job(row: RowMapping) -> ScheduledJob:
    """``mapRow``."""
    patient_id = row["patient_id"]
    return ScheduledJob(
        id=row["id"],
        clinic_id=row["clinic_id"],
        account_id=row["account_id"],
        thread_id=row["thread_id"],
        thread_type=row["thread_type"],
        name=row["name"],
        kind=JobKind(row["kind"]),
        payload=row["payload"],
        schedule_kind=ScheduleKind(row["schedule_kind"]),
        run_at=iso_or_none(row["run_at"]),
        every_minutes=row["every_minutes"],
        cron_expr=row["cron_expr"],
        timezone=row["timezone"],
        enabled=row["enabled"],
        next_run_at=iso_or_none(row["next_run_at"]),
        last_run_at=iso_or_none(row["last_run_at"]),
        last_status=row["last_status"],
        last_error=row["last_error"],
        run_count=row["run_count"],
        max_runs=row["max_runs"],
        delivery_attempts=row["delivery_attempts"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        dedupe_key=row["dedupe_key"],
        patient_id=None if patient_id is None else UUID(str(patient_id)),
        origin=JobOrigin(row["origin"]),
    )


@dataclass(frozen=True)
class ScheduleColumns:
    run_at: str | None
    every_minutes: int | None
    cron_expr: str | None


def schedule_columns(schedule: ParsedSchedule) -> ScheduleColumns:
    """Columns specific to ``schedule.kind``: exactly 1 of the 3 has a value, the others are NULL."""
    return ScheduleColumns(
        run_at=schedule.run_at_utc if isinstance(schedule, OnceSchedule) else None,
        every_minutes=schedule.minutes if isinstance(schedule, EverySchedule) else None,
        cron_expr=schedule.expr if isinstance(schedule, CronSchedule) else None,
    )


def schedule_of(job: ScheduledJob, default_time_zone: str) -> ParsedSchedule:
    """Rebuild the ``ParsedSchedule`` from a job: the bridge so the tick calls ``compute_next_run`` and
    ``decide_due_action`` directly without unpacking columns. An empty ``timezone`` column means the job
    follows the CURRENT configuration, so it falls back to ``default_time_zone`` (BOT_TIMEZONE) passed in by
    the CALLER: this module never reads env."""
    if job.schedule_kind is ScheduleKind.ONCE:
        if job.run_at is None:
            raise ValueError("a 'once' job row without run_at")
        return OnceSchedule(run_at_utc=job.run_at)
    if job.schedule_kind is ScheduleKind.EVERY:
        if job.every_minutes is None:
            raise ValueError("an 'every' job row without every_minutes")
        return EverySchedule(minutes=job.every_minutes)
    if job.cron_expr is None:
        raise ValueError("a 'cron' job row without cron_expr")
    return CronSchedule(expr=job.cron_expr, time_zone=job.timezone or default_time_zone)
