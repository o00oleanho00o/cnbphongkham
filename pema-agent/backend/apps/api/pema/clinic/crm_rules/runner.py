# new module (not a port): the browser ran the rules on every render; here a run is an explicit job
"""One run of the CRM rules for a clinic: load, decide (pure), persist, then create scheduler jobs.

    store.load -> run_rules (engine, pure) -> store.apply (one transaction, audited)
               -> plan_jobs (pure) -> SchedulerPort.create_job / set_enabled

Run it from an API-process task or a CLI as ``be_app`` (CONTRACTS section 7, decision 7). It is safe to run as
often as wanted and from two places at once:

* tasks are keyed by rule + patient + source event, ``apply`` skips keys that exist;
* jobs carry ``dedupe_key`` = task key, so ``SchedulerPort.create_job`` returns the first job again;
* jobs are created AFTER the tasks are stored. A crash in between is repaired by the next run, because the
  candidates are recomputed and the jobs are matched by key.

``SchedulerPort`` has no batch call: the runner lists the clinic's jobs once and calls ``create_job`` only for
jobs that do not exist yet, and ``set_enabled`` only for pending jobs that must go. Cost grows with the
changes, not with the number of patients.

A refusal of the scheduler (``DomainError``, for instance from the ``check_job`` policy hook) is counted and
logged by code; the staff task stays. Any other error propagates.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from uuid import UUID

from pema.clinic.crm_rules.engine import run_rules
from pema.clinic.crm_rules.jobs import (
    DEFAULT_MAX_LATENESS_DAYS,
    PendingJob,
    plan_jobs,
    scope_key_for,
)
from pema.clinic.crm_rules.records import PatientSnapshot
from pema.clinic.crm_rules.store import CrmRuleStore, StoreChanges
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.logger import create_logger
from pema_contracts.common import VN_TZ, now_vn
from pema_contracts.crm import TaskStatus
from pema_contracts.errors import DomainError
from pema_contracts.policy import DEFAULT_PROFILES, ProactiveCapScope
from pema_contracts.scheduler import JobOrigin, ScheduledJob, SchedulerPort

_log = create_logger("crm_rules")

_SETTLED_STATUSES = frozenset({TaskStatus.RESOLVED, TaskStatus.RESCHEDULED, TaskStatus.SUPERSEDED})


@dataclass(frozen=True, slots=True)
class RunReport:
    clinic_id: UUID
    patients: int
    candidates: int
    tasks_created: int
    tasks_superseded: int
    patients_updated: int
    jobs_created: int
    jobs_already_scheduled: int
    jobs_disabled: int
    jobs_failed: dict[str, int] = field(default_factory=dict[str, int])
    """Scheduler refusals by error code."""
    jobs_skipped: dict[str, int] = field(default_factory=dict[str, int])
    """Gates that kept a task from becoming a job, by ``JobSkipReason``."""


def _pending_jobs(jobs: Sequence[ScheduledJob], patients: dict[UUID, PatientSnapshot]) -> list[PendingJob]:
    """Enabled jobs that have not run: the planned load per proactive-cap scope and day."""
    pending: list[PendingJob] = []
    for job in jobs:
        if not job.enabled or job.run_count > 0 or job.next_run_at is None:
            continue
        moment = _parse_utc(job.next_run_at)
        if moment is None:
            continue
        patient = patients.get(job.patient_id) if job.patient_id is not None else None
        scope = (
            DEFAULT_PROFILES[patient.channel_target.policy_profile].proactive_cap_scope
            if patient is not None and patient.channel_target is not None
            else ProactiveCapScope.ACCOUNT_THREAD
        )
        pending.append(
            PendingJob(
                dedupe_key=job.dedupe_key,
                scope_key=scope_key_for(scope, job.patient_id, job.account_id, job.thread_id),
                run_day=_local_day(moment),
            )
        )
    return pending


def _local_day(moment: datetime) -> date:
    return moment.astimezone(VN_TZ).date()


def _parse_utc(value: str) -> datetime | None:
    """``next_run_at`` is UTC ISO 8601 with ``Z`` (``to_iso_z``); anything unparsable is ignored."""
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class CrmRulesRunner:
    def __init__(
        self,
        store: CrmRuleStore,
        scheduler: SchedulerPort,
        *,
        daily_cap: int | None = None,
        max_lateness_days: int = DEFAULT_MAX_LATENESS_DAYS,
    ) -> None:
        self._store = store
        self._scheduler = scheduler
        self._daily_cap = daily_cap
        self._max_lateness_days = max_lateness_days

    async def run_clinic(self, clinic_id: UUID, now: datetime | None = None) -> RunReport:
        moment = now if now is not None else now_vn()
        await self._store.ensure_rules(clinic_id)
        data = await self._store.load(clinic_id, moment)

        outcome = run_rules(data.patients, data.rules, data.existing_tasks, moment)
        inserted = await self._store.apply(
            clinic_id,
            StoreChanges(
                new_tasks=outcome.new_tasks,
                superseded_keys=outcome.superseded_keys,
                patient_updates=outcome.patient_updates,
                now=moment,
            ),
        )

        patients = {p.id: p for p in outcome.refreshed}
        jobs = await self._scheduler.list_jobs(clinic_id)
        pending = _pending_jobs(jobs, patients)
        settled = {t.task_key for t in data.existing_tasks if t.status in _SETTLED_STATUSES}
        settled.update(outcome.superseded_keys)
        cap = (
            self._daily_cap
            if self._daily_cap is not None
            else get_tuning_int("SCHEDULER_MAX_PROACTIVE_PER_DAY")
        )
        plan = plan_jobs(
            outcome.candidates,
            clinic_id=clinic_id,
            rules={r.key: r for r in data.rules},
            patients=patients,
            templates=data.templates,
            pending=pending,
            settled_task_keys=settled,
            now=moment,
            daily_cap=cap,
            max_lateness_days=self._max_lateness_days,
        )

        created = 0
        failed: Counter[str] = Counter()
        for planned in plan.planned:
            try:
                await self._scheduler.create_job(planned.job)
            except DomainError as exc:
                failed[exc.code.value] += 1
                _log.warning("scheduler refused a crm job", clinic_id=str(clinic_id), code=exc.code.value)
                continue
            created += 1

        disabled = 0
        desired = plan.desired_keys
        for job in jobs:
            if job.origin is not JobOrigin.CRM_RULE or not job.enabled or job.run_count > 0:
                continue
            if job.dedupe_key is None or job.dedupe_key in desired:
                continue
            if await self._scheduler.set_enabled(clinic_id, job.account_id, job.thread_id, job.id, False):
                disabled += 1

        skipped = Counter(s.reason.value for s in plan.skipped)
        report = RunReport(
            clinic_id=clinic_id,
            patients=len(data.patients),
            candidates=len(outcome.candidates),
            tasks_created=inserted,
            tasks_superseded=len(outcome.superseded_keys),
            patients_updated=len(outcome.patient_updates),
            jobs_created=created,
            jobs_already_scheduled=len(plan.already_scheduled),
            jobs_disabled=disabled,
            jobs_failed=dict(failed),
            jobs_skipped=dict(skipped),
        )
        _log.info(
            "crm rules run",
            clinic_id=str(clinic_id),
            patients=report.patients,
            candidates=report.candidates,
            tasks_created=report.tasks_created,
            tasks_superseded=report.tasks_superseded,
            jobs_created=report.jobs_created,
            jobs_disabled=report.jobs_disabled,
            jobs_failed=sum(failed.values()),
            jobs_skipped=sum(skipped.values()),
        )
        return report


__all__ = ["CrmRulesRunner", "RunReport"]
