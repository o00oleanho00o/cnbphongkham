# new module (not a port): the browser ran the rules on every render; here a run is an explicit job
"""One run of the CRM rules for a clinic: load, decide (pure), persist the staff tasks.

    store.load -> run_rules (engine, pure) -> store.apply (one transaction, audited)

Run it from an API-process task or a CLI as ``be_app``. It is safe to run as often as wanted and from two
places at once: tasks are keyed by rule + patient + source event and ``apply`` skips keys that exist.

Branch feat/agent-v2: the CRM no longer schedules messages itself. The rules create the CSKH tasks of
"Việc hôm nay"; sending anything to a customer belongs to the (future) agent service, which reads the tasks
through the API. That is why there is no scheduler here any more.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pema.clinic.crm_rules.engine import run_rules
from pema.clinic.crm_rules.store import CrmRuleStore, StoreChanges
from pema.live import emit_live
from pema.shared.logger import create_logger
from pema_contracts.common import now_vn
from pema_contracts.live import LiveEventType

_log = create_logger("crm_rules")


@dataclass(frozen=True, slots=True)
class RunReport:
    clinic_id: UUID
    patients: int
    candidates: int
    tasks_created: int
    tasks_superseded: int
    patients_updated: int


class CrmRulesRunner:
    def __init__(self, store: CrmRuleStore) -> None:
        self._store = store

    async def run_clinic(self, clinic_id: UUID, now: datetime | None = None) -> RunReport:
        moment = now if now is not None else now_vn()
        await self._store.ensure_rules(clinic_id)
        data = await self._store.load(clinic_id, moment)

        outcome = run_rules(data.patients, data.rules, data.existing_tasks, moment, data.protocols)
        inserted = await self._store.apply(
            clinic_id,
            StoreChanges(
                new_tasks=outcome.new_tasks,
                superseded_keys=outcome.superseded_keys,
                patient_updates=outcome.patient_updates,
                now=moment,
            ),
        )
        if inserted or outcome.superseded_keys:
            emit_live(LiveEventType.TASKS_CHANGED)  # after the commit of ``apply``: "Việc hôm nay" reloads

        report = RunReport(
            clinic_id=clinic_id,
            patients=len(data.patients),
            candidates=len(outcome.candidates),
            tasks_created=inserted,
            tasks_superseded=len(outcome.superseded_keys),
            patients_updated=len(outcome.patient_updates),
        )
        _log.info(
            "crm rules run",
            clinic_id=str(clinic_id),
            patients=report.patients,
            candidates=report.candidates,
            tasks_created=report.tasks_created,
            tasks_superseded=report.tasks_superseded,
        )
        return report


__all__ = ["CrmRulesRunner", "RunReport"]
