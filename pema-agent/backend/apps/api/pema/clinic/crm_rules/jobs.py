# new module (not a port): crm-automation.js only created staff tasks, it never sent anything
"""From CRM tasks to scheduler jobs: the policy that decides which task may ALSO become an automatic message.

A task is always a staff task (the "manual task"). Only a rule whose ``send_mode`` is not ``staff_task`` may
additionally produce ONE scheduler job, and only when every gate below passes. The result is a plain
``CreateScheduledJobInput`` for ``SchedulerPort.create_job``; this module does no I/O and has no clock.

========================  =================================================================================
``send_mode``             job
========================  =================================================================================
``staff_task`` (default)  none
``auto_reminder``         ``kind: message``, ``payload`` = the key of an APPROVED, ACTIVE template
                          (``rule.effective_template_key``). The scheduler resolves the key to text at
                          delivery; the text is never copied into the job
``draft_for_review``      ``kind: agent`` with an instruction that asks the agent for a DRAFT; only under a
                          profile whose outbound mode is ``review`` (``patient_channel``), because under
                          ``staff_assistant`` an agent job would be sent without a human
========================  =================================================================================

Gates, in order (each failure is a ``JobSkipReason`` the runner reports; the staff task still exists):

1. birthday never (AGENT.md: a birthday is a staff task, never sent automatically), whatever the mode;
2. ``marketing_opt_out`` blocks every marketing rule and every marketing template. The opt-out never removes
   a safety follow-up TASK; it only stops automatic marketing;
3. the patient needs a verified channel identity on an enabled account and a granted ``messaging`` consent;
4. ``auto_reminder`` needs an approved template; ``draft_for_review`` needs a review-mode profile;
5. not stale: a due day more than ``max_lateness_days`` in the past is left to staff (a reminder weeks late is
   worse than none, and enabling a rule must not flush a backlog);
6. daily cap: planned jobs per proactive-cap scope and local day never exceed the cap the scheduler's
   ``ProactiveSendGuard`` enforces (same key as ``PermissivePolicyHooks.proactive_cap``: per account+thread
   in ``staff_assistant``, per patient+account in ``patient_channel``). The guard still reserves the real
   slot atomically at delivery; this planning cap only keeps the CRM from queueing what the guard would
   refuse. Higher priority and earlier due first.

Idempotency: ``dedupe_key`` = the task key, so a rerun (or a crash between persisting tasks and creating
jobs) returns the existing job instead of a second one. ``desired_keys`` lets the runner disable pending jobs
whose task is closed or whose gates no longer hold (task done, opt-out, template un-approved, rule changed).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pema.clinic.crm_rules.dates import days_between
from pema.clinic.crm_rules.records import PatientSnapshot, TaskCandidate, TemplateRef
from pema.clinic.crm_rules.rules import RuleConfig
from pema.shared.zone_time import to_iso_z
from pema_contracts.common import VN_TZ
from pema_contracts.crm import RuleKey, RuleSendMode, TaskPriority
from pema_contracts.policy import DEFAULT_PROFILES, OutboundMode, PolicyProfile, ProactiveCapScope
from pema_contracts.scheduler import CreateScheduledJobInput, JobKind, JobOrigin, OnceSchedule

JOB_CREATED_BY = "crm_rules"
DEFAULT_MAX_LATENESS_DAYS = 1
_PRIORITY_RANK: dict[TaskPriority, int] = {TaskPriority.HIGH: 0, TaskPriority.NORMAL: 1, TaskPriority.LOW: 2}


class JobSkipReason(StrEnum):
    BIRTHDAY_NEVER_AUTO = "birthday_never_auto"
    MARKETING_OPT_OUT = "marketing_opt_out"
    NO_CHANNEL = "no_channel"
    NO_CONSENT = "no_consent"
    NO_TEMPLATE = "no_template"
    REVIEW_NOT_AVAILABLE = "review_not_available"
    STALE = "stale"
    DAILY_CAP = "daily_cap"


@dataclass(frozen=True, slots=True)
class PendingJob:
    """A job that is enabled and has not run yet (from ``SchedulerPort.list_jobs``)."""

    dedupe_key: str | None
    scope_key: str
    run_day: date


@dataclass(frozen=True, slots=True)
class PlannedJob:
    job: CreateScheduledJobInput
    task_key: str
    scope_key: str
    run_day: date


@dataclass(frozen=True, slots=True)
class SkippedJob:
    task_key: str
    reason: JobSkipReason


@dataclass(frozen=True, slots=True)
class JobPlan:
    planned: tuple[PlannedJob, ...]
    already_scheduled: tuple[str, ...]
    skipped: tuple[SkippedJob, ...]

    @property
    def desired_keys(self) -> frozenset[str]:
        """Task keys that must have a pending job after this run (new or already there)."""
        return frozenset(p.task_key for p in self.planned) | frozenset(self.already_scheduled)


def scope_key_for(scope: ProactiveCapScope, patient_id: UUID | None, account_id: str, thread_id: str) -> str:
    """Key of the proactive cap counter. Same as ``PermissivePolicyHooks.proactive_cap`` for
    ``account_thread``; ``patient_account`` is ``<patient id>:<account id>`` until package P publishes its
    own key (open item)."""
    if scope is ProactiveCapScope.PATIENT_ACCOUNT and patient_id is not None:
        return f"{patient_id}:{account_id}"
    return f"{account_id}:{thread_id}"


def draft_instruction(rule: RuleConfig, template: TemplateRef | None) -> str:
    """Instruction of a ``draft_for_review`` agent job. No patient name, code or clinical content: the thread
    identifies the patient, and the agent's answer is held for human review by the outbound policy."""
    style = (
        f" Dùng mẫu đã duyệt '{template.key}' làm giọng văn và nội dung gốc." if template is not None else ""
    )
    return (
        f"Soạn NHÁP một tin nhắn chăm sóc ngắn, lịch sự bằng tiếng Việt cho bệnh nhân của "
        f"cuộc trò chuyện này. "
        f"Mục tiêu: {rule.suggested_action}.{style} "
        "Không chẩn đoán, không tư vấn thuốc hay liều dùng, không hứa hẹn kết quả. "
        "Nếu nghi có triệu chứng bất thường, đề nghị bệnh nhân liên hệ phòng khám."
    )


def _ineligible(
    candidate: TaskCandidate,
    rule: RuleConfig,
    patient: PatientSnapshot,
    templates: Mapping[str, TemplateRef],
) -> JobSkipReason | None:
    """Gates 1 to 4. None means the candidate may have a job."""
    if rule.key is RuleKey.BIRTHDAY:
        return JobSkipReason.BIRTHDAY_NEVER_AUTO
    template = templates.get(rule.effective_template_key)
    if patient.marketing_opt_out and (rule.marketing or (template is not None and template.marketing)):
        return JobSkipReason.MARKETING_OPT_OUT
    if patient.channel_target is None:
        return JobSkipReason.NO_CHANNEL
    if not patient.messaging_consent:
        return JobSkipReason.NO_CONSENT
    if rule.send_mode is RuleSendMode.AUTO_REMINDER and template is None:
        return JobSkipReason.NO_TEMPLATE
    if rule.send_mode is RuleSendMode.DRAFT_FOR_REVIEW:
        profile = DEFAULT_PROFILES[patient.channel_target.policy_profile]
        if profile.outbound_mode is not OutboundMode.REVIEW:
            return JobSkipReason.REVIEW_NOT_AVAILABLE
    return None


def _build_job(
    candidate: TaskCandidate,
    rule: RuleConfig,
    patient: PatientSnapshot,
    template: TemplateRef | None,
    *,
    clinic_id: UUID,
    run_at: datetime,
    now: datetime,
) -> CreateScheduledJobInput:
    target = patient.channel_target
    if target is None:
        raise ValueError("channel target required")
    if rule.send_mode is RuleSendMode.AUTO_REMINDER:
        kind, payload = JobKind.MESSAGE, rule.effective_template_key
    else:
        kind, payload = JobKind.AGENT, draft_instruction(rule, template)
    return CreateScheduledJobInput(
        clinic_id=clinic_id,
        account_id=target.account_id,
        thread_id=target.thread_id,
        thread_type=target.thread_type,
        name=f"CRM {rule.key.value} {patient.code}"[:200],
        kind=kind,
        payload=payload,
        schedule=OnceSchedule(run_at_utc=to_iso_z(run_at)),
        max_runs=1,
        created_by=JOB_CREATED_BY,
        now=now,
        dedupe_key=candidate.task_key,
        patient_id=patient.id,
        origin=JobOrigin.CRM_RULE,
    )


def plan_jobs(
    candidates: Iterable[TaskCandidate],
    *,
    clinic_id: UUID,
    rules: Mapping[RuleKey, RuleConfig],
    patients: Mapping[UUID, PatientSnapshot],
    templates: Mapping[str, TemplateRef],
    pending: Sequence[PendingJob],
    settled_task_keys: Collection[str],
    now: datetime,
    daily_cap: int,
    max_lateness_days: int = DEFAULT_MAX_LATENESS_DAYS,
) -> JobPlan:
    """Decide which candidates get a job. Pure; see the module docstring for the gates.

    ``settled_task_keys`` are tasks that staff already handled (resolved or rescheduled) or that are
    superseded,
    stored or superseded in this very run: they never get a job, however eligible their rule still is.
    """
    today = now.astimezone(VN_TZ).date()
    pending_keys = {p.dedupe_key for p in pending if p.dedupe_key is not None}
    load: dict[tuple[str, date], int] = {}
    for existing in pending:
        slot = (existing.scope_key, existing.run_day)
        load[slot] = load.get(slot, 0) + 1

    planned: list[PlannedJob] = []
    already: list[str] = []
    skipped: list[SkippedJob] = []
    ordered = sorted(candidates, key=lambda c: (_PRIORITY_RANK[c.priority], c.due_at, c.task_key))
    for candidate in ordered:
        rule = rules.get(candidate.rule_key)
        patient = patients.get(candidate.patient_id)
        if rule is None or patient is None or candidate.task_key in settled_task_keys:
            continue
        if rule.send_mode is RuleSendMode.STAFF_TASK:
            continue
        reason = _ineligible(candidate, rule, patient, templates)
        if reason is not None:
            skipped.append(SkippedJob(candidate.task_key, reason))
            continue
        if candidate.task_key in pending_keys:
            already.append(candidate.task_key)
            continue
        due_day = candidate.due_at.astimezone(VN_TZ).date()
        if days_between(due_day, today) > max_lateness_days:
            skipped.append(SkippedJob(candidate.task_key, JobSkipReason.STALE))
            continue
        target = patient.channel_target
        if target is None:
            continue
        profile: PolicyProfile = DEFAULT_PROFILES[target.policy_profile]
        run_at = max(candidate.due_at, now)
        run_day = run_at.astimezone(VN_TZ).date()
        scope_key = scope_key_for(
            profile.proactive_cap_scope, patient.id, target.account_id, target.thread_id
        )
        slot = (scope_key, run_day)
        if load.get(slot, 0) >= daily_cap:
            skipped.append(SkippedJob(candidate.task_key, JobSkipReason.DAILY_CAP))
            continue
        load[slot] = load.get(slot, 0) + 1
        template = templates.get(rule.effective_template_key)
        job = _build_job(candidate, rule, patient, template, clinic_id=clinic_id, run_at=run_at, now=now)
        planned.append(PlannedJob(job=job, task_key=candidate.task_key, scope_key=scope_key, run_day=run_day))
    return JobPlan(planned=tuple(planned), already_scheduled=tuple(already), skipped=tuple(skipped))
