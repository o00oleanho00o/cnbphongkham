"""The per-test environment of the scheduler tests: a fresh clinic on a real Postgres plus the fakes of
``pema.scheduler.testing`` (new module, no zalo-agent source). Import in tests only.

Lives in the package (not in ``conftest.py``) so the test modules can import ``Env`` and the constants
for typing
without relying on ``conftest`` being importable under ``--import-mode=importlib``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Engine, text

from pema.channels.registry import InMemoryChannelRegistry
from pema.core.db import ClinicDatabase
from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.testing import FakeClinicActions, FakeEngine, FakeHistory, FakeOutbound, FakeUsage
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.scheduler import (
    CreateScheduledJobInput,
    JobKind,
    JobOrigin,
    OnceSchedule,
    ParsedSchedule,
    ScheduledJob,
)
from pema_contracts.testing import FakeChannel, InMemoryAccountStore, InMemoryAgentStore

ACC = "acc-s"
AGENT = "agent-s"


@dataclass
class Env:
    clinic_id: uuid.UUID
    db: ClinicDatabase
    admin: Engine
    deps: SchedulerDeps
    channel: FakeChannel
    registry: InMemoryChannelRegistry
    history: FakeHistory
    usage: FakeUsage
    engine: FakeEngine
    outbound: FakeOutbound
    actions: FakeClinicActions
    accounts: InMemoryAccountStore
    agents: InMemoryAgentStore
    profile: PolicyProfileKey
    extra_dbs: list[ClinicDatabase] = field(default_factory=list[ClinicDatabase])

    def make_thread(self, thread_id: str, *, bot_enabled: bool = True, account_id: str = ACC) -> None:
        with self.admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO agent.threads (clinic_id, account_id, thread_id, thread_type, bot_enabled) "
                    "VALUES (:c, :a, :t, 0, :b) ON CONFLICT DO NOTHING"
                ),
                {"c": self.clinic_id, "a": account_id, "t": thread_id, "b": bot_enabled},
            )

    def set_bot_enabled(self, thread_id: str, enabled: bool) -> None:
        with self.admin.begin() as conn:
            conn.execute(
                text("UPDATE agent.threads SET bot_enabled = :b WHERE clinic_id = :c AND thread_id = :t"),
                {"c": self.clinic_id, "t": thread_id, "b": enabled},
            )

    def add_patient(self, code: str, *, marketing_opt_out: bool = False) -> uuid.UUID:
        """A synthetic patient (code + opt-out only: the scheduler never reads anything else)."""
        patient_id = uuid.uuid4()
        with self.admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinic.patient (id, clinic_id, code, full_name, marketing_opt_out) "
                    "VALUES (:id, :c, :code, 'Synthetic Patient', :opt)"
                ),
                {"id": patient_id, "c": self.clinic_id, "code": code, "opt": marketing_opt_out},
            )
        return patient_id

    def add_template(self, key: str, body: str, *, marketing: bool = False, approved: bool = True) -> None:
        """A message template; ``approved=False`` stores it inactive and unapproved (no doctor signature)."""
        with self.admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinic.message_template (clinic_id, template_key, title, body, marketing, active, "  # noqa: E501
                    "approved_at) VALUES (:c, :key, :key, :body, :marketing, :active, "
                    "CASE WHEN :active THEN now() ELSE NULL END)"
                ),
                {"c": self.clinic_id, "key": key, "body": body, "marketing": marketing, "active": approved},
            )

    def go_offline(self) -> None:
        self.registry.unregister(self.clinic_id, ACC)

    def go_online(self) -> None:
        self.registry.register(self.clinic_id, self.channel)

    def row(self, sql: str, **params: object) -> tuple[object, ...] | None:
        with self.admin.begin() as conn:
            row = conn.execute(text(sql), {"c": self.clinic_id, **params}).first()
        return None if row is None else tuple(row)

    def execute(self, sql: str, **params: object) -> None:
        with self.admin.begin() as conn:
            conn.execute(text(sql), {"c": self.clinic_id, **params})

    async def make_job(
        self,
        *,
        thread_id: str = "t-1",
        schedule: ParsedSchedule | None = None,
        kind: JobKind = JobKind.MESSAGE,
        payload: str = "nội dung mặc định",
        name: str = "job test",
        thread_type: int = 0,
        now: datetime | None = None,
        max_runs: int | None = None,
        timezone: str = "",
        dedupe_key: str | None = None,
        patient_id: uuid.UUID | None = None,
        origin: JobOrigin = JobOrigin.AGENT_TOOL,
        account_id: str = ACC,
    ) -> ScheduledJob:
        self.make_thread(thread_id, account_id=account_id)
        return await self.deps.jobs.create_job(
            CreateScheduledJobInput(
                clinic_id=self.clinic_id,
                account_id=account_id,
                thread_id=thread_id,
                thread_type=thread_type,
                name=name,
                kind=kind,
                payload=payload,
                schedule=schedule or OnceSchedule(run_at_utc="2026-08-01T08:00:00.000Z"),
                timezone=timezone,
                max_runs=max_runs,
                created_by="user-1",
                now=now or datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
                dedupe_key=dedupe_key,
                patient_id=patient_id,
                origin=origin,
            )
        )
