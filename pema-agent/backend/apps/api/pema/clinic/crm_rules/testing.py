# new module (test support, like ``pema_contracts.testing``)
"""Fakes and builders for the tests of the CRM rules, usable by package G for its integration tests.

``pema_contracts.testing`` has no fake scheduler (package A shipped fakes for channels, turn queue and account
stores only), so ``FakeScheduler`` here implements ``SchedulerPort`` over a dict with the two behaviours
the CRM
relies on: ``dedupe_key`` returns the first job again, and ``set_enabled`` works on a pending job. It does not
compute schedules beyond ``next_run_at`` of a ``once`` job and it never sends anything.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from pema.clinic.crm_rules.records import (
    AppointmentSnapshot,
    AppointmentStatus,
    PatientSnapshot,
    SessionSnapshot,
)
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError
from pema_contracts.scheduler import (
    CreateScheduledJobInput,
    JobRunRecord,
    OnceSchedule,
    ScheduledJob,
    ScheduleKind,
)

NOW = datetime(2026, 9, 20, 9, 0, tzinfo=VN_TZ)
"""The fixed clock of crm-data.js (``DAY = '2026-09-20'``) at the 09:00 the JavaScript uses for due times."""


class FakeScheduler:
    """``SchedulerPort`` in memory. ``create_calls`` counts every ``create_job`` call (also deduplicated)."""

    def __init__(
        self, *, refuse: Callable[[CreateScheduledJobInput], DomainError | None] | None = None
    ) -> None:
        self.jobs: dict[str, ScheduledJob] = {}
        self.create_calls = 0
        self._refuse = refuse

    def seed(self, job: ScheduledJob) -> None:
        self.jobs[job.id] = job

    async def create_job(self, job: CreateScheduledJobInput) -> ScheduledJob:
        self.create_calls += 1
        if self._refuse is not None:
            error = self._refuse(job)
            if error is not None:
                raise error
        if job.dedupe_key is not None:
            for existing in self.jobs.values():
                if existing.clinic_id == job.clinic_id and existing.dedupe_key == job.dedupe_key:
                    return existing
        run_at = job.schedule.run_at_utc if isinstance(job.schedule, OnceSchedule) else None
        created = ScheduledJob(
            id=str(uuid4()),
            clinic_id=job.clinic_id,
            account_id=job.account_id,
            thread_id=job.thread_id,
            thread_type=job.thread_type,
            name=job.name,
            kind=job.kind,
            payload=job.payload,
            schedule_kind=ScheduleKind.ONCE if run_at is not None else job.schedule.kind,
            run_at=run_at,
            next_run_at=run_at,
            max_runs=1 if run_at is not None else job.max_runs,
            created_by=job.created_by,
            dedupe_key=job.dedupe_key,
            patient_id=job.patient_id,
            origin=job.origin,
        )
        self.jobs[created.id] = created
        return created

    async def get_job(
        self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str
    ) -> ScheduledJob | None:
        job = self.jobs.get(job_id)
        if job is None or (job.clinic_id, job.account_id, job.thread_id) != (
            clinic_id,
            account_id,
            thread_id,
        ):
            return None
        return job

    async def get_job_unscoped(self, clinic_id: UUID, job_id: str) -> ScheduledJob | None:
        job = self.jobs.get(job_id)
        return job if job is not None and job.clinic_id == clinic_id else None

    async def list_jobs_for_thread(
        self, clinic_id: UUID, account_id: str, thread_id: str
    ) -> list[ScheduledJob]:
        return [
            j
            for j in self.jobs.values()
            if (j.clinic_id, j.account_id, j.thread_id) == (clinic_id, account_id, thread_id)
        ]

    async def list_jobs(self, clinic_id: UUID, account_id: str | None = None) -> list[ScheduledJob]:
        return [
            j
            for j in self.jobs.values()
            if j.clinic_id == clinic_id and (account_id is None or j.account_id == account_id)
        ]

    async def get_job_by_dedupe_key(self, clinic_id: UUID, dedupe_key: str) -> ScheduledJob | None:
        for job in self.jobs.values():
            if job.clinic_id == clinic_id and job.dedupe_key == dedupe_key:
                return job
        return None

    async def set_enabled_by_dedupe_key(self, clinic_id: UUID, dedupe_key: str, enabled: bool) -> bool:
        job = await self.get_job_by_dedupe_key(clinic_id, dedupe_key)
        if job is None:
            return False
        self.jobs[job.id] = job.model_copy(update={"enabled": enabled})
        return True

    async def set_enabled(
        self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str, enabled: bool
    ) -> bool:
        job = await self.get_job(clinic_id, account_id, thread_id, job_id)
        if job is None:
            return False
        self.jobs[job_id] = job.model_copy(update={"enabled": enabled})
        return True

    async def delete_job(self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str) -> bool:
        return self.jobs.pop(job_id, None) is not None

    async def list_runs(self, clinic_id: UUID, job_id: str, limit: int = 20) -> list[JobRunRecord]:
        return []

    async def run_trial(self, clinic_id: UUID, job_id: str) -> JobRunRecord:
        raise NotImplementedError("the CRM never runs trials")

    def enabled(self) -> list[ScheduledJob]:
        return [j for j in self.jobs.values() if j.enabled]


def appointment(
    id: str,
    day: date,
    *,
    hour: int = 10,
    status: AppointmentStatus = AppointmentStatus.BOOKED,
    cancelled_at: datetime | None = None,
    missed_at: datetime | None = None,
) -> AppointmentSnapshot:
    return AppointmentSnapshot(
        id=id,
        starts_at=datetime(day.year, day.month, day.day, hour, 0, tzinfo=VN_TZ),
        status=status,
        cancelled_at=cancelled_at,
        missed_at=missed_at,
    )


def make_patient(code: str = "P900", **fields: Any) -> PatientSnapshot:
    """A synthetic patient with sensible defaults; override any field by name."""
    return replace(PatientSnapshot(id=uuid4(), code=code), **fields)


def session(id: str, day: date, protocol_id: str | None = None) -> SessionSnapshot:
    return SessionSnapshot(id=id, day=day, protocol_id=protocol_id)
