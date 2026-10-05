"""The facts of ONE run of a job, resolved once (new module, no zalo-agent source).

The original passed ``job``, ``timeZone``, ``scheduledFor``, ``now`` and the run id as separate arguments
through ``blockedByGuard`` / ``sendAndConclude`` / ``concludeCapBlocked``. The clinic version adds the policy
(which profile applies, the cap key, whether the job may only draft), so those values travel together in one
immutable ``RunContext`` instead of growing every signature.

How the policy is applied (CONTRACTS section 3, "Policy hook call sites"):

* the profile of the run is ``effective_profile_key(account.policy_profile, agent.policy_profile)`` (the
  RESTRICTIVE one wins) looked up in ``DEFAULT_PROFILES``;
* ``PolicyHooks.check_job`` decides ``allow`` / ``downgrade_to_draft`` / ``deny``. On top of the hook the
  scheduler applies the PROFILE itself (``job_kind_allowed``): a profile that only allows template messages
  turns an ``agent`` job into a draft even when the injected hooks are permissive. Clinic safety does not wait
  for package P to be wired;
* ``on_outbound`` decides ``send`` / ``hold_for_review`` / ``drop`` for every text that would leave the
  system, and a profile whose outbound mode is ``review`` can never end in a direct send.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from pema.config.runtime_tuning_settings import bot_time_zone
from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.proactive_send_guard import EffectiveCap
from pema.scheduler.scheduled_job_record import schedule_of
from pema_contracts.agents import AccountConfig
from pema_contracts.policy import (
    DEFAULT_PROFILES,
    JobAction,
    JobDecision,
    OutboundAction,
    OutboundDecision,
    OutboundMode,
    OutboundOrigin,
    PolicyContext,
    effective_profile_key,
    job_kind_allowed,
)
from pema_contracts.scheduler import CreateScheduledJobInput, JobKind, ScheduledJob


@dataclass(frozen=True)
class RunContext:
    job: ScheduledJob
    account: AccountConfig
    policy: PolicyContext
    cap: EffectiveCap
    time_zone: str
    scheduled_for: str
    """``next_run_at`` ORIGINAL (the instant the job SHOULD have run); for ``once`` it is ``run_at``."""
    now: datetime
    """The ONE instant of this run, fixed at the start of the tick (see ``proactive_send_guard``)."""
    run_id: int
    late: bool
    draft_only: bool = False
    """The policy turned this job into a draft: its output becomes a review item, never a send."""
    policy_reason: str | None = None
    """Why (short code or sentence, no PII) - goes into the review item payload."""
    review_key: str = ""
    """Idempotency key of the review item of this occurrence: ``<job id>@<scheduled instant>`` (a retry of the
    same occurrence gets the same item; a manual trial run adds ``#trial<run id>``)."""


async def resolve_policy_context(
    deps: SchedulerDeps, job: ScheduledJob, account: AccountConfig, *, isolated: bool
) -> PolicyContext:
    agent = await deps.agents.get_agent_for_account(job.clinic_id, account)
    key = effective_profile_key(account.policy_profile, agent.policy_profile)
    profile = DEFAULT_PROFILES[key]
    base = PolicyContext(
        clinic_id=job.clinic_id,
        account_id=job.account_id,
        agent_id=agent.id,
        channel=account.channel,
        thread_id=job.thread_id,
        profile=profile,
        isolated=isolated,
        patient_id=job.patient_id,
    )
    if not profile.require_identity_verification:
        return base
    status = await deps.hooks.verify_identity(base, account.channel, job.thread_id)
    return replace(
        base,
        identity_verified=status.verified,
        patient_id=status.patient_id if status.patient_id is not None else job.patient_id,
    )


def _as_create_input(job: ScheduledJob, time_zone: str, now: datetime) -> CreateScheduledJobInput:
    """The shape ``PolicyHooks.check_job`` takes, rebuilt from a stored job."""
    return CreateScheduledJobInput(
        clinic_id=job.clinic_id,
        account_id=job.account_id,
        thread_id=job.thread_id,
        thread_type=job.thread_type,
        name=job.name,
        kind=job.kind,
        payload=job.payload,
        schedule=schedule_of(job, time_zone),
        timezone=job.timezone,
        max_runs=job.max_runs,
        created_by=job.created_by,
        now=now,
        dedupe_key=job.dedupe_key,
        patient_id=job.patient_id,
        origin=job.origin,
    )


async def decide_job(
    deps: SchedulerDeps, ctx: PolicyContext, job_input: CreateScheduledJobInput
) -> JobDecision:
    """``check_job`` + the profile rule (see the module docstring). Used at creation and at every run."""
    decision = await deps.hooks.check_job(ctx, job_input)
    if decision.action is JobAction.ALLOW and not job_kind_allowed(ctx.profile, job_input.kind):
        return JobDecision(
            action=JobAction.DOWNGRADE_TO_DRAFT,
            reason="Hồ sơ chính sách chỉ cho phép tin theo mẫu đã duyệt; việc của agent chỉ soạn nháp.",
        )
    return decision


async def decide_job_at_run(
    deps: SchedulerDeps, ctx: PolicyContext, job: ScheduledJob, time_zone: str, now: datetime
) -> JobDecision:
    return await decide_job(deps, ctx, _as_create_input(job, time_zone, now))


async def decide_outbound(
    deps: SchedulerDeps, rc: RunContext, text: str, origin: OutboundOrigin
) -> OutboundDecision:
    """``on_outbound`` + the profile rule: under ``OutboundMode.REVIEW`` (``patient_channel``) or when the job
    is draft-only, a ``send`` answer is turned into ``hold_for_review`` - nothing proactive leaves the system
    without a human decision, whatever the hooks say."""
    decision = await deps.hooks.on_outbound(rc.policy, text, proactive=True, origin=origin)
    must_review = rc.draft_only or rc.policy.profile.outbound_mode is OutboundMode.REVIEW
    if decision.action is OutboundAction.SEND and must_review:
        return OutboundDecision(action=OutboundAction.HOLD_FOR_REVIEW, reason=decision.reason)
    return decision


def default_time_zone_of(job: ScheduledJob) -> str:
    """``job.timezone`` pinned on the row, else the CURRENT ``BOT_TIMEZONE``."""
    return job.timezone or bot_time_zone()


def is_message_kind(job: ScheduledJob) -> bool:
    return job.kind is JobKind.MESSAGE
