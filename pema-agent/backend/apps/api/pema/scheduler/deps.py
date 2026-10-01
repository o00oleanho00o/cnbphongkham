"""Everything the scheduler needs, wired once (new module, no zalo-agent source).

The original modules reached their collaborators through module-level singletons (``db``, ``getTuning``,
``getRunningAccountKenh``, ...). Here every collaborator is explicit: external ports first (implemented by
other packages, see ``pema.scheduler.ports``), then the stores built from the database. Package G constructs
one ``SchedulerDeps`` per worker process; tests construct it with fakes.

The default policy is ``PermissivePolicyHooks``, which is the ``staff_assistant`` behaviour. The scheduler
still consults the PROFILE of the account/agent (``PolicyContext.profile``) and enforces the
review-before-send rule of ``patient_channel`` by itself even when the injected hooks are permissive: clinic
safety must not depend on package P being wired."""

from __future__ import annotations

import os
import secrets
import socket

from pema.core.db import ClinicDatabase
from pema.scheduler.delivery_attempt_store import DeliveryAttemptStore
from pema.scheduler.job_run_log_store import JobRunLogStore
from pema.scheduler.pg_readers import (
    PgApprovedTemplateReader,
    PgChannelPolicyReader,
    PgPatientRefReader,
    PgThreadStatusReader,
)
from pema.scheduler.ports import (
    ApprovedTemplateReader,
    ChannelPolicyReader,
    OutboundPipeline,
    PatientRefReader,
    SendGate,
    ThreadStatusReader,
    WrapUntrustedContent,
)
from pema.scheduler.proactive_send_counter_store import ProactiveSendCounterStore
from pema.scheduler.proactive_send_guard import ProactiveSendGuardService
from pema.scheduler.proactive_send_queue import ProactiveSendQueue
from pema.scheduler.scheduled_job_list_store import ScheduledJobListStore
from pema.scheduler.scheduled_job_store import ScheduledJobStore
from pema_contracts.agent_turn import AgentEngine, ThreadLock
from pema_contracts.agents import AccountStore, AgentStore
from pema_contracts.channel import ChannelRegistry
from pema_contracts.clinic_actions import AgentFacingClinicActions
from pema_contracts.conversation import HistoryStore, UsageStore
from pema_contracts.policy import PermissivePolicyHooks, PolicyHooks

DEFAULT_STALE_RUN_SECONDS = 120.0
"""A ``running`` row with a heartbeat older than this belongs to a dead worker."""

DEFAULT_HEARTBEAT_SECONDS = 30.0
"""How often a running job proves its worker is alive: 4 beats fit in the stale window."""


def default_worker_id() -> str:
    """Unique per process (host, pid, random): two live processes never share it."""
    return f"{socket.gethostname()}-{os.getpid()}-{secrets.token_hex(3)}"


class SchedulerDeps:
    def __init__(
        self,
        *,
        db: ClinicDatabase,
        channels: ChannelRegistry,
        accounts: AccountStore,
        agents: AgentStore,
        history: HistoryStore,
        usage: UsageStore,
        engine: AgentEngine,
        outbound: OutboundPipeline,
        thread_lock: ThreadLock,
        clinic_actions: AgentFacingClinicActions,
        wrap_untrusted: WrapUntrustedContent,
        hooks: PolicyHooks | None = None,
        threads: ThreadStatusReader | None = None,
        channel_policy: ChannelPolicyReader | None = None,
        templates: ApprovedTemplateReader | None = None,
        patients: PatientRefReader | None = None,
        send_gate: SendGate | None = None,
        worker_id: str | None = None,
        stale_run_seconds: float = DEFAULT_STALE_RUN_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    ) -> None:
        self.db = db
        self.channels = channels
        self.accounts = accounts
        self.agents = agents
        self.history = history
        self.usage = usage
        self.engine = engine
        self.outbound = outbound
        self.thread_lock = thread_lock
        self.clinic_actions = clinic_actions
        self.wrap_untrusted = wrap_untrusted
        self.hooks: PolicyHooks = hooks if hooks is not None else PermissivePolicyHooks()
        self.threads: ThreadStatusReader = threads if threads is not None else PgThreadStatusReader(db)
        self.channel_policy: ChannelPolicyReader = (
            channel_policy if channel_policy is not None else PgChannelPolicyReader(db)
        )
        self.templates: ApprovedTemplateReader = (
            templates if templates is not None else PgApprovedTemplateReader(db)
        )
        self.patients: PatientRefReader = patients if patients is not None else PgPatientRefReader(db)
        self.worker_id = worker_id if worker_id is not None else default_worker_id()
        self.stale_run_seconds = stale_run_seconds
        self.heartbeat_seconds = heartbeat_seconds

        self.jobs = ScheduledJobStore(db)
        self.job_list = ScheduledJobListStore(db)
        self.runs = JobRunLogStore(db)
        self.attempts = DeliveryAttemptStore(db)
        self.counters = ProactiveSendCounterStore(db)
        self.guard = ProactiveSendGuardService(self.counters, channels, self.threads, self.channel_policy)
        self.queue = ProactiveSendQueue(thread_lock, send_gate)
