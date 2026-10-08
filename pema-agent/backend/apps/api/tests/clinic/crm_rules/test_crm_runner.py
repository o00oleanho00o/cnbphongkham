# new tests (orchestration of the ported engine; no JavaScript original)
"""One run of the rules over a clinic with the in-memory store.

What these pin: a run is idempotent, it creates and supersedes staff tasks only, and it writes the D+30
recommendation once. Since branch feat/agent-v2 the CRM schedules no messages: sending belongs to a future
agent service.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from uuid import UUID, uuid4

from pema.clinic.crm_rules.records import PatientSnapshot, TemplateRef
from pema.clinic.crm_rules.rules import DEFAULT_RULES, RuleConfig
from pema.clinic.crm_rules.runner import CrmRulesRunner
from pema.clinic.crm_rules.store import MemoryCrmRuleStore
from pema.clinic.crm_rules.testing import NOW, appointment, make_patient, session
from pema_contracts.crm import RuleSendMode

CLINIC: UUID = uuid4()
TODAY = date(2026, 9, 20)


def _rules(**modes: RuleSendMode) -> tuple[RuleConfig, ...]:
    return tuple(replace(r, send_mode=modes.get(r.key.value, r.send_mode)) for r in DEFAULT_RULES)


def _laser_patient(code: str = "P025", **fields: object) -> PatientSnapshot:
    base: dict[str, object] = {
        "last_visit": TODAY - timedelta(days=1),
        "sessions": (session("s-laser", TODAY - timedelta(days=1), "laser-co2"),),
        "total_sessions": 5,
        "completed_sessions": 1,
        "messaging_consent": True,
    }
    return make_patient(code, **{**base, **fields})


async def test_a_run_creates_the_tasks_and_a_rerun_creates_nothing() -> None:
    """Chạy một lần tạo đủ việc; chạy lại không tạo thêm việc nào."""
    store = MemoryCrmRuleStore(
        rules=_rules(d1=RuleSendMode.AUTO_REMINDER),
        patients=[_laser_patient()],
        templates=[TemplateRef("crm.d1")],
    )
    runner = CrmRulesRunner(store)

    first = await runner.run_clinic(CLINIC, NOW)
    assert first.tasks_created == 3  # d1, d3, d7

    second = await runner.run_clinic(CLINIC, NOW)
    assert (second.tasks_created, second.tasks_superseded, second.patients_updated) == (0, 0, 0)


async def test_the_first_run_applies_the_d30_recommendation_to_the_patient() -> None:
    """Lần chạy đầu ghi khuyến nghị D+30 cho hồ sơ và lần sau không ghi lại."""
    patient = _laser_patient()
    store = MemoryCrmRuleStore(patients=[patient])
    runner = CrmRulesRunner(store)
    first = await runner.run_clinic(CLINIC, NOW)
    stored = store.patients[patient.id]
    assert first.patients_updated == 1
    assert stored.recommendation_at == TODAY - timedelta(days=1) + timedelta(days=30)
    assert stored.last_protocol_session_id == "s-laser"
    assert (await runner.run_clinic(CLINIC, NOW)).patients_updated == 0


async def test_a_booking_supersedes_the_task() -> None:
    """Đặt lịch làm việc chăm sóc cũ bị thay thế."""
    old = TODAY - timedelta(days=95)
    patient = make_patient("P031", last_visit=old, sessions=(session("c", old),), messaging_consent=True)
    store = MemoryCrmRuleStore(patients=[patient])
    runner = CrmRulesRunner(store)
    assert (await runner.run_clinic(CLINIC, NOW)).tasks_created >= 1

    store.patients[patient.id] = replace(patient, appointments=(appointment("A", TODAY + timedelta(days=7)),))
    report = await runner.run_clinic(CLINIC, NOW)
    assert report.tasks_superseded == 1
