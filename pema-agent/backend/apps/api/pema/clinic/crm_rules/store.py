# new module (not a port): crm-automation.js kept its state in the browser (localStorage)
"""Persistence port of the CRM rule runner, and an in-memory implementation for tests and package G.

``CrmRuleStore`` is the only thing the runner needs from the database: load a clinic's rules, patient
snapshots, stored tasks and approved templates in a few bulk reads, and apply the outcome of a run in ONE
transaction. ``SqlCrmRuleStore`` (``sql_store.py``) implements it over Postgres as role ``be_app``
(CONTRACTS section 7, decision 7: the rules read broad clinic data, so they run in the API process or a CLI,
never as ``agent_worker``).

``apply`` MUST be idempotent: a task whose key exists is skipped (``ON CONFLICT DO NOTHING``), a task is
superseded only while it is still open or rescheduled, a patient update is a plain overwrite of the same
values.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pema.clinic.crm_rules.records import (
    OPEN_STATUSES,
    ClinicCrmData,
    ExistingTask,
    PatientCrmUpdate,
    PatientSnapshot,
    TaskCandidate,
    TemplateRef,
)
from pema.clinic.crm_rules.rules import DEFAULT_RULES, RuleConfig
from pema_contracts.crm import TaskStatus


@dataclass(frozen=True, slots=True)
class StoreChanges:
    """What one run decided, to be applied atomically."""

    new_tasks: tuple[TaskCandidate, ...]
    superseded_keys: tuple[str, ...]
    patient_updates: tuple[PatientCrmUpdate, ...]
    now: datetime


class CrmRuleStore(Protocol):
    async def ensure_rules(self, clinic_id: UUID) -> None:
        """Seed the ten default rules of a clinic that has none (idempotent)."""
        ...

    async def load(self, clinic_id: UUID, now: datetime) -> ClinicCrmData: ...

    async def apply(self, clinic_id: UUID, changes: StoreChanges) -> int:
        """Apply ``changes`` in one transaction (audited). Returns how many tasks were actually inserted."""
        ...


class MemoryCrmRuleStore:
    """Dict-based store: the reference semantics of ``apply`` that the SQL store must match."""

    def __init__(
        self,
        *,
        rules: Sequence[RuleConfig] = DEFAULT_RULES,
        patients: Sequence[PatientSnapshot] = (),
        tasks: Sequence[ExistingTask] = (),
        templates: Sequence[TemplateRef] = (),
    ) -> None:
        self.rules: list[RuleConfig] = list(rules)
        self.patients: dict[UUID, PatientSnapshot] = {p.id: p for p in patients}
        self.tasks: dict[str, ExistingTask] = {t.task_key: t for t in tasks}
        self.templates: dict[str, TemplateRef] = {t.key: t for t in templates}
        self.created: dict[str, TaskCandidate] = {}
        self.superseded_at: dict[str, datetime] = {}
        self.audit: list[dict[str, int]] = []

    async def ensure_rules(self, clinic_id: UUID) -> None:
        if not self.rules:
            self.rules = list(DEFAULT_RULES)

    async def load(self, clinic_id: UUID, now: datetime) -> ClinicCrmData:
        return ClinicCrmData(
            rules=tuple(self.rules),
            patients=tuple(self.patients.values()),
            existing_tasks=tuple(self.tasks.values()),
            templates=dict(self.templates),
        )

    async def apply(self, clinic_id: UUID, changes: StoreChanges) -> int:
        inserted = 0
        for task in changes.new_tasks:
            if task.task_key in self.tasks:
                continue
            self.tasks[task.task_key] = ExistingTask(task.task_key, task.rule_key, TaskStatus.OPEN)
            self.created[task.task_key] = task
            inserted += 1
        for key in changes.superseded_keys:
            current = self.tasks.get(key)
            if current is not None and current.status in OPEN_STATUSES:
                self.tasks[key] = replace(current, status=TaskStatus.SUPERSEDED)
                self.superseded_at[key] = changes.now
        for update in changes.patient_updates:
            patient = self.patients.get(update.patient_id)
            if patient is None:
                continue
            self.patients[update.patient_id] = replace(
                patient,
                recommendation_at=update.recommendation_at,
                expected_visit_source=update.expected_visit_source,
                expected_visit_reason=update.expected_visit_reason,
                last_protocol_session_id=update.last_protocol_session_id,
            )
        self.audit.append(
            {
                "new_tasks": inserted,
                "superseded": len(changes.superseded_keys),
                "patient_updates": len(changes.patient_updates),
            }
        )
        return inserted
