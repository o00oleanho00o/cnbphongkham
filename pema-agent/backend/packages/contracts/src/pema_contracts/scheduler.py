"""Scheduler job model and the ports other packages use to talk to the scheduler (package S).

Ported shape of zalo-agent ``src/scheduler``: ``ScheduledJob`` (scheduled-job-record.ts),
``ParsedSchedule`` / ``ScheduleInput`` (schedule-parser.ts), job run log (job-run-log-store.ts),
proactive send guard (proactive-send-guard.ts) and reply target (scheduled-job-reply-target.ts).
Field names are the snake_case form of the original camelCase names; the invariants documented in
the original stay normative:

* ``kind='once'`` always runs exactly once (``max_runs`` is forced to 1).
* A job that never delivered is not counted as run: ``delivery_attempts`` is incremented on each
  failed delivery and the run slot is only spent after ``MAX_DELIVERY_ATTEMPTS`` failures.
* Proactive messages are capped per (account, thread, local day); the slot is reserved atomically
  before sending and refunded when the send fails.
* A job never creates a job (``schedule_task`` is excluded from scheduled turns).

Additions for the clinic (marked ``# clinic``) are optional and default to the zalo-agent behaviour:
``clinic_id``, ``dedupe_key`` (idempotency for CRM rules: rule + patient + source event),
``patient_id`` and ``origin``. The ``patient_channel`` policy profile decides, through
``PolicyHooks.check_job``, whether an ``agent`` job may run or is downgraded to a review draft.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import Field

from pema_contracts.channel import ThreadKind
from pema_contracts.common import ApiModel, VnDatetime

MAX_DELIVERY_ATTEMPTS = 3
"""``MAX_DELIVERY_ATTEMPTS`` of delivery-attempt-store.ts."""


class JobKind(StrEnum):
    MESSAGE = "message"
    """Send ``payload`` verbatim (a template for ``patient_channel``)."""
    AGENT = "agent"
    """Run an isolated agent turn with ``payload`` as the instruction and send its answer."""


class ScheduleKind(StrEnum):
    ONCE = "once"
    EVERY = "every"
    CRON = "cron"


class JobRunStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    SILENT = "silent"
    SKIPPED = "skipped"
    ERROR = "error"
    INTERRUPTED = "interrupted"


class JobOrigin(StrEnum):  # clinic
    AGENT_TOOL = "agent_tool"
    """Created by the ``schedule_task`` tool during a normal turn."""
    STAFF = "staff"
    """Created from the admin UI."""
    CRM_RULE = "crm_rule"
    """Created by the CRM policy engine (package B2)."""
    SYSTEM = "system"


class OnceSchedule(ApiModel):
    kind: Literal[ScheduleKind.ONCE] = ScheduleKind.ONCE
    run_at_utc: str = Field(description="UTC ISO 8601 with Z, the instant it fires.")


class EverySchedule(ApiModel):
    kind: Literal[ScheduleKind.EVERY] = ScheduleKind.EVERY
    minutes: int = Field(ge=1)


class CronSchedule(ApiModel):
    kind: Literal[ScheduleKind.CRON] = ScheduleKind.CRON
    expr: str
    time_zone: str


type ParsedSchedule = Annotated[OnceSchedule | EverySchedule | CronSchedule, Field(discriminator="kind")]
"""Validated schedule, ready for ``next_run``. Output of ``schedule_parser.parse_schedule``."""


class OnceAtInput(ApiModel):
    """``date`` + ``time`` in the schedule's time zone. The raw datetime string of the LLM is NOT accepted:
    Node/Python would read it in the SERVER zone and shift the hour (schedule-parser.ts)."""

    kind: Literal[ScheduleKind.ONCE] = ScheduleKind.ONCE
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}$")


class OnceInMinutesInput(ApiModel):
    kind: Literal[ScheduleKind.ONCE] = ScheduleKind.ONCE
    in_minutes: int = Field(ge=1)


class EveryInput(ApiModel):
    kind: Literal[ScheduleKind.EVERY] = ScheduleKind.EVERY
    minutes: int = Field(ge=1)


class CronInput(ApiModel):
    kind: Literal[ScheduleKind.CRON] = ScheduleKind.CRON
    expr: str = Field(min_length=1, max_length=120)


type ScheduleInput = OnceAtInput | OnceInMinutesInput | EveryInput | CronInput
"""Raw schedule from a tool call or the admin UI; ``parse_schedule`` turns it into ``ParsedSchedule``
and rejects ``every``/``cron`` denser than ``SCHEDULER_MIN_INTERVAL_MINUTES``."""


class ScheduledJob(ApiModel):
    """A job's CURRENT state. History of runs is ``JobRunRecord``."""

    id: str
    clinic_id: UUID  # clinic
    account_id: str
    thread_id: str
    thread_type: int = Field(description="0 = direct, 1 = group (zca-js ThreadType).")
    name: str
    kind: JobKind
    payload: str
    schedule_kind: ScheduleKind
    run_at: str | None = None
    every_minutes: int | None = None
    cron_expr: str | None = None
    timezone: str = Field(default="", description="Empty = follow BOT_TIMEZONE at run time.")
    enabled: bool = True
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None
    run_count: int = 0
    max_runs: int | None = Field(default=None, description="None = unlimited; 'once' forces 1.")
    delivery_attempts: int = 0
    created_by: str = ""
    created_at: VnDatetime | None = None
    updated_at: VnDatetime | None = None
    dedupe_key: str | None = None  # clinic
    patient_id: UUID | None = None  # clinic
    origin: JobOrigin = JobOrigin.AGENT_TOOL  # clinic


class CreateScheduledJobInput(ApiModel):
    """Port of ``CreateScheduledJobInput`` (scheduled-job-store.ts)."""

    clinic_id: UUID  # clinic
    account_id: str
    thread_id: str
    thread_type: int
    name: str = Field(min_length=1, max_length=200)
    kind: JobKind
    payload: str = Field(min_length=1, max_length=4000)
    schedule: ParsedSchedule
    timezone: str = ""
    max_runs: int | None = None
    created_by: str
    now: VnDatetime | None = Field(default=None, description="Clock for the first next_run_at; tests set it.")
    dedupe_key: str | None = Field(  # clinic
        default=None,
        max_length=200,
        description="When set, a second create with the same key in the same clinic returns the first job.",
    )
    patient_id: UUID | None = None  # clinic
    origin: JobOrigin = JobOrigin.AGENT_TOOL  # clinic


class JobRunRecord(ApiModel):
    id: int
    job_id: str
    turn_id: int | None = None
    status: JobRunStatus
    detail: str = ""
    delivered_chars: int = 0
    started_at: VnDatetime
    finished_at: VnDatetime | None = None


class ProactiveSlotResult(ApiModel):
    reserved: bool
    count: int = 0
    cap: int | None = None


class ProactiveSendGuard(Protocol):
    """Port of proactive-send-guard.ts + proactive-send-counter-store.ts.

    The cap key is chosen by the policy profile (``ProactiveCapScope``): per (account, thread) in
    ``staff_assistant``; per (patient, account) in ``patient_channel``. ``scope_key`` carries it.
    """

    async def reserve_slot(self, scope_key: str, day_key: str, max_per_day: int) -> ProactiveSlotResult:
        """Atomic: ``INSERT ... ON CONFLICT DO UPDATE ... WHERE count < max RETURNING``."""
        ...

    async def refund_slot(self, scope_key: str, day_key: str) -> None: ...

    async def reserve_cap_notice(self, scope_key: str, day_key: str) -> bool:
        """True exactly once per day: the one 'daily cap reached' notice."""
        ...

    async def revert_cap_notice(self, scope_key: str, day_key: str) -> None: ...


class SchedulerPort(Protocol):
    """What the CRM rule engine (B2), the ``schedule_task`` tool (D4) and the admin API call.

    Implemented by ``pema.scheduler.store`` (package S) over Postgres. Every method sets the clinic
    context itself from ``clinic_id`` so callers do not manage RLS.
    """

    async def create_job(self, job: CreateScheduledJobInput) -> ScheduledJob:
        """Computes ``next_run_at``; enforces the ``once``/``max_runs`` invariant and ``dedupe_key``."""
        ...

    async def get_job(
        self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str
    ) -> ScheduledJob | None:
        """Scoped to (account, thread): a tool may only see the jobs of the chat it runs in."""
        ...

    async def get_job_unscoped(self, clinic_id: UUID, job_id: str) -> ScheduledJob | None: ...

    async def list_jobs_for_thread(
        self, clinic_id: UUID, account_id: str, thread_id: str
    ) -> list[ScheduledJob]: ...

    async def list_jobs(self, clinic_id: UUID, account_id: str | None = None) -> list[ScheduledJob]:
        """Admin view; ``account_id=None`` lists every account of the clinic."""
        ...

    async def get_job_by_dedupe_key(self, clinic_id: UUID, dedupe_key: str) -> ScheduledJob | None:
        """The job created with this ``dedupe_key`` (CRM rule + patient + source event), or ``None``. Lets the
        CRM engine find the job it created without storing its id."""
        ...

    async def set_enabled_by_dedupe_key(self, clinic_id: UUID, dedupe_key: str, enabled: bool) -> bool:
        """Switch off (or on) the job of a ``dedupe_key``: the CRM engine disables a waiting job when its
        task is done, superseded, opted out or its template was revoked. ``False`` when no job holds the key.
        A job that already ran stays as it is (``once`` jobs switch themselves off after their run)."""
        ...

    async def set_enabled(
        self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str, enabled: bool
    ) -> bool: ...

    async def delete_job(self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str) -> bool: ...

    async def list_runs(self, clinic_id: UUID, job_id: str, limit: int = 20) -> list[JobRunRecord]: ...

    async def run_trial(self, clinic_id: UUID, job_id: str) -> JobRunRecord:
        """Dry run (run-scheduled-job-trial.ts): runs the job but sends nothing."""
        ...


def thread_kind_of(thread_type: int) -> ThreadKind:
    """zca-js ``ThreadType`` int to ``ThreadKind``. Unknown values (-1 backfill) read as direct."""
    return ThreadKind.GROUP if thread_type == 1 else ThreadKind.USER
